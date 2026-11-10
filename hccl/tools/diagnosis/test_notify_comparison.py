from __future__ import annotations

from copy import deepcopy
import unittest

from . import rolling_diagnosis as rolling
from .notify_comparison import unique_channel_keys
from .test_source_events import capture


def controls():
    rows, edges, coords, _ = capture(execution_delay=True)
    for row in rows:
        row['_operation_scope_status'] = 'unique'
        if row['profiler_task_kind'] in {'notify_record', 'notify_wait'}:
            row.update(algorithm='', phase='', event='', semantic='', _notify_id=2**64-17)
    return rows, edges, coords


class NotifyComparisonTests(unittest.TestCase):
    def test_reused_channel_requires_distinct_unique_semantic_regions(self):
        rows, edges, coords=controls()
        for i in range(6):
            source=next(r for r in rows if r['_graph_id']==f'i{i}p0')
            record=next(r for r in rows if r['_graph_id']==f'i{i}p1')
            wait=next(r for r in rows if r['_graph_id']==f'i{i}p2')
            tail=next(r for r in rows if r['_graph_id']==f'i{i}p3')
            anchor=deepcopy(source)
            anchor.update(_graph_id=f'anchor-{i}',event='between_record_reuses')
            r2=deepcopy(record); r2['_graph_id']+= '-repeat'
            w2=deepcopy(wait); w2['_graph_id']+= '-repeat'
            rows.extend([anchor,r2,w2])
            for a,b in ((record,anchor),(anchor,r2),(tail,w2)):
                edges.append(dict(edge_id=a['_graph_id']+'-to-'+b['_graph_id'],src=a['_graph_id'],dst=b['_graph_id'],
                                  kind='direct_stream_order_observed',confidence='observed'))
            edges.append(dict(edge_id=f'repeat-pair-{i}',src=r2['_graph_id'],dst=w2['_graph_id'],
                              kind='direct_notify_sync_exact',confidence='exact'))
        keys=unique_channel_keys(rows,edges)
        self.assertEqual(keys['i5p1'][0],'same_capture_anchored_notify_channel')
        self.assertNotEqual(keys['i5p1'],keys['i5p1-repeat'])
        tasks=rolling.compare_tasks(rows,edges,coords,rolling.RollingOptions())
        self.assertTrue(all(t['reference_count']==5 for t in tasks if t['graph_id'] in {'i5p1','i5p1-repeat','i5p2','i5p2-repeat'}))

    def test_opaque_typed_work_between_unique_anchors_is_not_given_fake_semantics(self):
        rows,edges,coords,_=capture(execution_delay=True)
        for row in rows:
            row['_operation_scope_status']='unique'
        for i in range(6):
            source=next(r for r in rows if r['_graph_id']==f'i{i}p0')
            helper=deepcopy(source)
            helper.update(_graph_id=f'helper-{i}',profiler_task_kind='reduce_inline',profiler_size_bytes='4',
                          algorithm='',phase='',event='',semantic='',_duration=1)
            rows.append(helper)
            old=next(e for e in edges if e['edge_id']==f'i{i}e0')
            record_id=old['dst']; old['dst']=helper['_graph_id']
            edges.append(dict(old,edge_id=f'helper-to-record-{i}',src=helper['_graph_id'],dst=record_id))
        tasks=rolling.compare_tasks(rows,edges,coords,rolling.RollingOptions())
        helper=next(t for t in tasks if t['graph_id']=='helper-5')
        self.assertEqual(helper['reference_count'],5)
        self.assertEqual(helper['comparison_basis'],'same_capture_anchored_task')
        self.assertEqual(helper['phase'],'')
        # A missing order edge leaves a disconnected operation stream. It must
        # not be relabeled as an operation boundary to create a comparison.
        edges=[e for e in edges if e['edge_id']!='helper-to-record-5']
        tasks=rolling.compare_tasks(rows,edges,coords,rolling.RollingOptions())
        self.assertEqual(next(t for t in tasks if t['graph_id']=='helper-5')['reference_count'],0)

    def test_opaque_single_occurrence_channel_can_compare_without_inventing_a_phase(self):
        rows, edges, coords = controls()
        original = deepcopy((rows, edges))
        tasks = rolling.compare_tasks(rows, edges, coords, rolling.RollingOptions())
        selected = [t for t in tasks if t['graph_id'] in {'i5p1', 'i5p2'}]
        self.assertEqual(len(selected), 2)
        for task in selected:
            self.assertEqual(task['reference_count'], 5)
            self.assertEqual(task['comparison_basis'], 'same_capture_unique_notify_channel')
            self.assertEqual((task['algorithm'], task['phase'], task['event']), ('', '', ''))
        self.assertEqual((rows, edges), original)

    def test_multiple_reuses_never_receive_an_ordinal_comparison_key(self):
        rows, edges, _ = controls()
        for index in range(6):
            for suffix in ('p1', 'p2'):
                row = deepcopy(next(r for r in rows if r['_graph_id'] == 'i' + str(index) + suffix))
                row['_graph_id'] += '-repeat'
                rows.append(row)
            edge = deepcopy(next(e for e in edges if e['edge_id'] == 'i' + str(index) + 'e1'))
            edge.update(edge_id=edge['edge_id']+'-repeat', src=edge['src']+'-repeat', dst=edge['dst']+'-repeat')
            edges.append(edge)
        self.assertEqual(unique_channel_keys(rows, edges), {})

    def test_missing_pair_or_changed_resource_history_cannot_be_silently_zipped(self):
        for change in ('missing_pair', 'resource', 'device'):
            rows, edges, coords = controls()
            if change == 'missing_pair':
                edges = [e for e in edges if e['edge_id'] != 'i2e1']
            else:
                for row in rows:
                    if row['_graph_id'] in {'i2p1', 'i2p2'}:
                        row['_notify_id' if change == 'resource' else '_device_id'] += 1
            tasks = rolling.compare_tasks(rows, edges, coords, rolling.RollingOptions())
            for task in tasks:
                if task['graph_id'] in {'i5p1', 'i5p2'}:
                    self.assertEqual(task['reference_iterations'], [0, 1, 3, 4])

    def test_cross_node_and_nonexact_edges_are_not_this_comparison_basis(self):
        for change in ('node', 'confidence'):
            rows, edges, _ = controls()
            if change == 'node':
                for row in rows:
                    if row['profiler_task_kind'] == 'notify_wait':
                        row['_node_id'] = 'other-node'
            else:
                for edge in edges:
                    if 'notify_sync' in edge['kind']:
                        edge['confidence'] = 'observed'
            self.assertEqual(unique_channel_keys(rows, edges), {})
