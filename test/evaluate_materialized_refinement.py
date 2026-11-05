"""Score sealed native reports; keep original and audited control-window metrics separate."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from test.refine_multinode_sources import digest
from test.evaluate_multinode_refinement import evaluate


def summarize(reports, work, original, output, network_audit=None):
    prior = json.loads(original.read_text())
    audit = json.loads(network_audit.read_text()) if network_audit else None
    if audit and (not audit.get("evaluation_only") or not audit.get("no_candidate_or_diagnosis_input")):
        raise ValueError("network-window correction must be a separate evaluation-only control audit")
    cases, version = [], None
    for index, old in enumerate(prior["cases"], 521):
        path = reports / str(index) / "root_causes.json"
        seal = json.loads((work / str(index) / "sealed.json").read_text())
        if seal.get("truth_accessed") is not False or digest(path) != seal["root_report_sha256"]:
            raise ValueError("native output must be sealed before evaluation")
        if version is None:
            version = seal["consumer_sha256"]
        if version != seal["consumer_sha256"]:
            raise ValueError("all six reports must use identical consumers")
        report = json.loads(path.read_text())
        if report["run_id"] != old["case_id"]:
            raise ValueError("native report belongs to another original capture")
        sources = [dict(c, candidate_id=c["id"]) for c in report["source_candidates"]]
        if [c["candidate_id"] for c in sources] != seal["selected_source_ids"]:
            raise ValueError("sealed source list changed")
        raw = evaluate(dict(candidates=sources), old["windows"])
        corrected_windows = old["windows"]
        if audit and old["case_id"] == audit["case_id"]:
            if old["windows"] != [audit["original_window_unchanged"]]:
                raise ValueError("control audit changed the original comparison window")
            corrected_windows = [audit["separately_verified_window"]]
        corrected = evaluate(dict(candidates=sources), corrected_windows)
        cases.append(dict(case_id=old["case_id"], kind=old["kind"], count=len(sources),
            original_window_hits=sum(c["hit"] for c in raw), audited_window_hits=sum(c["hit"] for c in corrected),
            original_window_first_hit=bool(raw and raw[0]["hit"]), audited_window_first_hit=bool(corrected and corrected[0]["hit"]),
            candidates_original=raw, candidates_audited=corrected,
            propagation=report["propagation"], report_directory=str(path.parent.resolve()),
            source_report_sha256=seal["root_report_sha256"]))
    anomalies = cases[1:]
    count = sum(c["count"] for c in anomalies)
    metrics = {}
    for name in ("original", "audited"):
        hits = sum(c[name + "_window_hits"] for c in anomalies)
        metrics[name + "_windows"] = dict(hits=hits, count=count, fraction=hits / count if count else None,
            any_hit_cases=sum(c[name + "_window_hits"] > 0 for c in anomalies),
            first_hit_cases=sum(c[name + "_window_first_hit"] for c in anomalies))
    result = dict(schema_version=1, scope="known_sample_development_not_independent_validation", cases=cases,
        metrics=metrics, normal_false_positive_candidates=cases[0]["count"], same_consumer_sha256=version,
        original_windows_never_overwritten=True, network_control_audit_sha256=digest(network_audit) if audit else None,
        source_units_separate=True, caveat="A window hit is not proof of a physical fault; Host preparation and execution are distinct units.")
    with output.open("x", encoding="utf-8") as stream:
        json.dump(result, stream, indent=2)
        stream.write("\n")
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reports", type=Path, required=True)
    parser.add_argument("--work", type=Path, required=True)
    parser.add_argument("--original", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--network-audit", type=Path)
    args = parser.parse_args()
    result = summarize(args.reports, args.work, args.original, args.output, args.network_audit)
    print(json.dumps(result["metrics"]))
    for case in result["cases"]:
        print(case["kind"], "original {}/{}; audited {}/{}; chains {}".format(case["original_window_hits"],
            case["count"], case["audited_window_hits"], case["count"], case["propagation"]["chain_count"]))
