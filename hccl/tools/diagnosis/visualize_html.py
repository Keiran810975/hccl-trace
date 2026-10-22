#!/usr/bin/env python3
"""Render HCCL diagnosis views as interactive HTML canvas pages."""

from __future__ import annotations

import argparse
import csv
import html
import json
import math
import os
import sys
from collections import defaultdict
from decimal import Decimal
from pathlib import Path
from typing import Dict, List, Tuple

if __package__ in (None, ""):
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from diagnosis import visualize_dependency_graph as dep
    from diagnosis import resource_dependency_graph as resource_dep
    from diagnosis import visualize_timeline as timeline
    from diagnosis.dependency_model import stable_id
else:
    from . import visualize_dependency_graph as dep
    from . import resource_dependency_graph as resource_dep
    from . import visualize_timeline as timeline
    from .dependency_model import stable_id


def build_timeline_model(rows: List[dict], layout: str) -> dict:
    if not rows:
        raise ValueError("no timeline rows to render")
    left = 170
    top = 92
    lane_h = 30
    lane_gap = 8
    node_h = 16
    min_w = 4
    lanes = sorted({timeline.lane_key(row) for row in rows})
    lane_index = {key: index for index, key in enumerate(lanes)}
    lane_items = [
        {
            "key": "|".join(str(v) for v in key),
            "label": f"rank {key[2]} dev {key[1]} stream {key[3]}",
            "y": top + index * (lane_h + lane_gap),
            "height": lane_h,
        }
        for index, key in enumerate(lanes)
    ]
    nodes = []
    columns = []
    if layout == "logical":
        column_keys = sorted({timeline.logical_column_key(row) for row in rows})
        col_w = 92
        col_index = {key: index for index, key in enumerate(column_keys)}
        per_cell: Dict[Tuple[int, int], int] = defaultdict(int)
        for row in rows:
            lane = lane_index[timeline.lane_key(row)]
            col = col_index[timeline.logical_column_key(row)]
            slot = per_cell[(lane, col)]
            per_cell[(lane, col)] += 1
            x = left + col * col_w + 8 + (slot % 3) * 26
            y = lane_items[lane]["y"] + 6 + (slot // 3) * 18
            fill, stroke = timeline.row_color(row)
            nodes.append(node_record(row, x, y, 22, node_h, fill, stroke, timeline.short_label(row)))
        for key, index in col_index.items():
            _phase_order, phase, step, _event_order, event = key
            columns.append({"x": left + index * col_w, "w": col_w, "label": f"{timeline.phase_label(phase)} s{step} {timeline.short_label({'_event': event})}"})
        width = left + len(column_keys) * col_w + 80
    else:
        timeline.assign_time_slots(rows)
        min_start = min(row["_start"] for row in rows)
        max_stop = max(row["_stop"] for row in rows)
        span = max(1.0, max_stop - min_start)
        scale = max(0.06, min(3.0, 24000.0 / span))
        slot_counts: Dict[Tuple[str, int, int, int], int] = defaultdict(int)
        for row in rows:
            slot_counts[timeline.lane_key(row)] = max(slot_counts[timeline.lane_key(row)], row.get("_time_slot", 0) + 1)
        for index, key in enumerate(lanes):
            lane_items[index]["height"] = max(lane_h, 10 + slot_counts[key] * 20)
        y_cursor = top
        for index, key in enumerate(lanes):
            lane_items[index]["y"] = y_cursor
            y_cursor += lane_items[index]["height"] + lane_gap
        for row in rows:
            lane = lane_index[timeline.lane_key(row)]
            x = left + (row["_start"] - min_start) * scale
            w = max(min_w, (row["_stop"] - row["_start"]) * scale)
            y = lane_items[lane]["y"] + 6 + row.get("_time_slot", 0) * 20
            fill, stroke = timeline.row_color(row)
            nodes.append(node_record(row, x, y, w, node_h, fill, stroke, timeline.short_label(row)))
        width = left + span * scale + 100
    height = max(item["y"] + item["height"] for item in lane_items) + 80
    return {
        "kind": "timeline", "layout": layout, "timeOrigin": min(row["_start"] for row in rows),
        "width": width, "height": height, "lanes": lane_items, "columns": columns,
        "nodes": nodes, "edges": [], "edgeKinds": [],
    }


def node_record(row: dict, x: float, y: float, w: float, h: float, fill: str, stroke: str, label: str) -> dict:
    task_kind = row.get("profiler_task_kind", "")
    # HOST inline reduction can be reported as MEMCPY_ASYNC by the profiler.
    # An exact semantic match supplies the operation type, not the hardware name.
    if (task_kind == "sdma" and row.get("task_kind") == "reduce_inline"
            and row.get("match_confidence") == "exact"):
        task_kind = "reduce_inline"
    timing = {
        "rdma": "RDMA doorbell submission; transfer/reduction completion is not measured by this task",
        "sdma": "SDMA execution",
        "reduce_inline": "Inline reduction execution; control/payload role requires algorithm evidence",
        "notify_wait": "Local wait duration; not a measurement of remote execution time",
        "operation": "Device communication operation interval from COMMUNICATION_OP",
    }.get(task_kind, "Device task execution")
    size = str(row.get("profiler_size_bytes", ""))
    size = size if size and size != "-1" else ""
    display = {"rdma": "RDMA submit", "sdma": "Copy", "reduce_inline": "Inline reduce",
               "notify_wait": "Wait", "operation": "Communication op"}.get(task_kind, label)
    annotation = "Algorithm annotated" if row.get("algorithm") else "No algorithm annotation"
    title = (
        f"node={row.get('_node_id', '')} rank={row.get('_user_rank', row.get('_rank', ''))} "
        f"device={row.get('_device_id', '')} stream={row.get('_stream_id', '')} "
        f"semantic_task={row.get('task_id', row.get('_task_id', ''))} "
        f"profiler_task={row.get('_profiler_task_id', row.get('_task_id', ''))} subtask={row.get('_subtask_id', '')}\n"
        f"phase={row.get('phase', row.get('_phase', ''))} event={row.get('event', row.get('_event', ''))} semantic={row.get('semantic', row.get('_semantic', ''))}\n"
        f"step={row.get('step', row.get('_step', ''))} slice={row.get('slice', row.get('_slice', ''))} "
        f"hardware={row.get('event_name', '')} match={row.get('match_method', '')} confidence={row.get('match_confidence', '')}\n"
        f"operation_scope={row.get('_operation_scope', '')} "
        f"operation_scope_status={row.get('_operation_scope_status', '')}\n"
        f"{row.get('_start', 0):.3f}..{row.get('_stop', 0):.3f} us duration={row.get('_duration', 0):.3f} us\n"
        f"{timing}; bytes={size or 'unknown'}; {annotation}"
    )
    return {
        "id": row.get("_graph_id", f"n{row.get('_source_row', '')}"),
        "x": round(x, 2), "y": round(y, 2), "w": round(w, 2), "h": round(h, 2),
        "fill": fill, "stroke": stroke, "label": display, "title": title,
        "timingMeaning": timing, "sizeBytes": size, "annotation": annotation,
        "algorithm": row.get("algorithm", ""), "step": row.get("step", ""),
        "nodeKind": row.get("_node_kind", "execution"),
        "rank": row.get("_user_rank", row.get("_rank", -1)),
        "nodeId": row.get("_node_id", ""),
        "device": row.get("_device_id", -1),
        "stream": row.get("_stream_id", -1), "event": row.get("event", row.get("event_name", "")),
        "taskKind": task_kind, "profilerTaskKind": row.get("profiler_task_kind", ""),
        "match": row.get("match_confidence", ""),
        "start": row.get("_start", 0), "stop": row.get("_stop", 0),
        "duration": row.get("_duration", 0),
        "phase": row.get("phase", row.get("_phase", "")),
        "semantic": row.get("semantic", row.get("_semantic", "")),
        "hardware": row.get("event_name", ""),
        "taskId": row.get("_task_id", row.get("task_id", -1)),
        "semanticTaskId": row.get("task_id", -1),
        "subtaskId": row.get("_subtask_id", -1),
        "operationScope": row.get("_operation_scope", ""),
        "operationScopeStatus": row.get("_operation_scope_status", ""),
        "confidence": row.get("match_confidence", ""),
        "zeroDuration": row.get("_duration", 0) <= 0,
    }


def build_execution_dependency_model(rows: List[dict], edges: List[dict],
                                     operations: List[dict] = ()) -> dict:
    rows = list(rows) + list(operations)
    if not rows:
        raise ValueError("no timed profiler executions to render")
    left = 190
    top = 92
    node_h = 16
    lane_gap = 8
    lanes = sorted({(row["_node_id"], row["_device_id"], row["_stream_id"]) for row in rows})
    lane_index = {key: index for index, key in enumerate(lanes)}
    lane_items = []
    node_origins = {}
    precise_origins = {}
    for row in rows:
        node = row["_node_id"]
        node_origins[node] = min(node_origins.get(node, row["_start"]), row["_start"])
        precise_start = dep.execution_time_order_value(row, "start")
        precise_origins[node] = min(precise_origins.get(node, precise_start), precise_start)
    multi_node = len(node_origins) > 1
    if multi_node:
        left = 300
    for index, key in enumerate(lanes):
        lane_items.append({
            "key": "|".join(str(value) for value in key),
            "label": (f"{key[0].rsplit('/', 1)[-1]} " if multi_node else "") +
                     f"dev {key[1]} " + ("operations" if key[2] == -2 else f"stream {key[2]}"),
            "y": top + index * 38,
            "height": 30,
            "taskCount": 0,
        })
    min_start = 0 if multi_node else min(row["_start"] for row in rows)
    max_stop = max(row["_stop"] - (node_origins[row["_node_id"]] if multi_node else 0) for row in rows)
    span = max(1.0, max_stop - min_start)
    scale = max(0.06, min(2.0, 28000.0 / span))
    nodes = []
    positions = {}
    per_lane_slots: Dict[Tuple[str, int, int], List[float]] = defaultdict(list)
    for row in sorted(rows, key=lambda item: (item["_start"], item["_stop"], item["_source_row"])):
        key = (row["_node_id"], row["_device_id"], row["_stream_id"])
        slots = per_lane_slots[key]
        slot = next((index for index, stop in enumerate(slots) if row["_start"] >= stop), len(slots))
        if slot == len(slots):
            slots.append(row["_stop"])
        else:
            slots[slot] = row["_stop"]
        lane = lane_index[key]
        lane_items[lane]["taskCount"] += 1
        lane_items[lane]["height"] = max(lane_items[lane]["height"], 10 + (slot + 1) * 20)
        origin = node_origins[row["_node_id"]] if multi_node else min_start
        precise_origin = precise_origins[row["_node_id"]]
        relative_start = float(dep.execution_time_order_value(row, "start") - precise_origin)
        relative_stop = float(dep.execution_time_order_value(row, "stop") - precise_origin)
        x = left + relative_start * scale
        y = lane_items[lane]["y"] + 6 + slot * 20
        width = max(4, row["_duration"] * scale)
        fill, stroke = timeline.row_color({
            "_event": row.get("event", ""),
            "profiler_task_kind": row.get("profiler_task_kind", ""),
        })
        if row.get("_node_kind") == "operation":
            fill, stroke = "#dce9fa", "#4476a5"
        label = row.get("event", "") or row.get("event_name", "") or row.get("profiler_task_kind", "")
        record = node_record(row, x, y, width, node_h, fill, stroke, label)
        record["localTimeOrigin"] = origin
        record["relativeStart"] = relative_start
        record["relativeStop"] = relative_stop
        nodes.append(record)
        positions[row["_graph_id"]] = record
    y_cursor = top
    for lane in lane_items:
        lane["y"] = y_cursor
        y_cursor += lane["height"] + lane_gap
    # Node y positions need the compacted lane offsets.
    for row, node in zip(sorted(rows, key=lambda item: (item["_start"], item["_stop"], item["_source_row"])), nodes):
        key = (row["_node_id"], row["_device_id"], row["_stream_id"])
        old_base = top + lane_index[key] * 38
        node["y"] += lane_items[lane_index[key]]["y"] - old_base
    edge_items = []
    for edge in edges:
        if edge["src"] not in positions or edge["dst"] not in positions:
            continue
        metrics = []
        for name in (
            "weight_ns",
            "wait_span_ns",
            "remote_block_ns",
            "post_signal_ns",
            "handoff_gap_ns",
        ):
            if str(edge.get(name, "")).strip():
                metrics.append("{}={}".format(name, edge[name]))
        metric_text = " · " + " ".join(metrics) if metrics else ""
        edge_items.append({
            "id": edge["edge_id"], "src": edge["src"], "dst": edge["dst"], "kind": edge["kind"],
            "color": (
                dep.EDGE_COLOR.get(edge["kind"])
                or resource_dep.RESOURCE_EDGE_COLOR.get(edge["kind"], "#555")
            ),
            "confidence": edge.get("confidence", ""),
            "reason": edge.get("reason", ""),
            "evidence": edge.get("evidence", ""),
            "relationId": edge.get("relation_id", ""),
            "weightNs": edge.get("weight_ns", ""),
            "waitSpanNs": edge.get("wait_span_ns", ""),
            "remoteBlockNs": edge.get("remote_block_ns", ""),
            "postSignalNs": edge.get("post_signal_ns", ""),
            "handoffGapNs": edge.get("handoff_gap_ns", ""),
            "timingStatus": edge.get("timing_status", ""),
            "title": (
                f"{edge['kind']} [{edge.get('confidence', '')}]: "
                f"{edge['reason']}{metric_text}"
            ),
        })
    return {
        "kind": "dependency", "layout": "time", "timeOrigin": min_start,
        "clockLabel": "Node-local elapsed time; clocks uncalibrated" if multi_node else "dependency",
        "width": left + span * scale + 100, "height": y_cursor + 70,
        "contentLeft": left, "timeScale": scale, "timeMin": min_start, "timeMax": max_stop,
        "lanes": lane_items, "columns": [], "nodes": nodes, "edges": edge_items,
        "edgeKinds": sorted({edge["kind"] for edge in edge_items}),
    }


def read_operation_timings(path: Path) -> List[dict]:
    """Convert the exported operation artifact to separate display-only lanes."""
    operations, identities = [], set()
    with path.open(encoding="utf-8-sig", newline="") as source:
        for row in csv.DictReader(source):
            identity = (row["node_id"], int(row["device_id"]), row["operation_scope"])
            start, stop = int(row["start_ns"]), int(row["end_ns"])
            if identity in identities or stop < start or int(row["duration_ns"]) != stop - start:
                raise ValueError("invalid/duplicate operation timing: {!r}".format(identity))
            identities.add(identity)
            operations.append({
                "_graph_id": stable_id("display_op", identity), "_source_row": -len(operations) - 1,
                "_node_id": row["node_id"], "_device_id": int(row["device_id"]),
                "_user_rank": int(row["user_rank"]), "_stream_id": -2, "_task_id": -1,
                "_subtask_id": -1, "_node_kind": "operation", "profiler_task_kind": "operation",
                "_start": float(Decimal(start) / 1000), "_stop": float(Decimal(stop) / 1000),
                "_duration": float(Decimal(stop - start) / 1000),
                "_start_order": Decimal(start) / 1000, "_stop_order": Decimal(stop) / 1000,
                "_operation_scope": row["operation_scope"], "_operation_scope_status": "DB interval",
                "event": row["op_name"], "event_name": "COMMUNICATION_OP", "phase": "operation",
            })
    return operations


def build_wait_inventory(rows: List[dict], edges: List[dict], issues: List[dict] = ()) -> List[dict]:
    """Rank local waits from execution artifacts, including unresolved endpoints."""
    nodes = {row["_graph_id"]: row for row in rows}
    incoming, issues_by_node = defaultdict(list), defaultdict(list)
    for edge in edges:
        incoming[edge["dst"]].append(edge)
    for issue in issues:
        for node in issue.get("endpoint_graph_ids", "").split(";"):
            issues_by_node[node].append(issue.get("reason", "") or issue.get("status", ""))
    waits = []
    for row in rows:
        if row.get("profiler_task_kind") != "notify_wait":
            continue
        identifier = row["_graph_id"]
        sync = [e for e in incoming[identifier] if "notify_sync" in e["kind"]]
        duration = max(Decimal(0), dep.execution_time_order_value(row, "stop")
                       - dep.execution_time_order_value(row, "start")) * 1000
        waits.append({
            "wait_graph_id": identifier, "node_id": row["_node_id"], "device_id": row["_device_id"],
            "user_rank": row["_user_rank"], "stream_id": row["_stream_id"], "task_id": row["_task_id"],
            "operation_scope": row.get("_operation_scope", ""), "phase": row.get("phase", ""),
            "step": row.get("step", ""), "semantic": row.get("semantic", ""),
            "wait_span_ns": format(duration, "f"), "status": "paired" if sync else "unresolved",
            "record_graph_ids": ";".join(e["src"] for e in sync),
            "peer_ranks": ";".join(str(nodes[e["src"]]["_user_rank"]) for e in sync),
            "upstream_graph_ids": ";".join(e["src"] for e in incoming[identifier]),
            "reason": "; ".join(sorted(set(issues_by_node[identifier]))) or
                      ("Verified channel paired; local duration only" if sync else "No paired producer in supplied artifact"),
        })
    return sorted(waits, key=lambda row: (-Decimal(row["wait_span_ns"]), row["wait_graph_id"]))


def write_html(output: Path, title: str, model: dict) -> None:
    payload = json.dumps(model, ensure_ascii=False, separators=(",", ":")).replace("<", "\\u003c")
    template = PERFETTO_DEPENDENCY_TEMPLATE if model.get("kind") == "dependency" else HTML_TEMPLATE
    page = template.replace("__TITLE__", html.escape(title)).replace("__MODEL__", payload)
    page = page.replace('__CLOCK_LABEL__', html.escape(model.get("clockLabel", "dependency")))
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(page, encoding="utf-8")


def attach_diagnosis(model: dict, diagnosis: dict, waits: List[dict], view: str) -> None:
    """Reject mismatched analysis instead of displaying another run's findings."""
    if diagnosis.get("schema_version") != 1:
        raise ValueError("unsupported diagnosis schema")
    records = diagnosis.get("waits", [])
    diagnosed = {w["wait_graph_id"]: w for w in records}
    if len(diagnosed) != len(records):
        raise ValueError("duplicate diagnosis wait identity")
    if view != "resource" and set(diagnosed) != {w["wait_graph_id"] for w in waits}:
        raise ValueError("diagnosis and execution wait identities differ")
    scopes = {n["operationScope"] for n in model["nodes"]}
    if any(w["operation_scope"] and w["operation_scope"] not in scopes for w in records):
        raise ValueError("diagnosis operation does not belong to graph")
    node_ids = {n["id"] for n in model["nodes"]}
    if view != "resource" and any(c["graph_id"] not in node_ids for c in diagnosis.get("candidates", [])):
        raise ValueError("diagnosis candidate execution missing")
    model["diagnosis"] = diagnosis
    if view == "waits":
        model["waits"] = [diagnosed[w["wait_graph_id"]] for w in waits]


def write_dependency_svg(output: Path, title: str, model: dict) -> None:
    """Write a static SVG from the same artifact-backed dependency model."""
    node_by_id = {node["id"]: node for node in model["nodes"]}
    parts = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<svg xmlns="http://www.w3.org/2000/svg" width="{}" height="{}" '
        'viewBox="0 0 {} {}">'.format(
            int(model["width"]),
            int(model["height"]),
            int(model["width"]),
            int(model["height"]),
        ),
        "<title>{}</title>".format(html.escape(title)),
        '<rect width="100%" height="100%" fill="#fff"/>',
        '<text x="12" y="24" font-family="Arial" font-size="12">{}</text>'.format(
            html.escape(model.get("clockLabel", "dependency"))),
    ]
    for lane in model.get("lanes", []):
        parts.append(
            '<rect x="0" y="{y}" width="{w}" height="{h}" fill="#fafbfc" '
            'stroke="#e4e7eb"/><text x="12" y="{ty}" font-family="Arial" '
            'font-size="11" fill="#30343b">{label}</text>'.format(
                y=lane["y"],
                w=model["width"],
                h=lane["height"],
                ty=lane["y"] + 17,
                label=html.escape(str(lane["label"])),
            )
        )
    for edge in model.get("edges", []):
        src = node_by_id.get(edge["src"])
        dst = node_by_id.get(edge["dst"])
        if src is None or dst is None:
            continue
        parts.append(
            '<path d="M {x1} {y1} L {x2} {y2}" fill="none" '
            'stroke="{color}" stroke-width="1" opacity=".65">'
            "<title>{title}</title></path>".format(
                x1=src["x"] + src["w"],
                y1=src["y"] + src["h"] / 2,
                x2=dst["x"],
                y2=dst["y"] + dst["h"] / 2,
                color=html.escape(edge["color"]),
                title=html.escape(edge["title"]),
            )
        )
    for node in model["nodes"]:
        parts.append(
            '<rect id="{id}" x="{x}" y="{y}" width="{w}" height="{h}" '
            'rx="2" fill="{fill}" stroke="{stroke}"><title>{title}</title>'
            "</rect>".format(
                id=html.escape(node["id"]),
                x=node["x"],
                y=node["y"],
                w=max(1, node["w"]),
                h=node["h"],
                fill=html.escape(node["fill"]),
                stroke=html.escape(node["stroke"]),
                title=html.escape(node["title"]),
            )
        )
    parts.append("</svg>")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("\n".join(parts), encoding="utf-8")


