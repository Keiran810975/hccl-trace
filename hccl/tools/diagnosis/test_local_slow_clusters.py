from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
from decimal import Decimal
import unittest

from .local_slow_clusters import ClusterOptions, analyze, build_clusters, _task_score, selected_cluster_ids
from .test_significant_regions import task, edge


def history(values):
    values = deepcopy(values)
    result = list(values)
    for current in values:
        current["reference_graph_ids"] = []
        if current["task_kind"] not in {"sdma", "reduce_inline"}:
            continue
        for i in range(5):
            key = current["graph_id"]+"-history-"+str(i)
            current["reference_graph_ids"].append(key)
            duration = int(Decimal(current["reference_mean_ns"]))
            result.append(dict(current, graph_id=key, iteration=i, reference_count=0,
                reference_graph_ids=[], duration_ns=duration, observed_start_ns=i*1000,
                observed_stop_ns=i*1000+duration, operation_scope="history-"+str(i)))
    return result


def fork():
    a = task("a", "reduce_inline", stop=30)
    record = task("record", "notify_record", start=30, stop=31, mean="1")
    wait = task("wait", "notify_wait", start=20, stop=32, mean="12")
    wait["stream_id"] = 1
    b = task("b", start=31, stop=61)
    c = task("c", start=32, stop=62)
    c["stream_id"] = 1
    return history([a, record, wait, b, c]), [edge("a", "record"), edge("record", "b"),
        edge("record", "wait", True), edge("wait", "c")]


