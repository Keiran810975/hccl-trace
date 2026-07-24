#!/usr/bin/env python3
"""Stable identities and evidence vocabulary for dependency graph artifacts."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Iterable


GRAPH_SCHEMA_VERSION = 4

OPERATION_SCOPE_UNIQUE = "unique"
OPERATION_SCOPE_MISSING = "missing"
OPERATION_SCOPE_AMBIGUOUS = "ambiguous"

NOTIFY_ROLE_PRODUCER = "producer"
NOTIFY_ROLE_CONSUMER = "consumer"
NOTIFY_RANK_DOMAIN_USER = "user"
NOTIFY_RANK_DOMAIN_DEVICE_LOCAL = "device_local"

NOTIFY_SIGNAL_ACK = "ack"
NOTIFY_SIGNAL_DATA = "data_signal"

NOTIFY_SEQUENCE_FFTS_GRAPH = "ffts_graph_instance"
NOTIFY_SEQUENCE_PROTOCOL = "protocol_sequence"
NOTIFY_SEQUENCE_TOKEN = "dependency_token"
NOTIFY_SEQUENCE_DB_ORDINAL = "db_notify_ordinal"
NOTIFY_SEQUENCE_DB_LOCAL_ORDINAL = "db_local_notify_ordinal"

NOTIFY_RELATION_UNIQUE = "unique"
NOTIFY_RELATION_SINGLE = "single"
NOTIFY_RELATION_AMBIGUOUS = "ambiguous"
NOTIFY_RELATION_INCOMPLETE = "incomplete"
NOTIFY_RELATION_CONFLICT = "conflict"

NOTIFY_ENDPOINT_RULES = {
    ("notify_record", "tx_ack_start"): (
        NOTIFY_ROLE_PRODUCER,
        NOTIFY_SIGNAL_ACK,
    ),
    ("notify_wait", "rx_ack_start"): (
        NOTIFY_ROLE_CONSUMER,
        NOTIFY_SIGNAL_ACK,
    ),
    ("notify_record", "tx_data_signal_start"): (
        NOTIFY_ROLE_PRODUCER,
        NOTIFY_SIGNAL_DATA,
    ),
    # Direct AllGather uses a Notify record to publish payload readiness.
    ("notify_record", "tx_payload_start"): (
        NOTIFY_ROLE_PRODUCER,
        NOTIFY_SIGNAL_DATA,
    ),
    ("notify_wait", "rx_data_signal_start"): (
        NOTIFY_ROLE_CONSUMER,
        NOTIFY_SIGNAL_DATA,
    ),
}


def stable_id(prefix: str, parts: Iterable[object]) -> str:
    """Return a compact deterministic ID without exposing raw operation names."""
    payload = json.dumps(
        [str(part) for part in parts],
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    return "{}_{}".format(prefix, hashlib.sha256(payload).hexdigest()[:24])


@dataclass(frozen=True)
class ExecutionIdentity:
    """Single-node physical execution identity.

    Timing and CSV position are deliberately excluded: both are observations of
    an execution, not its identity.
    """

    node_id: str
    device_id: int
    stream_id: int
    task_id: int
    subtask_id: int
    connection_id: int

    @property
    def stable_id(self) -> str:
        return stable_id(
            "x",
            (
                self.node_id,
                self.device_id,
                self.stream_id,
                self.task_id,
                self.subtask_id,
                self.connection_id,
            ),
        )


@dataclass(frozen=True)
class DependencyEdgeIdentity:
    """Stable execution-graph edge identity, independent of export order."""

    kind: str
    src_graph_id: str
    dst_graph_id: str
    relation_id: str = ""

    @property
    def stable_id(self) -> str:
        return stable_id(
            "e",
            (
                GRAPH_SCHEMA_VERSION,
                self.kind,
                self.src_graph_id,
                self.dst_graph_id,
                self.relation_id,
            ),
        )


@dataclass(frozen=True)
class OperationScopeIdentity:
    """Collective invocation identity from msprof operation metadata."""

    group_name: str
    op_name: str

    @property
    def stable_id(self) -> str:
        return stable_id(
            "op",
            (self.group_name, self.op_name),
        )


@dataclass(frozen=True)
class NotifyResourceIdentity:
    """Reusable Notify storage identity, deliberately not a relation identity."""

    node_id: str
    notify_id: int

    @property
    def stable_id(self) -> str:
        return stable_id("notify", (self.node_id, self.notify_id))


@dataclass(frozen=True)
class DirectNotifyChannelIdentity:
    """One cross-rank direct Notify resource within a collective invocation."""

    node_id: str
    operation_scope: str
    producer_rank: int
    consumer_rank: int
    notify_id: int

    @property
    def missing_fields(self) -> tuple[str, ...]:
        missing = []
        for name in ("node_id", "operation_scope"):
            if not str(getattr(self, name) or "").strip():
                missing.append(name)
        for name in ("producer_rank", "consumer_rank", "notify_id"):
            if int(getattr(self, name)) < 0:
                missing.append(name)
        return tuple(missing)

    @property
    def complete(self) -> bool:
        return not self.missing_fields

    @property
    def stable_id(self) -> str:
        return stable_id(
            "dnc",
            (
                GRAPH_SCHEMA_VERSION,
                self.node_id,
                self.operation_scope,
                NOTIFY_RANK_DOMAIN_USER,
                self.producer_rank,
                self.consumer_rank,
                self.notify_id,
            ),
        )


@dataclass(frozen=True)
class DirectNotifyRelationIdentity:
    """One direct Notify state transition, derived from complete DB sequences."""

    channel: DirectNotifyChannelIdentity
    ordinal: int

    @property
    def stable_id(self) -> str:
        return stable_id(
            "dnr",
            (
                GRAPH_SCHEMA_VERSION,
                self.channel.stable_id,
                NOTIFY_SEQUENCE_DB_ORDINAL,
                self.ordinal,
            ),
        )


@dataclass(frozen=True)
class LocalNotifyChannelIdentity:
    """One device-local Notify resource within a collective invocation."""

    node_id: str
    operation_scope: str
    device_id: int
    notify_id: int

    @property
    def missing_fields(self) -> tuple[str, ...]:
        missing = []
        for name in ("node_id", "operation_scope"):
            if not str(getattr(self, name) or "").strip():
                missing.append(name)
        for name in ("device_id", "notify_id"):
            if int(getattr(self, name)) < 0:
                missing.append(name)
        return tuple(missing)

    @property
    def complete(self) -> bool:
        return not self.missing_fields

    @property
    def stable_id(self) -> str:
        return stable_id(
            "lnc",
            (
                GRAPH_SCHEMA_VERSION,
                self.node_id,
                self.operation_scope,
                NOTIFY_RANK_DOMAIN_DEVICE_LOCAL,
                self.device_id,
                self.notify_id,
            ),
        )


@dataclass(frozen=True)
class LocalNotifyRelationIdentity:
    """One device-local Notify state transition from DB-side ordinals."""

    channel: LocalNotifyChannelIdentity
    ordinal: int

    @property
    def stable_id(self) -> str:
        return stable_id(
            "lnr",
            (
                GRAPH_SCHEMA_VERSION,
                self.channel.stable_id,
                NOTIFY_SEQUENCE_DB_LOCAL_ORDINAL,
                self.ordinal,
            ),
        )


@dataclass(frozen=True)
class NotifyRelationIdentity:
    """One logical producer-to-consumer synchronization occurrence."""

    node_id: str
    operation_scope: str
    rank_domain: str
    producer_rank: int
    consumer_rank: int
    signal_kind: str
    phase: str
    step: int
    slice_id: int
    notify_id: int
    sequence_kind: str
    sequence_value: str

    @property
    def resource(self) -> NotifyResourceIdentity:
        return NotifyResourceIdentity(self.node_id, self.notify_id)

    @property
    def missing_fields(self) -> tuple[str, ...]:
        missing = []
        for name in (
            "node_id",
            "operation_scope",
            "rank_domain",
            "signal_kind",
            "phase",
            "sequence_kind",
            "sequence_value",
        ):
            if not str(getattr(self, name) or "").strip():
                missing.append(name)
        for name in ("producer_rank", "consumer_rank", "step", "slice_id", "notify_id"):
            if int(getattr(self, name)) < 0:
                missing.append(name)
        if self.signal_kind not in (NOTIFY_SIGNAL_ACK, NOTIFY_SIGNAL_DATA):
            missing.append("signal_kind")
        if self.rank_domain != NOTIFY_RANK_DOMAIN_USER:
            missing.append("rank_domain")
        if self.sequence_kind not in (
            NOTIFY_SEQUENCE_FFTS_GRAPH,
            NOTIFY_SEQUENCE_PROTOCOL,
            NOTIFY_SEQUENCE_TOKEN,
        ):
            missing.append("sequence_kind")
        elif self.sequence_kind in (
            NOTIFY_SEQUENCE_FFTS_GRAPH,
            NOTIFY_SEQUENCE_PROTOCOL,
        ):
            try:
                if int(self.sequence_value) < 0:
                    missing.append("sequence_value")
            except (TypeError, ValueError):
                missing.append("sequence_value")
        return tuple(dict.fromkeys(missing))

    @property
    def complete(self) -> bool:
        return not self.missing_fields

    @property
    def stable_id(self) -> str:
        return stable_id(
            "nr",
            (
                GRAPH_SCHEMA_VERSION,
                self.node_id,
                self.operation_scope,
                self.rank_domain,
                self.producer_rank,
                self.consumer_rank,
                self.signal_kind,
                self.phase,
                self.step,
                self.slice_id,
                self.notify_id,
                self.sequence_kind,
                self.sequence_value,
            ),
        )


def normalize_notify_endpoint(
    task_kind: str,
    event: str,
    user_rank: int,
    peer_rank: int,
):
    """Return ``(role, producer, consumer, signal)`` for a Notify endpoint."""
    rule = NOTIFY_ENDPOINT_RULES.get((
        str(task_kind or "").strip().lower(),
        str(event or "").strip().lower(),
    ))
    if rule is None or user_rank < 0 or peer_rank < 0:
        return None
    role, signal_kind = rule
    if role == NOTIFY_ROLE_PRODUCER:
        producer_rank, consumer_rank = user_rank, peer_rank
    else:
        producer_rank, consumer_rank = peer_rank, user_rank
    return role, producer_rank, consumer_rank, signal_kind
