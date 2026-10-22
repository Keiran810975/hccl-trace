#!/usr/bin/env python3
"""Explain local waits using exported execution evidence and CPU build spans."""
from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from collections import defaultdict
from decimal import Decimal
from pathlib import Path
from statistics import median

if __package__ in (None, ""):
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from diagnosis import visualize_dependency_graph as graph
    from diagnosis.schema import write_csv
    from diagnosis.visualize_html import build_wait_inventory
else:
    from . import visualize_dependency_graph as graph
    from .schema import write_csv
    from .visualize_html import build_wait_inventory


def read_csv(path):
    with Path(path).open(encoding="utf-8-sig", newline="") as source:
        return list(csv.DictReader(source))


def ns(row, side):
    return int(graph.execution_time_order_value(row, side) * 1000)


def duration(row):
    return max(0, ns(row, "stop") - ns(row, "start"))


def signature(row):
    return (row["_user_rank"], row.get("algorithm", ""), row.get("phase", ""),
            row.get("step", ""), row.get("event", ""), row.get("profiler_task_kind", ""),
            row.get("profiler_size_bytes", ""))


def union_ns(intervals):
    result, end = 0, None
    for start, stop in sorted(intervals):
        result += max(0, stop - max(start, end if end is not None else start))
        end = max(stop, end if end is not None else stop)
    return result


def analyze(rows, edges, issues=(), spans=(), baseline_rows=(), min_wait_ns=1000000,
            min_slow_ns=5000000, slowdown_factor=3):
    if min_wait_ns <= 0 or min_slow_ns <= 0 or slowdown_factor <= 1:
        raise ValueError("positive wait/slow thresholds and slowdown factor > 1 required")
    nodes = {r["_graph_id"]: r for r in rows}
    if len(nodes) != len(rows):
        raise ValueError("duplicate execution identity")
    incoming = defaultdict(list)
    for edge in edges:
        if edge["src"] not in nodes or edge["dst"] not in nodes:
            raise ValueError("diagnosis edge has missing endpoint")
        incoming[edge["dst"]].append(edge)
    reference = defaultdict(list)
    for row in baseline_rows:
        reference[signature(row)].append(duration(row))
    candidates = []
    for row in rows:
        kind = row.get("profiler_task_kind", "")
        # RDMA duration is doorbell submission, never transfer completion.
        if kind not in ("sdma", "reduce_inline", "kernel_aicpu") or not row.get("_operation_scope"):
            continue
        values = reference.get(signature(row), [])
        measured = duration(row)
        if measured < min_slow_ns or not values or measured < slowdown_factor * median(values):
            continue
        candidates.append(dict(id="task:" + row["_graph_id"], graph_id=row["_graph_id"],
            node_id=row["_node_id"], user_rank=row["_user_rank"], operation_scope=row.get("_operation_scope", ""),
            algorithm=row.get("algorithm", ""), phase=row.get("phase", "") or
                ("aicpu_orchestration" if kind == "kernel_aicpu" else "unannotated"),
            step=row.get("step", ""), duration_ns=measured, baseline_median_ns=str(median(values)),
            category="slow_aicpu_kernel" if kind == "kernel_aicpu" else "slow_device_execution",
            evidence="DB local duration vs structurally matching baseline; candidate, not proved root cause"))
    kernel_keys = defaultdict(list)
    for row in rows:
        kernel_keys[(row["_node_id"].rsplit("/", 1)[-1], row["_device_id"],
                     row["_stream_id"], row["_task_id"])].append(row)
    for index, span in enumerate(spans):
        key = (span["node_id"], int(span["device_id"]), int(span["kernel_stream_id"]), int(span["kernel_task_id"]))
        matches = kernel_keys.get(key, [])
        if len(matches) != 1 or matches[0].get("profiler_task_kind") != "kernel_aicpu":
            raise ValueError("build span kernel cannot be resolved in execution artifact")
        row = matches[0]
        if int(span["user_rank"]) != row["_user_rank"]:
            raise ValueError("build span rank conflicts with explicit device mapping")
        if int(span["duration_ns"]) < min_slow_ns:
            continue
        candidates.append(dict(id="build:{}:{}".format(row["_graph_id"], index), graph_id=row["_graph_id"],
            node_id=row["_node_id"], user_rank=row["_user_rank"], operation_scope=row.get("_operation_scope", ""),
            algorithm=span["algorithm"], phase=span["phase"], step=span["step"],
            duration_ns=int(span["duration_ns"]), baseline_median_ns="", category="slow_aicpu_build",
            evidence=span["evidence"] + "; CPU construction span, may overlap other spans; not device duration"))
    explained_kernels = {c["graph_id"] for c in candidates if c["category"] == "slow_aicpu_build"}
    candidates = [c for c in candidates if c["category"] != "slow_aicpu_kernel"
                  or c["graph_id"] not in explained_kernels]
    candidates.sort(key=lambda c: (-c["duration_ns"], c["id"]))
    by_op = defaultdict(list)
    for candidate in candidates:
        by_op[candidate["operation_scope"]].append(candidate)
    waits = build_wait_inventory(rows, edges, issues)
    for wait in waits:
        identifier, scope = wait["wait_graph_id"], wait["operation_scope"]
        sync = [e for e in incoming[identifier] if "notify_sync" in e["kind"]]
        seen, paths, queue = set(), {}, []
        for edge in sync:
            queue.append((edge["src"], [edge["edge_id"]]))
        # Only same-operation evidence; never follow yesterday's/previous-call waits.
        position = 0
        while position < len(queue) and len(seen) < 4096:
            current, path = queue[position]; position += 1
            if current in seen or nodes[current].get("_operation_scope", "") != scope:
                continue
            seen.add(current); paths[current] = path
            for edge in incoming[current]:
                if edge["src"] not in seen:
                    queue.append((edge["src"], [edge["edge_id"]] + path))
        related = []
        for candidate in by_op.get(scope, []):
            if candidate["graph_id"] in paths:
                endpoint = candidate["graph_id"]
                link = "dependency_path"
            elif candidate["category"] in ("slow_aicpu_build", "slow_aicpu_kernel"):
                # Kernel execution overlaps its child SQEs. Ownership is not an end->start DAG edge.
                owned = [key for key in seen if nodes[key]["_node_id"] == candidate["node_id"]
                         and nodes[key]["_user_rank"] == candidate["user_rank"]]
                if candidate["category"] == "slow_aicpu_build":
                    owned = [key for key in owned
                             if all(str(nodes[key].get(field, "")) == str(candidate[field])
                                    for field in ("algorithm", "phase", "step"))]
                if not owned:
                    continue
                endpoint = min(owned, key=lambda key: (len(paths[key]), key))
                link = "upstream_rank_operation_correlation"
            else:
                continue
            related.append((candidate, endpoint, link))
        long_wait = Decimal(wait["wait_span_ns"]) >= min_wait_ns
        category = "evidence_gap" if not sync else ("waiting_on_producer" if long_wait else "short_wait")
        if related and long_wait:
            category = "upstream_slow_candidate"
        elif long_wait and any(nodes[key].get("profiler_task_kind") == "notify_wait"
                               and duration(nodes[key]) >= min_wait_ns for key in seen):
            category = "upstream_wait_chain"
        elif long_wait and any(nodes[e["src"]].get("profiler_task_kind") == "rdma" for e in sync):
            category = "rdma_completion_unmeasured"
        wait.update(classification=category, long_wait=int(long_wait),
            candidate_ids=";".join(c["id"] for c, _, _ in related),
            candidate_ranks=";".join(str(c["user_rank"]) for c, _, _ in related),
            candidate_phases=";".join(c["phase"] for c, _, _ in related),
            candidate_graph_ids=";".join(c["graph_id"] for c, _, _ in related),
            evidence_path_edge_ids=";".join(dict.fromkeys(e for _, point, _ in related for e in paths[point])),
            attribution=";".join(dict.fromkeys(link for _, _, link in related)),
            traversal_truncated=int(position < len(queue) and len(seen) >= 4096))
    grouped = defaultdict(list)
    for row in rows:
        grouped[(row.get("_operation_scope", ""), row["_node_id"], row["_user_rank"],
                 row.get("algorithm", ""), row.get("phase", ""))].append(row)
    summaries = []
    for key, group in sorted(grouped.items()):
        local_waits = [r for r in group if r.get("profiler_task_kind") == "notify_wait"]
        payload = [r for r in group if r.get("profiler_task_kind") in ("sdma", "reduce_inline")]
        summaries.append(dict(zip(("operation_scope", "node_id", "user_rank", "algorithm", "phase"), key),
            task_count=len(group), wait_count=len(local_waits),
            wait_sum_ns=sum(duration(r) for r in local_waits),
            wait_union_ns=union_ns((ns(r, "start"), ns(r, "stop")) for r in local_waits),
            sdma_reduce_sum_ns=sum(duration(r) for r in payload),
            sdma_reduce_union_ns=union_ns((ns(r, "start"), ns(r, "stop")) for r in payload)))
    return dict(schema_version=1, waits=waits, candidates=candidates, summaries=summaries,
        limits=["Node clocks uncalibrated; no cross-node time subtraction or global critical path.",
                "CPU build spans are sparse (>=1ms), can overlap, and are not summed as hardware time.",
                "Candidate attribution is correlation where explicitly marked; RDMA completion is unmeasured."])


