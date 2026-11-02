"""Independent post-diagnosis audit of the two retained short-copy captures."""
from __future__ import annotations

import argparse
from collections import Counter
from contextlib import closing
from decimal import Decimal
import json
from pathlib import Path
import sqlite3

from hccl.tools.diagnosis import analyze_waits as waits
from hccl.tools.diagnosis import visualize_dependency_graph as graph
from hccl.tools.diagnosis.clock_alignment import models_from_report


def communication_fact(facts, row):
    found = []
    for path in (facts / "capture").rglob("msprof_*.db"):
        with closing(sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)) as db:
            db.row_factory = sqlite3.Row
            query = """SELECT t.globalTaskId,t.startNs,t.endNs,c.srcRank,c.dstRank,c.size,
                c.transportType,s.value AS subtype FROM TASK t JOIN COMMUNICATION_TASK_INFO c
                ON c.globalTaskId=t.globalTaskId LEFT JOIN STRING_IDS s ON s.id=c.taskType
                WHERE t.deviceId=? AND t.streamId=? AND t.taskId=? AND t.startNs=?"""
            for item in db.execute(query, (row["_device_id"], row["_stream_id"], row["_task_id"], waits.ns(row, "start"))):
                value = dict(item)
                if str(value["globalTaskId"]) + ":" + str(value["startNs"]) != row["profiler_task_index"]:
                    raise ValueError("physical task index differs from original DB")
                value.update(db=str(path.relative_to(facts)), semantic_peer_rank=row["_peer_rank"],
                             executing_rank=row["_user_rank"], physical_fault_owner_proven=False,
                             rank_fields_are_not_assumed_data_flow_direction=True)
                found.append(value)
    if len(found) > 1:
        raise ValueError("multiple raw DB communication records for one physical task")
    return found[0] if found else None


def audit(facts, replay):
    analysis = replay / "analysis"
    report = json.loads((analysis / "rolling/report.json").read_text())
    public = json.loads((replay / "report/root_causes.json").read_text())
    activity = json.loads((facts / "numerics/copy-burst.json").read_text())
    rows = graph.read_graph_artifact_nodes(analysis / "dep_graph_nodes.csv")
    clocks = models_from_report(json.loads((analysis / "clock_alignment.json").read_text()))
    lookup = {r["_graph_id"]: r for r in rows}
    targets = [t for t in report["tasks"] if t["stage"] == "measured" and t["iteration"] == 10 and t["user_rank"] == 4]
    scopes = {t["operation_scope"] for t in targets}
    if len(scopes) != 1:
        raise ValueError("selected public iteration is not a unique collective")
    scope = scopes.pop()
    node = targets[0]["node_id"]
    copies = [r for r in rows if r["_node_id"] == node and r["_user_rank"] == 4
              and not r.get("_operation_scope") and r.get("profiler_task_kind") == "sdma"]
    if len(copies) != 2 or len({r["_stream_id"] for r in copies}) != 1:
        raise ValueError("warmup and injected background SDMA tasks are not uniquely observable")
    copy = sorted(copies, key=lambda r: waits.ns(r, "start"))[-1]
    def raw(row, side):
        return waits.ns(row, side) - clocks[(row["_node_id"], row["_device_id"])].profiler_to_raw_offset_ns
    start, stop = raw(copy, "start"), raw(copy, "stop")
    # No nearest-time task matching. This evaluator checks the unique owned stream
    # against an independently bound iteration after the diagnosis is finished.
    current = [lookup[t["graph_id"]] for t in targets]
    first, last = min(raw(r, "start") for r in current), max(raw(r, "stop") for r in current)
    work = [t for t in report["tasks"] if t["operation_scope"] == scope and t["task_kind"] in {"sdma", "reduce_inline"}
            and t["reference_count"] == 5]
    slowed = []
    for task in work:
        if not task["duration_slow"]:
            continue
        row = lookup[task["graph_id"]]
        value = {k: task.get(k) for k in ("graph_id", "node_id", "user_rank", "stream_id", "task_id", "phase", "step", "event",
                 "duration_ns", "reference_mean_ns", "delta_ns", "slowdown_factor")}
        value["overlap_with_background_ns"] = max(0, min(raw(row, "stop"), stop) - max(raw(row, "start"), start)) if row["_node_id"] == node else None
        value["original_db_communication_fact"] = communication_fact(facts, row) if row["_node_id"] == node else None
        slowed.append(value)
    evaluated = []
    for candidate in public["candidates"]:
        row = lookup[candidate["graph_id"]]
        same_node = row["_node_id"] == node
        overlap = max(0, min(raw(row, "stop"), stop) - max(raw(row, "start"), start)) if same_node else 0
        evaluated.append(dict(candidate_id=candidate["id"], rank=candidate["user_rank"], overlap_ns=overlap,
                              original_same_rank_rule_hit=bool(overlap and same_node and row["_user_rank"] == 4)))
    target_factors = [Decimal(t["slowdown_factor"]) for t in work if t["user_rank"] == 4 and t["slowdown_factor"] is not None]
    return dict(analysis_used_injection_truth=False, evaluator_used_truth_after_diagnosis=True,
        evidence_class="exploratory; outcome-informed placement correction retained",
        activity=activity, background_graph_id=copy["_graph_id"], background_stream=copy["_stream_id"],
        background_task=copy["_task_id"], device_copy_duration_ns=stop-start,
        collective_interval_raw_ns=[first, last], collective_duration_ns=last-first,
        copy_interval_raw_ns=[start, stop], actual_overlap_ns=max(0,min(last,stop)-max(first,start)),
        short_overlap_contract_passed=first <= start < stop <= last,
        host_envelope_is_not_device_duration=True,
        target_rank_max_work_factor=str(max(target_factors)) if target_factors else None,
        selected_iteration_slow_work=slowed, internal_candidate_count=len(public["candidates"]),
        primary_candidate_id=public["primary_candidate_id"], candidate_evaluation=evaluated,
        original_same_rank_rule_hits=sum(c["original_same_rank_rule_hit"] for c in evaluated),
        boundary_counts=report["coverage"]["boundary_reason_counts"],
        dependency_timing_counts=dict(Counter(c["timing_status"] for t in report["wait_backtraces"] for c in t["release_checks"])),
        physical_injection_causation_proven=False)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--peer-facts", required=True, type=Path)
    parser.add_argument("--replay", required=True, type=Path)
    args = parser.parse_args()
    result = audit(args.peer_facts, args.replay)
    (args.replay / "independent-audit.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))
