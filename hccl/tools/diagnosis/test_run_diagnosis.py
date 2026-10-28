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
    from diagnosis.run_diagnosis import run_pipeline, attach_rolling_sources, resume_replay_analysis
    from diagnosis.test_multi_node_trace import create_run_fixture
else:
    from .run_diagnosis import run_pipeline, attach_rolling_sources, resume_replay_analysis
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
    def test_resume_consumers_requires_the_original_passed_replay_gates(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            manifest = four_node_fixture(root)
            original, ready = run_pipeline(manifest, root / "original", html_views=())
            self.assertTrue(ready)
            import csv
            with (original / "dep_graph_nodes.csv").open() as stream:
                scope = next(csv.DictReader(stream))["profiler_op_scope"]
            mapping = root / "coordinates.json"
            mapping.write_text(json.dumps(dict(schema_version=1, operations=[dict(operation_scope=scope,
                stage="measured", iteration=0, block=0, bucket=0, evidence="synthetic capture binding")])) )
            resumed, ready = resume_replay_analysis(original, root / "resumed", iteration_map=mapping)
            self.assertTrue(ready)
            self.assertEqual((resumed / "dep_graph_nodes.csv").read_bytes(), (original / "dep_graph_nodes.csv").read_bytes())
            self.assertTrue((resumed / "resumed-from.json").is_file())
            again, ready = resume_replay_analysis(resumed, root / "resumed-again", iteration_map=mapping)
            self.assertTrue(ready)
            self.assertTrue((again / "propagation/report.json").is_file())
            self.assertTrue((again / "rdma_timing/report.json").is_file())
            with self.assertRaises(FileExistsError):
                resume_replay_analysis(original, resumed, iteration_map=mapping)
            summary = original / "run_summary.csv"
            summary.write_text(summary.read_text().replace("replay_gate_passed,1", "replay_gate_passed,0"))
            with self.assertRaisesRegex(ValueError, "passed replay"):
                resume_replay_analysis(original, root / "bad-resume", iteration_map=mapping)

    def test_wait_index_preserves_candidate_order_paths_and_unrelated_waits(self):
        first = dict(status="dependency_supported_candidate", root_id="a", component="execution", reason="evidence",
                     graph_id="task-a", user_rank=0, phase="allgather", affected_wait_graph_ids=["w", "w"],
                     evidence_paths={"w": ["e1", "e2"]})
        second = dict(first, root_id="b", graph_id="task-b", affected_wait_graph_ids=["w"], evidence_paths={"w": ["e2", "e3"]})
        report = dict(reference_mode="previous_five_iteration_mean", root_causes=[second, first],
                      tasks=[dict(graph_id="w", duration_slow=True)])
        diagnosis = dict(waits=[dict(wait_graph_id="w", classification="short_wait"),
                                dict(wait_graph_id="other", classification="evidence_gap")])
        attach_rolling_sources(diagnosis, report)
        self.assertEqual(diagnosis["waits"][0]["candidate_ids"], "b;a")
        self.assertEqual(diagnosis["waits"][0]["evidence_path_edge_ids"], "e2;e3;e1")
        self.assertTrue(diagnosis["waits"][0]["rolling_slow"])
        self.assertEqual(diagnosis["waits"][1]["classification"], "evidence_gap")
        self.assertEqual(diagnosis["waits"][1]["candidate_ids"], "")

    def test_gap_observation_does_not_label_a_wait_as_explained(self):
        report = dict(reference_mode="previous_five_iteration_mean", source_policy_version=2,
                      root_causes=[dict(status="unattributed_gap", root_id="gap", component="pre_task_gap",
                                        graph_id="w", affected_wait_graph_ids=[], evidence_paths={}, reason="unknown owner")],
                      tasks=[dict(graph_id="w", duration_slow=True, reference_count=5)])
        diagnosis = dict(waits=[dict(wait_graph_id="w", classification="pending_rolling")])
        attach_rolling_sources(diagnosis, report)
        self.assertEqual(diagnosis["candidates"], [])
        self.assertEqual(diagnosis["unattributed_gap_count"], 1)
        self.assertEqual(diagnosis["source_policy_version"], 2)
        self.assertEqual(diagnosis["waits"][0]["classification"], "unresolved_upstream")
        self.assertEqual(diagnosis["waits"][0]["candidate_ids"], "")

    def test_noncritical_v3_candidate_stays_an_observation_not_a_wait_explanation(self):
        source = dict(status="dependency_supported_candidate", root_id="a", component="execution", reason="path only",
                      graph_id="task-a", user_rank=0, phase="allgather", affected_wait_graph_ids=["w"],
                      evidence_paths={"w": ["e1"]}, primary_eligible=False)
        report = dict(reference_mode="previous_five_iteration_mean", source_policy_version=3,
                      primary_source_candidate_id=None, diagnosis_status="no_slow_event", slow_event_count=0,
                      root_causes=[source], tasks=[dict(graph_id="w", duration_slow=True, reference_count=5)])
        diagnosis = dict(waits=[dict(wait_graph_id="w", classification="pending_rolling")])
        attach_rolling_sources(diagnosis, report)
        self.assertEqual(diagnosis["candidates"], [])
        self.assertEqual(diagnosis["waits"][0]["classification"], "unresolved_upstream")
        self.assertEqual(diagnosis["diagnosis_status"], "no_slow_event")

    def test_skipping_large_views_preserves_strict_analysis_and_artifacts(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            directory, ready = run_pipeline(four_node_fixture(root), root / "out", html_views=())
            self.assertTrue(ready)
            self.assertTrue((directory / "diagnosis.json").is_file())
            self.assertTrue((directory / "dep_graph_nodes.csv").is_file())
            self.assertTrue((directory / "critical_path.json").is_file())
            self.assertFalse((directory / "execution.html").exists())
            self.assertEqual(json.loads((directory / "pipeline_result.json").read_text())["html_views"], [])
            result=json.loads((directory / "pipeline_result.json").read_text())
            self.assertEqual(result["rdma_protocol_report"],"rdma_timing/index.html")
            self.assertFalse(result["rdma_hardware_transfer_duration_available"])
            self.assertTrue((directory / "rdma_timing/transfers.csv").is_file())
            self.assertNotIn("../execution.html",(directory / "rdma_timing/index.html").read_text())
            self.assertEqual(result["rdma_completion_report"], "rdma_completion/index.html")
            self.assertEqual(result["rdma_completion_observed_count"], 0)
            self.assertFalse(result["rdma_full_transfer_and_dependency_available"])
            self.assertFalse(result["rdma_completion_graph_binding_available"])
            self.assertTrue((directory / "rdma_completion/operations.csv").is_file())
            self.assertNotIn("../execution.html", (directory / "rdma_completion/index.html").read_text())

    def test_protocol_evidence_cannot_pass_complete_rdma_acceptance(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            directory, ready = run_pipeline(four_node_fixture(root), root / "out", html_views=(),
                                            require_complete_rdma=True)
            self.assertFalse(ready)
            result = json.loads((directory / "pipeline_result.json").read_text())
            self.assertEqual(result["status"], "incomplete")
            self.assertTrue(result["replay_gate_passed"])
            self.assertTrue(result["rdma_completion_gate_required"])
            self.assertFalse(result["rdma_completion_gate_passed"])
            self.assertTrue((directory / "rdma_timing/report.json").is_file())

    def test_rolling_mode_exports_history_status_without_external_baseline(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            manifest = four_node_fixture(root)
            original, _ = run_pipeline(manifest, root / "original")
            with (original / "dep_graph_nodes.csv").open() as source:
                import csv
                scope = next(csv.DictReader(source))["profiler_op_scope"]
            mapping = root / "public-call-map.json"
            mapping.write_text(json.dumps(dict(schema_version=1, operations=[dict(
                operation_scope=scope, stage="measured", iteration=0, block=0, bucket=0,
                evidence="synthetic public capture binding, not injection truth")])) )
            directory, ready = run_pipeline(manifest, root / "rolling", iteration_map=mapping)
            self.assertTrue(ready)
            result = json.loads((directory / "pipeline_result.json").read_text())
            self.assertEqual(result["reference_mode"], "previous_five_iteration_mean")
            self.assertEqual(result["rolling_status"], "no_comparable_history")
            self.assertFalse(result["anomaly_baseline_supplied"])
            self.assertTrue((directory / "rolling/index.html").exists())
            self.assertTrue((directory / "propagation/index.html").exists())
            self.assertEqual(result["propagation_chain_count"], 0)

    def test_rolling_mode_rejects_external_baseline(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            manifest = four_node_fixture(root)
            with self.assertRaisesRegex(ValueError, "external baseline"):
                run_pipeline(manifest, root / "out", baseline=root / "normal", iteration_map=root / "map.json")

    def test_changed_wait_exports_paired_figures_through_pipeline(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            manifest = four_node_fixture(root)
            baseline, _ = run_pipeline(manifest, root / "normal")
            receiver_db = next((root / "pair0/node1/db").glob("*.db"))
            with sqlite3.connect(receiver_db) as connection:
                connection.execute("UPDATE TASK SET endNs=endNs+2000000 WHERE taskId=1")
                connection.execute("UPDATE TASK SET startNs=startNs+2000000, endNs=endNs+2000000 WHERE taskId=2")
            directory, ready = run_pipeline(manifest, root / "anomaly", baseline=baseline)
            self.assertTrue(ready)
            report = json.loads((directory / "comparison/report.json").read_text())
            self.assertGreater(report["slow_task_count"], 0)
            self.assertTrue(report["figures"])
            self.assertEqual(report["root_causes"][0]["status"], "unresolved_upstream")
            self.assertTrue((directory / "comparison/focus-001-anomaly.html").exists())
            self.assertTrue((directory / "comparison/focus-001-baseline.svg").exists())

    def test_failed_baseline_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            manifest = four_node_fixture(root)
            baseline, _ = run_pipeline(manifest, root / "normal")
            (baseline / "pipeline_result.json").write_text(json.dumps(dict(status="failed")))
            with self.assertRaisesRegex(ValueError, "baseline diagnosis"):
                run_pipeline(manifest, root / "anomaly", baseline=baseline)
            result = json.loads((root / "anomaly/four-node-fixture/pipeline_result.json").read_text())
            self.assertEqual(result["status"], "failed")
            self.assertFalse((root / "anomaly/four-node-fixture/comparison/report.json").exists())

    def test_baseline_automatically_exports_comparison(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            manifest = four_node_fixture(root)
            baseline, _ = run_pipeline(manifest, root / "normal")
            directory, ready = run_pipeline(manifest, root / "anomaly", baseline=baseline)
            self.assertTrue(ready)
            result = json.loads((directory / "pipeline_result.json").read_text())
            self.assertTrue(result["comparison_completed"])
            self.assertEqual(result["slow_task_count"], 0)
            self.assertTrue((directory / "comparison/index.html").exists())
            report = json.loads((directory / "comparison/report.json").read_text())
            self.assertEqual(report["root_causes"], [])

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
