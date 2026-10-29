"""Bounded Node0 smoke in the existing owned container; no device policy edits."""
from __future__ import annotations

import argparse
import fcntl
import json
from pathlib import Path
import re
import shlex
import shutil
import socket
import subprocess
import time


def available(text, cards):
    empty = {int(x) for x in re.findall(r"No running processes found in NPU (\d+)", text)}
    memory, card = {}, None
    for line in text.splitlines():
        header = re.match(r"\|\s*(\d+)\s+Ascend910\b", line)
        if header:
            card = int(header.group(1))
        match = re.search(r"(\d+)\s*/\s*65536\s*\|$", line)
        if match and card in cards:
            memory.setdefault(card, []).append(int(match[1]))
    return (set(cards) <= empty and all(len(memory.get(c, [])) == 2 and max(memory[c]) < 4096 for c in cards))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--source-name", default=".")
    args = parser.parse_args()
    root = args.root.resolve()
    if (root.parent != Path("/home/commTeam/zjy/zjy-new-workspace") or not root.name.startswith("tool-smoke-")
            or socket.gethostname().split(".")[0] != "liteserver-560t-0"):
        raise ValueError("only the reviewed owned Node0 workspace is allowed")
    lock = (root / "smoke.lock").open("a" if args.resume else "x")
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    container = json.loads(subprocess.check_output(["docker", "inspect", "zjy-new"], text=True))[0]
    if (container["HostConfig"]["Privileged"] or not container["State"]["Running"]
            or not any(m["Destination"] == "/workspace" and Path(m["Source"]).resolve() == root.parent for m in container["Mounts"])):
        raise ValueError("unexpected owned container configuration")
    if not {"/dev/davinci13", "/dev/davinci15"} <= {d["PathOnHost"] for d in container["HostConfig"]["Devices"]}:
        raise ValueError("expected target physical devices are not exposed")
    base = "/workspace/" + root.name
    source_path = (root / args.source_name).resolve()
    if source_path != root and root not in source_path.parents:
        raise ValueError("source snapshot must stay inside the owned attempt")
    source = base if source_path == root else base + "/" + str(source_path.relative_to(root))
    python = "/project/venvs/hccl-py311/bin/python"
    runtime = "/workspace/gpt2-single-node0-50-20261029-001/a3-runtime"
    shell = ("source /usr/local/Ascend/ascend-toolkit/set_env.sh\n"
             "export ASCEND_OPP_PATH=" + runtime + "/opp\n"
             "export LD_LIBRARY_PATH=/workspace/nf-20261022/deploy/lib64:" + runtime + "/aarch64-linux/lib64:" + runtime + "/opp/built-in/op_impl/ai_core/tbe/op_tiling/lib/linux/aarch64:${LD_LIBRARY_PATH:-}\n"
             "export PYTHONPATH=" + shlex.quote(source) + "\n")
    (root / "logs").mkdir(exist_ok=args.resume)
    state = json.loads((root / "smoke-state.json").read_text()) if args.resume else dict(status="prechecking", selected_physical_cards=[6, 7], runtime_devices=[5, 7],
                 device_policy_changed=False, container="zjy-new", captures=[], reports=[])
    if state["selected_physical_cards"] != [6, 7] or state["runtime_devices"] != [5, 7] or state["container"] != "zjy-new":
        raise ValueError("resume scope changed")
    state.pop("error", None)
    state["consumer_source"] = args.source_name
    def save():
        (root / "smoke-state.json").write_text(json.dumps(state, indent=2) + "\n")
    def idle(label):
        text = subprocess.check_output(["npu-smi", "info"], text=True, timeout=30)
        (root / "logs" / (label + "-resources.txt")).write_text(text)
        if not available(text, [6, 7]):
            raise RuntimeError("target whole cards are busy; no load started")
        if shutil.disk_usage(root).free < 5 * 1024**3:
            raise RuntimeError("less than 5GiB free; no capture started")
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", 29781))
    def execute(label, command, seconds):
        if args.resume:
            label += "-resume-" + str(time.time_ns())
        with (root / "logs" / (label + ".log")).open("x") as log:
            subprocess.run(["docker", "exec", "zjy-new", "timeout", "--signal=TERM", "--kill-after=20s",
                            str(seconds) + "s", "bash", "-lc", shell + command], stdout=log,
                           stderr=subprocess.STDOUT, check=True, timeout=seconds + 40)
    try:
        save()
        idle("initial-1")
        time.sleep(30)
        idle("initial-2")
        # Query mapping without creating any NPU context or changing policies.
        mapping = subprocess.check_output(["docker", "exec", "zjy-new", "npu-smi", "info", "-m"], text=True, timeout=30)
        (root / "logs/mapping.txt").write_text(mapping)
        for line, expected in (("5", "13"), ("7", "15")):
            if not any(re.match(r"\s*\d+\s+\d+\s+" + line + r"\s+" + expected + r"\s+Ascend910", row) for row in mapping.splitlines()):
                raise ValueError("runtime-to-physical mapping changed")
        for name, delay in (("normal", 0), ("delayed", 20)):
            idle(name)
            capture = base + "/captures/" + name + "/nodes/node0"
            app = [python, "-m", "torch.distributed.run", "--nnodes=1", "--nproc-per-node=2", "--max-restarts=0",
                   "--master-addr=127.0.0.1", "--master-port=29781", source + "/examples/diagnosis_collectives.py",
                   "--devices", "5,7", "--numerics-dir", base + "/numerics/" + name,
                   "--delay-rank", "1", "--delay-ms", str(delay)]
            command = ("export HCCL_STEP_TRACE=1 HCCL_TASK_SEMANTIC_TRACE=1 HCCL_OP_EXPANSION_MODE=HOST\n"
                       "export HCCL_TRACE_NODE_ID=node0 HCCL_TRACE_RUN_ID=" + name + "\n"
                       "export HCCL_TRACE_CALLS_DIR=" + capture + "/calls\n"
                       "export ASCEND_PROCESS_LOG_PATH=" + capture + "/plog\n"
                       "export ASCEND_GLOBAL_LOG_LEVEL=1 ASCEND_SLOG_PRINT_TO_STDOUT=0 OMP_NUM_THREADS=1\n"
                       "export HCCL_EXEC_TIMEOUT=120 HCCL_CONNECT_TIMEOUT=120\n"
                       "unset ASCEND_RT_VISIBLE_DEVICES\n" + shlex.join(["msprof", "--application=" + shlex.join(app),
                        "--output=" + capture + "/msprof", "--hccl=on", "--task-time=on", "--type=db"]))
            if name not in state["captures"]:
                state.update(status="capturing", active_capture=name)
                save()
                execute(name + "-capture", command, 240)
            for rank in (0, 1):
                result_path = root / "numerics" / name / ("rank-{}.json".format(rank))
                if not result_path.is_file():
                    raise RuntimeError("workload did not complete; msprof exit zero is not a numerical pass; see " + name + "-capture.log")
                result = json.loads(result_path.read_text())
                if result["status"] != "passed" or len(result["results"]) != 8:
                    raise ValueError("smoke numerical/completion check failed")
            if name not in state["captures"]:
                state["captures"].append(name)
            state.update(status="analyzing", active_capture=None)
            save()
            command = [python, "-m", "hccl.tools.diagnosis.cli", "analyze", "--capture", base + "/captures/" + name,
                       "--mode", "rolling", "--output", base + "/results/" + name + "-rolling"]
            report_path = root / "results" / (name + "-rolling")
            if report_path.exists():
                result = json.loads((report_path / "root_causes.json").read_text())
                if not result["quality"]["pipeline_passed"]:
                    raise ValueError("existing report is not a passed analysis")
            else:
                execute(name + "-rolling", shlex.join(command), 240)
            if name + "-rolling" not in state["reports"]:
                state["reports"].append(name + "-rolling")
            save()
        command = [python, "-m", "hccl.tools.diagnosis.cli", "analyze", "--capture", base + "/captures/delayed",
                   "--baseline", base + "/captures/normal", "--mode", "baseline", "--output", base + "/results/delayed-baseline"]
        execute("delayed-baseline", shlex.join(command), 240)
        state["reports"].append("delayed-baseline")
        for name in state["reports"]:
            if {p.name for p in (root / "results" / name).iterdir()} != {"execution.html", "root_causes.json", "propagation.html"}:
                raise ValueError("final output is not exactly three files")
        state.update(status="passed", finished_unix_ns=time.time_ns())
    except BaseException as error:
        state.update(status="failed", error=str(error), finished_unix_ns=time.time_ns())
        raise
    finally:
        save()
        (root / "logs/final-resources.txt").write_text(subprocess.check_output(["npu-smi", "info"], text=True, timeout=30))


if __name__ == "__main__":
    main()
