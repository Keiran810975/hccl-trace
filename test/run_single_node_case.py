#!/usr/bin/env python3
"""One bounded profiled single-node attempt; no device policy modifications."""
from __future__ import annotations

import argparse
import faulthandler
import gc
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import time

from single_node_capture import bind, actual_windows
from single_node_random_suite import validate_case, evaluate_temporal_localization
from diagnosis.run_diagnosis import run_pipeline, resume_replay_analysis
from diagnosis.rolling_diagnosis import RollingOptions


def terminate(process, directory):
    (directory / "private/stop").touch()
    if process.poll() is None:
        os.killpg(process.pid, signal.SIGTERM)
        try:
            process.wait(timeout=20)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
            process.wait()
    # Only PIDs recorded as our spawned background process are eligible for cleanup.
    for path in (directory / "private").glob("rank-*.jsonl"):
        for line in path.read_text().splitlines():
            record = json.loads(line)
            if record["event"] == "background_spawn":
                try:
                    command = Path("/proc/{}/cmdline".format(record["pid"])).read_bytes().split(b"\0")
                    if str(directory / "private").encode() in command:
                        os.killpg(record["pid"], signal.SIGTERM)
                except ProcessLookupError:
                    pass
                except FileNotFoundError:
                    pass


def stop_own_attempt(directory):
    directory = Path(directory).resolve()
    (directory / "private/stop").touch()
    record = json.loads((directory / "runner.json").read_text())
    try:
        command = Path("/proc/{}/cmdline".format(record["pid"])).read_bytes().split(b"\0")
        if str(directory).encode() not in command or not any(b"run_single_node_case.py" in arg for arg in command):
            raise ValueError("runner PID no longer belongs to this attempt")
        os.kill(record["pid"], signal.SIGTERM)
    except FileNotFoundError:
        pass


