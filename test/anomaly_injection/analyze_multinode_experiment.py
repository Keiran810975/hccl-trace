#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Summarize a two-node HCCL baseline and targeted-delay experiment."
    )
    parser.add_argument("--baseline-dir", type=Path, required=True)
    parser.add_argument("--injected-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--target-node", default="node0")
    parser.add_argument("--rank", type=int, required=True)
    parser.add_argument("--phase", required=True)
    parser.add_argument("--step", type=int, required=True)
    parser.add_argument("--event", required=True)
    parser.add_argument("--occurrence", type=int, default=0)
    return parser.parse_args()


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def as_float(value: str | None) -> float:
    return float(value or 0)


def load_workload(case_dir: Path) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for log_path in sorted(case_dir.glob("node*/**/*.log")):
        for line in log_path.read_text(encoding="utf-8", errors="replace").splitlines():
            line = line.strip()
            if not line.startswith("{"):
                continue
            try:
                value = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(value, dict) and "rank" in value and "status" in value:
                results.append(value)
    unique = {int(row["rank"]): row for row in results}
    return [unique[rank] for rank in sorted(unique)]


def load_node(case_dir: Path, node_id: str) -> dict[str, Any]:
    diagnosis = case_dir / node_id / "diagnosis"
    nodes = read_csv(diagnosis / "dep_graph_nodes.csv")
    edges = read_csv(diagnosis / "dep_graph_edges.csv")
    resource_nodes = read_csv(diagnosis / "dep_graph_resource_nodes.csv")
    resource_edges = read_csv(diagnosis / "dep_graph_resource_edges.csv")
    merged = read_csv(diagnosis / "merged.csv")
    semantic = [row for row in merged if row.get("match_status") != "profiler_only"]
    matched = sum(row.get("match_status") == "matched" for row in semantic)
    return {
        "nodes": nodes,
        "edges": edges,
        "resource_nodes": {row["graph_id"]: row for row in resource_nodes},
        "resource_edges": resource_edges,
        "quality": {
            "semantic_total": len(semantic),
            "matched": matched,
            "unmatched_semantic": sum(
                row.get("match_status") == "unmatched_semantic" for row in semantic
            ),
            "exact_match_rate_percent": round(100.0 * matched / len(semantic), 2)
            if semantic
            else 0.0,
        },
    }


def target_gap(data: dict[str, Any], args: argparse.Namespace) -> tuple[dict[str, str], float]:
    candidates = [
        row
        for row in data["nodes"]
        if row.get("user_rank") == str(args.rank)
        and row.get("phase") == args.phase
        and row.get("step") == str(args.step)
        and row.get("event") == args.event
        and row.get("match_status") == "matched"
    ]
    candidates.sort(key=lambda row: as_float(row.get("task_start")))
    if args.occurrence < 0 or args.occurrence >= len(candidates):
        raise ValueError(
            f"target occurrence {args.occurrence} is outside 0..{len(candidates) - 1}"
        )
    target = candidates[args.occurrence]
    by_id = {row["graph_id"]: row for row in data["nodes"]}
    incoming = [
        edge
        for edge in data["edges"]
        if edge.get("dst") == target["graph_id"]
        and edge.get("kind") == "direct_stream_order_observed"
    ]
    if len(incoming) != 1:
        raise ValueError(f"expected one observed predecessor, got {len(incoming)}")
    predecessor = by_id[incoming[0]["src"]]
    return target, as_float(target.get("task_start")) - as_float(predecessor.get("task_stop"))


def wait_summary(data: dict[str, Any]) -> dict[str, float | int]:
    waits = [
        as_float(edge.get("wait_span_ns")) / 1_000_000
        for edge in data["resource_edges"]
        if edge.get("wait_span_ns") not in (None, "")
    ]
    return {
        "edge_count": len(waits),
        "max_local_wait_ms": round(max(waits, default=0.0), 3),
        "sum_local_wait_ms": round(sum(waits), 3),
    }


