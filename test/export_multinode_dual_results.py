"""Export all six frozen experiments, independently checking reports and archives."""
from __future__ import annotations

import argparse
from collections import Counter
import csv
import hashlib
import json
from pathlib import Path

if __package__:
    from .multinode_dual_suite import plan
else:
    from multinode_dual_suite import plan


LABELS = {"normal": "Baseline", "copy_contention": "Copy", "communication_contention": "Communication",
          "compute_contention": "Compute", "progress_delay": "Host Delay", "bandwidth_limit": "RoCE Limit"}
REPORTS = ("execution.html", "root_causes.json", "propagation.html")


def digest(path):
    value = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(8 * 1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def evaluate(report, windows):
    sources = report.get("source_candidates", report["candidates"])
    hits = [c["id"] for c in sources if any(c["node_id"] == w["node_id"] and c["user_rank"] == w["user_rank"]
        and min(c["observed_stop_ns"], w["stop_ns"]) > max(c["observed_start_ns"], w["start_ns"]) for w in windows)]
    return sources, hits, report.get("primary_source_id", report["primary_candidate_id"]) in hits


def export(base, state_path, output):
    state = json.loads(state_path.read_text())["last_remote"]
    frozen = plan()["cases"]
    if state.get("status") != "completed" or state.get("completed") != 6 or state.get("requested_runs") != 6:
        raise ValueError("all six actual experiments must have completed")
    cases = state["cases"]
    if len(cases) != 6 or [c["case_id"] for c in cases] != [c["case_id"] for c in frozen]:
        raise ValueError("six unique frozen cases required; no outcome filtering")
    if output.exists():
        raise FileExistsError("refusing to overwrite a previous exported result")
    rows, windows = [], []
    for case, specification in zip(cases, frozen):
        if case["injection"] != specification["injection"]:
            raise ValueError("injection parameters differ from the frozen plan")
        name = Path(case["directory"]).name
        matches = list(base.glob("live*/" + name + "/offload-receipt.json"))
        if len(matches) != 1:
            raise ValueError("a unique verified archive directory required: " + name)
        directory = matches[0].parent
        receipt = json.loads(matches[0].read_text())
        if receipt.get("status") != "verified" or not receipt.get("file_hashes_verified"):
            raise ValueError("lossless archive verification missing")
        archives = []
        for node in (0, 3):
            root = directory / ("node" + str(node))
            verified = json.loads((root / "verified.json").read_text())
            manifest = json.loads((root / "manifest.json").read_text())
            if (verified.get("node") != node or not verified.get("file_hashes_verified")
                    or hashlib.sha256(json.dumps(manifest, sort_keys=True).encode()).hexdigest() != verified["manifest_sha256"]
                    or digest(root / "replay.tar.gz") != verified["archive_sha256"]):
                raise ValueError("verified original archive changed")
            archives.append(dict(node=node, archive=str((root / "replay.tar.gz").resolve()),
                                 sha256=verified["archive_sha256"], file_count=verified["file_count"]))
        node0 = json.loads((directory / "node0/manifest.json").read_text())
        encoded = (json.dumps(case, indent=2, ensure_ascii=False) + "\n").encode()
        if hashlib.sha256(encoded).hexdigest() != node0["files"]["evaluation.json"]["sha256"]:
            raise ValueError("suite evaluation differs from the sealed archived evaluation")
        files = {}
        for name in REPORTS:
            path = directory / "report" / name
            if path.is_symlink() or digest(path) != node0["files"]["report/" + name]["sha256"]:
                raise ValueError("native report differs from the sealed original")
            files[name] = str(path.resolve())
        report = json.loads(Path(files["root_causes.json"]).read_text())
        if report["run_id"] != case["case_id"] or not report["quality"]["pipeline_passed"]:
            raise ValueError("native report identity or pipeline gate failed")
        sources, hits, primary = evaluate(report, case["windows"])
        if (sorted(hits) != sorted(case["hit_candidate_ids"]) or len(hits) != case["candidate_hit_count"]
                or len(sources) != case["candidate_count"] or primary != case["primary_hit"]):
            raise ValueError("independently recomputed source-window evaluation differs")
        rows.append(dict(case_id=case["case_id"], kind=case["injection"]["kind"], injection=case["injection"],
            windows=case["windows"], candidate_count=len(sources), hit_count=len(hits), primary_hit=primary,
            candidate_fraction=len(hits)/len(sources) if sources else None,
            selected_mechanism=case["selected_mechanism"], source_units=dict(Counter(c["source_unit"] for c in sources)),
            sources=[{k:c.get(k) for k in ("id", "source_unit", "node_id", "user_rank", "iteration", "phase", "step",
                "stream_id", "task_id", "observed_start_ns", "observed_stop_ns")} for c in sources],
            report_files=files, original_archives=archives,
            quality={k:report["quality"].get(k) for k in ("node_count", "rank_count", "wait_count", "paired_wait_count",
                "clock_alignment_estimated_error_ns", "global_critical_path_available", "rdma_hardware_transfer_duration_available")}))
        windows.extend(dict(case_id=case["case_id"], kind=case["injection"]["kind"],
                            requested_iteration=case["injection"].get("iteration"), **w) for w in case["windows"])
    anomalies = rows[1:]
    total = sum(r["candidate_count"] for r in anomalies)
    result = dict(schema_version=1, formal_runs=6, anomaly_runs=5, baseline_false_positive_sources=rows[0]["candidate_count"],
        hit_count=sum(r["hit_count"] for r in anomalies), candidate_count=total,
        candidate_overlap_fraction=sum(r["hit_count"] for r in anomalies)/total if total else None,
        any_source_hit_cases=sum(r["hit_count"]>0 for r in anomalies), primary_hit_cases=sum(r["primary_hit"] for r in anomalies),
        cases=rows, raw_archives_and_reports_rehashed=True,
        limitations=["Strict same Node/Rank and positive observed-time overlap; the analyzer did not read injection truth.",
            "Execution tasks, Host intervals and protocol intervals are different source units; this is a location/window score, not physical-fault proof.",
            "One exploratory run per type, no failed cases discarded and no representative accuracy claim.",
            "Network clocks are estimates; no hardware RDMA completion timing or global workload critical path is claimed."])
    output.mkdir(parents=True)
    (output / "summary.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    for filename, values in (("results.csv", [{k:r[k] for k in ("case_id", "kind", "candidate_count", "hit_count", "primary_hit", "candidate_fraction", "selected_mechanism")} for r in rows]),
                             ("injection-windows.csv", windows)):
        with (output / filename).open("w", encoding="utf-8", newline="") as stream:
            writer = csv.DictWriter(stream, list(values[0]) if values else ["case_id"])
            writer.writeheader()
            writer.writerows(values)
    body = ["# Node0 + Node3 GPT-2 Validation", "", "2 nodes x 4 ranks, 10 warmup + 50 measured per run; frozen dual policy.", "",
        "| Case | Final Hits / Sources | Primary Hit | Native Reports |", "|---|---|---|---|"]
    for r in rows:
        links = " / ".join("[{}]({})".format(name, path) for name, path in r["report_files"].items())
        body.append("| {} | {} | {} | {} |".format(LABELS[r["kind"]],
            "{} / {}".format(r["hit_count"],r["candidate_count"]) if r["kind"]!="normal" else "{} un-injected sources".format(r["candidate_count"]), r["primary_hit"],links))
    body += ["", "Full execution timelines are about 4.7 GB each. Propagation views and JSON are much smaller.",
        "Original archives and the three native reports were rehashed; no report was rewritten to change a result.",
        "See summary.json, results.csv and injection-windows.csv. Protocol observations are not pure wire durations."]
    (output / "README.md").write_text("\n".join(body)+"\n", encoding="utf-8")
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", type=Path, required=True)
    parser.add_argument("--follower-state", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = export(args.base, args.follower_state, args.output)
    print(json.dumps({k:v for k,v in result.items() if k!="cases"}))
