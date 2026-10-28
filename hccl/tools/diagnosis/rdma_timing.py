"""Receiver-clock protocol completion intervals over existing cross-node edges.

These are notification handshakes, not hardware payload transfer durations.
No tasks, graph edges, cross-clock differences or nearest-time matches are added.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from decimal import Decimal
import html
import json
from pathlib import Path
import sys

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from diagnosis import analyze_waits as waits
    from diagnosis import visualize_dependency_graph as graph
    from diagnosis.dependency_model import stable_id
    from diagnosis.schema import write_csv
else:
    from . import analyze_waits as waits
    from . import visualize_dependency_graph as graph
    from .dependency_model import stable_id
    from .schema import write_csv


ORDER = "direct_stream_order_observed"
CROSS_SYNC = "cross_node_notify_sync_observed"
DATA_WAIT_SEMANTICS = frozenset({"link_rx_data_signal", "link_rx_payload_copy", "link_rx_payload_reduce"})
LIMITS = [
    "The interval starts at the receiver's readiness ACK submission and ends at its data Notify Wait completion.",
    "It includes readiness synchronization, remote scheduling, transfer and completion-notification overhead.",
    "It is not a hardware payload duration, pure network latency, bandwidth or a global critical path.",
    "Only existing observed/exact edges are followed. Missing, ambiguous or incomplete paths remain unresolved.",
    "Both timing endpoints must be on the same receiver node/device/rank; no cross-node timestamps are subtracted.",
    "Only annotated payloads with an evidenced two-sided handshake are supported; this is not all RDMA traffic.",
]


def _lane(row):
    return tuple(row[k] for k in ("_node_id", "_device_id", "_stream_id"))


def _endpoint(row):
    return tuple(row[k] for k in ("_node_id", "_device_id", "_user_rank"))


def _fact(row):
    return dict(graph_id=row["_graph_id"], node_id=row["_node_id"], user_rank=row["_user_rank"],
        device_id=row["_device_id"], stream_id=row["_stream_id"], task_id=row["_task_id"],
        phase=row.get("phase", ""), step=row.get("step", ""), semantic=row.get("semantic", ""),
        event=row.get("event") or row.get("event_name", ""), task_kind=row.get("profiler_task_kind", ""),
        start_ns=waits.ns(row, "start"), stop_ns=waits.ns(row, "stop"))


def analyze(rows, edges, *, max_hops=256):
    if max_hops < 1:
        raise ValueError("max_hops must be positive")
    nodes = {row["_graph_id"]:row for row in rows}
    links = {edge["edge_id"]:edge for edge in edges}
    if len(nodes) != len(rows) or len(links) != len(edges):
        raise ValueError("duplicate graph node/edge IDs")
    incoming, outgoing = defaultdict(list), defaultdict(list)
    for edge in edges:
        if edge["src"] not in nodes or edge["dst"] not in nodes:
            raise ValueError("missing graph endpoint")
        incoming[edge["dst"]].append(edge)
        outgoing[edge["src"]].append(edge)

    def syncs(identifier, direction):
        adjacency = incoming if direction == "back" else outgoing
        return [e for e in adjacency[identifier] if "notify_sync" in e["kind"]]

    def valid_sync(edge):
        src, dst = nodes[edge["src"]], nodes[edge["dst"]]
        return (edge["kind"] == CROSS_SYNC and edge.get("confidence") == "observed"
                and src.get("profiler_task_kind") == "rdma" and dst.get("profiler_task_kind") == "notify_wait"
                and all(r.get("_subtask_id", -1) < 0 and r.get("_operation_scope_status") == "unique" for r in (src, dst))
                and src["_node_id"] != dst["_node_id"]
                and src.get("_peer_rank") == dst["_user_rank"] and dst.get("_peer_rank") == src["_user_rank"]
                and src.get("_operation_scope") == dst.get("_operation_scope"))

    def walk(payload, direction):
        """Walk unique physical-stream predecessors/successors, never time neighbours."""
        current = payload["_graph_id"]
        path, visited = [], {current}
        adjacency = incoming if direction == "back" else outgoing
        if direction == "forward" and syncs(current, direction):
            return payload, path, None  # A single doorbell can submit payload and its notification together.
        for _ in range(max_hops):
            candidates = [e for e in adjacency[current] if e["kind"] == ORDER]
            if len(candidates) != 1:
                return None, path, "missing_stream_order" if not candidates else "ambiguous_stream_order"
            edge, = candidates
            src, dst = nodes[edge["src"]], nodes[edge["dst"]]
            if (edge.get("confidence") not in {"observed", "exact"} or _lane(src) != _lane(dst)
                    or any(r.get("_subtask_id", -1) >= 0 for r in (src, dst))):
                return None, path, "unsupported_stream_evidence"
            if waits.ns(src, "stop") > waits.ns(dst, "start"):
                return None, path, "incompatible_local_stream_timestamps"
            current = edge["src"] if direction == "back" else edge["dst"]
            if current in visited:
                return None, path, "cycle_in_stream_path"
            visited.add(current)
            row = nodes[current]
            if row.get("_operation_scope") != payload["_operation_scope"]:
                return None, path, "operation_boundary"
            path = [edge["edge_id"]] + path if direction == "back" else path + [edge["edge_id"]]
            if row.get("semantic") == "link_tx_payload":
                return None, path, "another_payload_before_handshake_endpoint"
            if direction == "back" and row.get("profiler_task_kind") == "notify_wait" and syncs(current, direction):
                if row.get("semantic") != "link_rx_ack":
                    return None, path, "preceding_sync_is_not_readiness_ack"
                return row, path, None
            if direction == "forward" and syncs(current, direction):
                return row, path, None
        return None, path, "stream_traversal_truncated"

    rdma = [r for r in rows if r.get("profiler_task_kind") == "rdma"]
    payloads = [r for r in rdma if r.get("semantic") == "link_tx_payload"]
    transfers, facts = [], {}
    for payload in sorted(payloads, key=lambda r:r["_graph_id"]):
        identifier = payload["_graph_id"]
        size = payload.get("profiler_size_bytes")
        item = dict(transfer_id=stable_id("rdma_protocol", (identifier,)), payload_graph_id=identifier,
            operation_scope=payload.get("_operation_scope", ""), sender_node_id=payload["_node_id"],
            sender_rank=payload["_user_rank"], sender_device_id=payload["_device_id"],
            sender_stream_id=payload["_stream_id"], sender_task_id=payload["_task_id"],
            receiver_rank=payload.get("_peer_rank", -1), receiver_node_id=None, receiver_device_id=None,
            phase=payload.get("phase", ""), step=payload.get("step", ""),
            payload_size_bytes=int(size) if size not in (None, "") else None,
            submission_start_ns=waits.ns(payload, "start"), submission_stop_ns=waits.ns(payload, "stop"),
            submission_duration_ns=waits.ns(payload, "stop")-waits.ns(payload, "start"),
            status="unresolved_protocol_interval", protocol_start_graph_id=None, completion_graph_id=None,
            protocol_start_ns=None, protocol_stop_ns=None, protocol_duration_ns=None,
            network_transfer_duration_ns=None, timing_scope="receiver_readiness_to_data_notification",
            evidence_node_ids=[], evidence_edge_ids=[], issues=[])
        transfers.append(item)
        facts[identifier] = _fact(payload)
        if (payload.get("match_status") != "matched" or payload.get("_subtask_id", -1) >= 0
                or payload.get("_operation_scope_status") != "unique" or payload.get("_peer_rank", -1) < 0):
            item["issues"].append("payload_identity_or_semantics_not_supported")
            continue
        ack, before, error = walk(payload, "back")
        signal, after, other_error = walk(payload, "forward")
        item["issues"].extend(e for e in (error, other_error) if e)
        if item["issues"]:
            continue
        ready_edges, done_edges = syncs(ack["_graph_id"], "back"), syncs(signal["_graph_id"], "forward")
        if len(ready_edges) != 1 or len(done_edges) != 1:
            item["issues"].append("ambiguous_handshake_sync")
            continue
        ready_edge, done_edge = ready_edges[0], done_edges[0]
        if not all(valid_sync(e) for e in (ready_edge, done_edge)):
            item["issues"].append("unsupported_cross_node_sync")
            continue
        ready, done = nodes[ready_edge["src"]], nodes[done_edge["dst"]]
        if (ready.get("semantic") != "link_tx_ack" or done.get("semantic") not in DATA_WAIT_SEMANTICS
                or _endpoint(ready) != _endpoint(done) or ready["_user_rank"] != payload["_peer_rank"]
                or _endpoint(ack) != _endpoint(payload) or _endpoint(signal) != _endpoint(payload)
                or ready["_node_id"] == payload["_node_id"]):
            item["issues"].append("receiver_protocol_endpoint_mismatch")
            continue
        start, stop = waits.ns(ready, "start"), waits.ns(done, "stop")
        if start < 0 or stop < start or waits.ns(ready, "stop") > stop:
            item["issues"].append("incompatible_receiver_timestamps")
            continue
        path = [ready_edge["edge_id"]] + before + after + [done_edge["edge_id"]]
        cursor, ordered = ready_edge["src"], [ready_edge["src"]]
        for key in path:
            edge = links[key]
            if edge["src"] != cursor or edge["dst"] in ordered:
                item["issues"].append("disconnected_or_repeated_evidence_path")
                break
            cursor = edge["dst"]
            ordered.append(cursor)
        if item["issues"]:
            continue
        if any(waits.ns(nodes[key], "stop") < waits.ns(nodes[key], "start") or
               waits.ns(nodes[key], "start") < 0 for key in ordered):
            item["issues"].append("invalid_task_timestamps")
            continue
        item.update(status="protocol_interval_observed", receiver_node_id=ready["_node_id"],
            receiver_device_id=ready["_device_id"], protocol_start_graph_id=ready["_graph_id"],
            completion_graph_id=done["_graph_id"], protocol_start_ns=start, protocol_stop_ns=stop,
            protocol_duration_ns=stop-start, evidence_node_ids=ordered, evidence_edge_ids=path,
            evidence_confidence="observed")
        facts.update((key, _fact(nodes[key])) for key in ordered)
    return dict(schema_version=1, kind="rdma_receiver_protocol_intervals", transfers=transfers, nodes=facts,
        summary=dict(rdma_task_count=len(rdma), annotated_payload_count=len(payloads),
            protocol_interval_count=sum(t["status"] == "protocol_interval_observed" for t in transfers),
            unresolved_payload_count=sum(t["status"] != "protocol_interval_observed" for t in transfers),
            unresolved_reason_counts=dict(Counter(reason for t in transfers for reason in t["issues"])),
            hardware_transfer_duration_count=0),
        limits=LIMITS, new_execution_edges=0, cross_node_time_subtraction=False,
        hardware_transfer_duration_available=False)


def _us(value):
    return "未测得" if value is None else "{:.3f} μs".format(Decimal(str(value))/1000)


def render_html(report, *, execution_link=False):
    e = lambda value:html.escape(str(value))
    summary = report["summary"]
    body = ["<header><h1>跨机协议完成区间</h1><p>已观测 {} / {} 个已标注 Payload；未解析 {} 个。</p>".format(
        summary["protocol_interval_count"], summary["annotated_payload_count"], summary["unresolved_payload_count"]),
        "<nav><a href='report.json'>JSON</a> · <a href='transfers.csv'>CSV</a>"+
        (" · <a href='../execution.html'>原生依赖图</a>" if execution_link else "")+"</nav></header>",
        "<p class='notice'>时间口径：接收端发出准备 ACK → 接收端的数据 Notify Wait 结束。"
        "包含同步、远端调度、传输及通知开销，不是纯 RDMA 传输耗时。起止点使用同一接收节点、设备的时钟。</p>",
        "<p>精确硬件传输耗时：<strong>未测得</strong>。本报告不增加任务或依赖边，不计算跨机绝对时差。</p>"]
    example = next((t for t in report["transfers"] if t["status"] == "protocol_interval_observed"), None)
    if example:
        stages = []
        labels = {example["protocol_start_graph_id"]:"发出准备 ACK", example["payload_graph_id"]:"提交 Payload",
                  example["completion_graph_id"]:"数据到达通知 Wait 结束"}
        signal_id = example["evidence_node_ids"][-2]
        labels[signal_id] = "提交 Payload 与数据通知" if signal_id == example["payload_graph_id"] else "提交数据通知"
        for key in example["evidence_node_ids"]:
            node = report["nodes"][key]
            label = labels.get(key, "等待准备 ACK" if node["semantic"] == "link_rx_ack" else node["event"])
            stages.append("<li><b>{} / Rank {}</b><br>{}<br><small>stream {} / task {}</small></li>".format(
                e(node["node_id"].rsplit("/",1)[-1]), node["user_rank"], e(label), node["stream_id"], node["task_id"]))
        body.append("<section><h2>一条真实协议路径</h2><ol class='flow'>"+"".join(stages)+"</ol><p>"
            "接收端 Rank {} 协议区间：<strong>{}</strong>；发送端 RDMA 提交耗时：{}。</p></section>".format(
                example["receiver_rank"], _us(example["protocol_duration_ns"]), _us(example["submission_duration_ns"])))
    body.append("<div class='table-wrap'><table><thead><tr><th>发送端 Payload</th><th>对端 Rank</th><th>数据量 / Byte</th>"
                "<th>RDMA 提交耗时</th><th>接收端协议完成区间</th><th>状态与依赖</th></tr></thead><tbody>")
    for item in report["transfers"]:
        title = "{} / Rank {} / stream {} / task {}".format(item["sender_node_id"].rsplit("/",1)[-1],
            item["sender_rank"], item["sender_stream_id"], item["sender_task_id"])
        path = []
        for index, identifier in enumerate(item["evidence_node_ids"]):
            node = report["nodes"][identifier]
            path.append("<li><b>{} / Rank {}</b> · {} · stream {} / task {}<br><code>{}</code>{}</li>".format(
                e(node["node_id"].rsplit("/",1)[-1]), node["user_rank"], e(node["event"]), node["stream_id"],
                node["task_id"], e(identifier), "<br><small>进入此任务的边：{}</small>".format(
                e(item["evidence_edge_ids"][index-1])) if index else ""))
        details = ("<details><summary>查看真实依赖路径</summary><ol>"+"".join(path)+"</ol><p>接收端本地时钟："
            "<code>{} → {} ns</code></p></details>".format(item["protocol_start_ns"], item["protocol_stop_ns"]) if path else
            "<span class='unresolved'>未解析</span><br><code>"+e("; ".join(item["issues"]))+"</code>")
        body.append("<tr><td>{}<br><small>{} / step {}</small><br><code>{}</code></td><td>{}</td><td>{}</td>"
            "<td>{}</td><td><strong>{}</strong></td><td>{}</td></tr>".format(e(title), e(item["phase"]), e(item["step"]),
                e(item["payload_graph_id"]), item["receiver_rank"], e(item["payload_size_bytes"] or "未知"),
                _us(item["submission_duration_ns"]), _us(item["protocol_duration_ns"]), details))
    body.append("</tbody></table></div><p>协议区间之间可能重叠，不能相加为 workload 总损失。"
                "未标注 Payload 或缺失通知证据时，不推断传输完成。</p>")
    return """<!doctype html><html lang='zh-CN'><head><meta charset='utf-8'>
