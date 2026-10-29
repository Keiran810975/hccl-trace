#!/usr/bin/env python3
"""Parse fine-grained device executions from consolidated msprof SQLite databases."""

from __future__ import annotations

import argparse
import os
import sqlite3
import sys
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import List, Sequence

if __package__ in (None, ""):
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from diagnosis.schema import PROFILER_FIELDS, ProfilerTask, normalize_task_kind, write_csv
else:
    from .schema import PROFILER_FIELDS, ProfilerTask, normalize_task_kind, write_csv


UINT32_MAX = 0xFFFFFFFF
UINT64_MODULUS = 1 << 64
SUPPORTED_DB_SCHEMA_VERSIONS = frozenset(("1.2.0",))
TASK_BATCH_TABLE = "HCCL_TRACE_TASK_BATCH"
TASK_BATCH_ENCODING = "cann-8.5.1-flip16"
REQUIRED_COLUMNS = {
    "META_DATA": ("name", "value"),
    "STRING_IDS": ("id", "value"),
    "TASK": (
        "startNs", "endNs", "deviceId", "connectionId", "globalTaskId",
        "taskType", "contextId", "streamId", "taskId", "modelId",
    ),
    "COMMUNICATION_TASK_INFO": (
        "globalTaskId", "notifyId", "srcRank", "dstRank", "opId",
    ),
    "COMMUNICATION_OP": (
        "opName", "connectionId", "groupName", "opId", "deviceId",
    ),
    "COMPUTE_TASK_INFO": ("name", "globalTaskId"),
}
TASK_KIND_BY_EVENT = {
    "SDMA": "sdma",
    "MEMCPY_ASYNC": "sdma",
    "RDMASEND": "rdma",
    "RDMA_DB_SEND": "rdma",
    "REDUCE_INLINE": "reduce_inline",
    "REDUCE_TBE": "reduce_tbe",
    "NOTIFY_RECORD": "notify_record",
    "WRITE_VALUE": "notify_record",
    "NOTIFY_WAIT": "notify_wait",
    # Device-expanded AI_CPU executions use explicit SQE names in CANN 8.5.1.
    "SDMA_SQE": "sdma",
    "NOTIFY_RECORD_SQE": "notify_record",
    "NOTIFY_WAIT_SQE": "notify_wait",
}


class MsprofDbError(ValueError):
    """Raised when an msprof DB violates the supported input contract."""


def _task_kind(event_name: str) -> str:
    normalized = str(event_name or "").strip().upper().replace("-", "_").replace(" ", "_")
    return TASK_KIND_BY_EVENT.get(normalized, normalize_task_kind(event_name))


def _ns_to_us_text(value: int) -> str:
    sign = "-" if value < 0 else ""
    absolute = abs(value)
    whole, fraction = divmod(absolute, 1000)
    if not fraction:
        return "{}{}".format(sign, whole)
    return "{}{}.{:03d}".format(sign, whole, fraction).rstrip("0")


def _optional_int(value: object, invalid_sentinel: int = -1) -> int:
    if value is None:
        return -1
    parsed = int(value)
    return -1 if parsed == invalid_sentinel else parsed


def _notify_id(value: object) -> int:
    parsed = _optional_int(value)
    if parsed < -1:
        return parsed + UINT64_MODULUS
    return parsed


def _readonly_connection(path: str) -> sqlite3.Connection:
    resolved = Path(path).resolve()
    if not resolved.is_file():
        raise MsprofDbError("msprof DB not found: {!r}".format(str(resolved)))
    uri = "{}?mode=ro".format(resolved.as_uri())
    try:
        connection = sqlite3.connect(uri, uri=True)
    except sqlite3.Error as error:
        raise MsprofDbError(
            "cannot open msprof DB {!r} read-only: {}".format(str(resolved), error)
        ) from error
    connection.row_factory = sqlite3.Row
    return connection


def _table_columns(connection: sqlite3.Connection, table: str) -> set[str]:
    return {str(row["name"]) for row in connection.execute(
        "PRAGMA table_info({})".format(table)
    )}


