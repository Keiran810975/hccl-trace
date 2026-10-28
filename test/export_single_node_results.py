#!/usr/bin/env python3
"""Package completed formal cases into 21 HTML files and auditable rate tables."""
from __future__ import annotations

import argparse
import csv
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import zipfile

try:
    from test.run_single_node_suite import write_formal_summary
    from test.single_node_random_suite import evaluate_temporal_localization
except ModuleNotFoundError:
    from run_single_node_suite import write_formal_summary
    from single_node_random_suite import evaluate_temporal_localization


def export(directory):
    state = json.loads((directory / "records/suite-state.json").read_text())
    cases = state["cases"]
    if state["status"] != "completed" or len(cases) != 21 or state["completed"] != 21:
        raise ValueError("final export requires all 21 formal runs, not a partial queue")
    counts = {kind: sum(c["injection"]["kind"] == kind for c in cases)
              for kind in ("normal", "progress_delay", "copy_contention", "communication_contention", "compute_contention")}
    if counts != {"normal": 1, "progress_delay": 5, "copy_contention": 5,
                  "communication_contention": 5, "compute_contention": 5}:
        raise ValueError("case types differ from the frozen 1+4*5 plan")
    exported, rows = [], []
    for case in cases:
        identifier = case["case_id"]
        html = directory / "html" / (identifier + ".html")
        summary = json.loads((directory / "records" / identifier / "case-summary.json").read_text())
        sha = hashlib.sha256(html.read_bytes()).hexdigest()
        if sha != summary["html_sha256"]:
            raise ValueError("HTML checksum differs for " + identifier)
        evaluation = case["temporal_evaluation"]
        if not case.get("execution_success") or not case.get("strict_diagnosis_success"):
            raise ValueError("cannot package an incomplete capture/diagnosis as a finished experiment")
        if evaluation != summary["evaluation"]:
            raise ValueError("queue and case evaluation differ for " + identifier)
        primary = case.get("primary_source") or {}
        if case["injection"]["kind"] != "normal":
            windows = json.loads((directory / "records" / identifier / "injection-actual-windows.json").read_text())
            fixed = dict(primary_source_candidate_id=evaluation["primary_source_candidate_id"],
                         root_causes=[primary] if primary else [])
            checked = evaluate_temporal_localization(fixed, windows)
            if checked != evaluation:
                raise ValueError("independent retained-window evaluation differs: " + identifier)
            for name, data in (("evaluation-input.json", fixed), ("evaluation-recheck.json", checked)):
                (directory / "records" / identifier / name).write_text(json.dumps(data, indent=2) + "\n")
        item = dict(case, retained_html="html/" + html.name)
        exported.append(item)
        interval = evaluation.get("evaluated_source_interval_ns")
        chart = ([format(Decimal(t - summary["chart_origin_ns"]) / 1000000, "f") for t in interval]
                 if interval else [])
        rows.append(dict(case_id=identifier, kind=case["injection"]["kind"], html=item["retained_html"],
                         diagnosis_success=evaluation.get("diagnosis_success"),
                         classification=evaluation.get("classification", evaluation["status"]),
                         predicted_rank=primary.get("user_rank", ""), predicted_stream=primary.get("stream_id", ""),
                         predicted_iteration_0based=primary.get("iteration", ""),
                         predicted_block_0based=primary.get("block", ""), predicted_bucket_0based=primary.get("bucket", ""),
                         predicted_phase=primary.get("phase", ""), predicted_step=primary.get("step", ""),
                         predicted_task_id=primary.get("task_id", ""),
                         predicted_chart_interval_ms="..".join(chart),
                         analysis_location=case.get("analysis_location", "server"),
                         resource_scope=case.get("resource_scope", "whole_host_idle_precheck"),
                         injection=json.dumps(case["injection"], separators=(",", ":"))))
    if len(list((directory / "html").glob("*.html"))) != 21:
        raise ValueError("deliverable HTML directory must contain exactly 21 graphs")
    write_formal_summary(directory, exported)
    with (directory / "diagnosis-results.csv").open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    rates = json.loads((directory / "success-rates.json").read_text())
    labels = dict(progress_delay="定点延迟", copy_contention="Copy资源竞争",
                  communication_contention="机内通信竞争", compute_contention="通信与计算竞争")
    lines = ["# 910C单机4 Rank正式实验", "", "完成正常组1例和四类异常各5例，共21次独立workload。", "",
             "| 异常类型 | 诊断成功 | 成功率 | 无法评判 |", "| --- | --- | --- | --- |"]
    for group in rates["groups"]:
        lines.append("| {} | {}/5 | {}% | {} |".format(labels[group["kind"]], group["correct"],
                     group["success_rate_percent"], group["not_evaluable"]))
    normal = next(c for c in cases if c["injection"]["kind"] == "normal")
    lines += ["", "## 配置与口径", "",
              "- Node0自有非特权zjy-new，runtime1/3/5/7，4 Rank。未改验签、驱动或其他容器。",
              "- Rank0/1/2/3对应runtime1/3/5/7、物理芯片9/11/13/15，即NPU4/5/6/7的chip1。",
              "- 用户已允许其他卡忙碌时继续；本队列仍要求NPU4..7整卡无外部进程且显存接近基础占用。后续实验共享主机资源，存在CPU/内存干扰风险。",
              "- 4 Block，tokens2048/hidden4096/FFN16384，BF16单组GEMM/GELU。",
              "- 每Block 64/128/256MiB FP32 SUM AllReduce，每轮12次，每Rank每轮1.75GiB collective输入。",
              "- 每例10轮预热、50轮测量，均实际采集msprof DB与HOST语义，通过严格合并和构图门禁。",
              "- 判慢取前5个正式轮次同语义位置的均值，保留1.5倍和3*MAD条件，无绝对增量下限。",
              "- 主根因由分析器先选定。同一Rank且与实际注入窗口重叠计成功，不用真值重新挑选候选。",
              "- 每类分母为5；无法评判单独列出，不冒充成功。正常组不进入四类成功率分母。",
              "- 正常组误报标记：{}；标慢{} / 可比{}。".format(normal["temporal_evaluation"]["false_alarm"],
                  normal["temporal_evaluation"]["slow_task_count"], normal["temporal_evaluation"]["compared_task_count"]),
              "", "## 图与注入位置", "",
              "- html/只有21张自包含原生依赖图，浏览器直接打开。",
              "- 图展示真实注入窗口和前后上下文，并保留主根因所在通信操作。完整50轮参与诊断，图不是全50轮总览。",
              "- 正常图选第26个正式测量轮附近。轮次/Block/桶在配置中采用0基编号。",
              "- 图上0表示该HTML中最早保留的任务或operation，不是workload起点或iteration起点。",
              "- injection-locations.csv逐条记录注入处的node/rank、图中毫秒范围和前台stream编号。",
              "- Host sleep没有设备stream。anchor_collective_stream_ids是后续目标AllReduce的实际流，不是sleep执行流。",
              "- 后台通信的两个实际端点分别记录窗口。未推断或伪造后台stream编号。",
              "- diagnosis-results.csv给出主候选、成功/失败及原因，records/保留每例摘要、图门禁与原始DB哈希。",
              "- 每个异常的evaluation-input.json与injection-actual-windows.json可供独立脚本重新评判命中；evaluation-recheck.json须与原判定完全一致。",
              "- 正常组原始采集仍保存在服务器attempts/single-910c-4r-normal；异常组已按要求清理大体积中间数据。",
              "- 正常组和Copy首例曾恢复离线处理，未因此重复已完成的workload；判慢、根因选择和评判规则未改。",
              "- 通信首例另有一次未到注入的初始化端口冲突，单独归档；隔离自己的后台端口并通过双通信组真实预检后重试，不计为一个完成样例。", ""]
    lines += ["## 处理位置", "", "采集始终在910C服务器完成。前5例在服务器分析；其余真实DB和语义日志",
              "校验哈希后交给本地同版分析器。逐例records中的回执和analysis_location记录实际位置。",
              "移动离线处理不增加workload运行次数，也不改变判慢、源头选择或窗口评判规则。", ""]
    lines += ["## 收尾核验", "", "自有负载进程已退出，目标卡已释放。正常组4份原始DB仍保留，20例异常的大型数据目录已清理。",
              "Host库及官方Device包哈希与运行前一致；证据见records/provenance/formal-postflight-final.json。", ""]
    lines += ["## HTML清单", "", "| 样例 | 根因定位 | 原生依赖图 |", "| --- | --- | --- |"]
    for case in cases:
        evaluation = case["temporal_evaluation"]
        verdict = ("正常对照：有误报候选" if case["injection"]["kind"] == "normal" and evaluation["false_alarm"] else
                   "正常对照" if case["injection"]["kind"] == "normal" else
                   "成功" if evaluation.get("diagnosis_success") is True else
                   "未命中" if evaluation.get("diagnosis_success") is False else "不可评判")
        lines.append("| {} | {} | [打开](html/{}.html) |".format(case["case_id"], verdict, case["case_id"]))
    lines += ["", "## 解释边界", "",
              "- 同Rank且时间重叠是本次约定的成功指标，不代表已证明具体物理故障类型。",
              "- D2D Copy及机内HCCL背景流实际执行，不将它们直接声称为纯SDMA瓶颈或RoCE网络拥塞。",
              "- 按要求删除了异常样例的大型原始输入；局部HTML不能替代整次采集，不能据此完整重算另一套诊断算法。", ""]
    (directory / "README.md").write_text("\n".join(lines), encoding="utf-8")
    return rates


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    parser.add_argument("--zip", type=Path)
    args = parser.parse_args()
    result = export(args.directory)
    if args.zip:
        with zipfile.ZipFile(args.zip, "x", compression=zipfile.ZIP_DEFLATED) as archive:
            for path in args.directory.rglob("*"):
                if path.is_file() and ".qa" not in path.relative_to(args.directory).parts and path.name != ".offload.lock":
                    archive.write(path, args.directory.name + "/" + str(path.relative_to(args.directory)))
    print(json.dumps(result))
