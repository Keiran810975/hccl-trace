#!/usr/bin/env python3
"""Merge HCCL semantic plog records with msprof task_time.csv rows."""

from __future__ import annotations

import argparse
import csv
import os
import sys
from collections import Counter, defaultdict
from pathlib import Path
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


EVENT_PRIORITY = {
    "rx_payload_reduce_start": 90,
    "rx_payload_copy_start": 85,
    "tx_payload_start": 80,
    "copy_start": 75,
    "tx_data_signal_start": 70,
    "rx_data_signal_start": 70,
    "tx_ack_start": 60,
    "rx_ack_start": 60,
    "allreduce_start": 10,
}


def merge_records(
    semantics: Iterable[SemanticRecord],
    profilers: Iterable[ProfilerTask],
    rank_as_device_fallback: bool = False,
    dedupe_semantic_keys: bool = True,
) -> Tuple[List[Dict[str, object]], Counter]:
    raw_semantic_list = list(semantics)
    profiler_list = list(profilers)
    stats = Counter()
    stats["semantic_total_input"] = len(raw_semantic_list)
    if dedupe_semantic_keys:
        semantic_list, dedupe_stats = _dedupe_semantics(raw_semantic_list)
        stats.update(dedupe_stats)
    else:
        semantic_list = raw_semantic_list
    stats["semantic_total"] = len(semantic_list)
    stats["profiler_total"] = len(profiler_list)

    semantic_counts = Counter(_semantic_dedupe_key(record) for record in semantic_list)
    profiler_counts = Counter(record.merge_key for record in profiler_list)
    profiler_by_key = defaultdict(list)
    profiler_by_device_task_key = defaultdict(list)
    profiler_by_sequence_key = {}
    profiler_by_device_stream_sequence_key = defaultdict(list)
    profiler_by_stream = defaultdict(list)
    for task in profiler_list:
        profiler_by_key[task.merge_key].append(task)
        profiler_by_device_task_key[(task.device_id, task.stream_id, task.task_id)].append(task)
        profiler_by_stream[(task.node_id, task.device_id, task.stream_id)].append(task)
    for stream_key, stream_tasks in profiler_by_stream.items():
        stream_tasks.sort(key=_profiler_sequence_sort_key)
        for sequence, task in enumerate(stream_tasks):
            profiler_by_sequence_key[stream_key + (sequence,)] = task
            _node_id, device_id, stream_id = stream_key
            profiler_by_device_stream_sequence_key[(device_id, stream_id, sequence)].append(task)

    rows = []
    matched_profiler_keys = set()

    for semantic in semantic_list:
        if semantic.device_id < 0:
            stats["semantic_missing_device_id"] += 1

        matches = []
        if semantic.semantic_seq >= 0 and semantic.device_id >= 0:
            sequence_key = (semantic.node_id, semantic.device_id, semantic.stream_id, semantic.semantic_seq)
            matched_by_sequence = profiler_by_sequence_key.get(sequence_key)
            if not matched_by_sequence and not semantic.node_id:
                fallback_matches = profiler_by_device_stream_sequence_key.get(
                    (semantic.device_id, semantic.stream_id, semantic.semantic_seq), [])
                if len(fallback_matches) == 1:
                    matched_by_sequence = fallback_matches[0]
                    stats["semantic_seq_node_id_fallback_matches"] += 1
            if matched_by_sequence:
                matches = [matched_by_sequence]
                stats["semantic_seq_matches"] += 1

        if not matches:
            matches = profiler_by_key.get(semantic.merge_key, [])
        if not matches and not semantic.node_id and semantic.device_id >= 0:
            matches = _unique_device_task_match(profiler_by_device_task_key, semantic.device_id, semantic)
            if matches:
                stats["node_id_fallback_matches"] += 1

        if not matches and rank_as_device_fallback and not semantic.node_id and semantic.device_id < 0:
            matches = _rank_as_device_match(profiler_by_device_task_key, semantic)
            if matches:
                stats["rank_device_fallback_matches"] += 1

        duplicate_semantic = semantic_counts[_semantic_dedupe_key(semantic)] > 1
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



