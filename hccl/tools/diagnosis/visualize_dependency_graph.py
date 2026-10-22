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
        DependencyEdgeIdentity,
        DirectNotifyChannelIdentity,
        DirectNotifyRelationIdentity,
        ExecutionIdentity,
        GRAPH_SCHEMA_VERSION,
        LocalNotifyChannelIdentity,
        LocalNotifyRelationIdentity,
        NOTIFY_ENDPOINT_RULES,
        NOTIFY_RANK_DOMAIN_DEVICE_LOCAL,
        NOTIFY_RANK_DOMAIN_USER,
        NOTIFY_RELATION_AMBIGUOUS,
        NOTIFY_RELATION_CONFLICT,
        NOTIFY_RELATION_INCOMPLETE,
        NOTIFY_RELATION_SINGLE,
        NOTIFY_ROLE_CONSUMER,
        NOTIFY_ROLE_PRODUCER,
        NOTIFY_SEQUENCE_DB_ORDINAL,
        NOTIFY_SEQUENCE_DB_LOCAL_ORDINAL,
        NOTIFY_SEQUENCE_FFTS_GRAPH,
        NotifyRelationIdentity,
        normalize_notify_endpoint,
    )
    from diagnosis.schema import MERGED_FIELDS, write_csv
else:
    from .dependency_model import (
        DependencyEdgeIdentity,
        DirectNotifyChannelIdentity,
        DirectNotifyRelationIdentity,
        ExecutionIdentity,
        GRAPH_SCHEMA_VERSION,
        LocalNotifyChannelIdentity,
        LocalNotifyRelationIdentity,
        NOTIFY_ENDPOINT_RULES,
        NOTIFY_RANK_DOMAIN_DEVICE_LOCAL,
        NOTIFY_RANK_DOMAIN_USER,
        NOTIFY_RELATION_AMBIGUOUS,
        NOTIFY_RELATION_CONFLICT,
        NOTIFY_RELATION_INCOMPLETE,
        NOTIFY_RELATION_SINGLE,
        NOTIFY_ROLE_CONSUMER,
        NOTIFY_ROLE_PRODUCER,
        NOTIFY_SEQUENCE_DB_ORDINAL,
        NOTIFY_SEQUENCE_DB_LOCAL_ORDINAL,
        NOTIFY_SEQUENCE_FFTS_GRAPH,
        NotifyRelationIdentity,
        normalize_notify_endpoint,
    )
    from .schema import MERGED_FIELDS, write_csv


EDGE_COLOR = {
    "direct_stream_order_observed": "#444444",
    "ffts_logical_stream_order": "#5c6bc0",
    "ffts_notify_sync_observed": "#2b8a3e",
    "direct_notify_sync_exact": "#7b3fb3",
    "local_notify_sync_exact": "#d9488b",
    "cross_node_notify_sync_observed": "#007c91",
    "same_node_rdma_notify_sync_observed": "#b05b00",
}
PHYSICAL_EDGE_KINDS = tuple(EDGE_COLOR)

EDGE_FIELDS = [
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
    "sequence_kind",
    "sequence_value",
    "semantic_status",
    "signal_kind",
    "phase",
    "step",
    "slice",
]

GRAPH_SUMMARY_FIELDS = ["metric", "value"]

NOTIFY_AMBIGUITY_FIELDS = [
    "graph_schema_version",
    "relation_id",
    "status",
    "missing_role",
    "missing_fields",
    "endpoint_count",
    "producer_count",
    "consumer_count",
    "producer_stream_count",
    "consumer_stream_count",
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
    "semantic_status",
    "endpoint_graph_ids",
    "reason",
]


def to_int(value: object, default: int = -1) -> int:
    try:
        text = str(value).strip()
        if not text:
            return default
        try:
            return int(text, 10)
        except ValueError:
            return int(float(text))
    except (TypeError, ValueError, OverflowError):
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
            })
            rows.append(item)
    rows.sort(key=execution_sort_key)
    return rows


