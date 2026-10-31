#!/usr/bin/env python3
"""Strict multi-node replay, wait analysis, local critical paths and artifact views."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys

if __package__ in (None, ""):
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from diagnosis import analyze_waits as waits
    from diagnosis import critical_path as critical
    from diagnosis import visualize_dependency_graph as graph
    from diagnosis import visualize_html as view
    from diagnosis import compare_diagnosis as comparison
    from diagnosis import rolling_diagnosis as rolling
    from diagnosis import source_propagation as propagation
    from diagnosis import rdma_timing
    from diagnosis import rdma_completion
    from diagnosis import cross_node_diagnosis, clock_alignment
    from diagnosis.multi_node_trace import load_manifest, replay_manifest
    from diagnosis.validate_dependency_graph import validate_dependency_artifacts
else:
    from . import analyze_waits as waits
    from . import critical_path as critical
    from . import visualize_dependency_graph as graph
    from . import visualize_html as view
    from . import compare_diagnosis as comparison
    from . import rolling_diagnosis as rolling
    from . import source_propagation as propagation
    from . import rdma_timing
    from . import rdma_completion
    from . import cross_node_diagnosis, clock_alignment
    from .multi_node_trace import load_manifest, replay_manifest
    from .validate_dependency_graph import validate_dependency_artifacts


def attach_rolling_sources(diagnosis, rolling_report):
    if rolling_report.get("source_policy_version", 1) >= 6:
        sources = [r for r in rolling_report["root_causes"]
                   if r.get("diagnosis_category") in {"communication_source_candidate", "external_anomaly_clue"}]
    else:
        sources = [r for r in rolling_report["root_causes"]
                   if r["status"] in {"dependency_supported_candidate", "isolated_slow_task"}
                   and (rolling_report.get("source_policy_version", 1) < 3 or r.get("primary_eligible", False))]
    diagnosis["reference_mode"] = rolling_report["reference_mode"]
    diagnosis["source_policy_version"] = rolling_report.get("source_policy_version", 1)
    diagnosis["diagnosis_status"] = rolling_report.get("diagnosis_status", "legacy_candidates")
    diagnosis["primary_source_candidate_id"] = rolling_report.get("primary_source_candidate_id")
    diagnosis["slow_event_count"] = rolling_report.get("slow_event_count", 0)
    diagnosis["coverage"] = rolling_report.get("coverage", {})
    diagnosis["wait_backtraces"] = rolling_report.get("wait_backtraces", [])
    diagnosis["unattributed_gap_count"] = sum(r["status"] == "unattributed_gap" for r in rolling_report["root_causes"])
    diagnosis["candidates"] = [dict(r, id=r["root_id"], category=r["component"], evidence=r["reason"]) for r in sources]
    by_wait = {}
    for root in sources:
        for identifier in dict.fromkeys(root["affected_wait_graph_ids"]):
            by_wait.setdefault(identifier, []).append(root)
    slow_ids = {t["graph_id"] for t in rolling_report["tasks"] if t["duration_slow"]}
    task_by_id = {t["graph_id"]: t for t in rolling_report["tasks"]}
    for wait in diagnosis["waits"]:
        related = by_wait.get(wait["wait_graph_id"], [])
        wait.update(rolling_slow=wait["wait_graph_id"] in slow_ids,
                    candidate_ids=";".join(r["root_id"] for r in related),
                    candidate_ranks=";".join(str(r["user_rank"]) for r in related),
                    candidate_phases=";".join(r["phase"] for r in related),
                    candidate_graph_ids=";".join(r["graph_id"] for r in related),
                    evidence_path_edge_ids=";".join(dict.fromkeys(
                        edge for r in related for edge in r["evidence_paths"][wait["wait_graph_id"]])),
                    attribution="dependency_path" if related else "")
        if related:
            wait["classification"] = "upstream_slow_candidate"
        elif wait.get("classification") == "pending_rolling":
            task = task_by_id.get(wait["wait_graph_id"], {})
            wait["classification"] = ("unresolved_upstream" if wait["rolling_slow"] else
                                       "not_flagged_by_rolling" if task.get("reference_count") == 5 else "not_comparable_history")


def _run_pipeline(manifest: Path, output: Path, *, baseline: Path | None = None,
                  min_match_rate: float = 95.0, comparison_options=comparison.ComparisonOptions(),
                  operation_map: Path | None = None, iteration_map: Path | None = None, preparation_map: Path | None = None,
                  rolling_options=rolling.RollingOptions(),
                  html_views=("execution", "waits", "resource"), include_critical_path=True, allow_uncalibrated_clock=False):
    directory, ready = replay_manifest(manifest, output, min_match_rate)
    return _analyze_replayed(directory, ready, baseline=baseline, comparison_options=comparison_options,
                             operation_map=operation_map, iteration_map=iteration_map, preparation_map=preparation_map,
                             rolling_options=rolling_options, html_views=html_views, include_critical_path=include_critical_path,
                             allow_uncalibrated_clock=allow_uncalibrated_clock)


def _stage(name):
    if os.environ.get("HCCL_DIAG_PROGRESS") == "1":
        print("DIAG_STAGE " + name, flush=True)


def _analyze_replayed(directory, ready, *, baseline=None, comparison_options=comparison.ComparisonOptions(),
                      operation_map=None, iteration_map=None, preparation_map=None, rolling_options=rolling.RollingOptions(),
                      html_views=("execution", "waits", "resource"), include_critical_path=True, allow_uncalibrated_clock=False):
    _stage("read_artifacts")
    result = dict(status="failed", replay_gate_passed=ready, analysis_completed=False,
                  global_critical_path_available=False)
    if ready:
        rows = graph.read_graph_artifact_nodes(directory / "dep_graph_nodes.csv")
        edges = graph.read_graph_artifact_edges(directory / "dep_graph_edges.csv")
        alignment_path = directory / "clock_alignment.json"
        clock_error = None
        try:
            if alignment_path.is_file():
                alignment = json.loads(alignment_path.read_text(encoding="utf-8-sig"))
                clock_alignment.models_from_report(alignment)
            else:
                inputs = json.loads((directory / "inputs.json").read_text(encoding="utf-8-sig"))
                alignment = clock_alignment.build(inputs, max_error_ns=inputs.get("clock_alignment_max_error_ns", 1000000))
            if alignment is not None:
                clocks = clock_alignment.models_from_report(alignment)
                for row in rows:
                    clock = clocks.get((row["_node_id"], row["_device_id"]))
                    if clock is None:
                        raise ValueError("clock evidence does not cover every execution device")
                    for side in ("start", "stop"):
                        clock.map_ns(waits.ns(row, side))
                alignment_path.write_text(json.dumps(alignment, indent=2) + "\n", encoding="utf-8")
        except (OSError, ValueError, KeyError, ArithmeticError) as error:
            if not allow_uncalibrated_clock:
                raise
            alignment, clock_error = None, str(error)
            # A rejected estimate must never be picked up by the HTML exporter.
            if alignment_path.exists():
                alignment_path.unlink()
        result.update(clock_alignment_available=alignment is not None,
                      clock_alignment_status=alignment["status"] if alignment else "uncalibrated",
                      clock_alignment_estimated_error_ns=alignment["estimated_error_ns"] if alignment else None,
                      clock_alignment_error=clock_error,
                      profiler_clock_validation=alignment.get("profiler_calibrations", []) if alignment else [])
        issues = waits.read_csv(directory / "dep_graph_notify_ambiguities.csv")
        spans = [row for path in sorted(directory.glob("*/build_spans.csv")) for row in waits.read_csv(path)]
        reference = graph.read_graph_artifact_nodes(baseline / "dep_graph_nodes.csv") if baseline else []
        _stage("wait_inventory" if iteration_map is not None else "legacy_wait_inventory")
        diagnosis = waits.analyze(rows, edges, issues, spans, reference, trace_wait_chains=iteration_map is None)
        if not diagnosis["waits"]:
            raise ValueError("no Notify Wait evidence in the selected capture")
        rolling_report = None
        if iteration_map is not None:
            _stage("rolling_compare_and_sources")
            rolling_report = rolling.analyze(rows, edges, rolling.load_coordinates(iteration_map), rolling_options,
                                            preparations=rolling.source_events.load_preparations(preparation_map), alignment=alignment)
            _stage("attach_rolling_sources")
            attach_rolling_sources(diagnosis, rolling_report)
        _stage("export_wait_analysis")
        coverage = [dict(code="notify_ambiguity", graph_id="", execution_edge_id="",
                         detail="{}:{}".format(item.get("relation_id", ""), item.get("status", "")))
                    for item in issues]
        if include_critical_path:
            _stage("local_critical_path")
            critical.export_multi_node_report(
                critical.analyze_multi_node_critical_path(rows, edges, issues=coverage), directory / "critical_path")
        operations = view.read_operation_timings(directory / "operation_timings.csv")
        protocol_displays, communication_lookup = [], {}
        if len({row["_node_id"] for row in rows}) > 1:
            _stage("rdma_protocol_timing")
            rdma_report = rdma_timing.analyze(rows, edges)
            rdma_timing.export_report(rdma_report, directory / "rdma_timing", execution_link="execution" in html_views)
            result.update(rdma_protocol_report="rdma_timing/index.html",
                          rdma_protocol_interval_count=rdma_report["summary"]["protocol_interval_count"],
                          rdma_unresolved_payload_count=rdma_report["summary"]["unresolved_payload_count"],
                          rdma_hardware_transfer_duration_available=False)
            completion_report = rdma_completion.analyze(rdma_completion.read_events(
                sorted(directory.glob("*/rdma_completion_events.csv"))))
            rdma_completion.export_report(completion_report, directory / "rdma_completion",
                dependency_link="execution" in html_views, protocol_link=True)
            result.update(rdma_completion_report="rdma_completion/index.html",
                          rdma_completion_observed_count=completion_report["summary"]["completion_observed_count"],
                          rdma_completion_trace_gap_count=completion_report["summary"]["trace_gap_count"],
                          rdma_completion_graph_binding_available=False,
                          rdma_full_transfer_and_dependency_available=False)
            communication_tasks = [row for path in sorted(directory.glob("*/communication_tasks.csv"))
                                   for row in waits.read_csv(path)]
            cross_report = cross_node_diagnosis.analyze(rdma_report, rows, edges,
                rolling.load_coordinates(iteration_map) if iteration_map else None, rolling_options,
                rolling_report=rolling_report, communication_tasks=communication_tasks,
                operations=waits.read_csv(directory / "operation_timings.csv"))
            cross_node_diagnosis.export_report(cross_report, directory / "cross_node", execution_link="execution" in html_views)
            protocol_displays = cross_node_diagnosis.display_rows(cross_report, rows)
            communication_lookup = {item["graph_id"]: item for item in cross_report["communication_tasks"]}
            diagnosis["cross_node_communication"] = dict(report="cross_node/report.json", **cross_report["summary"])
            result.update(cross_node_report="cross_node/index.html", **cross_report["summary"])
        waits.export_analysis(diagnosis, directory)
        for name in html_views:
            selected_rows, selected_edges = rows, edges
            if name == "resource":
                selected_rows = graph.read_graph_artifact_nodes(directory / "dep_graph_resource_nodes.csv")
                selected_edges = graph.read_graph_artifact_edges(directory / "dep_graph_resource_edges.csv")
            displays = list(operations) + (protocol_displays if name != "resource" else [])
            model = view.build_execution_dependency_model(selected_rows, selected_edges, displays, alignment=alignment)
            for node in model["nodes"]:
                if node["id"] in communication_lookup:
                    node["communication"] = communication_lookup[node["id"]]
            model.update(graphView=name, issueCount=len(issues), waits=[])
            view.attach_diagnosis(model, diagnosis, diagnosis["waits"], name)
            view.write_html(directory / (name + ".html"), "HCCL " + name, model)
        result.update(status="passed", analysis_completed=True,
                      local_critical_path_computed=include_critical_path,
                      legacy_wait_chain_search=iteration_map is None,
                      html_views=list(html_views),
                      node_count=len({row["_node_id"] for row in rows}),
                      wait_count=len(diagnosis["waits"]),
                      paired_wait_count=sum(w["status"] == "paired" for w in diagnosis["waits"]),
                      candidate_count=len(diagnosis["candidates"]),
                      anomaly_baseline_supplied=baseline is not None)
        if rolling_report is not None:
            _stage("export_rolling_report")
            rolling.export_report(rolling_report, rows, edges, directory / "rolling", rolling_options)
            _stage("export_source_first_paths")
            propagation_report = propagation.build_report(rows, edges, diagnosis["candidates"], rolling_report["tasks"],
                primary_source_candidate_id=rolling_report["primary_source_candidate_id"])
            propagation.export_report(propagation_report, directory / "propagation")
            result.update(reference_mode="previous_five_iteration_mean", rolling_report="rolling/index.html",
                          propagation_report="propagation/index.html",
                          propagation_candidate_count=propagation_report["summary"]["candidate_count"],
                          propagation_chain_count=propagation_report["summary"]["chain_count"],
                          propagation_complete_chain_count=propagation_report["summary"]["complete_chain_count"],
                          source_policy_version=rolling_report["source_policy_version"],
                          rolling_status=rolling_report["status"],
                          slow_task_count=rolling_report["slow_task_count"],
                          diagnosis_status=rolling_report["diagnosis_status"],
                          slow_event_count=rolling_report["slow_event_count"],
                          primary_eligible_count=rolling_report["primary_eligible_count"],
                          public_preparation_count=rolling_report["public_preparation_count"],
                          local_source_impact_computed=True,
                          wait_backtrace_count=len(rolling_report["wait_backtraces"]),
                          comparison_coverage=rolling_report["coverage"],
                          source_candidate_count=sum(r["status"] in {"dependency_supported_candidate", "isolated_slow_task"}
                                                     for r in rolling_report["root_causes"]),
                          unattributed_gap_count=rolling_report["gap_observation_count"])
        if baseline is not None:
            # The new directory has passed its gates, but its final status is not written yet.
            reference_rows = graph.read_graph_artifact_nodes(baseline / "dep_graph_nodes.csv")
            reference_edges = graph.read_graph_artifact_edges(baseline / "dep_graph_edges.csv")
            baseline_gate = baseline / "pipeline_result.json"
            if baseline_gate.exists() and json.loads(baseline_gate.read_text(encoding="utf-8-sig")).get("status") != "passed":
                raise ValueError("baseline diagnosis has not passed its gates")
            comparison.evidence_adjacency(reference_rows, reference_edges)
            report = comparison.analyze(rows, edges, reference_rows, comparison_options,
                                        comparison.load_operation_map(operation_map), baseline_edges=reference_edges)
            report.update(anomaly_artifact_dir=str(directory.resolve()), baseline_artifact_dir=str(baseline.resolve()))
            comparison.export_report(report, rows, edges, reference_rows, reference_edges,
                                     directory / "comparison", comparison_options)
            result.update(comparison_completed=True, comparison_report="comparison/index.html",
                          source_policy_version=report["source_policy_version"],
                          slow_task_count=report["slow_task_count"],
                          source_candidate_count=sum(r["status"] in {"dependency_supported_candidate", "isolated_slow_task"}
                                                     for r in report["root_causes"]),
                          unattributed_gap_count=report["gap_observation_count"])
    (directory / "pipeline_result.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    return directory, ready


def resume_replay_analysis(source, output, *, iteration_map, preparation_map=None, rolling_options=rolling.RollingOptions(), html_views=(), include_critical_path=True, allow_uncalibrated_clock=False):
    """Resume consumers only after revalidating a complete previously passed replay."""
    source, output = Path(source).resolve(), Path(output).resolve()
    if output.exists():
        raise FileExistsError("refusing to overwrite resumed analysis")
    manifest = json.loads((source / "inputs.json").read_text())
    metrics = {r["metric"]: r["value"] for r in waits.read_csv(source / "run_summary.csv")}
    if any(metrics.get(key) != "1" for key in ("graph_gate_passed", "topology_sync_gate_passed", "replay_gate_passed")):
        raise ValueError("resume requires a complete passed replay, not a partial graph")
    merges = waits.read_csv(source / "merge_summary.csv")
    gates = [r for r in merges if r["metric"] == "merge_gate_passed"]
    if len(gates) != len(manifest["nodes"]) or any(r["value"] != "1" for r in gates):
        raise ValueError("resume requires passed semantic gates for every node")
    ready, _, _ = validate_dependency_artifacts(source / "dep_graph_summary.csv", source / "dep_graph_edges.csv",
                                                source / "dep_graph_resource_summary.csv", source / "dep_graph_resource_edges.csv")
    if not ready:
        raise ValueError("resume graph revalidation failed")
    excluded = ("diagnosis", "critical_path", "rolling", "comparison", "propagation", "cross_node", "rdma_timing", "rdma_completion", "pipeline_result", "execution.html", "waits.html", "resource.html")
    output.mkdir(parents=True, exist_ok=False)
    for path in source.rglob("*"):
        relative = path.relative_to(source)
        if relative.parts[0].startswith(excluded):
            continue
        if path.is_symlink():
            raise ValueError("resume inputs cannot be symlinks")
        if path.is_dir():
            (output / relative).mkdir(exist_ok=True)
        else:
            (output / relative).parent.mkdir(parents=True, exist_ok=True)
            os.link(path, output / relative)
    (output / "resumed-from.json").write_text(json.dumps(dict(source=str(source),
        workload_rerun=False, replay_revalidated=True), indent=2) + "\n")
    return _analyze_replayed(output, True, iteration_map=iteration_map, preparation_map=preparation_map,
                             rolling_options=rolling_options, html_views=html_views, include_critical_path=include_critical_path,
                             allow_uncalibrated_clock=allow_uncalibrated_clock)


def run_pipeline(manifest: Path, output: Path, *, baseline: Path | None = None,
                 min_match_rate: float = 95.0, comparison_options=comparison.ComparisonOptions(),
                 operation_map: Path | None = None, iteration_map: Path | None = None, preparation_map: Path | None = None,
                 rolling_options=rolling.RollingOptions(),
                 html_views=("execution", "waits", "resource"), include_critical_path=True,
                 require_complete_rdma=False, require_clock_alignment=False, allow_uncalibrated_clock=False):
    if require_clock_alignment and allow_uncalibrated_clock:
        raise ValueError("required alignment and explicit local-clock fallback are mutually exclusive")
    if len(set(html_views)) != len(html_views) or set(html_views) - {"execution", "waits", "resource"}:
        raise ValueError("invalid HTML view selection")
    if iteration_map is not None and (baseline is not None or operation_map is not None):
        raise ValueError("rolling history must not be combined with an external baseline")
    if preparation_map is not None and iteration_map is None:
        raise ValueError("public preparations require an evidenced iteration map")
    directory = output / load_manifest(manifest)["run_id"]
    if directory.exists():
        raise FileExistsError("refusing to reuse diagnosis directory: {}".format(directory))
    try:
        directory, ready = _run_pipeline(manifest, output, baseline=baseline, min_match_rate=min_match_rate,
                             comparison_options=comparison_options, operation_map=operation_map,
                             iteration_map=iteration_map, preparation_map=preparation_map, rolling_options=rolling_options, html_views=html_views,
                             include_critical_path=include_critical_path, allow_uncalibrated_clock=allow_uncalibrated_clock)
        if require_complete_rdma:
            result_path = directory / "pipeline_result.json"
            result = json.loads(result_path.read_text(encoding="utf-8"))
            passed = result.get("rdma_full_transfer_and_dependency_available", False)
            result.update(rdma_completion_gate_required=True, rdma_completion_gate_passed=passed)
            if ready and not passed:
                result.update(status="incomplete", error="complete RDMA timing and exact task binding are unavailable")
            result_path.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
            ready = ready and passed
        if require_clock_alignment:
            result_path = directory / "pipeline_result.json"
            result = json.loads(result_path.read_text(encoding="utf-8"))
            passed = result.get("clock_alignment_available", False)
            result.update(clock_alignment_gate_required=True, clock_alignment_gate_passed=passed)
            if result.get("analysis_completed") and not passed:
                result.update(status="incomplete", error="clock probes/calibration do not cover this capture")
            result_path.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
            ready = ready and passed
        return directory, ready
    except (OSError, ValueError, KeyError, ArithmeticError) as error:
        if directory.is_dir():
            result = dict(status="failed", replay_gate_passed=None, analysis_completed=False,
                          global_critical_path_available=False, error=str(error))
            (directory / "pipeline_result.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
        raise


run_pipeline.rolling_wait_index_version = 2


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("-o", "--output-dir", type=Path, required=True)
    parser.add_argument("--baseline-dir", type=Path)
    parser.add_argument("--baseline-operation-map", type=Path)
    parser.add_argument("--iteration-map", type=Path,
                        help="Evidenced public workload coordinates; compare only the preceding five measured iterations")
    parser.add_argument("--preparation-map", type=Path, help="Public Host preparation/API observations, without injection truth")
    parser.add_argument("--rolling-slowdown-factor", default="1.5")
    parser.add_argument("--rolling-mad-multiplier", default="3")
    parser.add_argument("--comparison-min-increase-us", type=int, default=10)
    parser.add_argument("--comparison-slowdown-factor", default="1.5")
    parser.add_argument("--comparison-context-us", type=int, default=100)
    parser.add_argument("--comparison-max-figures", type=int, default=5)
    parser.add_argument("--min-match-rate", type=float, default=95.0)
    parser.add_argument("--require-complete-rdma", action="store_true",
                        help="Fail completion acceptance if true RDMA completion timing/task binding is missing")
    parser.add_argument("--require-clock-alignment", action="store_true",
                        help="Require independent before/after clock probes covering every node/device")
    args = parser.parse_args()
    if not 0 < args.min_match_rate <= 100:
        parser.error("min-match-rate must be in (0, 100]")
    try:
        directory, ready = run_pipeline(args.manifest, args.output_dir, baseline=args.baseline_dir,
                                        min_match_rate=args.min_match_rate,
                                        comparison_options=comparison.ComparisonOptions(
                                            args.comparison_min_increase_us * 1000, args.comparison_slowdown_factor,
                                            args.comparison_context_us * 1000, args.comparison_max_figures),
                                        operation_map=args.baseline_operation_map, iteration_map=args.iteration_map, preparation_map=args.preparation_map,
                                        rolling_options=rolling.RollingOptions(
                                            slowdown_factor=args.rolling_slowdown_factor,
                                            mad_multiplier=args.rolling_mad_multiplier,
                                            max_figures=args.comparison_max_figures),
                                        require_complete_rdma=args.require_complete_rdma,
                                        require_clock_alignment=args.require_clock_alignment)
    except (OSError, ValueError, KeyError, ArithmeticError) as error:
        parser.exit(1, "diagnosis failed: {}\n".format(error))
    print("output={} pipeline_passed={} global_critical_path=unavailable".format(directory, int(ready)))
    return 0 if ready else 1


if __name__ == "__main__":
    raise SystemExit(main())
