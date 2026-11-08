"""Replay one dependency Top1, verifying exact original cluster membership first."""
from __future__ import annotations

# Archived experiment; supported diagnosis uses hccl-diag analyze.

import argparse
import fcntl
import gzip
import json
from pathlib import Path
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from hccl.tools.diagnosis.cluster_top1 import rank, finalize
from test.refine_multinode_sources import digest


def inputs(directory):
    proof = json.loads((directory / "verified.json").read_text())
    for name in ("tasks.jsonl.gz", "edges.jsonl.gz", "source_selection.json", "clock_alignment.json"):
        if digest(directory / name) != proof["files"][name]:
            raise ValueError("public cache changed: " + name)
    if proof["truth_accessed"] is not False:
        raise ValueError("only verified public inputs are accepted")
    with gzip.open(directory / "tasks.jsonl.gz", "rt") as stream:
        tasks = [json.loads(line) for line in stream]
    with gzip.open(directory / "edges.jsonl.gz", "rt") as stream:
        edges = [json.loads(line) for line in stream]
    old = json.loads((directory / "source_selection.json").read_text())
    hosts = [r for r in old["candidates"] if r.get("component") == "host_preparation"]
    declared = {p["proposal_id"] for p in old["proposals"] if p["mechanism"] == "host_preparation_late"}
    if declared != {h["source_activity_id"] for h in hosts}:
        raise ValueError("unretained valid Host proposals; this cache cannot faithfully replay dual selection")
    return tasks, edges, hosts, old, proof


def replay(directory, output):
    if output.exists():
        raise FileExistsError(output)
    tasks, edges, hosts, old, proof = inputs(directory)
    decision = rank(tasks, edges, hosts)
    actual = {c["region_id"] for c in decision["clusters"]}
    expected = {p["proposal_id"] for p in old["proposals"] if p["mechanism"] == "communication_execution_growth"}
    if actual != expected:
        raise ValueError("original cluster membership did not replay exactly: missing={}, extra={}".format(
            len(expected - actual), len(actual - expected)))
    if old.get("source_region"):
        original = old["source_region"]
        rebuilt = next(c for c in decision["clusters"] if c["region_id"] == original["region_id"])
        if rebuilt["preliminary_graph_ids"] != original["preliminary_graph_ids"]:
            raise ValueError("original selected cluster members changed")
    report = dict(tasks=tasks, root_causes=hosts, options=dict(slowdown_factor="1.5", mad_multiplier="3"))
    alignment = json.loads((directory / "clock_alignment.json").read_text())
    chosen, result = finalize(report, decision, edges, alignment)
    identifiers = {c["region_id"] for c in decision["clusters"] if c["selected"]}
    if len(identifiers) > 1 or any(r.get("region_id") not in identifiers for r in chosen["root_causes"] if r["component"] == "execution"):
        raise ValueError("Top1 invariant failed")
    old_scores = {p["proposal_id"]: p["score"] for p in old["proposals"]}
    selected = decision["selected_proposal"]
    result = dict(policy=result["policy"], candidate_relationship="parallel", truth_accessed=False,
        cluster_selection=result["cluster_selection"], selected_proposal=selected,
        candidates=result["candidates"], chains=result["chains"], summary=result["summary"],
        options=result["options"], limits=result["limits"], host_admission=result["host_admission"],
        cluster_rankings=[dict(p, old_relative_score=old_scores.get(p["proposal_id"])) for p in result["proposals"]],
        selected_cluster=next((c for c in result["clusters"] if c["selected"]), None),
        original_cluster_ids_identical=True, original_cluster_count=len(actual),
        original_selected_id=(old.get("primary_proposal") or {}).get("proposal_id"),
        original_candidates=old["candidates"],
        inputs=dict(public_cache=str(directory.resolve()), public_cache_receipt_sha256=digest(directory / "verified.json"),
                    original_archive_sha256=proof["original_archive_sha256"]),
        scope="original_dependency_cluster_and_directed_evidence_replay_not_new_DB_parse")
    output.mkdir(parents=True)
    target = output / "selection.json"
    target.write_text(json.dumps(result, indent=2) + "\n")
    root = Path(__file__).resolve().parents[3]
    names = ("hccl/tools/diagnosis/cluster_top1.py", "hccl/tools/diagnosis/local_slow_clusters.py",
        "hccl/tools/diagnosis/significant_regions.py", "hccl/tools/diagnosis/source_selection.py", "test/archive/diagnosis_20261108/replay_cluster_top1.py")
    (output / "sealed.json").write_text(json.dumps(dict(truth_accessed=False,
        selection_sha256=digest(target), consumer_sha256={n: digest(root / n) for n in names}), indent=2) + "\n")
    print(directory.name, json.dumps(dict(original_clusters=len(actual), selected=selected,
        candidates=len(result["candidates"]), chains=len(result["chains"])), ensure_ascii=False), flush=True)
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--batch", action="store_true")
    args = parser.parse_args()
    if args.batch:
        args.output.mkdir(parents=True, exist_ok=True)
        with (args.output / ".batch.lock").open("a+") as lock:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise SystemExit("another local replay batch already owns this output directory")
            for directory in sorted(args.cache.iterdir()):
                if (directory / "verified.json").is_file() and not (args.output / directory.name / "sealed.json").is_file():
                    subprocess.run([sys.executable, __file__, "--cache", str(directory), "--output", str(args.output / directory.name)], check=True)
    else:
        replay(args.cache, args.output)
