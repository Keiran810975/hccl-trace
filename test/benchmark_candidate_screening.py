"""Freeze public-input candidate ablations before running a separate truth audit."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from hccl.tools.diagnosis import rolling_diagnosis as rolling
from hccl.tools.diagnosis import visualize_dependency_graph as graph
from hccl.tools.diagnosis.candidate_screening import POLICIES, select_candidates, local_wait_impacts
from hccl.tools.diagnosis.task_classifier import INTERNAL


def digest(path):
    result = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(4 * 1024 * 1024), b""):
            result.update(chunk)
    return result.hexdigest()


def benchmark(artifact, iteration_map, output, *, alignment=None):
    files = [artifact / "dep_graph_nodes.csv", artifact / "dep_graph_edges.csv", iteration_map]
    if alignment:
        files.append(alignment)
    code = Path(__file__).resolve().parents[1] / "hccl/tools/diagnosis"
    files.extend(sorted(code.glob("*.py")))
    before = {str(p.resolve()): digest(p) for p in files}
    output.mkdir(parents=True, exist_ok=False)
    # Persist the complete policy set before any outputs or truth are inspected.
    (output / "frozen-inputs.json").write_text(json.dumps(dict(
        sha256=before, policies=POLICIES, truth_input=None, overwrite_original=False,
        evidence_class="exploratory; historical outcomes already inspected"), indent=2) + "\n")
    rows = graph.read_graph_artifact_nodes(files[0])
    edges = graph.read_graph_artifact_edges(files[1])
    scopes = {r.get("_operation_scope") for r in rows}
    coords = {k: v for k, v in rolling.load_coordinates(iteration_map).items() if k in scopes}
    options = rolling.RollingOptions(max_figures=0, calibrated_release_intervals=alignment is not None)
    report = rolling.analyze(rows, edges, coords, options, preparations=(),
                             alignment=json.loads(alignment.read_text()) if alignment else None)
    roots = [r for r in report["root_causes"] if r["diagnosis_category"] == INTERNAL]
    # Preserve every pre-screening source, including those no policy retains.
    (output / "source-observations.json").write_text(json.dumps(dict(roots=roots,
        source_policy_version=report["source_policy_version"], coverage=report["coverage"],
        options=report["options"], host_observations_included=False), indent=2) + "\n")
    result = []
    wait_impacts = local_wait_impacts(roots, rows, edges)
    for policy in POLICIES:
        decision = select_candidates(roots, report["tasks"], policy=policy, wait_impacts=wait_impacts)
        (output / (policy + ".json")).write_text(json.dumps(decision, indent=2) + "\n")
        result.append(dict(policy=policy, selected=decision["selected_candidate_count"],
                           original=decision["original_candidate_count"], deferred=decision["deferred_candidate_count"]))
    if before != {str(p.resolve()): digest(p) for p in files}:
        raise ValueError("public inputs or consumer changed during the benchmark")
    summary = dict(npu_runs=0, truth_consumed=False, original_facts_unchanged=True,
        host_observations_included=False, policy_results=result,
        decision_files_sha256={p.name: digest(p) for p in [output / "source-observations.json",
                                                         *[output / (name + ".json") for name in POLICIES]]},
        scope="current full backtrace over supplied graph; not re-collection or independent accuracy validation")
    (output / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifact", type=Path, required=True)
    parser.add_argument("--iteration-map", type=Path, required=True)
    parser.add_argument("--alignment", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(benchmark(args.artifact, args.iteration_map, args.output, alignment=args.alignment)))
