#!/usr/bin/env python3
"""Render merged HCCL step trace rows as an SVG timeline.

The default layout is logical instead of strictly time-scaled: columns are
phase/step/event buckets and dense slice-level tasks are stacked inside each
rank/stream lane. This keeps the graph readable when real task durations are
much shorter than the full operation span. Use ``--layout time`` to render the
raw msprof task_start/task_stop axis.
"""

from __future__ import annotations

import argparse
import csv
import html
import math
import os
import sys
from collections import defaultdict
from pathlib import Path
from typing import Dict, Iterable, List, Tuple

if __package__ in (None, ""):
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from diagnosis.schema import write_csv
else:
    from .schema import write_csv


EVENT_COLOR = {
    "allreduce_start": ("#f5f5f5", "#666666"),
    "copy_start": ("#e7f0ff", "#376eb5"),
    "tx_ack_start": ("#fff3c4", "#9a7500"),
    "rx_ack_start": ("#ffe8d2", "#b26000"),
    "tx_data_signal_start": ("#f2e6ff", "#7445b7"),
    "rx_data_signal_start": ("#e9e1ff", "#5b43a8"),
    "tx_payload_start": ("#ddf7e7", "#26844a"),
    "rx_payload_reduce_start": ("#ffd9bd", "#b45f06"),
    "rx_payload_copy_start": ("#d7f2ff", "#1683a8"),
}

HARDWARE_COLOR = {
    "sdma": ("#d7f2ff", "#1683a8"),
    "notify_record": ("#fff3c4", "#9a7500"),
    "notify_wait": ("#ffe8d2", "#b26000"),
    "reduce_inline": ("#ffd9bd", "#b45f06"),
    "rdma": ("#ddf7e7", "#26844a"),
}

PHASE_ORDER = {
    "allreduce_executor": 0,
    "reduce_scatter_direct": 1,
    "reduce_scatter": 1,
    "allgather_direct": 2,
    "allgather": 2,
}

EVENT_ORDER = {
    "allreduce_start": 0,
    "copy_start": 1,
    "tx_ack_start": 2,
    "rx_ack_start": 3,
    "tx_data_signal_start": 4,
    "rx_data_signal_start": 5,
    "tx_payload_start": 6,
    "rx_payload_reduce_start": 7,
    "rx_payload_copy_start": 8,
}


def to_int(value: object, default: int = -1) -> int:
    text = "" if value is None else str(value).strip()
    if not text:
        return default
    try:
        return int(float(text))
    except ValueError:
        return default


def to_float(value: object, default: float = math.nan) -> float:
    text = "" if value is None else str(value).strip()
    if not text:
        return default
    try:
        return float(text)
    except ValueError:
        return default


def read_rows(path: Path, include_profiler_only: bool = False) -> List[dict]:
    rows: List[dict] = []
    with path.open("r", encoding="utf-8-sig", newline="") as source:
        for index, row in enumerate(csv.DictReader(source)):
            status = row.get("match_status")
            if status == "profiler_only" and not include_profiler_only:
                continue
            if status not in ("matched", "profiler_only"):
                continue
            start = to_float(row.get("task_start"))
            stop = to_float(row.get("task_stop"))
            duration = to_float(row.get("duration"), 0.0)
            if math.isnan(start) and math.isnan(stop):
                continue
            if math.isnan(stop):
                stop = start + max(duration, 0.0)
            if math.isnan(start):
                start = stop - max(duration, 0.0)
            if stop < start:
                start, stop = stop, start
            item = dict(row)
            item.update({
                "_row_index": index,
                "_node_id": row.get("node_id", ""),
                "_device_id": to_int(row.get("device_id")),
                "_rank": to_int(row.get("user_rank", row.get("rank"))),
                "_stream_id": to_int(row.get("stream_id")),
                "_task_id": to_int(row.get("task_id")),
                "_profiler_task_id": to_int(row.get("profiler_task_id", row.get("task_id"))),
                "_subtask_id": to_int(row.get("subtask_id")),
                "_phase": row.get("phase", ""),
                "_event": row.get("event", ""),
                "_semantic": row.get("semantic", ""),
                "_step": to_int(row.get("step")),
                "_slice": to_int(row.get("slice")),
                "_start": start,
                "_stop": stop,
                "_duration": max(0.0, stop - start),
            })
            rows.append(item)
    rows.sort(key=timeline_sort_key)
    return rows


def timeline_sort_key(row: dict) -> Tuple[int, int, int, int, int, int, float, int]:
    return (
        row["_device_id"],
        row["_rank"],
        row["_stream_id"],
        PHASE_ORDER.get(row["_phase"], 99),
        row["_step"],
        EVENT_ORDER.get(row["_event"], 99),
        row["_start"],
        row["_task_id"],
    )


