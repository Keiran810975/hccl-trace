"""Small user-owned torchrun workload demonstrating the public observation SDK."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import time

import torch
import torch.distributed as dist
import torch_npu

from hccl_trace import Trace


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--devices", required=True, help="actual local runtime/profiler device IDs")
    parser.add_argument("--warmup", type=int, default=1)
    parser.add_argument("--iterations", type=int, default=7)
    parser.add_argument("--size-mib", type=int, default=2)
    parser.add_argument("--delay-rank", type=int, default=-1)
    parser.add_argument("--delay-iteration", type=int, default=6)
    parser.add_argument("--delay-ms", type=float, default=0)
    parser.add_argument("--numerics-dir", type=Path, required=True)
    args = parser.parse_args()
    devices = [int(value) for value in args.devices.split(",")]
    local = int(os.environ["LOCAL_RANK"])
    if len(set(devices)) != len(devices) or len(devices) != int(os.environ["LOCAL_WORLD_SIZE"]):
        raise ValueError("devices must explicitly match this node's torchrun workers")
    torch_npu.npu.set_device(devices[local])
    dist.init_process_group("hccl")
    rank, world = dist.get_rank(), dist.get_world_size()
    tensor = torch.empty(args.size_mib * 1024 * 1024 // 4, device="npu", dtype=torch.float32)
    expected = world * (world + 1) / 2
    results = []
    with Trace.from_environment(device_id=devices[local]) as trace:
        trace.group("training-data-parallel", dist.get_process_group_ranks(dist.group.WORLD))
        for stage, count in (("warmup", args.warmup), ("measured", args.iterations)):
            for iteration in range(count):
                tensor.fill_(rank + 1)
                # This standalone correctness test already synchronizes each call.
                # The SDK does not insert barriers into the user's training loop.
                torch_npu.npu.synchronize()
                with trace.iteration(iteration, stage=stage):
                    prepare = time.clock_gettime_ns(time.CLOCK_MONOTONIC_RAW)
                    if stage == "measured" and rank == args.delay_rank and iteration == args.delay_iteration:
                        time.sleep(args.delay_ms / 1000)
                    with trace.collective(group="training-data-parallel", call_site="gradient.sync",
                            operation_type="AllReduce", element_count=tensor.numel(), dtype="float32", reduction="sum",
                            preparation_start_raw_ns=prepare):
                        dist.all_reduce(tensor)
                        torch_npu.npu.synchronize()
                    trace.completion_boundary()
                error = float((tensor - expected).abs().max().item())
                if error:
                    raise RuntimeError("AllReduce numerical result mismatch")
                results.append(dict(stage=stage, iteration=iteration, max_error=error))
    args.numerics_dir.mkdir(parents=True, exist_ok=True)
    (args.numerics_dir / ("rank-{}.json".format(rank))).write_text(json.dumps(dict(
        status="passed", user_rank=rank, device_id=devices[local], results=results), indent=2) + "\n")
    dist.destroy_process_group()


if __name__ == "__main__":
    main()
