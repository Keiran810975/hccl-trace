#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import torch
import torch_npu


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate sustained device-to-device copy traffic on one NPU."
    )
    parser.add_argument("--device", type=int, default=0)
    parser.add_argument("--bytes", type=int, default=512 * 1024 * 1024)
    parser.add_argument("--seconds", type=float, default=45.0)
    parser.add_argument("--batch-copies", type=int, default=8)
    parser.add_argument("--ready-file", type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.bytes <= 0 or args.seconds <= 0 or args.batch_copies <= 0:
        raise ValueError("bytes, seconds, and batch-copies must be positive")

    torch_npu.npu.set_device(args.device)
    element_count = args.bytes // torch.tensor([], dtype=torch.float32).element_size()
    source = torch.ones(element_count, dtype=torch.float32, device=f"npu:{args.device}")
    destination = torch.empty_like(source)
    destination.copy_(source, non_blocking=True)
    torch_npu.npu.synchronize()

    if args.ready_file is not None:
        args.ready_file.parent.mkdir(parents=True, exist_ok=True)
        args.ready_file.write_text("ready\n", encoding="utf-8")

    started = time.monotonic()
    deadline = started + args.seconds
    copies = 0
    while time.monotonic() < deadline:
        for _ in range(args.batch_copies):
            destination.copy_(source, non_blocking=True)
            copies += 1
        torch_npu.npu.synchronize()

    elapsed = time.monotonic() - started
    checksum = float(destination[0].cpu())
    result = {
        "device": args.device,
        "buffer_bytes": args.bytes,
        "batch_copies": args.batch_copies,
        "copies": copies,
        "elapsed_seconds": elapsed,
        "copied_gib": copies * args.bytes / (1024**3),
        "effective_gib_per_second": copies * args.bytes / (1024**3) / elapsed,
        "checksum": checksum,
        "status": "passed" if checksum == 1.0 else "failed",
    }
    print(json.dumps(result, sort_keys=True), flush=True)
    return 0 if checksum == 1.0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
