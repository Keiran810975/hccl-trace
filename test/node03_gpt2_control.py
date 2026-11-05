"""Two-node injection control, without delaying a hook for a background active ACK."""
from __future__ import annotations

import os
import json
from pathlib import Path
import subprocess
import sys

if __package__:
    from .anomaly_injection.single_node_control import SingleControl
else:
    from anomaly_injection.single_node_control import SingleControl


def worker_environment(environment):
    value = dict(environment, HCCL_STEP_TRACE="0", HCCL_TASK_SEMANTIC_TRACE="0")
    for key in list(value):
        if key.startswith(("PROFILING_", "PROFILER_", "MSPROF_", "ASCEND_PROFILER_")):
            del value[key]
    value.pop("HCCL_WORKLOAD_RESULT_DIR", None)
    return value


class MultiNodeControl(SingleControl):
    def __init__(self, config, directory, rank, devices):
        super().__init__(config, directory, rank, devices, gemm_backend="grouped")
        self.kind = self.inj["kind"]
        self.network_first_iteration = None
        self.network_iterations = []
        self.network_closed = False
        self.communication_scoped = config is not None and self.case.get("experiment_contract", {}).get("profile") == "communication-calibration-v1"
        self.bounded_interference = self.case.get("experiment_contract", {}).get("profile") in {"multinode-dual-v1", "multinode20-v1"}
        if self.bounded_interference:
            self.communication_scoped = self.kind not in {"normal", "progress_delay", "bandwidth_limit"}
        if self.kind == "communication_contention":
            self.owner = rank in {self.inj["target_rank"], self.inj["peer_rank"]}

    def prepare(self):
        if not self.owner or self.kind in {"normal", "progress_delay"}:
            return
        if self.kind == "bandwidth_limit":
            # The independent host-side guard is the only process allowed to set a port limit.
            self.wait("network-guard-ready", timeout=60)
            return
        if self.kind != "communication_contention":
            # Isolate background profiling without changing the legacy single-node runner contract.
            super().prepare(environment=worker_environment(os.environ))
            return
        script = Path(__file__).with_name("anomaly_injection") / "npu_background_load.py"
        command = [sys.executable, str(script), "--kind", "communication", "--device", str(self.devices[self.rank]),
                   "--control-dir", str(self.directory), "--buffer-mib", str(self.inj["buffer_mib"]),
                   "--master-addr", os.environ["MASTER_ADDR"], "--master-port", "29775", "--rank",
                   "1" if self.rank == self.inj["target_rank"] else "0", "--timeout", "1800", "--defer-finalize"]
        environment = worker_environment(os.environ)
        environment.update(HCCL_IF_BASE_PORT="57000", HCCL_HOST_SOCKET_PORT_RANGE="57000-57127",
                           HCCL_NPU_SOCKET_PORT_RANGE="57200-57327")
        self.log = (self.directory / "background.log").open("x", encoding="utf-8")
        self.process = subprocess.Popen(command, env=environment, stdout=self.log, stderr=subprocess.STDOUT, start_new_session=True)
        self.record("background_spawn", pid=self.process.pid, command=command, cross_node_pair=sorted([self.inj['peer_rank'], self.inj['target_rank']]),
                    profiling_environment_isolated=True, shared_path_verified=False)
        self.wait("ready")

    def start(self, call):
        if self.kind == "progress_delay":
            return super().start(call)
        if not self.owner:
            return
        if self.started:
            raise RuntimeError("duplicate injection start")
        self.started = True
        self.record("injection_start", call=call)
        (self.directory / "start").touch()
        self.record("start_requested_without_blocking_foreground")

    def after_collective(self, call):
        if (not self.communication_scoped or not self.owner or self.started
                or call["stage"] != "measured" or call["iteration"] != self.inj.get("iteration")):
            return
        self.record("communication_activation_request", sequence=call["sequence"],
                    bucket_signature=call["bucket_signature"], input_buffer_ptr=call["input_buffer_ptr"],
                    activation="after_selected_allreduce_submit",
                    note="API return is not device completion; actual worker overlap is evaluated separately")
        self.start(call["sequence"])

    def before_iteration(self, iteration, total):
        if self.kind != "bandwidth_limit" or not self.owner or not self.started or self.stop_requested:
            return
        result = self.directory / "network-result.json"
        if result.exists():
            raise RuntimeError("network controller finished before the measured window: " + result.read_text())
        active = self.directory / "network-active.json"
        if self.network_first_iteration is not None or not active.exists():
            return
        ack = json.loads(active.read_text())
        if (ack.get("schema_version") != 1 or ack.get("case_id") != self.case["case_id"]
                or ack.get("limit_mbps") != self.inj["limit_mbps"] or ack.get("device") != self.inj["physical_device_id"]
                or ack.get("applied_verified") is not True or type(ack.get("started_raw_ns")) is not int):
            raise ValueError("network activation acknowledgement does not match this experiment")
        if iteration < 0 or iteration + self.inj["duration_iters"] > total:
            (self.directory / "abort").touch()
            raise RuntimeError("not enough formal iterations remain after verified network activation")
        self.network_first_iteration = iteration
        self.record("network_verified_window_begin", requested_iteration=self.inj["iteration"],
                    first_full_iteration=iteration, duration_iters=self.inj["duration_iters"],
                    verified_started_raw_ns=ack["started_raw_ns"])

    def after_iteration(self, iteration):
        if (self.bounded_interference and self.owner and self.kind in {
                "copy_contention", "communication_contention", "compute_contention"} and iteration == self.inj["iteration"]):
            if not self.started:
                raise ValueError("selected collective did not activate the interference")
            self.stop()
            self.wait("paused")
            self.record("background_paused_before_next_iteration")
            return
        if self.kind != "bandwidth_limit" or not self.owner or self.network_first_iteration is None or self.stop_requested:
            return
        expected = self.network_first_iteration + len(self.network_iterations)
        if iteration != expected:
            raise ValueError("verified network window must cover consecutive completed formal iterations")
        self.network_iterations.append(iteration)
        if len(self.network_iterations) == self.inj["duration_iters"]:
            window = dict(schema_version=1, case_id=self.case["case_id"], requested_iteration=self.inj["iteration"],
                          first_full_iteration=self.network_first_iteration, completed_iterations=self.network_iterations)
            temporary = self.directory / "network-measured-window.tmp"
            temporary.write_text(json.dumps(window) + "\n")
            temporary.replace(self.directory / "network-measured-window.json")
            self.stop()

    def finish(self):
        if self.kind != "bandwidth_limit":
            return super().finish()
        if not self.owner:
            return
        if not self.started or len(self.network_iterations) != self.inj["duration_iters"]:
            (self.directory / "abort").touch()
            raise RuntimeError("verified bandwidth limit did not cover the configured complete formal iterations")
        self.stop()
        self.wait("network-restored", timeout=120)
        import json
        result = json.loads((self.directory / "network-result.json").read_text())
        if (not self.started or not result.get("applied_verified") or not result.get("restored_verified")
                or not result.get("foreground_path_verified")
                or result.get("measurement_window", {}).get("completed_iterations") != self.network_iterations):
            raise ValueError("bandwidth injection is not proven to have affected this foreground path and restored")
        self.record("injection_stop", actual_hit=True)
        self.stopped = True

    def close(self):
        if self.kind == "bandwidth_limit" and self.owner and not self.network_closed:
            if not self.stopped and self.directory.is_dir():
                (self.directory / "abort").touch()
            self.network_closed = True
        super().close()
