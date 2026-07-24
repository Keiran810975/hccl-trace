#!/usr/bin/env python3
"""Quality gate for execution and resource dependency graph artifacts."""

from __future__ import annotations

import argparse
import csv
import os
import sys
from pathlib import Path
from typing import Dict

if __package__ in (None, ""):
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from diagnosis.schema import write_csv
    from diagnosis.visualize_dependency_graph import read_graph_artifact_edges
else:
    from .schema import write_csv
    from .visualize_dependency_graph import read_graph_artifact_edges


FORBIDDEN_EDGE_KINDS = frozenset({
    "ffts_physical_stream_order",
    "notify_sync_inferred",
    "peer_signal_semantic",
    "peer_payload_semantic",
    "resource_payload_semantic",
})
HARD_ZERO_METRICS = (
    "duplicate_node_ids",
    "duplicate_edge_ids",
    "missing_edge_sources",
    "missing_edge_destinations",
    "self_loop_edges",
    "cycle_residual_nodes",
)


def read_summary(path: Path) -> Dict[str, int]:
    summary: Dict[str, int] = {}
    with path.open("r", encoding="utf-8-sig", newline="") as source:
        for row in csv.DictReader(source):
            metric = str(row.get("metric", "")).strip()
            if not metric:
                continue
            value = str(row.get("value", "0")).strip()
            summary[metric] = int(float(value or "0"))
    return summary


def _edge_kind_counts(path: Path) -> Dict[str, int]:
    counts: Dict[str, int] = {}
    for edge in read_graph_artifact_edges(path):
        kind = str(edge.get("kind", ""))
        counts[kind] = counts.get(kind, 0) + 1
    return counts


def validate_dependency_artifacts(
    execution_summary_path: Path,
    execution_edges_path: Path,
    resource_summary_path: Path,
    resource_edges_path: Path,
    max_boundary_nodes: int | None = None,
    golden_summary_path: Path | None = None,
):
    execution = read_summary(execution_summary_path)
    resource = read_summary(resource_summary_path)
    execution_kinds = _edge_kind_counts(execution_edges_path)
    resource_kinds = _edge_kind_counts(resource_edges_path)
    stats: Dict[str, int] = {}
    failures = []
    for graph_name, summary in (
        ("execution", execution),
        ("resource", resource),
    ):
        for metric, value in summary.items():
            stats["{}_{}".format(graph_name, metric)] = value
        for metric in HARD_ZERO_METRICS:
            value = summary.get(metric, 0)
            if value:
                failures.append(
                    "{}_{}={}".format(graph_name, metric, value)
                )

    for status in ("ambiguous", "incomplete", "conflict"):
        value = execution.get("notify_relation_{}".format(status), 0)
        stats["notify_relation_{}".format(status)] = value
        if value:
            failures.append("notify_relation_{}={}".format(status, value))
    contraction_ambiguities = resource.get("contraction_ambiguities", 0)
    stats["resource_contraction_ambiguities"] = contraction_ambiguities
    if contraction_ambiguities:
        failures.append(
            "resource_contraction_ambiguities={}".format(
                contraction_ambiguities
            )
        )

    boundary_nodes = resource.get("boundary_nodes", 0)
    stats["resource_boundary_nodes"] = boundary_nodes
    if (
        max_boundary_nodes is not None
        and boundary_nodes > max_boundary_nodes
    ):
        failures.append(
            "resource_boundary_nodes={} exceeds {}".format(
                boundary_nodes, max_boundary_nodes
            )
        )

    stats["execution_stream_edges"] = sum(
        execution_kinds.get(kind, 0)
        for kind in (
            "direct_stream_order_observed",
            "ffts_logical_stream_order",
        )
    )
    stats["execution_sync_edges"] = sum(
        execution_kinds.get(kind, 0)
        for kind in (
            "direct_notify_sync_exact",
            "local_notify_sync_exact",
            "ffts_notify_sync_observed",
        )
    )
    stats["execution_payload_edges"] = execution_kinds.get(
        "peer_payload_semantic", 0
    )
    stats["resource_order_edges"] = sum(
        count
        for kind, count in resource_kinds.items()
        if kind.startswith("resource_") and "order" in kind
    )
    stats["resource_sync_edges"] = sum(
        count
        for kind, count in resource_kinds.items()
        if kind.startswith("resource_") and "notify_sync" in kind
    )
    stats["resource_payload_edges"] = resource_kinds.get(
        "resource_payload_semantic", 0
    )

    forbidden_count = 0
    time_inferred_count = 0
    ffts_pseudo_count = 0
    for kind_counts in (execution_kinds, resource_kinds):
        for kind, count in kind_counts.items():
            if kind in FORBIDDEN_EDGE_KINDS:
                forbidden_count += count
            if "time_inferred" in kind:
                time_inferred_count += count
            if kind == "ffts_physical_stream_order":
                ffts_pseudo_count += count
    stats["forbidden_edge_count"] = forbidden_count
    stats["ffts_pseudo_order_edges"] = ffts_pseudo_count
    stats["default_time_inferred_edges"] = time_inferred_count
    if forbidden_count:
        failures.append("forbidden_edge_count={}".format(forbidden_count))
    if time_inferred_count:
        failures.append(
            "default_time_inferred_edges={}".format(time_inferred_count)
        )

    if golden_summary_path is not None:
        golden = read_summary(golden_summary_path)
        mismatches = []
        for metric, expected in golden.items():
            actual = stats.get(metric)
            if actual != expected:
                mismatches.append(
                    "{}: expected {}, actual {}".format(
                        metric,
                        expected,
                        "missing" if actual is None else actual,
                    )
                )
        stats["golden_mismatch_count"] = len(mismatches)
        failures.extend("golden {}".format(item) for item in mismatches)
    else:
        stats["golden_mismatch_count"] = 0
    return not failures, stats, failures


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate execution/resource dependency graph artifacts."
    )
    parser.add_argument("artifact_prefix", type=Path)
    parser.add_argument("--max-boundary-nodes", type=int)
    parser.add_argument("--golden-summary", type=Path)
    parser.add_argument("--summary-output", type=Path)
    args = parser.parse_args()
    prefix = args.artifact_prefix
    ok, stats, failures = validate_dependency_artifacts(
        prefix.with_name(prefix.name + "_summary.csv"),
        prefix.with_name(prefix.name + "_edges.csv"),
        prefix.with_name(prefix.name + "_resource_summary.csv"),
        prefix.with_name(prefix.name + "_resource_edges.csv"),
        args.max_boundary_nodes,
        args.golden_summary,
    )
    for metric in sorted(stats):
        print("{}={}".format(metric, stats[metric]))
    if args.summary_output is not None:
        write_csv(
            str(args.summary_output),
            ["metric", "value"],
            (
                {"metric": metric, "value": stats[metric]}
                for metric in sorted(stats)
            ),
        )
        print("summary_csv={}".format(args.summary_output))
    if failures:
        for failure in failures:
            print("dependency graph validation failed: {}".format(failure))
    else:
        print("dependency graph validation passed")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
