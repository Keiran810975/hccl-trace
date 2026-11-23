"""Opt-in public training observations; never submits device tasks or barriers."""
from __future__ import annotations

from contextlib import contextmanager, suppress
import json
import os
from pathlib import Path
import socket
import threading
import time


def _clocks():
    if not hasattr(time, "CLOCK_MONOTONIC_RAW"):
        raise RuntimeError("capture requires CLOCK_MONOTONIC_RAW on the Linux training host")
    return dict(raw_ns=time.clock_gettime_ns(time.CLOCK_MONOTONIC_RAW), unix_ns=time.time_ns())


class Trace:
    """Record explicit rank/device, group membership and public call boundaries.

    Complete pending calls only AFTER an existing user-controlled device/work
    completion boundary. A Python collective return is not device completion.
    """

    def __init__(self, directory, *, node_id, user_rank, device_id, run_id="capture", online_probe=None,
                 timing_adapter=None, world_size=None):
        if any(type(v) is not int or v < 0 for v in (user_rank, device_id)):
            raise ValueError("explicit nonnegative global rank and profiler device ID required")
        if not node_id or not run_id:
            raise ValueError("node and shared run ID required")
        if world_size is not None and (type(world_size) is not int or world_size <= user_rank):
            raise ValueError("world_size must include this global rank")
        self.node_id, self.rank, self.device, self.run_id = node_id, user_rank, device_id, run_id
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self.groups, self.pending, self.occurrences = {}, [], {}
        self.active_iteration, self.sequence = None, 0
        self._owner_thread = threading.get_ident()
        self._file = (self.directory / ("rank-{}.jsonl".format(user_rank))).open("x", encoding="utf-8")
        self.online_probe = online_probe
        self.timing_adapter = timing_adapter
        self.online_token = None
        self._active_call = False
        self._failed_completion = False
        self._host_log_ns = self._host_log_writes = 0
        self._online_generations, self._online_pending = {}, []
        runtime = dict(event="runtime", schema_version=1, run_id=run_id, node_id=node_id,
                       user_rank=user_rank, device_id=device_id, pid=os.getpid())
        if world_size is not None:
            runtime["world_size"] = world_size
        self._write(runtime)

    @classmethod
    def from_environment(cls, *, device_id=None, node_id=None, timing_adapter=None):
        env = os.environ
        directory = env.get("HCCL_TRACE_CALLS_DIR")
        if not directory or "RANK" not in env:
            raise ValueError("set HCCL_TRACE_CALLS_DIR and RANK for training observations")
        if device_id is None:
            if "HCCL_TRACE_DEVICE_ID" not in env:
                raise ValueError("provide actual profiler device_id; it is not inferred from LOCAL_RANK")
            device_id = int(env["HCCL_TRACE_DEVICE_ID"])
        node_id = node_id or env.get("HCCL_TRACE_NODE_ID", socket.gethostname())
        user_rank = int(env["RANK"])
        world_size = int(env["WORLD_SIZE"]) if "WORLD_SIZE" in env else None
        run_id = env.get("HCCL_TRACE_RUN_ID", "capture")
        probe = None
        if env.get("HCCL_TRACE_ONLINE_ADDR") or env.get("HCCL_TRACE_ONLINE_TIMING", "host") != "host" or timing_adapter:
            from .online_probe import OnlineProbe

            if not env.get("HCCL_TRACE_RUN_ID"):
                raise ValueError("online telemetry requires an explicit shared HCCL_TRACE_RUN_ID")
            probe = OnlineProbe.from_environment(job_id=run_id, rank_id=user_rank, node_id=node_id,
                                                 timing_adapter=timing_adapter)
        try:
            return cls(directory, node_id=node_id, user_rank=user_rank, device_id=device_id,
                       run_id=run_id, online_probe=probe, timing_adapter=timing_adapter, world_size=world_size)
        except BaseException:
            if probe is not None:
                with suppress(RuntimeError):
                    probe.close()
            raise

    def _write(self, value):
        start = time.perf_counter_ns() if self.online_probe is not None else None
        self._file.write(json.dumps(value, ensure_ascii=False, sort_keys=True) + "\n")
        self._file.flush()
        if start is not None:
            self._host_log_ns += time.perf_counter_ns() - start
            self._host_log_writes += 1

    def _check_owner(self):
        if threading.get_ident() != self._owner_thread:
            raise ValueError("concurrent trace updates require an explicit framework adapter")

    def group(self, name, participants, *, db_group_name=None, communicator_generation=0):
        self._check_owner()
        members = list(participants)
        if (not isinstance(name, str) or not name or not members
                or any(type(rank) is not int or rank < 0 for rank in members)
                or len(set(members)) != len(members) or self.rank not in members):
            raise ValueError("explicit unique group members including this rank required")
        value = dict(group_id=name, participants=sorted(members), db_group_name=db_group_name)
        if name in self.groups and self.groups[name] != value:
            raise ValueError("communication group identity changed")
        if self.online_probe is not None:
            if self.timing_adapter is not None:
                self.timing_adapter.validate_group(name, value["participants"])
            self.online_probe.register(name, communicator_generation, members)
            self._online_generations[name] = communicator_generation
        self.groups[name] = value

    @contextmanager
    def iteration(self, index, *, stage="measured"):
        self._check_owner()
        if (self.active_iteration is not None or type(index) is not int or index < 0
                or stage not in {"warmup", "measured"}):
            raise ValueError("non-nested iteration with explicit warmup/measured stage required")
        self.active_iteration = stage, index
        self.occurrences = {}
        try:
            before = _clocks()
            try:
                yield self
            except BaseException:
                self._write(dict(event="iteration", schema_version=1, stage=stage, iteration=index,
                                 before=before, after=_clocks(), status="failed"))
                raise
            else:
                self._write(dict(event="iteration", schema_version=1, stage=stage, iteration=index,
                                 before=before, after=_clocks(), status="finished"))
        finally:
            self.active_iteration = None

    @contextmanager
    def collective(self, *, group, call_site, operation_type, element_count, dtype, reduction=None,
                   preparation_start_raw_ns=None):
        if self.online_probe is not None:
            raise ValueError("online telemetry requires Trace.call_collective; a with block is not a call boundary")
        with self._observe_collective(group=group, call_site=call_site, operation_type=operation_type,
                element_count=element_count, dtype=dtype, reduction=reduction,
                preparation_start_raw_ns=preparation_start_raw_ns):
            yield self

    @staticmethod
    def mark_preparation():
        """Take a local raw-clock observation at the actual start of preparation."""
        return time.clock_gettime_ns(time.CLOCK_MONOTONIC_RAW)

    def call_collective(self, submit, /, *, wait_for_work=False, preparation_definition=None, **signature):
        """Wrap only the submitting API; run an existing Work.wait outside its Host interval."""
        self._check_owner()
        if self._active_call or self.online_token is not None:
            raise ValueError("nested collectives do not have a single explicit API boundary")
        probe, adapter = self.online_probe, self.timing_adapter
        timing = token = None
        if probe is not None:
            from .online_probe import tensor_description

            dtype, size = tensor_description(signature["dtype"], signature["element_count"])
            kind = "".join(c for c in signature["operation_type"].lower() if c.isalnum()).removeprefix("hcom")
            reduction = signature.get("reduction")
            reduction = str(reduction).lower() if reduction is not None else None
            if adapter is not None:
                if not wait_for_work:
                    raise ValueError("NPU Event timing must use the existing Work.wait dependency")
                timing = adapter.begin(op_type=kind, bucket=signature["call_site"], tensor_bytes=size,
                    dtype=dtype, reduction=reduction, rank=self.rank,
                    participants=self.groups[signature["group"]]["participants"])
        submitted = False
        try:
            with self._observe_collective(**signature) as item:
                if probe is not None:
                    group = item["group_id"]
                    start = item.get("preparation_start_raw_ns")
                    if (start is None) != (preparation_definition is None):
                        raise ValueError("preparation timing requires an explicit start and definition")
                    token = probe.enter(group, self._online_generations[group], op_type=kind, tensor_bytes=size,
                        host_entry_ts=item["before"]["raw_ns"], stage=item["stage"], iteration=item["iteration"],
                        bucket_id=item["call_site"], occurrence=item["occurrence"], dtype=dtype, reduction=reduction,
                        preparation_ns=None if start is None else item["before"]["raw_ns"]-start,
                        preparation_definition=preparation_definition, host_entry_source="sdk_collective_submit")
                    self.online_token = token
                    item.update(online_op_counter=token.op_counter,
                                online_communicator_generation=token.communicator_generation)
                work = submit()
            submitted = True
            if wait_for_work and work.wait() is False:
                raise RuntimeError("collective Work.wait reported failure")
            if timing is not None:
                adapter.end(token, timing)
            return work
        except BaseException:
            if submitted:
                self._failed_completion = True
            if token is not None:
                probe.error(token)
            raise
        finally:
            self.online_token = None

    @contextmanager
    def _observe_collective(self, *, group, call_site, operation_type, element_count, dtype, reduction=None,
                            preparation_start_raw_ns=None):
        self._check_owner()
        if self._active_call:
            raise ValueError("nested collectives do not have a single explicit API boundary")
        if self.active_iteration is None or group not in self.groups or not call_site:
            raise ValueError("collective requires an active iteration, registered group and stable call_site")
        if type(element_count) is not int or element_count < 0:
            raise ValueError("element_count must describe the actual input tensor")
        key = group, call_site
        occurrence = self.occurrences.get(key, 0)
        stage, iteration = self.active_iteration
        item = dict(event="call", schema_version=1, sequence=self.sequence, node_id=self.node_id,
                    user_rank=self.rank, device_id=self.device, run_id=self.run_id,
                    stage=stage, iteration=iteration, call_site=call_site, occurrence=occurrence,
                    operation_type=operation_type, element_count=element_count, dtype=dtype,
                    reduction=reduction, before=_clocks(), **self.groups[group])
        if preparation_start_raw_ns is not None:
            if type(preparation_start_raw_ns) is not int or not 0 <= preparation_start_raw_ns <= item["before"]["raw_ns"]:
                raise ValueError("preparation start must be an actual earlier raw-clock observation")
            item["preparation_start_raw_ns"] = preparation_start_raw_ns
        self.occurrences[key] = occurrence + 1
        self.sequence += 1
        self._active_call = True
        try:
            yield item
        except BaseException:
            item.update(after=_clocks(), status="failed")
            self._write(item)
            raise
        else:
            item.update(after=_clocks(), status="submitted")
            self._write(item)
            self.pending.append(item["sequence"])
            if self.online_token is not None:
                self._online_pending.append(self.online_token)
        finally:
            self._active_call = False

    def completion_boundary(self):
        """Call only after the user's existing synchronize()/Work completion.

        This function records the observation; it never performs synchronization.
        The binder also requires every selected DB operation to end by this bound.
        """
        self._check_owner()
        if self._failed_completion:
            raise RuntimeError("cannot mark failed collective completion as successful")
        clocks = _clocks()
        self._write(dict(event="completion", schema_version=1, sequences=list(self.pending), clocks=clocks))
        self.pending.clear()
        if self.online_probe is not None:
            for token in self._online_pending:
                self.online_probe.host_boundary(token, clocks["raw_ns"])
            self._online_pending.clear()
            if self.timing_adapter is not None:
                self.timing_adapter.flush(self.online_probe)

    def close(self):
        self._check_owner()
        try:
            if not self._file.closed:
                record = dict(event="capture_end", schema_version=1, pending_sequences=list(self.pending))
                if self._failed_completion:
                    record["status"] = "failed_completion"
                self._write(record)
                self._file.close()
        finally:
            if self.online_probe is not None:
                self.online_probe.close(pending_calls=len(self.pending),
                    host_log=dict(writes=self._host_log_writes, elapsed_ns=self._host_log_ns))

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        if exc[0] is None:
            self.close()
        else:
            with suppress(RuntimeError):
                self.close()


__all__ = ["Trace"]
