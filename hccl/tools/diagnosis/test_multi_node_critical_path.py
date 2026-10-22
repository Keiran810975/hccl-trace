"""Multi-node timing boundaries; fixtures deliberately use incomparable clocks."""

from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from diagnosis.critical_path import analyze_multi_node_critical_path, export_multi_node_report
    from diagnosis.test_critical_path import task, order
    from diagnosis.schema import write_csv
else:
    from .critical_path import analyze_multi_node_critical_path, export_multi_node_report
    from .test_critical_path import task, order
    from .schema import write_csv


def remote(src="r", dst="w"):
    return dict(edge_id="remote", src=src, dst=dst, kind="cross_node_notify_sync_observed",
                confidence="observed")


class MultiNodeCriticalPathTests(unittest.TestCase):
    def rows(self, shift=0):
        return [task("r", 1000000, 1000001, kind="rdma", node="run/node0"),
                task("w", shift, shift + 200, kind="notify_wait", node="run/node1"),
                task("d", shift + 200, shift + 210, node="run/node1")]

    def test_local_paths_and_topology_not_global_sum(self):
        report = analyze_multi_node_critical_path(self.rows(), [remote(), order("w", "d")])
        self.assertIsNone(report["global_makespan_ns"])
        self.assertIsNone(report["global_critical_path"])
        self.assertEqual(report["local_reports"]["run/node0"]["makespan_ns"], 1000)
        self.assertEqual(report["local_reports"]["run/node1"]["makespan_ns"], 210000)
        bridge = report["cross_node_dependencies"][0]
        self.assertEqual(bridge["local_wait_duration_ns"], 200000)
        self.assertEqual(bridge["rdma_submission_duration_ns"], 1000)
        self.assertIsNone(bridge["network_transfer_ns"])
        self.assertIsNone(bridge["global_slack_ns"])
        self.assertEqual(bridge["wait_critical_in_local_scope"], 1)

    def test_independent_clock_shift_does_not_change_results(self):
        first = analyze_multi_node_critical_path(self.rows(), [remote(), order("w", "d")])
        shifted = analyze_multi_node_critical_path(self.rows(987654321), [remote(), order("w", "d")])
        for key in ("node_summaries", "cross_node_dependencies"):
            self.assertEqual(first[key], shifted[key])
        for node in first["local_reports"]:
            for key in ("tasks", "representative_path", "impacts"):
                self.assertEqual(first["local_reports"][node][key], shifted["local_reports"][node][key])

    def test_wait_is_opaque_at_remote_boundary(self):
        report = analyze_multi_node_critical_path(self.rows(), [remote(), order("w", "d")])
        local = report["local_reports"]["run/node1"]
        self.assertIn("remote_dependency_boundary", {issue["code"] for issue in local["issues"]})
        wait = next(row for row in local["tasks"] if row["graph_id"] == "w")
        self.assertEqual(wait["cost_kind"], "unresolved_wait")
        self.assertEqual(wait["effective_work_ns"], 200000)

    def test_local_criticality_is_not_promoted_to_global(self):
        rows = self.rows() + [task("z", 0, 500, stream=2, node="run/node1")]
        report = analyze_multi_node_critical_path(rows, [remote(), order("w", "d")])
        self.assertEqual(report["cross_node_dependencies"][0]["wait_critical_in_local_scope"], 0)
        self.assertIsNone(report["global_critical_task_count"])

    def test_explicit_completions_do_not_invent_other_node_endpoints(self):
        report = analyze_multi_node_critical_path(self.rows(), [remote(), order("w", "d")], completion_ids=["d"])
        self.assertEqual(len(report["local_reports"]), 1)
        self.assertEqual(report["node_summaries"][0]["status"], "not_selected_completion_domain")
        self.assertIsNone(report["cross_node_dependencies"][0]["producer_critical_in_local_scope"])

    def test_invalid_graph_and_endpoint_are_not_hidden(self):
        for rows, edges, options in [([], [], {}), (self.rows(), [remote("missing")], {}),
                (self.rows(), [remote()], {"completion_ids": ["missing"]}),
                (self.rows() + [self.rows()[0]], [remote()], {})]:
            with self.subTest(options=options), self.assertRaises(ValueError):
                analyze_multi_node_critical_path(rows, edges, **options)

    def test_unknown_remote_relation_remains_visible(self):
        edge = dict(remote(), kind="unsupported", confidence="semantic")
        report = analyze_multi_node_critical_path(self.rows(), [edge])
        self.assertEqual(report["cross_node_dependencies"][0]["timing_status"], "unsupported_remote_dependency")

    def test_export_uses_safe_filenames_not_node_paths(self):
        report = analyze_multi_node_critical_path(self.rows(), [remote()])
        with tempfile.TemporaryDirectory() as name:
            output = export_multi_node_report(report, Path(name) / "report")
            loaded = json.loads(output.read_text())
            self.assertNotIn("local_reports", loaded)
            self.assertEqual(loaded["local_report_files"]["run/node0"], "report_node0.json")
            self.assertTrue((Path(name) / "report_cross_node_dependencies.csv").exists())

    def test_cli_explicit_multinode_mode(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            common = dict(graph_schema_version=4, device_id=0, profiler_stream_id=0,
                          profiler_task_id=1, duration="5", subtask_id=-1)
            rows = [dict(common, graph_id="r", node_id="n0", task_start="1000", task_stop="1005", profiler_task_kind="rdma"),
                    dict(common, graph_id="w", node_id="n1", task_start="0", task_stop="5", profiler_task_kind="notify_wait")]
            edge = dict(remote(), graph_schema_version=4)
            write_csv(str(root / "nodes.csv"), list(rows[0]), rows)
            write_csv(str(root / "edges.csv"), list(edge), [edge])
            command = [sys.executable, "-m", "hccl.tools.diagnosis.critical_path", str(root / "nodes.csv"),
                       "--edges-csv", str(root / "edges.csv"), "--multi-node", "-o", str(root / "report")]
            done = subprocess.run(command, capture_output=True, text=True, cwd=Path(__file__).resolve().parents[3])
            self.assertEqual(done.returncode, 0, done.stderr)
            report = json.loads((root / "report.json").read_text())
            self.assertEqual(report["timing_status"], "cross_node_uncalibrated")
            self.assertIsNone(report["global_makespan_ns"])


if __name__ == "__main__":
    unittest.main()
