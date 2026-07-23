#!/usr/bin/env python3
"""Build evidence-labelled physical dependencies from merged msprof executions."""

from __future__ import annotations

import argparse
import csv
import math
import os
import sys
from collections import Counter, defaultdict
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Dict, List, Tuple

if __package__ in (None, ""):
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from diagnosis.dependency_model import (
        ExecutionIdentity,
        GRAPH_SCHEMA_VERSION,
        NOTIFY_ENDPOINT_RULES,
        NOTIFY_RANK_DOMAIN_USER,
        NOTIFY_RELATION_AMBIGUOUS,
        NOTIFY_RELATION_INCOMPLETE,
        NOTIFY_RELATION_SINGLE,
        NOTIFY_ROLE_CONSUMER,
        NOTIFY_ROLE_PRODUCER,
        NOTIFY_SEQUENCE_FFTS_GRAPH,
        NotifyRelationIdentity,
    )
    from diagnosis.schema import write_csv
else:
    from .dependency_model import (
        ExecutionIdentity,
        GRAPH_SCHEMA_VERSION,
        NOTIFY_ENDPOINT_RULES,
        NOTIFY_RANK_DOMAIN_USER,
        NOTIFY_RELATION_AMBIGUOUS,
        NOTIFY_RELATION_INCOMPLETE,
        NOTIFY_RELATION_SINGLE,
        NOTIFY_ROLE_CONSUMER,
        NOTIFY_ROLE_PRODUCER,
        NOTIFY_SEQUENCE_FFTS_GRAPH,
        NotifyRelationIdentity,
    )
    from .schema import write_csv


EDGE_COLOR = {
    "direct_stream_order_observed": "#444444",
    "ffts_logical_stream_order": "#5c6bc0",
    "ffts_notify_sync_observed": "#2b8a3e",
    "peer_signal_semantic": "#7b3fb3",
    "peer_payload_semantic": "#1f77b4",
}
PHYSICAL_EDGE_KINDS = tuple(EDGE_COLOR)

NOTIFY_AMBIGUITY_FIELDS = [
    "graph_schema_version",
    "relation_id",
    "status",
    "missing_role",
    "missing_fields",
    "endpoint_count",
    "producer_count",
    "consumer_count",
    "node_id",
    "operation_scope",
    "rank_domain",
    "producer_rank",
    "consumer_rank",
    "signal_kind",
    "phase",
    "step",
    "slice",
    "notify_id",
    "sequence_kind",
    "sequence_value",
    "endpoint_graph_ids",
    "reason",
]


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


def to_decimal(value: object):
    try:
        text = str(value).strip()
        return Decimal(text) if text else None
    except (InvalidOperation, ValueError):
        return None


def execution_time_order_value(row: dict, name: str) -> Decimal:
    internal = "_{}_order".format(name)
    if internal in row:
        return row[internal]
    return Decimal(str(row["_{}".format(name)]))


def phase_group(phase: str) -> str:
    if phase.startswith("reduce_scatter"):
        return "reduce_scatter"
    if phase.startswith("allgather"):
        return "allgather"
    return phase or "hardware"


