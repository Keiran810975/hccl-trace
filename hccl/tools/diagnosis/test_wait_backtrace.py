from __future__ import annotations

from copy import deepcopy
from decimal import Decimal
import json
from pathlib import Path
import tempfile
import unittest

from . import rolling_diagnosis as rolling
from .test_source_events import capture


def cross_call_capture():
    rows, edges, coordinates, _ = capture(execution_delay=True)
    coords = []
    for i in range(6):
        for bucket in (0, 1):
            coords.append(dict(operation_scope="op-{}-{}".format(i, bucket), stage="measured", iteration=i,
                               block=0, bucket=bucket, evidence="fixture: two independently bound calls"))
        for row in rows[i * 4:(i + 1) * 4]:
            row["_operation_scope"] = "op-{}-{}".format(i, 0 if row["_graph_id"].endswith("p0") else 1)
    return rows, edges, rolling.validate_coordinates(coords)


class WaitBacktraceTests(unittest.TestCase):
    def test_cross_call_order_is_kept_without_creating_an_edge(self):
        rows, edges, coords = cross_call_capture()
        before = deepcopy(edges)
        report = rolling.analyze(rows, edges, coords)
        root = next(r for r in report["root_causes"] if r["root_id"] == report["primary_source_candidate_id"])
        self.assertEqual(root["graph_id"], "i5p0")
        self.assertEqual(root["operation_scope"], "op-5-0")
        self.assertEqual(root["evidence_paths"]["i5p2"], ["i5e0", "i5e1"])
        self.assertEqual(edges, before)
        trace = next(t for t in report["wait_backtraces"] if t["wait_graph_id"] == "i5p2")
        self.assertEqual(trace["status"], "source_candidates_found")

    def test_cross_call_focus_keeps_real_source_and_wait_endpoints(self):
        rows, edges, coords = cross_call_capture()
        options = rolling.RollingOptions(max_figures=1)
        report = rolling.analyze(rows, edges, coords, options)
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "report"
            rolling.export_report(report, rows, edges, output, options)
            page = (output / "focus-001-current.html").read_text()
            model = json.JSONDecoder().raw_decode(page.split("const model=", 1)[1])[0]
            self.assertTrue(model["multipleOperationScopes"])
            self.assertTrue({"i5p0", "i5p2"} <= {n["id"] for n in model["nodes"]})

    def test_normal_execution_that_starts_late_is_not_the_root(self):
        rows, edges, coords, _ = capture(execution_delay=True)
        for i in range(6):
            source, record, wait, tail = rows[i * 4:(i + 1) * 4]
            middle = deepcopy(source)
            middle.update(_graph_id="middle-{}".format(i), _task_id=100 + i, event="forward_copy",
                          _start_order=Decimal(str(source["_stop"])), _stop_order=Decimal(str(source["_stop"])) + 1,
                          _start=source["_stop"], _stop=source["_stop"] + 1, _duration=1)
            for row in (record, tail):
                for key in ("_start", "_stop"):
                    row[key] += 1
                row["_start_order"] += 1
                row["_stop_order"] += 1
            wait["_stop"] += 1
            wait["_stop_order"] += 1
            wait["_duration"] += 1
            rows.append(middle)
            old = next(e for e in edges if e["edge_id"] == "i{}e0".format(i))
            old["dst"] = middle["_graph_id"]
            edges.append(dict(old, src=middle["_graph_id"], dst=record["_graph_id"], edge_id="middle-record-{}".format(i)))
        report = rolling.analyze(rows, edges, coords)
        middle = next(t for t in report["tasks"] if t["graph_id"] == "middle-5")
        self.assertTrue(middle["start_late"])
        self.assertFalse(middle["duration_slow"])
        root = next(r for r in report["root_causes"] if r["root_id"] == report["primary_source_candidate_id"])
        self.assertEqual(root["graph_id"], "i5p0")
        self.assertIn("middle-record-5", root["evidence_paths"]["i5p2"])

    def test_signal_already_recorded_stops_at_residual_wait_boundary(self):
        rows, edges, coords, _ = capture(execution_delay=True)
        wait = next(r for r in rows if r["_graph_id"] == "i5p2")
        wait.update(_start=5050, _stop=5100, _duration=50, _start_order=Decimal(5050), _stop_order=Decimal(5100))
        tail = next(r for r in rows if r["_graph_id"] == "i5p3")
        tail.update(_start=5100, _stop=5100.2, _duration=.2, _start_order=Decimal(5100), _stop_order=Decimal("5100.2"))
        report = rolling.analyze(rows, edges, coords)
        self.assertIsNone(report["primary_source_candidate_id"])
        self.assertGreater(report["coverage"]["boundary_reason_counts"]["signal_precedes_wait_start"], 0)

    def test_incompatible_notify_time_is_not_repaired(self):
        rows, edges, coords, _ = capture(execution_delay=True)
        record = next(r for r in rows if r["_graph_id"] == "i5p1")
        record.update(_start=5044, _stop=5045, _duration=1, _start_order=Decimal(5044), _stop_order=Decimal(5045))
        report = rolling.analyze(rows, edges, coords)
        self.assertIsNone(report["primary_source_candidate_id"])
        self.assertIn("incompatible_notify_timestamps", report["coverage"]["boundary_reason_counts"])

    def test_incompatible_stream_order_is_not_traversed(self):
        rows, edges, coords, _ = capture(execution_delay=True)
        record = next(r for r in rows if r["_graph_id"] == "i5p1")
        record.update(_start=5042, _stop=5042.001, _duration=.001,
                      _start_order=Decimal(5042), _stop_order=Decimal("5042.001"))
        report = rolling.analyze(rows, edges, coords)
        self.assertIsNone(report["primary_source_candidate_id"])
        self.assertIn("incompatible_stream_order_timestamps", report["coverage"]["boundary_reason_counts"])

    def test_tied_slow_paths_keep_both_sources_when_single_task_gain_is_zero(self):
        rows, edges, coords, _ = capture(execution_delay=True)
        extra_rows = []
        for row in rows:
            copy = deepcopy(row)
            copy.update(_graph_id=row["_graph_id"] + "b", _user_rank=row["_user_rank"] + 2, _device_id=row["_device_id"] + 2)
            extra_rows.append(copy)
        rows.extend(extra_rows)
        edges.extend(dict(e, src=e["src"] + "b", dst=e["dst"] + "b", edge_id=e["edge_id"] + "b") for e in list(edges))
        report = rolling.analyze(rows, edges, coords)
        sources = [r for r in report["root_causes"] if r["primary_eligible"]]
        self.assertEqual({r["graph_id"] for r in sources}, {"i5p0", "i5p0b"})
        self.assertTrue(all(r["modeled_execution_gain_ns"] == 0 for r in sources))

    def test_ambiguous_notify_producers_stay_a_boundary(self):
        rows, edges, coords, _ = capture(execution_delay=True)
        for i in range(6):
            extra = deepcopy(next(r for r in rows if r["_graph_id"] == "i{}p1".format(i)))
            extra.update(_graph_id="extra-record-{}".format(i), _stream_id=99, _task_id=999 + i, event="other_record")
            rows.append(extra)
        edges.append(dict(next(e for e in edges if e["edge_id"] == "i5e1"), src="extra-record-5", edge_id="ambiguous"))
        report = rolling.analyze(rows, edges, coords)
        self.assertIsNone(report["primary_source_candidate_id"])
        self.assertIn("ambiguous_notify_producers", report["coverage"]["boundary_reason_counts"])

    def test_traversal_limit_is_explicit_and_does_not_claim_a_source(self):
        rows, edges, coords, _ = capture(execution_delay=True)
        report = rolling.analyze(rows, edges, coords, rolling.RollingOptions(traversal_limit=1))
        self.assertIsNone(report["primary_source_candidate_id"])
        self.assertGreater(report["coverage"]["truncated_wait_backtrace_count"], 0)

    def test_coverage_separates_missing_semantics_from_healthy_tasks(self):
        rows, edges, coords, _ = capture(execution_delay=True)
        next(r for r in rows if r["_graph_id"] == "i5p0")["algorithm"] = ""
        report = rolling.analyze(rows, edges, coords)
        self.assertIsNone(report["primary_source_candidate_id"])
        self.assertIn("unannotated_task_location", report["coverage"]["comparison_status_counts"])

    def test_remote_clock_is_not_subtracted(self):
        rows, edges, coords, _ = capture(execution_delay=True)
        for row in rows:
            if row["_user_rank"] == 0:
                row["_node_id"] = "remote/node0"
                row["_start_order"] += 1000000000
                row["_stop_order"] += 1000000000
                row["_start"] += 1000000000
                row["_stop"] += 1000000000
        for edge in edges:
            if "notify_sync" in edge["kind"]:
                edge.update(kind="cross_node_notify_sync_observed", confidence="observed")
        report = rolling.analyze(rows, edges, coords)
        self.assertIsNotNone(report["primary_source_candidate_id"])
        self.assertTrue(any(c["timing_status"] == "remote_clock_boundary" for t in report["wait_backtraces"] for c in t["release_checks"]))


if __name__ == "__main__":
    unittest.main()
