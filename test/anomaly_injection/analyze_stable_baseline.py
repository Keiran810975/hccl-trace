#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

import argparse
import csv
import json
import math
import statistics
from collections import defaultdict
from pathlib import Path


SIGNATURE_FIELDS = (
    "node_id",
    "device_id",
    "user_rank",
    "phase",
    "step",
    "slice",
    "event",
    "stream_id",
    "task_kind",
    "ffts_ctx_id",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Summarize repeated HCCL baseline waits and export one stable iteration."
    )
    parser.add_argument("--diagnosis-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--warmup", type=int, default=5)
    parser.add_argument("--rank", type=int, default=2)
    parser.add_argument("--phase", default="allgather_direct")
    parser.add_argument("--event", default="rx_ack_start")
    parser.add_argument(
        "--representative-tail",
        type=int,
        default=5,
        help="Choose the median-like representative from this many final iterations.",
    )
    parser.add_argument(
        "--iteration",
        type=int,
        help="Export this zero-based overall iteration instead of choosing one automatically.",
    )
    return parser.parse_args()


def read_csv(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        return list(reader.fieldnames or []), list(reader)


def write_csv(path: Path, fields: list[str], rows: list[dict[str, object]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def percentile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    return ordered[max(0, math.ceil(fraction * len(ordered)) - 1)]


def stats(values: list[float]) -> dict[str, float]:
    mean = statistics.mean(values)
    deviation = statistics.stdev(values) if len(values) > 1 else 0.0
    return {
        "min_us": round(min(values), 3),
        "median_us": round(statistics.median(values), 3),
        "mean_us": round(mean, 3),
        "p95_us": round(percentile(values, 0.95), 3),
        "max_us": round(max(values), 3),
        "stdev_us": round(deviation, 3),
        "cv_percent": round(100.0 * deviation / mean, 2) if mean else 0.0,
    }


def assign_iteration(rows: list[dict[str, str]]) -> int:
    grouped: dict[tuple[str, ...], list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        if row.get("match_status") != "matched":
            continue
        grouped[tuple(row.get(field, "") for field in SIGNATURE_FIELDS)].append(row)

    counts = {len(group) for group in grouped.values()}
    if len(counts) != 1:
        raise ValueError(f"semantic signatures have inconsistent occurrence counts: {counts}")
    iteration_count = counts.pop()
    for group in grouped.values():
        group.sort(key=lambda row: float(row["task_start"]))
        for iteration, row in enumerate(group):
            row["iteration"] = str(iteration)
    return iteration_count


def main() -> int:
    args = parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)

    node_fields, nodes = read_csv(args.diagnosis_dir / "dep_graph_nodes.csv")
    edge_fields, edges = read_csv(args.diagnosis_dir / "dep_graph_edges.csv")
    iteration_count = assign_iteration(nodes)
    if not 0 <= args.warmup < iteration_count:
        raise ValueError("warmup must leave at least one measured iteration")

    targets = [
        row
        for row in nodes
        if row.get("match_status") == "matched"
        and row.get("user_rank") == str(args.rank)
        and row.get("phase") == args.phase
        and row.get("event") == args.event
    ]
    steps = sorted({int(row["step"]) for row in targets})
    by_iteration = {
        iteration: {"iteration": iteration, "measured_index": iteration - args.warmup}
        for iteration in range(iteration_count)
    }
    for row in targets:
        by_iteration[int(row["iteration"])][f"step_{row['step']}_wait_us"] = round(
            float(row["duration"]), 3
        )

    measured = [by_iteration[index] for index in range(args.warmup, iteration_count)]
    medians = {
        step: statistics.median(
            float(row[f"step_{step}_wait_us"]) for row in measured
        )
        for step in steps
    }
    tail = measured[-max(1, min(args.representative_tail, len(measured))) :]
    if args.iteration is not None:
        if not 0 <= args.iteration < iteration_count:
            raise ValueError(f"iteration must be in 0..{iteration_count - 1}")
        representative = by_iteration[args.iteration]
    else:
        representative = min(
            tail,
            key=lambda row: sum(
                abs(float(row[f"step_{step}_wait_us"]) - medians[step]) for step in steps
            ),
        )
    representative_iteration = int(representative["iteration"])

    summary = {
        "iteration_count": iteration_count,
        "warmup_iterations": args.warmup,
        "measured_iterations": iteration_count - args.warmup,
        "target": {
            "rank": args.rank,
            "phase": args.phase,
            "event": args.event,
        },
        "steps": {
            str(step): stats(
                [float(row[f"step_{step}_wait_us"]) for row in measured]
            )
            for step in steps
        },
        "representative_iteration": representative_iteration,
        "representative_measured_index": int(representative["measured_index"]),
        "representative_waits_us": {
            str(step): float(representative[f"step_{step}_wait_us"]) for step in steps
        },
    }

    wait_fields = ["iteration", "measured_index"] + [
        f"step_{step}_wait_us" for step in steps
    ]
    write_csv(args.output_dir / "rx_ack_waits_by_iteration.csv", wait_fields, list(by_iteration.values()))
    (args.output_dir / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    selected_nodes = [
        row
        for row in nodes
        if row.get("match_status") == "matched"
        and row.get("iteration") == str(representative_iteration)
    ]
    selected_ids = {row["graph_id"] for row in selected_nodes}
    selected_edges = [
        row for row in edges if row.get("src") in selected_ids and row.get("dst") in selected_ids
    ]
    write_csv(
        args.output_dir / "representative_nodes.csv",
        node_fields,
        selected_nodes,
    )
    write_csv(
        args.output_dir / "representative_edges.csv",
        edge_fields,
        selected_edges,
    )
    print(json.dumps(summary, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
