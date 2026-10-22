"""Regression tests for real AI_CPU timing and same-node RDMA failure modes."""
from __future__ import annotations

import csv
import json
import os
import sqlite3
import sys
import tempfile
import unittest
from copy import deepcopy
from dataclasses import replace
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from diagnosis import parse_msprof_db as db, multi_node_trace as multi, visualize_html as view
    from diagnosis.test_diagnosis import create_msprof_db, execution_row, SemanticRecord
    from diagnosis.test_multi_node_trace import cross_rows, RANKS, EVIDENCE
    from diagnosis.resource_dependency_graph import build_resource_graph
    from diagnosis.visualize_dependency_graph import build_execution_edges
    from diagnosis.merge_timeline import merge_records
else:
    from . import parse_msprof_db as db, multi_node_trace as multi, visualize_html as view
    from .test_diagnosis import create_msprof_db, execution_row, SemanticRecord
    from .test_multi_node_trace import cross_rows, RANKS, EVIDENCE
    from .resource_dependency_graph import build_resource_graph
    from .visualize_dependency_graph import build_execution_edges
    from .merge_timeline import merge_records


def local_rows():
    rows = cross_rows()
    for row in rows:
        row['_node_id'] = 'run/node0'
        row['_notify_id'] = 5124
    rows[0]['event_name'] = 'WRITE_VALUE_SQE'
    rows[1]['event_name'] = 'NOTIFY_WAIT_SQE'
    return rows, {3: ('run/node0', 6), 9: ('run/node0', 2)}


