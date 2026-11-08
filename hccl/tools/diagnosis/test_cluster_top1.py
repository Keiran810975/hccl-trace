from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
from decimal import Decimal
import unittest

from .cluster_top1 import rank, select, score_cluster
from .local_slow_clusters import ClusterOptions, build_clusters
from .test_local_slow_clusters import fork, history
from .test_significant_regions import task
from .test_source_selection import observations


class ClusterTop1Tests(unittest.TestCase):
    def test_tiny_high_ratio_no_longer_beats_material_execution_growth(self):
        values = history([task("large", stop=2000, mean="1000"), task("tiny", stop=10, mean="1", operation="other")])
        for t in values:
            if t["graph_id"].startswith("tiny-history"):
                t["operation_scope"] += "-other"
        decision = rank(values, [])
        self.assertEqual(decision["selected_proposal"]["candidate_graph_ids"], ["large"])
        self.assertEqual(decision["selected_proposal"]["score"], "1000")
        self.assertEqual(rank(list(reversed(values)), [])["selected_proposal"], decision["selected_proposal"])

    def test_one_cluster_all_parallel_members_and_no_parallel_stream_double_count(self):
        values, edges = fork()
        report = dict(tasks=values, root_causes=[], options=dict(slowdown_factor="1.5", mad_multiplier="3"))
        before = deepcopy((report, edges))
        chosen, decision = select(report, edges)
        self.assertEqual(len(chosen["root_causes"]), 3)
        self.assertIsNone(chosen["primary_source_candidate_id"])
        self.assertEqual(decision["cluster_selection"]["selected_cluster_count"], 1)
        self.assertEqual(decision["selected_proposal"]["score"], "40")
        self.assertEqual(len({r["region_id"] for r in chosen["root_causes"]}), 1)
        self.assertEqual((report, edges), before)

    def test_original_dependency_membership_not_semantic_call_grouping_is_preserved(self):
        values, edges = fork()
        _, expected, _ = build_clusters(values, edges)
        decision = rank(values, edges)
        self.assertEqual({c["region_id"]: c["preliminary_graph_ids"] for c in decision["clusters"]},
                         {c["region_id"]: c["preliminary_graph_ids"] for c in expected})
        self.assertEqual(len(rank(values, [])["clusters"]), 3)

    def test_all_other_clusters_remain_auditable_not_public_candidates(self):
        values = history([task("large", stop=1000), task("small", stop=30)])
        report = dict(tasks=values, root_causes=[], options=dict(slowdown_factor="1.5", mad_multiplier="3"))
        chosen, decision = select(report, [])
        self.assertEqual(len(decision["clusters"]), 2)
        self.assertEqual(len(chosen["root_causes"]), 1)
        self.assertEqual(chosen["root_causes"][0]["graph_id"], "large")

    def test_no_positive_cluster_is_not_replaced_by_largest_wait_or_gap(self):
        work = task("normal", stop=10)
        work["gap_before_ns"] = 10**9
        wait = task("wait", "notify_wait", stop=10**9)
        decision = rank(history([work, wait]), [])
        self.assertIsNone(decision["selected_proposal"])
        with self.assertRaises(ValueError):
            rank([], [], options=replace(ClusterOptions(), selection_policy="score-band"))

    def test_past_alarm_discount_is_bounded_and_overlapping_work_not_double_counted(self):
        nodes = {"a": task("a"), "b": task("b", start=31, stop=61)}
        group = dict(preliminary_graph_ids=["a", "b"], task_scores={k: dict(history_alarm_fraction="1") for k in nodes})
        self.assertEqual(Decimal(score_cluster(group, nodes)["score"]), 20)
        nodes["b"].update(observed_start_ns=0, observed_stop_ns=30)
        self.assertEqual(score_cluster(group, nodes)["status"], "overlapping_work_on_one_physical_stream")

    def test_host_requires_unchanged_public_endpoint_evidence_and_competes_as_one_interval(self):
        values, edges = fork()
        hosts = observations(host_delay=True)
        decision = rank(values, edges, hosts)
        self.assertEqual(decision["selected_proposal"]["mechanism"], "host_preparation_late")
        broken = deepcopy(hosts)
        broken[0]["supporting_dependencies"] = []
        self.assertEqual(rank(values, edges, broken)["selected_proposal"]["mechanism"], "communication_execution_growth")

    def test_selected_sources_survive_public_normalization_without_a_primary_id(self):
        from . import rolling_diagnosis as rolling
        from .result_normalizer import normalize
        from .test_source_events import capture
        rows, edges, coords, preparations = capture(execution_delay=True)
        report = rolling.analyze(rows, edges, coords, rolling.RollingOptions(source_policy="cluster-top1"), preparations=preparations)
        chosen, decision = select(report, edges)
        public, roots, _ = normalize(chosen, mode="rolling", run_id="fixture", rows=rows, edges=edges,
            pipeline=dict(status="passed"), binding_evidence={})
        self.assertEqual(public["diagnosis_status"], "localized_candidate")
        self.assertEqual(len(public["candidates"]), 1)
        self.assertIsNone(public["primary_candidate_id"])
        self.assertEqual(public["candidate_relationship"], "parallel")
        self.assertEqual(len({r["source_region_id"] for r in roots}), 1)

    def test_stable_wrapper_preserves_original_positive_candidates_and_score(self):
        from . import rolling_diagnosis as rolling
        from .parallel_sources import select as stable_select
        from .multinode_source_policy import select as old_select
        from .test_source_events import capture
        rows, edges, coords, preparations = capture(execution_delay=True)
        report = rolling.analyze(rows, edges, coords, rolling.RollingOptions(source_policy="dual-v2"), preparations=preparations)
        original, old = old_select(report, rows, edges, None, refined=True)
        chosen, stable = stable_select(report, edges, rows=rows)
        self.assertTrue(original["root_causes"])
        self.assertEqual(chosen["root_causes"], original["root_causes"])
        self.assertEqual(stable["cluster_selection"]["selected_cluster_id"], old["primary_proposal"]["proposal_id"])
        self.assertEqual(stable["cluster_selection"]["selected_score"], old["primary_proposal"]["score"])
        self.assertIsNone(chosen["primary_source_candidate_id"])


if __name__ == "__main__":
    unittest.main()
