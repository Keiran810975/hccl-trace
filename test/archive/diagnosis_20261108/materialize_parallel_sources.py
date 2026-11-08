"""Publish a separate three-file artifact replay, never overwrite sealed reports."""
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
from hccl.tools.diagnosis.parallel_sources import execution_calls, qualify_call_spans, select
from hccl.tools.diagnosis.result_normalizer import normalize
from hccl.tools.diagnosis.report_exporter import publish_final_report
from test.archive.diagnosis_20261108.replay_parallel_sources import HashedReader
from test.refine_multinode_sources import digest


def materialize(original, replay, work, output):
    seal = json.loads((replay / "sealed.json").read_text())
    if (seal["truth_accessed"] is not False or digest(replay / "selection.json") != seal["selection_sha256"]
            or digest(replay / "work-facts.jsonl.gz") != seal["public_cache_sha256"]):
        raise ValueError("public-fact selection seal changed")
    policy_path = "hccl/tools/diagnosis/parallel_sources.py"
    root = Path(__file__).resolve().parents[3]
    if digest(root / policy_path) != seal["consumer_sha256"][policy_path]:
        raise ValueError("materialization must use the sealed selection policy")
    with gzip.open(replay / "work-facts.jsonl.gz", "rt") as stream:
        tasks = [json.loads(line) for line in stream]
    regions, _ = execution_calls(tasks)
    call_span_observations = None
    if seal.get("call_spans_sha256"):
        if digest(replay / "call-spans.json") != seal["call_spans_sha256"]:
            raise ValueError("full call envelope facts changed")
        payload = json.loads((replay / "call-spans.json").read_text())
        call_span_observations = {tuple(r["key"]): (r["start_ns"], r["stop_ns"]) for r in payload["spans"]}
        regions, _ = qualify_call_spans(regions, call_span_observations)
    epochs = {r["iteration"] for r in regions}
    scopes = {r["operation_scope"] for r in regions}
    if not epochs:
        raise ValueError("there is no selected iteration to render")
    work.mkdir(parents=True, exist_ok=False)
    archive = original / "node0/replay.tar.gz"
    verified = json.loads((original / "node0/verified.json").read_text())
    if digest(archive) != verified["archive_sha256"]:
        raise ValueError("original archive changed")
    manifest = json.loads((original / "node0/manifest.json").read_text())["files"]
    suffixes = ("/dep_graph_nodes.csv", "/dep_graph_edges.csv", "/rolling/task_comparison.csv", "/clock_alignment.json")
    wanted = {name: value for name, value in manifest.items() if any(name.endswith(s) for s in suffixes)
              and "/selected-iteration-view/" not in name}
    if len(wanted) != 4:
        raise ValueError("expected four original full-capture artifact inputs")
    found = set()
    identifiers = set()
    with tarfile.open(archive, "r|gz") as tar:
        for member in tar:
            archived = manifest.get(member.name, {})
            matches = [name for name, value in wanted.items() if name not in found
                       and value["sha256"] == archived.get("sha256")]
            if not matches or not member.isfile():
                continue
            wanted_name = matches[0]
            expected = wanted[wanted_name]
            raw = HashedReader(tar.extractfile(member))
            stream = io.TextIOWrapper(io.BufferedReader(raw), encoding="utf-8-sig", newline="")
            name = Path(wanted_name).name
            if name == "clock_alignment.json":
                (work / name).write_text(stream.read())
            elif name == "dep_graph_edges.csv":
                with (work / "all-edges.csv").open("x", encoding="utf-8", newline="") as target:
                    shutil.copyfileobj(stream, target)
            else:
                with (work / name).open("x", encoding="utf-8", newline="") as target:
                    reader = csv.DictReader(stream)
                    writer = csv.DictWriter(target, reader.fieldnames)
                    writer.writeheader()
                    for row in reader:
                        selected = (row.get("profiler_op_scope") in scopes if name == "dep_graph_nodes.csv" else
                                    row.get("operation_scope") in scopes)
                        if selected:
                            writer.writerow(row)
                            if name == "dep_graph_nodes.csv":
                                identifiers.add(row["graph_id"])
            if raw.hasher.hexdigest() != expected["sha256"]:
                raise ValueError("original artifact member SHA mismatch: " + member.name)
            found.add(wanted_name)
            if found == set(wanted):
                break
    if found != set(wanted):
        raise ValueError("original full artifact is missing or deduplicated; refusing to guess")
    with (work / "all-edges.csv").open(encoding="utf-8", newline="") as source, (work / "dep_graph_edges.csv").open("x", encoding="utf-8", newline="") as target:
        reader = csv.DictReader(source)
        writer = csv.DictWriter(target, reader.fieldnames)
        writer.writeheader()
        writer.writerows(r for r in reader if r["src"] in identifiers and r["dst"] in identifiers)
    rows = graph.read_graph_artifact_nodes(work / "dep_graph_nodes.csv")
    edges = graph.read_graph_artifact_edges(work / "dep_graph_edges.csv")
    comparisons = source_propagation.load_csv_records(work / "task_comparison.csv")
    # Full work facts retain exact five-iteration histories; control/Wait rows
    # and all propagation edges come from the selected original iteration slice.
    work_ids = {t["graph_id"] for t in tasks}
    extra = [t for t in comparisons if t["graph_id"] not in work_ids]
    report = dict(tasks=tasks + extra, root_causes=[], options=dict(slowdown_factor="1.5", mad_multiplier="3"))
    if call_span_observations is not None:
        report["call_span_observations"] = call_span_observations
    alignment = json.loads((work / "clock_alignment.json").read_text())
    chosen, decision = select(report, edges, alignment)
    old = json.loads((original / "report/root_causes.json").read_text())
    expected_ids = {t["graph_id"] for t in json.loads((replay / "selection.json").read_text())["candidates"]}
    if not {r["graph_id"] for r in chosen["root_causes"]} <= expected_ids:
        raise ValueError("DAG refinement introduced a task outside sealed public preselection")
    chosen.update(tasks=comparisons, task_count=len(comparisons),
                  compared_task_count=sum(t["reference_count"] == 5 for t in comparisons), wait_backtraces=[])
    normalized, roots, comparisons = normalize(chosen, mode="rolling", run_id=old["run_id"], rows=rows, edges=edges,
        pipeline=dict(old["quality"], status="passed"), binding_evidence=old["binding"])
    normalized["source_candidates"] = normalized["candidates"] + normalized["external_anomaly_clues"]
    normalized["source_selection"] = {k: decision[k] for k in ("policy", "candidate_relationship", "summary", "call_admission", "call_span_admission")}
    normalized["analysis_scope"] = dict(kind="selected_call_slice_from_original_artifacts", iterations=sorted(epochs),
        selected_operation_scopes=sorted(scopes),
        diagnosis_used_full_work_population=True, raw_db_reparsed=False, original_full_graph_retained=True,
        original_artifact_sha256={k: v["sha256"] for k, v in wanted.items()})
    normalized["quality"]["replay_scope"] = "original_full_capture_gates_with_new_artifact_slice_source_analysis"
    (work / "diagnosis.json").write_text(json.dumps(analyze_waits.analyze(rows, edges, trace_wait_chains=False)))
    (work / "operation_timings.csv").write_text("node_id,device_id,operation_scope,start_ns,end_ns,duration_ns\n")
    (work / "dep_graph_notify_ambiguities.csv").write_text("kind,reason\n")
    source_propagation_report = source_propagation.build_report(rows, edges, roots, comparisons)
    if any(not c["path_complete"] for r in source_propagation_report["candidates"] for c in r["chains"]):
        raise ValueError("published evidence path is incomplete")
    result = publish_final_report(work, output, normalized, roots, comparisons)
    (work / "sealed.json").write_text(json.dumps(dict(truth_accessed=False,
        reports={p.name: digest(p) for p in output.iterdir()}, original_archive_sha256=verified["archive_sha256"],
        selection_sha256=seal["selection_sha256"]), indent=2) + "\n")
    (work / "source_selection.json").write_text(json.dumps(decision, indent=2) + "\n")
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("original", "replay", "work", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args()
    result = materialize(args.original, args.replay, args.work, args.output)
    print(json.dumps(dict(candidates=len(result["candidates"]), propagation=result["propagation"])))
