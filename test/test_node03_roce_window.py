from __future__ import annotations

import unittest
import json
from pathlib import Path
import tempfile

from test.node03_roce_window import baseline_active, counters, card_processes, chip_processes, Window


class RoceWindowTests(unittest.TestCase):
    def test_explicit_chip_process_output_fails_closed(self):
        self.assertEqual(chip_processes('\tNo process in device.\n'), set())
        self.assertEqual(chip_processes('| Process ID | Process name | Memory |\n| 123 | python | 64 |\n'), {123})
        self.assertEqual(chip_processes('Process ID    Process name    Memory\n123 python 64\n'), {123})
        self.assertEqual(chip_processes('\tProcess id:1850406 Process name:hccl-diagnose     Process memory(MB):116\n'), {1850406})
        self.assertEqual(chip_processes('Process id:11 Process name:hccl-diagnose Process memory(MB):116\n'
                                       'Process id:22 Process name:python Process memory(MB):2048\n'), {11, 22})
        for text in ('', 'query failed', '| Process ID | Name |\n', '| Process ID | Name |\n| unknown | python |\n'):
            with self.assertRaises(ValueError):
                chip_processes(text)
        for text in ('Process id:1 Process name:python Process memory(MB):64\nunknown row\n',
                     'Process id:1 Process name:python Process memory(MB):unknown\n'):
            with self.assertRaises(ValueError):
                chip_processes(text)

    def test_both_target_chips_are_checked_and_unknown_process_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); (root/'hold').mkdir(); (root/'gpt-output/runtime').mkdir(parents=True)
            (root/'hold/device-1.json').write_text(json.dumps(dict(pid=11)))
            (root/'gpt-output/runtime/rank-0.json').write_text(json.dumps(dict(pid=22)))
            window = Window.__new__(Window); window.root = root
            seen = []
            def query(command):
                seen.append(tuple(command))
                pid = 11 if command[-1] == '0' else 22
                return 'Process id:%d Process name:hccl-diagnose Process memory(MB):116\n' % pid
            window.run = query
            window.own_processes()
            self.assertEqual({x[-1] for x in seen}, {'0', '1'})
            self.assertTrue(all(x[4:6] == ('-i', '4') for x in seen))
            window.run = lambda command: 'Process ID  Process name\n33 foreign\n'
            with self.assertRaises(ValueError):
                window.own_processes()

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
