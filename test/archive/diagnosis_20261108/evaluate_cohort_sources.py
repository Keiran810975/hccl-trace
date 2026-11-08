"""Evaluate sealed cohort choices against unchanged original private windows."""
from __future__ import annotations

# Archived experiment; supported diagnosis uses hccl-diag analyze.

import argparse
import hashlib
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from test.archive.diagnosis_20261108.evaluate_parallel_sources import original_evaluation, overlap
from test.refine_multinode_sources import digest


def truth(original, archive_sha):
    receipt = json.loads((original / "node0/verified.json").read_text())
    expected = json.loads((original / "node0/manifest.json").read_text())["files"]["evaluation.json"]
    if receipt["archive_sha256"] != archive_sha:
        raise ValueError("choice and original evaluation use different captures")
    cache = Path(__file__).resolve().parent / "out/multinode-top1-20261108/amplitude-analysis/truth-cache" / (original.name.rsplit("-", 1)[-1] + ".json")
    if cache.exists():
        data = json.loads(cache.read_text())
        raw = data["raw_json_members"]["evaluation.json"].encode()
        if (data["archive_sha256"] != archive_sha or len(raw) != expected["size"]
                or hashlib.sha256(raw).hexdigest() != expected["sha256"]):
            raise ValueError("previous original-window cache changed")
        return json.loads(raw)
    return original_evaluation(original, archive_sha)


def evaluate(live, replays, output):
    originals = sorted(live.glob("hccl-diagnose-node03-20261106-*"))
    if any(not (replays / p.name.rsplit("-", 1)[-1] / "sealed.json").is_file() for p in originals):
        raise ValueError("all choices must be sealed before any private truth is read")
    cases, version = [], None
    for original in originals:
        case = original.name.rsplit("-", 1)[-1]
        folder = replays / case
        seal = json.loads((folder / "sealed.json").read_text())
        if seal["truth_accessed"] is not False or digest(folder / "selection.json") != seal["selection_sha256"]:
            raise ValueError("selection was not sealed before evaluation")
        if version is not None and version != seal["consumer_sha256"]:
            raise ValueError("all cases must use one unchanged consumer version")
        version = seal["consumer_sha256"]
        choice = json.loads((folder / "selection.json").read_text())
        if not choice["original_cluster_ids_identical"] or choice["cluster_selection"]["selected_cluster_count"] > 1:
            raise ValueError("original dependency cluster Top1 invariant failed")
        old = truth(original, choice["inputs"]["original_archive_sha256"])
        audit = json.loads((original / "independent-audit.json").read_text())
        if (audit["hit_count"], audit["candidate_count"]) != (old["candidate_hit_count"], old["candidate_count"]):
            raise ValueError("original result does not match prior independent audit")
        for name, expected in audit["report_sha256"].items():
            if digest(original / "report" / name) != expected:
                raise ValueError("original sealed report changed")
        records = [dict(id=c["root_id"], graph_id=c["graph_id"], node_id=c["node_id"], user_rank=c["user_rank"],
            iteration=c["iteration"], source_unit=c["source_unit"], overlap_ns=overlap(c, old["windows"]))
            for c in choice["candidates"]]
        hits = sum(c["overlap_ns"] > 0 for c in records)
        cases.append(dict(case=case, kind=old["injection"]["kind"], hits=hits, candidates=len(records),
            any_hit=hits > 0, old_hits=old["candidate_hit_count"], old_candidates=old["candidate_count"],
            old_any_hit=old["any_candidate_hit"], regression=old["any_candidate_hit"] and not hits,
            new_hit=not old["any_candidate_hit"] and hits > 0, excluded=False,
            selected_cluster=choice["cluster_selection"], candidate_records=records,
            endpoint_hits=[dict(node_id=w["node_id"], user_rank=w["user_rank"],
                hits=sum(c["overlap_ns"] > 0 and (c["node_id"],c["user_rank"]) == (w["node_id"],w["user_rank"]) for c in records))
                for w in old["windows"]],
            effect_gate_passed=audit["effect_gate_passed"], original_cluster_count=choice["original_cluster_count"],
            numerical_ranks_passed=audit["numerical_ranks_passed"], original_reports_unchanged=True,
            selection_sha256=seal["selection_sha256"], source_selection_truth_accessed=False,
            cohort_quality=choice["cohort_quality"]))
        print(case, old["injection"]["kind"], "{}/{}".format(hits, len(records)), flush=True)
    groups = {}
    for kind in sorted({c["kind"] for c in cases}):
        entries = [c for c in cases if c["kind"] == kind]
        groups[kind] = dict(completed=len(entries), hits=sum(c["hits"] for c in entries),
            candidates=sum(c["candidates"] for c in entries), any_hit=sum(c["any_hit"] for c in entries),
            old_hits=sum(c["old_hits"] for c in entries), old_candidates=sum(c["old_candidates"] for c in entries),
            old_any_hit=sum(c["old_any_hit"] for c in entries),
            unit="host_preparation_interval" if kind == "progress_delay" else "execution_task")
    value = dict(scope="known_sample_offline_development_not_independent_accuracy", cases=cases, groups=groups,
        consumer_sha256=version, excluded_cases=[], regressions=[c["case"] for c in cases if c["regression"]],
        new_hits=[c["case"] for c in cases if c["new_hit"]], criterion="same_node_rank_positive_overlap_original_actual_windows",
        cohort_snapshot=dict(requested=19, completed=12, failed=1, unrun=6, old_INFO_first_case_separate=True),
        limits=["Selections are all sealed before evaluating unchanged original private windows.",
                "No case is discarded based on a miss or background amplitude; task and Host units remain separate.",
                "RoCE execution-task overlap is not proof of a network resource cause.",
                "No new raw DB parse, training, device acceptance or normal false-positive calibration is claimed."])
    with output.open("x", encoding="utf-8") as out:
        json.dump(value, out, indent=2)
        out.write("\n")
    return value


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("live", "replays", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(evaluate(args.live, args.replays, args.output)["groups"], indent=2))
