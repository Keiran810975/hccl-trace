"""Local, dependency-witnessed resource overrun groups; propagation is optional support."""
from __future__ import annotations

from collections import Counter, defaultdict, deque
from dataclasses import asdict, dataclass
from decimal import Decimal

from .dependency_model import stable_id
from .significant_regions import RegionOptions, _edge_status, analyze_selected_tasks, region_key, slow
from .wait_backtrace import WORK_KINDS


@dataclass(frozen=True)
class ClusterOptions:
    source_factor: str = "1.5"
    propagation_factor: str = "1.2"
    mad_multiplier: str = "3"
    locality_factor: str = "2"
    saturation_increase: str = "1.5"
    similar_fraction: str = "0.9"
    propagation_bonus: str = "0.05"
    control_hop_limit: int = 32
    traversal_limit: int = 4096
    selection_policy: str = "top1"

    def validate(self):
        RegionOptions(source_factor=self.source_factor, propagation_factor=self.propagation_factor,
            mad_multiplier=self.mad_multiplier, similar_fraction=self.similar_fraction,
            secondary_factor=str(max(Decimal("2.5"), Decimal(self.source_factor))),
            traversal_limit=self.traversal_limit).validate()
        for key in ("locality_factor", "saturation_increase", "propagation_bonus"):
            value = Decimal(getattr(self, key))
            if not value.is_finite() or value < 0 or key != "propagation_bonus" and value == 0:
                raise ValueError("invalid local cluster scale")
        if Decimal(self.propagation_bonus) > 1 or self.control_hop_limit < 1:
            raise ValueError("invalid cluster bonus or control budget")
        if self.selection_policy not in {"top1", "score-band"}:
            raise ValueError("unknown cluster selection policy")


CONTROL_KINDS = frozenset({"notify_record", "notify_wait", "event_record", "event_wait"})


def _local_key(task):
    return (*region_key(task), task["device_id"], task["iteration"])


def _union_ns(intervals):
    total, last = 0, None
    for begin, end in sorted(intervals):
        total += max(0, end - max(begin, last if last is not None else begin))
        last = max(end, last if last is not None else end)
    return total


def _task_score(task, nodes, options):
    mean, mad = Decimal(task["reference_mean_ns"]), Decimal(task["reference_mad_ns"])
    references = task.get("reference_graph_ids", [])
    if len(references) != 5 or len(set(references)) != 5:
        raise ValueError("a cluster member needs five distinct original history references")
    history = [nodes[key] for key in references]
    if (sorted(t.get("iteration", -1) for t in history) != list(range(task["iteration"] - 5, task["iteration"]))
            or any(t.get("stage") != "measured" or (t["node_id"], t["device_id"], t["user_rank"], t["task_kind"], t.get("call_site"))
                   != (task["node_id"], task["device_id"], task["user_rank"], task["task_kind"], task.get("call_site")) for t in history)):
        raise ValueError("cluster history must retain the verified location and preceding-five boundary")
    comparable = [t for t in history if t.get("reference_count") == 5]
    alarms = sum(slow(t, options.source_factor, options) for t in comparable)
    alarm_fraction = Decimal(alarms) / len(comparable) if comparable else Decimal(0)
    noise_scale = max(mean, Decimal(options.mad_multiplier) * mad)
    severity = min((Decimal(task["duration_ns"]) - mean) / noise_scale, Decimal(options.saturation_increase))
    value = severity / (1 + alarm_fraction)
    return dict(score=str(value), clipped_severity=str(severity), history_alarm_count=alarms,
        history_alarm_reference_count=len(comparable), history_alarm_fraction=str(alarm_fraction),
        reference_relative_mad=str(mad / mean), reference_graph_ids=references,
        evidence="original preceding-five references; their prior alarm state is past-only, never future data")


