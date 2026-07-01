#!/usr/bin/env python3
"""Render task dependency edges from merged HCCL step trace rows."""

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


PHASE_ORDER = {
    "reduce_scatter_direct": 0,
    "reduce_scatter": 0,
    "allgather_direct": 1,
    "allgather": 1,
}

PHASE_GROUP_ORDER = {
    "reduce_scatter": 0,
    "allgather": 1,
}

EVENT_ORDER = {
    "rx_ack_start": 0,
    "tx_ack_start": 1,
    "rx_data_signal_start": 2,
    "tx_data_signal_start": 3,
    "rx_payload_reduce_start": 4,
    "rx_payload_copy_start": 5,
    "tx_payload_start": 6,
    "copy_start": 7,
}

EVENT_LABEL = {
    "rx_ack_start": "rx_ack",
    "tx_ack_start": "tx_ack",
    "rx_data_signal_start": "rx_sig",
    "tx_data_signal_start": "tx_sig",
    "rx_payload_reduce_start": "rx_reduce",
    "rx_payload_copy_start": "rx_copy",
    "tx_payload_start": "tx_payload",
    "copy_start": "copy",
}

EVENT_COLOR = {
    "rx_ack_start": ("#ffe8d2", "#b26000"),
    "tx_ack_start": ("#fff3c4", "#9a7500"),
    "rx_data_signal_start": ("#e9e1ff", "#5b43a8"),
    "tx_data_signal_start": ("#f2e6ff", "#7445b7"),
    "rx_payload_reduce_start": ("#ffd9bd", "#b45f06"),
    "rx_payload_copy_start": ("#d7f2ff", "#1683a8"),
    "tx_payload_start": ("#ddf7e7", "#26844a"),
    "copy_start": ("#e7f0ff", "#376eb5"),
}

EDGE_COLOR = {
    "same_rank_sequence": "#444444",
    "same_rank_step": "#777777",
    "right_neighbor_ack_dep": "#d98000",
    "upstream_data_signal_dep": "#276fbf",
    "upstream_prev_step": "#1f77b4",
    "phase_bridge": "#7b3fb3",
    "signal_payload": "#2b8a3e",
}

DEFAULT_EDGE_KINDS = (
    "same_rank_sequence",
    "right_neighbor_ack_dep",
    "upstream_data_signal_dep",
    "same_rank_step",
    "upstream_prev_step",
    "phase_bridge",
    "signal_payload",
)
DEFAULT_EVENTS = (
    "rx_ack_start",
    "rx_data_signal_start",
    "rx_payload_reduce_start",
    "rx_payload_copy_start",
    "tx_payload_start",
    "copy_start",
)


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


def phase_group(phase: str) -> str:
    if phase in ("reduce_scatter_direct", "reduce_scatter"):
        return "reduce_scatter"
    if phase in ("allgather_direct", "allgather"):
        return "allgather"
    return phase or "unknown"


def short_label(event: str) -> str:
    return EVENT_LABEL.get(event, event or "task")


def read_rows(path: Path, events: Iterable[str], include_unmatched: bool = False) -> List[dict]:
    event_set = set(events)
    rows: List[dict] = []
    with path.open("r", encoding="utf-8-sig", newline="") as source:
        for index, row in enumerate(csv.DictReader(source)):
            if not include_unmatched and row.get("match_status") != "matched":
                continue
            phase = row.get("phase", "")
            if phase not in PHASE_ORDER:
                continue
            event = row.get("event", "")
            if event_set and event not in event_set:
                continue
            start = to_float(row.get("task_start"))
            stop = to_float(row.get("task_stop"))
            duration = to_float(row.get("duration"), 0.0)
            if math.isnan(start) and math.isnan(stop):
                start = float(index)
                stop = start + max(duration, 0.0)
            elif math.isnan(stop):
                stop = start + max(duration, 0.0)
            elif math.isnan(start):
                start = stop - max(duration, 0.0)
            if stop < start:
                start, stop = stop, start
            item = dict(row)
            item.update({
                "_source_row": index,
                "_phase_group": phase_group(phase),
                "_phase_order": PHASE_ORDER.get(phase, 99),
                "_event_order": EVENT_ORDER.get(event, 99),
                "_node_id": row.get("node_id", ""),
                "_device_id": to_int(row.get("device_id")),
                "_rank": to_int(row.get("user_rank", row.get("rank"))),
                "_rank_size": to_int(row.get("rank_size")),
                "_stream_id": to_int(row.get("stream_id")),
                "_task_id": to_int(row.get("task_id")),
                "_step": to_int(row.get("step")),
                "_slice": to_int(row.get("slice")),
                "_start": start,
                "_stop": stop,
                "_duration": max(0.0, stop - start),
            })
            if item["_rank"] < 0 or item["_step"] < 0:
                continue
            rows.append(item)
    rows.sort(key=row_sort_key)
    return rows


