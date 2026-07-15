#!/usr/bin/env python3
"""Validate merged HCCL step trace data quality."""

from __future__ import annotations

import argparse
import csv
from collections import Counter


def validate_rows(rows, min_match_rate):
    stats = Counter()
    for row in rows:
        status = row.get("match_status", "")
        if status == "profiler_only":
            stats["profiler_only"] += 1
            if row.get("duplicate_profiler") == "1":
                stats["duplicate_profiler_rows"] += 1
            continue
        stats["total"] += 1
        stats[status] += 1
        if status == "matched" and row.get("match_confidence") == "heuristic":
            stats["heuristic_matched"] += 1
        elif status == "matched":
            stats["exact_matched"] += 1
        if row.get("duplicate_semantic") == "1":
            stats["duplicate_semantic_rows"] += 1
        if row.get("duplicate_profiler") == "1":
            stats["duplicate_profiler_rows"] += 1
    matched = stats.get("matched", 0)
    stats["match_rate_percent"] = round((matched * 100.0 / stats["total"]), 2) if stats["total"] else 0
    stats["exact_match_rate_percent"] = round(
        stats.get("exact_matched", 0) * 100.0 / stats["total"], 2
    ) if stats["total"] else 0
    ok = stats["total"] > 0 and stats["match_rate_percent"] >= min_match_rate
    if stats.get("duplicate_semantic_rows", 0) or stats.get("duplicate_profiler_rows", 0):
        ok = False
    return ok, stats


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate merged HCCL step trace coverage.")
    parser.add_argument("merged_csv")
    parser.add_argument("--min-match-rate", type=float, default=95.0)
    args = parser.parse_args()

    with open(args.merged_csv, "r", encoding="utf-8-sig", newline="") as source:
        ok, stats = validate_rows(csv.DictReader(source), args.min_match_rate)
    for key in sorted(stats):
        print("{}={}".format(key, stats[key]))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
