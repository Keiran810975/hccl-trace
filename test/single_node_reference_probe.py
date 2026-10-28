#!/usr/bin/env python3
"""Communication-only reference plumbing probe, never the formal mixed workload."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

import torch
import torch.distributed as dist
import torch_npu

from anomaly_injection.single_node_control import PublicCalls


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--public-calls-dir", type=Path, required=True)
    args = parser.parse_args()
    rank = int(os.environ["RANK"])
    device = [int(v) for v in os.environ["HCCL_WORKLOAD_DEVICES"].split(",")][int(os.environ["LOCAL_RANK"])]
    torch_npu.npu.set_device(device)
    dist.init_process_group("hccl")
    if dist.get_world_size() != 4:
        raise ValueError("reference probe requires four ranks")
    recorder = PublicCalls(args.public_calls_dir, rank, device)
    buckets = [torch.empty(mib * 1024 * 1024 // 4, dtype=torch.float32, device="npu:{}".format(device))
               for mib in (1, 2, 4)]
    for step in [-1, *range(7)]:
        for index, bucket in enumerate(buckets):
            bucket.fill_(step + rank + index + 1)
            recorder.begin(step, 0, index, bucket.numel())
            dist.all_reduce(bucket)
            recorder.end()
        torch_npu.npu.synchronize()
        recorder.iteration_done(step)
    error = max(float(torch.max(torch.abs(bucket - (4 * (7 + index) + 6))).cpu())
                for index, bucket in enumerate(buckets))
    if error:
        raise ValueError("communication reference probe numerical mismatch")
    recorder.close()
    dist.destroy_process_group()
    result = dict(rank=rank, status="passed", max_error=error, purpose="communication_reference_preflight")
    destination = Path(os.environ["HCCL_WORKLOAD_RESULT_DIR"]) / ("rank-{}.json".format(rank))
    destination.write_text(json.dumps(result) + "\n")


if __name__ == "__main__":
    main()