PERFETTO_DEPENDENCY_TEMPLATE = r'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>__TITLE__</title>
<style>
:root{--toolbar:116px;--side:390px;--label:190px;--border:#d8dce3;--ink:#202124;--muted:#68707d;--blue:#1967d2}
*{box-sizing:border-box}html,body{margin:0;height:100%;overflow:hidden;font:12px Arial,sans-serif;color:var(--ink);background:#fff}
#toolbar{height:var(--toolbar);display:flex;flex-wrap:wrap;align-content:center;align-items:center;gap:7px;padding:7px 10px;border-bottom:1px solid var(--border);background:#f8f9fa;overflow:auto}
#timingNote{flex-basis:100%;font-size:12px;color:#77521a}#waitPanel{max-height:42%;overflow:auto;border-bottom:1px solid #ddd;padding:8px 12px;flex-shrink:0}#waitList button{font-size:11px}#waitPanel summary{font-weight:bold;cursor:pointer}
#toolbar strong{font-size:14px;margin-right:4px}button,select,input{height:30px;border:1px solid #c8ccd3;border-radius:4px;background:#fff;padding:0 7px;color:#30343b}button{cursor:pointer}button:hover{background:#edf3fc;border-color:#9bb9e8}select{max-width:126px}input{width:112px}#search{width:180px}.sep{width:1px;height:24px;background:#d5d8de;margin:0 2px}.muted{color:var(--muted)}
#stage{position:fixed;left:0;right:var(--side);top:var(--toolbar);bottom:0;overflow:hidden;background:#fff}#trace{width:100%;height:100%;display:block;outline:none;cursor:default}
#side{position:fixed;right:0;top:var(--toolbar);bottom:0;width:var(--side);border-left:1px solid var(--border);background:#fff;display:flex;flex-direction:column;overflow:hidden}
#side h2{font-size:14px;margin:0;padding:13px 14px 9px;border-bottom:1px solid var(--border)}#details{padding:12px 14px;overflow:auto;flex:1}.empty{color:var(--muted);line-height:1.55;padding-top:4px}
.kv{display:grid;grid-template-columns:104px 1fr;gap:6px 8px;margin-bottom:14px}.kv .k{color:var(--muted)}.kv .v{font-family:Consolas,monospace;overflow-wrap:anywhere}
.section{font-weight:bold;margin:14px 0 7px}.dep{display:block;width:100%;height:auto;text-align:left;padding:7px 8px;margin:5px 0;border-left:4px solid var(--edge,#777);line-height:1.35}.dep small{display:block;color:var(--muted);margin-top:2px}.incoming:before{content:'← ';font-weight:bold}.outgoing:before{content:'→ ';font-weight:bold}
#legend{padding:9px 12px;border-top:1px solid var(--border);background:#fafbfc;line-height:1.8}.swatch{display:inline-block;width:9px;height:9px;margin:0 5px 0 9px;border-radius:2px}.swatch:first-child{margin-left:0}
#overview{height:96px;width:100%;display:block;border-top:1px solid var(--border);cursor:crosshair}.tip{position:fixed;display:none;max-width:520px;white-space:pre-wrap;background:#202124;color:#fff;padding:7px 9px;border-radius:4px;pointer-events:none;font:11px Consolas,monospace;z-index:5;box-shadow:0 2px 8px #0005}
@media(max-width:900px){:root{--toolbar:200px}#stage{right:0;bottom:45vh}#side{top:auto;left:0;width:100%;height:45vh;border-top:1px solid var(--border)}#overview,#legend{display:none}#waitPanel{max-height:45%}#side h2{padding:6px 14px}#toolbar{align-content:flex-start}}
</style></head><body>
<div id="toolbar"><strong>HCCL Trace</strong><span class="muted">__CLOCK_LABEL__</span><button id="fit">Fit trace</button><button id="focus">Focus selected</button><button id="clearSelection">Clear selection</button><span class="sep"></span><select id="deviceFilter" title="device"></select><select id="rankFilter" title="rank"></select><select id="streamFilter" title="stream"></select><select id="eventFilter" title="event"></select><select id="edgeFilter" title="dependency kind"></select><select id="typeFilter" title="task type"></select><select id="operationFilter" title="operation"></select><select id="phaseFilter" title="phase"></select><label><input type="checkbox" id="boundaries">Control boundaries</label><input id="search" placeholder="Find task / event"><button id="clearFilters">Reset filters</button><span id="timingNote"></span></div>
<div id="stage"><canvas id="trace" tabindex="0"></canvas></div>
<aside id="side"><details id="diagnosisPanel" open style="padding:8px 12px;max-height:25%;overflow:auto"><summary>Diagnosis candidates</summary><div id="candidateList"></div></details><details id="waitPanel" open><summary>Local waits</summary><select id="waitOrder" aria-label="Wait sort"><option value="desc">Longest first</option><option value="asc">Shortest first</option></select><span id="waitCount"></span><div id="waitList"></div><button id="moreWaits">Show more</button></details><h2 id="sideTitle">Task details</h2><div id="details"><div class="empty">Select a task block to inspect its direct predecessors and successors. Dependencies stay hidden until a task is selected.</div></div><canvas id="overview" title="Click to navigate"></canvas><div id="legend"></div></aside><div id="tip" class="tip"></div>
<script>
const model=__MODEL__,canvas=document.getElementById('trace'),ctx=canvas.getContext('2d'),overview=document.getElementById('overview'),octx=overview.getContext('2d'),tip=document.getElementById('tip'),details=document.getElementById('details'),sideTitle=document.getElementById('sideTitle');
const LABEL=Math.min(model.contentLeft||190,window.innerWidth<=900?155:1000),RULER=34,nodeById=new Map(model.nodes.map(n=>[n.id,n])),incident=new Map();for(const e of model.edges){if(!incident.has(e.src))incident.set(e.src,[]);if(!incident.has(e.dst))incident.set(e.dst,[]);incident.get(e.src).push(e);incident.get(e.dst).push(e)}
let xScale=1,viewX=LABEL,yPan=0,selectedId=null,coincidentIds=[],drag=null,dirty=false,hoverPending=null;
const controls={device:document.getElementById('deviceFilter'),rank:document.getElementById('rankFilter'),stream:document.getElementById('streamFilter'),event:document.getElementById('eventFilter'),edge:document.getElementById('edgeFilter'),type:document.getElementById('typeFilter'),operation:document.getElementById('operationFilter'),phase:document.getElementById('phaseFilter'),search:document.getElementById('search')};
function fillSelect(el,label,values){el.replaceChildren();for(const value of ['',...[...new Set(values)].sort((a,b)=>String(a).localeCompare(String(b),undefined,{numeric:true}))]){const option=document.createElement('option');option.value=value;option.textContent=value===''?`${label}: all`:value;el.append(option)}}
fillSelect(controls.device,'device',model.nodes.map(n=>n.device));fillSelect(controls.rank,'rank',model.nodes.map(n=>n.rank));fillSelect(controls.stream,'stream',model.nodes.map(n=>n.stream));fillSelect(controls.event,'event',model.nodes.map(n=>n.event||n.taskKind).filter(Boolean));fillSelect(controls.edge,'edge',model.edgeKinds||[]);
fillSelect(controls.phase,'phase',model.nodes.map(n=>n.phase).filter(Boolean));
fillSelect(controls.type,'type',model.nodes.map(n=>n.taskKind).filter(Boolean));fillSelect(controls.operation,'operation',model.nodes.map(n=>n.operationScope).filter(Boolean));
for(const option of controls.operation.options){const op=model.nodes.find(n=>n.nodeKind==='operation'&&n.operationScope===option.value);if(op)option.textContent=op.event}for(const option of controls.stream.options){if(option.value==='-2')option.textContent='operations'}
document.getElementById('boundaries').checked=model.graphView!=='resource';
controls.operation.value=model.initialOperation||'';
function nodeVisible(n){if(!n)return false;if(n.nodeKind==='boundary'&&!document.getElementById('boundaries').checked)return false;if(controls.phase.value&&n.phase!==controls.phase.value)return false;if(controls.type.value&&n.taskKind!==controls.type.value)return false;if(controls.operation.value&&n.operationScope!==controls.operation.value)return false;if(controls.device.value&&String(n.device)!==controls.device.value)return false;if(controls.rank.value&&String(n.rank)!==controls.rank.value)return false;if(controls.stream.value&&String(n.stream)!==controls.stream.value)return false;if(controls.event.value&&(n.event||n.taskKind)!==controls.event.value)return false;const q=controls.search.value.trim().toLowerCase();return !q||n.title.toLowerCase().includes(q)}
function edgeVisible(e){return(!controls.edge.value||e.kind===controls.edge.value)&&nodeVisible(nodeById.get(e.src))&&nodeVisible(nodeById.get(e.dst))}
for(const c of Object.values(controls)){c.addEventListener('input',()=>{requestDraw();renderDetails();renderWaits();renderCandidates()});c.addEventListener('change',()=>{requestDraw();renderDetails();renderWaits();renderCandidates()})}document.getElementById('clearFilters').onclick=()=>{for(const c of Object.values(controls))c.value='';requestDraw();renderDetails();renderWaits();renderCandidates()};
function sx(x){return LABEL+(x-viewX)*xScale}function wx(x){return viewX+(x-LABEL)/xScale}function sy(y){return y+yPan}function visibleX(){return[viewX,viewX+Math.max(1,canvas.clientWidth-LABEL)/xScale]}
function resize(){const d=window.devicePixelRatio||1;canvas.width=canvas.clientWidth*d;canvas.height=canvas.clientHeight*d;ctx.setTransform(d,0,0,d,0,0);overview.width=overview.clientWidth*d;overview.height=overview.clientHeight*d;octx.setTransform(d,0,0,d,0,0);requestDraw()}window.addEventListener('resize',resize);
function bounds(){const xs=model.nodes.filter(nodeVisible);if(!xs.length)return[model.contentLeft,model.width-40];return[Math.min(...xs.map(n=>n.x)),Math.max(...xs.map(n=>n.x+n.w))]}
function fit(){const [a,b]=bounds();viewX=a;xScale=Math.max(.0005,(canvas.clientWidth-LABEL-16)/Math.max(1,b-a));yPan=RULER+8-(model.lanes[0]?.y||0);requestDraw()}document.getElementById('fit').onclick=fit;
function focusNode(n){if(!n)return;xScale=Math.max(xScale,Math.min(12,120/Math.max(4,n.w)));viewX=n.x-(canvas.clientWidth-LABEL)/(2*xScale)+n.w/2;yPan=RULER+80-n.y;requestDraw()}document.getElementById('focus').onclick=()=>focusNode(nodeById.get(selectedId));
document.getElementById('clearSelection').onclick=()=>setSelected(null);
function setSelected(id,focus=false,peers=[]){selectedId=id&&nodeById.has(id)?id:null;coincidentIds=selectedId?peers:[];renderDetails();requestDraw();if(focus&&selectedId)focusNode(nodeById.get(selectedId))}
function text(tag,value,cls){const e=document.createElement(tag);if(cls)e.className=cls;e.textContent=value??'';return e}
function addKV(box,key,value){box.append(text('div',key,'k'),text('div',String(value??''),'v'))}
function selectContext(id){for(const c of Object.values(controls))c.value='';document.getElementById('boundaries').checked=true;setSelected(id,true);renderWaits();renderCandidates()}
function renderDetails(){
 details.replaceChildren();const n=nodeById.get(selectedId);
 if(!n){sideTitle.textContent='Task details';details.append(text('div','Select a task or operation. Waits include unresolved endpoints; durations use local clocks.','empty'));return}
 sideTitle.textContent=n.nodeKind==='operation'?'Communication operation':`Task ${n.taskId}${n.subtaskId>=0?'.'+n.subtaskId:''}`;
 const kv=text('div','', 'kv');
 for(const [key,value] of [['node',n.nodeId],['device / rank',`${n.device} / ${n.rank}`],['stream',n.stream],['physical task',n.taskId],['task type',n.taskKind],['duration',`${n.duration.toFixed(3)} us`],['timing meaning',n.timingMeaning],['size (bytes)',n.sizeBytes||'unknown'],['operation',n.operationScope||'unbound'],['event',n.event||'—'],['hardware',n.hardware||'—'],['algorithm',n.algorithm||'unannotated'],['phase / step',`${n.phase||'—'} / ${n.step??'—'}`],['semantic',n.semantic||'—'],['match',n.confidence||n.match||'—'],['relative time',`+${(n.relativeStart??(n.start-(n.localTimeOrigin??model.timeMin))).toFixed(3)} – +${(n.relativeStop??(n.stop-(n.localTimeOrigin??model.timeMin))).toFixed(3)} us`]])addKV(kv,key,value??'—');
 details.append(kv);
 const wait=(model.waits||[]).find(w=>w.wait_graph_id===n.id);
 if(wait){details.append(text('div',`${wait.status}: ${wait.reason}`,'empty'));
  if(wait.classification){details.append(text('div',`${wait.classification} · ${wait.attribution||'local observation'}`,'section'));
   const ids=new Set((wait.candidate_ids||'').split(';'));
   for(const c of model.diagnosis?.candidates||[]){if(!ids.has(c.id))continue;const b=text('button',`Candidate rank ${c.user_rank} · ${c.phase} step ${c.step} · ${(c.duration_ns/1e6).toFixed(3)} ms`,'dep');b.append(text('small',c.evidence));b.onclick=()=>selectContext(c.graph_id);details.append(b)}
   if(wait.evidence_path_edge_ids){const b=text('button','Show evidence chain');b.onclick=()=>{for(const c of Object.values(controls))c.value='';controls.operation.value=wait.operation_scope;document.getElementById('boundaries').checked=true;const ids=relatedSet();const visible=model.nodes.filter(n=>ids.has(n.id));if(visible.length){const a=Math.min(...visible.map(n=>n.x)),z=Math.max(...visible.map(n=>n.x+n.w));viewX=a;xScale=Math.max(.0005,(canvas.clientWidth-LABEL-16)/Math.max(1,z-a));yPan=RULER+8-Math.min(...visible.map(n=>n.y))}renderWaits();renderCandidates();requestDraw()};details.append(b)}
  }
 }
 if(n.nodeKind==='operation'){
  const button=text('button','Focus this operation');button.onclick=()=>{for(const c of Object.values(controls))c.value='';controls.operation.value=n.operationScope;fit();renderWaits()};details.append(button);
  details.append(text('div','This span comes from COMMUNICATION_OP. It is a display interval, not an added execution task or dependency.','empty'));return;
 }
 if(coincidentIds.length>1){details.append(text('div',`Candidates at this position (${coincidentIds.length})`,'section'));for(const id of coincidentIds.slice(0,24)){const other=nodeById.get(id),b=text('button',`task ${other.taskId} · ${other.label}`,'dep');b.onclick=()=>setSelected(id,false,coincidentIds);details.append(b)}}
 const edges=incident.get(n.id)||[];
 for(const direction of ['incoming','outgoing']){
  const list=edges.filter(e=>direction==='incoming'?e.dst===n.id:e.src===n.id);
  details.append(text('div',`${direction==='incoming'?'Predecessors':'Successors'} (${list.length}) — all task types`,'section'));
  if(!list.length)details.append(text('div','No edge in supplied artifact','empty'));
  for(const e of list){
   const other=nodeById.get(e.src===n.id?e.dst:e.src),b=text('button','',`dep ${direction}`);b.style.setProperty('--edge',e.color||'#777');
   b.append(text('span',`${other?.nodeId?.split('/').pop()} rank ${other?.rank} · ${other?.label} · task ${other?.taskId}`));
   const metrics=[e.waitSpanNs&&`local wait=${e.waitSpanNs} ns`,e.remoteBlockNs&&`observed pre-record=${e.remoteBlockNs} ns`,e.postSignalNs&&`observed post-record=${e.postSignalNs} ns`].filter(Boolean).join(' · ');
   b.append(text('small',[e.kind,e.confidence,other?.phase,other?.step,metrics,e.timingStatus].filter(v=>v!==undefined&&v!=='').join(' · ')));b.onclick=()=>selectContext(other?.id);details.append(b)
  }
 }
}
let waitLimit=100;
function renderWaits(){
 const panel=document.getElementById('waitPanel');panel.hidden=!(model.waits||[]).length;if(panel.hidden)return;
 const list=document.getElementById('waitList');list.replaceChildren();
 let waits=model.waits.filter(w=>nodeVisible(nodeById.get(w.wait_graph_id)));
 if(document.getElementById('waitOrder').value==='asc')waits=[...waits].reverse();
 document.getElementById('waitCount').textContent=` ${waits.length} waits (local duration)`;
 for(const w of waits.slice(0,waitLimit)){const b=text('button','', 'dep');b.append(text('span',`${(Number(w.wait_span_ns)/1e6).toFixed(6)} ms · ${w.node_id.split('/').pop()} rank ${w.user_rank} · task ${w.task_id}`));b.append(text('small',`${w.phase||'unannotated'} step ${w.step||'—'} · ${w.classification||w.status} · producer ranks ${w.peer_ranks||'unknown'}`));b.onclick=()=>setSelected(w.wait_graph_id,true);list.append(b)}
 document.getElementById('moreWaits').hidden=waits.length<=waitLimit;
}
function renderCandidates(){
 const panel=document.getElementById('diagnosisPanel'),list=document.getElementById('candidateList');panel.hidden=!model.diagnosis;if(panel.hidden)return;list.replaceChildren();
 const cs=(model.diagnosis.candidates||[]).filter(c=>!controls.operation.value||c.operation_scope===controls.operation.value);
 list.append(text('div',cs.length?`${cs.length} observed candidates; not all are proven root causes`:'No candidate exceeds the configured thresholds. This is not proof of absence.','empty'));
 for(const c of cs.slice(0,24)){const b=text('button',`rank ${c.user_rank} · ${c.phase} step ${c.step} · ${(c.duration_ns/1e6).toFixed(3)} ms`,'dep');b.append(text('small',`${c.category}: ${c.evidence}`));b.disabled=!nodeById.has(c.graph_id);b.onclick=()=>selectContext(c.graph_id);list.append(b)}
}
controls.operation.addEventListener('change',fit);
controls.phase.addEventListener('change',fit);
document.getElementById('boundaries').onchange=()=>{requestDraw();renderWaits()};
renderCandidates();
document.getElementById('waitOrder').onchange=()=>{waitLimit=100;renderWaits()};document.getElementById('moreWaits').onclick=()=>{waitLimit+=100;renderWaits()};
document.getElementById('timingNote').textContent=`RDMA blocks show doorbell submission, not transfer completion. ${model.issueCount==null?'Graph completeness not supplied':`${model.issueCount} unresolved Notify issue entries`}. Operation lanes use COMMUNICATION_OP; node clocks are not aligned. ${model.nodes.filter(n=>n.nodeKind==='boundary').length} control boundaries (not missing executions).`;

function selectedEdges(){const w=(model.waits||[]).find(w=>w.wait_graph_id===selectedId),ids=new Set((w?.evidence_path_edge_ids||'').split(';'));return [...new Set([...(incident.get(selectedId)||[]),...model.edges.filter(e=>ids.has(e.id))])].filter(edgeVisible)}
function relatedSet(){const out=new Set(selectedId?[selectedId]:[]);for(const e of selectedEdges()){out.add(e.src);out.add(e.dst)}const w=(model.waits||[]).find(w=>w.wait_graph_id===selectedId);for(const id of (w?.candidate_graph_ids||'').split(';'))if(nodeById.has(id))out.add(id);return out}
function requestDraw(){if(dirty)return;dirty=true;requestAnimationFrame(()=>{dirty=false;draw()})}
function niceStep(raw){const p=10**Math.floor(Math.log10(Math.max(raw,1e-9))),r=raw/p;return(r<=1?1:r<=2?2:r<=5?5:10)*p}function xToTime(x){return model.timeMin+(x-LABEL)/model.timeScale}function timeToX(t){return LABEL+(t-model.timeMin)*model.timeScale}function timeLabel(us,step){if(Math.abs(us)>=1e6)return(us/1e6).toFixed(step<1e4?4:2)+' s';if(Math.abs(us)>=1e3)return(us/1e3).toFixed(step<10?3:step<100?2:1)+' ms';return us.toFixed(step<1?3:step<10?1:0)+' us'}
function draw(){const W=canvas.clientWidth,H=canvas.clientHeight;ctx.clearRect(0,0,W,H);ctx.fillStyle='#fff';ctx.fillRect(0,0,W,H);drawTracks(W,H);ctx.save();ctx.beginPath();ctx.rect(LABEL,RULER,W-LABEL,H-RULER);ctx.clip();drawTimeGrid(W,H);drawSelectedEdges();drawNodes(W,H);ctx.restore();drawRuler(W);drawLabels(H);drawOverview()}
function drawTracks(W,H){for(let i=0;i<model.lanes.length;i++){const l=model.lanes[i],y=sy(l.y);if(y+l.height<RULER||y>H)continue;ctx.fillStyle=i%2?'#fbfcfe':'#f5f7fa';ctx.fillRect(0,y,W,l.height);ctx.strokeStyle='#e4e7eb';ctx.beginPath();ctx.moveTo(0,y+l.height+.5);ctx.lineTo(W,y+l.height+.5);ctx.stroke()}}
function drawTimeGrid(W,H){const [a,b]=visibleX(),usPerPx=1/(model.timeScale*xScale),step=niceStep(usPerPx*120),ta=xToTime(a),tb=xToTime(b),first=Math.ceil(ta/step)*step;ctx.strokeStyle='#e1e5ea';ctx.lineWidth=1;for(let t=first;t<=tb;t+=step){const x=sx(timeToX(t));ctx.beginPath();ctx.moveTo(x,RULER);ctx.lineTo(x,H);ctx.stroke()}}
function drawRuler(W){ctx.fillStyle='#f8f9fa';ctx.fillRect(0,0,W,RULER);ctx.strokeStyle='#cfd4dc';ctx.beginPath();ctx.moveTo(0,RULER-.5);ctx.lineTo(W,RULER-.5);ctx.stroke();const [a,b]=visibleX(),step=niceStep(1/(model.timeScale*xScale)*120),ta=xToTime(a),tb=xToTime(b),first=Math.ceil(ta/step)*step;ctx.fillStyle='#4c5562';ctx.font='11px Arial';ctx.textBaseline='top';for(let t=first;t<=tb;t+=step){const x=sx(timeToX(t));ctx.fillRect(x,25,1,8);ctx.fillText(timeLabel(t-model.timeMin,step),x+4,7)}ctx.fillStyle='#eef1f5';ctx.fillRect(0,0,LABEL,RULER);ctx.fillStyle='#4c5562';ctx.fillText('Tracks',12,10)}
function drawLabels(H){ctx.fillStyle='#f8f9fa';ctx.fillRect(0,RULER,LABEL,H-RULER);ctx.strokeStyle='#cfd4dc';ctx.beginPath();ctx.moveTo(LABEL-.5,0);ctx.lineTo(LABEL-.5,H);ctx.stroke();ctx.font='12px Arial';ctx.textBaseline='middle';for(const l of model.lanes){const y=sy(l.y);if(y+l.height<RULER||y>H)continue;ctx.fillStyle='#30343b';ctx.fillText(l.label,12,y+Math.min(18,l.height/2));ctx.fillStyle='#7a828e';ctx.font='10px Arial';ctx.fillText(`${l.taskCount||0} tasks`,12,y+Math.min(34,l.height-6));ctx.font='12px Arial'}}
function projectedDurationWidth(n){return Math.max(0,n.duration||0)*model.timeScale*xScale}function markerNode(n){return n.zeroDuration||projectedDurationWidth(n)<2}
function drawNodes(W,H){const [a,b]=visibleX(),related=relatedSet(),hasSelection=!!selectedId;ctx.font='10px Arial';ctx.textBaseline='middle';for(const n of model.nodes){if(!nodeVisible(n)||n.x+n.w<a||n.x>b)continue;const y=sy(n.y);if(y+n.h<RULER||y>H)continue;const x=sx(n.x),isMarker=markerNode(n),w=projectedDurationWidth(n),isSel=n.id===selectedId,isRel=related.has(n.id);ctx.globalAlpha=hasSelection&&!isRel?.18:1;ctx.fillStyle=n.fill;ctx.strokeStyle=isSel?'#111':isRel?'#1967d2':n.stroke;ctx.lineWidth=isSel?3:isRel?2:1;if(isMarker){const cy=y+n.h/2,r=isSel?6:4;ctx.beginPath();ctx.moveTo(x,cy-r);ctx.lineTo(x+r,cy);ctx.lineTo(x,cy+r);ctx.lineTo(x-r,cy);ctx.closePath();ctx.fill();ctx.stroke()}else{ctx.fillRect(x,y,w,n.h);ctx.strokeRect(x+.5,y+.5,Math.max(1,w-1),n.h-1);if(w>42){ctx.fillStyle='#202124';ctx.fillText(n.label,x+4,y+n.h/2)}}ctx.globalAlpha=1}}
function drawSelectedEdges(){if(!selectedId)return;const edges=selectedEdges();ctx.lineWidth=2;for(const e of edges){const s=nodeById.get(e.src),d=nodeById.get(e.dst);if(!s||!d)continue;const x1=sx(s.x+(markerNode(s)?0:Math.max(0,s.duration||0)*model.timeScale)),y1=sy(s.y+s.h/2),x2=sx(d.x),y2=sy(d.y+d.h/2);ctx.strokeStyle=e.color||'#555';ctx.globalAlpha=.9;ctx.beginPath();ctx.moveTo(x1,y1);const bend=Math.max(28,Math.abs(x2-x1)*.38);ctx.bezierCurveTo(x1+bend,y1,x2-bend,y2,x2,y2);ctx.stroke();const ang=Math.atan2(y2-y1,x2-x1),q=6;ctx.fillStyle=e.color||'#555';ctx.beginPath();ctx.moveTo(x2,y2);ctx.lineTo(x2-q*Math.cos(ang-.55),y2-q*Math.sin(ang-.55));ctx.lineTo(x2-q*Math.cos(ang+.55),y2-q*Math.sin(ang+.55));ctx.closePath();ctx.fill()}ctx.globalAlpha=1}
function hitNodes(clientX,clientY){const r=canvas.getBoundingClientRect(),px=clientX-r.left,py=clientY-r.top,out=[];for(let i=model.nodes.length-1;i>=0;i--){const n=model.nodes[i],y=sy(n.y);if(!nodeVisible(n)||py<y||py>y+n.h)continue;const x=sx(n.x),isMarker=markerNode(n),w=projectedDurationWidth(n),radius=isMarker?6:0;if(px>=x-radius&&px<=x+(isMarker?radius:w))out.push(n)}return out}
canvas.onmousedown=e=>{canvas.focus();drag={x:e.clientX,y:e.clientY,lastX:e.clientX,lastY:e.clientY,moved:false};canvas.style.cursor='grabbing'};window.onmousemove=e=>{if(drag){const dx=e.clientX-drag.lastX,dy=e.clientY-drag.lastY;if(Math.abs(e.clientX-drag.x)+Math.abs(e.clientY-drag.y)>4)drag.moved=true;viewX-=dx/xScale;yPan+=dy;drag.lastX=e.clientX;drag.lastY=e.clientY;requestDraw();return}hoverPending=e;requestAnimationFrame(()=>{if(!hoverPending)return;const p=hoverPending;hoverPending=null;const ns=hitNodes(p.clientX,p.clientY),n=ns[0];if(n){tip.style.display='block';tip.style.left=Math.min(window.innerWidth-530,p.clientX+12)+'px';tip.style.top=Math.min(window.innerHeight-120,p.clientY+12)+'px';tip.textContent=(ns.length>1?`${ns.length} candidate tasks at this position\n`:'')+n.title}else tip.style.display='none'})};window.onmouseup=e=>{if(!drag)return;const wasMoved=drag.moved;drag=null;canvas.style.cursor='default';if(!wasMoved){const ns=hitNodes(e.clientX,e.clientY);setSelected(ns[0]?.id||null,false,ns.map(n=>n.id))}};canvas.ondblclick=e=>{const ns=hitNodes(e.clientX,e.clientY);if(ns[0])setSelected(ns[0].id,true,ns.map(n=>n.id))};
canvas.onwheel=e=>{e.preventDefault();const r=canvas.getBoundingClientRect(),mx=e.clientX-r.left;if(e.ctrlKey){const anchor=wx(mx),factor=e.deltaY<0?1.18:.84;xScale=Math.max(.0005,Math.min(24,xScale*factor));viewX=anchor-(mx-LABEL)/xScale}else if(e.shiftKey){viewX+=e.deltaY/xScale}else{viewX+=e.deltaX/xScale;yPan-=e.deltaY}requestDraw()};canvas.onkeydown=e=>{if(e.key==='f'){fit();e.preventDefault()}else if(e.key==='Escape'){setSelected(null)}else if(e.key==='ArrowLeft'){viewX-=80/xScale;requestDraw()}else if(e.key==='ArrowRight'){viewX+=80/xScale;requestDraw()}else if(e.key==='ArrowUp'){yPan+=50;requestDraw()}else if(e.key==='ArrowDown'){yPan-=50;requestDraw()}};
function drawOverview(){const W=overview.clientWidth,H=overview.clientHeight,[a,b]=bounds(),span=Math.max(1,b-a);octx.clearRect(0,0,W,H);octx.fillStyle='#fafbfc';octx.fillRect(0,0,W,H);const step=Math.max(1,Math.ceil(model.nodes.length/7000));octx.fillStyle='#6584ad88';for(let i=0;i<model.nodes.length;i+=step){const n=model.nodes[i];if(!nodeVisible(n))continue;const x=(n.x-a)/span*W;octx.fillRect(x,10,Math.max(1,n.w/span*W),H-20)}const[v0,v1]=visibleX();octx.strokeStyle='#d93025';octx.lineWidth=2;octx.strokeRect((v0-a)/span*W,2,Math.max(2,(v1-v0)/span*W),H-4)}overview.onmousedown=e=>{const r=overview.getBoundingClientRect(),[a,b]=bounds(),world=a+(e.clientX-r.left)/r.width*(b-a);viewX=world-(canvas.clientWidth-LABEL)/(2*xScale);requestDraw()};
const colors={direct_stream_order_observed:'#444',ffts_logical_stream_order:'#5c6bc0',ffts_notify_sync_observed:'#2b8a3e',direct_notify_sync_exact:'#7b3fb3',local_notify_sync_exact:'#d9488b',resource_stream_order_observed:'#444',resource_ffts_order_observed:'#5c6bc0',resource_notify_sync_observed:'#2b8a3e',resource_notify_sync_exact:'#7b3fb3',resource_local_notify_sync_exact:'#d9488b',cross_node_notify_sync_observed:'#007c91',resource_cross_node_notify_sync_observed:'#007c91',resource_cross_node_notify_sync_semantic:'#007c91',same_node_rdma_notify_sync_observed:'#b05b00',resource_same_node_rdma_notify_sync_observed:'#b05b00',resource_same_node_rdma_notify_sync_semantic:'#b05b00'},legend=document.getElementById('legend');for(const k of model.edgeKinds){const s=text('span','', 'swatch');s.style.background=colors[k]||'#777';legend.append(s,text('span',k.replaceAll('_',' ')))}
resize();const initialSelection=decodeURIComponent(location.hash.slice(1));if(initialSelection&&nodeById.has(initialSelection)){controls.operation.value=nodeById.get(initialSelection).operationScope||'';setSelected(initialSelection,true);renderCandidates()}else fit();renderDetails();renderWaits();
</script></body></html>'''


HTML_TEMPLATE = r'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>__TITLE__</title>
<style>
html,body{margin:0;height:100%;font:13px Arial,sans-serif;color:#222;background:#fff}#bar{min-height:44px;display:flex;align-items:center;gap:8px;padding:5px 12px;border-bottom:1px solid #ddd;background:#fafafa;flex-wrap:wrap}button,select,input{height:28px;border:1px solid #bbb;background:#fff;border-radius:4px;padding:0 7px}input{width:92px}#search{width:170px}#wrap{position:fixed;left:0;right:0;top:76px;bottom:0;overflow:hidden}canvas{width:100%;height:100%;display:block;cursor:grab;outline:none}#mini{position:fixed;right:14px;bottom:14px;width:220px;height:130px;border:1px solid #bbb;background:#fff;box-shadow:0 2px 8px #0002;z-index:1;cursor:crosshair}.tip{position:fixed;display:none;max-width:560px;white-space:pre-wrap;background:#111;color:#fff;padding:8px 10px;border-radius:4px;pointer-events:none;font:12px Consolas,monospace;z-index:2}.muted{color:#666}.label{font-size:11px;color:#555}</style>
</head><body><div id="bar"><strong>__TITLE__</strong><span class="muted">wheel pan · Ctrl+wheel zoom · hover details</span><button id="fit">Fit all</button><button id="fitSelection">Fit selection</button><button id="reset">100%</button><span class="label">device</span><select id="deviceFilter"></select><span class="label">rank</span><select id="rankFilter"></select><span class="label">stream</span><select id="streamFilter"></select><span class="label">event</span><select id="eventFilter"></select><span class="label">edge</span><select id="edgeFilter"></select><span class="label">time us</span><input id="timeStart" placeholder="start"><input id="timeStop" placeholder="stop"><input id="search" placeholder="task/event/match"><button id="clearFilters">Clear filters</button></div><div id="wrap"><canvas id="c" tabindex="0"></canvas></div><canvas id="mini" title="Click to jump"></canvas><div id="tip" class="tip"></div>
<script>
const model=__MODEL__;const canvas=document.getElementById('c'),ctx=canvas.getContext('2d'),mini=document.getElementById('mini'),mctx=mini.getContext('2d'),tip=document.getElementById('tip');let scale=1,ox=0,oy=0,drag=false,last=null,dirty=false;const nodeById=new Map(model.nodes.map(n=>[n.id,n]));
const origin=model.timeOrigin||Math.min(...model.nodes.map(n=>n.start||0));const controls={device:document.getElementById('deviceFilter'),rank:document.getElementById('rankFilter'),stream:document.getElementById('streamFilter'),event:document.getElementById('eventFilter'),edge:document.getElementById('edgeFilter'),start:document.getElementById('timeStart'),stop:document.getElementById('timeStop'),search:document.getElementById('search')};
function fillSelect(el,values){el.innerHTML='<option value="">all</option>'+[...new Set(values)].sort((a,b)=>String(a).localeCompare(String(b),undefined,{numeric:true})).map(v=>`<option>${v}</option>`).join('')}
fillSelect(controls.device,model.nodes.map(n=>n.device));fillSelect(controls.rank,model.nodes.map(n=>n.rank));fillSelect(controls.stream,model.nodes.map(n=>n.stream));fillSelect(controls.event,model.nodes.map(n=>n.event||n.taskKind).filter(Boolean));fillSelect(controls.edge,model.edgeKinds||[...new Set((model.edges||[]).map(e=>e.kind))]);
function nodeVisible(n){if(!n)return false;if(controls.device.value&&String(n.device)!==controls.device.value)return false;if(controls.rank.value&&String(n.rank)!==controls.rank.value)return false;if(controls.stream.value&&String(n.stream)!==controls.stream.value)return false;if(controls.event.value&&(n.event||n.taskKind)!==controls.event.value)return false;const a=parseFloat(controls.start.value),b=parseFloat(controls.stop.value),s=(n.start||0)-origin,e=(n.stop||0)-origin;if(Number.isFinite(a)&&e<a)return false;if(Number.isFinite(b)&&s>b)return false;const q=controls.search.value.trim().toLowerCase();return !q||n.title.toLowerCase().includes(q)}
function edgeVisible(e){return(!controls.edge.value||e.kind===controls.edge.value)&&nodeVisible(nodeById.get(e.src))&&nodeVisible(nodeById.get(e.dst))}
for(const el of Object.values(controls)){el.addEventListener('input',requestDraw);el.addEventListener('change',requestDraw)}document.getElementById('clearFilters').onclick=()=>{for(const el of Object.values(controls))el.value='';requestDraw()};
function resize(){const d=window.devicePixelRatio||1;canvas.width=canvas.clientWidth*d;canvas.height=canvas.clientHeight*d;ctx.setTransform(d,0,0,d,0,0);mini.width=mini.clientWidth*d;mini.height=mini.clientHeight*d;mctx.setTransform(d,0,0,d,0,0);requestDraw()}window.addEventListener('resize',resize);
function fit(){scale=Math.min(canvas.clientWidth/model.width,canvas.clientHeight/model.height)*0.96;scale=Math.max(.001,scale);ox=20;oy=20;requestDraw()}document.getElementById('fit').onclick=fit;document.getElementById('reset').onclick=()=>{scale=1;ox=0;oy=0;requestDraw()};
function fitSelection(){const xs=model.nodes.filter(nodeVisible);if(!xs.length)return;const x0=Math.min(...xs.map(n=>n.x)),x1=Math.max(...xs.map(n=>n.x+n.w)),y0=Math.min(...xs.map(n=>n.y)),y1=Math.max(...xs.map(n=>n.y+n.h));scale=Math.max(.001,Math.min(8,Math.min((canvas.clientWidth-40)/Math.max(1,x1-x0),(canvas.clientHeight-40)/Math.max(1,y1-y0))));ox=20-x0*scale;oy=20-y0*scale;requestDraw()}document.getElementById('fitSelection').onclick=fitSelection;
function wx(x){return (x-ox)/scale}function wy(y){return (y-oy)/scale}
function visible(pad){return{x0:wx(0)-pad,y0:wy(0)-pad,x1:wx(canvas.clientWidth)+pad,y1:wy(canvas.clientHeight)+pad}}
function intersects(x,y,w,h,v){return x+w>=v.x0&&x<=v.x1&&y+h>=v.y0&&y<=v.y1}
function requestDraw(){if(dirty)return;dirty=true;requestAnimationFrame(()=>{dirty=false;draw()})}
function draw(){ctx.clearRect(0,0,canvas.clientWidth,canvas.clientHeight);ctx.save();ctx.translate(ox,oy);ctx.scale(scale,scale);ctx.fillStyle='#fff';ctx.fillRect(wx(0),wy(0),canvas.clientWidth/scale,canvas.clientHeight/scale);const v=visible(80);drawGrid(v);drawEdges(v);drawNodes(v);ctx.restore();drawMini()}
function drawGrid(v){ctx.font='12px Arial';ctx.textBaseline='middle';for(const col of model.columns||[]){if(col.x+col.w<v.x0||col.x>v.x1)continue;ctx.fillStyle=(Math.floor(col.x/Math.max(col.w,1))%2)?'#fff':'#fbfbfb';ctx.fillRect(col.x,Math.max(52,v.y0),col.w,Math.min(model.height-48,v.y1)-Math.max(52,v.y0));ctx.strokeStyle='#e7e7e7';ctx.beginPath();ctx.moveTo(col.x,Math.max(52,v.y0));ctx.lineTo(col.x,Math.min(model.height-48,v.y1));ctx.stroke();if(scale>.18){ctx.fillStyle='#444';ctx.fillText(col.label,col.x+8,68)}}for(const lane of model.lanes||[]){if(lane.y+lane.height<v.y0||lane.y>v.y1)continue;ctx.strokeStyle='#eee';ctx.beginPath();ctx.moveTo(Math.max(160,v.x0),lane.y+lane.height/2);ctx.lineTo(Math.min(model.width-40,v.x1),lane.y+lane.height/2);ctx.stroke();if(v.x0<170){ctx.fillStyle='#333';ctx.fillText(lane.label,22,lane.y+20)}}}
function drawEdges(v){if(!model.edges||scale<.008)return;ctx.lineWidth=1.2;ctx.globalAlpha=scale<.22?.35:.7;for(const e of model.edges){if(!edgeVisible(e))continue;const s=nodeById.get(e.src),d=nodeById.get(e.dst);if(!s||!d)continue;const sx=s.x+s.w,sy=s.y+s.h/2,dx=d.x,dy=d.y+d.h/2;if(Math.max(sx,dx)<v.x0||Math.min(sx,dx)>v.x1||Math.max(sy,dy)<v.y0||Math.min(sy,dy)>v.y1)continue;ctx.strokeStyle=e.color||'#666';ctx.beginPath();const m=Math.max(18,Math.abs(dx-sx)*.45);ctx.moveTo(sx,sy);ctx.bezierCurveTo(sx+m,sy,dx-m,dy,dx,dy);ctx.stroke()}ctx.globalAlpha=1}
function drawNodes(v){ctx.font='9px Arial';ctx.textAlign='center';ctx.textBaseline='middle';const showText=scale>.32;for(const n of model.nodes){if(!nodeVisible(n)||!intersects(n.x,n.y,n.w,n.h,v))continue;ctx.fillStyle=n.fill;ctx.strokeStyle=n.stroke;ctx.lineWidth=1;ctx.beginPath();ctx.roundRect(n.x,n.y,n.w,n.h,3);ctx.fill();ctx.stroke();if(showText&&n.w>18){ctx.fillStyle='#222';ctx.fillText(n.label,n.x+n.w/2,n.y+n.h/2)}}}
function drawMini(){const w=mini.clientWidth,h=mini.clientHeight,ms=Math.min(w/model.width,h/model.height),step=Math.max(1,Math.ceil(model.nodes.length/8000));mctx.clearRect(0,0,w,h);mctx.fillStyle='#fff';mctx.fillRect(0,0,w,h);mctx.strokeStyle='#ccc';mctx.strokeRect(.5,.5,w-1,h-1);mctx.fillStyle='#7895';for(let i=0;i<model.nodes.length;i+=step){const n=model.nodes[i];if(!nodeVisible(n))continue;const x=n.x*ms,y=n.y*ms,nw=Math.max(1,n.w*ms),nh=Math.max(1,n.h*ms);if(x>w||y>h)continue;mctx.fillRect(x,y,nw,nh)}mctx.strokeStyle='#d33';mctx.lineWidth=1.5;mctx.strokeRect(wx(0)*ms,wy(0)*ms,canvas.clientWidth/scale*ms,canvas.clientHeight/scale*ms)}
function hit(x,y){const px=wx(x),py=wy(y),v={x0:px-3/scale,y0:py-3/scale,x1:px+3/scale,y1:py+3/scale};for(let i=model.nodes.length-1;i>=0;i--){const n=model.nodes[i];if(nodeVisible(n)&&intersects(n.x,n.y,n.w,n.h,v)&&px>=n.x&&px<=n.x+n.w&&py>=n.y&&py<=n.y+n.h)return n}return null}
function pan(dx,dy){ox+=dx;oy+=dy;requestDraw()}
canvas.onmousedown=e=>{canvas.focus();drag=true;last=[e.clientX,e.clientY];canvas.style.cursor='grabbing'};window.onmouseup=()=>{drag=false;canvas.style.cursor='grab'};window.onmousemove=e=>{if(drag){pan(e.clientX-last[0],e.clientY-last[1]);last=[e.clientX,e.clientY];return}const n=hit(e.clientX,e.clientY-76);if(n){tip.style.display='block';tip.style.left=(e.clientX+12)+'px';tip.style.top=(e.clientY+12)+'px';tip.textContent=n.title}else{tip.style.display='none'}};
canvas.onwheel=e=>{e.preventDefault();if(e.ctrlKey){const mx=e.clientX,my=e.clientY-76,old=scale;scale*=e.deltaY<0?1.12:.89;scale=Math.max(.001,Math.min(8,scale));ox=mx-(mx-ox)*(scale/old);oy=my-(my-oy)*(scale/old);requestDraw()}else if(e.shiftKey){pan(-e.deltaY,-e.deltaX)}else{pan(-e.deltaX,-e.deltaY)}};
canvas.onkeydown=e=>{const step=e.shiftKey?180:60;if(e.key==='ArrowLeft'){pan(step,0);e.preventDefault()}else if(e.key==='ArrowRight'){pan(-step,0);e.preventDefault()}else if(e.key==='ArrowUp'){pan(0,step);e.preventDefault()}else if(e.key==='ArrowDown'){pan(0,-step);e.preventDefault()}else if(e.key==='0'){scale=1;ox=0;oy=0;requestDraw()}else if(e.key==='f'){fit()}};
mini.onmousedown=e=>{const r=mini.getBoundingClientRect(),ms=Math.min(mini.clientWidth/model.width,mini.clientHeight/model.height),cx=(e.clientX-r.left)/ms,cy=(e.clientY-r.top)/ms;ox=canvas.clientWidth/2-cx*scale;oy=canvas.clientHeight/2-cy*scale;requestDraw()};
resize();fit();
</script></body></html>'''

def main() -> int:
    parser = argparse.ArgumentParser(description="Render HCCL diagnosis views as interactive HTML canvas pages.")
    parser.add_argument("input_csv", type=Path)
    parser.add_argument(
        "--view",
        choices=("timeline", "dependency", "execution", "resource", "waits"),
        default="timeline",
    )
    parser.add_argument("--layout", choices=("logical", "time"), default="logical")
    parser.add_argument("--edges-csv", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--svg-output", type=Path)
    parser.add_argument("--diagnosis", type=Path, help="Artifact-only wait analysis JSON")
    parser.add_argument("--initial-operation", default="", help="Initially focus this exact operation scope")
    parser.add_argument("--operations-csv", type=Path, help="Exported COMMUNICATION_OP timing artifact")
    parser.add_argument("--issues-csv", type=Path, help="Execution Notify ambiguity artifact")
    parser.add_argument("--waits-csv", type=Path, help="Export all local waits, including unresolved endpoints")
    args = parser.parse_args()
    if args.view == "timeline":
        rows = timeline.read_rows(
            args.input_csv,
            include_profiler_only=args.layout == "time",
        )
        model = build_timeline_model(rows, args.layout)
        output = args.output or args.input_csv.with_name(
            args.input_csv.stem + f"_timeline_{args.layout}.html"
        )
        title = f"HCCL timeline ({args.layout})"
    else:
        if args.edges_csv is None:
            parser.error(
                "--edges-csv is required for dependency views; "
                "the layout consumes exported graph artifacts"
            )
        rows = dep.read_graph_artifact_nodes(args.input_csv)
        edges = dep.read_graph_artifact_edges(args.edges_csv)
        operations = read_operation_timings(args.operations_csv) if args.operations_csv else []
        model = build_execution_dependency_model(rows, edges, operations)
        issues = []
        if args.issues_csv:
            with args.issues_csv.open(encoding="utf-8-sig", newline="") as source:
                issues = list(csv.DictReader(source))
        waits = build_wait_inventory(rows, edges, issues)
        if args.view == "waits" and not waits:
            parser.error("--view waits requires execution nodes containing NotifyWait")
        model["waits"] = waits if args.view == "waits" else []
        model["issueCount"] = len(issues) if args.issues_csv else None
        model["initialOperation"] = args.initial_operation
        if args.initial_operation and not any(n["operationScope"] == args.initial_operation for n in model["nodes"]):
            parser.error("initial operation not present in artifact")
        if args.diagnosis:
            diagnosis = json.loads(args.diagnosis.read_text(encoding="utf-8-sig"))
            try:
                attach_diagnosis(model, diagnosis, waits, args.view)
            except ValueError as error:
                parser.error(str(error))

        if args.waits_csv:
            if not waits:
                parser.error("--waits-csv requires execution nodes containing NotifyWait")
            with args.waits_csv.open("w", encoding="utf-8", newline="") as destination:
                writer = csv.DictWriter(destination, fieldnames=list(waits[0]))
                writer.writeheader()
                writer.writerows(waits)
        graph_view = "execution" if args.view == "dependency" else args.view
        model["graphView"] = graph_view
        output = args.output or args.input_csv.with_name(
            args.input_csv.stem + "_{}.html".format(graph_view)
        )
        title = "HCCL {} dependency graph".format(graph_view)
    write_html(output, title, model)
    print(f"html={output}")
    if args.svg_output is not None:
        if args.view == "timeline":
            parser.error("--svg-output is supported only for dependency views")
        write_dependency_svg(args.svg_output, title, model)
        print(f"svg={args.svg_output}")
    print(f"nodes={len(model['nodes'])}")
    print(f"edges={len(model.get('edges', []))}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
