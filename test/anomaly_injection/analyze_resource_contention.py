#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

import argparse
import csv
import json
import statistics
from collections import defaultdict
from decimal import Decimal
from pathlib import Path
from typing import Any


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Compare physical HCCL resource task durations with a baseline."
    )
    parser.add_argument("--baseline-dir", type=Path, required=True)
    parser.add_argument("--contended-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--target-rank", type=int, required=True)
    parser.add_argument("--task-kind", default="sdma")
    parser.add_argument("--min-ratio", type=float, default=1.5)
    parser.add_argument("--min-delta-us", type=float, default=20.0)
    parser.add_argument("--min-slowed-tasks", type=int, default=2)
    parser.add_argument("--top", type=int, default=20)
    return parser.parse_args()


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def duration_us(row: dict[str, str]) -> float:
    if row.get("duration", "").strip():
        return float(Decimal(row["duration"]))
    return float(Decimal(row["task_stop"]) - Decimal(row["task_start"]))


def signature(row: dict[str, str]) -> tuple[str, ...]:
    return (
        row.get("user_rank", ""),
        row.get("phase", ""),
        row.get("step", ""),
        row.get("slice", ""),
        row.get("event", ""),
        row.get("semantic", ""),
        row.get("profiler_task_kind", ""),
    )


def edge_signature(
    edge: dict[str, str], nodes: dict[str, dict[str, str]]
) -> tuple[str, ...]:
    return (
        edge.get("kind", ""),
        *signature(nodes[edge["src"]]),
        *signature(nodes[edge["dst"]]),
    )


def artifact_dir(case_dir: Path) -> Path:
    diagnosis = case_dir / "diagnosis"
    return diagnosis if diagnosis.is_dir() else case_dir


def load_resource_tasks(case_dir: Path, task_kind: str) -> list[dict[str, str]]:
    rows = read_csv(artifact_dir(case_dir) / "dep_graph_resource_nodes.csv")
    return [
        row
        for row in rows
        if row.get("node_kind") != "boundary"
        and row.get("match_status") == "matched"
        and row.get("profiler_task_kind") == task_kind
        and row.get("user_rank", "-1").lstrip("-").isdigit()
        and int(row["user_rank"]) >= 0
    ]


def load_resource_graph(
    case_dir: Path,
) -> tuple[dict[str, dict[str, str]], list[dict[str, str]]]:
    diagnosis = artifact_dir(case_dir)
    nodes = read_csv(diagnosis / "dep_graph_resource_nodes.csv")
    return (
        {row["graph_id"]: row for row in nodes},
        read_csv(diagnosis / "dep_graph_resource_edges.csv"),
    )


