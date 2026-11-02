"""Experimental source-first region selection over immutable rolling task facts."""
from __future__ import annotations

from collections import Counter, defaultdict, deque
from dataclasses import asdict, dataclass
from decimal import Decimal

from .dependency_model import stable_id
from .wait_backtrace import WORK_KINDS


@dataclass(frozen=True)
class RegionOptions:
    source_factor: str = "1.5"
    secondary_factor: str = "2.5"
    similar_fraction: str = "0.9"
    propagation_factor: str = "1.2"
    mad_multiplier: str = "3"
    traversal_limit: int = 4096
    score_population: str = "preliminary_work"

    def validate(self):
        values = {k: Decimal(v) for k, v in asdict(self).items() if k not in {"traversal_limit", "score_population"}}
        if not all(v.is_finite() for v in values.values()):
            raise ValueError("finite region thresholds required")
        if not (1 < values["propagation_factor"] <= values["source_factor"] <= values["secondary_factor"]):
            raise ValueError("require 1 < propagation <= source <= secondary factor")
        if not 0 < values["similar_fraction"] <= 1 or values["mad_multiplier"] < 0 or self.traversal_limit < 1:
            raise ValueError("invalid region similarity, MAD or traversal limit")
        if self.score_population not in {"preliminary_work", "all_comparable_work"}:
            raise ValueError("unknown region score population")


def slow(task, factor, options):
    if task.get("stage") != "measured" or task.get("reference_count") != 5:
        return False
    mean, mad = task.get("reference_mean_ns"), task.get("reference_mad_ns")
    if mean is None or mad is None:
        return False
    mean, mad, value = Decimal(mean), Decimal(mad), Decimal(task["duration_ns"])
    return (value > mean and value >= mean * Decimal(factor)
            and value - mean >= Decimal(options.mad_multiplier) * mad)


def region_key(task):
    return task["node_id"], task["user_rank"], task["operation_scope"]


def select_regions(tasks, options=RegionOptions()):
    options.validate()
    groups = defaultdict(list)
    preliminary = []
    populations, spans = defaultdict(list), {}
    for task in tasks:
        if task.get("stage") == "measured" and task.get("operation_scope"):
            key = region_key(task)
            begin, end = task["observed_start_ns"], task["observed_stop_ns"]
            if key in spans:
                begin, end = min(begin, spans[key][0]), max(end, spans[key][1])
            spans[key] = begin, end
            if (task.get("task_domain") == "hccl_internal" and task.get("task_kind") in WORK_KINDS
                    and task.get("reference_count") == 5 and task.get("reference_mean_ns") is not None):
                populations[key].append(task)
        if (task.get("task_domain") == "hccl_internal" and task.get("task_kind") in WORK_KINDS
                and task.get("operation_scope") and slow(task, options.source_factor, options)):
            groups[region_key(task)].append(task)
            preliminary.append(task)
    regions = []
    for key, members in sorted(groups.items()):
        iterations = {t["iteration"] for t in members}
        if len(iterations) != 1 or None in iterations:
            raise ValueError("a communication region needs a unique measured iteration")
        population = members if options.score_population == "preliminary_work" else populations[key]
        reference = sum(Decimal(t["reference_mean_ns"]) for t in population)
        excess = sum(Decimal(t["duration_ns"]) - Decimal(t["reference_mean_ns"]) for t in population)
        # Reference-duration weights keep a tiny helper's ratio from dominating a call.
        score = excess / reference if reference else None
        regions.append(dict(region_id=stable_id("region", key), node_id=key[0], user_rank=key[1],
            operation_scope=key[2], iteration=members[0]["iteration"], call_site=members[0].get("call_site"),
            start_ns=spans[key][0], stop_ns=spans[key][1],
            preliminary_graph_ids=sorted(t["graph_id"] for t in members),
            preliminary_count=len(members), score_population_count=len(population),
            reference_sum_ns=str(reference), excess_sum_ns=str(excess),
            mean_increase=str(score) if score is not None else None, selected=False, selection_reasons=[]))
    best = max((Decimal(r["mean_increase"]) for r in regions if r["mean_increase"] is not None), default=None)
    for region in regions:
        if region["mean_increase"] is None:
            region["selection_reasons"].append("zero_reference_cannot_rank")
            continue
        score = Decimal(region["mean_increase"])
        if score > 0 and score >= best * Decimal(options.similar_fraction):
            region["selection_reasons"].append("within_similarity_fraction_of_largest_increase")
        if score >= Decimal(options.secondary_factor) - 1:
            region["selection_reasons"].append("exceeds_secondary_increase")
        region["selected"] = bool(region["selection_reasons"])
    regions.sort(key=lambda r: (-(Decimal(r["mean_increase"]) if r["mean_increase"] is not None else Decimal(-1)), r["region_id"]))
    return preliminary, regions


