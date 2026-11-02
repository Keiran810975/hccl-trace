#!/usr/bin/env python3
"""Independent overlap evaluation, only after a region diagnosis has been sealed."""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path


def evaluate(report_path, truth_path, node_id, rank):
    seal = json.loads(report_path.with_name("sealed.json").read_text())
    data = report_path.read_bytes()
    if hashlib.sha256(data).hexdigest() != seal["report_sha256"] or seal["truth_accessed"] is not False:
        raise ValueError("diagnosis must be sealed before independent truth evaluation")
    report = json.loads(data)
    truth = json.loads(truth_path.read_text())["strong_copy"]
    begin, end = truth["profiler_host_envelope_ns"]
    records = []
    for candidate in report["candidates"]:
        overlap = max(0, min(end, candidate["observed_stop_ns"]) - max(begin, candidate["observed_start_ns"]))
        records.append(dict(candidate_id=candidate["candidate_id"], graph_id=candidate["graph_id"],
            status=candidate["status"], node_id=candidate["node_id"], rank=candidate["user_rank"],
            stream=candidate["stream_id"], task=candidate["task_id"], iteration=candidate["iteration"],
            task_kind=candidate["task_kind"], overlap_ns=overlap,
            hit=candidate["node_id"] == node_id and candidate["user_rank"] == rank and overlap > 0))
    def count(values):
        hits = sum(c["hit"] for c in values)
        return dict(hits=hits, total=len(values), precision=hits/len(values) if values else None)
    return dict(criterion="same_node_rank_and_strict_positive_actual_activity_envelope_overlap",
        injection_node=node_id, injection_rank=rank, envelope_ns=[begin, end],
        envelope_is_hardware_duration=False, truth_accessed_only_by_independent_evaluator=True,
        report_sha256=seal["report_sha256"], all_candidates=count(records),
        execution_candidates=count([c for c in records if c["status"] == "unexplained_execution_growth"]),
        unexplained_wait_candidates=count([c for c in records if c["status"] == "unexplained_wait_candidate"]),
        first_candidate_hit=records[0]["hit"] if records else False,
        candidates_by_iteration=dict(Counter(c["iteration"] for c in records)), candidates=records,
        hit_source_chain_count=sum(c["source_graph_id"] in {r["graph_id"] for r in records if r["hit"]} for c in report["chains"]))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--activity-summary", type=Path, required=True)
    parser.add_argument("--node-id", required=True)
    parser.add_argument("--rank", type=int, required=True)
    args = parser.parse_args()
    report = evaluate(args.report, args.activity_summary, args.node_id, args.rank)
    target = args.report.with_name("independent-evaluation.json")
    if target.exists():
        raise ValueError("do not overwrite an earlier independent evaluation")
    target.write_text(json.dumps(report, indent=2)+"\n")
    print(json.dumps({k: v for k,v in report.items() if k != "candidates"}))


if __name__ == "__main__":
    main()
