"""Bounded Host telemetry; never query or synchronize the NPU."""
from __future__ import annotations

from dataclasses import dataclass
import json
import os
import queue
import socket
import threading
import time
import uuid


@dataclass(frozen=True)
class OperationToken:
    job_id: str
    communicator_id: str
    communicator_generation: int
    op_counter: int
    rank_id: int


def _natural(value):
    return type(value) is int and value >= 0


_SIZES = {"int8": 1, "uint8": 1, "bool": 1, "int16": 2, "uint16": 2,
          "float16": 2, "bfloat16": 2, "int32": 4, "uint32": 4, "float32": 4,
          "int64": 8, "uint64": 8, "float64": 8}
_ALIASES = {"fp16": "float16", "fp32": "float32", "fp64": "float64", "bf16": "bfloat16"}


def tensor_description(dtype, count):
    kind = str(dtype).lower().removeprefix("torch.")
    kind = _ALIASES.get(kind, kind)
    if kind not in _SIZES or not _natural(count):
        raise ValueError("online telemetry requires a supported dtype and actual input element count")
    return kind, count * _SIZES[kind]


class OnlineProbe:
    """The training thread only assigns IDs and enqueues; TCP runs on one worker."""

    def __init__(self, address, *, job_id, rank_id, host_clock_domain,
                 auth_token=None, heartbeat_seconds=1.0, queue_capacity=4096,
                 device_timing_expected=False):
        if not job_id or not _natural(rank_id) or not host_clock_domain:
            raise ValueError("online telemetry requires job, rank and Host clock identities")
        if not .05 <= heartbeat_seconds <= 10 or not _natural(queue_capacity) or queue_capacity < 1:
            raise ValueError("invalid heartbeat or queue bound")
        self.address, self.job_id, self.rank_id = address, job_id, rank_id
        self.host_clock_domain = host_clock_domain
        self.auth_token, self.interval = auth_token, heartbeat_seconds
        self.device_timing_expected = bool(device_timing_expected)
        self.session_id = uuid.uuid4().hex
        self.groups, self.counters = {}, {}
        self.sequence = self.dropped = 0
        self.closed = False
        self.finish_stats, self.finish_error = {}, "collector did not acknowledge run_end"
        self.lock, self.done = threading.Lock(), threading.Event()
        self.queue = queue.Queue(maxsize=queue_capacity)
        self.thread = threading.Thread(target=self._send, name="hccl-online-telemetry", daemon=True)
        self.thread.start()

    @classmethod
    def from_environment(cls, *, job_id, rank_id, node_id, timing_adapter=None):
        value = os.environ.get("HCCL_TRACE_ONLINE_ADDR")
        mode = os.environ.get("HCCL_TRACE_ONLINE_TIMING", "host")
        if mode not in {"host", "npu_event"} or (mode == "npu_event") != (timing_adapter is not None):
            raise ValueError("HCCL_TRACE_ONLINE_TIMING=npu_event requires an initialized NPU Event adapter")
        if not value:
            if timing_adapter is not None:
                raise ValueError("npu_event timing requires HCCL_TRACE_ONLINE_ADDR")
            return None
        host, sep, port = value.rpartition(":")
        if not sep or not host or not port.isdecimal() or not 1<=int(port)<=65535:
            raise ValueError("HCCL_TRACE_ONLINE_ADDR must be HOST:PORT")
        return cls((host,int(port)),job_id=job_id,rank_id=rank_id,
                   host_clock_domain="host_raw:"+node_id,auth_token=os.environ.get("HCCL_TRACE_ONLINE_TOKEN"),
                   device_timing_expected=timing_adapter is not None)

    def _emit_locked(self, kind, **fields):
        self.sequence += 1
        row = self._frame(kind, **fields)
        try:
            self.queue.put_nowait(row)
        except queue.Full:
            self.dropped += 1

    def _frame(self, kind, **fields):
        return dict(version=1,event=kind,job_id=self.job_id,rank_id=self.rank_id,
                    session_id=self.session_id,seq=self.sequence,dropped=self.dropped,**fields)

    def _heartbeat(self):
        with self.lock:
            if not self.closed:
                self._emit_locked("heartbeat", counters=[[k,g,n] for (k,g),n in self.counters.items()],
                                  _queued_ns=time.monotonic_ns())

    def register(self, communicator_id, generation, participants):
        group = communicator_id,generation
        ranks = tuple(sorted(participants))
        if (not communicator_id or not _natural(generation) or len(set(ranks))!=len(ranks)
                or any(not _natural(r) for r in ranks) or self.rank_id not in ranks):
            raise ValueError("invalid online communicator registration")
        with self.lock:
            if self.closed:
                raise ValueError("online probe is closed")
            if group in self.groups:
                if self.groups[group]!=ranks:
                    raise ValueError("online communicator membership changed within a generation")
                return
            self.groups[group] = ranks
            self.counters[group] = 0
            self._emit_locked("register",communicator_id=communicator_id,communicator_generation=generation,
                              participants=list(ranks),device_timing_expected=self.device_timing_expected)

    def enter(self, communicator_id, generation, *, op_type, tensor_bytes, host_entry_ts,
              stage=None, iteration=None, bucket_id=None, occurrence=0, dtype=None,
              reduction=None, host_entry_source="explicit_host_boundary", preparation_ns=None,
              preparation_definition=None):
        if (not op_type or not _natural(tensor_bytes) or not _natural(host_entry_ts)
                or not _natural(occurrence) or (iteration is not None and not _natural(iteration))):
            raise ValueError("invalid Host collective entry")
        group = communicator_id,generation
        with self.lock:
            if self.closed or group not in self.groups:
                raise ValueError("register the active online communicator before entering")
            self.counters[group] += 1
            counter = self.counters[group]
            self._emit_locked("enter",communicator_id=communicator_id,communicator_generation=generation,
                op_counter=counter,op_type=op_type,tensor_bytes=tensor_bytes,host_entry_ts=host_entry_ts,
                host_clock_domain=self.host_clock_domain,stage=stage,iteration=iteration,
                bucket_id=bucket_id,occurrence=occurrence,dtype=dtype,reduction=reduction,
                host_entry_source=host_entry_source, preparation_ns=preparation_ns,
                preparation_definition=preparation_definition)
        return OperationToken(self.job_id,communicator_id,generation,counter,self.rank_id)

    def _token_event(self, kind, token, **fields):
        if not isinstance(token,OperationToken) or (token.job_id,token.rank_id)!=(self.job_id,self.rank_id):
            raise ValueError("operation token belongs to another Rank or job")
        with self.lock:
            if not self.closed:
                self._emit_locked(kind,communicator_id=token.communicator_id,
                    communicator_generation=token.communicator_generation,op_counter=token.op_counter,**fields)

    def host_boundary(self, token, observed_ns):
        self._token_event("host_completion_bound",token,host_observed_ts=observed_ns,
                          host_clock_domain=self.host_clock_domain)

    def error(self, token):
        self._token_event("call_failed",token)

    def device_span(self, token, *, start_ns, end_ns, clock_domain, timing_definition,
                    source, evidence_ref, rank_role=None, algorithm=None, uncertainty_ns=None):
        """For a verified timing adapter only; do not pass Host return or observation time."""
        self._token_event("device_span",token,device_start_ts=start_ns,device_end_ts=end_ns,
                          device_clock_domain=clock_domain,timing_definition=timing_definition,
                          timing_source=source,evidence_ref=evidence_ref,rank_role=rank_role,
                          algorithm=algorithm,uncertainty_ns=uncertainty_ns)

    def device_duration(self, token, *, duration_ns, timing_definition, timing_source, evidence_ref,
                        algorithm=None, rank_role=None, uncertainty_ns=None, timing_profile_id=None,
                        boundary_evidence=None):
        """Send actual elapsed device time; absolute device timestamps are not required."""
        self._token_event("device_duration", token, device_duration_ns=duration_ns,
                          timing_definition=timing_definition, timing_source=timing_source,
                          evidence_ref=evidence_ref, algorithm=algorithm, rank_role=rank_role,
                          uncertainty_ns=uncertainty_ns, timing_profile_id=timing_profile_id,
                          boundary_evidence=boundary_evidence)

    def timing_failed(self, token, reason):
        self._token_event("timing_failed", token, reason=reason)

    def _send(self):
        connection = None
        connection_index = 0
        heartbeat_at = 0.0
        try:
            while not self.done.is_set() or not self.queue.empty():
                now = time.monotonic()
                if now >= heartbeat_at:
                    self._heartbeat()
                    heartbeat_at = now+self.interval
                try:
                    batch = [self.queue.get(timeout=min(.1,self.interval))]
                except queue.Empty:
                    continue
                while len(batch)<128:
                    try:
                        batch.append(self.queue.get_nowait())
                    except queue.Empty:
                        break
                try:
                    if connection is None:
                        connection = socket.create_connection(self.address,timeout=1)
                        connection.settimeout(1)
                        connection_index += 1
                    for row in batch:
                        if row["event"] == "heartbeat":
                            row["sender_queue_ns"] = time.monotonic_ns() - row.pop("_queued_ns")
                    payload = b"".join(self._encode(x, connection_index)
                                       for x in batch)
                    connection.sendall(payload)
                except (OSError, TypeError, ValueError):
                    if connection is not None:
                        connection.close()
                    connection = None
                    with self.lock:
                        self.dropped += len(batch)
                    if not self.done.is_set():
                        self.done.wait(.25)
            if connection is None:
                connection = socket.create_connection(self.address, timeout=1)
                connection.settimeout(1)
                connection_index += 1
            self.sequence += 1
            final = self._frame("run_end", counters=[[k,g,n] for (k,g),n in self.counters.items()],
                                host_log=self.finish_stats, pending_calls=self.pending_calls)
            connection.sendall(self._encode(final, connection_index))
            with connection.makefile("rb") as reply:
                ack = json.loads(reply.readline(4097))
            if (ack.get("event"), ack.get("session_id"), ack.get("seq")) == (
                    "run_end_ack", self.session_id, self.sequence):
                self.finish_error = None if ack.get("accepted") is True else "collector rejected Rank telemetry completeness"
        except (OSError, ValueError, TypeError, AttributeError):
            pass
        finally:
            if connection is not None:
                connection.close()

    def _encode(self, row, connection_index):
        return (json.dumps(dict(row, auth=self.auth_token, connection_index=connection_index),
                           separators=(",", ":")) + "\n").encode()

    def close(self, timeout=10.0, *, host_log=None, pending_calls=0):
        with self.lock:
            if not self.closed:
                self.closed = True
                self.finish_stats = host_log or {}
                self.pending_calls = pending_calls
        self.done.set()
        self.thread.join(timeout=timeout)
        if self.thread.is_alive() or self.finish_error:
            raise RuntimeError(self.finish_error or "timed out draining online telemetry")
