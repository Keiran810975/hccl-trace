"""Offline-only sensitivity replay over immutable, already validated graph facts."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from hccl.tools.diagnosis import rolling_diagnosis as rolling
from hccl.tools.diagnosis.run_diagnosis import resume_replay_analysis
from hccl.tools.diagnosis.result_normalizer import normalize
from hccl.tools.diagnosis.report_exporter import publish_final_report
from hccl.tools.diagnosis import visualize_dependency_graph as graph
from hccl.tools.diagnosis import analyze_waits as waits


def digest(path):
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(4 * 1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def replay(root, output, *, source_factor="1.5", wait_factor=None, intervals=False, completion=False):
    original = root / "preflight-report/root_causes.json"
    run_id = json.loads(original.read_text())["run_id"]
    debug = root / "preflight-report.debug"
    source = debug / "analysis" / run_id
    facts = [p for p in source.rglob("*") if p.is_file()]
    before = {str(p.relative_to(source)): digest(p) for p in facts}
    options = rolling.RollingOptions(max_figures=0, slowdown_factor=source_factor,
        wait_slowdown_factor=wait_factor, calibrated_release_intervals=intervals, completion_fallback=completion)
    directory, ready = resume_replay_analysis(source, output / "analysis",
        iteration_map=debug / "current/iteration-map.json",
        preparation_map=(debug / "current/preparation-map.json") if (debug / "current/preparation-map.json").exists() else None,
        rolling_options=options, include_critical_path=False, allow_uncalibrated_clock=True)
    if not ready:
        raise ValueError("strict graph gates failed during offline replay")
    pipeline = json.loads((directory / "pipeline_result.json").read_text())
    report = json.loads((directory / "rolling/report.json").read_text())
    rows = graph.read_graph_artifact_nodes(directory / "dep_graph_nodes.csv")
    edges = graph.read_graph_artifact_edges(directory / "dep_graph_edges.csv")
    normalized, roots, comparisons = normalize(report, mode="rolling", run_id=run_id, rows=rows, edges=edges,
        pipeline=pipeline, binding_evidence=dict(source="reused independently bound public coordinates; no injection input"),
        merge_metrics=waits.read_csv(directory / "merge_summary.csv"))
    publish_final_report(directory, output / "report", normalized, roots, comparisons)
    after = {str(p.relative_to(source)): digest(p) for p in facts}
    if before != after:
        raise ValueError("an immutable input changed during offline replay")
    receipt = dict(workload_rerun=False, truth_consumed_by_analyzer=False, immutable_facts_sha256=before,
                   original_facts_unchanged=True, options=report["options"], candidate_count=len(normalized["candidates"]),
                   primary_id=normalized["primary_candidate_id"], coverage=report["coverage"])
    code = Path(__file__).resolve().parents[1] / "hccl/tools/diagnosis"
    receipt["analyzer_files_sha256"] = {p.name: digest(p) for p in sorted(code.glob("*.py"))}
    (output / "replay-receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")
    return receipt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--source-factor", default="1.5")
    parser.add_argument("--wait-factor")
    parser.add_argument("--intervals", action="store_true")
    parser.add_argument("--completion", action="store_true")
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError("every offline method needs a fresh output directory")
    args.output.mkdir(parents=True)
    result = replay(args.root, args.output, source_factor=args.source_factor, wait_factor=args.wait_factor,
                    intervals=args.intervals, completion=args.completion)
    print(json.dumps({k: result[k] for k in ("candidate_count", "primary_id", "coverage", "original_facts_unchanged")}))


if __name__ == "__main__":
    main()
