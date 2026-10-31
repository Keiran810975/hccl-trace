#!/usr/bin/python3
# coding=utf-8
# Claude-generated simple AllReduce test for hccl-trace step trace validation.
# Usage:
#   torchrun --nproc_per_node=8 --master_port=29500 c_allreduce_test.py --count 268435456 --dtype fp32
#
import argparse
import os
import sys
import time
import torch
import torch.distributed as dist


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--count", type=int, default=268435456, help="Element count")
    parser.add_argument("--dtype", default="fp32", choices=["fp32", "fp16", "bf16"])
    parser.add_argument("--iters", type=int, default=10, help="Number of iterations")
    parser.add_argument("--warmup", type=int, default=5, help="Warmup iterations")
    return parser.parse_args()


def main():
    args = parse_args()

    dist.init_process_group("hccl")
    rank = dist.get_rank()
    local_rank = int(os.environ.get("LOCAL_RANK", rank % 8))
    torch.npu.set_device(local_rank)

    dtype_map = {"fp32": torch.float32, "fp16": torch.float16, "bf16": torch.bfloat16}
    dtype = dtype_map[args.dtype]

    # Allocate tensor
    with torch.device("npu"):
        x = torch.randn(args.count, dtype=dtype)

    # Warmup
    for _ in range(args.warmup):
        dist.all_reduce(x)
    torch.npu.synchronize()

    # Measured iterations
    tic = time.perf_counter()
    for _ in range(args.iters):
        dist.all_reduce(x)
    torch.npu.synchronize()
    toc = time.perf_counter()

    avg_ms = (toc - tic) * 1000 / args.iters
    if rank == 0:
        print(f"AllReduce count={args.count} dtype={args.dtype} iters={args.iters} avg={avg_ms:.4f} ms")

    dist.destroy_process_group()


if __name__ == "__main__":
    main()
