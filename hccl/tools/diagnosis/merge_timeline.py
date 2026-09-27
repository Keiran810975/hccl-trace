#!/usr/bin/env python3
"""Merge HCCL semantic plog records with fine-grained msprof DB executions."""

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
    from diagnosis.dependency_model import (
        OPERATION_SCOPE_AMBIGUOUS,
        OPERATION_SCOPE_MISSING,
        OPERATION_SCOPE_UNIQUE,
        OperationScopeIdentity,
    )
    from diagnosis.parse_msprof_db import MsprofDbError, parse_inputs as parse_msprof_db_inputs
    from diagnosis.parse_plog import (
        parse_file as parse_plog_file,
        parse_graph_correlations_file,
    )
    from diagnosis.schema import GraphCorrelation, MERGED_FIELDS, ProfilerTask, SemanticRecord, write_csv
else:
    from .dependency_model import (
        OPERATION_SCOPE_AMBIGUOUS,
        OPERATION_SCOPE_MISSING,
        OPERATION_SCOPE_UNIQUE,
        OperationScopeIdentity,
    )
    from .parse_msprof_db import MsprofDbError, parse_inputs as parse_msprof_db_inputs
    from .parse_plog import parse_file as parse_plog_file, parse_graph_correlations_file
    from .schema import GraphCorrelation, MERGED_FIELDS, ProfilerTask, SemanticRecord, write_csv


TASK_KIND_KERNEL_TYPES = {
    "sdma": {"MEMCPY_ASYNC"},
    "rdma": {"RDMASEND"},
    # A3 HOST inline reduction (aclrtReduceAsync) is recorded as MEMCPY_ASYNC
    # in msprof TASK. Keep the DB kind intact; only relax this compatibility
    # check after the exact node/device/stream/task identity lookup.
    "reduce_inline": {"REDUCE_INLINE", "MEMCPY_ASYNC"},
    "reduce_tbe": {"REDUCE_TBE"},
    "notify_record": {"NOTIFY_RECORD"},
    "notify_wait": {"NOTIFY_WAIT"},
}

AICPU_TASK_KIND_KERNEL_TYPES = {
    "sdma": {"SDMA_SQE"},
    "rdma": {"WRITE_VALUE_SQE"},
    "reduce_inline": {"SDMA_SQE"},
    "notify_record": {"NOTIFY_RECORD_SQE", "WRITE_VALUE_SQE"},
    "notify_wait": {"NOTIFY_WAIT_SQE"},
}

FFTS_TASK_KIND_KERNEL_TYPES = {
    "sdma": {"SDMA"},
    "rdma": {"RDMASEND"},
    # FFts inline reduce contexts are materialized as SDMA executions in msprof.
    "reduce_inline": {"SDMA"},
    "reduce_tbe": {"REDUCE_TBE"},
    "notify_record": {"WRITE VALUE"},
    "notify_wait": {"NOTIFY WAIT"},
}

class PhaseConflictError(ValueError):
    """One physical execution was claimed by different semantic phases."""


