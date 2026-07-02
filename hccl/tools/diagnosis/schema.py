#!/usr/bin/env python3
"""Shared schema objects for HCCL step trace diagnosis tools."""

from __future__ import annotations

from dataclasses import dataclass, fields
from typing import Dict, Iterable, List, Optional


SCHEMA_VERSION = 1
TRACE_TAG = "[HcclTaskSemantic]"
PROFILER_TRACE_EX = "PROFILER_TRACE_EX"


SEMANTIC_FIELDS = (
    "schema_version",
    "op_id",
    "op_type",
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
    "semantic_seq",
    "task_kind",
    "source",
    "device_id",
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
    "kernel_type",
)


MERGED_FIELDS = (
    "match_status",
    "duplicate_semantic",
    "duplicate_profiler",
) + SEMANTIC_FIELDS + (
    "profiler_task_kind",
    "task_start",
    "task_stop",
    "duration",
    "kernel_type",
)


@dataclass(frozen=True)
class SemanticRecord:
    schema_version: int = SCHEMA_VERSION
    op_id: str = ""
    op_type: str = ""
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
    semantic_seq: int = -1
    task_kind: str = ""
    source: str = ""
    device_id: int = -1
    node_id: str = ""
    pid: int = -1

    @property
    def merge_key(self):
        return (self.node_id, self.device_id, self.stream_id, self.task_id)

    def to_row(self) -> Dict[str, object]:
        return _to_row(self, SEMANTIC_FIELDS)


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
    kernel_type: str = ""

    @property
    def merge_key(self):
        return (self.node_id, self.device_id, self.stream_id, self.task_id)

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


def first_present(row: Dict[str, str], names: Iterable[str], default: str = "") -> str:
    lowered = {key.strip().lower(): value for key, value in row.items()}
    for name in names:
        if name.lower() in lowered and str(lowered[name.lower()]).strip() != "":
            return str(lowered[name.lower()]).strip()
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