<meta name='viewport' content='width=device-width,initial-scale=1'><title>跨机协议完成区间</title><style>
body{font:14px/1.6 -apple-system,BlinkMacSystemFont,'PingFang SC',sans-serif;color:#24292e;margin:24px;letter-spacing:0}
h1{font-size:24px;margin:0}a{color:#1268a5}header{border-bottom:1px solid #d9dde2;padding-bottom:16px}
.notice{border-left:3px solid #bb8126;padding-left:12px}.table-wrap{overflow-x:auto}table{border-collapse:collapse;width:100%;min-width:850px}
th,td{text-align:left;padding:12px 10px;border-bottom:1px solid #e0e4e8;vertical-align:top}th{background:#f5f7f8}
td:first-child{min-width:220px}td:last-child{min-width:250px}code{font-size:11px;overflow-wrap:anywhere}small{color:#59636d}
summary{cursor:pointer;color:#1268a5}li{margin:12px 0}ol{padding-left:20px}.unresolved{color:#a63124}
h2{font-size:17px;margin:12px 0}.flow{display:flex;list-style:none;padding:0;gap:24px;flex-wrap:wrap}.flow li{position:relative;padding:8px 18px 8px 0;border-bottom:2px solid #c7d0d8;flex:1;min-width:120px}.flow li:first-child{border-color:#45866b}.flow li:last-child{border-color:#bd852e}.flow li:not(:last-child):after{content:'→';position:absolute;right:-17px;top:22px;color:#59636d}
@media(max-width:600px){body{margin:16px}h1{font-size:21px}.flow{display:block}.flow li{padding:8px 0 16px;margin-bottom:12px}.flow li:not(:last-child):after{content:'↓';right:12px;top:auto;bottom:-17px}}
</style></head><body>"""+"".join(body)+"</body></html>"


def export_report(report, directory, *, execution_link=False):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=False)
    (directory/"report.json").write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    records = [dict(item, evidence_node_ids=json.dumps(item["evidence_node_ids"]),
                    evidence_edge_ids=json.dumps(item["evidence_edge_ids"]), issues=json.dumps(item["issues"]))
               for item in report["transfers"]]
    fields = list(records[0]) if records else ["transfer_id", "status", "protocol_duration_ns", "network_transfer_duration_ns"]
    write_csv(str(directory/"transfers.csv"), fields, records)
    (directory/"index.html").write_text(render_html(report,execution_link=execution_link),encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("artifact_dir",type=Path)
    parser.add_argument("-o","--output-dir",type=Path,required=True)
    args = parser.parse_args()
    try:
        gate=json.loads((args.artifact_dir/"pipeline_result.json").read_text(encoding="utf-8-sig"))
        if gate.get("status") != "passed" or not gate.get("analysis_completed"):
            raise ValueError("requires a passed diagnosis artifact")
        rows=graph.read_graph_artifact_nodes(args.artifact_dir/"dep_graph_nodes.csv")
        edges=graph.read_graph_artifact_edges(args.artifact_dir/"dep_graph_edges.csv")
        report=analyze(rows,edges)
        export_report(report,args.output_dir)
    except (OSError,ValueError,KeyError,ArithmeticError) as error:
        parser.exit(1,"RDMA protocol timing failed: "+str(error)+"\n")
    print(json.dumps(report["summary"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
