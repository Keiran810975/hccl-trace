"""Capture training and automatically diagnose single/multi-node traces."""
from __future__ import annotations

import argparse
from contextlib import redirect_stdout
import io
from pathlib import Path
import sys
import tempfile

from . import analyze_waits as waits, online_followup
from . import rolling_diagnosis as rolling
from . import visualize_dependency_graph as graph
from .capture_discovery import discover_capture, prepare_capture_identity, read_json, write_json
from .workload_binder import bind_capture
from .result_normalizer import normalize
from .report_paths import load_paths
from .report_exporter import publish_final_report, publish_selected_iteration_report
from .run_diagnosis import run_pipeline
from .workload_coordinates import position


class DiagnosisError(Exception):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


def _gate(directory, ready):
    result = read_json(directory / "pipeline_result.json")
    if not ready or result.get("status") != "passed" or not result.get("analysis_completed"):
        metrics = waits.read_csv(directory / "merge_summary.csv")
        bad = [r["node_id"] for r in metrics if r["metric"] == "merge_gate_passed" and r["value"] != "1"]
        if bad:
            raise DiagnosisError(3, "semantic association gate failed on " + ", ".join(bad))
        raise DiagnosisError(4, result.get("error", "dependency/topology gate failed; shared call identity, complete Notify channels and rank coverage are required"))
    return result


def _baseline_pairs(current, baseline, work):
    if not current.coordinates or not baseline.coordinates:
        return None
    def index(binding):
        evidence = read_json(binding.manifest.parent / "binding-evidence.json")["operations"]
        shape = {e["operation_id"]: (e["participants"], e["operation_type"], e["dtype"], e["element_count"], e.get('reduction')) for e in evidence}
        manifest = read_json(binding.manifest)
        from .dependency_model import stable_id
        shapes = {stable_id("op", (manifest["run_id"], key)): value for key, value in shape.items()}
        return {(c["stage"], c["iteration"], position(c)): (c["operation_scope"], shapes[c["operation_scope"]])
                for c in binding.coordinates}
    left, right = index(current), index(baseline)
    if set(left) != set(right) or any(left[key][1] != right[key][1] for key in left):
        raise ValueError("SDK baseline requires identical public locations, group members and collective shapes")
    pairs = [dict(current_scope=left[key][0], baseline_scope=right[key][0],
                  evidence="Independently API-bound SDK location, actual group membership and collective shape on both runs") for key in left]
    path = work / "operation-map.json"
    write_json(path, dict(schema_version=1, operation_pairs=pairs))
    return path


def _check_output(output, *inputs):
    if output.exists() or output.is_symlink():
        raise DiagnosisError(2, "refusing to overwrite existing report: " + str(output))
    resolved = output.resolve()
    for source in inputs:
        if source is not None:
            source = Path(source).resolve()
            root = source.parent if source.is_file() else source
            if resolved == root or root in resolved.parents:
                raise DiagnosisError(2, "output must be outside read-only capture directories")


