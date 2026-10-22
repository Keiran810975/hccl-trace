#!/usr/bin/env python3
"""Verify the fixed 2x4-rank Ring/NHR capture and its independent fault oracle."""
from __future__ import annotations

import argparse
from collections import Counter
from copy import deepcopy
from decimal import Decimal
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from hccl.tools.diagnosis import analyze_waits as diagnosis
from hccl.tools.diagnosis import visualize_dependency_graph as graph


def load(directory):
    rows = graph.read_graph_artifact_nodes(directory / 'dep_graph_nodes.csv')
    edges = graph.read_graph_artifact_edges(directory / 'dep_graph_edges.csv')
    issues = diagnosis.read_csv(directory / 'dep_graph_notify_ambiguities.csv')
    spans = [row for path in directory.glob('node*/build_spans.csv') for row in diagnosis.read_csv(path)]
    return rows, edges, issues, spans


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline', type=Path, required=True)
    parser.add_argument('--ring', type=Path, required=True)
    parser.add_argument('--nhr', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    baseline = load(args.baseline)
    assert not diagnosis.analyze(*baseline)['candidates']
    reports = {}
    for name, directory, rank, algorithm, phase, step in (
        ('ring', args.ring, 3, 'single_ring_direct', 'reduce_scatter_direct', 1),
        ('nhr', args.nhr, 7, 'nhr', 'reduce_scatter', 0),
    ):
        rows, edges, issues, spans = load(directory)
        result = diagnosis.analyze(rows, edges, issues, spans, baseline[0])
        gates = {r['metric']: r['value'] for r in diagnosis.read_csv(directory / 'run_summary.csv')}
        assert gates['graph_gate_passed'] == gates['replay_gate_passed'] == '1'
        assert gates['cross_node_edges'] == '288' and not issues
        assert len(result['waits']) == 1504 and all(w['status'] == 'paired' for w in result['waits'])
        candidates = result['candidates']
        assert len(candidates) == 4 and len({c['operation_scope'] for c in candidates}) == 4
        assert all((c['user_rank'], c['algorithm'], c['phase'], int(c['step'])) ==
                   (rank, algorithm, phase, step) and c['category'] == 'slow_aicpu_build'
                   and 39_000_000 <= c['duration_ns'] <= 100_000_000 for c in candidates)
        by_id = {e['edge_id']: e for e in edges}
        by_node = {r['_graph_id']: r for r in rows}
        long_waits = [w for w in result['waits'] if w['classification'] == 'upstream_slow_candidate']
        cross_node_examples = []
        for candidate in candidates:
            waits = [w for w in long_waits if candidate['id'] in w['candidate_ids'].split(';')
                     and w['node_id'] != candidate['node_id']]
            assert waits, 'No observed cross-node downstream wait for the injected operation'
            wait = max(waits, key=lambda w: Decimal(w['wait_span_ns']))
            path = [by_id[eid] for eid in wait['evidence_path_edge_ids'].split(';')]
            assert path[-1]['dst'] == wait['wait_graph_id']
            assert all(a['dst'] == b['src'] for a, b in zip(path, path[1:]))
            origin = by_node[path[0]['src']]
            assert origin['_user_rank'] == rank
            assert (origin['algorithm'], origin['phase'], int(origin['step'])) == (algorithm, phase, step)
            assert any(e['kind'] == 'cross_node_notify_sync_observed' for e in path)
            assert wait['attribution'] == 'upstream_rank_operation_correlation'
            cross_node_examples.append(dict(wait_graph_id=wait['wait_graph_id'], rank=wait['user_rank'],
                operation_scope=wait['operation_scope'], wait_span_ns=wait['wait_span_ns'],
                path_edge_ids=wait['evidence_path_edge_ids']))
        shifted = deepcopy(rows)
        for row in shifted:
            if row['_node_id'].endswith('/node1'):
                for side in ('start', 'stop'):
                    row['_'+side+'_order'] = graph.execution_time_order_value(row, side) + Decimal(10**12)
                    row['_'+side] = float(row['_'+side+'_order'])
        replay = diagnosis.analyze(shifted, edges, issues, spans, baseline[0])
        assert replay == result, 'Uncalibrated clock translation changed the diagnosis'
        try:
            diagnosis.analyze(rows + rows[:1], edges)
            raise AssertionError('duplicate execution accepted')
        except ValueError:
            pass
        chosen = long_waits[0]
        missing_edges = [e for e in edges if not
                         (e['dst'] == chosen['wait_graph_id'] and 'notify_sync' in e['kind'])]
        missing = diagnosis.analyze(rows, missing_edges, issues, spans, baseline[0])
        gap = next(w for w in missing['waits'] if w['wait_graph_id'] == chosen['wait_graph_id'])
        assert gap['classification'] == 'evidence_gap' and not gap['candidate_ids']
        reports[name] = dict(candidates=len(candidates), expected_rank=rank, phase=phase, step=step,
            duration_ns=[c['duration_ns'] for c in candidates],
            classifications=dict(Counter(w['classification'] for w in result['waits'])),
            cross_node_examples=cross_node_examples, clock_translation='PASS',
            missing_sync_endpoint='PASS', duplicate_execution='PASS')
    args.output.write_text(json.dumps(reports, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    print('RING_NHR_DIAGNOSIS_AND_PERTURBATION_PASS')


if __name__ == '__main__':
    main()