def read_execution_rows(path: Path) -> List[dict]:
    """Read every timed profiler execution exactly once, including profiler-only rows."""
    rows: List[dict] = []
    seen_identities = {}
    seen_graph_ids = {}
    with path.open("r", encoding="utf-8-sig", newline="") as source:
        for index, row in enumerate(csv.DictReader(source)):
            if row.get("match_status") not in ("matched", "profiler_only"):
                continue
            start = to_float(row.get("task_start"))
            stop = to_float(row.get("task_stop"))
            start_order = to_decimal(row.get("task_start"))
            stop_order = to_decimal(row.get("task_stop"))
            if (
                math.isnan(start)
                or math.isnan(stop)
                or start_order is None
                or stop_order is None
            ):
                continue
            duration = to_float(row.get("duration"))
            if math.isnan(duration):
                duration = float(abs(stop_order - start_order))
            stream_id = to_int(row.get("profiler_stream_id") or row.get("stream_id"))
            task_id = to_int(row.get("profiler_task_id") or row.get("task_id"))
            identity = ExecutionIdentity(
                node_id=row.get("node_id", ""),
                device_id=to_int(row.get("device_id")),
                stream_id=stream_id,
                task_id=task_id,
                subtask_id=to_int(row.get("subtask_id")),
                connection_id=to_int(row.get("connection_id")),
            )
            if identity in seen_identities:
                raise ValueError(
                    "duplicate physical execution identity at CSV rows {} and {}: {}".format(
                        seen_identities[identity] + 2,
                        index + 2,
                        identity,
                    )
                )
            if (
                identity.stable_id in seen_graph_ids
                and seen_graph_ids[identity.stable_id] != identity
            ):
                raise ValueError(
                    "stable graph ID collision for {}".format(identity.stable_id)
                )
            seen_identities[identity] = index
            seen_graph_ids[identity.stable_id] = identity
            item = dict(row)
            item.update({
                "_source_row": index,
                "_graph_id": identity.stable_id,
                "_execution_identity": identity,
                "_node_id": row.get("node_id", ""),
                "_device_id": to_int(row.get("device_id")),
                "_user_rank": to_int(row.get("user_rank")),
                "_rank": to_int(row.get("device_id")),
                "_rank_size": to_int(row.get("rank_size")),
                "_stream_id": stream_id,
                "_task_id": task_id,
                "_subtask_id": to_int(row.get("subtask_id")),
                "_connection_id": to_int(row.get("connection_id")),
                "_semantic_stream_id": to_int(row.get("stream_id")),
                "_pid": to_int(row.get("pid")),
                "_graph_instance_id": to_int(row.get("graph_instance_id")),
                "_correlation_parent_stream_id": to_int(
                    row.get("correlation_parent_stream_id")
                ),
                "_correlation_parent_task_id": to_int(
                    row.get("correlation_parent_task_id")
                ),
                "_operation_scope": row.get("profiler_op_scope", ""),
                "_operation_scope_status": row.get(
                    "profiler_op_scope_status", ""
                ),
                "_peer_rank": to_int(row.get("peer_rank")),
                "_notify_id": to_int(row.get("notify_id")),
                "_step": to_int(row.get("step")),
                "_slice": to_int(row.get("slice")),
                "_start": min(start, stop),
                "_stop": max(start, stop),
                "_start_order": min(start_order, stop_order),
                "_stop_order": max(start_order, stop_order),
                "_duration": abs(duration),
                "_phase_group": phase_group(row.get("phase", "")),
            })
            rows.append(item)
    rows.sort(key=execution_sort_key)
    return rows


def execution_sort_key(row: dict):
    return (
        row["_node_id"], row["_device_id"], row["_stream_id"],
        execution_time_order_value(row, "start"),
        execution_time_order_value(row, "stop"),
        row["_task_id"], row["_subtask_id"],
        row["_connection_id"], row["_graph_id"],
    )


def build_execution_edges(
    rows: List[dict],
    notify_ambiguities: List[dict] | None = None,
) -> List[dict]:
    """Build stream, local synchronization, and peer semantic dependencies."""
    edges: List[dict] = []
    seen = set()

    def add(
        kind: str,
        src: dict,
        dst: dict,
        reason: str,
        evidence: str,
        confidence: str,
        relation_id: str = "",
    ) -> None:
        if not src or not dst or src is dst:
            return
        key = (kind, src["_graph_id"], dst["_graph_id"])
        if key in seen:
            return
        seen.add(key)
        edges.append({
            "graph_schema_version": GRAPH_SCHEMA_VERSION,
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
            "relation_id": relation_id,
        })

    _add_direct_stream_order_edges(rows, add)
    _add_ffts_logical_stream_order_edges(rows, add)
    ambiguities = _add_ffts_notify_sync_edges(rows, add)
    if notify_ambiguities is not None:
        notify_ambiguities.extend(ambiguities)
    _add_peer_semantic_edges(rows, add)
    return edges


