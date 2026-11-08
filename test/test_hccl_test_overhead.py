from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from test.hccl_test_overhead import plan, parse_results, summarize, SIZES, OPERATORS, ORDERS
from test.node03_device_guard import Guard, scope, HCCL_TEST_OVERHEAD_ROOT
from test.run_hccl_test_overhead import launcher_entry, validate_probe_checkpoint


class HcclTestOverheadTests(unittest.TestCase):
    @unittest.skipUnless(sys.platform=='linux','launcher attestation uses Linux /proc')
    def test_launcher_emits_parseable_json_and_private_process_group(self):
        with tempfile.TemporaryDirectory() as directory:
            code=launcher_entry(directory,'cpu-only',[sys.executable,'-c','pass'])
            result=subprocess.run([sys.executable,'-c',code],start_new_session=True)
            self.assertEqual(result.returncode,0)
            self.assertGreater(json.loads((Path(directory)/'numerics/cpu-only/launcher.json').read_text())['pid'],0)

    def test_frozen_native_scope_and_sizes(self):
        p=plan()
        self.assertEqual(p['nodes'],[0]);self.assertEqual(p['physical_cards'],[4,5,6,7])
        self.assertEqual(p['runtime_devices'],[1,3,5,7]);self.assertEqual(p['requested_samples'],27)
        self.assertEqual(SIZES[-1],512*1024**2)

    def test_probe_recovery_cannot_repeat_any_performance_sample(self):
        previous=dict(status='failed',requested=27,completed=[],probes=[],source_snapshot_sha256='a')
        probe=dict(name='probe-all_reduce',operator='all_reduce',no_npu_rerun=True,original_source_snapshot_sha256='a',
            db_sha256_before_after={'one':'a','two':'b','three':'c','four':'d'},
            profile_evidence=dict(eligible=True,profiler_db_count=4,semantic_total=8760,exact_matched=8760))
        self.assertIs(validate_probe_checkpoint(previous,probe),probe)
        for change in (dict(completed=[{}]),dict(status='running'),dict(source_snapshot_sha256='other')):
            with self.assertRaises(ValueError):validate_probe_checkpoint(dict(previous,**change),probe)
        with self.assertRaises(ValueError):validate_probe_checkpoint(previous,dict(probe,no_npu_rerun=False))

    def test_native_output_requires_every_correct_size(self):
        native='data_size avg_time(us) alg_bandwidth(GB/s) check_result\n'+''.join('%d 10.5 1.2 success\n'%n for n in SIZES)
        self.assertEqual(len(parse_results(native)),9)
        self.assertEqual(len(parse_results(native.replace(' 10.5 1.2 success',' | 10.5 | 1.2 | success'))),9)
        for bad in (native.replace('success','failed',1),native.replace('10.5','nan',1),
                    native+native,native.rsplit('\n',2)[0]+'\n',native.replace('1.2','0',1)):
            with self.assertRaises(ValueError):parse_results(bad)
        with self.assertRaises(ValueError):parse_results(native+'local rank_id 2, check result failed, 8192 | 10 | 1 | failed\n')

    def test_paired_summary_never_drops_missing_samples(self):
        rows=[dict(block=b,operator=op,mode=m,results=[dict(bytes=n,average_us=str({'off':10,'semantic':11,'profile':12}[m])) for n in SIZES])
              for b,order in enumerate(ORDERS) for op in OPERATORS for m in order]
        report=summarize(rows)
        self.assertEqual(len(report['results']),27)
        self.assertEqual(report['results'][0]['median_paired_percent']['semantic'],10)
        self.assertEqual(report['results'][0]['median_paired_percent']['profile'],20)
        with self.assertRaises(ValueError):summarize(rows[:-1])
        with self.assertRaises(ValueError):summarize(rows[:-1]+[rows[0]])

    def test_new_root_is_node0_only_and_requires_exact_lowlog_build(self):
        root=Path('/home/commTeam/zjy/zjy-new-workspace')/HCCL_TEST_OVERHEAD_ROOT
        self.assertEqual(scope(root,'liteserver-560t-0'),root.resolve())
        with self.assertRaises(ValueError):scope(Path('/home/zjy-new/workspace')/root.name,'liteserver-560t-3')
        deployment=dict(profile=plan()['profile'],cards=[4,5,6,7])
        auth=dict(nodes=[0],physical_cards=[4,5,6,7],temporary_signature_user_confirmed=True,restore_required=True)
        build=dict(status='built',device_sha256='a'*64,host_sha256='b'*64,verified_current_producer_files={'x':'y'},host_libraries={})
        def read(path,*args,**kwargs):return json.dumps(deployment if path.name=='deployment.json' else auth if path.name=='authorization.json' else build)
        with patch('test.node03_device_guard.scope',return_value=root),patch.object(Path,'read_text',read):
            with self.assertRaisesRegex(ValueError,'tested low-log'):Guard(root)
            deployment['profile']='gpt-lowlog-v1'
            with self.assertRaisesRegex(ValueError,'profile'):Guard(root)


if __name__=='__main__':unittest.main()