def _validate_contract(connection: sqlite3.Connection, path: str) -> str:
    tables = {str(row["name"]) for row in connection.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    )}
    for table, required in REQUIRED_COLUMNS.items():
        if table not in tables:
            raise MsprofDbError(
                "unsupported msprof DB {!r}: missing table {}".format(path, table)
            )
        missing = sorted(set(required) - _table_columns(connection, table))
        if missing:
            raise MsprofDbError(
                "unsupported msprof DB {!r}: table {} missing columns {}".format(
                    path, table, ",".join(missing)
                )
            )
    version_row = connection.execute(
        "SELECT value FROM META_DATA WHERE name='SCHEMA_VERSION'"
    ).fetchone()
    version = str(version_row["value"]) if version_row is not None else ""
    if version not in SUPPORTED_DB_SCHEMA_VERSIONS:
        raise MsprofDbError(
            "unsupported msprof DB schema {!r} in {!r}; supported: {}".format(
                version, path, ",".join(sorted(SUPPORTED_DB_SCHEMA_VERSIONS))
            )
        )
    duplicate = connection.execute(
        "SELECT globalTaskId, COUNT(*) AS count "
        "FROM COMMUNICATION_TASK_INFO GROUP BY globalTaskId HAVING COUNT(*) > 1 LIMIT 1"
    ).fetchone()
    if duplicate is not None:
        raise MsprofDbError(
            "ambiguous COMMUNICATION_TASK_INFO in {!r}: globalTaskId {} has {} rows".format(
                path, duplicate["globalTaskId"], duplicate["count"]
            )
        )
    return version


def _task_index(global_task_id: int, start_ns: int) -> str:
    return "{}:{}".format(int(global_task_id), int(start_ns))


def _task_batches(connection: sqlite3.Connection) -> dict[tuple[int, int], int]:
    if not _table_columns(connection, TASK_BATCH_TABLE):
        return {}
    if _table_columns(connection, TASK_BATCH_TABLE) != {"globalTaskId", "startNs", "batchId"}:
        raise MsprofDbError("unsupported exported task batch columns")
    metadata = dict(connection.execute("SELECT name,value FROM META_DATA WHERE name LIKE 'HCCL_TRACE_TASK_BATCH_%'"))
    if (metadata.get("HCCL_TRACE_TASK_BATCH_SCHEMA") != "1"
            or metadata.get("HCCL_TRACE_TASK_BATCH_ENCODING") != TASK_BATCH_ENCODING):
        raise MsprofDbError("unsupported exported task batch schema/encoding")
    batches = {}
    for row in connection.execute("SELECT globalTaskId,startNs,batchId FROM " + TASK_BATCH_TABLE):
        key = int(row[0]), int(row[1])
        batch = int(row[2])
        if key in batches or not 0 <= batch <= 65535:
            raise MsprofDbError("duplicate/invalid exported task batch identity")
        batches[key] = batch
    orphan = connection.execute("SELECT 1 FROM " + TASK_BATCH_TABLE + " b LEFT JOIN TASK t "
        "ON b.globalTaskId=t.globalTaskId AND b.startNs=t.startNs WHERE t.globalTaskId IS NULL LIMIT 1").fetchone()
    if orphan is not None:
        raise MsprofDbError("exported task batch has no exact TASK endpoint")
    missing = connection.execute("SELECT 1 FROM TASK t JOIN COMMUNICATION_TASK_INFO c "
        "ON c.globalTaskId=t.globalTaskId LEFT JOIN " + TASK_BATCH_TABLE + " b "
        "ON b.globalTaskId=t.globalTaskId AND b.startNs=t.startNs "
        "WHERE b.globalTaskId IS NULL LIMIT 1").fetchone()
    if missing is not None:
        raise MsprofDbError("incomplete exported communication task batches")
    return batches


def _device_ids(connection: sqlite3.Connection) -> Sequence[int]:
    return tuple(int(row["deviceId"]) for row in connection.execute(
        "SELECT DISTINCT deviceId FROM TASK ORDER BY deviceId"
    ))


