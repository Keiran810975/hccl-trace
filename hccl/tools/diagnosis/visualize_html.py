#!/usr/bin/env python3
"""Render HCCL diagnosis views as interactive HTML canvas pages."""

from __future__ import annotations

import argparse
import html
import json
import math
import os
import sys
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Tuple

if __package__ in (None, ""):
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from diagnosis import visualize_dependency_graph as dep
    from diagnosis import visualize_timeline as timeline
else:
    from . import visualize_dependency_graph as dep
    from . import visualize_timeline as timeline


def color_for_event(event: str):
    return timeline.EVENT_COLOR.get(event) or dep.EVENT_COLOR.get(event) or ("#eeeeee", "#777777")


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
            fill, stroke = color_for_event(row.get("_event", ""))
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
            fill, stroke = color_for_event(row.get("_event", ""))
            nodes.append(node_record(row, x, y, w, node_h, fill, stroke, timeline.short_label(row)))
        width = left + span * scale + 100
    height = max(item["y"] + item["height"] for item in lane_items) + 80
    return {"kind": "timeline", "layout": layout, "width": width, "height": height, "lanes": lane_items, "columns": columns, "nodes": nodes, "edges": []}


def node_record(row: dict, x: float, y: float, w: float, h: float, fill: str, stroke: str, label: str) -> dict:
    title = (
        f"rank={row.get('_rank', '')} device={row.get('_device_id', '')} stream={row.get('_stream_id', '')} task={row.get('_task_id', '')}\n"
        f"phase={row.get('phase', row.get('_phase', ''))} event={row.get('event', row.get('_event', ''))} semantic={row.get('semantic', row.get('_semantic', ''))}\n"
        f"step={row.get('step', row.get('_step', ''))} slice={row.get('slice', row.get('_slice', ''))}\n"
        f"{row.get('_start', 0):.3f}..{row.get('_stop', 0):.3f} us duration={row.get('_duration', 0):.3f} us"
    )
    return {"x": round(x, 2), "y": round(y, 2), "w": round(w, 2), "h": round(h, 2), "fill": fill, "stroke": stroke, "label": label[:12], "title": title}


def build_dependency_model(rows: List[dict], edges: List[dict], col_width: int, row_height: int) -> dict:
    node_w = 50
    node_h = 22
    positions, columns, ranks, rank_y, rank_heights = dep.assign_positions(rows, col_width, row_height, node_w)
    nodes = []
    by_id = {row["_graph_id"]: row for row in rows}
    for row in rows:
        x, y = positions[row["_graph_id"]]
        fill, stroke = dep.EVENT_COLOR.get(row.get("event", ""), ("#eeeeee", "#777777"))
        rec = node_record(row, x, y, node_w, node_h, fill, stroke, dep.short_label(row.get("event", "")))
        rec["id"] = row["_graph_id"]
        rec["phase"] = row["_phase_group"]
        rec["step"] = row["_step"]
        nodes.append(rec)
    edge_items = []
    for edge in edges:
        src = positions.get(edge["src"])
        dst = positions.get(edge["dst"])
        if not src or not dst:
            continue
        edge_items.append({
            "src": edge["src"], "dst": edge["dst"], "kind": edge["kind"],
            "color": dep.EDGE_COLOR.get(edge["kind"], "#555"), "title": f"{edge['kind']}: {edge['reason']}",
        })
    width = 180 + max(1, len(columns)) * col_width + 100
    height = max((rank_y[rank] + rank_heights[rank] for rank in ranks), default=120) + 90
    return {
        "kind": "dependency", "width": width, "height": height,
        "columns": [{"x": 180 + i * col_width, "w": col_width, "label": f"{phase} step {step}"} for i, (phase, step) in enumerate(columns)],
        "lanes": [{"label": f"rank {rank}", "y": rank_y[rank], "height": rank_heights[rank]} for rank in ranks],
        "nodes": nodes, "edges": edge_items,
    }


def write_html(output: Path, title: str, model: dict) -> None:
    payload = json.dumps(model, ensure_ascii=False, separators=(",", ":"))
    page = HTML_TEMPLATE.replace("__TITLE__", html.escape(title)).replace("__MODEL__", payload)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(page, encoding="utf-8")


