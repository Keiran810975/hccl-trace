#!/usr/bin/env python3
"""Replay one profile run and join evidenced cross-node RDMA Notify channels."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections import defaultdict
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from diagnosis import merge_timeline as merge
    from diagnosis import visualize_dependency_graph as execution
    from diagnosis.dependency_model import DependencyEdgeIdentity, OperationScopeIdentity, stable_id
    from diagnosis.resource_dependency_graph import export_resource_dependency_tables
    from diagnosis.schema import MERGED_FIELDS, write_csv
    from diagnosis.validate_trace import validate_rows
    from diagnosis.validate_dependency_graph import validate_dependency_artifacts
    from diagnosis.parse_msprof_db import parse_operations
    from diagnosis.control_trace import parse_build_spans, BUILD_FIELDS
else:
    from . import merge_timeline as merge
    from . import visualize_dependency_graph as execution
    from .dependency_model import DependencyEdgeIdentity, OperationScopeIdentity, stable_id
    from .resource_dependency_graph import export_resource_dependency_tables
    from .schema import MERGED_FIELDS, write_csv
    from .validate_trace import validate_rows
    from .validate_dependency_graph import validate_dependency_artifacts
    from .parse_msprof_db import parse_operations
    from .control_trace import parse_build_spans, BUILD_FIELDS


UINT32_MAX = (1 << 32) - 1


def _name(value: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", value):
        raise ValueError("run/node ID must use letters, digits, '.', '_' or '-': {!r}".format(value))
    return value


def load_manifest(path: Path) -> dict:
    """Resolve paths and check only identities needed for safe input partitioning."""
    manifest = json.loads(path.read_text(encoding="utf-8-sig"))
    _name(manifest["run_id"])
    nodes = set()
    inputs = set()
    for node in manifest["nodes"]:
        node_id = _name(node["node_id"])
        if node_id in nodes:
            raise ValueError("duplicate node_id: {}".format(node_id))
        nodes.add(node_id)
        for field in ("plog_dir", "msprof_db_dir"):
            source = (path.parent / node[field]).resolve()
            if source in inputs:
                raise ValueError("input directory reused across nodes: {}".format(source))
            inputs.add(source)
            node[field] = str(source)
    if not nodes:
        raise ValueError("manifest has no nodes")
    ranks = set()
    devices = set()
    for rank in manifest["ranks"]:
        endpoint = (rank["node_id"], rank["device_id"])
        if rank["user_rank"] in ranks or endpoint in devices:
            raise ValueError("rank/device mapping must be one-to-one: {}".format(rank))
        if rank["node_id"] not in nodes or rank["user_rank"] < 0 or rank["device_id"] < 0:
            raise ValueError("invalid rank mapping: {}".format(rank))
        ranks.add(rank["user_rank"])
        devices.add(endpoint)
    # An operation binding is a capture-owner assertion backed by launch/DB
    # evidence. Equal DB strings alone never create a cross-node scope.
    seen_members = set()
    operation_ids = set()
    for operation in manifest.get("operations", []):
        if not operation["operation_id"] or operation["operation_id"] in operation_ids:
            raise ValueError("duplicate/empty operation_id")
        operation_ids.add(operation["operation_id"])
        if not operation.get("evidence", "").strip():
            raise ValueError("operation binding requires capture evidence")
        member_nodes = set()
        for member in operation["members"]:
            key = (member["node_id"], member["group_name"], member["op_name"])
            if (key in seen_members or member["node_id"] in member_nodes
                    or member["node_id"] not in nodes or not all(key)):
                raise ValueError("operation binding is not one-to-one: {}".format(key))
            member_nodes.add(member["node_id"])
            seen_members.add(key)
    return manifest


def operation_bindings(manifest: dict):
    bindings = {}
    evidence = {}
    for operation in manifest.get("operations", []):
        shared = stable_id("op", (manifest["run_id"], operation["operation_id"]))
        evidence[shared] = operation["evidence"]
        for member in operation["members"]:
            local = OperationScopeIdentity(member["group_name"], member["op_name"]).stable_id
            bindings[(member["node_id"], local)] = shared
    return bindings, evidence


def build_cross_node_edges(rows: list[dict], ranks: dict, operation_evidence: dict):
    """Compatibility entry point for cross-node-only audits."""
    return build_rdma_notify_edges(rows, ranks, operation_evidence, include_same_node=False)


def build_rdma_notify_edges(rows: list[dict], ranks: dict, operation_evidence: dict,
                           include_same_node: bool = True):
    """Join complete channels; no time comparison between different nodes.

    Host Ibverbs shares (receiver user rank, notify offset). AI_CPU shares the
    receiver's hardware Notify ID; DB rank endpoints disambiguate devices.
    Payload RDMA uses a low-word UINT32_MAX sentinel. Repeated
    direct occurrences require one uniquely ordered stream on each side;
    FFts currently supports only one occurrence per operation/channel.
    """
    groups = defaultdict(list)
    remote_ids = set()
    blocked_directions = set()
    # Do not steal SDMA Notify pairs from the existing local builder. A same-node
    # direction needs an actual RDMA Notify producer, not just a wait opcode.
    rdma_directions = {
        (row.get("_operation_scope", ""), row["_user_rank"], row["_peer_rank"])
        for row in rows if row.get("profiler_task_kind") == "rdma"
        and not (row["_notify_id"] >= 0 and row["_notify_id"] & UINT32_MAX == UINT32_MAX)
    }
    for row in rows:
        kind = row.get("profiler_task_kind", "")
        if kind not in ("rdma", "notify_wait"):
            continue
        notify = row["_notify_id"]
        if kind == "rdma" and notify >= 0 and notify & UINT32_MAX == UINT32_MAX:
            continue
        local, peer = row["_user_rank"], row["_peer_rank"]
        aicpu = row.get("event_name", "") in ("WRITE_VALUE_SQE", "NOTIFY_WAIT_SQE")
        encoding = "aicpu_notify_id" if aicpu else "host_rank_offset"
        if kind == "notify_wait" and peer < 0:
            continue  # Device-local control remains with the existing builder.
        local_endpoint, peer_endpoint = ranks.get(local), ranks.get(peer)
        producer, consumer = (local, peer) if kind == "rdma" else (peer, local)
        scope = row.get("_operation_scope", "")
        same_node = local_endpoint and peer_endpoint and local_endpoint[0] == peer_endpoint[0]
        if same_node and (not include_same_node or (scope, producer, consumer) not in rdma_directions):
            continue
        remote_ids.add(row["_graph_id"])
        error = ""
        if (not local_endpoint or not peer_endpoint
                or local_endpoint != (row["_node_id"], row["_device_id"])
                or local_endpoint == peer_endpoint):
            error = "rank_node_device_mapping"
        elif scope not in operation_evidence or row.get("_operation_scope_status") != "unique":
            error = "shared_operation_binding"
        elif (notify < 0 or notify & UINT32_MAX == UINT32_MAX
              or (aicpu and notify >= UINT32_MAX)
              or (not aicpu and notify >> 32 != consumer)):
            error = "receiver_rank_notify_offset"
        direction = (scope, producer, consumer)
        if error:
            blocked_directions.add(direction)
        groups[direction + (encoding, notify)].append({"row": row, "role": kind, "error": error})

    edges, ambiguities = [], []
    for key, endpoints in sorted(groups.items()):
        scope, producer_rank, consumer_rank, encoding, notify = key
        producers = [item for item in endpoints if item["role"] == "rdma"]
        consumers = [item for item in endpoints if item["role"] == "notify_wait"]
        channel_id = stable_id("rnc", key + (
            ranks.get(producer_rank, ()), ranks.get(consumer_rank, ()),
        ))
        stream_counts = [len({(item["row"]["_node_id"], item["row"]["_device_id"],
                              item["row"]["_stream_id"]) for item in side})
                         for side in (producers, consumers)]
        status, reason = "", ""
        if key[:3] in blocked_directions:
            status, reason = "incomplete", "channel direction has incomplete or conflicting endpoint metadata"
        elif not producers or not consumers:
            status, reason = "single", "RDMA Notify channel has only one endpoint role"
        elif len(producers) != len(consumers):
            status, reason = "ambiguous", "RDMA/Wait counts differ; no partial ordinal pairing"
        elif stream_counts != [1, 1]:
            status, reason = "ambiguous", "endpoint role spans multiple physical streams"
        elif len(producers) > 1 and any(item["row"]["_subtask_id"] >= 0 for item in endpoints):
            status, reason = "ambiguous", "repeated FFts channel lacks a shared occurrence identity"
        elif (execution._has_ambiguous_direct_order(producers)
              or execution._has_ambiguous_direct_order(consumers)):
            status, reason = "ambiguous", "endpoint local execution order is not unique"
        if status:
            ambiguities.append({
                "graph_schema_version": execution.GRAPH_SCHEMA_VERSION,
                "relation_id": channel_id, "status": status,
                "missing_role": "producer" if not producers else "consumer" if not consumers else "",
                "missing_fields": "|".join(sorted({item["error"] for item in endpoints if item["error"]})),
                "endpoint_count": len(endpoints), "producer_count": len(producers),
                "consumer_count": len(consumers), "producer_stream_count": stream_counts[0],
                "consumer_stream_count": stream_counts[1], "operation_scope": scope,
                "rank_domain": "user", "producer_rank": producer_rank, "consumer_rank": consumer_rank,
                "notify_id": notify, "reason": reason,
                "node_id": ";".join(sorted({item["row"]["_node_id"] for item in endpoints})),
                "endpoint_graph_ids": ";".join(sorted(item["row"]["_graph_id"] for item in endpoints)),
            })
            continue
        producers.sort(key=execution._direct_notify_order_key)
        consumers.sort(key=execution._direct_notify_order_key)
        for ordinal, (producer, consumer) in enumerate(zip(producers, consumers)):
            src, dst = producer["row"], consumer["row"]
            relation_id = stable_id("rnr", (channel_id, ordinal))
            same_node = ranks[producer_rank][0] == ranks[consumer_rank][0]
            kind = "same_node_rdma_notify_sync_observed" if same_node else "cross_node_notify_sync_observed"
            edge = {
                "graph_schema_version": execution.GRAPH_SCHEMA_VERSION,
                "edge_id": DependencyEdgeIdentity(kind, src["_graph_id"], dst["_graph_id"], relation_id).stable_id,
                "kind": kind, "src": src["_graph_id"], "dst": dst["_graph_id"],
                "relation_id": relation_id, "confidence": "observed",
                "reason": "shared operation, receiver Notify resource and complete per-side channel order",
                "evidence": ("msprof_aicpu_rdma_receiver_notify_id; " if encoding == "aicpu_notify_id"
                             else "msprof_rdma_notify_rank_offset; ") + operation_evidence[scope],
                "sequence_kind": "db_notify_ordinal", "sequence_value": str(ordinal),
            }
            for field in ("device", "stream", "task"):
                edge["src_" + field] = src["_" + field + "_id"]
                edge["dst_" + field] = dst["_" + field + "_id"]
            edges.append(edge)
    return edges, ambiguities, frozenset(remote_ids)


def replay_manifest(manifest_path: Path, output_dir: Path, min_match_rate: float = 95.0):
    manifest = load_manifest(manifest_path)
    run_id = manifest["run_id"]
    # A fresh run directory keeps failed/rerun outputs from inheriting old edges.
    destination = output_dir / run_id
    destination.mkdir(parents=True, exist_ok=False)
    bindings, evidence = operation_bindings(manifest)
    ranks = {rank["user_rank"]: (run_id + "/" + rank["node_id"], rank["device_id"])
             for rank in manifest["ranks"]}
    device_ranks = {endpoint: rank for rank, endpoint in ranks.items()}
    all_rows, summaries, inventory, operation_times = [], [], [], []
    node_gates = []
    for node in manifest["nodes"]:
        node_id = node["node_id"]
        node_dir = destination / node_id
        node_dir.mkdir()
        semantics = merge.parse_plog_inputs(plog_dir=node["plog_dir"], node_id=node_id)
        correlations = merge.parse_graph_correlation_inputs(plog_dir=node["plog_dir"], node_id=node_id)
        if any(record.node_id != node_id for record in semantics + correlations):
            raise ValueError("plog node_id conflicts with manifest: {}".format(node_id))
        profilers = merge.parse_msprof_inputs(msprof_db_dir=node["msprof_db_dir"], node_id=node_id)
        for operation in parse_operations(node["msprof_db_dir"], node_id):
            local_scope = OperationScopeIdentity(operation.group_name, operation.op_name).stable_id
            scope = bindings.get((node_id, local_scope), stable_id("op", (run_id, node_id, local_scope)))
            operation_times.append({
                "node_id": run_id + "/" + node_id, "device_id": operation.device_id,
                "user_rank": device_ranks.get((run_id + "/" + node_id, operation.device_id), -1),
                "operation_scope": scope, "op_name": operation.op_name, "group_name": operation.group_name,
                "start_ns": operation.start_ns, "end_ns": operation.end_ns,
                "duration_ns": operation.end_ns - operation.start_ns,
            })
        profilers, control_audit = merge.apply_control_inputs(profilers, plog_dir=node["plog_dir"], node_id=node_id)
        write_csv(str(node_dir / "control_metadata.csv"), merge.CONTROL_AUDIT_FIELDS, control_audit)
        rows, stats = merge.merge_records(semantics, profilers, correlations)
        stats["control_tasks_enriched"] = len(control_audit)
        build_spans = parse_build_spans(merge._semantic_log_paths(node["plog_dir"]), node_id, profilers)
        write_csv(str(node_dir / "build_spans.csv"), BUILD_FIELDS, build_spans)
        stats["build_spans_observed"] = len(build_spans)
        write_csv(str(node_dir / "merged.csv"), MERGED_FIELDS, rows)
        ok, _ = validate_rows([{key: str(value) for key, value in row.items()} for row in rows], min_match_rate)
        if stats["duplicate_graph_correlation_keys"] or stats["ambiguous_semantic"]:
            ok = False
        node_gates.append(ok)
        for metric, value in sorted(stats.items()):
            summaries.append({"node_id": node_id, "metric": metric, "value": value})
        summaries.append({"node_id": node_id, "metric": "merge_gate_passed", "value": int(ok)})
        for task in profilers:
            inventory.append({"node_id": node_id, "device_id": task.device_id,
                              "group_name": task.group_name, "op_name": task.op_name,
                              "profiler_op_id": task.profiler_op_id})
        for row in rows:
            item = dict(row, node_id=run_id + "/" + node_id)
            if row["match_status"] == "profiler_only" and int(row["user_rank"]) < 0:
                item["user_rank"] = device_ranks.get((item["node_id"], row["device_id"]), -1)
            local_scope = row["profiler_op_scope"]
            if local_scope:
                item["profiler_op_scope"] = bindings.get(
                    (node_id, local_scope), stable_id("op", (run_id, node_id, local_scope)))
            all_rows.append(item)
    write_csv(str(destination / "merge_summary.csv"), ["node_id", "metric", "value"], summaries)
    inventory_fields = ["node_id", "device_id", "group_name", "op_name", "profiler_op_id"]
    unique_inventory = {tuple(row[field] for field in inventory_fields) for row in inventory}
    write_csv(str(destination / "operations.csv"), inventory_fields,
              (dict(zip(inventory_fields, row)) for row in sorted(unique_inventory)))
    write_csv(str(destination / "operation_timings.csv"),
              ["node_id", "device_id", "user_rank", "operation_scope", "op_name", "group_name",
               "start_ns", "end_ns", "duration_ns"], operation_times)
    (destination / "inputs.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    merged_path = destination / "merged.csv"
    write_csv(str(merged_path), MERGED_FIELDS, all_rows)
    if not all(node_gates):
        return destination, False  # Keep local merge evidence; do not graph invalid matches.
    graph_rows = execution.read_execution_rows(merged_path)
    remote_edges, ambiguities, remote_ids = build_rdma_notify_edges(graph_rows, ranks, evidence)
    def same_node_issue(issue):
        producer, consumer = ranks.get(issue["producer_rank"]), ranks.get(issue["consumer_rank"])
        return bool(producer and consumer and producer[0] == consumer[0])
    local_unresolved = sum(same_node_issue(issue) for issue in ambiguities)
    remote_unresolved = len(ambiguities) - local_unresolved
    cross_count = sum(edge["kind"] == "cross_node_notify_sync_observed" for edge in remote_edges)
    edges = execution.build_execution_edges(graph_rows, ambiguities, remote_ids) + remote_edges
    prefix = destination / "dep_graph"
    execution.export_execution_tables(graph_rows, edges, ambiguities, prefix)
    export_resource_dependency_tables(
        destination / "dep_graph_nodes.csv", destination / "dep_graph_edges.csv", prefix)
    graph_ok, _, _ = validate_dependency_artifacts(
        destination / "dep_graph_summary.csv", destination / "dep_graph_edges.csv",
        destination / "dep_graph_resource_summary.csv", destination / "dep_graph_resource_edges.csv")
    ready = graph_ok and bool(cross_count) and remote_unresolved == 0 and local_unresolved == 0
    write_csv(str(destination / "run_summary.csv"), ["metric", "value"], [
        {"metric": "graph_gate_passed", "value": int(graph_ok)},
        {"metric": "cross_node_edges", "value": cross_count},
        {"metric": "same_node_rdma_edges", "value": len(remote_edges) - cross_count},
        {"metric": "same_node_rdma_unresolved_channels", "value": local_unresolved},
        {"metric": "cross_node_unresolved_channels", "value": remote_unresolved},
        {"metric": "replay_gate_passed", "value": int(ready)},
    ])
    return destination, ready


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("-o", "--output-dir", type=Path, required=True)
    parser.add_argument("--min-match-rate", type=float, default=95.0)
    args = parser.parse_args()
    try:
        destination, ok = replay_manifest(args.manifest, args.output_dir, args.min_match_rate)
    except (OSError, ValueError, KeyError) as error:
        parser.exit(1, "multi-node replay failed: {}\n".format(error))
    print("output={}".format(destination))
    print("replay_gate_passed={}".format(int(ok)))
    print("See merge_summary.csv, run_summary.csv and dep_graph_notify_ambiguities.csv for evidence.")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
