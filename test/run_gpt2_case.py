#!/usr/bin/env python3
"""Capture one GPT-2 run, diagnose independently, and retain only small receipts."""
from __future__ import annotations

import argparse
from collections import Counter
import csv
import hashlib
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "hccl/tools"))
from diagnosis.run_diagnosis import run_pipeline
from diagnosis.rolling_diagnosis import RollingOptions
if __package__:
    from .gpt2_diagnosis_suite import validate_case, evaluate, CANDIDATE_STATUSES
    from .single_node_capture import bind, actual_windows
else:
    from gpt2_diagnosis_suite import validate_case, evaluate, CANDIDATE_STATUSES
    from single_node_capture import bind, actual_windows


def write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    temporary.replace(path)


def gate_failure_evidence(diagnosis):
    merges = {}
    path = diagnosis / "merge_summary.csv"
    if path.is_file():
        with path.open(encoding="utf-8-sig", newline="") as f:
            for row in csv.DictReader(f):
                merges.setdefault(row["node_id"], {})[row["metric"]] = row["value"]
    gates = {}
    path = diagnosis / "run_summary.csv"
    if path.is_file():
        with path.open(encoding="utf-8-sig", newline="") as f:
            gates = {row["metric"]: row["value"] for row in csv.DictReader(f)}
    reasons = []
    for node, values in merges.items():
        if values.get("merge_gate_passed") == "0":
            reasons.append("{} semantic merge failed: exact={}%, unmatched={}, duplicate executions={}".format(
                node, values.get("exact_match_rate_percent", "unknown"),
                values.get("unmatched_semantic", "0"), values.get("duplicate_profiler_execution_keys", "0")))
    reasons += [name + "=0" for name in ("graph_gate_passed", "topology_sync_gate_passed") if gates.get(name) == "0"]
    return dict(status="failed", merge_metrics=merges, graph_metrics=gates,
                reasons=reasons or ["strict replay failed; see original pipeline artifacts"],
                gates_relaxed=False, raw_capture_retained=True)


def retain(directory, destination, case, diagnosis, found, numerics):
    destination.mkdir(parents=True, exist_ok=False)
    report = json.loads((diagnosis / "rolling/report.json").read_text())
    if report["status"] != "analyzed":
        raise ValueError("no comparable measured history")
    windows = actual_windows(directory, case["case_id"], case, found)
    evaluation = evaluate(report, windows, normal=case["injection"]["kind"] == "normal")
    candidates = [r for r in report["root_causes"] if r["status"] in CANDIDATE_STATUSES]
    wait_ids = {key for root in candidates for key in root.get("affected_wait_graph_ids", [])}
    pipeline = json.loads((diagnosis / "pipeline_result.json").read_text())
    # Only immutable source evidence and selected paths are retained, not the whole task table/graph.
    small = {k: v for k, v in report.items() if k not in {"tasks", "root_causes", "wait_backtraces", "events"}}
    small.update(root_causes=candidates, wait_backtraces=[t for t in report["wait_backtraces"] if t["wait_graph_id"] in wait_ids],
                 slow_events=[e for e in report["events"] if e["is_slow"]])
    result = dict(case_id=case["case_id"], status="diagnosed", injection=case["injection"], evaluation=evaluation,
                  workload=case["workload"], actual_windows=windows, pipeline=pipeline,
                  execution_cohort=case.get("execution_cohort"),
                  timings=[dict(rank=r["rank"], parameters=r["parameters"], iteration_ns=r["iteration_ns"], losses=r["losses"],
                                bucket_structure=r["bucket_structure"], selected_bucket=r["selected_bucket"]) for r in numerics],
                  diagnosis_status=report["diagnosis_status"], finished_unix_ns=time.time_ns())
    write_json(destination / "result.json", result)
    write_json(destination / "diagnosis.json", small)
    for name in ("binding-evidence.json", "iteration-map.json", "preparation-map.json", "launch.json"):
        if (directory / name).is_file():
            shutil.copy2(directory / name, destination / name)
    shutil.copytree(directory / "public", destination / "public")
    shutil.copytree(directory / "private", destination / "injection", ignore=shutil.ignore_patterns("background.log"))
    shutil.copytree(directory / "workload_results", destination / "numerics")
    (destination / "capture-tail.txt").write_text((directory / "capture.log").read_text(errors="replace")[-16000:])
    files = {str(p.relative_to(destination)): hashlib.sha256(p.read_bytes()).hexdigest()
             for p in destination.rglob("*") if p.is_file()}
    write_json(destination / "retention-receipt.json", dict(case_id=case["case_id"], sha256=files,
        raw_artifacts_eligible_for_removal=True, diagnosis_fixed_before_truth_evaluation=True))
    return result


