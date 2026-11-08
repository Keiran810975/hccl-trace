from __future__ import annotations

import tempfile
from pathlib import Path
from unittest import TestCase
from unittest.mock import patch

from test.run_gpt_profile_trim import CONFIGS, ORDERS, PROBES, choose_probe, inspect_capture, summarize, verified_prior_selection


class ProfileTrimTests(TestCase):
    def test_probe_changes_are_explicit_and_leave_l1_default_candidate(self):
        self.assertEqual(PROBES, ('no_pmu', 'no_task', 'no_acl'))
        self.assertIn('--ai-core=off', CONFIGS['no_pmu'])
        self.assertIn('--ascendcl=on', CONFIGS['no_pmu'])
        self.assertIn('--task-time=l1', CONFIGS['no_pmu'])
        self.assertIn('--task-time=off', CONFIGS['no_task'])
        self.assertIn('--ascendcl=off', CONFIGS['no_acl'])
        self.assertNotIn('--task-time=l0', {x for v in CONFIGS.values() for x in v})

    def test_selection_requires_compatibility_and_never_uses_speed(self):
        rows = [dict(configuration=m, eligible=True, counts=dict(COMPUTE_TASK_INFO=n,TASK=100,CANN_API=100,TASK_PMU_INFO=0),
                     measured=dict(maximum_rank_mean_ns=t))
                for m,n,t in [('no_pmu',100,1),('no_task',0,999),('no_acl',100,2)]]
        self.assertEqual(choose_probe(rows), 'no_task')
        rows[1]['eligible'] = False
        rows[2]['counts']['CANN_API'] = 10
        self.assertEqual(choose_probe(rows), 'no_acl')
        with self.assertRaises(ValueError):
            choose_probe([dict(configuration='no_task',eligible=False)])

    def test_frozen_complete_blocks_include_missing_factorial_control(self):
        self.assertEqual(len(ORDERS),3)
        for row in ORDERS:
            self.assertEqual(set(row),{'off','semantic','full_nosem','full','trim'})
        values=dict(off=100,semantic=110,full_nosem=120,full=150,trim=125)
        rows=[dict(block=b,mode=m,maximum_rank_mean_ns=values[m]) for b,order in enumerate(ORDERS) for m in order]
        result=summarize(rows)
        self.assertEqual(result['paired_means']['interaction_ns'],20)
        self.assertAlmostEqual(result['paired_means']['trim_vs_full_percent'],-100/6)
        for bad in (rows[:-1],rows[:-1]+[rows[0]]):
            with self.assertRaises(ValueError):summarize(bad)

    def test_missing_profiler_evidence_cannot_qualify(self):
        with tempfile.TemporaryDirectory() as directory:
            result=inspect_capture(Path(directory),'probe-no-task')
        self.assertFalse(result['eligible'])
        self.assertIn('four consolidated',result['error'])

    def test_only_previously_verified_unrun_benchmark_is_eligible(self):
        from copy import deepcopy
        value=dict(status='verified_probe_only_benchmark_blocked',training_runs=3,numerical_ranks_passed=12,
            benchmark_runs=0,unrun_benchmark_samples=15,selected_configuration='no_pmu',probes=[
                dict(configuration='no_pmu',eligible=True,counts=dict(TASK=100),
                    merge_stats=dict(semantic_total=224840,exact_matched=224840),binding=dict(sdk_bound_calls=3072)),
                dict(configuration='no_task',eligible=False),dict(configuration='no_acl',eligible=False)])
        self.assertEqual(verified_prior_selection(value),'no_pmu')
        for key,bad in (('benchmark_runs',1),('numerical_ranks_passed',11),('status','unverified')):
            changed=deepcopy(value);changed[key]=bad
            with self.assertRaises(ValueError):verified_prior_selection(changed)
        value['probes'][0]['merge_stats']['exact_matched']-=1
        with self.assertRaises(ValueError):verified_prior_selection(value)
