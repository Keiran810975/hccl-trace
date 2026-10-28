#!/usr/bin/env python3
"""Retrospective symptom audit of retained HTML, NOT diagnosis or causal proof.

Private windows select the audit region only. No report, source selection,
success rate or original capture is changed. Missing full history stays missing.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import csv
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import re
from statistics import median


OP_COUNTER = re.compile(r"hcom_allReduce__\d+_(\d+)_\d+$")
STRONG = 1.5
WEAK = 1.1


def model(path):
    raw = path.read_bytes()
    value = json.JSONDecoder().raw_decode(raw.decode("utf-8").split("const model=", 1)[1])[0]
    return value, hashlib.sha256(raw).hexdigest()


def ns(node, side):
    value = Decimal(str(node["relativeStart" if side == "start" else "relativeStop"])) * 1000
    if value != value.to_integral_value():
        raise ValueError("retained timeline lacks exact local nanosecond coordinates")
    return int(value)


def copy_signature(node):
    return tuple(node[k] for k in ("rank", "algorithm", "phase", "step", "event", "semantic", "taskKind", "sizeBytes"))


def fully_inside(node, start, stop):
    return start <= ns(node, "start") and ns(node, "stop") <= stop


def kernel_medians(nodes):
    values = defaultdict(list)
    for node in nodes:
        if node["nodeKind"] == "execution" and node["taskKind"] == "kernel_mix_aic":
            values[node["rank"]].append(node["duration"])
    return {rank: dict(median_us=median(samples), count=len(samples)) for rank, samples in values.items() if samples}


def copy_ratios(nodes, start, stop):
    references = defaultdict(list)
    for node in nodes:
        if (node["nodeKind"] == "execution" and node["taskKind"] == "sdma" and
                all(node[k] for k in ("algorithm", "phase", "event")) and ns(node, "stop") <= start):
            references[copy_signature(node)].append(node["duration"])
    ratios, keys = defaultdict(list), defaultdict(set)
    for node in nodes:
        key = copy_signature(node)
        if (node["nodeKind"] == "execution" and node["taskKind"] == "sdma" and fully_inside(node, start, stop)
                and key in references and median(references[key]) > 0):
            ratios[node["rank"]].append(node["duration"] / median(references[key]))
            keys[node["rank"]].add(key)
    return {rank: dict(median_normalized_duration=median(values), active_task_count=len(values),
                       reference_cohort_count=len(keys[rank]),
                       retained_reference_task_count=sum(len(references[key]) for key in keys[rank]),
                       minimum_reference_count_per_cohort=min(len(references[key]) for key in keys[rank]))
            for rank, values in ratios.items() if values}


def delay_pairs(value, scope, target, start, stop):
    nodes = {n["id"]: n for n in value["nodes"]}
    pairs = []
    for edge in value["edges"]:
        if "notify_sync" not in edge["kind"] or edge["confidence"] != "exact":
            continue
        src, dst = nodes[edge["src"]], nodes[edge["dst"]]
        if (src["rank"] != target or dst["rank"] == target or src["operationScope"] != scope
                or dst["operationScope"] != scope or src["taskKind"] != "notify_record" or dst["taskKind"] != "notify_wait"):
            continue
        overlap = max(0, min(stop, ns(dst, "stop")) - max(start, ns(dst, "start")))
        if overlap <= 0 or ns(src, "start") < stop:
            continue
        pairs.append(dict(edge_id=edge["id"], record_id=src["id"], wait_id=dst["id"], waiting_rank=dst["rank"],
                          record_event=src["event"], wait_event=dst["event"],
                          wait_duration_ms=dst["duration"] / 1000, window_wait_overlap_ms=overlap / 1000000,
                          record_start_after_window_ms=(ns(src, "start") - stop) / 1000000,
                          endpoint_timing_compatible=ns(src, "stop") <= ns(dst, "stop")))
    return sorted(pairs, key=lambda p: (-p["window_wait_overlap_ms"], p["edge_id"]))


def anchor_history(value, config, summary, binding):
    workload = config["workload"]
    per_iteration = workload["blocks"] * len(workload["bucket_mib"])
    expected_count = per_iteration * (workload["warmup"] + workload["iters"])
    if (len(binding["ranks"]) != 4 or {r["rank"] for r in binding["ranks"]} != set(range(4))
            or any(r["call_count"] != expected_count or r["api_containment_verified"] is not True for r in binding["ranks"])):
        raise ValueError("missing historical complete public-call/DB binding acceptance")
    by_counter = {}
    for node in value["nodes"]:
        if node["nodeKind"] != "operation":
            continue
        match = OP_COUNTER.fullmatch(node["event"])
        if not match:
            raise ValueError("unknown retained foreground operation naming")
        count = int(match[1])
        scope = node["operationScope"]
        if count in by_counter and by_counter[count] != scope:
            raise ValueError("operation counter does not identify one retained scope")
        by_counter[count] = scope
    inj = config["injection"]
    expected = workload["warmup"] * per_iteration + inj["start_call"]
    if by_counter.get(expected) != summary["anchor_operation_scope"]:
        raise ValueError("named operation counter disagrees with the independently retained anchor")
    history = [i for i in range(inj["iteration"] - 5, inj["iteration"])
               if workload["warmup"] * per_iteration + i * per_iteration + inj["block"] * len(workload["bucket_mib"]) + inj["bucket"] in by_counter]
    return history


def audit_case(delivery, path, baseline_kernels):
    value, digest = model(path)
    records = delivery / "records" / path.stem
    config = json.loads((records / "injection-case.json").read_text())
    summary = json.loads((records / "case-summary.json").read_text())
    windows = json.loads((records / "injection-actual-windows.json").read_text())
    binding = json.loads((records / "binding-evidence.json").read_text())
    if not windows or any(w["actual_hit"] is not True or w["clock_domain"] != "profiler_node_ns" for w in windows):
        raise ValueError("no verified actual injection window")
    origin = summary["chart_origin_ns"]
    start, stop = min(w["start_ns"] for w in windows) - origin, max(w["stop_ns"] for w in windows) - origin
    targets = sorted({rank for w in windows for rank in w["target_ranks"]})
    inj = config["injection"]
    history = anchor_history(value, config, summary, binding)
    numerical = [json.loads((records / "numerics-rank-{}.json".format(r)).read_text()) for r in range(4)]
    if any(r["status"] != "passed" or r["max_error"] != 0 for r in numerical):
        raise ValueError("foreground numerical gate failed")
    active = [n for n in value["nodes"] if n["nodeKind"] == "execution" and fully_inside(n, start, stop)]
    kernels = kernel_medians(active)
    peer_kernels = [r["median_us"] for rank, r in kernels.items() if rank not in targets]
    kernel_ratios = {}
    for rank in targets:
        if rank in kernels and rank in baseline_kernels and peer_kernels:
            kernel_ratios[rank] = dict(kernels[rank], baseline_ratio=kernels[rank]["median_us"] / baseline_kernels[rank]["median_us"],
                                      peer_ratio=kernels[rank]["median_us"] / median(peer_kernels))
    copies = copy_ratios(value["nodes"], start, stop)
    pairs = delay_pairs(value, summary["anchor_operation_scope"], inj["target_rank"], start, stop) if inj["kind"] == "progress_delay" else []
    background = None
    if inj["kind"] != "progress_delay":
        background = json.loads((records / "injection-result.json").read_text())
        if background["operations"] <= 0 or background["max_error"] != 0:
            raise ValueError("no successful actual background execution")
    if inj["kind"] == "progress_delay":
        strength = "clear_symptom" if pairs else "device_effect_unconfirmed"
        metric = dict(name="paired_peer_wait_overlaps_host_delay", pairs=len(pairs),
                      longest_wait_ms=max((p["wait_duration_ms"] for p in pairs), default=None))
    elif inj["kind"] == "communication_contention":
        ratio = max((copies[r]["median_normalized_duration"] for r in targets if r in copies), default=None)
        strength = "clear_symptom" if ratio is not None and ratio >= STRONG else "weak_symptom" if ratio is not None and ratio >= WEAK else "device_effect_unconfirmed"
        metric = dict(name="target_copy_vs_retained_pre_window_cohorts", ratio=ratio)
    else:
        ratio = max((v["peer_ratio"] for v in kernel_ratios.values()), default=None)
        baseline_ratio = max((v["baseline_ratio"] for v in kernel_ratios.values()), default=None)
        strength = ("clear_symptom" if ratio is not None and baseline_ratio is not None and min(ratio, baseline_ratio) >= STRONG
                    else "weak_symptom" if ratio is not None and ratio >= WEAK else "device_effect_unconfirmed")
        metric = dict(name="target_foreground_kernel_mix_aic_vs_peer_distribution", ratio=ratio, baseline_ratio=baseline_ratio)
    after = [n for n in value["nodes"] if n["taskKind"] == "notify_wait" and ns(n, "start") >= stop]
    longest_after = max(after, key=lambda n: n["duration"]) if after else None
    after_evidence = (dict(graph_id=longest_after["id"], rank=longest_after["rank"], duration_ms=longest_after["duration"] / 1000,
                           start_after_window_ms=(ns(longest_after, "start") - stop) / 1000000) if longest_after else None)
    return dict(case_id=path.stem, kind=inj["kind"], target_ranks=targets, injection=inj,
                injection_executed=True, actual_window_ms=(stop - start) / 1000000,
                chart_start_ms=start / 1000000, chart_stop_ms=stop / 1000000,
                evidence_grade=strength, metric=metric, baseline_kernel_medians=baseline_kernels,
                target_kernel_ratios=kernel_ratios, per_rank_pre_window_copy_ratios=copies,
                overlapping_exact_notify_pairs=pairs, post_window_wait=after_evidence,
                background=background, retained_previous_five_anchor_iterations=history,
                complete_previous_five_history_retained=len(history) == 5,
                avg_step_ms_by_rank={r["rank"]: r["avg_step_ms"] for r in numerical},
                original_html=str(path.resolve()), original_html_sha256=digest,
                causal_effect_proved=False, original_diagnosis_changed=False)


def run(delivery, output):
    output.mkdir(parents=True, exist_ok=False)
    baseline, baseline_sha = model(delivery / "html/single-910c-4r-normal.html")
    baseline_kernels = kernel_medians(baseline["nodes"])
    cases = [audit_case(delivery, path, baseline_kernels) for path in sorted((delivery / "html").glob("*.html"))
             if path.stem != "single-910c-4r-normal"]
    if len(cases) != 20:
        raise ValueError("expected exactly the twenty original anomaly cases")
    report = dict(schema_version=1, analysis_kind="retrospective_retained_symptom_audit_not_diagnosis",
                  all_injections_executed=all(c["injection_executed"] for c in cases),
                  evidence_grade_counts=dict(Counter(c["evidence_grade"] for c in cases)), cases=cases,
                  baseline_sha256=baseline_sha, new_device_runs=0, original_results_changed=False,
                  screening_magnitude_factors=dict(clear=STRONG, weak=WEAK),
                  limitations=["Grades describe observed symptoms, NOT independently proved injection causation or diagnosis accuracy.",
                               "Copy references are retained pre-window same-rank semantic/type/byte cohorts, not the required preceding five same-location iterations.",
                               "Kernel comparisons are distributions of kernel_mix_aic, not precisely bound GEMM tasks or equal-shape paired samples.",
                               "The separate normal HTML is a partial recorded sample; cross-run ratios alone are confounded.",
                               "Exact Notify identity does not guarantee comparable record.stop and wait.stop; incompatible endpoints are retained and never repaired.",
                               "Some post-window waits occur while the controller may await worker shutdown; overlap/code paths alone do not prove the responsible host call.",
                               "Unconfirmed device effects do not prove no effect. Large original anomaly inputs were deleted."])
    (output / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    rows = [dict(case_id=c["case_id"], kind=c["kind"], target_ranks=";".join(map(str, c["target_ranks"])),
                 evidence_grade=c["evidence_grade"], actual_window_ms=c["actual_window_ms"],
                 metric=c["metric"]["name"], ratio=c["metric"].get("ratio"),
                 peer_wait_ms=c["metric"].get("longest_wait_ms"),
                 post_window_wait_ms=c["post_window_wait"]["duration_ms"] if c["post_window_wait"] else None,
                 post_window_wait_start_offset_ms=c["post_window_wait"]["start_after_window_ms"] if c["post_window_wait"] else None,
                 complete_previous_five_history_retained=c["complete_previous_five_history_retained"],
                 html=c["original_html"]) for c in cases]
    with (output / "cases.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    for c in cases:
        if hashlib.sha256(Path(c["original_html"]).read_bytes()).hexdigest() != c["original_html_sha256"]:
            raise ValueError("an original graph changed during the audit")
    print(json.dumps(dict(case_count=len(cases), executed=report["all_injections_executed"],
                         grades=report["evidence_grade_counts"],
                         full_history_available=sum(c["complete_previous_five_history_retained"] for c in cases),
                         post_window_wait_over_one_second=sum(c["post_window_wait"] is not None and c["post_window_wait"]["duration_ms"] > 1000 for c in cases)), indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--delivery", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    run(args.delivery.resolve(), args.output.resolve())
