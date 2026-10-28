"""Presentation of existing source-to-Wait evidence, without inference or reranking."""
from __future__ import annotations

from decimal import Decimal
import json


TIMING_LABELS = {
    "compatible_stream_order": "同流时间顺序相容",
    "producer_observed_during_wait": "Record 完成于 Wait 期间",
    "cross_node_uncalibrated": "跨节点时钟未校准，仅展示依赖",
    "signal_precedes_wait_start": "Record 早于 Wait 开始，不能直接归因等待增长",
    "record_after_wait_end": "Record 晚于 Wait 结束，时间证据不相容",
    "overlapping_stream_tasks": "同流任务时间重叠，时间证据受限",
    "rdma_submission_not_completion": "RDMA 提交不等于传输完成",
    "ffts_not_complete_hardware_dag": "FFTS 不是完整硬件时序图",
}
BOUNDARY_LABELS = {
    "missing_source_anchor": "缺少源头设备锚点",
    "missing_reported_evidence_path": "分析器未报告这条路径",
    "missing_artifact_edge": "缺少原始依赖边",
    "disconnected_path": "路径不连续",
    "missing_artifact_endpoint": "依赖端点缺失",
    "repeated_path_node": "路径出现重复节点",
    "unsupported_evidence": "依赖证据等级不支持",
    "path_does_not_end_at_declared_wait": "路径未到达目标 Wait",
    "invalid_host_branch_anchor": "Host 分支的 Record 锚点不匹配",
}
STATUS_LABELS = {
    "incomplete_evidence": "证据中断",
    "complete_with_timing_limits": "路径连通 · 时间证据受限",
    "complete_observed_path": "路径连通",
}
EVENT_LABELS = {
    "copy_start": "Copy 数据搬运",
    "tx_ack_start": "发出 ACK",
    "rx_ack_start": "等待 ACK",
    "tx_data_signal_start": "发出数据就绪通知",
    "rx_data_signal_start": "等待数据就绪通知",
    "rx_payload_reduce_start": "接收并归约",
    "rx_payload_copy_start": "接收并拷贝",
    "NOTIFY_RECORD": "发出通知",
    "NOTIFY_WAIT": "等待通知",
}


def duration(value, *, signed=False):
    if value is None or str(value) == "":
        return "不可比"
    value = Decimal(str(value)) / 1000
    return ("+" if signed and value > 0 else "") + "{:.3f} μs".format(value)


def factor(value):
    return "不可比" if value is None or str(value) == "" else "{:.2f}×".format(Decimal(str(value)))


def location(value):
    return "{} · Rank {} · stream {} · task {}".format(value["node_id"].rsplit("/", 1)[-1],
        value["user_rank"], value["stream_id"], value["task_id"])


def coordinate(value):
    return "iter {} / Block {} / bucket {} · {} / step {}".format(
        *[value.get(k) if value.get(k) is not None else "?" for k in
          ("iteration", "block", "bucket", "phase", "step")])


def compact_path(report, chain):
    """Fold only ordinary same-stream interiors; retain sync and warning endpoints."""
    identifiers = chain["node_ids"]
    if not identifiers:
        return []
    keep = {0, len(identifiers) - 1}
    for index, identifier in enumerate(identifiers):
        if report["nodes"][identifier]["comparison"].get("duration_slow"):
            keep.add(index)
    for index, hop in enumerate(chain["hops"]):
        src, dst = (report["nodes"][hop[k]] for k in ("src", "dst"))
        if ("notify_sync" in hop["kind"] or hop["edge_id"] in chain["timing_warnings"] or
            any(src.get(k) != dst.get(k) for k in ("node_id", "user_rank", "stream_id", "operation_scope"))):
            keep.update((index, index + 1))
    segments, index = [], 0
    while index < len(identifiers):
        stop = index + 1
        if index not in keep:
            while stop < len(identifiers) and stop not in keep:
                stop += 1
        segments.append(dict(kind="task" if index in keep else "group",
                             node_ids=identifiers[index:stop], position=index))
        index = stop
    return segments


