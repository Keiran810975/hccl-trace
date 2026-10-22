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
    from diagnosis.multi_node_trace import load_manifest, replay_manifest
else:
    from . import analyze_waits as waits
    from . import critical_path as critical
    from . import visualize_dependency_graph as graph
    from . import visualize_html as view
    from .multi_node_trace import load_manifest, replay_manifest


def _run_pipeline(manifest: Path, output: Path, *, baseline: Path | None = None,
                  min_match_rate: float = 95.0):
    directory, ready = replay_manifest(manifest, output, min_match_rate)
    result = dict(status="failed", replay_gate_passed=ready, analysis_completed=False,
                  global_critical_path_available=False)
    if ready:
        rows = graph.read_graph_artifact_nodes(directory / "dep_graph_nodes.csv")
        edges = graph.read_graph_artifact_edges(directory / "dep_graph_edges.csv")
        issues = waits.read_csv(directory / "dep_graph_notify_ambiguities.csv")
        spans = [row for path in sorted(directory.glob("*/build_spans.csv")) for row in waits.read_csv(path)]
        reference = graph.read_graph_artifact_nodes(baseline / "dep_graph_nodes.csv") if baseline else []
        diagnosis = waits.analyze(rows, edges, issues, spans, reference)
        if not diagnosis["waits"]:
            raise ValueError("no Notify Wait evidence in the selected capture")
        waits.export_analysis(diagnosis, directory)
        coverage = [dict(code="notify_ambiguity", graph_id="", execution_edge_id="",
                         detail="{}:{}".format(item.get("relation_id", ""), item.get("status", "")))
                    for item in issues]
        critical.export_multi_node_report(
            critical.analyze_multi_node_critical_path(rows, edges, issues=coverage), directory / "critical_path")
        operations = view.read_operation_timings(directory / "operation_timings.csv")
        for name in ("execution", "waits", "resource"):
            selected_rows, selected_edges = rows, edges
            if name == "resource":
                selected_rows = graph.read_graph_artifact_nodes(directory / "dep_graph_resource_nodes.csv")
                selected_edges = graph.read_graph_artifact_edges(directory / "dep_graph_resource_edges.csv")
            model = view.build_execution_dependency_model(selected_rows, selected_edges, operations)
            model.update(graphView=name, issueCount=len(issues), waits=[])
            view.attach_diagnosis(model, diagnosis, diagnosis["waits"], name)
            view.write_html(directory / (name + ".html"), "HCCL " + name, model)
        result.update(status="passed", analysis_completed=True,
                      node_count=len({row["_node_id"] for row in rows}),
                      wait_count=len(diagnosis["waits"]),
                      paired_wait_count=sum(w["status"] == "paired" for w in diagnosis["waits"]),
                      candidate_count=len(diagnosis["candidates"]),
                      anomaly_baseline_supplied=baseline is not None)
    (directory / "pipeline_result.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    return directory, ready


def run_pipeline(manifest: Path, output: Path, *, baseline: Path | None = None,
                 min_match_rate: float = 95.0):
    directory = output / load_manifest(manifest)["run_id"]
    if directory.exists():
        raise FileExistsError("refusing to reuse diagnosis directory: {}".format(directory))
    try:
        return _run_pipeline(manifest, output, baseline=baseline, min_match_rate=min_match_rate)
    except (OSError, ValueError, KeyError, ArithmeticError) as error:
        if directory.is_dir():
            result = dict(status="failed", replay_gate_passed=None, analysis_completed=False,
                          global_critical_path_available=False, error=str(error))
            (directory / "pipeline_result.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("-o", "--output-dir", type=Path, required=True)
    parser.add_argument("--baseline-dir", type=Path)
    parser.add_argument("--min-match-rate", type=float, default=95.0)
    args = parser.parse_args()
    if not 0 < args.min_match_rate <= 100:
        parser.error("min-match-rate must be in (0, 100]")
    try:
        directory, ready = run_pipeline(args.manifest, args.output_dir, baseline=args.baseline_dir,
                                        min_match_rate=args.min_match_rate)
    except (OSError, ValueError, KeyError, ArithmeticError) as error:
        parser.exit(1, "diagnosis failed: {}\n".format(error))
    print("output={} pipeline_passed={} global_critical_path=unavailable".format(directory, int(ready)))
    return 0 if ready else 1


if __name__ == "__main__":
    raise SystemExit(main())
