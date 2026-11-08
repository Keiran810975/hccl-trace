from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from unittest import TestCase
from unittest.mock import patch

from test.run_gpt_profile_attribution import (MODES, ORDERS, ROOT, profiler_flags, summarize,
    LOGFILTER_ROOT, LOGFILTER_MODES, LOGFILTER_ORDERS, LOGFILTER_CONTRASTS,
    LOWLOG_DIRECTORY, LOWLOG_MODES, LOWLOG_ORDERS, LOWLOG_CONTRASTS)
from test.node03_device_guard import scope


class AttributionTests(TestCase):
    def test_lowlog_has_three_complete_unchanged_workload_comparisons(self):
        self.assertEqual(scope(LOWLOG_DIRECTORY,'liteserver-560t-0'),LOWLOG_DIRECTORY.resolve())
        with self.assertRaises(ValueError):
            scope(Path('/home/zjy-new/workspace')/LOWLOG_DIRECTORY.name,'liteserver-560t-3')
        self.assertEqual(len(LOWLOG_ORDERS),3)
        for order in LOWLOG_ORDERS:
            self.assertEqual(set(order),set(LOWLOG_MODES))
        self.assertEqual(LOWLOG_MODES['capture_warn']['log_level'],2)
        self.assertEqual(LOWLOG_MODES['capture_info']['log_level'],1)
        self.assertIn('--ai-core=off',profiler_flags('capture_warn',LOWLOG_MODES))
        values=dict(off_warn=100,semantic_warn=101,capture_warn=102,capture_info=300)
        rows=[dict(block=b,mode=m,maximum_rank_mean_ns=values[m]) for b,o in enumerate(LOWLOG_ORDERS) for m in o]
        result=summarize(rows,LOWLOG_ORDERS,LOWLOG_MODES,LOWLOG_CONTRASTS)
        self.assertEqual(result['repetitions_per_mode'],3)
        self.assertAlmostEqual(result['mean_contrasts']['capture_vs_off']['percent'],2)
        with self.assertRaises(ValueError):
            summarize(rows[:-1],LOWLOG_ORDERS,LOWLOG_MODES,LOWLOG_CONTRASTS)

    def test_hccl_only_logging_is_one_separate_node0_root(self):
        self.assertEqual(scope(LOGFILTER_ROOT,'liteserver-560t-0'),LOGFILTER_ROOT.resolve())
        with self.assertRaises(ValueError):
            scope(Path('/home/zjy-new/workspace')/LOGFILTER_ROOT.name,'liteserver-560t-3')
        for value in LOGFILTER_MODES.values():
            self.assertEqual(value['log_level'],2)
            self.assertEqual(value['module_log_level'],'HCCL=1')
        rows=[dict(block=b,mode=m,maximum_rank_mean_ns=100 if m=='off_hcclinfo' else 110)
            for b,o in enumerate(LOGFILTER_ORDERS) for m in o]
        result=summarize(rows,LOGFILTER_ORDERS,LOGFILTER_MODES,LOGFILTER_CONTRASTS)
        self.assertAlmostEqual(result['mean_contrasts']['profiler_plus_semantic']['percent'],10)
    def test_one_exact_node0_root(self):
        self.assertEqual(scope(ROOT,'liteserver-560t-0'),ROOT.resolve())
        for root,host in ((ROOT.with_name(ROOT.name+'-other'),'liteserver-560t-0'),
                (Path('/home/zjy-new/workspace')/ROOT.name,'liteserver-560t-3')):
            with self.assertRaises(ValueError):
                scope(root,host)

    def test_counterbalanced_two_blocks_never_change_workload(self):
        self.assertEqual(ORDERS[1],tuple(reversed(ORDERS[0])))
        self.assertEqual(len(ORDERS[0]),7)
        for mode in MODES:
            self.assertIn('--ai-core=off',profiler_flags(mode))
            self.assertIn('--task-time=l1',profiler_flags(mode))
        self.assertEqual([m for m,v in MODES.items() if v['trace']],['semantic_warn'])

    def test_adjacent_arm_contrasts_and_complete_denominators(self):
        values=dict(off_warn=100,task_warn=110,api_warn=130,hccl_warn=160,semantic_warn=165,hccl_info=180,off_info=105)
        rows=[dict(block=b,mode=m,maximum_rank_mean_ns=values[m]*1000000) for b,o in enumerate(ORDERS) for m in o]
        result=summarize(rows)
        self.assertEqual(result['mean_contrasts']['task_collection']['ms'],10)
        self.assertEqual(result['mean_contrasts']['acl_increment']['ms'],20)
        self.assertEqual(result['mean_contrasts']['hccl_increment']['ms'],30)
        self.assertEqual(result['mean_contrasts']['semantic_increment']['ms'],5)
        for bad in (rows[:-1],rows[:-1]+[rows[0]]):
            with self.assertRaises(ValueError):
                summarize(bad)

    def test_attribution_guard_requires_exact_profile_and_restore(self):
        from test.node03_device_guard import Guard
        import hashlib
        import json
        content=b'producer'
        build=dict(status='built',device_sha256='a'*64,host_sha256='b'*64,
            verified_current_producer_files={'hcomm/source.cc':hashlib.sha256(content).hexdigest()},
            host_libraries={'libhcomm.so':'b'*64,'libhccl_alg.so':'c'*64,'libhccl_plf.so':'d'*64})
        deployment=dict(profile='gpt-overhead-attribution-v1',cards=[4,5,6,7])
        auth=dict(nodes=[0],physical_cards=[4,5,6,7],temporary_signature_user_confirmed=True,restore_required=True)
        def read(path,*args,**kwargs):
            return json.dumps(deployment if path.name=='deployment.json' else auth if path.name=='authorization.json' else build)
        with patch('test.node03_device_guard.scope',return_value=ROOT),patch.object(Path,'read_text',read),patch.object(Path,'read_bytes',return_value=content):
            self.assertEqual(Guard(ROOT).cards,(4,5,6,7))
            deployment['profile']='gpt-overhead-benchmark-v1'
            with self.assertRaises(ValueError):
                Guard(ROOT)
            deployment['profile']='gpt-overhead-attribution-v1'
            auth['restore_required']=False
            with self.assertRaises(ValueError):
                Guard(ROOT)
        auth['restore_required']=True
        deployment['profile']='gpt-overhead-logfilter-v1'
        with patch('test.node03_device_guard.scope',return_value=LOGFILTER_ROOT),patch.object(Path,'read_text',read),patch.object(Path,'read_bytes',return_value=content):
            self.assertEqual(Guard(LOGFILTER_ROOT).cards,(4,5,6,7))
            deployment['profile']='gpt-overhead-attribution-v1'
            with self.assertRaises(ValueError):
                Guard(LOGFILTER_ROOT)
        deployment['profile']='gpt-lowlog-v1'
        with patch('test.node03_device_guard.scope',return_value=LOWLOG_DIRECTORY),patch.object(Path,'read_text',read),patch.object(Path,'read_bytes',return_value=content):
            self.assertEqual(Guard(LOWLOG_DIRECTORY).cards,(4,5,6,7))
            auth['nodes']=[0,3]
            with self.assertRaises(ValueError):
                Guard(LOWLOG_DIRECTORY)
