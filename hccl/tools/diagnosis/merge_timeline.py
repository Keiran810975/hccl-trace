#!/usr/bin/env python3
"""Merge HCCL semantic plog records with fine-grained msprof JSON rows."""

from __future__ import annotations

import argparse
import csv
import os
import sys
from collections import Counter, defaultdict
from dataclasses import replace
from pathlib import Path
from typing import Dict, Iterable, List, Tuple

if __package__ in (None, ""):
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from diagnosis.parse_msprof_json import parse_file as parse_msprof_json_file
    from diagnosis.parse_plog import parse_file as parse_plog_file
    from diagnosis.schema import MERGED_FIELDS, ProfilerTask, SemanticRecord, write_csv
else:
    from .parse_msprof_json import parse_file as parse_msprof_json_file
    from .parse_plog import parse_file as parse_plog_file
    from .schema import MERGED_FIELDS, ProfilerTask, SemanticRecord, write_csv


TASK_KIND_KERNEL_TYPES = {
    "sdma": {"MEMCPY_ASYNC"},
    "rdma": {"RDMASEND"},
    "reduce_inline": {"REDUCE_INLINE"},
    "reduce_tbe": {"REDUCE_TBE"},
    "notify_record": {"NOTIFY_RECORD"},
    "notify_wait": {"NOTIFY_WAIT"},
}


# The observed direct-ring FFts graph has three unannotated tasks before the
# first semantic row in each reduce-scatter AI_CORE group. Matches using this
# offset are explicitly marked heuristic in the merged output.
DIRECT_RING_COMPOSITE_FIRST_SEMANTIC_ORDINAL = 3


def merge_records(
    semantics: Iterable[SemanticRecord],
    profilers: Iterable[ProfilerTask],
) -> Tuple[List[Dict[str, object]], Counter]:
    semantic_list = list(semantics)
    profiler_list = list(profilers)
    stats = Counter()
    stats["semantic_total"] = len(semantic_list)
    stats["profiler_total"] = len(profiler_list)

    semantic_counts = Counter(_semantic_dedupe_key(record) for record in semantic_list)
    semantic_task_key_counts = Counter(record.merge_key for record in semantic_list)
    profiler_execution_counts = Counter(record.execution_key for record in profiler_list)
    json_exact_by_key = defaultdict(list)
    json_composite_by_key = defaultdict(list)
    for task in profiler_list:
        target = json_composite_by_key if task.subtask_id >= 0 else json_exact_by_key
        target[task.merge_key].append(task)
    for tasks in json_composite_by_key.values():
        tasks.sort(key=lambda task: (task.subtask_id, to_float_for_sort(task.task_start)))
    composite_group_starts = _composite_group_starts(semantic_list, json_composite_by_key)

    rows = []
    matched_profiler_keys = set()

    for semantic in semantic_list:
        if semantic.device_id < 0:
            stats["semantic_missing_device_id"] += 1

        matches = []
        match_method = ""
        match_confidence = ""
        composite = _json_composite_match(json_composite_by_key, composite_group_starts, semantic)
        if composite is not None:
            matches = [composite]
            match_method = "json_composite_profiler_seq"
            match_confidence = "heuristic"
            stats["json_composite_profiler_seq_matches"] += 1
            if not _is_compatible_task_kind(semantic, composite):
                stats["json_composite_kind_mismatches"] += 1
        else:
            exact_matches = _json_exact_matches(json_exact_by_key, semantic, semantic_task_key_counts)
            if exact_matches:
                matches = exact_matches
                match_method = "json_task_id"
                match_confidence = "exact"
                stats["json_task_id_matches"] += 1

        duplicate_semantic = semantic_counts[_semantic_dedupe_key(semantic)] > 1
        matched_profiler = matches[0] if matches else None
        duplicate_profiler = (
            profiler_execution_counts[matched_profiler.execution_key] > 1
            if matched_profiler else False
        )
        if not matches:
            stats["unmatched_semantic"] += 1
            rows.append(_merged_row("unmatched_semantic", semantic, None, duplicate_semantic, False))
            continue
        if matched_profiler.execution_key in matched_profiler_keys:
            stats["ambiguous_semantic"] += 1
            rows.append(_merged_row("ambiguous_semantic", semantic, matched_profiler,
                                    duplicate_semantic, True, match_method, match_confidence))
            continue
        stats["matched"] += 1
        matched_profiler_keys.add(matched_profiler.execution_key)
        rows.append(_merged_row("matched", semantic, matched_profiler, duplicate_semantic, duplicate_profiler,
                                match_method, match_confidence))

    for task in profiler_list:
        if task.execution_key in matched_profiler_keys:
            continue
        stats["unmatched_profiler"] += 1
        rows.append(_merged_row(
            "profiler_only",
            SemanticRecord(node_id=task.node_id, device_id=task.device_id,
                           stream_id=task.stream_id, task_id=task.task_id),
            task,
            False,
            profiler_execution_counts[task.execution_key] > 1,
        ))

    stats["duplicate_semantic_keys"] = sum(1 for count in semantic_counts.values() if count > 1)
    stats["duplicate_profiler_execution_keys"] = sum(
        1 for count in profiler_execution_counts.values() if count > 1)
    return rows, stats



