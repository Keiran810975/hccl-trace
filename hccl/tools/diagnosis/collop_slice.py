"""Extract one bound collective and optional local context from an msprof snapshot."""

from __future__ import annotations

from contextlib import closing
from pathlib import Path
import json
import re
import shutil
import sqlite3
import stat
import subprocess
from tempfile import TemporaryDirectory
import time

from .parse_msprof_db import SUPPORTED_DB_SCHEMA_VERSIONS, _readonly_connection


PHASES = {"s1-upstream": 1, "s2-internal": 0, "s2-downstream": 30}
NS_PER_SECOND = 10**9
MAX_SNAPSHOT_BYTES = 192 * 1024**2
TASK_FIELDS = """t.deviceId AS device_id, t.streamId AS stream_id, t.taskId AS task_id,
    t.contextId AS context_id, t.connectionId AS connection_id, t.globalTaskId AS global_task_id,
    t.startNs AS start_ns, t.endNs AS stop_ns, s.value AS event_name"""


def add_arguments(parser):
    parser.add_argument("source", type=Path, help="closed msprof DB or a raw PROF_* directory")
    parser.add_argument("--phase", choices=PHASES, required=True)
    parser.add_argument("--device-id", type=int, required=True, help="profiler device ID, not Rank")
    parser.add_argument("--group-name", required=True, help="exact group name in COMMUNICATION_OP")
    parser.add_argument("--op-name", required=True, help="exact invocation name in COMMUNICATION_OP")
    parser.add_argument("--delay-seconds", type=int,
                        help="wait before copying a raw capture (default: 30; DB input: 0)")
    parser.add_argument("--context-seconds", type=int,
                        help="device-local context width (defaults: S1 1s before, S2 30s after)")


def _task_rows(db, sql, parameters):
    rows = [dict(r) for r in db.execute(sql, parameters)]
    identities = set()
    for row in rows:
        if any(row[k] is None for k in ("global_task_id", "start_ns", "stop_ns", "event_name")):
            raise ValueError("snapshot contains an incomplete Task record")
        key = row["global_task_id"], row["start_ns"]
        if key in identities or row["stop_ns"] < row["start_ns"]:
            raise ValueError("snapshot contains duplicate or backwards Task executions")
        identities.add(key)
    return rows


def extract(path, *, phase, device_id, group_name, op_name, context_seconds=None):
    seconds = PHASES[phase] if context_seconds is None else context_seconds
    if not group_name.strip() or not op_name.strip():
        raise ValueError("collective identity must be non-empty")
    if device_id < 0 or not 0 <= seconds <= 60 or (phase == "s2-internal") != (seconds == 0):
        raise ValueError("invalid device or context: use 0 for S2 internal and 1-60 seconds for context")
    result = dict(schema_version=1, phase=phase, group_name=group_name,
                  op_name=op_name, device_id=device_id, coverage_verified=False,
                  timing_domain="same_profiler_device",
                  operation=None, context_window_ns=None, tasks=[], context_tasks=[])
    try:
        with closing(_readonly_connection(str(path))) as db:
            version = db.execute("SELECT value FROM META_DATA WHERE name='SCHEMA_VERSION'").fetchone()
            if version is None or str(version[0]) not in SUPPORTED_DB_SCHEMA_VERSIONS:
                raise ValueError("unsupported msprof DB schema")
            ops = db.execute("""SELECT o.opId, o.startNs, o.endNs FROM COMMUNICATION_OP o
                JOIN STRING_IDS g ON g.id=o.groupName JOIN STRING_IDS n ON n.id=o.opName
                WHERE o.deviceId=? AND g.value=? AND n.value=?""", (device_id, group_name, op_name)).fetchall()
            if not ops:
                return dict(result, status="target_not_available")
            if len(ops) != 1:
                raise ValueError("operation identity is not unique in the snapshot")
            op_id, start, stop = ops[0]
            if start is None or stop is None or stop <= start:
                return dict(result, status="operation_interval_not_available")
            result["operation"] = dict(start_ns=start, stop_ns=stop)
            result["tasks"] = _task_rows(db, f"""SELECT {TASK_FIELDS}, c.notifyId AS notify_id,
                c.srcRank AS src_rank, c.dstRank AS dst_rank
                FROM COMMUNICATION_TASK_INFO c JOIN TASK t ON t.globalTaskId=c.globalTaskId
                LEFT JOIN STRING_IDS s ON s.id=t.taskType WHERE c.opId=? AND t.deviceId=?
                ORDER BY t.startNs, t.streamId, t.taskId""", (op_id, device_id))
            if seconds:
                extent = seconds * NS_PER_SECOND
                begin, end = (start-extent, start) if phase == "s1-upstream" else (stop, stop+extent)
                result["context_window_ns"] = [begin, end]
                result["context_tasks"] = _task_rows(db, f"""SELECT {TASK_FIELDS}
                    FROM TASK t LEFT JOIN STRING_IDS s ON s.id=t.taskType WHERE t.deviceId=?
                    AND t.startNs<? AND (t.endNs>? OR (t.startNs=t.endNs AND t.startNs=?))
                    ORDER BY t.startNs, t.streamId, t.taskId""", (device_id, end, begin, begin))
    except sqlite3.Error as error:
        raise ValueError(f"cannot read collective snapshot: {error}") from error
    return dict(result, status="observed_not_certified_complete" if result["tasks"] else "tasks_not_available")


