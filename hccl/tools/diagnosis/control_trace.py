"""Exact local control metadata anchored to existing DB execution identities."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, replace
from pathlib import Path
import re

from .schema import ProfilerTask

TAG = "[HcclTaskControl]"
INVALID_U64 = (1 << 64) - 1
AUDIT_FIELDS = ["node_id", "device_id", "stream_id", "task_id", "task_kind",
                "anchor_stream_id", "anchor_task_id", "original_notify_id", "notify_id",
                "original_op_name", "op_name", "group_name", "evidence"]


@dataclass(frozen=True)
class ControlTask:
    node_id: str
    device_id: int
    stream_id: int
    task_id: int
    task_kind: str
    notify_id: int
    db_notify_id: int
    anchor_stream_id: int
    anchor_task_id: int
    evidence: str = ""

    @property
    def key(self):
        return self.node_id, self.device_id, self.stream_id, self.task_id

    @property
    def anchor(self):
        return self.node_id, self.device_id, self.anchor_stream_id, self.anchor_task_id


def parse_control_inputs(paths, node_id: str):
    records = []
    required = {"schema_version", "device_id", "stream_id", "task_id", "task_kind",
                "notify_id", "db_notify_id", "anchor_stream_id", "anchor_task_id"}
    for path in paths:
        with Path(path).open(encoding="utf-8-sig", errors="replace") as source:
            for line_number, line in enumerate(source, 1):
                if TAG not in line:
                    continue
                pairs = re.findall(r"(\w+)\[([^\]]*)\]", line.split(TAG, 1)[1])
                fields = dict(pairs)
                if set(fields) != required or len(pairs) != len(required):
                    raise ValueError("incomplete/duplicate control fields: {}:{}".format(path, line_number))
                if fields.pop("schema_version") != "1":
                    raise ValueError("unsupported control schema")
                kind = fields.pop("task_kind")
                if kind not in ("notify_record", "notify_wait", "kernel_aicpu"):
                    raise ValueError("unsupported control task kind: " + kind)
                values = {key: int(value) for key, value in fields.items()}
                if any(value < 0 for value in values.values()):
                    raise ValueError("negative control identity")
                if any(values[key] >= (1 << 32) - 1 for key in
                       ("device_id", "stream_id", "task_id", "anchor_stream_id", "anchor_task_id")):
                    raise ValueError("invalid control execution identity")
                if kind.startswith("notify") and values["notify_id"] == INVALID_U64:
                    raise ValueError("missing control Notify resource")
                records.append(ControlTask(node_id=node_id, task_kind=kind,
                    evidence="{}:{}".format(path, line_number), **values))
    return records


def enrich_control_tasks(profilers, records):
    """Require unique task keys, compatible kind, exact alias and anchored DB scope.

    Anchors may form a short chain (Device order -> Host kernel -> Host Post).
    An anchor is operation ownership evidence, never a synchronization edge.
    No timestamps, ordinals, offsets or rank-derived device IDs are used here.
    """
    tasks = list(profilers)
    by_key = defaultdict(list)
    for task in tasks:
        by_key[task.merge_key].append(task)
    controls = {}
    for record in records:
        if record.key in controls:
            raise ValueError("duplicate control execution: {!r}".format(record.key))
        controls[record.key] = record
    resolved = {}
    visiting = set()

    def unique(key):
        candidates = by_key.get(key, [])
        if len(candidates) != 1 or candidates[0].subtask_id >= 0:
            raise ValueError("missing/ambiguous direct control execution: {!r}".format(key))
        return candidates[0]

    def resolve(key):
        if key in resolved:
            return resolved[key]
        task = unique(key)
        if key not in controls:
            if not task.op_name or not task.group_name:
                raise ValueError("control anchor has no DB operation: {!r}".format(key))
            return task
        if key in visiting:
            raise ValueError("cyclic control anchors: {!r}".format(key))
        visiting.add(key)
        record = controls[key]
        if record.task_kind != task.task_kind:
            raise ValueError("control kind conflicts with DB execution: {!r}".format(key))
        if record.anchor == key:
            if not task.op_name or not task.group_name:
                raise ValueError("self control anchor needs DB operation")
            owner = task
        else:
            owner = resolve(record.anchor)
        if (task.op_name or task.group_name) and (task.op_name, task.group_name) != (owner.op_name, owner.group_name):
            raise ValueError("control anchor conflicts with DB operation")
        canonical = task.profiler_notify_id
        if record.task_kind.startswith("notify"):
            observed = record.db_notify_id
            if observed != INVALID_U64 and task.profiler_notify_id != observed:
                raise ValueError("control Notify alias conflicts with DB metadata")
            if observed == INVALID_U64 and task.profiler_notify_id not in (-1, record.notify_id):
                raise ValueError("control Notify resource conflicts with DB metadata")
            if task.profiler_dst_rank >= 0:
                raise ValueError("local control record cannot replace a peer channel")
            canonical = record.notify_id
        result = replace(task, op_name=owner.op_name, group_name=owner.group_name,
                         profiler_op_id=owner.profiler_op_id,
                         profiler_op_connection_id=owner.profiler_op_connection_id,
                         profiler_notify_id=canonical)
        resolved[key] = result
        visiting.remove(key)
        return result

    audit = []
    for key, record in controls.items():
        result = resolve(key)
        original = unique(key)
        audit.append(dict(node_id=record.node_id, device_id=record.device_id,
            stream_id=record.stream_id, task_id=record.task_id, task_kind=record.task_kind,
            anchor_stream_id=record.anchor_stream_id, anchor_task_id=record.anchor_task_id,
            original_notify_id=original.profiler_notify_id, notify_id=result.profiler_notify_id,
            original_op_name=original.op_name, op_name=result.op_name,
            group_name=result.group_name, evidence=record.evidence))
    return [resolved.get(task.merge_key, task) for task in tasks], audit


BUILD_FIELDS = ["node_id", "device_id", "kernel_stream_id", "kernel_task_id", "user_rank",
                "algorithm", "phase", "step", "slice", "duration_ns", "threshold_ns",
                "timing_domain", "op_name", "group_name", "evidence"]


def parse_build_spans(paths, node_id, profilers):
    """Sparse CPU construction spans; their durations can overlap and are not summed."""
    by_key = defaultdict(list)
    for task in profilers:
        by_key[task.merge_key].append(task)
    spans = []
    tag = "[HcclTaskBuildSpan]"
    expected = set(BUILD_FIELDS) - {"node_id", "op_name", "group_name", "evidence"} | {"schema_version"}
    for path in paths:
        with Path(path).open(encoding="utf-8-sig", errors="replace") as source:
            for number, line in enumerate(source, 1):
                if tag not in line:
                    continue
                pairs = re.findall(r"(\w+)\[([^\]]*)\]", line.split(tag, 1)[1])
                row = dict(pairs)
                if set(row) != expected or len(pairs) != len(expected) or row.pop("schema_version") != "1":
                    raise ValueError("invalid build span schema")
                for key in ("device_id", "kernel_stream_id", "kernel_task_id", "user_rank",
                            "step", "slice", "duration_ns", "threshold_ns"):
                    row[key] = int(row[key])
                    if row[key] < 0:
                        raise ValueError("negative build span value")
                if row["timing_domain"] != "aicpu_build_cpu" or row["duration_ns"] < row["threshold_ns"]:
                    raise ValueError("invalid build span clock/duration")
                key = node_id, row["device_id"], row["kernel_stream_id"], row["kernel_task_id"]
                candidates = by_key.get(key, [])
                if len(candidates) != 1 or candidates[0].task_kind != "kernel_aicpu":
                    raise ValueError("build span has missing/ambiguous kernel execution")
                task = candidates[0]
                if not task.op_name or not task.group_name:
                    raise ValueError("build span kernel lacks anchored DB operation")
                row.update(node_id=node_id, op_name=task.op_name, group_name=task.group_name,
                           evidence="{}:{}".format(path, number))
                spans.append(row)
    return spans