def merge_records(
    semantics: Iterable[SemanticRecord],
    profilers: Iterable[ProfilerTask],
    correlations: Iterable[GraphCorrelation] = (),
) -> Tuple[List[Dict[str, object]], Counter]:
    semantic_list = list(semantics)
    profiler_list = list(profilers)
    correlation_list = list(correlations)
    stats = Counter()
    stats["semantic_total"] = len(semantic_list)
    stats["profiler_total"] = len(profiler_list)
    stats["ffts_semantic_total"] = sum(
        1 for record in semantic_list if record.ffts_ctx_id >= 0)
    stats["graph_correlation_total"] = len(correlation_list)
    operation_scopes, operation_scope_stats = build_operation_scope_assignments(
        profiler_list
    )
    stats.update(operation_scope_stats)

    semantic_counts = Counter(_semantic_dedupe_key(record) for record in semantic_list)
    profiler_execution_counts = Counter(record.execution_key for record in profiler_list)
    profiler_exact_by_key = defaultdict(list)
    profiler_composite_by_execution = defaultdict(list)
    for task in profiler_list:
        if task.subtask_id >= 0:
            profiler_composite_by_execution[
                task.merge_key + (task.subtask_id,)
            ].append(task)
        else:
            profiler_exact_by_key[task.merge_key].append(task)
    correlation_counts = Counter(correlation.merge_key for correlation in correlation_list)
    graph_correlations = {
        correlation.merge_key: correlation
        for correlation in correlation_list
        if correlation_counts[correlation.merge_key] == 1
    }
    stats["duplicate_graph_correlation_keys"] = sum(
        1 for count in correlation_counts.values() if count > 1)
    rows = []
    matched_profiler_keys = set()
    matched_semantics = {}

    for semantic in semantic_list:
        if semantic.device_id < 0:
            stats["semantic_missing_device_id"] += 1

        duplicate_semantic = semantic_counts[_semantic_dedupe_key(semantic)] > 1
        matches = []
        match_method = ""
        match_confidence = ""
        matched_correlation = None
        correlated = _ffts_ctx_match(
            profiler_composite_by_execution, graph_correlations, semantic)
        if correlated is not None:
            composite, matched_correlation = correlated
            if not _is_compatible_task_kind(semantic, composite, ffts=True):
                stats["ffts_ctx_kind_mismatches"] += 1
                duplicate_profiler = (
                    profiler_execution_counts[composite.execution_key] > 1)
                rows.append(_merged_row(
                    "correlation_kind_mismatch", semantic, composite,
                    duplicate_semantic, duplicate_profiler,
                    "ffts_parent_ctx", "invalid", matched_correlation,
                    _operation_scope_for(operation_scopes, composite)))
                continue
            matches = [composite]
            match_method = "ffts_parent_ctx"
            match_confidence = "exact"
            stats["ffts_parent_ctx_matches"] += 1
        else:
            exact_matches = _exact_matches(profiler_exact_by_key, semantic)
            if exact_matches:
                matches = exact_matches
                match_method = "task_id"
                match_confidence = "exact"
                stats["task_id_matches"] += 1
            elif semantic.ffts_ctx_id >= 0:
                stats["ffts_semantic_missing_correlation"] += 1

        matched_profiler = matches[0] if matches else None
        duplicate_profiler = (
            profiler_execution_counts[matched_profiler.execution_key] > 1
            if matched_profiler else False
        )
        if not matches:
            stats["unmatched_semantic"] += 1
            rows.append(_merged_row("unmatched_semantic", semantic, None, duplicate_semantic, False))
            continue
        previous_semantic = matched_semantics.get(
            matched_profiler.execution_key
        )
        if previous_semantic is not None:
            if _normalized_phase(previous_semantic.phase) != _normalized_phase(
                semantic.phase
            ):
                raise PhaseConflictError(_phase_conflict_message(
                    matched_profiler,
                    previous_semantic,
                    semantic,
                ))
            stats["ambiguous_semantic"] += 1
            rows.append(_merged_row(
                "ambiguous_semantic",
                semantic,
                matched_profiler,
                duplicate_semantic,
                True,
                match_method,
                match_confidence,
                matched_correlation,
                _operation_scope_for(
                    operation_scopes,
                    matched_profiler,
                ),
            ))
            continue
        matched_semantics[matched_profiler.execution_key] = semantic
        notify_mismatches = _notify_metadata_mismatches(
            semantic,
            matched_profiler,
        )
        if notify_mismatches:
            for mismatch in notify_mismatches:
                stats[mismatch] += 1
            stats["notify_metadata_mismatch"] += 1
            matched_profiler_keys.add(matched_profiler.execution_key)
            rows.append(_merged_row(
                "notify_metadata_mismatch",
                semantic,
                matched_profiler,
                duplicate_semantic,
                duplicate_profiler,
                match_method,
                "invalid",
                matched_correlation,
                _operation_scope_for(operation_scopes, matched_profiler),
            ))
            continue
        stats["matched"] += 1
        if match_confidence == "exact":
            stats["exact_matched"] += 1
        matched_profiler_keys.add(matched_profiler.execution_key)
        rows.append(_merged_row(
            "matched",
            semantic,
            matched_profiler,
            duplicate_semantic,
            duplicate_profiler,
            match_method,
            match_confidence,
            matched_correlation,
            _operation_scope_for(operation_scopes, matched_profiler),
        ))

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
            operation_scope=_operation_scope_for(operation_scopes, task),
        ))

    stats["duplicate_semantic_keys"] = sum(1 for count in semantic_counts.values() if count > 1)
    stats["duplicate_profiler_execution_keys"] = sum(
        1 for count in profiler_execution_counts.values() if count > 1)
    stats["invalid_matches"] = (
        stats.get("ffts_ctx_kind_mismatches", 0)
        + stats.get("notify_metadata_mismatch", 0)
    )
    stats["match_rate_percent"] = round(
        stats.get("matched", 0) * 100.0 / len(semantic_list), 2
    ) if semantic_list else 0
    stats["exact_match_rate_percent"] = round(
        stats.get("exact_matched", 0) * 100.0 / len(semantic_list), 2
    ) if semantic_list else 0
    return rows, stats


