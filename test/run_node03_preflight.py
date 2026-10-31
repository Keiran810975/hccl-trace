"""Bounded Node0+Node3 eight-rank preflight in owned, nonprivileged containers."""
from __future__ import annotations

import argparse
import fcntl
import json
from pathlib import Path
import shlex
import shutil
import signal
import socket
import subprocess
import tarfile
import time


PYTHON = "/project/venvs/hccl-py311/bin/python"
PEER = "root@192.169.0.220"
LOCAL_PARENT = Path("/home/commTeam/zjy/zjy-new-workspace")
PEER_PARENT = "/home/zjy-new/workspace"
DEVICES = "1,3,5,7"


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n")
    temporary.replace(path)


def ssh(command):
    return ["ssh", "-i", str(Path.home() / ".ssh/KeyPair-f1dd.pem"), "-o", "IdentitiesOnly=yes",
            "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=yes", "-o", "ConnectTimeout=15", PEER, command]


def execute(argv, *, timeout=40):
    value = subprocess.run(argv, check=True, text=True, capture_output=True, timeout=timeout)
    return value.stdout


def own_container(node):
    command = ["docker", "inspect", "zjy-new"]
    value = json.loads(execute(ssh(shlex.join(command)) if node else command))[0]
    parent = PEER_PARENT if node else str(LOCAL_PARENT)
    if (value["HostConfig"]["Privileged"] or not value["State"]["Running"]
            or value["HostConfig"]["NetworkMode"] != "host"
            or not any(m["Source"] == parent and m["Destination"] == "/workspace" for m in value["Mounts"])):
        raise ValueError("unexpected owned container or workspace mapping")
    mapped = {d["PathOnHost"] for d in value["HostConfig"]["Devices"]}
    if not {"/dev/davinci" + str(d) for d in range(8, 16)} <= mapped:
        raise ValueError("four complete target cards must be mapped")
    return value["Id"]


def shell(base, node, command):
    runtime = "/workspace/gpt2-single-node3-20261029-001/a3-runtime" if node else "/workspace/gpt2-single-node0-50-20261029-001/a3-runtime"
    dependencies = "/workspace/gpt2-single-node3-20261029-001/deps" if node else "/workspace/gpt2-single-node0-50-20261029-001/deps"
    return ("source /usr/local/Ascend/ascend-toolkit/set_env.sh\n"
            "export ASCEND_OPP_PATH=" + runtime + "/opp\n"
            "export LD_LIBRARY_PATH=/workspace/nf-20261022/deploy/lib64:" + runtime + "/aarch64-linux/lib64:" + runtime + "/opp/built-in/op_impl/ai_core/tbe/op_tiling/lib/linux/aarch64:${LD_LIBRARY_PATH:-}\n"
            "export PYTHONPATH=" + base + "/src:" + dependencies + "\n"
            "export OMP_NUM_THREADS=1\n"
            "unset ASCEND_RT_VISIBLE_DEVICES\n" + command)


