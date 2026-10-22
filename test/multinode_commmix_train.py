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
import math
import os
from pathlib import Path
import socket
import time
from typing import Callable

import torch
import torch.distributed as dist
import torch.nn.functional as functional
import torch_npu


MIB = 1024 * 1024


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Training-shaped multi-node NPU compute and HCCL workload"
    )
    parser.add_argument(
        "--bucket-mib",
        default="1,8,32",
        help="Comma-separated fp32 AllReduce bucket sizes in MiB.",
    )
    parser.add_argument("--compute-size", type=int, default=1024)
    parser.add_argument("--blocks", type=int, default=1)
    parser.add_argument("--tokens", type=int, default=0)
    parser.add_argument("--hidden-size", type=int, default=0)
    parser.add_argument("--ffn-size", type=int, default=0)
    parser.add_argument("--warmup", type=int, default=5)
    parser.add_argument("--iters", type=int, default=30)
    parser.add_argument("--seed", type=int, default=20260924)
    parser.add_argument("--skip-check", action="store_true")
    parser.add_argument("--delay-rank", type=int, default=-1)
    parser.add_argument("--delay-iteration", type=int, default=0)
    parser.add_argument("--delay-block", type=int, default=-1)
    parser.add_argument("--delay-bucket", type=int, default=-1)
    parser.add_argument("--delay-ms", type=float, default=0.0)
    parser.add_argument("--case-config", type=Path)
    parser.add_argument("--case-cluster", type=Path)
    parser.add_argument("--events-dir", type=Path)
    parser.add_argument(
        "--no-barrier",
        action="store_true",
        help="Do not add process-group barriers around the measured region.",
    )
    return parser.parse_args()


def parse_bucket_counts(text: str) -> list[int]:
    sizes = [float(value.strip()) for value in text.split(",") if value.strip()]
    if not sizes or any(value <= 0 for value in sizes):
        raise ValueError("bucket-mib must contain positive sizes")
    counts = [int(value * MIB / torch.tensor([], dtype=torch.float32).element_size()) for value in sizes]
    if any(count <= 0 for count in counts):
        raise ValueError("bucket-mib contains a bucket smaller than one fp32 element")
    return counts


def percentile(values: list[float], percentile_value: float) -> float:
    ordered = sorted(values)
    index = max(0, math.ceil(percentile_value * len(ordered)) - 1)
    return ordered[index]


def compute_block(value: torch.Tensor, weight: torch.Tensor) -> torch.Tensor:
    return functional.gelu(torch.matmul(value, weight))


def run_legacy_step(
    step: int,
    rank: int,
    source: torch.Tensor,
    weights: list[torch.Tensor],
    buckets: list[torch.Tensor],
) -> torch.Tensor:
    activation = source
    for bucket_index, (weight, bucket) in enumerate(zip(weights, buckets)):
        activation = compute_block(activation, weight)
        bucket.fill_(step + rank + bucket_index + 1)
        dist.all_reduce(bucket, op=dist.ReduceOp.SUM)
    activation.mul_(0.999)
    return activation


def make_weight(rows: int, columns: int, device: str) -> torch.Tensor:
    weight = torch.randn((rows, columns), dtype=torch.bfloat16, device=device)
    weight.mul_(1 / math.sqrt(rows))
    return weight


def run_transformer_step(
    step: int,
    rank: int,
    source: torch.Tensor,
    block_weights: list[tuple[torch.Tensor, torch.Tensor, torch.Tensor, torch.Tensor]],
    buckets: list[torch.Tensor],
    delay_rank: int,
    delay_iteration: int,
    delay_block: int,
    delay_bucket: int,
    delay_ms: float,
    before_collective: Callable[[int, int, int], None] | None = None,
) -> tuple[torch.Tensor, bool]:
    activation = source
    delay_applied = False
    for block_index, (qkv_weight, output_weight, ffn_up, ffn_down) in enumerate(block_weights):
        qkv = compute_block(activation, qkv_weight)
        for bucket_index, bucket in enumerate(buckets):
            if bucket_index == 1:
                activation = compute_block(qkv, output_weight)
            elif bucket_index == 2:
                ffn_activation = compute_block(activation, ffn_up)
                activation = compute_block(ffn_activation, ffn_down)

            bucket.fill_(step + rank + block_index * len(buckets) + bucket_index + 1)
            if before_collective is not None:
                before_collective(step, block_index, bucket_index)
            if (
                delay_ms > 0
                and rank == delay_rank
                and step == delay_iteration
                and block_index == delay_block
                and bucket_index == delay_bucket
            ):
                time.sleep(delay_ms / 1000)
                delay_applied = True
            dist.all_reduce(bucket, op=dist.ReduceOp.SUM)
        activation.mul_(0.999)
    return activation, delay_applied


