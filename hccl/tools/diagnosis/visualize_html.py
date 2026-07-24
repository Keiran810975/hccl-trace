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
    from diagnosis import resource_dependency_graph as resource_dep
    from diagnosis import visualize_timeline as timeline
else:
    from . import visualize_dependency_graph as dep
    from . import resource_dependency_graph as resource_dep
    from . import visualize_timeline as timeline


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
    title = (
        f"rank={row.get('_rank', '')} device={row.get('_device_id', '')} stream={row.get('_stream_id', '')} "
        f"semantic_task={row.get('task_id', row.get('_task_id', ''))} "
        f"profiler_task={row.get('_profiler_task_id', row.get('_task_id', ''))} subtask={row.get('_subtask_id', '')}\n"
        f"phase={row.get('phase', row.get('_phase', ''))} event={row.get('event', row.get('_event', ''))} semantic={row.get('semantic', row.get('_semantic', ''))}\n"
        f"step={row.get('step', row.get('_step', ''))} slice={row.get('slice', row.get('_slice', ''))} "
        f"hardware={row.get('event_name', '')} match={row.get('match_method', '')} confidence={row.get('match_confidence', '')}\n"
        f"operation_scope={row.get('_operation_scope', '')} "
        f"operation_scope_status={row.get('_operation_scope_status', '')}\n"
        f"{row.get('_start', 0):.3f}..{row.get('_stop', 0):.3f} us duration={row.get('_duration', 0):.3f} us"
    )
    return {
        "id": row.get("_graph_id", f"n{row.get('_source_row', '')}"),
        "x": round(x, 2), "y": round(y, 2), "w": round(w, 2), "h": round(h, 2),
        "fill": fill, "stroke": stroke, "label": label[:12], "title": title,
        "rank": row.get("_rank", -1) if row.get("_rank", -1) >= 0 else row.get("_device_id", -1),
        "device": row.get("_device_id", -1),
        "stream": row.get("_stream_id", -1), "event": row.get("event", row.get("event_name", "")),
        "taskKind": row.get("profiler_task_kind", ""), "match": row.get("match_confidence", ""),
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


def build_execution_dependency_model(rows: List[dict], edges: List[dict]) -> dict:
    if not rows:
        raise ValueError("no timed profiler executions to render")
    left = 190
    top = 92
    node_h = 16
    lane_gap = 8
    lanes = sorted({(row["_node_id"], row["_device_id"], row["_stream_id"]) for row in rows})
    lane_index = {key: index for index, key in enumerate(lanes)}
    lane_items = []
    for index, key in enumerate(lanes):
        lane_items.append({
            "key": "|".join(str(value) for value in key),
            "label": f"dev {key[1]} stream {key[2]}",
            "y": top + index * 38,
            "height": 30,
            "taskCount": 0,
        })
    min_start = min(row["_start"] for row in rows)
    max_stop = max(row["_stop"] for row in rows)
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
        x = left + (row["_start"] - min_start) * scale
        y = lane_items[lane]["y"] + 6 + slot * 20
        width = max(4, row["_duration"] * scale)
        fill, stroke = timeline.row_color({
            "_event": row.get("event", ""),
            "profiler_task_kind": row.get("profiler_task_kind", ""),
        })
        label = row.get("event", "") or row.get("event_name", "") or row.get("profiler_task_kind", "")
        record = node_record(row, x, y, width, node_h, fill, stroke, label)
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
            "src": edge["src"], "dst": edge["dst"], "kind": edge["kind"],
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
        "width": left + span * scale + 100, "height": y_cursor + 70,
        "contentLeft": left, "timeScale": scale, "timeMin": min_start, "timeMax": max_stop,
        "lanes": lane_items, "columns": [], "nodes": nodes, "edges": edge_items,
        "edgeKinds": sorted({edge["kind"] for edge in edge_items}),
    }


