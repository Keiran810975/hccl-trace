"""Bind public SDK observations through exact DB/API correlation and boundaries."""
from __future__ import annotations

from collections import defaultdict
from contextlib import closing
from dataclasses import dataclass
from .clock_alignment import raw_to_profiler
import json
from pathlib import Path

from .capture_discovery import write_json, read_json
from .dependency_model import stable_id
from .parse_msprof_db import discover_db_files, _readonly_connection, _table_columns, _device_ids


DTYPES = {"int8": 0, "int16": 1, "int32": 2, "float16": 3, "fp16": 3,
          "float32": 4, "fp32": 4, "int64": 5, "uint64": 6, "uint8": 7,
          "uint16": 8, "uint32": 9, "float64": 10, "bf16": 11, "bfloat16": 11}
OPERATIONS = {"allreduce", "allgather", "reducescatter", "broadcast", "reduce", "alltoall", "alltoallv"}


def operation_type(value):
    value = "".join(c for c in str(value).lower() if c.isalnum())
    if value.startswith("hcom"):
        value = value[4:]
    if value not in OPERATIONS:
        raise ValueError("unsupported collective type: " + str(value))
    return value


@dataclass(frozen=True)
class Binding:
    manifest: Path
    iteration_map: Path | None
    preparation_map: Path | None
    coordinates: tuple
    evidence: dict


def _read_calls(path):
    records = [json.loads(line) for line in Path(path).read_text(encoding="utf-8-sig").splitlines() if line.strip()]
    header, calls, completions = records[0], [], {}
    if records[-1].get("event") != "capture_end" or records[-1].get("pending_sequences"):
        raise ValueError("SDK capture is incomplete or missing a user-controlled completion boundary")
    for record in records[1:]:
        if record["event"] == "call":
            if record.get("status") != "submitted":
                raise ValueError("failed public collective cannot be bound")
            if any(record.get(k) != header[k] for k in ("run_id", "node_id", "user_rank", "device_id")):
                raise ValueError("public call changed runtime identity")
            calls.append(record)
        elif record["event"] == "completion":
            for sequence in record["sequences"]:
                if sequence in completions:
                    raise ValueError("duplicate public completion observation")
                completions[sequence] = record["clocks"]["raw_ns"]
        elif record["event"] != "capture_end":
            raise ValueError("unsupported SDK event")
    if [c["sequence"] for c in calls] != list(range(len(calls))) or set(completions) != set(range(len(calls))):
        raise ValueError("complete unique SDK call/completion sequence required")
    for call in calls:
        before, after, complete = call["before"]["raw_ns"], call["after"]["raw_ns"], completions[call["sequence"]]
        if any(type(v) is not int or v < 0 for v in (before, after, complete)) or not before <= after <= complete:
            raise ValueError("invalid public call/completion clock observations")
        call["completion_raw_ns"] = complete
        if "input_buffer_ptr" in call and (type(call["input_buffer_ptr"]) is not int or not 0 < call["input_buffer_ptr"] < 2**64):
            raise ValueError("invalid observed input buffer identity")
        if (call.get("stage") not in {"warmup", "measured"}
                or any(type(call.get(k)) is not int or call[k] < 0 for k in ("iteration", "occurrence", "element_count"))
                or not call.get("call_site") or not call.get("group_id")):
            raise ValueError("invalid SDK workload location")
    return header, calls


