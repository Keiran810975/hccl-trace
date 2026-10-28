from __future__ import annotations

from copy import deepcopy
from decimal import Decimal
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest

from . import cross_node_diagnosis as cross
from . import rdma_timing
from .parse_msprof_db import parse_communication_details
from .rolling_diagnosis import RollingOptions
from .test_diagnosis import create_msprof_db
from .test_rdma_timing import fixture


def capture():
    rows, edges, coordinates = [], [], {}
    for iteration in range(8):
        local, links = fixture()
        for row in local:
            row["_graph_id"] += "-" + str(iteration)
            row["_operation_scope"] = "call-" + str(iteration)
            row["_start_order"] += iteration * 1000
            row["_stop_order"] += iteration * 1000
        if iteration == 7:
            local[-1]["_stop_order"] += 180
        for edge in links:
            for key in ("src", "dst", "edge_id"):
                edge[key] += "-" + str(iteration)
        rows += local
        edges += links
        coordinates["call-" + str(iteration)] = dict(stage="measured", iteration=iteration, block=0, bucket=0)
    return rows, edges, coordinates


class CrossNodeDiagnosisTests(unittest.TestCase):
    def report(self, rows, edges, coordinates, **args):
        return cross.analyze(rdma_timing.analyze(rows, edges), rows, edges, coordinates, RollingOptions(), **args)

    def test_detects_protocol_overrun_with_five_past_intervals_no_wire_claim(self):
        rows, edges, coordinates = capture()
        original = deepcopy((rows, edges))
        report = self.report(rows, edges, coordinates)
        slow, = [s for s in report["segments"] if s["is_slow"]]
        self.assertEqual(slow["iteration"], 7)
        self.assertEqual(slow["reference_iterations"], [2, 3, 4, 5, 6])
        self.assertEqual(slow["reference_mean_ns"], "20000")
        self.assertEqual(slow["protocol_duration_ns"], 200000)
        self.assertEqual(slow["diagnosis"], "cross_node_path_candidate")
        self.assertEqual(slow["physical_cause"], "unknown")
        self.assertIsNone(slow["network_transfer_duration_ns"])
        self.assertEqual((rows, edges), original)

    def test_links_existing_upstream_candidates_not_injection_truth(self):
        rows, edges, coordinates = capture()
        root = dict(root_id="source", status="dependency_supported_candidate",
                    evidence_paths={"done-7": ["payload-signal-7", "signal-done-7"]})
        report = self.report(rows, edges, coordinates, rolling_report=dict(root_causes=[root]))
        item, = [s for s in report["segments"] if s["is_slow"]]
        self.assertEqual(item["diagnosis"], "upstream_source_candidates")
        self.assertEqual(item["source_root_ids"], ["source"])

    def test_missing_mapping_history_and_ambiguity_do_not_get_guessed(self):
        rows, edges, coordinates = capture()
        self.assertTrue(all(s["comparison_status"] == "iteration_binding_required"
                            for s in self.report(rows, edges, None)["segments"]))
        del coordinates["call-4"]
        item = next(s for s in self.report(rows, edges, coordinates)["segments"] if s["iteration"] == 7)
        self.assertEqual(item["comparison_status"], "missing_or_ambiguous_previous_protocol")
        self.assertFalse(item["is_slow"])

    def test_sender_clock_offset_does_not_change_protocol_detection(self):
        rows, edges, coordinates = capture()
        expected = self.report(rows, edges, coordinates)
        for row in rows:
            if row["_node_id"] == "sender":
                row["_start_order"] += Decimal("1700000000000000.123")
                row["_stop_order"] += Decimal("1700000000000000.123")
        actual = self.report(rows, edges, coordinates)
        self.assertEqual([(s["is_slow"], s["protocol_duration_ns"]) for s in actual["segments"]],
                         [(s["is_slow"], s["protocol_duration_ns"]) for s in expected["segments"]])

    def test_compares_direct_operation_and_reported_bandwidth_proxy_separately(self):
        rows, edges, coordinates = capture()
        metadata, changes, operations = [], [], []
        for iteration in range(8):
            metadata.append(dict(graph_id="payload-" + str(iteration), node_id="sender", src_rank=1, dst_rank=3,
                rdma_type="RDMA_SEND_PAYLOAD", bandwidth_derived_duration_ns="200000" if iteration == 7 else "20000"))
            changes.append(dict(graph_id="payload-" + str(iteration), reference_count=5 if iteration >= 5 else 0,
                reference_graph_ids=["payload-" + str(i) for i in range(iteration - 5, iteration)] if iteration >= 5 else []))
            operations.append(dict(node_id="receiver", device_id=3, operation_scope="call-" + str(iteration),
                                   duration_ns="200000" if iteration == 7 else "20000"))
        report = self.report(rows, edges, coordinates, communication_tasks=metadata,
                             operations=operations, rolling_report=dict(tasks=changes))
        self.assertEqual(report["summary"]["reported_bandwidth_proxy_slow_count"], 1)
        self.assertEqual(report["summary"]["direct_operation_slow_count"], 1)
        self.assertEqual(report["communication_tasks"][-1]["node_pair_status"], "cross_node")

    def test_profiler_rank_numbers_without_semantic_endpoints_do_not_classify_nodes(self):
        rows, edges, coordinates = capture()
        for change in ({"src_rank": 0}, {"dst_rank": 1}, {"graph_id": "missing"}):
            with self.subTest(change=change):
                metadata = dict(graph_id="payload-7", node_id="sender", src_rank=1, dst_rank=3,
                                rdma_type="RDMA_SEND_PAYLOAD", bandwidth_derived_duration_ns=None)
                metadata.update(change)
                report = self.report(rows, edges, coordinates, communication_tasks=[metadata])
                item, = report["communication_tasks"]
                self.assertEqual(item["rank_mapping_status"], "unverified_profiler_ranks")
                self.assertEqual(item["node_pair_status"], "unknown_rank_mapping")

    def test_direct_details_bind_by_exact_physical_id_and_exports_keep_precision(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            db_path = root / "msprof_fixture.db"
            create_msprof_db(db_path)
            with sqlite3.connect(db_path) as db:
                for field, kind in (("transportType", "INTEGER"), ("rdmaType", "INTEGER"), ("size", "INTEGER"), ("bandwidth", "NUMERIC")):
                    db.execute("ALTER TABLE COMMUNICATION_TASK_INFO ADD COLUMN {} {}".format(field, kind))
                db.executescript("CREATE TABLE ENUM_HCCL_TRANSPORT_TYPE(id INTEGER,value TEXT);"
                    "INSERT INTO ENUM_HCCL_TRANSPORT_TYPE VALUES(1,'RDMA');"
                    "CREATE TABLE ENUM_HCCL_RDMA_TYPE(id INTEGER,value TEXT);"
                    "INSERT INTO ENUM_HCCL_RDMA_TYPE VALUES(1,'RDMA_SEND_PAYLOAD');"
                    "UPDATE COMMUNICATION_TASK_INFO SET transportType=1,rdmaType=1,size=2097152,bandwidth=41943040;")
            details = parse_communication_details(str(db_path), "run/node0")
            self.assertTrue(details)
            self.assertTrue(all(Decimal(row["bandwidth_derived_duration_ns"]) == 50000000 for row in details))
            self.assertTrue(all(row["hardware_completion_ns"] is None for row in details))
            with sqlite3.connect(db_path) as db:
                db.execute("UPDATE COMMUNICATION_TASK_INFO SET bandwidth=0")
            self.assertTrue(all(row["bandwidth_derived_duration_ns"] is None
                                for row in parse_communication_details(str(db_path), "run/node0")))

    def test_display_protocols_are_not_execution_tasks_or_new_edges(self):
        rows, edges, coordinates = capture()
        report = self.report(rows, edges, coordinates)
        displays = cross.display_rows(report, rows)
        self.assertEqual(len(displays), 8)
        self.assertTrue(all(row["_node_kind"] == "protocol" and row["_stream_id"] == -3 for row in displays))
        self.assertTrue(all(row["_graph_id"] not in {r["_graph_id"] for r in rows} for row in displays))
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary) / "report"
            cross.export_report(report, directory, execution_link=False)
            self.assertEqual(json.loads((directory / "report.json").read_text())["summary"]["slow_protocol_count"], 1)
            self.assertNotIn("../execution.html", (directory / "index.html").read_text())


if __name__ == "__main__":
    unittest.main()
