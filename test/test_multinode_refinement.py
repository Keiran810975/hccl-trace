from __future__ import annotations

import unittest

from .audit_roce_injection_window import confirmed_start
from .evaluate_multinode_refinement import evaluate
from .node03_evaluate import network_active_interval


class RefinementEvidenceTests(unittest.TestCase):
    def test_new_network_records_use_first_confirmed_limit_and_old_records_stay_unchanged(self):
        old = dict(started_raw_ns=30, finished_raw_ns=100)
        self.assertEqual(network_active_interval(old), (30, 100))
        current = dict(old, apply_returned_raw_ns=10, first_confirmed_limit_raw_ns=20)
        self.assertEqual(network_active_interval(current), (20, 100))
        with self.assertRaises(ValueError):
            network_active_interval(dict(current, first_confirmed_limit_raw_ns=5))

    def test_first_readback_not_later_counter_sampling_is_confirmed_active_start(self):
        control = dict(apply_returned_raw_ns=10, started_raw_ns=30)
        command = ["/usr/local/Ascend/driver/tools/hccn_tool", "-i", "9", "-shaping", "-g"]
        rows = [dict(command=command, returncode=0, started_raw_ns=11, raw_ns=20,
                     stdout="bw_limit[20000 Mbps], bw_max[200000 Mbps], bw_cur[20000 Mbps]\n"),
                dict(command=command, returncode=0, started_raw_ns=21, raw_ns=25,
                     stdout="bw_limit[20000 Mbps], bw_max[200000 Mbps], bw_cur[20000 Mbps]\n")]
        self.assertEqual(confirmed_start(rows, control, 9, 20000)["raw_ns"], 20)
        with self.assertRaises(ValueError):
            confirmed_start(rows, control, 8, 20000)
        with self.assertRaises(ValueError):
            confirmed_start(rows, control, 9, 100000)

    def test_evaluation_does_not_count_wrong_rank_or_boundary_touch_as_hit(self):
        candidate = dict(candidate_id="s", source_unit="execution_task", node_id="n", user_rank=1,
                         iteration=7, observed_start_ns=10, observed_stop_ns=20)
        report = dict(candidates=[candidate])
        self.assertFalse(evaluate(report, [dict(node_id="n", user_rank=0, start_ns=10, stop_ns=20)])[0]["hit"])
        self.assertFalse(evaluate(report, [dict(node_id="n", user_rank=1, start_ns=20, stop_ns=30)])[0]["hit"])
        self.assertTrue(evaluate(report, [dict(node_id="n", user_rank=1, start_ns=19, stop_ns=30)])[0]["hit"])
