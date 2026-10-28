#!/usr/bin/env python3
"""Observe native verbs completions without inventing device or cross-clock timing."""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, fields
import html
import json
import os
from pathlib import Path
import sys

if __package__ in (None, ""):
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from diagnosis.parse_plog import _parse_bracket_values
    from diagnosis.schema import write_csv
else:
    from .parse_plog import _parse_bracket_values
    from .schema import write_csv


TAG = "[HcclRdmaCompletion]"
KEY_FIELDS = ("node_id", "pid", "process_epoch", "cq_id", "qp_num", "wr_id")
WC_OPCODE = {"send": 0, "write": 1, "read": 2}


@dataclass(frozen=True)
class CompletionEvent:
    node_id: str
    stage: str
    schema_version: int = 1
    backend: str = ""
    clock: str = ""
    pid: int = -1
    process_epoch: int = -1
    cq_id: int = -1
    qp_num: int = -1
    wr_id: int = -1
    opcode: str = ""
    raw_opcode: int = -1
    bytes: int = -1
    accepted: int = -1
    result: int = -1
    start_ns: int = -1
    post_return_ns: int = -1
    local_rank: int = -1
    peer_rank: int = -1
    message_id: int = -1
    role: str = ""
    send_flags: int = -1
    wc_opcode: int = -1
    status: int = -1
    observed_ns: int = -1
    reason: str = ""
    source: str = ""


EVENT_FIELDS = tuple(field.name for field in fields(CompletionEvent))
TEXT_FIELDS = {"node_id", "stage", "backend", "clock", "opcode", "role", "reason", "source"}


def event_from_mapping(data, node_id, source=""):
    if int(data.get("schema_version", -1)) != 1:
        raise ValueError("unsupported RDMA completion schema")
    if data.get("node_id", node_id) != node_id:
        raise ValueError("RDMA completion node conflicts with capture partition")
    stage = data.get("stage")
    if stage not in {"post", "cqe", "gap"}:
        raise ValueError("unknown RDMA completion stage")
    required = {"reason"} if stage == "gap" else set(KEY_FIELDS) - {"node_id"}
    if stage == "post":
        required |= {"opcode", "raw_opcode", "bytes", "accepted", "result", "start_ns", "post_return_ns",
                     "send_flags", "local_rank", "peer_rank", "message_id", "role"}
    elif stage == "cqe":
        required |= {"wc_opcode", "status", "observed_ns"}
    if any(key not in data or str(data[key]) == "" for key in required):
        raise ValueError("incomplete RDMA completion record at " + source)
    if stage != "gap" and (data.get("backend") != "ibverbs" or data.get("clock") != "process_steady_ns"):
        raise ValueError("unsupported RDMA completion backend/clock")
    values = {key: value if key in TEXT_FIELDS else int(value) for key, value in data.items()
              if key in EVENT_FIELDS and key not in {"node_id", "source"}}
    event = CompletionEvent(node_id=node_id, source=source, **values)
    if stage != "gap":
        if any(getattr(event, key) < 0 for key in KEY_FIELDS[1:]):
            raise ValueError("negative RDMA completion identity")
        if event.wr_id > (1 << 64) - 1 or event.qp_num > (1 << 32) - 1:
            raise ValueError("RDMA completion identity out of range")
    if stage == "post" and (event.accepted not in {-1, 0, 1} or event.bytes < 0 or
                            event.start_ns < 0 or event.post_return_ns < event.start_ns or event.send_flags < 0):
        raise ValueError("invalid RDMA post interval/result")
    if stage == "cqe" and (event.observed_ns < 0 or event.status < 0 or event.wc_opcode < 0):
        raise ValueError("invalid RDMA completion status/time")
    return event


def parse_inputs(paths, node_id):
    events = []
    for path in paths:
        with Path(path).open(encoding="utf-8-sig", errors="replace") as stream:
            for number, line in enumerate(stream, 1):
                if TAG in line:
                    data = _parse_bracket_values(line.split(TAG, 1)[1])
                    events.append(event_from_mapping(data, node_id, "{}:{}".format(path, number)))
    return events


def read_events(paths):
    import csv
    events = []
    for path in paths:
        with Path(path).open(encoding="utf-8-sig", newline="") as stream:
            for row in csv.DictReader(stream):
                events.append(event_from_mapping(row, row["node_id"], row.get("source", "")))
    return events


