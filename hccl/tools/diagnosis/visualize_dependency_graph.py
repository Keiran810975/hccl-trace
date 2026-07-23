#!/usr/bin/env python3
"""Build evidence-labelled physical dependencies from merged msprof executions."""

from __future__ import annotations

import argparse
import csv
import math
import os
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Dict, List, Tuple

if __package__ in (None, ""):
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from diagnosis.schema import write_csv
else:
    from .schema import write_csv


EDGE_COLOR = {
    "stream_order_observed": "#444444",
    "notify_sync_observed": "#2b8a3e",
    "notify_sync_inferred": "#d98000",
    "peer_signal_semantic": "#7b3fb3",
    "peer_payload_semantic": "#1f77b4",
}
PHYSICAL_EDGE_KINDS = tuple(EDGE_COLOR)


def to_int(value: object, default: int = -1) -> int:
    try:
        text = str(value).strip()
        return int(float(text)) if text else default
    except (TypeError, ValueError):
        return default


def to_float(value: object, default: float = math.nan) -> float:
    try:
        text = str(value).strip()
        return float(text) if text else default
    except (TypeError, ValueError):
        return default


def phase_group(phase: str) -> str:
    if phase.startswith("reduce_scatter"):
        return "reduce_scatter"
    if phase.startswith("allgather"):
        return "allgather"
    return phase or "hardware"


def read_execution_rows(path: Path) -> List[dict]:
    """Read every timed profiler execution exactly once, including profiler-only rows."""
    rows: List[dict] = []
    with path.open("r", encoding="utf-8-sig", newline="") as source:
        for index, row in enumerate(csv.DictReader(source)):
            if row.get("match_status") not in ("matched", "profiler_only"):
                continue
            start = to_float(row.get("task_start"))
            stop = to_float(row.get("task_stop"))
            if math.isnan(start) or math.isnan(stop):
                continue
            item = dict(row)
            item.update({
                "_source_row": index,
                "_graph_id": f"p{index}",
                "_node_id": row.get("node_id", ""),
                "_device_id": to_int(row.get("device_id")),
                "_user_rank": to_int(row.get("user_rank")),
                "_rank": to_int(row.get("device_id")),
                "_rank_size": to_int(row.get("rank_size")),
                "_stream_id": to_int(row.get("profiler_stream_id") or row.get("stream_id")),
                "_task_id": to_int(row.get("profiler_task_id") or row.get("task_id")),
                "_subtask_id": to_int(row.get("subtask_id")),
                "_connection_id": to_int(row.get("connection_id")),
                "_peer_rank": to_int(row.get("peer_rank")),
                "_notify_id": to_int(row.get("notify_id")),
                "_step": to_int(row.get("step")),
                "_slice": to_int(row.get("slice")),
                "_start": min(start, stop),
                "_stop": max(start, stop),
                "_duration": abs(stop - start),
                "_phase_group": phase_group(row.get("phase", "")),
            })
            rows.append(item)
    rows.sort(key=execution_sort_key)
    return rows


def execution_sort_key(row: dict):
    return (
        row["_node_id"], row["_device_id"], row["_stream_id"], row["_start"],
        row["_task_id"], row["_subtask_id"], row["_source_row"],
    )


def build_execution_edges(rows: List[dict]) -> List[dict]:
    """Build stream, local synchronization, and peer semantic dependencies."""
    edges: List[dict] = []
    seen = set()

    def add(kind: str, src: dict, dst: dict, reason: str, evidence: str, confidence: str) -> None:
        if not src or not dst or src is dst:
            return
        key = (kind, src["_graph_id"], dst["_graph_id"])
        if key in seen:
            return
        seen.add(key)
        edges.append({
            "edge_id": f"e{len(edges)}",
            "kind": kind,
            "src": src["_graph_id"],
            "dst": dst["_graph_id"],
            "src_device": src["_device_id"],
            "dst_device": dst["_device_id"],
            "src_stream": src["_stream_id"],
            "dst_stream": dst["_stream_id"],
            "src_task": src["_task_id"],
            "dst_task": dst["_task_id"],
            "reason": reason,
            "evidence": evidence,
            "confidence": confidence,
        })

    by_stream: Dict[Tuple[str, int, int], List[dict]] = defaultdict(list)
    for row in rows:
        by_stream[(row["_node_id"], row["_device_id"], row["_stream_id"])].append(row)
    for stream_rows in by_stream.values():
        ordered = sorted(stream_rows, key=execution_sort_key)
        for prev, cur in zip(ordered, ordered[1:]):
            add(
                "stream_order_observed", prev, cur,
                "adjacent executions on the same physical stream",
                "msprof_stream_order", "observed",
            )

    _add_notify_sync_edges(rows, add)
    _add_peer_semantic_edges(rows, add)
    return edges