def build_clusters(tasks, edges, options=ClusterOptions()):
    options.validate()
    nodes = {t["graph_id"]: t for t in tasks}
    if len(nodes) != len(tasks):
        raise ValueError("duplicate resource observation")
    preliminary = [t for t in tasks if t.get("task_domain") == "hccl_internal" and t.get("task_kind") in WORK_KINDS
        and t.get("operation_scope") and slow(t, options.source_factor, options)]
    unrankable = [t["graph_id"] for t in preliminary if Decimal(t["reference_mean_ns"]) <= 0]
    unrankable_ids = set(unrankable)
    preliminary = [t for t in preliminary if t["graph_id"] not in unrankable_ids]
    ids = {t["graph_id"] for t in preliminary}
    scores = {t["graph_id"]: _task_score(t, nodes, options) for t in preliminary}
    adjacency, syncs = defaultdict(list), Counter()
    for edge in edges:
        if edge.get("confidence") not in {"exact", "observed"} or not (
                edge["kind"] == "direct_stream_order_observed" or "notify_sync" in edge["kind"]):
            continue
        a, b = nodes[edge["src"]], nodes[edge["dst"]]
        if "notify_sync" in edge["kind"]:
            syncs[edge["dst"]] += 1
        if _local_key(a) != _local_key(b) or a.get("stage") != "measured":
            continue
        status = _edge_status(edge, a, b)
        # Signal-before-Wait still proves grouping context, never delay propagation.
        if status not in {"accepted", "signal_precedes_wait_start"}:
            continue
        adjacency[edge["src"]].append((edge["dst"], edge, "forward"))
        adjacency[edge["dst"]].append((edge["src"], edge, "reverse"))
    parent = {key: key for key in ids}
    def find(key):
        while parent[key] != key:
            parent[key] = parent[parent[key]]
            key = parent[key]
        return key
    witnesses, bounds = {}, Counter()
    for task in sorted(preliminary, key=lambda t: t["graph_id"]):
        source = task["graph_id"]
        pending, seen = deque([(source, [])]), {source}
        while pending:
            current, path = pending.popleft()
            if len(path) >= options.control_hop_limit:
                bounds["control_hop_limit"] += 1
                continue
            for target_id, edge, direction in adjacency[current]:
                if "notify_sync" in edge["kind"] and syncs[edge["dst"]] != 1:
                    bounds["ambiguous_notify_relation"] += 1
                    continue
                if target_id in seen:
                    continue
                seen.add(target_id)
                target = nodes[target_id]
                next_path = path + [dict(edge_id=edge["edge_id"], direction=direction)]
                if target["task_kind"] in WORK_KINDS:
                    if target_id not in ids:
                        bounds["non_slow_resource_separator"] += 1
                        continue
                    gap = max(0, task["observed_start_ns"] - target["observed_stop_ns"],
                              target["observed_start_ns"] - task["observed_stop_ns"])
                    budget = Decimal(options.locality_factor) * max(Decimal(task["reference_mean_ns"]), Decimal(target["reference_mean_ns"]))
                    if gap > budget:
                        bounds["outside_adaptive_locality"] += 1
                        continue
                    pair = tuple(sorted((source, target_id)))
                    if pair not in witnesses:
                        witnesses[pair] = dict(src=source, dst=target_id, walk=next_path,
                            gap_ns=gap, locality_budget_ns=str(budget),
                            meaning="undirected_actual_dependency_context_not_a_causal_edge")
                    parent[find(source)] = find(target_id)
                elif target["task_kind"] in CONTROL_KINDS:
                    pending.append((target_id, next_path))
                else:
                    bounds["unsupported_intermediate_task"] += 1
    groups = defaultdict(list)
    for task in preliminary:
        groups[find(task["graph_id"])].append(task)
    clusters = []
    for group in groups.values():
        keys = sorted(t["graph_id"] for t in group)
        begin, end = min(t["observed_start_ns"] for t in group), max(t["observed_stop_ns"] for t in group)
        active = _union_ns((t["observed_start_ns"], t["observed_stop_ns"]) for t in group)
        units = defaultdict(list)
        for task in group:
            units[(task["stream_id"], task["task_kind"])].append(Decimal(scores[task["graph_id"]]["score"]))
        unit_means = [sum(values)/len(values) for values in units.values()]
        severity = sum(unit_means) / len(unit_means)
        coherence = Decimal(len(unit_means)) / (len(unit_means) + 1)
        density = Decimal(active) / (end - begin) if end > begin else Decimal(0)
        reference = sum(Decimal(t["reference_mean_ns"]) for t in group)
        excess = sum(Decimal(t["duration_ns"]) - Decimal(t["reference_mean_ns"]) for t in group)
        core = severity * coherence * density
        clusters.append(dict(region_id=stable_id("slow_cluster", keys),
            node_id=group[0]["node_id"], user_rank=group[0]["user_rank"], device_id=group[0]["device_id"],
            operation_scope=group[0]["operation_scope"], iteration=group[0]["iteration"], call_site=group[0].get("call_site"),
            start_ns=begin, stop_ns=end, preliminary_graph_ids=keys, preliminary_count=len(keys),
            mean_increase=str(excess/reference), core_score=str(core), score=str(core),
            task_scores={key: scores[key] for key in keys}, severity=str(severity), coherence=str(coherence),
            evidence_unit_count=len(units), temporal_density=str(density), active_union_ns=active,
            selected=True, selection_reasons=[],
            grouping_witnesses=[w for (a,b),w in witnesses.items() if a in keys and b in keys]))
    return preliminary, clusters, dict(boundary_counts=dict(bounds), unrankable_graph_ids=unrankable)