def short_label(row: dict) -> str:
    event = row.get("_event", "")
    semantic = row.get("_semantic", "")
    labels = {
        "allreduce_start": "op",
        "copy_start": "copy",
        "tx_ack_start": "tx_ack",
        "rx_ack_start": "rx_ack",
        "tx_data_signal_start": "tx_sig",
        "rx_data_signal_start": "rx_sig",
        "tx_payload_start": "tx_payload",
        "rx_payload_reduce_start": "rx_reduce",
        "rx_payload_copy_start": "rx_copy",
    }
    return labels.get(event, event or semantic or row.get("event_name", "") or row.get("profiler_task_kind", ""))


def row_color(row: dict):
    if row.get("_event"):
        return EVENT_COLOR.get(row["_event"], ("#eeeeee", "#777777"))
    return HARDWARE_COLOR.get(row.get("profiler_task_kind", ""), ("#eeeeee", "#777777"))


def phase_label(phase: str) -> str:
    labels = {
        "allreduce_executor": "executor",
        "reduce_scatter_direct": "reduce_scatter",
        "allgather_direct": "allgather",
    }
    return labels.get(phase, phase or "unknown")


def lane_key(row: dict) -> Tuple[str, int, int, int]:
    return (row["_node_id"], row["_device_id"], row["_rank"], row["_stream_id"])


def logical_column_key(row: dict) -> Tuple[int, str, int, int, str]:
    return (
        PHASE_ORDER.get(row["_phase"], 99),
        row["_phase"],
        row["_step"],
        EVENT_ORDER.get(row["_event"], 99),
        row["_event"],
    )


def build_gap_rows(rows: List[dict]) -> List[dict]:
    by_lane: Dict[Tuple[str, int, int, int], List[dict]] = defaultdict(list)
    for row in rows:
        by_lane[lane_key(row)].append(row)

    gaps: List[dict] = []
    for key, lane_rows in sorted(by_lane.items()):
        lane_rows.sort(key=timeline_sort_key)
        for prev, cur in zip(lane_rows, lane_rows[1:]):
            gaps.append({
                "node_id": key[0],
                "device_id": key[1],
                "rank": key[2],
                "stream_id": key[3],
                "prev_event": prev.get("event", ""),
                "prev_phase": prev.get("phase", ""),
                "prev_step": prev.get("step", ""),
                "prev_task_id": prev.get("task_id", ""),
                "prev_stop": prev["_stop"],
                "cur_event": cur.get("event", ""),
                "cur_phase": cur.get("phase", ""),
                "cur_step": cur.get("step", ""),
                "cur_task_id": cur.get("task_id", ""),
                "cur_start": cur["_start"],
                "gap": cur["_start"] - prev["_stop"],
            })
    return gaps


def export_nodes(path: Path, rows: Iterable[dict]) -> None:
    out = []
    for index, row in enumerate(rows):
        out.append({
            "node_index": index,
            "node_id": row.get("node_id", ""),
            "device_id": row.get("device_id", ""),
            "rank": row.get("user_rank", ""),
            "stream_id": row.get("stream_id", ""),
            "task_id": row.get("task_id", ""),
            "profiler_task_id": row.get("profiler_task_id", ""),
            "subtask_id": row.get("subtask_id", ""),
            "connection_id": row.get("connection_id", ""),
            "match_method": row.get("match_method", ""),
            "match_confidence": row.get("match_confidence", ""),
            "phase": row.get("phase", ""),
            "event": row.get("event", ""),
            "semantic": row.get("semantic", ""),
            "step": row.get("step", ""),
            "slice": row.get("slice", ""),
            "task_start": row["_start"],
            "task_stop": row["_stop"],
            "duration": row["_duration"],
            "label": short_label(row),
        })
    write_csv(str(path), list(out[0].keys()) if out else ["node_index"], out)


def task_title(row: dict) -> str:
    return (
        f'device={row["_device_id"]} rank={row["_rank"]} stream={row["_stream_id"]} '
        f'semantic_task={row["_task_id"]} profiler_task={row["_profiler_task_id"]} subtask={row["_subtask_id"]}\n'
        f'phase={row["_phase"]} event={row["_event"]} semantic={row["_semantic"]}\n'
        f'hardware={row.get("event_name", "")} match={row.get("match_method", "")} confidence={row.get("match_confidence", "")}\n'
        f'step={row["_step"]} slice={row["_slice"]}\n'
        f'{row["_start"]:.3f}..{row["_stop"]:.3f} us duration={row["_duration"]:.3f} us'
    )