def parse_file(path: str, default_node_id: str = "") -> List[ProfilerTask]:
    """Read one consolidated msprof DB into the shared physical task model."""
    connection = _readonly_connection(path)
    try:
        _validate_contract(connection, path)
        batches = _task_batches(connection)
        device_ids = _device_ids(connection)
        if len(device_ids) != 1:
            raise MsprofDbError(
                "msprof DB {!r} must contain exactly one TASK deviceId, found {}".format(
                    path, list(device_ids)
                )
            )
        has_communication_type = "taskType" in _table_columns(connection, "COMMUNICATION_TASK_INFO")
        size_column = ("communication.size" if "size" in _table_columns(connection, "COMMUNICATION_TASK_INFO") else "NULL")
        communication_type = "communication_type.value" if has_communication_type else "NULL"
        communication_type_join = (
            "LEFT JOIN STRING_IDS AS communication_type ON communication_type.id = communication.taskType"
            if has_communication_type else "")
        rows = connection.execute(
            """
            SELECT
                task.startNs AS start_ns,
                task.endNs AS end_ns,
                task.deviceId AS device_id,
                task.connectionId AS connection_id,
                task.globalTaskId AS global_task_id,
                task.contextId AS context_id,
                task.streamId AS stream_id,
                task.taskId AS task_id,
                task.modelId AS model_id,
                task_type.value AS task_type,
                {communication_type} AS communication_type,
                {size_column} AS size_bytes,
                compute_name.value AS compute_name,
                communication.notifyId AS notify_id,
                communication.srcRank AS src_rank,
                communication.dstRank AS dst_rank,
                operation.opId AS profiler_op_id,
                operation.connectionId AS profiler_op_connection_id,
                op_name.value AS op_name,
                group_name.value AS group_name
            FROM TASK AS task
            JOIN STRING_IDS AS task_type
              ON task_type.id = task.taskType
            LEFT JOIN COMPUTE_TASK_INFO AS compute
              ON compute.globalTaskId = task.globalTaskId
            LEFT JOIN STRING_IDS AS compute_name
              ON compute_name.id = compute.name
            LEFT JOIN COMMUNICATION_TASK_INFO AS communication
              ON communication.globalTaskId = task.globalTaskId
            {communication_type_join}
            LEFT JOIN COMMUNICATION_OP AS operation
              ON operation.opId = communication.opId
            LEFT JOIN STRING_IDS AS op_name
              ON op_name.id = operation.opName
            LEFT JOIN STRING_IDS AS group_name
              ON group_name.id = operation.groupName
            WHERE UPPER(task_type.value) <> 'AI_CORE'
            ORDER BY task.startNs, task.endNs, task.streamId, task.taskId, task.contextId
            """.format(communication_type=communication_type, size_column=size_column,
                       communication_type_join=communication_type_join)
        )
        tasks = []
        for row in rows:
            start_ns = int(row["start_ns"])
            end_ns = max(start_ns, int(row["end_ns"]))
            context_id = int(row["context_id"])
            if context_id == UINT32_MAX:
                context_id = -1
            task_type = str(row["task_type"] or "")
            event_name = str(row["compute_name"] or task_type).strip()
            task_kind = _task_kind(task_type)
            if task_type.upper() == "SDMA_SQE":
                # The same hardware opcode carries memcpy and inline reduction.
                # Size alone cannot distinguish a control counter from a payload.
                task_kind = {"REDUCE_INLINE": "reduce_inline", "MEMCPY": "sdma"}.get(
                    str(row["communication_type"] or "").upper(), task_kind)
            if task_type.upper() == "WRITE_VALUE_SQE":
                # SQE opcode alone conflates Notify writes and RDMA doorbells.
                # Require the same execution's communication profiling subtype.
                task_kind = {"RDMASEND": "rdma", "INTER_RANK_RECORD": "notify_record",
                             "NOTIFY_RECORD": "notify_record"}.get(
                    str(row["communication_type"] or "").upper(), task_kind)
            tasks.append(ProfilerTask(
                node_id=default_node_id,
                device_id=int(row["device_id"]),
                stream_id=int(row["stream_id"]),
                task_id=int(row["task_id"]),
                task_kind=task_kind,
                profiler_size_bytes=_optional_int(row["size_bytes"]),
                task_start=_ns_to_us_text(start_ns),
                task_stop=_ns_to_us_text(end_ns),
                duration=_ns_to_us_text(end_ns - start_ns),
                event_name=event_name,
                subtask_id=context_id,
                connection_id=int(row["connection_id"]),
                model_id=int(row["model_id"]),
                global_task_id=int(row["global_task_id"]),
                batch_id=batches.get((int(row["global_task_id"]), start_ns), -1),
                task_index=_task_index(row["global_task_id"], start_ns),
                op_name=str(row["op_name"] or ""),
                group_name=str(row["group_name"] or ""),
                profiler_op_id=_optional_int(row["profiler_op_id"]),
                profiler_op_connection_id=_optional_int(
                    row["profiler_op_connection_id"]
                ),
                profiler_notify_id=(
                    _notify_id(row["notify_id"])
                ),
                profiler_src_rank=_optional_int(row["src_rank"], UINT32_MAX),
                profiler_dst_rank=_optional_int(row["dst_rank"], UINT32_MAX),
            ))
        if not tasks:
            raise MsprofDbError(
                "msprof DB {!r} contains no target physical TASK rows".format(path)
            )
        return tasks
    except sqlite3.Error as error:
        raise MsprofDbError(
            "failed to parse msprof DB {!r}: {}".format(path, error)
        ) from error
    finally:
        connection.close()


