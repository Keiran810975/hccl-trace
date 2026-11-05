"""Independent evaluation of an already-sealed, same-version six-case replay."""
from __future__ import annotations

import argparse
from collections import Counter
import csv
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from test.refine_multinode_sources import digest


def evaluate(report, windows):
    records = []
    for source in report["candidates"]:
        overlap = max([0] + [max(0, min(source["observed_stop_ns"], w["stop_ns"]) - max(
            source["observed_start_ns"], w["start_ns"])) for w in windows
            if (source["node_id"], source["user_rank"]) == (w["node_id"], w["user_rank"])])
        records.append(dict(candidate_id=source["candidate_id"], source_unit=source["source_unit"],
            node_id=source["node_id"], user_rank=source["user_rank"], iteration=source["iteration"],
            observed_start_ns=source["observed_start_ns"], observed_stop_ns=source["observed_stop_ns"],
            overlap_ns=overlap, hit=overlap > 0))
    return records


def summarize(replays, original_path, output):
    original = json.loads(original_path.read_text())
    cases, consumers = [], None
    for index, old in enumerate(original["cases"], 521):
        path = replays / str(index) / "selection.json"
        seal = json.loads(path.with_name("sealed.json").read_text())
        if seal.get("truth_accessed") is not False or digest(path) != seal["selection_sha256"]:
            raise ValueError("all source outputs must be sealed before independent evaluation")
        report = json.loads(path.read_text())
        if report["inputs"]["original_archive_sha256"] != old["original_archives"][0]["sha256"]:
            raise ValueError("replay and original experiment identity differ")
        if consumers is None:
            consumers = seal["consumer_sha256"]
        if consumers != seal["consumer_sha256"]:
            raise ValueError("one unchanged consumer version required for all six cases")
        candidates = evaluate(report, old["windows"])
        hits = sum(c["hit"] for c in candidates)
        units = {}
        for unit in {c["source_unit"] for c in candidates}:
            subset = [c for c in candidates if c["source_unit"] == unit]
            units[unit] = dict(hits=sum(c["hit"] for c in subset), count=len(subset))
        cases.append(dict(case_id=old["case_id"], kind=old["kind"], mechanism=report["selected_mechanism"],
            hits=hits, count=len(candidates), fraction=hits / len(candidates) if candidates else None,
            first_candidate_hit=bool(candidates and candidates[0]["hit"]), units=units, candidates=candidates,
            selection_sha256=seal["selection_sha256"], original_hits=old["hit_count"],
            original_count=old["candidate_count"], original_windows_unchanged=old["windows"]))
    anomalies = cases[1:]
    count = sum(c["count"] for c in anomalies)
    hits = sum(c["hits"] for c in anomalies)
    result = dict(schema_version=1, criterion="same_node_same_rank_positive_overlap_original_windows_unchanged",
        scope="known_sample_offline_development_not_independent_validation", cases=cases,
        hits=hits, count=count, fraction=hits/count if count else None,
        any_hit_cases=sum(c["hits"] > 0 for c in anomalies), first_hit_cases=sum(c["first_candidate_hit"] for c in anomalies),
        normal_candidate_count=cases[0]["count"], same_consumer_sha256=consumers,
        caution="Execution tasks, Host intervals and submission-to-notification intervals are different units; no hardware RDMA completion is claimed.")
    with output.open("x", encoding="utf-8") as target:
        json.dump(result, target, indent=2)
        target.write("\n")
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--replays", type=Path, required=True)
    parser.add_argument("--original", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = summarize(args.replays, args.original, args.output)
    print(json.dumps({k:v for k,v in result.items() if k not in {"cases", "same_consumer_sha256"}}))
    for case in result["cases"]:
        print(case["kind"], case["mechanism"], "{}/{}".format(case["hits"], case["count"]),
              sorted({(c["user_rank"], c["iteration"]) for c in case["candidates"]}))
