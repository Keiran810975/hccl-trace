"""Wait-driven source candidates over existing execution evidence only."""
from __future__ import annotations

from collections import Counter, defaultdict, deque
from decimal import Decimal
from heapq import heappop, heappush
from . import analyze_waits as waits
from . import compare_diagnosis as comparison
from .dependency_model import stable_id
from .task_classifier import classify_task
from .clock_alignment import models_from_report
from .dependency_timing import ORDER, WAIT, cross_node_observation
from . import wait_arrival


WORK_KINDS = frozenset({"sdma", "reduce_inline", "kernel_mix_aic", "kernel_mix_aiv", "kernel_aivec"})


def trace_blocking_wait(gid, graph, progress, limit):
    """Follow observed release and dispatch prerequisites for an online S1 alert."""
    seed = progress.milestone(gid)
    producer = graph.wait_proof(gid)
    gaps, stages, found = set(), {}, {}
    best, settled, queue = {gid: 0}, set(), [(0, gid)]
    next_hop = {}

    def path_from(k):
        path = []
        while k in next_hop:
            proof = next_hop[k]
            path.append(proof)
            k = proof["dst"]
        return path

    while queue and len(settled) < limit:
        cost, key = heappop(queue)
        if key in settled or best[key] != cost:
            continue
        settled.add(key)
        node = progress.milestone(key)
        task = progress.tasks.get(key, {})
        if (task.get("stage") == "warmup" or node["iteration"] is not None and seed["iteration"] is not None
                and not seed["iteration"] - 1 <= node["iteration"] <= seed["iteration"]):
            gaps.add((key, "outside_backtrace_iteration_window"))
            continue
        path = path_from(key)
        if node["intrinsic_work_slow"] and path:
            growth = Decimal(node["duration_delta_ns"])
            found[key] = dict(task=node, path=path, path_slack_and_clock_ns=cost, status=(
                "blocking_overrun_supported" if growth > cost else "upstream_overrun_not_shown_to_block"))
        elif key != gid and node["task_kind"] not in WAIT and not node["duration_comparable"]:
            gaps.add((key, "upstream_task_without_comparable_history"))
        if node["task_kind"] in WAIT:
            release = graph.wait_proof(key)
            if key == gid and not seed["slow_wait"]:
                # A late Wait start precedes the gated interval itself. Its
                # arrival can be delayed by the stream, not by its future release.
                links = [graph.proof(e) for e in graph.orders[key]]
                if not links:
                    gaps.add((key, "missing_stream_or_host_predecessor"))
                if not release["verified"]:
                    gaps.add((key, release["status"]))
            elif release["verified"]:
                links = [release]
                if node["task_kind"] == "event_wait":
                    stage = progress.milestone(release["src"])
                    stages[key] = dict(task=stage, path=[release, *path],
                        status=("readiness_release_late_vs_history" if stage["completion_late"]
                                else "record_observed_during_wait"))
            elif release["status"] == "producer_already_ready":
                # This can explain late dispatch, but not growth of this Wait.
                links = ([graph.proof(e) for e in graph.orders[key]]
                         if node["starts_late"] and (key == gid or not node["slow_wait"]) else [])
                gaps.add((key, release["status"]))
            else:
                links = []
                gaps.add((key, release["status"]))
        else:
            links = [graph.proof(e) for e in graph.orders[key]]
        if not links and node["task_kind"] not in WAIT:
            gaps.add((key, "missing_stream_or_host_predecessor"))
        for proof in links:
            if not proof["verified"]:
                gaps.add((key, proof["status"]))
                continue
            parent = proof["src"]
            extra = proof["slack_ns"] + proof["estimated_error_ns"]
            if parent not in settled and (parent not in best or cost + extra < best[parent]):
                best[parent] = cost + extra
                next_hop[parent] = proof
                heappush(queue, (cost + extra, parent))

    truncated = any(key not in settled for _, key in queue)
    if truncated:
        gaps.add((gid, "backtrace_budget_exhausted"))
    # Prefer supported earlier work on the same path; independent branches survive.
    earlier_on_path = {edge["dst"] for item in found.values()
                       if item["status"] == "blocking_overrun_supported" for edge in item["path"]}
    for key in earlier_on_path & found.keys():
        found[key]["earlier_supported_overrun_on_path"] = True
    ranked = sorted(found.values(), key=lambda item: (
        item["status"] != "blocking_overrun_supported", item.get("earlier_supported_overrun_on_path", False),
        -len(item["path"]), item["task"]["graph_id"]))
    return dict(wait=seed, trigger="wait_duration_growth" if seed["slow_wait"] else "late_wait_start",
                producer=producer, upstream_task_or_stage=[*ranked, *stages.values()],
                evidence_gaps=[dict(graph_id=g, reason=r) for g, r in sorted(gaps)],
                visited_count=len(settled), search_truncated=truncated)