def discover_db_files(path: str) -> List[Path]:
    """Find consolidated msprof_*.db files under a PROF directory or its parent."""
    root = Path(path)
    if not root.exists():
        raise MsprofDbError("msprof DB input not found: {!r}".format(path))
    if root.is_file():
        return [root.resolve()]
    files = sorted(candidate.resolve() for candidate in root.rglob("msprof_*.db"))
    if not files:
        raise MsprofDbError(
            "no consolidated msprof_*.db found under {!r}".format(path)
        )
    return files


@dataclass(frozen=True)
class ProfilerOperation:
    node_id: str
    device_id: int
    group_name: str
    op_name: str
    op_id: int
    start_ns: int
    end_ns: int


def parse_operations(path: str, node_id: str = "") -> List[ProfilerOperation]:
    """Read actual COMMUNICATION_OP intervals; never infer from child tasks."""
    operations = []
    identities = set()
    seen_devices = set()
    for db in discover_db_files(path):
        connection = _readonly_connection(str(db))
        try:
            _validate_contract(connection, str(db))
            devices = _device_ids(connection)
            if len(devices) != 1 or devices[0] in seen_devices:
                raise MsprofDbError("operation input requires unique per-device DBs")
            seen_devices.add(devices[0])
            if not {"startNs", "endNs"} <= _table_columns(connection, "COMMUNICATION_OP"):
                continue  # Older minimal inputs have no operation timing evidence.
            for row in connection.execute(
                "SELECT o.*, g.value AS group_name, n.value AS op_name FROM COMMUNICATION_OP o "
                "JOIN STRING_IDS g ON g.id=o.groupName JOIN STRING_IDS n ON n.id=o.opName"
            ):
                key = (int(row["deviceId"]), row["group_name"], row["op_name"])
                if key in identities or key[0] != devices[0] or not all(key[1:]):
                    raise MsprofDbError("ambiguous operation timing identity: {!r}".format(key))
                identities.add(key)
                start, end = int(row["startNs"]), int(row["endNs"])
                if end < start:
                    raise MsprofDbError("operation end precedes start: {!r}".format(key))
                operations.append(ProfilerOperation(node_id, *key, int(row["opId"]), start, end))
        finally:
            connection.close()
    return operations


COMMUNICATION_DETAIL_FIELDS = ("graph_id", "node_id", "device_id", "stream_id", "task_id", "subtask_id",
    "connection_id", "start_ns", "end_ns", "submission_or_task_duration_ns", "src_rank", "dst_rank",
    "transport_type", "rdma_type", "size_bytes", "reported_bandwidth_bytes_per_s",
    "bandwidth_derived_duration_ns", "duration_evidence", "hardware_completion_ns")


