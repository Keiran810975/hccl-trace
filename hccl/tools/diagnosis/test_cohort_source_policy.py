from __future__ import annotations

from copy import deepcopy
from decimal import Decimal
import unittest

from .cohort_source_policy import POLICY, cohort_contexts, rank, select
from .local_slow_clusters import build_clusters
from .test_local_slow_clusters import fork, history
from .test_significant_regions import task
from .test_source_selection import observations


def population(prefix, *, rank=0, size=20, slow_count=4, factor=3, group="data-parallel"):
    values = []
    for i in range(size):
        start = i * 1000
        t = task(prefix + str(i), start=start, stop=start + (factor if i < slow_count else 1) * 10,
                 operation=prefix + "-call-" + str(i), rank=rank)
        t.update(group_id=group, call_site="call-" + str(i), reference_iterations=list(range(5)))
        values.append(t)
    return history(values)


def context(values, *, rank=0, group="data-parallel"):
    return cohort_contexts(values)[("node0", rank, rank, group, 5)]


class CohortSourcePolicyTests(unittest.TestCase):
    def test_population_includes_normal_work_not_just_the_slow_subset(self):
        values = population("task", slow_count=1, factor=100)
        found = context(values)
        self.assertEqual(found["population_count"], 20)
        self.assertEqual(found["comparable_count"], 20)
        self.assertEqual(found["p95_factor"], "1")
        self.assertEqual(found["multiplier"], "1")

    def test_coherent_context_beats_isolated_extreme_ratio_without_hard_filter(self):
        values = population("coherent") + population("isolated", rank=1, slow_count=1, factor=100)
        before = deepcopy(values)
        result = rank(values, [])
        self.assertEqual(result["primary_proposal"]["cohort_context"]["user_rank"], 0)
        self.assertEqual(len(result["candidates"]), 1)
        self.assertEqual(len(result["clusters"]), 5)
        self.assertEqual(result["cluster_selection"]["selected_cluster_count"], 1)
        self.assertEqual(values, before)
        self.assertEqual(rank(list(reversed(values)), [])["primary_proposal"], result["primary_proposal"])
        self.assertTrue(any(p["cohort_context"]["user_rank"] == 1 for p in result["proposals"]))

    def test_p95_small_population_is_neutral_not_its_maximum(self):
        found = context(population("small", size=19, slow_count=19, factor=100))
        self.assertEqual(found["status"], "population_below_twenty")
        self.assertIsNone(found["p95_factor"])
        self.assertEqual(found["multiplier"], "1")

    def test_one_missing_normal_history_disables_the_whole_population_support(self):
        values = population("tasks")
        missing = next(t for t in values if t["graph_id"] == "tasks19")["reference_graph_ids"][0]
        values = [t for t in values if t["graph_id"] != missing]
        found = context(values)
        self.assertEqual(found["status"], "incomplete_verified_previous_five_population")
        self.assertEqual(found["comparable_count"], 19)
        self.assertEqual(found["multiplier"], "1")

    def test_future_or_wrong_group_history_cannot_boost_population(self):
        for changed in (dict(iteration=99), dict(group_id="other")):
            values = population("tasks")
            normal = next(t for t in values if t["graph_id"] == "tasks19")
            reference = next(t for t in values if t["graph_id"] == normal["reference_graph_ids"][0])
            reference.update(changed)
            self.assertEqual(context(values)["multiplier"], "1")

    def test_node_device_rank_group_and_iteration_populations_are_separate(self):
        values = population("quiet", slow_count=0) + population("other-group", group="other", slow_count=4, factor=10)
        found = context(values)
        self.assertEqual(found["population_count"], 20)
        self.assertEqual(found["p95_factor"], "1")
        self.assertEqual(context(values, group="other")["p95_factor"], "10")
        future = deepcopy(population("future"))
        for t in future:
            t["iteration"] += 10
            if t["reference_count"] == 5:
                t["reference_iterations"] = list(range(10, 15))
        self.assertEqual(context(values + future), found)

    def test_log_support_uses_full_population_factor_without_truth_or_neighbour_counts(self):
        values = population("tasks")
        report = rank(values, [])
        expected = 1 + Decimal(3).ln()
        self.assertEqual(Decimal(context(values)["multiplier"]), expected)
        for proposal in report["proposals"]:
            self.assertEqual(Decimal(proposal["score"]), Decimal(proposal["relative_base_score"]) * expected)
            self.assertEqual(proposal["local_burst_context"]["multiplier"], "1")

    def test_missing_group_identity_does_not_infer_a_cohort_from_rank(self):
        values = population("task")
        for t in values:
            t.pop("group_id")
        result = rank(values, [])
        self.assertEqual(result["primary_proposal"]["cohort_context"]["status"], "public_cohort_identity_unavailable")
        self.assertEqual(result["primary_proposal"]["cohort_context"]["multiplier"], "1")

    def test_work_kind_and_history_thresholds_and_original_clusters_are_unchanged(self):
        values, edges = fork()
        expected = {c["region_id"]: c["preliminary_graph_ids"] for c in build_clusters(values, edges)[1]}
        result = rank(values, edges)
        self.assertEqual({c["region_id"]: c["preliminary_graph_ids"] for c in result["clusters"]}, expected)
        chosen, result = select(dict(tasks=values, root_causes=[], options=dict(slowdown_factor="1.5", mad_multiplier="3")), edges)
        self.assertEqual(len(chosen["root_causes"]), 3)
        self.assertTrue(all(r["source_selection_policy"] == POLICY for r in chosen["root_causes"]))
        self.assertIsNone(chosen["primary_source_candidate_id"])
        self.assertEqual(chosen["candidate_relationship"], "parallel")

    def test_normal_population_does_not_create_a_source_or_use_a_large_wait(self):
        values = population("normal", slow_count=0)
        values.append(task("wait", kind="notify_wait", stop=10**10))
        result = rank(values, [])
        self.assertFalse(result["candidates"])
        self.assertEqual(result["selected_mechanism"], "unlocalized")

    def test_host_still_requires_original_notify_and_endpoint_evidence(self):
        values, edges = fork()
        host = observations(host_delay=True)
        result = rank(values, edges, host)
        self.assertEqual(result["selected_mechanism"], "host_preparation_late")
        host[0]["supporting_dependencies"] = []
        self.assertEqual(rank(values, edges, host)["selected_mechanism"], "communication_execution_growth")

    def test_nonfinite_context_data_and_inconsistent_duration_are_rejected(self):
        for changed in (dict(reference_mean_ns="NaN"), dict(duration_ns=100000)):
            values = population("tasks")
            next(t for t in values if t["graph_id"] == "tasks19").update(changed)
            with self.assertRaises(ValueError):
                cohort_contexts(values)


if __name__ == "__main__":
    unittest.main()