def read_graph_artifact_nodes(path: Path) -> List[dict]:
    """Read stable execution/resource node artifacts without rebuilding edges."""
    rows: List[dict] = []
    graph_ids = set()
    with path.open("r", encoding="utf-8-sig", newline="") as source:
        for index, row in enumerate(csv.DictReader(source)):
            graph_id = str(row.get("graph_id", "")).strip()
            if not graph_id:
                raise ValueError(
                    "missing graph_id at artifact row {}".format(index + 2)
                )
            if graph_id in graph_ids:
                raise ValueError("duplicate graph_id in artifact: {}".format(graph_id))
            graph_ids.add(graph_id)
            start_order = to_decimal(row.get("task_start"))
            stop_order = to_decimal(row.get("task_stop"))
            if start_order is None or stop_order is None:
                raise ValueError(
                    "missing task time for graph node {}".format(graph_id)
                )
            start_order, stop_order = (
                min(start_order, stop_order),
                max(start_order, stop_order),
            )
            duration = to_decimal(row.get("duration"))
            if duration is None:
                duration = stop_order - start_order
            stream_id = to_int(
                row.get("profiler_stream_id") or row.get("stream_id")
            )
            task_id = to_int(
                row.get("profiler_task_id") or row.get("task_id")
            )
            item = dict(row)
            item.update({
                "_source_row": index,
                "_graph_id": graph_id,
                "_node_id": row.get("node_id", ""),
                "_device_id": to_int(row.get("device_id")),
                "_user_rank": to_int(row.get("user_rank")),
                "_rank": to_int(row.get("device_id")),
                "_rank_size": to_int(row.get("rank_size")),
                "_stream_id": stream_id,
                "_task_id": task_id,
                "_subtask_id": to_int(row.get("subtask_id")),
                "_connection_id": to_int(row.get("connection_id")),
                "_operation_scope": row.get("profiler_op_scope", ""),
                "_operation_scope_status": row.get(
                    "profiler_op_scope_status", ""
                ),
                "_peer_rank": to_int(row.get("peer_rank")),
                "_notify_id": to_int(row.get("notify_id")),
                "_step": to_int(row.get("step")),
                "_slice": to_int(row.get("slice")),
                "_start": float(start_order),
                "_stop": float(stop_order),
                "_start_order": start_order,
                "_stop_order": stop_order,
                "_duration": float(abs(duration)),
                "_node_kind": row.get("node_kind", "execution"),
                "_boundary_side": row.get("boundary_side", ""),
                "_boundary_reason": row.get("boundary_reason", ""),
                "_boundary_relation_id": row.get(
                    "boundary_relation_id", ""
                ),
            })
            rows.append(item)
    rows.sort(key=lambda item: item["_graph_id"])
    return rows


def read_graph_artifact_edges(path: Path) -> List[dict]:
    """Read stable dependency edges exactly as exported."""
    edges: List[dict] = []
    edge_ids = set()
    with path.open("r", encoding="utf-8-sig", newline="") as source:
        for index, row in enumerate(csv.DictReader(source)):
            edge_id = str(row.get("edge_id", "")).strip()
            if not edge_id:
                raise ValueError(
                    "missing edge_id at artifact row {}".format(index + 2)
                )
            if edge_id in edge_ids:
                raise ValueError("duplicate edge_id in artifact: {}".format(edge_id))
            edge_ids.add(edge_id)
            edges.append(dict(row))
    return sorted(edges, key=lambda edge: edge["edge_id"])


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
    excluded_notify_graph_ids: frozenset[str] = frozenset(),
) -> List[dict]:
    """Build stream, local synchronization, and peer semantic dependencies."""
    edges: List[dict] = []
    edge_by_endpoints = {}
    identities_by_stable_id = {}

    def add(
        kind: str,
        src: dict,
        dst: dict,
        reason: str,
        evidence: str,
        confidence: str,
        relation_id: str = "",
        sequence_kind: str = "",
        sequence_value: str = "",
        semantic_status: str = "",
        signal_kind: str = "",
        phase: str = "",
        step: int = -1,
        slice_id: int = -1,
    ) -> None:
        if not src or not dst:
            return
        src_graph_id = src["_graph_id"]
        dst_graph_id = dst["_graph_id"]
        if src_graph_id == dst_graph_id:
            return
        identity = DependencyEdgeIdentity(
            kind,
            src_graph_id,
            dst_graph_id,
            relation_id,
        )
        endpoint_key = (kind, src_graph_id, dst_graph_id)
        existing = edge_by_endpoints.get(endpoint_key)
        if existing is not None:
            if existing != identity:
                raise ValueError(
                    "conflicting relation identities for dependency edge "
                    "{} {} -> {}".format(kind, src_graph_id, dst_graph_id)
                )
            return
        stable_collision = identities_by_stable_id.get(identity.stable_id)
        if stable_collision is not None and stable_collision != identity:
            raise ValueError(
                "dependency edge stable ID collision for {}".format(
                    identity.stable_id
                )
            )
        edge_by_endpoints[endpoint_key] = identity
        identities_by_stable_id[identity.stable_id] = identity
        edges.append({
            "graph_schema_version": GRAPH_SCHEMA_VERSION,
            "edge_id": identity.stable_id,
            "kind": kind,
            "src": src_graph_id,
            "dst": dst_graph_id,
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
            "sequence_kind": sequence_kind,
            "sequence_value": sequence_value,
            "semantic_status": semantic_status,
            "signal_kind": signal_kind,
            "phase": phase,
            "step": step,
            "slice": slice_id,
        })

    _add_direct_stream_order_edges(rows, add)
    _add_ffts_logical_stream_order_edges(rows, add)
    notify_rows = [row for row in rows if row["_graph_id"] not in excluded_notify_graph_ids]
    ambiguities = _add_ffts_notify_sync_edges(notify_rows, add)
    ambiguities.extend(_add_direct_notify_sync_edges(notify_rows, add))
    ambiguities.extend(_add_local_notify_sync_edges(notify_rows, add))
    if notify_ambiguities is not None:
        notify_ambiguities.extend(ambiguities)
    return sorted(edges, key=lambda edge: edge["edge_id"])


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
        "producer_stream_count": len({
            (
                endpoint["row"]["_node_id"],
                endpoint["row"]["_device_id"],
                endpoint["row"]["_stream_id"],
            )
            for endpoint in endpoints
            if endpoint["role"] == NOTIFY_ROLE_PRODUCER
        }),
        "consumer_stream_count": len({
            (
                endpoint["row"]["_node_id"],
                endpoint["row"]["_device_id"],
                endpoint["row"]["_stream_id"],
            )
            for endpoint in endpoints
            if endpoint["role"] == NOTIFY_ROLE_CONSUMER
        }),
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
        "semantic_status": "",
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


