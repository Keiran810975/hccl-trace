"""CPU-only protocol tests; passing these is not an NPU/RDMA acceptance result."""
from __future__ import annotations

from copy import deepcopy
import csv
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import Mock
from unittest.mock import patch

from test.anomaly_injection.single_node_control import clocks
from test.node03_evaluate import network_active_interval
from test.node03_roce_window import Window, COUNTERS, DEVICE, SIBLING
from test.roce_single_collective import (
    ROOT_NAME, SingleCollectiveControl, audit_public_window, case, identity,
    validate_case, validate_participants, watch,
)


class MemoryStore:
    def __init__(self):
        self.values = {}
        self.lock = threading.Lock()

    def set(self, key, value):
        with self.lock:
            self.values[key] = value.encode()

    def get(self, key):
        with self.lock:
            return self.values[key]

    def check(self, keys):
        with self.lock:
            return all(k in self.values for k in keys)


class SingleCollectiveTests(unittest.TestCase):
    def fixture(self, parent, failure=None):
        root = parent / ROOT_NAME
        (root / 'input').mkdir(parents=True)
        value = case()
        (root / 'input/case.json').write_text(json.dumps(value))
        (root / 'authorization.json').write_text(json.dumps(dict(nodes=[0, 3], physical_cards=[4, 5, 6, 7],
            restore_required=True, single_collective_user_confirmed=True, node3_target_process_stop_user_confirmed=False)))
        zero = dict.fromkeys(COUNTERS, 0)
        (root / 'input/network-baseline.json').write_text(json.dumps(dict(node_id='node0', user_rank=0,
            physical_device_id=9, runtime_device_id=1, foreground_only=True, numerics_passed=True,
            before=zero, after=dict(zero, mac_tx_total_oct_num=2 * 1024**2, roce_tx_all_pkt_num=10))))
        window = object.__new__(Window)
        window.root, window.directory, window.control = root, root / 'network', root / 'gpt-output/private'
        window.snapshot = window.directory / 'snapshot.json'
        original = {d: dict(limit_mbps=200000, maximum_mbps=200000, current_mbps=200000) for d in (DEVICE, SIBLING)}
        ports, trace, store = deepcopy(original), [], MemoryStore()

        def shaping(device):
            result = dict(ports[device])
            if failure == 'readback' and device == DEVICE and result['limit_mbps'] == 20000:
                if not getattr(shaping, 'failed', False):
                    shaping.failed = True
                    result['limit_mbps'] = 1
            return result

        def set_limit(device, limit):
            if limit == 20000:
                self.assertTrue(all(store.check([value['case_id'] + '/single-collective/ready/%d' % r]) for r in range(8)))
                self.assertFalse(any(k.endswith('/completed/0') for k in store.values))
            trace.append(('set', device, limit))
            ports[device] = dict(ports[device], limit_mbps=limit)

        def run(command, check=True):
            if command[0] == 'systemd-run' and '--on-active=2s' in command:
                window.restore()
            if failure == 'timer' and command[:2] == ['systemctl', 'is-active'] and command[-1].endswith('-active.timer'):
                return 'inactive\n'
            return 'active\n'

        def traffic():
            if not getattr(traffic, 'called', False):
                traffic.called = True
                return zero
            return dict(zero, mac_tx_total_oct_num=0 if failure == 'no_traffic' else 10000000,
                        roce_tx_all_pkt_num=0 if failure == 'no_traffic' else 100)

        window.shaping, window.set, window.run = shaping, set_limit, run
        window.own_processes = Mock(side_effect=RuntimeError('unknown process') if failure == 'foreign' else None)
        window.query, window.stop_timer = traffic, Mock()
        errors, controls = [], []
        for rank in range(8):
            data = root / ('gpt-output' if rank < 4 else 'peer-preflight/gpt-output')
            synchronize = Mock(side_effect=lambda: trace.append(('sync',)))
            controls.append(SingleCollectiveControl(value, data / 'private', rank, store, synchronize, timeout=2))

        def guard():
            try:
                watch(window)
            except BaseException as error:
                errors.append(('guard', error))

        def worker(control):
            try:
                control.prepare()
                control.before_bucket(25, 'a' * 64, 1024)
                if ports[DEVICE]['limit_mbps'] != 20000:
                    raise AssertionError('target was released before native readback')
                now = clocks()
                call = dict(rank=control.rank, sequence=7, stage='measured', iteration=25,
                    bucket_signature='a' * 64, count=1024, before=clocks(), after=clocks(), preparation_before=now)
                public = control.directory.parent / 'public'
                (public / ('rank-%d.jsonl' % control.rank)).write_text(json.dumps(call) + '\n')
                future = Mock()
                if failure == 'future' and control.rank == 4:
                    future.wait.side_effect = RuntimeError('target device operation failed')
                control.after_bucket(future, call)
                future.wait.assert_called_once()
                if ports != original:
                    raise AssertionError('following call released before restoration')
                control.finish()
            except BaseException as error:
                errors.append((control.rank, error))
            finally:
                control.close()

        threads = [threading.Thread(target=guard)] + [threading.Thread(target=worker, args=(c,)) for c in controls]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=5)
        if any(t.is_alive() for t in threads):
            (window.control / 'abort').touch()
            store.set(value['case_id'] + '/single-collective/abort', '{}')
            for thread in threads:
                thread.join(timeout=3)
        self.assertFalse(any(t.is_alive() for t in threads), 'CPU test leaked a control thread')
        return root, value, window, ports, original, errors, controls, trace

    def test_one_collective_is_bracketed_by_eight_device_drains_and_verified_restore(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, value, window, ports, original, errors, controls, trace = self.fixture(Path(tmp))
            self.assertEqual(errors, [])
            self.assertEqual(ports, original)
            self.assertEqual([t for t in trace if t[0] == 'set'], [('set', 9, 20000), ('set', 9, 200000)])
            for c in controls:
                self.assertTrue(c.started and c.stopped)
                self.assertEqual(c.synchronize.call_count, 2)
            result = json.loads((window.control / 'network-result.json').read_text())
            audit = audit_public_window(root, value, result)
            self.assertEqual(len(audit['checked_ranks']), 8)
            self.assertTrue(audit['rdma_task_presence_requires_db_audit'])
            self.assertEqual(network_active_interval(result), (result['started_raw_ns'], result['finished_raw_ns']))
            stopped = [c.args[0] for c in window.stop_timer.call_args_list]
            self.assertTrue(any(u.endswith('-probe') for u in stopped))
            self.assertTrue(any(u.endswith('-active') for u in stopped))
            self.assertTrue(any(not u.endswith('-probe') for u in stopped))

    def test_native_readback_foreign_process_missing_traffic_and_future_failures_restore(self):
        for reason in ('readback', 'foreign', 'no_traffic', 'future', 'timer'):
            with self.subTest(reason=reason), tempfile.TemporaryDirectory() as tmp:
                _, _, window, ports, original, errors, controls, _ = self.fixture(Path(tmp), reason)
                self.assertTrue(errors)
                self.assertEqual(ports, original)
                self.assertFalse((window.control / 'single-call-restored.json').exists())
                self.assertFalse(any(c.stopped for c in controls))
                self.assertTrue(json.loads((window.control / 'network-result.json').read_text())['restored_verified'])

    def test_public_audit_rejects_another_call_inside_held_window(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, value, window, _, _, errors, _, _ = self.fixture(Path(tmp))
            self.assertEqual(errors, [])
            path = root / 'gpt-output/public/rank-0.jsonl'
            call = json.loads(path.read_text())
            with path.open('a') as output:
                output.write(json.dumps(dict(call, sequence=8)) + '\n')
            with self.assertRaisesRegex(ValueError, 'another collective'):
                audit_public_window(root, value, json.loads((window.control / 'network-result.json').read_text()))

    def test_successful_control_without_observed_rdma_is_not_an_effect_success(self):
        from test.run_roce_single_collective import inspect_effect
        import hashlib
        with tempfile.TemporaryDirectory() as tmp:
            root, value, window, _, _, errors, _, _ = self.fixture(Path(tmp))
            self.assertEqual(errors, [])
            report = root / 'report'; report.mkdir()
            names = ('root_causes.json', 'execution.html', 'propagation.html')
            for name in names:
                (report / name).write_text('{}')
            (root / 'diagnosis-seal.json').write_text(json.dumps(dict(truth_accessed=False,
                sha256={name: hashlib.sha256(b'{}').hexdigest() for name in names})))
            analysis = root / 'report.debug/analysis' / value['case_id']
            (analysis / 'rolling').mkdir(parents=True)
            (analysis / 'cross_node').mkdir()
            (analysis / 'rolling/task_comparison.csv').write_text('stage,iteration,call_site,node_id,user_rank,task_kind,observed_start_ns,observed_stop_ns\n')
            (analysis / 'cross_node/segments.csv').write_text('status,stage,iteration,call_site,sender_rank,sender_node_id,reference_count,reference_iterations,is_slow\n')
            result = inspect_effect(root, dict(candidate_hit_count=0, windows=[]))
            self.assertFalse(result['effect_gate_passed'])
            self.assertEqual(result['target_rdma_submission_task_count'], 0)
            activity = json.loads((window.control / 'network-result.json').read_text())
            before, after = activity['started_raw_ns'], activity['finished_raw_ns']
            evaluation = dict(candidate_hit_count=0, windows=[dict(user_rank=0, start_ns=before, stop_ns=after)])
            task = dict(stage='measured', iteration=25, call_site='ddp.gradient.'+'a'*64,
                node_id=value['case_id']+'/node0', user_rank=0, task_kind='rdma',
                observed_start_ns=before+1, observed_stop_ns=after-1)
            path = dict(status='protocol_interval_observed', stage='measured', iteration=25,
                call_site='ddp.gradient.'+'a'*64, sender_rank=0, sender_node_id=value['case_id']+'/node0',
                reference_count=5, reference_iterations=json.dumps(list(range(20,25))), is_slow=True, transfer_id='path1')
            with (analysis / 'rolling/task_comparison.csv').open('w', newline='') as output:
                writer = csv.DictWriter(output, fieldnames=list(task)); writer.writeheader(); writer.writerow(task)
            def write_paths(item):
                with (analysis / 'cross_node/segments.csv').open('w', newline='') as output:
                    writer = csv.DictWriter(output, fieldnames=list(item)); writer.writeheader(); writer.writerows([item,dict(item,transfer_id='path2')])
            write_paths(path)
            self.assertTrue(inspect_effect(root, evaluation)['effect_gate_passed'])
            path['reference_iterations'] = json.dumps(list(range(21,26)))
            write_paths(path)
            self.assertFalse(inspect_effect(root, evaluation)['effect_gate_passed'])

    def test_guard_rejects_implicit_or_changed_single_call_authorization(self):
        from test.node03_device_guard import Guard
        import hashlib
        root = Path('/home/commTeam/zjy/zjy-new-workspace') / ROOT_NAME
        content = b'producer'
        build = dict(status='built', device_sha256='b68ef612370ebb9c635e9fb9d94ddaf977be81a3d609d0e35936f20e41ceebd2',
            host_sha256='b'*64, verified_current_producer_files={'hcomm/source.cc': hashlib.sha256(content).hexdigest()},
            host_libraries={'libhcomm.so':'b'*64,'libhccl_alg.so':'c'*64,'libhccl_plf.so':'d'*64})
        deployment = dict(profile='roce-single-collective-v1', capture_policy=dict(global_log_level=2,
            module_override=False, task_time='l1', ai_core='off', hccl='on', ascendcl='on'))
        auth = dict(nodes=[0,3], physical_cards=[4,5,6,7], restore_required=True,
            temporary_signature_user_confirmed=True, single_collective_user_confirmed=True,
            node3_target_process_stop_user_confirmed=False)
        def content_for(path, *args, **kwargs):
            return json.dumps(deployment if path.name == 'deployment.json' else auth if path.name == 'authorization.json' else build)
        with patch('test.node03_device_guard.scope', return_value=root), patch.object(Path, 'is_file', return_value=True), \
                patch.object(Path, 'read_text', content_for), patch.object(Path, 'read_bytes', return_value=content):
            self.assertEqual(Guard(root).cards, (4,5,6,7))
            auth['single_collective_user_confirmed'] = False
            with self.assertRaises(ValueError): Guard(root)
            auth['single_collective_user_confirmed'] = True
            auth['node3_target_process_stop_user_confirmed'] = True
            with self.assertRaises(ValueError): Guard(root)

    def test_missing_duplicate_wrong_identity_and_api_only_completion_are_rejected(self):
        expected = identity(case()['case_id'], 25, 'a' * 64, 1024)
        valid = dict(identity=expected, phase='completed', ranks=[dict(identity=expected, phase='completed',
            rank=r, device_synchronized=True, raw_ns=30, submit_before_raw_ns=10, submit_after_raw_ns=20)
            for r in range(8)])
        self.assertEqual(set(validate_participants(valid, expected, 'completed')), set(range(8)))
        for reason in ('missing', 'duplicate', 'identity', 'sync', 'order'):
            bad = deepcopy(valid)
            if reason == 'missing': bad['ranks'].pop()
            if reason == 'duplicate': bad['ranks'][-1]['rank'] = 0
            if reason == 'identity': bad['ranks'][-1]['identity']['iteration'] = 24
            if reason == 'sync': bad['ranks'][-1]['device_synchronized'] = False
            if reason == 'order': bad['ranks'][-1]['submit_after_raw_ns'] = 31
            with self.subTest(reason=reason), self.assertRaises(ValueError):
                validate_participants(bad, expected, 'completed')

    def test_gate_timeout_and_abort_never_release_a_call(self):
        for abort in (False, True):
            with self.subTest(abort=abort), tempfile.TemporaryDirectory() as tmp:
                store = MemoryStore()
                c = SingleCollectiveControl(case(), Path(tmp) / 'private', 1, store, Mock(), timeout=.02)
                if abort:
                    c.put('abort', {})
                with self.assertRaises(RuntimeError if abort else TimeoutError):
                    c.before_bucket(25, 'a' * 64, 1024)
                self.assertFalse(c.stopped)
                c.close()

    def test_previous_async_work_is_waited_before_device_drain_and_ready(self):
        with tempfile.TemporaryDirectory() as tmp:
            order = []
            c = SingleCollectiveControl(case(), Path(tmp) / 'private', 1, MemoryStore(),
                lambda: order.append('device_sync'), timeout=.1)
            expected = identity(case()['case_id'], 25, 'a'*64, 1024)
            c.put('limited', dict(identity=expected, phase='limited'))
            future = Mock()
            future.wait.side_effect = lambda: order.append('future_wait')
            c.before_bucket(25, 'a'*64, 1024, previous_futures=[future])
            self.assertEqual(order, ['future_wait', 'device_sync'])
            c.close()

    def test_case_is_frozen_and_legacy_network_window_is_unchanged(self):
        original = case()
        for field, replacement in (('iteration', 26), ('duration_iters', 5), ('limit_mbps', 10000)):
            value = deepcopy(original)
            value['injection'][field] = replacement
            with self.assertRaises(ValueError): validate_case(value)
        self.assertEqual(network_active_interval(dict(started_raw_ns=20, finished_raw_ns=30,
            first_confirmed_limit_raw_ns=15, apply_returned_raw_ns=10)), (15, 30))


if __name__ == '__main__':
    unittest.main()