def _inventory(node):
    devices = {}
    for path in discover_db_files(node["msprof_db_dir"]):
        with closing(_readonly_connection(str(path))) as db:
            required = {"startNs", "endNs", "connectionId", "count", "dataType", "opType"}
            if not required <= _table_columns(db, "COMMUNICATION_OP") or not {
                    "startNs", "endNs", "connectionId", "name"} <= _table_columns(db, "CANN_API"):
                raise ValueError("SDK binding requires COMMUNICATION_OP/CANN_API timing, type/count and connectionId")
            info_path = path.parent / "host/start_info"
            if not info_path.is_file():
                raise ValueError("SDK binding needs the original profiler host/start_info clock observation")
            info = read_json(info_path)
            offset = int(info["collectionTimeBegin"]) * 1000 - int(info["clockMonotonicRaw"])
            device, = _device_ids(db)
            ops = [dict(row) for row in db.execute(
                "SELECT o.*,g.value AS group_name,n.value AS op_name,t.value AS operation_type "
                "FROM COMMUNICATION_OP o JOIN STRING_IDS g ON g.id=o.groupName "
                "JOIN STRING_IDS n ON n.id=o.opName JOIN STRING_IDS t ON t.id=o.opType")]
            apis, named = defaultdict(list), defaultdict(list)
            for row in db.execute("SELECT a.*,s.value AS api_name FROM CANN_API a JOIN STRING_IDS s ON s.id=a.name"):
                record = dict(row)
                apis[row["connectionId"]].append(record)
                name = "".join(c for c in record["api_name"].lower() if c.isalnum())
                named[(record.get("globalTid"), record["startNs"], record["endNs"], name)].append(record)
            linked = []
            for op in ops:
                try:
                    kind = operation_type(op["operation_type"])
                except ValueError:
                    continue
                matching = [a for a in apis[op["connectionId"]]
                            if "".join(c for c in a["api_name"].lower() if c.isalnum()) == "hcom" + kind]
                method = "named_api_connection_id"
                if not matching:
                    # HOST records the runtime launch connection, while AI_CPU
                    # records the HCCL API connection. Join only the exact same
                    # global thread and API interval, never a nearby/enclosing call.
                    launches = [a for a in apis[op["connectionId"]] if a["api_name"] == "launch" and "globalTid" in a]
                    if len(launches) == 1:
                        launch = launches[0]
                        matching = named[(launch["globalTid"], launch["startNs"], launch["endNs"], "hcom" + kind)]
                        method = "runtime_launch_connection_and_exact_named_api_interval"
                if len(matching) != 1:
                    raise ValueError("collective has no unique named CANN_API connectionId endpoint")
                op.update(api=matching[0], kind=kind, api_binding_method=method)
                linked.append(op)
            if device in devices:
                raise ValueError("duplicate per-device profiler input")
            stop_path = info_path.with_name("end_info")
            devices[device] = dict(path=path, offset=offset, operations=linked,
                clock_start=info, clock_stop=read_json(stop_path) if stop_path.is_file() else None)
    return devices


def _unique_assignment(candidates):
    """Only accept a provably unique complete bijection, never nearest/ordinal."""
    remaining = {key: set(values) for key, values in candidates.items()}
    if len(set().union(*remaining.values())) != len(remaining):
        raise ValueError("public calls do not cover a unique complete set of DB/API observations")
    result = {}
    while remaining:
        if any(not values for values in remaining.values()):
            raise ValueError("public call has no compatible DB/API evidence")
        forced = next(((key, next(iter(values))) for key, values in remaining.items() if len(values) == 1), None)
        if forced is None:
            owners = defaultdict(list)
            for key, values in remaining.items():
                for value in values:
                    owners[value].append(key)
            forced = next(((keys[0], value) for value, keys in owners.items() if len(keys) == 1), None)
        if forced is None:
            raise ValueError("ambiguous public/API binding; record narrower actual completion/call boundaries or explicit group names")
        key, value = forced
        result[key] = value
        del remaining[key]
        for values in remaining.values():
            values.discard(value)
    return result