def branch_summary(report, chain):
    target = report["nodes"].get(chain["target_wait_graph_id"])
    if not chain["path_complete"]:
        return "证据未连通到目标 Wait，不能确认完整等待关系。"
    sync = next((hop for hop in reversed(chain["hops"])
                 if hop["dst"] == chain["target_wait_graph_id"] and "notify_sync" in hop["kind"]), None)
    if not target or sync is None:
        return "存在已报告的依赖路径，但没有到目标 Wait 的直接 Notify 配对。"
    producer = report["nodes"][sync["src"]]
    return "{} 的 {} 等待 {} 的 {}。".format(
        location(target), target["event"] or "Wait", location(producer), producer["event"] or "Record")


def build_view_model(report):
    origins = {}
    for node in report["nodes"].values():
        origins[node["node_id"]] = min(origins.get(node["node_id"], node["start_ns"]), node["start_ns"])
    nodes = {}
    for identifier, node in report["nodes"].items():
        metrics = node["comparison"]
        nodes[identifier] = dict(node, start_ns=str(node["start_ns"]), stop_ns=str(node["stop_ns"]),
            event_label=EVENT_LABELS.get(node["event"], node["event"] or node["task_kind"]),
            location=location(node), coordinate=coordinate(node), duration=duration(node["duration_ns"]),
            reference=duration(metrics.get("reference_mean_ns")), delta=duration(metrics.get("delta_ns"), signed=True),
            factor=factor(metrics.get("slowdown_factor")),
            relative="{} – {}".format(duration(node["start_ns"]-origins[node["node_id"]]),
                                       duration(node["stop_ns"]-origins[node["node_id"]])))
    candidates = []
    for root in report["candidates"]:
        source = root["source"]
        chains = [dict(chain, segments=compact_path(report, chain), sentence=branch_summary(report, chain),
                       status_label=STATUS_LABELS[chain["status"]]) for chain in root["chains"]]
        source_label = ("Host 准备区间" if source["component"] == "host_preparation" else
                        EVENT_LABELS.get(source.get("event"), source.get("event") or "执行任务"))
        display_source = dict(source)
        for key in ("observed_start_ns", "observed_stop_ns"):
            if display_source.get(key) is not None:
                display_source[key] = str(display_source[key])
        candidates.append(dict(root, source=display_source, chains=chains, source_label=source_label, coordinate=coordinate(source),
            source_location=("{} · Rank {} · Host 观测区间".format(source["node_id"].rsplit("/", 1)[-1], source["user_rank"])
                             if source["component"] == "host_preparation" else location(source)),
            duration=duration(source["duration_ns"]), reference=duration(source["reference_mean_ns"]),
            delta=duration(source["delta_ns"], signed=True), factor=factor(source["slowdown_factor"]),
            model_gain=duration(source.get("modeled_execution_gain_ns")),
            wait_ranks=sorted({nodes[c["target_wait_graph_id"]]["user_rank"] for c in chains
                               if c["target_wait_graph_id"] in nodes}, key=str)))
    return dict(summary=report["summary"], candidates=candidates, nodes=nodes,
                origins={node:str(value) for node, value in origins.items()},
                timing_labels=TIMING_LABELS, boundary_labels=BOUNDARY_LABELS)


