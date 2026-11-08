"""Publish one sealed Top1 decision on an exact original iteration graph slice."""
from __future__ import annotations

# Archived experiment; supported diagnosis uses hccl-diag analyze.

import argparse
import csv
import gzip
import io
import json
from pathlib import Path
import shutil
import sys
import tarfile

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from hccl.tools.diagnosis import analyze_waits, source_propagation
from hccl.tools.diagnosis import visualize_dependency_graph as graph
from hccl.tools.diagnosis.result_normalizer import normalize
from hccl.tools.diagnosis.report_exporter import publish_final_report
from test.refine_multinode_sources import digest
from test.archive.diagnosis_20261108.replay_parallel_sources import HashedReader


def materialize(original, replay, work, output):
    if work.exists() or output.exists():
        raise FileExistsError("never overwrite an earlier report or work directory")
    seal = json.loads((replay / "sealed.json").read_text())
    if seal["truth_accessed"] is not False or digest(replay / "selection.json") != seal["selection_sha256"]:
        raise ValueError("source decision seal changed")
    decision = json.loads((replay / "selection.json").read_text())
    if decision["cluster_selection"]["selected_cluster_count"] != 1:
        raise ValueError("this renderer needs one selected cluster/Host interval")
    epochs = {r["iteration"] for r in decision["candidates"]}
    cache = Path(decision["inputs"]["public_cache"])
    proof = json.loads((cache / "verified.json").read_text())
    if digest(cache / "tasks.jsonl.gz") != proof["files"]["tasks.jsonl.gz"]:
        raise ValueError("original public task cache changed")
    with gzip.open(cache / "tasks.jsonl.gz", "rt") as source:
        comparisons = [r for r in map(json.loads, source) if r.get("stage") == "measured" and r.get("iteration") in epochs]
    identifiers = {t["graph_id"] for t in comparisons}
    archive = original / "node0/replay.tar.gz"
    if digest(archive) != decision["inputs"]["original_archive_sha256"]:
        raise ValueError("original archive SHA changed")
    manifest = json.loads((original / "node0/manifest.json").read_text())["files"]
    wanted = {k: v for k, v in manifest.items() if k.endswith(("/dep_graph_nodes.csv", "/dep_graph_edges.csv"))
              and "/selected-iteration-view/" not in k}
    if len(wanted) != 2:
        raise ValueError("two full original graph artifacts required")
    work.mkdir(parents=True)
    found = set()
    with tarfile.open(archive, "r|gz") as tar:
        for member in tar:
            candidates = [k for k, v in wanted.items() if k not in found
                          and manifest.get(member.name, {}).get("sha256") == v["sha256"]]
            if not candidates or not member.isfile():
                continue
            name = candidates[0]
            raw = HashedReader(tar.extractfile(member))
            source = io.TextIOWrapper(io.BufferedReader(raw), encoding="utf-8-sig", newline="")
            with (work / Path(name).name).open("x", encoding="utf-8", newline="") as target:
                reader = csv.DictReader(source)
                writer = csv.DictWriter(target, reader.fieldnames)
                writer.writeheader()
                for row in reader:
                    keep = (row["graph_id"] in identifiers if name.endswith("nodes.csv") else
                            row["src"] in identifiers and row["dst"] in identifiers)
                    if keep:
                        writer.writerow(row)
            if raw.hasher.hexdigest() != wanted[name]["sha256"]:
                raise ValueError("original graph artifact SHA mismatch")
            found.add(name)
            if found == set(wanted):
                break
    if found != set(wanted):
        raise ValueError("original graph artifact missing")
    rows = graph.read_graph_artifact_nodes(work / "dep_graph_nodes.csv")
    edges = graph.read_graph_artifact_edges(work / "dep_graph_edges.csv")
    old = json.loads((original / "report/root_causes.json").read_text())
    report = dict(tasks=comparisons, task_count=len(comparisons),
        compared_task_count=sum(t["reference_count"] == 5 for t in comparisons), root_causes=decision["candidates"],
        primary_source_candidate_id=None, options=decision["options"], limits=decision["limits"], wait_backtraces=[],
        source_policy_version=decision["policy"], diagnosis_status="localized_candidate")
    normalized, roots, tasks = normalize(report, mode="rolling", run_id=old["run_id"], rows=rows, edges=edges,
        pipeline=dict(old["quality"], status="passed"), binding_evidence=old["binding"])
    normalized["source_candidates"] = normalized["candidates"] + normalized["external_anomaly_clues"]
    normalized["source_selection"] = {k: decision[k] for k in ("policy", "candidate_relationship", "summary", "cluster_selection")}
    normalized["analysis_scope"] = dict(kind="selected_iteration_slice_from_original_artifacts", iterations=sorted(epochs),
        original_artifact_sha256={k: v["sha256"] for k, v in wanted.items()}, original_full_graph_retained=True,
        raw_db_reparsed=False, original_dependency_cluster_membership_verified=True)
    normalized["quality"]["replay_scope"] = "original_full_capture_gates_and_verified_iteration_artifact_slice"
    propagation = source_propagation.build_report(rows, edges, roots, tasks)
    if any(not c["path_complete"] for r in propagation["candidates"] for c in r["chains"]):
        raise ValueError("selected evidence path is not present in original iteration slice")
    (work / "diagnosis.json").write_text(json.dumps(analyze_waits.analyze(rows, edges, trace_wait_chains=False)))
    (work / "operation_timings.csv").write_text("node_id,device_id,operation_scope,start_ns,end_ns,duration_ns\n")
    (work / "dep_graph_notify_ambiguities.csv").write_text("kind,reason\n")
    shutil.copy2(cache / "clock_alignment.json", work / "clock_alignment.json")
    result = publish_final_report(work, output, normalized, roots, tasks)
    (work / "sealed.json").write_text(json.dumps(dict(truth_accessed=False,
        selection_sha256=seal["selection_sha256"], reports={p.name: digest(p) for p in output.iterdir()},
        selection_consumer_sha256=seal["consumer_sha256"]), indent=2) + "\n")
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("original", "replay", "work", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args()
    result = materialize(args.original, args.replay, args.work, args.output)
    print(json.dumps(dict(candidates=len(result["source_candidates"]), propagation=result["propagation"])))