def _profiler_sequence_sort_key(task: ProfilerTask):
    return (to_float_for_sort(task.task_start), to_float_for_sort(task.task_stop), task.task_id)


def to_float_for_sort(value: object) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0

def parse_task_time_inputs(task_time: str = "", task_time_dir: str = "", node_id: str = "") -> List[ProfilerTask]:
    tasks: List[ProfilerTask] = []
    if task_time:
        tasks.extend(parse_task_time_file(task_time, node_id))
    if task_time_dir:
        for path in sorted(Path(task_time_dir).rglob("task_time*.csv")):
            tasks.extend(parse_task_time_file(str(path), node_id))
    return tasks


def parse_plog_inputs(plog: str = "", plog_dir: str = "") -> List[SemanticRecord]:
    records: List[SemanticRecord] = []
    if plog:
        records.extend(parse_plog_file(plog))
    if plog_dir:
        for path in sorted(Path(plog_dir).rglob("plog*.log")):
            records.extend(parse_plog_file(str(path)))
    return records



def _semantic_dedupe_key(record: SemanticRecord):
    if record.semantic_seq >= 0 and record.device_id >= 0 and record.stream_id >= 0:
        return (record.node_id, record.device_id, record.stream_id, "semantic_seq", record.semantic_seq)
    return record.merge_key

def _dedupe_semantics(semantics: List[SemanticRecord]) -> Tuple[List[SemanticRecord], Counter]:
    stats = Counter()
    by_key = defaultdict(list)
    for index, record in enumerate(semantics):
        by_key[_semantic_dedupe_key(record)].append((index, record))

    deduped: List[SemanticRecord] = []
    for _key, items in by_key.items():
        if len(items) > 1:
            stats["duplicate_semantic_keys_input"] += 1
            stats["duplicate_semantic_rows_input"] += len(items)
            stats["deduped_semantic_rows"] += len(items) - 1
        _index, best = max(items, key=lambda item: (_semantic_specificity(item[1]), -item[0]))
        deduped.append(best)
    deduped.sort(key=lambda record: (record.node_id, record.device_id, record.stream_id, record.task_id))
    return deduped, stats


def _semantic_specificity(record: SemanticRecord) -> int:
    score = EVENT_PRIORITY.get(record.event, 40 if record.event else 0)
    if record.phase and record.phase != "allreduce_executor":
        score += 100
    if record.semantic and record.semantic != "allreduce_executor":
        score += 30
    if record.slice >= 0:
        score += 5
    if record.peer_rank >= 0:
        score += 5
    return score


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
    parser.add_argument("--plog", default="")
    parser.add_argument("--plog-dir", default="", help="Directory containing one or more plog*.log files.")
    parser.add_argument("--task-time", default="")
    parser.add_argument("--task-time-dir", default="", help="Directory containing one or more msprof task_time*.csv files.")
    parser.add_argument("-o", "--output", required=True)
    parser.add_argument("--node-id", default="")
    parser.add_argument("--summary", default="")
    parser.add_argument(
        "--rank-as-device-fallback",
        action="store_true",
        help="Use semantic rank as msprof Device_id only for legacy single-node plog without device_id.",
    )
    parser.add_argument(
        "--keep-duplicate-semantic-keys",
        action="store_true",
        help="Keep raw duplicate semantic merge keys instead of selecting one best semantic row per task.",
    )
    args = parser.parse_args()
    if not args.plog and not args.plog_dir:
        parser.error("one of --plog or --plog-dir is required")
    if not args.task_time and not args.task_time_dir:
        parser.error("one of --task-time or --task-time-dir is required")

    rows, stats = merge_records(
        parse_plog_inputs(args.plog, args.plog_dir),
        parse_task_time_inputs(args.task_time, args.task_time_dir, args.node_id),
        rank_as_device_fallback=args.rank_as_device_fallback,
        dedupe_semantic_keys=not args.keep_duplicate_semantic_keys,
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