def cleanup(directory, destination):
    directory, destination = directory.resolve(), destination.resolve()
    owned = json.loads((directory / "owned-attempt.json").read_text())
    receipt = json.loads((destination / "retention-receipt.json").read_text())
    if str(directory) != owned["directory"] or receipt["case_id"] != owned["case_id"] or not receipt["raw_artifacts_eligible_for_removal"]:
        raise ValueError("cleanup ownership/receipt mismatch")
    for name, digest in receipt["sha256"].items():
        if hashlib.sha256((destination / name).read_bytes()).hexdigest() != digest:
            raise ValueError("retained evidence failed its checksum")
    names = ("msprof", "ascend_log", "foreground-dbs", "diagnosis", "public", "private", "workload_results")
    removed = []
    for name in names:
        path = directory / name
        if path.is_symlink() or any(p.is_symlink() for p in path.rglob("*")):
            raise ValueError("refusing linked artifact cleanup")
        if path.exists():
            shutil.rmtree(path)
            removed.append(name)
    for name in ("capture.log", "manifest.json", "iteration-map.json", "preparation-map.json", "binding-evidence.json"):
        path = directory / name
        if path.is_symlink():
            raise ValueError("refusing linked artifact cleanup")
        if path.is_file():
            path.unlink()
            removed.append(name)
    write_json(directory / "cleanup.json", dict(removed=removed, retained=str(destination), completed_unix_ns=time.time_ns()))


