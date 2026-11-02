"""Post-diagnosis audit: actual SDMA intervals, candidate hits and paired overhead."""
from __future__ import annotations

from collections import Counter, defaultdict
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import statistics

from hccl.tools.diagnosis import analyze_waits as waits
from hccl.tools.diagnosis import visualize_dependency_graph as graph


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def summary(root, name, *, prefix='coverage-v2-'):
    folder = root / 'reports' / (prefix + name)
    public = json.loads((folder / 'root_causes.json').read_text())
    paths = list(folder.with_name(folder.name + '.debug').glob('**/rolling/report.json'))
    if len(paths) != 1:
        raise ValueError('one retained diagnosis is required')
    analysis = paths[0].parent.parent
    report = json.loads(paths[0].read_text())
    rows = graph.read_graph_artifact_nodes(analysis / 'dep_graph_nodes.csv')
    counts = defaultdict(Counter)
    for t in report['tasks']:
        if t.get('stage') == 'measured' and t.get('iteration', -1) >= 5:
            counts[t['task_kind']][t['comparison_status']] += 1
    result = dict(coverage={k:dict(v) for k,v in counts.items()},
                  candidates=len(public['candidates']), primary=public['primary_candidate_id'],
                  paired_waits=public['quality']['paired_wait_count'], waits=public['quality']['wait_count'],
                  pipeline_passed=public['quality']['pipeline_passed'], reports=str(folder),
                  graph_nodes_sha256=sha(analysis/'dep_graph_nodes.csv'), graph_edges_sha256=sha(analysis/'dep_graph_edges.csv'))
    if name != 'strong-copy':
        return result
    # The analyzer has already finished and its outputs are sealed above.
    activity = json.loads((root / 'numerics/strong-copy/injection.json').read_text())
    lookup = {r['_graph_id']:r for r in rows}
    background = [r for r in rows if r['_device_id']==3 and not r.get('_operation_scope')
                  and r.get('profiler_task_kind')=='sdma']
    background.sort(key=lambda r: waits.ns(r,'start'))
    if len(background) != 5 or len({r['_stream_id'] for r in background}) != 1:
        raise ValueError('expected exactly one preparation and four injected copies on one owned stream')
    copies = background[1:]
    begin, end = waits.ns(copies[0],'start'), waits.ns(copies[-1],'stop')
    intervals = [(waits.ns(r,'start'),waits.ns(r,'stop')) for r in copies]
    def overlap(start,stop):
        return sum(max(0,min(stop,b)-max(start,a)) for a,b in intervals)
    targets = [t for t in report['tasks'] if t.get('stage')=='measured' and t.get('iteration')==15 and t['user_rank']==0]
    first = min(t['observed_start_ns'] for t in targets)
    last = max(t['observed_stop_ns'] for t in targets)
    evaluated = []
    for c in public['candidates']:
        row=lookup[c['graph_id']]
        value = overlap(waits.ns(row,'start'),waits.ns(row,'stop')) if row['_device_id']==3 else 0
        evaluated.append(dict(id=c['id'], rank=c['user_rank'], graph_id=c['graph_id'], overlap_ns=value,
                              hit=bool(value and c['user_rank']==0)))
    measured = [t for t in report['tasks'] if t.get('stage')=='measured' and t.get('iteration',-1)>=5
                and t['user_rank']==0 and t['reference_count']==5 and t['task_kind'] in {'sdma','reduce_inline'}]
    buckets=defaultdict(list)
    slow=defaultdict(int)
    for t in measured:
        key = 'overlapping_copy' if overlap(t['observed_start_ns'],t['observed_stop_ns']) else 'outside_copy'
        if t['slowdown_factor'] is not None:
            buckets[key].append(Decimal(t['slowdown_factor']))
            slow[key] += int(t['duration_slow'])
    result.update(actual_injection=activity, device_copy_intervals_ns=[[waits.ns(r,'start'),waits.ns(r,'stop')] for r in copies],
        copy_identity_evidence='exactly five unbound SDMA tasks on one stream: one worker preparation and four bounded injected copies; size absent from graph, not inferred as a DB field',
        copy_stream=copies[0]['_stream_id'], copy_task_ids=[r['_task_id'] for r in copies],
        target_collective_interval_ns=[first,last], actual_overlap_ns=overlap(first,last),
        interval_contained_in_collective=first<=begin<end<=last, candidate_evaluation=evaluated,
        hits=sum(e['hit'] for e in evaluated), candidate_precision=(sum(e['hit'] for e in evaluated)/len(evaluated) if evaluated else None),
        task_factor_distributions={k:dict(count=len(v),slow_count=slow[k],median=str(statistics.median(v)),maximum=str(max(v))) for k,v in buckets.items()},
        assessment='posthoc same Node/Rank positive device-interval overlap; no injection truth was supplied to analysis')
    return result


def overhead(root):
    data={}
    for repeat in range(5):
        for mode in ('off','semantic','profile'):
            samples=[json.loads((root/'numerics'/f'overhead-{repeat}-{mode}'/f'rank-{rank}.json').read_text()) for rank in range(3)]
            series=[[t['elapsed_ns'] for t in r['samples'] if t['stage']=='measured'] for r in samples]
            data[(repeat,mode)]=statistics.mean(max(row[i] for row in series) for i in range(30))
    pairs=[]
    for repeat in range(5):
        off=data[(repeat,'off')]
        pairs.append(dict(repeat=repeat,off_ns=off,semantic_ns=data[(repeat,'semantic')],profile_ns=data[(repeat,'profile')],
                     semantic_percent=100*(data[(repeat,'semantic')]/off-1),profile_percent=100*(data[(repeat,'profile')]/off-1)))
    return dict(metric='mean of per-iteration maximum across three ranks, 30 measured iterations',pairs=pairs,
                semantic_percent_mean=statistics.mean(p['semantic_percent'] for p in pairs),
                profile_percent_mean=statistics.mean(p['profile_percent'] for p in pairs),
                fixed_scope='same custom Host/Device, public SDK logging and checks in all modes; no injected load; excludes launch/export/offline time')


if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',type=Path,required=True)
    parser.add_argument('--prefix',default='coverage-v2-')
    parser.add_argument('--output-name',default='experiment-summary.json')
    args=parser.parse_args()
    result=dict(normal=summary(args.root,'normal',prefix=args.prefix),strong_copy=summary(args.root,'strong-copy',prefix=args.prefix),overhead=overhead(args.root))
    (args.root/args.output_name).write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2))
