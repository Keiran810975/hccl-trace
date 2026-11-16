"""Use exact archived online alert identities to select offline dependency evidence."""
from __future__ import annotations

from collections import defaultdict
from decimal import Decimal
import json
from pathlib import Path

from hccl_trace.online_probe import tensor_description
from . import downstream_propagation, rank_progress, wait_backtrace
from .dependency_timing import EvidenceGraph, WAIT
from .workload_binder import _read_calls, operation_type


SLOW = {"COMPUTATION_SLOW", "COMMUNICATION_SLOW", "SLOW_UNCLASSIFIED"}  # Last entry reads older archives only.
ROUTES = {"COMPUTATION_SLOW": "S1", "COMMUNICATION_SLOW": "S2", "SLOW_UNCLASSIFIED": "undetermined"}


def alert_path(capture, requested=None, *, configured=None):
    if requested is not None:
        path = Path(requested).resolve()
        return path / "events.jsonl" if path.is_dir() else path
    root = Path(capture).resolve()
    if root.is_file():
        root = root.parent
    locations = [root / "online/events.jsonl"]
    if root.name == "capture":
        locations.append(root.parent / "online/events.jsonl")
    if configured is not None:
        locations.append(configured)
    found = list(dict.fromkeys(p.resolve() for p in locations if p.is_file()))
    if len(found) > 1:
        raise ValueError("multiple online logs found; select one with --online")
    return found[0] if found else None


def load_alerts(path, run_id):
    events = []
    with path.open(encoding="utf-8-sig") as stream:
        for line in stream:
            if not line.strip():
                continue
            event = json.loads(line)
            if event.get("version") != 1 or event.get("job_id") != run_id:
                raise ValueError("online event version or job ID disagrees with capture")
            if event.get("event_type") in SLOW and event.get("stage") == "measured":
                events.append(event)
    return events


def _token(row, names):
    group, generation, counter = (row.get(k) for k in names)
    if (not isinstance(group, str) or not group or type(generation) is not int or generation < 0
            or type(counter) is not int or counter <= 0):
        raise ValueError("online alert or SDK call has an invalid operation token")
    return group, generation, counter


def resolve(events, call_logs, coordinates):
    slots = {(c["group_id"], c["stage"], c["iteration"], c["call_site"], c["occurrence"]): c["operation_scope"]
             for c in coordinates if "group_id" in c}
    pending = {_token(e, ("communicator_id", "communicator_generation", "op_counter")): e for e in events}
    if len(pending) != len(events):
        raise ValueError("duplicate online slowdown token")
    calls = defaultdict(dict)
    for path in call_logs if pending else ():
        header, rows = _read_calls(path)
        rank = header["user_rank"]
        for row in rows:
            if "online_op_counter" not in row:
                continue
            token = _token(row, ("group_id", "online_communicator_generation", "online_op_counter"))
            if token in pending:
                if rank in calls[token] or header["run_id"] != pending[token]["job_id"]:
                    raise ValueError("duplicate or foreign SDK call for online token")
                calls[token][rank] = row

    results = []
    for (group, generation, counter), event in pending.items():
        token = group, generation, counter
        key = group, event["stage"], event["iteration"], event["bucket_id"], event["occurrence"]
        recorded = calls[token]
        first = next(iter(recorded.values()), None)
        participants = first["participants"] if first else []
        if recorded:
            for row in recorded.values():
                _, size = tensor_description(row["dtype"], row["element_count"])
                if ((row["group_id"], row["stage"], row["iteration"], row["call_site"], row["occurrence"]) != key
                        or row["participants"] != participants or size != event["tensor_bytes"]
                        or operation_type(row["operation_type"]) != event["op_type"]):
                    raise ValueError("online token disagrees with SDK location, participants or collective shape")
        # When original collector Rank entries exist, validate the same raw Host observation too.
        for item in event.get("ranks", []):
            rank = item["rank_id"]
            if rank in recorded and (item.get("entry") or {}).get("host_entry_ts") != recorded[rank]["before"]["raw_ns"]:
                raise ValueError("online Rank Host entry does not match the captured SDK call")
        complete = bool(participants) and sorted(recorded) == participants
        scope = slots.get(key) if complete else None
        metrics = event.get("metrics", {})
        roles = {}
        for rank in event.get("ranks", ()):
            timing = rank.get("device") or {}
            roles[rank["rank_id"]] = dict(role=timing.get("rank_role"), algorithm=timing.get("algorithm"),
                verified=bool(timing.get("rank_role") and timing.get("algorithm")
                              and timing.get("timing_profile_id") and metrics.get("timing_boundary_verified")))
        results.append(dict(event_id=event["event_id"], event_type=event["event_type"], group_id=group,
            generation=generation, op_counter=counter, iteration=key[2], bucket=key[3], occurrence=key[4],
            route=ROUTES[event["event_type"]], rank_roles=roles,
            operation_scope=scope, ranks=participants, suspected_ranks=event.get("suspected_ranks"),
            binding_status="bound_exact" if scope else "profiler_operation_not_uniquely_bound" if complete else "incomplete_sdk_token",
            online_metrics={k: metrics.get(k) for k in ("R", "P", "P_relative", "classification_evidence",
                "timing_source", "timing_boundary_verified", "preparation_by_rank")}))
    return results


