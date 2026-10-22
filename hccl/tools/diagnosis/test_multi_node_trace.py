#!/usr/bin/env python3
"""Multi-node input and dependency regression fixtures; no device claims."""

from __future__ import annotations

import csv
import json
import os
import sqlite3
import sys
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from diagnosis.multi_node_trace import build_cross_node_edges, load_manifest, replay_manifest
    from diagnosis.resource_dependency_graph import build_resource_graph
    from diagnosis.test_diagnosis import create_msprof_db, direct_notify_row, execution_row
    from diagnosis.visualize_dependency_graph import build_execution_edges, read_graph_artifact_nodes
    from diagnosis.validate_dependency_graph import validate_dependency_artifacts
    from diagnosis.visualize_html import build_execution_dependency_model, write_html, write_dependency_svg
else:
    from .multi_node_trace import build_cross_node_edges, load_manifest, replay_manifest
    from .resource_dependency_graph import build_resource_graph
    from .test_diagnosis import create_msprof_db, direct_notify_row, execution_row
    from .visualize_dependency_graph import build_execution_edges, read_graph_artifact_nodes
    from .validate_dependency_graph import validate_dependency_artifacts
    from .visualize_html import build_execution_dependency_model, write_html, write_dependency_svg


NOTIFY = (9 << 32) | 128
RANKS = {3: ("run/node0", 6), 9: ("run/node1", 2)}
EVIDENCE = {"op_fixture": "fixture launch invocation 0, group A"}


def cross_rows():
    send = direct_notify_row(0, 3, 9, "rdma", 100, notify_id=NOTIFY)
    wait = direct_notify_row(1, 9, 3, "notify_wait", 1, notify_id=NOTIFY)
    send.update(_node_id="run/node0", _device_id=6)
    wait.update(_node_id="run/node1", _device_id=2)
    return [send, wait]


def read_csv(path):
    with path.open(encoding="utf-8-sig", newline="") as source:
        return list(csv.DictReader(source))


def create_run_fixture(root):
    """Two physical devices with colliding task IDs and independent clocks."""
    manifest = {"run_id": "fixture", "nodes": [], "ranks": [], "operations": [{
        "operation_id": "allreduce-0", "evidence": "synthetic collective invocation 0",
        "members": [],
    }]}
    for index, (rank, device) in enumerate(((3, 6), (9, 2))):
        node = "node{}".format(index)
        folder = root / node
        plog = folder / "plog"
        db_dir = folder / "db"
        plog.mkdir(parents=True)
        db_dir.mkdir()
        path = db_dir / "msprof_fixture.db"
        create_msprof_db(path, device_id=device)
        connection = sqlite3.connect(path)
        connection.executescript("DELETE FROM TASK; DELETE FROM COMMUNICATION_TASK_INFO; "
                                 "DELETE FROM COMPUTE_TASK_INFO; DELETE FROM COMMUNICATION_OP;")
        connection.execute("INSERT INTO STRING_IDS VALUES(7, ?)", ("RDMASEND" if index == 0 else "NOTIFY_WAIT",))
        op_name = "local_allreduce_{}".format(index)
        connection.execute("UPDATE STRING_IDS SET value=? WHERE id=4", (op_name,))
        connection.execute("INSERT INTO COMMUNICATION_OP VALUES(4, 77, 5, 7, ?)", (device,))
        # Sender's DMA precedes its signal; receiver's DMA follows its wait.
        types = (1, 7) if index == 0 else (7, 1)
        for task, kind in enumerate(types, start=1):
            start = 100000 + task * 1000 if index == 0 else task * 1000
            connection.execute("INSERT INTO TASK VALUES(?, ?, ?, 77, ?, ?, 4294967295, 13, ?, 0)",
                               (start, start + 500, device, task, kind, task))
            connection.execute("INSERT INTO COMMUNICATION_TASK_INFO VALUES(?, ?, ?, ?, 7)",
                               (task, NOTIFY if kind == 7 else -1, rank, 9 if rank == 3 else 3))
        connection.commit()
        connection.close()
        semantic_task = 2 if index == 0 else 1
        kind = "rdma" if index == 0 else "notify_wait"
        event = "tx_ack_start" if index == 0 else "rx_ack_start"
        (plog / "plog-fixture.log").write_text(
            "[HcclTaskSemantic] schema_version[4] device_id[{}] stream_id[13] hccl_task_id[{}] "
            "task_kind[{}] user_rank[{}] comm_rank[{}] rank_size[2] peer_rank[{}] "
            "phase[reduce_scatter] step[0] slice[0] event[{}] semantic[link_ack] "
            "algorithm[ring] notify_id[{}]\n".format(
                device, semantic_task, kind, rank, index, 9 if rank == 3 else 3, event, NOTIFY),
            encoding="utf-8")
        manifest["nodes"].append({"node_id": node, "plog_dir": node + "/plog", "msprof_db_dir": node + "/db"})
        manifest["ranks"].append({"user_rank": rank, "node_id": node, "device_id": device})
        manifest["operations"][0]["members"].append({"node_id": node, "group_name": "group_fixture", "op_name": op_name})
    path = root / "run.json"
    path.write_text(json.dumps(manifest), encoding="utf-8")
    return path, manifest


