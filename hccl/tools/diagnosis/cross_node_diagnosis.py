"""Cross-node protocol slowdown detection over existing, evidenced paths."""
from __future__ import annotations

from collections import defaultdict
from decimal import Decimal
import html
import json

from . import source_events
from .schema import write_csv
from .workload_coordinates import position, location_fields


def analyze(protocol, rows, edges, coordinates, options, *, rolling_report=None, communication_tasks=(), operations=()):
    communication_tasks, operations = list(communication_tasks), list(operations)
    nodes = {row["_graph_id"]: row for row in rows}
    edge_ids = {edge["edge_id"] for edge in edges}
    ranks = {}
    for row in rows:
        rank = row["_user_rank"]
        if rank >= 0:
            ranks.setdefault(rank, set()).add(row["_node_id"])
    slots = defaultdict(list)
    segments = []
    for transfer in protocol["transfers"]:
        item = dict(transfer, comparison_status="iteration_binding_required", reference_count=0,
                    reference_iterations=[], reference_transfer_ids=[], reference_mean_ns=None, delta_ns=None,
                    reference_mad_ns=None, is_slow=False, diagnosis="not_compared", source_root_ids=[],
                    physical_cause="unknown")
        coord = coordinates.get(item["operation_scope"]) if coordinates is not None else None
        item.update(location_fields(coord) if coord else dict(stage="unbound", iteration=None, block=None, bucket=None))
        segments.append(item)
        if transfer["status"] != "protocol_interval_observed":
            item["comparison_status"] = "unresolved_protocol_path"
            continue
        if not all(identifier in edge_ids for identifier in transfer["evidence_edge_ids"]):
            raise ValueError("protocol path references missing execution edges")
        payload = nodes[item["payload_graph_id"]]
        signature = (item["sender_node_id"], item["sender_rank"], item["receiver_node_id"], item["receiver_rank"],
                     payload.get("algorithm", ""), item["phase"], item["step"], payload.get("slice", ""),
                     item["payload_size_bytes"], tuple((nodes[key]["_node_id"], nodes[key]["_user_rank"],
                         nodes[key].get("semantic", ""), nodes[key].get("profiler_task_kind", ""))
                         for key in item["evidence_node_ids"]))
        item["_signature"] = signature
        if coord is not None:
            slots[(coord["stage"], coord["iteration"], position(coord), signature)].append(item)
    roots = (rolling_report or {}).get("root_causes", [])
    for item in segments:
        if "_signature" not in item or item["stage"] == "unbound":
            continue
        key = (item["stage"], item["iteration"], position(item), item["_signature"])
        if len(slots[key]) != 1:
            item["comparison_status"] = "ambiguous_protocol_position"
            continue
        if item["stage"] != "measured" or item["iteration"] < 5:
            item["comparison_status"] = "insufficient_measured_history"
            continue
        iterations = list(range(item["iteration"] - 5, item["iteration"]))
        history = [slots.get(("measured", iteration, position(item), item["_signature"]), [])
                   for iteration in iterations]
        if any(len(group) != 1 for group in history):
            item["comparison_status"] = "missing_or_ambiguous_previous_protocol"
            continue
        history = [group[0] for group in history]
        mean, mad = source_events.statistics([value["protocol_duration_ns"] for value in history])
        slow = source_events.slow(item["protocol_duration_ns"], mean, mad, options)
        item.update(comparison_status="previous_five_iteration_mean", reference_count=5,
                    reference_iterations=iterations, reference_transfer_ids=[value["transfer_id"] for value in history],
                    reference_mean_ns=str(mean), reference_mad_ns=str(mad),
                    delta_ns=str(Decimal(item["protocol_duration_ns"]) - mean), is_slow=slow,
                    diagnosis="cross_node_path_candidate" if slow else "not_flagged")
        if slow:
            for root in roots:
                path = root.get("evidence_paths", {}).get(item["completion_graph_id"])
                if (root.get("status") == "dependency_supported_candidate" and path
                        and all(edge in edge_ids for edge in path)):
                    item["source_root_ids"].append(root["root_id"])
            if item["source_root_ids"]:
                item["diagnosis"] = "upstream_source_candidates"
    for item in segments:
        item.pop("_signature", None)
    details = []
    task_changes = {item["graph_id"]: item for item in (rolling_report or {}).get("tasks", [])}
    metadata = {item["graph_id"]: item for item in communication_tasks}
    for record in communication_tasks:
        item = dict(record, graph_binding_status="exact" if record["graph_id"] in nodes else "not_in_execution_graph")
        node = nodes.get(record["graph_id"])
        if node is not None:
            item.update(user_rank=node["_user_rank"], peer_rank=node.get("_peer_rank", -1),
                        operation_scope=node.get("_operation_scope", ""), algorithm=node.get("algorithm", ""),
                        phase=node.get("phase", ""), step=node.get("step", ""), slice=node.get("slice", ""),
                        event=node.get("event", ""), semantic=node.get("semantic", ""))
        src_rank, dst_rank = int(record["src_rank"]), int(record["dst_rank"])
        verified = (node is not None and node.get("_operation_scope_status") == "unique"
                    and node["_user_rank"] == src_rank and node.get("_peer_rank", -1) == dst_rank
                    and src_rank >= 0 and dst_rank >= 0)
        src, dst = ranks.get(src_rank, set()), ranks.get(dst_rank, set())
        item["rank_mapping_status"] = "semantic_endpoints_verified" if verified else "unverified_profiler_ranks"
        item["node_pair_status"] = ("cross_node" if verified and len(src) == len(dst) == 1 and src != dst else
                                    "same_node" if verified and len(src) == len(dst) == 1 else "unknown_rank_mapping")
        item.update(bandwidth_proxy_slow=False, bandwidth_reference_mean_ns=None, bandwidth_increase_ns=None,
                    bandwidth_comparison_status="missing_history_or_metadata")
        change = task_changes.get(record["graph_id"], {})
        reference_ids = change.get("reference_graph_ids", [])
        values = [metadata.get(key, {}).get("bandwidth_derived_duration_ns") for key in reference_ids]
        current = record.get("bandwidth_derived_duration_ns")
        if current and len(values) == 5 and all(values) and change.get("reference_count") == 5:
            mean, mad = source_events.statistics([Decimal(value) for value in values])
            item.update(bandwidth_proxy_slow=source_events.slow(Decimal(current), mean, mad, options),
                        bandwidth_reference_mean_ns=str(mean), bandwidth_increase_ns=str(Decimal(current) - mean),
                        bandwidth_comparison_status="previous_five_reported_bandwidth_estimates")
        details.append(item)
    operation_records, operation_slots = [], {}
    for operation in operations:
        item = dict(operation, direct_operation_slow=False, reference_mean_ns=None, delta_ns=None,
                    comparison_status="iteration_binding_required")
        coord = coordinates.get(operation["operation_scope"]) if coordinates is not None else None
        if coord is not None:
            item.update(location_fields(coord))
            item["comparison_status"] = "insufficient_measured_history"
            key = (item["node_id"], str(item["device_id"]), coord["stage"], coord["iteration"], position(coord))
            if key in operation_slots:
                raise ValueError("duplicate per-device communication operation position")
            operation_slots[key] = item
        operation_records.append(item)
    for item in operation_records:
        if item.get("stage") != "measured" or item["iteration"] < 5:
            continue
        history = [operation_slots.get((item["node_id"], str(item["device_id"]), "measured", iteration, position(item)))
                   for iteration in range(item["iteration"] - 5, item["iteration"])]
        if any(row is None for row in history):
            item["comparison_status"] = "missing_previous_operation"
            continue
        mean, mad = source_events.statistics([int(row["duration_ns"]) for row in history])
        item.update(direct_operation_slow=source_events.slow(int(item["duration_ns"]), mean, mad, options),
                    reference_mean_ns=str(mean), delta_ns=str(Decimal(item["duration_ns"]) - mean),
                    comparison_status="previous_five_direct_db_intervals")
    return dict(schema_version=1, reference_mode="previous_five_iteration_mean", segments=segments,
                communication_tasks=details, operations=operation_records,
                summary=dict(protocol_count=len(segments), comparable_protocol_count=sum(s["reference_count"] == 5 for s in segments),
                    slow_protocol_count=sum(s["is_slow"] for s in segments),
                    cross_node_path_candidate_count=sum(s["diagnosis"] == "cross_node_path_candidate" for s in segments),
                    upstream_explained_count=sum(s["diagnosis"] == "upstream_source_candidates" for s in segments),
                    direct_communication_task_count=len(details),
                    rdma_payload_metadata_count=sum(s["rdma_type"] == "RDMA_SEND_PAYLOAD" for s in details),
                    reported_bandwidth_proxy_slow_count=sum(s["bandwidth_proxy_slow"] for s in details),
                    direct_operation_slow_count=sum(s["direct_operation_slow"] for s in operation_records),
                    direct_operation_interval_count=len(operations)),
                limits=["Protocol intervals include readiness, sender scheduling, transfer and notification release; not pure network time.",
                        "A path candidate is not proof of NIC/switch congestion; physical_cause remains unknown.",
                        "Reported bandwidth and size/bandwidth estimates come from the same profiler metadata, not independent hardware completion evidence.",
                        "No aggregate statistic is divided among tasks and no execution dependency is added."])


