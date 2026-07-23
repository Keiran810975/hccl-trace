#!/usr/bin/env python3
"""Measure offline parsing cost for consolidated msprof SQLite databases."""

from __future__ import annotations

import argparse
import csv
import statistics
import sys
import time
import tracemalloc
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT_DIR / "hccl"))

from tools.diagnosis.parse_msprof_db import discover_db_files, parse_inputs  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--msprof-db-dir", required=True)
    parser.add_argument("--repeat", type=int, default=5)
    parser.add_argument("--warmup", type=int, default=1)
    parser.add_argument("--node-id", default="node0")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    if args.repeat <= 0 or args.warmup < 0:
        parser.error("--repeat must be positive and --warmup must be non-negative")

    db_files = discover_db_files(args.msprof_db_dir)
    input_bytes = sum(path.stat().st_size for path in db_files)
    for _ in range(args.warmup):
        parse_inputs(msprof_db_dir=args.msprof_db_dir, default_node_id=args.node_id)

    elapsed_values = []
    peak_values = []
    task_count = 0
    for _ in range(args.repeat):
        tracemalloc.start()
        started = time.perf_counter()
        tasks = parse_inputs(
            msprof_db_dir=args.msprof_db_dir,
            default_node_id=args.node_id,
        )
        elapsed_values.append(time.perf_counter() - started)
        _, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        peak_values.append(peak)
        task_count = len(tasks)

    median_seconds = statistics.median(elapsed_values)
    result = {
        "db_files": len(db_files),
        "input_bytes": input_bytes,
        "profiler_tasks": task_count,
        "repeat": args.repeat,
        "median_seconds": "{:.9f}".format(median_seconds),
        "min_seconds": "{:.9f}".format(min(elapsed_values)),
        "max_seconds": "{:.9f}".format(max(elapsed_values)),
        "peak_bytes_median": int(statistics.median(peak_values)),
        "tasks_per_second": "{:.3f}".format(
            task_count / median_seconds if median_seconds else 0.0
        ),
    }
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", newline="", encoding="utf-8") as output:
        writer = csv.DictWriter(output, fieldnames=list(result))
        writer.writeheader()
        writer.writerow(result)
    for key, value in result.items():
        print("{}={}".format(key, value))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