def _direct_notify_endpoint(row: dict):
    """Normalize one direct physical Notify endpoint using canonical DB fields."""
    if row["_subtask_id"] >= 0:
        return None
    task_kind = str(
        row.get("profiler_task_kind") or row.get("task_kind") or ""
    ).strip().lower()
    if task_kind not in ("notify_record", "notify_wait"):
        return None
    user_rank = row["_user_rank"]
    peer_rank = row["_peer_rank"]
    # dstRank=-1 denotes local stream control, not a cross-rank channel.
    if peer_rank < 0:
        return None
    if task_kind == "notify_record":
        role = NOTIFY_ROLE_PRODUCER
        producer_rank, consumer_rank = user_rank, peer_rank
    else:
        role = NOTIFY_ROLE_CONSUMER
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
    channel = DirectNotifyChannelIdentity(
        node_id=row["_node_id"],
        operation_scope=operation_scope,
        producer_rank=producer_rank,
        consumer_rank=consumer_rank,
        notify_id=row["_notify_id"],
    )
    return {
        "row": row,
        "role": role,
        "channel": channel,
    }


def _direct_notify_ambiguity_row(
    channel: DirectNotifyChannelIdentity,
    endpoints: List[dict],
    status: str,
    reason: str,
    missing_fields: str = "",
    relation_id: str = "",
    sequence_value: str = "",
    semantic_status: str = "",
) -> dict:
    role_counts = Counter(endpoint["role"] for endpoint in endpoints)
    producer_streams = {
        (
            endpoint["row"]["_node_id"],
            endpoint["row"]["_device_id"],
            endpoint["row"]["_stream_id"],
        )
        for endpoint in endpoints
        if endpoint["role"] == NOTIFY_ROLE_PRODUCER
    }
    consumer_streams = {
        (
            endpoint["row"]["_node_id"],
            endpoint["row"]["_device_id"],
            endpoint["row"]["_stream_id"],
        )
        for endpoint in endpoints
        if endpoint["role"] == NOTIFY_ROLE_CONSUMER
    }
    missing_role = ""
    if not role_counts[NOTIFY_ROLE_PRODUCER]:
        missing_role = NOTIFY_ROLE_PRODUCER
    elif not role_counts[NOTIFY_ROLE_CONSUMER]:
        missing_role = NOTIFY_ROLE_CONSUMER
    return {
        "graph_schema_version": GRAPH_SCHEMA_VERSION,
        "relation_id": relation_id or channel.stable_id,
        "status": status,
        "missing_role": missing_role,
        "missing_fields": missing_fields,
        "endpoint_count": len(endpoints),
        "producer_count": role_counts[NOTIFY_ROLE_PRODUCER],
        "consumer_count": role_counts[NOTIFY_ROLE_CONSUMER],
        "producer_stream_count": len(producer_streams),
        "consumer_stream_count": len(consumer_streams),
        "node_id": channel.node_id,
        "operation_scope": channel.operation_scope,
        "rank_domain": NOTIFY_RANK_DOMAIN_USER,
        "producer_rank": channel.producer_rank,
        "consumer_rank": channel.consumer_rank,
        "signal_kind": "",
        "phase": "",
        "step": -1,
        "slice": -1,
        "notify_id": channel.notify_id,
        "sequence_kind": NOTIFY_SEQUENCE_DB_ORDINAL,
        "sequence_value": sequence_value,
        "semantic_status": semantic_status,
        "endpoint_graph_ids": "|".join(
            sorted(endpoint["row"]["_graph_id"] for endpoint in endpoints)
        ),
        "reason": reason,
    }


