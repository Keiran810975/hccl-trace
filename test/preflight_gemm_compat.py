#!/usr/bin/env python3
"""Bounded, evidence-producing GEMM/bootstrap compatibility probe, not a dataset case."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import time
import traceback


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--hidden-size", type=int, choices=(256, 4096, 8192), default=4096)
    parser.add_argument("--tokens", type=int, default=2048)
    parser.add_argument("--devices", default="1,3,5,7")
    parser.add_argument("--device", type=int, default=7)
    parser.add_argument("--bootstrap", action="store_true")
    parser.add_argument("--backend", choices=("matmul", "linear", "grouped"), default="matmul")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    rank = int(os.environ.get("RANK", "0"))
    result = dict(purpose="gemm_compatibility_preflight", hidden_size=args.hidden_size, tokens=args.tokens,
                  bootstrap=args.bootstrap, backend=args.backend, rank=rank, started_unix_ns=time.time_ns(),
                  environment={k: os.environ.get(k) for k in ("HCCL_OP_EXPANSION_MODE", "ASCEND_OPP_PATH",
                               "ASCEND_HOME_PATH", "LD_LIBRARY_PATH", "ASCEND_CUSTOM_OPP_PATH")})
    status = 1
    import torch
    import torch_npu
    import torch.distributed as dist
    import torch.nn.functional as functional
    result.update(torch=torch.__version__, torch_npu=torch_npu.__version__)
    try:
        device = ([int(v) for v in args.devices.split(",")][int(os.environ["LOCAL_RANK"])]
                  if args.bootstrap else args.device)
        result["device"] = device
        torch_npu.npu.set_device(device)
        if args.bootstrap:
            dist.init_process_group("hccl")
            value = torch.ones(32, dtype=torch.int32, device="npu:{}".format(device))
            dist.all_reduce(value)
            if int(value[0].cpu()) != dist.get_world_size():
                raise ValueError("configuration bootstrap numerical failure")
            dist.all_reduce(value[:1], op=dist.ReduceOp.MAX)
            torch_npu.npu.synchronize()
        left = torch.ones((args.tokens, args.hidden_size), dtype=torch.bfloat16, device="npu:{}".format(device))
        right = torch.full((args.hidden_size, args.hidden_size * 3), 1 / args.hidden_size,
                           dtype=torch.bfloat16, device="npu:{}".format(device))
        if args.backend == "linear":
            output = functional.linear(left, right.transpose(0, 1).contiguous())
        elif args.backend == "grouped":
            output = torch_npu.npu_grouped_matmul([left], [right], split_item=0, group_type=-1)[0]
        else:
            output = torch.matmul(left, right)
        torch_npu.npu.synchronize()
        error = float(torch.max(torch.abs(output.float() - 1)).cpu())
        result["gemm_max_error"] = error
        if error:
            raise ValueError("GEMM numerical failure")
        activated = functional.gelu(output)
        torch_npu.npu.synchronize()
        result["gelu_finite"] = bool(torch.isfinite(activated).all().cpu())
        if not result["gelu_finite"]:
            raise ValueError("GELU numerical failure")
        result["status"] = "passed"
        status = 0
    except Exception as error:
        result.update(status="failed", error=str(error), traceback=traceback.format_exc())
    finally:
        if dist.is_initialized():
            dist.destroy_process_group()
        maps = Path("/proc/self/maps").read_text()
        paths = {line.split()[-1] for line in maps.splitlines()
                 if any(name in line for name in ("libopapi", "libnnopbase", "libhccl", "libhcomm"))
                 and line.split()[-1].startswith("/")}
        result["loaded_libraries"] = {str(p): hashlib.sha256(p.read_bytes()).hexdigest()
                                      for p in map(Path, sorted(paths)) if p.is_file()}
        result["finished_unix_ns"] = time.time_ns()
        target = args.output / ("rank-{}.json".format(rank))
        if target.exists():
            raise FileExistsError("refusing to overwrite compatibility evidence")
        target.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(result), flush=True)
    return status


if __name__ == "__main__":
    raise SystemExit(main())
