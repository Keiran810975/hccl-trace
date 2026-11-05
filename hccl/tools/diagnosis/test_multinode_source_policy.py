from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict
from dataclasses import replace
import unittest
from unittest.mock import patch

from .clock_alignment import DeviceClock
from .dependency_timing import edge_observation
from .local_slow_clusters import analyze
from .multinode_source_policy import select
from . import rolling_diagnosis as rolling, cross_node_diagnosis, rdma_timing
from .test_local_slow_clusters import history
from .test_significant_regions import task, edge
from .test_source_events import capture, cross_node_capture
from .test_cross_node_diagnosis import capture as protocol_capture
from .result_normalizer import normalize
from .source_propagation import build_report
from .source_propagation_view import render_html


class MultiNodeSourcePolicyTests(unittest.TestCase):
    def test_dual_skips_unused_legacy_backtrace_without_changing_selected_sources(self):
        for kwargs in (dict(execution_delay=True),dict(host_delay=True),{}):
            rows,edges,coords,preps=capture(**kwargs)
            legacy=rolling.analyze(rows,edges,coords,preparations=preps)
            with patch.object(rolling.wait_backtrace,'trace_sources',side_effect=AssertionError('unused legacy traversal')):
                fast=rolling.analyze(rows,edges,coords,replace(rolling.RollingOptions(),source_policy='dual'),preparations=preps)
            self.assertEqual([{k:v for k,v in t.items() if k!='role'} for t in legacy['tasks']],fast['tasks'])
            _,left=select(legacy,rows,edges,None)
            _,right=select(fast,rows,edges,None)
            self.assertEqual(left['selected_mechanism'],right['selected_mechanism'])
            self.assertEqual([c['candidate_id'] for c in left['candidates']],[c['candidate_id'] for c in right['candidates']])
    def test_calibrated_remote_doorbell_supports_topology_not_hardware_completion(self):
        work = task("work")
        submit = task("submit", "rdma", start=30, stop=31, mean="1")
        wait = task("wait", "notify_wait", start=1000020, stop=1000120, mean="10", rank=1)
        wait['node_id'] = 'node1'
        values = history([work, submit, wait])
        remote = dict(edge("submit", "wait", True), kind="cross_node_notify_sync_observed", confidence="observed")
        links = [edge("work", "submit"), remote]
        models = [DeviceClock('node0',0,0,0,0,1,1,0,10**9,1), DeviceClock('node1',1,1000000,0,0,1,1,0,10**9,1)]
        alignment = dict(schema_version=3,status='network_probe_estimate',models=list(map(asdict,models)))
        self.assertFalse(analyze(values, links)['chains'])
        original = deepcopy((values, links))
        result = analyze(values, links, alignment=alignment)
        self.assertEqual(len(result['chains']), 1)
        evidence = result['chains'][0]['timing_evidence'][remote['edge_id']]
        self.assertEqual(evidence['status'], 'accepted')
        self.assertFalse(evidence['hardware_completion_observed'])
        self.assertEqual((values, links), original)
        wait['observed_stop_ns'] = 1000000
        self.assertEqual(edge_observation(remote, submit, wait, {('node0',0):models[0],('node1',1):models[1]})['status'], 'incompatible_calibrated_notify_timestamps')

    def test_public_cross_node_host_evidence_survives_selection(self):
        rows, edges, coords, preps, alignment = cross_node_capture()
        original = rolling.analyze(rows, edges, coords, preparations=preps, alignment=alignment)
        chosen, result = select(original, rows, edges, alignment)
        self.assertEqual(result['selected_mechanism'], 'host_preparation_late')
        self.assertEqual(chosen['root_causes'][0]['component'], 'host_preparation')
        self.assertEqual(chosen['root_causes'][0]['graph_id'], 'i5p1')
        self.assertEqual(chosen['root_causes'][0]['support_evidence_version'], 1)

    def test_receiver_local_protocol_can_be_candidate_without_wire_time(self):
        rows, edges, coords = protocol_capture()
        coords = {k:dict(v,operation_scope=k,evidence='public fixture') for k,v in coords.items()}
        original = rolling.analyze(rows, edges, coords)
        protocols = cross_node_diagnosis.analyze(rdma_timing.analyze(rows, edges), rows, edges, coords, rolling.RollingOptions())
        before = deepcopy((rows, edges, protocols))
        chosen, result = select(original, rows, edges, None, protocols)
        self.assertEqual(result['selected_mechanism'], 'cross_node_protocol_slow')
        source, = chosen['root_causes']
        self.assertEqual(source['iteration'],7)
        self.assertIsNone(source['task_id'])
        self.assertEqual(source['component'],'protocol_interval')
        normalized, roots, tasks = normalize(chosen, mode='rolling', run_id='fixture', rows=rows, edges=edges,
            pipeline=dict(status='passed'),binding_evidence={})
        self.assertEqual(len(normalized['candidates']),1)
        propagation = build_report(rows,edges,roots,tasks)
        self.assertEqual(propagation['summary']['complete_chain_count'],1)
        self.assertIn('不是纯传输耗时',render_html(propagation,standalone=True))
        self.assertEqual((rows, edges, protocols), before)
        protocols['segments'][-1]['evidence_edge_ids'] = ['invented']
        with self.assertRaises(ValueError):
            select(original, rows, edges, None, protocols)

    def test_normal_has_no_host_or_protocol_proposal(self):
        rows, edges, coords, preps = capture()
        original = rolling.analyze(rows, edges, coords, preparations=preps)
        chosen, result = select(original, rows, edges, None)
        self.assertFalse(chosen['root_causes'])
        self.assertEqual(result['selected_mechanism'],'unlocalized')


if __name__ == '__main__':
    unittest.main()
