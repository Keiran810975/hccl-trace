"""Ten fixed-position GPT SDMA replications; effect evidence is evaluated after sealing."""
from __future__ import annotations

import argparse
import csv
from decimal import Decimal
import fcntl
import json
from pathlib import Path
import shlex
import shutil
import signal
import socket
import subprocess
import time

if __package__:
    from .run_single_gpt40 import verify_snapshot, digest_case, evaluate, retain_and_cleanup
    from .run_gpt_three_anomalies import PARENT, PREVIOUS, PYTHON, capture, execute, bind_capture, digest
    from .gpt2_diagnosis_suite import WORKLOAD
    from .node03_device_guard import Guard, write
    from .run_tool_smoke import available
else:
    from run_single_gpt40 import verify_snapshot, digest_case, evaluate, retain_and_cleanup
    from run_gpt_three_anomalies import PARENT, PREVIOUS, PYTHON, capture, execute, bind_capture, digest
    from gpt2_diagnosis_suite import WORKLOAD
    from node03_device_guard import Guard, write
    from run_tool_smoke import available


ROOT = PARENT / "hccl-diagnose-single-20261104-800"


def plan():
    cases = []
    for repeat in range(1, 11):
        case = dict(schema_version=1, case_id="single-sdma03-{:02d}".format(repeat),
            topology=dict(nnodes=1, ranks_per_node=4), workload=dict(WORKLOAD, iters=50), workload_seed=20261028,
            injection=dict(kind="copy_contention", target_rank=0, iteration=25, bucket_selector_seed=20261102,
                duration_iters=1, copy_backend="acl_memcpy_async", buffer_mib=2048, active_timeout_seconds=5,
                background_processes=1, declared_affected_ranks=[0],
                start="selected_bucket_async_submit_return", stop="selected_iteration_device_synchronized"),
            experiment_contract=dict(profile="gpt-copy-window-v1", source_selection="frozen-single-dual-v1",
                numeric_reference="previous-five-measured-mean", warmup=10, measured=50))
        cases.append(dict(root=str(PARENT / ("hccl-diagnose-single-20261104-" + str(800 + repeat))), case=case))
    return dict(schema_version=1, profile="single-gpt-sdma10-npu03-v1", requested=10, cases=cases,
        cards=[0,1,2,3], runtime_devices=[1,3,5,7], new_baseline=False,
        fixed_successful_position_repetitions_not_random_location_accuracy=True,
        detector=dict(source_factor="1.5", mad_multiplier="3", propagation_factor="1.2", selection="single-dual-top1"),
        effect_gate=dict(minimum_slow_sdma_tasks=2, minimum_sdma_factor="2", require_actual_copy_spans=True),
        stop_on_ineffective_injection=True, stop_on_diagnosis_miss=False,
        analyzer_reads_injection_truth=False, never_replace_failed_cases=True)


def prepare(root):
    snapshot = verify_snapshot(root)
    build = json.loads((PREVIOUS / "build-receipt.json").read_text())
    if build["status"] != "built" or any(digest(root / "src" / name) != value
            for name, value in build["verified_current_producer_files"].items()):
        raise ValueError("current producers must match the attested Host/Device build")
    frozen = plan()
    for entry in frozen["cases"]:
        attempt = Path(entry["root"])
        attempt.mkdir(exist_ok=False)
        shutil.copytree(root / "src", attempt / "src")
        shutil.copytree(PREVIOUS / "deploy", attempt / "deploy")
        (attempt / "input").mkdir()
        shutil.copy2(PREVIOUS / "input/aicpu_hcomm.tar.gz", attempt / "input/aicpu_hcomm.tar.gz")
        if digest(attempt / "input/aicpu_hcomm.tar.gz") != build["device_sha256"] or any(
                digest(attempt / "deploy/lib64" / name) != value for name, value in build["host_libraries"].items()):
            raise ValueError("matching Host/Device files changed")
        write(attempt / "build-receipt.json", build)
        write(attempt / "deployment.json", dict(profile=frozen["profile"], cards=frozen["cards"]))
        shutil.copy2(root / "authorization.json", attempt / "authorization.json")
        write(attempt / "input/case.json", entry["case"])
        write(attempt / "owned-attempt.json", dict(root=str(attempt), suite=str(root), case_id=entry["case"]["case_id"]))
        for name in ("logs", "bin"):
            (attempt / name).mkdir()
    write(root / "plan.json", frozen)
    write(root / "prepared.json", dict(prepared=True, cases=10, no_device_changes=True,
        plan_sha256=digest(root / "plan.json"), source_snapshot_sha256=digest(root / "source-snapshot.json"),
        source_files=len(snapshot["files"]), created_unix_ns=time.time_ns()))


