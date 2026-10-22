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
        description="Compare one HCCL baseline capture with a targeted delay capture."
    )
    parser.add_argument("--baseline-dir", type=Path, required=True)
    parser.add_argument("--injected-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--rank", type=int, required=True)
    parser.add_argument("--phase", required=True)
    parser.add_argument("--step", type=int, required=True)
    parser.add_argument("--event", required=True)
    parser.add_argument("--occurrence", type=int, default=0)
    parser.add_argument("--slow-wait-ms", type=float, default=50.0)
    return parser.parse_args()


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def as_float(value: str | None) -> float:
    return float(value or 0)


def load_workload_results(case_dir: Path) -> list[dict[str, Any]]:
    for name in ("capture.log", "workload.log"):
        path = case_dir / name
        if not path.exists():
            continue
        results = []
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            line = line.strip()
            if not line.startswith("{"):
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


def select_target(
    nodes: list[dict[str, str]], args: argparse.Namespace
) -> dict[str, str]:
    candidates = [
        row
        for row in nodes
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
    return candidates[args.occurrence]


def incoming_stream_gap(
    target: dict[str, str],
    nodes_by_id: dict[str, dict[str, str]],
    edges: list[dict[str, str]],
) -> tuple[dict[str, str], float]:
    incoming = [
        edge
        for edge in edges
        if edge.get("dst") == target["graph_id"]
        and edge.get("kind") == "direct_stream_order_observed"
    ]
    if len(incoming) != 1:
        raise ValueError(
            f"expected one incoming direct stream edge for {target['graph_id']}, got {len(incoming)}"
        )
    predecessor = nodes_by_id[incoming[0]["src"]]
    gap_us = as_float(target.get("task_start")) - as_float(predecessor.get("task_stop"))
    return predecessor, gap_us


def node_signature(node: dict[str, str]) -> tuple[str, ...]:
    return (
        node.get("profiler_op_scope", ""),
        node.get("device_id", ""),
        node.get("user_rank", ""),
        node.get("phase", ""),
        node.get("step", ""),
        node.get("slice", ""),
        node.get("event", ""),
        node.get("profiler_task_kind", ""),
    )


def edge_signature(
    edge: dict[str, str], nodes_by_id: dict[str, dict[str, str]]
) -> tuple[str, ...]:
    return (
        edge.get("kind", ""),
        edge.get("phase", ""),
        edge.get("step", ""),
        edge.get("slice", ""),
        edge.get("signal_kind", ""),
        *node_signature(nodes_by_id[edge["src"]]),
        *node_signature(nodes_by_id[edge["dst"]]),
    )


def trace_quality(case_dir: Path) -> dict[str, Any]:
    rows = read_csv(case_dir / "diagnosis" / "merged.csv")
    semantic = [row for row in rows if row.get("match_status") != "profiler_only"]
    matched = sum(row.get("match_status") == "matched" for row in semantic)
    unmatched = sum(row.get("match_status") == "unmatched_semantic" for row in semantic)
    invalid = sum(
        row.get("match_status") == "matched"
        and row.get("match_confidence") not in ("", "exact")
        for row in semantic
    )
    return {
        "semantic_total": len(semantic),
        "matched": matched,
        "unmatched_semantic": unmatched,
        "exact_match_rate_percent": round(100.0 * matched / len(semantic), 2)
        if semantic
        else 0.0,
        "non_exact_matched": invalid,
    }


def write_edge_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    fieldnames = [
        "kind",
        "phase",
        "step",
        "signal_kind",
        "src_rank",
        "src_event",
        "dst_rank",
        "dst_event",
        "baseline_wait_ms",
        "injected_wait_ms",
        "delta_wait_ms",
        "evidence",
        "confidence",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    args = parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)

    case_data: dict[str, dict[str, Any]] = {}
    for label, case_dir in (
        ("baseline", args.baseline_dir),
        ("injected", args.injected_dir),
    ):
        diagnosis = case_dir / "diagnosis"
        nodes = read_csv(diagnosis / "dep_graph_nodes.csv")
        edges = read_csv(diagnosis / "dep_graph_edges.csv")
        nodes_by_id = {row["graph_id"]: row for row in nodes}
        target = select_target(nodes, args)
        predecessor, gap_us = incoming_stream_gap(target, nodes_by_id, edges)
        resource_nodes = read_csv(diagnosis / "dep_graph_resource_nodes.csv")
        resource_edges = read_csv(diagnosis / "dep_graph_resource_edges.csv")
        case_data[label] = {
            "case_dir": case_dir,
            "target": target,
            "predecessor": predecessor,
            "gap_us": gap_us,
            "resource_nodes": {row["graph_id"]: row for row in resource_nodes},
            "resource_edges": resource_edges,
            "workload": load_workload_results(case_dir),
            "quality": trace_quality(case_dir),
        }

    baseline_resource_nodes = case_data["baseline"]["resource_nodes"]
    baseline_by_signature: dict[tuple[str, ...], float] = {}
    for edge in case_data["baseline"]["resource_edges"]:
        signature = edge_signature(edge, baseline_resource_nodes)
        baseline_by_signature[signature] = max(
            baseline_by_signature.get(signature, 0.0),
            as_float(edge.get("wait_span_ns")) / 1_000_000,
        )

    injected_target_scope = case_data["injected"]["target"].get("profiler_op_scope")
    injected_resource_nodes = case_data["injected"]["resource_nodes"]
    slow_edges = []
    for edge in case_data["injected"]["resource_edges"]:
        src = injected_resource_nodes[edge["src"]]
        dst = injected_resource_nodes[edge["dst"]]
        if injected_target_scope not in (
            src.get("profiler_op_scope"),
            dst.get("profiler_op_scope"),
        ):
            continue
        wait_ms = as_float(edge.get("wait_span_ns")) / 1_000_000
        if wait_ms < args.slow_wait_ms:
            continue
        baseline_wait_ms = baseline_by_signature.get(
            edge_signature(edge, injected_resource_nodes), 0.0
        )
        slow_edges.append(
            {
                "kind": edge.get("kind", ""),
                "phase": edge.get("phase", ""),
                "step": edge.get("step", ""),
                "signal_kind": edge.get("signal_kind", ""),
                "src_rank": src.get("user_rank", ""),
                "src_event": src.get("event", ""),
                "dst_rank": dst.get("user_rank", ""),
                "dst_event": dst.get("event", ""),
                "baseline_wait_ms": round(baseline_wait_ms, 3),
                "injected_wait_ms": round(wait_ms, 3),
                "delta_wait_ms": round(wait_ms - baseline_wait_ms, 3),
                "evidence": edge.get("evidence", ""),
                "confidence": edge.get("confidence", ""),
            }
        )
    slow_edges.sort(key=lambda row: row["injected_wait_ms"], reverse=True)

    baseline_workload = case_data["baseline"]["workload"]
    injected_workload = case_data["injected"]["workload"]
    baseline_avg_ms = max((float(row["avg_ms"]) for row in baseline_workload), default=0.0)
    injected_avg_ms = max((float(row["avg_ms"]) for row in injected_workload), default=0.0)
    target_gap_delta_ms = (
        case_data["injected"]["gap_us"] - case_data["baseline"]["gap_us"]
    ) / 1000
    propagated_ranks = sorted(
        {
            int(row["dst_rank"])
            for row in slow_edges
            if row["kind"] == "resource_notify_sync_exact"
            and row["dst_rank"].lstrip("-").isdigit()
            and int(row["dst_rank"]) >= 0
        }
    )
    workload_correct = bool(injected_workload) and all(
        row.get("status") == "passed" and float(row.get("max_error", 1)) == 0
        for row in injected_workload
    )
    summary = {
        "experiment": {
            "rank": args.rank,
            "phase": args.phase,
            "step": args.step,
            "event": args.event,
            "occurrence": args.occurrence,
            "operation_scope": injected_target_scope,
        },
        "baseline": {
            "max_rank_avg_ms": round(baseline_avg_ms, 3),
            "target_incoming_gap_us": round(case_data["baseline"]["gap_us"], 3),
            "trace_quality": case_data["baseline"]["quality"],
        },
        "injected": {
            "max_rank_avg_ms": round(injected_avg_ms, 3),
            "target_incoming_gap_us": round(case_data["injected"]["gap_us"], 3),
            "trace_quality": case_data["injected"]["quality"],
            "workload_correct": workload_correct,
        },
        "diagnosis": {
            "target_gap_delta_ms": round(target_gap_delta_ms, 3),
            "slow_dependency_edge_count": len(slow_edges),
            "propagated_destination_ranks": propagated_ranks,
            "target_localized": target_gap_delta_ms >= args.slow_wait_ms,
            "wait_anomaly_detected": bool(slow_edges),
            "blocking_propagation_detected": len(propagated_ranks) >= 2,
        },
        "slow_edges": slow_edges,
    }

    (args.output_dir / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    write_edge_csv(args.output_dir / "slow_dependency_edges.csv", slow_edges)
    markdown = [
        "# 910B 单机 HCCL 异常诊断结果",
        "",
        f"- 注入目标：rank {args.rank} / {args.phase} / step {args.step} / {args.event} / occurrence {args.occurrence}",
        f"- baseline 最慢 rank：{baseline_avg_ms:.3f} ms；注入后：{injected_avg_ms:.3f} ms",
        f"- 目标任务入边间隙增量：{target_gap_delta_ms:.3f} ms",
        f"- 超过 {args.slow_wait_ms:.1f} ms 的依赖等待边：{len(slow_edges)} 条",
        f"- 阻塞传播到的目标 ranks：{propagated_ranks}",
        f"- 工作负载数值正确：{'PASS' if workload_correct else 'FAIL'}",
        f"- 目标定位：{'PASS' if summary['diagnosis']['target_localized'] else 'FAIL'}",
        f"- Notify/等待异常：{'PASS' if summary['diagnosis']['wait_anomaly_detected'] else 'FAIL'}",
        f"- 跨 Rank 阻塞传播：{'PASS' if summary['diagnosis']['blocking_propagation_detected'] else 'FAIL'}",
        "",
        "详细等待边见 `slow_dependency_edges.csv`，完整机器可读结果见 `summary.json`。",
    ]
    (args.output_dir / "RESULTS.md").write_text("\n".join(markdown) + "\n", encoding="utf-8")

    print(json.dumps(summary["diagnosis"], ensure_ascii=False, sort_keys=True))
    return 0 if all(
        (
            workload_correct,
            summary["diagnosis"]["target_localized"],
            summary["diagnosis"]["wait_anomaly_detected"],
            summary["diagnosis"]["blocking_propagation_detected"],
        )
    ) else 1


if __name__ == "__main__":
    raise SystemExit(main())