def render_markdown(report):
    def cell(value):
        return str(value).replace("|", "\\|").replace("\n", " ").replace("\r", " ")

    lines = ["# 异常传播链", "", "{candidate_count} 个候选源头，{chain_count} 条已报告路径，"
             "{unique_target_wait_count} 个不同目标 Wait。".format(**report["summary"]), "",
             "参考为同次运行前5个正式 iteration 的同定位任务均值；候选排序保持原序。",
             "路径连通不等于物理因果已证明；Wait 增量不能相加为 workload 损失。",
             "完整节点、依赖边和精确时间见 report.json / steps.csv。", ""]
    if not report["candidates"]:
        lines.extend(["未输出候选根因；不能据此判断 workload 没有异常。", ""])
    for root in report["candidates"]:
        source = root["source"]
        label = "Host 准备区间" if source["component"] == "host_preparation" else source.get("event") or "执行任务"
        lines.extend(["## 候选 {}{}：Rank {} / {}".format(root["candidate_rank"],
            "（主候选）" if root["primary"] else "", source["user_rank"], cell(label)), "",
            coordinate(source), "",
            "前5轮均值 {} → 当前 {}；增量 {}；慢化 {}。".format(duration(source["reference_mean_ns"]),
                duration(source["duration_ns"]), duration(source["delta_ns"], signed=True), factor(source["slowdown_factor"])), "",
            "本地关键路径模型收益 {}；物理原因 {}。".format(duration(source.get("modeled_execution_gain_ns")),
                cell(source.get("physical_cause") or "unknown")), ""])
        if root["anchor_meaning"] == "observed_device_anchor_only":
            lines.extend(["下列设备路径从各分支实际 Record 开始；Host 区间不是设备任务，不新增 Host → 设备边。", ""])
        if source.get("traversal_truncated") or source.get("other_backtrace_branches_truncated"):
            lines.extend(["注意：分析器回溯存在截断，分支列表并非完整影响范围。", ""])
        if not root["chains"]:
            lines.extend(["没有已报告的下游路径。", ""])
        for index, chain in enumerate(root["chains"], 1):
            stages = []
            for segment in compact_path(report, chain):
                if segment["kind"] == "group":
                    stages.append("同流推进（{} 个任务）".format(len(segment["node_ids"])))
                else:
                    node = report["nodes"][segment["node_ids"][0]]
                    stages.append("Rank {} {} [stream {}, task {}]".format(
                        node["user_rank"], cell(node["event"] or node["task_kind"]), node["stream_id"], node["task_id"]))
            lines.extend(["### 分支 {} · {}".format(index, STATUS_LABELS[chain["status"]]), "",
                          " → ".join(stages) or "缺少设备锚点", "", branch_summary(report, chain), ""])
            target = report["nodes"].get(chain["target_wait_graph_id"])
            if target:
                lines.extend(["目标 Wait：前5轮均值 {} → 当前 {}，增量 {}。".format(
                    duration(target["comparison"].get("reference_mean_ns")), duration(target["duration_ns"]),
                    duration(target["comparison"].get("delta_ns"), signed=True)), ""])
            lines.extend(["证据：{} 条边，最弱等级 {}。链 ID：`{}`。".format(
                len(chain["edge_ids"]), chain["evidence_confidence"], chain["chain_id"]), ""])
            for hop in chain["hops"]:
                if hop["edge_id"] in chain["timing_warnings"]:
                    lines.extend(["时间限制：{}（{}）。".format(TIMING_LABELS.get(hop["timing_status"], hop["timing_status"]), hop["edge_id"]), ""])
            for boundary in chain["boundaries"]:
                lines.extend(["证据断点：{}。".format(BOUNDARY_LABELS.get(boundary["reason"], boundary["reason"])), ""])
    return "\n".join(lines) + "\n"


def render_html(report):
    # Absolute nanoseconds travel as strings; the browser never rounds profiler timestamps.
    data = json.dumps(build_view_model(report), ensure_ascii=False, separators=(",", ":"))
    for value, escaped in (("&", "\\u0026"), ("<", "\\u003c"), (">", "\\u003e"),
                           ("\u2028", "\\u2028"), ("\u2029", "\\u2029")):
        data = data.replace(value, escaped)
    return PAGE.replace("__MODEL__", data)