def _task(t):
    return {k: t.get(k) for k in ("graph_id", "node_id", "user_rank", "stream_id", "task_id", "task_kind",
        "event", "observed_start_ns", "observed_stop_ns", "duration_ns", "reference_mean_ns",
        "delta_ns", "reference_count", "iteration_start_delta_ns", "role")}


def _gate_entry(gate, progress):
    proof = gate["wait"]["wait_producer"]
    paired = proof["status"] in {"verified_producer_during_wait", "producer_already_ready", "clock_order_uncertain",
                                 "producer_after_wait_release", "missing_cross_device_clock", "clock_coverage_boundary",
                                 "rdma_submission_not_payload_completion"}
    producer = progress.milestone(proof["src"]) if paired else None
    return dict(gate, producer=producer, wait_timing=("zero_duration_no_observed_block"
                if gate["wait"]["duration_ns"] == 0 else "wait_interval_observed"))


def _explain(selection, progress, host_observations, protocol_observations):
    graph = progress.graph
    scope = selection["operation_scope"]
    milestones = progress.for_scope(scope)
    observed_ranks = {rank for rank in milestones if rank >= 0}
    ranks = selection["ranks"] or sorted(observed_ranks)
    result = dict(detailed_rank_count=len(observed_ranks & set(ranks)), expected_rank_count=len(ranks))
    all_tasks = [m for rank in ranks for m in milestones[rank]]
    waits = [m for m in all_tasks if m["task_kind"] in WAIT]
    gaps = []
    if not all_tasks:
        gaps.append(dict(reason="no_detailed_tasks_for_bound_operation"))
    if set(ranks) - observed_ranks:
        gaps.append(dict(reason="missing_detailed_rank_tasks", ranks=sorted(set(ranks) - observed_ranks)))
    if any(not m["duration_comparable"] for m in all_tasks):
        gaps.append(dict(reason="incomplete_same_position_history"))
    if any(m["progress_status"] in {"missing_rank_collop_interval", "task_outside_rank_collop_interval"} for m in all_tasks):
        gaps.append(dict(reason="incomplete_rank_collop_device_interval_coverage"))
    entry_waits = ([_gate_entry(gate, progress) for gate in progress.entry_waits(scope)]
                   if selection["route"] in {"S1", "undetermined"} else [])
    unresolved_events = sorted({m["graph_id"] for m in (*waits, *(e["wait"] for e in entry_waits))
                                if m["task_kind"] == "event_wait" and m["wait_producer"]["status"] in
                                {"unresolved_event_dependency", "ambiguous_sync_producer"}})
    gaps.extend(dict(graph_id=g, reason="unresolved_event_dependency") for g in unresolved_events)
    result.update(evidence_gaps=gaps, unresolved_event_wait_ids=unresolved_events, entry_wait_observations=entry_waits)
    route = selection["route"]
    if route in {"S1", "undetermined"}:
        suspect = set(selection["suspected_ranks"] or ())
        observations = [r for r in host_observations if not suspect or r["user_rank"] in suspect]
        result["host_preparation_observation"] = [dict(user_rank=r["user_rank"], node_id=r["node_id"],
            graph_id=r.get("graph_id"), device_id=r.get("device_id"),
            start_ns=r["observed_start_ns"], stop_ns=r["observed_stop_ns"],
            api_start_ns=r.get("api_start_ns"), api_stop_ns=r.get("api_stop_ns"), duration_ns=r["duration_ns"],
            reference_mean_ns=r["reference_mean_ns"], reference_mad_ns=r["reference_mad_ns"],
            delta_ns=r["delta_ns"], reference_count=r["reference_count"],
            related_waits=[dict(graph_id=w, edge_ids=path) for w, path in r.get("evidence_paths", {}).items() if path],
            status=r["status"], cpu_task="unknown") for r in observations]
        if not observations:
            gaps.append(dict(reason="no_comparable_abnormal_host_preparation_interval"))
        if route == "S1":
            result["suspected_rank"] = next(iter(suspect)) if len(suspect) == 1 else None
            starts = progress.latest_entry(scope, ranks)
            result["rank_start_evidence"] = starts
            focus = set(starts["possible_latest_ranks"]) or suspect
            result["entry_dependency_by_rank"] = [
                dict(rank=rank, gates=[e for e in entry_waits if e["wait"]["rank"] == rank],
                     status="observed_entry_wait" if any(e["wait"]["rank"] == rank for e in entry_waits)
                            else "no_verified_wait_on_device_entry")
                for rank in sorted(focus)]
            result["blocking_waits"] = traces = []
            remaining = progress.options.traversal_limit
            scoped_waits = {m["graph_id"]: m for m in [*waits, *(e["wait"] for e in entry_waits)]}
            for item in sorted(scoped_waits.values(), key=lambda m: (m["rank"] not in focus, not m["slow_wait"], m["graph_id"])):
                if not (item["slow_wait"] or item["starts_late"]):
                    continue
                if remaining <= 0:
                    gaps.append(dict(reason="alert_backtrace_budget_exhausted"))
                    break
                trace = wait_backtrace.trace_blocking_wait(item["graph_id"], graph, progress, min(256, remaining))
                remaining -= trace["visited_count"]
                traces.append(trace)
    elif route == "S2":
        searches = []
        result["downstream_propagation"] = searches
        result["downstream_search_policy"] = "bounded_active_search_on_verified_execution_dependencies"
        result["slow_duration_min_increase_percent"] = 100
        by_rank = result["slow_tasks_by_rank"] = []
        candidates = []
        for rank in ranks:
            items = milestones[rank]
            comparable = [m for m in items if m["duration_comparable"] and m["reference_mean_ns"] is not None
                          and Decimal(m["reference_mean_ns"]) > 0]
            slow = [s for m in comparable if (s := rank_progress.s2_growth(m)) is not None]
            by_rank.append(dict(rank=rank, task_count=len(items), comparable_count=len(comparable),
                slow_tasks=[m for m in slow if m["task_kind"] not in WAIT],
                slow_waits=[m for m in slow if m["task_kind"] in WAIT]))
            candidates.extend(m for m in slow if m["task_kind"] in rank_progress.WORK | WAIT)
        result["observed_receive_protocol_intervals"] = protocol_observations
        remaining = progress.options.traversal_limit
        for item in sorted(candidates, key=lambda m: (m["task_kind"] in WAIT, -Decimal(m["duration_delta_ns"]), m["graph_id"])):
            if remaining <= 0:
                break
            trace = downstream_propagation.trace_downstream(item, graph, progress, min(256, remaining), s2_threshold=True)
            remaining -= trace["visited_count"]
            searches.append(trace)
        if len(searches) < len(candidates):
            gaps.append(dict(reason="alert_forward_budget_exhausted"))
        result["unsearched_slow_seed_count"] = len(candidates)-len(searches)
    return result