def row_sort_key(row: dict) -> Tuple[int, int, int, int, int, int, float, int]:
    return (
        row["_rank"],
        row["_phase_order"],
        row["_step"],
        row["_event_order"],
        row["_slice"],
        row["_stream_id"],
        row["_start"],
        row["_task_id"],
    )


def infer_rank_size(rows: List[dict], explicit: int = -1) -> int:
    if explicit > 0:
        return explicit
    for row in rows:
        if row["_rank_size"] > 0:
            return row["_rank_size"]
    ranks = {row["_rank"] for row in rows if row["_rank"] >= 0}
    return max(ranks) + 1 if ranks else 0


def neighbor_rank(rank: int, rank_size: int, direction: str) -> int:
    if rank < 0 or rank_size <= 0:
        return -1
    if direction == "next":
        return (rank + 1) % rank_size
    return (rank - 1 + rank_size) % rank_size


def upstream_rank(rank: int, rank_size: int, direction: str) -> int:
    return neighbor_rank(rank, rank_size, direction)


def right_neighbor_rank(rank: int, rank_size: int, upstream_direction: str) -> int:
    opposite = "next" if upstream_direction == "previous" else "previous"
    return neighbor_rank(rank, rank_size, opposite)


def preferred_payload_events(phase: str) -> Tuple[str, ...]:
    if phase == "reduce_scatter":
        return ("rx_payload_reduce_start", "tx_payload_start", "copy_start")
    if phase == "allgather":
        return ("rx_payload_copy_start", "tx_payload_start", "copy_start")
    return ("rx_payload_reduce_start", "rx_payload_copy_start", "tx_payload_start", "copy_start")


def select_representatives(rows: List[dict]) -> Dict[Tuple[str, int, int], dict]:
    by_step: Dict[Tuple[str, int, int], List[dict]] = defaultdict(list)
    for row in rows:
        if row["_rank"] < 0 or row["_step"] < 0:
            continue
        by_step[(row["_phase_group"], row["_rank"], row["_step"])].append(row)

    reps: Dict[Tuple[str, int, int], dict] = {}
    for key, candidates in by_step.items():
        phase, _rank, _step = key
        event_rank = {event: index for index, event in enumerate(preferred_payload_events(phase))}
        reps[key] = min(
            candidates,
            key=lambda row: (
                event_rank.get(row.get("event", ""), 99),
                row["_slice"] if row["_slice"] >= 0 else 999999,
                row["_start"],
                row["_source_row"],
            ),
        )
    return reps


def build_nodes(rows: List[dict]) -> List[dict]:
    nodes = []
    for index, row in enumerate(rows):
        node_key = f"n{index}"
        row["_graph_id"] = node_key
        nodes.append({
            "graph_id": node_key,
            "source_row": row["_source_row"],
            "node_id": row.get("node_id", ""),
            "device_id": row.get("device_id", ""),
            "rank": row.get("user_rank", ""),
            "rank_size": row.get("rank_size", ""),
            "stream_id": row.get("stream_id", ""),
            "task_id": row.get("task_id", ""),
            "phase": row.get("phase", ""),
            "phase_group": row["_phase_group"],
            "event": row.get("event", ""),
            "semantic": row.get("semantic", ""),
            "step": row.get("step", ""),
            "slice": row.get("slice", ""),
            "task_start": row["_start"],
            "task_stop": row["_stop"],
            "duration": row["_duration"],
            "label": short_label(row.get("event", "")),
        })
    return nodes


def prev_payload_key(phase: str, rank: int, step: int, reps: Dict[Tuple[str, int, int], dict]):
    if step > 0:
        return (phase, rank, step - 1)
    if phase == "allgather":
        rs_steps = [item_step for item_phase, item_rank, item_step in reps if item_phase == "reduce_scatter" and item_rank == rank]
        if rs_steps:
            return ("reduce_scatter", rank, max(rs_steps))
    return None


