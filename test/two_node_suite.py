#!/usr/bin/env python3
"""Paired two-node/four-rank Transformer-CommMix cases and local runner."""

from __future__ import annotations

if __package__ in (None, ""):
    from four_node_suite import main
else:
    from .four_node_suite import main


if __name__ == "__main__":
    raise SystemExit(main(nnodes=2, ranks_per_node=2))
