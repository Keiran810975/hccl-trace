from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from fractions import Fraction
from unittest.mock import patch

from . import clock_alignment as clock
from .multi_node_trace import load_manifest
from .run_diagnosis import run_pipeline
from .test_multi_node_trace import create_run_fixture
from . import visualize_dependency_graph as graph
from . import visualize_html as view


def calibrated_fixture(root):
    path, manifest = create_run_fixture(root)
    for index, node in enumerate(manifest["nodes"]):
        folder = root / node["msprof_db_dir"]
        with sqlite3.connect(folder / "msprof_fixture.db") as db:
            db.execute("CREATE TABLE SESSION_TIME_INFO(startTimeNs INTEGER,endTimeNs INTEGER)")
            if index == 0:
                db.execute("INSERT INTO SESSION_TIME_INFO VALUES(100000,110000)")
            else:
                db.execute("UPDATE TASK SET startNs=startNs+1000,endNs=endNs+1000")
                db.execute("INSERT INTO SESSION_TIME_INFO VALUES(0,10000)")
        (folder / "host").mkdir()
        raw = 100000 if index == 0 else 200000
        epoch = 100000 if index == 0 else 0
        (folder / "host/start_info").write_text(json.dumps(dict(collectionTimeBegin=str(epoch // 1000), clockMonotonicRaw=str(raw))))
        (folder / "host/end_info").write_text(json.dumps(dict(collectionTimeEnd=str((epoch + 10000) // 1000), clockMonotonicRaw=str(raw + 10000))))
        probe = dict(schema_version=1, clock="CLOCK_MONOTONIC_RAW", capture_id="independent-fixture",
                     node_id=node["node_id"], reference_node="node0")
        if index == 0:
            probe.update(before_raw_ns=90000, after_raw_ns=130000)
        else:
            for name, base in (("before", 190000), ("after", 220000)):
                probe[name] = [dict(local_send_ns=base + j * 10, local_recv_ns=base + j * 10 + 100,
                    reference_recv_ns=base + j * 10 - 100000 + 40,
                    reference_send_ns=base + j * 10 - 100000 + 60) for j in range(4)]
        evidence = root / node["node_id"] / "clock-probes.json"
        evidence.write_text(json.dumps(probe))
        node["clock_probe_files"] = [str(evidence)]
    path.write_text(json.dumps(manifest))
    return path


class ClockAlignmentTests(unittest.TestCase):
    def long_clock(self, root, *, jump=False):
        folder = root / "db"
        (folder / "host").mkdir(parents=True)
        p0, duration, r0 = 1000000000000, 40000000000, 100000000
        r1 = r0 + duration + 1500000
        with sqlite3.connect(folder / "msprof_fixture.db") as db:
            db.execute("CREATE TABLE TASK(deviceId INTEGER)")
            db.execute("INSERT INTO TASK VALUES(7)")
            db.execute("CREATE TABLE SESSION_TIME_INFO(startTimeNs INTEGER,endTimeNs INTEGER)")
            db.execute("INSERT INTO SESSION_TIME_INFO VALUES(?,?)", (p0, p0 + duration))
        (folder / "host/start_info").write_text(json.dumps(dict(collectionTimeBegin=p0 // 1000, clockMonotonicRaw=r0)))
        (folder / "host/end_info").write_text(json.dumps(dict(collectionTimeEnd=(p0 + duration) // 1000, clockMonotonicRaw=r1)))
        probe = root / "probe.json"
        probe.write_text(json.dumps(dict(schema_version=1, clock="CLOCK_MONOTONIC_RAW", capture_id="long", node_id="node0",
            reference_node="node0", before_raw_ns=r0 - 10000, after_raw_ns=r1 + 10000)))
        samples = root / "clocks.jsonl"
        header = dict(event="runtime", schema_version=1, run_id="long", node_id="node0", user_rank=11, device_id=7)
        records = [header]
        for i in range(1, 40):
            p = p0 + i * 1000000000
            r = r0 + round(Fraction(i * 1000000000 * (r1 - r0), duration))
            if jump and i == 20:
                r += 2000000
            records.append(dict(event="call", before=dict(unix_ns=p, raw_ns=r)))
        samples.write_text("\n".join(map(json.dumps, records)))
        manifest = dict(run_id="long", ranks=[dict(node_id="node0", user_rank=11, device_id=7)],
            nodes=[dict(node_id="node0", plog_dir=str(root / "plog"), msprof_db_dir=str(folder),
                        clock_probe_files=[str(probe)], clock_validation_files=[str(samples)])])
        return manifest, p0, duration, r0, r1

    def test_realtime_drift_does_not_rescale_cann_db_event_time(self):
        with tempfile.TemporaryDirectory() as directory:
            manifest, p0, duration, r0, r1 = self.long_clock(Path(directory))
            report = clock.build(manifest)
            self.assertEqual(report["schema_version"], 3)
            self.assertLessEqual(report["estimated_error_ns"], 1001)
            model = next(iter(clock.models_from_report(report).values()))
            self.assertEqual(model.map_ns(p0), r0)
            self.assertEqual(model.map_ns(p0 + duration), r0 + duration)
            self.assertEqual(model.map_ns(p0 + r1 - r0), r1)
            self.assertEqual(report["profiler_calibrations"][0]["model"], "cann_start_offset")
            self.assertEqual(report["profiler_calibrations"][0]["realtime_offset_change_ns"], -1500000)
            manifest["nodes"][0]["clock_validation_files"] = []
            self.assertEqual(clock.build(manifest)["models"], report["models"])

    def test_public_realtime_disagreement_is_audited_not_applied_to_db(self):
        with tempfile.TemporaryDirectory() as directory:
            manifest, p0, _, r0, _ = self.long_clock(Path(directory), jump=True)
            report = clock.build(manifest)
            self.assertGreater(report["profiler_calibrations"][0]["max_public_realtime_offset_change_ns"], 2000000)
            model = next(iter(clock.models_from_report(report).values()))
            self.assertEqual(model.map_ns(p0 + 20000000000), r0 + 20000000000)

    def test_original_failed_call_boundary_is_exact_with_start_offset(self):
        start = dict(collectionTimeBegin=1793385338476754, clockMonotonicRaw=189447326123510)
        stop = dict(collectionTimeEnd=1793385377336754, clockMonotonicRaw=189486184584970)
        raw = 189476639218840
        expected = raw + 1793385338476754000 - 189447326123510
        self.assertEqual(clock.raw_to_profiler(raw, start, stop), expected)
        with self.assertRaisesRegex(ValueError, "coverage"):
            clock.raw_to_profiler(189486184584971, start, stop)

    def test_retired_realtime_affine_artifact_requires_offline_replay(self):
        with tempfile.TemporaryDirectory() as temporary:
            report = clock.build(load_manifest(calibrated_fixture(Path(temporary))))
            report["schema_version"] = 2
            report["models"][0].update(profiler_anchor_ns=100000, profiler_stop_ns=110000,
                                       profiler_rate_numerator=99999, profiler_rate_denominator=100000)
            with self.assertRaisesRegex(ValueError, "retired realtime-affine"):
                clock.models_from_report(report)

    def test_explicit_uncalibrated_fallback_keeps_execution_gates_and_marks_the_axis(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = calibrated_fixture(root)
            manifest = json.loads(path.read_text())
            probe = Path(manifest["nodes"][1]["clock_probe_files"][0])
            data = json.loads(probe.read_text())
            data["after"] = data["before"]
            probe.write_text(json.dumps(data))
            out, ready = run_pipeline(path, root / "local", allow_uncalibrated_clock=True,
                                      html_views=(), include_critical_path=False)
            self.assertTrue(ready)
            result = json.loads((out / "pipeline_result.json").read_text())
            self.assertFalse(result["clock_alignment_available"])
            self.assertTrue(result["clock_alignment_error"])
            self.assertFalse((out / "clock_alignment.json").exists())
            with patch("hccl.tools.diagnosis.multi_node_trace.operation_sync_connected", return_value=False):
                _, ready = run_pipeline(path, root / "bad-graph", allow_uncalibrated_clock=True, html_views=())
                self.assertFalse(ready)

    def test_independent_probes_map_clocks_without_changing_raw_graph(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            path = calibrated_fixture(root)
            directory, ready = run_pipeline(path, root / "out", require_clock_alignment=True)
            self.assertTrue(ready)
            report = json.loads((directory / "clock_alignment.json").read_text())
            models = clock.models_from_report(report)
            self.assertEqual(models[("fixture/node0", 6)].map_ns(102000),
                             models[("fixture/node1", 2)].map_ns(2000))
            rows = graph.read_graph_artifact_nodes(directory / "dep_graph_nodes.csv")
            edges = graph.read_graph_artifact_edges(directory / "dep_graph_edges.csv")
            raw = deepcopy((rows, edges))
            model = view.build_execution_dependency_model(rows, edges, alignment=report)
            self.assertIn("Estimated aligned", model["clockLabel"])
            sender = next(n for n in model["nodes"] if n["nodeId"].endswith("node0") and n["taskId"] == 1)
            receiver = next(n for n in model["nodes"] if n["nodeId"].endswith("node1") and n["taskId"] == 1)
            self.assertEqual(receiver["relativeStart"] - sender["relativeStart"], 1)
            self.assertEqual((rows, edges), raw)

    def test_old_capture_is_not_aligned_by_first_task_or_operation(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            path, _ = create_run_fixture(root)
            directory, ready = run_pipeline(path, root / "out", require_clock_alignment=True, html_views=())
            self.assertFalse(ready)
            result = json.loads((directory / "pipeline_result.json").read_text())
            self.assertEqual(result["status"], "incomplete")
            self.assertFalse(result["clock_alignment_available"])

    def test_rejects_unrelated_stale_incomplete_or_imprecise_calibration(self):
        for failure in ("session", "capture", "partial", "tolerance", "clock_order"):
            with self.subTest(failure=failure), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                path = calibrated_fixture(root)
                manifest = load_manifest(path)
                probe = Path(manifest["nodes"][1]["clock_probe_files"][0])
                data = json.loads(probe.read_text())
                if failure == "session":
                    data["after"] = data["before"]
                elif failure == "capture":
                    data["capture_id"] = "other-run"
                elif failure == "partial":
                    del manifest["nodes"][1]["clock_probe_files"]
                elif failure == "clock_order":
                    data["before"][0]["reference_send_ns"] = data["before"][0]["reference_recv_ns"] - 1
                probe.write_text(json.dumps(data))
                with self.assertRaises(ValueError):
                    clock.build(manifest, max_error_ns=500 if failure == "tolerance" else 1000000)

    def test_mapping_refuses_extrapolation_and_invalid_models(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            report = clock.build(load_manifest(calibrated_fixture(root)))
            model = next(iter(clock.models_from_report(report).values()))
            with self.assertRaises(ValueError):
                model.map_ns(-1000000)
            report["models"][0]["rate_denominator"] = 0
            with self.assertRaises(ValueError):
                clock.models_from_report(report)


if __name__ == "__main__":
    unittest.main()
