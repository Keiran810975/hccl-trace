"""Readable source-first views of already reported dependency evidence paths."""
from __future__ import annotations

from collections import Counter

from . import analyze_waits as waits
from .dependency_model import stable_id
from .task_classifier import source_category, INTERNAL, EXTERNAL, UNRESOLVED


METRIC_FIELDS = ("comparison_status", "reference_count", "reference_iterations", "reference_mean_ns",
                 "reference_value_ns", "reference_metric", "delta_ns", "slowdown_factor", "duration_slow", "role")
SOURCE_FIELDS = ("root_id", "component", "node_id", "user_rank", "device_id", "stream_id", "task_id",
                 "source_activity_id",
                 "operation_scope", "iteration", "block", "bucket", "phase", "step", "event", "observed_start_ns",
                 "observed_stop_ns", "duration_ns", "reference_mean_ns", "delta_ns", "slowdown_factor",
                 "reference_iterations", "reference_count", "reason",
                 "physical_cause", "traversal_truncated",
                 "other_backtrace_branches_truncated")
SOURCE_FIELDS += ("group_id", "call_site", "occurrence", "reference_value_ns", "reference_metric", "baseline_median_ns")
SOURCE_FIELDS += ("diagnosis_category", "task_domain", "category_rank", "cross_operation")
SOURCE_FIELDS += ("local_completion_evidence", "dependency_timing", "communication_context")
SOURCE_FIELDS += ("event_slow",)
SOURCE_FIELDS += ("protocol_endpoints", "source_selection_policy", "anchor_graph_id")
SOURCE_FIELDS += ("source_unit",)
SOURCE_FIELDS += ("source_region_id", "source_region_rank", "source_region_budget_ns", "ranking_execution_budget_ns",
                  "ranking_metric", "supported_wait_max_excess_ns", "supported_wait_excess_beyond_source_growth_ns")
LIMITS = [
    "Paths start at reported candidates, not at independently inferred physical faults.",
    "Only existing reported evidence paths are expanded; downstream descendants are not exhaustively searched.",
    "A path and a Wait duration increase do not measure the candidate's individual causal contribution.",
    "Concurrent Wait increases must not be summed as workload completion loss.",
    "Cross-node hops retain independent calibration limits when present; uncalibrated hops remain explicit and no global latency sum is performed.",
    "Host preparation is an observed interval. Its device anchor is not a fabricated Host-to-device edge.",
    "Missing/disconnected paths and incompatible local timestamps stay explicit, without inferred repair.",
]


def node_fact(row, comparison):
    start, stop = waits.ns(row, "start"), waits.ns(row, "stop")
    return dict(graph_id=row["_graph_id"], node_id=row["_node_id"], user_rank=row["_user_rank"],
        device_id=row["_device_id"], stream_id=row["_stream_id"], task_id=row["_task_id"],
        subtask_id=row.get("_subtask_id", -1), operation_scope=row.get("_operation_scope", ""),
        task_kind=row.get("profiler_task_kind", ""), event=row.get("event") or row.get("event_name", ""),
        phase=row.get("phase", ""), step=row.get("step", ""), slice=row.get("slice", ""),
        iteration=comparison.get("iteration"), block=comparison.get("block"), bucket=comparison.get("bucket"),
        group_id=comparison.get("group_id"), call_site=comparison.get("call_site"), occurrence=comparison.get("occurrence"),
        start_ns=start, stop_ns=stop, duration_ns=stop-start,
        comparison={k:comparison.get(k) for k in METRIC_FIELDS})


def timing_check(edge, src, dst):
    if "ffts" in edge["kind"] or any(n["subtask_id"]>=0 for n in (src,dst)):
        return "ffts_not_complete_hardware_dag"
    if src["node_id"] != dst["node_id"]:
        return "cross_node_uncalibrated"
    if edge["kind"] == "direct_stream_order_observed":
        return "compatible_stream_order" if src["stop_ns"] <= dst["start_ns"] else "overlapping_stream_tasks"
    if src["task_kind"] == "rdma":
        return "rdma_submission_not_completion"
    if src["stop_ns"] > dst["stop_ns"]:
        return "record_after_wait_end"
    if src["stop_ns"] <= dst["start_ns"]:
        return "signal_precedes_wait_start"
    return "producer_observed_during_wait"


