"""Host-side test control; this is not part of the diagnosis input or trace schema."""

from __future__ import annotations

import json
import hashlib
import os
from pathlib import Path
import subprocess
import sys
import time

try:
    from test.four_node_suite import read_json, validate_case, write_json
except ModuleNotFoundError:
    from four_node_suite import read_json, validate_case, write_json


class CaseControl:
    def __init__(self, case: dict, cluster: dict, rank: int, local_rank: int, events_dir: Path):
        validate_case(case)
        self.case, self.cluster, self.rank, self.local_rank = case, cluster, rank, local_rank
        self.inj = case["injection"]
        self.ranks_per_node = case["ranks_per_node"]
        self.world_size = case["nnodes"] * self.ranks_per_node
        self.device_id = cluster["nodes"][rank // self.ranks_per_node]["devices"][local_rank]
        self.directory = events_dir / f"rank{rank}"
        self.directory.mkdir(parents=True, exist_ok=False)
        self.events = (self.directory / "events.jsonl").open("w", encoding="utf-8")
        self.workers = []
        self.logs = []
        self.closed = False
        self.emit("control_created", kind=self.inj["kind"])

    def verify_configuration(self, torch: object, dist: object, device: str) -> None:
        payload = json.dumps({"case": self.case, "cluster": self.cluster}, sort_keys=True).encode()
        digest = hashlib.sha256(payload).digest()
        expected = torch.tensor(list(digest), dtype=torch.int32, device=device)
        actual = expected.clone()
        dist.all_reduce(actual, op=dist.ReduceOp.SUM)
        mismatch = torch.tensor([int(bool(torch.any(actual != expected * self.world_size).item()))],
                                dtype=torch.int32, device=device)
        dist.all_reduce(mismatch, op=dist.ReduceOp.MAX)
        if mismatch.item():
            raise ValueError("nodes launched different cases or cluster configurations")
        self.emit("configuration_agreed", sha256=digest.hex())

    def emit(self, event: str, **fields: object) -> None:
        self.events.write(json.dumps({"event": event, "rank": self.rank, "pid": os.getpid(),
                                     "unix_ns": time.time_ns(), "monotonic_ns": time.monotonic_ns(),
                                     **fields}, sort_keys=True) + "\n")
        if event != "collective_submit":
            self.events.flush()

    def wait_files(self, name: str, timeout: float = 180) -> None:
        deadline = time.monotonic() + timeout
        while not all((directory / name).exists() for _, directory in self.workers):
            for process, directory in self.workers:
                if process.poll() is not None:
                    raise RuntimeError(f"background worker exited before {name}: {directory}, rc={process.returncode}")
            if time.monotonic() >= deadline:
                raise TimeoutError("background workers did not reach " + name)
            time.sleep(0.01)

    def prepare(self) -> None:
        kind = self.inj["kind"]
        if kind not in {"copy_contention", "compute_contention", "communication_contention"}:
            return
        participants = [self.inj["target_rank"]]
        if kind == "communication_contention":
            participants.append(self.inj["peer_rank"])
        if self.rank not in participants:
            return
        script = Path(__file__).with_name("npu_background_load.py")
        worker_kind = {"copy_contention": "copy", "compute_contention": "compute",
                       "communication_contention": "communication"}[kind]
        for index in range(self.inj["level"]):
            directory = self.directory / f"worker{index}"
            directory.mkdir()
            command = [sys.executable, str(script), "--kind", worker_kind, "--device", str(self.device_id),
                       "--control-dir", str(directory), "--timeout", "1200"]
            if worker_kind == "communication":
                server_node = self.cluster["nodes"][participants[0] // self.ranks_per_node]
                address = server_node.get("background_addr")
                if not address:
                    raise ValueError("background_addr is required on the target node")
                command += ["--master-addr", address, "--master-port",
                            str(self.cluster["background_port_base"] + index),
                            "--rank", str(participants.index(self.rank))]
            env = {k: v for k, v in os.environ.items() if not k.startswith("HCCL_DIAG_INJECT_")}
            for key in ("RANK", "WORLD_SIZE", "LOCAL_RANK", "LOCAL_WORLD_SIZE", "GROUP_RANK",
                        "ROLE_RANK", "MASTER_ADDR", "MASTER_PORT"):
                env.pop(key, None)
            (directory / "ascend_log").mkdir()
            env.update(HCCL_STEP_TRACE="0", HCCL_TASK_SEMANTIC_TRACE="0",
                       ASCEND_PROCESS_LOG_PATH=str(directory / "ascend_log"))
            if worker_kind == "communication":
                # HCCL's internal listeners also need isolation, not just TCPStore.
                env.update(HCCL_HOST_SOCKET_PORT_RANGE="auto", HCCL_NPU_SOCKET_PORT_RANGE="auto")
            log = (directory / "worker.log").open("w", encoding="utf-8")
            self.logs.append(log)
            # Children remain in the torchrun process group for bounded outer cleanup.
            process = subprocess.Popen(command, env=env, stdout=log, stderr=subprocess.STDOUT)
            self.workers.append((process, directory))
            self.emit("worker_spawned", pid=process.pid, index=index, runtime_device_index=self.device_id)
        self.wait_files("ready")
        self.emit("workers_ready", count=len(self.workers))

    def transition(self, iteration: int) -> bool:
        start = self.inj["iteration"]
        end = start + self.inj["duration_iters"]
        if iteration not in {start, end}:
            return False
        if iteration == start:
            for _, directory in self.workers:
                (directory / "start").touch()
            if self.workers:
                self.wait_files("active")
            self.emit("window_start", iteration=iteration)
        else:
            self.stop_workers()
            self.emit("window_stop", iteration=iteration)
        return True

    def before_collective(self, iteration: int, block: int, bucket: int) -> None:
        self.emit("collective_submit", iteration=iteration, block=block, bucket=bucket,
                  input_mib=self.case["workload"]["bucket_mib"][bucket])
        if (self.inj["kind"] == "progress_delay" and self.inj["mode"] == "arrival"
                and self.rank == self.inj["target_rank"]
                and (iteration, block, bucket) == (self.inj["iteration"], self.inj["block"], self.inj["bucket"])):
            before = time.monotonic_ns()
            time.sleep(self.inj["level"] / 1000)
            self.emit("arrival_delay_applied", iteration=iteration, block=block, bucket=bucket,
                      requested_ms=self.inj["level"], elapsed_ns=time.monotonic_ns() - before)

    def step_done(self, iteration: int, elapsed_ns: int) -> None:
        for process, directory in self.workers:
            if (directory / "start").exists() and not (directory / "stop").exists() and process.poll() is not None:
                raise RuntimeError(f"background worker ended during its requested window: {directory}")
        self.emit("iteration_complete", iteration=iteration, elapsed_ns=elapsed_ns)

    def stop_workers(self) -> None:
        for _, directory in self.workers:
            (directory / "stop").touch()
        deadline = time.monotonic() + 180
        for process, directory in self.workers:
            process.wait(timeout=max(0.1, deadline - time.monotonic()))
            if process.returncode != 0:
                raise RuntimeError(f"background worker failed: {directory}, rc={process.returncode}")

    def close(self, completed: bool = False) -> None:
        if self.closed:
            return
        self.closed = True
        cleanup_error = None
        try:
            self.stop_workers()
        except Exception as error:
            cleanup_error = str(error)
        finally:
            for process, _ in self.workers:
                if process.poll() is None:
                    process.terminate()
                    try:
                        process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait()
            for log in self.logs:
                log.close()
            self.emit("control_closed", completed=completed and cleanup_error is None, cleanup_error=cleanup_error)
            self.events.close()
        if completed and cleanup_error:
            raise RuntimeError(cleanup_error)

    def record_result(self, result: dict) -> None:
        write_json(self.directory / "workload-result.json", result)


def load_control(case_path: Path, cluster_path: Path, events_dir: Path,
                 rank: int, local_rank: int, world_size: int, args: object) -> CaseControl:
    case, cluster = read_json(case_path), read_json(cluster_path)
    validate_case(case)
    if world_size != case["nnodes"] * case["ranks_per_node"]:
        raise ValueError("world size does not match the case topology")
    node = rank // case["ranks_per_node"]
    if not 0 <= node < case["nnodes"] or local_rank != rank % case["ranks_per_node"]:
        raise ValueError("global/local rank does not match the case topology")
    for key in ("blocks", "tokens", "hidden_size", "ffn_size", "warmup", "iters"):
        if getattr(args, key) != case["workload"][key]:
            raise ValueError("command/case workload mismatch: " + key)
    buckets = [float(x) for x in args.bucket_mib.split(",")]
    if buckets != case["workload"]["bucket_mib"] or args.seed != case["seed"]:
        raise ValueError("command/case buckets or seed mismatch")
    if args.delay_ms != 0 or args.no_barrier:
        raise ValueError("case control cannot be mixed with legacy delay or --no-barrier")
    return CaseControl(case, cluster, rank, local_rank, events_dir)
