from __future__ import annotations

import unittest

from test.node03_roce_window import baseline_active, counters, card_processes


class RoceWindowTests(unittest.TestCase):
    def test_real_pipe_columns_and_compact_process_rows(self):
        text = "| NPU Chip | Process id | Process name |\n| 4 1 | 1234 | hccl-diagnose |\n| 4 0 | 5678 | unknown |\n| 5 1 | 99 | other |\n"
        self.assertEqual(card_processes(text, 4), {1234, 5678})
        self.assertEqual(card_processes("Process id\n| 4 1 1234 hccl-diagnose |", 4), {1234})
        with self.assertRaises(ValueError):
            card_processes("missing process report", 4)
    def test_native_counters_are_explicit_and_never_cleared(self):
        values = counters("packet statistics:\nmac_tx_total_oct_num:100\nmac_rx_total_oct_num:90\nroce_tx_all_pkt_num:3\nroce_rx_all_pkt_num:2")
        self.assertEqual(values["mac_tx_total_oct_num"], 100)
        with self.assertRaises(ValueError):
            counters("mac_tx_total_oct_num:100")

    def test_only_a_real_foreground_egress_baseline_enables_the_limiter(self):
        before = dict(mac_tx_total_oct_num=0, mac_rx_total_oct_num=0, roce_tx_all_pkt_num=0, roce_rx_all_pkt_num=0)
        after = dict(before, mac_tx_total_oct_num=2 * 1024**2, roce_tx_all_pkt_num=99)
        proof = dict(node_id="node0", user_rank=0, physical_device_id=9, runtime_device_id=1,
                     foreground_only=True, numerics_passed=True, before=before, after=after)
        baseline_active(proof)
        for altered in (dict(proof, foreground_only=False), dict(proof, after=before), dict(proof, physical_device_id=11)):
            with self.assertRaises(ValueError):
                baseline_active(altered)


if __name__ == "__main__":
    unittest.main()
