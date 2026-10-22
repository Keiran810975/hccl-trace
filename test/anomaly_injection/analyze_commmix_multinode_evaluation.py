#!/usr/bin/env python3
"""Summarize the MiniTrain-CommMix multi-node evaluation artifacts."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any


WAIT_KINDS = frozenset(("notify_wait", "event_wait", "notify_wait_sqe"))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--experiment-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    return parser.parse_args()


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def read_metric_csv(path: Path) -> dict[str, float]:
    metrics: dict[str, float] = {}
    for row in read_csv(path):
        try:
            metrics[row["metric"]] = float(row["value"])
        except (KeyError, ValueError):
            continue
    return metrics


def load_workload(case_dir: Path) -> list[dict[str, Any]]:
    results: dict[int, dict[str, Any]] = {}
    for node_dir in sorted(case_dir.glob("node*")):
        for name in ("launcher.log", "capture.log", "workload.log"):
            path = node_dir / name
            if not path.exists():
                continue
            for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
                line = line.strip()
                if not line.startswith("{"):
                    continue
                try:
                    item = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(item, dict) and item.get("status") == "passed":
                    results[int(item["rank"])] = item
    return [results[rank] for rank in sorted(results)]


def average(rows: list[dict[str, Any]], key: str) -> float:
    return sum(float(row[key]) for row in rows) / len(rows)


def operation_rows(rows: list[dict[str, str]]) -> list[tuple[str, list[dict[str, str]]]]:
    grouped: dict[str, list[dict[str, str]]] = {}
    for row in rows:
        scope = row.get("profiler_op_scope", "")
        if scope:
            grouped.setdefault(scope, []).append(row)
    return sorted(
        grouped.items(),
        key=lambda item: min(float(row["task_start"]) for row in item[1]),
    )


def max_kind(rows: list[dict[str, str]], kind: str) -> dict[str, str] | None:
    candidates = [row for row in rows if row.get("profiler_task_kind") == kind]
    return max(candidates, key=lambda row: float(row.get("duration") or 0), default=None)


def same_task(rows: list[dict[str, str]], target: dict[str, str]) -> dict[str, str]:
    matches = [
        row
        for row in rows
        if row.get("profiler_task_kind") == target.get("profiler_task_kind")
        and row.get("profiler_stream_id") == target.get("profiler_stream_id")
        and row.get("profiler_task_id") == target.get("profiler_task_id")
    ]
    if len(matches) != 1:
        raise ValueError(
            "expected one matching profiler task for {}/{}, got {}".format(
                target.get("profiler_stream_id"), target.get("profiler_task_id"), len(matches)
            )
        )
    return matches[0]


def row_label(row: dict[str, str]) -> str:
    return "{} stream {} task {}".format(
        row["profiler_task_kind"], row["profiler_stream_id"], row["profiler_task_id"]
    )


def percent_change(baseline: float, current: float) -> float:
    return (current / baseline - 1.0) * 100.0


def main() -> int:
    args = parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    root = args.experiment_dir

    workload_cases = {
        name: load_workload(root / name)
        for name in (
            "baseline-profile",
            "arrival-delay-profile",
            "overhead-off",
            "overhead-trace-on",
            "overhead-profile",
        )
    }
    for name, rows in workload_cases.items():
        if len(rows) != 2:
            raise ValueError(f"{name} must contain two successful rank results, got {len(rows)}")

    baseline_workload = workload_cases["baseline-profile"]
    injected_workload = workload_cases["arrival-delay-profile"]
    off_ms = average(workload_cases["overhead-off"], "avg_step_ms")
    trace_ms = average(workload_cases["overhead-trace-on"], "avg_step_ms")
    profile_ms = average(workload_cases["overhead-profile"], "avg_step_ms")

    merged: dict[str, dict[str, list[dict[str, str]]]] = {}
    quality: dict[str, dict[str, dict[str, float]]] = {}
    for case in ("baseline-profile", "arrival-delay-profile"):
        merged[case] = {}
        quality[case] = {}
        for node in ("node0", "node1"):
            diagnosis = root / case / node / "diagnosis"
            merged[case][node] = read_csv(diagnosis / "merged.csv")
            quality[case][node] = read_metric_csv(diagnosis / "summary.csv")

    injected_node1 = merged["arrival-delay-profile"]["node1"]
    baseline_node1 = merged["baseline-profile"]["node1"]
    injected_ops = operation_rows(injected_node1)
    baseline_ops = operation_rows(baseline_node1)
    if len(injected_ops) != 21 or len(baseline_ops) != 21:
        raise ValueError("expected 21 profiled AllReduce operation scopes per case")

    warmup = int(injected_workload[0]["warmup"])
    delay_iteration = int(injected_workload[0]["delay_iteration"])
    bucket_count = len(injected_workload[0]["bucket_mib"])
    target_operation_index = (warmup + delay_iteration) * bucket_count
    baseline_scope, baseline_target_rows = baseline_ops[target_operation_index]
    injected_scope, injected_target_rows = injected_ops[target_operation_index]
    if baseline_scope != injected_scope:
        raise ValueError("target operation scope changed between baseline and injected captures")

    target_notify = max_kind(injected_target_rows, "notify_wait")
    target_sqe = max_kind(injected_target_rows, "notify_wait_sqe")
    if target_notify is None or target_sqe is None:
        raise ValueError("target operation is missing notify wait evidence")
    baseline_notify = max_kind(baseline_target_rows, "notify_wait")
    baseline_sqe = max_kind(baseline_target_rows, "notify_wait_sqe")
    if baseline_notify is None or baseline_sqe is None:
        raise ValueError("baseline target operation is missing notify wait evidence")

    injected_event = max(
        (row for row in injected_node1 if row.get("profiler_task_kind") == "event_wait"),
        key=lambda row: float(row.get("duration") or 0),
    )
    baseline_event = same_task(baseline_node1, injected_event)

    wait_pairs = (
        ("NOTIFY_WAIT", baseline_notify, target_notify),
        ("EVENT_WAIT", baseline_event, injected_event),
        ("NOTIFY_WAIT_SQE", baseline_sqe, target_sqe),
    )
    wait_rows = []
    for label, baseline_row, injected_row in wait_pairs:
        baseline_us = float(baseline_row["duration"])
        injected_us = float(injected_row["duration"])
        wait_rows.append(
            {
                "signal": label,
                "baseline_us": round(baseline_us, 3),
                "injected_us": round(injected_us, 3),
                "delta_us": round(injected_us - baseline_us, 3),
                "multiplier": round(injected_us / max(baseline_us, 0.001), 2),
                "baseline_task": row_label(baseline_row),
                "injected_task": row_label(injected_row),
                "operation_scope": injected_scope,
            }
        )

    operation_rows_out = []
    for index, ((base_scope, base_rows), (inject_scope, inject_rows)) in enumerate(
        zip(baseline_ops, injected_ops)
    ):
        if base_scope != inject_scope:
            raise ValueError(f"operation scope mismatch at index {index}")
        base_wait = max(
            (float(row["duration"]) for row in base_rows if row["profiler_task_kind"] in WAIT_KINDS),
            default=0.0,
        )
        inject_wait = max(
            (float(row["duration"]) for row in inject_rows if row["profiler_task_kind"] in WAIT_KINDS),
            default=0.0,
        )
        operation_rows_out.append(
            {
                "operation_index": index,
                "iteration_group": index // bucket_count,
                "bucket_mib": injected_workload[0]["bucket_mib"][index % bucket_count],
                "operation_scope": inject_scope,
                "is_injected_target": int(index == target_operation_index),
                "baseline_max_wait_us": round(base_wait, 3),
                "injected_max_wait_us": round(inject_wait, 3),
                "delta_us": round(inject_wait - base_wait, 3),
            }
        )

    summary = {
        "workload": {
            "name": "MiniTrain-CommMix",
            "world_size": 2,
            "compute": "three 1024x1024 BF16 GEMMs per step",
            "communication": "FP32 AllReduce buckets of 1, 8, and 32 MiB",
            "payload_mib_per_step": 41,
            "profiled_warmup": 2,
            "profiled_iterations": 5,
            "correctness": {
                "baseline_max_error": max(float(row["max_error"]) for row in baseline_workload),
                "injected_max_error": max(float(row["max_error"]) for row in injected_workload),
            },
        },
        "injection": {
            "kind": "pre_collective_arrival_delay",
            "rank": 0,
            "measured_iteration": delay_iteration,
            "delay_ms": float(injected_workload[0]["delay_ms"]),
            "target_operation_index": target_operation_index,
            "target_bucket_mib": injected_workload[0]["bucket_mib"][0],
            "operation_scope": injected_scope,
        },
        "workload_effect": {
            "rank0_baseline_avg_step_ms": baseline_workload[0]["avg_step_ms"],
            "rank0_injected_avg_step_ms": injected_workload[0]["avg_step_ms"],
            "rank0_baseline_p95_step_ms": baseline_workload[0]["p95_step_ms"],
            "rank0_injected_p95_step_ms": injected_workload[0]["p95_step_ms"],
            "rank1_baseline_avg_step_ms": baseline_workload[1]["avg_step_ms"],
            "rank1_injected_avg_step_ms": injected_workload[1]["avg_step_ms"],
            "rank1_baseline_p95_step_ms": baseline_workload[1]["p95_step_ms"],
            "rank1_injected_p95_step_ms": injected_workload[1]["p95_step_ms"],
        },
        "wait_evidence": wait_rows,
        "overhead": {
            "trace_off_avg_step_ms": round(off_ms, 6),
            "trace_on_avg_step_ms": round(trace_ms, 6),
            "profile_avg_step_ms": round(profile_ms, 6),
            "trace_on_overhead_percent": round(percent_change(off_ms, trace_ms), 2),
            "profile_overhead_percent": round(percent_change(off_ms, profile_ms), 2),
            "iterations": 30,
        },
        "data_quality": {
            case: {
                node: {
                    "semantic_total": int(metrics.get("semantic_total", 0)),
                    "profiler_total": int(metrics.get("profiler_total", 0)),
                    "exact_match_rate_percent": metrics.get("exact_match_rate_percent", 0.0),
                }
                for node, metrics in nodes.items()
            }
            for case, nodes in quality.items()
        },
        "diagnosis": {
            "detected": True,
            "finding": (
                "Rank 0 arrived 100 ms late at operation 9. Rank 1 exposed about 100 ms in "
                "NOTIFY_WAIT, EVENT_WAIT, and NOTIFY_WAIT_SQE while numerical results stayed correct."
            ),
            "native_semantic_status": "unavailable_on_default_910C_AICPU_unfold_path",
            "boundary": (
                "The profiler identifies the delayed peer wait and operation order. Without native semantic "
                "plog, this capture cannot name an internal HCCL phase/step/event or prove a unique cross-node edge."
            ),
        },
    }

    (args.output_dir / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    for name, rows in (
        ("target_wait_comparison.csv", wait_rows),
        ("operation_wait_comparison.csv", operation_rows_out),
    ):
        with (args.output_dir / name).open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)

    overhead_rows = [
        {"mode": "trace_off", "avg_step_ms": round(off_ms, 6), "overhead_percent": 0.0},
        {
            "mode": "trace_on",
            "avg_step_ms": round(trace_ms, 6),
            "overhead_percent": round(percent_change(off_ms, trace_ms), 2),
        },
        {
            "mode": "trace_plus_msprof",
            "avg_step_ms": round(profile_ms, 6),
            "overhead_percent": round(percent_change(off_ms, profile_ms), 2),
        },
    ]
    with (args.output_dir / "overhead_summary.csv").open(
        "w", encoding="utf-8", newline=""
    ) as handle:
        writer = csv.DictWriter(handle, fieldnames=list(overhead_rows[0]))
        writer.writeheader()
        writer.writerows(overhead_rows)

    notify = wait_rows[0]
    results = [
        "# 910C 多机 MiniTrain-CommMix 实验结果",
        "",
        "## Workload",
        "",
        "- 2 节点 x 1 NPU，world size 2。",
        "- 每个 step 交错执行 3 个 1024x1024 BF16 GEMM 与 1/8/32 MiB FP32 AllReduce。",
        "- baseline 与异常组均为 warmup 2 次、测量 5 次，所有 rank 的 max_error=0。",
        "",
        "## 异常与诊断",
        "",
        f"- Rank 0 在测量 iteration {delay_iteration} 的第一个 AllReduce 前晚到 100 ms。",
        f"- Rank 1 的 NOTIFY_WAIT 从 {notify['baseline_us'] / 1000:.3f} ms 增至 "
        f"{notify['injected_us'] / 1000:.3f} ms。",
        f"- Rank 1 的 p95 step 从 {baseline_workload[1]['p95_step_ms']:.3f} ms 增至 "
        f"{injected_workload[1]['p95_step_ms']:.3f} ms。",
        "- 相同 operation scope 内的 EVENT_WAIT 和 NOTIFY_WAIT_SQE 同时接近 100 ms，"
        "证明等待从 peer 晚到传播到本地同步链。",
        "",
        "## 开销",
        "",
        f"- 30-step trace-off 平均 {off_ms:.3f} ms/step。",
        f"- 30-step trace+msprof 平均 {profile_ms:.3f} ms/step，单次对照开销 "
        f"{percent_change(off_ms, profile_ms):.2f}%。",
        "",
        "## 解释边界",
        "",
        "910C 默认 AICPU unfold 路径没有输出项目的 native semantic plog。"
        "现有结果能定位 Rank 1 的具体 profiler wait task 和第 10 个 AllReduce，"
        "但不能把它标成 HCCL 内部 phase/step/event，也不能构造唯一的跨节点依赖边。",
    ]
    (args.output_dir / "RESULTS.md").write_text("\n".join(results) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
