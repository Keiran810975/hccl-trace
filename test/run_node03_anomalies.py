"""SDMA-first Node0/Node3 continuation, gated on each complete restored report."""
from __future__ import annotations

import argparse
import ctypes
import fcntl
import hashlib
import json
from pathlib import Path
import shlex
import shutil
import socket
import subprocess
import sys
import time

from node03_gpt2_suite import build_plan, validate_plan
from run_node03_preflight import (LOCAL_PARENT, PEER_PARENT, PYTHON, container_command,
                                  execute, own_container, ssh, write)


ORDER = ("copy_contention", "communication_contention", "compute_contention", "bandwidth_limit", "progress_delay")


def ordered_cases():
    plan = build_plan()
    validate_plan(plan)
    cases = {c["injection"]["kind"]: c for c in plan["cases"]}
    return [cases[k] for k in ORDER]


def verify_report(report, restored):
    if (report.get("schema_version") != 2 or not report["quality"]["pipeline_passed"]
            or report["quality"]["rank_count"] != 8 or report["quality"]["notify_ambiguity_count"] != 0
            or report["quality"]["wait_count"] != report["quality"]["paired_wait_count"]
            or restored.get("status") != "passed" or restored.get("restored_nodes") != [0, 3]):
        raise ValueError("complete eight-rank schema2 diagnosis and both restorations are required")


def source_hashes(root):
    return {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(root.rglob("*")) if p.is_file() and "__pycache__" not in p.parts}


def select_remaining(previous, frozen):
    cases = ordered_cases()
    if previous is None:
        return cases, []
    state = json.loads((previous / "suite-state.json").read_text())
    completed = state.get("previous_completed", []) + state.get("cases", [])
    if (state.get("status") != "stopped" or state.get("completed") != len(state.get("cases", []))
            or not 0 < len(completed) < len(cases)
            or [c["case_id"] for c in completed] != [c["case_id"] for c in cases[:len(completed)]]):
        raise ValueError("continuation requires an ordered completed prefix from a stopped queue")
    consumers = lambda hashes: {k: v for k, v in hashes.items() if k.endswith(".py")
                               and k.startswith(("hccl/tools/diagnosis/", "hccl_trace/"))}
    if consumers(state["source_files"]) != consumers(frozen):
        raise ValueError("continuation cannot re-attest prior results with different diagnosis consumers")
    for prior, expected in zip(completed, cases):
        directory = Path(prior["directory"])
        if directory.parent != previous.parent or not directory.name.startswith("hccl-diagnose-node03-"):
            raise ValueError("prior result is outside the owned queue workspace")
        if json.loads((directory / "input/case.json").read_text()) != expected:
            raise ValueError("prior frozen experiment input differs")
        report = json.loads((directory / "report/root_causes.json").read_text())
        verify_report(report, json.loads((directory / "authorized-state.json").read_text()))
        evaluation = json.loads((directory / "evaluation.json").read_text())
        if (not evaluation["pipeline_passed"] or evaluation["case_id"] != expected["case_id"]
                or evaluation["candidate_count"] != len(report["candidates"])
                or not json.loads((directory / "cleanup-receipt.json").read_text())["restored_before_cleanup"]
                or any(not (directory / "report" / name).is_file() for name in ("execution.html", "root_causes.json", "propagation.html"))):
            raise ValueError("prior report, independent evaluation or restoration receipt is incomplete")
    return cases[len(completed):], completed


def resources(root, label, *, cards=tuple(range(8))):
    from run_tool_smoke import available
    for node in (0, 1):
        own_container(node)
        report = execute(ssh("npu-smi info") if node else ["npu-smi", "info"])
        (root / (label + "-node" + str(3 if node else 0) + ".txt")).write_text(report)
        if not available(report, list(cards)):
            raise RuntimeError("an external task or abnormal HBM appeared; no load started")
        parent = PEER_PARENT if node else str(LOCAL_PARENT)
        free = int(execute(ssh(shlex.join(["python3", "-c", "import shutil;print(shutil.disk_usage(" + repr(parent) + ").free)"]))
                           if node else ["python3", "-c", "import shutil;print(shutil.disk_usage(" + repr(parent) + ").free)"]))
        if free < 40 * 1024**3:
            raise RuntimeError("less than 40GiB working space; no load started")
        if node:
            busy = execute(ssh("test ! -e " + shlex.quote(parent + "/.hccl-diagnose-device-active.json") + " && echo clear")).strip()
        else:
            busy = "busy" if (LOCAL_PARENT / ".hccl-diagnose-device-active.json").exists() else "clear"
        if busy != "clear":
            raise RuntimeError("an owned device lease already exists")
        ports = "import socket; sockets=[]\nfor port in (29773,29774,29775,29776):\n s=socket.socket();s.bind(('0.0.0.0',port));sockets.append(s)\nprint('ports clear')"
        execute(ssh(shlex.join(["python3", "-c", ports])) if node else ["python3", "-c", ports])


