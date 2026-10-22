"""Four independent clock domains through the real replay/diagnosis entry point."""

from __future__ import annotations

import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
from unittest.mock import patch

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from diagnosis.run_diagnosis import run_pipeline
    from diagnosis.test_multi_node_trace import create_run_fixture
else:
    from .run_diagnosis import run_pipeline
    from .test_multi_node_trace import create_run_fixture


def four_node_fixture(root):
    # Two independent complete channels exercise four node identities, not a
    # simulated implementation of a particular collective algorithm.
    manifest = dict(run_id="four-node-fixture", nodes=[], ranks=[], operations=[dict(
        operation_id="call0", evidence="synthetic four-node invocation", members=[])])
    for pair in range(2):
        folder = root / ("pair" + str(pair))
        folder.mkdir()
        _, original = create_run_fixture(folder)
        if pair:
            for node in original["nodes"]:
                db = next((folder / node["msprof_db_dir"]).glob("*.db"))
                with sqlite3.connect(db) as connection:
                    connection.execute("UPDATE COMMUNICATION_TASK_INFO SET srcRank=srcRank+10, dstRank=dstRank+10")
                    connection.execute("UPDATE COMMUNICATION_TASK_INFO SET notifyId=? WHERE notifyId>=0",
                                       ((19 << 32) | 128,))
                plog = folder / node["plog_dir"] / "plog-fixture.log"
                contents = plog.read_text().replace("user_rank[3]", "user_rank[13]")
                contents = contents.replace("user_rank[9]", "user_rank[19]")
                contents = contents.replace("peer_rank[3]", "peer_rank[13]").replace("peer_rank[9]", "peer_rank[19]")
                plog.write_text(contents.replace("notify_id[{}]".format((9 << 32) | 128),
                                                "notify_id[{}]".format((19 << 32) | 128)))
        for index, node in enumerate(original["nodes"]):
            name = "node" + str(2 * pair + index)
            manifest["nodes"].append(dict(node_id=name, plog_dir="pair{}/{}".format(pair, node["plog_dir"]),
                                          msprof_db_dir="pair{}/{}".format(pair, node["msprof_db_dir"])))
            rank = dict(original["ranks"][index], node_id=name)
            rank["user_rank"] += pair * 10
            manifest["ranks"].append(rank)
            member = dict(original["operations"][0]["members"][index], node_id=name)
            manifest["operations"][0]["members"].append(member)
    path = root / "four.json"
    path.write_text(json.dumps(manifest))
    return path


class FullDiagnosisTests(unittest.TestCase):
    def test_analysis_exception_leaves_failed_status(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            manifest = four_node_fixture(root)
            with patch(run_pipeline.__module__ + ".waits.analyze", side_effect=ValueError("bad evidence")):
                with self.assertRaisesRegex(ValueError, "bad evidence"):
                    run_pipeline(manifest, root / "out")
            directory = root / "out/four-node-fixture"
            result = json.loads((directory / "pipeline_result.json").read_text())
            self.assertEqual(result["status"], "failed")
            self.assertEqual(result["error"], "bad evidence")
            self.assertFalse(result["analysis_completed"])
            self.assertFalse((directory / "waits.html").exists())

    def test_existing_result_is_never_overwritten(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            manifest = four_node_fixture(root)
            directory, _ = run_pipeline(manifest, root / "out")
            original = (directory / "pipeline_result.json").read_bytes()
            with self.assertRaises(FileExistsError):
                run_pipeline(manifest, root / "out")
            self.assertEqual(original, (directory / "pipeline_result.json").read_bytes())

    def test_four_nodes_export_real_edges_analysis_and_views(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            directory, ready = run_pipeline(four_node_fixture(root), root / "out")
            self.assertTrue(ready)
            result = json.loads((directory / "pipeline_result.json").read_text())
            self.assertEqual(result["node_count"], 4)
            self.assertEqual(result["paired_wait_count"], 2)
            self.assertFalse(result["global_critical_path_available"])
            critical = json.loads((directory / "critical_path.json").read_text())
            self.assertEqual(len(critical["local_report_files"]), 4)
            self.assertEqual(len(critical["cross_node_dependencies"]), 2)
            for name in ("execution", "waits", "resource"):
                self.assertTrue((directory / (name + ".html")).is_file())
            diagnosis = json.loads((directory / "diagnosis.json").read_text())
            self.assertEqual(diagnosis["candidates"], [])

    def test_missing_semantics_prevents_downstream_success(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            manifest = four_node_fixture(root)
            (root / "pair1/node1/plog/plog-fixture.log").write_text("")
            directory, ready = run_pipeline(manifest, root / "out")
            self.assertFalse(ready)
            result = json.loads((directory / "pipeline_result.json").read_text())
            self.assertFalse(result["analysis_completed"])
            for name in ("dep_graph_nodes.csv", "diagnosis.json", "waits.html", "critical_path.json"):
                self.assertFalse((directory / name).exists())

    def test_unbound_operation_is_not_a_complete_diagnosis(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            path = four_node_fixture(root)
            manifest = json.loads(path.read_text())
            manifest["operations"] = []
            path.write_text(json.dumps(manifest))
            directory, ready = run_pipeline(path, root / "out")
            self.assertFalse(ready)
            self.assertFalse((directory / "diagnosis.json").exists())


if __name__ == "__main__":
    unittest.main()