def _add_notify_sync_edges(rows: List[dict], add) -> None:
    exact_used = set()
    by_notify: Dict[Tuple[str, int, int], List[dict]] = defaultdict(list)
    for row in rows:
        if row["_notify_id"] >= 0:
            by_notify[(row["_node_id"], row["_device_id"], row["_notify_id"])].append(row)
    for notify_rows in by_notify.values():
        records = sorted(
            (row for row in notify_rows if row.get("task_kind") == "notify_record"),
            key=lambda row: row["_start"],
        )
        waits = sorted(
            (row for row in notify_rows if row.get("task_kind") == "notify_wait"),
            key=lambda row: row["_start"],
        )
        if len(records) != len(waits):
            continue
        for record, wait in zip(records, waits):
            if record["_stream_id"] == wait["_stream_id"]:
                continue
            exact_used.update((record["_graph_id"], wait["_graph_id"]))
            add(
                "notify_sync_observed", record, wait,
                "same producer notify_id on record and wait tasks",
                "plog_notify_id", "observed",
            )

    groups: Dict[Tuple[str, int, int], List[dict]] = defaultdict(list)
    for row in rows:
        if row["_connection_id"] >= 0:
            groups[(row["_node_id"], row["_device_id"], row["_connection_id"])].append(row)
    for group_rows in groups.values():
        records = [row for row in group_rows if row.get("profiler_task_kind") == "notify_record"]
        waits = [row for row in group_rows if row.get("profiler_task_kind") == "notify_wait"]
        used = set()
        for wait in sorted(waits, key=lambda row: row["_stop"]):
            candidates = [
                record for record in records
                if record["_graph_id"] not in used and record["_graph_id"] not in exact_used
                and record["_stream_id"] != wait["_stream_id"]
                and record["_start"] <= wait["_stop"]
            ]
            if not candidates:
                continue
            if wait["_graph_id"] in exact_used:
                continue
            candidates.sort(key=lambda record: (wait["_stop"] - record["_start"], -record["_start"]))
            best = candidates[0]
            if len(candidates) > 1:
                first_gap = wait["_stop"] - best["_start"]
                second_gap = wait["_stop"] - candidates[1]["_start"]
                if abs(second_gap - first_gap) < 0.1:
                    continue
            used.add(best["_graph_id"])
            add(
                "notify_sync_inferred", best, wait,
                "nearest cross-stream notify record before wait completion within one connection",
                "event_type_connection_time", "inferred",
            )


def _add_peer_semantic_edges(rows: List[dict], add) -> None:
    receives: Dict[Tuple[int, int, str, int, int, str], List[dict]] = defaultdict(list)
    transmits: Dict[Tuple[int, int, str, int, int, str], List[dict]] = defaultdict(list)
    receive_kind = {
        "rx_ack_start": "ack",
        "rx_data_signal_start": "data_signal",
        "rx_payload_reduce_start": "payload",
        "rx_payload_copy_start": "payload",
    }
    for row in rows:
        kind = receive_kind.get(row.get("event", ""))
        if kind and row["_user_rank"] >= 0 and row["_peer_rank"] >= 0:
            key = (
                row["_peer_rank"], row["_user_rank"], kind, row["_step"], row["_slice"],
                row["_phase_group"],
            )
            receives[key].append(row)

    transmit_kind = {
        "tx_ack_start": "ack",
        "tx_data_signal_start": "data_signal",
        "tx_payload_start": "payload",
    }
    for src in rows:
        kind = transmit_kind.get(src.get("event", ""))
        if not kind or src["_user_rank"] < 0 or src["_peer_rank"] < 0:
            continue
        key = (
            src["_user_rank"], src["_peer_rank"], kind, src["_step"], src["_slice"],
            src["_phase_group"],
        )
        transmits[key].append(src)

    for key, senders in transmits.items():
        receivers = receives.get(key, [])
        if len(senders) != len(receivers):
            continue
        kind = key[2]
        senders.sort(key=lambda row: (row["_start"], row["_source_row"]))
        receivers.sort(key=lambda row: (row["_start"], row["_source_row"]))
        for src, dst in zip(senders, receivers):
            edge_kind = "peer_payload_semantic" if kind == "payload" else "peer_signal_semantic"
            add(
                edge_kind, src, dst,
                f"peer_rank semantic pair for {kind}, aligned by occurrence order",
                "semantic_peer_phase_step_slice_occurrence", "semantic",
            )


def export_dependency_tables(merged_csv: Path, prefix: Path) -> Tuple[Path, Path, Counter]:
    rows = read_execution_rows(merged_csv)
    edges = build_execution_edges(rows)
    nodes_path = prefix.with_name(prefix.name + "_nodes.csv")
    edges_path = prefix.with_name(prefix.name + "_edges.csv")
    node_fields = [key for key in rows[0] if not key.startswith("_")] if rows else ["graph_id"]
    node_fields = ["graph_id"] + node_fields
    node_rows = [dict({"graph_id": row["_graph_id"]}, **{key: row.get(key, "") for key in node_fields[1:]})
                 for row in rows]
    write_csv(str(nodes_path), node_fields, node_rows)
    write_csv(str(edges_path), list(edges[0]) if edges else ["edge_id"], edges)
    return nodes_path, edges_path, Counter(edge["kind"] for edge in edges)


def main() -> int:
    parser = argparse.ArgumentParser(description="Export evidence-labelled physical dependency tables.")
    parser.add_argument("merged_csv", type=Path)
    parser.add_argument("-o", "--output-prefix", type=Path)
    args = parser.parse_args()
    prefix = args.output_prefix or args.merged_csv.with_name(args.merged_csv.stem + "_dependency")
    nodes_path, edges_path, counts = export_dependency_tables(args.merged_csv, prefix)
    for kind in PHYSICAL_EDGE_KINDS:
        print(f"{kind}={counts[kind]}")
    print(f"nodes_csv={nodes_path}")
    print(f"edges_csv={edges_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
