"""Compare Event elapsed time with exactly bound msprof COMMUNICATION_OP rows."""
from __future__ import annotations

import argparse
from contextlib import closing
import json
from pathlib import Path
from tempfile import TemporaryDirectory

from .capture_discovery import read_json
from .dependency_model import stable_id
from .online_replay import collect_bound
from .parse_msprof_db import _readonly_connection, _table_columns, discover_db_files


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


def compare(bundle, frames, algorithms):
    run = bundle["manifest"]["run_id"]
    semantic = ("group_id", "stage", "iteration", "call_site", "occurrence")
    owner = ("node_id", "device_id", "group_name", "op_name")
    location = lambda row: tuple(row[k] for k in semantic)
    device = lambda row: tuple(row[k] for k in owner)
    coordinates = _index(bundle["coordinates"], location)
    operations = _index(bundle["manifest"]["operations"], lambda row: stable_id("op", (run, row["operation_id"])))
    profiler = _index(bundle["spans"], device)
    token = lambda row: (row["communicator_id"], row["communicator_generation"], row["op_counter"], row["rank_id"])
    entries = _index((f for f in frames if f["event"] == "enter"), token)
    durations = _index((f for f in frames if f["event"] == "device_duration"), token)
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
    return dict(job_id=run, classification_certified=False, bounds_equivalent=None, rows=rows)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("capture", type=Path)
    parser.add_argument("online_output", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    health = read_json(args.online_output / "run_health.jsonl")
    if health.get("rank_streams_complete") is not True:
        raise ValueError("cannot compare timings from an incomplete telemetry session")
    with TemporaryDirectory(prefix="hccl-event-audit-") as work:
        bundle = collect_bound(args.capture, Path(work))
        with (args.online_output / "telemetry.jsonl").open(encoding="utf-8") as data:
            result = compare(bundle, [json.loads(line) for line in data], dict(_algorithms(bundle["manifest"])))
    with args.output.open("x", encoding="utf-8") as out:
        json.dump(result, out, indent=2)
        out.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
