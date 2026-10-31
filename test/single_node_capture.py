#!/usr/bin/env python3
"""Bind a complete public foreground call sequence to actual consolidated DBs."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import shutil
import sqlite3
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "hccl/tools"))
from diagnosis.dependency_model import OperationScopeIdentity, stable_id


COUNTER = re.compile(r"hcom_allReduce__\d+_(\d+)_\d+$")


def read_jsonl(path):
    return [json.loads(line) for line in Path(path).read_text(encoding="utf-8").splitlines() if line.strip()]


def bind(directory, run_id, *, ddp_capture=False, preserve_task_batches=False):
    directory = Path(directory)
    public = {int(p.stem.split("-")[-1]): read_jsonl(p) for p in (directory / "public").glob("rank-*.jsonl")}
    if set(public) != set(range(4)):
        raise ValueError("four independent public call logs required")
    boundaries = {}
    for rank, calls in public.items():
        if not calls or [c["sequence"] for c in calls] != list(range(len(calls))):
            raise ValueError("public call sequence missing or duplicated")
        if any(c["rank"] != rank or c["dtype"] != "fp32" or c["reduction"] != "sum" for c in calls):
            raise ValueError("invalid public call identity")
        if ddp_capture:
            signatures = {}
            for c in calls:
                if not c.get("bucket_signature"):
                    raise ValueError("DDP calls need independently recorded parameter bucket signatures")
                if c["stage"] == "measured":
                    key = c["block"], c["bucket"]
                    value = c["bucket_signature"], c["count"]
                    if key in signatures and signatures[key] != value:
                        raise ValueError("DDP measured bucket structure changed")
                    signatures[key] = value
            if [c["bucket_signature"] for c in calls] != [c["bucket_signature"] for c in public[0]]:
                raise ValueError("DDP parameter bucket order differs across ranks")
        done = read_jsonl(directory / "public" / ("boundaries-rank-{}.jsonl".format(rank)))
        indexed = {(r["stage"], r["iteration"]): r for r in done}
        if (len(indexed) != len(done) or set(indexed) != {(c["stage"], c["iteration"]) for c in calls}
                or any(r["rank"] != rank or r.get("device_synchronized") is not True for r in done)):
            raise ValueError("each iteration needs one independent device-synchronization boundary")
        boundaries[rank] = indexed
        if [(c["stage"], c["iteration"], c["block"], c["bucket"], c["count"]) for c in calls] != [
            (c["stage"], c["iteration"], c["block"], c["bucket"], c["count"]) for c in public[0]]:
            raise ValueError("foreground ranks disagree on business call sequence")
    found, noncommunication_inputs = {}, []
    for path in sorted((directory / "msprof").rglob("msprof_*.db")):
        with sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True) as db:
            db.row_factory = sqlite3.Row
            if not db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='COMMUNICATION_OP'").fetchone():
                noncommunication_inputs.append(dict(path=str(path), reason="no COMMUNICATION_OP table; not a foreground collective DB"))
                continue
            operations = [dict(r) for r in db.execute(
                "SELECT o.*,g.value group_name,n.value op_name FROM COMMUNICATION_OP o "
                "JOIN STRING_IDS g ON g.id=o.groupName JOIN STRING_IDS n ON n.id=o.opName")]
            groups = sorted({r["group_name"] for r in operations})
            for rank, calls in public.items():
                device = calls[0]["runtime_device_id"]
                for group in groups:
                    selected = [r for r in operations if r["group_name"] == group and r["deviceId"] == device
                                and (not ddp_capture or COUNTER.fullmatch(r["op_name"]))]
                    if len(selected) != len(calls):
                        continue
                    counters = {}
                    for op in selected:
                        match = COUNTER.fullmatch(op["op_name"])
                        if not match or int(match[1]) in counters:
                            break
                        counters[int(match[1])] = op
                    if len(counters) != len(calls) or (not ddp_capture and set(counters) != set(range(len(calls)))):
                        continue
                    if ddp_capture:
                        counters = dict(enumerate(counters[k] for k in sorted(counters)))
                    if any(counters[c["sequence"]]["count"] != c["count"] or counters[c["sequence"]]["dataType"] != 4
                           for c in calls):
                        continue
                    if rank in found:
                        raise ValueError("multiple DB foreground matches; no ordinal or nearest-time fallback")
                    info = json.loads((path.parent / "host/start_info").read_text())
                    offset = int(info["collectionTimeBegin"]) * 1000 - int(info["clockMonotonicRaw"])
                    apis = [dict(r) for r in db.execute(
                        "SELECT a.* FROM CANN_API a JOIN STRING_IDS s ON s.id=a.name "
                        "WHERE s.value='hcom_allReduce_' ORDER BY a.startNs")]
                    if len(apis) != len(calls):
                        raise ValueError("foreground HCCL API count differs from public calls")
                    # HCCL may dispatch after the Python call returned. The actual
                    # API must follow submission and finish before this iteration's device sync.
                    # No clock is fitted to injection truth, and no nearest-time pairing is used.
                    errors = []
                    for call, api in zip(calls, apis):
                        lower = call["before"]["raw_ns"] + offset
                        boundary = boundaries[rank][(call["stage"], call["iteration"])]
                        upper = boundary["clocks"]["raw_ns"] + offset
                        if not lower <= api["startNs"] <= api["endNs"] <= upper:
                            errors.append(dict(sequence=call["sequence"], lower=lower, upper=upper,
                                               api_start_ns=api["startNs"]))
                    if errors:
                        raise ValueError("profiler API outside public submission/device-sync envelope: {}".format(errors[:3]))
                    found[rank] = dict(path=path, counters=counters, apis=apis, offset=offset, info_path=path.parent / "host/start_info",
                                       api_count=len(apis), device=device)
    if set(found) != set(range(4)):
        raise ValueError("no complete unique foreground DB sequence for all four ranks")
    selected_dir = directory / "foreground-dbs"
    selected_dir.mkdir(exist_ok=False)
    evidence = []
    for rank, entry in found.items():
        selected = selected_dir / ("msprof_rank-{}-".format(rank) + entry["path"].name)
        identity_export = None
        if preserve_task_batches:
            from diagnosis.export_msprof_identity import export_identity
            identity_export = export_identity(entry["path"], entry["path"].parent, selected)
        else:
            shutil.copy2(entry["path"], selected)
        evidence.append(dict(rank=rank, runtime_device_id=entry["device"], source_db=str(entry["path"]),
                             call_count=entry["api_count"], clock_info=str(entry["info_path"]),
                             raw_to_profiler_offset_ns=entry["offset"], api_containment_verified=True,
                             task_identity_export=identity_export))
    bindings = []
    for call in public[0]:
        seq = call["sequence"]
        names = {(item["counters"][seq]["group_name"], item["counters"][seq]["op_name"]) for item in found.values()}
        if len(names) != 1:
            raise ValueError("operation strings differ between foreground ranks")
        group, name = names.pop()
        local = OperationScopeIdentity(group, name).stable_id
        scope = stable_id("op", (run_id, "node0", local))
        bindings.append(dict(operation_scope=scope, **{k: call[k] for k in ("stage", "iteration", "block", "bucket")},
                             evidence="Complete public rank call sequences; DB AllReduce operation counter, FP32 count and group agreed on four devices; host CANN_API inside submission/device-sync envelope; see binding-evidence.json"))
    manifest = dict(run_id=run_id, nodes=[dict(node_id="node0", plog_dir=str(directory / "ascend_log"),
                                            msprof_db_dir=str(selected_dir))],
                    ranks=[dict(node_id="node0", device_id=found[r]["device"], user_rank=r) for r in range(4)])
    for filename, data in (("manifest.json", manifest), ("iteration-map.json", dict(schema_version=1, operations=bindings)),
                           ("binding-evidence.json", dict(schema_version=1, binding_kind="ddp_gradient_buckets" if ddp_capture else "explicit_collectives", ranks=evidence,
                                                          noncommunication_inputs=noncommunication_inputs))):
        (directory / filename).write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    has_preparations = ["preparation_before" in call for calls in public.values() for call in calls]
    if any(has_preparations):
        if not all(has_preparations):
            raise ValueError("public preparations must cover every foreground rank/call or none")
        preparations = []
        for rank, calls in public.items():
            entry = found[rank]
            for call, binding, api in zip(calls, bindings, entry["apis"]):
                start = call["preparation_before"]["raw_ns"] + entry["offset"]
                stop = call["before"]["raw_ns"] + entry["offset"]
                if not start <= stop <= api["startNs"] <= api["endNs"]:
                    raise ValueError("Host preparation does not precede its verified foreground API")
                preparations.append(dict(operation_scope=binding["operation_scope"], node_id=run_id + "/node0",
                    user_rank=rank, device_id=entry["device"], start_ns=start, stop_ns=stop,
                    api_start_ns=api["startNs"], api_stop_ns=api["endNs"],
                    evidence="Public preparation/submission clocks; complete foreground named operation/count binding and independently verified CANN_API envelope; binding-evidence.json"))
        (directory / "preparation-map.json").write_text(json.dumps(dict(schema_version=1, preparations=preparations), indent=2) + "\n", encoding="utf-8")
    return found


def actual_windows(directory, run_id, case, found):
    """Evaluator-only clock conversion after the independent diagnosis is fixed."""
    injection = case["injection"]
    if injection["kind"] == "normal":
        return []
    rank = injection["target_rank"]
    records = read_jsonl(Path(directory) / "private" / ("rank-{}.jsonl".format(rank)))
    starts = [r for r in records if r["event"] == "injection_start"]
    stops = [r for r in records if r["event"] == "injection_stop" and r.get("actual_hit")]
    if len(starts) != 1 or len(stops) != 1:
        raise ValueError("actual injection start/stop evidence missing")
    first, last = starts[0]["clocks"]["raw_ns"], stops[0]["clocks"]["raw_ns"]
    if injection["kind"] != "progress_delay":
        background = json.loads((Path(directory) / "private/result.json").read_text())
        if background["operations"] <= 0 or background["max_error"] != 0:
            raise ValueError("no actual successful background execution")
        first, last = background["started_raw_ns"], background["finished_raw_ns"]
        if injection["kind"] == "communication_contention":
            if background.get("process_count") != 1:
                raise ValueError("background must use exactly one process")
    ranks = [rank]
    if injection["kind"] == "communication_contention":
        ranks.append(injection["peer_rank"])
    # Both communication endpoints receive the background load. Each has its own
    # independently checked capture clock conversion; a window never borrows another rank's offset.
    return [dict(source="captured_injection_window", actual_hit=True, node_id=run_id + "/node0",
                 clock_domain="profiler_node_ns", start_ns=first + found[r]["offset"],
                 stop_ns=last + found[r]["offset"], target_ranks=[r],
                 clock_evidence="host/start_info raw-to-epoch conversion, independently checked against every foreground submission/device-sync API envelope; binding-evidence.json")
            for r in ranks]


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--ddp-capture", action="store_true")
    parser.add_argument("--preserve-task-batches", action="store_true", help="Export verified CANN 8.5.1 HOST batch identities.")
    args = parser.parse_args()
    bind(args.directory.resolve(), args.run_id, ddp_capture=args.ddp_capture,
         preserve_task_batches=args.preserve_task_batches)
