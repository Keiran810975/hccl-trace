"""Two-node injection control, without delaying a hook for a background active ACK."""
from __future__ import annotations

import os
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
        self.record("background_spawn", pid=self.process.pid, command=command, cross_node_pair=[0, 4],
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

    def finish(self):
        if self.kind != "bandwidth_limit":
            return super().finish()
        if not self.owner:
            return
        self.stop()
        self.wait("network-restored", timeout=120)
        import json
        result = json.loads((self.directory / "network-result.json").read_text())
        if (not self.started or not result.get("applied_verified") or not result.get("restored_verified")
                or not result.get("foreground_path_verified")):
            raise ValueError("bandwidth injection is not proven to have affected this foreground path and restored")
        self.record("injection_stop", actual_hit=True)
        self.stopped = True
