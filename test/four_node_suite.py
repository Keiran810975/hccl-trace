#!/usr/bin/env python3
"""Shared paired two/four-node cases and local runner, without SSH or shell hooks."""

from __future__ import annotations

import argparse
import copy
import csv
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import socket
import subprocess
import sys
import time


ROOT = Path(__file__).resolve().parents[1]
SIZES = {"small": [32, 64, 128], "main": [128, 256, 512], "large": [256, 512, 1024]}
LEVELS = {
    "progress_delay": [1, 20, 200],
    "nic_limit": [75, 50, 25],
    "copy_contention": [1, 2, 4],
    "compute_contention": [1, 2, 4],
    "communication_contention": [1, 2, 4],
}
KINDS = {"normal", *LEVELS}


def read_json(path: Path) -> dict:
    with path.open(encoding="utf-8-sig") as handle:
        return json.load(handle)


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def identifier(value: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", value) or value in {".", ".."}:
        raise ValueError("unsafe case/attempt identifier")
    return value


def validate_case(case: dict) -> None:
    if case.get("schema_version") != 1:
        raise ValueError("unsupported case schema")
    identifier(case["case_id"])
    identifier(case["baseline_case_id"])
    w, inj = case["workload"], case["injection"]
    if (case["nnodes"], case["ranks_per_node"]) not in {(4, 4), (2, 2)}:
        raise ValueError("supported topologies are 4 nodes x 4 ranks or 2 nodes x 2 ranks")
    world_size = case["nnodes"] * case["ranks_per_node"]
    for key in ("blocks", "tokens", "hidden_size", "ffn_size", "iters"):
        if type(w[key]) is not int or w[key] <= 0:
            raise ValueError("invalid workload " + key)
    if type(w["warmup"]) is not int or w["warmup"] < 0:
        raise ValueError("invalid warmup")
    if len(w["bucket_mib"]) != 3 or any(type(n) is not int or n <= 0 for n in w["bucket_mib"]):
        raise ValueError("exactly three positive integer MiB buckets are required")
    if inj["kind"] not in KINDS or not 0 <= inj["target_rank"] < world_size:
        raise ValueError("invalid injection kind or target rank")
    if not 0 <= inj["iteration"] < w["iters"] or not 1 <= inj["duration_iters"] <= w["iters"] - inj["iteration"]:
        raise ValueError("injection window is outside measured iterations")
    if not 0 <= inj["block"] < w["blocks"] or not 0 <= inj["bucket"] < 3:
        raise ValueError("injection slot is outside the workload")
    if inj["kind"] != "normal" and inj["level"] not in LEVELS[inj["kind"]]:
        raise ValueError("unsupported severity")
    if inj["kind"] == "progress_delay":
        if inj["mode"] not in {"arrival", "library_task"}:
            raise ValueError("delay mode must be arrival or library_task")
        if inj["mode"] == "library_task":
            selector = inj["selector"]
            if not selector.get("phase") or not selector.get("event") or not selector.get("evidence"):
                raise ValueError("internal delay requires phase/event and selection evidence")
            if any(type(selector[k]) is not int or selector[k] < 0 for k in ("step", "skip_matches")):
                raise ValueError("invalid internal task selector")
    if inj["kind"] == "communication_contention":
        if (not 0 <= inj["peer_rank"] < world_size
                or inj["peer_rank"] // case["ranks_per_node"] == inj["target_rank"] // case["ranks_per_node"]):
            raise ValueError("background communication needs a peer on another node")


def generate_cases(sizes: list[str], positions: list[int], seeds: list[int], selector: dict | None = None,
                   smoke: bool = False, *, nnodes: int = 4, ranks_per_node: int = 4) -> list[dict]:
    if not sizes or not positions or not seeds or any(size not in SIZES for size in sizes):
        raise ValueError("choose nonempty sizes from small,main,large and nonempty positions/seeds")
    if len(set(sizes)) != len(sizes) or len(set(positions)) != len(positions) or len(set(seeds)) != len(seeds):
        raise ValueError("duplicate matrix dimensions")
    if selector is not None and (len(sizes) != 1 or len(positions) != 1):
        raise ValueError("an internal selector is valid for only one size/position; calibrate each separately")
    result = []
    for size in sizes:
        for position in positions:
            for seed in seeds:
                topology = "2n4r-" if (nnodes, ranks_per_node) == (2, 2) else ""
                prefix = ("smoke-" if smoke else "") + topology + f"{size}-i{position}-s{seed}"
                normal = {
                    "schema_version": 1, "case_id": prefix + "-normal",
                    "baseline_case_id": prefix + "-normal", "nnodes": nnodes, "ranks_per_node": ranks_per_node,
                    "seed": seed, "purpose": "preflight" if smoke else "dataset",
                    "workload": {"blocks": 8, "tokens": 2048, "hidden_size": 8192,
                                 "ffn_size": 32768, "bucket_mib": SIZES[size][:], "warmup": 10, "iters": 50},
                    "injection": {"kind": "normal", "target_rank": (nnodes // 2) * ranks_per_node, "iteration": position,
                                  "duration_iters": 5, "block": 3, "bucket": 1, "level": 0},
                }
                if smoke:
                    normal["workload"].update(warmup=1, iters=2)
                    normal["injection"]["duration_iters"] = 1
                validate_case(normal)
                result.append(normal)
                for kind, levels in LEVELS.items():
                    for level in levels:
                        item = copy.deepcopy(normal)
                        item["case_id"] = f"{prefix}-{kind}-{level}"
                        item["injection"].update(kind=kind, level=level)
                        if kind == "progress_delay":
                            item["injection"]["mode"] = "library_task" if selector is not None else "arrival"
                            if selector is not None:
                                item["injection"]["selector"] = copy.deepcopy(selector)
                        if kind == "communication_contention":
                            item["injection"]["peer_rank"] = 0
                        validate_case(item)
                        result.append(item)
    return result


def workload_stats(case: dict) -> dict:
    w = case["workload"]
    payload_mib = w["blocks"] * sum(w["bucket_mib"])
    h, f = w["hidden_size"], w["ffn_size"]
    return {"world_size": case["nnodes"] * case["ranks_per_node"], "allreduces_per_iteration": w["blocks"] * 3,
            "allreduces_including_warmup": (w["warmup"] + w["iters"]) * w["blocks"] * 3,
            "input_mib_per_rank_iteration": payload_mib,
            "input_mib_per_rank_measured": payload_mib * w["iters"],
            "bf16_weight_bytes_per_rank": w["blocks"] * (6 * h * h + 2 * h * f) * 2}


def validate_cluster(cluster: dict, case: dict, execute: bool, allow_background: bool, allow_network_change: bool) -> None:
    validate_case(case)
    nodes = cluster["nodes"]
    nnodes, ranks_per_node = case["nnodes"], case["ranks_per_node"]
    if len(nodes) != nnodes or [n["node_rank"] for n in nodes] != list(range(nnodes)):
        raise ValueError("nodes must be ordered node_rank 0.." + str(nnodes - 1))
    for node in nodes:
        devices = node["devices"]
        if (len(devices) != ranks_per_node or len(set(devices)) != ranks_per_node
                or any(type(d) is not int or d < 0 for d in devices)):
            raise ValueError("each node needs distinct, explicitly verified runtime device IDs")
    if cluster.get("op_expansion_mode", "AI_CPU") not in {"AI_CPU", "HOST", "DEFAULT"}:
        raise ValueError("op_expansion_mode must be AI_CPU, HOST or DEFAULT")
    for key in ("master_port", "background_port_base"):
        if type(cluster[key]) is not int or not 1024 <= cluster[key] <= 65531:
            raise ValueError("invalid port")
    if cluster["master_port"] in range(cluster["background_port_base"], cluster["background_port_base"] + 4):
        raise ValueError("foreground and background rendezvous ports overlap")
    if not execute:
        return
    if cluster.get("preflight_confirmed") is not True or "SET_" in cluster["master_addr"]:
        raise ValueError("confirm resource reservation, device mapping, software compatibility and reachable master IP first")
    inj = case["injection"]
    if inj["kind"].endswith("_contention") and not allow_background:
        raise ValueError("background workloads require --allow-background")
    if inj["kind"] == "nic_limit":
        if not allow_network_change:
            raise ValueError("NIC changes require --allow-network-change")
        hooks = cluster.get("nic_limit") or {}
        if hooks.get("node_rank") != inj["target_rank"] // ranks_per_node or not hooks.get("port_evidence"):
            raise ValueError("NIC hooks must identify the target node/port and mapping evidence")
        for name in ("query", "apply", "verify", "restore"):
            command = hooks.get(name)
            if not isinstance(command, list) or not command or any(not isinstance(s, str) for s in command):
                raise ValueError("NIC hooks must be nonempty argv arrays: " + name)
        if not any("{snapshot}" in arg for arg in hooks["restore"]):
            raise ValueError("restore must consume the original configuration snapshot")
    if inj["kind"] == "communication_contention" and not cluster.get("shared_path_evidence"):
        raise ValueError("record the foreground/background shared RoCE path before execution")
    if inj["kind"] == "communication_contention":
        address = nodes[inj["target_rank"] // ranks_per_node].get("background_addr", "")
        if not address or "SET_" in address:
            raise ValueError("set a reachable background_addr on the target node")
    if inj["kind"] == "progress_delay" and inj["mode"] == "library_task":
        if not cluster.get("internal_delay_runtime_evidence"):
            raise ValueError("library_task needs an explicitly verified HCCL_DIAG_INJECT runtime; no automatic patching")


def build_command(case: dict, cluster: dict, node_rank: int, out: Path, profile: bool,
                  *, public_calls: bool = False) -> tuple[list[str], dict]:
    if not 0 <= node_rank < case["nnodes"]:
        raise ValueError("node rank is outside the case topology")
    node, w, inj = cluster["nodes"][node_rank], case["workload"], case["injection"]
    env = {"HCCL_WORKLOAD_DEVICES": ",".join(map(str, node["devices"])),
           "HCCL_STEP_TRACE": "1", "HCCL_TASK_SEMANTIC_TRACE": "1",
           "HCCL_CONNECT_TIMEOUT": "180", "ASCEND_PROCESS_LOG_PATH": str(out / "ascend_log")}
    mode = cluster.get("op_expansion_mode", "AI_CPU")
    if mode != "DEFAULT":
        env["HCCL_OP_EXPANSION_MODE"] = mode
    if node.get("hccl_if_ip"):
        env["HCCL_IF_IP"] = node["hccl_if_ip"]
    if node.get("hccl_socket_ifname"):
        env["HCCL_SOCKET_IFNAME"] = node["hccl_socket_ifname"]
    if node.get("runtime_lib_dir"):
        env["LD_LIBRARY_PATH"] = node["runtime_lib_dir"] + ":" + os.environ.get("LD_LIBRARY_PATH", "")
    if inj["kind"] == "progress_delay" and inj["mode"] == "library_task":
        selector = inj["selector"]
        env.update(HCCL_DIAG_INJECT_DELAY_US=str(inj["level"] * 1000),
                   HCCL_DIAG_INJECT_RANK=str(inj["target_rank"]), HCCL_DIAG_INJECT_PHASE=selector["phase"],
                   HCCL_DIAG_INJECT_STEP=str(selector["step"]), HCCL_DIAG_INJECT_EVENT=selector["event"],
                   HCCL_DIAG_INJECT_SKIP_MATCHES=str(selector["skip_matches"]), HCCL_DIAG_INJECT_MAX_HITS="1")
    command = [cluster.get("python", "python3"), "-m", "torch.distributed.run", f"--nnodes={case['nnodes']}",
               f"--nproc-per-node={case['ranks_per_node']}", "--max-restarts=0", f"--node-rank={node_rank}",
               "--master-addr=" + cluster["master_addr"], "--master-port=" + str(cluster["master_port"]),
               str(ROOT / "test/multinode_commmix_train.py"), "--bucket-mib", ",".join(map(str, w["bucket_mib"]))]
    for key in ("blocks", "tokens", "hidden_size", "ffn_size", "warmup", "iters"):
        command += ["--" + key.replace("_", "-"), str(w[key])]
    command += ["--seed", str(case["seed"]), "--case-config", str(out / "private/case.json"),
                "--case-cluster", str(out / "private/cluster.json"), "--events-dir", str(out / "private/events")]
    if public_calls:
        command += ["--public-calls-dir", str(out / "public"), "--no-barrier"]
    if profile:
        if any(any(c.isspace() for c in arg) for arg in command):
            raise ValueError("msprof application paths/arguments cannot contain whitespace")
        command = ["msprof", "--application=" + " ".join(command), "--output=" + str(out / "msprof"),
                   "--hccl=on", "--task-time=on", "--type=db"]
    return command, env


def captured(command: list[str]) -> dict:
    try:
        done = subprocess.run(command, capture_output=True, text=True, timeout=30, cwd=ROOT)
        return {"returncode": done.returncode, "stdout": done.stdout, "stderr": done.stderr}
    except (OSError, subprocess.TimeoutExpired) as error:
        return {"error": str(error)}


def terminate_group(process: subprocess.Popen) -> None:
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        return
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        pass
    finally:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        process.wait()


def run_capture(command: list[str], env: dict, log: Path, timeout: float) -> int:
    with log.open("w", encoding="utf-8") as handle:
        process = subprocess.Popen(command, env=env, stdout=handle, stderr=subprocess.STDOUT, start_new_session=True)
        try:
            return process.wait(timeout=timeout)
        finally:
            terminate_group(process)


class NicLimit:
    """Only run site-provided argv hooks, and always attempt restoration after apply."""

    def __init__(self, hooks: dict, percent: int, out: Path):
        self.hooks, self.percent, self.out, self.touched = hooks, percent, out, False

    def call(self, stage: str) -> dict:
        values = {"percent": str(self.percent), "snapshot": str(self.out / "nic-original.json")}
        command = [arg.replace("{percent}", values["percent"]).replace("{snapshot}", values["snapshot"])
                   for arg in self.hooks[stage]]
        done = subprocess.run(command, capture_output=True, text=True, timeout=30)
        write_json(self.out / ("nic-" + stage + ".json"), {"argv": command, "returncode": done.returncode,
                                                           "stdout": done.stdout, "stderr": done.stderr})
        done.check_returncode()
        return json.loads(done.stdout) if stage in {"query", "verify"} else {}

    def apply(self) -> None:
        write_json(self.out / "nic-original.json", self.call("query"))
        self.touched = True
        self.call("apply")
        verification = self.call("verify")
        if verification.get("configured_percent") != self.percent:
            raise ValueError("NIC hook did not confirm the requested cap; throughput still needs separate measurement")

    def restore(self) -> None:
        if self.touched:
            self.call("restore")


def execute_node(args: argparse.Namespace) -> int:
    case, cluster = read_json(args.case), read_json(args.cluster)
    validate_cluster(cluster, case, False, args.allow_background, args.allow_network_change)
    out = (args.output / identifier(case["case_id"]) / identifier(args.attempt) / f"node{args.node_rank}").resolve()
    command, overrides = build_command(case, cluster, args.node_rank, out, not args.no_profile,
                                       public_calls=getattr(args, "diagnosis_capture", False))
    if not args.execute:
        print(json.dumps({"dry_run": True, "argv": command, "environment_overrides": overrides,
                          "stats": workload_stats(case)}, indent=2))
        return 0
    out.mkdir(parents=True, exist_ok=False)
    write_json(out / "private/case.json", case)
    write_json(out / "private/cluster.json", cluster)
    write_json(out / "private/command.json", {"argv": command, "environment_overrides": overrides})
    env = {k: v for k, v in os.environ.items() if not k.startswith("HCCL_DIAG_INJECT_")}
    env.pop("ASCEND_RT_VISIBLE_DEVICES", None)
    env.pop("HCCL_WORKLOAD_RESULT_DIR", None)
    if cluster.get("op_expansion_mode", "AI_CPU") == "DEFAULT":
        env.pop("HCCL_OP_EXPANSION_MODE", None)
    env.update(overrides)
    result = {"status": "preflight_failed", "stage": "preflight", "started_unix_ns": time.time_ns(),
              "injection_effect": "not_evaluated"}
    limiter = None
    clock_server, clock_data = None, None
    try:
        validate_cluster(cluster, case, True, args.allow_background, args.allow_network_change)
        (out / "ascend_log").mkdir()
        (out / "msprof").mkdir()
        node = cluster["nodes"][args.node_rank]
        runtime_files = node.get("runtime_files", [])
        if not runtime_files:
            raise ValueError("record explicit runtime_files (loaded library/kernel paths) before execution")
        hashes = {name: hashlib.sha256(Path(name).read_bytes()).hexdigest() for name in runtime_files}
        npu = captured(["npu-smi", "info"])
        if npu.get("returncode") != 0:
            raise RuntimeError("npu-smi preflight failed")
        write_json(out / "environment.json", {"hostname": socket.gethostname(), "npu_smi": npu,
                   "git": {name: {"head": captured(["git", "-C", str(ROOT / name), "rev-parse", "HEAD"]),
                                  "status": captured(["git", "-C", str(ROOT / name), "status", "--short"])}
                           for name in (".", "hccl", "hcomm")}, "runtime_sha256": hashes,
                   "source_sha256": {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
                       for p in [Path(__file__), ROOT / "test/multinode_commmix_train.py",
                                 ROOT / "test/anomaly_injection/four_node_control.py",
                                 ROOT / "test/anomaly_injection/npu_background_load.py",
                                 ROOT / "test/anomaly_injection/single_node_control.py",
                                 ROOT / "test/multinode_clock_probe.py"]
                       + ([ROOT / "test/two_node_suite.py"] if case["nnodes"] == 2 else [])}})
        if case["injection"]["kind"] == "nic_limit" and args.node_rank == cluster["nic_limit"]["node_rank"]:
            limiter = NicLimit(cluster["nic_limit"], case["injection"]["level"], out / "private")
            limiter.apply()
        if getattr(args, "clock_probe_port", None) is not None:
            if __package__ in (None, ""):
                from multinode_clock_probe import ProbeServer, probe_batch, raw_ns
            else:
                from .multinode_clock_probe import ProbeServer, probe_batch, raw_ns
            port = args.clock_probe_port
            if not 1024 <= port <= 65535 or port in {cluster["master_port"], *range(cluster["background_port_base"], cluster["background_port_base"] + 4)}:
                raise ValueError("clock probe port must be distinct from foreground/background ports")
            names = [n["node_id"] for n in cluster["nodes"]]
            if len(set(names)) != len(names):
                raise ValueError("clock probes require unique explicit physical node IDs")
            clock_data = dict(schema_version=1, clock="CLOCK_MONOTONIC_RAW", capture_id=case["case_id"] + "/" + args.attempt,
                              node_id=names[args.node_rank], reference_node=names[0])
            if args.node_rank == 0:
                clock_server = ProbeServer(cluster["master_addr"], port, clock_data["capture_id"], names[0], names[1:])
                clock_server.__enter__()
                clock_data["before_raw_ns"] = raw_ns()
            else:
                clock_data["before"] = probe_batch(cluster["master_addr"], port, clock_data["capture_id"],
                    names[args.node_rank], names[0], "before", timeout=args.clock_probe_timeout)
        result.update(status="running", stage="workload")
        result["returncode"] = run_capture(command, env, out / "private/capture.log", args.timeout)
        result["status"] = "completed" if result["returncode"] == 0 else "failed"
        ranks_per_node = case["ranks_per_node"]
        expected_ranks = set(range(args.node_rank * ranks_per_node, (args.node_rank + 1) * ranks_per_node))
        results = [read_json(p) for p in (out / "private/events").glob("rank*/workload-result.json")]
        if result["status"] == "completed" and (len(results) != ranks_per_node
                or {r["rank"] for r in results} != expected_ranks
                or any(r["status"] != "passed" or r["max_error"] != 0
                       or r["world_size"] != case["nnodes"] * ranks_per_node for r in results)):
            result.update(status="failed", error="missing, duplicated or invalid per-rank numerical results")
        if case["injection"]["kind"] == "progress_delay" and case["injection"]["mode"] == "library_task":
            result["injection_effect"] = "requires_exact_hit_log_and_db_review"
    except subprocess.TimeoutExpired:
        result["status"] = "timeout"
    except KeyboardInterrupt:
        result["status"] = "interrupted"
    except Exception as error:
        result.update(status="preflight_failed" if result["stage"] == "preflight" else "failed", error=str(error))
    finally:
        if clock_data is not None:
            try:
                if args.node_rank == 0:
                    if clock_server is None or not clock_server.wait_for_after(args.clock_probe_timeout):
                        raise TimeoutError("clock peers did not complete their after probes")
                    clock_data["after_raw_ns"] = raw_ns()
                elif "before" in clock_data:
                    clock_data["after"] = probe_batch(cluster["master_addr"], args.clock_probe_port,
                        clock_data["capture_id"], clock_data["node_id"], clock_data["reference_node"], "after",
                        timeout=args.clock_probe_timeout)
                write_json(out / "clock-probes.json", clock_data)
            except Exception as error:
                result["clock_probe_error"] = str(error)
                if result["status"] == "completed":
                    result["status"] = "clock_collection_failed"
            finally:
                if clock_server is not None:
                    clock_server.__exit__(None, None, None)
        if limiter is not None:
            try:
                limiter.restore()
            except Exception as error:
                result.update(status="restore_failed", restore_error=str(error))
        result["finished_unix_ns"] = time.time_ns()
        result["msprof_db_count"] = len(list((out / "msprof").rglob("msprof_*.db")))
        if not args.no_profile and result["status"] == "completed" and result["msprof_db_count"] == 0:
            result.update(status="collection_failed", error="no consolidated msprof DB was found")
        write_json(out / "execution.json", result)
    print(json.dumps(result, indent=2))
    return 0 if result["status"] == "completed" else 1


def injection_observation(case: dict, attempt: Path) -> str:
    inj = case["injection"]
    ranks_per_node = case["ranks_per_node"]
    if inj["kind"] == "normal":
        return "normal_control"
    if inj["kind"] == "nic_limit":
        path = attempt / f"node{inj['target_rank'] // ranks_per_node}" / "private/nic-verify.json"
        return "cap_configured_effect_unverified" if path.exists() else "not_observed"
    event_root = attempt / f"node{inj['target_rank'] // ranks_per_node}" / "private/events" / f"rank{inj['target_rank']}"
    if inj["kind"] == "progress_delay":
        if inj["mode"] == "library_task":
            node = attempt / f"node{inj['target_rank'] // ranks_per_node}"
            logs = list((node / "ascend_log").rglob("*.log"))
            logs += [node / "private/capture.log"]
            expected = {"type": "task_launch_delay", "user_rank": str(inj["target_rank"]),
                        "delay_us": str(inj["level"] * 1000), "phase": inj["selector"]["phase"],
                        "step": str(inj["selector"]["step"]), "event": inj["selector"]["event"]}
            hits = set()
            for path in logs:
                if not path.is_file():
                    continue
                with path.open(encoding="utf-8", errors="replace") as handle:
                    for line in handle:
                        if "[HcclDiagInject]" not in line:
                            continue
                        fields = dict(re.findall(r"(\w+)\[([^\]]*)\]", line.split("[HcclDiagInject]", 1)[1]))
                        if all(fields.get(k) == v for k, v in expected.items()):
                            hits.add(tuple(sorted(fields.items())))
            if len(hits) == 0:
                return "native_hit_not_observed"
            if len(hits) != 1:
                return "invalid_multiple_native_hits"
            return "native_hit_observed_task_identity_and_effect_unverified"
        path = event_root / "events.jsonl"
        events = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()] if path.exists() else []
        hits = [e for e in events if e["event"] == "arrival_delay_applied"]
        good = len(hits) == 1 and hits[0]["elapsed_ns"] >= inj["level"] * 1_000_000
        return "arrival_delay_observed_effect_unverified" if good else "not_observed"
    participants = [inj["target_rank"]]
    if inj["kind"] == "communication_contention":
        participants.append(inj["peer_rank"])
    for rank in participants:
        root = attempt / f"node{rank // ranks_per_node}" / "private/events" / f"rank{rank}"
        results = [read_json(p) for p in root.glob("worker*/result.json")]
        if len(results) != inj["level"] or any(r["operations"] <= 0 for r in results):
            return "not_observed"
    return "background_executed_effect_unverified"


def summarize(suite_path: Path, runs: Path, output: Path) -> list[dict]:
    suite = read_json(suite_path)
    rows = []
    for entry in suite["cases"]:
        case = read_json(suite_path.parent / entry["path"])
        case_root = runs / identifier(entry["case_id"])
        attempts = sorted(p for p in case_root.iterdir() if p.is_dir()) if case_root.exists() else []
        if not attempts:
            rows.append({"case_id": entry["case_id"], "attempt": "", "baseline_case_id": case["baseline_case_id"],
                         "status": "not_run", "completed_nodes": 0, "injection_observation": "not_observed"})
        for attempt in attempts:
            states = []
            for path in (attempt / f"node{index}/execution.json" for index in range(case["nnodes"])):
                if not path.exists():
                    continue
                try:
                    states.append(read_json(path))
                except (OSError, ValueError):
                    states.append({"status": "malformed_record"})
            completed = sum(s["status"] == "completed" for s in states)
            state = "execution_complete" if completed == case["nnodes"] else "partial"
            if any(s["status"] != "completed" for s in states):
                state = "execution_failed"
            try:
                observation = injection_observation(case, attempt)
            except (OSError, ValueError, KeyError):
                observation = "malformed_injection_evidence"
            rows.append({"case_id": entry["case_id"], "attempt": attempt.name,
                         "baseline_case_id": case["baseline_case_id"], "status": state,
                         "completed_nodes": completed, "injection_observation": observation})
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    return rows


def main(nnodes: int = 4, ranks_per_node: int = 4) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    generate = commands.add_parser("generate")
    generate.add_argument("--output", type=Path, required=True)
    generate.add_argument("--sizes", default="main")
    generate.add_argument("--positions")
    generate.add_argument("--seeds", default="20261022")
    generate.add_argument("--internal-selector", type=Path)
    generate.add_argument("--smoke", action="store_true", help="Separate 1-warmup/2-measurement preflight cases, not formal samples")
    run = commands.add_parser("run-node")
    run.add_argument("--case", type=Path, required=True)
    run.add_argument("--cluster", type=Path, required=True)
    run.add_argument("--node-rank", type=int, choices=range(nnodes), required=True)
    run.add_argument("--output", type=Path, required=True)
    run.add_argument("--attempt", default="attempt-001")
    run.add_argument("--timeout", type=float, default=1800)
    run.add_argument("--execute", action="store_true")
    run.add_argument("--allow-background", action="store_true")
    run.add_argument("--allow-network-change", action="store_true")
    run.add_argument("--no-profile", action="store_true")
    run.add_argument("--diagnosis-capture", action="store_true", help="Record public business calls and omit extra barrier operations")
    run.add_argument("--clock-probe-port", type=int, help="Opt-in independent CPU probes before/after profiling; same free port on all nodes")
    run.add_argument("--clock-probe-timeout", type=float, default=180)
    ledger = commands.add_parser("summarize")
    ledger.add_argument("--suite", type=Path, required=True)
    ledger.add_argument("--runs", type=Path, required=True)
    ledger.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "summarize":
        rows = summarize(args.suite, args.runs, args.output)
        print(f"Wrote {len(rows)} case/attempt records; execution completion is not diagnosis accuracy.")
        return 0
    if args.command == "run-node":
        case = read_json(args.case)
        if (case["nnodes"], case["ranks_per_node"]) != (nnodes, ranks_per_node):
            parser.error("case topology does not match this entry point")
        if args.timeout <= 0:
            parser.error("timeout must be positive")
        if args.execute:
            def interrupt(signum: int, frame: object) -> None:
                raise KeyboardInterrupt
            signal.signal(signal.SIGTERM, interrupt)
        return execute_node(args)
    positions = args.positions or ("0" if args.smoke else "25")
    cases = generate_cases(args.sizes.split(","), [int(x) for x in positions.split(",")],
                           [int(x) for x in args.seeds.split(",")],
                           read_json(args.internal_selector) if args.internal_selector else None, args.smoke,
                           nnodes=nnodes, ranks_per_node=ranks_per_node)
    args.output.mkdir(parents=True, exist_ok=False)
    for case in cases:
        write_json(args.output / "cases" / (case["case_id"] + ".json"), case)
    write_json(args.output / "suite.json", {"schema_version": 1, "status": "planned_not_collected",
               "case_count": len(cases), "normal_count": sum(c["injection"]["kind"] == "normal" for c in cases),
               "cases": [{"case_id": c["case_id"], "baseline_case_id": c["baseline_case_id"],
                          "path": "cases/" + c["case_id"] + ".json"} for c in cases],
               "stats": workload_stats(cases[0])})
    print(f"Generated {len(cases)} planned cases in {args.output}; no devices were used.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
