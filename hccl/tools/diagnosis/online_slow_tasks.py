"""Publish S2 duration observations without building dependency edges."""
from __future__ import annotations

from collections import defaultdict
from decimal import Decimal
from pathlib import Path
from tempfile import TemporaryDirectory
from time import monotonic_ns

from . import merge_timeline as merge, online_followup, rank_progress, rolling_diagnosis as rolling
from .capture_discovery import discover_capture, prepare_capture_identity, read_json, write_json
from .dependency_timing import WAIT
from .multi_node_trace import operation_bindings
from .validate_trace import validate_rows
from .visualize_dependency_graph import read_execution_rows
from .workload_binder import bind_capture
from .workload_coordinates import position


def _rows(manifest, window, scopes):
    bindings, _ = operation_bindings(manifest)
    run = manifest["run_id"]
    ranks = {(r["node_id"], r["device_id"]): r["user_rank"] for r in manifest["ranks"]}
    for node in manifest["nodes"]:
        name, logs = node["node_id"], node["plog_dir"]
        semantics = merge.parse_plog_inputs(plog_dir=logs, node_id=name)
        correlations = merge.parse_graph_correlation_inputs(plog_dir=logs, node_id=name)
        if any(record.node_id != name for record in semantics + correlations):
            raise ValueError("plog identity disagrees with the capture node")
        profiler = merge.parse_msprof_inputs(msprof_db_dir=node["msprof_db_dir"], node_id=name)
        profiler, _ = merge.apply_control_inputs(profiler, plog_dir=logs, node_id=name)
        rows, metrics = merge.merge_records(semantics, profiler, correlations)
        passed, _ = validate_rows(rows, 95.0)
        if not passed or any(metrics[k] for k in (
                "duplicate_graph_correlation_keys", "ambiguous_profiler", "ambiguous_semantic")):
            raise ValueError(f"exact semantic association gate failed on {name}")
        for row in rows:
            if row["match_status"] not in {"matched", "profiler_only"}:
                continue
            device = int(row["device_id"])
            scope = bindings.get((name, device, row["profiler_op_scope"]))
            if scope not in scopes or row["profiler_op_scope_status"] != "unique":
                continue
            rank = ranks[name, device]
            if int(row["user_rank"]) not in (-1, rank):
                raise ValueError("semantic rank disagrees with capture topology")
            row.update(node_id=f"{run}/{name}", user_rank=rank, profiler_op_scope=scope)
            if not window.keep_row(row):
                # Do not compare the shape of a partially present collective.
                raise ValueError("bound communication task is outside the captured history window")
            yield {k: "" if v is None else str(v) for k, v in row.items()}


def _observe(rows, coordinates, selections):
    groups = defaultdict(list)
    by_id = {}
    for row in rows:
        by_id[row["_graph_id"]] = row
        groups[row["_operation_scope"]].append(row)
    eligible = {scope: coord for scope, coord in coordinates.items() if scope in groups}
    tasks = rolling.compare_tasks(rows, (), eligible, rolling.RollingOptions())
    by_scope = defaultdict(list)
    for task in tasks:
        by_scope[task["operation_scope"]].append(task)
    results = []
    for selection in selections:
        scope = selection["operation_scope"]
        by_rank = {rank: dict(rank=rank, task_count=0, comparable_count=0, slow_tasks=[], slow_waits=[])
                   for rank in selection["ranks"]}
        for task in by_scope[scope]:
            row = by_id[task["graph_id"]]
            summary = by_rank[row["_user_rank"]]
            summary["task_count"] += 1
            # Unannotated control tasks need the full dependency path for comparison.
            if (row["match_status"] != "matched" or row["_step"] < 0
                    or task["reference_count"] < rank_progress.MIN_SAMPLES):
                continue
            item = rank_progress.task_evidence(row, task)
            item["duration_comparable"] = True
            if item["reference_mean_ns"] is None or Decimal(item["reference_mean_ns"]) <= 0:
                continue
            summary["comparable_count"] += 1
            if (slow := rank_progress.s2_growth(item)) is not None:
                summary["slow_waits" if item["task_kind"] in WAIT else "slow_tasks"].append(slow)
        coverage = list(by_rank.values())
        if not all(r["task_count"] for r in coverage):
            raise ValueError("missing device Task coverage for a bound S2 Rank")
        comparable = sum(r["comparable_count"] for r in coverage)
        slow_count = sum(len(r["slow_tasks"]) + len(r["slow_waits"]) for r in coverage)
        results.append(dict(selection, status=("insufficient_history" if not comparable else
            "slow_tasks_observed" if slow_count else "no_comparable_task_over_threshold"),
            slow_task_and_wait_count=slow_count, tasks_by_rank=coverage))
    return results


