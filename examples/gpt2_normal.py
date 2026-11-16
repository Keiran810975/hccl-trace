"""Run normal GPT-2 Small training with explicit data-parallel gradient sync."""
from __future__ import annotations

import argparse
from contextlib import nullcontext
import math
import os

from hccl_trace import Trace
from hccl_trace.npu_event import NpuEventTiming


def device_list(value):
    try:
        devices = [int(part) for part in value.split(",")]
    except ValueError as error:
        raise argparse.ArgumentTypeError("use comma-separated device IDs") from error
    if min(devices) < 0 or len(set(devices)) != len(devices):
        raise argparse.ArgumentTypeError("device IDs must be nonnegative and unique")
    return devices


def gradient_buckets(parameters, capacity):
    """Use stable parameter order and keep each gradient intact."""
    bucket, size = [], 0
    for parameter in parameters:
        grad = parameter.grad
        if grad is None:
            raise RuntimeError("expected a gradient for every trainable parameter")
        nbytes = grad.numel() * grad.element_size()
        if bucket and size + nbytes > capacity:
            yield bucket
            bucket, size = [], 0
        bucket.append(grad)
        size += nbytes
    if bucket:
        yield bucket


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--devices", type=device_list, required=True, help="runtime device IDs in local-rank order")
    parser.add_argument("--profiler-devices", type=device_list, help="actual profiler device IDs when different")
    parser.add_argument("--warmup", type=int, default=10)
    parser.add_argument("--online-startup-iterations", type=int,
                        help="untracked steps to initialize communication and Event timing (Event mode default: 3)")
    parser.add_argument("--iterations", type=int, default=20)
    parser.add_argument("--batch-size", type=int, default=1, help="per rank")
    parser.add_argument("--seq-length", type=int, default=256)
    parser.add_argument("--bucket-mib", type=int, default=25)
    parser.add_argument("--precision", choices=("bf16", "fp32"), default="bf16")
    parser.add_argument("--seed", type=int, default=20261028)
    args = parser.parse_args()
    if args.warmup < 0 or args.iterations < 2 or args.batch_size < 1 or not 2 <= args.seq_length <= 1024 or args.bucket_mib < 1:
        parser.error("require >=2 formal iterations, positive batch/bucket, and sequence length 2..1024")
    if (args.online_startup_iterations is not None and (args.online_startup_iterations < 0
            or (args.online_startup_iterations and os.environ.get("HCCL_TRACE_ONLINE_TIMING") != "npu_event"))):
        parser.error("a positive startup iteration count is only supported in npu_event mode")
    try:
        local = int(os.environ["LOCAL_RANK"])
        local_size = int(os.environ["LOCAL_WORLD_SIZE"])
        world_size = int(os.environ["WORLD_SIZE"])
    except (KeyError, ValueError):
        parser.error("start the workload with torchrun under hccl-diag capture")
    profiler = args.profiler_devices or args.devices
    if len(args.devices) != local_size or len(profiler) != local_size or not 0 <= local < local_size or world_size < 2:
        parser.error("supply one runtime/profiler device per local rank and at least two total ranks")
    import torch
    import torch.distributed as dist
    import torch_npu
    from transformers import GPT2Config, GPT2LMHeadModel

    torch_npu.npu.set_device(args.devices[local])
    device = f"npu:{args.devices[local]}"
    dist.init_process_group("hccl")
    try:
        rank, world = dist.get_rank(), dist.get_world_size()
        # All ranks construct identical CPU weights. Inputs use a separate per-rank seed.
        torch.manual_seed(args.seed)
        config = GPT2Config(n_layer=12, n_head=12, n_embd=768, use_cache=False,
                            attn_implementation="eager")
        model = GPT2LMHeadModel(config).to(device).train()
        parameters = tuple(p for p in model.parameters() if p.requires_grad)
        optimizer = torch.optim.AdamW(parameters, lr=1e-4, foreach=False)
        tokens = torch.Generator().manual_seed(args.seed + rank + 1)
        capacity = args.bucket_mib * 1024**2
        timing = NpuEventTiming.from_environment(torch_npu.npu, torch_npu_version=getattr(torch_npu, "__version__", None))
        if timing is not None and not os.environ.get("HCCL_TRACE_ONLINE_ADDR"):
            parser.error("npu_event mode requires HCCL_TRACE_ONLINE_ADDR")
        startup = args.online_startup_iterations if args.online_startup_iterations is not None else (3 if timing else 0)

        def run_rounds(trace, stage, count):
            for iteration in range(count):
                batch = torch.randint(config.vocab_size, (args.batch_size, args.seq_length),
                                      generator=tokens).to(device)
                optimizer.zero_grad(set_to_none=True)
                startup_events = []
                with trace.iteration(iteration, stage=stage) if trace is not None else nullcontext():
                    precision = torch.autocast(device_type="npu", dtype=torch.bfloat16) if args.precision == "bf16" else nullcontext()
                    with precision:
                        loss = model(input_ids=batch, labels=batch).loss
                    loss.backward()
                    # Explicit synchronization keeps the SDK on the submitting thread.
                    for index, grads in enumerate(gradient_buckets(parameters, capacity)):
                        preparation = trace.mark_preparation() if trace is not None and trace.online_probe is not None else None
                        flat = torch.cat([grad.reshape(-1) for grad in grads])
                        if flat.dtype != torch.float32:
                            raise RuntimeError("sample expects FP32 gradients")
                        def submit():
                            return dist.all_reduce(flat, op=dist.ReduceOp.SUM, async_op=True)

                        if trace is None:
                            startup_events.append(timing.startup_collective(submit))
                        else:
                            trace.call_collective(submit, wait_for_work=True, group="gpt2-data-parallel",
                                call_site=f"gradient.bucket.{index}", operation_type="AllReduce",
                                element_count=flat.numel(), dtype="float32", reduction="sum",
                                preparation_start_raw_ns=preparation,
                                preparation_definition="gradient_bucket_pack_to_submit_v1" if preparation is not None else None)
                        flat.div_(world)
                        offset = 0
                        for grad in grads:
                            end = offset + grad.numel()
                            grad.copy_(flat[offset:end].view_as(grad))
                            offset = end
                    optimizer.step()
                    torch_npu.npu.synchronize()
                    if trace is None:
                        max_ns = max(timing.read_elapsed_ns(*events) for events in startup_events)
                        print(f"startup rank={rank} iteration={iteration}: max_event_ms={max_ns/1e6:.6f}", flush=True)
                    else:
                        trace.completion_boundary()
                value = float(loss.detach().float().item())
                if not math.isfinite(value):
                    raise RuntimeError(f"non-finite loss on rank {rank}")
                if rank == 0 and trace is not None:
                    print(f"{stage} {iteration}: loss={value:.4f}", flush=True)

        run_rounds(None, "startup", startup)
        with Trace.from_environment(device_id=profiler[local], timing_adapter=timing) as trace:
            trace.group("gpt2-data-parallel", range(world))
            run_rounds(trace, "warmup", args.warmup)
            run_rounds(trace, "measured", args.iterations)
    finally:
        dist.destroy_process_group()


if __name__ == "__main__":
    main()
