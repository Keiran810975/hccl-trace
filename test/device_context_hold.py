"""Keep owned NPU contexts alive without a background compute/traffic loop."""
from __future__ import annotations

import argparse
import ctypes
import json
import multiprocessing as mp
import os
from pathlib import Path
import signal
import time


def name_process():
    if ctypes.CDLL(None).prctl(15, ctypes.c_char_p(b"hccl-diagnose"), 0, 0, 0):
        raise OSError("could not set diagnostic job name")


def write(path, value):
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(value, indent=2) + "\n")
    temporary.replace(path)


def hold(device, directory, stop):
    name_process()
    import torch
    import torch_npu
    torch_npu.npu.set_device(device)
    allocation = torch.empty(16, dtype=torch.float32, device="npu:{}".format(device))
    write(directory / ("device-{}.json".format(device)),
          dict(pid=os.getpid(), runtime_device_id=device, tensor_bytes=allocation.numel() * allocation.element_size(),
               role="context_holder_not_workload", exclusive_device_lock=False))
    while not stop.wait(.5):
        pass
    del allocation


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--devices", required=True)
    parser.add_argument("--directory", type=Path, required=True)
    parser.add_argument("--seconds", type=int, default=1800)
    args = parser.parse_args()
    devices = [int(x) for x in args.devices.split(",")]
    if not devices or len(devices) != len(set(devices)) or min(devices) < 0 or not 60 <= args.seconds <= 21600:
        raise ValueError("explicit unique devices and a bounded 60..21600 second lifetime required")
    name_process()
    args.directory.mkdir(parents=True, exist_ok=False)
    ctx = mp.get_context("spawn")
    stop = ctx.Event()
    for signum in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP):
        signal.signal(signum, lambda *unused: stop.set())
    processes = [ctx.Process(target=hold, args=(d, args.directory, stop)) for d in devices]
    state = dict(status="starting", pid=os.getpid(), devices=devices, deadline_unix_ns=time.time_ns() + args.seconds * 10**9,
                 job_name="hccl-diagnose", exclusive_device_lock=False)
    deadline = time.monotonic() + args.seconds
    try:
        for process in processes:
            process.start()
        ready_deadline = min(deadline, time.monotonic() + 120)
        while not all((args.directory / ("device-{}.json".format(d))).is_file() for d in devices):
            if any(p.exitcode is not None for p in processes) or time.monotonic() >= ready_deadline or stop.is_set():
                raise RuntimeError("device context acquisition failed; holders will be released")
            time.sleep(.2)
        state.update(status="holding", children=[p.pid for p in processes])
        write(args.directory / "state.json", state)
        while not stop.wait(.5):
            if (args.directory / "release").exists() or time.monotonic() >= deadline:
                break
            if any(not p.is_alive() for p in processes):
                raise RuntimeError("one context holder exited unexpectedly")
        state["status"] = "released"
    except BaseException as error:
        state.update(status="failed", error=str(error))
        raise
    finally:
        stop.set()
        for process in processes:
            if process.pid:
                process.join(timeout=20)
                if process.is_alive():
                    process.terminate()
                    process.join(timeout=10)
        state["finished_unix_ns"] = time.time_ns()
        write(args.directory / "state.json", state)


if __name__ == "__main__":
    main()
