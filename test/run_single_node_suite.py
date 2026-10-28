#!/usr/bin/env python3
"""Host-side 21-case supervisor; refuses occupied devices and never alters policy."""
from __future__ import annotations

import argparse
import csv
import fcntl
import hashlib
import json
from pathlib import Path
import re
import shlex
import signal
import subprocess
import time


def host_is_idle(output):
    if output.count("No running processes found in NPU") != 8:
        return False
    memory = re.findall(r"\|\s*\d+\s+\d+\s*\|[^\n]*?\s(\d+)\s*/\s*65536\s*\|", output)
    return len(memory) == 16 and all(int(value) < 4096 for value in memory)


def write_json(path, data):
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def write_results(path, cases):
    fields = ["case_id", "execution_success", "strict_diagnosis_success", "diagnosis_success",
              "evaluation_status", "evaluation_rule", "classification", "temporal_hit",
              "target_rank_hit", "rank_time_hit", "reason", "diagnosis_directory"]
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for item in cases:
            evaluation = item["temporal_evaluation"]
            row = {key: item[key] for key in fields if key in item}
            row.update({key: evaluation.get(key) for key in fields if key not in row})
            row["evaluation_status"] = evaluation["status"]
            writer.writerow(row)


def write_formal_summary(root, cases):
    kinds = ("progress_delay", "copy_contention", "communication_contention", "compute_contention")
    groups = []
    for kind in kinds:
        group = [c for c in cases if c.get("injection", {}).get("kind") == kind]
        correct = sum(c["temporal_evaluation"].get("diagnosis_success") is True for c in group)
        unknown = sum(c["temporal_evaluation"].get("diagnosis_success") is None for c in group)
        groups.append(dict(kind=kind, expected=5, completed=len(group), correct=correct, not_evaluable=unknown,
                           success_rate_percent=correct * 20 if len(group) == 5 else None))
    write_json(root / "success-rates.json", dict(expected_runs=21, completed_runs=len(cases), groups=groups,
                                                rule="primary_source_same_rank_and_time_overlap"))
    fields = ["case_id", "kind", "html_path", "node_id", "rank", "chart_start_ms", "chart_stop_ms",
              "active_foreground_stream_ids", "anchor_collective_stream_ids", "anchor_operation_scope"]
    with (root / "injection-locations.csv").open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for case in cases:
            for location in case.get("injection_locations", []) or [{}]:
                row = {k: location.get(k, "") for k in fields}
                row.update(case_id=case["case_id"], kind=case.get("injection", {}).get("kind", ""),
                           html_path=case.get("retained_html", ""))
                for key in ("active_foreground_stream_ids", "anchor_collective_stream_ids"):
                    row[key] = ";".join(map(str, row[key]))
                writer.writerow(row)


def validate_mixed_preflight(result, launch, workload):
    if (not result.get("strict_diagnosis_success") or not result.get("execution_success")
            or result.get("purpose") != "full_shape_mixed_preflight"
            or result.get("gemm_backend") != "grouped" or launch.get("gemm_backend") != "grouped"):
        raise ValueError("strict rolling mixed-workload preflight must pass with the selected backend")
    expected = dict(workload, warmup=1, iters=7)
    if launch.get("workload") != expected or launch.get("devices") != [1, 3, 5, 7]:
        raise ValueError("preflight must retain the full formal compute/communication shapes and devices")


