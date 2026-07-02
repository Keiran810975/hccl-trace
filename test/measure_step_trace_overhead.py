#!/usr/bin/env python3
"""Measure HCCL step trace wall-time overhead for a single-node workload."""

from __future__ import annotations

import argparse
import csv
import os
import statistics
import subprocess
import sys
import time
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run one workload with HCCL_STEP_TRACE disabled/enabled and report wall-time overhead."
    )
    parser.add_argument("--repeat", type=int, default=10, help="Measured runs per mode. Default: 10")
    parser.add_argument("--warmup", type=int, default=2, help="Warmup runs per mode. Default: 2")
    parser.add_argument("--output", default="test/out/overhead/overhead.csv", help="CSV output path")
    parser.add_argument("--summary", default="test/out/overhead/summary.txt", help="Text summary path")
    parser.add_argument("--timeout", type=float, default=None, help="Per-run timeout in seconds")
    parser.add_argument(
        "--trace-env",
        action="append",
        default=[],
        metavar="KEY=VALUE",
        help="Extra environment variable for trace mode; may be repeated.",
    )
    parser.add_argument(
        "--baseline-env",
        action="append",
        default=[],
        metavar="KEY=VALUE",
        help="Extra environment variable for baseline mode; may be repeated.",
    )
    parser.add_argument("command", nargs=argparse.REMAINDER, help="Command after --")
    args = parser.parse_args()
    if args.command and args.command[0] == "--":
        args.command = args.command[1:]
    if not args.command:
        parser.error("a workload command is required after --")
    if args.repeat <= 0:
        parser.error("--repeat must be positive")
    if args.warmup < 0:
        parser.error("--warmup must be non-negative")
    return args


def env_pairs(values: list[str]) -> dict[str, str]:
    result = {}
    for item in values:
        if "=" not in item:
            raise ValueError("environment override must be KEY=VALUE: {}".format(item))
        key, value = item.split("=", 1)
        if not key:
            raise ValueError("environment override has empty key: {}".format(item))
        result[key] = value
    return result


def run_once(command: list[str], env: dict[str, str], timeout: float | None) -> tuple[int, float]:
    start = time.perf_counter()
    completed = subprocess.run(command, env=env, timeout=timeout)
    elapsed = time.perf_counter() - start
    return completed.returncode, elapsed


def run_mode(
    mode: str,
    command: list[str],
    base_env: dict[str, str],
    overrides: dict[str, str],
    warmup: int,
    repeat: int,
    timeout: float | None,
) -> list[dict[str, object]]:
    env = dict(base_env)
    env.update(overrides)
    rows = []
    for index in range(warmup + repeat):
        phase = "warmup" if index < warmup else "measure"
        measure_index = index - warmup if phase == "measure" else index
        return_code, elapsed = run_once(command, env, timeout)
        row = {
            "mode": mode,
            "phase": phase,
            "index": measure_index,
            "elapsed_s": "{:.9f}".format(elapsed),
            "return_code": return_code,
        }
        rows.append(row)
        print(
            "[{}] {} #{} elapsed_s={:.6f} return_code={}".format(
                mode, phase, measure_index, elapsed, return_code
            ),
            flush=True,
        )
        if return_code != 0:
            raise RuntimeError("{} {} run #{} failed with return code {}".format(mode, phase, measure_index, return_code))
    return rows


def summarize(rows: list[dict[str, object]]) -> dict[str, float]:
    values = {}
    for mode in ("baseline", "trace"):
        elapsed = [
            float(row["elapsed_s"])
            for row in rows
            if row["mode"] == mode and row["phase"] == "measure"
        ]
        values[mode + "_mean_s"] = statistics.mean(elapsed)
        values[mode + "_median_s"] = statistics.median(elapsed)
        values[mode + "_min_s"] = min(elapsed)
        values[mode + "_max_s"] = max(elapsed)
    baseline = values["baseline_mean_s"]
    trace = values["trace_mean_s"]
    values["overhead_percent"] = ((trace / baseline) - 1.0) * 100.0 if baseline > 0 else float("nan")
    values["median_overhead_percent"] = (
        ((values["trace_median_s"] / values["baseline_median_s"]) - 1.0) * 100.0
        if values["baseline_median_s"] > 0
        else float("nan")
    )
    return values


def main() -> int:
    args = parse_args()
    baseline_extra = env_pairs(args.baseline_env)
    trace_extra = env_pairs(args.trace_env)

    base_env = os.environ.copy()
    baseline_env = {
        "HCCL_STEP_TRACE": "0",
        "HCCL_TASK_SEMANTIC_TRACE": "0",
    }
    baseline_env.update(baseline_extra)
    trace_env = {
        "HCCL_STEP_TRACE": "1",
        "HCCL_TASK_SEMANTIC_TRACE": "1",
    }
    trace_env.update(trace_extra)

    output = Path(args.output)
    summary_path = Path(args.summary)
    output.parent.mkdir(parents=True, exist_ok=True)
    summary_path.parent.mkdir(parents=True, exist_ok=True)

    rows = []
    rows.extend(run_mode("baseline", args.command, base_env, baseline_env, args.warmup, args.repeat, args.timeout))
    rows.extend(run_mode("trace", args.command, base_env, trace_env, args.warmup, args.repeat, args.timeout))

    with output.open("w", newline="", encoding="utf-8") as target:
        writer = csv.DictWriter(target, fieldnames=("mode", "phase", "index", "elapsed_s", "return_code"))
        writer.writeheader()
        writer.writerows(rows)

    values = summarize(rows)
    lines = [
        "command={}".format(" ".join(args.command)),
        "repeat={}".format(args.repeat),
        "warmup={}".format(args.warmup),
    ]
    for key in sorted(values):
        lines.append("{}={:.6f}".format(key, values[key]))
    summary_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    print("csv={}".format(output))
    print("summary={}".format(summary_path))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        raise SystemExit(130)
    except Exception as exc:
        print("error: {}".format(exc), file=sys.stderr)
        raise SystemExit(1)

