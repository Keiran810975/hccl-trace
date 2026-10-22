#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

import argparse
import csv
import json
import shutil
import sqlite3
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build deterministic HCCL trace quality cases.")
    parser.add_argument("--baseline-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--drop-count", type=int, default=12)
    parser.add_argument("--operation-occurrence", type=int, default=1)
    return parser.parse_args()


def copy_raw_case(baseline: Path, destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=False)
    shutil.copytree(baseline / "plog", destination / "plog")
    shutil.copytree(baseline / "msprof", destination / "msprof")


def read_merged(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def matching_rows(rows: list[dict[str, str]], occurrence: int) -> list[dict[str, str]]:
    scopes = []
    for row in rows:
        scope = row.get("profiler_op_scope", "")
        if scope and scope not in scopes:
            scopes.append(scope)
    if occurrence < 0 or occurrence >= len(scopes):
        raise ValueError(f"operation occurrence {occurrence} is outside 0..{len(scopes) - 1}")
    scope = scopes[occurrence]
    return [
        row
        for row in rows
        if row.get("match_status") == "matched"
        and row.get("profiler_op_scope") == scope
    ]


def find_database(msprof_dir: Path, device_id: int) -> Path:
    candidates = []
    for path in msprof_dir.rglob("msprof_*.db"):
        with sqlite3.connect(f"file:{path}?mode=ro", uri=True) as connection:
            devices = {int(row[0]) for row in connection.execute("SELECT DISTINCT deviceId FROM TASK")}
        if device_id in devices:
            candidates.append(path)
    if len(candidates) != 1:
        raise ValueError(f"expected one DB for device {device_id}, got {candidates}")
    return candidates[0]


def drop_plog_rows(case_dir: Path, count: int) -> list[str]:
    removed = []
    remaining = count
    for path in sorted((case_dir / "plog").rglob("plog*.log")):
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines(keepends=True)
        output = []
        for line in lines:
            if remaining and "[HcclTaskSemantic]" in line:
                removed.append(line.rstrip("\n"))
                remaining -= 1
            else:
                output.append(line)
        path.write_text("".join(output), encoding="utf-8")
        if remaining == 0:
            break
    if remaining:
        raise ValueError(f"only found {count - remaining} semantic rows to remove")
    return removed


def drop_profiler_tasks(case_dir: Path, rows: list[dict[str, str]], count: int) -> list[dict[str, str]]:
    selected = [row for row in rows if row.get("ffts_ctx_id") in ("", "-1")][:count]
    if len(selected) != count:
        raise ValueError(f"only found {len(selected)} matched direct tasks to delete")
    by_device: dict[int, list[dict[str, str]]] = {}
    for row in selected:
        by_device.setdefault(int(row["device_id"]), []).append(row)
    for device_id, device_rows in by_device.items():
        database = find_database(case_dir / "msprof", device_id)
        with sqlite3.connect(database) as connection:
            for row in device_rows:
                connection.execute(
                    "DELETE FROM TASK WHERE deviceId=? AND streamId=? AND taskId=?",
                    (device_id, int(row["profiler_stream_id"]), int(row["profiler_task_id"])),
                )
            connection.commit()
    return selected


def change_task_kind(case_dir: Path, rows: list[dict[str, str]]) -> dict[str, str]:
    selected = next(
        row
        for row in rows
        if int(row.get("ffts_ctx_id") or -1) >= 0
        and row.get("task_kind") in ("sdma", "reduce", "reduce_inline")
    )
    device_id = int(selected["device_id"])
    database = find_database(case_dir / "msprof", device_id)
    with sqlite3.connect(database) as connection:
        task_type = connection.execute(
            "SELECT id FROM STRING_IDS WHERE value='Notify Wait' ORDER BY id LIMIT 1"
        ).fetchone()
        if task_type is None:
            raise ValueError(f"Notify Wait string id is missing in {database}")
        cursor = connection.execute(
            "UPDATE TASK SET taskType=? WHERE deviceId=? AND streamId=? AND taskId=? AND contextId=?",
            (
                int(task_type[0]),
                device_id,
                int(selected["profiler_stream_id"]),
                int(selected["profiler_task_id"]),
                int(selected["ffts_ctx_id"]),
            ),
        )
        if cursor.rowcount != 1:
            raise ValueError(f"expected one TASK update, got {cursor.rowcount}")
        connection.commit()
    return selected


def compact_row(row: dict[str, str]) -> dict[str, str]:
    keys = (
        "device_id",
        "user_rank",
        "phase",
        "step",
        "event",
        "task_kind",
        "ffts_ctx_id",
        "profiler_stream_id",
        "profiler_task_id",
        "profiler_op_scope",
    )
    return {key: row.get(key, "") for key in keys}


def main() -> int:
    args = parse_args()
    rows = matching_rows(
        read_merged(args.baseline_dir / "diagnosis" / "merged.csv"),
        args.operation_occurrence,
    )
    cases = {
        "plog_missing": args.output_dir / "plog_missing",
        "profiler_missing": args.output_dir / "profiler_missing",
        "kind_mismatch": args.output_dir / "kind_mismatch",
    }
    for path in cases.values():
        copy_raw_case(args.baseline_dir, path)

    removed_plog = drop_plog_rows(cases["plog_missing"], args.drop_count)
    removed_tasks = drop_profiler_tasks(cases["profiler_missing"], rows, args.drop_count)
    changed_task = change_task_kind(cases["kind_mismatch"], rows)
    manifest = {
        "plog_missing": {"removed_semantic_rows": len(removed_plog)},
        "profiler_missing": {
            "removed_profiler_tasks": [compact_row(row) for row in removed_tasks]
        },
        "kind_mismatch": {
            "changed_from": compact_row(changed_task),
            "changed_to_profiler_kind": "notify_wait",
        },
    }
    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(manifest, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