def _raw_inventory(root):
    files = {}
    total = 0
    for folder in root.iterdir():
        if folder.name != "host" and not re.fullmatch(r"device_\d+", folder.name):
            continue
        if folder.is_symlink() or not folder.is_dir():
            raise ValueError("expected an ordinary raw profile directory")
        paths = list(folder.iterdir())
        data = folder/"data"
        if data.is_symlink():
            raise ValueError("snapshot data must not be a symbolic link")
        if data.is_dir():
            paths.extend(data.rglob("*"))
        for path in paths:
            meta = path.lstat()
            if stat.S_ISDIR(meta.st_mode):
                continue
            if not stat.S_ISREG(meta.st_mode):
                raise ValueError("snapshot sources must be ordinary files")
            total += meta.st_size
            if total > MAX_SNAPSHOT_BYTES:
                raise ValueError("raw profile snapshot exceeds the 192 MiB trial limit")
            files[path.relative_to(root)] = (meta.st_ino, meta.st_size, meta.st_mtime_ns)
    return files


def _export_slice(source, options):
    if not source.name.startswith("PROF_") or source.is_symlink():
        raise ValueError("raw input must be a PROF_* directory")
    with TemporaryDirectory(prefix="hccl-collop-") as directory:
        snapshot = Path(directory)/source.name
        inventory = _raw_inventory(source)
        if not inventory:
            raise ValueError("raw profile data are not yet available")
        for name, (_, size, _) in inventory.items():
            dest = snapshot/name
            dest.parent.mkdir(parents=True, exist_ok=True)
            with (source/name).open("rb") as stream, dest.open("xb") as output:
                remaining = size
                while remaining:
                    chunk = stream.read(min(remaining, 1024**2))
                    if not chunk:
                        raise ValueError("raw profile changed while copying; retry with a stable snapshot")
                    output.write(chunk)
                    remaining -= len(chunk)
        if inventory != _raw_inventory(source):
            raise ValueError("raw profile changed while copying; retry with a stable snapshot")
        msprof = shutil.which("msprof")
        if msprof is None:
            raise ValueError("msprof is unavailable; load the CANN environment or supply a DB")
        try:
            completed = subprocess.run(
                ["timeout", "--signal=TERM", "--kill-after=5s", "60s", msprof,
                 "--export=on", "--type=db", f"--output={snapshot}"],
                capture_output=True, text=True, check=False)
        except FileNotFoundError as error:
            raise ValueError("raw profile export requires GNU timeout; use a closed DB on other hosts") from error
        if completed.returncode:
            raise ValueError(f"msprof snapshot export failed ({completed.returncode}): "
                             + (completed.stderr or completed.stdout)[-1000:].strip())
        dbs = list(snapshot.glob("msprof_*.db"))
        if len(dbs) != 1:
            raise ValueError("msprof did not produce exactly one snapshot DB")
        return extract(dbs[0], **options)


def run(args):
    raw = args.source.is_dir()
    delay = args.delay_seconds if args.delay_seconds is not None else (30 if raw else 0)
    if not 0 <= delay <= 300:
        raise ValueError("delay must be in 0..300 seconds")
    options = {key: getattr(args, key) for key in ("phase", "group_name", "op_name", "device_id", "context_seconds")}
    start = time.monotonic()
    time.sleep(delay)
    result = _export_slice(args.source, options) if raw else extract(args.source, **options)
    result.update(wait_before_read_seconds=delay, elapsed_seconds=time.monotonic()-start)
    print(json.dumps(result, ensure_ascii=False))
    return 0