def _direct_notify_order_key(endpoint: dict):
    row = endpoint["row"]
    return (
        execution_time_order_value(row, "start"),
        execution_time_order_value(row, "stop"),
        row["_task_id"],
        row["_connection_id"],
        row["_graph_id"],
    )


def _has_ambiguous_direct_order(endpoints: List[dict]) -> bool:
    order_keys = Counter(
        (
            execution_time_order_value(endpoint["row"], "start"),
            execution_time_order_value(endpoint["row"], "stop"),
            endpoint["row"]["_task_id"],
        )
        for endpoint in endpoints
    )
    return any(count > 1 for count in order_keys.values())


def _direct_semantic_annotation(endpoint: dict):
    row = endpoint["row"]
    normalized = normalize_notify_endpoint(
        str(row.get("task_kind", "")).strip().lower(),
        str(row.get("event", "")).strip().lower(),
        row["_user_rank"],
        row["_peer_rank"],
    )
    if normalized is None:
        return None
    role, producer_rank, consumer_rank, signal_kind = normalized
    return {
        "role": role,
        "producer_rank": producer_rank,
        "consumer_rank": consumer_rank,
        "signal_kind": signal_kind,
        "phase": str(row.get("phase", "")).strip(),
        "step": row["_step"],
        "slice": row["_slice"],
    }


def _direct_pair_semantics(
    channel: DirectNotifyChannelIdentity,
    producer: dict,
    consumer: dict,
):
    annotations = [
        annotation for annotation in (
            _direct_semantic_annotation(producer),
            _direct_semantic_annotation(consumer),
        )
        if annotation is not None
    ]
    if not annotations:
        return "none", "", "", -1, -1, ""
    status = "both" if len(annotations) == 2 else "partial"
    conflicts = []
    for annotation in annotations:
        if (
            annotation["producer_rank"] != channel.producer_rank
            or annotation["consumer_rank"] != channel.consumer_rank
        ):
            conflicts.append("semantic rank direction differs from DB channel")
    if len(annotations) == 2:
        fields = ("signal_kind", "phase", "step", "slice")
        if any(annotations[0][field] != annotations[1][field] for field in fields):
            conflicts.append("producer/consumer semantic coordinates differ")
    annotation = annotations[0]
    if conflicts:
        status = NOTIFY_RELATION_CONFLICT
    return (
        status,
        annotation["signal_kind"],
        annotation["phase"],
        annotation["step"],
        annotation["slice"],
        "; ".join(conflicts),
    )


