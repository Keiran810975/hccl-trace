"""Replay and validate a capture before running the selected public comparison."""
from __future__ import annotations

from pathlib import Path

from . import analyze_waits as waits
from . import clock_alignment
from . import compare_diagnosis as comparison
from . import rolling_diagnosis as rolling
from . import visualize_dependency_graph as graph
from .capture_discovery import read_json, write_json
from .multi_node_trace import load_manifest, replay_manifest
from .schema import write_csv


def _alignment(directory, rows, *, allow_uncalibrated_clock):
    path = directory / "clock_alignment.json"
    try:
        inputs = read_json(directory / "inputs.json")
        alignment = clock_alignment.build(inputs, max_error_ns=inputs.get("clock_alignment_max_error_ns", 1000000))
        if alignment is not None:
            clocks = clock_alignment.models_from_report(alignment)
            for row in rows:
                clock = clocks.get((row["_node_id"], row["_device_id"]))
                if clock is None:
                    raise ValueError("clock evidence does not cover every execution device")
                for side in ("start", "stop"):
                    clock.map_ns(waits.ns(row, side))
            write_json(path, alignment)
        return alignment, None
    except (OSError, ValueError, KeyError, ArithmeticError) as error:
        if not allow_uncalibrated_clock:
            raise
        return None, str(error)


def _graph(directory):
    return (graph.read_graph_artifact_nodes(directory / "dep_graph_nodes.csv"),
            graph.read_graph_artifact_edges(directory / "dep_graph_edges.csv"))


def _save_comparison(directory, name, report, keep_debug):
    output = directory / name
    output.mkdir()
    write_json(output / "report.json", report)
    if keep_debug:
        for kind, records in (("task_comparison", report["tasks"]),
                              ("slow_tasks", [t for t in report["tasks"] if t["is_slow"]]),
                              ("root_causes", report["root_causes"])):
            fields = list(dict.fromkeys(k for record in records for k in record))
            write_csv(str(output / (kind + ".csv")), fields, records)


def run_pipeline(manifest: Path, output: Path, *, baseline: Path | None = None,
                 min_match_rate: float = 95.0, operation_map: Path | None = None,
                 iteration_map: Path | None = None, preparation_map: Path | None = None,
                 rolling_options=rolling.RollingOptions(), keep_debug=False,
                 require_clock_alignment=False, allow_uncalibrated_clock=False):
    if require_clock_alignment and allow_uncalibrated_clock:
        raise ValueError("required alignment and explicit local-clock fallback are mutually exclusive")
    if iteration_map is not None and (baseline is not None or operation_map is not None):
        raise ValueError("rolling history must not be combined with an external baseline")
    if preparation_map is not None and iteration_map is None:
        raise ValueError("public preparations require an evidenced iteration map")
    directory = output / load_manifest(manifest)["run_id"]
    if directory.exists():
        raise FileExistsError("refusing to reuse diagnosis directory: {}".format(directory))
    result = dict(status="failed", replay_gate_passed=False, analysis_completed=False)
    try:
        directory, ready = replay_manifest(manifest, output, min_match_rate)
        result["replay_gate_passed"] = ready
        if not ready:
            return directory, False
        rows, edges = _graph(directory)
        alignment, clock_error = _alignment(directory, rows, allow_uncalibrated_clock=allow_uncalibrated_clock)
        result.update(clock_alignment_available=alignment is not None,
                      clock_alignment_status=alignment["status"] if alignment else "uncalibrated",
                      clock_alignment_estimated_error_ns=alignment["estimated_error_ns"] if alignment else None,
                      clock_alignment_error=clock_error,
                      profiler_clock_validation=alignment.get("profiler_calibrations", []) if alignment else [])
        if require_clock_alignment and alignment is None:
            result.update(status="incomplete", error="clock probes/calibration do not cover this capture")
            return directory, False
        reference, reference_edges = _graph(baseline) if baseline is not None else ([], [])
        issues = waits.read_csv(directory / "dep_graph_notify_ambiguities.csv")
        spans = [row for path in sorted(directory.glob("*/build_spans.csv")) for row in waits.read_csv(path)]
        diagnosis = waits.analyze(rows, edges, issues, spans, reference, trace_wait_chains=iteration_map is None)
        if not diagnosis["waits"]:
            raise ValueError("no Notify Wait evidence in the selected capture")
        waits.export_analysis(diagnosis, directory)
        if iteration_map is not None:
            report = rolling.analyze(rows, edges, rolling.load_coordinates(iteration_map), rolling_options,
                                     preparations=rolling.source_events.load_preparations(preparation_map), alignment=alignment)
            _save_comparison(directory, "rolling", report, keep_debug)
            result.update(reference_mode=report["reference_mode"], source_policy_version=report["source_policy_version"],
                          rolling_status=report["status"], comparison_coverage=report["coverage"],
                          slow_task_count=report["slow_task_count"], diagnosis_status=report["diagnosis_status"])
        elif baseline is not None:
            if read_json(baseline / "pipeline_result.json")["status"] != "passed":
                raise ValueError("baseline diagnosis has not passed its gates")
            comparison.evidence_adjacency(reference, reference_edges)
            report = comparison.analyze(rows, edges, reference,
                operation_pairs=comparison.load_operation_map(operation_map), baseline_edges=reference_edges)
            _save_comparison(directory, "comparison", report, keep_debug)
            result.update(comparison_completed=True, source_policy_version=report["source_policy_version"],
                          slow_task_count=report["slow_task_count"])
        result.update(status="passed", analysis_completed=True, node_count=len({r["_node_id"] for r in rows}),
                      wait_count=len(diagnosis["waits"]), paired_wait_count=sum(w["status"] == "paired" for w in diagnosis["waits"]))
        return directory, True
    except (OSError, ValueError, KeyError, ArithmeticError) as error:
        result["error"] = str(error)
        raise
    finally:
        if directory.is_dir():
            write_json(directory / "pipeline_result.json", result)