def positive_overlap(task, spans):
    return sum(max(0, min(int(task["observed_stop_ns"]), stop) - max(int(task["observed_start_ns"]), begin))
               for begin, stop in spans)


def effect_evidence(attempt, case, evaluation):
    seal = json.loads((attempt / "diagnosis/sealed.json").read_text())
    if seal["truth_accessed"] is not False or any(digest(attempt / "diagnosis" / name) != value
            for name, value in seal["files"].items()):
        raise ValueError("effect inspection must follow sealed diagnosis")
    truth = json.loads((attempt / "capture/private/result.json").read_text())
    raw = truth.get("copy_host_envelopes_raw_ns", [])
    if (truth.get("backend") != "aclrtMemcpyAsync" or truth.get("max_error") != 0 or truth.get("buffer_mib") != 2048
            or truth.get("operations", 0) != len(raw) or not raw
            or any(not truth["started_raw_ns"] <= a < b <= truth["finished_raw_ns"] for a, b in raw)
            or any(raw[i][1] > raw[i+1][0] for i in range(len(raw)-1))):
        raise ValueError("completed, individually recorded ACL D2D operations required")
    binding = json.loads((attempt / "capture/binding-evidence.json").read_text())
    target = case["injection"]["target_rank"]
    evidence = [r for r in binding["ranks"] if r["rank"] == target and r["api_containment_verified"]]
    if len(evidence) != 1:
        raise ValueError("unique checked target-rank clock conversion required")
    offset = evidence[0]["raw_to_profiler_offset_ns"]
    spans = [[a+offset, b+offset] for a, b in raw]
    tasks = []
    with (attempt / "diagnosis/resource-comparisons.csv").open(newline="", encoding="utf-8-sig") as stream:
        for row in csv.DictReader(stream):
            if (row["node_id"] == case["case_id"] + "/node0" and row["user_rank"] == str(target)
                    and row["iteration"] == str(case["injection"]["iteration"]) and positive_overlap(row, spans) > 0):
                tasks.append(row)
    strong = [t for t in tasks if t["task_kind"] == "sdma" and t["duration_slow"] == "True"
              and Decimal(t["slowdown_factor"]) >= 2]
    result = dict(effect_gate_passed=len(strong) >= 2, overlap_resource_count=len(tasks),
        overlapping_slow_resource_count=sum(t["duration_slow"] == "True" for t in tasks),
        overlapping_sdma_at_least_2x_count=len(strong), strong_sdma_tasks=strong,
        actual_copy_operations=truth["operations"], actual_copy_envelopes_ns=spans,
        actual_activity_ns=truth["finished_raw_ns"]-truth["started_raw_ns"], active_stop_reason=truth["active_stop_reason"],
        criterion="at least two foreground HCCL SDMA tasks >=2x own preceding-five mean and 3MAD, overlapping completed copy API/sync spans",
        hardware_copy_duration_claimed=False, physical_causation_proven=False,
        diagnosis_sealed_before_truth_inspection=True, diagnosis_hit_not_an_effect_gate=evaluation["any_candidate_hit"])
    write(attempt / "effect-evidence.json", result)
    return result


