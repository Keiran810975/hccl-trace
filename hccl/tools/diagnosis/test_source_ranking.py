"""Source ranking uses reported execution evidence, never injection locations."""
from __future__ import annotations

from copy import deepcopy
from decimal import Decimal
import unittest

from .source_ranking import rank_regions
from .task_classifier import EXTERNAL, INTERNAL, UNRESOLVED


def root(identifier, *, iteration=8, rank=0, node="node0", delta=20, targets=("wait",), **extra):
    return dict(root_id=identifier, graph_id=identifier, node_id=node, user_rank=rank,
                group_id="foreground", iteration=iteration, observed_start_ns=iteration * 1000,
                observed_stop_ns=iteration * 1000 + 100, delta_ns=str(delta),
                diagnosis_category=INTERNAL, primary_eligible=True, affected_wait_graph_ids=list(targets), **extra)


def wait(identifier="wait", delta=1000):
    return dict(graph_id=identifier, delta_ns=str(delta), reference_count=5, duration_slow=True)


class SourceRankingTests(unittest.TestCase):
    def test_coherent_region_beats_isolated_fanout_and_model_gain(self):
        isolated = root("noise", iteration=5, delta=35, targets=("wait", "other"),
                        affected_rank_count=100, modeled_execution_gain_ns=100000)
        roots = [isolated, root("b", iteration=9), root("a")]
        regions = rank_regions(roots, [wait(), wait("other")])
        self.assertEqual([r["root_id"] for r in roots], ["a", "b", "noise"])
        self.assertEqual(regions[0]["iterations"], [8, 9])
        self.assertEqual(Decimal(regions[0]["ranking_execution_budget_ns"]), 40)
        self.assertIsNone(regions[0]["workload_loss_ns"])
        self.assertFalse(regions[0]["physical_cause_proven"])

    def test_budget_is_bounded_and_fanout_does_not_multiply_it(self):
        roots = [root("large", delta=200, targets=("wait", "other", "wait"))]
        rank_regions(roots, [wait(delta=30), wait("other", 50)])
        self.assertEqual(Decimal(roots[0]["ranking_execution_budget_ns"]), 50)
        small = root("small", delta=2)
        rank_regions([small], [wait(delta=100)])
        self.assertEqual(Decimal(small["supported_wait_excess_beyond_source_growth_ns"]), 98)
        self.assertNotIn("supported_wait_unexplained_lower_bound_ns", small)

    def test_regions_keep_nodes_ranks_groups_and_iteration_gaps_separate(self):
        roots = [root("a"), root("b", iteration=10), root("c", rank=1), root("d", node="node1")]
        roots.append(dict(root("e"), group_id="background"))
        self.assertEqual(len(rank_regions(roots, [wait()])), 5)

    def test_duplicate_execution_is_not_counted_twice(self):
        roots = [root("a"), dict(root("b"), graph_id="a")]
        region, = rank_regions(roots, [wait()])
        self.assertEqual(region["unique_execution_count"], 1)
        self.assertEqual(Decimal(region["ranking_execution_budget_ns"]), 20)

    def test_external_and_unresolved_are_not_promoted(self):
        roots = [dict(root("host", delta=100000), diagnosis_category=EXTERNAL, primary_eligible=False),
                 dict(root("gap", delta=100000), diagnosis_category=UNRESOLVED, primary_eligible=False),
                 root("internal", modeled_execution_gain_ns=0)]
        region, = rank_regions(roots, [wait()])
        self.assertEqual(region["candidate_ids"], ["internal"])
        self.assertEqual(roots[0]["root_id"], "internal")
        self.assertEqual(roots[1]["diagnosis_category"], EXTERNAL)
        self.assertEqual(roots[2]["diagnosis_category"], UNRESOLVED)

    def test_reranking_clears_stale_regions_and_is_deterministic(self):
        roots = [root("b"), root("a", rank=1)]
        rank_regions(roots, [wait()])
        first = deepcopy(roots)
        roots.reverse()
        rank_regions(roots, [wait()])
        self.assertEqual(roots, first)
        roots[0]["primary_eligible"] = False
        rank_regions(roots, [wait()])
        ineligible = next(r for r in roots if not r["primary_eligible"])
        self.assertNotIn("source_region_id", ineligible)

    def test_uncompared_wait_is_not_ranking_support(self):
        item = root("a")
        rank_regions([item], [dict(wait(), reference_count=4)])
        self.assertEqual(Decimal(item["ranking_execution_budget_ns"]), 0)


if __name__ == "__main__":
    unittest.main()
