#!/usr/bin/env python3
"""Contract execution dependencies into a resource-task dependency graph."""

from __future__ import annotations

import argparse
import os
import sys
from collections import Counter, defaultdict
from decimal import Decimal
from pathlib import Path
from typing import Dict, Iterable, List

if __package__ in (None, ""):
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from diagnosis.dependency_model import (
        DependencyEdgeIdentity,
        GRAPH_SCHEMA_VERSION,
        stable_id,
    )
    from diagnosis.schema import MERGED_FIELDS, normalize_task_kind, write_csv
    from diagnosis import visualize_dependency_graph as execution
else:
    from .dependency_model import (
        DependencyEdgeIdentity,
        GRAPH_SCHEMA_VERSION,
        stable_id,
    )
    from .schema import MERGED_FIELDS, normalize_task_kind, write_csv
    from . import visualize_dependency_graph as execution


RESOURCE_TASK_KINDS = frozenset({
    "sdma",
    "rdma",
    "reduce_inline",
    "reduce_tbe",
})
ORDER_EDGE_KINDS = frozenset({
    "direct_stream_order_observed",
    "ffts_logical_stream_order",
})
SYNC_EDGE_KIND_MAP = {
    "direct_notify_sync_exact": "resource_notify_sync_exact",
    "local_notify_sync_exact": "resource_local_notify_sync_exact",
    "ffts_notify_sync_observed": "resource_notify_sync_observed",
    "cross_node_notify_sync_observed": "resource_cross_node_notify_sync_observed",
    "same_node_rdma_notify_sync_observed": "resource_same_node_rdma_notify_sync_observed",
}
RESOURCE_EDGE_COLOR = {
    "resource_stream_order_observed": "#444444",
    "resource_ffts_order_semantic": "#5c6bc0",
    "resource_order_semantic": "#5c6bc0",
    "resource_local_notify_sync_observed": "#d9488b",
    "resource_local_notify_sync_semantic": "#d9488b",
    "resource_notify_sync_semantic": "#2b8a3e",
    "resource_notify_sync_observed": "#2b8a3e",
    "resource_notify_sync_exact": "#7b3fb3",
    "resource_local_notify_sync_exact": "#d9488b",
    "resource_cross_node_notify_sync_observed": "#007c91",
    "resource_cross_node_notify_sync_semantic": "#007c91",
    "resource_same_node_rdma_notify_sync_observed": "#b05b00",
    "resource_same_node_rdma_notify_sync_semantic": "#b05b00",
}

RESOURCE_NODE_FIELDS = [
    "graph_schema_version",
    "graph_id",
    "node_kind",
    "boundary_side",
    "boundary_reason",
    "boundary_relation_id",
] + list(MERGED_FIELDS)

RESOURCE_EDGE_FIELDS = [
    "graph_schema_version",
    "edge_id",
    "kind",
    "src",
    "dst",
    "src_device",
    "dst_device",
    "src_stream",
    "dst_stream",
    "src_task",
    "dst_task",
    "reason",
    "evidence",
    "confidence",
    "relation_id",
    "source_execution_edge_ids",
    "control_graph_ids",
    "record_graph_id",
    "wait_graph_id",
    "semantic_status",
    "signal_kind",
    "phase",
    "step",
    "slice",
    "weight_ns",
    "wait_span_ns",
    "remote_block_ns",
    "post_signal_ns",
    "handoff_gap_ns",
    "timing_status",
]

RESOURCE_AMBIGUITY_FIELDS = [
    "graph_schema_version",
    "source_edge_id",
    "relation_id",
    "kind",
    "status",
    "upstream_resource_count",
    "downstream_resource_count",
    "upstream_resource_ids",
    "downstream_resource_ids",
    "control_graph_ids",
    "reason",
]


def _task_kind(row: dict) -> str:
    return normalize_task_kind(
        row.get("profiler_task_kind") or row.get("task_kind", "")
    )


