#!/usr/bin/env python3
"""Require numerical success records from every local workload worker."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path


def validate(directory: Path, node_rank: int, nnodes: int, nproc: int) -> None:
    expected = set(range(node_rank * nproc, (node_rank + 1) * nproc))
    found = set()
    for path in directory.glob("rank-*.json"):
        result = json.loads(path.read_text(encoding="utf-8"))
        rank = result["rank"]
        error = float(result["max_error"])
        tolerance = 1e-2 if result.get("dtype") in ("fp16", "bf16") else 1e-5
        if (rank not in expected or rank in found or path.name != f"rank-{rank}.json"
                or result["world_size"] != nnodes * nproc or result["status"] != "passed"
                or not math.isfinite(error) or not 0 <= error <= tolerance):
            raise ValueError(f"invalid workload success record: {path}")
        found.add(rank)
    if found != expected:
        raise ValueError(f"missing successful workload ranks: {sorted(expected - found)}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    parser.add_argument("--node-rank", type=int, required=True)
    parser.add_argument("--nnodes", type=int, required=True)
    parser.add_argument("--nproc-per-node", type=int, required=True)
    args = parser.parse_args()
    try:
        validate(args.directory, args.node_rank, args.nnodes, args.nproc_per_node)
    except (OSError, ValueError, KeyError, TypeError) as error:
        parser.exit(1, f"workload validation failed: {error}\n")
    print("workload_validation=passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
