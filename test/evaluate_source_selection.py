#!/usr/bin/env python3
"""Evaluate sealed selected sources, keeping Host intervals separate from device tasks."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from test.audit_gpt_three_results import overlap
from test.replay_significant_regions import digest


def evaluate(report_path, original_evaluation_path):
    seal = json.loads(report_path.with_name('sealed.json').read_text())
    if digest(report_path) != seal['report_sha256'] or seal['truth_accessed'] is not False:
        raise ValueError('selection must be sealed before evaluation')
    report = json.loads(report_path.read_text())
    windows = json.loads(original_evaluation_path.read_text())['actual_windows']
    records = [dict(candidate_id=c['candidate_id'], node_id=c['node_id'], user_rank=c['user_rank'],
        iteration=c['iteration'], bucket=c.get('bucket'), task_kind=c['task_kind'],
        stream_id=c['stream_id'], task_id=c['task_id'], observed_start_ns=c['observed_start_ns'],
        observed_stop_ns=c['observed_stop_ns'], overlap_ns=overlap(c, windows), hit=overlap(c, windows) > 0)
        for c in report['candidates']]
    def counts(values):
        hits = sum(v['hit'] for v in values)
        return dict(hits=hits, count=len(values), precision=hits/len(values) if values else None)
    return dict(report_sha256=seal['report_sha256'], independent_evaluation_input_sha256=digest(original_evaluation_path),
        criterion='same_node_predeclared_rank_and_positive_actual_window_overlap',
        truth_accessed_only_after_seal=True, replay_scope='known_sample_decision_layer_not_independent_trial',
        selected_mechanism=report['selected_mechanism'], candidates=records,
        host_intervals=counts([v for v in records if v['task_kind'] == 'host_interval']),
        execution_tasks=counts([v for v in records if v['task_kind'] != 'host_interval']),
        first_candidate_hit=records[0]['hit'] if records else False,
        host_support_provenance=sorted({s['support_provenance'] for s in report['host_support_chains']}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--report', type=Path, required=True)
    parser.add_argument('--original-evaluation', type=Path, required=True)
    args = parser.parse_args()
    result = evaluate(args.report, args.original_evaluation)
    with args.report.with_name('evaluation.json').open('x') as stream:
        stream.write(json.dumps(result, indent=2)+'\n')
    print(json.dumps({k: v for k, v in result.items() if k != 'candidates'}))
