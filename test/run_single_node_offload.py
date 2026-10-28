#!/usr/bin/env python3
"""Serial server capture/local diagnosis handoff for the frozen 21-case plan."""
from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import re
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
import tarfile
import time

from run_single_node_suite import host_is_idle, write_json, write_formal_summary, write_results


HOST_ROOT = Path("/home/commTeam/zjy/zjy-new-workspace/single-910c-random-20261024")
CONTAINER_ROOT = Path("/workspace/single-910c-random-20261024")
SOURCE = "src-formal-offload-20261025"
SSH = ["ssh", "-i", str(Path.home() / ".ssh/id_rsa_k1"), "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=yes",
       "-o", "ConnectTimeout=15", "-o", "ControlMaster=auto", "-o",
       "ControlPath=/private/tmp/codex-single-formal-20261025.sock", "-o", "ControlPersist=300",
       "commTeam@heter.2.heroism.win"]


def digest(path):
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def archive_case(identifier, completed):
    root = CONTAINER_ROOT
    case = root / "attempts" / identifier
    if case.parent != root / "attempts" or case.is_symlink():
        raise ValueError("invalid owned case directory")
    names = ["launch.json", "runner.json", "public", "private", "workload_results"]
    if completed:
        result = json.loads((case / "result.json").read_text())
        if not result["strict_diagnosis_success"] or not (case / "retained/dependency.html").is_file():
            raise ValueError("completed case lacks a valid retained graph")
        names += ["result.json", "evaluation.json", "retained"]
        names += [name for name in ("iteration-map.json", "preparation-map.json", "binding-evidence.json")
                  if (case / name).is_file()]
    else:
        if json.loads((case / "capture-result.json").read_text())["status"] != "captured_pending_diagnosis":
            raise ValueError("capture not completed")
        names += ["capture-result.json", "ascend_log"]
        for index in range(2):
            name = "host-precheck-{}.txt".format(index)
            shutil.copy2(root / (identifier + "-idle-{}.txt".format(index)), case / name)
            names.append(name)
    files = [p for name in names for p in ([case / name] if (case / name).is_file()
                                           else sorted((case / name).rglob("*"))) if p.is_file()]
    if not completed:
        dbs = sorted((case / "msprof").rglob("msprof_*.db"))
        if len(dbs) < 4:
            raise ValueError("expected at least four consolidated DBs; foreground selection remains strict")
        files += dbs + [db.parent / "host/start_info" for db in dbs]
    if any(p.is_symlink() or not p.resolve().is_relative_to(case) for p in files):
        raise ValueError("refusing linked/outside transport input")
    hashes = {str(p.relative_to(case)): digest(p) for p in files}
    write_json(case / "transport-sha256.json", hashes)
    files.append(case / "transport-sha256.json")
    destination = root / "transfers" / (identifier + ".tar.gz")
    destination.parent.mkdir(exist_ok=True)
    if not destination.exists():
        with tarfile.open(destination, "w:gz", compresslevel=1) as archive:
            for path in files:
                archive.add(path, arcname=str(path.relative_to(case)), recursive=False)
    print(json.dumps(dict(archive=str(destination), sha256=digest(destination), size=destination.stat().st_size)), flush=True)


def target_cards_idle(output):
    if any("No running processes found in NPU {} ".format(card) not in output for card in (4, 5, 6, 7)):
        return False
    memory = re.findall(r"\|\s*\d+\s+(\d+)\s*\|[^\n]*?\s(\d+)\s*/\s*65536\s*\|", output)
    if len(memory) != 16 or {int(p) for p, _ in memory} != set(range(16)):
        return False
    return all(int(value) < 4096 for physical, value in memory if int(physical) in range(8, 16))


