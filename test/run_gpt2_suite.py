#!/usr/bin/env python3
"""Owned-host GPT-2 supervisor; preserve Node0 results and support an explicit Node3 cohort."""
from __future__ import annotations

import argparse
import csv
from contextlib import contextmanager
import fcntl
import hashlib
import json
from pathlib import Path
import re
import shlex
import shutil
import signal
import socket
import subprocess
import tempfile
import time

if __package__:
    from .gpt2_diagnosis_suite import write_plan, summarize, validate_plan
    from .run_single_node_suite import host_is_idle, write_json
else:
    from gpt2_diagnosis_suite import write_plan, summarize, validate_plan
    from run_single_node_suite import host_is_idle, write_json


def operator_environment(root, operator_root):
    if operator_root is None:
        return ""
    root, operator_root = root.resolve(), operator_root.resolve()
    if root not in operator_root.parents:
        raise ValueError("operator runtime must be inside this owned experiment directory")
    libraries = operator_root / "aarch64-linux/lib64"
    if (not (operator_root / "opp/built-in").is_dir()
            or any(not (libraries / name).is_file() for name in
                   ("libopapi.so", "libopapi_math.so", "libopapi_nn.so", "libopapi_transformer.so"))):
        raise ValueError("incomplete isolated A3 operator runtime")
    base = "/workspace/" + str(operator_root.relative_to(root.parent))
    paths = base + "/aarch64-linux/lib64:" + base + "/opp/built-in/op_impl/ai_core/tbe/op_tiling/lib/linux/aarch64"
    return ("export ASCEND_OPP_PATH=" + shlex.quote(base + "/opp") + "\n"
            "export LD_LIBRARY_PATH=" + shlex.quote(paths) + ":${LD_LIBRARY_PATH:-}\n")


@contextmanager
def atomic_csv(path):
    """Replace summaries without truncating a file written by a container UID."""
    if path.is_symlink():
        raise ValueError("summary destination cannot be a symlink")
    temporary = tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", newline="",
        dir=path.parent, prefix="." + path.name + ".", suffix=".tmp", delete=False)
    try:
        with temporary:
            yield temporary
        Path(temporary.name).replace(path)
    finally:
        Path(temporary.name).unlink(missing_ok=True)


def export(root, results):
    plan_path = root / "plan/suite.json"
    plan = json.loads(plan_path.read_text()) if plan_path.is_file() else None
    write_json(root / "summary.json", summarize(results, plan))
    columns = ["case_id", "kind", "status", "target_rank", "iteration", "selected_bucket", "strength", "strength_unit", "actual_windows", "candidate_count",
               "candidate_hit_count", "candidate_hit_fraction", "any_candidate_hit", "primary_hit", "diagnosis_status",
               "physical_node", "measured_iterations"]
    with atomic_csv(root / "results.csv") as f:
        writer = csv.DictWriter(f, fieldnames=columns)
        writer.writeheader()
        for item in results:
            inj, evaluation = item["injection"], item["evaluation"]
            writer.writerow(dict(case_id=item["case_id"], kind=inj["kind"], status=item["status"],
                target_rank=inj.get("target_rank"), iteration=inj.get("iteration"),
                selected_bucket=next((r["selected_bucket"] for r in item["timings"] if r["selected_bucket"] is not None), None),
                strength=inj.get("delay_ms", inj.get("buffer_mib", inj.get("matrix_size"))),
                strength_unit="ms" if inj["kind"] == "progress_delay" else "matrix_dimension" if inj["kind"] == "compute_contention" else "MiB" if inj["kind"] != "normal" else "",
                actual_windows=json.dumps(item.get("actual_windows", []), separators=(",", ":")),
                physical_node=(item.get("execution_cohort") or {}).get("physical_node", "node0"),
                measured_iterations=item.get("workload", {}).get("iters"),
                **{k: evaluation[k] for k in ("candidate_count", "candidate_hit_count", "candidate_hit_fraction", "any_candidate_hit", "primary_hit")},
                diagnosis_status=item["diagnosis_status"]))
    fields = ["case_id", "kind", "root_id", "graph_id", "node_id", "user_rank", "device_id", "stream_id", "task_id",
              "iteration", "bucket", "phase", "step", "event", "component", "status", "observed_start_ns", "observed_stop_ns",
              "duration_ns", "reference_mean_ns", "delta_ns", "hit", "overlap_ns"]
    with atomic_csv(root / "candidates.csv") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for item in results:
            sources = json.loads((root / "records" / item["case_id"] / "diagnosis.json").read_text())["root_causes"]
            matched = {c["root_id"]: c for c in item["evaluation"]["candidates"]}
            for source in sources:
                row = {k: source.get(k) for k in fields}
                row.update(case_id=item["case_id"], kind=item["injection"]["kind"],
                           hit=matched[source["root_id"]]["hit"], overlap_ns=matched[source["root_id"]]["overlap_ns"])
                writer.writerow(row)