def is_resource_task(row: dict) -> bool:
    return _task_kind(row) in RESOURCE_TASK_KINDS


def _ordered_unique(values: Iterable[str]) -> List[str]:
    return sorted({str(value) for value in values if str(value)})


def _decimal_ns(value: Decimal) -> str:
    nanoseconds = value * Decimal(1000)
    integral = nanoseconds.to_integral_value()
    if nanoseconds == integral:
        return str(int(integral))
    return format(nanoseconds.normalize(), "f")


def _frontiers(
    start_id: str,
    adjacency: Dict[str, List[dict]],
    rows_by_id: Dict[str, dict],
    reverse: bool,
    stop_at_start: bool = True,
) -> Dict[str, dict]:
    """Return first reachable resource tasks and every retained control path."""
    if (
        stop_at_start
        and start_id in rows_by_id
        and is_resource_task(rows_by_id[start_id])
    ):
        return {
            start_id: {
                "edge_ids": set(),
                "control_ids": set(),
            }
        }
    result: Dict[str, dict] = {}
    stack = [(start_id, tuple(), tuple())]
    visited = set()
    while stack:
        node_id, edge_ids, control_ids = stack.pop()
        state = (node_id, edge_ids)
        if state in visited:
            continue
        visited.add(state)
        row = rows_by_id.get(node_id)
        next_controls = control_ids
        if row is not None and not is_resource_task(row):
            next_controls = control_ids + (node_id,)
        for edge in adjacency.get(node_id, []):
            successor = edge["src"] if reverse else edge["dst"]
            next_edge_ids = (
                (edge["edge_id"],) + edge_ids
                if reverse
                else edge_ids + (edge["edge_id"],)
            )
            successor_row = rows_by_id.get(successor)
            if successor_row is None:
                continue
            if is_resource_task(successor_row):
                item = result.setdefault(
                    successor,
                    {"edge_ids": set(), "control_ids": set()},
                )
                item["edge_ids"].update(next_edge_ids)
                item["control_ids"].update(next_controls)
            else:
                stack.append((successor, next_edge_ids, next_controls))
    return result


def _boundary_row(
    source_edge: dict,
    endpoint_row: dict,
    side: str,
) -> dict:
    relation_id = str(source_edge.get("relation_id", ""))
    graph_id = stable_id(
        "b",
        (
            GRAPH_SCHEMA_VERSION,
            source_edge.get("edge_id", ""),
            relation_id,
            side,
        ),
    )
    timestamp = (
        execution.execution_time_order_value(endpoint_row, "start")
        if side == "upstream"
        else execution.execution_time_order_value(endpoint_row, "stop")
    )
    item = {
        key: "" for key in MERGED_FIELDS
    }
    item.update({
        "match_status": "boundary",
        "node_id": endpoint_row.get("_node_id", ""),
        "device_id": endpoint_row.get("_device_id", -1),
        "stream_id": endpoint_row.get("_stream_id", -1),
        "task_id": -1,
        "task_kind": "boundary",
        "profiler_task_kind": "boundary",
        "profiler_stream_id": endpoint_row.get("_stream_id", -1),
        "profiler_task_id": -1,
        "task_start": format(timestamp, "f"),
        "task_stop": format(timestamp, "f"),
        "duration": "0",
        "event_name": "{}_resource_boundary".format(side),
        "subtask_id": -1,
        "connection_id": -1,
    })
    item.update({
        "_source_row": -1,
        "_graph_id": graph_id,
        "_node_id": item["node_id"],
        "_device_id": execution.to_int(item["device_id"]),
        "_user_rank": -1,
        "_rank": execution.to_int(item["device_id"]),
        "_stream_id": execution.to_int(item["stream_id"]),
        "_task_id": -1,
        "_subtask_id": -1,
        "_connection_id": -1,
        "_operation_scope": "",
        "_operation_scope_status": "",
        "_start": float(timestamp),
        "_stop": float(timestamp),
        "_start_order": timestamp,
        "_stop_order": timestamp,
        "_duration": 0.0,
        "_node_kind": "boundary",
        "_boundary_side": side,
        "_boundary_reason": "no unique reachable resource endpoint",
        "_boundary_relation_id": relation_id,
    })
    return item