def render_logical_svg(rows: List[dict], output: Path, col_width: int, node_width: int) -> None:
    if not rows:
        raise ValueError("no matched timed rows to render")

    left = 250
    right = 80
    top = 126
    bottom = 76
    node_h = 22
    slot_gap = 5
    lane_gap = 12
    group_gap = 24
    header_h = 72

    columns = sorted({logical_column_key(row) for row in rows})
    col_index = {key: index for index, key in enumerate(columns)}
    lanes = sorted({lane_key(row) for row in rows})

    per_lane_column_counts: Dict[Tuple[str, int, int, int], Dict[Tuple[int, str, int, int, str], int]] = defaultdict(lambda: defaultdict(int))
    for row in rows:
        per_lane_column_counts[lane_key(row)][logical_column_key(row)] += 1

    lane_heights: Dict[Tuple[str, int, int, int], int] = {}
    for lane in lanes:
        max_stack = max(per_lane_column_counts[lane].values()) if per_lane_column_counts[lane] else 1
        lane_heights[lane] = max(34, 8 + max_stack * (node_h + slot_gap))

    lane_y = {}
    y = top + header_h
    last_group = None
    for lane in lanes:
        group = lane[:3]
        if last_group is not None and group != last_group:
            y += group_gap
        lane_y[lane] = y
        y += lane_heights[lane] + lane_gap
        last_group = group

    width = left + max(1, len(columns)) * col_width + right
    height = y + bottom
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        '<rect x="0" y="0" width="100%" height="100%" fill="#fff"/>',
        f'<text x="{left}" y="30" font-family="Arial" font-size="22" font-weight="700">HCCL step trace logical timeline</text>',
        f'<text x="{left}" y="54" font-family="Arial" font-size="12" fill="#555">Rows: {len(rows)}. Columns are phase / step / event; dense slices stack vertically inside each lane. Hover nodes for real timing.</text>',
    ]

    # Column headers and vertical bands.
    previous_phase = None
    for key, index in col_index.items():
        _phase_order, phase, step, _event_order, event = key
        x = left + index * col_width
        fill = "#fbfbfb" if index % 2 == 0 else "#ffffff"
        parts.append(f'<rect x="{x}" y="76" width="{col_width}" height="{height - bottom - 66}" fill="{fill}"/>')
        parts.append(f'<line x1="{x}" y1="76" x2="{x}" y2="{height - bottom + 8}" stroke="#e5e5e5"/>')
        if phase != previous_phase:
            parts.append(f'<text x="{x + 8}" y="94" font-family="Arial" font-size="12" font-weight="700" fill="#333">{html.escape(phase_label(phase))}</text>')
            previous_phase = phase
        parts.append(f'<text x="{x + col_width / 2:.1f}" y="113" text-anchor="middle" font-family="Arial" font-size="10" fill="#555">step {step}</text>')
        parts.append(f'<text x="{x + col_width / 2:.1f}" y="128" text-anchor="middle" font-family="Arial" font-size="9" fill="#777">{html.escape(short_label({"_event": event}))}</text>')
    parts.append(f'<line x1="{left + len(columns) * col_width}" y1="76" x2="{left + len(columns) * col_width}" y2="{height - bottom + 8}" stroke="#e5e5e5"/>')

    # Lane labels.
    for lane in lanes:
        node_id, device_id, rank, stream_id = lane
        yy = lane_y[lane]
        lane_h = lane_heights[lane]
        label = f'{node_id or "node"} dev {device_id} rank {rank} stream {stream_id}'
        parts.append(f'<text x="20" y="{yy + 20}" font-family="Arial" font-size="11" fill="#333">{html.escape(label)}</text>')
        parts.append(f'<line x1="{left - 10}" y1="{yy + lane_h / 2:.1f}" x2="{width - right}" y2="{yy + lane_h / 2:.1f}" stroke="#f0f0f0"/>')

    # Assign stack slots per lane/column.
    slot_cursor: Dict[Tuple[Tuple[str, int, int, int], Tuple[int, str, int, int, str]], int] = defaultdict(int)
    for row in sorted(rows, key=lambda item: (lane_key(item), logical_column_key(item), item["_slice"], item["_start"])):
        lane = lane_key(row)
        col_key = logical_column_key(row)
        slot_key = (lane, col_key)
        slot = slot_cursor[slot_key]
        slot_cursor[slot_key] += 1
        x = left + col_index[col_key] * col_width + (col_width - node_width) / 2
        y = lane_y[lane] + 4 + slot * (node_h + slot_gap)
        fill, stroke = row_color(row)
        label = short_label(row)
        title = task_title(row)
        parts.append(f'<rect x="{x:.1f}" y="{y:.1f}" width="{node_width}" height="{node_h}" rx="3" ry="3" fill="{fill}" stroke="{stroke}" stroke-width="1"><title>{html.escape(title)}</title></rect>')
        if node_width >= 72:
            parts.append(f'<text x="{x + node_width / 2:.1f}" y="{y + 14:.1f}" text-anchor="middle" font-family="Arial" font-size="8.5">{html.escape(label)}</text>')

    # Legend.
    legend_x = left
    legend_y = height - 22
    x = legend_x
    for event, (fill, stroke) in EVENT_COLOR.items():
        label = short_label({"_event": event, "_semantic": ""})
        parts.append(f'<rect x="{x}" y="{legend_y - 10}" width="12" height="8" fill="{fill}" stroke="{stroke}"/>')
        parts.append(f'<text x="{x + 16}" y="{legend_y - 3}" font-family="Arial" font-size="9">{html.escape(label)}</text>')
        x += 90
        if x > width - 170:
            x = legend_x
            legend_y += 14

    parts.append('</svg>')
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text('\n'.join(parts), encoding='utf-8')


