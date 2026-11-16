"""Compare Event elapsed time with exactly bound msprof COMMUNICATION_OP rows."""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from contextlib import closing
import json
from pathlib import Path
from tempfile import TemporaryDirectory

from .capture_discovery import discover_capture, read_json
from .clock_alignment import raw_to_profiler
from .dependency_model import stable_id
from .online_replay import collect_bound
from .parse_msprof_db import _readonly_connection, _table_columns, discover_db_files
from .workload_binder import _inventory, _read_calls, operation_candidates


_SEMANTIC = ("group_id", "stage", "iteration", "call_site", "occurrence")


def _index(records, key):
    index = {}
    for row in records:
        identity = key(row)
        if identity in index:
            raise ValueError(f"duplicate timing identity: {identity}")
        index[identity] = row
    return index


def _algorithms(manifest):
    for node in manifest["nodes"]:
        for path in discover_db_files(node["msprof_db_dir"]):
            with closing(_readonly_connection(str(path))) as db:
                if "algType" not in _table_columns(db, "COMMUNICATION_OP"):
                    raise ValueError(f"profiler DB is missing COMMUNICATION_OP.algType: {path.name}")
                for device, group, op, algorithm in db.execute(
                        "SELECT o.deviceId,g.value,n.value,a.value FROM COMMUNICATION_OP o "
                        "JOIN STRING_IDS g ON g.id=o.groupName JOIN STRING_IDS n ON n.id=o.opName "
                        "LEFT JOIN STRING_IDS a ON a.id=o.algType"):
                    yield (node["node_id"], device, group, op), algorithm


def bind_bucket(source, work, bucket):
    """A scoped certification input, not a fallback to ordering ambiguous calls."""
    capture = discover_capture(source, work)
    manifest = capture.manifest
    inventory = {node["node_id"]: _inventory(node) for node in manifest["nodes"]}
    groups, spans, rank_calls, claimed, owners = defaultdict(list), [], [], {}, {}
    seen_ranks = set()
    for path in capture.call_logs:
        header, calls = _read_calls(path)
        rank, node, dev = (header[k] for k in ("user_rank", "node_id", "device_id"))
        if rank in seen_ranks:
            raise ValueError("duplicate SDK rank")
        seen_ranks.add(rank)
        data = inventory[node][dev]
        ops = data["operations"]
        def convert(raw):
            return raw_to_profiler(raw, data["clock_start"], data["clock_stop"])

        # Include all calls in the reverse degree, even ones outside the requested bucket.
        if any("input_buffer_ptr" in call for call in calls):
            raise ValueError("pointer-annotated captures require the complete pointer-aware binder")
        possible = [operation_candidates(call, ops, dev, convert) for call in calls]
        degree = Counter(i for matches in possible for i in matches)
        selected = []
        for call, matches in zip(calls, possible):
            if call["call_site"] != bucket:
                continue
            if len(matches) != 1 or degree[next(iter(matches))] != 1:
                raise ValueError(f"target bucket is not mutually unique: Rank {rank}, sequence {call['sequence']}")
            op = ops[next(iter(matches))]
            gid, observed = call["group_id"], op["group_name"]
            if (claimed.setdefault((node, dev, gid), observed) != observed
                    or owners.setdefault((node, dev, observed), gid) != gid):
                raise ValueError("SDK/native communicator identity changed or is aliased")
            member = dict(node_id=node, device_id=dev, group_name=observed, op_name=op["op_name"])
            key = tuple(call[k] for k in _SEMANTIC)
            signature = (tuple(call["participants"]), call["operation_type"].lower(), op["dataType"],
                         call["element_count"], call.get("reduction"))
            selected.append(call)
            groups[key].append((rank, signature, member))
            spans.append(dict(member, start_ns=op["startNs"], end_ns=op["endNs"]))
        rank_calls.append((header, selected))
    if not groups:
        raise ValueError(f"no SDK calls for requested bucket: {bucket}")
    coordinates, operations = [], []
    for key, ranks in groups.items():
        signature = ranks[0][1]
        if (tuple(sorted(r for r, _, _ in ranks)) != signature[0]
                or any(s != signature for _, s, _ in ranks)):
            raise ValueError(f"target bucket is missing Rank coverage or has conflicting signatures: {key}")
        op_id = stable_id("call", key)
        operations.append(dict(operation_id=op_id, members=[m for _, _, m in ranks]))
        coordinates.append(dict(zip(_SEMANTIC, key), operation_scope=stable_id("op", (manifest["run_id"], op_id))))
    return dict(manifest=dict(manifest, operations=operations), coordinates=coordinates,
                spans=spans, rank_calls=rank_calls)


