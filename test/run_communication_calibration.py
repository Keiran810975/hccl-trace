"""Bounded Node0/Node3 exploration with per-case restoration and explicit gates."""
from __future__ import annotations

import argparse
import fcntl
import json
from pathlib import Path
import shlex
import shutil
import socket
import subprocess
import sys
import time

from communication_calibration import LEVELS, advance, cases
from run_node03_anomalies import resources, source_hashes, verify_report
from run_node03_preflight import LOCAL_PARENT, PEER_PARENT, PYTHON, container_command, execute, ssh, write


def inspect_case(current):
    base = "/workspace/" + current.name
    report = json.loads((current / "report/root_causes.json").read_text())
    verify_report(report, json.loads((current / "authorized-state.json").read_text()))
    from run_node03_authorized import root_command
    for node in (0, 3):
        location = (str(LOCAL_PARENT) if node == 0 else PEER_PARENT) + "/" + current.name
        code = ("import sys,json;from pathlib import Path;sys.path.insert(0," + repr(location + "/src/test") + ");"
                "from node03_device_guard import Guard;g=Guard(Path(" + repr(location) + "));"
                "s=json.loads(g.snapshot.read_text());assert s['phase']=='restored';g.verify_original(s)")
        execute(root_command(node, ["python3", "-c", code]), timeout=180)
    evaluation = json.loads(execute(container_command(base, 0, shlex.join([
        PYTHON, base + "/src/test/node03_evaluate.py", "--root", base])), timeout=180))
    write(current / "evaluation.json", evaluation)
    output = execute(container_command(base, 0, shlex.join([
        PYTHON, "-m", "test.communication_impact", "--root", base])), timeout=240)
    impact = json.loads(output)
    return evaluation, impact


def prepare_attempt(root, index, case, normal):
    prefix, start = root.name.rsplit("-", 1)
    current = root.parent / (prefix + "-{:03d}".format(int(start) + index))
    current.mkdir()
    shutil.copytree(root / "src", current / "src")
    (current / "input").mkdir()
    shutil.copy2(root / "input/aicpu_hcomm.tar.gz", current / "input/aicpu_hcomm.tar.gz")
    write(current / "input/case.json", case)
    if case["injection"]["kind"] == "bandwidth_limit":
        if normal is None:
            raise ValueError("a fresh foreground-only normal port observation is required")
        proof = json.loads((normal / "network-port-evidence.json").read_text())
        from node03_roce_window import baseline_active
        baseline_active(proof)
        write(current / "input/network-baseline.json", proof)
    peer = Path(PEER_PARENT) / current.name
    code = ("import shutil,json;from pathlib import Path;r=Path(" + repr(str(peer)) + ");r.mkdir();"
            "q=Path(" + repr(str(Path(PEER_PARENT) / root.name)) + ");"
            "shutil.copytree(q/'src',r/'src');(r/'input').mkdir();"
            "shutil.copy2(q/'input/aicpu_hcomm.tar.gz',r/'input/aicpu_hcomm.tar.gz');"
            "(r/'input/case.json').write_text(" + repr(json.dumps(case)) + ")")
    execute(ssh(shlex.join(["python3", "-c", code])), timeout=90)
    return current


def free_space(node):
    parent = PEER_PARENT if node else str(LOCAL_PARENT)
    query = ["python3", "-c", "import shutil;print(shutil.disk_usage(" + repr(parent) + ").free)"]
    return int(execute(ssh(shlex.join(query)) if node else query))


def protected_run(command, log, *, timeout=6500):
    """Do not let a shared filesystem fill while retaining one full replay."""
    process = subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT)
    deadline = time.monotonic() + timeout
    try:
        while process.poll() is None:
            if time.monotonic() > deadline:
                raise TimeoutError("protected attempt exceeded its bounded lifetime")
            if any(free_space(n) < 8 * 1024**3 for n in (0, 1)):
                raise RuntimeError("8GiB emergency reserve reached; cancelling only this attempt")
            time.sleep(5)
        if process.returncode:
            raise subprocess.CalledProcessError(process.returncode, command)
    except BaseException:
        if process.poll() is None:
            process.terminate()  # The authorized wrapper cleans captures and restores both leases.
            process.wait(timeout=650)
        raise


