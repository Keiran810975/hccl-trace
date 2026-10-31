"""Single-node random-window injection; private truth never enters analysis."""
from __future__ import annotations

import atexit
import json
import os
from pathlib import Path
import subprocess
import sys
import time


def clocks():
    return dict(unix_ns=time.time_ns(), raw_ns=time.clock_gettime_ns(time.CLOCK_MONOTONIC_RAW),
                monotonic_ns=time.monotonic_ns())


class PublicCalls:
    def __init__(self, directory, rank, device):
        directory = Path(directory)
        directory.mkdir(parents=True, exist_ok=True)
        self.file = (directory / ("rank-{}.jsonl".format(rank))).open("x", encoding="utf-8")
        self.boundaries = (directory / ("boundaries-rank-{}.jsonl".format(rank))).open("x", encoding="utf-8")
        self.controls = (directory / ("controls-rank-{}.jsonl".format(rank))).open("x", encoding="utf-8")
        self.rank, self.device, self.sequence = rank, device, 0
        self.preparation = None

    def prepare(self, step, block, bucket, count):
        if self.preparation is not None:
            raise ValueError("previous public preparation was not consumed")
        self.preparation = dict(location=(step, block, bucket, count), clocks=clocks())

    def begin(self, step, block, bucket, count):
        self.current = dict(sequence=self.sequence, rank=self.rank, runtime_device_id=self.device,
                            stage="measured" if step >= 0 else "warmup",
                            iteration=step if step >= 0 else -step - 1, block=block, bucket=bucket,
                            count=count, dtype="fp32", reduction="sum", before=clocks())
        if self.preparation is not None:
            if self.preparation["location"] != (step, block, bucket, count):
                raise ValueError("public preparation/call location mismatch")
            self.current["preparation_before"] = self.preparation["clocks"]
            self.preparation = None

    def end(self):
        self.current["after"] = clocks()
        self.file.write(json.dumps(self.current, sort_keys=True) + "\n")
        self.file.flush()
        self.sequence += 1

    def close(self):
        self.file.close()
        self.boundaries.close()
        self.controls.close()

    def control_begin(self, label, count, dtype, reduction):
        self.control = dict(label=label, rank=self.rank, runtime_device_id=self.device,
                            count=count, dtype=dtype, reduction=reduction, before=clocks())

    def control_end(self):
        self.control["after"] = clocks()
        self.controls.write(json.dumps(self.control) + "\n")
        self.controls.flush()

    def controls_done(self):
        self.controls.write(json.dumps(dict(label="configuration_device_synchronized", rank=self.rank,
                                            clocks=clocks())) + "\n")
        self.controls.flush()

    def iteration_done(self, step):
        self.boundaries.write(json.dumps(dict(rank=self.rank, stage="measured" if step >= 0 else "warmup",
                                              iteration=step if step >= 0 else -step - 1,
                                              device_synchronized=True, clocks=clocks())) + "\n")
        self.boundaries.flush()


