#!/usr/bin/env python3
"""Validate the single background GEMM worker before running random injections."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time


def run(output, size, device):
    output.mkdir(exist_ok=False)
    command = [sys.executable, str(Path(__file__).parent / "anomaly_injection/npu_background_load.py"),
               "--kind", "compute", "--device", str(device), "--matrix-size", str(size),
               "--gemm-backend", "grouped", "--control-dir", str(output), "--timeout", "150"]
    env = dict(os.environ, HCCL_STEP_TRACE="0", HCCL_TASK_SEMANTIC_TRACE="0",
               ASCEND_PROCESS_LOG_PATH=str(output / "logs"))
    with (output / "worker.log").open("x") as log:
        worker = subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT,
                                  env=env, start_new_session=True)
        try:
            deadline = time.monotonic() + 120
            for name in ("ready", "active"):
                while not (output / name).exists():
                    if worker.poll() is not None or time.monotonic() > deadline:
                        raise RuntimeError("compute preflight failed before " + name)
                    time.sleep(.01)
                if name == "ready":
                    (output / "start").touch()
            time.sleep(1)
            (output / "stop").touch()
            if worker.wait(timeout=30):
                raise RuntimeError("compute preflight failed numerical/cleanup check")
        finally:
            if worker.poll() is None:
                (output / "stop").touch()
                os.killpg(worker.pid, signal.SIGTERM)
                try:
                    worker.wait(timeout=15)
                except subprocess.TimeoutExpired:
                    os.killpg(worker.pid, signal.SIGKILL)
                    worker.wait()
    result = json.loads((output / "result.json").read_text())
    if result["operations"] <= 0 or result["max_error"] != 0 or result["gemm_backend"] != "grouped":
        raise ValueError("compute background numerical gate failed")
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--device", type=int, default=7)
    parser.add_argument("--sizes", default="2304,6144")
    args = parser.parse_args()
    args.output.mkdir(exist_ok=False)
    results = [run(args.output / ("n-" + str(n)), n, args.device) for n in map(int, args.sizes.split(","))]
    (args.output / "result.json").write_text(json.dumps(results, indent=2) + "\n")
    print(json.dumps(results), flush=True)