def analyze_capture(capture, output=None, *, mode, baseline=None, topology=None, manifest=None,
                    min_match_rate=95.0, require_clock_alignment=False,
                    verbose=False, allow_uncalibrated_clock=False,
                    source_slowdown_factor="1.5", wait_slowdown_factor=None,
                    calibrated_release_intervals=False, online=None, paths=None,
                    without_online=False, target_iteration=None, online_records=None, report_style="standard"):
    if require_clock_alignment and allow_uncalibrated_clock:
        raise DiagnosisError(2, "required alignment and explicit local-clock fallback are mutually exclusive")
    if mode not in {"rolling", "baseline"} or (mode == "baseline") != (baseline is not None):
        raise DiagnosisError(2, "baseline mode requires --baseline; rolling forbids it")
    if online is not None and without_online:
        raise DiagnosisError(2, "--online and --without-online are mutually exclusive")
    if (online is not None or online_records is not None) and mode != "rolling":
        raise DiagnosisError(2, "--online requires rolling history (do not combine with --baseline)")
    if target_iteration is not None and (mode != "rolling" or not online_records or
            any(a.get("iteration") != target_iteration for a in online_records)):
        raise DiagnosisError(2, "whole-iteration follow-up requires online alerts for that iteration")
    if report_style not in {"standard", "full", "json"} or (target_iteration is not None and report_style != "standard"):
        raise DiagnosisError(2, "choose a supported offline report style; online reports are iteration scoped")
    rolling_options = rolling.RollingOptions(slowdown_factor=source_slowdown_factor,
        wait_slowdown_factor=wait_slowdown_factor if wait_slowdown_factor is not None else "1.2",
        calibrated_release_intervals=calibrated_release_intervals)
    if mode == 'rolling':
        try:
            rolling_options.validate()
        except (ValueError, ArithmeticError) as error:
            raise DiagnosisError(2, 'invalid diagnosis options: ' + str(error)) from error
    if not 0 < min_match_rate <= 100:
        raise DiagnosisError(2, "min-match-rate must be in (0,100]")
    if paths is None and (output is None or (mode == "rolling" and not without_online and online_records is None)):
        paths = load_paths()
    if output is not None:
        output = Path(output).absolute()
        _check_output(output, capture, baseline, manifest)
    with tempfile.TemporaryDirectory(prefix="hccl-diag-") as temporary:
        work = Path(temporary)
        try:
            current_capture = discover_capture(capture, work / "discovery-current", topology=topology, manifest_path=manifest)
            run_id = current_capture.manifest["run_id"]
            if output is None:
                output = paths.for_run("offline", run_id)
                _check_output(output, capture, baseline, manifest)
            online_path = (online_followup.alert_path(capture, online,
                configured=paths.for_run("online", run_id) / "events.jsonl")
                if mode == "rolling" and not without_online and online_records is None else None)
            alert_events = (online_followup.load_alerts(online_path, run_id)
                            if online_path is not None else online_records)
            if alert_events and any(a.get("job_id") != run_id for a in alert_events):
                raise ValueError("online event job ID disagrees with capture")
            current_capture = prepare_capture_identity(current_capture, work / "identity-current")
            current = bind_capture(current_capture, work / "current", mode=mode, allow_partial=alert_events is not None,
                                   target_iteration=target_iteration)
            selected = (online_followup.resolve(alert_events, current_capture.call_logs, current.coordinates)
                        if alert_events is not None else None)
            if target_iteration is not None and any(not s["operation_scope"] for s in selected):
                raise ValueError("target alerts do not bind exactly to the sealed iteration")
            reference = None
            pair_map = current_capture.operation_map
            if baseline is not None:
                base_capture = discover_capture(baseline, work / "discovery-baseline")
                base_capture = prepare_capture_identity(base_capture, work / "identity-baseline")
                base = bind_capture(base_capture, work / "baseline", mode="baseline")
                pair_map = pair_map or _baseline_pairs(current, base, work)
        except DiagnosisError:
            raise
        except Exception as error:
            raise DiagnosisError(2, "capture/binding: " + str(error)) from error
        try:
            # The core algorithms are invoked directly, not chained subprocesses.
            live = {} if mode == "rolling" else None
            with redirect_stdout(sys.stdout if verbose else io.StringIO()):
                if baseline is not None:
                    reference, ready = run_pipeline(base.manifest, work / "reference",
                        min_match_rate=min_match_rate,
                        require_clock_alignment=require_clock_alignment, allow_uncalibrated_clock=allow_uncalibrated_clock)
                    _gate(reference, ready)
                directory, ready = run_pipeline(current.manifest, work / "analysis", baseline=reference,
                    operation_map=pair_map if baseline is not None else None,
                    iteration_map=current.iteration_map if mode == "rolling" else None,
                    preparation_map=current.preparation_map if mode == "rolling" else None,
                    min_match_rate=min_match_rate, require_clock_alignment=require_clock_alignment,
                    allow_uncalibrated_clock=allow_uncalibrated_clock,
                    rolling_options=rolling_options, live=live, iteration_window=current.iteration_window)
            pipeline = _gate(directory, ready)
            if live is None:
                report = read_json(directory / "comparison/report.json")
                rows = graph.read_graph_artifact_nodes(directory / "dep_graph_nodes.csv")
                edges = graph.read_graph_artifact_edges(directory / "dep_graph_edges.csv")
            else:
                report = live.pop("report")
                rows, edges = live["graph"]
            if selected is not None:
                clock_path = directory / "clock_alignment.json"
                report, followed = online_followup.focus_report(report, selected,
                    rolling.source_events.load_preparations(current.preparation_map), rows=rows, edges=edges,
                    timings=waits.read_csv(directory / "operation_timings.csv"),
                    alignment=read_json(clock_path) if clock_path.is_file() else None, options=rolling_options,
                    local_clocks=live["local_clocks"] if selected else {})
            normalized, roots, tasks = normalize(report, mode=mode,
                run_id=current_capture.manifest["run_id"], rows=rows, edges=edges, pipeline=pipeline,
                binding_evidence=dict(current.evidence, identity_exports=list(current_capture.identity_exports)),
                merge_metrics=waits.read_csv(directory / "merge_summary.csv"), formal_only=mode == "rolling")
            if selected is not None:
                normalized["online_followup"] = dict(schema_version=3, alert_count=len(followed),
                    bound_count=sum(bool(a["operation_scope"]) for a in followed), alerts=followed)
            del report
            if mode == 'rolling':
                nodes = sorted({r['_node_id'] for r in rows})
                normalized['automatic_diagnosis'] = dict(node_count=len(nodes), node_ids=nodes,
                    execution_mode='single_node' if len(nodes) == 1 else 'multi_node',
                    selected_policy='wait_backtrace_v1')
                normalized['source_candidates'] = normalized['candidates'] + normalized['external_anomaly_clues']
                for candidate in normalized['source_candidates']:
                    candidate['source_unit'] = ('host_preparation' if candidate['component'] == 'host_preparation'
                                                else 'execution_task')
        except DiagnosisError:
            raise
        except Exception as error:
            raise DiagnosisError(4, "analysis: " + str(error)) from error
        try:
            if mode == 'rolling' and report_style == "standard":
                return publish_selected_iteration_report(directory, output, normalized, roots, tasks,
                    graph_data=(rows, edges), iteration_window=current.iteration_window)
            json_only = report_style == "json"
            if not json_only:
                normalized["analysis_scope"] = dict(kind="full_capture_execution_graph",
                    diagnosis_used_full_capture=True, original_full_graph_retained=True)
            diagnosis = waits.analyze(rows, edges, trace_wait_chains=False) if mode == "rolling" and not json_only else None
            return publish_final_report(directory, output, normalized, roots, tasks, graph_data=(rows, edges),
                                        diagnosis_data=diagnosis, json_only=json_only)
        except Exception as error:
            raise DiagnosisError(5, "report publication: " + str(error)) from error


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, epilog="Exit codes: 0 command completed (capture alone is not diagnosis or numerical validation); 2 input/capture/binding; 3 association gate; 4 graph/diagnosis; 5 publication. Inputs are never deleted.")
    sub = parser.add_subparsers(dest="command", required=True)
    from .capture_command import add_commands, dispatch
    from . import clock_probe, collop_slice, online_service
    add_commands(sub)
    online_service.add_arguments(sub.add_parser("online", help="start the online collector for RUN_ID"))
    clock_probe.add_arguments(sub.add_parser("clock-probe", help="collect CPU clock evidence for multi-node diagnosis"))
    collop_slice.add_arguments(sub.add_parser("slice-collop", help="read one collective and its local context from an msprof snapshot"))
    analyze = sub.add_parser("analyze", aliases=['diag'], help="automatically diagnose single/multi-node capture")
    analyze.add_argument("capture", type=Path)
    analyze.add_argument("--baseline", type=Path)
    alerts = analyze.add_mutually_exclusive_group()
    alerts.add_argument("--online", type=Path, help="override the auto-detected events.jsonl or its directory")
    alerts.add_argument("--without-online", action="store_true", help="analyze without online alert selection")
    analyze.add_argument("--config", type=Path, help="report path configuration (default: ./config.yaml)")
    analyze.add_argument("--output", "-o", type=Path, help="override offline_output_dir/RUN_ID")
    analyze.add_argument("--report", dest="report_style", choices=("standard", "full", "json"), default="standard",
                         help="standard: default report bundle; full: include the complete captured graph; json: no HTML")
    analyze.add_argument("--topology", type=Path)
    analyze.add_argument("--manifest", type=Path)
    analyze.add_argument("--min-match-rate", type=float, default=95.0)
    analyze.add_argument("--require-clock-alignment", action="store_true")
    analyze.add_argument("--allow-uncalibrated-clock", action="store_true", help="on rejected display calibration, retain node-local axes and report the reason; semantic/graph gates remain required")
    analyze.add_argument("--verbose", action="store_true")
    analyze.add_argument("--source-slowdown-factor", default="1.5")
    analyze.add_argument("--wait-slowdown-factor")
    analyze.add_argument("--calibrated-release-intervals", action="store_true")
    args = parser.parse_args(argv)
    try:
        if args.command == "online":
            return online_service.run(args)
        if args.command == "clock-probe":
            clock_probe.run(args)
            return 0
        if args.command == "slice-collop":
            return collop_slice.run(args)
        if args.command not in {'analyze', 'diag'}:
            return dispatch(args)
        args.mode = 'baseline' if args.baseline else 'rolling'
        args.paths = load_paths(args.config)
        del args.config
        result = analyze_capture(**{key: value for key, value in vars(args).items() if key != "command"})
    except DiagnosisError as error:
        print("hccl-diag: " + str(error), file=sys.stderr)
        return error.code
    except (OSError, ValueError) as error:
        print('hccl-diag: ' + str(error), file=sys.stderr)
        return 2
    except KeyboardInterrupt as error:
        print("hccl-diag: interrupted; original capture inputs retained", file=sys.stderr)
        return 128 + getattr(error, 'signum', 2)
    output = args.output or args.paths.for_run("offline", result["run_id"])
    print("status={} candidates={} chains={} output={}".format(result["status"], len(result.get("source_candidates", result["candidates"])),
          result["propagation"]["chain_count"], output.absolute()))
    late_count = result.get("iteration_start_observations", {}).get("late_task_count")
    if late_count is not None:
        print(f"relative late starts={late_count} (not Host causes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