def _add_direct_notify_sync_edges(rows: List[dict], add) -> List[dict]:
    """Pair complete direct Notify DB sequences by per-side local ordinal."""
    groups: Dict[str, List[dict]] = defaultdict(list)
    channels: Dict[str, DirectNotifyChannelIdentity] = {}
    ambiguities: List[dict] = []
    for row in rows:
        endpoint = _direct_notify_endpoint(row)
        if endpoint is None:
            continue
        channel = endpoint["channel"]
        if not channel.complete:
            ambiguities.append(_direct_notify_ambiguity_row(
                channel,
                [endpoint],
                NOTIFY_RELATION_INCOMPLETE,
                "direct Notify endpoint has incomplete DB channel metadata",
                "|".join(channel.missing_fields),
            ))
            continue
        if channel.stable_id in channels and channels[channel.stable_id] != channel:
            raise ValueError(
                "direct Notify channel stable ID collision for {}".format(
                    channel.stable_id
                )
            )
        channels[channel.stable_id] = channel
        groups[channel.stable_id].append(endpoint)

    for channel_id, endpoints in groups.items():
        channel = channels[channel_id]
        producers = [
            endpoint for endpoint in endpoints
            if endpoint["role"] == NOTIFY_ROLE_PRODUCER
        ]
        consumers = [
            endpoint for endpoint in endpoints
            if endpoint["role"] == NOTIFY_ROLE_CONSUMER
        ]
        producer_streams = {
            (
                endpoint["row"]["_node_id"],
                endpoint["row"]["_device_id"],
                endpoint["row"]["_stream_id"],
            )
            for endpoint in producers
        }
        consumer_streams = {
            (
                endpoint["row"]["_node_id"],
                endpoint["row"]["_device_id"],
                endpoint["row"]["_stream_id"],
            )
            for endpoint in consumers
        }
        if not producers or not consumers:
            ambiguities.append(_direct_notify_ambiguity_row(
                channel,
                endpoints,
                NOTIFY_RELATION_SINGLE,
                "direct Notify DB channel has only one endpoint role",
            ))
            continue
        if len(producer_streams) != 1 or len(consumer_streams) != 1:
            ambiguities.append(_direct_notify_ambiguity_row(
                channel,
                endpoints,
                NOTIFY_RELATION_AMBIGUOUS,
                "direct Notify role is not totally ordered by one local physical stream",
            ))
            continue
        if len(producers) != len(consumers):
            ambiguities.append(_direct_notify_ambiguity_row(
                channel,
                endpoints,
                NOTIFY_RELATION_AMBIGUOUS,
                "direct Notify Record/Wait counts differ; ordinal alignment is unsafe",
            ))
            continue
        if (
            _has_ambiguous_direct_order(producers)
            or _has_ambiguous_direct_order(consumers)
        ):
            ambiguities.append(_direct_notify_ambiguity_row(
                channel,
                endpoints,
                NOTIFY_RELATION_AMBIGUOUS,
                "direct Notify local execution order is not unique",
            ))
            continue

        producers.sort(key=_direct_notify_order_key)
        consumers.sort(key=_direct_notify_order_key)
        for ordinal, (producer, consumer) in enumerate(zip(producers, consumers)):
            relation = DirectNotifyRelationIdentity(channel, ordinal)
            (
                semantic_status,
                signal_kind,
                phase,
                step,
                slice_id,
                semantic_conflict,
            ) = _direct_pair_semantics(channel, producer, consumer)
            if semantic_status == NOTIFY_RELATION_CONFLICT:
                ambiguities.append(_direct_notify_ambiguity_row(
                    channel,
                    [producer, consumer],
                    NOTIFY_RELATION_CONFLICT,
                    semantic_conflict,
                    relation_id=relation.stable_id,
                    sequence_value=str(ordinal),
                    semantic_status=semantic_status,
                ))
            add(
                "direct_notify_sync_exact",
                producer["row"],
                consumer["row"],
                "same DB Notify channel and per-side local execution ordinal",
                "msprof_notify_resource_rank_direction_and_local_ordinal",
                "exact",
                relation.stable_id,
                NOTIFY_SEQUENCE_DB_ORDINAL,
                str(ordinal),
                semantic_status,
                signal_kind,
                phase,
                step,
                slice_id,
            )
    return ambiguities


def _local_notify_endpoint(row: dict):
    """Normalize one device-local direct Notify endpoint from DB fields."""
    if row["_subtask_id"] >= 0 or row["_peer_rank"] != -1:
        return None
    task_kind = str(
        row.get("profiler_task_kind") or row.get("task_kind") or ""
    ).strip().lower()
    if task_kind not in ("notify_record", "notify_wait"):
        return None
    operation_scope = str(
        row.get("_operation_scope", row.get("profiler_op_scope", ""))
    ).strip()
    operation_scope_status = row.get(
        "_operation_scope_status",
        row.get("profiler_op_scope_status", ""),
    )
    if operation_scope_status != "unique":
        operation_scope = ""
    channel = LocalNotifyChannelIdentity(
        node_id=row["_node_id"],
        operation_scope=operation_scope,
        device_id=row["_device_id"],
        notify_id=row["_notify_id"],
    )
    return {
        "row": row,
        "role": (
            NOTIFY_ROLE_PRODUCER
            if task_kind == "notify_record"
            else NOTIFY_ROLE_CONSUMER
        ),
        "channel": channel,
    }


