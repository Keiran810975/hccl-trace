"""Review regressions for public selection, capture integrity and report facts."""
from __future__ import annotations

from contextlib import redirect_stderr
from copy import deepcopy
import csv
import io
import json
from pathlib import Path
import shutil
import signal
import sqlite3
import tempfile
import unittest
from unittest.mock import patch, Mock

from . import cli, rolling_diagnosis as rolling, source_propagation as propagation
from .capture_command import join
from .recommended_policy import select
from .result_normalizer import normalize
from .test_rolling_diagnosis import repeated
from .test_tool_cli import sdk_capture, hashes
from .workload_binder import _read_calls
from . import compare_diagnosis, source_propagation_view
from .test_compare_diagnosis import fixture


def normalized(report, rows, edges):
    return normalize(report, mode='rolling', run_id='review', rows=rows, edges=edges,
                     pipeline=dict(status='passed'), binding_evidence={})


class ReviewRegressions(unittest.TestCase):
    def test_selected_single_node_sources_survive_normalization_and_propagation(self):
        rows, edges, coordinates = repeated()
        for row in rows:
            row['_node_id'] = 'review/node0'
        report = rolling.analyze(rows, edges, coordinates, rolling.RollingOptions(source_policy='dual'))
        chosen, _, _ = select(report, rows, edges)
        public, roots, tasks = normalized(chosen, rows, edges)
        self.assertTrue(chosen['root_causes'])
        self.assertEqual(len(public['candidates']), len(chosen['root_causes']))
        self.assertTrue(public['candidates'][0]['evidence_supported'])
        self.assertEqual(public['candidates'][0]['support_kind'], 'slow_notify_wait')
        view = propagation.build_report(rows, edges, roots, tasks)
        self.assertEqual(view['summary']['candidate_count'], len(public['candidates']))

    def test_single_node_sqlite_capture_publishes_actual_execution_anomaly(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = sdk_capture(root/'capture')
            first, second = source/'nodes/node0', source/'nodes/node1'
            shutil.copytree(second/'db', first/'db/peer-device')
            shutil.copy2(second/'plog/plog-fixture.log', first/'plog/plog-peer.log')
            records = [json.loads(line) for line in (second/'calls/rank-9.jsonl').read_text().splitlines()]
            for record in records:
                if 'node_id' in record:
                    record['node_id'] = 'node0'
            (first/'calls/rank-9.jsonl').write_text('\n'.join(json.dumps(r) for r in records)+'\n')
            metadata = json.loads((source/'capture.json').read_text())
            metadata['nodes'] = metadata['nodes'][:1]
            for rank in metadata['ranks']:
                rank['node_id'] = 'node0'
            (source/'capture.json').write_text(json.dumps(metadata))
            shutil.rmtree(second)
            with (first/'plog/plog-fixture.log').open('a') as stream:
                for iteration in range(6):
                    stream.write('[HcclTaskSemantic] schema_version[4] device_id[6] stream_id[13] '
                        'hccl_task_id[{}] task_kind[sdma] user_rank[3] comm_rank[0] rank_size[2] '
                        'peer_rank[9] phase[reduce_scatter] step[0] slice[0] event[copy_start] '
                        'semantic[payload] algorithm[ring]\n'.format(iteration*10+1))
            with sqlite3.connect(first/'db/msprof_fixture.db') as database:
                database.execute('UPDATE TASK SET endNs=startNs+1000 WHERE taskId=51')
            before = hashes(source)
            self.assertEqual(cli.main(['diag', str(source)]), 0)
            report = json.loads((root/'capture-report/root_causes.json').read_text())
            self.assertEqual(report['automatic_diagnosis']['execution_mode'], 'single_node')
            self.assertTrue(report['candidates'])
            self.assertEqual({c['user_rank'] for c in report['candidates']}, {3})
            self.assertEqual({c['iteration'] for c in report['candidates']}, {5})
            self.assertEqual(hashes(source), before)

    def test_unlinked_slow_waits_remain_observations_without_new_roots(self):
        for single in (False, True):
            with self.subTest(single=single):
                rows, edges, coordinates = repeated((1, 1, 1, 1, 1, 1))
                for row in rows:
                    if single:
                        row['_node_id'] = 'review/node0'
                    if row['_graph_id'] == 'i5p2':
                        row['_stop'] += 9
                        row['_duration'] += 9
                    if row['_graph_id'] == 'i5p3':
                        row['_start'] += 9
                        row['_stop'] += 9
                report = rolling.analyze(rows, edges, coordinates, rolling.RollingOptions(source_policy='dual'))
                chosen, _, _ = select(report, rows, edges)
                public, _, _ = normalized(chosen, rows, edges)
                self.assertEqual(public['candidates'], [])
                self.assertEqual(public['diagnosis_status'], 'unresolved_waits')
                self.assertEqual(public['unresolved_observations'][0]['graph_id'], 'i5p2')
                self.assertEqual(public['coverage']['not_linked_to_selected_source_slow_wait_count'], 1)

    def test_normalization_never_promotes_semantic_or_missing_path_evidence(self):
        rows, edges, coordinates = repeated()
        report = rolling.analyze(rows, edges, coordinates)
        for missing in (False, True):
            with self.subTest(missing=missing):
                changed = deepcopy(edges)
                if missing:
                    changed = [e for e in changed if e['edge_id'] != 'i5e0']
                else:
                    next(e for e in changed if e['edge_id'] == 'i5e0')['confidence'] = 'semantic'
                public, _, _ = normalized(report, rows, changed)
                candidate = next(c for c in public['candidates'] if c['graph_id'] == 'i5p0')
                self.assertEqual(candidate['evidence_confidence'], 'unavailable' if missing else 'semantic')
                self.assertFalse(candidate['evidence_supported'])

    def test_slice_preserves_quality_operation_lanes_and_honest_retention(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); source = sdk_capture(root/'capture')
            original = cli.run_pipeline
            def add_issue(*args, **kwargs):
                directory, ready = original(*args, **kwargs)
                path = directory/'dep_graph_notify_ambiguities.csv'
                with path.open(newline='') as stream:
                    fields = csv.DictReader(stream).fieldnames
                with path.open('a', newline='') as stream:
                    csv.DictWriter(stream, fields).writerow(dict(status='review_fixture_ambiguity', relation_id='fixture'))
                return directory, ready
            with patch.object(cli, 'run_pipeline', side_effect=add_issue):
                report = cli.analyze_capture(source, root/'report', mode='rolling', source_policy='auto',
                                             selected_iteration_view=True, keep_debug=True)
            self.assertEqual(report['quality']['notify_ambiguity_count'], 1)
            self.assertTrue(report['analysis_scope']['original_full_graph_retained'])
            sliced = next((root/'report.debug/analysis').glob('*/selected-iteration-view'))
            with (sliced/'operation_timings.csv').open(newline='') as stream:
                self.assertTrue(list(csv.DictReader(stream)))
            without_debug = cli.analyze_capture(source, root/'no-debug', mode='rolling', source_policy='auto',
                                                selected_iteration_view=True)
            self.assertFalse(without_debug['analysis_scope']['original_full_graph_retained'])
            self.assertTrue(without_debug['analysis_scope']['full_graph_replayable_from_capture'])

    def test_join_reads_declared_calls_path_and_rejects_incomplete_logs(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); source = sdk_capture(root/'capture')
            metadata = json.loads((source/'capture.json').read_text())
            for node in metadata['nodes']:
                original = source/'nodes'/node['node_id']/'calls'
                moved = original.with_name('observations')
                original.rename(moved)
                node['calls_dir'] = str(moved.relative_to(source))
            (source/'capture.json').write_text(json.dumps(metadata))
            self.assertEqual(join([source], root/'joined')['node_count'], 2)
            self.assertEqual(cli.main(['diag', str(root/'joined')]), 0)
            path = source/'nodes/node0/observations/rank-3.jsonl'
            path.write_text('\n'.join(path.read_text().splitlines()[:-1])+'\n')
            before = hashes(source)
            with self.assertRaisesRegex(ValueError, 'incomplete'):
                join([source], root/'incomplete')
            self.assertFalse((root/'incomplete').exists())
            self.assertEqual(hashes(source), before)

    def test_binder_rejects_false_completion_and_post_end_records(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = sdk_capture(Path(tmp)/'capture')
            path = source/'nodes/node0/calls/rank-3.jsonl'
            original = [json.loads(line) for line in path.read_text().splitlines()]
            for malformed in ('missing-completion', 'premature-completion', 'post-end'):
                with self.subTest(malformed=malformed):
                    records = deepcopy(original)
                    if malformed == 'missing-completion':
                        del records[-2]
                    elif malformed == 'premature-completion':
                        records[1:3] = records[1:3][::-1]
                    else:
                        records.append(records[1])
                    path.write_text('\n'.join(json.dumps(r) for r in records)+'\n')
                    with self.assertRaises(ValueError):
                        _read_calls(path)

    def test_baseline_rejects_changed_declared_reduction(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            current, normal = sdk_capture(root/'current'), sdk_capture(root/'normal')
            for path in current.glob('nodes/*/calls/rank-*.jsonl'):
                records = [json.loads(line) for line in path.read_text().splitlines()]
                for record in records:
                    if record['event'] == 'call':
                        record['reduction'] = 'max'
                path.write_text('\n'.join(json.dumps(r) for r in records)+'\n')
            with redirect_stderr(io.StringIO()):
                self.assertEqual(cli.main(['diag', str(current), '--baseline', str(normal)]), 2)
            self.assertFalse((root/'current-report').exists())

    def test_baseline_markdown_labels_the_actual_reference_and_values(self):
        rows, edges, normal, normal_edges = fixture()
        report = compare_diagnosis.analyze(rows, edges, normal, baseline_edges=normal_edges)
        public, roots, tasks = normalize(report, mode='baseline', run_id='review', rows=rows, edges=edges,
                                        pipeline=dict(status='passed'), binding_evidence={})
        view = propagation.build_report(rows, edges, roots, tasks, reference=public['reference'])
        markdown = source_propagation_view.render_markdown(view)
        self.assertIn('Baseline 中位数', markdown)
        self.assertNotIn('前5轮', markdown)
        self.assertIn('10.000 μs', markdown)

    def test_explicit_debug_directory_is_not_silently_ignored(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); source = sdk_capture(root/'capture')
            self.assertEqual(cli.main(['diag', str(source), '--debug-dir', str(root/'evidence')]), 0)
            self.assertTrue((root/'evidence/analysis').is_dir())
            public = json.loads((root/'capture-report/root_causes.json').read_text())
            self.assertTrue(public['analysis_scope']['original_full_graph_retained'])

    def test_debug_path_alias_cannot_create_files_inside_report(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); (root/'actual').mkdir()
            (root/'alias').symlink_to(root/'actual', target_is_directory=True)
            with self.assertRaises(cli.DiagnosisError) as error:
                cli.analyze_capture(root/'missing-capture', root/'actual/report', mode='rolling',
                                    debug_dir=root/'alias/report/evidence')
            self.assertEqual(error.exception.code, 2)
            self.assertFalse((root/'actual/report').exists())

    def test_invalid_threshold_fails_before_reading_capture(self):
        for factor in ('nan', 'not-a-number', '1'):
            with self.subTest(factor=factor), patch.object(cli, 'discover_capture') as discover:
                with self.assertRaises(cli.DiagnosisError) as error:
                    cli.analyze_capture('missing-capture', 'unused-report', mode='rolling',
                                        source_slowdown_factor=factor)
                self.assertEqual(error.exception.code, 2)
                discover.assert_not_called()

    def test_capture_sigterm_cleans_only_owned_group_and_restores_handler(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp)/'capture'
            previous = signal.getsignal(signal.SIGTERM)
            handlers = []
            child = Mock(pid=12345)
            def wait(*args, **kwargs):
                if child.wait.call_count == 1:
                    handlers[0](signal.SIGTERM, None)
                return 0
            child.wait.side_effect = wait
            with patch('sys.platform', 'linux'), patch('shutil.which', return_value='/bin/msprof'), \
                    patch('subprocess.Popen', return_value=child), patch('os.killpg') as stop, \
                    patch('signal.signal', side_effect=lambda signum, handler: handlers.append(handler)), \
                    redirect_stderr(io.StringIO()):
                self.assertEqual(cli.main(['cap', '-o', str(output), '--node', 'node0', '--', 'train']), 143)
            stop.assert_called_once_with(child.pid, signal.SIGTERM)
            self.assertEqual(handlers[-1], previous)
            self.assertEqual(json.loads((output/'nodes/node0/collection.json').read_text())['status'], 'failed')

    def test_join_reports_malformed_metadata_without_starting_copy(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); source = sdk_capture(root/'capture')
            for metadata in ([], dict(nodes='invalid'), dict(nodes=[{}]),
                             dict(nodes=[dict(node_id='node0', calls_dir=1)])):
                with self.subTest(metadata=metadata), redirect_stderr(io.StringIO()):
                    (source/'capture.json').write_text(json.dumps(metadata))
                    self.assertEqual(cli.main(['join', str(source), '-o', str(root/'refused')]), 2)
                    self.assertFalse((root/'refused').exists())

    def test_unresolved_html_preview_is_bounded_without_deleting_report_facts(self):
        from .test_source_propagation import diagnosed
        rows, edges, roots, tasks, _ = diagnosed()
        observations = [dict(graph_id='wait-'+str(i), iteration=i % 2) for i in range(1000)]
        report = propagation.build_report(rows, edges, roots, tasks, unresolved_observations=observations)
        report['analysis_scope'] = dict(iterations=[1])
        model = source_propagation_view.build_view_model(report)
        self.assertEqual(model['unresolved_observation_count'], 1000)
        self.assertEqual(model['unresolved_in_view_count'], 500)
        self.assertEqual(len(model['unresolved_observations']), 200)
        self.assertTrue(all(item['iteration'] == 1 for item in model['unresolved_observations']))
        self.assertEqual(report['unresolved_observations'], observations)

    def test_debug_retention_failure_is_an_error_not_silent_success(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); source = sdk_capture(root/'capture')
            before = hashes(source)
            rename = Path.rename
            def unavailable(path, destination):
                if Path(destination) == root/'evidence':
                    raise OSError('synthetic destination unavailable')
                return rename(path, destination)
            with patch.object(Path, 'rename', unavailable):
                with self.assertRaises(cli.DiagnosisError) as error:
                    cli.analyze_capture(source, root/'report', mode='rolling', debug_dir=root/'evidence')
            self.assertEqual(error.exception.code, 5)
            self.assertIn('debug retention failed', str(error.exception))
            self.assertEqual(hashes(source), before)


if __name__ == '__main__':
    unittest.main()
