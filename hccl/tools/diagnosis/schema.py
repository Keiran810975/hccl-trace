#!/usr/bin/env python3
"""Shared schema objects for HCCL step trace diagnosis tools."""

from __future__ import annotations

from dataclasses import dataclass, fields
from typing import Dict, Iterable, List, Optional


SCHEMA_VERSION = 4
SUPPORTED_SEMANTIC_SCHEMA_VERSIONS = frozenset((2, 3, 4))
TRACE_TAG = "[HcclTaskSemantic]"
GRAPH_CORRELATION_TAG = "[HcclTaskGraphCorrelation]"


SEMANTIC_FIELDS = (
    "schema_version",
    "algorithm",
    "phase",
    "step",
    "slice",
    "user_rank",
    "comm_rank",
    "rank_size",
    "peer_rank",
    "event",
    "semantic",
    "stream_id",
    "task_id",
    "task_kind",
    "ffts_ctx_id",
    "graph_instance_id",
    "source",
    "device_id",
    "submit_ts",
    "notify_id",
    "notify_stage",
    "node_id",
    "pid",
)


PROFILER_FIELDS = (
    "node_id",
    "device_id",
    "stream_id",
    "task_id",
    "task_kind",
    "task_start",
    "task_stop",
    "duration",
    "event_name",
    "subtask_id",
    "connection_id",
    "model_id",
)


MERGED_FIELDS = (
    "match_status",
    "duplicate_semantic",
    "duplicate_profiler",
) + SEMANTIC_FIELDS + (
    "profiler_task_kind",
    "profiler_stream_id",
    "profiler_task_id",
    "task_start",
    "task_stop",
    "duration",
    "event_name",
    "subtask_id",
    "connection_id",
    "model_id",
    "profiler_op_scope",
    "profiler_op_scope_status",
    "correlation_parent_stream_id",
    "correlation_parent_task_id",
    "match_method",
    "match_confidence",
    "profiler_size_bytes",
)


@dataclass(frozen=True)
class SemanticRecord:
    schema_version: int = SCHEMA_VERSION
    algorithm: str = ""
    phase: str = ""
    step: int = -1
    slice: int = -1
    user_rank: int = -1
    comm_rank: int = -1
    rank_size: int = -1
    peer_rank: int = -1
    event: str = ""
    semantic: str = ""
    stream_id: int = -1
    task_id: int = -1
    task_kind: str = ""
    ffts_ctx_id: int = -1
    graph_instance_id: int = -1
    source: str = ""
    device_id: int = -1
    submit_ts: int = 0
    notify_id: int = -1
    notify_stage: int = -1
    node_id: str = ""
    pid: int = -1

    @property
    def merge_key(self):
        return (self.node_id, self.device_id, self.stream_id, self.task_id)

    def to_row(self) -> Dict[str, object]:
        return _to_row(self, SEMANTIC_FIELDS)


@dataclass(frozen=True)
class GraphCorrelation:
    schema_version: int = 1
    graph_instance_id: int = -1
    device_id: int = -1
    anchor_task_id: int = -1
    parent_stream_id: int = -1
    parent_task_id: int = -1
    node_id: str = ""
    pid: int = -1

    @property
    def merge_key(self):
        return (self.node_id, self.device_id, self.pid, self.graph_instance_id)


@dataclass(frozen=True)
class ProfilerTask:
    node_id: str = ""
    device_id: int = -1
    stream_id: int = -1
    task_id: int = -1
    task_kind: str = ""
    task_start: str = ""
    task_stop: str = ""
    duration: str = ""
    event_name: str = ""
    subtask_id: int = -1
    connection_id: int = -1
    model_id: int = -1
    global_task_id: int = -1
    op_name: str = ""
    group_name: str = ""
    profiler_op_id: int = -1
    profiler_op_connection_id: int = -1
    profiler_notify_id: int = -1
    profiler_src_rank: int = -1
    profiler_dst_rank: int = -1
    profiler_size_bytes: int = -1

    @property
    def merge_key(self):
        return (self.node_id, self.device_id, self.stream_id, self.task_id)

    @property
    def execution_key(self):
        return self.merge_key + (self.subtask_id, self.connection_id)

    def to_row(self) -> Dict[str, object]:
        return _to_row(self, PROFILER_FIELDS)


def _to_row(record, ordered_fields: Iterable[str]) -> Dict[str, object]:
    values = {field.name: getattr(record, field.name) for field in fields(record)}
    return {name: values.get(name, "") for name in ordered_fields}


def parse_int(value: Optional[str], default: int = -1) -> int:
    if value is None:
        return default
    text = str(value).strip()
    if not text:
        return default
    try:
        return int(text, 0)
    except ValueError:
        return default


def normalize_task_kind(value: str) -> str:
    return str(value or "").strip().lower()


def write_csv(path: str, fieldnames: List[str], rows: Iterable[Dict[str, object]]) -> None:
    import csv

    with open(path, "w", newline="", encoding="utf-8") as output:
        writer = csv.DictWriter(output, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)
