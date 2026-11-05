"""Run one protected AI_CPU validation and restore both nodes on every exit."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shlex
import signal
import socket
import subprocess
import sys
import time

if __package__:
    from .run_node03_preflight import LOCAL_PARENT, PEER_PARENT, PYTHON, container_command, write
else:
    from run_node03_preflight import LOCAL_PARENT, PEER_PARENT, PYTHON, container_command, write


def cancel_capture(root):
    """Used only for the new calibration path, before restoring its Device lease."""
    base = "/workspace/" + root.name
    errors = []
    for node in (0, 1):
        code = ("import json;from pathlib import Path;from test.stop_owned_capture import terminate;"
                "p=Path(" + repr(base + "/gpt-output/private") + ");p.mkdir(parents=True,exist_ok=True);"
                "(p/'abort').touch();print(json.dumps(terminate(" + repr(base) + ")))")
        try:
            result = subprocess.run(container_command(base, node, shlex.join([PYTHON, "-c", code]), 60),
                                    capture_output=True, text=True, check=True, timeout=75)
            write(root / ("cancel-capture-node{}.json".format(3 if node else 0)), json.loads(result.stdout))
        except Exception as error:
            errors.append(str(error))
    # Abort the owned network watcher and independently read back the saved ports.
    code = ("import sys,json;from pathlib import Path;r=Path(" + repr(str(root)) + ");"
            "sys.path.insert(0,str(r/'src/test'));from node03_roce_window import Window;"
            "w=Window(r);s=w.snapshot;"
            "(w.restore(),w.stop_timer(json.loads(s.read_text())['unit'])) if s.exists() else None")
    try:
        subprocess.run(root_command(0, ["python3", "-c", code]), capture_output=True, text=True, check=True, timeout=180)
    except Exception as error:
        errors.append(str(error))
    if errors:
        raise RuntimeError("owned cancellation requires attention: " + "; ".join(errors))


def root_command(node, command):
    if node not in (0, 3):
        raise ValueError('only Node0 and Node3 are authorized')
    if node == 0 and os.geteuid() == 0 and socket.gethostname().split('.')[0] == 'liteserver-560t-0':
        return list(command)
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
    parser.add_argument("--communication-calibration", action="store_true")
    parser.add_argument("--short-copy-burst", action="store_true")
    parser.add_argument("--copy-burst-phase", choices=("submit", "payload"), default="submit")
    args = parser.parse_args()
    root = args.root.resolve()
    if root.parent != LOCAL_PARENT or not root.name.startswith("hccl-diagnose-node03-"):
        raise ValueError("reviewed owned Node0 root required")
    if args.short_copy_burst and (args.gpt or args.formal_case or args.communication_calibration):
        raise ValueError("short-copy profile must run independently")
    if args.copy_burst_phase != "submit" and not args.short_copy_burst:
        raise ValueError("copy placement requires an explicit short-copy profile")
    if args.communication_calibration:
        if not args.gpt or args.formal_case is None or args.formal_case.resolve() != root / "input/case.json":
            raise ValueError("communication calibration requires the explicit owned GPT case before device preparation")
        from communication_calibration import validate_case
        validate_case(json.loads(args.formal_case.read_text()))
    state = dict(status="preparing", formal_runs=0, requested_formal_runs=6, started_unix_ns=time.time_ns())
    path = root / "authorized-state.json"
    if path.exists():
        raise ValueError("do not restart a used protected attempt")
    log = (root / "authorized.log").open("x")
    prepared, restored, validation_process = [], [], None

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
                   "--algorithm", "ring", "--size-mib", "128" if args.short_copy_burst else "32", "--op-expansion-mode", "AI_CPU", "--protected-package"]
        if args.short_copy_burst:
            command += ["--short-copy-burst", "--copy-burst-phase", args.copy_burst_phase]
        if args.gpt:
            command.append("--gpt")
        if args.formal_case:
            command += ["--formal-case", str(args.formal_case)]
        if args.communication_calibration:
            command.append("--communication-calibration")
        validation_process = subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT)
        if validation_process.wait(timeout=5400 if args.formal_case else 3000 if args.gpt else 1200):
            raise RuntimeError("protected capture/diagnosis preflight failed; inspect authorized.log")
        state["validation_passed"] = True
    except BaseException as error:
        state.update(status="failed", error=str(error))
        repeat20 = args.formal_case and json.loads(args.formal_case.read_text()).get('experiment_contract', {}).get('profile') == 'multinode20-v1'
        if (args.communication_calibration or args.short_copy_burst or repeat20) and validation_process is not None:
            try:
                cancel_capture(root)
            except Exception as cleanup_error:
                state["capture_cancellation_error"] = str(cleanup_error)
        if validation_process is not None and validation_process.poll() is None:
            validation_process.terminate()
            try:
                validation_process.wait(timeout=120)
            except subprocess.TimeoutExpired:
                validation_process.kill()
                validation_process.wait(timeout=30)
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
