from __future__ import annotations

import unittest
from .multinode_dual_suite import plan, validate_case


class MultiNodeDualSuiteTests(unittest.TestCase):
    def test_frozen_six_cases_and_one_iteration_interference(self):
        cases = plan()['cases']
        self.assertEqual(len(cases),6)
        self.assertEqual([c['injection']['kind'] for c in cases], ['normal','copy_contention','communication_contention','compute_contention','progress_delay','bandwidth_limit'])
        for case in cases:
            validate_case(case)
            self.assertEqual(case['workload']['warmup'],10)
            self.assertEqual(case['workload']['iters'],50)
            self.assertEqual(case['topology']['ranks_per_node'],4)
        self.assertEqual(cases[2]['injection']['declared_affected_ranks'],[0,4])
        self.assertEqual(cases[4]['injection']['delay_ms'],500)
        self.assertEqual(cases[1]['injection']['buffer_mib'],2048)
        self.assertEqual(cases[3]['injection']['matrix_size'],8192)
        cases[1]['injection']['buffer_mib']=1
        with self.assertRaises(ValueError): validate_case(cases[1])
