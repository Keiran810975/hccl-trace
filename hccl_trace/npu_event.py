"""Opt-in elapsed timing on the stream which consumes an HCCL result."""
from __future__ import annotations

import hashlib
import json
from math import isfinite
import os
from pathlib import Path


EVENT_DEFINITION = "consumer_stream_collective_v1"


class NpuEventTiming:
    def __init__(self, npu, *, stack_id=None, torch_npu_version=None, profile=None):
        self.npu, self.profile, self.profile_id = npu, profile, None
        self.pending = []
        if profile is not None:
            evidence = profile.get("boundary_evidence")
            if (profile.get("schema_version") != 1 or profile.get("timing_definition") != EVENT_DEFINITION
                    or not stack_id or profile.get("stack_id") != stack_id
                    or not torch_npu_version or profile.get("torch_npu_version") != torch_npu_version
                    or not isinstance(evidence, str) or not evidence.strip()):
                raise ValueError("timing profile must match the running stack and cite independent boundary validation")
            self.profile_id = hashlib.sha256(json.dumps(profile, sort_keys=True).encode()).hexdigest()
        try:
            self.first_pair = self._events()
            if not callable(npu.current_stream):
                raise TypeError("current_stream is not callable")
        except (AttributeError, TypeError, RuntimeError) as exc:
            raise RuntimeError("npu_event timing requires working timing-enabled Event APIs") from exc

    @classmethod
    def from_environment(cls, npu, *, torch_npu_version):
        if os.environ.get("HCCL_TRACE_ONLINE_TIMING") != "npu_event":
            return None
        path = os.environ.get("HCCL_TRACE_ONLINE_TIMING_PROFILE")
        profile = json.loads(Path(path).read_text(encoding="utf-8")) if path else None
        if path and not isinstance(profile, dict):
            raise ValueError("timing profile must be a JSON object")
        return cls(npu, stack_id=os.environ.get("HCCL_TRACE_ONLINE_STACK_ID"),
                   torch_npu_version=torch_npu_version, profile=profile)

    def _events(self):
        start, end = (self.npu.Event(enable_timing=True) for _ in range(2))
        if not all(callable(getattr(e, name, None)) for e in (start, end)
                   for name in ("record", "query", "elapsed_time")):
            raise RuntimeError("installed NPU Event does not expose record/query/elapsed_time")
        return start, end

    def validate_group(self, group, participants):
        if self.profile is not None and (self.profile.get("communicator_id") != group
                or self.profile.get("participants") != list(participants)):
            raise ValueError("timing profile does not cover the registered communicator/Rank set")

    def begin(self, *, op_type, bucket, tensor_bytes, dtype, reduction, rank, participants):
        if op_type != "allreduce":
            raise ValueError("npu_event V1 times explicit AllReduce only")
        metadata = {}
        if self.profile is not None:
            spec = self.profile.get("buckets", {}).get(bucket, {})
            roles = spec.get("rank_roles", {})
            algorithm = spec.get("algorithm")
            role = roles.get(str(rank))
            if ((spec.get("tensor_bytes"), spec.get("dtype"), spec.get("reduction")) !=
                    (tensor_bytes, dtype, reduction) or not isinstance(algorithm, str) or not algorithm.strip()
                    or set(roles) != {str(r) for r in participants}
                    or any(not isinstance(value, str) or not value.strip() for value in roles.values())):
                raise ValueError(f"timing profile does not attest this AllReduce signature/roles: {bucket}")
            metadata = dict(algorithm=algorithm, rank_role=role, timing_profile_id=self.profile_id,
                            boundary_evidence=self.profile["boundary_evidence"])
        pair = self.first_pair or self._events()
        self.first_pair = None
        start, end = pair
        stream = self.npu.current_stream()
        start.record(stream)
        return start, end, stream, metadata

    def end(self, token, observation):
        start, end, stream, metadata = observation
        if self.npu.current_stream() != stream:
            raise RuntimeError("Work.wait did not leave the timed consumer stream current")
        end.record(stream)
        self.pending.append((token, start, end, metadata))

    def flush(self, probe):
        pending, self.pending = self.pending, []
        for i, (token, start, end, metadata) in enumerate(pending):
            try:
                # The caller already synchronized. Never make a pending Event complete here.
                if not start.query() or not end.query():
                    raise RuntimeError("NPU timing events are not complete at the existing completion boundary")
                elapsed_ms = start.elapsed_time(end)
                if not isfinite(elapsed_ms) or elapsed_ms < .0000005:
                    raise RuntimeError("NPU Event elapsed time is not a positive, finite duration")
                ns = round(elapsed_ms * 1_000_000)
                if ns <= 0:
                    raise RuntimeError("NPU Event duration rounded to zero")
                probe.device_duration(token, duration_ns=ns, timing_source="npu_event_elapsed",
                    timing_definition=EVENT_DEFINITION, evidence_ref=f"consumer_events:{probe.session_id}:{token.op_counter}",
                    **metadata)
            except (RuntimeError, ValueError, TypeError, OverflowError) as exc:
                for remaining, *_ in pending[i:]:
                    probe.timing_failed(remaining, "npu_event_readback_failed")
                raise RuntimeError("NPU Event readback failed; run cannot pass timing acceptance") from exc
