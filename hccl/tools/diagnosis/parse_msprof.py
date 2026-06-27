#!/usr/bin/env python3
"""Parse msprof task_time.csv rows used by step trace merging."""

from __future__ import annotations

import argparse
import csv
import os
import sys
from typing import Dict, Iterable, Iterator, List

if __package__ in (None, ""):
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from diagnosis.schema import PROFILER_FIELDS, PROFILER_TRACE_EX, ProfilerTask, first_present, normalize_task_kind, parse_int, write_csv
else:
    from .schema import PROFILER_FIELDS, PROFILER_TRACE_EX, ProfilerTask, first_present, normalize_task_kind, parse_int, write_csv


def parse_task_time_rows(rows: Iterable[Dict[str, str]], default_node_id: str = "") -> Iterator[ProfilerTask]:
    for row in rows:
        kernel_type = first_present(row, ("kernel_type", "Kernel Type", "Task Type", "task_type"))
        if kernel_type == PROFILER_TRACE_EX:
            continue
        task_kind = first_present(row, ("task_kind", "Task Type", "task_type", "kernel_type", "Kernel Type"))
        yield ProfilerTask(
            node_id=first_present(row, ("node_id", "Node_id", "node"), default_node_id),
            device_id=parse_int(first_present(row, ("device_id", "Device_id", "Device ID", "device"))),
            stream_id=parse_int(first_present(row, ("stream_id", "Stream_id", "Stream ID", "stream"))),
            task_id=parse_int(first_present(row, ("task_id", "Task_id", "Task ID", "task"))),
            task_kind=normalize_task_kind(task_kind),
            task_start=first_present(row, ("task_start", "task_start(us)", "Task Start Time(us)", "Start Time(us)", "start_time")),
            task_stop=first_present(row, ("task_stop", "task_stop(us)", "Task Stop Time(us)", "End Time(us)", "stop_time")),
            duration=first_present(row, ("duration", "task_time(us)", "Task Duration(us)", "Duration(us)")),
            kernel_type=kernel_type,
        )


def parse_file(path: str, default_node_id: str = "") -> List[ProfilerTask]:
    with open(path, "r", encoding="utf-8-sig", newline="") as source:
        return list(parse_task_time_rows(csv.DictReader(source), default_node_id=default_node_id))


def main() -> int:
    parser = argparse.ArgumentParser(description="Parse msprof task_time.csv into normalized CSV.")
    parser.add_argument("task_time_csv")
    parser.add_argument("-o", "--output", required=True)
    parser.add_argument("--node-id", default="")
    args = parser.parse_args()
    tasks = parse_file(args.task_time_csv, default_node_id=args.node_id)
    write_csv(args.output, list(PROFILER_FIELDS), (task.to_row() for task in tasks))
    print("profiler_tasks={}".format(len(tasks)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