def build_operation_scope_assignments(
    profilers: Iterable[ProfilerTask],
) -> Tuple[Dict[tuple, Tuple[str, str]], Counter]:
    """Classify DB operation metadata without using local IDs as graph scope.

    ``opId`` only proves that one device-local DB reference maps one-to-one to
    ``(group_name, op_name)``.  The exported scope is derived only from those
    names, so different devices/nodes may use different local IDs safely within
    one profile run.
    """
    profiler_list = list(profilers)
    ref_to_scopes = defaultdict(set)
    scope_to_refs = defaultdict(set)
    task_candidates = []

    for task in profiler_list:
        op_name = str(task.op_name or "").strip()
        group_name = str(task.group_name or "").strip()
        scope = (
            OperationScopeIdentity(group_name, op_name)
            if op_name and group_name
            else None
        )
        task_candidates.append((task, scope))
        if scope is None or task.profiler_op_id < 0:
            continue
        local_ref = (task.node_id, task.device_id, task.profiler_op_id)
        local_scope = (task.node_id, task.device_id, group_name, op_name)
        ref_to_scopes[local_ref].add(scope)
        scope_to_refs[local_scope].add(task.profiler_op_id)

    candidates_by_execution = defaultdict(set)
    for task, scope in task_candidates:
        op_name = str(task.op_name or "").strip()
        group_name = str(task.group_name or "").strip()
        if not op_name and not group_name:
            candidate = ("", OPERATION_SCOPE_MISSING)
        elif scope is None or task.profiler_op_id < 0:
            candidate = ("", OPERATION_SCOPE_AMBIGUOUS)
        else:
            local_ref = (task.node_id, task.device_id, task.profiler_op_id)
            local_scope = (task.node_id, task.device_id, group_name, op_name)
            if (
                ref_to_scopes[local_ref] != {scope}
                or scope_to_refs[local_scope] != {task.profiler_op_id}
            ):
                candidate = ("", OPERATION_SCOPE_AMBIGUOUS)
            else:
                candidate = (scope.stable_id, OPERATION_SCOPE_UNIQUE)
        candidates_by_execution[task.execution_key].add(candidate)

    assignments = {}
    stats = Counter()
    unique_scopes = set()
    for task in profiler_list:
        candidates = candidates_by_execution[task.execution_key]
        if len(candidates) != 1:
            assignment = ("", OPERATION_SCOPE_AMBIGUOUS)
        else:
            assignment = next(iter(candidates))
        assignments[task.execution_key] = assignment
        stats["profiler_operation_scope_{}".format(assignment[1])] += 1
        if assignment[1] == OPERATION_SCOPE_UNIQUE:
            unique_scopes.add(assignment[0])
    stats["profiler_operation_scope_distinct"] = len(unique_scopes)
    return assignments, stats


