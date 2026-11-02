"""Same-capture physical control/typed-task comparison with semantic anchors.

This is not algorithm annotation or cross-capture task matching. A resource
reused in the same unseparated region remains ambiguous; no ordinal is invented.
"""
from __future__ import annotations

from collections import defaultdict
from collections import Counter
from .compare_diagnosis import task_signature


def semantic_regions(rows, edges):
    nodes = {r['_graph_id']:r for r in rows}
    links = {direction:defaultdict(list) for direction in ('before','after')}
    for e in edges:
        if e.get('kind') == 'direct_stream_order_observed' and e.get('confidence') in {'observed','exact'}:
            links['before'][e['dst']].append(e['src'])
            links['after'][e['src']].append(e['dst'])
    labeled = lambda r: all(r.get(k) for k in ('algorithm','phase','event','semantic'))
    counts = Counter((r.get('_operation_scope'),task_signature(r)) for r in rows if labeled(r))
    stream_key=lambda r: (r.get('_operation_scope'),r['_node_id'],r['_device_id'],r['_stream_id'])
    members=defaultdict(set)
    for row in rows:
        members[stream_key(row)].add(row['_graph_id'])
    complete=set()
    for key,ids in members.items():
        before={i:[j for j in links['before'][i] if j in ids] for i in ids}
        after={i:[j for j in links['after'][i] if j in ids] for i in ids}
        heads=[i for i in ids if not before[i]]
        if len(heads)!=1 or any(len(before[i])>1 or len(after[i])>1 for i in ids):
            continue
        seen=set()
        current=heads[0]
        while current not in seen:
            seen.add(current)
            if not after[current]:
                break
            current=after[current][0]
        if seen==ids:
            complete.add(key)
    def frontier(row, direction):
        current, seen = row, set()
        while current['_graph_id'] not in seen:
            seen.add(current['_graph_id'])
            parents = links[direction][current['_graph_id']]
            if not parents:
                return ('operation_boundary',direction)
            if len(parents)!=1:
                return None
            parent=nodes[parents[0]]
            if any(parent[k]!=row[k] for k in ('_node_id','_device_id','_stream_id')):
                return None
            if parent.get('_operation_scope')!=row.get('_operation_scope'):
                return ('operation_boundary',direction)
            if labeled(parent):
                key=task_signature(parent)
                return ('semantic_anchor',*key) if counts[(row['_operation_scope'],key)]==1 else None
            current=parent
        return None
    result={}
    for row in rows:
        if row.get('_operation_scope_status')!='unique' or not row.get('_operation_scope') or stream_key(row) not in complete:
            continue
        if labeled(row):
            key=task_signature(row)
            if counts[(row['_operation_scope'],key)]==1:
                result[row['_graph_id']]=(('semantic_anchor',*key),('semantic_anchor',*key))
            continue
        a,b=frontier(row,'before'),frontier(row,'after')
        if a and b and any(x[0]=='semantic_anchor' for x in (a,b)):
            result[row['_graph_id']]=(a,b)
    return result


def unique_channel_keys(rows, edges):
    nodes = {r['_graph_id']: r for r in rows}
    channels = defaultdict(list)
    endpoints = defaultdict(list)
    regions = semantic_regions(rows, edges)
    for edge in edges:
        if 'notify_sync' in edge.get('kind', ''):
            endpoints[edge['src']].append(edge['edge_id'])
            endpoints[edge['dst']].append(edge['edge_id'])
        if edge.get('kind') not in {'direct_notify_sync_exact', 'local_notify_sync_exact'} or edge.get('confidence') != 'exact':
            continue
        source, target = nodes[edge['src']], nodes[edge['dst']]
        if (source.get('profiler_task_kind') != 'notify_record' or target.get('profiler_task_kind') != 'notify_wait'
                or source['_node_id'] != target['_node_id']
                or not source.get('_operation_scope') or source['_operation_scope'] != target.get('_operation_scope')):
            continue
        resource = source.get('_notify_id')
        if type(resource) is not int or resource < 0 or resource != target.get('_notify_id'):
            continue
        if any(r.get('_subtask_id', -1) >= 0 or r.get('_operation_scope_status') != 'unique' for r in (source, target)):
            continue
        if any(type(r.get(k)) is not int or r[k] < 0 for r in (source, target)
               for k in ('_device_id', '_stream_id', '_user_rank')):
            continue
        key = (source['_node_id'], resource, *(source[k] for k in ('_device_id', '_stream_id', '_user_rank')),
               *(target[k] for k in ('_device_id', '_stream_id', '_user_rank')))
        channels[(source['_operation_scope'], key)].append((source['_graph_id'], target['_graph_id']))
    result = {}
    for (_, channel), pairs in channels.items():
        buckets=defaultdict(list)
        for pair in pairs:
            if any(len(endpoints[key])!=1 for key in pair):
                continue
            if len(pairs)==1:
                buckets[()].append(pair)
            elif all(key in regions for key in pair):
                buckets[tuple(regions[key] for key in pair)].append(pair)
        for region,group in buckets.items():
            if len(group)!=1:
                continue
            for role,key in zip(('record','wait'),group[0]):
                result[key]=('same_capture_anchored_notify_channel' if region else 'same_capture_unique_notify_channel',
                             role,*channel,region)
    return result


def comparison_keys(rows, edges):
    result=unique_channel_keys(rows,edges)
    regions=semantic_regions(rows,edges)
    buckets=defaultdict(list)
    for row in rows:
        if row.get('profiler_task_kind') not in {'sdma','reduce_inline','rdma'} or row['_graph_id'] not in regions:
            continue
        key=('same_capture_anchored_task',row['_node_id'],row['_device_id'],row['_stream_id'],
             row['_user_rank'],row['_peer_rank'],row['profiler_task_kind'],str(row.get('profiler_size_bytes','')),
             regions[row['_graph_id']])
        buckets[(row['_operation_scope'],key)].append(row['_graph_id'])
    for (_,key),ids in buckets.items():
        if len(ids)==1:
            result[ids[0]]=key
    return result