def export_analysis(result, directory):
    directory = Path(directory)
    (directory / "diagnosis.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    for key in ("waits", "candidates", "summaries"):
        values = result[key]
        fields = list(values[0]) if values else (["id", "graph_id", "node_id", "user_rank",
            "operation_scope", "algorithm", "phase", "step", "duration_ns", "baseline_median_ns",
            "category", "evidence"] if key == "candidates" else [])
        write_csv(str(directory / ("diagnosis_" + key + ".csv")), fields, values)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("artifact_dir", type=Path)
    parser.add_argument("--baseline-dir", type=Path)
    parser.add_argument("--min-wait-ms", type=Decimal, default=Decimal(1))
    parser.add_argument("--min-slow-ms", type=Decimal, default=Decimal(5))
    args = parser.parse_args()
    if not all(value.is_finite() and value > 0 for value in (args.min_wait_ms, args.min_slow_ms)):
        parser.error("wait/slow thresholds must be positive finite milliseconds")
    directory = args.artifact_dir
    rows = graph.read_graph_artifact_nodes(directory / "dep_graph_nodes.csv")
    edges = graph.read_graph_artifact_edges(directory / "dep_graph_edges.csv")
    issues = read_csv(directory / "dep_graph_notify_ambiguities.csv")
    spans = [row for path in sorted(directory.glob("node*/build_spans.csv")) for row in read_csv(path)]
    baseline = graph.read_graph_artifact_nodes(args.baseline_dir / "dep_graph_nodes.csv") if args.baseline_dir else []
    result = analyze(rows, edges, issues, spans, baseline,
                     int(args.min_wait_ms * 1000000), int(args.min_slow_ms * 1000000))
    export_analysis(result, directory)
    print("waits={} candidates={} unresolved={}".format(len(result["waits"]), len(result["candidates"]),
          sum(w["status"] != "paired" for w in result["waits"])))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
