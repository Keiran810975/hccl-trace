from __future__ import annotations

from copy import deepcopy
from collections import Counter
import unittest

from test.run_gpt_overhead import ORDERS, metrics, summarize, validate_mapping, entry_code


class OverheadTests(unittest.TestCase):
    def samples(self):
        return [dict(rank=r, status='passed', warmup=10, iters=50, iteration_ns=[r + 1]*50,
            parameter_update_observed=True, parameter_samples=[1, 2], initialization={'sha': 'same'}) for r in range(4)]

    def test_balanced_orders(self):
        self.assertEqual(len(set(ORDERS)), 6)
        for position in range(3):
            self.assertEqual(Counter(row[position] for row in ORDERS), {'off': 2, 'semantic': 2, 'profile': 2})

    def test_real_mapping_columns_include_card_chip_logic_and_physical(self):
        text = 'NPU ID Chip ID Chip Logic ID Chip Phy-ID Chip Name\n'
        text += '\n'.join('{} 1 {} {} Ascend910'.format(c, r, p) for c, r, p in
                          ((4, 1, 9), (5, 3, 11), (6, 5, 13), (7, 7, 15)))
        text += '\n4 2 - - Mcu\n'
        validate_mapping(text)
        for bad in (text.replace('7 1 7 15', '7 1 7 7'), text + '7 1 7 15 Ascend910\n'):
            with self.assertRaises(ValueError):
                validate_mapping(bad)

    def test_entry_uses_existing_isolated_exec_group(self):
        code = entry_code('/workspace/owned', 'probe', ['/bin/true'])
        compile(code, '<entry>', 'exec')
        self.assertNotIn('setsid(', code)
        self.assertIn('os.getpgid(0)==os.getpid()', code)
        self.assertIn("'/workspace/owned/numerics/probe/launcher.json'", code)

    def test_slowest_rank_per_iteration_not_launcher_wall(self):
        rows = self.samples()
        rows[0]['iteration_ns'] = [10]*25 + [1]*25
        self.assertEqual(metrics(rows)['maximum_rank_mean_ns'], 7)

    def test_failed_or_partial_rank_is_not_dropped(self):
        for field, value in (('status', 'failed'), ('iters', 49), ('iteration_ns', [1]*49),
                             ('iteration_ns', [float('nan')]*50), ('parameter_samples', [3])):
            rows = self.samples()
            rows[0][field] = value
            with self.assertRaises(ValueError):
                metrics(rows)
        with self.assertRaises(ValueError):
            metrics(self.samples()[:3])

    def test_pairs_and_unstable_baseline(self):
        rows = [dict(block=b, mode=m, maximum_rank_mean_ns=(100 if b < 5 else 200)*factor)
                for b in range(6) for m, factor in (('off', 1), ('semantic', 1.1), ('profile', 1.3))]
        result = summarize(rows)
        self.assertAlmostEqual(result['paired_mean_percent']['semantic'], 10)
        self.assertAlmostEqual(result['paired_mean_percent']['profile'], 30)
        self.assertTrue(result['baseline_unstable'])
        for bad in (rows[:-1], rows[:-1] + [deepcopy(rows[0])]):
            with self.assertRaises(ValueError):
                summarize(bad)


if __name__ == '__main__':
    unittest.main()
