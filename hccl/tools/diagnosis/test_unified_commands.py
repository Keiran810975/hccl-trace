"""Unified public commands, topology selection and retired report annotations."""
from __future__ import annotations

from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import tempfile
import shutil
import signal
import unittest
from unittest.mock import patch, Mock

from .cli import main
from .capture_command import capture, join
from .report_contract import without_critical_path
from .test_tool_cli import sdk_capture, hashes


class UnifiedCommandsTests(unittest.TestCase):
    def test_one_command_automatically_selects_multi_node_and_omits_critical_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = sdk_capture(root / 'capture')
            before = hashes(source)
            self.assertEqual(main(['diag', str(source)]), 0)
            report = root / 'capture-report'
            value = json.loads((report / 'root_causes.json').read_text())
            self.assertEqual(value['automatic_diagnosis']['node_count'], 2)
            self.assertEqual(value['automatic_diagnosis']['selected_policy'], 'wait_backtrace_v1')
            self.assertNotIn('source_selection', value)
            self.assertEqual(value['source_regions'], [])
            self.assertEqual(set(p.name for p in report.iterdir()), {'root_causes.json','execution.html','propagation.html'})
            for path in report.iterdir():
                text = path.read_text()
                self.assertNotIn('关键路径', text)
                self.assertNotIn('modeled_execution_gain_ns', text)
                self.assertNotIn('local_model_execution_gain_ns', text)
                self.assertNotIn('critical_path', text)
            self.assertEqual(hashes(source), before)

    def test_single_node_multiple_ranks_is_not_misdetected_as_multi_node(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); source = sdk_capture(root/'capture')
            first, second = source/'nodes/node0', source/'nodes/node1'
            shutil.copytree(second/'db', first/'db/peer-device')
            shutil.copy2(second/'plog/plog-fixture.log', first/'plog/plog-peer.log')
            records = [json.loads(line) for line in (second/'calls/rank-9.jsonl').read_text().splitlines()]
            for record in records:
                if 'node_id' in record: record['node_id'] = 'node0'
            (first/'calls/rank-9.jsonl').write_text('\n'.join(json.dumps(r) for r in records)+'\n')
            metadata = json.loads((source/'capture.json').read_text())
            metadata['nodes'] = metadata['nodes'][:1]
            for rank in metadata['ranks']: rank['node_id'] = 'node0'
            (source/'capture.json').write_text(json.dumps(metadata))
            shutil.rmtree(second)
            self.assertEqual(main(['analyze',str(source)]), 0)
            value = json.loads((root/'capture-report/root_causes.json').read_text())
            self.assertEqual(value['automatic_diagnosis']['node_count'], 1)
            self.assertEqual(value['quality']['rank_count'], 2)

    def test_help_has_no_user_strategy_version_switch(self):
        output = io.StringIO()
        with redirect_stdout(output), self.assertRaises(SystemExit):
            main(['analyze','--help'])
        self.assertNotIn('--source-policy', output.getvalue())
        self.assertNotIn('--candidate-policy', output.getvalue())

    def test_capture_wraps_launcher_lowlog_and_rejects_false_profiler_success(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / 'capture'
            child = Mock(); child.wait.return_value = 0
            def start(command, **kwargs):
                self.assertIn('--task-time=l1', command)
                self.assertIn('--ai-core=off', command)
                self.assertEqual(kwargs['env']['ASCEND_GLOBAL_LOG_LEVEL'], '2')
                self.assertTrue(kwargs['start_new_session'])
                folder = root / 'nodes/node0'
                (folder / 'msprof').mkdir()
                (folder / 'msprof/msprof_fixture.db').write_bytes(b'fixture')
                runtime = dict(event='runtime', schema_version=1, run_id='capture', node_id='node0', user_rank=3, device_id=6)
                call = dict(runtime, event='call', sequence=0, stage='measured', iteration=0, occurrence=0,
                    element_count=8, call_site='gradient', group_id='dp', before=dict(raw_ns=1),
                    after=dict(raw_ns=2), status='submitted')
                events = [runtime, call, dict(event='completion', schema_version=1, sequences=[0], clocks=dict(raw_ns=3)),
                          dict(event='capture_end', schema_version=1, pending_sequences=[])]
                (folder/'calls/rank-3.jsonl').write_text('\n'.join(json.dumps(e) for e in events)+'\n')
                return child
            with patch('sys.platform','linux'), patch('shutil.which',return_value='/bin/msprof'), patch('subprocess.Popen',side_effect=start):
                self.assertEqual(capture(root, ['--','torchrun','train.py'], node='node0')['status'], 'captured_not_yet_diagnosed')
            with patch('sys.platform','linux'), patch('shutil.which',return_value='/bin/msprof'), patch('subprocess.Popen',return_value=child):
                with self.assertRaisesRegex(ValueError,'missing consolidated'):
                    capture(Path(tmp)/'bad', ['python','train.py'], node='node0')
            self.assertEqual(json.loads((root/'nodes/node0/collection.json').read_text())['numerical_correctness_verified'], False)

    def test_join_checks_shared_run_and_hashes_without_changing_sources(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); source = sdk_capture(root/'source'); before = hashes(source)
            result = join([source], root/'joined')
            self.assertEqual(result['node_count'], 2)
            self.assertTrue(result['sha256'])
            self.assertEqual(main(['analyze', str(root/'joined')]), 0)
            self.assertEqual(hashes(source), before)
            with self.assertRaisesRegex(ValueError,'duplicate'):
                join([source, source], root/'duplicate')

    def test_join_preserves_explicit_clock_files_and_refuses_external_links(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); source = sdk_capture(root/'source')
            metadata = json.loads((source/'capture.json').read_text())
            for node in metadata['nodes']:
                relative = 'nodes/'+node['node_id']+'/clock.json'
                (source/relative).write_text('{"original_probe": true}\n')
                node['clock_probe_files'] = [relative]
            (source/'capture.json').write_text(json.dumps(metadata))
            before = hashes(source)
            join([source], root/'joined')
            copied = json.loads((root/'joined/capture.json').read_text())
            self.assertEqual(copied['nodes'], metadata['nodes'])
            self.assertEqual(hashes(source), before)
            (root/'alias').symlink_to(source, target_is_directory=True)
            with self.assertRaisesRegex(ValueError,'symlinks'):
                join([root/'alias'], root/'refused')
            self.assertFalse((root/'refused').exists())

    def test_interrupted_capture_only_terminates_its_owned_process_group(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp)/'capture'
            child = Mock(pid=12345)
            child.wait.side_effect = [KeyboardInterrupt, 0]
            with patch('sys.platform','linux'), patch('shutil.which',return_value='/bin/msprof'), \
                    patch('subprocess.Popen',return_value=child), patch('os.killpg') as stop:
                with self.assertRaises(KeyboardInterrupt):
                    capture(output, ['torchrun','train.py'], node='node0')
            stop.assert_called_once_with(child.pid, signal.SIGTERM)
            self.assertEqual(json.loads((output/'nodes/node0/collection.json').read_text())['status'],'failed')
            self.assertTrue((output/'nodes/node0/profiler.log').is_file())

    def test_retired_annotations_removed_recursively_but_real_paths_remain(self):
        value = dict(critical_path={}, chains=[dict(edge_ids=['edge1'],modeled_execution_gain_ns=5)],
                     quality=dict(global_critical_path_available=False), limits=['no global critical path','physical cause unknown'])
        self.assertEqual(without_critical_path(value),dict(chains=[dict(edge_ids=['edge1'])],quality={},limits=['physical cause unknown']))


if __name__ == '__main__':
    unittest.main()
