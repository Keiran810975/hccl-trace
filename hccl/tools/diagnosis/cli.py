"""One offline analyze command, isolated intermediates and three final files."""
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
        shape = {e["operation_id"]: (e["participants"], e["operation_type"], e["dtype"], e["element_count"]) for e in evidence}
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
                    debug_dir=None, verbose=False):
    if mode not in {"rolling", "baseline"} or (mode == "baseline") != (baseline is not None):
        raise DiagnosisError(2, "baseline mode requires --baseline; rolling forbids it")
    if not 0 < min_match_rate <= 100:
        raise DiagnosisError(2, "min-match-rate must be in (0,100]")
    output = Path(output).absolute()
    if output.exists() or output.is_symlink():
        raise DiagnosisError(2, "refusing to overwrite existing report: " + str(output))
    inputs = [Path(p).resolve() for p in (capture, baseline) if p is not None]
    for source in inputs:
        root = source.parent if source.is_file() else source
        if output.resolve() == root or root in output.resolve().parents:
            raise DiagnosisError(2, "output must be outside read-only capture directories")
    debug = Path(debug_dir).absolute() if debug_dir else output.with_name(output.name + ".debug")
    if keep_debug:
        if debug.exists() or debug.is_symlink() or debug == output or output in debug.parents or debug in output.parents:
            raise DiagnosisError(2, "debug must be a fresh directory separate from the final report")
        if any((p.parent if p.is_file() else p) == debug.resolve() or
               (p.parent if p.is_file() else p) in debug.resolve().parents for p in inputs):
            raise DiagnosisError(2, "debug cannot be placed inside capture inputs")
    with tempfile.TemporaryDirectory(prefix="hccl-diag-") as temporary:
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
                            require_clock_alignment=require_clock_alignment)
                        _gate(reference, ready)
                    directory, ready = run_pipeline(current.manifest, work / "analysis", baseline=reference,
                        operation_map=pair_map if baseline is not None else None,
                        iteration_map=current.iteration_map if mode == "rolling" else None,
                        preparation_map=current.preparation_map if mode == "rolling" else None,
                        min_match_rate=min_match_rate, require_clock_alignment=require_clock_alignment,
                        comparison_options=comparison.ComparisonOptions(max_figures=0),
                        rolling_options=rolling.RollingOptions(max_figures=0), html_views=(), include_critical_path=False)
                pipeline = _gate(directory, ready)
                report = read_json(directory / ("rolling/report.json" if mode == "rolling" else "comparison/report.json"))
                rows = graph.read_graph_artifact_nodes(directory / "dep_graph_nodes.csv")
                edges = graph.read_graph_artifact_edges(directory / "dep_graph_edges.csv")
                normalized, roots, tasks = normalize(report, mode=mode,
                    run_id=current_capture.manifest["run_id"], rows=rows, edges=edges, pipeline=pipeline,
                    binding_evidence=dict(current.evidence, identity_exports=list(current_capture.identity_exports)),
                    merge_metrics=waits.read_csv(directory / "merge_summary.csv"))
            except DiagnosisError:
                raise
            except Exception as error:
                raise DiagnosisError(4, "analysis: " + str(error)) from error
            try:
                return publish_final_report(directory, output, normalized, roots, tasks)
            except Exception as error:
                raise DiagnosisError(5, "report publication: " + str(error)) from error
        finally:
            if keep_debug:
                try:
                    debug.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copytree(work, debug)
                except Exception as error:
                    print("hccl-diag: debug retention failed: " + str(error), file=sys.stderr)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, epilog="Exit codes: 0 pipeline passed (check report status/coverage); 2 input/binding; 3 association gate; 4 graph/diagnosis; 5 publication. Inputs are never deleted.")
    sub = parser.add_subparsers(dest="command", required=True)
    analyze = sub.add_parser("analyze", help="merge, build dependencies, diagnose and publish only three files")
    analyze.add_argument("--capture", type=Path, required=True)
    analyze.add_argument("--mode", choices=("baseline", "rolling"), required=True)
    analyze.add_argument("--baseline", type=Path)
    analyze.add_argument("--output", "-o", type=Path, required=True)
    analyze.add_argument("--topology", type=Path)
    analyze.add_argument("--manifest", type=Path)
    analyze.add_argument("--min-match-rate", type=float, default=95.0)
    analyze.add_argument("--require-clock-alignment", action="store_true")
    analyze.add_argument("--keep-debug", action="store_true")
    analyze.add_argument("--debug-dir", type=Path)
    analyze.add_argument("--verbose", action="store_true")
    args = parser.parse_args(argv)
    try:
        result = analyze_capture(**{key: value for key, value in vars(args).items() if key != "command"})
    except DiagnosisError as error:
        print("hccl-diag: " + str(error), file=sys.stderr)
        return error.code
    except KeyboardInterrupt:
        print("hccl-diag: interrupted; temporary analysis removed", file=sys.stderr)
        return 130
    print("status={} candidates={} chains={} output={}".format(result["status"], len(result["candidates"]),
          result["propagation"]["chain_count"], args.output.absolute()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