def _local_notify_ambiguity_row(
    channel: LocalNotifyChannelIdentity,
    endpoints: List[dict],
    status: str,
    reason: str,
    missing_fields: str = "",
) -> dict:
    role_counts = Counter(endpoint["role"] for endpoint in endpoints)
    producer_streams = {
        (
            endpoint["row"]["_node_id"],
            endpoint["row"]["_device_id"],
            endpoint["row"]["_stream_id"],
        )
        for endpoint in endpoints
        if endpoint["role"] == NOTIFY_ROLE_PRODUCER
    }
    consumer_streams = {
        (
            endpoint["row"]["_node_id"],
            endpoint["row"]["_device_id"],
            endpoint["row"]["_stream_id"],
        )
        for endpoint in endpoints
        if endpoint["role"] == NOTIFY_ROLE_CONSUMER
    }
    missing_role = ""
    if not role_counts[NOTIFY_ROLE_PRODUCER]:
        missing_role = NOTIFY_ROLE_PRODUCER
    elif not role_counts[NOTIFY_ROLE_CONSUMER]:
        missing_role = NOTIFY_ROLE_CONSUMER
    return {
        "graph_schema_version": GRAPH_SCHEMA_VERSION,
        "relation_id": channel.stable_id,
        "status": status,
        "missing_role": missing_role,
        "missing_fields": missing_fields,
        "endpoint_count": len(endpoints),
        "producer_count": role_counts[NOTIFY_ROLE_PRODUCER],
        "consumer_count": role_counts[NOTIFY_ROLE_CONSUMER],
        "producer_stream_count": len(producer_streams),
        "consumer_stream_count": len(consumer_streams),
        "node_id": channel.node_id,
        "operation_scope": channel.operation_scope,
        "rank_domain": NOTIFY_RANK_DOMAIN_DEVICE_LOCAL,
        "producer_rank": -1,
        "consumer_rank": -1,
        "signal_kind": "",
        "phase": "",
        "step": -1,
        "slice": -1,
        "notify_id": channel.notify_id,
        "sequence_kind": NOTIFY_SEQUENCE_DB_LOCAL_ORDINAL,
        "sequence_value": "",
        "semantic_status": "none",
        "endpoint_graph_ids": "|".join(
            sorted(endpoint["row"]["_graph_id"] for endpoint in endpoints)
        ),
        "reason": reason,
    }


def _add_local_notify_sync_edges(rows: List[dict], add) -> List[dict]:
    """Pair device-local Record/Wait sequences without cross-stream time zipping."""
    groups: Dict[str, List[dict]] = defaultdict(list)
    channels: Dict[str, LocalNotifyChannelIdentity] = {}
    ambiguities: List[dict] = []
    for row in rows:
        endpoint = _local_notify_endpoint(row)
        if endpoint is None:
            continue
        channel = endpoint["channel"]
        if not channel.complete:
            ambiguities.append(_local_notify_ambiguity_row(
                channel,
                [endpoint],
                NOTIFY_RELATION_INCOMPLETE,
                "local Notify endpoint has incomplete DB channel metadata",
                "|".join(channel.missing_fields),
            ))
            continue
        if channel.stable_id in channels and channels[channel.stable_id] != channel:
            raise ValueError(
                "local Notify channel stable ID collision for {}".format(
                    channel.stable_id
                )
            )
        channels[channel.stable_id] = channel
        groups[channel.stable_id].append(endpoint)

    for channel_id, endpoints in groups.items():
        channel = channels[channel_id]
        producers = [
            endpoint for endpoint in endpoints
            if endpoint["role"] == NOTIFY_ROLE_PRODUCER
        ]
        consumers = [
            endpoint for endpoint in endpoints
            if endpoint["role"] == NOTIFY_ROLE_CONSUMER
        ]
        producer_streams = {
            (
                endpoint["row"]["_node_id"],
                endpoint["row"]["_device_id"],
                endpoint["row"]["_stream_id"],
            )
            for endpoint in producers
        }
        consumer_streams = {
            (
                endpoint["row"]["_node_id"],
                endpoint["row"]["_device_id"],
                endpoint["row"]["_stream_id"],
            )
            for endpoint in consumers
        }
        if not producers or not consumers:
            ambiguities.append(_local_notify_ambiguity_row(
                channel,
                endpoints,
                NOTIFY_RELATION_SINGLE,
                "local Notify DB channel has only one endpoint role",
            ))
            continue
        if len(producer_streams) != 1 or len(consumer_streams) != 1:
            ambiguities.append(_local_notify_ambiguity_row(
                channel,
                endpoints,
                NOTIFY_RELATION_AMBIGUOUS,
                "local Notify role is not totally ordered by one physical stream",
            ))
            continue
        if len(producers) != len(consumers):
            ambiguities.append(_local_notify_ambiguity_row(
                channel,
                endpoints,
                NOTIFY_RELATION_AMBIGUOUS,
                "local Notify Record/Wait counts differ; ordinal alignment is unsafe",
            ))
            continue
        if (
            _has_ambiguous_direct_order(producers)
            or _has_ambiguous_direct_order(consumers)
        ):
            ambiguities.append(_local_notify_ambiguity_row(
                channel,
                endpoints,
                NOTIFY_RELATION_AMBIGUOUS,
                "local Notify per-stream execution order is not unique",
            ))
            continue

        producers.sort(key=_direct_notify_order_key)
        consumers.sort(key=_direct_notify_order_key)
        for ordinal, (producer, consumer) in enumerate(zip(producers, consumers)):
            relation = LocalNotifyRelationIdentity(channel, ordinal)
            add(
                "local_notify_sync_exact",
                producer["row"],
                consumer["row"],
                "same verified device-local Notify resource and DB per-stream execution ordinal; "
                "explicit control aliases, when present, are audited in control_metadata.csv",
                "verified_local_notify_resource_and_db_per_stream_ordinal",
                "exact",
                relation.stable_id,
                NOTIFY_SEQUENCE_DB_LOCAL_ORDINAL,
                str(ordinal),
                "none",
            )
    return ambiguities


