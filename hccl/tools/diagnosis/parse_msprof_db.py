#!/usr/bin/env python3
"""Parse fine-grained device executions from consolidated msprof SQLite databases."""

from __future__ import annotations

import argparse
import os
import sqlite3
import sys
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


def _device_ids(connection: sqlite3.Connection) -> Sequence[int]:
    return tuple(int(row["deviceId"]) for row in connection.execute(
        "SELECT DISTINCT deviceId FROM TASK ORDER BY deviceId"
    ))


def parse_file(path: str, default_node_id: str = "") -> List[ProfilerTask]:
    """Read one consolidated msprof DB into the shared physical task model."""
    connection = _readonly_connection(path)
    try:
        _validate_contract(connection, path)
        device_ids = _device_ids(connection)
        if len(device_ids) != 1:
            raise MsprofDbError(
                "msprof DB {!r} must contain exactly one TASK deviceId, found {}".format(
                    path, list(device_ids)
                )
            )
        has_communication_type = "taskType" in _table_columns(connection, "COMMUNICATION_TASK_INFO")
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
            """.format(communication_type=communication_type,
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
                task_start=_ns_to_us_text(start_ns),
                task_stop=_ns_to_us_text(end_ns),
                duration=_ns_to_us_text(end_ns - start_ns),
                event_name=event_name,
                subtask_id=context_id,
                connection_id=int(row["connection_id"]),
                model_id=int(row["model_id"]),
                global_task_id=int(row["global_task_id"]),
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