def build_report(rows, edges, candidates, comparisons=(), *, primary_source_candidate_id=None, reference=None,
                 unresolved_observations=()):
    nodes = {r["_graph_id"]:r for r in rows}
    links = {e["edge_id"]:e for e in edges}
    if len(nodes) != len(rows) or len(links) != len(edges):
        raise ValueError("propagation export requires unique artifact node/edge IDs")
    metrics = {t["graph_id"]:t for t in comparisons}
    facts, exported = {}, []

    def fact(identifier):
        if identifier not in facts:
            facts[identifier] = node_fact(nodes[identifier], metrics.get(identifier, {}))
        return facts[identifier]

    for rank, root in enumerate(candidates, 1):
        if root["component"] not in {"execution", "host_preparation", "protocol_interval"}:
            raise ValueError("only execution and observed Host candidates are supported; not legacy gap roots")
        anchor = root["graph_id"]
        category = source_category(root, nodes.get(anchor, {}))
        if category == UNRESOLVED:
            continue
        item = dict(candidate_id=root["root_id"], candidate_rank=rank,
            diagnosis_category=category,
            primary=category == INTERNAL and root["root_id"] == primary_source_candidate_id,
            source={k:root.get(k) for k in SOURCE_FIELDS}, anchor_graph_id=anchor,
            anchor_meaning="observed_device_anchor_only" if root["component"] in {"host_preparation", "protocol_interval"} else "source_execution",
            status=root["status"], chains=[])
        for target in dict.fromkeys(root.get("affected_wait_graph_ids", [])):
            path = root.get("evidence_paths", {}).get(target)
            chain = dict(chain_id=stable_id("propagation", (root["root_id"], target)), target_wait_graph_id=target,
                         node_ids=[], edge_ids=[], hops=[], boundaries=[], path_complete=False)
            cursor = anchor
            if root["component"]=="host_preparation" and isinstance(path,list) and path and path[0] in links:
                branch_anchor = nodes.get(links[path[0]]["src"])
                if branch_anchor and all(branch_anchor[k]==root[field] for k,field in
                    (("_node_id","node_id"),("_user_rank","user_rank"),("_device_id","device_id"),("_operation_scope","operation_scope"))) and branch_anchor.get("profiler_task_kind") in {"notify_record", "rdma"}:
                    cursor=branch_anchor["_graph_id"]
                else:
                    chain["boundaries"].append(dict(reason="invalid_host_branch_anchor",edge_id=path[0]))
            chain["anchor_graph_id"]=cursor
            if target in nodes:
                fact(target)
            if cursor in nodes:
                fact(cursor)
                chain["node_ids"].append(cursor)
            else:
                chain["boundaries"].append(dict(reason="missing_source_anchor", graph_id=cursor))
            if not isinstance(path, list) or not path:
                chain["boundaries"].append(dict(reason="missing_reported_evidence_path", graph_id=target))
            else:
                seen = {cursor}
                for identifier in path:
                    edge = links.get(identifier)
                    reason = ("missing_artifact_edge" if edge is None else
                              "disconnected_path" if edge["src"] != cursor else
                              "missing_artifact_endpoint" if edge["src"] not in nodes or edge["dst"] not in nodes else
                              "repeated_path_node" if edge["dst"] in seen else
                              "unsupported_evidence" if edge.get("confidence") not in {"observed", "exact"} or
                              not (edge["kind"]=="direct_stream_order_observed" or "notify_sync" in edge["kind"]) else None)
                    if reason:
                        chain["boundaries"].append(dict(reason=reason, edge_id=identifier))
                        break
                    src, dst = fact(edge["src"]), fact(edge["dst"])
                    timing = root.get("dependency_timing", {}).get(identifier)
                    valid_timing = (timing and timing.get("wait_graph_id") == dst["graph_id"]
                                    and timing.get("producer_graph_id") == src["graph_id"]
                                    and timing.get("timing_domain") == "same_node_monotonic_raw"
                                    and src["node_id"] == dst["node_id"]
                                    and timing.get("producer_profiler_interval_ns") == [src["start_ns"], src["stop_ns"]]
                                    and timing.get("wait_profiler_interval_ns") == [dst["start_ns"], dst["stop_ns"]]
                                    and "ffts" not in edge["kind"]
                                    and src["subtask_id"] < 0 and dst["subtask_id"] < 0)
                    protocol_clock = (timing if timing and root.get("source_selection_policy") == "wait_backtrace_v1"
                        and timing.get("timing_domain") == "independent_network_probe_estimate"
                        and timing.get("status") == "accepted" and src["node_id"] != dst["node_id"]
                        and timing.get("source_profiler_interval_ns") == [src["start_ns"], src["stop_ns"]]
                        and timing.get("target_profiler_interval_ns") == [dst["start_ns"], dst["stop_ns"]] else None)
                    chain["hops"].append(dict(edge_id=identifier, src=edge["src"], dst=edge["dst"],
                        kind=edge["kind"], confidence=edge["confidence"], reason=edge.get("reason", ""),
                        timing_status=(timing["timing_status"] if valid_timing else "protocol_dependency_with_estimated_clock_limits"
                            if protocol_clock else timing_check(edge, src, dst)),
                        protocol_clock_evidence=protocol_clock,
                        calibrated_release_evidence=timing if valid_timing else None))
                    chain["edge_ids"].append(identifier)
                    cursor = edge["dst"]
                    seen.add(cursor)
                    chain["node_ids"].append(cursor)
                chain["path_complete"] = (not chain["boundaries"] and cursor==target and
                                           fact(target)["task_kind"]=="notify_wait")
                if not chain["path_complete"] and not chain["boundaries"]:
                    chain["boundaries"].append(dict(reason="path_does_not_end_at_declared_wait", graph_id=cursor))
            chain["evidence_confidence"] = ("observed" if any(h["confidence"]=="observed" for h in chain["hops"])
                                             else "exact" if chain["hops"] else "unavailable")
            chain["timing_warnings"] = [h["edge_id"] for h in chain["hops"] if h["timing_status"] not in
                                        {"compatible_stream_order", "producer_observed_during_wait"}]
            chain["status"] = ("incomplete_evidence" if not chain["path_complete"] else
                               "complete_with_timing_limits" if chain["timing_warnings"] else "complete_observed_path")
            item["chains"].append(chain)
        item["chains"].sort(key=lambda c:(len(c["edge_ids"]), c["target_wait_graph_id"]))
        completion = root.get("local_completion_evidence")
        if completion:
            cursor, identifiers = anchor, [anchor]
            for identifier in completion["edge_ids"]:
                edge = links[identifier]
                if edge["src"] != cursor or edge["confidence"] not in {"observed", "exact"}:
                    raise ValueError("local completion proof is disconnected or unsupported")
                cursor = edge["dst"]
                identifiers.append(cursor)
            if cursor != completion["terminal_graph_id"]:
                raise ValueError("local completion proof ends at the wrong task")
            for identifier in identifiers:
                fact(identifier)
            item["completion_path"] = dict(node_ids=identifiers, edge_ids=completion["edge_ids"],
                                           path_complete=True, slow_wait_propagation_claimed=False)
        exported.append(item)
    chains = [c for root in exported for c in root["chains"]]
    return dict(schema_version=2, kind="source_first_dependency_evidence", primary_source_candidate_id=primary_source_candidate_id,
        summary=dict(candidate_count=sum(c["diagnosis_category"] == INTERNAL for c in exported),
            result_entry_count=len(exported), chain_count=len(chains),
            unique_target_wait_count=len({c["target_wait_graph_id"] for c in chains}),
            complete_chain_count=sum(c["path_complete"] for c in chains),
            communication_source_count=sum(c["diagnosis_category"] == INTERNAL for c in exported),
            external_clue_count=sum(c["diagnosis_category"] == EXTERNAL for c in exported),
            unresolved_observation_count=len(unresolved_observations),
            chain_status_counts=dict(Counter(c["status"] for c in chains))),
        candidates=exported, nodes=facts, unresolved_observations=list(unresolved_observations), limits=LIMITS, candidate_order_changed=False,
        exhaustive_downstream_search=False, physical_causation_proven=False,
        reference=reference or dict(kind="previous_five_measured", statistic="mean", window=5))