def _add_direct_stream_order_edges(rows: List[dict], add) -> None:
    """Order only non-FFts executions on the same physical stream."""
    by_stream: Dict[Tuple[str, int, int], List[dict]] = defaultdict(list)
    for row in rows:
        if row["_subtask_id"] >= 0:
            continue
        by_stream[(row["_node_id"], row["_device_id"], row["_stream_id"])].append(row)

    for stream_rows in by_stream.values():
        start_buckets: Dict[Decimal, List[dict]] = defaultdict(list)
        for row in stream_rows:
            start_buckets[execution_time_order_value(row, "start")].append(row)
        ordered_buckets = [
            sorted(start_buckets[start], key=execution_sort_key)
            for start in sorted(start_buckets)
        ]
        for previous, current in zip(ordered_buckets, ordered_buckets[1:]):
            for src in previous:
                for dst in current:
                    if (
                        execution_time_order_value(src, "stop")
                        > execution_time_order_value(dst, "start")
                    ):
                        continue
                    add(
                        "direct_stream_order_observed",
                        src,
                        dst,
                        "consecutive direct execution start groups on one physical stream",
                        "msprof_direct_physical_stream_order",
                        "observed",
                    )


def _ffts_value(row: dict, internal: str, public: str) -> int:
    if internal in row:
        return to_int(row.get(internal))
    return to_int(row.get(public))


def _ffts_logical_group_key(row: dict):
    if row["_subtask_id"] < 0 or row.get("match_status") != "matched":
        return None
    ffts_ctx_id = to_int(row.get("ffts_ctx_id"))
    graph_instance_id = _ffts_value(
        row, "_graph_instance_id", "graph_instance_id"
    )
    logical_stream_id = _ffts_value(
        row, "_semantic_stream_id", "stream_id"
    )
    pid = _ffts_value(row, "_pid", "pid")
    parent_stream_id = _ffts_value(
        row,
        "_correlation_parent_stream_id",
        "correlation_parent_stream_id",
    )
    parent_task_id = _ffts_value(
        row,
        "_correlation_parent_task_id",
        "correlation_parent_task_id",
    )
    operation_scope = row.get(
        "_operation_scope", row.get("profiler_op_scope", "")
    )
    operation_scope_status = row.get(
        "_operation_scope_status",
        row.get("profiler_op_scope_status", ""),
    )
    if ffts_ctx_id < 0:
        return None
    if ffts_ctx_id != row["_subtask_id"]:
        raise ValueError(
            "matched FFts execution has inconsistent semantic/context IDs: "
            "graph_id={} ffts_ctx_id={} subtask_id={}".format(
                row["_graph_id"], ffts_ctx_id, row["_subtask_id"]
            )
        )
    if (
        graph_instance_id < 0
        or logical_stream_id < 0
        or pid < 0
        or parent_stream_id < 0
        or parent_task_id < 0
        or not operation_scope
        or operation_scope_status != "unique"
    ):
        return None
    return (
        row["_node_id"],
        row["_device_id"],
        pid,
        operation_scope,
        graph_instance_id,
        parent_stream_id,
        parent_task_id,
        logical_stream_id,
    )


def _add_ffts_logical_stream_order_edges(rows: List[dict], add) -> None:
    """Rebuild FFts declaration order within each semantic logical stream."""
    groups: Dict[tuple, List[dict]] = defaultdict(list)
    for row in rows:
        key = _ffts_logical_group_key(row)
        if key is not None:
            groups[key].append(row)

    for key, group_rows in groups.items():
        contexts = Counter(row["_subtask_id"] for row in group_rows)
        duplicates = sorted(context for context, count in contexts.items() if count > 1)
        if duplicates:
            raise ValueError(
                "duplicate FFts context IDs in logical stream group {}: {}".format(
                    key, duplicates
                )
            )
        ordered = sorted(
            group_rows,
            key=lambda row: (row["_subtask_id"], row["_graph_id"]),
        )
        for src, dst in zip(ordered, ordered[1:]):
            add(
                "ffts_logical_stream_order",
                src,
                dst,
                "adjacent FFts context declarations in one semantic logical stream",
                "ffts_graph_context_and_semantic_stream",
                "semantic",
            )