def run(args):
    case = json.loads(args.case.read_text())
    validate_case(case)
    if args.resume_analysis:
        return resume(args, case)
    devices = [int(d) for d in args.devices.split(",")]
    if len(devices) != 4 or len(set(devices)) != 4:
        raise ValueError("exactly four distinct runtime devices required")
    directory = args.output.resolve()
    if shutil.disk_usage(directory.parent).free < 15 * 1024**3:
        raise ValueError("less than 15GiB free: refusing to fill the shared filesystem")
    directory.mkdir(exist_ok=False)
    for name in ("public", "private", "ascend_log", "workload_results", "msprof"):
        (directory / name).mkdir()
    (directory / "runner.json").write_text(json.dumps(dict(pid=os.getpid(), output=str(directory))) + "\n")
    (directory / "private/case.json").write_text(json.dumps(case, indent=2) + "\n")
    workload = dict(case["workload"])
    if args.preflight:
        if case["injection"]["kind"] != "normal":
            raise ValueError("preflight cannot silently alter an anomaly case")
        workload.update(warmup=1, iters=7)
    command = [sys.executable, "-m", "torch.distributed.run", "--nnodes=1", "--nproc-per-node=4",
               "--max-restarts=0", "--master-addr=127.0.0.1", "--master-port=" + str(args.port),
               str(Path(__file__).with_name("multinode_commmix_train.py")), "--no-barrier",
               "--bucket-mib", ",".join(map(str, workload["bucket_mib"])), "--seed", str(case["workload_seed"]),
               "--public-calls-dir", str(directory / "public"), "--single-case", str(directory / "private/case.json"),
               "--private-events-dir", str(directory / "private"), "--communication-worker", str(args.communication_worker)]
    command += ["--gemm-backend", args.gemm_backend]
    for key in ("blocks", "tokens", "hidden_size", "ffn_size", "warmup", "iters"):
        command += ["--" + key.replace("_", "-"), str(workload[key])]
    if args.communication_reference_probe:
        if not args.preflight:
            raise ValueError("communication-only probe cannot replace a formal experiment")
        command = command[:8] + [str(Path(__file__).with_name("single_node_reference_probe.py")),
                                 "--public-calls-dir", str(directory / "public")]
    if any(any(c.isspace() for c in arg) for arg in command):
        raise ValueError("msprof application arguments cannot contain whitespace")
    env = dict(os.environ, HCCL_WORKLOAD_DEVICES=args.devices, HCCL_STEP_TRACE="1", HCCL_TASK_SEMANTIC_TRACE="1",
               HCCL_OP_EXPANSION_MODE="HOST", OMP_NUM_THREADS="1", HCCL_CONNECT_TIMEOUT="120", HCCL_EXEC_TIMEOUT="120",
               ASCEND_GLOBAL_LOG_LEVEL="1", ASCEND_SLOG_PRINT_TO_STDOUT="0",
               ASCEND_PROCESS_LOG_PATH=str(directory / "ascend_log"),
               HCCL_WORKLOAD_RESULT_DIR=str(directory / "workload_results"))
    env.pop("ASCEND_RT_VISIBLE_DEVICES", None)
    for key in list(env):
        if key.startswith("HCCL_DIAG_INJECT_"):
            del env[key]
    launch = dict(case_id=case["case_id"], purpose="full_shape_mixed_preflight" if args.preflight else "formal_experiment",
                  workload=workload, devices=devices, command=command, started_unix_ns=time.time_ns(),
                  device_policy_changed=False, reference="previous_five_measured_iterations", gemm_backend=args.gemm_backend)
    launch["rolling_wait_index_version"] = getattr(run_pipeline, "rolling_wait_index_version", 0)
    launch["consumer_cyclic_gc_enabled"] = gc.isenabled()
    if args.communication_reference_probe:
        launch.update(purpose="communication_reference_preflight",
                      workload=dict(kind="AllReduce-only", blocks=1, bucket_mib=[1, 2, 4], warmup=1, iters=7,
                                    compute_included=False))
    (directory / "launch.json").write_text(json.dumps(launch, indent=2) + "\n")
    with (directory / "capture.log").open("x") as log:
        process = subprocess.Popen(["msprof", "--application=" + " ".join(command),
                                    "--output=" + str(directory / "msprof"), "--hccl=on", "--task-time=on", "--type=db"],
                                   env=env, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
        try:
            if process.wait(timeout=args.timeout):
                raise RuntimeError("msprof exited unsuccessfully")
        except BaseException:
            terminate(process, directory)
            raise
    results = [json.loads(p.read_text()) for p in (directory / "workload_results").glob("rank-*.json")]
    if len(results) != 4 or {r["rank"] for r in results} != set(range(4)) or any(
            r["status"] != "passed" or r["max_error"] != 0 for r in results):
        raise ValueError("foreground workload numerical result gate failed")
    if getattr(args, "capture_only", False):
        captured = dict(case_id=case["case_id"], status="captured_pending_diagnosis",
                        execution_success=True, workload_executions=1,
                        finished_unix_ns=time.time_ns())
        (directory / "capture-result.json").write_text(json.dumps(captured, indent=2) + "\n")
        return captured
    run_id = ("preflight-" if args.preflight else "") + case["case_id"]
    found = bind(directory, run_id)
    options = dict(html_views=(), rolling_options=RollingOptions(max_figures=0), include_critical_path=False) if args.compact_output else {}
    output, passed = run_pipeline(directory / "manifest.json", directory / "diagnosis",
                                  iteration_map=directory / "iteration-map.json",
                                  preparation_map=directory / "preparation-map.json" if (directory / "preparation-map.json").is_file() else None, **options)
    return finish(args, case, directory, output, passed, run_id, found)


def finish(args, case, directory, output, passed, run_id, found):
    launch = json.loads((directory / "launch.json").read_text())
    if not passed:
        raise ValueError("strict semantic/graph gate failed; stopping the suite")
    report = json.loads((output / "rolling/report.json").read_text())
    if report["status"] != "analyzed":
        raise ValueError("no comparable rolling task history; stopping the suite")
    windows = actual_windows(directory, run_id, case, found)
    (directory / "private/actual-windows.json").write_text(json.dumps(windows, indent=2) + "\n")
    evaluation = (dict(status="normal_control", diagnosis_success=None,
                       false_alarm=report["primary_source_candidate_id"] is not None,
                       slow_task_count=report["slow_task_count"], compared_task_count=report["compared_task_count"])
                  if case["injection"]["kind"] == "normal" else evaluate_temporal_localization(report, windows))
    (directory / "evaluation.json").write_text(json.dumps(evaluation, indent=2) + "\n")
    result = dict(case_id=case["case_id"], execution_success=True, strict_diagnosis_success=True,
                  temporal_evaluation=evaluation, diagnosis_directory=str(output),
                  finished_unix_ns=time.time_ns(), purpose=launch["purpose"], gemm_backend=args.gemm_backend,
                  analysis_resumed=bool(args.resume_analysis), workload_executions=1)
    (directory / "result.json").write_text(json.dumps(result, indent=2) + "\n")
    if args.compact_output:
        from single_node_retention import retain_case
        retained = retain_case(directory)
        result.update(retained_html=str(directory / "retained/dependency.html"),
                      injection=case["injection"],
                      injection_locations=retained["injection_locations"],
                      primary_source=retained["primary_source"],
                      retention_policy=retained["retention_policy"],
                      raw_diagnosis_removed=case["injection"]["kind"] != "normal")
        (directory / "result.json").write_text(json.dumps(result, indent=2) + "\n")
    return result


def resume(args, case):
    directory = args.output.resolve()
    if json.loads((directory / "private/case.json").read_text()) != case:
        raise ValueError("resume case differs from the captured workload")
    launch = json.loads((directory / "launch.json").read_text())
    if launch["gemm_backend"] != args.gemm_backend or launch["case_id"] != case["case_id"]:
        raise ValueError("resume compute/case configuration differs")
    if (directory / "retained").exists():
        raise ValueError("refusing to overwrite retained results")
    values = [json.loads(p.read_text()) for p in (directory / "workload_results").glob("rank-*.json")]
    if len(values) != 4 or {r["rank"] for r in values} != set(range(4)) or any(r["max_error"] != 0 or r["status"] != "passed" for r in values):
        raise ValueError("resume requires successful numerical results for all four ranks")
    previous = json.loads((directory / "runner.json").read_text())
    (directory / "runner.json").write_text(json.dumps(dict(pid=os.getpid(), output=str(directory),
        resumed_from_pid=previous["pid"], workload_rerun=False)) + "\n")
    if (directory / "failed.json").exists():
        (directory / "failed.json").rename(directory / ("offline-interrupted-" + str(time.time_ns()) + ".json"))
    run_id = ("preflight-" if args.preflight else "") + case["case_id"]
    output = directory / ("diagnosis-recovered-" + str(time.time_ns())) / run_id
    found = {r["rank"]: dict(offset=r["raw_to_profiler_offset_ns"])
             for r in json.loads((directory / "binding-evidence.json").read_text())["ranks"]}
    output, passed = resume_replay_analysis(directory / "diagnosis" / run_id, output,
        iteration_map=directory / "iteration-map.json", rolling_options=RollingOptions(max_figures=0), html_views=(),
        preparation_map=directory / "preparation-map.json" if (directory / "preparation-map.json").is_file() else None,
        include_critical_path=not args.compact_output)
    return finish(args, case, directory, output, passed, run_id, found)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--devices", default="1,3,5,7")
    parser.add_argument("--communication-worker", required=True, type=Path)
    parser.add_argument("--port", type=int, default=29724)
    parser.add_argument("--timeout", type=int, default=1800)
    parser.add_argument("--preflight", action="store_true")
    parser.add_argument("--gemm-backend", choices=("matmul", "grouped"), default="matmul")
    parser.add_argument("--communication-reference-probe", action="store_true")
    parser.add_argument("--compact-output", action="store_true",
                        help="Keep one native dependency excerpt and small evidence; preserve baseline raw data")
    parser.add_argument("--resume-analysis", action="store_true", help="Reuse passed replay artifacts; never rerun workload")
    parser.add_argument("--capture-only", action="store_true",
                        help="Capture real DB/logs and verify numerics, leaving diagnosis to an offline consumer")
    options = parser.parse_args()
    signal.signal(signal.SIGTERM, lambda *_: (_ for _ in ()).throw(KeyboardInterrupt("termination requested")))
    if options.compact_output:
        # The short-lived CSV/graph consumer holds its data explicitly and exits
        # per case. Avoid rescanning millions of live dictionaries; NPU workers exec fresh Python.
        gc.disable()
        os.environ["HCCL_DIAG_PROGRESS"] = "1"
        faulthandler.dump_traceback_later(60, repeat=True)
    try:
        print(json.dumps(run(options)), flush=True)
    except (ValueError, OSError, RuntimeError, subprocess.TimeoutExpired) as error:
        if options.output.is_dir():
            (options.output / "failed.json").write_text(json.dumps(dict(error=str(error), status="failed"), indent=2) + "\n")
        parser.exit(1, str(error) + "\n")
    except KeyboardInterrupt as error:
        if options.output.is_dir():
            (options.output / "failed.json").write_text(json.dumps(dict(error=str(error), status="interrupted")) + "\n")
        parser.exit(130, "single-node attempt interrupted\n")