PAGE = r"""<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>异常传播诊断</title><style>
*{box-sizing:border-box}body{margin:0;color:#24292e;background:#fff;font:14px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC",sans-serif;letter-spacing:0}
header{padding:20px 24px 16px;border-bottom:1px solid #d9dde2;display:flex;gap:20px;align-items:center;justify-content:space-between;flex-wrap:wrap}
h1{font-size:24px;margin:0 0 4px}h2{font-size:20px;margin:0 0 8px}h3{font-size:15px;margin:0 0 10px}p{margin:6px 0}a{color:#1268a5}small,.muted{color:#59636d}small{font-size:12px}
code{font:12px/1.5 ui-monospace,monospace;overflow-wrap:anywhere}button,input,select{font:inherit;color:inherit}button,select{cursor:pointer}button:focus-visible,input:focus-visible,select:focus-visible,summary:focus-visible{outline:2px solid #1268a5;outline-offset:2px}
.downloads{display:flex;gap:16px;flex-wrap:wrap}.layout{display:grid;grid-template-columns:240px minmax(0,1fr);max-width:1600px;margin:auto}
aside{background:#f6f7f8;border-right:1px solid #d9dde2;padding:18px 12px}aside label{display:block;font-weight:600;margin-bottom:8px}input{width:100%;padding:8px;border:1px solid #b5bec7;border-radius:4px;background:#fff;margin-bottom:12px}
#candidates{display:grid;gap:2px}.candidate{border:0;border-left:3px solid transparent;background:transparent;text-align:left;padding:10px;min-width:0;overflow-wrap:anywhere}.candidate[aria-pressed=true]{background:#e6f1fa;border-left-color:#1268a5}.candidate strong,.candidate small{display:block}.candidate small{margin-top:3px}.candidate[hidden]{display:none}
main{padding:22px 28px;min-width:0}.source-top{display:flex;align-items:flex-start;gap:12px;justify-content:space-between}.tag{display:inline-block;font-size:12px;background:#edf1f4;padding:3px 7px;border-radius:3px;white-space:nowrap}.primary{color:#1268a5;background:#e6f1fa}
.metrics{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:16px;margin:20px 0;padding:16px 0;border-top:1px solid #e0e4e8;border-bottom:1px solid #e0e4e8}.metric span{display:block;color:#59636d;font-size:12px}.metric strong{display:block;font-size:21px;font-weight:600;font-variant-numeric:tabular-nums;overflow-wrap:anywhere}.increase{color:#b53e20}
.scope{display:flex;gap:10px 24px;flex-wrap:wrap;margin-bottom:8px}.scope strong{font-variant-numeric:tabular-nums}.limit{font-size:12px;color:#59636d;border-left:3px solid #adb5bd;padding-left:10px;margin:12px 0}.warning{color:#845310;background:#fff5df;padding:9px 12px;border-radius:3px}.boundary{color:#a63124;background:#fdf0ed;padding:10px 12px}
.controls{display:grid;grid-template-columns:130px minmax(0,1fr);gap:14px;margin:22px 0 12px}.controls label{display:block;font-size:12px;color:#59636d;margin-bottom:5px}select{width:100%;min-width:0;padding:8px;border:1px solid #b5bec7;border-radius:4px;background:#fff}
details{border-top:1px solid #d9dde2;margin-top:20px;padding-top:12px}summary{cursor:pointer;font-weight:600;overflow-wrap:anywhere}.sentence{font-size:15px;margin:12px 0;overflow-wrap:anywhere}.status{font-size:12px;color:#386b47}.status.limited{color:#845310}.status.broken{color:#a63124}
.flow{list-style:none;margin:16px 0 0;padding:0}.stage{display:grid;grid-template-columns:100px 22px minmax(0,1fr);gap:12px;position:relative;min-width:0}.rank{padding-top:15px;font-weight:600;overflow-wrap:anywhere}.rank small{display:block;font-weight:400}.rail{position:relative}.rail:before{content:"";position:absolute;top:23px;left:7px;width:9px;height:9px;background:#9aa4ad;border-radius:50%}.rail:after{content:"";position:absolute;left:11px;top:32px;bottom:0;width:1px;background:#c8ced4}.stage:not(:last-child) .stage-content:after{content:"";position:absolute;left:118px;bottom:0;border-left:4px solid transparent;border-right:4px solid transparent;border-top:6px solid #9aa4ad}
.stage:last-child .rail:after{display:none}.stage-content{padding:12px 0 18px;min-width:0;border-bottom:1px solid #edf0f2}.stage:last-child .stage-content{border-bottom:0}.stage-head{display:flex;gap:10px;align-items:baseline;flex-wrap:wrap}.stage-head strong{font-size:15px;overflow-wrap:anywhere}.role{font-size:12px;color:#59636d}.node-source .rail:before{background:#c04a2b}.node-source .role{color:#b53e20}.node-record .rail:before{background:#397453}.node-record .role{color:#397453}.node-wait .rail:before{background:#bf861a}.node-wait .role{color:#845310}.fold .stage-content{color:#59636d}.node-metrics{display:flex;gap:5px 20px;flex-wrap:wrap;margin:6px 0;font-variant-numeric:tabular-nums}.incoming{font-size:12px;color:#59636d;margin-bottom:4px}.node-meta{font-size:12px;color:#59636d;overflow-wrap:anywhere}.timing-warning{color:#845310;font-size:12px}.host-anchor{border-left:3px dashed #aeb8c1;padding-left:10px;font-size:12px;color:#59636d;margin:14px 0}
.table-wrap{overflow-x:auto;margin:12px 0}table{border-collapse:collapse;width:100%;font-size:12px;text-align:left}th,td{border-bottom:1px solid #e0e4e8;padding:8px;vertical-align:top}th{color:#59636d;font-weight:600;background:#f8f9fa}td{overflow-wrap:anywhere}.evidence-table{min-width:900px}.wait-table{min-width:650px}.evidence-table td:first-child{width:45px}.evidence-table td:nth-child(2){min-width:195px}.evidence-table code{font-size:11px}.table-button{background:none;border:0;color:#1268a5;padding:2px 0;text-decoration:underline}.empty{padding:28px 0;color:#59636d}footer{margin-top:24px;color:#59636d;font-size:12px}.empty-result{padding:24px;max-width:900px}
@media(max-width:900px){.layout{grid-template-columns:200px minmax(0,1fr)}main{padding:20px}.metrics{grid-template-columns:repeat(2,minmax(0,1fr))}.metric strong{font-size:19px}}
@media(max-width:640px){header{padding:16px}.layout{display:block}aside{border-right:0;border-bottom:1px solid #d9dde2;padding:14px 16px}#candidates{max-height:190px;overflow:auto}.candidate{padding:8px}main{padding:18px 16px}.controls{grid-template-columns:1fr}.stage{grid-template-columns:60px 16px minmax(0,1fr);gap:8px}.stage:not(:last-child) .stage-content:after{left:76px}.rail:before{left:3px}.rail:after{left:7px}.metrics{gap:12px}.source-top{flex-wrap:wrap}select,input{font-size:16px}}
@media print{aside,.downloads,.controls{display:none}.layout{display:block}main{padding:10px}details{break-inside:avoid}}
</style></head><body>
<header><div><h1>异常传播诊断</h1><div id="report-counts" class="muted"></div></div>
<nav class="downloads" aria-label="诊断数据"><a href="report.json">完整 JSON</a><a href="chains.csv">分支 CSV</a><a href="steps.csv">逐跳 CSV</a><a href="chains.md">文字报告</a></nav></header>
<div class="layout" id="layout"><aside><label for="search">候选源头</label><input id="search" type="search" placeholder="Rank / iter / 任务名" autocomplete="off"><nav id="candidates" aria-label="候选源头列表"></nav><p id="no-matches" class="muted" hidden>没有匹配的候选</p></aside>
<main id="main"><section aria-labelledby="source-title"><div class="source-top"><div><h2 id="source-title"></h2><p id="source-location"></p><p id="source-coordinate" class="muted"></p></div><span id="primary-tag" class="tag"></span></div>
<div id="source-metrics" class="metrics"></div><div id="scope" class="scope"></div><p id="source-limit" class="limit"></p><p id="truncation" class="warning" hidden></p></section>
<div class="controls"><div><label for="rank-filter">目标 Rank</label><select id="rank-filter"></select></div><div><label for="branch-select">等待分支</label><select id="branch-select"></select></div></div>
<section id="chain-panel" aria-labelledby="chain-title"><h3 id="chain-title">源头到等待的路径</h3><span id="chain-status" class="status"></span><p id="chain-sentence" class="sentence"></p><p id="host-anchor" class="host-anchor" hidden>Host 区间与下方设备 Record 是观测关联，不是新增的 Host → 设备依赖边。</p><ol id="flow" class="flow" aria-label="源头到目标 Wait 的有序依赖路径"></ol><div id="boundaries"></div>
<details id="evidence"><summary>完整逐跳证据 <span id="edge-count"></span></summary><div class="table-wrap"><table class="evidence-table"><thead><tr><th>步骤</th><th>任务定位 / 图节点</th><th>任务耗时 / 参考均值 / 增量</th><th>进入此任务的依赖证据</th></tr></thead><tbody id="evidence-rows"></tbody></table></div><p id="time-origins" class="node-meta"></p></details></section>
<details id="wait-details"><summary>关联 Wait 明细 <span id="wait-count"></span></summary><div class="table-wrap"><table class="wait-table"><thead><tr><th>Rank / stream / task</th><th>Wait</th><th>前5轮均值</th><th>当前耗时</th><th>增量</th><th>路径状态</th></tr></thead><tbody id="wait-rows"></tbody></table></div></details>
<details id="limitations"><summary>诊断边界与关键路径影响</summary><p id="impact"></p><p>候选源头沿已报告的真实依赖关联到慢 Wait，不等于已证明物理故障类型，也不代表该 Wait 的全部增量由此源头造成。多个并发 Wait 的增量不能相加为整个 workload 的损失。</p><p>这里只展开分析器已经报告的路径，不穷尽全部下游。缺边不补边；跨节点时钟未校准时不计算全局时差或全局关键路径。</p><p>参考为同一次运行前5个正式 iteration 的同定位任务均值，不是外部 baseline。</p></details>
<footer>候选排序保持诊断器原序；不使用异常注入位置生成或筛选传播路径。</footer></main></div>
<script id="propagation-data" type="application/json">__MODEL__</script><script>
"use strict";
const model=JSON.parse(document.getElementById("propagation-data").textContent);
const $=id=>document.getElementById(id);
const esc=value=>String(value??"?").replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
let selected=model.candidates.findIndex(root=>root.primary);if(selected<0)selected=0;
let activeBranch=0;
const target=chain=>model.nodes[chain.target_wait_graph_id];
const edgeLabel=hop=>hop.kind==="direct_stream_order_observed"?"同流顺序":hop.kind.includes("notify_sync")?"Record → Wait 通知配对":hop.kind;
const metric=(label,value,extra="")=>`<div class="metric"><span>${esc(label)}</span><strong class="${extra}">${esc(value)}</strong></div>`;
$("report-counts").textContent=`${model.summary.candidate_count} 个候选源头 · ${model.summary.chain_count} 条已报告路径 · ${model.summary.unique_target_wait_count} 个不同目标 Wait`;
function renderNavigation(){
  $("candidates").innerHTML=model.candidates.map((root,i)=>`<button type="button" class="candidate" data-root="${i}" aria-pressed="${i===selected}"><strong>候选 ${root.candidate_rank}${root.primary?" · 主候选":""} · Rank ${esc(root.source.user_rank)}</strong><span>${esc(root.source_label)}</span><small>iter ${esc(root.source.iteration)} · ${esc(root.delta)} · ${esc(root.factor)}</small></button>`).join("");
  applySearch();
}
function applySearch(){
  const query=$("search").value.trim().toLowerCase();let count=0;
  document.querySelectorAll("[data-root]").forEach(button=>{const root=model.candidates[Number(button.dataset.root)];button.hidden=!`${root.source_location} ${root.coordinate} ${root.source_label} ${root.source.iteration}`.toLowerCase().includes(query);if(!button.hidden)count++;});
  $("no-matches").hidden=count>0;
}
function renderRoot(){
  const root=model.candidates[selected];activeBranch=0;
  $("source-title").textContent=`候选 ${root.candidate_rank} · ${root.source_label}`;
  $("source-location").textContent=root.source_location;
  $("source-coordinate").textContent=`${root.coordinate} · ${root.source.event||root.source_label} · 参考轮次 ${(root.source.reference_iterations||[]).join(", ")||"未知"}`;
  $("primary-tag").textContent=root.primary?"主候选":"其他候选";$("primary-tag").className=`tag${root.primary?" primary":""}`;
  $("source-metrics").innerHTML=metric("前5轮均值",root.reference)+metric("当前耗时",root.duration)+metric("耗时增量",root.delta,"increase")+metric("慢化倍数",root.factor);
  const complete=root.chains.filter(c=>c.path_complete).length;
  $("scope").innerHTML=`<span>关联 Wait <strong>${root.chains.length}</strong></span><span>已连通路径 <strong>${complete}</strong></span><span>目标 Rank <strong>${esc(root.wait_ranks.join(" / ")||"无")}</strong></span>`;
  $("source-limit").textContent=`物理原因：${root.source.physical_cause==="unknown"||!root.source.physical_cause?"尚未确定":root.source.physical_cause}。路径连通与任务变慢是观测证据，不等于源头独占的完成时间损失。`;
  const truncated=root.source.traversal_truncated||root.source.other_backtrace_branches_truncated;
  $("truncation").hidden=!truncated;$("truncation").textContent="分析器的回溯存在截断，当前分支列表并非完整影响范围。";
  $("rank-filter").innerHTML='<option value="all">全部 Rank</option>'+root.wait_ranks.map(rank=>`<option value="${esc(rank)}">Rank ${esc(rank)}</option>`).join("");
  $("rank-filter").disabled=!root.chains.length;
  $("impact").textContent=`该候选的本地关键路径模型收益：${root.model_gain}（${root.source.impact_status||"未计算"}）。这是独立的局部模型指标，不是全局 workload 的实测收益。`;
  $("wait-count").textContent=`（${root.chains.length}）`;
  $("wait-rows").innerHTML=root.chains.map((chain,i)=>{const wait=target(chain);return `<tr><td><button class="table-button" data-branch="${i}">${wait?`Rank ${esc(wait.user_rank)} / ${esc(wait.stream_id)} / ${esc(wait.task_id)}`:"端点缺失"}</button></td><td>${esc(wait?.event||"Wait")}</td><td>${esc(wait?.reference||"不可比")}</td><td>${esc(wait?.duration||"未知")}</td><td>${esc(wait?.delta||"不可比")}</td><td>${esc(chain.status_label)}</td></tr>`;}).join("");
  renderBranches();renderNavigation();
}
function renderBranches(){
  const root=model.candidates[selected], rank=$("rank-filter").value;
  const visible=root.chains.map((chain,i)=>({chain,i})).filter(({chain})=>rank==="all"||String(target(chain)?.user_rank)===rank);
  $("branch-select").innerHTML=visible.map(({chain,i})=>{const wait=target(chain);return `<option value="${i}">分支 ${i+1} · Rank ${esc(wait?.user_rank)} · ${esc(wait?.event||"Wait")} · 增量 ${esc(wait?.delta||"不可比")}</option>`;}).join("");
  $("branch-select").disabled=!visible.length;$("chain-panel").hidden=!visible.length;
  if(!visible.length){$("scope").insertAdjacentHTML("beforeend",'<span class="muted">没有已报告的下游路径</span>');return;}
  activeBranch=visible[0].i;renderChain();
}
function renderChain(){
  const root=model.candidates[selected],chain=root.chains[activeBranch];$("branch-select").value=String(activeBranch);
  $("chain-status").textContent=chain.status_label;$("chain-status").className=`status${!chain.path_complete?" broken":chain.timing_warnings.length?" limited":""}`;
  $("chain-sentence").textContent=chain.sentence;$("host-anchor").hidden=root.anchor_meaning!=="observed_device_anchor_only";
  $("flow").innerHTML=chain.segments.map(segment=>{
    const node=model.nodes[segment.node_ids[0]],hop=segment.position?chain.hops[segment.position-1]:null;
    const incoming=hop?`<div class="incoming">${esc(edgeLabel(hop))} · ${esc(hop.confidence)}</div>`:"";
    if(segment.kind==="group")return `<li class="stage fold"><div class="rank">Rank ${esc(node.user_rank)}</div><div class="rail"></div><div class="stage-content">${incoming}<strong>同流推进 · ${segment.node_ids.length} 个中间任务</strong><div class="node-meta">${esc(node.node_id.split("/").pop())} · stream ${esc(node.stream_id)} · observed</div></div></li>`;
    const isSource=segment.position===0&&root.anchor_meaning!=="observed_device_anchor_only";
    const kind=isSource?"source":node.task_kind==="notify_record"?"record":node.task_kind==="notify_wait"?"wait":"task";
    const role=isSource?"慢源头候选":segment.position===0&&root.anchor_meaning==="observed_device_anchor_only"?"设备 Record 锚点":kind==="record"?"发送通知 Record":kind==="wait"?"等待通知 Wait":"中间任务";
    const warning=hop&&chain.timing_warnings.includes(hop.edge_id)?`<div class="timing-warning">${esc(model.timing_labels[hop.timing_status]||hop.timing_status)}</div>`:"";
    return `<li class="stage node-${kind}" data-node="${esc(node.graph_id)}"><div class="rank">Rank ${esc(node.user_rank)}<small>${esc(node.node_id.split("/").pop())}</small></div><div class="rail"></div><div class="stage-content">${incoming}<div class="stage-head"><span class="role">${role}</span><strong>${esc(node.event_label)}</strong></div><div class="node-metrics"><span>当前 <b>${esc(node.duration)}</b></span><span>参考 ${esc(node.reference)}</span><span class="${node.comparison.duration_slow?"increase":""}">增量 ${esc(node.delta)}</span></div><div class="node-meta">${esc(node.event||node.task_kind)} · stream ${esc(node.stream_id)} · task ${esc(node.task_id)} · ${esc(node.coordinate)}</div>${warning}</div></li>`;
  }).join("");
  $("boundaries").innerHTML=chain.boundaries.map(boundary=>`<p class="boundary">证据断点：${esc(model.boundary_labels[boundary.reason]||boundary.reason)}<br><code>${esc(boundary.edge_id||boundary.graph_id||"")}</code></p>`).join("");
  $("edge-count").textContent=`（${chain.node_ids.length} 个任务 / ${chain.edge_ids.length} 条边）`;
  $("evidence-rows").innerHTML=chain.node_ids.map((id,i)=>{const node=model.nodes[id],hop=i?chain.hops[i-1]:null;return `<tr><td>${i+1}</td><td>${esc(node.location)}<br>${esc(node.event||node.task_kind)}<br><code>${esc(id)}</code><br><small>${esc(node.coordinate)}</small><br><small>节点内相对时间 ${esc(node.relative)}</small><br><code>${esc(node.start_ns)} – ${esc(node.stop_ns)} ns</code></td><td>${esc(node.duration)}<br>${esc(node.reference)}<br>${esc(node.delta)}</td><td>${hop?`${esc(edgeLabel(hop))} · ${esc(hop.confidence)}<br><code>${esc(hop.edge_id)}</code><br>${esc(model.timing_labels[hop.timing_status]||hop.timing_status)}<br><small>${esc(hop.reason)}</small>`:"源头设备锚点"}</td></tr>`;}).join("");
  const involved=[...new Set(chain.node_ids.map(id=>model.nodes[id].node_id))];
  $("time-origins").textContent="相对时间仅在各节点内部计算；起点为本报告该节点最早证据任务，不是 iteration 起点。"+involved.map(node=>`${node}: ${model.origins[node]} ns`).join("；");
}
$("candidates").addEventListener("click",event=>{const button=event.target.closest("[data-root]");if(button){selected=Number(button.dataset.root);renderRoot();}});
$("search").addEventListener("input",applySearch);
$("rank-filter").addEventListener("change",renderBranches);
$("branch-select").addEventListener("change",()=>{activeBranch=Number($("branch-select").value);renderChain();});
$("wait-rows").addEventListener("click",event=>{const button=event.target.closest("[data-branch]");if(button){$("rank-filter").value="all";renderBranches();activeBranch=Number(button.dataset.branch);renderChain();$("chain-panel").scrollIntoView({block:"start",behavior:"smooth"});}});
if(model.candidates.length){renderRoot();}else{$("layout").innerHTML='<div class="empty-result"><h2>未输出候选根因</h2><p>本报告没有可展开的源头传播链。这不等于 workload 没有异常；慢 Wait 是否尚未定位，需查看原诊断结果和覆盖率。</p></div>';}
</script></body></html>
"""
