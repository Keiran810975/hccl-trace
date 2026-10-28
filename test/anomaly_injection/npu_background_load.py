#!/usr/bin/env python3
"""Bounded NPU interference worker with explicit ready/start/active/stop files."""

from __future__ import annotations

import argparse
from datetime import timedelta
import json
import os
from pathlib import Path
import time

if __package__:
    from .npu_compute import gemm
else:
    from npu_compute import gemm


def communication_continue(store: object, index: int, rank: int, stop: bool) -> bool:
    # A host-store handshake prevents one peer exiting while the other starts another collective.
    store.set(f"continue/{index}/{rank}", "0" if stop else "1")
    peer = store.get(f"continue/{index}/{1 - rank}")
    return not stop and peer == b"1"


def wait_for_finalize(directory: Path, deadline: float) -> None:
    while not (directory / "finalize").exists():
        if time.monotonic() >= deadline:
            raise TimeoutError("foreground measurement did not authorize background finalization")
        time.sleep(.01)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--kind", choices=("copy", "compute", "communication"), required=True)
    parser.add_argument("--device", type=int, required=True)
    parser.add_argument("--control-dir", type=Path, required=True)
    parser.add_argument("--timeout", type=float, default=1200)
    parser.add_argument("--buffer-mib", type=int, default=256)
    parser.add_argument("--matrix-size", type=int, default=4096)
    parser.add_argument("--gemm-backend", choices=("matmul", "grouped"), default="matmul")
    parser.add_argument("--defer-finalize", action="store_true")
    parser.add_argument("--master-addr")
    parser.add_argument("--master-port", type=int)
    parser.add_argument("--rank", type=int, choices=(0, 1))
    args = parser.parse_args()
    if min(args.timeout, args.buffer_mib, args.matrix_size) <= 0:
        parser.error("timeout and load sizes must be positive")
    if args.kind == "communication" and any(v is None for v in (args.master_addr, args.master_port, args.rank)):
        parser.error("communication needs a master address/port and a background rank")

    import torch
    import torch.distributed as dist
    import torch_npu

    torch_npu.npu.set_device(args.device)
    device = f"npu:{args.device}"
    store = None
    if args.kind == "compute":
        left = torch.ones((args.matrix_size, args.matrix_size), dtype=torch.bfloat16, device=device)
        right = (torch.ones_like(left) if args.gemm_backend == "grouped" else
                 torch.full_like(left, 1 / args.matrix_size))
        output = torch.empty_like(left)

        def operation() -> None:
            nonlocal output
            if args.gemm_backend == "grouped":
                output = gemm(left, right, "grouped")
            else:
                torch.mm(left, right, out=output)
    else:
        left = torch.ones(args.buffer_mib * 1024 * 1024 // 4, dtype=torch.float32, device=device)
        output = torch.empty_like(left)
        if args.kind == "copy":
            def operation() -> None:
                output.copy_(left, non_blocking=True)
        else:
            store = dist.TCPStore(args.master_addr, args.master_port, 2, args.rank == 0,
                                  timeout=timedelta(seconds=120))
            dist.init_process_group("hccl", store=dist.PrefixStore("background", store),
                                    rank=args.rank, world_size=2, timeout=timedelta(seconds=120))

            def operation() -> None:
                output.fill_(1)
                dist.all_reduce(output)

    operation()
    torch_npu.npu.synchronize()
    (args.control_dir / "ready").touch()
    deadline = time.monotonic() + args.timeout
    while not (args.control_dir / "start").exists():
        if (args.control_dir / "stop").exists():
            if store is not None:
                dist.destroy_process_group()
            return 0
        if time.monotonic() >= deadline:
            raise TimeoutError("background start was not received")
        time.sleep(0.01)
    started = time.monotonic_ns()
    started_raw = time.clock_gettime_ns(time.CLOCK_MONOTONIC_RAW)
    operations = 0
    peer_stopped = False
    try:
        while True:
            stop = (args.control_dir / "stop").exists() or time.monotonic() >= deadline
            if store is not None:
                if not communication_continue(store, operations, args.rank, stop):
                    peer_stopped = not stop
                    break
            elif stop:
                break
            operation()
            torch_npu.npu.synchronize()
            operations += 1
            if operations == 1:
                (args.control_dir / "active").touch()
        finished_raw = time.clock_gettime_ns(time.CLOCK_MONOTONIC_RAW)
        if operations == 0:
            raise RuntimeError("background worker did not execute during the requested window")
        if args.defer_finalize:
            (args.control_dir / "activity-window.json").write_text(json.dumps(dict(started_raw_ns=started_raw,
                finished_raw_ns=finished_raw, operations=operations, validation_status="pending")) + "\n")
            (args.control_dir / "paused").touch()
            wait_for_finalize(args.control_dir, deadline)
        finalize_authorized_raw = time.clock_gettime_ns(time.CLOCK_MONOTONIC_RAW)
        expected = 2 if args.kind == "communication" else 1
        if args.kind == "compute" and args.gemm_backend == "grouped":
            expected = args.matrix_size  # Exact BF16 integer for the suite's multiples of 256.
        error = float(torch.max(torch.abs(output.float() - expected)).cpu())
        if error != 0:
            raise RuntimeError("background load numerical check failed")
        while peer_stopped and not (args.control_dir / "stop").exists() and time.monotonic() < deadline:
            time.sleep(0.01)
        if not (args.control_dir / "stop").exists() and not peer_stopped:
            raise TimeoutError("background worker lifetime expired before an explicit stop")
        if peer_stopped and not (args.control_dir / "stop").exists():
            raise TimeoutError("local controller did not acknowledge the peer stop")
        result = {"kind": args.kind, "pid": os.getpid(), "runtime_device_index": args.device,
                  "operations": operations, "started_monotonic_ns": started,
                  "finished_monotonic_ns": time.monotonic_ns(), "max_error": error,
                  "started_raw_ns": started_raw, "finished_raw_ns": finished_raw,
                  "finalize_deferred": args.defer_finalize, "finalize_authorized_raw_ns": finalize_authorized_raw,
                  "status": "completed_not_proof_of_contention"}
        if args.kind == "compute":
            result.update(gemm_backend=args.gemm_backend, matrix_size=args.matrix_size,
                          expected=expected, input_pattern="ones" if args.gemm_backend == "grouped" else "scaled_ones")
        (args.control_dir / "result.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(result), flush=True)
    finally:
        if store is not None:
            dist.destroy_process_group()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