def capture(identifier, allow_other_cards_busy=False):
    lock = (HOST_ROOT / "suite.lock").open("a")
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    inspect = json.loads(subprocess.check_output(["docker", "inspect", "zjy-new"], text=True))[0]
    devices = {d["PathOnHost"] for d in inspect["HostConfig"]["Devices"]}
    if (not inspect["State"]["Running"] or inspect["HostConfig"]["Privileged"]
            or not {"/dev/davinci{}".format(d) for d in (9, 11, 13, 15)} <= devices
            or not any(Path(m["Source"]).resolve() == HOST_ROOT.parent and m["Destination"] == "/workspace"
                       for m in inspect["Mounts"])):
        raise ValueError("owned container/mapping differs")
    for i in range(2):
        info = subprocess.check_output(["npu-smi", "info"], text=True, timeout=30)
        (HOST_ROOT / (identifier + "-idle-{}.txt".format(i))).write_text(info)
        if not (target_cards_idle(info) if allow_other_cards_busy else host_is_idle(info)):
            raise RuntimeError("selected resource scope occupied; no workload started")
        if i == 0:
            time.sleep(30)
    case_path = HOST_ROOT / "plan/private/cases" / (identifier + ".json")
    if json.loads(case_path.read_text())["case_id"] != identifier:
        raise ValueError("unknown planned case")
    directory = HOST_ROOT / "attempts" / identifier
    if directory.exists():
        raise ValueError("refusing to rerun an existing capture")
    source = CONTAINER_ROOT / SOURCE
    command = ["/project/venvs/hccl-py311/bin/python", str(source / "test/run_single_node_case.py"),
               "--case", str(CONTAINER_ROOT / "plan/private/cases" / (identifier + ".json")),
               "--output", str(CONTAINER_ROOT / "attempts" / identifier), "--devices", "1,3,5,7",
               "--communication-worker", str(CONTAINER_ROOT / "single_process_comm_load-v2"),
               "--gemm-backend", "grouped", "--capture-only"]
    shell = ("source /usr/local/Ascend/ascend-toolkit/set_env.sh\n"
             "export LD_LIBRARY_PATH=/workspace/nf-20261022/deploy/lib64:${LD_LIBRARY_PATH:-}\n" + shlex.join(command))
    with (HOST_ROOT / (identifier + "-capture-only.log")).open("x") as log:
        process = subprocess.run(["docker", "exec", "zjy-new", "timeout", "--signal=TERM", "--kill-after=30s", "2000s",
                                  "bash", "-lc", shell], stdout=log, stderr=subprocess.STDOUT, timeout=2100)
    if process.returncode:
        raise RuntimeError("capture failed: " + identifier)
    subprocess.run(["docker", "exec", "zjy-new", "/project/venvs/hccl-py311/bin/python", str(source / "test/run_single_node_offload.py"),
                    "--archive-capture", identifier], check=True)


def cleanup(identifier, expected_sha):
    root = CONTAINER_ROOT
    case = root / "attempts" / identifier
    if case.is_symlink() or case.parent != root / "attempts" or identifier.endswith("normal"):
        raise ValueError("cleanup limited to an owned anomaly capture")
    received = root / "transfers" / (identifier + "-receipt.json")
    receipt = json.loads(received.read_text())
    archive = root / "transfers" / (identifier + ".tar.gz")
    if (not receipt["strict_diagnosis_success"] or not receipt["browser_qa_passed"]
            or receipt["capture_archive_sha256"] != expected_sha or digest(archive) != expected_sha):
        raise ValueError("no verified local diagnosis/HTML receipt")
    for name in ("msprof", "ascend_log"):
        folder = case / name
        if folder.is_symlink() or any(p.is_symlink() for p in folder.rglob("*")):
            raise ValueError("refusing symlink cleanup")
    for name in ("msprof", "ascend_log"):
        folder = case / name
        if folder.exists():
            shutil.rmtree(folder)
    archive.unlink()
    shutil.copy2(received, case / "local-diagnosis-receipt.json")
    print(json.dumps(dict(case_id=identifier, raw_removed=True, receipt=str(received))))


