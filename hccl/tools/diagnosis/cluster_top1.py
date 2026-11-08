"""One original dependency cluster; parallel members and time-weighted ranking."""
from __future__ import annotations

from collections import defaultdict
from copy import deepcopy
from dataclasses import asdict
from decimal import Decimal

from .local_slow_clusters import ClusterOptions, build_clusters
from .significant_regions import analyze_selected_tasks
from .source_selection import SelectionOptions, _validate_host


POLICY = "dependency_cluster_top1_time_v1"


def score_cluster(cluster, nodes):
    """Accounting over serial work; never sum parallel streams into elapsed loss."""
    streams = defaultdict(list)
    for identifier in cluster["preliminary_graph_ids"]:
        task = nodes[identifier]
        delta = Decimal(task["duration_ns"]) - Decimal(task["reference_mean_ns"])
        alarm = Decimal(cluster["task_scores"][identifier]["history_alarm_fraction"])
        if delta <= 0 or not Decimal(0) <= alarm <= 1:
            raise ValueError("cluster ranking needs positive execution growth and valid past alarm fraction")
        streams[task["stream_id"]].append((task, delta, delta / (1 + alarm)))
    budgets = []
    for stream, members in sorted(streams.items()):
        ordered = sorted(members, key=lambda entry: (entry[0]["observed_start_ns"], entry[0]["graph_id"]))
        if any(a[0]["observed_stop_ns"] > b[0]["observed_start_ns"] for a, b in zip(ordered, ordered[1:])):
            return dict(score="0", status="overlapping_work_on_one_physical_stream", streams=[])
        budgets.append(dict(stream_id=stream, task_count=len(members),
            execution_excess_ns=str(sum(v[1] for v in members)),
            past_alarm_adjusted_excess_ns=str(sum(v[2] for v in members))))
    score = max((Decimal(v["past_alarm_adjusted_excess_ns"]) for v in budgets), default=Decimal(0))
    return dict(score=str(score), status="rankable", streams=budgets,
        meaning="maximum_serial_stream_execution_excess_discounted_by_past_alarms_not_workload_loss")


def rank(tasks, edges, hosts=(), options=ClusterOptions()):
    """No expected ranks, injection windows, run names or truth are ranking inputs."""
    if options.selection_policy != "top1":
        raise ValueError("this policy always selects at most one dependency cluster")
    preliminary, clusters, quality = build_clusters(tasks, edges, options)
    nodes = {t["graph_id"]: t for t in tasks}
    proposals, host_decisions, accepted_hosts = [], [], {}
    for cluster in clusters:
        budget = score_cluster(cluster, nodes)
        cluster.update(score=budget["score"], time_budget=budget, selected=False)
        proposals.append(dict(proposal_id=cluster["region_id"], mechanism="communication_execution_growth",
            score=budget["score"], node_id=cluster["node_id"], user_rank=cluster["user_rank"],
            iteration=cluster["iteration"], candidate_count=cluster["preliminary_count"],
            candidate_graph_ids=cluster["preliminary_graph_ids"], time_budget=budget))
    thresholds = SelectionOptions(options.source_factor, options.mad_multiplier)
    for host in hosts:
        reason = _validate_host(host, thresholds, allow_inherited_support=False)
        host_decisions.append(dict(source_activity_id=host.get("source_activity_id"), reason=reason or "admitted"))
        if reason:
            continue
        key = host["source_activity_id"]
        if key in accepted_hosts:
            raise ValueError("duplicate Host preparation identity")
        accepted_hosts[key] = host
        delta = Decimal(host["duration_ns"]) - Decimal(host["reference_mean_ns"])
        score = min(delta, Decimal(host["observed_wait_overlap_ns"]))
        proposals.append(dict(proposal_id=key, mechanism="host_preparation_late", score=str(score),
            node_id=host["node_id"], user_rank=host["user_rank"], iteration=host["iteration"],
            candidate_count=1, candidate_graph_ids=[host["anchor_graph_id"]],
            meaning="preparation_growth_capped_by_observed_wait_overlap_not_causal_contribution"))
    proposals.sort(key=lambda p: (-Decimal(p["score"]), p["proposal_id"]))
    chosen = proposals[0] if proposals and Decimal(proposals[0]["score"]) > 0 else None
    selected_id = chosen["proposal_id"] if chosen else None
    for cluster in clusters:
        cluster["selected"] = cluster["region_id"] == selected_id
    return dict(policy=POLICY, options=asdict(options), preliminary=preliminary, clusters=clusters,
        proposals=proposals, selected_proposal=chosen, accepted_hosts=accepted_hosts,
        host_admission=host_decisions, cluster_quality=quality, truth_accessed=False,
        cluster_selection=dict(policy="top1", selected_cluster_id=selected_id,
            selected_mechanism=chosen["mechanism"] if chosen else "unlocalized",
            selected_score_ns=chosen["score"] if chosen else None, selected_cluster_count=int(chosen is not None),
            execution_cluster_count=len(clusters), candidate_relationship="parallel",
            ranking_metric="maximum_past_alarm_adjusted_serial_execution_excess_ns"))