def build_edges(rows: List[dict], edge_kinds: Iterable[str], rank_size: int, direction: str) -> List[dict]:
    enabled = set(edge_kinds)
    reps = select_representatives(rows)
    edges = []
    seen = set()

    def add(kind: str, src: dict, dst: dict, reason: str) -> None:
        if kind not in enabled or not src or not dst:
            return
        if src is dst:
            return
        key = (kind, src["_graph_id"], dst["_graph_id"])
        if key in seen:
            return
        seen.add(key)
        edges.append({
            "edge_id": f"e{len(edges)}",
            "kind": kind,
            "src": src["_graph_id"],
            "dst": dst["_graph_id"],
            "src_rank": src["_rank"],
            "dst_rank": dst["_rank"],
            "src_phase": src["_phase_group"],
            "dst_phase": dst["_phase_group"],
            "src_step": src["_step"],
            "dst_step": dst["_step"],
            "src_event": src.get("event", ""),
            "dst_event": dst.get("event", ""),
            "reason": reason,
        })

    by_rank: Dict[int, List[dict]] = defaultdict(list)
    for row in rows:
        by_rank[row["_rank"]].append(row)
    for rank, rank_rows in by_rank.items():
        ordered = sorted(rank_rows, key=row_sort_key)
        for prev, cur in zip(ordered, ordered[1:]):
            add("same_rank_sequence", prev, cur, "same-rank task program order")

    by_phase_rank: Dict[Tuple[str, int], List[int]] = defaultdict(list)
    for phase, rank, step in reps:
        by_phase_rank[(phase, rank)].append(step)

    for (phase, rank), steps in by_phase_rank.items():
        ordered = sorted(set(step for step in steps if step >= 0))
        for prev_step, cur_step in zip(ordered, ordered[1:]):
            add(
                "same_rank_step",
                reps.get((phase, rank, prev_step)),
                reps.get((phase, rank, cur_step)),
                "same rank next step waits for previous step payload",
            )

    for (phase, rank), steps in by_phase_rank.items():
        for step in sorted(set(steps)):
            src_key = prev_payload_key(phase, upstream_rank(rank, rank_size, direction), step, reps)
            add(
                "upstream_prev_step",
                reps.get(src_key) if src_key else None,
                reps.get((phase, rank, step)),
                f"single-ring {direction} upstream previous payload",
            )

    for rank in sorted({row["_rank"] for row in rows if row["_rank"] >= 0}):
        rs_steps = sorted(step for phase, r, step in reps if phase == "reduce_scatter" and r == rank and step >= 0)
        if rs_steps:
            add(
                "phase_bridge",
                reps.get(("reduce_scatter", rank, rs_steps[-1])),
                reps.get(("allgather", rank, 0)),
                "allgather step 0 starts after reduce_scatter final step",
            )

    by_phase_rank_step: Dict[Tuple[str, int, int], List[dict]] = defaultdict(list)
    for row in rows:
        by_phase_rank_step[(row["_phase_group"], row["_rank"], row["_step"])].append(row)
    for key, candidates in by_phase_rank_step.items():
        phase, rank, step = key
        candidates.sort(key=row_sort_key)
        first_by_event = {}
        for row in candidates:
            first_by_event.setdefault(row.get("event", ""), row)
        payload = reps.get(key)
        ack = first_by_event.get("rx_ack_start")
        signal = first_by_event.get("rx_data_signal_start")
        add("signal_payload", ack, signal, "ack wait completes before data-signal wait")
        add("signal_payload", signal, payload, "data-signal wait releases payload task")

        right = right_neighbor_rank(rank, rank_size, direction)
        right_key = prev_payload_key(phase, right, step, reps)
        add(
            "right_neighbor_ack_dep",
            reps.get(right_key) if right_key else None,
            ack,
            "RxAck wait depends on right-neighbor previous payload completion",
        )

        upstream = upstream_rank(rank, rank_size, direction)
        upstream_key = prev_payload_key(phase, upstream, step, reps)
        add(
            "upstream_data_signal_dep",
            reps.get(upstream_key) if upstream_key else None,
            signal,
            "data-signal wait depends on upstream producer previous payload completion",
        )

    return edges


def export_nodes(path: Path, nodes: List[dict]) -> None:
    fields = list(nodes[0].keys()) if nodes else ["graph_id"]
    write_csv(str(path), fields, nodes)


def export_edges(path: Path, edges: List[dict]) -> None:
    fields = list(edges[0].keys()) if edges else ["edge_id"]
    write_csv(str(path), fields, edges)


