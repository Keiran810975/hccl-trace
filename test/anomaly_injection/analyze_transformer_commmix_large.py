#!/usr/bin/env python3
"""Compare one node of the large Transformer-CommMix baseline and delay capture."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any


WAIT_KINDS = frozenset(("notify_wait", "event_wait", "notify_wait_sqe"))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--baseline-dir", type=Path, required=True)
    parser.add_argument("--injected-dir", type=Path, required=True)
    parser.add_argument("--baseline-log", type=Path, required=True)
    parser.add_argument("--injected-log", type=Path, required=True)
    parser.add_argument("--devices", required=True)
    parser.add_argument("--node-rank", type=int, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    return parser.parse_args()


def load_workload(path: Path) -> list[dict[str, Any]]:
    results: dict[int, dict[str, Any]] = {}
    text = path.read_text(encoding="utf-8", errors="replace")
    decoder = json.JSONDecoder()
    offset = 0
    while offset < len(text):
        object_start = text.find("{", offset)
        if object_start < 0:
            break
        try:
            item, object_end = decoder.raw_decode(text, object_start)
        except json.JSONDecodeError:
            offset = object_start + 1
            continue
        offset = object_end
        if isinstance(item, dict) and item.get("status") == "passed":
            results[int(item["rank"])] = item
    return [results[rank] for rank in sorted(results)]


def load_operations(path: Path) -> list[tuple[str, dict[str, list[dict[str, str]]]]]:
    scopes: dict[str, dict[str, Any]] = {}
    with path.open(encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            scope = row.get("profiler_op_scope", "")
            if not scope:
                continue
            item = scopes.setdefault(scope, {"start": None, "waits": {}})
            start = float(row["task_start"])
            if item["start"] is None or start < item["start"]:
                item["start"] = start
            kind = row.get("profiler_task_kind", "")
            if kind in WAIT_KINDS:
                device = row.get("device_id", "")
                item["waits"].setdefault(device, []).append(row)
    ordered = sorted(scopes.items(), key=lambda pair: pair[1]["start"])
    return [(scope, item["waits"]) for scope, item in ordered]


def max_kind(rows: list[dict[str, str]], kind: str) -> dict[str, str] | None:
    candidates = [row for row in rows if row.get("profiler_task_kind") == kind]
    return max(candidates, key=lambda row: float(row.get("duration") or 0), default=None)


def max_wait(by_device: dict[str, list[dict[str, str]]]) -> float:
    return max(
        (
            float(row.get("duration") or 0)
            for rows in by_device.values()
            for row in rows
        ),
        default=0.0,
    )


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    args = parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    baseline_workload = load_workload(args.baseline_log)
    injected_workload = load_workload(args.injected_log)
    if len(baseline_workload) != 4 or len(injected_workload) != 4:
        raise ValueError("each node must contain four successful workload results")

    devices = [item.strip() for item in args.devices.split(",") if item.strip()]
    if len(devices) != 4:
        raise ValueError("expected four device ids")
    rank_by_device = {
        device: args.node_rank * len(devices) + local_rank
        for local_rank, device in enumerate(devices)
    }

    baseline_ops = load_operations(args.baseline_dir / "merged.csv")
    injected_ops = load_operations(args.injected_dir / "merged.csv")
    expected_operations = int(injected_workload[0]["warmup"] + injected_workload[0]["iters"]) * int(
        injected_workload[0]["collectives_per_step"]
    )
    if len(baseline_ops) != expected_operations or len(injected_ops) != expected_operations:
        raise ValueError(
            f"expected {expected_operations} operation scopes, got "
            f"{len(baseline_ops)} and {len(injected_ops)}"
        )

    warmup = int(injected_workload[0]["warmup"])
    iteration = int(injected_workload[0]["delay_iteration"])
    block = int(injected_workload[0]["delay_block"])
    bucket = int(injected_workload[0]["delay_bucket"])
    bucket_count = len(injected_workload[0]["bucket_mib"])
    collectives_per_step = int(injected_workload[0]["collectives_per_step"])
    target_index = (warmup + iteration) * collectives_per_step + block * bucket_count + bucket

    operation_comparison = []
    for index, ((base_scope, base_devices), (injected_scope, injected_devices)) in enumerate(
        zip(baseline_ops, injected_ops)
    ):
        if base_scope != injected_scope:
            raise ValueError(f"operation scope mismatch at index {index}")
        baseline_us = max_wait(base_devices)
        injected_us = max_wait(injected_devices)
        within_step = index % collectives_per_step
        operation_comparison.append(
            {
                "operation_index": index,
                "iteration_group": index // collectives_per_step,
                "block": within_step // bucket_count,
                "bucket_index": within_step % bucket_count,
                "bucket_mib": injected_workload[0]["bucket_mib"][within_step % bucket_count],
                "operation_scope": injected_scope,
                "is_injected_target": int(index == target_index),
                "baseline_max_wait_us": round(baseline_us, 3),
                "injected_max_wait_us": round(injected_us, 3),
                "delta_us": round(injected_us - baseline_us, 3),
            }
        )

    baseline_scope, baseline_target = baseline_ops[target_index]
    injected_scope, injected_target = injected_ops[target_index]
    if baseline_scope != injected_scope:
        raise ValueError("target operation scope changed")

    target_rows = []
    propagated_ranks: set[int] = set()
    threshold_us = float(injected_workload[0]["delay_ms"]) * 1000 * 0.5
    for device in devices:
        for kind in sorted(WAIT_KINDS):
            baseline_row = max_kind(baseline_target.get(device, []), kind)
            injected_row = max_kind(injected_target.get(device, []), kind)
            if baseline_row is None or injected_row is None:
                continue
            baseline_us = float(baseline_row["duration"])
            injected_us = float(injected_row["duration"])
            delta_us = injected_us - baseline_us
            rank = rank_by_device[device]
            if delta_us >= threshold_us:
                propagated_ranks.add(rank)
            target_rows.append(
                {
                    "node_rank": args.node_rank,
                    "device_id": device,
                    "global_rank": rank,
                    "signal": kind,
                    "baseline_us": round(baseline_us, 3),
                    "injected_us": round(injected_us, 3),
                    "delta_us": round(delta_us, 3),
                    "multiplier": round(injected_us / max(baseline_us, 0.001), 2),
                    "baseline_stream": baseline_row["profiler_stream_id"],
                    "baseline_task": baseline_row["profiler_task_id"],
                    "injected_stream": injected_row["profiler_stream_id"],
                    "injected_task": injected_row["profiler_task_id"],
                    "operation_scope": injected_scope,
                }
            )

    summary = {
        "node_rank": args.node_rank,
        "devices": devices,
        "ranks": sorted(rank_by_device.values()),
        "operation_count": expected_operations,
        "target_operation_index": target_index,
        "target_operation_scope": injected_scope,
        "injection": {
            "rank": int(injected_workload[0]["delay_rank"]),
            "measured_iteration": iteration,
            "block": block,
            "bucket_index": bucket,
            "bucket_mib": injected_workload[0]["bucket_mib"][bucket],
            "delay_ms": float(injected_workload[0]["delay_ms"]),
        },
        "workload": {
            "world_size": int(injected_workload[0]["world_size"]),
            "blocks": int(injected_workload[0]["blocks"]),
            "tokens": int(injected_workload[0]["tokens"]),
            "hidden_size": int(injected_workload[0]["hidden_size"]),
            "ffn_size": int(injected_workload[0]["ffn_size"]),
            "payload_mib_per_step": int(injected_workload[0]["payload_bytes_per_step"]) / 1024 / 1024,
            "baseline_avg_step_ms": sum(float(row["avg_step_ms"]) for row in baseline_workload) / 4,
            "injected_avg_step_ms": sum(float(row["avg_step_ms"]) for row in injected_workload) / 4,
            "baseline_max_error": max(float(row["max_error"]) for row in baseline_workload),
            "injected_max_error": max(float(row["max_error"]) for row in injected_workload),
        },
        "propagated_ranks": sorted(propagated_ranks),
        "detected": bool(propagated_ranks),
        "semantic_boundary": "native semantic unavailable on the default 910C AICPU path",
    }
    (args.output_dir / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    write_csv(args.output_dir / "target_wait_comparison.csv", target_rows)
    write_csv(args.output_dir / "operation_wait_comparison.csv", operation_comparison)

    top = sorted(operation_comparison, key=lambda row: float(row["delta_us"]), reverse=True)[:5]
    lines = [
        f"# Transformer-CommMix node{args.node_rank} 诊断结果",
        "",
        f"- operation 数量：{expected_operations}",
        f"- 注入目标：operation {target_index}，step {iteration} / block {block} / "
        f"bucket {bucket} ({summary['injection']['bucket_mib']} MiB)",
        f"- operation scope：`{injected_scope}`",
        f"- 本节点检测到传播的 ranks：{summary['propagated_ranks']}",
        f"- baseline / 异常组 max_error：{summary['workload']['baseline_max_error']} / "
        f"{summary['workload']['injected_max_error']}",
        "",
        "## 最大等待增量 operation",
        "",
        "| operation | block | bucket/MiB | baseline/us | injected/us | delta/us |",
        "|---:|---:|---:|---:|---:|---:|",
    ]
    lines.extend(
        "| {operation_index} | {block} | {bucket_mib} | {baseline_max_wait_us:.3f} | "
        "{injected_max_wait_us:.3f} | {delta_us:.3f} |".format(**row)
        for row in top
    )
    lines.extend(
        [
            "",
            "## 解释边界",
            "",
            "当前结果能定位 profiler operation、设备、Rank 和 wait task；由于 native semantic 缺失，"
            "不能进一步命名 HCCL 内部 phase/step/event 或证明唯一跨节点依赖边。",
        ]
    )
    (args.output_dir / "RESULTS.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return 0 if summary["detected"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
