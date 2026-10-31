"""Wait-driven source candidates over existing execution evidence only."""
from __future__ import annotations

from collections import Counter, defaultdict, deque
from . import analyze_waits as waits
from . import compare_diagnosis as comparison
from .dependency_model import stable_id
from .task_classifier import classify_task


WORK_KINDS = frozenset({"sdma", "reduce_inline", "kernel_mix_aic", "kernel_mix_aiv", "kernel_aivec"})


def trace_sources(rows, edges, tasks, options):
    nodes, incoming, _ = comparison.evidence_adjacency(rows, edges, cross_operations=True)
    changes = {t["graph_id"]: t for t in tasks}
    syncs, orders = defaultdict(list), defaultdict(list)
    edge_by_id = {e["edge_id"]: e for e in edges}
    for key, group in incoming.items():
        for src, edge_id in group:
            if "notify_sync" in edge_by_id[edge_id]["kind"]:
                syncs[key].append((src, edge_id))
            else:
                orders[key].append((src, edge_id))
    seeds = [t for t in tasks if t["task_kind"] == "notify_wait" and t["duration_slow"]]
    roots, traces = {}, []
    for seed in sorted(seeds, key=lambda t: t["graph_id"]):
        target = seed["graph_id"]
        trace = dict(wait_graph_id=target, operation_scope=seed["operation_scope"], node_id=seed["node_id"],
                     source_root_ids=[], boundaries=[], release_checks=[], traversal_truncated=False, visited_count=0)
        queue, seen = deque([(target, (), "wait_duration")]), set()

        def boundary(key, path, reason):
            trace["boundaries"].append(dict(graph_id=key, reason=reason, evidence_path_edge_ids=list(path)))

        def source(key, path):
            item = changes[key]
            root_id = stable_id("root", (key, "execution"))
            if root_id not in roots:
                roots[root_id] = dict(item, root_id=root_id, component="execution", status="dependency_supported_candidate",
                    reason="Observed execution overrun reached by tracing a slow Wait through its actual producer and prerequisites; physical cause unknown",
                    affected_wait_graph_ids=[], evidence_paths={}, upstream_slow_graph_ids=[], traversal_truncated=False,
                    source_policy="wait_driven", physical_cause="unknown")
            roots[root_id]["cross_operation"] = (roots[root_id].get("cross_operation", False)
                                                   or item["operation_scope"] != seed["operation_scope"])
            confidence = min((edge_by_id[e]["confidence"] for e in path), key=lambda c: {"observed": 0, "exact": 1}[c])
            root = roots[root_id]
            root["evidence_confidence"] = "observed" if root.get("evidence_confidence") == "observed" else confidence
            if target not in root["affected_wait_graph_ids"]:
                root["affected_wait_graph_ids"].append(target)
                root["evidence_paths"][target] = list(path)
            trace["source_root_ids"].append(root_id)

        def follow_order(key, path):
            predecessors = orders[key]
            if len(predecessors) != 1:
                boundary(key, path, "missing_stream_predecessor" if not predecessors else "ambiguous_stream_predecessors")
                return
            parent, edge_id = predecessors[0]
            if waits.ns(nodes[parent], "stop") > waits.ns(nodes[key], "start"):
                boundary(key, path, "incompatible_stream_order_timestamps")
                return
            queue.append((parent, (edge_id,) + path, "completion"))

        while queue:
            if len(seen) >= options.traversal_limit:
                trace["traversal_truncated"] = True
                break
            key, path, mode = queue.popleft()
            if (key, mode) in seen:
                continue
            seen.add((key, mode))
            row, item = nodes[key], changes[key]
            kind = row.get("profiler_task_kind", "")
            if item.get("stage") == "warmup":
                boundary(key, path, "warmup_boundary")
                continue
            if item.get("iteration") is None or item.get("stage") != "measured":
                boundary(key, path, "missing_iteration_identity")
                continue
            if item["iteration"] != seed["iteration"]:
                boundary(key, path, "iteration_boundary")
                continue
            if kind == "notify_wait":
                if mode == "wait_duration" or item["duration_slow"]:
                    producers = syncs[key]
                    if len(producers) != 1:
                        boundary(key, path, "unpaired_notify_wait" if not producers else "ambiguous_notify_producers")
                    else:
                        producer, edge_id = producers[0]
                        src = nodes[producer]
                        if "ffts" in edge_by_id[edge_id]["kind"] or any(r.get("_subtask_id", -1) >= 0 for r in (src, row)):
                            boundary(key, path, "ffts_timing_not_a_complete_dag")
                            continue
                        if src.get("profiler_task_kind") not in {"notify_record", "rdma"}:
                            boundary(key, path, "unsupported_notify_producer_kind")
                            continue
                        remote = src["_node_id"] != row["_node_id"]
                        timing = "rdma_completion_unmeasured" if src.get("profiler_task_kind") == "rdma" else "remote_clock_boundary"
                        if not remote and src.get("profiler_task_kind") == "notify_record":
                            if waits.ns(src, "stop") > waits.ns(row, "stop"):
                                timing = "incompatible_notify_timestamps"
                            elif waits.ns(src, "stop") <= waits.ns(row, "start"):
                                timing = "signal_precedes_wait_start"
                            else:
                                timing = "producer_observed_during_wait"
                        trace["release_checks"].append(dict(wait_graph_id=key, producer_graph_id=producer,
                                                            edge_id=edge_id, timing_status=timing))
                        if timing in {"incompatible_notify_timestamps", "signal_precedes_wait_start"}:
                            boundary(key, path, timing)
                        else:
                            queue.append((producer, (edge_id,) + path, "completion"))
                if mode != "wait_duration" and (item.get("start_late") or item["gap_slow"]):
                    follow_order(key, path)
                elif mode != "wait_duration" and not item["duration_slow"]:
                    if item["reference_count"] == 5 and item.get("start_late") is False:
                        boundary(key, path, "normal_reference_boundary")
                    else:
                        follow_order(key, path)
                continue
            intrinsic = (item["duration_slow"] and kind in WORK_KINDS
                         and classify_task(row)["task_domain"] == "hccl_internal")
            if intrinsic:
                source(key, path)
                # Execution growth and late release can coexist; preserve both routes.
                if not item.get("start_late") and not item["gap_slow"]:
                    continue
            if item["gap_slow"]:
                boundary(key, path, "unattributed_pre_task_gap")
            if (not intrinsic and item["reference_count"] == 5 and item.get("start_late") is False
                    and not item["gap_slow"] and nodes[key]["_node_id"] == seed["node_id"]):
                boundary(key, path, "normal_reference_boundary")
                continue
            if kind in WORK_KINDS and item["reference_count"] != 5:
                boundary(key, path, "execution_not_comparable:" + item["comparison_status"])
            if kind == "rdma":
                boundary(key, path, "rdma_submission_is_not_payload_completion")
            follow_order(key, path)
        trace["visited_count"] = len(seen)
        trace["source_root_ids"] = sorted(set(trace["source_root_ids"]))
        trace["status"] = "source_candidates_found" if trace["source_root_ids"] else "unresolved_upstream"
        if trace["traversal_truncated"]:
            for root_id in trace["source_root_ids"]:
                roots[root_id]["other_backtrace_branches_truncated"] = True
        traces.append(trace)
    connected = {r["graph_id"] for r in roots.values()}
    observations = []
    for item in tasks:
        key = item["graph_id"]
        if item["duration_slow"] and item["task_kind"] in WORK_KINDS and key not in connected:
            observations.append(dict(item, root_id=stable_id("isolated", (key,)), component="execution", status="isolated_slow_task",
                reason="Execution increased, but no slow Wait backtrace established its propagation",
                affected_wait_graph_ids=[], evidence_paths={}, upstream_slow_graph_ids=[], traversal_truncated=False, physical_cause="unknown"))
        if item["gap_slow"]:
            observation = dict(item, root_id=stable_id("root", (key, "gap")), component="pre_task_gap", status="unattributed_gap",
                reason="Observed gap only; no executing owner is inferred", affected_wait_graph_ids=[], evidence_paths={},
                upstream_slow_graph_ids=[], traversal_truncated=False, physical_cause="unknown")
            observation.update(duration_ns=item["gap_before_ns"], delta_ns=item["gap_delta_ns"],
                               reference_mean_ns=item["reference_gap_mean_ns"], reference_mad_ns=item["reference_gap_mad_ns"])
            observations.append(observation)
    for trace in traces:
        if not trace["source_root_ids"]:
            item = changes[trace["wait_graph_id"]]
            observations.append(dict(item, root_id=stable_id("boundary", (item["graph_id"],)), component="wait_boundary",
                status="unresolved_upstream", reason="Wait-driven backtrace reached explicit evidence boundaries, not a proved root",
                affected_wait_graph_ids=[item["graph_id"]], evidence_paths={item["graph_id"]: []}, upstream_slow_graph_ids=[],
                traversal_truncated=trace["traversal_truncated"], physical_cause="unknown"))
    for root in roots.values():
        root["affected_wait_graph_ids"].sort()
    covered = {w for root in roots.values() for w in root["affected_wait_graph_ids"]}
    for item in tasks:
        item["role"] = ("source_candidate" if item["graph_id"] in connected else "propagated_wait" if item["graph_id"] in covered
                        else "slow_unattributed_task" if item["is_slow"] else "not_flagged")
    return list(roots.values()) + observations, traces


def coverage(tasks, traces):
    eligible = [t for t in tasks if t["stage"] == "measured" and t["iteration"] >= 5]
    reasons = Counter(b["reason"] for trace in traces for b in trace["boundaries"])
    return dict(history_eligible_task_count=len(eligible), comparable_task_count=sum(t["reference_count"] == 5 for t in eligible),
                comparison_status_counts=dict(Counter(t["comparison_status"] for t in eligible)),
                unbound_task_kind_counts=dict(Counter(t["task_kind"] for t in tasks if t["stage"] == "unbound")),
                wait_backtrace_count=len(traces), boundary_reason_counts=dict(reasons),
                truncated_wait_backtrace_count=sum(t["traversal_truncated"] for t in traces))