def _ffts_notify_endpoint(row: dict):
    if row["_subtask_id"] < 0 or row.get("match_status") != "matched":
        return None
    task_kind = str(row.get("task_kind", "")).strip().lower()
    event = str(row.get("event", "")).strip().lower()
    rule = NOTIFY_ENDPOINT_RULES.get((task_kind, event))
    if rule is None:
        return None

    role, signal_kind = rule
    user_rank = row["_user_rank"]
    peer_rank = row["_peer_rank"]
    if role == NOTIFY_ROLE_PRODUCER:
        producer_rank, consumer_rank = user_rank, peer_rank
    else:
        producer_rank, consumer_rank = peer_rank, user_rank
    operation_scope = str(
        row.get("_operation_scope", row.get("profiler_op_scope", ""))
    ).strip()
    operation_scope_status = row.get(
        "_operation_scope_status",
        row.get("profiler_op_scope_status", ""),
    )
    if operation_scope_status != "unique":
        operation_scope = ""
    graph_instance_id = _ffts_value(
        row, "_graph_instance_id", "graph_instance_id"
    )
    relation = NotifyRelationIdentity(
        node_id=row["_node_id"],
        operation_scope=operation_scope,
        rank_domain=NOTIFY_RANK_DOMAIN_USER,
        producer_rank=producer_rank,
        consumer_rank=consumer_rank,
        signal_kind=signal_kind,
        phase=str(row.get("phase", "")).strip(),
        step=row["_step"],
        slice_id=row["_slice"],
        notify_id=row["_notify_id"],
        sequence_kind=NOTIFY_SEQUENCE_FFTS_GRAPH,
        sequence_value=str(graph_instance_id),
    )
    return {
        "row": row,
        "role": role,
        "relation": relation,
    }


def _notify_ambiguity_row(
    relation: NotifyRelationIdentity,
    endpoints: List[dict],
    status: str,
    missing_role: str,
    missing_fields: str,
    reason: str,
) -> dict:
    role_counts = Counter(endpoint["role"] for endpoint in endpoints)
    return {
        "graph_schema_version": GRAPH_SCHEMA_VERSION,
        "relation_id": relation.stable_id,
        "status": status,
        "missing_role": missing_role,
        "missing_fields": missing_fields,
        "endpoint_count": len(endpoints),
        "producer_count": role_counts[NOTIFY_ROLE_PRODUCER],
        "consumer_count": role_counts[NOTIFY_ROLE_CONSUMER],
        "node_id": relation.node_id,
        "operation_scope": relation.operation_scope,
        "rank_domain": relation.rank_domain,
        "producer_rank": relation.producer_rank,
        "consumer_rank": relation.consumer_rank,
        "signal_kind": relation.signal_kind,
        "phase": relation.phase,
        "step": relation.step,
        "slice": relation.slice_id,
        "notify_id": relation.notify_id,
        "sequence_kind": relation.sequence_kind,
        "sequence_value": relation.sequence_value,
        "endpoint_graph_ids": "|".join(
            sorted(endpoint["row"]["_graph_id"] for endpoint in endpoints)
        ),
        "reason": reason,
    }


