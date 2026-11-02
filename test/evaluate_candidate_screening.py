"""Post-analysis overlap evaluator; never supplies labels to the analyzer."""
from __future__ import annotations

import argparse
from decimal import Decimal
import hashlib
import json
from pathlib import Path


def evaluate(roots, selection, windows, *, profiler_offsets=None):
    by_id = {r["root_id"]: r for r in roots}
    if len(by_id) != len(roots):
        raise ValueError("duplicate original candidate IDs")
    selected = selection["selected_candidate_ids"]
    if len(set(selected)) != len(selected) or not set(selected) <= by_id.keys():
        raise ValueError("selection contains duplicate or unknown candidates")
    if any(type(w.get("start_ns")) is not int or type(w.get("stop_ns")) is not int
           or w["start_ns"] >= w["stop_ns"] or not isinstance(w.get("target_ranks"), list)
           or not w.get("node_id") for w in windows):
        raise ValueError("complete independently captured node/rank windows required")
    evaluated = []
    for identifier, root in by_id.items():
        start, stop = root["observed_start_ns"], root["observed_stop_ns"]
        if profiler_offsets is not None:
            key = root["node_id"], root["device_id"]
            if key not in profiler_offsets:
                raise ValueError("independent device clock mapping missing")
            start -= profiler_offsets[key]
            stop -= profiler_offsets[key]
        overlaps = [max(0, min(stop, w["stop_ns"]) - max(start, w["start_ns"])) for w in windows
                    if root["node_id"] == w["node_id"] and root["user_rank"] in w["target_ranks"]]
        evaluated.append(dict(candidate_id=identifier, selected=identifier in selected,
                              hit=max(overlaps, default=0) > 0, overlap_ns=max(overlaps, default=0)))
    original_hits = sum(e["hit"] for e in evaluated)
    hits = sum(e["hit"] and e["selected"] for e in evaluated)
    return dict(policy=selection["policy"], original_hits=original_hits, original_count=len(roots),
                hits=hits, candidate_count=len(selected),
                precision=str(Decimal(hits) / len(selected)) if selected else None,
                strictly_above_75_percent=bool(selected and hits * 4 > len(selected) * 3),
                any_hit=hits > 0, lost_hit_candidates=original_hits - hits,
                empty_result_is_success=False, candidate_evaluations=evaluated,
                rule="same_node_same_executing_rank_positive_interval_overlap",
                physical_causation_proven=False)


def audit(directory, truth, output, *, alignment=None):
    # Refuse partial ablations: labels are read only after all declared decisions exist.
    frozen = json.loads((directory / "frozen-inputs.json").read_text())
    summary = json.loads((directory / "summary.json").read_text())
    sealed = summary.get("decision_files_sha256")
    expected = {"source-observations.json", *(p + ".json" for p in frozen["policies"])}
    if not sealed or set(sealed) != expected:
        raise ValueError("pre-evaluation decision seal missing or incomplete")
    hashes = {name: hashlib.sha256((directory / name).read_bytes()).hexdigest() for name in sealed}
    if hashes != sealed:
        raise ValueError("diagnostic decisions changed before evaluation")
    decisions = [json.loads((directory / (p + ".json")).read_text()) for p in frozen["policies"]]
    roots = json.loads((directory / "source-observations.json").read_text())["roots"]
    windows = json.loads(truth.read_text())
    offsets = None
    if alignment:
        from hccl.tools.diagnosis.clock_alignment import models_from_report
        clocks = models_from_report(json.loads(alignment.read_text()))
        offsets = {key: value.profiler_to_raw_offset_ns for key, value in clocks.items()}
    results = [evaluate(roots, item, windows, profiler_offsets=offsets) for item in decisions]
    if hashes != {name: hashlib.sha256((directory / name).read_bytes()).hexdigest() for name in sealed}:
        raise ValueError("diagnostic decisions changed during evaluation")
    record = dict(evaluator_consumed_truth_after_all_selections=True, analysis_modified=False,
                  decision_files_sha256=hashes, results=results)
    with output.open("x", encoding="utf-8") as stream:
        json.dump(record, stream, indent=2)
        stream.write("\n")
    return [{k: v for k, v in r.items() if k != "candidate_evaluations"} for r in results]


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--analysis", type=Path, required=True)
    parser.add_argument("--windows", type=Path, required=True)
    parser.add_argument("--alignment", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(audit(args.analysis, args.windows, args.output, alignment=args.alignment)))