def effect_summary(report, evaluation):
    matching = set(evaluation["hit_candidate_ids"])
    return dict(case_id=evaluation["case_id"], pipeline_passed=True,
                candidate_count=len(report["candidates"]), matching_source_count=len(matching),
                primary_hit=evaluation["primary_hit"], injection_windows=evaluation["windows"],
                matching_sources=[c for c in report["candidates"] if c["id"] in matching],
                external_clue_count=len(report["external_anomaly_clues"]),
                unresolved_observation_count=len(report["unresolved_observations"]),
                propagation=report["propagation"], physical_cause_proven=False,
                note="A complete diagnosis is not a successful localization. No matching source means unlocalized, not no injection effect.")


def run(args):
    root, historical = args.root.resolve(), args.historical_normal.resolve()
    if root.parent != LOCAL_PARENT or historical.parent != LOCAL_PARENT or socket.gethostname().split(".")[0] != "liteserver-560t-0":
        raise ValueError("only reviewed owned Node0 workspaces are accepted")
    baseline = json.loads((historical / "input/case.json").read_text())
    if baseline != build_plan()["cases"][0]:
        raise ValueError("historical normal workload does not match the frozen GPT workload")
    normal = json.loads((historical / "authorized-state.json").read_text())
    if normal.get("restored_nodes") != [0, 3]:
        raise ValueError("historical normal restoration is not verified")
    # The current analysis uses only each run's preceding five iterations. The
    # historical normal is NOT re-attested as analyzed by the new consumer.
    proof = json.loads((historical / "network-port-evidence.json").read_text())
    from node03_roce_window import baseline_active
    baseline_active(proof)
    frozen = source_hashes(root / "src")
    if frozen != json.loads((root / "deployment.json").read_text())["source_files"]:
        raise ValueError("prepared source differs from the deployment attestation")
    previous = args.continue_from.resolve() if args.continue_from else None
    if previous is not None and (previous.parent != LOCAL_PARENT or previous == root):
        raise ValueError("continuation must use a different owned stopped queue")
    selected, inherited = select_remaining(previous, frozen)
    state = dict(status="prechecking", job_name="hccl-diagnose", requested_anomalies=len(selected), completed=0,
                 order=[c["injection"]["kind"] for c in selected], cases=[], historical_normal=str(historical), normal_reanalyzed=False,
                 previous_queue=str(previous) if previous else None, previous_completed=inherited,
                 reference="each run's own preceding five measured iterations", source_files=frozen,
                 active_case=None, started_unix_ns=time.time_ns(), parent_pid=__import__("os").getpid())
    path = root / "suite-state.json"
    write(path, state)
    offset = int(root.name.rsplit("-", 1)[1])
    prefix = root.name.rsplit("-", 1)[0]
    try:
        for i, case in enumerate(selected, 1):
            if source_hashes(root / "src") != frozen:
                raise ValueError("source changed during queue")
            resources(root, "before-{}-1".format(i))
            time.sleep(30)
            resources(root, "before-{}-2".format(i))
            current = root.parent / (prefix + "-{:03d}".format(offset + i))
            current.mkdir()
            shutil.copytree(root / "src", current / "src")
            (current / "input").mkdir()
            shutil.copy2(root / "input/aicpu_hcomm.tar.gz", current / "input/aicpu_hcomm.tar.gz")
            write(current / "input/case.json", case)
            if case["injection"]["kind"] == "bandwidth_limit":
                write(current / "input/network-baseline.json", proof)
            peer = Path(PEER_PARENT) / current.name
            code = ("from pathlib import Path;import shutil,json;r=Path(" + repr(str(peer)) + ");r.mkdir();"
                    "shutil.copytree(Path(" + repr(str(Path(PEER_PARENT) / root.name / "src")) + "),r/'src');"
                    "(r/'input').mkdir();shutil.copy2(Path(" + repr(str(Path(PEER_PARENT) / root.name / "input/aicpu_hcomm.tar.gz")) + "),r/'input/aicpu_hcomm.tar.gz');"
                    "(r/'input/case.json').write_text(" + repr(json.dumps(case)) + ")")
            execute(ssh(shlex.join(["python3", "-c", code])), timeout=90)
            state.update(status="running", active_case=case["case_id"], active_directory=str(current))
            write(path, state)
            command = [sys.executable, str(current / "src/test/run_node03_authorized.py"), "--root", str(current),
                       "--gpt", "--formal-case", str(current / "input/case.json")]
            with (root / (case["case_id"] + ".log")).open("x") as log:
                subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, check=True, timeout=6500)
            restored = json.loads((current / "authorized-state.json").read_text())
            base = "/workspace/" + current.name
            observed = execute(container_command(base, 0, shlex.join([PYTHON, "-c",
                "import json;from pathlib import Path;from hccl.tools.diagnosis.report_exporter import validate_final;"
                "p=Path(" + repr(base + "/report") + ");validate_final(p);print((p/'root_causes.json').read_text())"])), timeout=180)
            report = json.loads(observed)
            verify_report(report, restored)
            # Read back original policies and official package hashes on both hosts,
            # not just a stale successful restoration receipt.
            from run_node03_authorized import root_command
            for node in (0, 3):
                location = (str(LOCAL_PARENT) if node == 0 else PEER_PARENT) + "/" + current.name
                check = ("import sys,json;from pathlib import Path;sys.path.insert(0," + repr(location + "/src/test") + ");"
                         "from node03_device_guard import Guard;g=Guard(Path(" + repr(location) + "));"
                         "s=json.loads(g.snapshot.read_text());assert s['phase']=='restored';g.verify_original(s);print('restored')")
                execute(root_command(node, ["python3", "-c", check]), timeout=180)
            evaluation = json.loads(execute(container_command(base, 0, shlex.join([PYTHON,
                base + "/src/test/node03_evaluate.py", "--root", base])), timeout=180))
            write(current / "evaluation.json", evaluation)
            write(current / "effect-summary.json", effect_summary(report, evaluation))
            state["cases"].append(dict(case_id=case["case_id"], directory=str(current),
                pipeline_passed=True, any_candidate_hit=evaluation["any_candidate_hit"],
                primary_hit=evaluation["primary_hit"], candidate_count=evaluation["candidate_count"],
                candidate_hit_count=evaluation["candidate_hit_count"], both_originals_read_back=True,
                files=[str(current / "report" / f) for f in ("execution.html", "root_causes.json", "propagation.html")]))
            state["completed"] = len(state["cases"])
            if case["injection"]["kind"] == "copy_contention":
                state["first_sdma_flow_passed"] = True
            write(path, state)
            # Cleanup only this case, after report validation, independent evaluation,
            # effect evidence and original policy/package readback all passed.
            for node in (0, 1):
                cleanup = ("from pathlib import Path;import shutil,json;r=Path(" + repr(base) + ");"
                           "assert json.loads((r/'security/restored.json').read_text())['restored'];"
                           "[shutil.rmtree(p) for p in (r/'capture',r/'peer-preflight') if p.is_dir()];"
                           "p=r/'node3-preflight.tar';p.unlink() if p.exists() else None")
                execute(container_command(base, node, shlex.join([PYTHON, "-c", cleanup])), timeout=180)
            write(current / "cleanup-receipt.json", dict(only_own_raw_removed=True, reports_retained=True,
                evaluated_before_cleanup=True, effect_summary_retained=True, restored_before_cleanup=True))
        state.update(status="completed", active_case=None, active_directory=None)
    except BaseException as error:
        state.update(status="stopped", error=str(error), subsequent_cases_not_started=True)
        raise
    finally:
        state["finished_unix_ns"] = time.time_ns()
        write(path, state)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--historical-normal", type=Path, required=True)
    parser.add_argument("--continue-from", type=Path, help="fresh attempt: validate and skip the completed prefix of a stopped queue")
    args = parser.parse_args()
    root = args.root.resolve()
    ctypes.CDLL(None).prctl(15, b"hccl-diagnose", 0, 0, 0)
    with (root / "suite.lock").open("x") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        run(args)


if __name__ == "__main__":
    main()