def summarize(root, state):
    values = state["cases"]
    hits = sum(c["hits"] for c in values)
    total = sum(c["candidate_count"] for c in values)
    result = dict(status=state["status"], completed=len(values), requested=10, hits=hits, candidate_count=total,
        candidate_hit_fraction=hits/total if total else None, any_hit_cases=sum(c["any_candidate_hit"] for c in values),
        primary_hit_cases=sum(c["primary_hit"] for c in values),
        effective_cases=sum(c["effect_gate_passed"] for c in values), all_cases=values,
        fixed_position_replication=True, ineffective_and_missed_cases_not_removed=True,
        pending_cases=10-len(values), first_raw_and_diagnosis_misses_retained=True)
    write(root / "summary.json", result)
    fields = ["case_id", "hits", "candidate_count", "candidate_hit_fraction", "any_candidate_hit", "primary_hit",
              "effect_gate_passed", "overlapping_sdma_at_least_2x_count", "actual_copy_operations", "raw_retained"]
    with (root / "results.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(values)
    return result


def run(root):
    if (root / "state.json").exists():
        raise ValueError("never restart or duplicate the SDMA ten-case queue")
    frozen = json.loads((root / "plan.json").read_text())
    if frozen != plan() or digest(root / "plan.json") != json.loads((root / "prepared.json").read_text())["plan_sha256"]:
        raise ValueError("frozen SDMA plan changed")
    snapshot = verify_snapshot(root)
    state = dict(status="running", requested=10, completed=0, cases=[], active=None, started_unix_ns=time.time_ns(),
        plan_sha256=digest(root / "plan.json"), source_snapshot_sha256=digest(root / "source-snapshot.json"))
    write(root / "state.json", state)
    deadline = time.monotonic()+24*3600
    try:
        for number, entry in enumerate(frozen["cases"]):
            attempt = Path(entry["root"]); case = entry["case"]; base = "/workspace/" + attempt.name
            while not available(subprocess.check_output(["npu-smi", "info"], text=True, timeout=30), frozen["cards"]):
                if time.monotonic() > deadline or (root / "STOP").exists():
                    raise TimeoutError("bounded resource waiting stopped")
                state.update(status="waiting_resources", active=None, next_case=case["case_id"])
                write(root / "state.json", state)
                time.sleep(300)
            if time.monotonic() > deadline or (root / "STOP").exists():
                raise InterruptedError("SDMA suite stopped before a new capture")
            if (PARENT / ".hccl-diagnose-device-active.json").exists():
                raise ValueError("another owned device lease is active")
            if digest(attempt / "input/case.json") != digest_case(case) or any(
                    digest(attempt / "src" / name) != value for name, value in snapshot["files"].items()):
                raise ValueError("frozen per-case input or implementation changed")
            state.update(status="running", active=case["case_id"], active_root=str(attempt), phase="capturing")
            write(root / "state.json", state)
            capture(attempt, case, Guard(attempt))
            state["phase"] = "binding"; write(root / "state.json", state)
            bind_capture(attempt, case)
            state["phase"] = "diagnosing"; write(root / "state.json", state)
            execute(attempt, "diagnose", shlex.join([PYTHON, base+"/src/test/diagnose_single_gpt40.py",
                "--capture", base+"/capture", "--output", base+"/diagnosis"]), 1800)
            state["phase"] = "evaluating"; write(root / "state.json", state)
            result = evaluate(attempt, case)
            effect = effect_evidence(attempt, case, result)
            keep_raw = number == 0 or not result["any_candidate_hit"] or not effect["effect_gate_passed"]
            retain_and_cleanup(attempt, root, keep_raw=keep_raw)
            receipt_path = attempt / "retention-receipt.json"
            receipt = json.loads(receipt_path.read_text())
            receipt["files"]["effect-evidence.json"] = digest(attempt / "effect-evidence.json")
            write(receipt_path, receipt)
            state["cases"].append(dict(result, root=str(attempt), effect_gate_passed=effect["effect_gate_passed"],
                overlapping_sdma_at_least_2x_count=effect["overlapping_sdma_at_least_2x_count"],
                actual_copy_operations=effect["actual_copy_operations"], raw_retained=keep_raw,
                restoration_verified=True, retention_verified=True))
            state.update(completed=len(state["cases"]), active=None, phase="between_cases")
            if not effect["effect_gate_passed"]:
                state.update(status="ineffective_injection", phase="stopped_after_effect_gate", finished_unix_ns=time.time_ns())
                summarize(root, state); write(root / "state.json", state)
                return
            summarize(root, state); write(root / "state.json", state)
    except BaseException as error:
        state.update(status="failed", error=str(error), finished_unix_ns=time.time_ns())
        summarize(root, state); write(root / "state.json", state)
        raise
    finally:
        try:
            if __package__:
                from .remap_owned_npu_container import restore, ROOT as container_root
            else:
                from remap_owned_npu_container import restore, ROOT as container_root
            restored = restore(container_root)
            write(root / "container-restoration.json", restored)
            state["original_container_restored"] = restored["phase"] == "original_restored"
            write(root / "state.json", state)
        except BaseException as error:
            state.update(status="failed", container_restore_error=str(error), finished_unix_ns=time.time_ns())
            summarize(root, state); write(root / "state.json", state)
            raise
    state.update(status="completed", active=None, phase="finished", finished_unix_ns=time.time_ns())
    summarize(root, state); write(root / "state.json", state)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--prepare", action="store_true")
    args = parser.parse_args()
    if args.root.resolve() != ROOT or socket.gethostname().split(".")[0] != "liteserver-560t-0":
        raise ValueError("this queue is limited to the reviewed Node0 SDMA workspace")
    if args.prepare:
        prepare(ROOT)
    else:
        def interrupted(signum, frame):
            raise InterruptedError("SDMA queue interrupted")
        signal.signal(signal.SIGTERM, interrupted); signal.signal(signal.SIGINT, interrupted)
        with (ROOT / "queue.lock").open("x") as stream:
            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
            run(ROOT)
