"""Evaluate sealed selections; injection truth is only consumed in this step."""
from __future__ import annotations

# Archived experiment; supported diagnosis uses hccl-diag analyze.

import argparse
from collections import defaultdict
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import sys
import tarfile

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from test.refine_multinode_sources import digest


def original_evaluation(directory, archive_sha):
    files = json.loads((directory / "node0/manifest.json").read_text())["files"]
    expected = files["evaluation.json"]
    proof = json.loads((directory / "node0/verified.json").read_text())
    if proof["archive_sha256"] != archive_sha:
        raise ValueError("selection and evaluation are from different captures")
    with tarfile.open(directory / "node0/replay.tar.gz", "r|gz") as tar:
        for member in tar:
            record = files.get(member.name, {})
            if record.get("sha256") == expected["sha256"] and member.isfile():
                if member.size != expected["size"] or member.size > 8 * 1024**2:
                    raise ValueError("invalid bounded evaluation member")
                data = tar.extractfile(member).read()
                if hashlib.sha256(data).hexdigest() != expected["sha256"]:
                    raise ValueError("evaluation member SHA mismatch")
                return json.loads(data)
    raise ValueError("original evaluation is unavailable")


def overlap(item, windows):
    return max([0] + [max(0, min(item["observed_stop_ns"], w["stop_ns"]) - max(
        item["observed_start_ns"], w["start_ns"])) for w in windows
        if (item["node_id"], item["user_rank"]) == (w["node_id"], w["user_rank"])])


def evaluate(live, replays, output):
    cases, groups, version = [], defaultdict(list), None
    for directory in sorted(live.glob("hccl-diagnose-node03-20261106-*")):
        case = directory.name.rsplit("-", 1)[-1]
        folder = replays / case
        seal = json.loads((folder / "sealed.json").read_text())
        if seal["truth_accessed"] is not False or digest(folder / "selection.json") != seal["selection_sha256"]:
            raise ValueError("source selection must be sealed before evaluation")
        current = seal["consumer_sha256"]["hccl/tools/diagnosis/parallel_sources.py"]
        if version is not None and current != version:
            raise ValueError("all selections must use the same frozen source policy")
        version = current
        decision = json.loads((folder / "selection.json").read_text())
        old = original_evaluation(directory, decision["inputs"]["archive_sha256"])
        windows, kind = old["windows"], old["injection"]["kind"]
        records = [dict(graph_id=t["graph_id"], node_id=t["node_id"], user_rank=t["user_rank"],
            iteration=t["iteration"], overlap_ns=overlap(t, windows)) for t in decision["candidates"]]
        count, hits = len(records), sum(t["overlap_ns"] > 0 for t in records)
        main = old["injection"]["target_rank"]
        diagnostics = []
        for item in decision["call_admission"]:
            if item.get("admitted"):
                members = [t for t in decision["candidates"]
                    if (t["node_id"], t["user_rank"], t["operation_scope"])
                    == (item["node_id"], item["user_rank"], item["operation_scope"])]
                if not members:
                    continue
                diagnostics.append(dict(item, overlaps_injection=overlap(dict(item,
                    observed_start_ns=min(t["observed_start_ns"] for t in members),
                    observed_stop_ns=max(t["observed_stop_ns"] for t in members)), windows) > 0))
        true_growth = max((Decimal(t["work_sum_factor"]) for t in diagnostics if t["overlaps_injection"]), default=None)
        other_growth = max((Decimal(t["work_sum_factor"]) for t in diagnostics if not t["overlaps_injection"]), default=None)
        entry = dict(case=case, kind=kind, hits=hits, candidates=count, any_hit=hits > 0,
            candidate_overlap_fraction=hits / count if count else None,
            main_rank_hits=sum(t["overlap_ns"] > 0 and t["user_rank"] == main for t in records),
            old_hits=old["candidate_hit_count"], old_candidates=old["candidate_count"],
            old_any_hit=old["any_candidate_hit"], candidate_records=records,
            excluded=False, competing_growth_at_least_as_large=bool(other_growth is not None and
                (true_growth is None or other_growth >= true_growth)),
            max_injection_unit_factor=str(true_growth) if true_growth is not None else None,
            max_other_unit_factor=str(other_growth) if other_growth is not None else None,
            selection_sha256=seal["selection_sha256"],
            scope="execution_selection_only_Host_and_protocol_roots_not_replayed")
        cases.append(entry)
        if kind != "progress_delay":
            groups[kind].append(entry)
        print(case, kind, "{}/{}".format(hits, count), flush=True)
    result = dict(scope="known_data_offline_development_not_independent_accuracy_validation",
        criterion="same_node_same_rank_positive_overlap_original_actual_windows",
        source_policy_sha256=version, excluded_cases=[], cases=cases,
        groups={kind: dict(completed=len(items), hits=sum(t["hits"] for t in items),
            candidates=sum(t["candidates"] for t in items), any_hit=sum(t["any_hit"] for t in items),
            old_hits=sum(t["old_hits"] for t in items), old_candidates=sum(t["old_candidates"] for t in items),
            old_any_hit=sum(t["old_any_hit"] for t in items)) for kind, items in groups.items()},
        denominators=dict(original_requested=19, completed=12, failed=1, unrun=6, old_INFO_first_case_separate=True),
        limitations=["Candidate counts and false/nonoverlapping candidates must be reported, not only any-hit experiments.",
            "Competition outside injection is a post-hoc noise audit, not an exclusion rule or input to diagnosis.",
            "Communication windows include both declared participants; main-rank hits are separately retained.",
            "Host interval results are not comparable to this execution-only artifact selection replay.",
            "No new raw DB parse, full pipeline acceptance, network hardware diagnosis or general accuracy is claimed."])
    with output.open("x", encoding="utf-8") as target:
        json.dump(result, target, indent=2)
        target.write("\n")
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("live", "replays", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args()
    result = evaluate(args.live, args.replays, args.output)
    print(json.dumps(result["groups"], indent=2))
