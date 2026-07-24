#!/usr/bin/env python3
"""Validate merged HCCL step trace data quality."""

from __future__ import annotations

import argparse
import csv
import sys
from collections import Counter


RING_STEP_PHASES = frozenset((
    "reduce_scatter_direct",
    "allgather_direct",
))

# These events describe a main Ring communication round.  Prelude/final local
# copies may share the step-0 round anchor or use the rank-size epilogue bucket,
# but a link event in the epilogue bucket is always a contract violation.
RING_MAIN_ROUND_EVENTS = frozenset((
    "tx_ack_start",
    "rx_ack_start",
    "tx_payload_start",
    "rx_payload_copy_start",
    "rx_payload_reduce_start",
    "tx_data_signal_start",
    "rx_data_signal_start",
))


def _int_field(row, name):
    value = str(row.get(name, "")).strip()
    if not value:
        return None
    try:
        return int(value, 0)
    except ValueError:
        return None


def step_contract_violation(row):
    """Return a stable violation code for the current Ring step contract."""
    if row.get("match_status", "") == "profiler_only":
        return ""
    phase = str(row.get("phase", "")).strip()
    if phase not in RING_STEP_PHASES:
        return ""

    step = _int_field(row, "step")
    rank_size = _int_field(row, "rank_size")
    if step is None:
        return "missing_step"
    if rank_size is None:
        return "missing_rank_size"
    if rank_size <= 0:
        return "invalid_rank_size"
    if step < 0 or step >= rank_size:
        return "step_out_of_range"

    event = str(row.get("event", "")).strip()
    if event in RING_MAIN_ROUND_EVENTS and step >= rank_size - 1:
        return "main_event_in_epilogue"
    return ""


def collect_step_contract_errors(rows, limit=None):
    """Return row-addressable Ring step errors without guessing a correction."""
    errors = []
    for csv_row, row in enumerate(rows, start=2):
        reason = step_contract_violation(row)
        if not reason:
            continue
        errors.append(
            "row {row}: reason={reason} node_id={node!r} device_id={device!r} "
            "stream_id={stream!r} task_id={task!r} phase={phase!r} "
            "step={step!r} rank_size={rank_size!r} slice={slice!r} "
            "event={event!r}".format(
                row=csv_row,
                reason=reason,
                node=row.get("node_id", ""),
                device=row.get("device_id", ""),
                stream=row.get("stream_id", ""),
                task=row.get("task_id", ""),
                phase=row.get("phase", ""),
                step=row.get("step", ""),
                rank_size=row.get("rank_size", ""),
                slice=row.get("slice", ""),
                event=row.get("event", ""),
            )
        )
        if limit is not None and len(errors) >= limit:
            break
    return errors


def validate_rows(rows, min_match_rate):
    stats = Counter()
    stats["step_contract_rows"] = 0
    stats["step_contract_violations"] = 0
    for row in rows:
        status = row.get("match_status", "")
        if status == "profiler_only":
            stats["profiler_only"] += 1
            if row.get("duplicate_profiler") == "1":
                stats["duplicate_profiler_rows"] += 1
            continue
        stats["total"] += 1
        stats[status] += 1
        if status == "matched":
            stats["exact_matched"] += 1
        elif status in (
            "correlation_kind_mismatch",
            "notify_metadata_mismatch",
        ):
            stats["invalid_matches"] += 1
        if row.get("duplicate_semantic") == "1":
            stats["duplicate_semantic_rows"] += 1
        if row.get("duplicate_profiler") == "1":
            stats["duplicate_profiler_rows"] += 1
        if str(row.get("phase", "")).strip() in RING_STEP_PHASES:
            stats["step_contract_rows"] += 1
        step_violation = step_contract_violation(row)
        if step_violation:
            stats["step_contract_violations"] += 1
            stats["step_contract_{}".format(step_violation)] += 1
    matched = stats.get("matched", 0)
    stats["match_rate_percent"] = round(
        (matched * 100.0 / stats["total"]), 2) if stats["total"] else 0
    stats["exact_match_rate_percent"] = round(
        stats.get("exact_matched", 0) * 100.0 / stats["total"], 2
    ) if stats["total"] else 0
    ok = stats["total"] > 0 and stats["exact_match_rate_percent"] >= min_match_rate
    if stats.get("duplicate_semantic_rows", 0) or stats.get("duplicate_profiler_rows", 0):
        ok = False
    if stats.get("invalid_matches", 0):
        ok = False
    if stats.get("step_contract_violations", 0):
        ok = False
    return ok, stats


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate merged HCCL step trace coverage.")
    parser.add_argument("merged_csv")
    parser.add_argument("--min-match-rate", type=float, default=95.0)
    args = parser.parse_args()

    with open(args.merged_csv, "r", encoding="utf-8-sig", newline="") as source:
        rows = list(csv.DictReader(source))
    ok, stats = validate_rows(rows, args.min_match_rate)
    for key in sorted(stats):
        print("{}={}".format(key, stats[key]))
    for error in collect_step_contract_errors(rows, limit=20):
        print("step_contract_error={}".format(error), file=sys.stderr)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
