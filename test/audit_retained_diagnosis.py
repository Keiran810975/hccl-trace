"""Read retained source reports for CPU-only audit; never consume injection truth."""
from __future__ import annotations

import argparse
from copy import deepcopy
from collections import defaultdict
from decimal import Decimal
from html.parser import HTMLParser
import json
from pathlib import Path

from hccl.tools.diagnosis.source_ranking import rank_regions
from hccl.tools.diagnosis.task_classifier import INTERNAL


class PropagationData(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=False)
        self.active, self.parts, self.count = False, [], 0

    def handle_starttag(self, tag, attrs):
        if tag == "script" and dict(attrs).get("id") == "propagation-data":
            self.active = True
            self.count += 1

    def handle_endtag(self, tag):
        if tag == "script":
            self.active = False

    def handle_data(self, data):
        if self.active:
            self.parts.append(data)


def read_propagation(path):
    parser = PropagationData()
    with Path(path).open(encoding="utf-8") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), ""):
            parser.feed(chunk)
    parser.close()
    if parser.count != 1:
        raise ValueError("expected one native propagation JSON payload")
    return json.loads("".join(parser.parts))


def retained_observations(directory):
    report = json.loads((directory / "root_causes.json").read_text())
    if report.get("schema_version") != 2 or not report["quality"]["pipeline_passed"]:
        raise ValueError("a complete schema2 report is required")
    propagation = read_propagation(directory / "propagation.html")
    slow_waits = {}
    for item in report["unresolved_observations"]:
        if item.get("component") == "wait_boundary":
            slow_waits[item["graph_id"]] = dict(item, duration_slow=True, task_kind="notify_wait",
                reference_count=5)
    roots = []
    for entry in propagation["candidates"]:
        root = dict(entry["source"], graph_id=entry["anchor_graph_id"], status=entry["status"],
                    primary_eligible=(entry["diagnosis_category"] == "communication_source_candidate"
                                      and not entry["source"].get("traversal_truncated")),
                    affected_wait_graph_ids=[c["target_wait_graph_id"] for c in entry["chains"]],
                    evidence_paths={c["target_wait_graph_id"]: c["edge_ids"] for c in entry["chains"]})
        root["observed_start_ns"] = int(root["observed_start_ns"])
        root["observed_stop_ns"] = int(root["observed_stop_ns"])
        roots.append(root)
    for key, item in propagation["nodes"].items():
        metrics = item["comparison"]
        if item["task_kind"] == "notify_wait" and metrics.get("duration_slow"):
            wait = dict(item, graph_id=key, observed_start_ns=int(item["start_ns"]),
                        observed_stop_ns=int(item["stop_ns"]), **metrics)
            previous = slow_waits.get(key)
            if previous and (previous["observed_start_ns"] != wait["observed_start_ns"]
                             or previous["observed_stop_ns"] != wait["observed_stop_ns"]
                             or Decimal(previous["delta_ns"]) != Decimal(wait["delta_ns"])):
                raise ValueError("retained Wait facts disagree across final reports")
            slow_waits[key] = wait
    if len(slow_waits) != report["coverage"]["wait_backtrace_count"]:
        raise ValueError("retained slow Wait coverage is incomplete; ranking replay refused")
    return dict(schema_version=1, run_id=report["run_id"], reference=report["reference"],
        source="original normalized observations and source-first paths; no tasks or dependencies rebuilt",
        expected_slow_wait_count=report["coverage"]["wait_backtrace_count"],
        retained_slow_wait_count=len(slow_waits), roots=roots, slow_waits=list(slow_waits.values()),
        original_primary_id=report["primary_candidate_id"], original_candidate_ids=[c["id"] for c in report["candidates"]],
        coverage=report["coverage"], quality=report["quality"])


def summarize(data):
    by_iteration = defaultdict(list)
    for wait in data["slow_waits"]:
        by_iteration[wait["iteration"]].append(wait)
    episodes = []
    for iteration, waits in by_iteration.items():
        positive = [Decimal(w["delta_ns"]) for w in waits]
        roots = [r for r in data["roots"] if r["iteration"] == iteration and r["component"] == "execution"]
        episodes.append(dict(iteration=iteration, max_wait_delta_ns=str(max(positive)),
            slow_wait_count=len(waits), ranks=sorted({w["user_rank"] for w in waits}),
            root_count=len(roots), max_root_delta_ns=str(max((Decimal(r["delta_ns"]) for r in roots), default=0))))
    episodes.sort(key=lambda e: -Decimal(e["max_wait_delta_ns"]))
    return dict(run_id=data["run_id"], expected=data["expected_slow_wait_count"], retained=data["retained_slow_wait_count"],
                top_iterations=episodes[:12], all_iterations=episodes)


def rerank(data):
    if data["expected_slow_wait_count"] != data["retained_slow_wait_count"]:
        raise ValueError("retained slow Wait coverage is incomplete")
    roots = deepcopy(data["roots"])
    before = {r["root_id"] for r in roots if r["diagnosis_category"] == INTERNAL}
    if before != set(data["original_candidate_ids"]):
        raise ValueError("retained candidate membership disagrees with original public report")
    if any(not r.get("graph_id") for r in roots):
        raise ValueError("retained candidate execution anchors are missing")
    regions = rank_regions(roots, data["slow_waits"])
    return dict(schema_version=1, source_ranking_version=2, run_id=data["run_id"],
                analysis_scope="retained_candidate_ranking_only_not_full_backtrace_replay",
                original_primary_id=data["original_primary_id"],
                primary_candidate_id=next((r["root_id"] for r in roots if r["primary_eligible"]), None),
                recommended_candidate_ids=regions[0]["candidate_ids"] if regions else [],
                source_regions=regions, roots=roots, candidate_membership_changed=False,
                limits=["Original tasks, paths, detector thresholds and candidate membership are unchanged.",
                        "Ranking is heuristic, not measured causal attribution or workload loss.",
                        "No injection truth was consumed; evaluation must be separate."])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    inputs = parser.add_mutually_exclusive_group(required=True)
    inputs.add_argument("--report", type=Path)
    inputs.add_argument("--replay-input", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    data = (retained_observations(args.report) if args.report else
            json.loads(args.replay_input.read_text(encoding="utf-8")))
    if args.report:
        (args.output / "analysis-input.json").write_text(json.dumps(data) + "\n")
    summary = summarize(data)
    (args.output / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    ranked = rerank(data)
    (args.output / "reranked.json").write_text(json.dumps(ranked, indent=2) + "\n")
    print(json.dumps({k: v for k, v in summary.items() if k != "all_iterations"}))


if __name__ == "__main__":
    main()
