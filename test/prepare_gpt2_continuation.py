#!/usr/bin/env python3
"""Freeze the thirty unexecuted GPT-2 cases as a separate Node3/50-iteration cohort."""
from __future__ import annotations

import argparse
from pathlib import Path

if __package__:
    from .gpt2_diagnosis_suite import write_continuation
else:
    from gpt2_diagnosis_suite import write_continuation


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--parent", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--physical-node", choices=("node0", "node3"), default="node3")
    args = parser.parse_args()
    plan = write_continuation(args.parent, args.output, physical_node=args.physical_node)
    print("Prepared", plan["requested_runs"], "runs; original completed cases remain unchanged")


if __name__ == "__main__":
    main()