def _timing_metrics(
    execution_edge: dict,
    rows_by_id: Dict[str, dict],
    downstream_row: dict | None,
) -> dict:
    if execution_edge["kind"] not in SYNC_EDGE_KIND_MAP:
        return {
            "weight_ns": "",
            "wait_span_ns": "",
            "remote_block_ns": "",
            "post_signal_ns": "",
            "handoff_gap_ns": "",
            "timing_status": "not_notify_sync",
        }
    record = rows_by_id[execution_edge["src"]]
    wait = rows_by_id[execution_edge["dst"]]
    wait_start = execution.execution_time_order_value(wait, "start")
    wait_stop = execution.execution_time_order_value(wait, "stop")
    wait_span = max(Decimal(0), wait_stop - wait_start)
    metrics = {
        "weight_ns": _decimal_ns(wait_span),
        "wait_span_ns": _decimal_ns(wait_span),
        "remote_block_ns": "",
        "post_signal_ns": "",
        "handoff_gap_ns": "",
        "timing_status": "cross_node_uncalibrated",
    }
    if execution_edge["kind"] == "same_node_rdma_notify_sync_observed":
        # Doorbell completion is not remote data completion. Keep local wait
        # duration without presenting a network/compute delay decomposition.
        metrics["timing_status"] = "same_node_rdma_completion_unmeasured"
    elif record.get("_node_id") == wait.get("_node_id"):
        record_stop = execution.execution_time_order_value(record, "stop")
        remote_block = min(
            wait_span,
            max(Decimal(0), record_stop - wait_start),
        )
        metrics["remote_block_ns"] = _decimal_ns(remote_block)
        metrics["post_signal_ns"] = _decimal_ns(wait_span - remote_block)
        metrics["timing_status"] = "same_node_observed"
    if (
        downstream_row is not None
        and downstream_row.get("_node_kind", "resource") == "resource"
        and downstream_row.get("_node_id") == wait.get("_node_id")
    ):
        handoff = max(
            Decimal(0),
            execution.execution_time_order_value(downstream_row, "start")
            - wait_stop,
        )
        metrics["handoff_gap_ns"] = _decimal_ns(handoff)
    return metrics