class LocalSlowClusterTests(unittest.TestCase):
    def test_fork_is_one_cluster_without_a_slow_wait(self):
        values, edges = fork()
        before = deepcopy((values, edges))
        report = analyze(values, edges)
        self.assertEqual(report["summary"]["selected_region_count"], 1)
        self.assertEqual(report["summary"]["candidate_count"], 3)
        self.assertFalse(report["chains"])
        self.assertEqual(report["regions"][0]["evidence_unit_count"], 3)
        self.assertEqual((values, edges), before)

    def test_temporal_overlap_without_dependency_does_not_merge(self):
        _, groups, _ = build_clusters(history([task("a"), task("b")]), [])
        self.assertEqual(len(groups), 2)

    def test_normal_resource_separates_slow_resources(self):
        values = history([task("a"), task("normal", start=31, stop=41), task("b", start=42, stop=72)])
        _, groups, _ = build_clusters(values, [edge("a", "normal"), edge("normal", "b")])
        self.assertEqual(len(groups), 2)

    def test_long_gap_splits_a_call_adaptively(self):
        values = history([task("a"), task("b", start=1000, stop=1030)])
        _, groups, quality = build_clusters(values, [edge("a", "b")])
        self.assertEqual(len(groups), 2)
        self.assertGreater(quality["boundary_counts"]["outside_adaptive_locality"], 0)

    def test_singleton_can_be_selected_without_propagation(self):
        report = analyze(history([task("a")]), [])
        self.assertEqual(report["summary"]["candidate_count"], 1)
        self.assertFalse(report["candidates"][0]["affected_wait_graph_ids"])

    def test_default_top1_keeps_only_best_cluster_with_near_tie_audited(self):
        values = history([task("a", stop=30), task("b", stop=29)])
        report = analyze(values, [])
        self.assertEqual(report["summary"]["selected_region_count"], 1)
        self.assertEqual(report["summary"]["candidate_count"], 1)
        self.assertEqual(len(report["deferred_candidates"]), 1)
        self.assertEqual(len(report["cluster_selection"]["near_top_deferred_cluster_ids"]), 1)
        self.assertEqual(report["cluster_selection"]["policy"], "top1")

    def test_equal_scores_use_stable_id_and_not_input_order(self):
        clusters = [dict(region_id="z", score="1", core_score="1"), dict(region_id="a", score="1", core_score="1")]
        self.assertEqual(selected_cluster_ids(clusters, ClusterOptions()), {"a"})
        self.assertEqual(selected_cluster_ids(list(reversed(clusters)), ClusterOptions()), {"a"})

    def test_explicit_score_band_preserves_previous_multiple_cluster_policy(self):
        report = analyze(history([task("a"), task("b")]), [], replace(ClusterOptions(), selection_policy="score-band"))
        self.assertEqual(report["summary"]["selected_region_count"], 2)
        self.assertEqual(report["summary"]["candidate_count"], 2)

    def test_no_positive_cluster_means_no_forced_top1(self):
        self.assertFalse(selected_cluster_ids([], ClusterOptions()))
        self.assertFalse(selected_cluster_ids([dict(region_id="a", score="0")], ClusterOptions()))

    def test_unexplained_wait_is_preserved_but_not_execution_root(self):
        values = history([task("a"), task("w", "notify_wait", start=1, stop=60)])
        report = analyze(values, [])
        self.assertEqual(report["summary"]["candidate_count"], 1)
        self.assertEqual(report["summary"]["unexplained_wait_observation_count"], 1)
        self.assertEqual(report["unexplained_wait_observations"][0]["graph_id"], "w")

    def test_propagation_only_gives_a_bounded_bonus(self):
        values, edges = fork()
        next(t for t in values if t["graph_id"] == "wait")["reference_mean_ns"] = "9"
        report = analyze(values, edges)
        self.assertTrue(report["chains"])
        self.assertEqual(report["summary"]["candidate_count"], 3)
        group = report["regions"][0]
        self.assertTrue(1 < Decimal(group["score"])/Decimal(group["core_score"]) <= Decimal("1.05"))

    def test_extreme_ratio_has_no_unbounded_priority(self):
        values = history([task("a", stop=100000, mean="1")])
        _, groups, _ = build_clusters(values, [])
        score = groups[0]["task_scores"]["a"]
        self.assertEqual(Decimal(score["clipped_severity"]), Decimal("1.5"))

    def test_repeated_work_on_same_stream_is_one_evidence_unit(self):
        values = history([task("a"), task("b", start=30, stop=60)])
        _, groups, _ = build_clusters(values, [edge("a", "b")])
        self.assertEqual(groups[0]["preliminary_count"], 2)
        self.assertEqual(groups[0]["evidence_unit_count"], 1)

    def test_future_or_wrong_rank_history_is_rejected(self):
        values = history([task("a")])
        values[1]["iteration"] = 5
        with self.assertRaises(ValueError):
            build_clusters(values, [])
        values = history([task("a")])
        values[1]["user_rank"] = 99
        with self.assertRaises(ValueError):
            build_clusters(values, [])

    def test_past_alarm_frequency_penalizes_recurrent_noise(self):
        values = history([task("a")])
        lookup = {v["graph_id"]: v for v in values}
        original = Decimal(_task_score(values[0], lookup, ClusterOptions())["score"])
        for item in values[1:]:
            item.update(reference_count=5, reference_mean_ns="1", reference_mad_ns="0")
        penalized = _task_score(values[0], lookup, ClusterOptions())
        self.assertEqual(penalized["history_alarm_count"], 5)
        self.assertEqual(Decimal(penalized["score"]), original/2)

    def test_signal_already_ready_is_group_context_not_propagation(self):
        values, edges = fork()
        wait = next(t for t in values if t["graph_id"] == "wait")
        wait.update(observed_start_ns=31, observed_stop_ns=32, duration_ns=1)
        report = analyze(values, edges)
        self.assertEqual(report["summary"]["selected_region_count"], 1)
        self.assertFalse(report["chains"])

    def test_invalid_options(self):
        for options in (replace(ClusterOptions(), locality_factor="NaN"),
                        replace(ClusterOptions(), propagation_bonus="2"),
                        replace(ClusterOptions(), control_hop_limit=0),
                        replace(ClusterOptions(), selection_policy="unknown")):
            with self.assertRaises(ValueError):
                options.validate()


if __name__ == "__main__":
    unittest.main()
