"""Retain original sealed dual-v2 Top1 decisions with equal member presentation."""
from __future__ import annotations

# Archived experiment; supported diagnosis uses hccl-diag analyze.

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from test.refine_multinode_sources import digest


def adopt(cache, output):
    if output.exists():
        raise FileExistsError(output)
    proof = json.loads((cache / "verified.json").read_text())
    source = cache / "source_selection.json"
    if proof["truth_accessed"] is not False or digest(source) != proof["files"][source.name]:
        raise ValueError("original public decision changed")
    original = json.loads(source.read_text())
    proposal = original["primary_proposal"]
    result = dict(policy=original["policy"], candidate_relationship="parallel", truth_accessed=False,
        candidates=original["candidates"], chains=original["chains"], options=original["options"],
        summary=original["summary"], limits=original["limits"],
        cluster_selection=dict(policy="top1", selected_cluster_count=int(bool(original["candidates"])),
            selected_cluster_id=proposal["proposal_id"] if proposal else None,
            selected_mechanism=original["selected_mechanism"], selected_score=proposal["score"] if proposal else None,
            ranking_metric="original_dual_v2_relative_cluster_score_unchanged"),
        inputs=dict(public_cache=str(cache.resolve()), public_cache_receipt_sha256=digest(cache / "verified.json"),
                    original_archive_sha256=proof["original_archive_sha256"]),
        scope="unchanged_original_sealed_top1_decision_new_parallel_presentation_only")
    if original.get("source_region") and (original["source_region"]["region_id"] != proposal["proposal_id"]
            or {c["graph_id"] for c in result["candidates"]} != set(original["source_region"]["preliminary_graph_ids"])):
        raise ValueError("original Top1 candidate membership is inconsistent")
    output.mkdir(parents=True)
    target = output / "selection.json"
    target.write_text(json.dumps(result, indent=2) + "\n")
    root = Path(__file__).resolve().parents[3]
    names = ("hccl/tools/diagnosis/parallel_sources.py", "hccl/tools/diagnosis/multinode_source_policy.py",
             "hccl/tools/diagnosis/multinode_source_refinement.py", "test/archive/diagnosis_20261108/adopt_cluster_top1.py")
    (output / "sealed.json").write_text(json.dumps(dict(truth_accessed=False,
        selection_sha256=digest(target), original_decision_sha256=proof["files"][source.name],
        consumer_sha256={n: digest(root / n) for n in names}), indent=2) + "\n")
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    for cache in sorted(args.cache.iterdir()):
        if (cache / "verified.json").is_file():
            result = adopt(cache, args.output / cache.name)
            print(cache.name, len(result["candidates"]), "original Top1 members retained", flush=True)
