"""Three-rank single-node AllReduce with public call records and finite D2D load."""
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
from test.short_copy_burst import ShortCopyBurst


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--warmup', type=int, default=10)
    parser.add_argument('--iterations', type=int, default=30)
    parser.add_argument('--size-mib', type=int, default=128)
    parser.add_argument('--copy-mib', type=int, default=0)
    parser.add_argument('--copy-operations', type=int, default=4)
    parser.add_argument('--inject-iteration', type=int, default=15)
    args = parser.parse_args()
    rank = int(os.environ['RANK'])
    device = (3, 5, 7)[int(os.environ['LOCAL_RANK'])]
    torch_npu.npu.set_device(device)
    dist.init_process_group('hccl')
    if dist.get_world_size() != 3 or args.copy_mib not in (0, 512, 2048):
        raise ValueError('explicitly reviewed three-rank and bounded Copy configuration required')
    args.output.mkdir(parents=True, exist_ok=True)
    tensor = torch.empty(args.size_mib * 1024**2 // 4, dtype=torch.float32, device='npu')
    burst = (ShortCopyBurst(device, args.copy_mib, args.output / 'injection.json', operations=args.copy_operations)
             if args.copy_mib and rank == 0 else None)
    samples = []
    try:
        with Trace.from_environment(device_id=device) as trace:
            trace.group('three-rank-allreduce', [0, 1, 2])
            for stage, count in [('warmup', args.warmup), ('measured', args.iterations)]:
                for iteration in range(count):
                    tensor.fill_(rank + 1)
                    torch_npu.npu.synchronize()
                    start = time.perf_counter_ns()
                    with trace.iteration(iteration, stage=stage):
                        with trace.collective(group='three-rank-allreduce', call_site='allreduce.fp32',
                                              operation_type='AllReduce', element_count=tensor.numel(),
                                              dtype='float32', reduction='sum'):
                            work = dist.all_reduce(tensor, async_op=True)
                            if burst and stage == 'measured' and iteration == args.inject_iteration:
                                burst.start()
                            work.wait()
                            torch_npu.npu.synchronize()
                        trace.completion_boundary()
                    elapsed = time.perf_counter_ns() - start
                    # The next collective cannot accidentally become a second
                    # intervention. This post-call CPU wait is not timed as HCCL.
                    if burst and stage == 'measured' and iteration == args.inject_iteration:
                        burst.wait_finished()
                    error = float((tensor - 6).abs().max().item())
                    if error != 0:
                        raise ValueError('AllReduce full-buffer numerical mismatch')
                    samples.append(dict(stage=stage, iteration=iteration, elapsed_ns=elapsed, max_error=error))
    finally:
        if burst:
            burst.close()
    (args.output / ('rank-' + str(rank) + '.json')).write_text(json.dumps(dict(
        status='passed', rank=rank, pid=os.getpid(), runtime_device_id=device,
        loaded_hcomm_libraries=sorted({line.split()[-1] for line in Path('/proc/self/maps').read_text().splitlines()
            if any(name in line for name in ('libhcomm.so', 'libhccl_alg.so', 'libhccl_plf.so'))}),
        warmup=args.warmup, iterations=args.iterations, size_mib=args.size_mib, samples=samples), indent=2) + '\n')
    dist.destroy_process_group()


if __name__ == '__main__':
    main()