def assign_time_slots(rows: List[dict]) -> Dict[Tuple[str, int, int, int], int]:
    by_lane: Dict[Tuple[str, int, int, int], List[dict]] = defaultdict(list)
    for row in rows:
        by_lane[lane_key(row)].append(row)

    slot_counts: Dict[Tuple[str, int, int, int], int] = {}
    for lane, lane_rows in by_lane.items():
        slot_stops: List[float] = []
        for row in sorted(lane_rows, key=lambda item: (item["_start"], item["_stop"], timeline_sort_key(item))):
            slot = None
            for index, stop in enumerate(slot_stops):
                if row["_start"] >= stop:
                    slot = index
                    break
            if slot is None:
                slot = len(slot_stops)
                slot_stops.append(row["_stop"])
            else:
                slot_stops[slot] = row["_stop"]
            row["_time_slot"] = slot
        slot_counts[lane] = max(1, len(slot_stops))
    return slot_counts


def render_time_svg(rows: List[dict], gaps: List[dict], output: Path, max_width: int, min_px_per_us: float,
                    show_gap_threshold: float, time_scale: str, time_span_us: float = 0.0) -> None:
    if not rows:
        raise ValueError("no matched timed rows to render")

    min_t = min(row["_start"] for row in rows)
    max_t = max(row["_stop"] for row in rows)
    actual_span = max(1.0, max_t - min_t)
    if time_span_us < 0:
        raise ValueError("time span must be non-negative")
    if time_span_us and time_span_us < actual_span:
        raise ValueError(
            f"time span {time_span_us:.3f} us is shorter than task span {actual_span:.3f} us"
        )
    span = time_span_us or actual_span
    left = 250
    right = 80
    top = 92
    bottom = 86
    lane_gap = 7
    group_gap = 24
    min_node_w = 8
    node_h = 20
    slot_gap = 4
    fit_px_per_us = (max_width - left - right) / span
    px_per_us = fit_px_per_us if time_scale == "fit" else max(fit_px_per_us, max(min_px_per_us, 0.001))
    width = int(left + span * px_per_us + right)

    lanes = sorted({lane_key(row) for row in rows})
    slot_counts = assign_time_slots(rows)
    lane_heights = {lane: max(28, 8 + slot_counts.get(lane, 1) * (node_h + slot_gap)) for lane in lanes}
    lane_y = {}
    y = top
    last_group = None
    for lane in lanes:
        group = lane[:3]
        if last_group is not None and group != last_group:
            y += group_gap
        lane_y[lane] = y
        y += lane_heights[lane] + lane_gap
        last_group = group
    height = y + bottom

    def x_for(t: float) -> float:
        return left + (t - min_t) * px_per_us

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        '<rect x="0" y="0" width="100%" height="100%" fill="#fff"/>',
        f'<text x="{left}" y="30" font-family="Arial" font-size="22" font-weight="700">HCCL step trace time-scaled timeline</text>',
        f'<text x="{left}" y="54" font-family="Arial" font-size="12" fill="#555">Rows: {len(rows)}. Real x-axis uses msprof task_start/task_stop, origin {min_t:.3f} us.</text>',
    ]

    axis_y = height - 48
    parts.append(f'<line x1="{left}" y1="{axis_y}" x2="{width - right}" y2="{axis_y}" stroke="#222"/>')
    for i in range(11):
        rel = span * i / 10
        x = left + rel * px_per_us
        parts.append(f'<line x1="{x:.1f}" y1="{top - 18}" x2="{x:.1f}" y2="{axis_y}" stroke="#eee"/>')
        parts.append(f'<text x="{x:.1f}" y="{axis_y + 22}" text-anchor="middle" font-family="Arial" font-size="10">{rel:.0f} us</text>')

    for lane in lanes:
        node_id, device_id, rank, stream_id = lane
        yy = lane_y[lane]
        label = f'{node_id or "node"} dev {device_id} rank {rank} stream {stream_id}'
        lane_h = lane_heights[lane]
        parts.append(f'<text x="22" y="{yy + 17}" font-family="Arial" font-size="11" fill="#333">{html.escape(label)}</text>')
        parts.append(f'<line x1="{left - 10}" y1="{yy + lane_h / 2:.1f}" x2="{width - right}" y2="{yy + lane_h / 2:.1f}" stroke="#f2f2f2"/>')

    for gap in gaps:
        if float(gap["gap"]) < show_gap_threshold:
            continue
        lane = (str(gap["node_id"]), to_int(gap["device_id"]), to_int(gap["rank"]), to_int(gap["stream_id"]))
        if lane not in lane_y:
            continue
        x1 = x_for(to_float(gap["prev_stop"]))
        x2 = x_for(to_float(gap["cur_start"]))
        if x2 <= x1:
            continue
        yy = lane_y[lane] + lane_heights[lane] - 2
        parts.append(f'<line x1="{x1:.1f}" y1="{yy:.1f}" x2="{x2:.1f}" y2="{yy:.1f}" stroke="#999" stroke-dasharray="2 2"/>')
        if x2 - x1 > 24:
            parts.append(f'<text x="{(x1 + x2) / 2:.1f}" y="{yy - 2:.1f}" text-anchor="middle" font-family="Arial" font-size="8" fill="#666">{float(gap["gap"]):.1f}</text>')

    for row in rows:
        x = x_for(row["_start"])
        w = max(min_node_w, row["_duration"] * px_per_us)
        yy = lane_y[lane_key(row)] + 4 + row.get("_time_slot", 0) * (node_h + slot_gap)
        h = node_h
        fill, stroke = row_color(row)
        parts.append(f'<rect x="{x:.1f}" y="{yy:.1f}" width="{w:.1f}" height="{h:.1f}" rx="2" ry="2" fill="{fill}" stroke="{stroke}"><title>{html.escape(task_title(row))}</title></rect>')
        if w > 42:
            parts.append(f'<text x="{x + w / 2:.1f}" y="{yy + 14:.1f}" text-anchor="middle" font-family="Arial" font-size="8.5">{html.escape(short_label(row))}</text>')

    parts.append('</svg>')
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text('\n'.join(parts), encoding='utf-8')