def selected_cluster_ids(clusters, options, *, metric="score"):
    ranked = sorted((c for c in clusters if Decimal(c[metric]) > 0),
                    key=lambda c: (-Decimal(c[metric]), c["region_id"]))
    if not ranked:
        return set()
    if options.selection_policy == "top1":
        return {ranked[0]["region_id"]}
    floor = Decimal(ranked[0][metric]) * Decimal(options.similar_fraction)
    return {c["region_id"] for c in ranked if Decimal(c[metric]) >= floor}


def analyze(tasks, edges, options=ClusterOptions(), *, alignment=None):
    preliminary, clusters, quality = build_clusters(tasks, edges, options)
    probe = analyze_selected_tasks(tasks, edges, preliminary, clusters, options, include_wait_roots=False, alignment=alignment)
    by_source = {c["graph_id"]: c for c in probe["candidates"]}
    for cluster in clusters:
        targets = {w for key in cluster["preliminary_graph_ids"] for w in by_source[key]["affected_wait_graph_ids"]}
        support = Decimal(len(targets)) / (len(targets) + 1)
        cluster["propagated_wait_count"] = len(targets)
        cluster["propagation_multiplier"] = str(1 + Decimal(options.propagation_bonus) * support)
        cluster["score"] = str(Decimal(cluster["core_score"]) * Decimal(cluster["propagation_multiplier"]))
    chosen = selected_cluster_ids(clusters, options)
    core_chosen = selected_cluster_ids(clusters, options, metric="core_score")
    for cluster in clusters:
        cluster["selected"] = cluster["region_id"] in chosen
        cluster["selected_without_propagation_bonus"] = cluster["region_id"] in core_chosen
        cluster["selection_reasons"] = (["highest_ranked_local_cluster" if options.selection_policy == "top1"
            else "within_similarity_fraction_of_largest_local_score"] if cluster["selected"] else [])
    clusters.sort(key=lambda c: (-Decimal(c["score"]), c["region_id"]))
    selected = {key: c for c in clusters if c["selected"] for key in c["preliminary_graph_ids"]}
    admitted = [dict(c, cluster_score=selected[c["graph_id"]]["score"],
        cluster_core_score=selected[c["graph_id"]]["core_score"],
        cluster_task_score=selected[c["graph_id"]]["task_scores"][c["graph_id"]]["score"])
        for c in probe["candidates"] if c["graph_id"] in selected]
    admitted.sort(key=lambda c: (-Decimal(c["cluster_score"]), -Decimal(c["cluster_task_score"]), -Decimal(c["delta_ns"]), c["graph_id"]))
    admitted_ids = {c["graph_id"] for c in admitted}
    chains = [c for c in probe["chains"] if c["source_graph_id"] in admitted_ids]
    links = {e["edge_id"]: e for e in edges}
    used = set(admitted_ids)
    retained_edges = set()
    for chain in chains:
        retained_edges.update(chain["edge_ids"])
    for cluster in clusters:
        if cluster["selected"]:
            for witness in cluster["grouping_witnesses"]:
                retained_edges.update(step["edge_id"] for step in witness["walk"])
    for key in retained_edges:
        used.update((links[key]["src"], links[key]["dst"]))
    nodes = {t["graph_id"]: t for t in tasks if t["graph_id"] in used}
    unresolved = [w for w in probe["unexplained_wait_observations"] if any(
        c["selected"] and region_key(w) == region_key(c) and w["observed_start_ns"] < c["stop_ns"]
        and w["observed_stop_ns"] > c["start_ns"] for c in clusters)]
    best = Decimal(clusters[0]["score"]) if clusters else Decimal(0)
    return dict(schema_version=1, policy="local_dependency_clusters_v1", options=asdict(options),
        cluster_selection=dict(policy=options.selection_policy,
            primary_cluster_id=clusters[0]["region_id"] if chosen else None,
            tie_break="descending_score_then_stable_cluster_id",
            equal_top_score_cluster_ids=[c["region_id"] for c in clusters if best > 0 and Decimal(c["score"]) == best],
            near_top_deferred_cluster_ids=[c["region_id"] for c in clusters if not c["selected"]
                and best > 0 and Decimal(c["score"]) >= best * Decimal(options.similar_fraction)]),
        summary=dict(preliminary_execution_count=len(preliminary), preliminary_region_count=len(clusters),
            selected_region_count=sum(c["selected"] for c in clusters), candidate_count=len(admitted),
            execution_candidate_count=len(admitted), unexplained_wait_candidate_count=0,
            unexplained_wait_observation_count=len(unresolved), propagation_chain_count=len(chains),
            propagated_wait_count=len({c["target_graph_id"] for c in chains}),
            singleton_cluster_count=sum(c["preliminary_count"] == 1 for c in clusters),
            grouping_quality=quality),
        regions=clusters, candidates=admitted, chains=chains, nodes=nodes,
        edges=[links[key] for key in sorted(retained_edges)], unexplained_wait_observations=unresolved,
        deferred_candidates=[dict(c, deferred_reason="outside_selected_local_cluster_policy") for c in probe["candidates"] if c["graph_id"] not in admitted_ids],
        without_propagation_candidate_ids=[by_source[key]["candidate_id"] for c in clusters if c["selected_without_propagation_bonus"] for key in c["preliminary_graph_ids"]],
        limits=["Exploratory opt-in consumer; no capture, dependency identity or default diagnosis changes.",
            "Grouping uses undirected walks of actual dependencies within one node/device/rank/call, not inferred causal edges or cross-node time subtraction.",
            "Normal resource tasks separate groups. The pair gap budget is twice the larger prior-five resource mean, never an injection-derived time window.",
            "Severity uses preceding-five means/MAD, capped relative excess, and the same preceding-five tasks' already-past alarm frequency. No future samples or truth are read.",
            "Repeated work of one kind on one physical stream is averaged as one evidence unit, a conservative heuristic, not statistical independence.",
            "Temporal density and evidence-unit coherence affect ranking. Singleton sources remain eligible without a slow Wait.",
            "Propagation can add at most the configured bounded bonus; a path is not measured physical causal contribution.",
            "Unexplained Waits are preserved as unresolved observations, not automatically renamed execution roots. Report them alongside task-level candidate precision.",
            "Relative selection ranks the most suspicious available groups; it is not calibrated false-alarm control or proof a physical fault occurred.",
            "Top1 retains every source task and supported path in the highest-ranked cluster, not just one task. Equal scores use a deterministic stable-ID tie break, not truth or temporal proximity.",
            "All deferred execution candidates, equal/near ties and all group scores remain auditable. Top1 can omit genuine additional sources."])