def analyze_execution_graph(rows: List[dict], edges: List[dict]) -> Counter:
    """Return structural quality statistics for one execution graph artifact."""
    stats = Counter()
    node_ids = [row["_graph_id"] for row in rows]
    node_id_set = set(node_ids)
    edge_ids = [str(edge.get("edge_id", "")) for edge in edges]
    stats["graph_schema_version"] = GRAPH_SCHEMA_VERSION
    stats["node_count"] = len(node_ids)
    stats["edge_count"] = len(edges)
    stats["duplicate_node_ids"] = len(node_ids) - len(node_id_set)
    stats["duplicate_edge_ids"] = len(edge_ids) - len(set(edge_ids))

    missing_sources = [
        edge for edge in edges if edge.get("src") not in node_id_set
    ]
    missing_destinations = [
        edge for edge in edges if edge.get("dst") not in node_id_set
    ]
    self_loops = [
        edge for edge in edges if edge.get("src") == edge.get("dst")
    ]
    stats["missing_edge_sources"] = len(missing_sources)
    stats["missing_edge_destinations"] = len(missing_destinations)
    stats["self_loop_edges"] = len(self_loops)

    adjacency = {node_id: set() for node_id in node_id_set}
    reverse = {node_id: set() for node_id in node_id_set}
    incident = set()
    for edge in edges:
        src = edge.get("src")
        dst = edge.get("dst")
        if src not in node_id_set or dst not in node_id_set or src == dst:
            continue
        adjacency[src].add(dst)
        reverse[dst].add(src)
        incident.add(src)
        incident.add(dst)

    stats["isolated_nodes"] = len(node_id_set - incident)
    stats["root_nodes"] = sum(
        1 for node_id in node_id_set if not reverse[node_id]
    )
    stats["leaf_nodes"] = sum(
        1 for node_id in node_id_set if not adjacency[node_id]
    )

    indegree = {
        node_id: len(reverse[node_id]) for node_id in node_id_set
    }
    ready = sorted(
        node_id for node_id, degree in indegree.items() if degree == 0
    )
    cursor = 0
    processed = 0
    while cursor < len(ready):
        node_id = ready[cursor]
        cursor += 1
        processed += 1
        for successor in sorted(adjacency[node_id]):
            indegree[successor] -= 1
            if indegree[successor] == 0:
                ready.append(successor)
    stats["cycle_residual_nodes"] = len(node_id_set) - processed
    stats["has_cycle"] = int(stats["cycle_residual_nodes"] > 0)
    return stats


def _assert_execution_graph_integrity(stats: Counter) -> None:
    failures = {
        name: stats[name]
        for name in (
            "duplicate_node_ids",
            "duplicate_edge_ids",
            "missing_edge_sources",
            "missing_edge_destinations",
            "self_loop_edges",
        )
        if stats[name]
    }
    if failures:
        raise ValueError(
            "invalid execution graph artifact: {}".format(
                ", ".join(
                    "{}={}".format(name, failures[name])
                    for name in sorted(failures)
                )
            )
        )


def export_dependency_tables(
    merged_csv: Path,
    prefix: Path,
):
    rows = read_execution_rows(merged_csv)
    notify_ambiguities: List[dict] = []
    edges = build_execution_edges(rows, notify_ambiguities)
    return export_execution_tables(rows, edges, notify_ambiguities, prefix)