def _add_ffts_notify_sync_edges(rows: List[dict], add) -> List[dict]:
    """Pair FFts Notify endpoints only by a complete shared relation identity."""
    complete_groups: Dict[str, List[dict]] = defaultdict(list)
    identities: Dict[str, NotifyRelationIdentity] = {}
    ambiguities: List[dict] = []
    for row in rows:
        endpoint = _ffts_notify_endpoint(row)
        if endpoint is None:
            continue
        relation = endpoint["relation"]
        if not relation.complete:
            ambiguities.append(_notify_ambiguity_row(
                relation,
                [endpoint],
                NOTIFY_RELATION_INCOMPLETE,
                "",
                "|".join(relation.missing_fields),
                "FFts Notify endpoint has an incomplete relation identity",
            ))
            continue
        if (
            relation.stable_id in identities
            and identities[relation.stable_id] != relation
        ):
            raise ValueError(
                "Notify relation stable ID collision for {}".format(
                    relation.stable_id
                )
            )
        identities[relation.stable_id] = relation
        complete_groups[relation.stable_id].append(endpoint)

    for relation_id, endpoints in complete_groups.items():
        relation = identities[relation_id]
        producers = [
            endpoint for endpoint in endpoints
            if endpoint["role"] == NOTIFY_ROLE_PRODUCER
        ]
        consumers = [
            endpoint for endpoint in endpoints
            if endpoint["role"] == NOTIFY_ROLE_CONSUMER
        ]
        if len(endpoints) == 2 and len(producers) == 1 and len(consumers) == 1:
            add(
                "ffts_notify_sync_observed",
                producers[0]["row"],
                consumers[0]["row"],
                "unique producer and consumer for one FFts Notify relation identity",
                "ffts_notify_relation_identity",
                "observed",
                relation_id,
            )
            continue
        if len(endpoints) == 1:
            missing_role = (
                NOTIFY_ROLE_CONSUMER
                if producers
                else NOTIFY_ROLE_PRODUCER
            )
            ambiguities.append(_notify_ambiguity_row(
                relation,
                endpoints,
                NOTIFY_RELATION_SINGLE,
                missing_role,
                "",
                "complete FFts Notify relation identity has only one endpoint",
            ))
            continue
        ambiguities.append(_notify_ambiguity_row(
            relation,
            endpoints,
            NOTIFY_RELATION_AMBIGUOUS,
            "",
            "",
            "FFts Notify relation identity has multiple producer or consumer endpoints",
        ))
    return ambiguities


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


def export_dependency_tables(
    merged_csv: Path,
    prefix: Path,
) -> Tuple[Path, Path, Path, Counter, Counter]:
    rows = read_execution_rows(merged_csv)
    notify_ambiguities: List[dict] = []
    edges = build_execution_edges(rows, notify_ambiguities)
    nodes_path = prefix.with_name(prefix.name + "_nodes.csv")
    edges_path = prefix.with_name(prefix.name + "_edges.csv")
    ambiguities_path = prefix.with_name(
        prefix.name + "_notify_ambiguities.csv"
    )
    node_fields = [key for key in rows[0] if not key.startswith("_")] if rows else []
    node_fields = ["graph_schema_version", "graph_id"] + node_fields
    node_rows = [
        dict(
            {
                "graph_schema_version": GRAPH_SCHEMA_VERSION,
                "graph_id": row["_graph_id"],
            },
            **{key: row.get(key, "") for key in node_fields[2:]},
        )
                 for row in rows]
    write_csv(str(nodes_path), node_fields, node_rows)
    write_csv(
        str(edges_path),
        list(edges[0]) if edges else ["graph_schema_version", "edge_id"],
        edges,
    )
    write_csv(
        str(ambiguities_path),
        NOTIFY_AMBIGUITY_FIELDS,
        notify_ambiguities,
    )
    return (
        nodes_path,
        edges_path,
        ambiguities_path,
        Counter(edge["kind"] for edge in edges),
        Counter(row["status"] for row in notify_ambiguities),
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Export evidence-labelled physical dependency tables.")
    parser.add_argument("merged_csv", type=Path)
    parser.add_argument("-o", "--output-prefix", type=Path)
    args = parser.parse_args()
    prefix = args.output_prefix or args.merged_csv.with_name(args.merged_csv.stem + "_dependency")
    (
        nodes_path,
        edges_path,
        ambiguities_path,
        counts,
        ambiguity_counts,
    ) = export_dependency_tables(args.merged_csv, prefix)
    for kind in PHYSICAL_EDGE_KINDS:
        print(f"{kind}={counts[kind]}")
    for status in (
        NOTIFY_RELATION_SINGLE,
        NOTIFY_RELATION_AMBIGUOUS,
        NOTIFY_RELATION_INCOMPLETE,
    ):
        print(f"notify_relation_{status}={ambiguity_counts[status]}")
    print(f"nodes_csv={nodes_path}")
    print(f"edges_csv={edges_path}")
    print(f"notify_ambiguities_csv={ambiguities_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
