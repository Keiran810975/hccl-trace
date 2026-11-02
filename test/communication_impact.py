"""Post-diagnosis communication impact audit; private truth never enters diagnosis."""
from __future__ import annotations

import argparse
from collections import Counter
import csv
from decimal import Decimal
import json
from pathlib import Path

from hccl.tools.diagnosis.wait_backtrace import WORK_KINDS


def boolean(value):
    if value not in (True, False, "True", "False"):
        raise ValueError("expected an explicit comparison boolean")
    return value in (True, "True")


def intersects(item, windows):
    return any(item["node_id"] == w["node_id"] and int(item["user_rank"]) == w["user_rank"]
               and min(int(item["observed_stop_ns"]), w["stop_ns"]) >
               max(int(item["observed_start_ns"]), w["start_ns"]) for w in windows)


def assess(tasks, report, evaluation):
    if not report["quality"]["pipeline_passed"] or not evaluation["pipeline_passed"]:
        raise ValueError("impact assessment requires a complete diagnosis and independent evaluation")
    windows = evaluation["windows"]
    counters, slow = Counter(), []
    for item in tasks:
        if (item.get("task_domain") != "hccl_internal" or item.get("stage") != "measured"
                or not intersects(item, windows)):
            continue
        kind = item["task_kind"]
        counters["overlapping_" + kind] += 1
        if int(item["reference_count"]) != 5:
            counters["incomparable_" + item["comparison_status"]] += 1
            continue
        counters["comparable_" + kind] += 1
        if not boolean(item["duration_slow"]):
            continue
        counters["slow_" + kind] += 1
        if kind in WORK_KINDS:
            slow.append({k: item.get(k) for k in (
                "graph_id", "node_id", "user_rank", "device_id", "stream_id", "task_id", "iteration",
                "operation_scope", "group_id", "call_site", "phase", "step", "event", "task_kind",
                "observed_start_ns", "observed_stop_ns", "duration_ns", "reference_mean_ns", "delta_ns", "slowdown_factor")})
    slow.sort(key=lambda row: (-Decimal(row["delta_ns"]), row["graph_id"]))
    hits = [c for c in report["candidates"] if intersects(c, windows)]
    if {c["id"] for c in hits} != set(evaluation["hit_candidate_ids"]):
        raise ValueError("independent candidate overlap evaluation disagrees")
    linked = [c for c in hits if c.get("evidence_supported") and c.get("chain_ids")]
    return dict(schema_version=1, case_id=evaluation["case_id"],
        injection_kind=evaluation["injection"]["kind"], actual_windows=windows,
        status="communication_effect_observed" if slow else "no_measurable_intrinsic_communication_slowdown",
        overlapping_communication_facts=dict(counters), slow_execution_count=len(slow), slow_executions=slow,
        localization=dict(candidate_count=len(report["candidates"]), hit_count=len(hits),
                          primary_hit=evaluation["primary_hit"], propagation_supported_hit_ids=[c["id"] for c in linked]),
        physical_cause_proven=False, rdma_hardware_completion_proven=False,
        limits=["Overlap and measured growth establish association, not the physical cause.",
                "Slow Waits and RDMA doorbell durations are not counted as intrinsic work execution slowdown.",
                "A missing/incomparable duration is not proof that the injection had no effect.",
                "This evaluator may read private truth only after diagnosis has completed; it cannot add candidates or edges."])


def comparison_path(root, report):
    run_id = report["run_id"]
    if not isinstance(run_id, str) or not run_id or run_id in {".", ".."} or "/" in run_id or "\\" in run_id:
        raise ValueError("report run_id must be one path component")
    path = root / "report.debug" / "analysis" / run_id / "rolling" / "task_comparison.csv"
    if not path.is_file():
        raise ValueError("missing task comparison for report run_id: " + str(path))
    return path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    args = parser.parse_args()
    root = args.root
    report = json.loads((root / "report/root_causes.json").read_text())
    evaluation = json.loads((root / "evaluation.json").read_text())
    with comparison_path(root, report).open(encoding="utf-8-sig", newline="") as stream:
        result = assess(csv.DictReader(stream), report, evaluation)
    output = root / "communication-impact.json"
    with output.open("x", encoding="utf-8") as stream:
        stream.write(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({k: v for k, v in result.items() if k != "slow_executions"}))


if __name__ == "__main__":
    main()