def finalize(report, decision, edges, alignment=None):
    options = ClusterOptions(**decision["options"])
    groups = [c for c in decision["clusters"] if c["selected"]]
    probe = analyze_selected_tasks(report["tasks"], edges, decision["preliminary"], groups, options,
                                   include_wait_roots=False, alignment=alignment)
    roots = []
    for candidate in probe["candidates"]:
        paths = [c for c in probe["chains"] if c["source_graph_id"] == candidate["graph_id"]]
        roots.append(dict(candidate, root_id=candidate["candidate_id"], component="execution", source_unit="execution_task",
            source_selection_policy=POLICY, source_region_id=candidate["region_id"],
            evidence_paths={c["target_graph_id"]: c["edge_ids"] for c in paths},
            dependency_timing={k: v for c in paths for k, v in c.get("timing_evidence", {}).items()}))
    selected = decision["selected_proposal"]
    if selected and selected["mechanism"] == "host_preparation_late":
        host = deepcopy(decision["accepted_hosts"][selected["proposal_id"]])
        host.update(graph_id=host["anchor_graph_id"], source_selection_policy=POLICY, source_unit="host_preparation")
        roots.append(host)
    roots.sort(key=lambda r: (r["observed_start_ns"], r["root_id"]))
    result = dict(decision, candidates=roots, chains=probe["chains"], candidate_relationship="parallel",
        summary=dict(candidate_count=len(roots), selected_cluster_count=int(selected is not None),
                     propagation_chain_count=len(probe["chains"])),
        limits=["The original dependency/locality cluster membership and task/history thresholds are unchanged.",
            "Only one highest-scoring cluster or validated Host interval is selected; its members are peers.",
            "Scores account for local execution growth in nanoseconds, not global critical-path gain or physical causal contribution.",
            "Parallel stream growth is not summed; tiny high-ratio tasks no longer receive equal weight to larger execution growth.",
            "No new dependency, resource-cause label, absolute timing floor, truth window or target rank is introduced.",
            "A genuine larger unrelated overrun can still outrank an injection; this is not calibrated false-alarm control."])
    chosen = dict(report, root_causes=roots, primary_source_candidate_id=None, candidate_admission=None,
        source_regions=[], recommended_candidate_ids=[r["root_id"] for r in roots],
        source_policy_version=POLICY, source_selection_policy=POLICY, candidate_relationship="parallel",
        diagnosis_status="localized_candidate" if roots else "unlocalized", limits=result["limits"])
    return chosen, result


def select(report, edges, alignment=None):
    options = ClusterOptions(source_factor=report["options"]["slowdown_factor"],
                             mad_multiplier=report["options"]["mad_multiplier"])
    hosts = [r for r in report["root_causes"] if r.get("component") == "host_preparation"]
    return finalize(report, rank(report["tasks"], edges, hosts, options), edges, alignment)