def _is_compatible_task_kind(semantic: SemanticRecord, profiler: ProfilerTask) -> bool:
    expected = TASK_KIND_KERNEL_TYPES.get(str(semantic.task_kind or "").strip().lower())
    if not expected:
        return True
    return str(profiler.kernel_type or "").strip().upper() in expected


def _json_exact_matches(json_exact_by_key, semantic: SemanticRecord, semantic_task_key_counts) -> List[ProfilerTask]:
    if semantic.phase.startswith("reduce_scatter") and semantic_task_key_counts[semantic.merge_key] > 1:
        return []
    tasks = _json_group_lookup(json_exact_by_key, semantic, semantic.task_id)
    return [task for task in tasks if _is_compatible_task_kind(semantic, task)]


def _json_group_lookup(groups, semantic: SemanticRecord, task_id: int) -> List[ProfilerTask]:
    key = (semantic.node_id, semantic.device_id, semantic.stream_id, task_id)
    tasks = groups.get(key, [])
    if tasks or semantic.node_id:
        return tasks
    candidates = [
        value for candidate_key, value in groups.items()
        if candidate_key[1:] == (semantic.device_id, semantic.stream_id, task_id)
    ]
    return candidates[0] if len(candidates) == 1 else []


def _composite_group_starts(semantics, json_composite_by_key):
    starts = {}
    grouped = defaultdict(list)
    for semantic in semantics:
        if semantic.profiler_seq < 0 or not semantic.phase.startswith("reduce_scatter"):
            continue
        tasks = _json_group_lookup(json_composite_by_key, semantic, semantic.task_id + 1)
        if tasks:
            actual_key = tasks[0].merge_key
            grouped[actual_key].append(semantic)
    for key, records in grouped.items():
        first_seq = min(record.profiler_seq for record in records)
        starts[key] = first_seq - DIRECT_RING_COMPOSITE_FIRST_SEMANTIC_ORDINAL
    return starts


def _json_composite_match(json_composite_by_key, group_starts, semantic: SemanticRecord):
    tasks = _json_group_lookup(json_composite_by_key, semantic, semantic.task_id + 1)
    key = tasks[0].merge_key if tasks else None
    start = group_starts.get(key)
    if not tasks or start is None or semantic.profiler_seq < start:
        return None
    ordinal = semantic.profiler_seq - start
    return tasks[ordinal] if ordinal < len(tasks) else None


def to_float_for_sort(value: object) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0