def _edge_status(edge, a, b):
    if "ffts" in edge["kind"]:
        return "ffts_not_complete_hardware_dag"
    if a["node_id"] != b["node_id"]:
        return "uncalibrated_cross_node_boundary"
    if edge["kind"] == "direct_stream_order_observed":
        return "accepted" if a["observed_stop_ns"] <= b["observed_start_ns"] else "incompatible_stream_order_timestamps"
    if a["task_kind"] != "notify_record" or b["task_kind"] != "notify_wait":
        return "unsupported_or_unmeasured_notify_release"
    if a["observed_stop_ns"] > b["observed_stop_ns"]:
        return "incompatible_notify_timestamps"
    if a["observed_stop_ns"] <= b["observed_start_ns"]:
        return "signal_precedes_wait_start"
    return "accepted"


def analyze(tasks, edges, options=RegionOptions()):
    """No truth, baseline capture, inferred edges or unobserved physical cause is input."""
    preliminary, regions = select_regions(tasks, options)
    return analyze_selected_tasks(tasks, edges, preliminary, regions, options)


def analyze_selected_tasks(tasks, edges, preliminary, regions, options, *, include_wait_roots=True):
    """Expand evidence for explicitly selected resource groups without rebuilding edges."""
    nodes = {t["graph_id"]: t for t in tasks}
    if len(nodes) != len(tasks):
        raise ValueError("duplicate task graph identity")
    outgoing, incoming, links = defaultdict(list), defaultdict(list), {}
    for edge in edges:
        if edge["edge_id"] in links:
            raise ValueError("duplicate artifact edge identity")
        if edge["src"] not in nodes or edge["dst"] not in nodes:
            raise ValueError("artifact edge endpoint absent from rolling task facts")
        links[edge["edge_id"]] = edge
        if (edge.get("confidence") in {"observed", "exact"} and (edge["kind"] == "direct_stream_order_observed"
                or "notify_sync" in edge["kind"])):
            outgoing[edge["src"]].append(edge)
            incoming[edge["dst"]].append(edge)
    selected = {r["region_id"]: r for r in regions if r["selected"]}
    selected_by_graph = {}
    selected_scopes = defaultdict(list)
    for region in selected.values():
        selected_scopes[region_key(region)].append(region)
        for key in region["preliminary_graph_ids"]:
            if key in selected_by_graph:
                raise ValueError("resource groups must not overlap")
            selected_by_graph[key] = region
    root_tasks = [t for t in preliminary if t["graph_id"] in selected_by_graph]
    preliminary_ids = {t["graph_id"] for t in preliminary}
    chains, candidates, boundary_counts, visited_edges = [], [], Counter(), {}
    wait_roots = []

    def same_iteration(a, b):
        return (a.get("stage") == b.get("stage") == "measured" and a.get("iteration") is not None
                and a["iteration"] == b.get("iteration"))

    # A Wait's duration may be explained by a producer. An upstream task's late
    # arrival alone cannot explain a Copy/Reduce's increased execution duration.
    def explain_wait(target):
        queue, seen = deque([(target, [])]), set()
        boundaries = Counter()
        while queue and len(seen) < options.traversal_limit:
            current, path = queue.popleft()
            if current["graph_id"] in seen:
                continue
            seen.add(current["graph_id"])
            if path and current["graph_id"] in preliminary_ids:
                return dict(upstream_graph_id=current["graph_id"], edge_ids=path,
                            reason="slow_execution_reached_through_actual_producer", boundaries=dict(boundaries))
            predecessors = incoming[current["graph_id"]]
            if current["task_kind"] == "notify_wait":
                syncs = [e for e in predecessors if "notify_sync" in e["kind"]]
                if len(syncs) != 1:
                    boundaries["missing_or_ambiguous_notify_producer"] += 1
                    continue
                predecessors = syncs
            else:
                predecessors = [e for e in predecessors if e["kind"] == "direct_stream_order_observed"]
                if len(predecessors) != 1:
                    boundaries["missing_or_ambiguous_stream_predecessor"] += 1
                    continue
            for edge in predecessors:
                parent = nodes[edge["src"]]
                status = _edge_status(edge, parent, current)
                if not same_iteration(parent, target):
                    boundaries["iteration_boundary"] += 1
                elif status != "accepted":
                    boundaries[status] += 1
                else:
                    queue.append((parent, [edge["edge_id"]] + path))
        return dict(upstream_graph_id=None, edge_ids=[], boundaries=dict(boundaries),
                    traversal_truncated=bool(queue))

    explained = []
    for task in tasks:
        if (region_key(task) in selected_scopes and task["task_kind"] == "notify_wait"
                and any(task["observed_start_ns"] < r["stop_ns"] and task["observed_stop_ns"] > r["start_ns"]
                        for r in selected_scopes[region_key(task)])
                and slow(task, options.source_factor, options)):
            evidence = explain_wait(task)
            if evidence["upstream_graph_id"]:
                explained.append(dict(graph_id=task["graph_id"], **evidence))
            else:
                wait_roots.append(dict(task, upstream_explanation=evidence))

    def priority(task):
        region = selected_by_graph[task["graph_id"]]
        value = region.get("score", region.get("mean_increase"))
        return value is None, -Decimal(value or 0), -Decimal(task["delta_ns"]), task["graph_id"]
    for root in sorted(root_tasks, key=priority):
        identifier = root["graph_id"]
        paths, queue = {identifier: []}, deque([identifier])
        targets, boundaries, explored = [], Counter(), set()
        while queue and len(explored) < options.traversal_limit:
            current_id = queue.popleft()
            if current_id in explored:
                continue
            explored.add(current_id)
            current = nodes[current_id]
            for edge in outgoing[current_id]:
                target_id = edge["dst"]
                target = nodes[target_id]
                status = _edge_status(edge, current, target)
                if not same_iteration(root, target):
                    boundaries["iteration_boundary"] += 1
                    continue
                if status != "accepted":
                    boundaries[status] += 1
                    continue
                is_sync = "notify_sync" in edge["kind"]
                if is_sync and len([e for e in incoming[target_id] if "notify_sync" in e["kind"]]) != 1:
                    boundaries["ambiguous_notify_producers"] += 1
                    continue
                path = paths[current_id] + [edge["edge_id"]]
                # Order arrival does not explain increased Wait duration: only the
                # actual paired producer can establish that evidence route.
                if is_sync and slow(target, options.propagation_factor, options):
                    chain_id = stable_id("region_chain", (identifier, target_id))
                    if target_id not in targets:
                        chains.append(dict(chain_id=chain_id, source_graph_id=identifier, target_graph_id=target_id,
                            edge_ids=path, source_factor=root["slowdown_factor"], target_factor=target["slowdown_factor"],
                            evidence="actual_dependency_and_observed_slow_wait", causal_contribution_ns=None))
                        targets.append(target_id)
                if target["task_kind"] == "notify_wait" and not slow(target, options.propagation_factor, options):
                    boundaries["wait_below_propagation_threshold"] += 1
                    continue
                if target["task_kind"] in WORK_KINDS and target_id in preliminary_ids and target_id != identifier:
                    # A second intrinsic overrun remains a separate source, rather
                    # than assigning its own execution growth to this predecessor.
                    boundaries["independent_execution_growth"] += 1
                    continue
                visited_edges[edge["edge_id"]] = edge
                if target_id not in paths:
                    paths[target_id] = path
                    queue.append(target_id)
        boundary_counts.update(boundaries)
        candidate = dict(root, candidate_id=stable_id("region_root", (identifier,)),
            region_id=selected_by_graph[identifier]["region_id"], status="unexplained_execution_growth",
            reason="Own execution increased; prior stream arrival is not evidence explaining execution growth",
            affected_wait_graph_ids=targets, boundary_counts=dict(boundaries), traversal_truncated=bool(queue),
            upstream_explained=False, physical_cause="unknown")
        candidates.append(candidate)
    for task in wait_roots if include_wait_roots else ():
        region = next(r for r in selected_scopes[region_key(task)]
                      if task["observed_start_ns"] < r["stop_ns"] and task["observed_stop_ns"] > r["start_ns"])
        candidates.append(dict(task, candidate_id=stable_id("region_wait_root", (task["graph_id"],)),
            region_id=region["region_id"], status="unexplained_wait_candidate",
            reason="No upstream slow execution established within evidence boundaries; root location uncertain",
            affected_wait_graph_ids=[], upstream_explained=False, physical_cause="unknown"))
    used = {c["graph_id"] for c in candidates}
    for chain in chains:
        for key in chain["edge_ids"]:
            used.update((links[key]["src"], links[key]["dst"]))
    return dict(schema_version=1, policy="significant_call_regions_v1", options=asdict(options),
        summary=dict(preliminary_execution_count=len(preliminary), preliminary_region_count=len(regions),
            selected_region_count=len(selected), candidate_count=len(candidates),
            execution_candidate_count=len(root_tasks), unexplained_wait_candidate_count=len(wait_roots) if include_wait_roots else 0,
            unexplained_wait_observation_count=0 if include_wait_roots else len(wait_roots),
            upstream_explained_wait_count=len(explained), propagation_chain_count=len(chains),
            propagated_wait_count=len({c["target_graph_id"] for c in chains}),
            boundary_counts=dict(boundary_counts)),
        regions=regions, candidates=candidates, upstream_explained_tasks=explained, chains=chains,
        unexplained_wait_observations=[] if include_wait_roots else wait_roots,
        nodes={key: nodes[key] for key in sorted(used)},
        edges=[links[key] for key in sorted({key for c in chains for key in c["edge_ids"]})],
        limits=["Experimental opt-in offline policy; original default diagnosis and input facts are unchanged.",
            "Region = one publicly bound collective call on one node/rank; not an inferred fault interval.",
            "Region increase is reference-duration-weighted over the explicitly configured work population, not summed Waits or workload loss.",
            "Select regions within 90% of the maximum or above the configured secondary increase; this policy can select normal outliers.",
            "Waits without an upstream explanation are uncertain candidates, not confirmed physical source tasks.",
            "Record duration ratios are control observations, not independent payload-execution sources.",
            "All reachable branches are visited within the iteration and traversal budget, with one witness path per source/slow-Wait pair, not exponential enumeration of all possible paths.",
            "A second intrinsic execution overrun is independent; ordinary dependency order cannot explain its own longer execution.",
            "A valid dependency plus a longer Wait is propagation evidence, not a measured causal contribution.",
            "Normal/shorter Waits stop propagation; attenuation below 20% is not claimed observable.",
            "No cross-node time subtraction, global critical path, inferred edges or RDMA completion claims."])