def local_release_check(src, dst, clocks, quantization, local_clocks=None):
    """Compare availability intervals, never rewrite an execution timestamp."""
    keys = ((src["_node_id"], src["_device_id"]), (dst["_node_id"], dst["_device_id"]))
    producer = [waits.ns(src, side) for side in ("start", "stop")]
    waiter = [waits.ns(dst, side) for side in ("start", "stop")]
    if keys[0][0] != keys[1][0]:
        raise ValueError("local Notify release check cannot compare different nodes")
    if keys[0] == keys[1]:
        rs, re = producer
        ws, we = waiter
        uncertainty, domain = 0, "same_profiler_device"
    else:
        local_clocks = local_clocks or {}
        if all(key in local_clocks for key in keys):
            offsets = local_clocks
            uncertainty = sum(offsets[key].estimated_error_ns for key in keys)
        elif all(key in clocks and key in quantization for key in keys):
            offsets = clocks
            uncertainty = sum(quantization[key] for key in keys)
        else:
            return dict(timing_status="missing_same_node_cross_device_clock")
        try:
            rs, re = (offsets[keys[0]].raw_ns(ns) for ns in producer)
            ws, we = (offsets[keys[1]].raw_ns(ns) for ns in waiter)
        except ValueError:
            return dict(timing_status="clock_coverage_boundary")
        domain = "same_node_monotonic_raw"
    if rs - uncertainty > we:
        status = "incompatible_notify_timestamps"
    elif re + uncertainty <= ws:
        status = "signal_precedes_wait_start"
    elif ws < rs - uncertainty and re + uncertainty <= we:
        status = "producer_observed_during_wait"
    else:
        status = "producer_release_interval_compatible"
    return dict(timing_status=status, timing_domain=domain,
                producer_profiler_interval_ns=producer, wait_profiler_interval_ns=waiter,
                producer_interval_ns=[rs, re], wait_interval_ns=[ws, we],
                metadata_uncertainty_ns=uncertainty, exact_release_time_available=False)


