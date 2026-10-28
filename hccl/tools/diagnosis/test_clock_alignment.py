from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest

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