def assign_positions(rows: List[dict], col_width: int, row_height: int):
    columns = sorted({(row["_phase_group"], row["_step"]) for row in rows}, key=lambda item: (PHASE_GROUP_ORDER.get(item[0], 99), item[1]))
    ranks = sorted({row["_rank"] for row in rows if row["_rank"] >= 0})
    col_index = {key: index for index, key in enumerate(columns)}

    per_cell_counts: Dict[Tuple[int, int], int] = defaultdict(int)
    for row in rows:
        per_cell_counts[(row["_rank"], col_index[(row["_phase_group"], row["_step"])])] += 1

    rank_heights = {}
    for rank in ranks:
        max_stack = max((count for (item_rank, _col), count in per_cell_counts.items() if item_rank == rank), default=1)
        stack_rows = int(math.ceil(max_stack / 3.0))
        rank_heights[rank] = max(row_height, 48 + stack_rows * 30)

    rank_y = {}
    y_cursor = 116
    for rank in ranks:
        rank_y[rank] = y_cursor
        y_cursor += rank_heights[rank] + 18

    per_cell_slots: Dict[Tuple[int, int], int] = defaultdict(int)
    positions = {}
    for row in sorted(rows, key=row_sort_key):
        col = col_index[(row["_phase_group"], row["_step"])]
        rank = row["_rank"]
        slot_key = (rank, col)
        slot = per_cell_slots[slot_key]
        per_cell_slots[slot_key] += 1
        x = 180 + col * col_width + 18 + (slot % 3) * 46
        y = rank_y[rank] + 16 + (slot // 3) * 30
        positions[row["_graph_id"]] = (x, y)
    return positions, columns, ranks, rank_y, rank_heights


def title_for(row: dict) -> str:
    return (
        f'rank={row["_rank"]} device={row["_device_id"]} stream={row["_stream_id"]} task={row["_task_id"]}\n'
        f'phase={row.get("phase", "")} event={row.get("event", "")} semantic={row.get("semantic", "")}\n'
        f'step={row["_step"]} slice={row["_slice"]}\n'
        f'{row["_start"]:.3f}..{row["_stop"]:.3f} us duration={row["_duration"]:.3f} us'
    )


def render_svg(rows: List[dict], edges: List[dict], output: Path, col_width: int, row_height: int) -> None:
    if not rows:
        raise ValueError("no dependency rows to render")

    positions, columns, ranks, rank_y, rank_heights = assign_positions(rows, col_width, row_height)
    left = 180
    right = 72
    top = 94
    bottom = 84
    node_w = 40
    node_h = 20
    width = left + max(1, len(columns)) * col_width + right
    height = (max((rank_y[rank] + rank_heights[rank] for rank in ranks), default=top) + bottom)

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        '<defs><marker id="arrow" markerWidth="8" markerHeight="8" refX="7" refY="3" orient="auto"><path d="M0,0 L0,6 L7,3 z" fill="#555"/></marker></defs>',
        '<rect x="0" y="0" width="100%" height="100%" fill="#fff"/>',
        f'<text x="{left}" y="30" font-family="Arial" font-size="22" font-weight="700">HCCL task dependency graph</text>',
        f'<text x="{left}" y="54" font-family="Arial" font-size="12" fill="#555">Nodes are matched tasks. Edges show inferred single-ring step, upstream, phase, and ack/signal/payload dependencies.</text>',
    ]

    previous_phase = None
    for index, (phase, step) in enumerate(columns):
        x = left + index * col_width
        parts.append(f'<rect x="{x}" y="{top - 18}" width="{col_width}" height="{height - bottom - top + 42}" fill="{"#fbfbfb" if index % 2 == 0 else "#ffffff"}"/>')
        parts.append(f'<line x1="{x}" y1="{top - 18}" x2="{x}" y2="{height - bottom + 24}" stroke="#e6e6e6"/>')
        if phase != previous_phase:
            parts.append(f'<text x="{x + 10}" y="{top - 30}" font-family="Arial" font-size="12" font-weight="700">{html.escape(phase)}</text>')
            previous_phase = phase
        parts.append(f'<text x="{x + col_width / 2:.1f}" y="{top - 12}" text-anchor="middle" font-family="Arial" font-size="10" fill="#555">step {step}</text>')
    parts.append(f'<line x1="{left + len(columns) * col_width}" y1="{top - 18}" x2="{left + len(columns) * col_width}" y2="{height - bottom + 24}" stroke="#e6e6e6"/>')

    for rank in ranks:
        y = rank_y[rank]
        lane_h = rank_heights[rank]
        parts.append(f'<text x="28" y="{y + 24}" font-family="Arial" font-size="12" fill="#333">rank {rank}</text>')
        parts.append(f'<line x1="{left - 12}" y1="{y + lane_h / 2:.1f}" x2="{width - right}" y2="{y + lane_h / 2:.1f}" stroke="#f0f0f0"/>')

    for edge in edges:
        src_pos = positions.get(edge["src"])
        dst_pos = positions.get(edge["dst"])
        if not src_pos or not dst_pos:
            continue
        sx, sy = src_pos
        dx, dy = dst_pos
        sx += node_w
        sy += node_h / 2
        dy += node_h / 2
        color = EDGE_COLOR.get(edge["kind"], "#555")
        mid = max(18.0, abs(dx - sx) * 0.45)
        parts.append(
            f'<path d="M {sx:.1f} {sy:.1f} C {sx + mid:.1f} {sy:.1f}, {dx - mid:.1f} {dy:.1f}, {dx:.1f} {dy:.1f}" '
            f'fill="none" stroke="{color}" stroke-width="1.2" stroke-opacity="0.72" marker-end="url(#arrow)">'
            f'<title>{html.escape(edge["kind"] + ": " + edge["reason"])}</title></path>'
        )

    for row in rows:
        x, y = positions[row["_graph_id"]]
        fill, stroke = EVENT_COLOR.get(row.get("event", ""), ("#eeeeee", "#777777"))
        label = short_label(row.get("event", ""))
        parts.append(f'<rect x="{x:.1f}" y="{y:.1f}" width="{node_w}" height="{node_h}" rx="3" ry="3" fill="{fill}" stroke="{stroke}" stroke-width="1"><title>{html.escape(title_for(row))}</title></rect>')
        parts.append(f'<text x="{x + node_w / 2:.1f}" y="{y + 13.5:.1f}" text-anchor="middle" font-family="Arial" font-size="7.5">{html.escape(label[:8])}</text>')

    legend_y = height - 52
    legend_x = left
    for kind, color in EDGE_COLOR.items():
        if legend_x > width - 220:
            legend_x = left
            legend_y += 16
        parts.append(f'<line x1="{legend_x}" y1="{legend_y}" x2="{legend_x + 26}" y2="{legend_y}" stroke="{color}" stroke-width="1.5" marker-end="url(#arrow)"/>')
        parts.append(f'<text x="{legend_x + 34}" y="{legend_y + 4}" font-family="Arial" font-size="10">{html.escape(kind)}</text>')
        legend_x += 190

    parts.append('</svg>')
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("\n".join(parts), encoding="utf-8")


