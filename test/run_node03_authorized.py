"""Run one protected AI_CPU validation and restore both nodes on every exit."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import shlex
import signal
import subprocess
import sys
import time

from run_node03_preflight import LOCAL_PARENT, PEER_PARENT, write


def root_command(node, command):
    value = ["ssh", "-i", str(Path.home() / ".ssh/KeyPair-f1dd.pem"), "-o", "IdentitiesOnly=yes",
             "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=yes", "-o", "ConnectTimeout=15"]
    if node == 0:
        value += ["-o", "UserKnownHostsFile=" + str(LOCAL_PARENT / "nf-20261022/authorized/known_hosts")]
    value += ["root@192.169.0.173" if node == 0 else "root@192.169.0.220", shlex.join(command)]
    return value


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--gpt", action="store_true")
    parser.add_argument("--formal-case", type=Path)
    args = parser.parse_args()
    root = args.root.resolve()
    if root.parent != LOCAL_PARENT or not root.name.startswith("hccl-diagnose-node03-"):
        raise ValueError("reviewed owned Node0 root required")
    state = dict(status="preparing", formal_runs=0, requested_formal_runs=6, started_unix_ns=time.time_ns())
    path = root / "authorized-state.json"
    if path.exists():
        raise ValueError("do not restart a used protected attempt")
    log = (root / "authorized.log").open("x")
    prepared, restored = [], []

    def interrupted(signum, frame):
        raise InterruptedError("protected run interrupted by signal " + str(signum))

    for signum in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP):
        signal.signal(signum, interrupted)

    def guard(node, action):
        location = (str(LOCAL_PARENT) if node == 0 else PEER_PARENT) + "/" + root.name
        command = ["python3", location + "/src/test/node03_device_guard.py", action, "--root", location]
        if action == "prepare" and args.gpt:
            command += ["--seconds", "7200"]
        result = subprocess.run(root_command(node, command), stdout=log, stderr=subprocess.STDOUT, timeout=240)
        if result.returncode:
            raise RuntimeError("node{} device guard {} failed; inspect authorized.log".format(node, action))

    try:
        write(path, state)
        for node in (0, 3):
            # Mark before prepare so partial arming failures also get a restoration attempt.
            prepared.append(node)
            guard(node, "prepare")
        state["status"] = "activating"
        write(path, state)
        for node in (0, 3):
            guard(node, "activate")
        state["status"] = "validating"
        write(path, state)
        command = [sys.executable, str(root / "src/test/run_node03_preflight.py"), "--root", str(root),
                   "--algorithm", "ring", "--size-mib", "32", "--op-expansion-mode", "AI_CPU", "--protected-package"]
        if args.gpt:
            command.append("--gpt")
        if args.formal_case:
            command += ["--formal-case", str(args.formal_case)]
        result = subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, timeout=5400 if args.formal_case else 3000 if args.gpt else 1200)
        if result.returncode:
            raise RuntimeError("protected capture/diagnosis preflight failed; inspect authorized.log")
        state["validation_passed"] = True
    except BaseException as error:
        state.update(status="failed", error=str(error))
        raise
    finally:
        for node in reversed(prepared):
            try:
                guard(node, "restore")
                restored.append(node)
            except Exception as error:
                state.setdefault("restoration_errors", []).append(str(error))
        state["restored_nodes"] = sorted(restored)
        state["finished_unix_ns"] = time.time_ns()
        if state.get("validation_passed") and len(restored) == 2:
            state["status"] = "passed"
            state["formal_runs"] = int(args.formal_case is not None)
        write(path, state)
        log.close()
        if len(restored) != len(prepared):
            raise RuntimeError("restoration needs attention; independent timers have not been cancelled")


if __name__ == "__main__":
    main()