def group_occurrences(
    rows: list[dict[str, str]],
) -> dict[tuple[str, ...], list[dict[str, str]]]:
    grouped: dict[tuple[str, ...], list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        grouped[signature(row)].append(row)
    for occurrences in grouped.values():
        occurrences.sort(key=lambda row: float(row["task_start"]))
    return grouped


def summarize(values: list[float]) -> dict[str, float | int]:
    ordered = sorted(values)
    if not ordered:
        return {"count": 0, "median_us": 0.0, "p95_us": 0.0, "max_us": 0.0}
    p95_index = min(len(ordered) - 1, int(0.95 * len(ordered)))
    return {
        "count": len(ordered),
        "median_us": round(statistics.median(ordered), 3),
        "p95_us": round(ordered[p95_index], 3),
        "max_us": round(ordered[-1], 3),
    }


def load_workload_results(case_dir: Path) -> list[dict[str, Any]]:
    for name in ("capture.log", "workload.log", "workload_results.jsonl"):
        path = case_dir / name
        if not path.exists():
            continue
        results = []
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            if not line.lstrip().startswith("{"):
                continue
            try:
                value = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(value, dict) and "rank" in value and "status" in value:
                results.append(value)
        if results:
            return sorted(results, key=lambda item: int(item["rank"]))
    return []


def write_comparison(path: Path, rows: list[dict[str, Any]]) -> None:
    fieldnames = [
        "rank",
        "phase",
        "step",
        "slice",
        "event",
        "semantic",
        "task_kind",
        "occurrence",
        "baseline_duration_us",
        "contended_duration_us",
        "delta_us",
        "ratio",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def write_affected_edges(path: Path, rows: list[dict[str, Any]]) -> None:
    fieldnames = [
        "kind",
        "confidence",
        "src_rank",
        "src_phase",
        "src_step",
        "src_slice",
        "src_event",
        "dst_rank",
        "dst_phase",
        "dst_step",
        "dst_slice",
        "dst_event",
        "baseline_wait_us",
        "contended_wait_us",
        "delta_wait_us",
        "baseline_handoff_us",
        "contended_handoff_us",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def ns_to_us(value: str | None) -> float:
    return float(value) / 1000 if value else 0.0


def main() -> int:
    args = parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)

    baseline = load_resource_tasks(args.baseline_dir, args.task_kind)
    contended = load_resource_tasks(args.contended_dir, args.task_kind)
    baseline_groups = group_occurrences(baseline)
    contended_groups = group_occurrences(contended)

    comparisons: list[dict[str, Any]] = []
    unmatched_occurrences = 0
    for key in sorted(set(baseline_groups) | set(contended_groups)):
        baseline_rows = baseline_groups.get(key, [])
        contended_rows = contended_groups.get(key, [])
        paired = min(len(baseline_rows), len(contended_rows))
        unmatched_occurrences += abs(len(baseline_rows) - len(contended_rows))
        for occurrence in range(paired):
            baseline_duration = duration_us(baseline_rows[occurrence])
            contended_duration = duration_us(contended_rows[occurrence])
            comparisons.append(
                {
                    "rank": int(key[0]),
                    "phase": key[1],
                    "step": int(key[2]),
                    "slice": int(key[3]),
                    "event": key[4],
                    "semantic": key[5],
                    "task_kind": key[6],
                    "occurrence": occurrence,
                    "baseline_duration_us": round(baseline_duration, 3),
                    "contended_duration_us": round(contended_duration, 3),
                    "delta_us": round(contended_duration - baseline_duration, 3),
                    "ratio": round(contended_duration / baseline_duration, 3)
                    if baseline_duration > 0
                    else 0.0,
                }
            )

    comparisons.sort(key=lambda row: (row["ratio"], row["delta_us"]), reverse=True)
    write_comparison(args.output_dir / "resource_task_comparison.csv", comparisons)

    rank_summary: dict[str, dict[str, Any]] = {}
    for rank in sorted({int(row["user_rank"]) for row in baseline + contended}):
        baseline_values = [duration_us(row) for row in baseline if int(row["user_rank"]) == rank]
        contended_values = [duration_us(row) for row in contended if int(row["user_rank"]) == rank]
        base_stats = summarize(baseline_values)
        contended_stats = summarize(contended_values)
        rank_summary[str(rank)] = {
            "baseline": base_stats,
            "contended": contended_stats,
            "p95_ratio": round(
                float(contended_stats["p95_us"]) / float(base_stats["p95_us"]), 3
            )
            if float(base_stats["p95_us"]) > 0
            else 0.0,
            "max_ratio": round(
                float(contended_stats["max_us"]) / float(base_stats["max_us"]), 3
            )
            if float(base_stats["max_us"]) > 0
            else 0.0,
        }

    target = rank_summary.get(str(args.target_rank), {})
    target_p95_ratio = float(target.get("p95_ratio", 0.0))
    target_pairs = [row for row in comparisons if row["rank"] == args.target_rank]
    max_target_ratio = max((float(row["ratio"]) for row in target_pairs), default=0.0)
    baseline_workload = load_workload_results(args.baseline_dir)
    contended_workload = load_workload_results(args.contended_dir)
    workload = baseline_workload + contended_workload
    workload_correct = bool(baseline_workload) and bool(contended_workload) and all(
        row.get("status") == "passed" and float(row.get("max_error", 1)) == 0
        for row in workload
    )
    slowed_target_tasks = [
        row
        for row in target_pairs
        if float(row["ratio"]) >= args.min_ratio
        and float(row["delta_us"]) >= args.min_delta_us
    ]
    detected = len(slowed_target_tasks) >= args.min_slowed_tasks

    baseline_nodes, baseline_edges = load_resource_graph(args.baseline_dir)
    contended_nodes, contended_edges = load_resource_graph(args.contended_dir)
    slowed_graph_ids = set()
    for row in slowed_target_tasks:
        key = (
            str(row["rank"]),
            str(row["phase"]),
            str(row["step"]),
            str(row["slice"]),
            str(row["event"]),
            str(row["semantic"]),
            str(row["task_kind"]),
        )
        occurrences = contended_groups.get(key, [])
        occurrence = int(row["occurrence"])
        if occurrence < len(occurrences):
            slowed_graph_ids.add(occurrences[occurrence]["graph_id"])

    baseline_edge_groups: dict[tuple[str, ...], list[dict[str, str]]] = defaultdict(list)
    for edge in baseline_edges:
        baseline_edge_groups[edge_signature(edge, baseline_nodes)].append(edge)
    for edges in baseline_edge_groups.values():
        edges.sort(key=lambda edge: edge.get("relation_id", ""))

    affected_edges: list[dict[str, Any]] = []
    edge_occurrences: dict[tuple[str, ...], int] = defaultdict(int)
    candidate_edges = sorted(
        (
            edge
            for edge in contended_edges
            if edge["src"] in slowed_graph_ids and "notify_sync" in edge.get("kind", "")
        ),
        key=lambda edge: (edge_signature(edge, contended_nodes), edge.get("relation_id", "")),
    )
    for edge in candidate_edges:
        key = edge_signature(edge, contended_nodes)
        occurrence = edge_occurrences[key]
        edge_occurrences[key] += 1
        baseline_candidates = baseline_edge_groups.get(key, [])
        baseline_edge = (
            baseline_candidates[occurrence]
            if occurrence < len(baseline_candidates)
            else {}
        )
        src = contended_nodes[edge["src"]]
        dst = contended_nodes[edge["dst"]]
        baseline_wait = ns_to_us(baseline_edge.get("wait_span_ns"))
        contended_wait = ns_to_us(edge.get("wait_span_ns"))
        affected_edges.append(
            {
                "kind": edge.get("kind", ""),
                "confidence": edge.get("confidence", ""),
                "src_rank": src.get("user_rank", ""),
                "src_phase": src.get("phase", ""),
                "src_step": src.get("step", ""),
                "src_slice": src.get("slice", ""),
                "src_event": src.get("event", ""),
                "dst_rank": dst.get("user_rank", ""),
                "dst_phase": dst.get("phase", ""),
                "dst_step": dst.get("step", ""),
                "dst_slice": dst.get("slice", ""),
                "dst_event": dst.get("event", ""),
                "baseline_wait_us": round(baseline_wait, 3),
                "contended_wait_us": round(contended_wait, 3),
                "delta_wait_us": round(contended_wait - baseline_wait, 3),
                "baseline_handoff_us": round(
                    ns_to_us(baseline_edge.get("handoff_gap_ns")), 3
                ),
                "contended_handoff_us": round(
                    ns_to_us(edge.get("handoff_gap_ns")), 3
                ),
            }
        )
    write_affected_edges(args.output_dir / "affected_dependency_edges.csv", affected_edges)

    summary = {
        "experiment": {
            "target_rank": args.target_rank,
            "task_kind": args.task_kind,
            "minimum_detection_ratio": args.min_ratio,
            "minimum_detection_delta_us": args.min_delta_us,
            "minimum_slowed_tasks": args.min_slowed_tasks,
        },
        "resource_tasks": {
            "baseline": len(baseline),
            "contended": len(contended),
            "paired": len(comparisons),
            "unmatched_occurrences": unmatched_occurrences,
        },
        "rank_summary": rank_summary,
        "top_slowed_tasks": comparisons[: args.top],
        "diagnosis": {
            "target_rank_p95_ratio": target_p95_ratio,
            "maximum_target_task_ratio": round(max_target_ratio, 3),
            "slowed_target_task_count": len(slowed_target_tasks),
            "slowed_target_tasks": slowed_target_tasks,
            "affected_dependency_edge_count": len(affected_edges),
            "affected_dependency_edges": affected_edges,
            "resource_slowdown_detected": detected,
            "workload_correct": workload_correct,
        },
    }
    (args.output_dir / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    markdown = [
        "# 910B 单机 HCCL 资源竞争诊断结果",
        "",
        f"- 目标 Rank：{args.target_rank}",
        f"- 资源类型：{args.task_kind}",
        f"- 目标 Rank P95 duration ratio：{target_p95_ratio:.3f}x",
        f"- 目标 Rank 最大同语义 task duration ratio：{max_target_ratio:.3f}x",
        f"- 同时超过 {args.min_ratio:.2f}x 和 {args.min_delta_us:.1f} us 的目标任务：{len(slowed_target_tasks)} 个",
        f"- 从变慢任务出发的 Notify 依赖边：{len(affected_edges)} 条",
        f"- 配对资源任务：{len(comparisons)}，未配对 occurrence：{unmatched_occurrences}",
        f"- 工作负载数值正确：{'PASS' if workload_correct else 'FAIL'}",
        f"- 资源任务变慢检测：{'PASS' if detected else 'FAIL'}",
        "",
        "任务对比见 `resource_task_comparison.csv`，下游等待见 `affected_dependency_edges.csv`，完整结果见 `summary.json`。",
    ]
    (args.output_dir / "RESULTS.md").write_text("\n".join(markdown) + "\n", encoding="utf-8")
    print(json.dumps(summary["diagnosis"], ensure_ascii=False, sort_keys=True))
    return 0 if workload_correct and detected else 1


if __name__ == "__main__":
    raise SystemExit(main())
