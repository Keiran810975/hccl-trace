"""Replay cohort-supported Top1 on verified public facts without injection inputs."""
from __future__ import annotations

# Archived experiment; supported diagnosis uses hccl-diag analyze.

import argparse
import fcntl
import json
from pathlib import Path
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from hccl.tools.diagnosis.cohort_source_policy import rank, finalize
from test.archive.diagnosis_20261108.replay_cluster_top1 import inputs
from test.refine_multinode_sources import digest


def replay(cache, output):
    if output.exists():
        raise FileExistsError(output)
    tasks, edges, hosts, old, proof = inputs(cache)
    decision = rank(tasks, edges, hosts)
    expected = {p["proposal_id"] for p in old["proposals"] if p["mechanism"] == "communication_execution_growth"}
    actual = {c["region_id"] for c in decision["clusters"]}
    if expected != actual:
        raise ValueError("cohort support must not change the original dependency clusters")
    if old.get("source_region"):
        original = old["source_region"]
        rebuilt = next(c for c in decision["clusters"] if c["region_id"] == original["region_id"])
        if original["preliminary_graph_ids"] != rebuilt["preliminary_graph_ids"]:
            raise ValueError("original cluster members changed")
    report = dict(tasks=tasks, root_causes=hosts, options=dict(slowdown_factor="1.5", mad_multiplier="3"))
    alignment = json.loads((cache / "clock_alignment.json").read_text())
    chosen, result = finalize(report, decision, edges, alignment)
    if result["cluster_selection"]["selected_cluster_count"] > 1 or chosen["primary_source_candidate_id"] is not None:
        raise ValueError("single cluster with parallel members required")
    old_scores = {p["proposal_id"]: p["score"] for p in old["proposals"]}
    value = dict(policy=result["policy"], candidate_relationship="parallel", truth_accessed=False,
        cluster_selection=result["cluster_selection"], selected_proposal=result["primary_proposal"],
        candidates=result["candidates"], chains=result["chains"], summary=result["summary"],
        options=result["options"], limits=result["limits"], host_admission=result["host_admission"],
        cohort_quality=result["cohort_quality"], cluster_quality=result["cluster_quality"],
        cluster_rankings=[dict(p, original_relative_score=old_scores.get(p["proposal_id"])) for p in result["proposals"]],
        selected_cluster=result["source_region"], original_cluster_ids_identical=True,
        original_cluster_count=len(actual), original_candidates=old["candidates"],
        inputs=dict(public_cache=str(cache.resolve()), public_cache_receipt_sha256=digest(cache / "verified.json"),
                    original_archive_sha256=proof["original_archive_sha256"]),
        scope="public_population_supported_original_artifact_replay_not_new_DB_parse")
    output.mkdir(parents=True)
    (output / "selection.json").write_text(json.dumps(value, indent=2) + "\n")
    root = Path(__file__).resolve().parents[3]
    names = ("hccl/tools/diagnosis/cohort_source_policy.py", "hccl/tools/diagnosis/local_slow_clusters.py",
        "hccl/tools/diagnosis/multinode_source_refinement.py", "hccl/tools/diagnosis/source_selection.py",
        "hccl/tools/diagnosis/significant_regions.py", "hccl/tools/diagnosis/dependency_timing.py",
        "test/archive/diagnosis_20261108/replay_cluster_top1.py", "test/archive/diagnosis_20261108/replay_cohort_sources.py")
    (output / "sealed.json").write_text(json.dumps(dict(truth_accessed=False,
        selection_sha256=digest(output / "selection.json"), consumer_sha256={n:digest(root / n) for n in names}), indent=2) + "\n")
    print(cache.name, json.dumps(dict(candidate_count=len(value["candidates"]),
        selected_cluster_id=value["cluster_selection"]["selected_cluster_id"],
        cohort_quality=value["cohort_quality"], chains=len(value["chains"]))), flush=True)
    return value


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
                raise SystemExit("another local cohort replay batch owns this output")
            for directory in sorted(args.cache.iterdir()):
                if (directory / "verified.json").is_file() and not (args.output / directory.name / "sealed.json").exists():
                    subprocess.run([sys.executable, __file__, "--cache", str(directory), "--output", str(args.output / directory.name)], check=True)
    else:
        replay(args.cache, args.output)
