"""Six serial GPT-2 experiments; each capture, diagnosis, evaluation and cleanup is bounded."""
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
from run_node03_preflight import LOCAL_PARENT, PEER_PARENT, PYTHON, container_command, execute, ssh, write


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--validated-smoke", type=Path)
    parser.add_argument("--validated-replay", type=Path, help="separate successful read-only replay of the same smoke capture")
    parser.add_argument("--reuse-normal", type=Path, help="reuse a restored real 10+50 normal capture after successful audited CPU diagnosis")
    args = parser.parse_args()
    root = args.root.resolve()
    if root.parent != LOCAL_PARENT or socket.gethostname().split(".")[0] != "liteserver-560t-0":
        raise ValueError("reviewed own Node0 root required")
    ctypes.CDLL(None).prctl(15, b"hccl-diagnose", 0, 0, 0)
    with (root / "suite.lock").open("x") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        run_suite(args, root)


def run_suite(args, root):
    if bool(args.validated_smoke) == bool(args.reuse_normal):
        raise ValueError("choose either validated short training or a completed formal normal experiment")
    training = (args.reuse_normal or args.validated_smoke).resolve()
    if training.parent != LOCAL_PARENT or not training.name.startswith("hccl-diagnose-node03-"):
        raise ValueError("the reviewed owned training directory is required")
    smoke = json.loads((training / "authorized-state.json").read_text())
    if smoke["restored_nodes"] != [0, 3] or (not args.reuse_normal and smoke["status"] != "passed" and args.validated_replay is None):
        raise ValueError("real GPT smoke and verified restoration are required before formal runs")
    replay = args.reuse_normal or args.validated_replay or args.validated_smoke
    # CPU replay may fix a consumer bug, but cannot stand in for actual eight-rank training.
    program = ("import json,pathlib; s=pathlib.Path(" + repr("/workspace/" + training.name) + ");"
               "r=pathlib.Path(" + repr("/workspace/" + replay.name) + ");"
               "p=r/'report/root_causes.json';p=p if p.exists() else r/'preflight-report/root_causes.json';"
               "q=json.loads(p.read_text()); assert q['quality']['pipeline_passed'] and q['quality']['rank_count']==8;"
               "a=[json.loads(p.read_text()) for d in (s/'gpt-output/workload_results',s/'peer-preflight/gpt-output/workload_results') for p in d.glob('rank-*.json')];"
               "assert len(a)==8 and {x['rank'] for x in a}==set(range(8));"
               "assert all(x['status']=='passed' and x['world_size']==8 and x['warmup']==10 and x['iters']==" + str(50 if args.reuse_normal else 7) + " for x in a);"
               "print(q['run_id'])")
    if args.reuse_normal:
        program += ";assert q['run_id']==json.loads((s/'input/case.json').read_text())['case_id']"
    execute(container_command("/workspace/" + root.name, 0, shlex.join([PYTHON, "-c", program])), timeout=90)
    attestation = json.loads((training / "diagnosis-consumer.json").read_text()) if args.reuse_normal else None
    for source_file in sorted((root / "src/hccl/tools/diagnosis").glob("*.py")):
        source = source_file.relative_to(root)
        actual = hashlib.sha256((root / source).read_bytes()).hexdigest()
        expected = attestation["files"].get(str(source.relative_to("src"))) if attestation else hashlib.sha256((replay / source).read_bytes()).hexdigest()
        if actual != expected:
            raise ValueError("formal consumer differs from the independently validated replay")
    plan = build_plan()
    validate_plan(plan)
    if args.reuse_normal and json.loads((training / "input/case.json").read_text()) != plan["cases"][0]:
        raise ValueError("reused normal experiment differs from the exact frozen formal workload")
    if attestation and not attestation.get("pipeline_passed"):
        raise ValueError("normal consumer attestation must follow successful complete diagnosis")
    write(root / "plan.json", plan)
    state = dict(status="running", job_name="hccl-diagnose", requested_runs=6, completed=0,
                 cases=[], started_unix_ns=time.time_ns(), parent_pid=__import__("os").getpid())
    state_path = root / "suite-state.json"
    counter = int(root.name.rsplit("-", 1)[1])
    prefix = root.name.rsplit("-", 1)[0]
    try:
        for index, case in enumerate(plan["cases"], 1):
            name = prefix + "-{:03d}".format(counter + index)
            reused = bool(args.reuse_normal and index == 1)
            current = training if reused else root.parent / name
            name = current.name
            peer = Path(PEER_PARENT) / name
            state["active_case"] = case["case_id"]
            state["active_directory"] = str(current)
            write(state_path, state)
            if not reused:
                current.mkdir()
                shutil.copytree(root / "src", current / "src")
                (current / "input").mkdir()
                shutil.copy2(root / "input/aicpu_hcomm.tar.gz", current / "input/aicpu_hcomm.tar.gz")
                write(current / "input/case.json", case)
                if case["injection"]["kind"] == "bandwidth_limit":
                    proof = json.loads((Path(state["cases"][0]["directory"]) / "network-port-evidence.json").read_text())
                    write(current / "input/network-baseline.json", proof)
            # Clone only the frozen owned source and this case. The peer's old data is never overwritten.
            code = ("from pathlib import Path;import shutil,json; r=Path(" + repr(str(peer)) + ");r.mkdir();"
                    "shutil.copytree(Path(" + repr(str(Path(PEER_PARENT) / root.name / "src")) + "),r/'src');"
                    "(r/'input').mkdir();shutil.copy2(Path(" + repr(str(Path(PEER_PARENT) / root.name / "input/aicpu_hcomm.tar.gz")) + "),r/'input/aicpu_hcomm.tar.gz');"
                    "(r/'input/case.json').write_text(" + repr(json.dumps(case)) + ")")
            if not reused:
                execute(ssh(shlex.join(["python3", "-c", code])), timeout=90)
            log = (root / (case["case_id"] + ".log")).open("x")
            try:
                command = [sys.executable, str(current / "src/test/run_node03_authorized.py"), "--root", str(current),
                           "--gpt", "--formal-case", str(current / "input/case.json")]
                if not reused:
                    result = subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, timeout=6500)
                    if result.returncode:
                        raise RuntimeError("formal capture/diagnosis/restoration failed for " + case["case_id"])
                base = "/workspace/" + name
                evaluated = json.loads(execute(container_command("/workspace/" + root.name, 0, shlex.join([PYTHON,
                    "/workspace/" + root.name + "/src/test/node03_evaluate.py", "--root", base])), timeout=120))
                evaluated.update(status="diagnosed", directory=str(current),
                                 reused_completed_normal=reused,
                                 files=[str(current / "report" / f) for f in ("execution.html", "root_causes.json", "propagation.html")])
                write(current / "evaluation.json", evaluated)
                state["cases"].append(evaluated)
                state["completed"] = len(state["cases"])
                write(state_path, state)
                # Only new raw captures created by this case are removed, after report/evaluation and restoration passed.
                for node in (0, 1):
                    cleanup = ("from pathlib import Path;import shutil; r=Path(" + repr(base) + ");"
                               "assert (r/'security/restored.json').exists();"
                               "[shutil.rmtree(p) for p in (r/'capture',r/'peer-preflight') if p.is_dir()];"
                               "p=r/'node3-preflight.tar';p.unlink() if p.exists() else None")
                    execute(container_command(base, node, shlex.join([PYTHON, "-c", cleanup])), timeout=180)
            finally:
                log.close()
        state.update(status="completed", active_case=None, active_directory=None)
    except BaseException as error:
        state.update(status="stopped", error=str(error))
        raise
    finally:
        state["finished_unix_ns"] = time.time_ns()
        write(state_path, state)


if __name__ == "__main__":
    main()