def run(args):
    case = json.loads(args.case.read_text())
    validate_case(case)
    if args.preflight and case["injection"]["kind"] != "normal":
        raise ValueError("preflight cannot alter anomaly experiments")
    directory = args.output.resolve()
    directory.mkdir(parents=True, exist_ok=False)
    for name in ("public", "private", "ascend_log", "workload_results", "msprof"):
        (directory / name).mkdir()
    write_json(directory / "owned-attempt.json", dict(case_id=case["case_id"], directory=str(directory), runner_pid=os.getpid()))
    write_json(directory / "private/case.json", case)
    source = Path(__file__).resolve().parents[1]
    command = [sys.executable, "-m", "torch.distributed.run", "--nnodes=1", "--nproc-per-node=4", "--max-restarts=0",
               "--master-addr=127.0.0.1", "--master-port=" + str(args.port), str(source / "test/gpt2_train.py"),
               "--case", str(args.case.resolve()), "--output", str(directory), "--data", str(args.data.resolve()),
               "--devices", args.devices, "--communication-worker", str(args.communication_worker.resolve())]
    if args.preflight:
        command += ["--warmup", "10", "--iters", "7"]
    if any(any(c.isspace() for c in arg) for arg in command):
        raise ValueError("msprof application arguments cannot contain spaces")
    env = dict(os.environ, HCCL_STEP_TRACE="1", HCCL_TASK_SEMANTIC_TRACE="1", HCCL_OP_EXPANSION_MODE="HOST",
               HCCL_EXEC_TIMEOUT="120", HCCL_CONNECT_TIMEOUT="120", OMP_NUM_THREADS="1",
               ASCEND_GLOBAL_LOG_LEVEL="1", ASCEND_SLOG_PRINT_TO_STDOUT="0",
               ASCEND_PROCESS_LOG_PATH=str(directory / "ascend_log"), HCCL_WORKLOAD_DEVICES=args.devices)
    env.pop("ASCEND_RT_VISIBLE_DEVICES", None)
    for name in list(env):
        if name.startswith("HCCL_DIAG_INJECT_"):
            del env[name]
    launch = dict(command=command, case_id=case["case_id"], workload=case["workload"], preflight=args.preflight,
                  execution_cohort=case.get("execution_cohort"),
                  devices=args.devices, source_revision=args.revision, started_unix_ns=time.time_ns(), device_policy_changed=False,
                  ascend_opp_path=env.get("ASCEND_OPP_PATH"), library_path=env.get("LD_LIBRARY_PATH"))
    write_json(directory / "launch.json", launch)
    if args.stop_file is not None and args.stop_file.exists():
        raise InterruptedError("suite stop requested before capture")
    with (directory / "capture.log").open("x") as log:
        process = subprocess.Popen(["msprof", "--application=" + " ".join(command), "--output=" + str(directory / "msprof"),
                                    "--hccl=on", "--task-time=on", "--type=db"], env=env, stdout=log,
                                   stderr=subprocess.STDOUT, start_new_session=True)
        write_json(directory / "capture-process.json", dict(pid=process.pid, argv=command))
        try:
            deadline = time.monotonic() + args.timeout
            while process.poll() is None:
                if args.stop_file is not None and args.stop_file.exists():
                    raise InterruptedError("suite stop requested")
                if time.monotonic() >= deadline:
                    raise subprocess.TimeoutExpired(command, args.timeout)
                time.sleep(.5)
            if process.returncode:
                raise RuntimeError("GPT-2/msprof capture failed; see capture.log")
        except BaseException:
            from run_single_node_case import terminate
            terminate(process, directory)
            raise
    numerics = [json.loads(p.read_text()) for p in sorted((directory / "workload_results").glob("rank-*.json"))]
    expected_iterations = 7 if args.preflight else case["workload"]["iters"]
    if (len(numerics) != 4 or {r["rank"] for r in numerics} != set(range(4))
            or any(r.get("warmup") != 10 or r.get("iters") != expected_iterations
                   or len(r["iteration_ns"]) != expected_iterations or len(r["losses"]) != expected_iterations for r in numerics)
            or any(r["status"] != "passed" or not r["parameter_update_observed"] for r in numerics)
            or any(r["parameter_samples"] != numerics[0]["parameter_samples"] for r in numerics)
            or any(not r.get("initialization", {}).get("parameter_sha256")
                   or r["initialization"] != numerics[0]["initialization"] for r in numerics)):
        raise ValueError("GPT-2 training finite/update/replica consistency gate failed")
    found = bind(directory, case["case_id"], ddp_capture=True, preserve_task_batches=True)
    diagnosis, passed = run_pipeline(directory / "manifest.json", directory / "diagnosis",
        iteration_map=directory / "iteration-map.json", preparation_map=directory / "preparation-map.json",
        html_views=(), rolling_options=RollingOptions(max_figures=0), include_critical_path=False)
    if not passed:
        evidence = gate_failure_evidence(diagnosis)
        write_json(directory / "gate-failure.json", evidence)
        raise ValueError("strict semantic/dependency gate failed: " + "; ".join(evidence["reasons"]))
    result = retain(directory, args.records.resolve(), case, diagnosis, found, numerics)
    if args.cleanup:
        cleanup(directory, args.records)
    print(json.dumps(dict(case_id=case["case_id"], status=result["status"], evaluation=result["evaluation"]), ensure_ascii=False), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--records", type=Path, required=True)
    parser.add_argument("--data", type=Path, required=True)
    parser.add_argument("--communication-worker", type=Path, required=True)
    parser.add_argument("--devices", default="1,3,5,7")
    parser.add_argument("--port", type=int, default=29683)
    parser.add_argument("--timeout", type=int, default=1800)
    parser.add_argument("--revision", default="unrecorded")
    parser.add_argument("--stop-file", type=Path)
    parser.add_argument("--preflight", action="store_true")
    parser.add_argument("--cleanup", action="store_true")
    args = parser.parse_args()
    def interrupted(signum, frame):
        raise InterruptedError("GPT-2 attempt interrupted")
    signal.signal(signal.SIGTERM, interrupted)
    signal.signal(signal.SIGINT, interrupted)
    try:
        run(args)
    except BaseException as error:
        if args.output.exists():
            write_json(args.output / "failure.json", dict(error=str(error), type=type(error).__name__, at_unix_ns=time.time_ns()))
        raise


if __name__ == "__main__":
    main()
