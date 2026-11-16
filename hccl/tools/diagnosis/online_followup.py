"""Use exact archived online alert identities to select offline dependency evidence."""
from __future__ import annotations

from collections import defaultdict
import json
from pathlib import Path

from hccl_trace.online_probe import tensor_description
from .workload_binder import _read_calls, operation_type


SLOW = {"COMPUTATION_SLOW", "COMMUNICATION_SLOW", "SLOW_UNCLASSIFIED"}  # Last entry reads older archives only.
WAIT = {"notify_wait", "event_wait"}


def alert_path(capture, requested=None):
    if requested is not None:
        path = Path(requested).resolve()
        return path / "events.jsonl" if path.is_dir() else path
    root = Path(capture).resolve()
    if root.is_file():
        root = root.parent
    locations = [root / "online/events.jsonl"]
    if root.name == "capture":
        locations.append(root.parent / "online/events.jsonl")
    found = [p for p in locations if p.is_file()]
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
        results.append(dict(event_id=event["event_id"], event_type=event["event_type"], group_id=group,
            generation=generation, op_counter=counter, iteration=key[2], bucket=key[3], occurrence=key[4],
            route="S1" if event["event_type"] == "COMPUTATION_SLOW" else "communication",
            operation_scope=scope, ranks=participants, suspected_ranks=event.get("suspected_ranks"),
            binding_status="bound_exact" if scope else "profiler_operation_not_uniquely_bound" if complete else "incomplete_sdk_token",
            online_metrics={k: metrics.get(k) for k in ("R", "P", "P_relative", "classification_evidence",
                "timing_source", "timing_boundary_verified", "preparation_by_rank")}))
    return results


def _task(t):
    return {k: t.get(k) for k in ("graph_id", "node_id", "user_rank", "stream_id", "task_id", "task_kind",
        "event", "observed_start_ns", "observed_stop_ns", "duration_ns", "reference_mean_ns",
        "delta_ns", "reference_count", "iteration_start_delta_ns", "role")}


def focus_report(report, selections, preparations=()):
    """Retain reported graph paths only; never synthesize edges from alert timing."""
    targets = {a["operation_scope"] for a in selections if a["operation_scope"]}
    communication = {a["operation_scope"] for a in selections if a["route"] != "S1" and a["operation_scope"]}
    tasks, roots, dependency_paths = defaultdict(list), defaultdict(list), defaultdict(list)
    for t in report["tasks"]:
        if t.get("operation_scope") in targets:
            tasks[t["operation_scope"]].append(t)
    scope_by_id = {t["graph_id"]: t.get("operation_scope") for t in report["tasks"]}
    picked, used_waits = [], set()
    for source in report["root_causes"]:
        scope = source["operation_scope"]
        paths = {w: p for w, p in source.get("evidence_paths", {}).items()
                 if p and (scope_by_id.get(w) in targets or (scope in communication and source["component"] == "execution"))}
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
        if selection["route"] == "S1":
            suspect = set(selection["suspected_ranks"] or ())
            row.update(host_preparation=[p for p in preparation_by_scope.get(scope, []) if p["user_rank"] in suspect],
                       late_task_observations=[_task(t) for t in compared if t.get("iteration_start_late") and t["user_rank"] in suspect],
                       unresolved_cause="Preparation may be measured without evidence identifying the upstream Host work.")
        results.append(row)
    return dict(report, root_causes=picked, diagnosis_status=None,
        wait_backtraces=[t for t in report.get("wait_backtraces", [])
                         if t["operation_scope"] in targets or t["wait_graph_id"] in used_waits],
        unresolved_observations=[r for r in report.get("unresolved_observations", []) if r.get("operation_scope") in targets],
        cross_node_path_candidates=[r for r in report.get("cross_node_path_candidates", [])
                                    if scope_by_id.get(r["payload_graph_id"]) in targets],
        peer_read_observations=[r for r in report.get("peer_read_observations", []) if r.get("operation_scope") in targets],
        iteration_start_observations=dict(report.get("iteration_start_observations", {}), examples=[])), results
