"""Independent, post-diagnosis GPT overlap and paired-overhead evaluation."""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import sqlite3
import statistics

from hccl.tools.diagnosis import analyze_waits as waits
from hccl.tools.diagnosis import visualize_dependency_graph as graph
from hccl.tools.diagnosis.clock_alignment import raw_to_profiler


def inspect(root, name):
    public_path = root / 'reports' / name / 'root_causes.json'
    public_bytes = public_path.read_bytes()
    public = json.loads(public_bytes)
    matches = list((root / 'reports' / (name + '.debug')).glob('**/rolling/report.json'))
    if len(matches) != 1 or not public['quality']['pipeline_passed']:
        raise ValueError('complete independently generated report is required')
    report = json.loads(matches[0].read_text())
    counts = defaultdict(Counter)
    for task in report['tasks']:
        if task.get('stage') == 'measured' and task.get('iteration', -1) >= 5:
            counts[task['task_kind']][task['comparison_status']] += 1
    result = dict(candidate_count=len(public['candidates']), primary_candidate_id=public['primary_candidate_id'],
                  pipeline_quality=public['quality'], comparison_coverage={k: dict(v) for k, v in counts.items()},
                  report_sha256=hashlib.sha256(public_bytes).hexdigest(),
                  candidate_admission=public.get('candidate_admission'), reports=str(public_path.parent))
    if name == 'normal':
        return result
    activity = json.loads((root / 'numerics' / name / 'private/injection.json').read_text())
    if activity.get('validation_passed') is not True or activity['operations'] != 4:
        raise ValueError('the four finite copies did not complete numerical validation')
    runtime = json.loads((root / 'numerics' / name / 'runtime/rank-0.json').read_text())
    clocks = []
    for path in (root / 'captures' / name).rglob('msprof_*.db'):
        with sqlite3.connect(path.resolve().as_uri() + '?mode=ro', uri=True) as db:
            devices = {r[0] for r in db.execute('SELECT DISTINCT deviceId FROM TASK')}
        if devices == {runtime['runtime_device_id']}:
            clocks.append(json.loads((path.parent / 'host/start_info').read_text()))
    if len(clocks) != 1:
        raise ValueError('one target-device profiler clock is required')
    convert = lambda v: raw_to_profiler(v, clocks[0])
    envelope = [convert(activity[k]) for k in ('started_raw_ns', 'finished_raw_ns')]
    rows = graph.read_graph_artifact_nodes(matches[0].parent.parent / 'dep_graph_nodes.csv')
    background = [r for r in rows if r['_device_id'] == runtime['runtime_device_id']
                  and not r.get('_operation_scope') and r.get('profiler_task_kind') == 'sdma']
    options = []
    for begin, end in activity['copy_host_envelopes_raw_ns']:
        per_stream = defaultdict(list)
        for row in background:
            if convert(begin)-1000 <= waits.ns(row, 'start') < waits.ns(row, 'stop') <= convert(end)+1000:
                per_stream[row['_stream_id']].append(row)
        options.append({stream: values[0] for stream, values in per_stream.items() if len(values) == 1})
    streams = set.intersection(*(set(o) for o in options))
    device_intervals = None
    if len(streams) == 1:
        stream = streams.pop()
        copies = [o[stream] for o in options]
        if len({r['_graph_id'] for r in copies}) == 4:
            device_intervals = [[waits.ns(r, 'start'), waits.ns(r, 'stop')] for r in copies]
            result.update(copy_stream=stream, copy_task_ids=[r['_task_id'] for r in copies],
                          device_copy_intervals_ns=device_intervals,
                          copy_identity_evidence='unique common stream, one unbound SDMA per independently recorded finite-copy envelope; not a nearest-time match')
    def overlap(task, intervals):
        return sum(max(0, min(task['observed_stop_ns'], end)-max(task['observed_start_ns'], begin))
                   for begin, end in intervals)
    evaluated = []
    for candidate in public['candidates']:
        same = (candidate['node_id'] == name + '/node0' and candidate['user_rank'] == 0
                and candidate['device_id'] == runtime['runtime_device_id'])
        host_overlap = overlap(candidate, [envelope]) if same else 0
        actual_overlap = overlap(candidate, device_intervals) if same and device_intervals is not None else None
        evaluated.append(dict(candidate_id=candidate['id'], node_id=candidate['node_id'],
            rank=candidate['user_rank'], stream=candidate['stream_id'], task=candidate['task_id'],
            iteration=candidate['iteration'], host_envelope_overlap_ns=host_overlap,
            device_overlap_ns=actual_overlap, hit=host_overlap > 0,
            device_hit=actual_overlap > 0 if actual_overlap is not None else None))
    hit_count = sum(c['hit'] for c in evaluated)
    result.update(activity=activity, profiler_host_envelope_ns=envelope, candidate_evaluation=evaluated,
        hits=hit_count, candidate_precision=hit_count/len(evaluated) if evaluated else None,
        device_hits=sum(c['device_hit'] is True for c in evaluated) if device_intervals else None,
        primary_hit=next((c['hit'] for c in evaluated if c['candidate_id'] == public['primary_candidate_id']), False),
        analyzer_used_injection_truth=False, evaluator_used_truth_after_sealed_diagnosis=True,
        target_rank_slow_communication_tasks=[{k:t.get(k) for k in ('graph_id', 'iteration', 'call_site',
            'stream_id', 'task_id', 'task_kind', 'duration_ns', 'reference_mean_ns', 'delta_ns', 'slowdown_factor')}
            for t in report['tasks'] if t['user_rank']==0 and t.get('duration_slow')
            and t['task_kind'] in {'sdma', 'reduce_inline'} and overlap(t, [envelope]) > 0])
    if public_path.read_bytes() != public_bytes:
        raise ValueError('diagnosis changed during independent evaluation')
    return result


def overhead(root):
    state = json.loads((root / 'state.json').read_text())
    data = {c['name']: c['maximum_rank_mean_ns'] for c in state['completed']}
    pairs = []
    for repeat in range(3):
        prefix = 'overhead-' + str(repeat) + '-'
        off, semantic, profile = [data[prefix + m] for m in ('off', 'semantic', 'profile')]
        pairs.append(dict(repeat=repeat, off_ns=off, semantic_ns=semantic, profile_ns=profile,
                          semantic_percent=100*(semantic/off-1), profile_percent=100*(profile/off-1)))
    references = [p['off_ns'] for p in pairs]
    unstable = max(references)/min(references) > 1.25
    return dict(pairs=pairs, semantic_percent_mean=statistics.mean(p['semantic_percent'] for p in pairs),
        profile_percent_mean=statistics.mean(p['profile_percent'] for p in pairs),
        off_maximum_to_minimum=max(references)/min(references), reference_unstable=unstable,
        interpretation='descriptive paired differences; reference drift prevents a precise causal overhead estimate' if unstable else 'paired differences; limited repetitions',
        metric='per-iteration maximum across four ranks, mean of 50 measured iterations; three rotated paired repetitions',
        scope='same custom Host/Device, public call logging and numerical checks in every mode; excludes launch, export and offline diagnosis')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    args = parser.parse_args()
    result = dict(normal=inspect(args.root, 'normal'), strong_copy=inspect(args.root, 'strong-copy'), overhead=overhead(args.root))
    (args.root / 'experiment-summary.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({k:{a:b for a,b in v.items() if a in {'candidate_count','hits','device_hits','candidate_precision',
         'primary_hit','semantic_percent_mean','profile_percent_mean'}} for k,v in result.items()},indent=2))