def prepare_observations(source, work, *, epoch, alerts):
    """Use exact capture evidence for the sealed-input path and offline replays."""
    if not alerts or any(a["event_type"] != "COMMUNICATION_SLOW" or a["iteration"] != epoch
                         or a["stage"] != "measured" for a in alerts):
        raise ValueError("task-only analysis requires S2 alerts from one formal iteration")
    locations = {(a["communicator_id"], a["stage"], epoch, a["bucket_id"], a["occurrence"]) for a in alerts}
    capture = discover_capture(source, work/"discovery")
    if any(a["job_id"] != capture.manifest["run_id"] for a in alerts):
        raise ValueError("S2 alert belongs to another capture")
    capture = prepare_capture_identity(capture, work/"identity")
    binding = bind_capture(capture, work/"binding", mode="rolling", allow_partial=True,
                           target_iteration=epoch, target_locations=locations)
    selections = online_followup.resolve(alerts, capture.call_logs, binding.coordinates)
    if any(not s["operation_scope"] for s in selections):
        raise ValueError("S2 alert does not bind exactly to the sealed capture")
    coords = {c["operation_scope"]: c for c in binding.coordinates}
    positions = {position(coords[s["operation_scope"]]) for s in selections}
    coords = {scope: c for scope, c in coords.items() if position(c) in positions}
    window = binding.iteration_window
    rows = read_execution_rows(None, records=_rows(read_json(binding.manifest), window, coords))
    for row in rows:
        if row["_operation_scope"] in window.target_scopes:
            _, begin, end = window.bounds[row["_node_id"], row["_device_id"]]
            if not begin <= row["_start_ns"] <= row["_stop_ns"] <= end:
                raise ValueError("bound S2 task extends beyond the closed iteration")
    return capture, window, rows, coords, selections


def publish(source, output, *, epoch, alerts, trace_source):
    started = monotonic_ns()
    if output.exists() or output.is_symlink():
        raise FileExistsError("refusing to overwrite a task-only report")
    with TemporaryDirectory(prefix="hccl-slow-tasks-") as temporary:
        capture, window, rows, coords, selections = prepare_observations(
            source, Path(temporary), epoch=epoch, alerts=alerts)
        results = _observe(rows, coords, selections)
    report = dict(schema_version=1, run_id=capture.manifest["run_id"], iteration=epoch,
        diagnosis_status="task_observations_only", trace_source=trace_source,
        minimum_duration_increase_percent=100, minimum_history_samples=rank_progress.MIN_SAMPLES,
        first_history_iteration=window.first, depends_on_sealed_device_tasks=True,
        dependency_graph_built=False, propagation_analyzed=False, physical_cause_inferred=False,
        analysis_ms=(monotonic_ns()-started)/1e6, alerts=results)
    output.parent.mkdir(exist_ok=True, parents=True)
    with TemporaryDirectory(prefix=".slow-tasks-", dir=output.parent) as stage:
        file = Path(stage)/output.name
        write_json(file, report)
        file.replace(output)
    return report