def evidence_paths(alert):
    for entry in alert.get("entry_wait_observations", ()):
        yield [entry["stream_edge"]]
        producer = entry["wait"]["wait_producer"]
        if producer.get("verified"):
            yield [producer, entry["stream_edge"]]
    for trace in alert.get("blocking_waits", ()):
        if trace["producer"].get("verified"):
            yield [trace["producer"]]
        for item in trace["upstream_task_or_stage"]:
            yield item["path"]
    for search in alert.get("downstream_propagation", ()):
        for item in search["downstream"]:
            yield item["path"]


def focus_report(report, selections, preparations=(), *, rows=(), edges=(), timings=(), alignment=None, options=None,
                 local_clocks=None):
    """Keep exact operation binding and diagnose it using the original execution graph."""
    targets = {a["operation_scope"] for a in selections if a["operation_scope"]}
    communication = {a["operation_scope"] for a in selections if a["route"] == "S2" and a["operation_scope"]}
    upstream_targets = {a["operation_scope"] for a in selections if a["route"] != "S2" and a["operation_scope"]}
    tasks, roots, dependency_paths, host_by_scope, protocol_by_scope = (defaultdict(list) for _ in range(5))
    for r in (*report["root_causes"], *report.get("unresolved_observations", ())):
        if r["component"] == "host_preparation" and r["operation_scope"] in targets:
            host_by_scope[r["operation_scope"]].append(r)
    for t in report["tasks"]:
        if t.get("operation_scope") in targets:
            tasks[t["operation_scope"]].append(t)
    scope_by_id = {t["graph_id"]: t.get("operation_scope") for t in report["tasks"]}
    for path in report.get("cross_node_path_candidates", ()):
        scope = scope_by_id.get(path["payload_graph_id"])
        if scope in communication:
            protocol_by_scope[scope].append(path)
    progress = None
    if rows and targets:
        if options is None:
            from .rolling_diagnosis import RollingOptions
            options = RollingOptions()
        progress = rank_progress.Progress(EvidenceGraph(rows, edges, alignment, local_clocks),
            {t["graph_id"]: t for t in report["tasks"]}, timings, options)
    edge_by_id = {e["edge_id"]: e for e in edges} if progress is not None else {}
    picked, used_waits = [], set()
    for source in report["root_causes"]:
        scope = source["operation_scope"]
        paths = {w: p for w, p in source.get("evidence_paths", {}).items()
                 if p and (scope_by_id.get(w) in targets or (scope in communication and source["component"] == "execution"))}
        if progress is not None:
            paths = {w: p for w, p in paths.items() if scope_by_id.get(w) in upstream_targets}
        if progress is not None and source["component"] == "execution":
            paths = {w: p for w, p in paths.items() if all(
                edge_id in edge_by_id and progress.graph.proof(edge_by_id[edge_id])["verified"] for edge_id in p)}
        if paths:
            used_waits.update(paths)
            picked.append(dict(source, evidence_paths=paths, affected_wait_graph_ids=sorted(paths)))
            touched = {scope, *(scope_by_id.get(w) for w in paths)} & targets
            for loc in touched:
                roots[loc].append(source["root_id"])
                for wait, path in paths.items():
                    wait_scope = scope_by_id.get(wait)
                    if loc in {scope, wait_scope}:
                        dependency_paths[loc].append(dict(candidate_id=source["root_id"],
                            source_graph_id=source["graph_id"], source_component=source["component"],
                            source_scope=scope, wait_graph_id=wait, wait_scope=wait_scope, edge_ids=path))
    by_scope = defaultdict(list)
    for trace in report.get("wait_backtraces", []):
        if trace["operation_scope"] in targets:
            by_scope[trace["operation_scope"]].append(trace)
    preparation_by_scope = defaultdict(list)
    for p in preparations:
        preparation_by_scope[p["operation_scope"]].append(p)
    results = []
    for selection in selections:
        scope = selection["operation_scope"]
        compared = tasks.get(scope, ())
        waits = [_task(t) for t in compared if t.get("duration_slow") and t["task_kind"] in WAIT]
        slow = [_task(t) for t in compared if t.get("duration_slow") and t["task_kind"] not in WAIT]
        row = dict(selection, source_candidate_ids=roots.get(scope, []), slow_tasks=slow, slow_waits=waits,
                   comparable_task_count=sum(bool(t.get("reference_count")) for t in compared),
                   uncomparable_wait_count=sum(t["task_kind"] in WAIT and not t.get("reference_count") for t in compared),
                   dependency_paths=dependency_paths.get(scope, []),
                   wait_backtraces=by_scope.get(scope, []),
                   unresolved_event_wait_ids=[t["graph_id"] for t in waits if t["task_kind"] == "event_wait"])
        if selection["route"] in {"S1", "undetermined"}:
            suspect = set(selection["suspected_ranks"] or ())
            row.update(host_preparation=[p for p in preparation_by_scope.get(scope, []) if not suspect or p["user_rank"] in suspect],
                       late_task_observations=[_task(t) for t in compared if t.get("iteration_start_late")
                                               and (not suspect or t["user_rank"] in suspect)],
                       unresolved_cause="Preparation may be measured without evidence identifying the upstream Host work.")
        if scope and progress is not None:
            row.update(_explain(selection, progress, host_by_scope[scope], protocol_by_scope[scope]))
            if selection["route"] == "S2":
                for label in ("slow_tasks", "slow_waits"):
                    row[label] = [item for rank in row["slow_tasks_by_rank"] for item in rank[label]]
        elif not scope:
            row["evidence_gaps"] = [dict(reason=selection["binding_status"])]
        results.append(row)
    return dict(report, root_causes=picked, diagnosis_status=None,
        wait_backtraces=[t for t in report.get("wait_backtraces", [])
                         if t["operation_scope"] in targets or t["wait_graph_id"] in used_waits],
        unresolved_observations=[r for r in report.get("unresolved_observations", []) if r.get("operation_scope") in targets],
        cross_node_path_candidates=[r for r in report.get("cross_node_path_candidates", [])
                                    if scope_by_id.get(r["payload_graph_id"]) in targets],
        peer_read_observations=[r for r in report.get("peer_read_observations", []) if r.get("operation_scope") in targets],
        iteration_start_observations=dict(report.get("iteration_start_observations", {}), examples=[])), results