def _operation_scope_for(
    assignments: Dict[tuple, Tuple[str, str]],
    profiler: ProfilerTask,
) -> Tuple[str, str]:
    return assignments.get(
        profiler.execution_key,
        ("", OPERATION_SCOPE_MISSING),
    )



def _is_compatible_task_kind(
    semantic: SemanticRecord,
    profiler: ProfilerTask,
    ffts: bool = False,
) -> bool:
    compatibility = FFTS_TASK_KIND_KERNEL_TYPES if ffts else TASK_KIND_KERNEL_TYPES
    if not ffts and semantic.source == "aicpu":
        compatibility = AICPU_TASK_KIND_KERNEL_TYPES
        expected_kind = "sdma" if semantic.task_kind == "reduce_inline" else semantic.task_kind
        if profiler.task_kind != expected_kind:
            return False
    expected = compatibility.get(str(semantic.task_kind or "").strip().lower())
    if not expected:
        return True
    return str(profiler.event_name or "").strip().upper() in expected


def _normalized_rank(value: int) -> int:
    return -1 if int(value) == 0xFFFFFFFF else int(value)


def _notify_metadata_mismatches(
    semantic: SemanticRecord,
    profiler: ProfilerTask,
) -> tuple[str, ...]:
    """Validate trace-side Notify identity against authoritative DB metadata."""
    semantic_kind = str(semantic.task_kind or "").strip().lower()
    profiler_kind = str(profiler.task_kind or "").strip().lower()
    if semantic_kind not in ("notify_record", "notify_wait"):
        return ()
    mismatches = []
    if profiler_kind not in ("notify_record", "notify_wait"):
        mismatches.append("notify_task_kind_mismatch")
    if profiler.profiler_notify_id < 0:
        mismatches.append("notify_db_metadata_missing")
    elif semantic.notify_id != profiler.profiler_notify_id:
        mismatches.append("notify_id_mismatch")
    if profiler.profiler_src_rank < 0:
        mismatches.append("notify_db_metadata_missing")
    elif _normalized_rank(semantic.user_rank) != profiler.profiler_src_rank:
        mismatches.append("notify_rank_mismatch")
    if (
        profiler.profiler_dst_rank >= 0
        and _normalized_rank(semantic.peer_rank) != profiler.profiler_dst_rank
    ):
        mismatches.append("notify_rank_mismatch")
    return tuple(dict.fromkeys(mismatches))


def _exact_matches(
    profiler_exact_by_key,
    semantic: SemanticRecord,
) -> List[ProfilerTask]:
    if semantic.ffts_ctx_id >= 0:
        return []
    tasks = _group_lookup(profiler_exact_by_key, semantic, semantic.task_id)
    return [task for task in tasks if _is_compatible_task_kind(semantic, task)]


def _normalized_phase(value: str) -> str:
    return str(value or "").strip()


def _phase_conflict_message(
    profiler: ProfilerTask,
    previous: SemanticRecord,
    current: SemanticRecord,
) -> str:
    identity = (
        "node_id={!r}, device_id={}, stream_id={}, task_id={}, "
        "subtask_id={}, connection_id={}"
    ).format(
        profiler.node_id,
        profiler.device_id,
        profiler.stream_id,
        profiler.task_id,
        profiler.subtask_id,
        profiler.connection_id,
    )
    return (
        "phase conflict for physical execution ({identity}): "
        "first phase={first_phase!r}, step={first_step}, event={first_event!r}; "
        "current phase={current_phase!r}, step={current_step}, "
        "event={current_event!r}"
    ).format(
        identity=identity,
        first_phase=_normalized_phase(previous.phase),
        first_step=previous.step,
        first_event=previous.event,
        current_phase=_normalized_phase(current.phase),
        current_step=current.step,
        current_event=current.event,
    )