def main() -> None:
    args = parse_args()
    if args.compute_size <= 0 or args.blocks <= 0 or args.warmup < 0 or args.iters <= 0:
        raise ValueError("compute-size, blocks, and iters must be positive; warmup must be non-negative")
    if args.delay_ms < 0 or args.delay_iteration < 0:
        raise ValueError("delay-ms and delay-iteration must be non-negative")
    if args.delay_ms > 0 and args.delay_iteration >= args.iters:
        raise ValueError("delay-iteration must select one of the measured iterations")

    transformer_mode = args.tokens > 0 or args.hidden_size > 0 or args.ffn_size > 0
    if transformer_mode:
        if args.tokens <= 0 or args.hidden_size <= 0:
            raise ValueError("tokens and hidden-size must both be positive in transformer mode")
        if len(parse_bucket_counts(args.bucket_mib)) != 3:
            raise ValueError("transformer mode requires exactly three AllReduce buckets")
        if args.ffn_size <= 0:
            args.ffn_size = args.hidden_size * 2
        if args.delay_ms > 0 and not (
            0 <= args.delay_block < args.blocks and 0 <= args.delay_bucket < 3
        ):
            raise ValueError("transformer delay requires a valid delay-block and delay-bucket")

    bucket_counts = parse_bucket_counts(args.bucket_mib)
    local_rank = int(os.environ["LOCAL_RANK"])
    selected = [int(value) for value in os.environ.get("HCCL_WORKLOAD_DEVICES", "").split(",") if value]
    if selected and (local_rank >= len(selected) or len(set(selected)) != len(selected) or min(selected) < 0):
        raise ValueError("invalid HCCL_WORKLOAD_DEVICES for local rank")
    device_id = selected[local_rank] if selected else local_rank
    torch_npu.npu.set_device(device_id)
    dist.init_process_group(backend="hccl", init_method="env://")

    rank = dist.get_rank()
    world_size = dist.get_world_size()
    control = None
    if any((args.case_config, args.case_cluster, args.events_dir)):
        if not all((args.case_config, args.case_cluster, args.events_dir)) or not transformer_mode:
            raise ValueError("case-config, case-cluster and events-dir require transformer mode and each other")
        try:
            from test.anomaly_injection.four_node_control import load_control
        except ModuleNotFoundError:
            from anomaly_injection.four_node_control import load_control
        control = load_control(args.case_config, args.case_cluster, args.events_dir,
                               rank, local_rank, world_size, args)
        import atexit
        atexit.register(control.close)
        control.verify_configuration(torch, dist, f"npu:{device_id}")
        control.prepare()
    torch.manual_seed(args.seed)
    torch_npu.npu.manual_seed_all(args.seed)
    device = f"npu:{device_id}"
    if transformer_mode:
        source = torch.randn(
            (args.tokens, args.hidden_size), dtype=torch.bfloat16, device=device
        )
        block_weights = [
            (
                make_weight(args.hidden_size, args.hidden_size * 3, device),
                make_weight(args.hidden_size * 3, args.hidden_size, device),
                make_weight(args.hidden_size, args.ffn_size, device),
                make_weight(args.ffn_size, args.hidden_size, device),
            )
            for _ in range(args.blocks)
        ]
        weights: list[torch.Tensor] = []
    else:
        source = torch.randn(
            (args.compute_size, args.compute_size), dtype=torch.bfloat16, device=device
        )
        weights = [
            make_weight(args.compute_size, args.compute_size, device)
            for _ in bucket_counts
        ]
        block_weights = []
    buckets = [torch.empty(count, dtype=torch.float32, device=device) for count in bucket_counts]

    activation = source
    for warmup_step in range(args.warmup):
        if transformer_mode:
            activation, _ = run_transformer_step(
                -(warmup_step + 1),
                rank,
                source,
                block_weights,
                buckets,
                args.delay_rank,
                args.delay_iteration,
                args.delay_block,
                args.delay_bucket,
                args.delay_ms,
            )
        else:
            activation = run_legacy_step(
                -(warmup_step + 1), rank, source, weights, buckets
            )
    torch_npu.npu.synchronize()
    if not args.no_barrier:
        dist.barrier()

    step_times_ms: list[float] = []
    delay_applied = False
    measured_started_ns = time.perf_counter_ns()
    for step in range(args.iters):
        if control is not None and control.transition(step):
            # All cases, including paired normals, use the same two window barriers.
            dist.barrier()
            torch_npu.npu.synchronize()
        if (
            not transformer_mode
            and args.delay_ms > 0
            and rank == args.delay_rank
            and step == args.delay_iteration
        ):
            time.sleep(args.delay_ms / 1000)
            delay_applied = True
        started_ns = time.perf_counter_ns()
        if transformer_mode:
            activation, step_delay_applied = run_transformer_step(
                step,
                rank,
                source,
                block_weights,
                buckets,
                args.delay_rank,
                args.delay_iteration,
                args.delay_block,
                args.delay_bucket,
                args.delay_ms,
                control.before_collective if control is not None else None,
            )
            delay_applied = delay_applied or step_delay_applied
        else:
            activation = run_legacy_step(step, rank, source, weights, buckets)
        torch_npu.npu.synchronize()
        elapsed_ns = time.perf_counter_ns() - started_ns
        step_times_ms.append(elapsed_ns / 1_000_000)
        if control is not None:
            control.step_done(step, elapsed_ns)

    if control is not None:
        if control.transition(args.iters):
            dist.barrier()
            torch_npu.npu.synchronize()
        control.close(completed=True)
    measured_region_ns = time.perf_counter_ns() - measured_started_ns

    max_error = 0.0
    if not args.skip_check:
        last_step = args.iters - 1
        for bucket_index, bucket in enumerate(buckets):
            block_offset = (args.blocks - 1) * len(buckets) if transformer_mode else 0
            expected = (
                world_size * (last_step + block_offset + bucket_index + 1)
                + world_size * (world_size - 1) / 2
            )
            error = float(torch.max(torch.abs(bucket - expected)).cpu())
            max_error = max(max_error, error)
        if max_error > 1e-5:
            raise RuntimeError(f"rank {rank} AllReduce mismatch: max_error={max_error}")

    collectives_per_step = len(buckets) * (args.blocks if transformer_mode else 1)
    payload_bytes_per_step = sum(
        bucket.numel() * bucket.element_size() for bucket in buckets
    ) * (args.blocks if transformer_mode else 1)
    elapsed_s = sum(step_times_ms) / 1000
    result = {
        "rank": rank,
        "world_size": world_size,
        "host": socket.gethostname(),
        "local_rank": local_rank,
        "runtime_device_id": device_id,
        "workload": "Transformer-CommMix" if transformer_mode else "MiniTrain-CommMix",
        "compute_dtype": "bf16",
        "communication_dtype": "fp32",
        "compute_size": args.compute_size,
        "blocks": args.blocks,
        "tokens": args.tokens,
        "hidden_size": args.hidden_size,
        "ffn_size": args.ffn_size,
        "collectives_per_step": collectives_per_step,
        "bucket_mib": [bucket.numel() * bucket.element_size() / MIB for bucket in buckets],
        "payload_bytes_per_step": payload_bytes_per_step,
        "warmup": args.warmup,
        "iters": args.iters,
        "avg_step_ms": sum(step_times_ms) / len(step_times_ms),
        "median_step_ms": percentile(step_times_ms, 0.50),
        "p95_step_ms": percentile(step_times_ms, 0.95),
        "steps_per_second": args.iters / elapsed_s,
        "max_error": max_error,
        "delay_rank": args.delay_rank,
        "delay_iteration": args.delay_iteration,
        "delay_block": args.delay_block,
        "delay_bucket": args.delay_bucket,
        "delay_ms": args.delay_ms,
        "delay_applied": delay_applied,
        "injection_kind": "pre_collective_arrival_delay" if args.delay_ms > 0 else "none",
        "activation_checksum": float(activation.float().mean().cpu()),
        "status": "passed",
    }
    if control is not None:
        result["injection_kind"] = control.inj["kind"]
        result["control_barriers"] = "before_measurement,window_start,window_stop,after_measurement"
        result["configuration_check_allreduces"] = 2
        result["measured_region_ns_including_window_control"] = measured_region_ns
        result["delay_applied"] = None  # Use private control events / native hit logs, not the legacy flag.
    if not args.no_barrier:
        dist.barrier()
    dist.destroy_process_group()
    if control is not None:
        control.record_result(result)
    if os.environ.get("HCCL_WORKLOAD_RESULT_DIR"):
        destination = Path(os.environ["HCCL_WORKLOAD_RESULT_DIR"]) / f"rank-{rank}.json"
        destination.write_text(json.dumps(result, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, sort_keys=True), flush=True)


if __name__ == "__main__":
    main()