def parse_csv_list(value: str) -> Tuple[str, ...]:
    return tuple(item.strip() for item in value.split(",") if item.strip())


def main() -> int:
    parser = argparse.ArgumentParser(description="Render inferred HCCL task dependencies as an SVG graph.")
    parser.add_argument("merged_csv", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--include-unmatched", action="store_true")
    parser.add_argument("--events", default=",".join(DEFAULT_EVENTS), help="Comma-separated event filter; empty means all events.")
    parser.add_argument("--edge-kinds", default=",".join(DEFAULT_EDGE_KINDS), help="Comma-separated edge kinds.")
    parser.add_argument("--rank-size", type=int, default=-1)
    parser.add_argument("--upstream", choices=("previous", "next"), default="previous")
    parser.add_argument("--col-width", type=int, default=130)
    parser.add_argument("--row-height", type=int, default=94)
    args = parser.parse_args()

    output = args.output or args.merged_csv.with_name(args.merged_csv.stem + "_dependency.svg")
    events = parse_csv_list(args.events)
    edge_kinds = parse_csv_list(args.edge_kinds)
    rows = read_rows(args.merged_csv, events, include_unmatched=args.include_unmatched)
    build_nodes(rows)
    rank_size = infer_rank_size(rows, args.rank_size)
    edges = build_edges(rows, edge_kinds, rank_size, args.upstream)
    render_svg(rows, edges, output, args.col_width, args.row_height)

    nodes_path = output.with_name(output.stem + "_nodes.csv")
    edges_path = output.with_name(output.stem + "_edges.csv")
    export_nodes(nodes_path, build_nodes(rows))
    export_edges(edges_path, edges)
    print(f"nodes={len(rows)}")
    print(f"edges={len(edges)}")
    print(f"rank_size={rank_size}")
    print(f"svg={output}")
    print(f"nodes_csv={nodes_path}")
    print(f"edges_csv={edges_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