def _group_lookup(groups, semantic: SemanticRecord, task_id: int) -> List[ProfilerTask]:
    key = (semantic.node_id, semantic.device_id, semantic.stream_id, task_id)
    tasks = groups.get(key, [])
    if tasks or semantic.node_id:
        return tasks
    candidates = [
        value for candidate_key, value in groups.items()
        if candidate_key[1:] == (semantic.device_id, semantic.stream_id, task_id)
    ]
    return candidates[0] if len(candidates) == 1 else []


def _graph_correlation_lookup(graph_correlations, semantic: SemanticRecord):
    key = (semantic.node_id, semantic.device_id, semantic.pid, semantic.graph_instance_id)
    correlation = graph_correlations.get(key)
    if correlation is not None or semantic.node_id:
        return correlation
    candidates = [
        value for candidate_key, value in graph_correlations.items()
        if candidate_key[1:] == (semantic.device_id, semantic.pid, semantic.graph_instance_id)
    ]
    return candidates[0] if len(candidates) == 1 else None


def _ffts_ctx_match(profiler_composite_by_execution, graph_correlations, semantic: SemanticRecord):
    if semantic.ffts_ctx_id < 0 or semantic.graph_instance_id < 0:
        return None
    correlation = _graph_correlation_lookup(graph_correlations, semantic)
    if correlation is None:
        return None
    key = (
        correlation.node_id or semantic.node_id,
        semantic.device_id,
        correlation.parent_stream_id,
        correlation.parent_task_id,
        semantic.ffts_ctx_id,
    )
    tasks = profiler_composite_by_execution.get(key, [])
    if not tasks and not key[0]:
        candidates = [
            value for candidate_key, value in profiler_composite_by_execution.items()
            if candidate_key[1:] == key[1:]
        ]
        tasks = candidates[0] if len(candidates) == 1 else []
    return (tasks[0], correlation) if len(tasks) == 1 else None


def to_float_for_sort(value: object) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0

def parse_msprof_inputs(
    msprof_db: str = "",
    msprof_db_dir: str = "",
    node_id: str = "",
) -> List[ProfilerTask]:
    return parse_msprof_db_inputs(msprof_db, msprof_db_dir, node_id)


def _semantic_log_paths(plog_dir: str):
    # CANN collects AI_CPU reports in device-<pid>_<timestamp>.log, while
    # Host reports retain the plog prefix. Preserve both original inputs.
    return sorted(path for path in Path(plog_dir).rglob("*.log")
                  if path.is_file() and path.name.startswith(("plog", "device-")))


def parse_plog_inputs(plog: str = "", plog_dir: str = "", node_id: str = "") -> List[SemanticRecord]:
    records: List[SemanticRecord] = []
    if plog:
        records.extend(parse_plog_file(plog))
    if plog_dir:
        for path in _semantic_log_paths(plog_dir):
            records.extend(parse_plog_file(str(path)))
    if node_id:
        records = [replace(record, node_id=node_id) if not record.node_id else record for record in records]
    return records


def parse_graph_correlation_inputs(
    plog: str = "",
    plog_dir: str = "",
    node_id: str = "",
) -> List[GraphCorrelation]:
    records: List[GraphCorrelation] = []
    if plog:
        records.extend(parse_graph_correlations_file(plog))
    if plog_dir:
        for path in _semantic_log_paths(plog_dir):
            records.extend(parse_graph_correlations_file(str(path)))
    if node_id:
        records = [
            replace(record, node_id=node_id) if not record.node_id else record
            for record in records
        ]
    return records