def container_command(base, node, command, seconds=360):
    argv = ["docker", "exec", "zjy-new", "timeout", "--signal=TERM", "--kill-after=20s", str(seconds) + "s",
            "bash", "-lc", shell(base, node, command)]
    return ssh(shlex.join(argv)) if node else argv


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--algorithm", choices=("default", "ring"), default="default")
    parser.add_argument("--size-mib", type=int, choices=(2, 32), default=2)
    parser.add_argument("--official-reference", action="store_true", help="numerics only: official libraries, no profiling or context holders")
    parser.add_argument("--op-expansion-mode", choices=("HOST", "AI_CPU"), default="HOST")
    parser.add_argument("--gpt", action="store_true", help="actual GPT-2 short training, 10 warmup + 7 measured")
    parser.add_argument("--protected-package", action="store_true", help="metadata: launched by the authorized Host/Device wrapper")
    parser.add_argument("--formal-case", type=Path, help="frozen input/case.json: one real 10+50 experiment")
    args = parser.parse_args()
    root = args.root.resolve()
    if (root.parent != LOCAL_PARENT or not root.name.startswith("hccl-diagnose-node03-")
            or socket.gethostname().split(".")[0] != "liteserver-560t-0"):
        raise ValueError("reviewed owned Node0 workspace required")
    lock = (root / "preflight.lock").open("x")
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    base = "/workspace/" + root.name
    if args.formal_case:
        if not args.gpt or args.formal_case.resolve() != root / "input/case.json":
            raise ValueError("formal GPT case must be the frozen owned input/case.json")
        from node03_gpt2_suite import build_plan
        formal_case = json.loads(args.formal_case.read_text())
        if formal_case not in build_plan()["cases"]:
            raise ValueError("formal case differs from the requested frozen six-case plan")
    state = dict(status="prechecking", job_name="hccl-diagnose", devices=DEVICES, physical_cards=[4, 5, 6, 7],
                 physical_chips=[9, 11, 13, 15], nodes=["node0", "node3"], started_unix_ns=time.time_ns(),
                 workload_is_formal_gpt=bool(args.formal_case), device_policy_changed=args.protected_package, gpt_short_validation=args.gpt and not args.formal_case)
    state.update(algorithm=args.algorithm, size_mib=args.size_mib, official_reference=args.official_reference,
                 op_expansion_mode=args.op_expansion_mode)
    state_path = root / "preflight-state.json"
    (root / "logs").mkdir()
    processes, holders, logs, clock_server, network_process = [], [], [], None, None
    measured = 50 if args.formal_case else 7
    case_name = "case.json" if args.formal_case else "normal.json"
    try:
        state["containers"] = [own_container(n) for n in (0, 1)]
        # A zero utilization figure alone is insufficient: require no process and idle HBM on both chips.
        from run_tool_smoke import available
        for check in (1, 2):
            for node in (0, 1):
                text = execute(ssh("npu-smi info") if node else ["npu-smi", "info"])
                (root / "logs" / ("node{}-idle{}.txt".format(3 if node else 0, check))).write_text(text)
                if not available(text, [4, 5, 6, 7]):
                    raise RuntimeError("target whole cards are not idle")
            if check == 1:
                time.sleep(30)
        if shutil.disk_usage(root).free < 30 * 1024**3:
            raise RuntimeError("insufficient local working space")
        hold_seconds, capture_seconds, analysis_seconds = (6000, 1800 if args.formal_case else 900, 2400 if args.formal_case else 1200) if args.gpt else (1200, 360, 400)
        for node in (() if args.official_reference else (0, 1)):
            command = shlex.join([PYTHON, base + "/src/test/device_context_hold.py", "--devices", DEVICES,
                                  "--directory", base + "/hold", "--seconds", str(hold_seconds)])
            log = (root / "logs" / ("hold-node{}.log".format(node))).open("x")
            logs.append(log)
            holders.append(subprocess.Popen(container_command(base, node, "export HCCL_STEP_TRACE=0 HCCL_TASK_SEMANTIC_TRACE=0\n" + command, hold_seconds + 30), stdout=log, stderr=subprocess.STDOUT))
        for node in (() if args.official_reference else (0, 1)):
            deadline = time.monotonic() + 150
            while True:
                command = ["docker", "exec", "zjy-new", "cat", base + "/hold/state.json"]
                observed = subprocess.run(ssh(shlex.join(command)) if node else command, capture_output=True, text=True, timeout=25)
                if observed.returncode == 0:
                    if json.loads(observed.stdout)["status"] != "holding":
                        raise RuntimeError("NPU holders failed")
                    break
                if holders[node].poll() is not None or time.monotonic() >= deadline:
                    raise RuntimeError("context reservation did not become ready")
                time.sleep(1)
        state["status"] = "capturing"
        write(state_path, state)
        run_id = root.name + "-preflight"
        if args.gpt:
            run_id = json.loads((root / "input" / case_name).read_text())["case_id"]
            from multinode_clock_probe import ProbeServer, raw_ns
            clock_server = ProbeServer("192.169.0.173", 29776, run_id, "node0", ["node3"])
            clock_server.__enter__()
            clock_data = dict(schema_version=1, clock="CLOCK_MONOTONIC_RAW", capture_id=run_id,
                              node_id="node0", reference_node="node0", before_raw_ns=raw_ns())
            def clock_probe(phase):
                command = [PYTHON, base + "/src/test/multinode_clock_probe.py", "probe", "--address", "192.169.0.173",
                           "--port", "29776", "--capture-id", run_id, "--node-id", "node3", "--phase", phase,
                           "--output", base + "/capture/nodes/node3/clock-" + phase + ".json"]
                execute(container_command(base, 1, shlex.join(command)), timeout=50)
            clock_probe("before")
        if args.formal_case:
            from run_node03_authorized import root_command
            query = ["python3", str(root / "src/test/node03_roce_window.py"), "query", "--root", str(root)]
            network_before = json.loads(execute(root_command(0, query)))
            if formal_case["injection"]["kind"] == "bandwidth_limit":
                log = (root / "logs/network.log").open("x")
                logs.append(log)
                command = query.copy()
                command[2] = "watch"
                network_process = subprocess.Popen(root_command(0, command), stdout=log, stderr=subprocess.STDOUT)
        for node in (0, 1):
            label = "node3" if node else "node0"
            capture = base + "/capture/nodes/" + label
            app = [PYTHON, "-m", "torch.distributed.run", "--nnodes=2", "--nproc-per-node=4", "--node-rank=" + str(node),
                   "--master-addr=192.169.0.173", "--master-port=29773", "--max-restarts=0",
                   base + "/src/examples/diagnosis_collectives.py", "--devices", DEVICES, "--warmup", "1", "--iterations", "7",
                   "--size-mib", str(args.size_mib), "--numerics-dir", base + "/numerics"]
            if args.gpt:
                output = base + "/gpt-output"
                execute(container_command(base, node, shlex.join([PYTHON, "-c", "from pathlib import Path;Path(" + repr(output + "/workload_results") + ").mkdir(parents=True)"])))
                data = "/workspace/gpt2-single-node3-20261029-001/data" if node else "/workspace/gpt2-single-node0-50-20261029-001/data"
                app = app[:9] + [base + "/src/test/gpt2_train.py", "--case", base + "/input/" + case_name, "--output", output,
                    "--data", data, "--devices", DEVICES, "--warmup", "10", "--iters", str(measured), "--coordination-port", "29774",
                    "--sdk-observations", capture + "/calls"]
            command = ("export HCCL_STEP_TRACE=" + ("0" if args.official_reference else "1") + " HCCL_TASK_SEMANTIC_TRACE=" + ("0" if args.official_reference else "1") + " HCCL_OP_EXPANSION_MODE=" + args.op_expansion_mode + "\n"
                       + ("export LD_LIBRARY_PATH=${LD_LIBRARY_PATH#/workspace/nf-20261022/deploy/lib64:}\n" if args.official_reference else "") +
                       "export HCCL_IF_IP=" + ("192.169.0.220" if node else "192.169.0.173") + " HCCL_SOCKET_IFNAME=enp23s0f3\n"
                       + ("export HCCL_ALGO='level0:ring;level1:ring;level2:ring'\n" if args.algorithm == "ring" else "unset HCCL_ALGO\n") +
                       "export HCCL_TRACE_RUN_ID=" + run_id + " HCCL_TRACE_NODE_ID=" + label + "\n"
                       "export HCCL_TRACE_CALLS_DIR=" + capture + "/calls ASCEND_PROCESS_LOG_PATH=" + capture + "/plog\n"
                       "export ASCEND_GLOBAL_LOG_LEVEL=1 ASCEND_SLOG_PRINT_TO_STDOUT=0 HCCL_EXEC_TIMEOUT=120 HCCL_CONNECT_TIMEOUT=120\n"
                       "export HCCL_IF_BASE_PORT=55000 HCCL_HOST_SOCKET_PORT_RANGE=55000-55127 HCCL_NPU_SOCKET_PORT_RANGE=55200-55327\n" +
                       (shlex.join(app) if args.official_reference else
                        shlex.join(["msprof", "--application=" + shlex.join(app), "--output=" + capture + "/msprof", "--hccl=on", "--task-time=on", "--type=db"])))
            log = (root / "logs" / ("capture-" + label + ".log")).open("x")
            logs.append(log)
            processes.append(subprocess.Popen(container_command(base, node, command, capture_seconds), stdout=log, stderr=subprocess.STDOUT))
        for process in processes:
            if process.wait(timeout=capture_seconds + 40):
                raise RuntimeError("a reference workload or profiler failed; check capture log")
        state["status"] = "captured"
        write(state_path, state)
        if args.gpt:
            clock_probe("after")
            if not clock_server.wait_for_after(5):
                raise RuntimeError("clock peer did not acknowledge completion")
            clock_data["after_raw_ns"] = raw_ns()
            metadata = dict(run_id=run_id, sdk_auxiliary_operation_types=["Broadcast"], nodes=[dict(node_id="node0", clock_probe_files=["nodes/node0/clock.json"]),
                dict(node_id="node3", clock_probe_files=["nodes/node3/clock-before.json", "nodes/node3/clock-after.json"])])
            program = "import pathlib,json;r=pathlib.Path(" + repr(base + "/capture") + ");(r/'nodes/node0/clock.json').write_text(" + repr(json.dumps(clock_data)) + ");(r/'capture.json').write_text(" + repr(json.dumps(metadata)) + ")"
            execute(container_command(base, 0, shlex.join([PYTHON, "-c", program])))
        if args.formal_case:
            network_after = json.loads(execute(root_command(0, query)))
            evidence = dict(node_id="node0", user_rank=0, physical_device_id=9, runtime_device_id=1,
                            foreground_only=formal_case["injection"]["kind"] == "normal", numerics_passed=False,
                            before=network_before, after=network_after, source_case_id=run_id)
        for node in (0, 1):
            expected = list(range(4, 8)) if node else list(range(4))
            check = ("import json,pathlib; p=pathlib.Path(" + repr(base + "/numerics") + ");"
                     "a=[json.loads(f.read_text()) for f in p.glob('rank-*.json')];"
                     "assert {r['user_rank'] for r in a}==set(" + repr(expected) + "), 'workload did not complete; msprof exit zero is not a numeric pass';"
                     "assert all(r['status']=='passed' and len(r['results'])==8 for r in a)")
            if args.gpt:
                check = ("import json,pathlib;p=pathlib.Path(" + repr(base + "/gpt-output/workload_results") + ");"
                         "a=[json.loads(f.read_text()) for f in p.glob('rank-*.json')];"
                         "assert {r['rank'] for r in a}==set(" + repr(expected) + ");"
                         "assert all(r['status']=='passed' and r['world_size']==8 and r['warmup']==10 and r['iters']==" + str(measured) +
                         " and r['parameter_update_observed'] and len(r['losses'])==" + str(measured) + " for r in a)")
            execute(container_command(base, node, shlex.join([PYTHON, "-c", check])), timeout=40)
        if args.formal_case:
            if network_process is not None and network_process.wait(timeout=60):
                raise RuntimeError("actual network limit window or restoration did not pass")
            evidence["numerics_passed"] = True
            write(root / "network-port-evidence.json", evidence)
        if args.official_reference:
            state.update(status="reference_numerics_passed", diagnosis_not_attempted=True)
            return
        # Transfer only this owned attempt; never traverse another container's files.
        archive = root / "node3-preflight.tar"
        with archive.open("xb") as stream:
            subprocess.run(ssh(shlex.join(["docker", "exec", "zjy-new", "tar", "-cf", "-", "-C", base,
                                          "capture/nodes/node3", "gpt-output" if args.gpt else "numerics"])), stdout=stream, check=True, timeout=90)
        unpack = root / "peer-preflight"
        unpack.mkdir()
        with tarfile.open(archive) as contents:
            for member in contents.getmembers():
                destination = (unpack / member.name).resolve()
                if unpack not in destination.parents or not (member.isfile() or member.isdir()):
                    raise ValueError("unsafe peer capture archive")
            contents.extractall(unpack)
        # Use the container for root-owned captures and publication; the host never changes permissions globally.
        program = ("import json,pathlib,shutil; r=pathlib.Path(" + repr(base) + ");"
                   "shutil.copytree(r/'peer-preflight/capture/nodes/node3',r/'capture/nodes/node3');"
                   "a=[json.loads(p.read_text()) for d in (r/'numerics',r/'peer-preflight/numerics') for p in d.glob('rank-*.json')];"
                   "assert {x['user_rank'] for x in a}==set(range(8)) and len(a)==8;"
                   "assert all(x['status']=='passed' and len(x['results'])==8 for x in a)")
        if args.gpt:
            program = ("import json,pathlib,shutil;r=pathlib.Path(" + repr(base) + ");"
                       "shutil.copytree(r/'peer-preflight/capture/nodes/node3',r/'capture/nodes/node3');"
                       "a=[json.loads(p.read_text()) for d in (r/'gpt-output/workload_results',r/'peer-preflight/gpt-output/workload_results') for p in d.glob('rank-*.json')];"
                       "assert len(a)==8 and {x['rank'] for x in a}==set(range(8));"
                       "assert all(x['initialization']==a[0]['initialization'] and x['parameter_samples']==a[0]['parameter_samples'] for x in a)")
        execute(container_command(base, 0, shlex.join([PYTHON, "-c", program])), timeout=60)
        state["status"] = "analyzing"
        write(state_path, state)
        report = "/report" if args.formal_case else "/preflight-report"
        cmd = [PYTHON, "-m", "hccl.tools.diagnosis.cli", "analyze", "--capture", base + "/capture", "--mode", "rolling", "--output", base + report]
        if not args.formal_case:
            cmd.append("--keep-debug")
        if args.gpt:
            cmd.append("--allow-uncalibrated-clock")
        log = (root / "logs/diagnosis.log").open("x")
        logs.append(log)
        subprocess.run(container_command(base, 0, shlex.join(cmd), analysis_seconds), stdout=log, stderr=subprocess.STDOUT, check=True, timeout=analysis_seconds + 30)
        state["status"] = "passed"
    except BaseException as error:
        state.update(status="failed", error=str(error))
        raise
    finally:
        if clock_server is not None:
            clock_server.__exit__(None, None, None)
        if network_process is not None and network_process.poll() is None:
            try:
                execute(container_command(base, 0, shlex.join([PYTHON, "-c", "from pathlib import Path;p=Path(" + repr(base + "/gpt-output/private") + ");p.mkdir(parents=True,exist_ok=True);(p/'abort').touch()"])))
                network_process.wait(timeout=60)
            except Exception as error:
                state.setdefault("cleanup_errors", []).append(str(error))
        # Only our context holders are released. Independent container timeouts bound interrupted captures.
        for node in (0, 1):
            try:
                execute(container_command(base, node, shlex.join([PYTHON, "-c", "from pathlib import Path; p=Path(" + repr(base + "/hold") + "); (p/'release').touch() if p.is_dir() else None"])), timeout=30)
            except Exception as error:
                state.setdefault("cleanup_errors", []).append(str(error))
        for process in processes + holders:
            try:
                process.wait(timeout=30)
            except subprocess.TimeoutExpired:
                state.setdefault("cleanup_errors", []).append("bounded child still exiting: " + str(process.pid))
        for log in logs:
            log.close()
        state["finished_unix_ns"] = time.time_ns()
        if state.get("cleanup_errors"):
            state["status"] = "failed"
        write(state_path, state)
        if state.get("cleanup_errors"):
            raise RuntimeError("owned job cleanup needs attention; see preflight-state.json")


if __name__ == "__main__":
    main()