def bind_capture(capture, work, *, mode):
    work = Path(work)
    manifest = json.loads(json.dumps(capture.manifest))
    if not capture.call_logs:
        if mode == "rolling" and capture.iteration_map is None:
            raise ValueError("rolling requires SDK observations or an evidenced legacy iteration-map.json")
        path = work / "manifest.json"
        write_json(path, manifest)
        return Binding(path, capture.iteration_map, capture.preparation_map, (),
                       dict(kind="legacy_manifest", sdk_bound_calls=0))
    inventory = {n["node_id"]: _inventory(n) for n in manifest["nodes"]}
    from .aicpu_buffers import read_buffers
    pointer_facts = {}
    # Sparse optional evidence; ordinary SDK workloads still use the existing unique API proof.
    pointer_nodes = set()
    for path in capture.call_logs:
        header, records = _read_calls(path)
        if any("input_buffer_ptr" in call for call in records):
            if not all("input_buffer_ptr" in call for call in records):
                raise ValueError("buffer identity observation must cover every call on a rank")
            pointer_nodes.add(header["node_id"])
    for node in manifest["nodes"]:
        if node["node_id"] in pointer_nodes:
            pointer_facts[node["node_id"]] = read_buffers(node["plog_dir"])
    bound, seen = defaultdict(list), set()
    for path in capture.call_logs:
        header, calls = _read_calls(path)
        rank, node, device = (header[k] for k in ("user_rank", "node_id", "device_id"))
        if rank in seen:
            raise ValueError("duplicate SDK rank")
        seen.add(rank)
        data = inventory[node][device]
        ops, offset = data["operations"], data["offset"]
        clock_start, clock_stop = data["clock_start"], data["clock_stop"]
        def convert(raw, start=clock_start, stop=clock_stop):
            return raw_to_profiler(raw, start, stop)
        if node in pointer_facts:
            with closing(_readonly_connection(str(data["path"]))) as db:
                required = {"deviceId", "streamId", "taskId", "connectionId"}
                if not required <= _table_columns(db, "TASK"):
                    raise ValueError("buffer binding needs exact runtime TASK anchors")
                anchors = defaultdict(list)
                if not {"globalTaskId", "opId", "groupName"} <= _table_columns(db, "COMMUNICATION_TASK_INFO"):
                    raise ValueError("buffer binding needs authoritative communication task ownership")
                for row in db.execute("SELECT t.streamId,t.taskId,c.opId,c.groupName FROM TASK t "
                        "JOIN COMMUNICATION_TASK_INFO c ON c.globalTaskId=t.globalTaskId WHERE t.deviceId=?", (device,)):
                    anchors[(row["streamId"], row["taskId"])].append((row["opId"], row["groupName"]))
                by_connection = defaultdict(list)
                for index, op in enumerate(ops):
                    by_connection[(op["opId"], op["groupName"])].append(index)
                for (owner, rank_size, stream, task), (fact, proof) in pointer_facts[node].items():
                    if owner != rank or rank_size not in {len(call["participants"]) for call in calls}:
                        continue
                    endpoints = anchors.get((stream, task), [])
                    if len(endpoints) != 1 or len(by_connection[endpoints[0]]) != 1:
                        raise ValueError("AI_CPU buffer has no unique exact TASK/communication ownership")
                    op = ops[by_connection[endpoints[0]][0]]
                    if op["kind"] != "allreduce" or op["dataType"] != 4:
                        continue
                    if op["count"] * 4 != fact["input_buffer_bytes"]:
                        raise ValueError("buffer bytes/type disagree with anchored communication op")
                    op.update(input_buffer_ptr=fact["input_buffer_ptr"], buffer_identity_evidence=proof)
        possible = {}
        for call in calls:
            kind = operation_type(call["operation_type"])
            dtype = DTYPES.get(call["dtype"].lower())
            if dtype is None:
                raise ValueError("unsupported recorded dtype")
            matches = set()
            before_epoch, completion_epoch = convert(call["before"]["raw_ns"]), convert(call["completion_raw_ns"])
            for index, op in enumerate(ops):
                api = op["api"]
                if (op["kind"] == kind and op["count"] == call["element_count"] and op["dataType"] == dtype
                        and ("input_buffer_ptr" not in call or call["input_buffer_ptr"] == op.get("input_buffer_ptr"))
                        and op["deviceId"] == device
                        and (not call.get("db_group_name") or op["group_name"] == call["db_group_name"])
                        and before_epoch <= api["startNs"] <= api["endNs"] <= completion_epoch
                        and api["startNs"] <= op["startNs"] <= op["endNs"] <= completion_epoch):
                    matches.add(index)
            possible[call["sequence"]] = matches
        if not calls:
            raise ValueError("SDK rank has no observable collective calls")
        try:
            assignment = _unique_assignment(possible)
        except ValueError as error:
            missing = [sequence for sequence, choices in possible.items() if not choices]
            raise ValueError("{}; node={} rank={} device={} unmatched public sequences={}".format(
                error, node, rank, device, missing[:8])) from error
        for call in calls:
            op = ops[assignment[call["sequence"]]]
            key = tuple(call[k] for k in ("group_id", "stage", "iteration", "call_site", "occurrence"))
            bound[key].append(dict(call=call, op=op, offset=offset, convert=convert, node_id=node, device_id=device, user_rank=rank))
    coordinates, preparations, operations, evidence = [], [], [], []
    group_names, db_owners = {}, {}
    for key, entries in sorted(bound.items()):
        first = entries[0]["call"]
        participants = first["participants"]
        if (not participants or participants != sorted(set(participants))
                or any(type(r) is not int or r < 0 for r in participants)
                or {e["user_rank"] for e in entries} != set(participants)
                or len(entries) != len(participants)):
            raise ValueError("missing or duplicate actual communication group participants")
        signature = (tuple(participants), operation_type(first["operation_type"]), DTYPES[first["dtype"].lower()],
                     first["element_count"], first.get("reduction"))
        if any((tuple(e["call"]["participants"]), operation_type(e["call"]["operation_type"]),
                DTYPES[e["call"]["dtype"].lower()], e["call"]["element_count"], e["call"].get("reduction")) != signature for e in entries):
            raise ValueError("ranks disagree on group membership or collective shape")
        op_id = stable_id("call", key)
        scope = stable_id("op", (manifest["run_id"], op_id))
        members = []
        for entry in entries:
            op = entry["op"]
            endpoint = entry["node_id"], entry["device_id"], key[0]
            if endpoint in group_names and group_names[endpoint] != op["group_name"]:
                raise ValueError("logical group changes its actual DB communicator")
            owner = entry["node_id"], entry["device_id"], op["group_name"]
            if owner in db_owners and db_owners[owner] != key[0]:
                raise ValueError("two logical groups alias the same actual communicator")
            group_names[endpoint], db_owners[owner] = op["group_name"], key[0]
            members.append(dict(node_id=entry["node_id"], device_id=entry["device_id"],
                                group_name=op["group_name"], op_name=op["op_name"]))
            call, api, offset = entry["call"], op["api"], entry["offset"]
            if "preparation_start_raw_ns" in call:
                preparations.append(dict(operation_scope=scope, node_id=manifest["run_id"] + "/" + entry["node_id"],
                    user_rank=entry["user_rank"], device_id=entry["device_id"],
                    start_ns=entry["convert"](call["preparation_start_raw_ns"]), stop_ns=entry["convert"](call["before"]["raw_ns"]),
                    api_start_ns=api["startNs"], api_stop_ns=api["endNs"], evidence="SDK public preparation + exact CANN_API connectionId binding"))
        proof = "Complete explicit group membership; unique public clock envelopes; exact named API connectionId or runtime launch connectionId plus identical global thread/start/end; verified type/dtype/count and observed completion bounds"
        if "input_buffer_ptr" in first:
            proof += "; actual DDP tensor address equals Device input address; exact reported main-stream TASK/globalTaskId/COMMUNICATION_TASK_INFO opId+groupName ownership (no task offset or order fallback)"
        operations.append(dict(operation_id=op_id, members=members, participants=participants, evidence=proof))
        coordinates.append(dict(operation_scope=scope, **dict(zip(("group_id", "stage", "iteration", "call_site", "occurrence"), key)), evidence=proof))
        evidence.append(dict(operation_id=op_id, participants=participants, group_id=key[0],
                             operation_type=signature[1], dtype=signature[2], element_count=signature[3],
                             operation_connection_ids=[e["op"]["connectionId"] for e in entries],
                             named_api_connection_ids=[e["op"]["api"]["connectionId"] for e in entries],
                             api_binding_methods=[e["op"]["api_binding_method"] for e in entries],
                             reduction_verified_in_database=False))
    if manifest.get("operations"):
        raise ValueError("do not mix prebound legacy operations with SDK bindings")
    for node in manifest["nodes"]:
        node["clock_validation_files"] = [str(path) for path in capture.call_logs
            if _read_calls(path)[0]["node_id"] == node["node_id"]]
    auxiliary_count = 0
    if manifest.get("sdk_auxiliary_operation_types"):
        from .auxiliary_operations import bind_auxiliary
        controls, audit = bind_auxiliary(bound, inventory, manifest["sdk_auxiliary_operation_types"])
        operations.extend(controls)
        evidence.extend(audit)
        auxiliary_count = len(controls)
    manifest["operations"] = operations
    path, iteration = work / "manifest.json", work / "iteration-map.json"
    write_json(path, manifest)
    write_json(iteration, dict(schema_version=2, operations=coordinates))
    prep = work / "preparation-map.json" if preparations else None
    if prep:
        write_json(prep, dict(schema_version=1, preparations=preparations))
    write_json(work / "binding-evidence.json", dict(schema_version=1, operations=evidence))
    return Binding(path, iteration, prep, tuple(coordinates), dict(kind="sdk_exact_api", sdk_bound_calls=sum(len(v) for v in bound.values()),
        bound_operation_count=len(operations), auxiliary_bound_operation_count=auxiliary_count, reduction_verified_in_database=False))