def run(args):
    root = args.host_directory.resolve()
    if root.name != "single-910c-random-20261024":
        raise ValueError("use the reviewed dedicated experiment directory")
    lock_file = (root / "suite.lock").open("a")
    fcntl.flock(lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
    state_path = root / "suite-state.json"
    previous_state = json.loads(state_path.read_text()) if state_path.exists() else None
    if previous_state and not args.resume:
        raise ValueError("refusing to start a duplicate or silently resume the queue")
    if args.resume and (not previous_state or previous_state["status"] != "stopped"):
        raise ValueError("explicit resume requires a stopped owned queue")
    preflight = json.loads((root / "preflight-mixed-grouped-v1/result.json").read_text())
    launch = json.loads((root / "preflight-mixed-grouped-v1/launch.json").read_text())
    normal = json.loads((root / "plan/private/cases/single-910c-4r-normal.json").read_text())
    validate_mixed_preflight(preflight, launch, normal["workload"])
    background = json.loads((root / "preflight-communication-v2/result.json").read_text())
    if background.get("operations", 0) <= 0 or background.get("max_error") != 0 or background.get("process_count") != 1:
        raise ValueError("single-process two-device communication runtime preflight must pass first")
    compute = json.loads((root / "preflight-compute-grouped-v1/result.json").read_text())
    if ({c.get("matrix_size") for c in compute} != {2304, 6144}
            or any(c.get("operations", 0) <= 0 or c.get("max_error") != 0
                   or c.get("gemm_backend") != "grouped" for c in compute)):
        raise ValueError("random-size compute worker runtime preflight must pass first")
    inspect = json.loads(subprocess.check_output(["docker", "inspect", args.container], text=True))[0]
    if not inspect["State"]["Running"] or inspect["HostConfig"]["Privileged"]:
        raise ValueError("only the existing running nonprivileged own container is allowed")
    if not any(Path(m["Source"]).resolve() == root.parent and m["Destination"] == "/workspace"
               for m in inspect["Mounts"]):
        raise ValueError("container workspace mount differs from the reviewed host directory")
    devices = {d["PathOnHost"] for d in inspect["HostConfig"]["Devices"]}
    if not {"/dev/davinci{}".format(d) for d in (9, 11, 13, 15)} <= devices:
        raise ValueError("reviewed physical device mapping not present")
    plan = json.loads((root / "plan/suite.json").read_text())
    if plan["run_count"] != 21 or len(plan["cases"]) != 21:
        raise ValueError("expected exactly 21 cases")
    attempts = root / "attempts"
    attempts.mkdir(exist_ok=args.resume)
    state = previous_state or dict(status="prechecking", started=0, completed=0, requested=21, cases=[], device_policy_changed=False)
    if [c["case_id"] for c in state["cases"]] != [c["case_id"] for c in plan["cases"][:state["completed"]]]:
        raise ValueError("completed state differs from the frozen plan")
    state.update(status="prechecking")
    write_json(state_path, state)
    def idle(label):
        output = subprocess.check_output(["npu-smi", "info"], text=True, timeout=30)
        (root / (label + "-npu-smi.txt")).write_text(output, encoding="utf-8")
        if not host_is_idle(output):
            raise RuntimeError("host is occupied or memory differs from checked base; queue stopped, no polling")
    current = None
    try:
        idle("initial-1")
        time.sleep(30)
        idle("initial-2")
        source = Path(__file__).resolve().parents[1]
        source_relative = source.relative_to(root)
        source_files = {str(p.relative_to(source)): hashlib.sha256(p.read_bytes()).hexdigest()
                        for folder in (source / "test", source / "hccl/tools/diagnosis")
                        for p in folder.rglob("*") if p.is_file() and p.suffix in {".py", ".cc", ".md"}}
        write_json(root / "source-sha256.json", source_files)
        for index, entry in enumerate(plan["cases"]):
            if index < state["completed"]:
                continue
            idle("case-{:02d}".format(index))
            case = root / "plan" / entry["path"]
            attempt = attempts / entry["case_id"]
            base = "/workspace/" + root.name
            source_base = base + "/" + str(source_relative)
            command = ["/project/venvs/hccl-py311/bin/python", source_base + "/test/run_single_node_case.py",
                       "--case", base + "/plan/" + entry["path"], "--output", base + "/attempts/" + entry["case_id"],
                       "--devices", "1,3,5,7", "--communication-worker", base + "/single_process_comm_load-v2",
                       "--gemm-backend", "grouped"]
            if args.retain_html_only:
                command.append("--compact-output")
            continuing = attempt.exists()
            if continuing:
                if not args.resume:
                    raise ValueError("existing attempt requires explicit resume")
                command.append("--resume-analysis")
            shell = "source /usr/local/Ascend/ascend-toolkit/set_env.sh\n" + (
                "export LD_LIBRARY_PATH=/workspace/nf-20261022/deploy/lib64:${LD_LIBRARY_PATH:-}\n") + shlex.join(command)
            state.update(status="running", active_case=entry["case_id"], started=index + 1)
            write_json(state_path, state)
            write_results(root / "results.csv", state["cases"])
            print("START {} {}".format(index + 1, entry["case_id"]), flush=True)
            log_path = root / ("case-{:02d}{}.log".format(index, "-resume-" + str(time.time_ns()) if continuing else ""))
            with log_path.open("x") as log:
                current = subprocess.Popen(["docker", "exec", args.container, "timeout", "--signal=TERM", "--kill-after=30s",
                                            "2000s", "bash", "-lc", shell],
                                           stdout=log, stderr=subprocess.STDOUT)
                try:
                    code = current.wait(timeout=2100)
                except BaseException:
                    cleanup = ("import sys; sys.path.insert(0," + repr(source_base + "/test") + "); "
                               "from run_single_node_case import stop_own_attempt; stop_own_attempt(" +
                               repr(base + "/attempts/" + entry["case_id"]) + ")")
                    subprocess.run(["docker", "exec", args.container, "/project/venvs/hccl-py311/bin/python", "-c", cleanup], timeout=30)
                    current.wait(timeout=60)
                    raise
            if code or not (attempt / "result.json").exists():
                raise RuntimeError("case failed; inspect {}".format(root / ("case-{:02d}.log".format(index))))
            result = json.loads((attempt / "result.json").read_text())
            state["cases"].append(result)
            state.update(completed=index + 1, active_case=None)
            write_json(state_path, state)
            write_formal_summary(root, state["cases"])
            print("DONE {} {} {}".format(index + 1, entry["case_id"], result["temporal_evaluation"]), flush=True)
        state.update(status="completed")
    except BaseException as error:
        state.update(status="stopped", error=str(error), manual_review_required=True)
        raise
    finally:
        write_json(state_path, state)
        write_results(root / "results.csv", state["cases"])
        write_formal_summary(root, state["cases"])
    return state


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host-directory", type=Path, required=True)
    parser.add_argument("--container", default="zjy-new", choices=["zjy-new"])
    parser.add_argument("--retain-html-only", action="store_true")
    parser.add_argument("--resume", action="store_true", help="Explicitly continue a stopped queue, without rerunning captured workloads")
    args = parser.parse_args()
    signal.signal(signal.SIGTERM, lambda *_: (_ for _ in ()).throw(KeyboardInterrupt("termination requested")))
    try:
        print(json.dumps(run(args)), flush=True)
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
        parser.exit(1, str(error) + "\n")
