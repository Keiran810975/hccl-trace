#!/usr/bin/env python3
"""Parse fine-grained device execution events from an msprof Chrome-trace JSON."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections import defaultdict
from pathlib import Path
from typing import Dict, Iterable, Iterator, List, Optional

if __package__ in (None, ""):
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from diagnosis.schema import PROFILER_FIELDS, ProfilerTask, normalize_task_kind, parse_int, write_csv
else:
    from .schema import PROFILER_FIELDS, ProfilerTask, normalize_task_kind, parse_int, write_csv


UINT32_MAX = 0xFFFFFFFF
DEVICE_DIR_RE = re.compile(r"^device_(\d+)$")
TASK_KIND_BY_EVENT = {
    "SDMA": "sdma",
    "MEMCPY_ASYNC": "sdma",
    "RDMASEND": "rdma",
    "REDUCE_INLINE": "reduce_inline",
    "REDUCE_TBE": "reduce_tbe",
    "NOTIFY_RECORD": "notify_record",
    "WRITE_VALUE": "notify_record",
    "NOTIFY_WAIT": "notify_wait",
}


def infer_device_id(path: str) -> int:
    """Infer the card id from a PROF directory containing exactly one device_N."""
    current = Path(path).resolve().parent
    for parent in (current,) + tuple(current.parents):
        match = DEVICE_DIR_RE.match(parent.name)
        if match:
            return int(match.group(1))
        if parent.name.startswith("PROF_"):
            device_ids = []
            try:
                for child in parent.iterdir():
                    match = DEVICE_DIR_RE.match(child.name)
                    if match and child.is_dir():
                        device_ids.append(int(match.group(1)))
            except OSError:
                return -1
            return device_ids[0] if len(device_ids) == 1 else -1
    return -1


def _number(value: object, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _task_kind(event_name: str) -> str:
    normalized = str(event_name or "").strip().upper().replace("-", "_").replace(" ", "_")
    return TASK_KIND_BY_EVENT.get(normalized, normalize_task_kind(event_name))


def parse_events(
    events: Iterable[Dict[str, object]],
    device_id: int,
    default_node_id: str = "",
) -> Iterator[ProfilerTask]:
    """Yield device complete events; host APIs, flows, counters and metadata are skipped."""
    event_list = list(events)
    flow_ids = defaultdict(list)
    for event in event_list:
        if event.get("ph") == "f" and event.get("cat") == "HostToDevice":
            flow_ids[(parse_int(event.get("tid")), _number(event.get("ts")))].append(str(event.get("id", "")))

    for event in event_list:
        if event.get("ph") != "X":
            continue
        args = event.get("args")
        if not isinstance(args, dict):
            continue
        stream_value = args.get("Physic Stream Id")
        task_value = args.get("Task Id")
        if stream_value is None or task_value is None:
            continue
        event_name = str(event.get("name") or args.get("Task Type") or "").strip()
        start = _number(event.get("ts"))
        duration = max(0.0, _number(event.get("dur")))
        subtask_id = parse_int(args.get("Subtask Id"))
        if subtask_id == UINT32_MAX:
            subtask_id = -1
        stream_id = parse_int(stream_value)
        yield ProfilerTask(
            node_id=default_node_id,
            device_id=device_id,
            stream_id=stream_id,
            task_id=parse_int(task_value),
            task_kind=_task_kind(event_name),
            task_start=_format_number(start),
            task_stop=_format_number(start + duration),
            duration=_format_number(duration),
            event_name=event_name,
            subtask_id=subtask_id,
            connection_id=parse_int(args.get("connection_id")),
            model_id=parse_int(args.get("Model Id")),
            flow_id="|".join(flow_ids.get((stream_id, start), ())),
        )


def _format_number(value: float) -> str:
    return format(value, ".15g")


def parse_file(path: str, default_node_id: str = "", device_id: Optional[int] = None) -> List[ProfilerTask]:
    resolved_device_id = infer_device_id(path) if device_id is None else device_id
    if resolved_device_id < 0:
        raise ValueError(
            "cannot infer device_id for {!r}; pass --device-id or use one device_N directory per PROF directory".format(path)
        )
    with open(path, "r", encoding="utf-8-sig") as source:
        events = json.load(source)
    if not isinstance(events, list):
        raise ValueError("msprof JSON root must be an event array: {!r}".format(path))
    return list(parse_events(events, resolved_device_id, default_node_id))


def main() -> int:
    parser = argparse.ArgumentParser(description="Parse fine-grained device events from msprof JSON.")
    parser.add_argument("msprof_json")
    parser.add_argument("-o", "--output", required=True)
    parser.add_argument("--node-id", default="")
    parser.add_argument("--device-id", type=int)
    args = parser.parse_args()
    tasks = parse_file(args.msprof_json, args.node_id, args.device_id)
    write_csv(args.output, list(PROFILER_FIELDS), (task.to_row() for task in tasks))
    print("profiler_tasks={}".format(len(tasks)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
