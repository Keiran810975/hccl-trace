"""Frozen single-node dual source diagnosis; publish an explicit original-graph iteration slice."""
from __future__ import annotations

import argparse
from dataclasses import asdict
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from hccl.tools.diagnosis import analyze_waits, rolling_diagnosis as rolling
from hccl.tools.diagnosis import visualize_dependency_graph as graph
from hccl.tools.diagnosis.multi_node_trace import replay_manifest
from hccl.tools.diagnosis.multinode_source_policy import select
from hccl.tools.diagnosis.report_exporter import publish_final_report
from hccl.tools.diagnosis.result_normalizer import normalize
from hccl.tools.diagnosis.visualize_html import build_wait_inventory
from test.materialize_multinode_refinement import filter_csv
from test.refine_multinode_sources import digest


def diagnose(capture, output):
    capture, output = Path(capture), Path(output)
    output.mkdir(exist_ok=False)
    public_inputs = {name: digest(capture / name) for name in (
        "manifest.json", "iteration-map.json", "preparation-map.json", "binding-evidence.json")}
    directory, passed = replay_manifest(capture / "manifest.json", output / "analysis", 95)
    if not passed:
        raise ValueError("strict semantic/dependency gate failed")
    rows = graph.read_graph_artifact_nodes(directory / "dep_graph_nodes.csv")
    edges = graph.read_graph_artifact_edges(directory / "dep_graph_edges.csv")
    coordinates = rolling.load_coordinates(capture / "iteration-map.json")
    options = rolling.RollingOptions(max_figures=0, source_policy="dual")
    report = rolling.analyze(rows, edges, coordinates, options,
        preparations=rolling.source_events.load_preparations(capture / "preparation-map.json"))
    chosen, selection = select(report, rows, edges, None)
    inventory = build_wait_inventory(rows, edges)
    pipeline = dict(status="passed", node_count=1, wait_count=len(inventory),
                    paired_wait_count=sum(w["status"] == "paired" for w in inventory))
    normalized, roots, comparisons = normalize(chosen, mode="rolling",
        run_id=json.loads((capture / "manifest.json").read_text())["run_id"], rows=rows, edges=edges,
        pipeline=pipeline, binding_evidence=json.loads((capture / "binding-evidence.json").read_text()),
        merge_metrics=analyze_waits.read_csv(directory / "merge_summary.csv"))
    normalized["source_candidates"] = normalized["candidates"] + normalized["external_anomaly_clues"]
    if len(normalized["source_candidates"]) != len(selection["candidates"]):
        raise ValueError("native export may not silently drop a selected source")
    normalized["primary_source_id"] = chosen["primary_source_candidate_id"]
    for candidate in normalized["source_candidates"]:
        candidate["source_unit"] = "host_preparation" if candidate["component"] == "host_preparation" else "execution_task"
    selected_epochs = sorted({c["iteration"] for c in normalized["source_candidates"]})
    epochs = selected_epochs or [max(c["iteration"] for c in coordinates.values() if c["stage"] == "measured")]
    wanted = {t["graph_id"] for t in comparisons if t.get("stage") == "measured" and t.get("iteration") in epochs}
    normalized["analysis_scope"] = dict(kind="selected_iteration_slice_from_original_artifacts", iterations=epochs,
        selected_source_iterations=selected_epochs, fallback_when_no_source="last_measured_context_only",
        original_full_graph_retained_until_verified_cleanup=True)
    normalized["source_selection"] = {k:selection[k] for k in ("policy", "selected_mechanism", "primary_proposal")}
    view = output / "view"
    filter_csv(directory / "dep_graph_nodes.csv", view / "dep_graph_nodes.csv", lambda r:r["graph_id"] in wanted)
    filter_csv(directory / "dep_graph_edges.csv", view / "dep_graph_edges.csv", lambda r:r["src"] in wanted and r["dst"] in wanted)
    view_rows = [r for r in rows if r["_graph_id"] in wanted]
    view_edges = [e for e in edges if e["src"] in wanted and e["dst"] in wanted]
    (view / "diagnosis.json").write_text(json.dumps(analyze_waits.analyze(view_rows, view_edges, trace_wait_chains=False)))
    (view / "operation_timings.csv").write_text("node_id,device_id,operation_scope,start_ns,end_ns,duration_ns\n")
    (view / "dep_graph_notify_ambiguities.csv").write_text("kind,reason\n")
    normalized = publish_final_report(view, output / "report", normalized, roots,
        [t for t in comparisons if t["graph_id"] in wanted])
    (output / "selection.json").write_text(json.dumps(selection, ensure_ascii=False) + "\n")
    import csv
    fields = ("graph_id", "node_id", "user_rank", "device_id", "stream_id", "task_id", "iteration", "task_kind",
              "observed_start_ns", "observed_stop_ns", "duration_ns", "reference_mean_ns", "reference_count", "slowdown_factor", "duration_slow")
    with (output / "resource-comparisons.csv").open("x", newline="") as stream:
        writer=csv.DictWriter(stream,fields,extrasaction="ignore"); writer.writeheader()
        writer.writerows(t for t in comparisons if t["task_domain"] == "hccl_internal" and t["task_kind"] in rolling.wait_backtrace.WORK_KINDS)
    for name in ("merge_summary.csv", "run_summary.csv", "dep_graph_summary.csv"):
        (output / name).write_bytes((directory / name).read_bytes())
    (output / "sealed.json").write_text(json.dumps(dict(truth_accessed=False, public_input_sha256=public_inputs,
        source_options=asdict(options), full_graph_input_sha256={name:digest(directory / name) for name in ("dep_graph_nodes.csv","dep_graph_edges.csv")},
        files={str(p.relative_to(output)):digest(p) for p in list((output / "report").iterdir()) + [output / "selection.json", output / "resource-comparisons.csv"]}), indent=2) + "\n")
    print(json.dumps(dict(status="passed",sources=len(normalized["source_candidates"]),
        mechanism=selection["selected_mechanism"],chains=normalized["propagation"]["chain_count"])),flush=True)


if __name__ == "__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--capture",type=Path,required=True)
    parser.add_argument("--output",type=Path,required=True)
    args=parser.parse_args()
    diagnose(args.capture,args.output)