def validate_host(root, physical_node, hostname):
    if physical_node == "node3":
        valid = (root.parent == Path("/home/zjy-new/workspace") and root.name.startswith("gpt2-single-node3-")
                 and hostname.split(".")[0] == "liteserver-560t-3")
    else:
        valid = root.parent == Path("/home/commTeam/zjy/zjy-new-workspace") and root.name.startswith("gpt2-single-")
    if not valid:
        raise ValueError("GPT-2 suite must use the reviewed owned host and workspace")


def allocation_is_idle(output, allocation):
    if allocation == "whole-host":
        return host_is_idle(output)
    if allocation != "node0-cards0-3":
        raise ValueError("unknown explicit device allocation")
    empty = {int(x) for x in re.findall(r"\|\s*No running processes found in NPU (\d+)\s*\|", output)}
    memory, card = {}, None
    for line in output.splitlines():
        header = re.match(r"\|\s*(\d+)\s+Ascend910\b", line)
        if header:
            card = int(header.group(1))
        match = re.search(r"(\d+)\s*/\s*65536\s*\|$", line)
        if match and card in range(4):
            memory.setdefault(card, []).append(int(match.group(1)))
    return (set(range(4)) <= empty and set(memory) == set(range(4))
            and all(len(values) == 2 and max(values) < 4096 for values in memory.values()))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--container", default="zjy-new")
    parser.add_argument("--revision", required=True)
    parser.add_argument("--source-name", default="src")
    parser.add_argument("--operator-root", type=Path)
    parser.add_argument("--physical-node", choices=("node0", "node3"), default="node0")
    parser.add_argument("--allocation", choices=("whole-host", "node0-cards0-3"), default="whole-host")
    parser.add_argument("--preflight-only", action="store_true")
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()
    root = args.root.resolve()
    validate_host(root, args.physical_node, socket.gethostname())
    lock = (root / "suite.lock").open("a")
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    container = json.loads(subprocess.check_output(["docker", "inspect", args.container], text=True))[0]
    first_four = args.allocation == "node0-cards0-3"
    expected_container = "zjy-gpt2-node0-50" if first_four else "zjy-new"
    if first_four and (args.physical_node != "node0" or socket.gethostname().split(".")[0] != "liteserver-560t-0"):
        raise ValueError("the explicitly authorized partial allocation is only on Node0")
    if args.container != expected_container or container["HostConfig"]["Privileged"] or not container["State"]["Running"]:
        raise ValueError("only own existing nonprivileged container is allowed")
    if first_four and (container["Config"].get("Labels", {}).get("hccl-trace.experiment") != root.name
                       or container["HostConfig"]["PidMode"] not in {"", "private"}):
        raise ValueError("unexpected experiment container ownership or PID mode")
    if not any(m["Destination"] == "/workspace" and Path(m["Source"]).resolve() == root.parent for m in container["Mounts"]):
        raise ValueError("unexpected container mount")
    mapped = {d["PathOnHost"] for d in container["HostConfig"]["Devices"]}
    physical = (1, 3, 5, 7) if first_four else (9, 11, 13, 15)
    if not {"/dev/davinci{}".format(d) for d in physical} <= mapped:
        raise ValueError("target physical mapping changed")
    if first_four and {d for d in mapped if re.fullmatch(r"/dev/davinci\d+", d)} != {"/dev/davinci" + str(d) for d in range(8)}:
        raise ValueError("the new container must expose exactly physical NPU0..3")
    state_path = root / "state.json"
    if state_path.exists() and not args.resume:
        raise ValueError("existing suite state; refusing duplicate execution")
    if not (root / "plan").exists():
        if args.physical_node != "node0":
            raise ValueError("Node3 requires its own explicit frozen continuation plan")
        write_plan(root / "plan")
    plan = json.loads((root / "plan/suite.json").read_text())
    validate_plan(plan, root / "plan")
    if (plan.get("execution_cohort") or {}).get("physical_node", "node0") != args.physical_node:
        raise ValueError("physical host differs from the frozen plan")
    if (plan.get("execution_cohort") or {}).get("allocation", "whole-host") != args.allocation:
        raise ValueError("device allocation differs from the frozen plan")
    plan_hash = hashlib.sha256((root / "plan/suite.json").read_bytes()).hexdigest()
    state = json.loads(state_path.read_text()) if state_path.exists() else dict(status="prechecking", requested=plan["requested_runs"], completed=0, cases=[])
    if state.get("plan_sha256", plan_hash) != plan_hash or state["requested"] != plan["requested_runs"]:
        raise ValueError("frozen plan changed since this queue started")
    if state["status"] == "completed":
        return
    if (state["completed"] != len(state["cases"])
            or [c["case_id"] for c in state["cases"]] != [c["case_id"] for c in plan["cases"][:state["completed"]]]):
        raise ValueError("completed state differs from the frozen plan prefix")
    stop_path = root / "stop-requested"
    if stop_path.exists():
        if not args.resume:
            raise ValueError("suite was explicitly stopped")
        stop_path.unlink()
    def idle(label):
        result = subprocess.check_output(["npu-smi", "info"], text=True, timeout=30)
        (root / "logs" / (label + "-resources.txt")).write_text(result)
        if not allocation_is_idle(result, args.allocation):
            raise RuntimeError(args.physical_node + " has an external NPU task or unexpected HBM; stopped without polling")
        if shutil.disk_usage(root).free < 30 * 1024**3:
            raise RuntimeError("less than 30GiB available; stopped before capture")
    current, current_directory = None, None
    def stop(signum, frame):
        stop_path.touch()
        if current_directory is not None:
            code = ("import json,os,signal;from pathlib import Path;"
                    "p=Path(" + repr(current_directory) + ");"
                    "r=json.loads((p/'owned-attempt.json').read_text());"
                    "cmd=(Path('/proc')/str(r['runner_pid'])/'cmdline').read_bytes().split(b'\\0');"
                    "assert str(p).encode() in cmd and any(b'run_gpt2_case.py' in x for x in cmd);"
                    "os.kill(r['runner_pid'],signal.SIGTERM)")
            if (root / ("preflight" if current_directory.endswith("/preflight") else
                        "attempts/" + current_directory.rsplit("/", 1)[1]) / "owned-attempt.json").is_file():
                subprocess.run(["docker", "exec", args.container, "/project/venvs/hccl-py311/bin/python", "-c", code], timeout=30, check=False)
        if current is not None and current.poll() is None:
            try:
                current.wait(timeout=40)
            except subprocess.TimeoutExpired:
                current.terminate()
        raise InterruptedError("user/signal stopped GPT-2 suite")
    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    base = "/workspace/" + root.name
    if not args.source_name.replace("-", "").replace("_", "").isalnum():
        raise ValueError("invalid source snapshot name")
    source = base + "/" + args.source_name
    operator_shell = operator_environment(root, args.operator_root)
    def attempt(case, preflight=False):
        nonlocal current, current_directory
        suffix = "preflight" if preflight else "attempts/" + case
        record = "preflight-records" if preflight else "records/" + case
        current_directory = base + "/" + suffix
        command = ["/project/venvs/hccl-py311/bin/python", source + "/test/run_gpt2_case.py", "--case", base + "/plan/" + case + ".json",
                   "--output", base + "/" + suffix, "--records", base + "/" + record, "--data", base + "/data",
                   "--communication-worker", base + "/single_process_comm_load", "--revision", args.revision, "--cleanup",
                   "--stop-file", base + "/stop-requested"]
        if preflight:
            command.append("--preflight")
        shell = ("source /usr/local/Ascend/ascend-toolkit/set_env.sh\n" + operator_shell +
                 "export LD_LIBRARY_PATH=/workspace/nf-20261022/deploy/lib64:${LD_LIBRARY_PATH:-}\n"
                 "export PYTHONPATH=" + shlex.quote(base + "/deps:" + source + "/hccl/tools:" + source + "/test") + "\n" +
                 "export HF_HOME=" + shlex.quote(base + "/data/hf-cache") + "\n" + shlex.join(command))
        with (root / "logs" / (case + ("-preflight" if preflight else "") + ".log")).open("x") as log:
            current = subprocess.Popen(["docker", "exec", args.container, "timeout", "--signal=TERM", "--kill-after=30s", "3600s",
                                        "bash", "-lc", shell], stdout=log, stderr=subprocess.STDOUT)
            if current.wait(timeout=3660):
                raise RuntimeError("capture/diagnosis failed: " + case + "; inspect own log")
        current, current_directory = None, None
        return json.loads((root / record / "result.json").read_text())
    try:
        if args.resume and state["cases"]:
            export(root, state["cases"])
        state.update(status="prechecking", source_revision=args.revision,
                     physical_node=args.physical_node, plan_sha256=plan_hash, execution_cohort=plan.get("execution_cohort"),
                     allocation=args.allocation,
                     operator_root=str(args.operator_root.resolve()) if args.operator_root else None)
        state.pop("error", None)
        state.pop("active_case", None)
        write_json(state_path, state)
        idle("initial-1")
        time.sleep(30)
        idle("initial-2")
        formal_control_first = (plan.get("execution_cohort") or {}).get("validation_mode") == "formal-control-first"
        if formal_control_first and args.preflight_only:
            raise ValueError("this continuation validates the full formal clean control before anomalies")
        if not formal_control_first and not (root / "preflight-records/retention-receipt.json").is_file():
            state.update(status="preflight", active_case="preflight")
            write_json(state_path, state)
            attempt("gpt2-4r-normal", True)
            state.update(active_case=None)
            write_json(state_path, state)
        if args.preflight_only:
            state.update(status="preflight_passed", active_case=None)
            write_json(state_path, state)
            return
        for entry in plan["cases"][state["completed"]:]:
            case = entry["case_id"]
            idle(case)
            state.update(status="running", active_case=case)
            write_json(state_path, state)
            result = attempt(case)
            state["cases"].append(result)
            state.update(completed=len(state["cases"]), active_case=None)
            export(root, state["cases"])
            write_json(state_path, state)
            print("DONE", state["completed"], case, result["evaluation"]["candidate_hit_count"], flush=True)
        state.update(status="completed", finished_unix_ns=time.time_ns())
    except BaseException as error:
        state.update(status="stopped", error=str(error), stopped_unix_ns=time.time_ns())
        raise
    finally:
        write_json(state_path, state)


if __name__ == "__main__":
    main()
