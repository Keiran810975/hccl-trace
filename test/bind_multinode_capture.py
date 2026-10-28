#!/usr/bin/env python3
"""Bind this runner's complete public control/business calls, never injection truth."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from hccl.tools.diagnosis.dependency_model import stable_id
from hccl.tools.diagnosis.multi_node_trace import _name
from test.single_node_capture import COUNTER, read_jsonl


def bind(attempt, cluster_path, output, run_id):
    _name(run_id)
    attempt, output = Path(attempt).resolve(), Path(output).resolve()
    if output.exists():
        raise FileExistsError("refusing to overwrite bound capture")
    cluster = json.loads(Path(cluster_path).read_text(encoding="utf-8-sig"))
    nodes = cluster["nodes"]
    for node in nodes:
        _name(node["node_id"])
    if len({n["node_id"] for n in nodes}) != len(nodes) or [n["node_rank"] for n in nodes] != list(range(len(nodes))):
        raise ValueError("explicit unique physical nodes and ordered launcher ranks required")
    per_node = len(nodes[0]["devices"])
    if per_node <= 0 or any(len(n["devices"]) != per_node for n in nodes):
        raise ValueError("uniform explicit devices per node required")
    found, original_calls, public_evidence = {}, None, []
    for index, node in enumerate(nodes):
        folder = attempt / ("node" + str(index))
        execution = json.loads((folder / "execution.json").read_text())
        if execution.get("status") != "completed" or execution.get("returncode") != 0:
            raise ValueError("bind only a successfully completed numerical workload capture")
        for local_rank, device in enumerate(node["devices"]):
            rank = index * per_node + local_rank
            calls_path = folder / "public" / ("rank-{}.jsonl".format(rank))
            calls = read_jsonl(calls_path)
            boundaries = read_jsonl(folder / "public" / ("boundaries-rank-{}.jsonl".format(rank)))
            controls = read_jsonl(folder / "public" / ("controls-rank-{}.jsonl".format(rank)))
            done = [c for c in controls if c["label"] == "configuration_device_synchronized"]
            controls = [c for c in controls if c["label"] != "configuration_device_synchronized"]
            if (not calls or [c["sequence"] for c in calls] != list(range(len(calls))) or len(done) != 1
                    or [(c["label"], c["count"], c["dtype"], c["reduction"]) for c in controls] !=
                    [("configuration_sum", 32, "int32", "sum"), ("configuration_max", 1, "int32", "max")]):
                raise ValueError("complete public business/configuration sequence required")
            if (any(c["rank"] != rank or c["runtime_device_id"] != device for c in controls)
                    or done[0]["rank"] != rank):
                raise ValueError("configuration logs conflict with explicit rank/device mapping")
            sequence = [(c["stage"], c["iteration"], c["block"], c["bucket"], c["count"]) for c in calls]
            if original_calls is None:
                original_calls = calls
            elif sequence != [(c["stage"], c["iteration"], c["block"], c["bucket"], c["count"]) for c in original_calls]:
                raise ValueError("ranks disagree on public business sequence")
            if any(c["rank"] != rank or c["runtime_device_id"] != device or c["dtype"] != "fp32" or c["reduction"] != "sum" for c in calls):
                raise ValueError("public rank/device/dtype mismatch")
            limits = {(c["stage"], c["iteration"]): c for c in boundaries}
            if (len(limits) != len(boundaries) or set(limits) != {(c["stage"], c["iteration"]) for c in calls}
                    or any(c["rank"] != rank or c.get("device_synchronized") is not True for c in boundaries)):
                raise ValueError("each business iteration needs an independent synchronized boundary")
            matches = []
            for path in sorted((folder / "msprof").rglob("msprof_*.db")):
                with sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True) as db:
                    db.row_factory = sqlite3.Row
                    if not db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='COMMUNICATION_OP'").fetchone():
                        continue
                    ops = [dict(r) for r in db.execute("SELECT o.*,g.value AS group_name,n.value AS op_name FROM COMMUNICATION_OP o "
                        "JOIN STRING_IDS g ON g.id=o.groupName JOIN STRING_IDS n ON n.id=o.opName WHERE o.deviceId=?", (device,))]
                    for group in {c["group_name"] for c in ops}:
                        selected = [c for c in ops if c["group_name"] == group]
                        numbered = {}
                        for op in selected:
                            counter = COUNTER.fullmatch(op["op_name"])
                            if counter is None or int(counter[1]) in numbered:
                                break
                            numbered[int(counter[1])] = op
                        if set(numbered) != set(range(len(calls) + len(controls))) or len(selected) != len(numbered):
                            continue
                        ordered = [numbered[i] for i in range(len(numbered))]
                        public = controls + calls
                        if any(op["count"] != call["count"] or op["dataType"] != (2 if k < 2 else 4)
                               for k, (op, call) in enumerate(zip(ordered, public))):
                            continue
                        apis = [dict(r) for r in db.execute("SELECT a.* FROM CANN_API a JOIN STRING_IDS s ON s.id=a.name "
                            "WHERE s.value='hcom_allReduce_' ORDER BY a.startNs")]
                        if len(apis) != len(public):
                            continue
                        info = json.loads((path.parent / "host/start_info").read_text())
                        offset = int(info["collectionTimeBegin"]) * 1000 - int(info["clockMonotonicRaw"])
                        compatible = True
                        for k, (call, api) in enumerate(zip(public, apis)):
                            upper = (done[0]["clocks"]["raw_ns"] if k < 2 else
                                     limits[(call["stage"], call["iteration"])]["clocks"]["raw_ns"]) + offset
                            if not call["before"]["raw_ns"] + offset <= api["startNs"] <= api["endNs"] <= upper:
                                compatible = False
                        if compatible:
                            matches.append(dict(path=path, operations=ordered, apis=apis, offset=offset,
                                                calls=calls, node_id=node["node_id"], device_id=device))
            if len(matches) != 1:
                raise ValueError("no unique complete public/API/DB binding for Rank {}".format(rank))
            found[rank] = matches[0]
            public_evidence.append(dict(rank=rank, node_id=node["node_id"], device_id=device,
                database=str(matches[0]["path"]), public_log_sha256=hashlib.sha256(calls_path.read_bytes()).hexdigest(),
                control_calls=2, business_calls=len(calls), api_envelopes_verified=True))
    manifest = dict(run_id=run_id, nodes=[], ranks=[], operations=[])
    copies = []
    for index, node in enumerate(nodes):
        folder = attempt / ("node" + str(index))
        selected = output / "foreground" / node["node_id"]
        for rank in range(index * per_node, (index + 1) * per_node):
            source = found[rank]["path"]
            destination = selected / ("rank-" + str(rank))
            copies.append((source, destination / source.name))
            for filename in ("start_info", "end_info"):
                metadata = source.parent / "host" / filename
                if metadata.is_file():
                    copies.append((metadata, destination / "host" / filename))
        item = dict(node_id=node["node_id"], plog_dir=str(folder / "ascend_log"), msprof_db_dir=str(selected))
        if (folder / "clock-probes.json").is_file():
            item["clock_probe_files"] = [str(folder / "clock-probes.json")]
        manifest["nodes"].append(item)
    coordinates, preparations = [], []
    for sequence in range(len(original_calls) + 2):
        entries = [found[rank]["operations"][sequence] for rank in sorted(found)]
        if len({(op["count"], op["dataType"]) for op in entries}) != 1:
            raise ValueError("ranks disagree on the public DB invocation size/type")
        operation_id = "public-call-{}".format(sequence)
        scope = stable_id("op", (run_id, operation_id))
        members = {}
        for rank, entry in found.items():
            op = entry["operations"][sequence]
            member = dict(node_id=entry["node_id"], group_name=op["group_name"], op_name=op["op_name"])
            if member["node_id"] in members and member != members[member["node_id"]]:
                raise ValueError("inconsistent per-node DB invocation")
            members[member["node_id"]] = member
            if sequence >= 2:
                call, api = entry["calls"][sequence - 2], entry["apis"][sequence]
                if "preparation_before" in call:
                    preparations.append(dict(operation_scope=scope, node_id=run_id + "/" + entry["node_id"],
                        user_rank=rank, device_id=entry["device_id"], start_ns=call["preparation_before"]["raw_ns"] + entry["offset"],
                        stop_ns=call["before"]["raw_ns"] + entry["offset"], api_start_ns=api["startNs"], api_stop_ns=api["endNs"],
                        evidence="Independent public preparation and complete named DB/API envelope binding"))
        manifest["operations"].append(dict(operation_id=operation_id, members=list(members.values()),
            evidence="Complete public configuration/business sequence on all ranks; named DB counters, group/dtype/count and ordered CANN_API envelopes independently verified; binding-evidence.json"))
        if sequence >= 2:
            call = original_calls[sequence - 2]
            coordinates.append(dict(operation_scope=scope, **{k: call[k] for k in ("stage", "iteration", "block", "bucket")},
                                    evidence="All-node complete public named invocation binding; binding-evidence.json"))
    for rank, entry in found.items():
        manifest["ranks"].append(dict(user_rank=rank, node_id=entry["node_id"], device_id=entry["device_id"]))
    if preparations and len(preparations) != len(found) * len(original_calls):
        raise ValueError("partial public preparation coverage")
    output.mkdir(parents=True, exist_ok=False)
    for source, destination in copies:
        if source.is_symlink():
            raise ValueError("foreground source cannot be a symlink")
        destination.parent.mkdir(parents=True, exist_ok=True)
        try:
            os.link(source, destination)
        except OSError:
            shutil.copy2(source, destination)
    artifacts = {"manifest.json": manifest, "iteration-map.json": dict(schema_version=1, operations=coordinates),
                 "binding-evidence.json": dict(schema_version=1, ranks=public_evidence)}
    if preparations:
        artifacts["preparation-map.json"] = dict(schema_version=1, preparations=preparations)
    for name, data in artifacts.items():
        (output / name).write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("attempt", type=Path)
    parser.add_argument("--cluster", type=Path, required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("-o", "--output", type=Path, required=True)
    args = parser.parse_args()
    bind(args.attempt, args.cluster, args.output, args.run_id)


if __name__ == "__main__":
    main()