class MultiNodeTraceTest(unittest.TestCase):
    def test_aicpu_raw_notify_id_requires_complete_rank_channel(self):
        rows = cross_rows()
        rows[0].update(event_name="WRITE_VALUE_SQE", _notify_id=5124)
        rows[1].update(event_name="NOTIFY_WAIT_SQE", _notify_id=5124)
        edges, issues, _ = build_cross_node_edges(rows, RANKS, EVIDENCE)
        self.assertEqual(len(edges), 1)
        self.assertEqual(issues, [])
        self.assertIn("aicpu_rdma_receiver_notify_id", edges[0]["evidence"])
        for change in ({"_notify_id": 5125}, {"_device_id": 3},
                       {"event_name": "NOTIFY_WAIT"}, {"_peer_rank": -1}):
            changed = deepcopy(rows)
            changed[1].update(change)
            edges, issues, _ = build_cross_node_edges(changed, RANKS, EVIDENCE)
            self.assertEqual(edges, [])
            self.assertTrue(issues)
        payload = dict(rows[0], _notify_id=0xFFFFFFFF)
        edges, issues, remote_ids = build_cross_node_edges([payload], RANKS, EVIDENCE)
        self.assertEqual((edges, issues, remote_ids), ([], [], frozenset()))

    def test_cross_node_resource_wait_uses_local_clock(self):
        rows = cross_rows()
        resource = execution_row(2, 45, 3, 3, rank=9)
        resource.update(_node_id="run/node1", _device_id=2)
        rows.append(resource)
        remote, ambiguities, remote_ids = build_cross_node_edges(rows, RANKS, EVIDENCE)
        self.assertEqual(len(remote), 1)
        self.assertEqual(ambiguities, [])
        edges = build_execution_edges(rows, [], remote_ids) + remote
        _, resources, _ = build_resource_graph(rows, edges)
        edge = next(edge for edge in resources if edge["kind"] == "resource_cross_node_notify_sync_observed")
        self.assertEqual(edge["wait_span_ns"], "1000")
        self.assertEqual(edge["remote_block_ns"], "")
        self.assertEqual(edge["post_signal_ns"], "")
        self.assertEqual(edge["timing_status"], "cross_node_uncalibrated")
        self.assertEqual(edge["record_graph_id"], rows[0]["_graph_id"])
        self.assertEqual(edge["wait_graph_id"], rows[1]["_graph_id"])
        shifted = deepcopy(rows)
        for row in shifted:
            if row["_node_id"] == "run/node1":
                row["_start"] += 1000000
                row["_stop"] += 1000000
        remote_shifted, _, _ = build_cross_node_edges(shifted, RANKS, EVIDENCE)
        self.assertEqual(remote_shifted, remote)
        _, shifted_resources, _ = build_resource_graph(shifted, edges)
        self.assertEqual(resources, shifted_resources)

    def test_complete_repeated_direct_channel(self):
        rows = cross_rows()
        for row in deepcopy(rows):
            row["_graph_id"] += "-second"
            row["_task_id"] += 2
            row["_start"] += 10
            row["_stop"] += 10
            rows.append(row)
        edges, issues, _ = build_cross_node_edges(rows[::-1], RANKS, EVIDENCE)
        self.assertEqual(len(edges), 2)
        self.assertEqual(issues, [])
        self.assertEqual({edge["sequence_value"] for edge in edges}, {"0", "1"})

    def test_missing_endpoint_is_single(self):
        edges, issues, _ = build_cross_node_edges(cross_rows()[:1], RANKS, EVIDENCE)
        self.assertEqual(edges, [])
        self.assertEqual(issues[0]["status"], "single")

    def test_no_partial_pairing_for_extra_endpoint_or_stream(self):
        for extra_stream in (45, 46):
            rows = cross_rows()
            extra = dict(rows[0], _graph_id="extra", _stream_id=extra_stream, _task_id=50, _start=110, _stop=111)
            edges, issues, _ = build_cross_node_edges(rows + [extra], RANKS, EVIDENCE)
            self.assertEqual(edges, [])
            self.assertEqual(issues[0]["status"], "ambiguous")

    def test_missing_operation_binding_does_not_join_equal_names(self):
        edges, issues, _ = build_cross_node_edges(cross_rows(), RANKS, {})
        self.assertEqual(edges, [])
        self.assertEqual(issues[0]["missing_fields"], "shared_operation_binding")

    def test_multiple_streams_and_tied_order_do_not_pair(self):
        for multiple_streams in (False, True):
            rows = cross_rows()
            extra = [dict(row, _graph_id=row["_graph_id"] + "-extra") for row in rows]
            if multiple_streams:
                for row in extra:
                    row["_stream_id"] += 1
            edges, issues, _ = build_cross_node_edges(rows + extra, RANKS, EVIDENCE)
            self.assertEqual(edges, [])
            self.assertEqual(issues[0]["status"], "ambiguous")

    def test_incomplete_extra_endpoint_blocks_entire_direction(self):
        rows = cross_rows()
        rows.append(dict(rows[0], _graph_id="missing-notify", _notify_id=-1))
        edges, issues, _ = build_cross_node_edges(rows, RANKS, EVIDENCE)
        self.assertEqual(edges, [])
        self.assertTrue(all(issue["status"] == "incomplete" for issue in issues))

    def test_operations_and_notify_resources_do_not_mix(self):
        rows = cross_rows()
        rows[1]["_operation_scope"] = "other"
        edges, issues, _ = build_cross_node_edges(rows, RANKS, dict(EVIDENCE, other="other invocation"))
        self.assertEqual(edges, [])
        self.assertEqual([issue["status"] for issue in issues], ["single", "single"])
        rows = cross_rows()
        rows[1]["_notify_id"] += 8
        edges, issues, _ = build_cross_node_edges(rows, RANKS, EVIDENCE)
        self.assertEqual(edges, [])
        self.assertEqual(len(issues), 2)

    def test_rank_device_conflict_blocks_direction(self):
        rows = cross_rows()
        rows[0]["_device_id"] = 3  # rank is not the device ID
        edges, issues, _ = build_cross_node_edges(rows, RANKS, EVIDENCE)
        self.assertEqual(edges, [])
        self.assertEqual(issues[0]["missing_fields"], "rank_node_device_mapping")

    def test_payload_sentinel_is_not_a_notify_send(self):
        rows = cross_rows()
        rows[0]["_notify_id"] = (9 << 32) | 0xFFFFFFFF
        edges, issues, _ = build_cross_node_edges(rows, RANKS, EVIDENCE)
        self.assertEqual(edges, [])
        self.assertEqual(issues[0]["missing_role"], "producer")

    def test_single_ffts_occurrence_ignores_local_graph_number(self):
        rows = cross_rows()
        for index, row in enumerate(rows):
            row.update(_subtask_id=index, _graph_instance_id=100 + index)
        edges, issues, _ = build_cross_node_edges(rows, RANKS, EVIDENCE)
        self.assertEqual(len(edges), 1)
        self.assertEqual(issues, [])
        rows += [dict(row, _graph_id=row["_graph_id"] + "-second") for row in rows]
        edges, issues, _ = build_cross_node_edges(rows, RANKS, EVIDENCE)
        self.assertEqual(edges, [])
        self.assertIn("FFts", issues[0]["reason"])

    def test_receiver_semantic_order_is_not_promoted(self):
        rows = cross_rows()
        resource = execution_row(2, 45, 3, 3, rank=9)
        resource.update(_node_id="run/node1", _device_id=2)
        rows.append(resource)
        remote, _, _ = build_cross_node_edges(rows, RANKS, EVIDENCE)
        order = {"edge_id": "order", "kind": "ffts_logical_stream_order", "src": "p1", "dst": "p2",
                 "confidence": "semantic"}
        _, edges, _ = build_resource_graph(rows, remote + [order])
        edge = next(edge for edge in edges if "cross_node" in edge["kind"])
        self.assertEqual(edge["confidence"], "semantic")
        self.assertEqual(edge["kind"], "resource_cross_node_notify_sync_semantic")

    def test_manifest_replay_and_run_isolation(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            path, manifest = create_run_fixture(root)
            first, ok = replay_manifest(path, root / "out")
            self.assertTrue(ok)
            edges = read_csv(first / "dep_graph_edges.csv")
            self.assertEqual(sum(edge["kind"] == "cross_node_notify_sync_observed" for edge in edges), 1)
            nodes = read_graph_artifact_nodes(first / "dep_graph_nodes.csv")
            self.assertEqual(len(nodes), 4)
            self.assertEqual({row["_user_rank"] for row in nodes}, {3, 9})
            self.assertEqual({row["_node_id"] for row in nodes}, {"fixture/node0", "fixture/node1"})
            gate = validate_dependency_artifacts(first / "dep_graph_summary.csv", first / "dep_graph_edges.csv",
                                                 first / "dep_graph_resource_summary.csv", first / "dep_graph_resource_edges.csv")
            self.assertTrue(gate[0], gate)
            manifest["run_id"] = "second"
            path.write_text(json.dumps(manifest), encoding="utf-8")
            second, ok = replay_manifest(path, root / "out")
            self.assertTrue(ok)
            other = read_graph_artifact_nodes(second / "dep_graph_nodes.csv")
            self.assertTrue({row["_graph_id"] for row in nodes}.isdisjoint(row["_graph_id"] for row in other))
            self.assertTrue({row["_operation_scope"] for row in nodes}.isdisjoint(row["_operation_scope"] for row in other))
            with self.assertRaises(FileExistsError):
                replay_manifest(path, root / "out")

    def test_unbound_operations_export_inventory_without_cross_edges(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            path, manifest = create_run_fixture(root)
            manifest["operations"] = []
            path.write_text(json.dumps(manifest), encoding="utf-8")
            output, ok = replay_manifest(path, root / "out")
            self.assertFalse(ok)
            self.assertEqual(len(read_csv(output / "operations.csv")), 2)
            self.assertFalse(any("cross_node" in edge["kind"] for edge in read_csv(output / "dep_graph_edges.csv")))

    def test_multinode_view_uses_local_origins_and_user_rank(self):
        rows = cross_rows()
        edges, _, _ = build_cross_node_edges(rows, RANKS, EVIDENCE)
        before = build_execution_dependency_model(rows, edges)
        rows[1]["_start"] += 10000000
        rows[1]["_stop"] += 10000000
        after = build_execution_dependency_model(rows, edges)
        self.assertEqual({node["id"]: node["x"] for node in before["nodes"]},
                         {node["id"]: node["x"] for node in after["nodes"]})
        self.assertEqual({node["rank"] for node in after["nodes"]}, {3, 9})
        self.assertTrue(all("node" in lane["label"] for lane in after["lanes"]))
        with tempfile.TemporaryDirectory() as temp:
            html, svg = Path(temp) / "graph.html", Path(temp) / "graph.svg"
            write_html(html, "fixture", after)
            write_dependency_svg(svg, "fixture", after)
            self.assertNotIn("__CLOCK_LABEL__", html.read_text(encoding="utf-8"))
            self.assertIn("clocks uncalibrated", svg.read_text(encoding="utf-8"))

    def test_manifest_identity_conflicts(self):
        with tempfile.TemporaryDirectory() as temp:
            path, original = create_run_fixture(Path(temp))
            for field in ("nodes", "ranks"):
                manifest = deepcopy(original)
                manifest[field].append(manifest[field][0])
                path.write_text(json.dumps(manifest), encoding="utf-8")
                with self.assertRaises(ValueError):
                    load_manifest(path)
            manifest = deepcopy(original)
            manifest["operations"].append(dict(manifest["operations"][0], operation_id="another"))
            path.write_text(json.dumps(manifest), encoding="utf-8")
            with self.assertRaises(ValueError):
                load_manifest(path)

    def test_failed_node_merge_does_not_export_graph(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            path, _ = create_run_fixture(root)
            plog = root / "node1/plog/plog-fixture.log"
            plog.write_text(plog.read_text(encoding="utf-8") * 2, encoding="utf-8")
            output, ok = replay_manifest(path, root / "out")
            self.assertFalse(ok)
            self.assertTrue((output / "merge_summary.csv").exists())
            self.assertFalse((output / "dep_graph_nodes.csv").exists())


if __name__ == "__main__":
    unittest.main()