def analyze(events):
    groups, gaps = defaultdict(list), []
    for event in events:
        if event.stage == "gap":
            gaps.append(asdict(event))
        else:
            groups[tuple(getattr(event, key) for key in KEY_FIELDS)].append(event)
    operations, unmatched = [], []
    for key, members in sorted(groups.items()):
        posts = sorted((e for e in members if e.stage == "post"), key=lambda e: e.start_ns)
        completions = sorted((e for e in members if e.stage == "cqe"), key=lambda e: e.observed_ns)
        accepted = [e for e in posts if e.accepted == 1]
        # Reused WR IDs are safe only when *all* local lifetimes are disjoint.
        # An outstanding duplicate or missing record invalidates the whole key.
        unique = bool(accepted) and len(accepted) == len(completions) and not any(e.accepted == -1 for e in posts)
        if unique:
            unique = all(c.observed_ns >= p.start_ns for p, c in zip(accepted, completions))
            unique &= all(completions[i].observed_ns < accepted[i + 1].start_ns for i in range(len(accepted) - 1))
        paired = dict(zip(accepted, completions)) if unique else {}
        for post in posts:
            item = {name: getattr(post, name) for name in EVENT_FIELDS if name != "stage"}
            item.update(completion_observed_ns=None, operation_elapsed_observed_ns=None,
                        network_transfer_duration_ns=None, graph_id=None, completion_source=None,
                        completion_status=None, status="missing_completion")
            if post.accepted == 0:
                item["status"] = "post_failed"
            elif post.accepted == -1:
                item["status"] = "unknown_post_result"
            elif not unique and completions:
                item["status"] = "ambiguous_completion"
            elif post in paired:
                completion = paired[post]
                item.update(completion_observed_ns=completion.observed_ns,
                            completion_status=completion.status, completion_source=completion.source)
                if completion.status:
                    item["status"] = "completion_error"
                elif WC_OPCODE.get(post.opcode) != completion.wc_opcode:
                    item["status"] = "completion_opcode_mismatch"
                else:
                    item.update(status="completion_observed",
                                operation_elapsed_observed_ns=completion.observed_ns - post.start_ns)
            operations.append(item)
        if not unique:
            unmatched.extend(dict(asdict(c), pairing_status="ambiguous_or_orphan_completion") for c in completions)
    counts = Counter(item["status"] for item in operations)
    return dict(schema_version=1, measurement="post_send_entry_to_successful_cq_observation",
                clock="per_node_process_steady_ns", cross_node_time_subtraction=False,
                hardware_transfer_duration_available=False, execution_graph_binding_available=False,
                full_transfer_and_dependency_available=False,
                limitations=["CQ observation includes posting, queueing and polling delay; it is not wire time.",
                             "Native WR identities are not profiler task identities; no time-nearest binding is performed.",
                             "AI_CPU/HDC device-managed CQ paths are not covered by the native verbs observer.",
                             "Successful Send completion is not proof that the peer application consumed the data."],
                summary=dict(post_count=len(operations), completion_observed_count=counts["completion_observed"],
                             missing_completion_count=counts["missing_completion"], trace_gap_count=len(gaps),
                             unmatched_completion_count=len(unmatched), status_counts=dict(counts)),
                operations=operations, unmatched_completions=unmatched, trace_gaps=gaps)


def export_report(report, output, *, dependency_link=False, protocol_link=False):
    output.mkdir(parents=True, exist_ok=False)
    (output / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    columns = ("node_id", "local_rank", "peer_rank", "pid", "process_epoch", "cq_id", "qp_num", "wr_id", "opcode",
               "role", "bytes", "message_id", "start_ns", "post_return_ns", "completion_observed_ns",
               "operation_elapsed_observed_ns", "status", "completion_status", "network_transfer_duration_ns",
               "graph_id", "source", "completion_source")
    write_csv(str(output / "operations.csv"), columns,
              ({key: item[key] for key in columns} for item in report["operations"]))
    esc = lambda value: html.escape(str(value)) if value is not None else "不可用"
    rows = "".join("<tr>" + "".join("<td>" + esc(item[key]) + "</td>" for key in
        ("node_id", "local_rank", "peer_rank", "opcode", "role", "bytes", "operation_elapsed_observed_ns", "status")) + "</tr>"
        for item in report["operations"])
    links = ('<a href="../execution.html">任务依赖图</a> ' if dependency_link else "")
    links += '<a href="../rdma_timing/index.html">协议区间及跨机依赖</a>' if protocol_link else ""
    page = '''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width">
<title>RDMA 完成证据</title><style>body{font:16px system-ui,sans-serif;color:#173344;margin:24px;line-height:1.6}
h1{font-size:24px}table{border-collapse:collapse;white-space:nowrap}th,td{padding:8px 12px;border:1px solid #ccd5dc;text-align:left}
th{background:#eef3f6}section{overflow:auto}a{color:#0066ad}.status{color:#a42b20;font-weight:600}</style>
<h1>RDMA 完成证据</h1><p class="status">完整跨机传输计时＋任务绑定：未具备</p>
<p>已取得成功 CQ 完成观测：COUNT 条。这里的纳秒区间从 post_send 入口到 CQ 被观察到，包含排队和轮询开销，
不是纯网络传输耗时。没有完成事件时保留“不可用”，不使用 Notify Wait 或提交时长代替。</p>
<p>当前 AI_CPU 路径仍缺独立的硬件完成证据；WR 尚未与 profiler 物理任务精确绑定。已有跨机同步依赖单独保留。</p>
<p>LINKS</p><section><table><thead><tr><th>Node</th><th>Rank</th><th>Peer</th><th>操作</th><th>角色</th><th>字节</th>
<th>完成观测区间 / ns</th><th>状态</th></tr></thead><tbody>ROWS</tbody></table></section></html>'''
    page = page.replace("COUNT", str(report["summary"]["completion_observed_count"]))
    page = page.replace("LINKS", links).replace("ROWS", rows)
    (output / "index.html").write_text(page, encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("events", nargs="+", type=Path, help="replayed rdma_completion_events.csv artifacts")
    parser.add_argument("-o", "--output-dir", type=Path, required=True)
    args = parser.parse_args()
    export_report(analyze(read_events(args.events)), args.output_dir)


if __name__ == "__main__":
    main()
