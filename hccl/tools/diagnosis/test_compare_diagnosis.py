"""Baseline comparison never guesses identity or promotes blocked waits to roots."""
from __future__ import annotations

from copy import deepcopy
from decimal import Decimal
import csv
import json
from pathlib import Path
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from diagnosis import compare_diagnosis as compare
    from diagnosis.test_diagnosis import execution_row, dependency_edge
else:
    from . import compare_diagnosis as compare
    from .test_diagnosis import execution_row, dependency_edge


def fixture():
    rows = []
    for index, (rank, kind, start, length, event) in enumerate((
        (0, "sdma", 100, 1000, "copy_start"),
        (0, "notify_record", 1100, 1, "tx_data_signal_start"),
        (1, "notify_wait", 110, 1000, "rx_data_signal_start"),
        (1, "sdma", 1110, 200, "rx_payload_copy"),
    )):
        row = execution_row(index, 45, index + 10, start, kind=kind, rank=rank, event=event)
        row.update(_node_id="run/node" + str(rank), _operation_scope="anomaly-op",
                   match_status="matched", semantic="fixture_hccl_semantics",
                   algorithm="ring", phase="allgather", step="0", slice="0",
                   profiler_size_bytes="67108864" if kind == "sdma" else "",
                   _stop=start + length, _duration=length)
        rows.append(row)
    edges = [dependency_edge("direct_stream_order_observed", "p0", "p1", "e0"),
             dependency_edge("cross_node_notify_sync_observed", "p1", "p2", "e1", "channel"),
             dependency_edge("direct_stream_order_observed", "p2", "p3", "e2")]
    baseline = deepcopy(rows)
    for index, row in enumerate(baseline):
        row.update(_graph_id="b" + str(index), _operation_scope="baseline-op",
                   _node_id="baseline/node" + str(row["_user_rank"]))
        if row["profiler_task_kind"] in ("sdma", "notify_wait"):
            row.update(_stop=row["_start"] + 10, _duration=10)
    baseline_edges = [dict(e, src="b" + e["src"][1:], dst="b" + e["dst"][1:], edge_id="b" + e["edge_id"]) for e in edges]
    return rows, edges, baseline, baseline_edges


