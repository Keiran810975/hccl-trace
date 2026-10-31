"""Revalidate the captured normal graph, rerun only consumers, and attest their source."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import time

from hccl.tools.diagnosis import rolling_diagnosis as rolling
from hccl.tools.diagnosis import visualize_dependency_graph as graph
from hccl.tools.diagnosis import analyze_waits as waits
from hccl.tools.diagnosis.capture_discovery import discover_capture, prepare_capture_identity, read_json, write_json
from hccl.tools.diagnosis.workload_binder import bind_capture
from hccl.tools.diagnosis.run_diagnosis import resume_replay_analysis
from hccl.tools.diagnosis.cli import _gate
from hccl.tools.diagnosis.result_normalizer import normalize
from hccl.tools.diagnosis.report_exporter import publish_final_report


def members(manifest):
    return {op["operation_id"]: (op["participants"], sorted((m["node_id"], m["device_id"], m["group_name"], m["op_name"])
                for m in op["members"])) for op in manifest["operations"]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case-root", type=Path, required=True)
    parser.add_argument("--source-debug", type=Path, required=True)
    parser.add_argument("--work", type=Path, required=True)
    args = parser.parse_args()
    root, work = args.case_root.resolve(), args.work.resolve()
    if read_json(root / "input/case.json")["injection"]["kind"] != "normal":
        raise ValueError("this replay only reuses the already trained normal experiment")
    if read_json(root / "authorized-state.json")["restored_nodes"] != [0, 3]:
        raise ValueError("both actual device restorations are required")
    work.mkdir()
    source = Path(__file__).resolve().parents[1]
    hashes = {str(p.relative_to(source)): hashlib.sha256(p.read_bytes()).hexdigest()
              for p in sorted((source / "hccl/tools/diagnosis").glob("*.py"))}
    capture = prepare_capture_identity(discover_capture(root / "capture", work / "discover"), work / "identity")
    binding = bind_capture(capture, work / "binding", mode="rolling")
    manifest = read_json(binding.manifest)
    original = args.source_debug / "analysis" / manifest["run_id"]
    old = read_json(original / "inputs.json")
    if members(old) != members(manifest) or old["ranks"] != manifest["ranks"]:
        raise ValueError("new exact binding changed operation members/ranks; do not reuse a different graph")
    out, ready = resume_replay_analysis(original, work / "analysis", iteration_map=binding.iteration_map,
        preparation_map=binding.preparation_map, rolling_options=rolling.RollingOptions(max_figures=0),
        html_views=(), include_critical_path=False, allow_uncalibrated_clock=True)
    pipeline = _gate(out, ready)
    rows, edges = graph.read_graph_artifact_nodes(out / "dep_graph_nodes.csv"), graph.read_graph_artifact_edges(out / "dep_graph_edges.csv")
    normalized, roots, tasks = normalize(read_json(out / "rolling/report.json"), mode="rolling", run_id=manifest["run_id"],
        rows=rows, edges=edges, pipeline=pipeline, binding_evidence=dict(binding.evidence, identity_exports=list(capture.identity_exports)),
        merge_metrics=waits.read_csv(out / "merge_summary.csv"))
    if any(hashlib.sha256((source / name).read_bytes()).hexdigest() != value for name, value in hashes.items()):
        raise ValueError("consumer source changed during replay")
    publish_final_report(out, root / "report", normalized, roots, tasks)
    write_json(root / "diagnosis-consumer.json", dict(pipeline_passed=True, files=hashes,
        source=str(source), original_capture_reused=True, replay_gates_revalidated=True, unix_ns=time.time_ns()))
    print(json.dumps(dict(status="passed", candidates=len(normalized["candidates"]),
        chains=normalized["propagation"]["chain_count"], quality=normalized["quality"])), flush=True)


if __name__ == "__main__":
    main()
