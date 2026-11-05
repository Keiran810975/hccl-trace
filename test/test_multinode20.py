from __future__ import annotations

from copy import deepcopy
import json
import io
import hashlib
from pathlib import Path
import tarfile
import tempfile
import unittest

from test.multinode20_suite import plan, validate_case, effect_evidence, KINDS
from test.node03_gpt2_control import MultiNodeControl
from test.calibration_offload import case_name
from test.calibration_offload import verify_archive
from test.run_multinode20 import idle, validate_prestart_resume


class MultiNode20Tests(unittest.TestCase):
    def test_twenty_distinct_frozen_runs_without_compute_or_extra_baseline(self):
        p = plan()
        self.assertEqual(p, plan())
        self.assertEqual(p['requested_runs'], 20)
        self.assertEqual(len({c['case_id'] for c in p['cases']}), 20)
        for kind in KINDS:
            cases = [c for c in p['cases'] if c['injection']['kind'] == kind]
            self.assertEqual(len(cases), 5)
            self.assertEqual(len({(c['injection']['target_rank'], c['injection']['iteration'], c['injection']['bucket_selector_seed']) for c in cases}), 5)
        for c in p['cases']:
            validate_case(c)
            self.assertEqual((c['workload']['warmup'], c['workload']['iters']), (10, 50))
            self.assertEqual(c['topology']['ranks_per_node'], 4)
            self.assertEqual(c['experiment_contract']['source_policy'], 'dual-v2')
            changed = deepcopy(c)
            changed['injection']['iteration'] += 1
            with self.assertRaises(ValueError):
                validate_case(changed)

    def test_five_distinct_global_rank_pairs_and_bounded_control(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for i, case in enumerate(c for c in plan()['cases'] if c['injection']['kind'] == 'communication_contention'):
                path = root / ('case%d.json' % i)
                path.write_text(json.dumps(case))
                inj = case['injection']
                self.assertEqual(inj['declared_affected_ranks'], [inj['peer_rank'], inj['target_rank']])
                self.assertEqual(inj['buffer_mib'], 1024)
                for rank in range(8):
                    control = MultiNodeControl(path, root / ('private%d-%d' % (i, rank)), rank, {rank: 1})
                    self.assertEqual(control.owner, rank in inj['declared_affected_ranks'])
                    self.assertTrue(control.bounded_interference)
                    self.assertTrue(control.communication_scoped)
                    control.close()

    def test_archive_allowlist_is_only_twenty_new_attempts(self):
        for i in range(901, 921):
            self.assertEqual(case_name('hccl-diagnose-node03-20261105-' + str(i)), 'hccl-diagnose-node03-20261105-' + str(i))
        for name in ['hccl-diagnose-node03-20261105-900', 'hccl-diagnose-node03-20261105-921']:
            with self.assertRaises(ValueError):
                case_name(name)

    def test_copy_gap_does_not_prove_effect(self):
        c = plan()['cases'][0]
        evaluation = dict(windows=[dict(node_id='n', user_rank=4, start_ns=100, stop_ns=400)])
        row = dict(graph_id='t', node_id='n', user_rank='4', observed_start_ns='190', observed_stop_ns='210',
                   task_domain='hccl_internal', stage='measured', reference_count='5', duration_slow='True',
                   task_kind='sdma', slowdown_factor='3', iteration='12')
        activity = dict(operations=2, max_error=0, started_raw_ns=100,
                        copy_host_envelopes_raw_ns=[[100, 150], [250, 300]])
        self.assertFalse(effect_evidence(c, evaluation, [row, dict(row, graph_id='u')], [activity])['effect_gate_passed'])
        row.update(observed_start_ns='110', observed_stop_ns='130')
        self.assertTrue(effect_evidence(c, evaluation, [row, dict(row, graph_id='u')], [activity])['effect_gate_passed'])

    def test_zero_utilization_is_not_idle(self):
        self.assertFalse(idle(dict(registry=False, npu='AICore 0', free=10**12), [4]))
        self.assertFalse(idle(dict(registry=True, npu='No running processes found in NPU 4', free=10**12), [4]))

    def test_prestart_continuation_forbids_any_started_training_or_second_resume(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / 'queue';root.mkdir()
            previous = dict(status='stopped', completed=0, cases=[], active_case=None, active_directory=None,
                error='target resources changed after Node3 release; no repeated stop')
            (root/'state.json').write_text(json.dumps(previous))
            self.assertEqual(validate_prestart_resume(root), previous)
            current = root.parent/'hccl-diagnose-node03-20261105-901';current.mkdir()
            (current/'authorized-state.json').write_text('{}')
            with self.assertRaises(ValueError):validate_prestart_resume(root)
            (current/'authorized-state.json').unlink()
            (root/'prestart-resume.json').write_text('{}')
            with self.assertRaises(ValueError):validate_prestart_resume(root)

    def test_lossless_dedup_accepts_only_verified_preceding_regular_content(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'replay.tar.gz'
            payload = b'actual profiler bytes'
            with tarfile.open(path, 'w:gz') as archive:
                item = tarfile.TarInfo('capture/original.db');item.size=len(payload)
                archive.addfile(item, io.BytesIO(payload))
                link = tarfile.TarInfo('peer/copy.db');link.type=tarfile.LNKTYPE;link.linkname=item.name
                archive.addfile(link)
            record = dict(size=len(payload), sha256=hashlib.sha256(payload).hexdigest())
            manifest = dict(content_deduplicated=True,files={'capture/original.db':record,'peer/copy.db':dict(record)})
            self.assertEqual(verify_archive(path, manifest), set(manifest['files']))
            del manifest['content_deduplicated']
            with self.assertRaises(ValueError):verify_archive(path, manifest)
            manifest['content_deduplicated']=True
            manifest['files']['peer/copy.db']['sha256']='0'*64
            with self.assertRaises(ValueError):verify_archive(path, manifest)


if __name__ == '__main__':
    unittest.main()