def build_resource_graph(
    rows: List[dict],
    execution_edges: List[dict],
):
    """Build resource nodes/edges without guessing ambiguous contractions."""
    rows_by_id = {row["_graph_id"]: row for row in rows}
    resource_nodes = {
        row["_graph_id"]: dict(
            row,
            _node_kind="resource",
            _boundary_side="",
            _boundary_reason="",
            _boundary_relation_id="",
        )
        for row in rows
        if is_resource_task(row)
    }
    forward: Dict[str, List[dict]] = defaultdict(list)
    reverse: Dict[str, List[dict]] = defaultdict(list)
    for edge in execution_edges:
        if edge["kind"] in ORDER_EDGE_KINDS:
            forward[edge["src"]].append(edge)
            reverse[edge["dst"]].append(edge)
    for values in forward.values():
        values.sort(key=lambda item: item["edge_id"])
    for values in reverse.values():
        values.sort(key=lambda item: item["edge_id"])

    resource_edges: List[dict] = []
    ambiguities: List[dict] = []
    edge_identities = {}
    endpoint_identities = {}

    def add_edge(
        kind: str,
        src_id: str,
        dst_id: str,
        relation_id: str,
        source_edge_ids: Iterable[str],
        control_ids: Iterable[str],
        reason: str,
        evidence: str,
        confidence: str,
        source_execution_edge: dict | None = None,
    ) -> None:
        if src_id == dst_id:
            return
        identity = DependencyEdgeIdentity(kind, src_id, dst_id, relation_id)
        endpoint_key = (kind, src_id, dst_id, relation_id)
        existing = endpoint_identities.get(endpoint_key)
        if existing is not None:
            if existing != identity:
                raise ValueError(
                    "conflicting resource relations for {} {} -> {}".format(
                        kind, src_id, dst_id
                    )
                )
            return
        collision = edge_identities.get(identity.stable_id)
        if collision is not None and collision != identity:
            raise ValueError(
                "resource dependency edge ID collision {}".format(
                    identity.stable_id
                )
            )
        endpoint_identities[endpoint_key] = identity
        edge_identities[identity.stable_id] = identity
        src = resource_nodes[src_id]
        dst = resource_nodes[dst_id]
        source = source_execution_edge or {}
        metrics = _timing_metrics(
            source,
            rows_by_id,
            dst,
        ) if source else {
            "weight_ns": "",
            "wait_span_ns": "",
            "remote_block_ns": "",
            "post_signal_ns": "",
            "handoff_gap_ns": "",
            "timing_status": "not_notify_sync",
        }
        resource_edges.append({
            "graph_schema_version": GRAPH_SCHEMA_VERSION,
            "edge_id": identity.stable_id,
            "kind": kind,
            "src": src_id,
            "dst": dst_id,
            "src_device": src.get("_device_id", -1),
            "dst_device": dst.get("_device_id", -1),
            "src_stream": src.get("_stream_id", -1),
            "dst_stream": dst.get("_stream_id", -1),
            "src_task": src.get("_task_id", -1),
            "dst_task": dst.get("_task_id", -1),
            "reason": reason,
            "evidence": evidence,
            "confidence": confidence,
            "relation_id": relation_id,
            "source_execution_edge_ids": ";".join(
                _ordered_unique(source_edge_ids)
            ),
            "control_graph_ids": ";".join(_ordered_unique(control_ids)),
            "record_graph_id": (
                source.get("src", "")
                if source.get("kind") in SYNC_EDGE_KIND_MAP
                else ""
            ),
            "wait_graph_id": (
                source.get("dst", "")
                if source.get("kind") in SYNC_EDGE_KIND_MAP
                else ""
            ),
            "semantic_status": source.get("semantic_status", ""),
            "signal_kind": source.get("signal_kind", ""),
            "phase": source.get("phase", ""),
            "step": source.get("step", -1),
            "slice": source.get("slice", -1),
            **metrics,
        })

    # Contract every maximal local order path between two resource tasks.
    execution_edges_by_id = {
        edge["edge_id"]: edge for edge in execution_edges
    }
    local_paths = defaultdict(
        lambda: {"edge_ids": set(), "control_ids": set(), "kinds": set()}
    )
    for src_id in sorted(resource_nodes):
        frontiers = _frontiers(
            src_id,
            forward,
            rows_by_id,
            reverse=False,
            stop_at_start=False,
        )
        for dst_id, path in frontiers.items():
            if dst_id == src_id:
                continue
            item = local_paths[(src_id, dst_id)]
            item["edge_ids"].update(path["edge_ids"])
            item["control_ids"].update(path["control_ids"])
            for edge_id in path["edge_ids"]:
                item["kinds"].add(execution_edges_by_id[edge_id]["kind"])
    def weakest(edge_ids):
        return min((execution_edges_by_id[e]["confidence"] for e in edge_ids),
                   key={"semantic": 0, "observed": 1, "exact": 2}.__getitem__)

    for (src_id, dst_id), path in sorted(local_paths.items()):
        if path["kinds"] == {"direct_stream_order_observed"}:
            kind = "resource_stream_order_observed"
        elif path["kinds"] == {"ffts_logical_stream_order"}:
            kind = "resource_ffts_order_observed"
        else:
            kind = "resource_order_observed"
        confidence = weakest(path["edge_ids"])
        kind = kind.rsplit("_", 1)[0] + "_" + confidence
        relation_id = stable_id("rp", _ordered_unique(path["edge_ids"]))
        add_edge(
            kind,
            src_id,
            dst_id,
            relation_id,
            path["edge_ids"],
            path["control_ids"],
            "maximal execution-order path contracted through control tasks",
            "execution_order_transitive_contraction",
            confidence,
        )

    contract_kinds = set(SYNC_EDGE_KIND_MAP)
    for source_edge in sorted(execution_edges, key=lambda item: item["edge_id"]):
        if source_edge["kind"] not in contract_kinds:
            continue
        upstream = _frontiers(
            source_edge["src"], reverse, rows_by_id, reverse=True
        )
        downstream = _frontiers(
            source_edge["dst"], forward, rows_by_id, reverse=False
        )
        control_ids = set()
        for item in list(upstream.values()) + list(downstream.values()):
            control_ids.update(item["control_ids"])
        if len(upstream) > 1 or len(downstream) > 1:
            ambiguities.append({
                "graph_schema_version": GRAPH_SCHEMA_VERSION,
                "source_edge_id": source_edge["edge_id"],
                "relation_id": source_edge.get("relation_id", ""),
                "kind": source_edge["kind"],
                "status": "ambiguous",
                "upstream_resource_count": len(upstream),
                "downstream_resource_count": len(downstream),
                "upstream_resource_ids": ";".join(sorted(upstream)),
                "downstream_resource_ids": ";".join(sorted(downstream)),
                "control_graph_ids": ";".join(sorted(control_ids)),
                "reason": "multiple reachable resource frontiers; no cross product emitted",
            })
            continue
        if not upstream:
            endpoint = rows_by_id[source_edge["src"]]
            boundary = _boundary_row(source_edge, endpoint, "upstream")
            resource_nodes[boundary["_graph_id"]] = boundary
            upstream = {
                boundary["_graph_id"]: {
                    "edge_ids": set(),
                    "control_ids": {source_edge["src"]},
                }
            }
        if not downstream:
            endpoint = rows_by_id[source_edge["dst"]]
            boundary = _boundary_row(source_edge, endpoint, "downstream")
            resource_nodes[boundary["_graph_id"]] = boundary
            downstream = {
                boundary["_graph_id"]: {
                    "edge_ids": set(),
                    "control_ids": {source_edge["dst"]},
                }
            }
        src_id, upstream_path = next(iter(upstream.items()))
        dst_id, downstream_path = next(iter(downstream.items()))
        source_edge_ids = (
            set(upstream_path["edge_ids"])
            | {source_edge["edge_id"]}
            | set(downstream_path["edge_ids"])
        )
        control_ids = (
            set(upstream_path["control_ids"])
            | set(downstream_path["control_ids"])
        )
        kind = SYNC_EDGE_KIND_MAP[source_edge["kind"]]
        confidence = weakest(source_edge_ids)
        kind = kind.rsplit("_", 1)[0] + "_" + confidence
        reason = "Notify record/wait control chain contracted between resource tasks"
        add_edge(
            kind,
            src_id,
            dst_id,
            source_edge.get("relation_id", "") or source_edge["edge_id"],
            source_edge_ids,
            control_ids,
            reason,
            source_edge.get("evidence", ""),
            confidence,
            source_edge,
        )
    return (
        sorted(resource_nodes.values(), key=lambda row: row["_graph_id"]),
        sorted(resource_edges, key=lambda edge: edge["edge_id"]),
        sorted(
            ambiguities,
            key=lambda row: (
                row["source_edge_id"],
                row["upstream_resource_ids"],
                row["downstream_resource_ids"],
            ),
        ),
    )


