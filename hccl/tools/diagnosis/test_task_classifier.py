"""Ownership, category separation and iteration boundaries are evidence contracts."""
from __future__ import annotations

from copy import deepcopy
import unittest

from . import rolling_diagnosis as rolling
from . import wait_backtrace
from . import source_propagation as propagation
from . import source_propagation_view as presentation
from .result_normalizer import normalize
from .task_classifier import classify_task, INTERNAL, EXTERNAL, UNRESOLVED
from .test_source_events import capture, cross_node_capture
from .test_wait_backtrace import cross_call_capture


class TaskOwnershipTests(unittest.TestCase):
    def test_mixed_kernel_name_or_missing_edges_do_not_prove_external_compute(self):
        for kind in ("kernel_mix_aic", "kernel_mix_aiv", "sdma", "MatMul"):
            self.assertEqual(classify_task(dict(profiler_task_kind=kind))["task_domain"], "unknown")

    def test_matched_semantics_and_unique_db_ownership_are_independent_evidence(self):
        semantic = dict(match_status="matched", algorithm="ring", phase="allgather", event="copy", semantic="payload")
        self.assertEqual(classify_task(semantic)["task_domain"], "hccl_internal")
        self.assertEqual(classify_task(dict(semantic, match_status="profiler_only"))["task_domain"], "unknown")
        self.assertEqual(classify_task(dict(profiler_task_kind="kernel_mix_aic", _operation_scope="op",
                                           _operation_scope_status="unique"))["task_domain"], "hccl_internal")
        self.assertEqual(classify_task(dict(_operation_scope="op"))["task_domain"], "unknown")


class CategoryPolicyTests(unittest.TestCase):
    def public(self, rows, edges, report):
        return normalize(report, mode="rolling", run_id="fixture", rows=rows, edges=edges,
                         pipeline=dict(status="passed"), binding_evidence={})

    def test_internal_copy_has_real_path_and_unknown_physical_cause(self):
        rows, edges, coords, _ = capture(execution_delay=True)
        original = deepcopy((rows, edges))
        report = rolling.analyze(rows, edges, coords)
        public, roots, _ = self.public(rows, edges, report)
        self.assertEqual(public["schema_version"], 2)
        self.assertEqual(public["candidates"], public["communication_source_candidates"])
        root, = public["candidates"]
        self.assertEqual(root["diagnosis_category"], INTERNAL)
        self.assertEqual(root["task_domain"], "hccl_internal")
        self.assertEqual(root["physical_cause"], "unknown")
        self.assertEqual(roots[0]["evidence_paths"], {"i5p2": ["i5e0", "i5e1"]})
        self.assertEqual((rows, edges), original)

    def test_untrusted_slow_execution_is_not_an_internal_or_external_root(self):
        rows, edges, coords, _ = capture(execution_delay=True)
        for row in rows:
            if row["profiler_task_kind"] == "sdma":
                row.update(match_status="profiler_only", profiler_task_kind="kernel_mix_aic")
        report = rolling.analyze(rows, edges, coords)
        public, _, _ = self.public(rows, edges, report)
        self.assertEqual(public["candidates"], [])
        self.assertEqual(public["external_anomaly_clues"], [])
        self.assertTrue(any(r["graph_id"] == "i5p0" and r["task_domain"] == "unknown"
                            for r in public["unresolved_observations"] if "graph_id" in r))

    def test_isolated_copy_stays_observation_not_candidate(self):
        rows, edges, coords, _ = capture(execution_delay=True)
        edges = [e for e in edges if "notify_sync" not in e["kind"]]
        public, _, _ = self.public(rows, edges, rolling.analyze(rows, edges, coords))
        self.assertIsNone(public["primary_candidate_id"])
        self.assertEqual(public["candidates"], [])
        self.assertTrue(any(r.get("status") == "isolated_slow_task" for r in public["unresolved_observations"]))

    def test_host_and_internal_candidates_have_separate_rankings_and_primary(self):
        rows, edges, coords, prep = capture(host_delay=True, execution_delay=True)
        report = rolling.analyze(rows, edges, coords, preparations=prep)
        public, roots, tasks = self.public(rows, edges, report)
        self.assertEqual(len(public["candidates"]), 1)
        clue, = public["external_anomaly_clues"]
        self.assertEqual(clue["diagnosis_category"], EXTERNAL)
        self.assertTrue(clue["evidence_supported"])
        self.assertEqual(clue["category_rank"], 1)
        self.assertNotEqual(public["primary_candidate_id"], clue["id"])
        self.assertEqual(public["primary_external_clue_id"], clue["id"])
        shown = propagation.build_report(rows, edges, roots, tasks, unresolved_observations=public["unresolved_observations"])
        self.assertEqual(shown["summary"]["communication_source_count"], 1)
        self.assertEqual(shown["summary"]["external_clue_count"], 1)
        page = presentation.render_html(shown, standalone=True)
        self.assertIn("通信内部源头候选", page)
        self.assertIn("外部异常线索", page)
        self.assertIn("未归因观测", page)

    def test_unpaired_host_is_visible_clue_without_any_synthetic_chain(self):
        rows, edges, coords, prep = capture(host_delay=True)
        edges = [e for e in edges if "notify_sync" not in e["kind"]]
        report = rolling.analyze(rows, edges, coords, preparations=prep)
        public, roots, tasks = self.public(rows, edges, report)
        self.assertEqual(public["candidates"], [])
        clue, = public["external_anomaly_clues"]
        self.assertFalse(clue["evidence_supported"])
        self.assertEqual(clue["status"], "unresolved_host_preparation")
        shown = propagation.build_report(rows, edges, roots, tasks)
        self.assertEqual(shown["summary"]["chain_count"], 0)
        self.assertEqual(shown["candidates"][0]["chains"], [])

    def test_cross_node_host_rdma_anchor_is_a_real_protocol_endpoint(self):
        rows, edges, coords, prep, alignment = cross_node_capture()
        report = rolling.analyze(rows, edges, coords, preparations=prep, alignment=alignment)
        public, roots, tasks = self.public(rows, edges, report)
        self.assertIsNone(public["primary_candidate_id"])
        shown = propagation.build_report(rows, edges, roots, tasks)
        clue, = shown["candidates"]
        self.assertEqual(clue["diagnosis_category"], EXTERNAL)
        self.assertTrue(clue["chains"][0]["path_complete"])
        self.assertEqual(clue["chains"][0]["edge_ids"], ["i5e1"])


