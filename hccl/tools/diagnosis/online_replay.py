"""Replay the online Slow detector from public SDK markers and profiler DBs, not injection truth."""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory

from hccl_trace.online_probe import tensor_description
from .capture_discovery import discover_capture, read_json
from .dependency_model import stable_id
from .online_tracker import OnlineTracker
from .parse_msprof_db import parse_operations
from .workload_binder import _read_calls, bind_capture, operation_type


_LOCATION = ("group_id", "stage", "iteration", "call_site", "occurrence")


def collect_bound(source, scratch):
    capture = discover_capture(source, scratch / "discovery")
    binding = bind_capture(capture, scratch / "binding", mode="rolling")
    if not binding.coordinates:
        raise ValueError("online replay requires public SDK coordinates; legacy rank order is not inferred")
    manifest = read_json(binding.manifest)
    return dict(manifest=manifest, coordinates=binding.coordinates,
                rank_calls=[_read_calls(path) for path in capture.call_logs],
                spans=[asdict(span) for node in manifest["nodes"]
                       for span in parse_operations(node["msprof_db_dir"], node["node_id"])])


def replay_bound(bundle):
    manifest, coordinates = bundle["manifest"], bundle["coordinates"]
    job = manifest["run_id"]
    locations = {tuple(c[k] for k in _LOCATION): c["operation_scope"] for c in coordinates}
    if not locations or len(locations) != len(coordinates):
        raise ValueError("duplicate replay collective coordinate")
    by_scope = {stable_id("op", (job, o["operation_id"])): o for o in manifest["operations"]}
    ranks = {(r["node_id"], r["device_id"]): r["user_rank"] for r in manifest["ranks"]}
    # These are profiler's recorded CollOp/device envelopes, not the Python API intervals.
    spans = {}
    for span in bundle["spans"]:
        key = tuple(span[k] for k in ("node_id", "device_id", "group_name", "op_name"))
        if key in spans:
            raise ValueError("duplicate replay profiler operation")
        spans[key] = span
    entries = defaultdict(dict)
    registrations = {}
    for header, calls in bundle["rank_calls"]:
        node, device, rank = (header[x] for x in ("node_id", "device_id", "user_rank"))
        if ranks.get((node, device)) != rank:
            raise ValueError("SDK Rank is inconsistent with the bound profiler device")
        counters = Counter()
        for call in sorted(calls, key=lambda c: c["sequence"]):
            group, stage, iteration, bucket, occurrence = (call[k] for k in _LOCATION)
            members = tuple(call["participants"])
            if registrations.setdefault((group, rank), members) != members:
                raise ValueError("replay requires one proven communicator per group label")
            counters[group] += 1
            key = group, counters[group]
            scope = locations[tuple(call[k] for k in _LOCATION)]
            op = by_scope[scope]
            identity, = [m for m in op["members"] if (m["node_id"], m["device_id"]) == (node, device)]
            span = spans[node, device, identity["group_name"], identity["op_name"]]
            dtype, size = tensor_description(call["dtype"], call["element_count"])
            if rank in entries[key] or (entries[key] and next(iter(entries[key].values()))[0] != scope):
                raise ValueError("collective order differs across Rank logs")
            entries[key][rank] = scope, dict(op_type=operation_type(call["operation_type"]),
                tensor_bytes=size, dtype=dtype,
                reduction=str(call["reduction"]).lower() if call.get("reduction") is not None else None, stage=stage,
                iteration=iteration, bucket_id=bucket, occurrence=occurrence,
                host_entry_ts=call["before"]["raw_ns"], host_clock_domain=f"archive-host-raw:{node}",
                host_entry_source="archived_sdk_before_collective_call"), dict(device_start_ts=span["start_ns"],
                device_end_ts=span["end_ns"], device_clock_domain=f"device:profiler:{node}:{device}",
                timing_definition="profiler_communication_op_v1", timing_source="cann_communication_op",
                evidence_ref=dict(node_id=node, profiler_device_id=device, group=span["group_name"],
                                  operation=span["op_name"], op_id=span["op_id"]))
    if {scope for records in entries.values() for scope, _, _ in records.values()} != set(locations.values()):
        raise ValueError("public SDK calls do not cover all bound replay collectives")
    measurements, events = [], []
    tracker = OnlineTracker(job, observe_measurement=measurements.append)
    sequences = Counter()
    frame_index = 0

    def feed(event, rank, group, **data):
        nonlocal frame_index
        sequences[rank] += 1
        frame_index += 1
        tracker.ingest(dict(version=1, job_id=job, rank_id=rank, event=event, seq=sequences[rank],
            session_id=f"archive-rank-{rank}", dropped=0, communicator_id=group,
            communicator_generation=0, **data), frame_index)

    for (group, rank), members in sorted(registrations.items()):
        feed("register", rank, group, participants=list(members), device_timing_expected=True)
    for (group, counter), records in sorted(entries.items()):
        first_rank = min(records)
        if tuple(sorted(records)) != registrations[group, first_rank]:
            raise ValueError("replay collective is missing participating Rank records")
        for rank, (_, entry, _) in sorted(records.items()):
            feed("enter", rank, group, op_counter=counter, **entry)
        for rank, (_, _, span) in sorted(records.items()):
            span["evidence_ref"] = json.dumps(span["evidence_ref"], sort_keys=True, separators=(",", ":"))
            feed("device_span", rank, group, op_counter=counter, **span)
        for event in tracker.drain():
            event.pop("collector")  # Archive playback has no real collector arrival times.
            event["event_id"] = stable_id("online-replay", (job, group, counter, event["event_type"]))
            event["operation_scope"] = records[first_rank][0]
            events.append(event)
        if measurements and measurements[-1]["communicator_id"] == group and measurements[-1]["op_counter"] == counter:
            measurements[-1]["operation_scope"] = records[first_rank][0]
    if tracker.operations or tracker.counts.get("COMPLETED", 0) != len(entries):
        raise ValueError("archived collectives did not all complete in replay")
    return dict(mode="offline_equivalent_slow_only", job_id=job, bound_collectives=len(entries),
        counts=tracker.counts, events=events, measurements=measurements,
        timing_definition="profiler_communication_op_v1", rank_roles="not_assumed_from_db_or_topology")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("capture", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    with TemporaryDirectory(prefix="hccl-online-replay-") as temporary:
        result = replay_bound(collect_bound(args.capture, Path(temporary)))
    payload = json.dumps(result, sort_keys=True, separators=(",", ":")).encode() + b"\n"
    with args.output.open("xb") as out:
        out.write(payload)
    print(json.dumps(dict(job_id=result["job_id"], counts=result["counts"],
                          sha256=hashlib.sha256(payload).hexdigest()), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
