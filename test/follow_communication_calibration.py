"""Local bounded follower: verify backups between experiments without NPU access."""
from __future__ import annotations

import argparse
import fcntl
import json
from pathlib import Path
import subprocess
import time

if __package__:
    from .calibration_offload import SSH, offload
else:
    from calibration_offload import SSH, offload
import shlex


ROOT = "/home/commTeam/zjy/zjy-new-workspace/hccl-diagnose-node03-20261101-200"
ROOTS = (ROOT, ROOT[:-3] + "220")


def snapshot(root=ROOT):
    code = ("import pathlib,json;r=pathlib.Path(" + repr(root) + ");"
            "p=r/'calibration-state.json';d=json.loads(p.read_text()) if p.exists() else dict(status='not_created');"
            "d.pop('source_files',None);print(json.dumps(d))")
    value = subprocess.run(SSH + ["python3 -c " + shlex.quote(code)], capture_output=True, text=True,
                           check=True, timeout=60)
    return json.loads(value.stdout)


def write(path, value):
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(value, indent=2) + "\n")
    temporary.replace(path)


def follow(output, hours, remote_root=ROOT):
    if remote_root not in ROOTS:
        raise ValueError("only reviewed calibration queue directories are accepted")
    output.mkdir(parents=True, exist_ok=True)
    path = output / "follower-state.json"
    deadline = time.monotonic() + hours * 3600
    state = dict(status="following", remote_root=remote_root, backups=[], started_unix_ns=time.time_ns(),
                 never_changes_devices=True, never_stops_other_tasks=True)
    errors = 0
    while time.monotonic() < deadline:
        try:
            remote = snapshot(remote_root)
            errors = 0
        except (OSError, subprocess.SubprocessError, ValueError) as error:
            errors += 1
            state.update(status="connection_retry", error=str(error), consecutive_errors=errors)
            write(path, state)
            if errors >= 3:
                raise RuntimeError("three bounded connection attempts failed; remote queue is not resubmitted") from error
            time.sleep(30)
            continue
        state.update(status="following", last_remote=remote, checked_unix_ns=time.time_ns())
        write(path, state)
        status = remote["status"]
        if status in {"awaiting_verified_archive", "diagnosis_refinement_needed"}:
            name = Path(remote["active_directory"] if status == "awaiting_verified_archive"
                        else remote["attempts"][-1]["directory"]).name
            state.update(status="backing_up", active_backup=name)
            write(path, state)
            receipt = offload(name, output, remove_remote=status == "awaiting_verified_archive")
            state["backups"].append(receipt)
            state.pop("active_backup", None)
            write(path, state)
            if status == "diagnosis_refinement_needed":
                state.update(status="needs_offline_diagnosis_refinement", no_new_capture_started=True)
                write(path, state)
                return state
        elif status in {"stopped", "exploration_complete"}:
            if status == "stopped" and remote.get("active_directory"):
                name = Path(remote["active_directory"]).name
                state.update(status="backing_up_stopped_attempt", active_backup=name)
                write(path, state)
                state["backups"].append(offload(name, output, remove_remote=False))
                state.pop("active_backup", None)
            state.update(status=status, finished_unix_ns=time.time_ns())
            write(path, state)
            return state
        time.sleep(30)
    state.update(status="follower_deadline_reached", finished_unix_ns=time.time_ns(),
                 remote_jobs_not_killed=True)
    write(path, state)
    return state


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--hours", type=float, default=8)
    parser.add_argument("--remote-root", choices=ROOTS, default=ROOT)
    args = parser.parse_args()
    if not 0 < args.hours <= 12:
        parser.error("bounded follower lifetime must be 0..12 hours")
    args.output.mkdir(parents=True, exist_ok=True)
    lock = (args.output / "follower.lock").open("x")
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    try:
        result = follow(args.output, args.hours, args.remote_root)
    except BaseException as error:
        write(args.output / "follower-error.json", dict(error=str(error), unix_ns=time.time_ns(),
            remote_jobs_not_resubmitted=True, no_unverified_data_deleted=True))
        raise
    print(json.dumps(result))


if __name__ == "__main__":
    main()