def analyze_resource_graph(
    execution_rows: List[dict],
    resource_rows: List[dict],
    resource_edges: List[dict],
    ambiguities: List[dict],
) -> Counter:
    stats = Counter(execution.analyze_execution_graph(resource_rows, resource_edges))
    stats["resource_task_nodes"] = sum(
        row.get("_node_kind", "resource") == "resource"
        for row in resource_rows
    )
    stats["boundary_nodes"] = sum(
        row.get("_node_kind") == "boundary" for row in resource_rows
    )
    stats["excluded_control_nodes"] = (
        len(execution_rows) - stats["resource_task_nodes"]
    )
    stats["contraction_ambiguities"] = len(ambiguities)
    for kind, count in Counter(
        edge["kind"] for edge in resource_edges
    ).items():
        stats["edge_kind_{}".format(kind)] = count
    for status, count in Counter(
        edge.get("timing_status", "") for edge in resource_edges
    ).items():
        stats["timing_status_{}".format(status)] = count
    return stats


def export_resource_dependency_tables(
    execution_nodes_csv: Path,
    execution_edges_csv: Path,
    prefix: Path,
):
    execution_rows = execution.read_graph_artifact_nodes(execution_nodes_csv)
    execution_edges = execution.read_graph_artifact_edges(execution_edges_csv)
    execution_stats = execution.analyze_execution_graph(
        execution_rows, execution_edges
    )
    execution._assert_execution_graph_integrity(execution_stats)
    if execution_stats["cycle_residual_nodes"]:
        raise ValueError(
            "cannot contract cyclic execution graph: cycle_residual_nodes={}"
            .format(execution_stats["cycle_residual_nodes"])
        )
    resource_rows, resource_edges, ambiguities = build_resource_graph(
        execution_rows, execution_edges
    )
    stats = analyze_resource_graph(
        execution_rows, resource_rows, resource_edges, ambiguities
    )
    execution._assert_execution_graph_integrity(stats)
    nodes_path = prefix.with_name(prefix.name + "_resource_nodes.csv")
    edges_path = prefix.with_name(prefix.name + "_resource_edges.csv")
    ambiguities_path = prefix.with_name(prefix.name + "_resource_ambiguities.csv")
    summary_path = prefix.with_name(prefix.name + "_resource_summary.csv")
    node_rows = []
    for row in resource_rows:
        item = {
            "graph_schema_version": GRAPH_SCHEMA_VERSION,
            "graph_id": row["_graph_id"],
            "node_kind": row.get("_node_kind", "resource"),
            "boundary_side": row.get("_boundary_side", ""),
            "boundary_reason": row.get("_boundary_reason", ""),
            "boundary_relation_id": row.get("_boundary_relation_id", ""),
        }
        item.update({key: row.get(key, "") for key in MERGED_FIELDS})
        node_rows.append(item)
    write_csv(str(nodes_path), RESOURCE_NODE_FIELDS, node_rows)
    write_csv(str(edges_path), RESOURCE_EDGE_FIELDS, resource_edges)
    write_csv(str(ambiguities_path), RESOURCE_AMBIGUITY_FIELDS, ambiguities)
    write_csv(
        str(summary_path),
        execution.GRAPH_SUMMARY_FIELDS,
        (
            {"metric": metric, "value": stats[metric]}
            for metric in sorted(stats)
        ),
    )
    return nodes_path, edges_path, ambiguities_path, summary_path, stats


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Contract an execution dependency artifact into resource tasks."
    )
    parser.add_argument("execution_nodes_csv", type=Path)
    parser.add_argument("execution_edges_csv", type=Path)
    parser.add_argument("-o", "--output-prefix", type=Path, required=True)
    args = parser.parse_args()
    paths = export_resource_dependency_tables(
        args.execution_nodes_csv,
        args.execution_edges_csv,
        args.output_prefix,
    )
    for label, path in zip(
        ("resource_nodes_csv", "resource_edges_csv",
         "resource_ambiguities_csv", "resource_summary_csv"),
        paths[:4],
    ):
        print("{}={}".format(label, path))
    for metric in (
        "resource_task_nodes",
        "boundary_nodes",
        "edge_count",
        "contraction_ambiguities",
        "cycle_residual_nodes",
    ):
        print("{}={}".format(metric, paths[4][metric]))
    return 1 if paths[4]["contraction_ambiguities"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
