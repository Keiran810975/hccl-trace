from __future__ import annotations

import unittest

from .evaluate_candidate_screening import evaluate


class EvaluationTests(unittest.TestCase):
    def test_strict_ratio_and_no_empty_success(self):
        roots = [dict(root_id=str(i), user_rank=0, node_id="n", device_id=4,
                      observed_start_ns=10 if i < 3 else 30, observed_stop_ns=20 if i < 3 else 40)
                 for i in range(4)]
        windows = [dict(node_id="n", target_ranks=[0], start_ns=10, stop_ns=20)]
        selection = dict(policy="test", selected_candidate_ids=[r["root_id"] for r in roots])
        result = evaluate(roots, selection, windows)
        self.assertEqual(result["precision"], "0.75")
        self.assertFalse(result["strictly_above_75_percent"])
        selection["selected_candidate_ids"] = []
        result = evaluate(roots, selection, windows)
        self.assertIsNone(result["precision"])
        self.assertFalse(result["any_hit"])
        self.assertEqual(result["lost_hit_candidates"], 3)

    def test_no_peer_rank_credit_or_boundary_touch_credit(self):
        root = dict(root_id="s", user_rank=5, peer_rank=4, node_id="n", device_id=3,
                    observed_start_ns=100, observed_stop_ns=200)
        selected = dict(policy="test", selected_candidate_ids=["s"])
        window = dict(node_id="n", target_ranks=[4], start_ns=100, stop_ns=200)
        self.assertEqual(evaluate([root], selected, [window])["hits"], 0)
        window.update(target_ranks=[5], start_ns=200, stop_ns=300)
        self.assertEqual(evaluate([root], selected, [window])["hits"], 0)
        window.update(start_ns=50, stop_ns=150)
        self.assertEqual(evaluate([root], selected, [window], profiler_offsets={("n", 3): 50})["hits"], 1)


if __name__ == "__main__":
    unittest.main()
