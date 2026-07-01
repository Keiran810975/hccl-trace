#!/usr/bin/env python3
"""Merge HCCL semantic plog records with msprof task_time.csv rows."""

from __future__ import annotations

import argparse
import csv
import os
import sys
from collections import Counter, defaultdict
from typing import Dict, Iterable, List, Tuple

if __package__ in (None, ""):
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from diagnosis.parse_msprof import parse_file as parse_task_time_file
    from diagnosis.parse_plog import parse_file as parse_plog_file
    from diagnosis.schema import MERGED_FIELDS, ProfilerTask, SemanticRecord, write_csv
else:
    from .parse_msprof import parse_file as parse_task_time_file
    from .parse_plog import parse_file as parse_plog_file
    from .schema import MERGED_FIELDS, ProfilerTask, SemanticRecord, write_csv


def merge_records(
    semantics: Iterable[SemanticRecord],
    profilers: Iterable[ProfilerTask],
    rank_as_device_fallback: bool = False,
) -> Tuple[List[Dict[str, object]], Counter]:
    semantic_list = list(semantics)
    profiler_list = list(profilers)
    semantic_counts = Counter(record.merge_key for record in semantic_list)
    profiler_counts = Counter(record.merge_key for record in profiler_list)
    profiler_by_key = defaultdict(list)
    profiler_by_device_task_key = defaultdict(list)
    for task in profiler_list:
        profiler_by_key[task.merge_key].append(task)
        profiler_by_device_task_key[(task.device_id, task.stream_id, task.task_id)].append(task)

    rows = []
    matched_profiler_keys = set()
    stats = Counter()
    stats["semantic_total"] = len(semantic_list)
    stats["profiler_total"] = len(profiler_list)

    for semantic in semantic_list:
        if semantic.device_id < 0:
            stats["semantic_missing_device_id"] += 1

        matches = profiler_by_key.get(semantic.merge_key, [])
        if not matches and not semantic.node_id and semantic.device_id >= 0:
            matches = _unique_device_task_match(profiler_by_device_task_key, semantic.device_id, semantic)
            if matches:
                stats["node_id_fallback_matches"] += 1

        if not matches and rank_as_device_fallback and not semantic.node_id and semantic.device_id < 0:
            matches = _rank_as_device_match(profiler_by_device_task_key, semantic)
            if matches:
                stats["rank_device_fallback_matches"] += 1

        duplicate_semantic = semantic_counts[semantic.merge_key] > 1
        matched_profiler = matches[0] if matches else None
        profiler_key = matched_profiler.merge_key if matched_profiler else semantic.merge_key
        duplicate_profiler = profiler_counts[profiler_key] > 1
        if not matches:
            stats["unmatched_semantic"] += 1
            rows.append(_merged_row("unmatched_semantic", semantic, None, duplicate_semantic, duplicate_profiler))
            continue
        stats["matched"] += 1
        matched_profiler_keys.add(matched_profiler.merge_key)
        rows.append(_merged_row("matched", semantic, matched_profiler, duplicate_semantic, duplicate_profiler))

    for task in profiler_list:
        if task.merge_key in matched_profiler_keys:
            continue
        stats["unmatched_profiler"] += 1

    stats["duplicate_semantic_keys"] = sum(1 for count in semantic_counts.values() if count > 1)
    stats["duplicate_profiler_keys"] = sum(1 for count in profiler_counts.values() if count > 1)
    return rows, stats


def _unique_device_task_match(profiler_by_device_task_key, device_id: int, semantic: SemanticRecord) -> List[ProfilerTask]:
    matches = profiler_by_device_task_key.get((device_id, semantic.stream_id, semantic.task_id), [])
    return matches if len(matches) == 1 else []


def _rank_as_device_match(profiler_by_device_task_key, semantic: SemanticRecord) -> List[ProfilerTask]:
    candidate_device_ids = []
    for value in (semantic.user_rank, semantic.comm_rank):
        if value >= 0 and value not in candidate_device_ids:
            candidate_device_ids.append(value)

    unique_matches = []
    seen_keys = set()
    for device_id in candidate_device_ids:
        for task in _unique_device_task_match(profiler_by_device_task_key, device_id, semantic):
            if task.merge_key not in seen_keys:
                unique_matches.append(task)
                seen_keys.add(task.merge_key)
    return unique_matches if len(unique_matches) == 1 else []


def _merged_row(status: str, semantic: SemanticRecord, profiler: ProfilerTask, duplicate_semantic: bool, duplicate_profiler: bool):
    row = semantic.to_row()
    row.update({
        "match_status": status,
        "duplicate_semantic": int(duplicate_semantic),
        "duplicate_profiler": int(duplicate_profiler),
        "profiler_task_kind": profiler.task_kind if profiler else "",
        "task_start": profiler.task_start if profiler else "",
        "task_stop": profiler.task_stop if profiler else "",
        "duration": profiler.duration if profiler else "",
        "kernel_type": profiler.kernel_type if profiler else "",
    })
    return row


def main() -> int:
    parser = argparse.ArgumentParser(description="Merge HCCL semantic plog and msprof task_time.csv.")
    parser.add_argument("--plog", required=True)
    parser.add_argument("--task-time", required=True)
    parser.add_argument("-o", "--output", required=True)
    parser.add_argument("--node-id", default="")
    parser.add_argument("--summary", default="")
    parser.add_argument(
        "--rank-as-device-fallback",
        action="store_true",
        help="Use semantic rank as msprof Device_id only for legacy single-node plog without device_id.",
    )
    args = parser.parse_args()

    rows, stats = merge_records(
        parse_plog_file(args.plog),
        parse_task_time_file(args.task_time, args.node_id),
        rank_as_device_fallback=args.rank_as_device_fallback,
    )
    write_csv(args.output, list(MERGED_FIELDS), rows)
    for key in sorted(stats):
        print("{}={}".format(key, stats[key]))
    if args.summary:
        with open(args.summary, "w", newline="", encoding="utf-8") as output:
            writer = csv.writer(output)
            writer.writerow(("metric", "value"))
            for key in sorted(stats):
                writer.writerow((key, stats[key]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