class TimingDiagnosisTest(unittest.TestCase):
    def test_host_rdma_doorbell_uses_exact_task_identity(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "msprof_host.db"
            create_msprof_db(path)
            with sqlite3.connect(path) as connection:
                connection.execute("UPDATE STRING_IDS SET value='RDMA_DB_SEND' WHERE id=1")
                connection.execute("INSERT INTO COMMUNICATION_TASK_INFO VALUES(10,?,3,9,7)",
                                   ((9 << 32) | 128,))
            task = next(item for item in db.parse_file(str(path), "node0") if item.task_id == 1)
            self.assertEqual(task.task_kind, "rdma")
            self.assertEqual(task.event_name, "RDMA_DB_SEND")
            semantic = replace(SemanticRecord(), node_id="node0", device_id=0, stream_id=13,
                               task_id=1, user_rank=3, peer_rank=9, task_kind="rdma", source="host")
            _, stats = merge_records([semantic], [task])
            self.assertEqual(stats["exact_matched"], 1)
            for changed in (replace(semantic, task_id=2), replace(semantic, device_id=2),
                            replace(semantic, task_kind="notify_record")):
                _, stats = merge_records([changed], [task])
                self.assertEqual(stats["exact_matched"], 0)

    def test_db_inline_reduce_preserves_copy_identity_size_and_time(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'msprof_test.db'
            create_msprof_db(path)
            c = sqlite3.connect(path)
            c.executescript("ALTER TABLE COMMUNICATION_TASK_INFO ADD COLUMN taskType INTEGER; "
                            "ALTER TABLE COMMUNICATION_TASK_INFO ADD COLUMN size INTEGER;")
            c.execute("UPDATE STRING_IDS SET value='SDMA_SQE' WHERE id=1")
            c.execute("INSERT INTO STRING_IDS VALUES(8,'Reduce_Inline')")
            c.execute("INSERT INTO COMMUNICATION_TASK_INFO VALUES(10,-1,0,4294967295,7,8,4)")
            c.commit(); c.close()
            task = next(t for t in db.parse_file(str(path)) if t.task_id == 1)
            self.assertEqual((task.task_kind, task.profiler_size_bytes, task.duration), ('reduce_inline', 4, '1.001'))
            self.assertEqual(task.event_name, 'SDMA_SQE')
            semantic = replace(SemanticRecord(), device_id=0, stream_id=13, task_id=1,
                               task_kind='reduce_inline', source='aicpu')
            merged, stats = merge_records([semantic], [task])
            self.assertEqual(stats['exact_matched'], 1)
            self.assertEqual(merged[0]['profiler_size_bytes'], 4)
            merged, stats = merge_records([replace(semantic, task_kind='sdma')], [task])
            self.assertEqual(stats['exact_matched'], 0)

    def test_same_node_complete_channel_and_weakest_resource_evidence(self):
        rows, ranks = local_rows()
        resource = execution_row(2, 45, 3, 3, rank=9)
        resource.update(_node_id='run/node0', _device_id=2)
        rows.append(resource)
        edges, issues, handled = multi.build_rdma_notify_edges(rows, ranks, EVIDENCE)
        self.assertEqual(len(edges), 1)
        self.assertEqual(issues, [])
        self.assertEqual(edges[0]['kind'], 'same_node_rdma_notify_sync_observed')
        order = {'edge_id': 'semantic-order', 'kind': 'ffts_logical_stream_order',
                 'src': 'p1', 'dst': 'p2', 'confidence': 'semantic'}
        _, contracted, _ = build_resource_graph(rows, edges + [order])
        edge = next(e for e in contracted if 'same_node_rdma' in e['kind'])
        self.assertEqual(edge['confidence'], 'semantic')
        self.assertEqual(edge['kind'], 'resource_same_node_rdma_notify_sync_semantic')
        self.assertEqual(edge['wait_span_ns'], '1000')
        self.assertEqual(edge['remote_block_ns'], '')
        self.assertEqual(edge['timing_status'], 'same_node_rdma_completion_unmeasured')

    def test_same_node_missing_duplicate_multistream_and_conflict_fail_closed(self):
        for failure in ('missing', 'duplicate', 'stream', 'mapping', 'operation', 'notify', 'encoding'):
            with self.subTest(failure=failure):
                rows, ranks = local_rows()
                if failure == 'missing': rows = rows[:1]
                if failure == 'duplicate': rows.append(dict(rows[0], _graph_id='extra'))
                if failure == 'stream':
                    rows += [dict(r, _graph_id=r['_graph_id']+'extra', _stream_id=99) for r in rows[:]]
                if failure == 'mapping': rows[0]['_device_id'] = 11
                if failure == 'operation': rows[0]['_operation_scope_status'] = 'missing'
                if failure == 'notify': rows[1]['_notify_id'] += 1
                if failure == 'encoding': rows[1]['event_name'] = 'NOTIFY_WAIT'
                edges, issues, _ = multi.build_rdma_notify_edges(rows, ranks, EVIDENCE)
                self.assertEqual(edges, [])
                self.assertTrue(issues)

    def test_local_sdma_pairs_are_not_stolen_and_payload_is_not_a_signal(self):
        rows, ranks = local_rows()
        rows[0]['profiler_task_kind'] = 'notify_record'
        self.assertEqual(multi.build_rdma_notify_edges(rows, ranks, EVIDENCE), ([], [], frozenset()))
        rows, ranks = local_rows()
        rows[0]['_notify_id'] = 2**32-1
        self.assertEqual(multi.build_rdma_notify_edges(rows, ranks, EVIDENCE), ([], [], frozenset()))

    def test_repeated_local_channels_keep_identity_under_time_shift(self):
        rows, ranks = local_rows()
        for row in deepcopy(rows):
            row.update(_graph_id=row['_graph_id']+'second', _task_id=row['_task_id']+10,
                       _start=row['_start']+10, _stop=row['_stop']+10)
            rows.append(row)
        before = multi.build_rdma_notify_edges(rows, ranks, EVIDENCE)
        for row in rows:
            row['_start'] += 1000000; row['_stop'] += 1000000
        after = multi.build_rdma_notify_edges(rows[::-1], ranks, EVIDENCE)
        self.assertEqual(before, after)
        self.assertEqual(len(before[0]), 2)

    def test_operation_times_come_from_db_and_reject_bad_interval(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'msprof_test.db'
            create_msprof_db(path)
            self.assertEqual(db.parse_operations(str(path)), [])
            c = sqlite3.connect(path)
            c.executescript('ALTER TABLE COMMUNICATION_OP ADD COLUMN startNs INTEGER; '
                            'ALTER TABLE COMMUNICATION_OP ADD COLUMN endNs INTEGER;')
            start = 1790185900000000001
            c.execute('UPDATE COMMUNICATION_OP SET startNs=?,endNs=?', (start, start+12345))
            c.commit()
            op = db.parse_operations(str(path))[0]
            self.assertEqual(op.start_ns, start)
            self.assertEqual(op.end_ns-op.start_ns, 12345)
            c.execute('UPDATE COMMUNICATION_OP SET endNs=startNs-1'); c.commit(); c.close()
            with self.assertRaisesRegex(db.MsprofDbError, 'end precedes'):
                db.parse_operations(str(path))

    def test_operation_artifact_is_display_only_and_duration_is_exact(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'operations.csv'
            start = 1790185900000000001
            record = dict(node_id='run/node0', device_id=6, user_rank=3,
                          operation_scope='shared-call', op_name='AllReduce', group_name='group',
                          start_ns=start, end_ns=start+12345, duration_ns=12345)
            def write(records):
                with path.open('w', encoding='utf-8', newline='') as output:
                    writer = csv.DictWriter(output, fieldnames=list(record))
                    writer.writeheader(); writer.writerows(records)
            write([record])
            operations = view.read_operation_timings(path)
            self.assertEqual(operations[0]['_duration'], 12.345)
            single = view.build_execution_dependency_model([], [], operations)['nodes'][0]
            self.assertEqual((single['relativeStart'], single['relativeStop']), (0.0, 12.345))
            rows = cross_rows()
            edges, _, _ = multi.build_cross_node_edges(rows, RANKS, EVIDENCE)
            model = view.build_execution_dependency_model(rows, edges, operations)
            self.assertEqual(len(model['nodes']), len(rows)+1)
            self.assertEqual(len(model['edges']), len(edges))
            op = next(n for n in model['nodes'] if n['nodeKind']=='operation')
            self.assertEqual(op['duration'], 12.345)
            self.assertEqual(op['label'], 'Communication op')
            self.assertFalse(any(e['src']==op['id'] or e['dst']==op['id'] for e in model['edges']))
            write([record, record])
            with self.assertRaisesRegex(ValueError, 'duplicate operation'):
                view.read_operation_timings(path)
            write([dict(record, duration_ns=1)])
            with self.assertRaisesRegex(ValueError, 'invalid/duplicate'):
                view.read_operation_timings(path)

    def test_wait_inventory_includes_unresolved_and_follows_actual_edges(self):
        rows = cross_rows()
        edges, _, _ = multi.build_cross_node_edges(rows, RANKS, EVIDENCE)
        extra = dict(rows[1], _graph_id='unresolved', _task_id=11, _start=1, _stop=10)
        issues = [{'endpoint_graph_ids': 'unresolved', 'reason': 'missing metadata'}]
        waits = view.build_wait_inventory(rows+[extra], edges, issues)
        self.assertEqual(waits[0]['status'], 'unresolved')
        self.assertEqual(waits[0]['wait_span_ns'], '9000')
        self.assertEqual(waits[0]['reason'], 'missing metadata')
        self.assertEqual(waits[1]['record_graph_ids'], rows[0]['_graph_id'])
        self.assertEqual(waits[1]['peer_ranks'], '3')

    def test_html_distinguishes_timing_and_does_not_invent_counter_role(self):
        rows = cross_rows()
        rows[0]['profiler_task_kind'] = 'reduce_inline'
        rows[0]['profiler_size_bytes'] = '4'
        model = view.build_execution_dependency_model(rows, [])
        node = next(n for n in model['nodes'] if n['taskKind']=='reduce_inline')
        self.assertEqual(node['label'], 'Inline reduce')
        self.assertEqual(node['sizeBytes'], '4')
        self.assertIn('requires algorithm evidence', node['timingMeaning'])
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp)/'view.html'
            model['unsafe_example'] = '</script><script>bad()</script>'
            view.write_html(path, 'fixture', model)
            content = path.read_text(encoding='utf-8')
            self.assertNotIn('</script><script>bad()', content)
            self.assertIn('RDMA blocks show doorbell submission', content)

    def test_host_inline_reduce_display_requires_exact_semantic_match(self):
        row = dict(cross_rows()[0], profiler_task_kind='sdma', task_kind='reduce_inline',
                   match_confidence='exact', event_name='MEMCPY_ASYNC')
        model = view.build_execution_dependency_model([row], [])
        node = model['nodes'][0]
        self.assertEqual((node['label'], node['taskKind'], node['profilerTaskKind']),
                         ('Inline reduce', 'reduce_inline', 'sdma'))
        self.assertEqual(node['hardware'], 'MEMCPY_ASYNC')
        row['match_confidence'] = ''
        self.assertEqual(view.build_execution_dependency_model([row], [])['nodes'][0]['label'], 'Copy')


if __name__ == '__main__':
    unittest.main()
