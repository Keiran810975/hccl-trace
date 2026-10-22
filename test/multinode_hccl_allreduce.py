#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# -----------------------------------------------------------------------------
# This program is free software, you can redistribute it and/or modify it.
# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# This file is a part of the CANN Open Software.
# Licensed under CANN Open Software License Agreement Version 2.0 (the "License").
# Please refer to the License for details. You may not use this file except in compliance with the License.
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED, INCLUDING
# BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
# See LICENSE in the root of the software repository for the full text of the License.
# -----------------------------------------------------------------------------

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import socket
import time

import torch
import torch.distributed as dist
import torch_npu


DTYPES = {
    "fp32": torch.float32,
    "fp16": torch.float16,
    "bf16": torch.bfloat16,
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Multi-node HCCL AllReduce baseline")
    parser.add_argument("--count", type=int, default=16 * 1024 * 1024)
    parser.add_argument("--dtype", choices=sorted(DTYPES), default="fp32")
    parser.add_argument("--warmup", type=int, default=5)
    parser.add_argument("--iters", type=int, default=20)
    parser.add_argument("--skip-check", action="store_true")
    parser.add_argument(
        "--sync-each-iteration",
        action="store_true",
        help="Synchronize the local NPU after every AllReduce for independent latency samples.",
    )
    parser.add_argument(
        "--delay-rank",
        type=int,
        default=-1,
        help="Global rank delayed immediately before a measured AllReduce.",
    )
    parser.add_argument(
        "--delay-iteration",
        type=int,
        default=0,
        help="Zero-based measured iteration selected for --delay-rank.",
    )
    parser.add_argument(
        "--delay-ms",
        type=float,
        default=0.0,
        help="Pre-collective arrival delay; this is not an internal HCCL task delay.",
    )
    parser.add_argument(
        "--no-barrier",
        action="store_true",
        help="Run only AllReduce collectives so profiler data is not mixed with barrier tasks.",
    )
    return parser.parse_args()


def run_all_reduce(tensor: torch.Tensor, rank: int) -> None:
    tensor.fill_(rank + 1)
    dist.all_reduce(tensor, op=dist.ReduceOp.SUM)


def main() -> None:
    args = parse_args()
    if args.count <= 0 or args.warmup < 0 or args.iters <= 0:
        raise ValueError("count and iters must be positive; warmup must be non-negative")
    if args.delay_ms < 0 or args.delay_iteration < 0:
        raise ValueError("delay-ms and delay-iteration must be non-negative")
    if args.delay_ms > 0 and args.delay_iteration >= args.iters:
        raise ValueError("delay-iteration must select one of the measured iterations")

    local_rank = int(os.environ["LOCAL_RANK"])
    selected = [int(value) for value in os.environ.get("HCCL_WORKLOAD_DEVICES", "").split(",") if value]
    if selected and (local_rank >= len(selected) or len(set(selected)) != len(selected) or min(selected) < 0):
        raise ValueError("invalid HCCL_WORKLOAD_DEVICES for local rank")
    device_id = selected[local_rank] if selected else local_rank
    torch_npu.npu.set_device(device_id)
    dist.init_process_group(backend="hccl", init_method="env://")

    rank = dist.get_rank()
    world_size = dist.get_world_size()
    dtype = DTYPES[args.dtype]
    tensor = torch.empty(args.count, dtype=dtype, device=f"npu:{device_id}")

    for _ in range(args.warmup):
        run_all_reduce(tensor, rank)
        if args.sync_each_iteration:
            torch_npu.npu.synchronize()
    torch_npu.npu.synchronize()
    if not args.no_barrier:
        dist.barrier()

    start = time.perf_counter_ns()
    delay_applied = False
    for iteration in range(args.iters):
        if (
            args.delay_ms > 0
            and rank == args.delay_rank
            and iteration == args.delay_iteration
        ):
            time.sleep(args.delay_ms / 1000)
            delay_applied = True
        run_all_reduce(tensor, rank)
        if args.sync_each_iteration:
            torch_npu.npu.synchronize()
    torch_npu.npu.synchronize()
    elapsed_ns = time.perf_counter_ns() - start

    expected = world_size * (world_size + 1) / 2
    max_error = 0.0
    if not args.skip_check:
        max_error = float(torch.max(torch.abs(tensor.float() - expected)).cpu())
        tolerance = 1e-5 if dtype == torch.float32 else 1e-2
        if max_error > tolerance:
            raise RuntimeError(
                f"rank {rank} AllReduce mismatch: expected={expected}, max_error={max_error}"
            )

    avg_s = elapsed_ns / 1_000_000_000 / args.iters
    payload_bytes = tensor.numel() * tensor.element_size()
    algorithmic_gbps = payload_bytes / avg_s / 1_000_000_000
    bus_gbps = algorithmic_gbps * 2 * (world_size - 1) / world_size
    result = {
        "rank": rank,
        "world_size": world_size,
        "host": socket.gethostname(),
        "local_rank": local_rank,
        "runtime_device_id": device_id,
        "dtype": args.dtype,
        "count": args.count,
        "payload_bytes": payload_bytes,
        "warmup": args.warmup,
        "iters": args.iters,
        "sync_each_iteration": args.sync_each_iteration,
        "avg_ms": avg_s * 1000,
        "algorithmic_gbps": algorithmic_gbps,
        "bus_gbps": bus_gbps,
        "expected": expected,
        "max_error": max_error,
        "delay_rank": args.delay_rank,
        "delay_iteration": args.delay_iteration,
        "delay_ms": args.delay_ms,
        "delay_applied": delay_applied,
        "injection_kind": "pre_collective_arrival_delay"
        if args.delay_ms > 0
        else "none",
        "status": "passed",
    }
    if not args.no_barrier:
        dist.barrier()
    dist.destroy_process_group()
    if os.environ.get("HCCL_WORKLOAD_RESULT_DIR"):
        destination = Path(os.environ["HCCL_WORKLOAD_RESULT_DIR"]) / f"rank-{rank}.json"
        destination.write_text(json.dumps(result, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, sort_keys=True), flush=True)


if __name__ == "__main__":
    main()
