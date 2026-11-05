"""Reconstruct native source evidence from unchanged, verified execution artifacts."""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
import shutil
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from hccl.tools.diagnosis import visualize_dependency_graph as graph
from hccl.tools.diagnosis import source_propagation, analyze_waits
from hccl.tools.diagnosis.multinode_source_refinement import refine, finalize, validate_protocol_witnesses
from hccl.tools.diagnosis.result_normalizer import normalize
from hccl.tools.diagnosis.report_exporter import publish_final_report
from test.refine_multinode_sources import digest, load_segments


def filter_csv(source, target, predicate):
    target.parent.mkdir(parents=True, exist_ok=True)
    with source.open(encoding="utf-8-sig", newline="") as data, target.open("x", encoding="utf-8", newline="") as out:
        reader = csv.DictReader(data)
        writer = csv.DictWriter(out, reader.fieldnames)
        writer.writeheader()
        for row in reader:
            if predicate(row):
                writer.writerow(row)


def materialize(public, work, output):
    if output.exists():
        raise FileExistsError("never overwrite an original or previous refinement report")
    receipt = json.loads((public / "public-inputs.json").read_text())
    required = ("source_selection.json", "clock_alignment.json", "cross_node/segments.csv",
                "rolling/task_comparison.csv", "dep_graph_nodes.csv", "dep_graph_edges.csv")
    if receipt.get("truth_accessed") is not False or any(digest(public / name) != receipt["files"][name]["sha256"] for name in required):
        raise ValueError("verified public artifacts changed")
    selection = json.loads((public / "source_selection.json").read_text())
    alignment = json.loads((public / "clock_alignment.json").read_text())
    segments = load_segments(public / "cross_node/segments.csv")
    draft = refine(selection, segments, alignment)
    epochs = {r["iteration"] for r in draft["candidates"]}
    if not epochs:
        raise ValueError("this evidence renderer requires a selected measured epoch")
    wanted = {key for s in segments if s.get("status") == "protocol_interval_observed" for key in s["evidence_node_ids"]}
    epoch_ids = set()
    work.mkdir(parents=True, exist_ok=False)
    def keep_task(row):
        chosen = row.get("stage") == "measured" and row.get("iteration") and int(row["iteration"]) in epochs
        if chosen:
            epoch_ids.add(row["graph_id"])
        if chosen or row["graph_id"] in wanted:
            wanted.add(row["graph_id"])
            return True
        return False
    filter_csv(public / "rolling/task_comparison.csv", work / "all-comparisons.csv", keep_task)
    extras = set()
    def keep_edge(row):
        both = row["src"] in wanted and row["dst"] in wanted
        notify = "notify_sync" in row["kind"] and row["dst"] in wanted
        if notify:
            extras.add(row["src"])
        return both or notify
    filter_csv(public / "dep_graph_edges.csv", work / "witness-edges.csv", keep_edge)
    wanted.update(extras)
    filter_csv(public / "dep_graph_nodes.csv", work / "witness-nodes.csv", lambda row: row["graph_id"] in wanted)
    witness_rows = graph.read_graph_artifact_nodes(work / "witness-nodes.csv")
    witness_edges = graph.read_graph_artifact_edges(work / "witness-edges.csv")
    signatures = validate_protocol_witnesses(segments, witness_rows, witness_edges)
    decision = refine(selection, segments, alignment, witness_signatures=signatures)
    if [r["candidate_id"] for r in decision["candidates"]] != [r["candidate_id"] for r in draft["candidates"]]:
        raise ValueError("witness validation must not silently change source selection")
    # The view is an explicit iteration slice. The full original capture remains intact.
    filter_csv(work / "witness-nodes.csv", work / "dep_graph_nodes.csv", lambda row: row["graph_id"] in epoch_ids)
    filter_csv(work / "witness-edges.csv", work / "dep_graph_edges.csv",
               lambda row: row["src"] in epoch_ids and row["dst"] in epoch_ids)
    filter_csv(work / "all-comparisons.csv", work / "comparisons.csv", lambda row: row["graph_id"] in epoch_ids)
    rows = graph.read_graph_artifact_nodes(work / "dep_graph_nodes.csv")
    edges = graph.read_graph_artifact_edges(work / "dep_graph_edges.csv")
    comparisons = source_propagation.load_csv_records(work / "comparisons.csv")
    if any(t.get("occurrence") is not None and type(t["occurrence"]) is not int for t in comparisons):
        raise ValueError("materialized coordinates must retain native integer occurrence")
    original_dir = Path(receipt["source_archive"]).parents[1]
    original_manifest = json.loads((original_dir / "node0/manifest.json").read_text())
    original_report = original_dir / "report/root_causes.json"
    if digest(original_report) != original_manifest["files"]["report/root_causes.json"]["sha256"]:
        raise ValueError("original public report changed")
    original = json.loads(original_report.read_text())
    if original["quality"].get("notify_ambiguity_count") != 0:
        raise ValueError("this slice renderer requires the original zero-ambiguity graph gate")
    report = dict(tasks=comparisons, task_count=len(comparisons), compared_task_count=sum(t["reference_count"] == 5 for t in comparisons),
        options=decision["options"], limits=decision["limits"], wait_backtraces=[])
    chosen, result = finalize(report, decision, edges, alignment)
    witness = source_propagation.build_report(rows, edges, chosen["root_causes"], comparisons)
    if any(not c["path_complete"] for root in witness["candidates"] for c in root["chains"]):
        raise ValueError("an incomplete path may not be published as successful source evidence")
    pipeline = dict(original["quality"], status="passed")
    normalized, roots, tasks = normalize(chosen, mode="rolling", run_id=original["run_id"], rows=rows, edges=edges,
                                        pipeline=pipeline, binding_evidence=original["binding"])
    normalized["source_candidates"] = normalized["candidates"] + normalized["external_anomaly_clues"]
    normalized["primary_source_id"] = chosen["primary_source_candidate_id"]
    by_id = {r["root_id"]: r for r in roots}
    for source in normalized["source_candidates"]:
        source["source_unit"] = by_id[source["id"]]["source_unit"]
    normalized["source_selection"] = {k:result[k] for k in ("policy", "selected_mechanism", "primary_proposal", "transfer_coverage")}
    normalized["source_selection"]["outgoing_path_observations"] = result["outgoing_path_observations"]
    normalized["analysis_scope"] = dict(kind="selected_iteration_slice_from_original_artifacts", iterations=sorted(epochs),
        original_execution_html=str((original_dir / "report/execution.html").resolve()),
        raw_db_or_dependency_reconstruction_performed=False, original_artifact_sha256={name:receipt["files"][name]["sha256"] for name in required})
    (work / "diagnosis.json").write_text(json.dumps(analyze_waits.analyze(rows, edges, trace_wait_chains=False)))
    shutil.copy2(public / "clock_alignment.json", work / "clock_alignment.json")
    (work / "operation_timings.csv").write_text("node_id,device_id,operation_scope,start_ns,end_ns,duration_ns\n")
    (work / "dep_graph_notify_ambiguities.csv").write_text("kind,reason\n")
    result = publish_final_report(work, output, normalized, roots, tasks)
    root = Path(__file__).resolve().parents[1]
    consumers = tuple(str(p.relative_to(root)) for p in sorted((root / "hccl/tools/diagnosis").glob("*.py"))) + (
        "test/materialize_multinode_refinement.py", "test/refine_multinode_sources.py")
    inputs = dict(truth_accessed=False, root_report_sha256=digest(output / "root_causes.json"),
        artifact_inputs=normalized["analysis_scope"], selected_source_ids=[s["id"] for s in result["source_candidates"]],
        consumer_sha256={name:digest(root / name) for name in consumers},
        source_unit_counts={unit:sum(s["source_unit"] == unit for s in result["source_candidates"])
                            for unit in {s["source_unit"] for s in result["source_candidates"]}})
    (work / "decision.json").write_text(json.dumps(decision, indent=2) + "\n")
    (work / "sealed.json").write_text(json.dumps(inputs, indent=2) + "\n")
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--public", type=Path, required=True)
    parser.add_argument("--work", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = materialize(args.public, args.work, args.output)
    print(json.dumps(dict(sources=len(result["source_candidates"]), propagation=result["propagation"])))
