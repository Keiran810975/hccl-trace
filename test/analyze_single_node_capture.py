#!/usr/bin/env python3
"""Run the same strict diagnosis on a transported, numerically verified capture."""
from __future__ import annotations

import argparse
import gc
import hashlib
import json
import os
from pathlib import Path
from types import SimpleNamespace

from single_node_capture import bind
from single_node_random_suite import validate_case
from run_single_node_case import finish
from diagnosis.run_diagnosis import run_pipeline
from diagnosis.rolling_diagnosis import RollingOptions


def analyze(directory):
    directory = directory.resolve()
    captured = json.loads((directory / "capture-result.json").read_text())
    case = json.loads((directory / "private/case.json").read_text())
    validate_case(case)
    launch = json.loads((directory / "launch.json").read_text())
    if (captured.get("status") != "captured_pending_diagnosis"
            or not captured.get("execution_success") or captured.get("workload_executions") != 1
            or captured["case_id"] != case["case_id"] or launch["case_id"] != case["case_id"]
            or launch["workload"] != case["workload"] or launch["purpose"] != "formal_experiment"
            or launch["gemm_backend"] != "grouped" or launch["devices"] != [1, 3, 5, 7]):
        raise ValueError("transported capture is not the frozen formal workload")
    for relative, expected in json.loads((directory / "transport-sha256.json").read_text()).items():
        path = (directory / ("capture-runner.json" if relative == "runner.json" and
                              (directory / "capture-runner.json").is_file() else relative)).resolve()
        if not path.is_relative_to(directory) or not path.is_file():
            raise ValueError("invalid transported input")
        if hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            raise ValueError("transport checksum differs: " + relative)
    values = [json.loads(p.read_text()) for p in (directory / "workload_results").glob("rank-*.json")]
    if (len(values) != 4 or {v["rank"] for v in values} != set(range(4))
            or any(v["status"] != "passed" or v["max_error"] != 0 for v in values)):
        raise ValueError("four successful numerical results required")
    if (directory / "retained").exists() or (directory / "foreground-dbs").exists():
        raise ValueError("refusing to overwrite an existing analysis")
    if not (directory / "capture-runner.json").exists():
        (directory / "runner.json").rename(directory / "capture-runner.json")
    (directory / "runner.json").write_text(json.dumps(dict(pid=os.getpid(), output=str(directory),
        analysis_location="local", workload_rerun=False)) + "\n")
    gc.disable()
    os.environ["HCCL_DIAG_PROGRESS"] = "1"
    found = bind(directory, case["case_id"])
    output, passed = run_pipeline(directory / "manifest.json", directory / "diagnosis",
        iteration_map=directory / "iteration-map.json", html_views=(),
        preparation_map=directory / "preparation-map.json" if (directory / "preparation-map.json").is_file() else None,
        rolling_options=RollingOptions(max_figures=0), include_critical_path=False)
    args = SimpleNamespace(gemm_backend=launch["gemm_backend"], resume_analysis=False, compact_output=True)
    result = finish(args, case, directory, output, passed, case["case_id"], found)
    result["analysis_location"] = "local_same_analyzer"
    (directory / "result.json").write_text(json.dumps(result, indent=2) + "\n")
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    args = parser.parse_args()
    result = analyze(args.directory)
    print(json.dumps(dict(case_id=result["case_id"], evaluation=result["temporal_evaluation"])), flush=True)