def parse_communication_details(path: str, node_id: str = "") -> List[dict]:
    """Read real per-task communication metadata; never divide by SQE duration."""
    if __package__ in (None, ""):
        from diagnosis.dependency_model import ExecutionIdentity
    else:
        from .dependency_model import ExecutionIdentity
    result, identities = [], set()
    for db_path in discover_db_files(path):
        connection = _readonly_connection(str(db_path))
        try:
            _validate_contract(connection, str(db_path))
            columns = _table_columns(connection, "COMMUNICATION_TASK_INFO")
            if not {"transportType", "rdmaType", "size", "bandwidth"} <= columns:
                continue  # Old fixtures/captures do not contain these optional facts.
            enums = {}
            for field, table in (("transport_type", "ENUM_HCCL_TRANSPORT_TYPE"), ("rdma_type", "ENUM_HCCL_RDMA_TYPE")):
                if connection.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone():
                    values = connection.execute("SELECT * FROM " + table).fetchall()
                    if any(len(row) != 2 for row in values):
                        raise MsprofDbError("unsupported communication enum layout")
                    enums[field] = {int(row[0]): str(row[1]) for row in values}
                else:
                    enums[field] = {}
            records = connection.execute("SELECT t.*,c.srcRank,c.dstRank,c.transportType,c.rdmaType,c.size,"
                "CAST(c.bandwidth AS TEXT) AS bandwidth FROM TASK t "
                "JOIN COMMUNICATION_TASK_INFO c ON t.globalTaskId=c.globalTaskId ORDER BY t.startNs,t.taskId")
            for row in records:
                if int(row["endNs"]) < int(row["startNs"]):
                    raise MsprofDbError("communication task end precedes start")
                context = int(row["contextId"])
                context = -1 if context == UINT32_MAX else context
                identity = ExecutionIdentity(node_id, int(row["deviceId"]), int(row["streamId"]),
                    int(row["taskId"]), context, int(row["connectionId"]),
                    _task_index(row["globalTaskId"], row["startNs"])).stable_id
                if identity in identities:
                    raise MsprofDbError("duplicate physical communication task identity")
                identities.add(identity)
                size = _optional_int(row["size"])
                bandwidth = "" if row["bandwidth"] is None else str(row["bandwidth"])
                transport = enums["transport_type"].get(_optional_int(row["transportType"]), "unknown")
                rdma = enums["rdma_type"].get(_optional_int(row["rdmaType"]), "unknown")
                estimate = None
                try:
                    value = Decimal(bandwidth) if bandwidth else Decimal(0)
                    if size > 0 and value.is_finite() and value > 0 and rdma == "RDMA_SEND_PAYLOAD":
                        estimate = str(Decimal(size) * 1000000000 / value)
                except InvalidOperation:
                    raise MsprofDbError("invalid reported communication bandwidth")
                result.append(dict(graph_id=identity, node_id=node_id, device_id=int(row["deviceId"]),
                    stream_id=int(row["streamId"]), task_id=int(row["taskId"]), subtask_id=context,
                    connection_id=int(row["connectionId"]), start_ns=int(row["startNs"]), end_ns=int(row["endNs"]),
                    submission_or_task_duration_ns=int(row["endNs"]) - int(row["startNs"]),
                    src_rank=_optional_int(row["srcRank"], UINT32_MAX), dst_rank=_optional_int(row["dstRank"], UINT32_MAX),
                    transport_type=transport, rdma_type=rdma, size_bytes=size,
                    reported_bandwidth_bytes_per_s=bandwidth, bandwidth_derived_duration_ns=estimate,
                    duration_evidence="size/reported_bandwidth_estimate" if estimate is not None else "not_available",
                    hardware_completion_ns=None))
        finally:
            connection.close()
    return result


def parse_inputs(
    msprof_db: str = "",
    msprof_db_dir: str = "",
    default_node_id: str = "",
) -> List[ProfilerTask]:
    if bool(msprof_db) == bool(msprof_db_dir):
        raise MsprofDbError(
            "exactly one of msprof_db or msprof_db_dir must be provided"
        )
    paths = discover_db_files(msprof_db or msprof_db_dir)
    tasks: List[ProfilerTask] = []
    seen_devices = {}
    for path in paths:
        parsed = parse_file(str(path), default_node_id)
        device_id = parsed[0].device_id if parsed else -1
        if device_id in seen_devices:
            raise MsprofDbError(
                "duplicate device {} in msprof DB inputs {!r} and {!r}".format(
                    device_id, str(seen_devices[device_id]), str(path)
                )
            )
        seen_devices[device_id] = path
        tasks.extend(parsed)
    return tasks


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Parse fine-grained device executions from consolidated msprof SQLite DB."
    )
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--msprof-db", help="One consolidated msprof_*.db file.")
    source.add_argument(
        "--msprof-db-dir",
        help="Directory containing one or more PROF_*/msprof_*.db files.",
    )
    parser.add_argument("-o", "--output", required=True)
    parser.add_argument("--node-id", default="")
    args = parser.parse_args()
    try:
        tasks = parse_inputs(
            args.msprof_db or "", args.msprof_db_dir or "", args.node_id)
    except MsprofDbError as error:
        parser.error(str(error))
    write_csv(args.output, list(PROFILER_FIELDS), (task.to_row() for task in tasks))
    print("profiler_tasks={}".format(len(tasks)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
