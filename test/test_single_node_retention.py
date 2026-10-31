from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from test import single_node_retention as retention
from test.single_node_retention import build_excerpt
from hccl.tools.diagnosis import rolling_diagnosis as rolling
from hccl.tools.diagnosis import visualize_html as view
from hccl.tools.diagnosis.test_rolling_diagnosis import repeated
from hccl.tools.diagnosis.test_source_events import capture
from hccl.tools.diagnosis.test_diagnosis import dependency_edge


class RetentionTests(unittest.TestCase):
    def test_retention_keeps_intermediate_call_outside_injection_context(self):
        rows, _, _, _ = capture()
        source, record, wait = deepcopy(rows[:3])
        middle = deepcopy(source)
        for row, key, scope, start, stop in ((source, "source", "a", 0, 100), (middle, "middle", "b", 100000, 100001),
                                             (record, "record", "c", 200001, 200002), (wait, "wait", "c", 199990, 200003)):
            row.update(_graph_id=key, _operation_scope=scope, _start=start, _stop=stop, _duration=stop-start,
                       _start_order=retention.Decimal(start), _stop_order=retention.Decimal(stop))
        rows = [source, middle, record, wait]
        edges = [dependency_edge("direct_stream_order_observed", "source", "middle", "a-b"),
                 dependency_edge("direct_stream_order_observed", "middle", "record", "b-c"),
                 dependency_edge("direct_notify_sync_exact", "record", "wait", "sync")]
        coords = [dict(operation_scope=scope, stage="measured", iteration=5, block=0, bucket=i) for i, scope in enumerate(("a", "b", "c"))]
        root = dict(root_id="root", graph_id="source", operation_scope="a", component="execution",
                    evidence_paths={"wait": ["a-b", "b-c", "sync"]})
        report = dict(primary_source_candidate_id="root", root_causes=[root])
        diagnosis = dict(schema_version=1, waits=view.build_wait_inventory(rows, edges), candidates=[])
        case = dict(case_id="synthetic-cross-call", injection=dict(kind="copy_contention", iteration=5, block=0, bucket=0))
        windows = [dict(node_id="run/node0", target_ranks=[0], start_ns=0, stop_ns=100000)]
        model, _ = build_excerpt(rows, edges, [], coords, report, diagnosis, case, windows)
        self.assertEqual({e["id"] for e in model["edges"]}, {"a-b", "b-c", "sync"})
        self.assertIn("middle", {n["id"] for n in model["nodes"]})

    def test_diagnosed_host_interval_is_an_annotation_not_a_fabricated_task(self):
        rows, edges, coords, preparations = capture(host_delay=True)
        report = rolling.analyze(rows, edges, coords, preparations=preparations)
        self.assertIsNone(report["primary_source_candidate_id"])
        primary = next(r for r in report["root_causes"] if r["root_id"] == report["primary_external_clue_id"])
        case = dict(case_id="synthetic-host", injection=dict(kind="progress_delay", iteration=5, block=0, bucket=0))
        windows = [dict(node_id="run/node0", target_ranks=[0], start_ns=primary["observed_start_ns"], stop_ns=primary["observed_stop_ns"])]
        diagnosis = dict(schema_version=1, waits=view.build_wait_inventory(rows, edges), candidates=[])
        model, summary = build_excerpt(rows, edges, [], list(coords.values()), report, diagnosis, case, windows)
        self.assertIsNone(summary["primary_source"])
        self.assertEqual(summary["primary_external_clue"]["root_id"], primary["root_id"])
        self.assertEqual(model["observedHostSource"]["durationUs"], 100)
        self.assertEqual(model["observedHostSource"]["rank"], 0)
        self.assertEqual(model["observedHostSource"]["startUs"], (primary["observed_start_ns"] - summary["chart_origin_ns"]) / 1000)
        self.assertFalse(any(n["taskKind"] == "host_interval" for n in model["nodes"]))

    def fixture(self):
        rows, edges, coordinates = repeated((1,) * 29 + (2,))
        for row in rows:
            row["_node_id"] = "capture/node0"
        for edge in edges:
            if "notify_sync" in edge["kind"]:
                edge.update(kind="direct_notify_sync_exact", confidence="exact")
        report = rolling.analyze(rows, edges, coordinates)
        primary = next(r for r in report["root_causes"] if r["root_id"] == report["primary_source_candidate_id"])
        waits = view.build_wait_inventory(rows, edges)
        candidates = [dict(r, id=r["root_id"], category=r["component"], evidence=r["reason"])
                      for r in report["root_causes"] if r["status"] == "dependency_supported_candidate"]
        diagnosis = dict(schema_version=1, waits=waits, candidates=candidates)
        window = dict(node_id="capture/node0", target_ranks=[primary["user_rank"]],
                      start_ns=primary["observed_start_ns"], stop_ns=primary["observed_stop_ns"])
        case = dict(case_id="synthetic", injection=dict(kind="copy_contention", iteration=29, block=0, bucket=0))
        return rows, edges, list(coordinates.values()), report, diagnosis, case, [window]

    def test_excerpt_keeps_real_edges_and_truth_does_not_change_source(self):
        args = self.fixture()
        before = deepcopy(args[3])
        model, summary = build_excerpt(args[0], args[1], [], *args[2:])
        self.assertEqual(args[3], before)
        self.assertEqual(model["initialSelection"], summary["primary_source"]["graph_id"])
        original = {e["edge_id"]: (e["src"], e["dst"]) for e in args[1]}
        self.assertTrue(model["edges"])
        self.assertTrue(all(original[e["id"]] == (e["src"], e["dst"]) for e in model["edges"]))
        self.assertFalse(summary["complete_workload_graph"])
        location, = summary["injection_locations"]
        self.assertTrue(location["anchor_collective_stream_ids"])
        self.assertEqual(location["rank"], args[-1][0]["target_ranks"][0])
        self.assertIn("0 = first retained", model["caseNote"])

    def test_normal_has_no_injection_location_and_uses_fixed_measured_context(self):
        args = list(self.fixture())
        args[-2] = dict(case_id="normal", injection=dict(kind="normal"))
        args[-1] = []
        _, summary = build_excerpt(args[0], args[1], [], *args[2:])
        self.assertEqual(summary["injection_locations"], [])
        self.assertEqual(summary["baseline_display_iteration"], 25)

    def test_unresolved_source_still_retains_real_dependency_excerpt(self):
        args = self.fixture()
        args[3]["primary_source_candidate_id"] = None
        args[4]["candidates"] = []
        model, summary = build_excerpt(args[0], args[1], [], *args[2:])
        self.assertIsNone(summary["primary_source"])
        self.assertIsNone(model["caseInfo"]["primary_source_candidate_id"])
        self.assertTrue(model["edges"])
        self.assertTrue(summary["injection_locations"])

    def test_multiple_clock_domains_are_rejected(self):
        args = self.fixture()
        args[0][0]["_node_id"] = "another-node"
        with self.assertRaisesRegex(ValueError, "clock"):
            build_excerpt(args[0], args[1], [], *args[2:])

    def persisted(self, root, normal=False):
        rows, edges, coordinates, report, diagnosis, case, windows = self.fixture()
        if normal:
            case["injection"] = dict(kind="normal")
            windows = []
        directory = (root / "attempt").resolve()
        directory.mkdir()
        for name in ("private", "msprof", "ascend_log", "foreground-dbs", "diagnosis/rolling"):
            (directory / name).mkdir(parents=True)
        (directory / "foreground-dbs/msprof_fixture.db").write_bytes(b"synthetic fixture, not a captured DB")
        (root / "outside.txt").write_text("must not change")
        diagnosis_dir = directory / "diagnosis"
        records = {"runner.json": dict(output=str(directory)),
                   "result.json": dict(execution_success=True, strict_diagnosis_success=True,
                                       diagnosis_directory=str(diagnosis_dir), temporal_evaluation=dict(diagnosis_success=False)),
                   "private/case.json": case, "private/actual-windows.json": windows,
                   "iteration-map.json": dict(operations=coordinates), "diagnosis/rolling/report.json": report,
                   "diagnosis/diagnosis.json": diagnosis, "diagnosis/pipeline_result.json": dict(status="passed")}
        for name, data in records.items():
            (directory / name).write_text(json.dumps(data))
        for name in ("merge_summary.csv", "dep_graph_summary.csv"):
            (diagnosis_dir / name).write_text("metric,value\nsynthetic,1\n")
        return directory, rows, edges

    def test_cleanup_keeps_html_small_evidence_and_baseline_raw(self):
        for normal in (False, True):
            with self.subTest(normal=normal), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                directory, rows, edges = self.persisted(root, normal)
                with patch.object(retention.graph, "read_graph_artifact_nodes", return_value=rows), \
                     patch.object(retention.graph, "read_graph_artifact_edges", return_value=edges), \
                     patch.object(retention.view, "read_operation_timings", return_value=[]):
                    summary = retention.retain_case(directory)
                self.assertTrue((directory / "retained/dependency.html").is_file())
                self.assertTrue((directory / "retained/case-summary.json").is_file())
                self.assertEqual((root / "outside.txt").read_text(), "must not change")
                self.assertTrue(summary["source_input_sha256"])
                for name in ("msprof", "ascend_log", "foreground-dbs", "diagnosis"):
                    self.assertEqual((directory / name).exists(), normal)

    def test_symlink_raw_directory_prevents_all_cleanup(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            directory, rows, edges = self.persisted(root)
            (directory / "msprof").rmdir()
            (directory / "msprof").symlink_to(root, target_is_directory=True)
            with patch.object(retention.graph, "read_graph_artifact_nodes", return_value=rows), \
                 patch.object(retention.graph, "read_graph_artifact_edges", return_value=edges), \
                 patch.object(retention.view, "read_operation_timings", return_value=[]):
                with self.assertRaisesRegex(ValueError, "cleanup"):
                    retention.retain_case(directory)
            self.assertTrue((directory / "diagnosis").is_dir())
            self.assertTrue((directory / "foreground-dbs").is_dir())
            self.assertEqual((root / "outside.txt").read_text(), "must not change")

    def test_compact_cleanup_keeps_propagation_evidence_without_a_second_html(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory,rows,edges=self.persisted(Path(temporary))
            source=directory/"diagnosis/propagation"
            source.mkdir()
            for name in ("report.json","chains.csv","steps.csv","chains.md","index.html"):
                (source/name).write_text("synthetic propagation "+name)
            with patch.object(retention.graph,"read_graph_artifact_nodes",return_value=rows), \
                 patch.object(retention.graph,"read_graph_artifact_edges",return_value=edges), \
                 patch.object(retention.view,"read_operation_timings",return_value=[]):
                summary=retention.retain_case(directory)
            self.assertEqual(len(summary["propagation_files"]),4)
            self.assertEqual((directory/"retained/propagation-report.json").read_text(),"synthetic propagation report.json")
            self.assertFalse((directory/"diagnosis").exists())
            self.assertEqual(len(list((directory/"retained").glob("*.html"))),1)
