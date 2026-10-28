#!/usr/bin/env python3
"""Evaluate a fixed diagnosis using captured rank/time windows, without running an NPU workload."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

if __package__ in (None, ""):
    from single_node_random_suite import evaluate_temporal_localization
else:
    from .single_node_random_suite import evaluate_temporal_localization


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", required=True, type=Path)
    parser.add_argument("--actual-windows", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        report = json.loads(args.report.read_text(encoding="utf-8-sig"))
        windows = json.loads(args.actual_windows.read_text(encoding="utf-8-sig"))
        result = evaluate_temporal_localization(report, windows)
        result.update(schema_version=1, diagnosis_report=str(args.report.resolve()),
                      injection_windows=str(args.actual_windows.resolve()))
        with args.output.open("x", encoding="utf-8") as stream:
            stream.write(json.dumps(result, indent=2) + "\n")
    except (OSError, ValueError, KeyError, TypeError) as error:
        parser.exit(1, "diagnosis evaluation failed: {}\n".format(error))
    print(json.dumps(result), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