def wait_for_archive(root, current, state, path):
    state.update(status="awaiting_verified_archive", active_directory=str(current))
    write(path, state)
    deadline = time.monotonic() + 3600
    ack = current / "offload-receipt.json"
    while not ack.exists():
        if time.monotonic() > deadline:
            raise TimeoutError("local verified backup did not arrive; no next experiment started")
        time.sleep(2)
    receipt = json.loads(ack.read_text())
    if (receipt.get("status") != "verified" or receipt.get("case_directory") != str(current)
            or not receipt.get("local_archive_sha256") or not receipt.get("file_hashes_verified")
            or not receipt.get("owned_raw_removed") or not receipt.get("local_report_files")):
        raise ValueError("incomplete local replay backup and cleanup receipt")


def reuse_completed_normal(previous, frozen):
    if previous.parent != LOCAL_PARENT or previous.name == "hccl-diagnose-node03-20261101-200":
        raise ValueError("reused normal must be a completed owned attempt")
    if json.loads((previous / "input/case.json").read_text()) != cases()[0]:
        raise ValueError("reused normal differs from the exact frozen workload")
    # Only post-run auditing/orchestration fixes may differ. Never re-attest
    # a normal report produced by different diagnostic or workload code.
    allowed = {"test/communication_impact.py", "test/run_communication_calibration.py",
               "test/follow_communication_calibration.py", "test/test_communication_calibration.py",
               "test/test_run_communication_calibration.py", "test/test_follow_communication_calibration.py"}
    original = source_hashes(previous / "src")
    if {k: v for k, v in original.items() if k not in allowed} != {k: v for k, v in frozen.items() if k not in allowed}:
        raise ValueError("reused normal requires identical diagnostic, producer and workload sources")
    report = json.loads((previous / "report/root_causes.json").read_text())
    verify_report(report, json.loads((previous / "authorized-state.json").read_text()))
    evaluation = json.loads((previous / "evaluation.json").read_text())
    impact = json.loads((previous / "communication-impact.json").read_text())
    if (report["run_id"] != cases()[0]["case_id"] or evaluation["case_id"] != report["run_id"]
            or not evaluation["pipeline_passed"] or evaluation["windows"]
            or impact["injection_kind"] != "normal" or impact["actual_windows"]
            or evaluation["candidate_count"] != len(report["candidates"])):
        raise ValueError("normal report and independent audit disagree")
    receipt = json.loads((previous / "offload-receipt.json").read_text())
    if (receipt.get("status") != "verified" or not receipt.get("file_hashes_verified")
            or len(receipt.get("local_archive_sha256", [])) != 2):
        raise ValueError("reused normal requires both independently verified replay archives")
    for node in (0, 1):
        base = "/workspace/" + previous.name
        code = ("import json;from pathlib import Path;r=Path(" + repr(base) + ");"
                "a=[json.loads(p.read_text()) for p in (r/'gpt-output/workload_results').glob('rank-*.json')];"
                "assert len(a)==4 and {x['rank'] for x in a}==set(" + repr(list(range(4, 8) if node else range(4))) + ");"
                "assert all(x['status']=='passed' and x['world_size']==8 and x['warmup']==10 and x['iters']==50 for x in a)")
        execute(container_command(base, node, shlex.join([PYTHON, "-c", code])), timeout=90)
    return dict(kind="normal", level=None, directory=str(previous), case_id=evaluation["case_id"],
                status=impact["status"], primary_hit=evaluation["primary_hit"],
                any_candidate_hit=evaluation["any_candidate_hit"], candidate_hit_count=evaluation["candidate_hit_count"],
                candidate_count=evaluation["candidate_count"], reused_completed_normal=True,
                raw_replay_archived=True, normal_false_positive_candidate_count=len(report["candidates"]))


