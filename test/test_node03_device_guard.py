from __future__ import annotations

from pathlib import Path
import json
import unittest
from unittest.mock import Mock, patch

from test.node03_device_guard import CARDS, Guard, policy, scope, own_transition


class DeviceGuardTests(unittest.TestCase):
    def test_new_producer_probe_is_node0_and_three_whole_cards_only(self):
        root = Path('/home/commTeam/zjy/zjy-new-workspace/semantic-coverage-20261102')
        self.assertEqual(scope(root, 'liteserver-560t-0'), root.resolve())
        with self.assertRaises(ValueError):
            scope(Path('/home/zjy-new/workspace/semantic-coverage-20261102'), 'liteserver-560t-3')
        receipt = dict(status='built', device_sha256='a'*64, host_sha256='b'*64,
                       host_libraries={'libhcomm.so':'b'*64, 'libhccl_alg.so':'c'*64, 'libhccl_plf.so':'d'*64})
        with patch('test.node03_device_guard.scope', return_value=root), patch.object(Path, 'read_text', return_value=json.dumps(receipt)):
            guard = Guard(root)
            self.assertEqual(guard.cards, (5, 6, 7))
            self.assertEqual(len(guard.host_libraries), 3)
        receipt['host_libraries'].pop('libhccl_alg.so')
        with patch('test.node03_device_guard.scope', return_value=root), patch.object(Path, 'read_text', return_value=json.dumps(receipt)):
            with self.assertRaises(ValueError):
                Guard(root)

    def test_scope_does_not_expand_to_other_nodes_or_card_sets(self):
        self.assertEqual(CARDS, (4, 5, 6, 7))
        for host, parent in (("liteserver-560t-0", "/home/commTeam/zjy/zjy-new-workspace"),
                             ("liteserver-560t-3", "/home/zjy-new/workspace")):
            root = Path(parent) / "hccl-diagnose-node03-20261029-006"
            self.assertEqual(scope(root, host), root.resolve())
            for other in ("liteserver-560t-1", "liteserver-560t-2"):
                with self.assertRaises(ValueError):
                    scope(root, other)
        with self.assertRaises(ValueError):
            scope(Path("/tmp/hccl-diagnose-node03-20261029-006"), "liteserver-560t-0")

    def test_gpt_probe_reuses_attested_build_only_on_node0_four_cards(self):
        root = Path('/home/commTeam/zjy/zjy-new-workspace/gpt2-semantic-20261102-001')
        self.assertEqual(scope(root, 'liteserver-560t-0'), root.resolve())
        with self.assertRaises(ValueError):
            scope(Path('/home/zjy-new/workspace/gpt2-semantic-20261102-001'), 'liteserver-560t-3')
        receipt = dict(status='built', device_sha256='a'*64, host_sha256='b'*64,
                       host_libraries={'libhcomm.so':'b'*64, 'libhccl_alg.so':'c'*64, 'libhccl_plf.so':'d'*64})
        with patch('test.node03_device_guard.scope', return_value=root), patch.object(Path, 'read_text', return_value=json.dumps(receipt)):
            guard = Guard(root)
            self.assertEqual(guard.cards, (4, 5, 6, 7))
            self.assertEqual(len(guard.host_libraries), 3)

    def test_original_policy_requires_both_chips(self):
        enable = "Custom-op-secverify-enable : False\n" * 2
        mode = "Custom-op-secverify-mode : 5\n" * 2
        self.assertEqual(policy(enable, mode), dict(enable=False, mode=5))
        for a, b in ((enable.splitlines()[0], mode), (enable, mode.replace("5", "0", 1))):
            with self.assertRaises(ValueError):
                policy(a, b)

    def test_explicit_sdma03_profile_cannot_change_cards_4_to_7(self):
        root = Path('/home/commTeam/zjy/zjy-new-workspace/hccl-diagnose-single-20261104-801')
        build = dict(status='built',device_sha256='a'*64,host_sha256='b'*64,verified_current_producer_files={},
            host_libraries={'libhcomm.so':'b'*64,'libhccl_alg.so':'c'*64,'libhccl_plf.so':'d'*64})
        deployment = dict(profile='single-gpt-sdma10-npu03-v1',cards=[0,1,2,3])
        authorization = dict(physical_cards=[0,1,2,3],temporary_signature_user_confirmed=True,restore_required=True)
        def read(path, *args, **kwargs):
            return json.dumps(deployment if path.name=='deployment.json' else authorization if path.name=='authorization.json' else build)
        with patch('test.node03_device_guard.scope',return_value=root), patch.object(Path,'read_text',read):
            guard=Guard(root)
            self.assertEqual(guard.cards,(0,1,2,3))
            guard.run=Mock(side_effect=AssertionError('out-of-scope command must never execute'))
            with self.assertRaises(ValueError):guard.query(6)
            with self.assertRaises(ValueError):guard.set(7,'custom-op-secverify-enable',1)
            guard.run.assert_not_called()
            authorization['temporary_signature_user_confirmed']=False
            with self.assertRaises(ValueError):Guard(root)
            authorization['temporary_signature_user_confirmed']=True
            deployment['cards']=[4,5,6,7]
            with self.assertRaises(ValueError):Guard(root)

    def test_three_new_gpt_cases_are_node0_only_and_use_attested_build(self):
        for number in (101, 102, 103):
            root = Path('/home/commTeam/zjy/zjy-new-workspace/gpt2-three-anomalies-20261102-'+str(number))
            self.assertEqual(scope(root, 'liteserver-560t-0'), root.resolve())
            with self.assertRaises(ValueError):
                scope(Path('/home/zjy-new/workspace')/root.name, 'liteserver-560t-3')
        with self.assertRaises(ValueError):
            scope(Path('/home/commTeam/zjy/zjy-new-workspace/gpt2-three-anomalies-20261102-104'), 'liteserver-560t-0')

    def test_partial_apply_can_restore_but_unknown_admin_change_is_not_clobbered(self):
        original = dict(enable=False, mode=5)
        for current in (original, dict(enable=True, mode=5), dict(enable=True, mode=0)):
            self.assertTrue(own_transition(current, original))
        self.assertFalse(own_transition(dict(enable=True, mode=3), original))

    def test_expired_transient_timer_can_already_be_unloaded(self):
        guard = object.__new__(Guard)
        for status in ("unknown\n", "inactive\n"):
            guard.run = Mock(side_effect=["", status])
            guard.stop_timer("owned")
            self.assertEqual(guard.run.call_args.kwargs, dict(check=False))
        guard.run = Mock(side_effect=["", "active\n"])
        with self.assertRaises(RuntimeError):
            guard.stop_timer("owned")

    def test_overhead_is_one_root_node0_four_cards_and_explicit_restore(self):
        name = 'gpt2-overhead-20261105-001'
        root = Path('/home/commTeam/zjy/zjy-new-workspace') / name
        self.assertEqual(scope(root, 'liteserver-560t-0'), root.resolve())
        for invalid, host in ((Path('/home/zjy-new/workspace') / name, 'liteserver-560t-3'),
                              (root.with_name(name + '-other'), 'liteserver-560t-0')):
            with self.assertRaises(ValueError):
                scope(invalid, host)
        import hashlib
        content = b'producer'
        build = dict(status='built', device_sha256='a'*64, host_sha256='b'*64,
            verified_current_producer_files={'hcomm/source.cc': hashlib.sha256(content).hexdigest()},
            host_libraries={'libhcomm.so':'b'*64, 'libhccl_alg.so':'c'*64, 'libhccl_plf.so':'d'*64})
        deployment = dict(profile='gpt-overhead-v1', cards=[4, 5, 6, 7])
        auth = dict(nodes=[0], physical_cards=[4, 5, 6, 7], temporary_signature_user_confirmed=True, restore_required=True)
        def read(path, *args, **kwargs):
            return json.dumps(deployment if path.name == 'deployment.json' else auth if path.name == 'authorization.json' else build)
        with patch('test.node03_device_guard.scope', return_value=root), patch.object(Path, 'read_text', read), patch.object(Path, 'read_bytes', return_value=content):
            self.assertEqual(Guard(root).cards, (4, 5, 6, 7))
            for key, bad in (('nodes', [0, 3]), ('physical_cards', [0, 1, 2, 3]), ('restore_required', False), ('temporary_signature_user_confirmed', False)):
                old = auth[key]
                auth[key] = bad
                with self.assertRaises(ValueError):
                    Guard(root)
                auth[key] = old

    def test_trim_trial_is_one_additional_node0_root(self):
        name = 'gpt2-overhead-trim-20261105-001'
        root = Path('/home/commTeam/zjy/zjy-new-workspace') / name
        self.assertEqual(scope(root, 'liteserver-560t-0'), root.resolve())
        for invalid, host in ((Path('/home/zjy-new/workspace') / name, 'liteserver-560t-3'),
                              (root.with_name(name + '-other'), 'liteserver-560t-0')):
            with self.assertRaises(ValueError):
                scope(invalid, host)
        import hashlib
        content = b'producer'
        build = dict(status='built', device_sha256='a'*64, host_sha256='b'*64,
            verified_current_producer_files={'hcomm/source.cc': hashlib.sha256(content).hexdigest()},
            host_libraries={'libhcomm.so':'b'*64, 'libhccl_alg.so':'c'*64, 'libhccl_plf.so':'d'*64})
        deployment = dict(profile='gpt-overhead-trim-v1', cards=[4,5,6,7])
        auth = dict(nodes=[0], physical_cards=[4,5,6,7], temporary_signature_user_confirmed=True, restore_required=True)
        def read(path,*args,**kwargs):
            return json.dumps(deployment if path.name=='deployment.json' else auth if path.name=='authorization.json' else build)
        with patch('test.node03_device_guard.scope',return_value=root),patch.object(Path,'read_text',read),patch.object(Path,'read_bytes',return_value=content):
            self.assertEqual(Guard(root).cards,(4,5,6,7))
            deployment['profile']='gpt-overhead-v1'
            with self.assertRaises(ValueError):Guard(root)
            deployment['profile']='gpt-overhead-trim-v1'
            auth['restore_required']=False
            with self.assertRaises(ValueError):Guard(root)

    def test_benchmark_only_root_is_node0_and_requires_its_exact_profile(self):
        root=Path('/home/commTeam/zjy/zjy-new-workspace/gpt2-overhead-benchmark-20261106-001')
        self.assertEqual(scope(root,'liteserver-560t-0'),root.resolve())
        for path,host in ((root.with_name(root.name+'-other'),'liteserver-560t-0'),
                (Path('/home/zjy-new/workspace')/root.name,'liteserver-560t-3')):
            with self.assertRaises(ValueError):scope(path,host)
        import hashlib
        content=b'producer'
        build=dict(status='built',device_sha256='a'*64,host_sha256='b'*64,
            verified_current_producer_files={'hcomm/source.cc':hashlib.sha256(content).hexdigest()},
            host_libraries={'libhcomm.so':'b'*64,'libhccl_alg.so':'c'*64,'libhccl_plf.so':'d'*64})
        deployment=dict(profile='gpt-overhead-benchmark-v1',cards=[4,5,6,7])
        auth=dict(nodes=[0],physical_cards=[4,5,6,7],temporary_signature_user_confirmed=True,restore_required=True)
        def read(path,*args,**kwargs):
            return json.dumps(deployment if path.name=='deployment.json' else auth if path.name=='authorization.json' else build)
        with patch('test.node03_device_guard.scope',return_value=root),patch.object(Path,'read_text',read),patch.object(Path,'read_bytes',return_value=content):
            self.assertEqual(Guard(root).cards,(4,5,6,7))
            deployment['profile']='gpt-overhead-trim-v1'
            with self.assertRaises(ValueError):Guard(root)
            deployment['profile']='gpt-overhead-benchmark-v1';auth['physical_cards']=[0,1,2,3]
            with self.assertRaises(ValueError):Guard(root)


if __name__ == "__main__":
    unittest.main()
