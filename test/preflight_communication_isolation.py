#!/usr/bin/env python3
"""Verify two real communication groups can coexist on the selected own devices."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import signal
import subprocess
import time


def run(worker, output):
    output.mkdir(exist_ok=False)
    processes, directories, logs = [], [], []
    try:
        for index in range(2):
            directory = output / str(index)
            directory.mkdir()
            directories.append(directory)
            env = dict(os.environ, HCCL_OP_EXPANSION_MODE="HOST", HCCL_STEP_TRACE="0", HCCL_TASK_SEMANTIC_TRACE="0")
            if index:
                env.update(HCCL_IF_BASE_PORT="53000", HCCL_HOST_SOCKET_PORT_RANGE="53000-53063",
                           HCCL_NPU_SOCKET_PORT_RANGE="53100-53163")
            log = (directory / "worker.log").open("x")
            logs.append(log)
            process = subprocess.Popen([str(worker), "5", "1", "32", str(directory)], env=env,
                stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
            processes.append(process)
            deadline = time.monotonic() + 120
            while not (directory / "ready").exists():
                if process.poll() is not None or time.monotonic() > deadline:
                    raise RuntimeError("concurrent communication initialization failed")
                time.sleep(.01)
        for directory in directories:
            (directory / "start").touch()
        time.sleep(2)
        for directory in directories:
            (directory / "stop").touch()
        for process in processes:
            if process.wait(timeout=120):
                raise RuntimeError("concurrent communication numerical check failed")
        results = [json.loads((directory / "result.json").read_text()) for directory in directories]
        if any(r["operations"] <= 0 or r["max_error"] != 0 for r in results):
            raise ValueError("no real successful concurrent operations")
        (output / "result.json").write_text(json.dumps(results, indent=2) + "\n")
        print(json.dumps(results), flush=True)
    finally:
        for directory in directories:
            (directory / "stop").touch()
        for process in processes:
            if process.poll() is None:
                os.killpg(process.pid, signal.SIGTERM)
                try:
                    process.wait(timeout=15)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid, signal.SIGKILL)
                    process.wait()
        for log in logs:
            log.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--worker", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    run(args.worker, args.output)
