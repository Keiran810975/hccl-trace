"""Capture exactly one immutable communication intervention, with no data cleanup."""
from __future__ import annotations

import argparse
import fcntl
import json
from pathlib import Path
import socket
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parent))

from communication_calibration import cases
from run_communication_calibration import prepare_attempt, protected_run, inspect_case
from run_node03_anomalies import resources, source_hashes
from run_node03_preflight import LOCAL_PARENT, PEER_PARENT, execute, ssh, write
import shlex


def run(root):
    if root.parent != LOCAL_PARENT or socket.gethostname().split(".")[0] != "liteserver-560t-0":
        raise ValueError("only the reviewed owned Node0 workspace is accepted")
    if root.name != "hccl-diagnose-node03-20261101-230":
        raise ValueError("this one-shot capture has a fixed fresh directory")
    path = root / "fixed-trace-state.json"
    if path.exists():
        raise ValueError("never restart a used capture; inspect its recorded result")
    frozen = source_hashes(root / "src")
    if frozen != json.loads((root / "deployment.json").read_text())["source_files"]:
        raise ValueError("prepared source does not match its deployment attestation")
    selected = next(c for c in cases() if c["injection"].get("kind") == "copy_contention"
                    and c["injection"].get("buffer_mib") == 1024)
    state = dict(status="prechecking", source_files=frozen, requested_runs=1, completed_runs=0,
                 case_id=selected["case_id"], retention="all_raw_semantics_graphs_and_reports",
                 other_tasks_not_stopped=True, started_unix_ns=time.time_ns(), active_directory=None)
    write(path, state)
    try:
        resources(root, "target-idle-1", cards=(4, 5, 6, 7))
        time.sleep(30)
        resources(root, "target-idle-2", cards=(4, 5, 6, 7))
        current = prepare_attempt(root, 1, selected, None)
        policy = dict(retain_all_evidence=True, user_requested=True, automatic_cleanup_forbidden=True,
                      purpose="fixed factual input for offline diagnosis development")
        write(current / "retain-all-evidence.json", policy)
        peer = str(Path(PEER_PARENT) / current.name / "retain-all-evidence.json")
        code = "from pathlib import Path;Path(" + repr(peer) + ").write_text(" + repr(json.dumps(policy)) + ")"
        execute(ssh(shlex.join(["python3", "-c", code])))
        state.update(status="running", active_directory=str(current))
        write(path, state)
        with (root / "capture.log").open("x") as log:
            protected_run([sys.executable, str(current / "src/test/run_node03_authorized.py"),
                "--root", str(current), "--gpt", "--formal-case", str(current / "input/case.json"),
                "--communication-calibration"], log)
        state.update(status="auditing")
        write(path, state)
        evaluation, impact = inspect_case(current)
        state.update(status="capture_complete", completed_runs=1, evaluation=evaluation,
                     impact={k: v for k, v in impact.items() if k != "slow_executions"},
                     original_policies_read_back=True, no_new_capture_for_diagnosis_tuning=True)
    except BaseException as error:
        state.update(status="stopped", error=str(error), no_automatic_resubmission=True)
        if getattr(error, "stderr", None):
            state["command_stderr"] = error.stderr[-6000:]
        raise
    finally:
        state["finished_unix_ns"] = time.time_ns()
        write(path, state)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    args = parser.parse_args()
    with (args.root / "fixed-trace.lock").open("x") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        run(args.root.resolve())


if __name__ == "__main__":
    main()