def _semantic_dedupe_key(record: SemanticRecord):
    if (
        record.ffts_ctx_id >= 0
        and record.graph_instance_id >= 0
        and record.device_id >= 0
    ):
        return (
            record.node_id,
            record.device_id,
            record.pid,
            "ffts_graph_context",
            record.graph_instance_id,
            record.ffts_ctx_id,
        )
    return record.merge_key

def _merged_row(status: str, semantic: SemanticRecord, profiler: ProfilerTask, duplicate_semantic: bool,
                duplicate_profiler: bool, match_method: str = "", match_confidence: str = "",
                graph_correlation: GraphCorrelation = None,
                operation_scope: Tuple[str, str] = ("", "")):
    row = semantic.to_row()
    if profiler and profiler.task_kind in ("notify_record", "notify_wait", "rdma"):
        # DB metadata also covers unannotated RDMA Notify sends. Keep one
        # canonical representation instead of duplicate notify/src/dst columns.
        row["task_kind"] = profiler.task_kind
        if profiler.profiler_notify_id >= 0:
            row["notify_id"] = profiler.profiler_notify_id
        if profiler.profiler_src_rank >= 0:
            row["user_rank"] = profiler.profiler_src_rank
        row["peer_rank"] = profiler.profiler_dst_rank
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
        "event_name": profiler.event_name if profiler else "",
        "subtask_id": profiler.subtask_id if profiler else "",
        "connection_id": profiler.connection_id if profiler else "",
        "model_id": profiler.model_id if profiler else "",
        "profiler_op_scope": operation_scope[0] if profiler else "",
        "profiler_op_scope_status": operation_scope[1] if profiler else "",
        "correlation_parent_stream_id": (
            graph_correlation.parent_stream_id if graph_correlation else ""),
        "correlation_parent_task_id": (
            graph_correlation.parent_task_id if graph_correlation else ""),
        "match_method": match_method,
        "match_confidence": match_confidence,
    })
    return row


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Merge HCCL semantic plog and fine-grained msprof DB executions."
    )
    parser.add_argument("--plog", default="")
    parser.add_argument("--plog-dir", default="", help="Directory containing Host plog*.log and AI_CPU device-*.log files.")
    profiler_source = parser.add_mutually_exclusive_group(required=True)
    profiler_source.add_argument(
        "--msprof-db", default="", help="One consolidated msprof_*.db file.")
    profiler_source.add_argument(
        "--msprof-db-dir",
        default="",
        help="Directory containing one or more PROF_*/msprof_*.db files.",
    )
    parser.add_argument("-o", "--output", required=True)
    parser.add_argument("--node-id", default="")
    parser.add_argument("--summary", default="")
    args = parser.parse_args()
    if not args.plog and not args.plog_dir:
        parser.error("one of --plog or --plog-dir is required")
    try:
        profilers = parse_msprof_inputs(
            args.msprof_db, args.msprof_db_dir, args.node_id)
    except MsprofDbError as error:
        parser.error(str(error))

    try:
        rows, stats = merge_records(
            parse_plog_inputs(args.plog, args.plog_dir, args.node_id),
            profilers,
            parse_graph_correlation_inputs(
                args.plog,
                args.plog_dir,
                args.node_id,
            ),
        )
    except PhaseConflictError as error:
        print("phase_conflict_error={}".format(error), file=sys.stderr)
        return 1
    write_csv(args.output, list(MERGED_FIELDS), rows)
    for key in sorted(stats):
        print("{}={}".format(key, stats[key]))
    if args.summary:
        with open(args.summary, "w", newline="", encoding="utf-8") as output:
            writer = csv.writer(output)
            writer.writerow(("metric", "value"))
            for key in sorted(stats):
                writer.writerow((key, stats[key]))
    return 1 if stats.get("duplicate_graph_correlation_keys", 0) else 0


if __name__ == "__main__":
    raise SystemExit(main())
