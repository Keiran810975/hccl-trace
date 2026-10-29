#!/usr/bin/env python3
"""Preserve vendor batch identities in a NEW consolidated DB, before diagnosis.

Only this capture/export adapter reads the vendor intermediate table. Analysis
continues to consume consolidated DBs read-only. No semantic/injection input is
accepted, and no timestamp or stream-position matching is performed.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import sys

if __package__ in (None, ""):
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from diagnosis.parse_msprof_db import (MsprofDbError, TASK_BATCH_ENCODING,
        TASK_BATCH_TABLE, _readonly_connection, _table_columns, _validate_contract)
else:
    from .parse_msprof_db import (MsprofDbError, TASK_BATCH_ENCODING,
        TASK_BATCH_TABLE, _readonly_connection, _table_columns, _validate_contract)


def sha256(path: Path) -> str:
    result = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            result.update(block)
    return result.hexdigest()


def export_identity(source_db: Path, profile: Path, output: Path) -> dict:
    source_db, profile = source_db.resolve(), profile.resolve()
    if source_db.parent != profile or not profile.name.startswith("PROF_"):
        raise MsprofDbError("source DB must belong to the specified original PROF directory")
    if output.exists() or output.is_symlink() or output.resolve() == source_db:
        raise MsprofDbError("identity export requires a new, non-linked output DB")
    source = _readonly_connection(str(source_db))
    intermediate = None
    created = False
    try:
        _validate_contract(source, str(source_db))
        if _table_columns(source, TASK_BATCH_TABLE):
            raise MsprofDbError("source DB is already identity-enriched")
        devices = [int(r[0]) for r in source.execute("SELECT DISTINCT deviceId FROM TASK")]
        if len(devices) != 1:
            raise MsprofDbError("identity export needs one physical device per DB")
        intermediate_path = profile / ("device_" + str(devices[0])) / "sqlite/hccl_single_device.db"
        intermediate = _readonly_connection(str(intermediate_path))
        required = {"stream_id", "task_id", "context_id", "connection_id", "batch_id", "op_name"}
        if not required <= _table_columns(intermediate, "HCCLTaskSingleDevice"):
            raise MsprofDbError("unsupported vendor HCCLTaskSingleDevice layout")
        lookup = defaultdict(set)
        for row in intermediate.execute("SELECT stream_id,task_id,context_id,connection_id,batch_id,op_name "
                                        "FROM HCCLTaskSingleDevice"):
            stream, task, context, connection, batch = map(int, row[:5])
            if not 0 <= batch <= 65535 or not 0 <= task < 65535:
                raise MsprofDbError("invalid vendor flip/task identity")
            lookup[(stream, task, context, connection)].add((batch, str(row[5])))
        identities, seen, batches = [], set(), defaultdict(int)
        query = """SELECT t.globalTaskId,t.startNs,t.streamId,t.taskId,t.contextId,t.connectionId,s.value
                   FROM TASK t JOIN COMMUNICATION_TASK_INFO c ON c.globalTaskId=t.globalTaskId
                   LEFT JOIN COMMUNICATION_OP o ON o.opId=c.opId
                   LEFT JOIN STRING_IDS s ON s.id=o.opName"""
        for row in source.execute(query):
            key = tuple(int(x) for x in row[2:6])
            candidates = lookup.get(key, set())
            if len(candidates) != 1:
                raise MsprofDbError("missing/ambiguous vendor batch for exact communication task: {!r}".format(key))
            batch, op_name = next(iter(candidates))
            if op_name != str(row[6]):
                raise MsprofDbError("vendor/consolidated operation name mismatch")
            identity = int(row[0]), int(row[1])
            if identity in seen:
                raise MsprofDbError("duplicate consolidated TaskIndex")
            seen.add(identity)
            identities.append((*identity, batch))
            batches[batch] += 1
        if not identities:
            raise MsprofDbError("no authoritative communication batches to export")
        evidence = dict(schema_version=1, encoding=TASK_BATCH_ENCODING,
            source_db=str(source_db), source_sha256=sha256(source_db),
            vendor_db=str(intermediate_path), vendor_sha256=sha256(intermediate_path),
            device_id=devices[0], correlated_tasks=len(identities), batch_counts=dict(batches),
            join_fields=["device", "stream", "task", "context", "connection", "op_name"],
            semantic_input_used=False, temporal_matching_used=False)
        output.parent.mkdir(parents=True, exist_ok=True)
        # Exclusive creation avoids modifying an existing capture on a retry.
        with output.open("xb"):
            created = True
        destination = sqlite3.connect(output)
        try:
            source.backup(destination)
            destination.execute("CREATE TABLE " + TASK_BATCH_TABLE + " (globalTaskId INTEGER NOT NULL, "
                "startNs INTEGER NOT NULL,batchId INTEGER NOT NULL,PRIMARY KEY(globalTaskId,startNs))")
            destination.executemany("INSERT INTO " + TASK_BATCH_TABLE + " VALUES(?,?,?)", identities)
            destination.executemany("INSERT INTO META_DATA(name,value) VALUES(?,?)", [
                ("HCCL_TRACE_TASK_BATCH_SCHEMA", "1"),
                ("HCCL_TRACE_TASK_BATCH_ENCODING", TASK_BATCH_ENCODING),
                ("HCCL_TRACE_TASK_BATCH_PROVENANCE", json.dumps(evidence, sort_keys=True))])
            destination.commit()
        finally:
            destination.close()
        if sha256(source_db) != evidence["source_sha256"] or sha256(intermediate_path) != evidence["vendor_sha256"]:
            raise MsprofDbError("source capture changed during identity export")
        return evidence
    except BaseException:
        if created:
            output.unlink(missing_ok=True)
        raise
    finally:
        source.close()
        if intermediate is not None:
            intermediate.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-db", type=Path, required=True)
    parser.add_argument("--profile", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(export_identity(args.source_db, args.profile, args.output), sort_keys=True))


if __name__ == "__main__":
    main()
