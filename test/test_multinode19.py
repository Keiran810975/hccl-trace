"""The manual low-log continuation cannot repeat or rewrite the stopped first case."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from test.multinode20_suite import (plan, continuation_plan, queue_plan, lowlog_capture,
    ROOT_NAME, CONTINUATION_ROOT, CONTINUATION_PROFILE, CONTINUATION_CASES, LOWLOG_CAPTURE)
from test.run_multinode20 import verify_continuation_origin, validate_evaluated_resume
from test.node03_device_guard import Guard
from test.calibration_offload import case_name


class Multinode19Tests(unittest.TestCase):
    def test_only_original_nineteen_remaining_cases_and_frozen_rules(self):
        old, new = plan(), continuation_plan()
        self.assertEqual(new['cases'], old['cases'][1:])
        self.assertEqual(new['requested_runs'], 19)
        self.assertEqual(new['diagnosis'], old['diagnosis'])
        self.assertFalse(new['origin_result_included'])
        self.assertFalse(new['resource_scope']['stop_node3_target_processes_once_after_node0_idle'])
        self.assertEqual(queue_plan(Path(CONTINUATION_ROOT)), new)
        self.assertEqual(queue_plan(Path(ROOT_NAME)), old)
        with self.assertRaises(ValueError):queue_plan(Path('other'))

    def test_new_archive_scope_excludes_first_case_and_queue_root(self):
        self.assertEqual(len(CONTINUATION_CASES), 19)
        for name in CONTINUATION_CASES:self.assertEqual(case_name(name), name)
        for number in (1000, 1001, 1021):
            with self.assertRaises(ValueError):case_name('hccl-diagnose-node03-20261106-'+str(number))

    def test_lowlog_configuration_is_explicit_and_does_not_change_old_defaults(self):
        self.assertFalse(lowlog_capture(Path('hccl-diagnose-node03-20261105-902')))
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/sorted(CONTINUATION_CASES)[0];root.mkdir()
            value=dict(profile=CONTINUATION_PROFILE,capture_policy=dict(LOWLOG_CAPTURE))
            p=root/'deployment.json';p.write_text(json.dumps(value))
            self.assertTrue(lowlog_capture(root))
            value['capture_policy']['ai_core']='on';p.write_text(json.dumps(value))
            with self.assertRaises(ValueError):lowlog_capture(root)

    def test_origin_requires_stopped_exactly_one_case_and_unused_remaining_attempts(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/CONTINUATION_ROOT;root.mkdir()
            old=root.parent/ROOT_NAME;old.mkdir()
            state=dict(status='stopped',completed=1,active_case=None,active_directory=None,
                cases=[dict(case_id=plan()['cases'][0]['case_id'])])
            p=old/'state.json';p.write_text(json.dumps(state))
            (old/'launch.json').write_text(json.dumps(dict(pid=2147483647,start_ticks=1)))
            (root/'origin.json').write_text(json.dumps(dict(origin_queue=str(old),training_repeated=False,
                files={'state.json':hashlib.sha256(p.read_bytes()).hexdigest()})))
            first=old.parent/'hccl-diagnose-node03-20261105-901';first.mkdir()
            (first/'offload-receipt.json').write_text(json.dumps(dict(status='verified')))
            self.assertEqual(verify_continuation_origin(root), state)
            second=old.parent/'hccl-diagnose-node03-20261105-902';second.mkdir()
            (second/'authorized-state.json').write_text('{}')
            with self.assertRaises(ValueError):verify_continuation_origin(root)
            (second/'authorized-state.json').unlink()
            state['completed']=2;p.write_text(json.dumps(state))
            with self.assertRaises(ValueError):verify_continuation_origin(root)

    def test_guard_pins_new_device_and_manual_authorization(self):
        root=Path('/home/commTeam/zjy/zjy-new-workspace/hccl-diagnose-node03-20261106-1002')
        content=b'producer'
        build=dict(status='built',device_sha256='b68ef612370ebb9c635e9fb9d94ddaf977be81a3d609d0e35936f20e41ceebd2',
            host_sha256='b'*64,verified_current_producer_files={'hcomm/source.cc':hashlib.sha256(content).hexdigest()},
            host_libraries={'libhcomm.so':'b'*64,'libhccl_alg.so':'c'*64,'libhccl_plf.so':'d'*64})
        deployment=dict(profile=CONTINUATION_PROFILE,capture_policy=dict(LOWLOG_CAPTURE))
        auth=dict(nodes=[0,3],physical_cards=[4,5,6,7],restore_required=True,
            temporary_signature_user_confirmed=True,manual_continuation_user_confirmed=True,
            node3_target_process_stop_user_confirmed=False)
        def read(path,*args,**kwargs):
            return json.dumps(deployment if path.name=='deployment.json' else auth if path.name=='authorization.json' else build)
        with patch('test.node03_device_guard.scope',return_value=root),patch.object(Path,'is_file',return_value=True),patch.object(Path,'read_text',read),patch.object(Path,'read_bytes',return_value=content):
            self.assertEqual(Guard(root).cards,(4,5,6,7))
            auth['node3_target_process_stop_user_confirmed']=True
            with self.assertRaises(ValueError):Guard(root)
            auth['node3_target_process_stop_user_confirmed']=False
            build['device_sha256']='a'*64
            with self.assertRaises(ValueError):Guard(root)

    def test_evaluation_recovery_requires_passed_sealed_capture_and_is_once_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/CONTINUATION_ROOT;root.mkdir()
            current=root.parent/'hccl-diagnose-node03-20261106-1002';current.mkdir()
            state=dict(status='stopped',completed=0,cases=[],active_directory=str(current))
            (root/'state.json').write_text(json.dumps(state))
            for name in ('authorized-state.json','preflight-state.json'):
                (current/name).write_text(json.dumps(dict(status='passed')))
            (current/'report').mkdir();p=current/'report/root_causes.json';p.write_text('{}')
            (current/'diagnosis-seal.json').write_text(json.dumps(dict(truth_accessed=False,
                sha256={'root_causes.json':hashlib.sha256(p.read_bytes()).hexdigest()})))
            self.assertEqual(validate_evaluated_resume(root),state)
            (root/'evaluation-continuation.json').write_text('{}')
            with self.assertRaises(ValueError):validate_evaluated_resume(root)
            (root/'evaluation-continuation.json').unlink();p.write_text('{"changed":true}')
            with self.assertRaises(ValueError):validate_evaluated_resume(root)


if __name__ == '__main__':
    unittest.main()
