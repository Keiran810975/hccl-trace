"""Opt-in public training observations; never submits device tasks or barriers."""
from __future__ import annotations

from contextlib import contextmanager
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

    def __init__(self, directory, *, node_id, user_rank, device_id, run_id="capture"):
        if any(type(v) is not int or v < 0 for v in (user_rank, device_id)):
            raise ValueError("explicit nonnegative global rank and profiler device ID required")
        if not node_id or not run_id:
            raise ValueError("node and shared run ID required")
        self.node_id, self.rank, self.device, self.run_id = node_id, user_rank, device_id, run_id
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self.groups, self.pending, self.occurrences = {}, [], {}
        self.active_iteration, self.sequence = None, 0
        self._owner_thread = threading.get_ident()
        self._file = (self.directory / ("rank-{}.jsonl".format(user_rank))).open("x", encoding="utf-8")
        self._write(dict(event="runtime", schema_version=1, run_id=run_id, node_id=node_id,
                         user_rank=user_rank, device_id=device_id, pid=os.getpid()))

    @classmethod
    def from_environment(cls, *, device_id=None, node_id=None):
        env = os.environ
        directory = env.get("HCCL_TRACE_CALLS_DIR")
        if not directory or "RANK" not in env:
            raise ValueError("set HCCL_TRACE_CALLS_DIR and RANK for training observations")
        if device_id is None:
            if "HCCL_TRACE_DEVICE_ID" not in env:
                raise ValueError("provide actual profiler device_id; it is not inferred from LOCAL_RANK")
            device_id = int(env["HCCL_TRACE_DEVICE_ID"])
        return cls(directory, node_id=node_id or env.get("HCCL_TRACE_NODE_ID", socket.gethostname()),
                   user_rank=int(env["RANK"]), device_id=device_id,
                   run_id=env.get("HCCL_TRACE_RUN_ID", "capture"))

    def _write(self, value):
        self._file.write(json.dumps(value, ensure_ascii=False, sort_keys=True) + "\n")
        self._file.flush()

    def group(self, name, participants, *, db_group_name=None):
        members = list(participants)
        if (not isinstance(name, str) or not name or not members
                or any(type(rank) is not int or rank < 0 for rank in members)
                or len(set(members)) != len(members) or self.rank not in members):
            raise ValueError("explicit unique group members including this rank required")
        value = dict(group_id=name, participants=sorted(members), db_group_name=db_group_name)
        if name in self.groups and self.groups[name] != value:
            raise ValueError("communication group identity changed")
        self.groups[name] = value

    @contextmanager
    def iteration(self, index, *, stage="measured"):
        if (self.active_iteration is not None or type(index) is not int or index < 0
                or stage not in {"warmup", "measured"}):
            raise ValueError("non-nested iteration with explicit warmup/measured stage required")
        self.active_iteration = stage, index
        self.occurrences = {}
        try:
            yield self
        finally:
            self.active_iteration = None

    @contextmanager
    def collective(self, *, group, call_site, operation_type, element_count, dtype, reduction=None,
                   preparation_start_raw_ns=None):
        if threading.get_ident() != self._owner_thread:
            raise ValueError("concurrent submitting threads require an explicit framework adapter; call order is not guessed")
        if self.active_iteration is None or group not in self.groups or not call_site:
            raise ValueError("collective requires an active iteration, registered group and stable call_site")
        if type(element_count) is not int or element_count < 0:
            raise ValueError("element_count must describe the actual input tensor")
        key = group, call_site
        occurrence = self.occurrences.get(key, 0)
        self.occurrences[key] = occurrence + 1
        stage, iteration = self.active_iteration
        item = dict(event="call", schema_version=1, sequence=self.sequence, node_id=self.node_id,
                    user_rank=self.rank, device_id=self.device, run_id=self.run_id,
                    stage=stage, iteration=iteration, call_site=call_site, occurrence=occurrence,
                    operation_type=operation_type, element_count=element_count, dtype=dtype,
                    reduction=reduction, before=_clocks(), **self.groups[group])
        self.sequence += 1
        if preparation_start_raw_ns is not None:
            if type(preparation_start_raw_ns) is not int or not 0 <= preparation_start_raw_ns <= item["before"]["raw_ns"]:
                raise ValueError("preparation start must be an actual earlier raw-clock observation")
            item["preparation_start_raw_ns"] = preparation_start_raw_ns
        try:
            yield self
        except BaseException:
            item.update(after=_clocks(), status="failed")
            self._write(item)
            raise
        else:
            item.update(after=_clocks(), status="submitted")
            self._write(item)
            self.pending.append(item["sequence"])

    def completion_boundary(self):
        """Call only after the user's existing synchronize()/Work completion.

        This function records the observation; it never performs synchronization.
        The binder also requires every selected DB operation to end by this bound.
        """
        self._write(dict(event="completion", schema_version=1, sequences=list(self.pending), clocks=_clocks()))
        self.pending.clear()

    def close(self):
        if not self._file.closed:
            self._write(dict(event="capture_end", schema_version=1, pending_sequences=list(self.pending)))
            self._file.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()


__all__ = ["Trace"]