class BaselineComparisonTests(unittest.TestCase):
    def test_increased_gap_is_not_reported_as_kernel_duration(self):
        rows, edges, baseline, baseline_edges = fixture()
        rows[0].update(_stop=110, _duration=10)
        rows[3].update(_stop=1120, _duration=10)
        baseline[1].update(_start=111, _stop=112)
        report = compare.analyze(rows, edges, baseline, baseline_edges=baseline_edges)
        root = next(r for r in report["root_causes"] if r["component"] == "pre_task_gap")
        self.assertEqual(root["graph_id"], "p1")
        self.assertEqual(root["component"], "pre_task_gap")
        self.assertEqual(root["status"], "unattributed_gap")
        self.assertIsNone(report["primary_source_candidate_id"])
        self.assertTrue(any(r["status"] == "unresolved_upstream" for r in report["root_causes"]))
        self.assertEqual(root["duration_ns"], 990000)
        self.assertEqual(root["delta_ns"], "989000")
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "comparison"
            compare.export_report(report, rows, edges, baseline, baseline_edges, output, compare.ComparisonOptions())
            svg = (output / root["comparison_page"].replace(".html", "-anomaly.svg")).read_text()
            self.assertIn('stroke-dasharray="4 3"', svg)

    def test_capture_start_is_not_an_inferred_gap(self):
        rows, edges, baseline, baseline_edges = fixture()
        self.assertNotIn("p0", compare.local_gaps(rows, edges))
        self.assertNotIn("p2", compare.local_gaps(rows, edges))

    def test_large_gap_is_not_hidden_by_smaller_upstream_slowdown(self):
        rows, edges, baseline, baseline_edges = fixture()
        rows[0].update(_stop=150, _duration=50)
        baseline[1].update(_start=111, _stop=112)
        report = compare.analyze(rows, edges, baseline, baseline_edges=baseline_edges)
        gap = next(r for r in report["root_causes"] if r["graph_id"] == "p1")
        self.assertEqual(gap["component"], "pre_task_gap")
        self.assertEqual(gap["upstream_slow_graph_ids"], ["p0"])
        self.assertEqual(gap["status"], "unattributed_gap")
        primary = next(r for r in report["root_causes"] if r["root_id"] == report["primary_source_candidate_id"])
        self.assertEqual((primary["graph_id"], primary["component"]), ("p0", "execution"))

    def test_gap_does_not_override_slow_execution_on_the_same_task(self):
        rows, edges, baseline, baseline_edges = fixture()
        for group, key, scope in ((rows, "p4", "anomaly-op"), (baseline, "b4", "baseline-op")):
            extra = deepcopy(group[0])
            extra.update(_graph_id=key, _operation_scope=scope, _task_id=40, event="prep_copy",
                         _start=0, _stop=10, _duration=10)
            group.append(extra)
        edges.append(dependency_edge("direct_stream_order_observed", "p4", "p0", "prep"))
        baseline_edges.append(dependency_edge("direct_stream_order_observed", "b4", "b0", "base-prep"))
        baseline[0].update(_start=11, _stop=21, _duration=10)
        report = compare.analyze(rows, edges, baseline, baseline_edges=baseline_edges)
        components = {r["component"]: r for r in report["root_causes"] if r["graph_id"] == "p0"}
        self.assertEqual(set(components), {"execution", "pre_task_gap"})
        self.assertEqual(components["execution"]["duration_ns"], 1000000)
        self.assertEqual(components["execution"]["status"], "dependency_supported_candidate")
        self.assertEqual(components["pre_task_gap"]["duration_ns"], 90000)
        self.assertEqual(components["pre_task_gap"]["status"], "unattributed_gap")
        self.assertEqual(report["primary_source_candidate_id"], components["execution"]["root_id"])

    def test_upstream_gap_and_wait_do_not_hide_independent_work_execution(self):
        rows, edges, baseline, baseline_edges = fixture()
        rows[0].update(_stop=110, _duration=10)
        baseline[1].update(_start=111, _stop=112)
        for group, prefix, record_start, wait_start, wait_length in (
                (rows, "p", 1311, 1100, 1000), (baseline, "b", 1121, 1115, 15)):
            record = deepcopy(group[1])
            record.update(_graph_id=prefix + "4", _node_id=group[2]["_node_id"], _user_rank=1,
                          _task_id=44, event="tail_record", _start=record_start, _stop=record_start + 1, _duration=1)
            wait = deepcopy(group[2])
            wait.update(_graph_id=prefix + "5", _node_id=group[0]["_node_id"], _user_rank=0,
                        _task_id=45, event="tail_wait", _start=wait_start, _stop=wait_start + wait_length, _duration=wait_length)
            group.extend((record, wait))
        for items, prefix in ((edges, "p"), (baseline_edges, "b")):
            items.extend((dependency_edge("direct_stream_order_observed", prefix + "3", prefix + "4", prefix + "tail-order"),
                          dependency_edge("cross_node_notify_sync_observed", prefix + "4", prefix + "5", prefix + "tail-sync", "tail-channel")))
        report = compare.analyze(rows, edges, baseline, baseline_edges=baseline_edges)
        source = next(r for r in report["root_causes"] if r["graph_id"] == "p3" and r["component"] == "execution")
        self.assertEqual(source["status"], "dependency_supported_candidate")
        self.assertEqual(source["evidence_paths"], {"p5": ["ptail-order", "ptail-sync"]})
        self.assertEqual(report["primary_source_candidate_id"], source["root_id"])

    def test_stream_order_to_wait_is_not_notification_producer_evidence(self):
        rows, edges, baseline, baseline_edges = fixture()
        for group in (rows, baseline):
            for row in group:
                row.update(_node_id=group[0]["_node_id"], _user_rank=0)
        edges[1].update(kind="direct_stream_order_observed", confidence="observed")
        baseline_edges[1].update(kind="direct_stream_order_observed", confidence="observed")
        report = compare.analyze(rows, edges, baseline, baseline_edges=baseline_edges)
        self.assertIsNone(report["primary_source_candidate_id"])
        source = next(r for r in report["root_causes"] if r["graph_id"] == "p0")
        self.assertEqual(source["status"], "isolated_slow_task")
        self.assertEqual(source["affected_wait_graph_ids"], [])

    def test_wait_gap_cannot_use_its_own_zero_edge_path_as_support(self):
        rows, edges, baseline, baseline_edges = fixture()
        rows[0].update(_stop=110, _duration=10)
        rows[3]["profiler_task_kind"] = baseline[3]["profiler_task_kind"] = "rdma"
        baseline[2].update(_start=2, _stop=3, _duration=1)
        for group, prefix in ((rows, "p"), (baseline, "b")):
            ready = deepcopy(group[2])
            ready.update(_graph_id=prefix + "4", _task_id=44, profiler_task_kind="notify_record",
                         event="ready_record", _start=0, _stop=1, _duration=1)
            group.append(ready)
        edges.append(dependency_edge("direct_stream_order_observed", "p4", "p2", "wait-order"))
        baseline_edges.append(dependency_edge("direct_stream_order_observed", "b4", "b2", "base-wait-order"))
        report = compare.analyze(rows, edges, baseline, baseline_edges=baseline_edges)
        gap = next(r for r in report["root_causes"] if r["graph_id"] == "p2" and r["component"] == "pre_task_gap")
        self.assertEqual(gap["status"], "unattributed_gap")
        self.assertEqual(gap["affected_wait_graph_ids"], [])
        self.assertEqual(gap["evidence_paths"], {})
        self.assertIsNone(report["primary_source_candidate_id"])

    def test_source_and_propagation_are_separate(self):
        rows, edges, baseline, _ = fixture()
        report = compare.analyze(rows, edges, baseline)
        self.assertEqual(report["slow_task_count"], 3)
        root, = report["root_causes"]
        self.assertEqual(root["graph_id"], "p0")
        self.assertEqual(root["status"], "dependency_supported_candidate")
        self.assertEqual(root["delta_ns"], "990000")
        self.assertEqual(root["evidence_paths"], {"p2": ["e0", "e1"]})
        self.assertEqual(next(t for t in report["tasks"] if t["graph_id"] == "p3")["role"], "downstream_slow_task")
        self.assertEqual(root["physical_cause"], "unknown")
        self.assertEqual(report["primary_source_candidate_id"], root["root_id"])

    def test_wait_only_does_not_become_proved_source(self):
        rows, edges, baseline, _ = fixture()
        for index in (0, 3):
            rows[index].update(_stop=rows[index]["_start"] + 10, _duration=10)
        report = compare.analyze(rows, edges, baseline)
        root, = report["root_causes"]
        self.assertEqual(root["status"], "unresolved_upstream")
        self.assertEqual(root["producer_graph_ids"], ["p1"])
        self.assertEqual(root["graph_id"], "p2")

    def test_no_change_produces_no_source(self):
        rows, edges, _, _ = fixture()
        report = compare.analyze(rows, edges, deepcopy(rows))
        self.assertEqual(report["slow_task_count"], 0)
        self.assertEqual(report["root_causes"], [])

    def test_node_clock_shifts_do_not_change_diagnosis(self):
        rows, edges, baseline, _ = fixture()
        before = compare.analyze(rows, edges, baseline)
        for row in rows:
            if row["_user_rank"] == 1:
                row["_start"] += 999999999
                row["_stop"] += 999999999
        self.assertEqual(before, compare.analyze(rows, edges, baseline))

    def test_different_sizes_or_shapes_are_not_paired(self):
        rows, edges, baseline, _ = fixture()
        baseline[0]["profiler_size_bytes"] = "1"
        report = compare.analyze(rows, edges, baseline)
        self.assertEqual(report["status"], "no_comparable_tasks")
        self.assertEqual(report["root_causes"], [])

    def test_evidenced_operation_map_is_not_task_identity(self):
        rows, edges, baseline, _ = fixture()
        pairs = [dict(current_scope="anomaly-op", baseline_scope="baseline-op", evidence="controlled call binding")]
        report = compare.analyze(rows, edges, baseline, operation_pairs=pairs)
        self.assertTrue(all(t["comparison_status"] == "explicit_operation_reference" for t in report["tasks"]))
        for bad in ([dict(pairs[0], evidence="")], pairs * 2,
                    [dict(pairs[0], baseline_scope="missing")]):
            with self.assertRaises(ValueError):
                compare.analyze(rows, edges, baseline, operation_pairs=bad)

    def test_median_reference_and_mad_guard_against_jitter(self):
        rows, edges, baseline, _ = fixture()
        extra = deepcopy(baseline)
        for row in extra:
            row["_graph_id"] += "-2"
            row["_operation_scope"] = "baseline-op-2"
            if row["profiler_task_kind"] in ("sdma", "notify_wait"):
                row.update(_stop=row["_start"] + 900, _duration=900)
        report = compare.analyze(rows, edges, baseline + extra)
        self.assertEqual(report["slow_task_count"], 0)
        self.assertEqual(report["tasks"][0]["baseline_median_ns"], "455000")
        self.assertEqual(report["tasks"][0]["baseline_mad_ns"], "445000")

    def test_unknown_operation_and_topology_are_not_hidden(self):
        rows, edges, baseline, _ = fixture()
        rows[0]["_operation_scope"] = ""
        report = compare.analyze(rows, edges, baseline)
        self.assertEqual(report["uncomparable_task_count"], 4)
        baseline[0]["_user_rank"] = 100
        with self.assertRaisesRegex(ValueError, "topology"):
            compare.analyze(rows, edges, baseline)

    def test_rdma_and_kernel_envelopes_are_not_payload_sources(self):
        for kind in ("rdma", "kernel_aicpu"):
            rows, edges, baseline, _ = fixture()
            rows[0]["profiler_task_kind"] = baseline[0]["profiler_task_kind"] = kind
            report = compare.analyze(rows, edges, baseline)
            self.assertFalse(any(r["graph_id"] == "p0" for r in report["root_causes"]))
            self.assertTrue(any(t["graph_id"] == "p0" and t["is_slow"] for t in report["tasks"]))

    def test_semantic_edges_do_not_prove_a_source_path(self):
        rows, edges, baseline, _ = fixture()
        edges[0].update(kind="ffts_logical_stream_order", confidence="semantic")
        report = compare.analyze(rows, edges, baseline)
        source = next(r for r in report["root_causes"] if r["graph_id"] == "p0")
        self.assertEqual(source["status"], "isolated_slow_task")

    def test_truncated_search_is_not_dependency_supported(self):
        rows, edges, baseline, _ = fixture()
        report = compare.analyze(rows, edges, baseline, compare.ComparisonOptions(traversal_limit=1))
        self.assertTrue(any(r["traversal_truncated"] for r in report["root_causes"]))

    def test_svg_html_and_structured_report_share_real_ids_and_scale(self):
        rows, edges, baseline, baseline_edges = fixture()
        report = compare.analyze(rows, edges, baseline)
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "comparison"
            compare.export_report(report, rows, edges, baseline, baseline_edges, output, compare.ComparisonOptions())
            saved = json.loads((output / "report.json").read_text())
            figure, = saved["figures"]
            self.assertEqual(figure["anomaly_graph_id"], "p0")
            self.assertEqual(figure["baseline_graph_id"], "b0")
            models = []
            for suffix in ("baseline", "anomaly"):
                svg = ET.parse(output / ("focus-001-" + suffix + ".svg"))
                self.assertIn("Operation-relative", ET.tostring(svg.getroot(), encoding="unicode"))
                page = (output / ("focus-001-" + suffix + ".html")).read_text()
                self.assertIn('"initialWindow":true', page)
                models.append(json.JSONDecoder().raw_decode(page.split("const model=", 1)[1])[0])
            self.assertEqual(models[0]["timeMax"], models[1]["timeMax"])
            self.assertEqual(models[0]["timeScale"], models[1]["timeScale"])
            self.assertGreaterEqual(models[1]["timeMax"], 1100)
            self.assertIn('"e0","e1"', (output / "focus-001-anomaly.html").read_text())
            self.assertTrue((output / "slow_tasks.csv").exists())
            with self.assertRaises(FileExistsError):
                compare.export_report(report, rows, edges, baseline, baseline_edges, output, compare.ComparisonOptions())

    def test_html_escapes_event_text(self):
        rows, edges, baseline, baseline_edges = fixture()
        rows[0]["phase"] = baseline[0]["phase"] = "<script>bad()</script>"
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "comparison"
            compare.export_report(compare.analyze(rows, edges, baseline), rows, edges, baseline, baseline_edges,
                                  output, compare.ComparisonOptions())
            self.assertNotIn("<script>bad()", (output / "index.html").read_text())
            self.assertIn("&lt;script&gt;", (output / "index.html").read_text())

    def test_mixed_source_csv_keeps_boundary_producer_fields(self):
        rows, edges, baseline, baseline_edges = fixture()
        edges = edges[1:]
        report = compare.analyze(rows, edges, baseline)
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "comparison"
            compare.export_report(report, rows, edges, baseline, baseline_edges, output, compare.ComparisonOptions())
            with (output / "root_causes.csv").open(newline="") as source:
                records = list(csv.DictReader(source))
            boundary = next(r for r in records if r["status"] == "unresolved_upstream")
            self.assertEqual(json.loads(boundary["producer_graph_ids"]), ["p1"])

    def test_thresholds_and_zero_baseline_are_finite(self):
        rows, edges, baseline, _ = fixture()
        baseline[0].update(_stop=baseline[0]["_start"], _duration=0)
        report = compare.analyze(rows, edges, baseline)
        self.assertTrue(report["tasks"][0]["is_slow"])
        self.assertIsNone(report["tasks"][0]["slowdown_factor"])
        for factor in ("NaN", "Infinity", "1", "0"):
            with self.assertRaises(ValueError):
                compare.analyze(rows, edges, baseline, compare.ComparisonOptions(slowdown_factor=factor))


if __name__ == "__main__":
    unittest.main()
