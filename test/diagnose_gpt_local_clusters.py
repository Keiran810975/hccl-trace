#!/usr/bin/env python3
"""Strict replay, resource Top1 and evidenced preparation-delay selection; no truth inputs."""
from __future__ import annotations

import argparse
import csv
from collections import Counter, defaultdict
from dataclasses import asdict
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from hccl.tools.diagnosis.multi_node_trace import replay_manifest
from hccl.tools.diagnosis import rolling_diagnosis as rolling
from hccl.tools.diagnosis import visualize_dependency_graph as graph
from hccl.tools.diagnosis.visualize_html import build_wait_inventory
from hccl.tools.diagnosis.local_slow_clusters import ClusterOptions, analyze
from hccl.tools.diagnosis.wait_backtrace import WORK_KINDS
from hccl.tools.diagnosis import source_selection
from test.replay_significant_regions import digest, render


def diagnose(manifest, coordinates_path, preparations_path, output, *, source_policy='dual'):
    if source_policy not in {'dual', 'execution-only'}:
        raise ValueError('unknown source policy')
    output.mkdir(parents=True, exist_ok=False)
    inputs = dict(manifest_sha256=digest(manifest), coordinates_sha256=digest(coordinates_path),
                  preparations_sha256=digest(preparations_path), truth_accessed=False,
                  rolling_options=asdict(rolling.RollingOptions()), cluster_options=asdict(ClusterOptions()),
                  source_policy=source_policy, selection_options=asdict(source_selection.SelectionOptions()))
    inputs['consumer_sha256'] = {name: digest(Path(__file__).resolve().parents[1]/name) for name in (
        'hccl/tools/diagnosis/local_slow_clusters.py', 'hccl/tools/diagnosis/significant_regions.py',
        'hccl/tools/diagnosis/rolling_diagnosis.py', 'hccl/tools/diagnosis/source_events.py',
        'hccl/tools/diagnosis/source_selection.py', 'test/diagnose_gpt_local_clusters.py')}
    (output/'input-manifest.json').write_text(json.dumps(inputs, indent=2)+'\n')
    directory, ready = replay_manifest(manifest, output/'analysis', 95)
    if not ready:
        raise ValueError('strict semantic/dependency replay failed; thresholds are not relaxed')
    print('strict replay passed', flush=True)
    rows = graph.read_graph_artifact_nodes(directory/'dep_graph_nodes.csv')
    edges = graph.read_graph_artifact_edges(directory/'dep_graph_edges.csv')
    coordinates = rolling.load_coordinates(coordinates_path)
    tasks = rolling.compare_tasks(rows, edges, coordinates, rolling.RollingOptions())
    report = analyze(tasks, edges, ClusterOptions())
    print('local Top1 completed', flush=True)
    observations = rolling.source_events.preparation_sources(
        rolling.source_events.load_preparations(preparations_path), rows, edges, coordinates, tasks,
        rolling.RollingOptions())
    report['external_host_observations'] = observations
    if source_policy == 'dual':
        report = source_selection.select_sources(report, observations)
    counts = defaultdict(Counter)
    for task in tasks:
        if task.get('stage') == 'measured' and task.get('iteration', -1) >= 5:
            counts[task['task_kind']][task['comparison_status']] += 1
    inventory = build_wait_inventory(rows, edges)
    report['quality'] = dict(strict_replay_passed=True, task_count=len(tasks),
        wait_count=len(inventory), paired_wait_count=sum(w['status'] == 'paired' for w in inventory),
        comparison_coverage={kind: dict(v) for kind,v in counts.items()},
        semantic_gate_source='analysis/merge_summary.csv', graph_gate_source='analysis/run_summary.csv')
    report['inputs'] = inputs
    fields = ('graph_id', 'node_id', 'user_rank', 'device_id', 'stream_id', 'task_id', 'operation_scope',
        'stage', 'iteration', 'call_site', 'task_kind', 'phase', 'step', 'event', 'observed_start_ns',
        'observed_stop_ns', 'duration_ns', 'reference_mean_ns', 'reference_mad_ns', 'reference_count',
        'slowdown_factor', 'delta_ns', 'duration_slow')
    with (output/'resource-comparisons.csv').open('x', newline='', encoding='utf-8') as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, extrasaction='ignore')
        writer.writeheader()
        writer.writerows(t for t in tasks if t.get('task_domain') == 'hccl_internal' and t['task_kind'] in WORK_KINDS)
    for name in ('merge_summary.csv', 'run_summary.csv', 'dep_graph_summary.csv'):
        (output/name).write_bytes((directory/name).read_bytes())
    path = output/'report.json'
    path.write_text(json.dumps(report, indent=2, ensure_ascii=False)+'\n')
    (output/'report.html').write_text((source_selection.render if source_policy == 'dual' else render)(report), encoding='utf-8')
    (output/'sealed.json').write_text(json.dumps(dict(report_sha256=digest(path),
        resource_comparisons_sha256=digest(output/'resource-comparisons.csv'), truth_accessed=False), indent=2)+'\n')
    print(json.dumps(report['summary']), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', type=Path, required=True)
    parser.add_argument('--coordinates', type=Path, required=True)
    parser.add_argument('--preparations', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--source-policy', choices=('dual', 'execution-only'), default='dual')
    args = parser.parse_args()
    diagnose(args.manifest, args.coordinates, args.preparations, args.output, source_policy=args.source_policy)
