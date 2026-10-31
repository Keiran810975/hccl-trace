"""Post-diagnosis overlap evaluation; injection truth never enters the analyzer."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sqlite3
from hccl.tools.diagnosis.clock_alignment import raw_to_profiler


def evaluate(root):
    case = json.loads((root / "input/case.json").read_text())
    report = json.loads((root / "report/root_causes.json").read_text())
    if not report["quality"]["pipeline_passed"] or report["quality"]["rank_count"] != 8:
        raise ValueError("complete eight-rank diagnosis is required before evaluation")
    windows = []
    injection = case["injection"]
    owners = [] if injection["kind"] == "normal" else [injection["target_rank"]]
    if injection["kind"] == "communication_contention":
        owners.append(injection["peer_rank"])
    for rank in owners:
        node = "node0" if rank < 4 else "node3"
        data = root / ("gpt-output" if node == "node0" else "peer-preflight/gpt-output")
        runtime = json.loads((data / "runtime" / ("rank-{}.json".format(rank))).read_text())
        clocks = []
        for path in (root / "capture/nodes" / node / "msprof").rglob("msprof_*.db"):
            with sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True) as db:
                if {r[0] for r in db.execute("SELECT DISTINCT deviceId FROM TASK")} != {runtime["runtime_device_id"]}:
                    continue
            info = json.loads((path.parent / "host/start_info").read_text())
            stop_path = path.parent / "host/end_info"
            clocks.append((info, json.loads(stop_path.read_text()) if stop_path.exists() else None))
        if len(clocks) != 1:
            raise ValueError("a unique actual target-device profiler clock observation is required")
        if injection["kind"] == "progress_delay":
            rows = [json.loads(s) for s in (data / "private" / ("rank-{}.jsonl".format(rank))).read_text().splitlines()]
            starts = [r["clocks"]["raw_ns"] for r in rows if r["event"] == "injection_start"]
            stops = [r["clocks"]["raw_ns"] for r in rows if r["event"] == "injection_stop" and r.get("actual_hit")]
            if len(starts) != 1 or len(stops) != 1:
                raise ValueError("actual delay interval is missing")
            begin, end = starts[0], stops[0]
        else:
            filename = "network-result.json" if injection["kind"] == "bandwidth_limit" else "result.json"
            activity = json.loads((data / "private" / filename).read_text())
            if filename == "network-result.json":
                if not all(activity.get(k) for k in ("applied_verified", "restored_verified", "foreground_path_verified")):
                    raise ValueError("real network injection or restoration is unproven")
            elif activity.get("operations", 0) <= 0 or activity.get("max_error") != 0:
                raise ValueError("background activity did not actually execute correctly")
            begin, end = activity["started_raw_ns"], activity["finished_raw_ns"]
        if end <= begin:
            raise ValueError("actual injection interval is empty")
        start, stop = clocks[0]
        public = root / "capture/nodes" / node / "calls" / ("rank-{}.jsonl".format(rank))
        if public.is_file():
            with public.open(encoding="utf-8-sig") as source:
                header = json.loads(next((line for line in source if line.strip()), "{}"))
            if (header.get("event") != "runtime" or header.get("schema_version") != 1
                    or header.get("run_id") != report["run_id"] or header.get("user_rank") != rank
                    or header.get("device_id") != runtime["runtime_device_id"]
                    or header.get("node_id") not in {node, report["run_id"] + "/" + node}):
                raise ValueError("public clock validation identity mismatch during evaluation")
        windows.append(dict(node_id=report["run_id"] + "/" + node, user_rank=rank,
                            start_ns=raw_to_profiler(begin, start, stop),
                            stop_ns=raw_to_profiler(end, start, stop),
                            clock_conversion="cann_start_offset"))
    hits = [c["id"] for c in report["candidates"] if any(c["node_id"] == w["node_id"]
            and c["user_rank"] == w["user_rank"] and min(c["observed_stop_ns"], w["stop_ns"]) > max(c["observed_start_ns"], w["start_ns"])
            for w in windows)]
    return dict(case_id=case["case_id"], injection=injection, diagnosis_status=report["diagnosis_status"],
                pipeline_passed=True, windows=windows, candidate_count=len(report["candidates"]),
                hit_candidate_ids=hits, candidate_hit_count=len(hits), any_candidate_hit=bool(hits),
                candidate_hit_fraction=len(hits) / len(report["candidates"]) if report["candidates"] else None,
                primary_hit=report["primary_candidate_id"] in hits, chain_count=report["propagation"]["chain_count"],
                quality=report["quality"], normal_false_positive_candidate_count=len(report["candidates"]) if not owners else None)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(evaluate(args.root)))


if __name__ == "__main__":
    main()