def write_html(output: Path, title: str, model: dict) -> None:
    payload = json.dumps(model, ensure_ascii=False, separators=(",", ":"))
    template = PERFETTO_DEPENDENCY_TEMPLATE if model.get("kind") == "dependency" else HTML_TEMPLATE
    page = template.replace("__TITLE__", html.escape(title)).replace("__MODEL__", payload)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(page, encoding="utf-8")


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
:root{--toolbar:58px;--side:360px;--label:190px;--border:#d8dce3;--ink:#202124;--muted:#68707d;--blue:#1967d2}
*{box-sizing:border-box}html,body{margin:0;height:100%;overflow:hidden;font:12px Arial,sans-serif;color:var(--ink);background:#fff}
#toolbar{height:var(--toolbar);display:flex;align-items:center;gap:7px;padding:7px 10px;border-bottom:1px solid var(--border);background:#f8f9fa;white-space:nowrap}
#toolbar strong{font-size:14px;margin-right:4px}button,select,input{height:30px;border:1px solid #c8ccd3;border-radius:4px;background:#fff;padding:0 7px;color:#30343b}button{cursor:pointer}button:hover{background:#edf3fc;border-color:#9bb9e8}select{max-width:126px}input{width:112px}#search{width:180px}.sep{width:1px;height:24px;background:#d5d8de;margin:0 2px}.muted{color:var(--muted)}
#stage{position:fixed;left:0;right:var(--side);top:var(--toolbar);bottom:0;overflow:hidden;background:#fff}#trace{width:100%;height:100%;display:block;outline:none;cursor:default}
#side{position:fixed;right:0;top:var(--toolbar);bottom:0;width:var(--side);border-left:1px solid var(--border);background:#fff;display:flex;flex-direction:column;overflow:hidden}
#side h2{font-size:14px;margin:0;padding:13px 14px 9px;border-bottom:1px solid var(--border)}#details{padding:12px 14px;overflow:auto;flex:1}.empty{color:var(--muted);line-height:1.55;padding-top:4px}
.kv{display:grid;grid-template-columns:104px 1fr;gap:6px 8px;margin-bottom:14px}.kv .k{color:var(--muted)}.kv .v{font-family:Consolas,monospace;overflow-wrap:anywhere}
.section{font-weight:bold;margin:14px 0 7px}.dep{display:block;width:100%;height:auto;text-align:left;padding:7px 8px;margin:5px 0;border-left:4px solid var(--edge,#777);line-height:1.35}.dep small{display:block;color:var(--muted);margin-top:2px}.incoming:before{content:'← ';font-weight:bold}.outgoing:before{content:'→ ';font-weight:bold}
#legend{padding:9px 12px;border-top:1px solid var(--border);background:#fafbfc;line-height:1.8}.swatch{display:inline-block;width:9px;height:9px;margin:0 5px 0 9px;border-radius:2px}.swatch:first-child{margin-left:0}
#overview{height:96px;width:100%;display:block;border-top:1px solid var(--border);cursor:crosshair}.tip{position:fixed;display:none;max-width:520px;white-space:pre-wrap;background:#202124;color:#fff;padding:7px 9px;border-radius:4px;pointer-events:none;font:11px Consolas,monospace;z-index:5;box-shadow:0 2px 8px #0005}
</style></head><body>
<div id="toolbar"><strong>HCCL Trace</strong><span class="muted">dependency</span><button id="fit">Fit trace</button><button id="focus">Focus selected</button><button id="clearSelection">Clear selection</button><span class="sep"></span><select id="deviceFilter" title="device"></select><select id="rankFilter" title="rank"></select><select id="streamFilter" title="stream"></select><select id="eventFilter" title="event"></select><select id="edgeFilter" title="dependency kind"></select><input id="search" placeholder="Find task / event"><button id="clearFilters">Reset filters</button></div>
<div id="stage"><canvas id="trace" tabindex="0"></canvas></div>
<aside id="side"><h2 id="sideTitle">Task details</h2><div id="details"><div class="empty">Select a task block to inspect its direct predecessors and successors. Dependencies stay hidden until a task is selected.</div></div><canvas id="overview" title="Click to navigate"></canvas><div id="legend"></div></aside><div id="tip" class="tip"></div>
<script>
const model=__MODEL__,canvas=document.getElementById('trace'),ctx=canvas.getContext('2d'),overview=document.getElementById('overview'),octx=overview.getContext('2d'),tip=document.getElementById('tip'),details=document.getElementById('details'),sideTitle=document.getElementById('sideTitle');
const LABEL=model.contentLeft||190,RULER=34,nodeById=new Map(model.nodes.map(n=>[n.id,n])),incident=new Map();for(const e of model.edges){if(!incident.has(e.src))incident.set(e.src,[]);if(!incident.has(e.dst))incident.set(e.dst,[]);incident.get(e.src).push(e);incident.get(e.dst).push(e)}
let xScale=1,viewX=LABEL,yPan=0,selectedId=null,coincidentIds=[],drag=null,dirty=false,hoverPending=null;
const controls={device:document.getElementById('deviceFilter'),rank:document.getElementById('rankFilter'),stream:document.getElementById('streamFilter'),event:document.getElementById('eventFilter'),edge:document.getElementById('edgeFilter'),search:document.getElementById('search')};
function fillSelect(el,label,values){el.innerHTML=`<option value="">${label}: all</option>`+[...new Set(values)].sort((a,b)=>String(a).localeCompare(String(b),undefined,{numeric:true})).map(v=>`<option value="${String(v).replaceAll('&','&amp;').replaceAll('"','&quot;')}">${v}</option>`).join('')}
fillSelect(controls.device,'device',model.nodes.map(n=>n.device));fillSelect(controls.rank,'rank',model.nodes.map(n=>n.rank));fillSelect(controls.stream,'stream',model.nodes.map(n=>n.stream));fillSelect(controls.event,'event',model.nodes.map(n=>n.event||n.taskKind).filter(Boolean));fillSelect(controls.edge,'edge',model.edgeKinds||[]);
function nodeVisible(n){if(controls.device.value&&String(n.device)!==controls.device.value)return false;if(controls.rank.value&&String(n.rank)!==controls.rank.value)return false;if(controls.stream.value&&String(n.stream)!==controls.stream.value)return false;if(controls.event.value&&(n.event||n.taskKind)!==controls.event.value)return false;const q=controls.search.value.trim().toLowerCase();return !q||n.title.toLowerCase().includes(q)}
function edgeVisible(e){return(!controls.edge.value||e.kind===controls.edge.value)&&nodeVisible(nodeById.get(e.src))&&nodeVisible(nodeById.get(e.dst))}
for(const c of Object.values(controls)){c.addEventListener('input',()=>{requestDraw();renderDetails()});c.addEventListener('change',()=>{requestDraw();renderDetails()})}document.getElementById('clearFilters').onclick=()=>{for(const c of Object.values(controls))c.value='';requestDraw();renderDetails()};
function sx(x){return LABEL+(x-viewX)*xScale}function wx(x){return viewX+(x-LABEL)/xScale}function sy(y){return y+yPan}function visibleX(){return[viewX,viewX+Math.max(1,canvas.clientWidth-LABEL)/xScale]}
function resize(){const d=window.devicePixelRatio||1;canvas.width=canvas.clientWidth*d;canvas.height=canvas.clientHeight*d;ctx.setTransform(d,0,0,d,0,0);overview.width=overview.clientWidth*d;overview.height=overview.clientHeight*d;octx.setTransform(d,0,0,d,0,0);requestDraw()}window.addEventListener('resize',resize);
function bounds(){const xs=model.nodes.filter(nodeVisible);if(!xs.length)return[model.contentLeft,model.width-40];return[Math.min(...xs.map(n=>n.x)),Math.max(...xs.map(n=>n.x+n.w))]}
function fit(){const [a,b]=bounds();viewX=a;xScale=Math.max(.0005,(canvas.clientWidth-LABEL-16)/Math.max(1,b-a));yPan=RULER+8-(model.lanes[0]?.y||0);requestDraw()}document.getElementById('fit').onclick=fit;
function focusNode(n){if(!n)return;xScale=Math.max(xScale,Math.min(12,120/Math.max(4,n.w)));viewX=n.x-(canvas.clientWidth-LABEL)/(2*xScale)+n.w/2;yPan=RULER+80-n.y;requestDraw()}document.getElementById('focus').onclick=()=>focusNode(nodeById.get(selectedId));
document.getElementById('clearSelection').onclick=()=>setSelected(null);
function setSelected(id,focus=false,peers=[]){selectedId=id&&nodeById.has(id)?id:null;coincidentIds=selectedId?peers:[];renderDetails();requestDraw();if(focus&&selectedId)focusNode(nodeById.get(selectedId))}
function text(tag,value,cls){const e=document.createElement(tag);if(cls)e.className=cls;e.textContent=value??'';return e}
function addKV(box,key,value){box.append(text('div',key,'k'),text('div',String(value??''),'v'))}
function renderDetails(){details.replaceChildren();const n=nodeById.get(selectedId);if(!n){sideTitle.textContent='Task details';details.append(text('div','Select a task marker or block to inspect its direct predecessors and successors. Dependencies stay hidden until a task is selected.','empty'));return}sideTitle.textContent=`Task ${n.taskId}${n.subtaskId>=0?'.'+n.subtaskId:''}`;const kv=text('div','', 'kv');addKV(kv,'device / rank',`${n.device} / ${n.rank}`);addKV(kv,'stream',n.stream);addKV(kv,'physical task',`${n.taskId}${n.subtaskId>=0?'.'+n.subtaskId:''}`);addKV(kv,'semantic task',n.semanticTaskId>=0?n.semanticTaskId:'—');addKV(kv,'relative time',`+${(n.start-model.timeMin).toFixed(3)} – +${(n.stop-model.timeMin).toFixed(3)} us`);addKV(kv,'absolute start',`${n.start.toFixed(3)} us`);addKV(kv,'duration',`${n.duration.toFixed(3)} us`);addKV(kv,'event',n.event||'—');addKV(kv,'hardware',n.hardware||n.taskKind||'—');addKV(kv,'phase',n.phase||'—');addKV(kv,'semantic',n.semantic||'—');addKV(kv,'match',n.confidence||n.match||'—');details.append(kv);if(coincidentIds.length>1){details.append(text('div',`Candidates at this position (${coincidentIds.length})`,'section'));for(const id of coincidentIds.slice(0,24)){const other=nodeById.get(id),b=text('button',`task ${other.taskId}${other.subtaskId>=0?'.'+other.subtaskId:''} · ${other.event||other.hardware||other.taskKind}`,'dep');b.onclick=()=>setSelected(id,false,coincidentIds);details.append(b)}if(coincidentIds.length>24)details.append(text('div',`${coincidentIds.length-24} more; zoom in or narrow the filters.`, 'empty'))}const edges=(incident.get(n.id)||[]).filter(edgeVisible);for(const direction of ['incoming','outgoing']){const list=edges.filter(e=>direction==='incoming'?e.dst===n.id:e.src===n.id);details.append(text('div',`${direction==='incoming'?'Predecessors':'Successors'} (${list.length})`,'section'));if(!list.length){details.append(text('div','None under current filters','empty'));continue}for(const e of list){const other=nodeById.get(e.src===n.id?e.dst:e.src),b=text('button','',`dep ${direction}`);b.style.setProperty('--edge',e.color||'#777');b.append(text('span',`${e.kind} · task ${other?.taskId??'?'}`));const metrics=[e.waitSpanNs&&`wait=${e.waitSpanNs} ns`,e.remoteBlockNs&&`remote=${e.remoteBlockNs} ns`,e.postSignalNs&&`post=${e.postSignalNs} ns`,e.handoffGapNs&&`handoff=${e.handoffGapNs} ns`].filter(Boolean).join(' · ');b.append(text('small',[e.confidence,e.reason,metrics,e.timingStatus].filter(Boolean).join(' · ')));b.onclick=()=>setSelected(other?.id,true);details.append(b)}}}
function relatedSet(){const out=new Set(selectedId?[selectedId]:[]);for(const e of incident.get(selectedId)||[]){if(edgeVisible(e)){out.add(e.src);out.add(e.dst)}}return out}
function requestDraw(){if(dirty)return;dirty=true;requestAnimationFrame(()=>{dirty=false;draw()})}
function niceStep(raw){const p=10**Math.floor(Math.log10(Math.max(raw,1e-9))),r=raw/p;return(r<=1?1:r<=2?2:r<=5?5:10)*p}function xToTime(x){return model.timeMin+(x-LABEL)/model.timeScale}function timeToX(t){return LABEL+(t-model.timeMin)*model.timeScale}function timeLabel(us,step){if(Math.abs(us)>=1e6)return(us/1e6).toFixed(step<1e4?4:2)+' s';if(Math.abs(us)>=1e3)return(us/1e3).toFixed(step<10?3:step<100?2:1)+' ms';return us.toFixed(step<1?3:step<10?1:0)+' us'}
function draw(){const W=canvas.clientWidth,H=canvas.clientHeight;ctx.clearRect(0,0,W,H);ctx.fillStyle='#fff';ctx.fillRect(0,0,W,H);drawTracks(W,H);ctx.save();ctx.beginPath();ctx.rect(LABEL,RULER,W-LABEL,H-RULER);ctx.clip();drawTimeGrid(W,H);drawSelectedEdges();drawNodes(W,H);ctx.restore();drawRuler(W);drawLabels(H);drawOverview()}
function drawTracks(W,H){for(let i=0;i<model.lanes.length;i++){const l=model.lanes[i],y=sy(l.y);if(y+l.height<RULER||y>H)continue;ctx.fillStyle=i%2?'#fbfcfe':'#f5f7fa';ctx.fillRect(0,y,W,l.height);ctx.strokeStyle='#e4e7eb';ctx.beginPath();ctx.moveTo(0,y+l.height+.5);ctx.lineTo(W,y+l.height+.5);ctx.stroke()}}
function drawTimeGrid(W,H){const [a,b]=visibleX(),usPerPx=1/(model.timeScale*xScale),step=niceStep(usPerPx*120),ta=xToTime(a),tb=xToTime(b),first=Math.ceil(ta/step)*step;ctx.strokeStyle='#e1e5ea';ctx.lineWidth=1;for(let t=first;t<=tb;t+=step){const x=sx(timeToX(t));ctx.beginPath();ctx.moveTo(x,RULER);ctx.lineTo(x,H);ctx.stroke()}}
function drawRuler(W){ctx.fillStyle='#f8f9fa';ctx.fillRect(0,0,W,RULER);ctx.strokeStyle='#cfd4dc';ctx.beginPath();ctx.moveTo(0,RULER-.5);ctx.lineTo(W,RULER-.5);ctx.stroke();const [a,b]=visibleX(),step=niceStep(1/(model.timeScale*xScale)*120),ta=xToTime(a),tb=xToTime(b),first=Math.ceil(ta/step)*step;ctx.fillStyle='#4c5562';ctx.font='11px Arial';ctx.textBaseline='top';for(let t=first;t<=tb;t+=step){const x=sx(timeToX(t));ctx.fillRect(x,25,1,8);ctx.fillText(timeLabel(t-model.timeMin,step),x+4,7)}ctx.fillStyle='#eef1f5';ctx.fillRect(0,0,LABEL,RULER);ctx.fillStyle='#4c5562';ctx.fillText('Tracks',12,10)}
function drawLabels(H){ctx.fillStyle='#f8f9fa';ctx.fillRect(0,RULER,LABEL,H-RULER);ctx.strokeStyle='#cfd4dc';ctx.beginPath();ctx.moveTo(LABEL-.5,0);ctx.lineTo(LABEL-.5,H);ctx.stroke();ctx.font='12px Arial';ctx.textBaseline='middle';for(const l of model.lanes){const y=sy(l.y);if(y+l.height<RULER||y>H)continue;ctx.fillStyle='#30343b';ctx.fillText(l.label,12,y+Math.min(18,l.height/2));ctx.fillStyle='#7a828e';ctx.font='10px Arial';ctx.fillText(`${l.taskCount||0} tasks`,12,y+Math.min(34,l.height-6));ctx.font='12px Arial'}}
function projectedDurationWidth(n){return Math.max(0,n.duration||0)*model.timeScale*xScale}function markerNode(n){return n.zeroDuration||projectedDurationWidth(n)<2}
function drawNodes(W,H){const [a,b]=visibleX(),related=relatedSet(),hasSelection=!!selectedId;ctx.font='10px Arial';ctx.textBaseline='middle';for(const n of model.nodes){if(!nodeVisible(n)||n.x+n.w<a||n.x>b)continue;const y=sy(n.y);if(y+n.h<RULER||y>H)continue;const x=sx(n.x),isMarker=markerNode(n),w=projectedDurationWidth(n),isSel=n.id===selectedId,isRel=related.has(n.id);ctx.globalAlpha=hasSelection&&!isRel?.18:1;ctx.fillStyle=n.fill;ctx.strokeStyle=isSel?'#111':isRel?'#1967d2':n.stroke;ctx.lineWidth=isSel?3:isRel?2:1;if(isMarker){const cy=y+n.h/2,r=isSel?6:4;ctx.beginPath();ctx.moveTo(x,cy-r);ctx.lineTo(x+r,cy);ctx.lineTo(x,cy+r);ctx.lineTo(x-r,cy);ctx.closePath();ctx.fill();ctx.stroke()}else{ctx.fillRect(x,y,w,n.h);ctx.strokeRect(x+.5,y+.5,Math.max(1,w-1),n.h-1);if(w>42){ctx.fillStyle='#202124';ctx.fillText(n.label,x+4,y+n.h/2)}}ctx.globalAlpha=1}}
function drawSelectedEdges(){if(!selectedId)return;const edges=(incident.get(selectedId)||[]).filter(edgeVisible);ctx.lineWidth=2;for(const e of edges){const s=nodeById.get(e.src),d=nodeById.get(e.dst);if(!s||!d)continue;const x1=sx(s.x+(markerNode(s)?0:Math.max(0,s.duration||0)*model.timeScale)),y1=sy(s.y+s.h/2),x2=sx(d.x),y2=sy(d.y+d.h/2);ctx.strokeStyle=e.color||'#555';ctx.globalAlpha=.9;ctx.beginPath();ctx.moveTo(x1,y1);const bend=Math.max(28,Math.abs(x2-x1)*.38);ctx.bezierCurveTo(x1+bend,y1,x2-bend,y2,x2,y2);ctx.stroke();const ang=Math.atan2(y2-y1,x2-x1),q=6;ctx.fillStyle=e.color||'#555';ctx.beginPath();ctx.moveTo(x2,y2);ctx.lineTo(x2-q*Math.cos(ang-.55),y2-q*Math.sin(ang-.55));ctx.lineTo(x2-q*Math.cos(ang+.55),y2-q*Math.sin(ang+.55));ctx.closePath();ctx.fill()}ctx.globalAlpha=1}
function hitNodes(clientX,clientY){const r=canvas.getBoundingClientRect(),px=clientX-r.left,py=clientY-r.top,out=[];for(let i=model.nodes.length-1;i>=0;i--){const n=model.nodes[i],y=sy(n.y);if(!nodeVisible(n)||py<y||py>y+n.h)continue;const x=sx(n.x),isMarker=markerNode(n),w=projectedDurationWidth(n),radius=isMarker?6:0;if(px>=x-radius&&px<=x+(isMarker?radius:w))out.push(n)}return out}
canvas.onmousedown=e=>{canvas.focus();drag={x:e.clientX,y:e.clientY,lastX:e.clientX,lastY:e.clientY,moved:false};canvas.style.cursor='grabbing'};window.onmousemove=e=>{if(drag){const dx=e.clientX-drag.lastX,dy=e.clientY-drag.lastY;if(Math.abs(e.clientX-drag.x)+Math.abs(e.clientY-drag.y)>4)drag.moved=true;viewX-=dx/xScale;yPan+=dy;drag.lastX=e.clientX;drag.lastY=e.clientY;requestDraw();return}hoverPending=e;requestAnimationFrame(()=>{if(!hoverPending)return;const p=hoverPending;hoverPending=null;const ns=hitNodes(p.clientX,p.clientY),n=ns[0];if(n){tip.style.display='block';tip.style.left=Math.min(window.innerWidth-530,p.clientX+12)+'px';tip.style.top=Math.min(window.innerHeight-120,p.clientY+12)+'px';tip.textContent=(ns.length>1?`${ns.length} candidate tasks at this position\n`:'')+n.title}else tip.style.display='none'})};window.onmouseup=e=>{if(!drag)return;const wasMoved=drag.moved;drag=null;canvas.style.cursor='default';if(!wasMoved){const ns=hitNodes(e.clientX,e.clientY);setSelected(ns[0]?.id||null,false,ns.map(n=>n.id))}};canvas.ondblclick=e=>{const ns=hitNodes(e.clientX,e.clientY);if(ns[0])setSelected(ns[0].id,true,ns.map(n=>n.id))};
canvas.onwheel=e=>{e.preventDefault();const r=canvas.getBoundingClientRect(),mx=e.clientX-r.left;if(e.ctrlKey){const anchor=wx(mx),factor=e.deltaY<0?1.18:.84;xScale=Math.max(.0005,Math.min(24,xScale*factor));viewX=anchor-(mx-LABEL)/xScale}else if(e.shiftKey){viewX+=e.deltaY/xScale}else{viewX+=e.deltaX/xScale;yPan-=e.deltaY}requestDraw()};canvas.onkeydown=e=>{if(e.key==='f'){fit();e.preventDefault()}else if(e.key==='Escape'){setSelected(null)}else if(e.key==='ArrowLeft'){viewX-=80/xScale;requestDraw()}else if(e.key==='ArrowRight'){viewX+=80/xScale;requestDraw()}else if(e.key==='ArrowUp'){yPan+=50;requestDraw()}else if(e.key==='ArrowDown'){yPan-=50;requestDraw()}};
function drawOverview(){const W=overview.clientWidth,H=overview.clientHeight,[a,b]=bounds(),span=Math.max(1,b-a);octx.clearRect(0,0,W,H);octx.fillStyle='#fafbfc';octx.fillRect(0,0,W,H);const step=Math.max(1,Math.ceil(model.nodes.length/7000));octx.fillStyle='#6584ad88';for(let i=0;i<model.nodes.length;i+=step){const n=model.nodes[i];if(!nodeVisible(n))continue;const x=(n.x-a)/span*W;octx.fillRect(x,10,Math.max(1,n.w/span*W),H-20)}const[v0,v1]=visibleX();octx.strokeStyle='#d93025';octx.lineWidth=2;octx.strokeRect((v0-a)/span*W,2,Math.max(2,(v1-v0)/span*W),H-4)}overview.onmousedown=e=>{const r=overview.getBoundingClientRect(),[a,b]=bounds(),world=a+(e.clientX-r.left)/r.width*(b-a);viewX=world-(canvas.clientWidth-LABEL)/(2*xScale);requestDraw()};
const colors={direct_stream_order_observed:'#444',ffts_logical_stream_order:'#5c6bc0',ffts_notify_sync_observed:'#2b8a3e',direct_notify_sync_exact:'#7b3fb3',local_notify_sync_exact:'#d9488b',resource_stream_order_observed:'#444',resource_ffts_order_observed:'#5c6bc0',resource_notify_sync_observed:'#2b8a3e',resource_notify_sync_exact:'#7b3fb3',resource_local_notify_sync_exact:'#d9488b'},legend=document.getElementById('legend');for(const k of model.edgeKinds){const s=text('span','', 'swatch');s.style.background=colors[k]||'#777';legend.append(s,text('span',k.replaceAll('_',' ')))}
resize();const initialSelection=decodeURIComponent(location.hash.slice(1));if(initialSelection&&nodeById.has(initialSelection))setSelected(initialSelection,true);else fit();renderDetails();
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
        choices=("timeline", "dependency", "execution", "resource"),
        default="timeline",
    )
    parser.add_argument("--layout", choices=("logical", "time"), default="logical")
    parser.add_argument("--edges-csv", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--svg-output", type=Path)
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
        model = build_execution_dependency_model(rows, edges)
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
