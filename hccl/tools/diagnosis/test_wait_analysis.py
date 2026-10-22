"""Wait attribution preserves dependency evidence and clock-domain limits."""
from __future__ import annotations
import os
import sys
import unittest
from copy import deepcopy

if __package__ in (None, ""):
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from diagnosis.analyze_waits import analyze, union_ns
    from diagnosis.test_diagnosis import execution_row, dependency_edge
    from diagnosis.resource_dependency_graph import build_resource_graph
    from diagnosis.visualize_html import attach_diagnosis
else:
    from .analyze_waits import analyze, union_ns
    from .test_diagnosis import execution_row, dependency_edge
    from .resource_dependency_graph import build_resource_graph
    from .visualize_html import attach_diagnosis


def fixture():
    rows = [execution_row(0, 90, 0, 0, rank=0),
            execution_row(1, 90, 1, 20000, rank=0, kind="notify_record"),
            execution_row(2, 90, 0, 1, rank=1, kind="notify_wait"),
            execution_row(3, 12, 9, 0, rank=0, kind="kernel_aicpu")]
    for row in rows:
        row["_operation_scope"] = "op"
    rows[2].update(_stop=20001, _duration=20000)
    rows[1].update(algorithm="nhr", phase="reduce_scatter", step=0)
    rows[3].update(_stop=20000, _duration=20000)
    edges = [dependency_edge("direct_stream_order_observed", "p0", "p1", "e0"),
             dependency_edge("cross_node_notify_sync_observed", "p1", "p2", "e1", "relation")]
    span = dict(node_id="node0", device_id=0, kernel_stream_id=12, kernel_task_id=9,
                user_rank=0, algorithm="nhr", phase="reduce_scatter", step=0,
                duration_ns=20000000, evidence="fixture.log:1")
    return rows, edges, span


class WaitAnalysisTest(unittest.TestCase):
    def test_view_rejects_foreign_or_duplicate_diagnosis(self):
        rows, edges, span = fixture()
        result = analyze(rows, edges, spans=[span])
        model = dict(nodes=[dict(id=r['_graph_id'], operationScope=r['_operation_scope']) for r in rows])
        attach_diagnosis(model, result, result['waits'], 'waits')
        self.assertEqual(model['waits'], result['waits'])
        for view in ('execution', 'resource', 'waits'):
            foreign = deepcopy(result)
            foreign['waits'][0]['operation_scope'] = 'another-run'
            with self.assertRaises(ValueError):
                attach_diagnosis(model, foreign, result['waits'], view)
            duplicate = deepcopy(result)
            duplicate['waits'] *= 2
            with self.assertRaises(ValueError):
                attach_diagnosis(model, duplicate, result['waits'], view)

    def test_cpu_build_candidate_uses_upstream_rank_and_operation_not_false_dag_edge(self):
        rows, edges, span = fixture()
        result = analyze(rows, edges, spans=[span])
        wait, = result["waits"]
        self.assertEqual(wait["classification"], "upstream_slow_candidate")
        self.assertEqual(wait["candidate_ranks"], "0")
        self.assertEqual(wait["candidate_phases"], "reduce_scatter")
        self.assertEqual(wait["attribution"], "upstream_rank_operation_correlation")
        self.assertEqual(wait["evidence_path_edge_ids"], "e1")
        self.assertEqual(len(edges), 2)

    def test_missing_endpoint_remains_gap_and_other_operation_does_not_leak(self):
        rows, edges, span = fixture()
        self.assertEqual(analyze(rows, edges[:1], spans=[span])["waits"][0]["classification"], "evidence_gap")
        rows[3]["_operation_scope"] = "another"
        self.assertEqual(analyze(rows, edges, spans=[span])["waits"][0]["candidate_ids"], "")

    def test_cpu_phase_must_be_on_upstream_path(self):
        rows, edges, span = fixture()
        rows[1]["step"] = 1
        self.assertEqual(analyze(rows, edges, spans=[span])["waits"][0]["candidate_ids"], "")

    def test_node_clock_shift_does_not_change_attribution(self):
        rows, edges, span = fixture()
        before = analyze(rows, edges, spans=[span])
        shifted = deepcopy(rows)
        for row in shifted:
            if row["_user_rank"] == 0:
                row["_start"] += 99999999
                row["_stop"] += 99999999
        after = analyze(shifted, edges, spans=[span])
        self.assertEqual(before["waits"], after["waits"])
        self.assertEqual(before["candidates"], after["candidates"])

    def test_rdma_submission_is_never_device_transfer_outlier(self):
        rows, edges, _ = fixture()
        rows[0].update(profiler_task_kind="rdma", _stop=999999, _duration=999999)
        baseline = deepcopy(rows)
        baseline[0].update(_stop=1, _duration=1)
        self.assertEqual(analyze(rows, edges, baseline_rows=baseline)["candidates"], [])

    def test_unbound_setup_kernel_is_not_an_operation_root_candidate(self):
        rows, edges, _ = fixture()
        rows[3]["_operation_scope"] = ""
        baseline = deepcopy(rows)
        baseline[3].update(_stop=1, _duration=1)
        self.assertEqual(analyze(rows, edges, baseline_rows=baseline)["candidates"], [])

    def test_union_does_not_double_count_overlapping_waits(self):
        self.assertEqual(union_ns([(1, 9), (3, 10), (12, 15), (4, 5)]), 12)

    def test_resource_paths_keep_weakest_order_and_sync_evidence(self):
        rows, _, _ = fixture()
        rows[2]["profiler_task_kind"] = "sdma"
        for kind, confidence in (("direct_stream_order_observed", "observed"),
                                 ("ffts_logical_stream_order", "semantic")):
            edges = [dependency_edge(kind, "p0", "p1", "a"),
                     dependency_edge("direct_notify_sync_exact", "p1", "p2", "b", "relation")]
            _, derived, _ = build_resource_graph(rows[:3], edges)
            sync, = [e for e in derived if "notify_sync" in e["kind"]]
            self.assertEqual(sync["confidence"], confidence)
            self.assertTrue(sync["kind"].endswith("_" + confidence))
        middle = deepcopy(rows[1]); middle["profiler_task_kind"] = "notify_record"
        edges = [dependency_edge("ffts_logical_stream_order", "p0", "p1", "a"),
                 dependency_edge("direct_stream_order_observed", "p1", "p2", "b")]
        _, derived, _ = build_resource_graph([rows[0], middle, rows[2]], edges)
        self.assertEqual(derived[0]["kind"], "resource_order_semantic")


if __name__ == "__main__":
    unittest.main()