HTML_TEMPLATE = r'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>__TITLE__</title>
<style>
html,body{margin:0;height:100%;font:13px Arial,sans-serif;color:#222;background:#fff}#bar{height:44px;display:flex;align-items:center;gap:10px;padding:0 14px;border-bottom:1px solid #ddd;background:#fafafa}button{height:28px;border:1px solid #bbb;background:#fff;border-radius:4px;padding:0 10px}#wrap{position:fixed;left:0;right:0;top:45px;bottom:0;overflow:hidden}canvas{width:100%;height:100%;display:block;cursor:grab}.tip{position:fixed;display:none;max-width:520px;white-space:pre-wrap;background:#111;color:#fff;padding:8px 10px;border-radius:4px;pointer-events:none;font:12px Consolas,monospace;z-index:2}.muted{color:#666}</style>
</head><body><div id="bar"><strong>__TITLE__</strong><span class="muted">drag to pan, wheel to zoom, hover for details</span><button id="fit">Fit</button><button id="reset">100%</button></div><div id="wrap"><canvas id="c"></canvas></div><div id="tip" class="tip"></div>
<script>
const model=__MODEL__;const canvas=document.getElementById('c'),ctx=canvas.getContext('2d'),tip=document.getElementById('tip');let scale=1,ox=0,oy=0,drag=false,last=null;const nodeById=new Map(model.nodes.map(n=>[n.id,n]));
function resize(){const d=window.devicePixelRatio||1;canvas.width=canvas.clientWidth*d;canvas.height=canvas.clientHeight*d;ctx.setTransform(d,0,0,d,0,0);draw()}window.addEventListener('resize',resize);
function fit(){scale=Math.min(canvas.clientWidth/model.width,canvas.clientHeight/model.height)*0.96;ox=20;oy=20;draw()}document.getElementById('fit').onclick=fit;document.getElementById('reset').onclick=()=>{scale=1;ox=0;oy=0;draw()};
function wx(x){return (x-ox)/scale}function wy(y){return (y-oy)/scale}
function draw(){ctx.clearRect(0,0,canvas.clientWidth,canvas.clientHeight);ctx.save();ctx.translate(ox,oy);ctx.scale(scale,scale);ctx.fillStyle='#fff';ctx.fillRect(0,0,model.width,model.height);drawGrid();drawEdges();drawNodes();ctx.restore()}
function drawGrid(){ctx.font='12px Arial';ctx.textBaseline='middle';for(const col of model.columns||[]){ctx.fillStyle=(Math.floor(col.x/Math.max(col.w,1))%2)?'#fff':'#fbfbfb';ctx.fillRect(col.x,52,col.w,model.height-100);ctx.strokeStyle='#e7e7e7';ctx.beginPath();ctx.moveTo(col.x,52);ctx.lineTo(col.x,model.height-48);ctx.stroke();ctx.fillStyle='#444';ctx.fillText(col.label,col.x+8,68)}for(const lane of model.lanes||[]){ctx.strokeStyle='#eee';ctx.beginPath();ctx.moveTo(160,lane.y+lane.height/2);ctx.lineTo(model.width-40,lane.y+lane.height/2);ctx.stroke();ctx.fillStyle='#333';ctx.fillText(lane.label,22,lane.y+20)}}
function drawEdges(){if(!model.edges)return;ctx.lineWidth=1.2;for(const e of model.edges){const s=nodeById.get(e.src),d=nodeById.get(e.dst);if(!s||!d)continue;const sx=s.x+s.w,sy=s.y+s.h/2,dx=d.x,dy=d.y+d.h/2;ctx.strokeStyle=e.color||'#666';ctx.globalAlpha=.7;ctx.beginPath();const m=Math.max(18,Math.abs(dx-sx)*.45);ctx.moveTo(sx,sy);ctx.bezierCurveTo(sx+m,sy,dx-m,dy,dx,dy);ctx.stroke();ctx.globalAlpha=1}}
function drawNodes(){ctx.font='9px Arial';ctx.textAlign='center';ctx.textBaseline='middle';const x0=wx(0)-80,y0=wy(45)-40,x1=wx(canvas.clientWidth)+80,y1=wy(canvas.clientHeight)+80;for(const n of model.nodes){if(n.x+n.w<x0||n.x>x1||n.y+n.h<y0||n.y>y1)continue;ctx.fillStyle=n.fill;ctx.strokeStyle=n.stroke;ctx.lineWidth=1;ctx.beginPath();ctx.roundRect(n.x,n.y,n.w,n.h,3);ctx.fill();ctx.stroke();if(n.w>18){ctx.fillStyle='#222';ctx.fillText(n.label,n.x+n.w/2,n.y+n.h/2)}}}
function hit(x,y){const px=wx(x),py=wy(y);for(let i=model.nodes.length-1;i>=0;i--){const n=model.nodes[i];if(px>=n.x&&px<=n.x+n.w&&py>=n.y&&py<=n.y+n.h)return n}return null}
canvas.onmousedown=e=>{drag=true;last=[e.clientX,e.clientY];canvas.style.cursor='grabbing'};window.onmouseup=()=>{drag=false;canvas.style.cursor='grab'};window.onmousemove=e=>{if(drag){ox+=e.clientX-last[0];oy+=e.clientY-last[1];last=[e.clientX,e.clientY];draw();return}const n=hit(e.clientX,e.clientY-45);if(n){tip.style.display='block';tip.style.left=(e.clientX+12)+'px';tip.style.top=(e.clientY+12)+'px';tip.textContent=n.title}else{tip.style.display='none'}};
canvas.onwheel=e=>{e.preventDefault();const mx=e.clientX,my=e.clientY-45,old=scale;scale*=e.deltaY<0?1.12:.89;scale=Math.max(.05,Math.min(8,scale));ox=mx-(mx-ox)*(scale/old);oy=my-(my-oy)*(scale/old);draw()};
resize();fit();
</script></body></html>'''


def main() -> int:
    parser = argparse.ArgumentParser(description="Render HCCL diagnosis views as interactive HTML canvas pages.")
    parser.add_argument("merged_csv", type=Path)
    parser.add_argument("--view", choices=("timeline", "dependency"), default="timeline")
    parser.add_argument("--layout", choices=("logical", "time"), default="logical")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--include-unmatched", action="store_true")
    parser.add_argument("--events", default=",".join(dep.DEFAULT_EVENTS))
    parser.add_argument("--edge-kinds", default=",".join(dep.DEFAULT_EDGE_KINDS))
    parser.add_argument("--rank-size", type=int, default=-1)
    parser.add_argument("--rank-field", choices=("auto", "user_rank", "device_id"), default="auto")
    parser.add_argument("--node-mode", choices=("compact", "task"), default="compact")
    parser.add_argument("--upstream", choices=("previous", "next"), default="previous")
    args = parser.parse_args()
    if args.view == "timeline":
        rows = timeline.read_rows(args.merged_csv, include_unmatched=args.include_unmatched)
        model = build_timeline_model(rows, args.layout)
        output = args.output or args.merged_csv.with_name(args.merged_csv.stem + f"_timeline_{args.layout}.html")
        title = f"HCCL timeline ({args.layout})"
    else:
        rows = dep.read_rows(args.merged_csv, dep.parse_csv_list(args.events), include_unmatched=args.include_unmatched)
        dep.apply_rank_field(rows, args.rank_field)
        if args.node_mode == "compact":
            rows = dep.compact_dependency_rows(rows)
        dep.build_nodes(rows)
        edges = dep.build_edges(rows, dep.parse_csv_list(args.edge_kinds), dep.infer_rank_size(rows, args.rank_size), args.upstream)
        model = build_dependency_model(rows, edges, 140, 96)
        output = args.output or args.merged_csv.with_name(args.merged_csv.stem + "_dependency.html")
        title = "HCCL dependency graph"
    write_html(output, title, model)
    print(f"html={output}")
    print(f"nodes={len(model['nodes'])}")
    print(f"edges={len(model.get('edges', []))}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())