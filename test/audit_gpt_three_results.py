"""Verify compact three-case receipts and independently recount overlap hits."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path
import statistics


def digest(path):
    result = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024*1024), b''):
            result.update(block)
    return result.hexdigest()


def overlap(task, windows):
    return sum(max(0, min(int(task['observed_stop_ns']), w['stop_ns'])
        - max(int(task['observed_start_ns']), w['start_ns'])) for w in windows
        if task['node_id'] == w['node_id'] and int(task['user_rank']) in w['target_ranks'])


def audit_case(attempt):
    receipt = json.loads((attempt/'retention-receipt.json').read_text())
    for name, expected in receipt['retained_sha256'].items():
        path = attempt/name
        if not path.resolve().is_relative_to(attempt.resolve()) or digest(path) != expected:
            raise ValueError('missing or modified retained evidence: '+name)
    seal = json.loads((attempt/'top1/sealed.json').read_text())
    if digest(attempt/'top1/report.json') != seal['report_sha256']:
        raise ValueError('report changed after diagnosis')
    if digest(attempt/'top1/resource-comparisons.csv') != seal['resource_comparisons_sha256']:
        raise ValueError('resource comparison evidence changed after diagnosis')
    report = json.loads((attempt/'top1/report.json').read_text())
    evaluation = json.loads((attempt/'evaluation.json').read_text())
    windows = evaluation['actual_windows']
    candidates = report['candidates']
    decisions = {c['candidate_id']: c for c in evaluation['candidates']}
    if len(decisions) != len(candidates):
        raise ValueError('evaluation candidate set differs from the sealed diagnosis')
    for task in candidates:
        decision = decisions[task['candidate_id']]
        if decision['overlap_ns'] != overlap(task, windows) or decision['hit'] != (overlap(task, windows) > 0):
            raise ValueError('independent candidate/window overlap disagrees')
    execution = report.get('execution_proposal', report)
    edges = {e['edge_id']: e for e in execution['edges']}
    for chain in report['chains']:
        current = chain['source_graph_id']
        for key in chain['edge_ids']:
            edge = edges[key]
            if edge['src'] != current:
                raise ValueError('non-contiguous propagation path')
            current = edge['dst']
        if current != chain['target_graph_id']:
            raise ValueError('propagation target differs from the retained path')
    factors = dict(inside=[], outside=[])
    slow = dict(inside=0, outside=0)
    with (attempt/'top1/resource-comparisons.csv').open(newline='', encoding='utf-8') as stream:
        for task in csv.DictReader(stream):
            if int(task['reference_count']) != 5 or not task['slowdown_factor']:
                continue
            key = 'inside' if overlap(task, windows) > 0 else 'outside'
            factors[key].append(float(task['slowdown_factor']))
            slow[key] += task['duration_slow'] == 'True'
    results = [json.loads(p.read_text()) for p in sorted((attempt/'retained/workload_results').glob('rank-*.json'))]
    if len(results) != 4 or any(r['status'] != 'passed' or r['warmup'] != 10 or r['iters'] != 50 for r in results):
        raise ValueError('incomplete four-rank 10+50 training')
    if any(r['initialization'] != results[0]['initialization'] or r['parameter_samples'] != results[0]['parameter_samples'] for r in results):
        raise ValueError('training replicas disagree')
    cleanup = json.loads((attempt/'cleanup.json').read_text())
    if (attempt/'capture').exists() or (attempt/'top1/analysis').exists():
        raise ValueError('large consumed capture/analysis has not been removed')
    if not json.loads((attempt/'restoration-verified.json').read_text())['restored']:
        raise ValueError('device restoration receipt missing')
    hits = sum(overlap(task, windows) > 0 for task in candidates)
    if hits != evaluation['hits'] or len(candidates) != evaluation['candidate_count']:
        raise ValueError('reported candidate precision differs from independent audit')
    primary_hits = sum(overlap(task, windows) > 0 and int(task['user_rank'])
        == evaluation['injection']['target_rank'] for task in candidates)
    if primary_hits != evaluation['primary_target_rank_hits']:
        raise ValueError('primary-target-only precision differs from independent audit')
    host_hits = sum(overlap(task, windows) > 0 for task in report['external_host_observations'])
    if host_hits != evaluation['host_observation_hits']:
        raise ValueError('Host observation overlap differs from independent audit')
    def typed_counts(host):
        values = [c for c in candidates if (c['task_kind'] == 'host_interval') == host]
        found = sum(overlap(c, windows) > 0 for c in values)
        primary = sum(overlap(c, windows) > 0 and c['user_rank'] == evaluation['injection']['target_rank'] for c in values)
        return dict(hits=found, count=len(values), primary_target_hits=primary,
                    precision=found/len(values) if values else None)
    return dict(case_id=evaluation['case_id'], injection=evaluation['injection'],
        selected_mechanism=report.get('selected_mechanism', 'communication_execution_growth'),
        execution_tasks=typed_counts(False), host_intervals=typed_counts(True),
        actual_windows=windows, hits=hits, candidate_count=len(candidates),
        precision=hits/len(candidates) if candidates else None,
        primary_target_rank_hits=primary_hits,
        first_candidate_hit=evaluation['first_candidate_hit'], candidates=evaluation['candidates'],
        propagation_chain_count=len(report['chains']), paired_wait_count=report['quality']['paired_wait_count'],
        wait_count=report['quality']['wait_count'],
        host_observation_count=len(report['external_host_observations']), host_observation_hits=host_hits,
        resource_factors={k: dict(count=len(v), slow_count=slow[k],
            median=statistics.median(v) if v else None,
            maximum=max(v) if v else None) for k,v in factors.items()},
        max_rank_iteration25_ms=max(r['iteration_ns'][25] for r in results)/1e6,
        prior_five_max_rank_mean_ms=statistics.mean(max(r['iteration_ns'][i] for r in results) for i in range(20,25))/1e6,
        cleaned_bytes=sum(r['bytes'] for r in cleanup['removed']),
        diagnosis_options=report['options'], inputs=report['inputs'],
        independently_recounted=True, raw_inputs_no_longer_replayable=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory', type=Path)
    parser.add_argument('--expected-completed', type=int, choices=(1,2,3), default=3)
    args = parser.parse_args()
    paths=sorted(args.directory.glob('gpt2-three-anomalies-20261102-10[123]'))
    summaries = [audit_case(path) for path in paths if (path/'evaluation.json').is_file()]
    if len(summaries) != args.expected_completed:
        raise ValueError('completed case count differs from the explicit audit expectation')
    if any(s['diagnosis_options'] != summaries[0]['diagnosis_options']
            or s['inputs']['consumer_sha256'] != summaries[0]['inputs']['consumer_sha256'] for s in summaries):
        raise ValueError('diagnosis changed between independent cases')
    pending=[path.name for path in paths if not (path/'evaluation.json').is_file()]
    total=sum(s['execution_tasks']['count'] for s in summaries)
    hits=sum(s['execution_tasks']['hits'] for s in summaries)
    primary_hits=sum(s['execution_tasks']['primary_target_hits'] for s in summaries)
    host_total=sum(s['host_intervals']['count'] for s in summaries)
    host_hits=sum(s['host_intervals']['hits'] for s in summaries)
    (args.directory/'audit-summary.json').write_text(json.dumps(dict(cases=summaries,
        completed=len(summaries),requested=3,not_completed=pending,
        execution_candidates=dict(hits=hits,total=total,precision=hits/total if total else None,
            criterion='same Node, predeclared affected endpoint Rank, positive actual-activity overlap'),
        host_intervals=dict(hits=host_hits,total=host_total,precision=host_hits/host_total if host_total else None),
        primary_target_only=dict(hits=primary_hits,total=total,precision=primary_hits/total if total else None)), indent=2)+'\n')
    print(json.dumps([{k:s[k] for k in ('case_id','hits','candidate_count','precision','host_observation_hits','propagation_chain_count')} for s in summaries], indent=2))