def parse_msprof_json_inputs(msprof_json: str = "", msprof_json_dir: str = "", node_id: str = "",
                             device_id: int = None) -> List[ProfilerTask]:
    tasks: List[ProfilerTask] = []
    if msprof_json:
        tasks.extend(parse_msprof_json_file(msprof_json, node_id, device_id))
    if msprof_json_dir:
        for path in sorted(Path(msprof_json_dir).rglob("msprof_*.json")):
            tasks.extend(parse_msprof_json_file(str(path), node_id, device_id))
    return tasks


def parse_plog_inputs(plog: str = "", plog_dir: str = "", node_id: str = "") -> List[SemanticRecord]:
    records: List[SemanticRecord] = []
    if plog:
        records.extend(parse_plog_file(plog))
    if plog_dir:
        for path in sorted(Path(plog_dir).rglob("plog*.log")):
            records.extend(parse_plog_file(str(path)))
    if node_id:
        records = [replace(record, node_id=node_id) if not record.node_id else record for record in records]
    return records



def _semantic_dedupe_key(record: SemanticRecord):
    if record.semantic_seq >= 0 and record.device_id >= 0 and record.stream_id >= 0:
        return (record.node_id, record.device_id, record.stream_id, "semantic_seq", record.semantic_seq)
    return record.merge_key

def _merged_row(status: str, semantic: SemanticRecord, profiler: ProfilerTask, duplicate_semantic: bool,
                duplicate_profiler: bool, match_method: str = "", match_confidence: str = ""):
    row = semantic.to_row()
    row.update({
        "node_id": profiler.node_id if profiler else semantic.node_id,
        "device_id": profiler.device_id if profiler else semantic.device_id,
        "match_status": status,
        "duplicate_semantic": int(duplicate_semantic),
        "duplicate_profiler": int(duplicate_profiler),
        "profiler_task_kind": profiler.task_kind if profiler else "",
        "profiler_stream_id": profiler.stream_id if profiler else "",
        "profiler_task_id": profiler.task_id if profiler else "",
        "task_start": profiler.task_start if profiler else "",
        "task_stop": profiler.task_stop if profiler else "",
        "duration": profiler.duration if profiler else "",
        "kernel_type": profiler.kernel_type if profiler else "",
        "event_name": profiler.event_name if profiler else "",
        "subtask_id": profiler.subtask_id if profiler else "",
        "connection_id": profiler.connection_id if profiler else "",
        "model_id": profiler.model_id if profiler else "",
        "flow_id": profiler.flow_id if profiler else "",
        "match_method": match_method,
        "match_confidence": match_confidence,
    })
    return row


def main() -> int:
    parser = argparse.ArgumentParser(description="Merge HCCL semantic plog and fine-grained msprof JSON.")
    parser.add_argument("--plog", default="")
    parser.add_argument("--plog-dir", default="", help="Directory containing one or more plog*.log files.")
    parser.add_argument("--msprof-json", default="", help="Fine-grained msprof Chrome-trace JSON.")
    parser.add_argument("--msprof-json-dir", default="", help="Directory containing one or more msprof_*.json files.")
    parser.add_argument("--device-id", type=int, help="Override device id for a single JSON input.")
    parser.add_argument("-o", "--output", required=True)
    parser.add_argument("--node-id", default="")
    parser.add_argument("--summary", default="")
    args = parser.parse_args()
    if not args.plog and not args.plog_dir:
        parser.error("one of --plog or --plog-dir is required")
    if not args.msprof_json and not args.msprof_json_dir:
        parser.error("one of --msprof-json or --msprof-json-dir is required")
    if args.device_id is not None and args.msprof_json_dir:
        parser.error("--device-id is only valid with one --msprof-json file")

    profilers = parse_msprof_json_inputs(
        args.msprof_json, args.msprof_json_dir, args.node_id, args.device_id)

    rows, stats = merge_records(
        parse_plog_inputs(args.plog, args.plog_dir, args.node_id),
        profilers,
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
