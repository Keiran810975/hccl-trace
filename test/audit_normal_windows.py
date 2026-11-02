"""CPU-only fixed-window negative-control audit of a verified retained normal trace."""
from __future__ import annotations

import argparse
from collections import Counter
import csv
import hashlib
import json
from pathlib import Path, PurePosixPath
import shutil
import tarfile

from hccl.tools.diagnosis import rolling_diagnosis as rolling
from hccl.tools.diagnosis import visualize_dependency_graph as graph
from hccl.tools.diagnosis.task_classifier import INTERNAL


def digest(path):
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def extract_verified(source, destination):
    manifest = json.loads((source / "manifest.json").read_text())
    verified = json.loads((source / "verified.json").read_text())
    archive = source / "replay.tar.gz"
    if digest(archive) != verified["archive_sha256"]:
        raise ValueError("retained archive changed")
    parents = [str(PurePosixPath(p).parent) for p in manifest["files"] if p.endswith("/dep_graph_nodes.csv")]
    if len(parents) != 1:
        raise ValueError("expected one complete retained analysis")
    prefix = parents[0]
    names = {prefix + "/" + name for name in ("dep_graph_nodes.csv", "dep_graph_edges.csv", "clock_alignment.json",
             "run_summary.csv", "merge_summary.csv", "inputs.json")}
    names.update(("report.debug/current/iteration-map.json", "report.debug/current/preparation-map.json"))
    if not names <= set(manifest["files"]):
        raise ValueError("retained normal trace lacks required public inputs")
    destination.mkdir(parents=True, exist_ok=False)
    remaining = set(names)
    with tarfile.open(archive, "r|gz") as stream:
        for member in stream:
            if member.name not in remaining:
                continue
            relative = PurePosixPath(member.name)
            if relative.is_absolute() or ".." in relative.parts or not member.isfile():
                raise ValueError("unsafe normal-trace member")
            target = destination / member.name
            target.parent.mkdir(parents=True, exist_ok=True)
            with stream.extractfile(member) as content, target.open("xb") as output:
                shutil.copyfileobj(content, output)
            if digest(target) != manifest["files"][member.name]["sha256"]:
                raise ValueError("normal-trace member changed: " + member.name)
            remaining.remove(member.name)
            print("verified " + member.name, flush=True)
    if remaining or digest(archive) != verified["archive_sha256"]:
        raise ValueError("incomplete or concurrently changed archive")
    return destination / prefix, destination / "report.debug/current", verified["archive_sha256"]


def select_window(analysis, current, destination, end):
    coordinates = rolling.load_coordinates(current / "iteration-map.json")
    selected = {key: value for key, value in coordinates.items()
                if value["stage"] == "measured" and end - 5 <= value["iteration"] <= end}
    if {c["iteration"] for c in selected.values()} != set(range(end - 5, end + 1)):
        raise ValueError("fixed window lacks one of its five history iterations")
    destination.mkdir(parents=True, exist_ok=False)
    identifiers = set()
    with (analysis / "dep_graph_nodes.csv").open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        with (destination / "dep_graph_nodes.csv").open("w", encoding="utf-8", newline="") as output:
            writer = csv.DictWriter(output, fieldnames=reader.fieldnames)
            writer.writeheader()
            for row in reader:
                if row["profiler_op_scope"] in selected:
                    identifiers.add(row["graph_id"])
                    writer.writerow(row)
    cut = 0
    with (analysis / "dep_graph_edges.csv").open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        with (destination / "dep_graph_edges.csv").open("w", encoding="utf-8", newline="") as output:
            writer = csv.DictWriter(output, fieldnames=reader.fieldnames)
            writer.writeheader()
            for row in reader:
                src, dst = row["src"] in identifiers, row["dst"] in identifiers
                if src and dst:
                    writer.writerow(row)
                elif src or dst:
                    cut += 1
    rows = graph.read_graph_artifact_nodes(destination / "dep_graph_nodes.csv")
    edges = graph.read_graph_artifact_edges(destination / "dep_graph_edges.csv")
    alignment = json.loads((analysis / "clock_alignment.json").read_text())
    report = rolling.analyze(rows, edges, selected, rolling.RollingOptions(max_figures=0, calibrated_release_intervals=True),
        preparations=(), alignment=alignment)
    roots = [r for r in report["root_causes"] if r["diagnosis_category"] == INTERNAL]
    result = dict(evidence_scope="fixed normal window, not a full workload replay or accuracy estimate",
        selected_iteration=end, history_iterations=list(range(end - 5, end)), public_call_count=sum(c["iteration"] == end for c in selected.values()),
        node_count=len(rows), edge_count=len(edges), omitted_boundary_edges=cut,
        root_count=len(roots), roots=roots, coverage=report["coverage"], options=report["options"],
        host_observations_included=False, source_policy_version=report["source_policy_version"],
        task_count=report["task_count"], compared_task_count=report["compared_task_count"],
        target_task_count=sum(t["iteration"] == end for t in report["tasks"]),
        target_comparison_status_counts=dict(Counter(t["comparison_status"] for t in report["tasks"] if t["iteration"] == end)),
        history_only_tasks_are_not_evaluation_targets=True,
        selected_call_scopes=[key for key, coord in selected.items() if coord["iteration"] == end])
    (destination / "summary.json").write_text(json.dumps(result, indent=2) + "\n")
    return {k: value for k, value in result.items() if k not in {"roots", "selected_call_scopes"}}


def audit(source, output):
    output.mkdir(parents=True, exist_ok=False)
    # Freeze selection before reading any normal candidates. These are controls,
    # not a denominator chosen to maximize agreement with the changed analyzer.
    (output / "selection.json").write_text(json.dumps(dict(end_iterations=[10, 45],
        reference_window=5, selection_uses_candidate_results=False, npu_runs=0), indent=2) + "\n")
    analysis, current, archive_hash = extract_verified(source, output / "inputs")
    with (analysis / "run_summary.csv").open(newline="") as stream:
        gates = {r["metric"]: r["value"] for r in csv.DictReader(stream)}
    if any(gates.get(k) != "1" for k in ("graph_gate_passed", "topology_sync_gate_passed", "replay_gate_passed")):
        raise ValueError("original normal trace did not pass its complete pipeline gates")
    with (analysis / "merge_summary.csv").open(newline="") as stream:
        merge = [r for r in csv.DictReader(stream) if r["metric"] == "merge_gate_passed"]
    if len(merge) != len(json.loads((analysis / "inputs.json").read_text())["nodes"]) or any(r["value"] != "1" for r in merge):
        raise ValueError("original normal trace lacks complete semantic gates")
    results = []
    for end in (10, 45):
        result = select_window(analysis, current, output / ("iteration-" + str(end)), end)
        results.append(result)
        print(json.dumps(result), flush=True)
    receipt = dict(source_archive_sha256=archive_hash, original_complete_graph_gates_verified=True,
        rebuilt_dependency_edges=False, full_workload_replay=False, truth_consumed=False, windows=results)
    (output / "summary.json").write_text(json.dumps(receipt, indent=2) + "\n")
    return receipt


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    audit(args.source, args.output)