def compare(bundle, frames, algorithms, *, bucket=None):
    run = bundle["manifest"]["run_id"]
    owner = ("node_id", "device_id", "group_name", "op_name")
    location = lambda row: tuple(row[k] for k in _SEMANTIC)
    device = lambda row: tuple(row[k] for k in owner)
    coordinates = _index(bundle["coordinates"], location)
    operations = _index(bundle["manifest"]["operations"], lambda row: stable_id("op", (run, row["operation_id"])))
    profiler = _index(bundle["spans"], device)
    token = lambda row: (row["communicator_id"], row["communicator_generation"], row["op_counter"], row["rank_id"])
    entries = _index((f for f in frames if f["event"] == "enter" and (bucket is None or f["bucket_id"] == bucket)), token)
    durations = _index((f for f in frames if f["event"] == "device_duration" and (bucket is None or token(f) in entries)), token)
    rows = []
    seen = set()
    for header, calls in bundle["rank_calls"]:
        for call in calls:
            if call.get("operation_type", "").lower() != "allreduce":
                raise ValueError("timing audit only supports explicit AllReduce captures")
            key = call["group_id"], call["online_communicator_generation"], call["online_op_counter"], header["user_rank"]
            entry, timing = entries.get(key), durations.get(key)
            if entry is None or timing is None:
                raise ValueError(f"incomplete ENTER/DEVICE_DURATION evidence: {key}")
            if (entry["job_id"] != run or timing["job_id"] != run or entry["session_id"] != timing["session_id"]
                    or (entry["stage"], entry["iteration"], entry["bucket_id"], entry["occurrence"], entry["host_entry_ts"])
                    != (call["stage"], call["iteration"], call["call_site"], call["occurrence"], call["before"]["raw_ns"])
                    or entry["op_type"] != "allreduce" or entry["tensor_bytes"] != call["element_count"] * 4
                    or call["dtype"].lower() not in {"float32", "fp32"}
                    or timing["timing_source"] != "npu_event_elapsed" or timing["timing_definition"] != "consumer_stream_collective_v1"):
                raise ValueError(f"telemetry identity/timing does not match the FP32 AllReduce SDK record: {key}")
            op = operations[coordinates[location(call)]["operation_scope"]]
            member, = (r for r in op["members"] if (r["node_id"], r["device_id"]) == (header["node_id"], header["device_id"]))
            interval = profiler[device(member)]
            measured = timing["device_duration_ns"]
            reference = interval["end_ns"]-interval["start_ns"]
            actual_algorithm = algorithms.get(device(member))
            if reference <= 0 or type(measured) is not int or measured <= 0 or not actual_algorithm:
                raise ValueError(f"missing measured duration or algorithm evidence: {key}")
            seen.add(key)
            rows.append(dict(token=key, stage=call["stage"], iteration=call["iteration"], bucket=call["call_site"],
                node_id=header["node_id"], profiler_identity=device(member), profiler_algorithm=actual_algorithm,
                declared_algorithm=timing.get("algorithm"), event_duration_ns=measured, profiler_duration_ns=reference,
                event_to_profiler_ratio=measured/reference, delta_ns=measured-reference,
                device_interval_ns=[interval["start_ns"], interval["end_ns"]]))
    if not rows or seen != entries.keys() or seen != durations.keys():
        raise ValueError("profiler and online records do not cover exactly the same Rank calls")
    return dict(job_id=run, bucket_scope=bucket, classification_certified=False, bounds_equivalent=None, rows=rows)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("capture", type=Path)
    parser.add_argument("online_output", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--bucket", help="audit only this call site; require every Rank call to be mutually unique")
    args = parser.parse_args(argv)
    health = read_json(args.online_output / "run_health.jsonl")
    if health.get("rank_streams_complete") is not True:
        raise ValueError("cannot compare timings from an incomplete telemetry session")
    with TemporaryDirectory(prefix="hccl-event-audit-") as work:
        bundle = bind_bucket(args.capture, Path(work), args.bucket) if args.bucket else collect_bound(args.capture, Path(work))
        with (args.online_output / "telemetry.jsonl").open(encoding="utf-8") as data:
            result = compare(bundle, [json.loads(line) for line in data], dict(_algorithms(bundle["manifest"])),
                             bucket=args.bucket)
    with args.output.open("x", encoding="utf-8") as out:
        json.dump(result, out, indent=2)
        out.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