def display_rows(report, rows):
    nodes = {row["_graph_id"]: row for row in rows}
    result = []
    for item in report["segments"]:
        if item["status"] != "protocol_interval_observed":
            continue
        done = nodes[item["completion_graph_id"]]
        start, stop = Decimal(item["protocol_start_ns"]) / 1000, Decimal(item["protocol_stop_ns"]) / 1000
        row = dict(done, _graph_id="display_" + item["transfer_id"], _source_row=-100000-len(result),
                   _node_kind="protocol", _stream_id=-3, _task_id=-1, _subtask_id=-1,
                   profiler_task_kind="protocol", event="Rank {} -> {} protocol".format(item["sender_rank"], item["receiver_rank"]),
                   event_name="PROTOCOL_INTERVAL", task_start=str(start), task_stop=str(stop),
                   _start_order=start, _stop_order=stop, _start=float(start), _stop=float(stop),
                   _duration=float(stop - start), semantic="", _protocol=item)
        result.append(row)
    return result


def export_report(report, directory, *, execution_link=True):
    directory.mkdir(parents=True, exist_ok=False)
    (directory / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    for filename, values in (("segments", report["segments"]), ("communication_tasks", report["communication_tasks"]),
                             ("communication_ops", report["operations"])):
        columns = list(dict.fromkeys(key for value in values for key in value)) or ["status"]
        write_csv(str(directory / (filename + ".csv")), columns, ({key: json.dumps(value, ensure_ascii=False)
            if isinstance(value, (list, dict)) else value for key, value in row.items()} for row in values))
    esc = lambda value: html.escape(str(value)) if value is not None else "不可用"
    labels = {"cross_node_path_candidate": "跨机路径候选，物理原因未知", "upstream_source_candidates": "存在上游源头候选",
              "not_flagged": "未标慢", "not_compared": "尚不可比较"}
    body = []
    for item in report["segments"]:
        path = ""
        if item["evidence_node_ids"]:
            links = []
            for key in item["evidence_node_ids"]:
                text = esc(key)
                if execution_link:
                    text = '<a href="../execution.html#{}">{}</a>'.format(esc(key), text)
                links.append("<li>" + text + "</li>")
            path = '<details><summary>真实依赖链</summary><ol>{}</ol><p>边：{}</p></details>'.format(
                "".join(links), esc("; ".join(item["evidence_edge_ids"])))
        values = ("{} → {}".format(item["sender_rank"], item["receiver_rank"]), item["iteration"], item["phase"], item["step"],
                  item["protocol_duration_ns"], item["reference_mean_ns"], item["delta_ns"],
                  labels[item["diagnosis"]] + " / " + item["comparison_status"])
        body.append('<tr{}>'.format(' class="slow"' if item["is_slow"] else "") +
                    "".join("<td>" + esc(value) + "</td>" for value in values) + "<td>" + path + "</td></tr>")
    page = '''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width">
<title>跨机通信诊断</title><style>body{font:15px system-ui,sans-serif;color:#183443;margin:24px;line-height:1.6}
h1{font-size:24px}section{overflow:auto}table{border-collapse:collapse;white-space:nowrap}td,th{border:1px solid #ccd5dc;padding:8px;text-align:left}
th{background:#edf3f7}.slow{background:#fff0db}a{color:#0066ad}details{max-width:420px;white-space:normal;overflow-wrap:anywhere}</style>
<h1>跨机通信诊断</h1><p>协议区间包含准备同步、发送端调度、传输和通知释放，不等于纯 RDMA 传输耗时。
当前值与前五个正式轮次同位置的协议区间均值比较。没有完整历史时明确保留不可比。</p>
<p><a href="communication_ops.csv">直接采集的通信算子区间</a> · <a href="communication_tasks.csv">细粒度通信任务及带宽事实</a> ·
<a href="report.json">结构化结果</a></p><section><table><thead><tr><th>Rank 方向</th><th>正式 iter</th><th>phase</th><th>step</th>
<th>协议区间 / ns</th><th>前五轮均值 / ns</th><th>增量 / ns</th><th>诊断与覆盖状态</th><th>依赖证据</th></tr></thead><tbody>ROWS</tbody></table></section></html>'''
    (directory / "index.html").write_text(page.replace("ROWS", "".join(body)), encoding="utf-8")