def run(root, *, allow_other_cards=False, archive_between_cases=False, reuse_normal=None):
    if root.parent != LOCAL_PARENT or socket.gethostname().split(".")[0] != "liteserver-560t-0":
        raise ValueError("only the owned Node0 workspace is allowed")
    frozen = source_hashes(root / "src")
    if frozen != json.loads((root / "deployment.json").read_text())["source_files"]:
        raise ValueError("consumer snapshot changed after deployment")
    path = root / "calibration-state.json"
    if path.exists():
        raise ValueError("do not restart a used calibration; inspect state and retained evidence")
    state = dict(status="prechecking", evidence_class="exploratory", attempts=[], active_case=None,
                 maximum_runs=len(cases()), source_files=frozen, original_results_replaced=False,
                 blocked=["progress_delay: communication-internal hook not yet device-validated"],
                 started_unix_ns=time.time_ns())
    state.update(resource_scope="target_whole_cards_4_7" if allow_other_cards else "whole_hosts",
                 other_tasks_not_stopped=True, archive_between_cases=archive_between_cases,
                 minimum_start_free_gib=40, emergency_reserve_gib=8)
    write(path, state)
    normal = None
    try:
        if reuse_normal is not None:
            normal = reuse_normal.resolve()
            inherited = reuse_completed_normal(normal, frozen)
            state.update(normal_directory=str(normal), normal_reused=True, attempts=[inherited])
            write(path, state)
        while True:
            selected = None
            if normal is None:
                selected = cases()[0]
            else:
                for kind in LEVELS:
                    decision = advance(state["attempts"], kind)
                    if decision["action"] == "run":
                        key = "matrix_size" if kind == "compute_contention" else "limit_mbps" if kind == "bandwidth_limit" else "buffer_mib"
                        selected = next(c for c in cases() if c["injection"]["kind"] == kind
                                        and c["injection"][key] == decision["level"])
                        break
                if selected is None:
                    state.update(status="exploration_complete", independent_validation_not_run=True)
                    break
            if len(state["attempts"]) >= state["maximum_runs"]:
                raise RuntimeError("predeclared exploration bound reached")
            if source_hashes(root / "src") != frozen:
                raise ValueError("source changed during calibration")
            cards = (4, 5, 6, 7) if allow_other_cards else tuple(range(8))
            resources(root, "attempt{}-idle1".format(len(state["attempts"]) + 1), cards=cards)
            time.sleep(30)
            resources(root, "attempt{}-idle2".format(len(state["attempts"]) + 1), cards=cards)
            for node in (0, 1):
                if free_space(node) < 40 * 1024**3:
                    raise RuntimeError("one-at-a-time replay requires 40GiB before capture")
            current = prepare_attempt(root, len(state["attempts"]) + 1, selected, normal)
            state.update(status="running", active_case=selected["case_id"], active_directory=str(current))
            write(path, state)
            with (root / (selected["case_id"] + ".log")).open("x") as log:
                protected_run([sys.executable, str(current / "src/test/run_node03_authorized.py"),
                    "--root", str(current), "--gpt", "--formal-case", str(current / "input/case.json"),
                    "--communication-calibration"], log)
            evaluation, impact = inspect_case(current)
            kind = selected["injection"]["kind"]
            level = next((selected["injection"][k] for k in ("matrix_size", "limit_mbps", "buffer_mib")
                          if k in selected["injection"]), None)
            state["attempts"].append(dict(kind=kind, level=level, directory=str(current),
                case_id=selected["case_id"], status=impact["status"],
                primary_hit=evaluation["primary_hit"], any_candidate_hit=evaluation["any_candidate_hit"],
                candidate_hit_count=evaluation["candidate_hit_count"], candidate_count=evaluation["candidate_count"],
                raw_and_debug_retained=True, original_policies_read_back=True))
            state.update(active_case=None, active_directory=None)
            if kind == "normal":
                normal = current
                state["normal_directory"] = str(normal)
            elif impact["status"] == "communication_effect_observed" and not evaluation["primary_hit"]:
                state.update(status="diagnosis_refinement_needed", reason="effect observed but top1 missed; retain input for offline analysis, do not hide this attempt")
                break
            if archive_between_cases:
                wait_for_archive(root, current, state, path)
            write(path, state)
    except BaseException as error:
        state.update(status="stopped", error=str(error), no_automatic_resubmission=True)
        if isinstance(error, subprocess.CalledProcessError):
            state.update(command_exit_code=error.returncode, command_stderr=(error.stderr or "")[-6000:])
        raise
    finally:
        state["finished_unix_ns"] = time.time_ns()
        write(path, state)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--allow-other-cards", action="store_true", help="requires explicit user authorization; never stops unrelated tasks")
    parser.add_argument("--archive-between-cases", action="store_true", help="wait for independently hash-verified local backup before the next capture")
    parser.add_argument("--reuse-normal", type=Path, help="reuse an archived completed normal with identical diagnosis and workload sources; never restart a failed queue")
    args = parser.parse_args()
    with (args.root / "calibration.lock").open("x") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        run(args.root.resolve(), allow_other_cards=args.allow_other_cards,
            archive_between_cases=args.archive_between_cases, reuse_normal=args.reuse_normal)


if __name__ == "__main__":
    main()