def export_execution_tables(
    rows: List[dict],
    edges: List[dict],
    notify_ambiguities: List[dict],
    prefix: Path,
):
    """Export an already constructed graph through the shared artifact format."""
    graph_stats = analyze_execution_graph(rows, edges)
    _assert_execution_graph_integrity(graph_stats)
    nodes_path = prefix.with_name(prefix.name + "_nodes.csv")
    edges_path = prefix.with_name(prefix.name + "_edges.csv")
    ambiguities_path = prefix.with_name(
        prefix.name + "_notify_ambiguities.csv"
    )
    summary_path = prefix.with_name(prefix.name + "_summary.csv")
    node_fields = ["graph_schema_version", "graph_id"] + list(MERGED_FIELDS)
    node_rows = [
        dict(
            {
                "graph_schema_version": GRAPH_SCHEMA_VERSION,
                "graph_id": row["_graph_id"],
            },
            **{key: row.get(key, "") for key in node_fields[2:]},
        )
        for row in sorted(rows, key=lambda item: item["_graph_id"])
    ]
    edge_counts = Counter(edge["kind"] for edge in edges)
    ambiguity_counts = Counter(
        row["status"] for row in notify_ambiguities
    )
    summary = Counter(graph_stats)
    for kind, count in edge_counts.items():
        summary["edge_kind_{}".format(kind)] = count
    for status, count in ambiguity_counts.items():
        summary["notify_relation_{}".format(status)] = count
    write_csv(str(nodes_path), node_fields, node_rows)
    write_csv(str(edges_path), EDGE_FIELDS, sorted(edges, key=lambda edge: edge["edge_id"]))
    write_csv(
        str(ambiguities_path),
        NOTIFY_AMBIGUITY_FIELDS,
        sorted(
            notify_ambiguities,
            key=lambda row: (
                row.get("relation_id", ""),
                row.get("status", ""),
                row.get("endpoint_graph_ids", ""),
            ),
        ),
    )
    write_csv(
        str(summary_path),
        GRAPH_SUMMARY_FIELDS,
        (
            {"metric": metric, "value": summary[metric]}
            for metric in sorted(summary)
        ),
    )
    return (
        nodes_path,
        edges_path,
        ambiguities_path,
        summary_path,
        edge_counts,
        ambiguity_counts,
        graph_stats,
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
        summary_path,
        counts,
        ambiguity_counts,
        graph_stats,
    ) = export_dependency_tables(args.merged_csv, prefix)
    if __package__ in (None, ""):
        from diagnosis.resource_dependency_graph import (
            export_resource_dependency_tables,
        )
    else:
        from .resource_dependency_graph import (
            export_resource_dependency_tables,
        )
    (
        resource_nodes_path,
        resource_edges_path,
        resource_ambiguities_path,
        resource_summary_path,
        resource_stats,
    ) = export_resource_dependency_tables(nodes_path, edges_path, prefix)
    for kind in PHYSICAL_EDGE_KINDS:
        print(f"{kind}={counts[kind]}")
    for status in (
        NOTIFY_RELATION_SINGLE,
        NOTIFY_RELATION_AMBIGUOUS,
        NOTIFY_RELATION_INCOMPLETE,
        NOTIFY_RELATION_CONFLICT,
    ):
        print(f"notify_relation_{status}={ambiguity_counts[status]}")
    print(f"nodes_csv={nodes_path}")
    print(f"edges_csv={edges_path}")
    print(f"notify_ambiguities_csv={ambiguities_path}")
    for metric in (
        "node_count",
        "edge_count",
        "isolated_nodes",
        "missing_edge_sources",
        "missing_edge_destinations",
        "cycle_residual_nodes",
        "has_cycle",
    ):
        print(f"graph_{metric}={graph_stats[metric]}")
    print(f"summary_csv={summary_path}")
    print(f"resource_nodes_csv={resource_nodes_path}")
    print(f"resource_edges_csv={resource_edges_path}")
    print(f"resource_ambiguities_csv={resource_ambiguities_path}")
    print(f"resource_summary_csv={resource_summary_path}")
    for label, metric in (
        ("resource_task_nodes", "resource_task_nodes"),
        ("resource_boundary_nodes", "boundary_nodes"),
        ("resource_edge_count", "edge_count"),
        ("resource_contraction_ambiguities", "contraction_ambiguities"),
        ("resource_cycle_residual_nodes", "cycle_residual_nodes"),
    ):
        print(f"{label}={resource_stats[metric]}")
    return 1 if (
        ambiguity_counts[NOTIFY_RELATION_CONFLICT]
        or resource_stats["contraction_ambiguities"]
    ) else 0


if __name__ == "__main__":
    raise SystemExit(main())
