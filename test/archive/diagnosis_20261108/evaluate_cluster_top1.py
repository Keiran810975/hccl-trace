"""Independent original-window evaluation of sealed single-cluster outputs."""
from __future__ import annotations

# Archived experiment; supported diagnosis uses hccl-diag analyze.

import argparse
import gzip
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from test.archive.diagnosis_20261108.evaluate_parallel_sources import original_evaluation, overlap
from test.refine_multinode_sources import digest


def evaluate(live, replays, output):
    cases, version = [], None
    for original in sorted(live.glob("hccl-diagnose-node03-20261106-*")):
        case = original.name.rsplit("-", 1)[-1]
        folder = replays / case
        seal = json.loads((folder / "sealed.json").read_text())
        if seal["truth_accessed"] is not False or digest(folder / "selection.json") != seal["selection_sha256"]:
            raise ValueError("selection not sealed before truth evaluation")
        current = seal["consumer_sha256"]["hccl/tools/diagnosis/cluster_top1.py"]
        if version is not None and version != current:
            raise ValueError("one unchanged ranking policy required")
        version = current
        decision = json.loads((folder / "selection.json").read_text())
        if decision["cluster_selection"]["selected_cluster_count"] > 1 or not decision["original_cluster_ids_identical"]:
            raise ValueError("Top1 or original cluster membership invariant failed")
        truth = original_evaluation(original, decision["inputs"]["original_archive_sha256"])
        candidates = [dict(id=c["root_id"], graph_id=c["graph_id"], node_id=c["node_id"], user_rank=c["user_rank"],
            iteration=c["iteration"], source_unit=c["source_unit"], overlap_ns=overlap(c, truth["windows"])) for c in decision["candidates"]]
        hits = sum(c["overlap_ns"] > 0 for c in candidates)
        wanted = {key for p in decision["cluster_rankings"] for key in p["candidate_graph_ids"]}
        matching = set()
        cache = Path(decision["inputs"]["public_cache"])
        with gzip.open(cache / "tasks.jsonl.gz", "rt") as stream:
            for line in stream:
                task = json.loads(line)
                if task["graph_id"] in wanted and overlap(task, truth["windows"]) > 0:
                    matching.add(task["graph_id"])
        ranked = decision["cluster_rankings"]
        supported = [dict(rank=i, proposal_id=p["proposal_id"], score_ns=p["score"],
                         matching_task_count=len(set(p["candidate_graph_ids"]) & matching))
            for i, p in enumerate(ranked, 1) if set(p["candidate_graph_ids"]) & matching]
        entry = dict(case=case, kind=truth["injection"]["kind"], hits=hits, candidates=len(candidates),
            any_hit=hits > 0, old_hits=truth["candidate_hit_count"], old_candidates=truth["candidate_count"],
            old_any_hit=truth["any_candidate_hit"], selected_cluster=decision["cluster_selection"],
            main_rank_hits=sum(c["overlap_ns"] > 0 and c["user_rank"] == truth["injection"]["target_rank"] for c in candidates),
            best_window_overlapping_execution_cluster=supported[0] if supported else None,
            candidate_records=candidates, excluded=False, original_clusters_identical=True,
            selection_sha256=seal["selection_sha256"], effect_original_unchanged=True)
        cases.append(entry)
        print(case, entry["kind"], "{}/{}".format(hits, len(candidates)), flush=True)
    groups = {}
    for kind in {c["kind"] for c in cases}:
        records = [c for c in cases if c["kind"] == kind]
        groups[kind] = dict(completed=len(records), hits=sum(c["hits"] for c in records),
            candidates=sum(c["candidates"] for c in records), any_hit=sum(c["any_hit"] for c in records),
            main_rank_any_hit=sum(c["main_rank_hits"] > 0 for c in records),
            old_hits=sum(c["old_hits"] for c in records), old_candidates=sum(c["old_candidates"] for c in records),
            old_any_hit=sum(c["old_any_hit"] for c in records), unit="host_preparation" if kind == "progress_delay" else "execution_task")
    result = dict(policy_sha256=version, scope="known_sample_offline_development_not_independent_accuracy",
        criterion="same_node_same_rank_positive_overlap_unchanged_original_actual_windows", cases=cases,
        groups=groups, excluded_cases=[], original_cluster_membership_verified_in_every_case=True,
        candidate_relationship="parallel_members_of_one_winning_cluster", raw_inputs_retained=True,
        cohort_snapshot=dict(requested=19, completed=12, failed=1, unrun=6, old_INFO_first_case_separate=True),
        limits=["All source selections are sealed before reading original truth; no candidate window or rank is changed.",
            "A larger unrelated execution-growth cluster is preserved as a miss, not discarded or relabelled success.",
            "The score is local execution-growth accounting, not proved physical cause or training critical-path impact.",
            "RoCE sample overlap is not proof of network port or NIC localization; Host intervals and execution tasks are different units."])
    with output.open("x", encoding="utf-8") as target:
        json.dump(result, target, indent=2)
        target.write("\n")
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("live", "replays", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(evaluate(args.live, args.replays, args.output)["groups"], indent=2))