class SingleControl:
    def __init__(self, config, directory, rank, devices, communication_worker=None, gemm_backend="matmul"):
        self.case = json.loads(Path(config).read_text(encoding="utf-8"))
        self.inj = self.case["injection"]
        self.directory, self.rank = Path(directory), rank
        self.directory.mkdir(parents=True, exist_ok=True)
        self.process, self.log = None, None
        self.started, self.stopped = False, False
        self.stop_requested = False
        self.owner = self.inj.get("target_rank") == rank
        self.devices, self.communication_worker = devices, communication_worker
        self.gemm_backend = gemm_backend
        atexit.register(self.close)

    def record(self, event, **fields):
        with (self.directory / ("rank-{}.jsonl".format(self.rank))).open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(dict(event=event, rank=self.rank, clocks=clocks(), **fields)) + "\n")

    def wait(self, name, timeout=180):
        deadline = time.monotonic() + timeout
        while not (self.directory / name).exists():
            if self.process is not None and self.process.poll() is not None:
                raise RuntimeError("background worker exited before {}".format(name))
            if time.monotonic() > deadline:
                raise TimeoutError("background worker did not signal {}".format(name))
            time.sleep(.005)

    def prepare(self, *, environment=None):
        kind = self.inj["kind"]
        if not self.owner or kind in {"normal", "progress_delay"}:
            return
        if kind == "communication_contention":
            if not self.communication_worker:
                raise ValueError("single-process native communication worker is required")
            command = [str(self.communication_worker), str(self.devices[self.rank]),
                       str(self.devices[self.inj["peer_rank"]]), str(self.inj["buffer_mib"]),
                       str(self.directory), "--defer-finalize"]
        else:
            backend = self.inj.get("copy_backend", "tensor")
            if kind == "copy_contention" and backend not in {"tensor", "acl_memcpy_async"}:
                raise ValueError("unknown copy backend")
            worker = "acl_copy_load.py" if kind == "copy_contention" and backend == "acl_memcpy_async" else "npu_background_load.py"
            command = [sys.executable, str(Path(__file__).with_name(worker)),
                       "--kind", "copy" if kind == "copy_contention" else "compute",
                       "--device", str(self.devices[self.rank]), "--control-dir", str(self.directory),
                       "--timeout", "1800", "--defer-finalize"]
            if kind == "copy_contention":
                command += ["--buffer-mib", str(self.inj["buffer_mib"])]
            else:
                command += ["--matrix-size", str(self.inj["matrix_size"]), "--gemm-backend", self.gemm_backend]
        env = dict(os.environ if environment is None else environment,
                   HCCL_STEP_TRACE="0", HCCL_TASK_SEMANTIC_TRACE="0")
        if kind == "communication_contention":
            # The foreground keeps its original ports. Separate only this process's
            # bootstrap and transport listeners on the same physical devices.
            env.update(HCCL_IF_BASE_PORT="53000", HCCL_HOST_SOCKET_PORT_RANGE="53000-53063",
                       HCCL_NPU_SOCKET_PORT_RANGE="53100-53163")
        # Keep background profiler inputs separate from the four foreground ranks.
        env.pop("HCCL_WORKLOAD_RESULT_DIR", None)
        self.log = (self.directory / "background.log").open("x", encoding="utf-8")
        self.process = subprocess.Popen(command, env=env, stdout=self.log, stderr=subprocess.STDOUT,
                                        start_new_session=True)
        self.record("background_spawn", pid=self.process.pid, command=command,
                    port_environment={key: env[key] for key in
                                      ("HCCL_IF_BASE_PORT", "HCCL_HOST_SOCKET_PORT_RANGE", "HCCL_NPU_SOCKET_PORT_RANGE") if key in env})
        self.wait("ready")

    def before_collective(self, step, block, bucket):
        if not self.owner or step < 0:
            return
        slot = step * 12 + block * 3 + bucket
        if slot == self.inj["start_call"]:
            self.start(slot)
        if self.inj["kind"] != "progress_delay" and slot == self.inj["start_call"] + self.inj["duration_calls"]:
            self.stop()

    def start(self, call):
        if not self.owner:
            return
        if self.started:
            raise RuntimeError("the selected injection call occurred more than once")
        self.started = True
        self.record("injection_start", call=call)
        if self.inj["kind"] == "progress_delay":
            time.sleep(self.inj["delay_ms"] / 1000)
            self.record("injection_stop", call=call, actual_hit=True)
            self.stopped = True
        else:
            (self.directory / "start").touch()
            self.wait("active")
            self.record("background_active_confirmed")

    def stop(self):
        if self.started and not self.stopped and not self.stop_requested:
            (self.directory / "stop").touch()
            self.record("injection_stop_requested")
            self.stop_requested = True

    def finish(self):
        if self.owner and self.inj["kind"] != "normal":
            self.stop()
            if self.started and self.inj["kind"] != "progress_delay":
                self.wait("paused")
                activity = json.loads((self.directory / "activity-window.json").read_text())
                authorized = clocks()["raw_ns"]
                self.record("measurement_finished_finalize_authorized")
                (self.directory / "finalize").touch()
                self.process.wait(timeout=180)
                if self.process.returncode:
                    raise RuntimeError("background worker failed its numerical/lifetime check")
                result = json.loads((self.directory / "result.json").read_text())
                if result.get("finalize_deferred") is not True or result.get("max_error") != 0 or result.get("operations", 0) <= 0:
                    raise ValueError("background did not honor deferred finalization or numerical validation")
                if (any(result.get(k) != activity.get(k) for k in ("started_raw_ns", "finished_raw_ns", "operations"))
                        or not result["started_raw_ns"] <= result["finished_raw_ns"] <= authorized <= result["finalize_authorized_raw_ns"]):
                    raise ValueError("background activity and post-measurement finalization clocks disagree")
                self.record("injection_stop", actual_hit=True)
                self.stopped = True
            if not self.started or not self.stopped:
                raise RuntimeError("configured injection was not executed")

    def close(self):
        if self.process is not None and self.process.poll() is None:
            (self.directory / "stop").touch()
            (self.directory / "finalize").touch()
            try:
                self.process.wait(timeout=20)
            except subprocess.TimeoutExpired:
                import signal
                os.killpg(self.process.pid, signal.SIGTERM)
                try:
                    self.process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    os.killpg(self.process.pid, signal.SIGKILL)
                    self.process.wait()
        if self.log is not None:
            self.log.close()