def main() -> int:
    args = parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    node_ids = sorted(
        path.name
        for path in args.baseline_dir.glob("node*")
        if (path / "diagnosis" / "merged.csv").exists()
    )
    if not node_ids:
        raise ValueError("no node*/diagnosis/merged.csv inputs found")

    cases: dict[str, dict[str, Any]] = {}
    for label, case_dir in (("baseline", args.baseline_dir), ("injected", args.injected_dir)):
        cases[label] = {
            "workload": load_workload(case_dir),
            "nodes": {node_id: load_node(case_dir, node_id) for node_id in node_ids},
        }

    baseline_target, baseline_gap_us = target_gap(
        cases["baseline"]["nodes"][args.target_node], args
    )
    injected_target, injected_gap_us = target_gap(
        cases["injected"]["nodes"][args.target_node], args
    )
    node_comparison = {}
    for node_id in node_ids:
        baseline_node = cases["baseline"]["nodes"][node_id]
        injected_node = cases["injected"]["nodes"][node_id]
        base_wait = wait_summary(baseline_node)
        inject_wait = wait_summary(injected_node)
        node_comparison[node_id] = {
            "baseline_quality": baseline_node["quality"],
            "injected_quality": injected_node["quality"],
            "baseline_wait": base_wait,
            "injected_wait": inject_wait,
            "max_local_wait_delta_ms": round(
                float(inject_wait["max_local_wait_ms"])
                - float(base_wait["max_local_wait_ms"]),
                3,
            ),
        }

    baseline_workload = cases["baseline"]["workload"]
    injected_workload = cases["injected"]["workload"]
    summary = {
        "experiment": {
            "nodes": node_ids,
            "target_node": args.target_node,
            "rank": args.rank,
            "phase": args.phase,
            "step": args.step,
            "event": args.event,
            "occurrence": args.occurrence,
        },
        "workload": {
            "baseline": baseline_workload,
            "injected": injected_workload,
            "baseline_correct": bool(baseline_workload)
            and all(row.get("status") == "passed" and float(row.get("max_error", 1)) == 0 for row in baseline_workload),
            "injected_correct": bool(injected_workload)
            and all(row.get("status") == "passed" and float(row.get("max_error", 1)) == 0 for row in injected_workload),
        },
        "target": {
            "baseline_graph_id": baseline_target["graph_id"],
            "injected_graph_id": injected_target["graph_id"],
            "baseline_incoming_gap_us": round(baseline_gap_us, 3),
            "injected_incoming_gap_us": round(injected_gap_us, 3),
            "gap_delta_ms": round((injected_gap_us - baseline_gap_us) / 1000, 3),
        },
        "nodes": node_comparison,
        "cross_node_dependency": {
            "status": "not_proven_by_current_artifact",
            "reason": (
                "Per-node artifacts preserve local exact identities. Current production graph "
                "does not yet provide a unique shared cross-node relation token, so local wait "
                "changes are reported without inventing a cross-node edge."
            ),
        },
    }
    (args.output_dir / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    rows = []
    for node_id, item in node_comparison.items():
        rows.append(
            {
                "node_id": node_id,
                "baseline_exact_rate_percent": item["baseline_quality"]["exact_match_rate_percent"],
                "injected_exact_rate_percent": item["injected_quality"]["exact_match_rate_percent"],
                "baseline_max_local_wait_ms": item["baseline_wait"]["max_local_wait_ms"],
                "injected_max_local_wait_ms": item["injected_wait"]["max_local_wait_ms"],
                "max_local_wait_delta_ms": item["max_local_wait_delta_ms"],
            }
        )
    with (args.output_dir / "node_comparison.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

    markdown = [
        "# 多机 HCCL 定点延迟实验结果",
        "",
        f"- 注入目标：{args.target_node} / rank {args.rank} / {args.phase} / step {args.step} / {args.event}",
        f"- 目标任务前驱间隔增量：{summary['target']['gap_delta_ms']:.3f} ms",
        f"- baseline 数值正确：{summary['workload']['baseline_correct']}",
        f"- 注入后数值正确：{summary['workload']['injected_correct']}",
        "",
        "| 节点 | baseline exact | 注入 exact | baseline 最大本地等待/ms | 注入最大本地等待/ms | 增量/ms |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for row in rows:
        markdown.append(
            f"| {row['node_id']} | {row['baseline_exact_rate_percent']:.2f}% | "
            f"{row['injected_exact_rate_percent']:.2f}% | "
            f"{row['baseline_max_local_wait_ms']:.3f} | "
            f"{row['injected_max_local_wait_ms']:.3f} | {row['max_local_wait_delta_ms']:.3f} |"
        )
    markdown.extend(
        [
            "",
            "## 解释边界",
            "",
            "当前 artifact 可以精确定位每个节点内的任务和等待，但尚无可唯一配对的跨节点共享 relation token。",
            "因此报告节点间现象相关性，不伪造跨节点精确因果边，也不做跨节点绝对时间相减。",
        ]
    )
    (args.output_dir / "RESULTS.md").write_text("\n".join(markdown) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