def remote(arguments):
    command = ["python3", str(HOST_ROOT / SOURCE / "test/run_single_node_offload.py")] + arguments
    return subprocess.check_output(SSH + [shlex.join(command)], text=True, timeout=2400)


def transfer(command):
    subprocess.run(command, check=True, timeout=300)


def local_run(destination, allow_other_cards_busy=False):
    destination = destination.resolve()
    records = destination / "records"
    records.mkdir(exist_ok=True, parents=True)
    (destination / "html").mkdir(exist_ok=True)
    work = destination / ".work"
    work.mkdir(exist_ok=True)
    lock = (destination / ".offload.lock").open("a")
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    control = json.loads(subprocess.check_output(SSH + ["cat " + str(HOST_ROOT / "suite-state.json")], text=True))
    if control["status"] != "stopped":
        raise ValueError("old controller must be safely stopped first")
    plan = json.loads(subprocess.check_output(SSH + ["cat " + str(HOST_ROOT / "plan/suite.json")], text=True))
    state_path = records / "suite-state.json"
    state = dict(status="running", started=0, completed=0, requested=21, cases=[], analysis_mode="server_capture_local_consumer",
                 baseline_raw_directory=str(HOST_ROOT / "attempts/single-910c-4r-normal"))
    if state_path.exists():
        old = json.loads(state_path.read_text())
        if old.get("analysis_mode") == state["analysis_mode"]:
            state = old
    state.update(status="running", shared_host_execution_authorized=allow_other_cards_busy,
                 resource_scope="NPU4..7 whole cards" if allow_other_cards_busy else "whole host")
    scp = ["scp", "-i", str(Path.home() / ".ssh/id_rsa_k1"), "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=yes",
           "-o", "ControlPath=/private/tmp/codex-single-formal-20261025.sock"]
    repo = Path(__file__).resolve().parents[1]
    try:
        for entry in plan["cases"][state["completed"]:]:
            identifier = entry["case_id"]
            state.update(active_case=identifier, started=state["completed"] + 1)
            write_json(state_path, state)
            print("START", state["started"], identifier, flush=True)
            completed = any(c["case_id"] == identifier for c in control["cases"])
            archive = work / (identifier + ".tar.gz")
            directory = work / identifier
            locally_finished = (directory / "result.json").is_file() and (directory / "retained/dependency.html").is_file()
            if locally_finished:
                expected = subprocess.check_output(SSH + ["sha256sum " + str(HOST_ROOT / "transfers" / archive.name)],
                                                   text=True, timeout=60).split()[0]
                transport = dict(sha256=expected)
            elif completed:
                command = ["docker", "exec", "zjy-new", "/project/venvs/hccl-py311/bin/python",
                           str(CONTAINER_ROOT / SOURCE / "test/run_single_node_offload.py"), "--archive-completed", identifier]
                response = subprocess.check_output(SSH + [shlex.join(command)], text=True, timeout=300)
            else:
                response = remote(["--capture", identifier] + (["--allow-other-cards-busy"] if allow_other_cards_busy else []))
            if not locally_finished:
                transport = json.loads(response.strip().splitlines()[-1])
                transfer(scp + ["commTeam@heter.2.heroism.win:" + str(HOST_ROOT / "transfers" / archive.name), str(archive)])
            if digest(archive) != transport["sha256"]:
                raise ValueError("archive transport checksum differs")
            if not locally_finished:
                directory.mkdir(exist_ok=False)
                with tarfile.open(archive) as packed:
                    members = packed.getmembers()
                    if any(not (directory / m.name).resolve().is_relative_to(directory) or not m.isfile() for m in members):
                        raise ValueError("unsafe transport archive")
                    packed.extractall(directory, members=members, filter="data")
            if not completed and not locally_finished:
                with (records / (identifier + "-analysis.log")).open("x") as log:
                    subprocess.run([sys.executable, str(repo / "test/analyze_single_node_capture.py"), str(directory)],
                                   stdout=log, stderr=subprocess.STDOUT, check=True, timeout=900)
            result = json.loads((directory / "result.json").read_text())
            resource_scope = ("whole_host_idle_precheck" if completed else
                              "NPU4..7_idle_other_cards_allowed" if allow_other_cards_busy else "whole_host_idle_precheck")
            result["resource_scope"] = resource_scope
            target = records / identifier
            target.mkdir(exist_ok=True)
            for p in (directory / "retained").iterdir():
                if p.name != "dependency.html":
                    shutil.copy2(p, target / p.name)
            for name in ("launch.json", "binding-evidence.json", "preparation-map.json", "iteration-map.json",
                         "capture-result.json", "host-precheck-0.txt", "host-precheck-1.txt"):
                if (directory / name).is_file():
                    shutil.copy2(directory / name, target / name)
            for name in ("case.json", "actual-windows.json", "result.json"):
                if (directory / "private" / name).is_file():
                    shutil.copy2(directory / "private" / name, target / ("injection-" + name))
            for p in (directory / "workload_results").glob("rank-*.json"):
                shutil.copy2(p, target / ("numerics-" + p.name))
            html = destination / "html" / (identifier + ".html")
            shutil.copy2(directory / "retained/dependency.html", html)
            env = dict(__import__("os").environ,
                CHROME_PATH="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
                NODE_PATH="/Users/pigmilk/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules")
            qa = subprocess.check_output(["/Users/pigmilk/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node",
                str(repo / "test/check_single_node_retained_html.cjs"), str(html)], env=env, text=True, timeout=120)
            (target / "browser-qa.json").write_text(qa)
            receipt = dict(case_id=identifier, strict_diagnosis_success=result["strict_diagnosis_success"], browser_qa_passed=True,
                           html_sha256=digest(html), capture_archive_sha256=transport["sha256"], evaluation=result["temporal_evaluation"],
                           resource_scope=resource_scope)
            write_json(target / "transfer-receipt.json", receipt)
            if not completed:
                remote_receipt = HOST_ROOT / "transfers" / (identifier + "-receipt.json")
                transfer(scp + [str(target / "transfer-receipt.json"), "commTeam@heter.2.heroism.win:" + str(remote_receipt)])
                command = ["docker", "exec", "zjy-new", "/project/venvs/hccl-py311/bin/python",
                           str(CONTAINER_ROOT / SOURCE / "test/run_single_node_offload.py"), "--cleanup", identifier,
                           "--sha256", transport["sha256"]]
                subprocess.run(SSH + [shlex.join(command)], check=True, timeout=120)
            result["retained_html"] = str(html)
            result["capture_transport_sha256"] = transport["sha256"]
            state["cases"].append(result)
            state.update(completed=len(state["cases"]), active_case=None)
            write_json(state_path, state)
            write_formal_summary(destination, state["cases"])
            write_results(destination / "results.csv", state["cases"])
            shutil.rmtree(directory)
            archive.unlink()
            print("DONE", state["completed"], identifier, result["temporal_evaluation"].get("diagnosis_success"), flush=True)
        state.update(status="completed")
    except BaseException as error:
        state.update(status="stopped", error=str(error))
        raise
    finally:
        write_json(state_path, state)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--capture")
    mode.add_argument("--archive-capture")
    mode.add_argument("--archive-completed")
    mode.add_argument("--cleanup")
    mode.add_argument("--local-run", type=Path)
    parser.add_argument("--sha256")
    parser.add_argument("--allow-other-cards-busy", action="store_true",
                        help="Explicit authorization required: still demand whole NPU4..7 idle")
    args = parser.parse_args()
    if args.capture:
        capture(args.capture, args.allow_other_cards_busy)
    elif args.archive_capture or args.archive_completed:
        archive_case(args.archive_capture or args.archive_completed, bool(args.archive_completed))
    elif args.cleanup:
        cleanup(args.cleanup, args.sha256)
    else:
        local_run(args.local_run, args.allow_other_cards_busy)
