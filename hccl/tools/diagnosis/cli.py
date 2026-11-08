"""Capture training and automatically diagnose single/multi-node traces."""
from __future__ import annotations

import argparse
from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import shutil
import sys
import tempfile

from . import analyze_waits as waits
from . import compare_diagnosis as comparison
from . import rolling_diagnosis as rolling
from . import visualize_dependency_graph as graph
from .capture_discovery import discover_capture, prepare_capture_identity, read_json, write_json
from .workload_binder import bind_capture
from .result_normalizer import normalize
from .report_exporter import publish_final_report
from .run_diagnosis import run_pipeline
from .workload_coordinates import position


class DiagnosisError(Exception):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


ROLLING_SELECTION_POLICIES = frozenset({'dual', 'dual-v2', 'parallel', 'cluster-top1',
                                       'cluster-top1-time', 'cluster-top1-cohort'})


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


def analyze_capture(capture, output, *, mode, baseline=None, topology=None, manifest=None,
                    min_match_rate=95.0, require_clock_alignment=False, keep_debug=False,
                    debug_dir=None, verbose=False, allow_uncalibrated_clock=False,
                    source_slowdown_factor="1.5", wait_slowdown_factor=None,
                    calibrated_release_intervals=False, completion_fallback=False, candidate_policy="all", source_policy="legacy",
                    selected_iteration_view=False):
    if require_clock_alignment and allow_uncalibrated_clock:
        raise DiagnosisError(2, "required alignment and explicit local-clock fallback are mutually exclusive")
    if mode not in {"rolling", "baseline"} or (mode == "baseline") != (baseline is not None):
        raise DiagnosisError(2, "baseline mode requires --baseline; rolling forbids it")
    if source_policy not in ROLLING_SELECTION_POLICIES | {'auto', 'legacy'}:
        raise DiagnosisError(2, 'unknown source policy')
    if source_policy in ROLLING_SELECTION_POLICIES and (mode != 'rolling' or candidate_policy != 'all'):
        raise DiagnosisError(2, "dual source policy requires rolling mode and no separate candidate filter")
    if source_policy == 'auto' and candidate_policy != 'all':
        raise DiagnosisError(2, 'automatic diagnosis does not accept an archived candidate filter')
    from .candidate_screening import POLICIES
    if candidate_policy not in POLICIES or mode != "rolling" and candidate_policy != "all":
        raise DiagnosisError(2, "experimental candidate admission requires rolling mode and a supported policy")
    rolling_options = rolling.RollingOptions(max_figures=0, slowdown_factor=source_slowdown_factor,
        wait_slowdown_factor=wait_slowdown_factor, calibrated_release_intervals=calibrated_release_intervals,
        completion_fallback=completion_fallback, candidate_policy=candidate_policy,
        source_policy='dual' if source_policy == 'auto' else source_policy)
    if mode == 'rolling':
        try:
            rolling_options.validate()
        except (ValueError, ArithmeticError) as error:
            raise DiagnosisError(2, 'invalid diagnosis options: ' + str(error)) from error
    if not 0 < min_match_rate <= 100:
        raise DiagnosisError(2, "min-match-rate must be in (0,100]")
    output = Path(output).absolute()
    keep_debug = keep_debug or debug_dir is not None
    if output.exists() or output.is_symlink():
        raise DiagnosisError(2, "refusing to overwrite existing report: " + str(output))
    inputs = [Path(p).resolve() for p in (capture, baseline) if p is not None]
    for source in inputs:
        root = source.parent if source.is_file() else source
        if output.resolve() == root or root in output.resolve().parents:
            raise DiagnosisError(2, "output must be outside read-only capture directories")
    debug = Path(debug_dir).absolute() if debug_dir else output.with_name(output.name + ".debug")
    if keep_debug:
        resolved_debug, resolved_output = debug.resolve(), output.resolve()
        if (debug.exists() or debug.is_symlink() or resolved_debug == resolved_output
                or resolved_output in resolved_debug.parents or resolved_debug in resolved_output.parents):
            raise DiagnosisError(2, "debug must be a fresh directory separate from the final report")
        if any((p.parent if p.is_file() else p) == debug.resolve() or
               (p.parent if p.is_file() else p) in debug.resolve().parents for p in inputs):
            raise DiagnosisError(2, "debug cannot be placed inside capture inputs")
        debug.parent.mkdir(parents=True, exist_ok=True)
    # Keep replay on its destination filesystem so retention is an atomic move,
    # not a second full copy of multi-gigabyte captures and graph artifacts.
    with tempfile.TemporaryDirectory(prefix="hccl-diag-", dir=debug.parent if keep_debug else None) as temporary:
        work = Path(temporary)
        try:
            try:
                current_capture = discover_capture(capture, work / "discovery-current", topology=topology, manifest_path=manifest)
                current_capture = prepare_capture_identity(current_capture, work / "identity-current")
                current = bind_capture(current_capture, work / "current", mode=mode)
                reference = None
                pair_map = current_capture.operation_map
                if baseline is not None:
                    base_capture = discover_capture(baseline, work / "discovery-baseline")
                    base_capture = prepare_capture_identity(base_capture, work / "identity-baseline")
                    base = bind_capture(base_capture, work / "baseline", mode="baseline")
                    pair_map = pair_map or _baseline_pairs(current, base, work)
            except Exception as error:
                raise DiagnosisError(2, "capture/binding: " + str(error)) from error
            try:
                # The core algorithms are invoked directly, not chained subprocesses.
                with redirect_stdout(sys.stdout if verbose else io.StringIO()):
                    if baseline is not None:
                        reference, ready = run_pipeline(base.manifest, work / "reference",
                            min_match_rate=min_match_rate, html_views=(), include_critical_path=False,
                            require_clock_alignment=require_clock_alignment, allow_uncalibrated_clock=allow_uncalibrated_clock)
                        _gate(reference, ready)
                    directory, ready = run_pipeline(current.manifest, work / "analysis", baseline=reference,
                        operation_map=pair_map if baseline is not None else None,
                        iteration_map=current.iteration_map if mode == "rolling" else None,
                        preparation_map=current.preparation_map if mode == "rolling" else None,
                        min_match_rate=min_match_rate, require_clock_alignment=require_clock_alignment,
                        allow_uncalibrated_clock=allow_uncalibrated_clock,
                        comparison_options=comparison.ComparisonOptions(max_figures=0),
                        rolling_options=rolling_options,
                        html_views=(), include_critical_path=False)
                pipeline = _gate(directory, ready)
                report = read_json(directory / ("rolling/report.json" if mode == "rolling" else "comparison/report.json"))
                rows = graph.read_graph_artifact_nodes(directory / "dep_graph_nodes.csv")
                edges = graph.read_graph_artifact_edges(directory / "dep_graph_edges.csv")
                selection = None
                automatic = None
                if source_policy == 'auto' and mode == 'rolling':
                    from .recommended_policy import select
                    alignment = read_json(directory / 'clock_alignment.json') if (directory / 'clock_alignment.json').exists() else None
                    report, selection, automatic = select(report, rows, edges, alignment)
                    write_json(directory / 'source_selection.json', selection)
                elif source_policy in {"parallel", "cluster-top1", "cluster-top1-time", "cluster-top1-cohort"}:
                    from .parallel_sources import select as select_parallel
                    alignment = read_json(directory / "clock_alignment.json") if (directory / "clock_alignment.json").exists() else None
                    if source_policy == "cluster-top1-time":
                        from .cluster_top1 import select as select_time
                        report, selection = select_time(report, edges, alignment)
                    elif source_policy == "cluster-top1-cohort":
                        from .cohort_source_policy import select as select_cohort
                        report, selection = select_cohort(report, edges, alignment)
                    else:
                        protocol = read_json(directory / "cross_node/report.json") if (directory / "cross_node/report.json").exists() else None
                        report, selection = select_parallel(report, edges, alignment, rows=rows, protocol_report=protocol)
                    write_json(directory / "source_selection.json", selection)
                elif source_policy in {"dual", "dual-v2"}:
                    from .multinode_source_policy import select
                    alignment = read_json(directory / "clock_alignment.json") if (directory / "clock_alignment.json").exists() else None
                    protocol = read_json(directory / "cross_node/report.json") if (directory / "cross_node/report.json").exists() else None
                    report, selection = select(report, rows, edges, alignment, protocol, refined=source_policy == "dual-v2")
                    write_json(directory / "source_selection.json", selection)
                normalized, roots, tasks = normalize(report, mode=mode,
                    run_id=current_capture.manifest["run_id"], rows=rows, edges=edges, pipeline=pipeline,
                    binding_evidence=dict(current.evidence, identity_exports=list(current_capture.identity_exports)),
                    merge_metrics=waits.read_csv(directory / "merge_summary.csv"))
                if automatic is not None:
                    normalized['automatic_diagnosis'] = automatic
                if selection is not None:
                    if source_policy == 'auto':
                        keys = ('policy', 'summary', 'cluster_selection')
                    elif source_policy in {'parallel', 'cluster-top1', 'cluster-top1-time', 'cluster-top1-cohort'}:
                        keys = ('policy', 'candidate_relationship', 'summary', 'cluster_selection', 'host_admission')
                    elif source_policy == 'dual':
                        keys = ('selected_mechanism', 'primary_proposal', 'proposals', 'host_admission_decisions')
                    else:
                        keys = ('policy', 'selected_mechanism', 'primary_proposal', 'transfer_coverage')
                    normalized["source_selection"] = {k: selection[k] for k in keys}
                    normalized["source_candidates"] = normalized["candidates"] + normalized["external_anomaly_clues"]
                    normalized["primary_source_id"] = report["primary_source_candidate_id"]
                    for candidate in normalized["source_candidates"]:
                        root = next(r for r in roots if r["root_id"] == candidate["id"])
                        candidate.update(source_activity_id=root.get("source_activity_id"), anchor_graph_id=root["graph_id"],
                            protocol_endpoints=root.get("protocol_endpoints"), source_unit=root.get("source_unit", root["component"]))
                    if "protocol_observations" in selection:
                        normalized["source_selection"]["protocol_coverage"] = {k: v for k, v in selection["protocol_observations"].items() if k != "candidates"}
            except DiagnosisError:
                raise
            except Exception as error:
                raise DiagnosisError(4, "analysis: " + str(error)) from error
            try:
                if selected_iteration_view:
                    from .report_exporter import publish_selected_iteration_report
                    return publish_selected_iteration_report(directory, output, normalized, roots, tasks,
                                                             full_graph_retained=keep_debug)
                return publish_final_report(directory, output, normalized, roots, tasks)
            except Exception as error:
                raise DiagnosisError(5, "report publication: " + str(error)) from error
        finally:
            if keep_debug:
                try:
                    if debug.exists() or debug.is_symlink():
                        raise FileExistsError("debug appeared during analysis; refusing overwrite")
                    work.rename(debug)
                except Exception as error:
                    raise DiagnosisError(5, 'debug retention failed; original capture retained: ' + str(error)) from error


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, epilog="Exit codes: 0 command completed (capture alone is not diagnosis or numerical validation); 2 input/capture/binding; 3 association gate; 4 graph/diagnosis; 5 publication. Inputs are never deleted.")
    sub = parser.add_subparsers(dest="command", required=True)
    from .capture_command import add_commands, dispatch
    add_commands(sub)
    analyze = sub.add_parser("analyze", aliases=['diag'], help="automatically diagnose single/multi-node capture")
    analyze.add_argument('capture_path', type=Path, nargs='?')
    analyze.add_argument("--capture", type=Path, help=argparse.SUPPRESS)
    analyze.add_argument("--mode", choices=("baseline", "rolling"), default=None, help=argparse.SUPPRESS)
    analyze.add_argument("--baseline", type=Path)
    analyze.add_argument("--output", "-o", type=Path, help="default: CAPTURE-report")
    analyze.add_argument("--topology", type=Path)
    analyze.add_argument("--manifest", type=Path)
    analyze.add_argument("--min-match-rate", type=float, default=95.0)
    analyze.add_argument("--require-clock-alignment", action="store_true")
    analyze.add_argument("--allow-uncalibrated-clock", action="store_true", help="on rejected display calibration, retain node-local axes and report the reason; semantic/graph gates remain required")
    analyze.add_argument("--keep-debug", action="store_true")
    analyze.add_argument("--selected-iteration-view", action="store_true", help="render selected formal iterations; keep full diagnosis and original debug graph")
    analyze.add_argument("--debug-dir", type=Path, help="retain full intermediate evidence here (implies --keep-debug)")
    analyze.add_argument("--verbose", action="store_true")
    analyze.add_argument("--source-slowdown-factor", default="1.5")
    analyze.add_argument("--wait-slowdown-factor")
    analyze.add_argument("--calibrated-release-intervals", action="store_true")
    analyze.add_argument("--completion-fallback", action="store_true")
    analyze.add_argument("--source-policy", choices=("auto", "legacy", "dual", "dual-v2", "cluster-top1", "cluster-top1-time", "cluster-top1-cohort", "parallel"), default="auto", help=argparse.SUPPRESS)
    from .candidate_screening import POLICIES
    analyze.add_argument("--candidate-policy", choices=POLICIES, default="all", help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    try:
        if args.command not in {'analyze', 'diag'}:
            return dispatch(args)
        if args.capture and args.capture_path:
            raise DiagnosisError(2, 'provide the capture only once')
        args.capture = args.capture or args.capture_path
        if args.capture is None:
            raise DiagnosisError(2, 'provide a capture directory')
        del args.capture_path
        args.mode = args.mode or ('baseline' if args.baseline else 'rolling')
        capture_path = args.capture.absolute()
        args.output = args.output or capture_path.with_name(capture_path.name + '-report')
        if args.source_policy == 'auto' and args.mode == 'rolling':
            args.selected_iteration_view = True
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
    print("status={} candidates={} chains={} output={}".format(result["status"], len(result["candidates"]),
          result["propagation"]["chain_count"], args.output.absolute()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