class IterationBoundaryTests(unittest.TestCase):
    def test_same_iteration_cross_call_remains_supported(self):
        rows, edges, coords = cross_call_capture()
        report = rolling.analyze(rows, edges, coords)
        root = next(r for r in report["root_causes"] if r["primary_eligible"])
        self.assertTrue(root["cross_operation"])
        self.assertEqual(root["evidence_paths"]["i5p2"], ["i5e0", "i5e1"])

    def test_cross_iteration_or_missing_identity_stops_before_source(self):
        for changed in (dict(iteration=4), dict(iteration=None, stage="unbound")):
            with self.subTest(changed=changed):
                rows, edges, coords = cross_call_capture()
                tasks = rolling.compare_tasks(rows, edges, coords, rolling.RollingOptions())
                source = next(t for t in tasks if t["graph_id"] == "i5p0")
                self.assertTrue(source["duration_slow"])
                source.update(changed)
                roots, traces = wait_backtrace.trace_sources(rows, edges, tasks, rolling.RollingOptions())
                self.assertFalse(any(r["status"] == "dependency_supported_candidate" for r in roots))
                reason = "iteration_boundary" if source["iteration"] is not None else "missing_iteration_identity"
                trace = next(t for t in traces if t["wait_graph_id"] == "i5p2")
                self.assertIn(reason, {b["reason"] for b in trace["boundaries"]})

    def test_missing_intermediate_call_binding_is_not_skipped(self):
        rows, edges, coords = cross_call_capture()
        for row in rows:
            if row["profiler_task_kind"] == "notify_record":
                row["_operation_scope"] = "unbound-control"
        report = rolling.analyze(rows, edges, coords)
        self.assertIsNone(report["primary_source_candidate_id"])
        self.assertIn("missing_iteration_identity", report["coverage"]["boundary_reason_counts"])
        public, _, _ = normalize(report, mode="rolling", run_id="fixture", rows=rows, edges=edges,
                                 pipeline=dict(status="passed"), binding_evidence={})
        self.assertTrue(any(b["graph_id"] == "i5p1" and b["reason"] == "missing_iteration_identity"
                            for item in public["unresolved_observations"] for b in item.get("boundaries", [])))


if __name__ == "__main__":
    unittest.main()