def main() -> int:
    parser = argparse.ArgumentParser(description="Render merged HCCL step trace rows as an SVG timeline.")
    parser.add_argument("merged_csv", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--layout", choices=("logical", "time"), default="logical")
    parser.add_argument("--col-width", type=int, default=146)
    parser.add_argument("--node-width", type=int, default=112)
    parser.add_argument("--max-width", type=int, default=28000)
    parser.add_argument("--min-px-per-us", type=float, default=0.025)
    parser.add_argument("--show-gap-threshold", type=float, default=20.0)
    parser.add_argument("--time-scale", choices=("minimum", "fit"), default="minimum")
    parser.add_argument(
        "--time-span-us",
        type=float,
        default=0.0,
        help="Use a fixed relative time span for comparable time-layout SVGs.",
    )
    args = parser.parse_args()

    output = args.output or args.merged_csv.with_name(args.merged_csv.stem + "_timeline.svg")
    rows = read_rows(
        args.merged_csv,
        include_profiler_only=args.layout == "time",
    )
    gaps = build_gap_rows(rows)
    if args.layout == "logical":
        render_logical_svg(rows, output, args.col_width, args.node_width)
    else:
        render_time_svg(
            rows,
            gaps,
            output,
            args.max_width,
            args.min_px_per_us,
            args.show_gap_threshold,
            args.time_scale,
            args.time_span_us,
        )
    nodes_path = output.with_name(output.stem + "_nodes.csv")
    gaps_path = output.with_name(output.stem + "_gaps.csv")
    export_nodes(nodes_path, rows)
    write_csv(str(gaps_path), list(gaps[0].keys()) if gaps else ["gap"], gaps)
    print(f"rows={len(rows)}")
    print(f"gaps={len(gaps)}")
    print(f"layout={args.layout}")
    print(f"svg={output}")
    print(f"nodes={nodes_path}")
    print(f"gaps_csv={gaps_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