def trace_sources(rows, edges, tasks, options, *, alignment=None, local_clocks=None, graph_validated=False):
    if not graph_validated:
        comparison.validate_comparison_graph(rows, edges)
    nodes = {row["_graph_id"]: row for row in rows}
    changes = {t["graph_id"]: t for t in tasks}
    measured = {t["graph_id"] for t in tasks if t["stage"] == "measured"}
    syncs, orders = defaultdict(list), defaultdict(list)
    edge_by_id = {}
    # Keep every predecessor of measured work, including unbound endpoints that stop the backtrace.
    for edge in edges:
        dst, kind = edge["dst"], edge["kind"]
        if dst not in measured or edge.get("confidence") not in {"observed", "exact"}:
            continue
        sync = "notify_sync" in kind
        if not sync and kind != "direct_stream_order_observed":
            continue
        edge_id = edge["edge_id"]
        edge_by_id[edge_id] = edge
        (syncs if sync else orders)[dst].append((edge["src"], edge_id))
    seeds = [t for t in tasks if t["task_kind"] == "notify_wait" and t["duration_slow"]]
    roots, traces = {}, []
    protocol_clocks = models_from_report(alignment)
    calibration = {(item["node_id"], item["device_id"]): item.get("metadata_quantization_ns")
                   for item in (alignment or {}).get("profiler_calibrations", ())}
    quantization = {key: value for key in protocol_clocks
                    if type(value := calibration.get((key[0].rsplit("/", 1)[-1], key[1]))) is int and value >= 0}
    clocks = ({**protocol_clocks, **(local_clocks or {})} if options.calibrated_release_intervals else {})
    arrival_quantization = dict(quantization)
    arrival_quantization.update({key: clock.estimated_error_ns for key, clock in (local_clocks or {}).items()})
    origins = wait_arrival.local_origins(rows, clocks) if clocks else {}
    for seed in sorted(seeds, key=lambda t: t["graph_id"]):
        target = seed["graph_id"]
        trace = dict(wait_graph_id=target, operation_scope=seed["operation_scope"], node_id=seed["node_id"],
                     notify_pairing_status="paired" if len(syncs[target]) == 1 else "unpaired" if not syncs[target] else "ambiguous",
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
            root.setdefault("dependency_timing", {}).update({check["edge_id"]: check
                for check in trace["release_checks"] if check["edge_id"] in path})
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
                uncomparable = not item["reference_count"]
                if uncomparable:
                    boundary(key, path, "notify_wait_not_comparable:" + item["comparison_status"])
                if mode == "wait_duration" or item["duration_slow"] or uncomparable:
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
                        if remote:
                            observation = cross_node_observation(edge_by_id[edge_id], changes[producer], item, protocol_clocks)
                            trace["release_checks"].append(dict(observation, edge_id=edge_id,
                                wait_graph_id=key, producer_graph_id=producer,
                                timing_status=observation["status"], dependency_identity_preserved=True))
                            if observation["status"] == "accepted":
                                queue.append((producer, (edge_id,) + path, "completion"))
                            else:
                                boundary(key, path, observation["status"])
                            if mode != "wait_duration" and (item.get("start_late") or item["gap_slow"]):
                                follow_order(key, path)
                            continue
                        interval = (dict(timing_status="rdma_completion_unmeasured")
                                    if src.get("profiler_task_kind") == "rdma" else
                                    local_release_check(src, row, protocol_clocks, quantization, local_clocks))
                        check = dict(wait_graph_id=key, producer_graph_id=producer,
                                     edge_id=edge_id, dependency_identity_preserved=True, **interval)
                        trace["release_checks"].append(check)
                        if interval["timing_status"] == "producer_observed_during_wait":
                            queue.append((producer, (edge_id,) + path, "completion"))
                        else:
                            boundary(key, path, interval["timing_status"])
                if mode != "wait_duration" and (item.get("start_late") or item["gap_slow"]):
                    follow_order(key, path)
                elif mode != "wait_duration" and not item["duration_slow"]:
                    # A short Wait can inherit its stream's arrival delay. A call
                    # starting earlier than history can conceal that relative delay.
                    follow_order(key, path)
                continue
            overlap_explained = item.get("copy_overlap_explained", False)
            if overlap_explained:
                boundary(key, path, "input_copy_duration_explained_by_overlap")
                if not item.get("start_late") and not item["gap_slow"]:
                    continue
            intrinsic = (item["duration_slow"] and not overlap_explained and kind in WORK_KINDS
                         and classify_task(row)["task_domain"] == "hccl_internal")
            if intrinsic:
                source(key, path)
                # Execution growth and late release can coexist; preserve both routes.
                if not item.get("start_late") and not item["gap_slow"]:
                    continue
            if item["gap_slow"]:
                boundary(key, path, "unattributed_pre_task_gap")
            if kind in WORK_KINDS and not item["reference_count"]:
                boundary(key, path, "execution_not_comparable:" + item["comparison_status"])
            if kind == "rdma":
                boundary(key, path, "rdma_submission_is_not_payload_completion")
            follow_order(key, path)
        trace["visited_count"] = len(seen)
        if len(syncs[target]) == 1 and clocks:
            producer = nodes[syncs[target][0][0]]
            arrival = wait_arrival.observe(nodes[target], producer, seed, nodes, syncs, clocks, arrival_quantization, origins,
                                           comparisons=changes)
            if arrival is not None:
                trace["arrival_observation"] = arrival
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
        if (item["duration_slow"] and not item.get("copy_overlap_explained")
                and item["task_kind"] in WORK_KINDS and key not in connected):
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
                        else "slow_unattributed_task" if item["gap_slow"]
                        else "input_copy_overlap_explained" if item.get("copy_overlap_explained")
                        else "slow_unattributed_task" if item["is_slow"] else "not_flagged")
    return list(roots.values()) + observations, traces


def coverage(tasks, traces, *, minimum_iteration=5):
    eligible = [t for t in tasks if t["stage"] == "measured" and t["iteration"] >= minimum_iteration]
    reasons = Counter(b["reason"] for trace in traces for b in trace["boundaries"])
    return dict(history_eligible_task_count=len(eligible), comparable_task_count=sum(t["reference_count"] > 0 for t in eligible),
                reference_sample_counts=dict(Counter(t["reference_count"] for t in eligible)),
                comparison_status_counts=dict(Counter(t["comparison_status"] for t in eligible)),
                unbound_task_kind_counts=dict(Counter(t["task_kind"] for t in tasks if t["stage"] == "unbound")),
                wait_backtrace_count=len(traces), boundary_reason_counts=dict(reasons),
                paired_slow_wait_count=sum(t["notify_pairing_status"] == "paired" for t in traces),
                unpaired_or_ambiguous_slow_wait_count=sum(t["notify_pairing_status"] != "paired" for t in traces),
                source_linked_slow_wait_count=sum(bool(t["source_root_ids"]) for t in traces),
                upstream_dependency_gap_wait_count=sum(any(b["reason"] in {"missing_stream_predecessor", "unpaired_notify_wait",
                    "ambiguous_stream_predecessors", "ambiguous_notify_producers"} for b in t["boundaries"]) for t in traces),
                timing_conflict_wait_count=sum(any(b["reason"] in {"incompatible_notify_timestamps", "incompatible_stream_order_timestamps"}
                    for b in t["boundaries"]) for t in traces),
                wait_arrival_observation_counts=dict(Counter(t["arrival_observation"]["status"] for t in traces if t.get("arrival_observation"))),
                truncated_wait_backtrace_count=sum(t["traversal_truncated"] for t in traces))
