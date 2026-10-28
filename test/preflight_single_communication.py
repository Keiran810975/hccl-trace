#!/usr/bin/env python3
"""Bounded runtime check for the one-process, two-device communication worker."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import signal
import subprocess
import time


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--worker", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(exist_ok=False)
    env = dict(os.environ, HCCL_OP_EXPANSION_MODE="HOST", HCCL_STEP_TRACE="0", HCCL_TASK_SEMANTIC_TRACE="0",
               HCCL_CONNECT_TIMEOUT="120", HCCL_EXEC_TIMEOUT="120", ASCEND_PROCESS_LOG_PATH=str(args.output / "logs"))
    with (args.output / "worker.log").open("x") as log:
        worker = subprocess.Popen([str(args.worker), "1", "3", "32", str(args.output)], env=env,
                                  stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
        deadline = time.monotonic() + 150
        try:
            for name in ("ready", "active"):
                while not (args.output / name).exists():
                    if worker.poll() is not None or time.monotonic() > deadline:
                        raise RuntimeError("native background preflight failed before " + name)
                    time.sleep(.01)
                if name == "ready":
                    (args.output / "start").touch()
            time.sleep(2)
            (args.output / "stop").touch()
            if worker.wait(timeout=120):
                raise RuntimeError("native background preflight numerical/cleanup check failed")
        finally:
            if worker.poll() is None:
                (args.output / "stop").touch()
                os.killpg(worker.pid, signal.SIGTERM)
                try:
                    worker.wait(timeout=15)
                except subprocess.TimeoutExpired:
                    os.killpg(worker.pid, signal.SIGKILL)
                    worker.wait()
    result = json.loads((args.output / "result.json").read_text())
    if result["operations"] <= 0 or result["max_error"] != 0 or result["process_count"] != 1:
        raise RuntimeError("invalid single-process preflight result")
    print(json.dumps(result), flush=True)


if __name__ == "__main__":
    main()
