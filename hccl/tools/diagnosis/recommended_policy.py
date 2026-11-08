"""Two supported rolling selectors, chosen from observed node identity."""
from __future__ import annotations

from .task_classifier import SINGLE_NODE_SOURCE_POLICY


def select(report, rows, edges, alignment=None):
    nodes = sorted({r['_node_id'] for r in rows})
    if not nodes:
        raise ValueError('automatic diagnosis requires observed node identities')
    if len(nodes) == 1:
        from .multinode_source_policy import select as local_dual
        # No protocol symptom proposals: this is the validated local cluster/Host path.
        chosen, decision = local_dual(report, rows, edges, alignment, protocol_report=None)
        policy = SINGLE_NODE_SOURCE_POLICY
        decision['policy'] = policy
        decision['cluster_selection'] = dict(decision['execution_proposal']['cluster_selection'])
        for root in chosen['root_causes']:
            root.update(source_selection_policy=policy,
                source_unit='host_preparation' if root['component'] == 'host_preparation' else 'execution_task')
        chosen.update(source_selection_policy=policy, source_policy_version=policy,
                      primary_source_candidate_id=None, candidate_relationship='parallel')
    else:
        from .cohort_source_policy import select as distributed
        chosen, decision = distributed(report, edges, alignment)
        policy = decision['policy']
        chosen['limits'] = [s for s in chosen['limits'] if 'default and original' not in s]
    _retain_unlinked_waits(chosen, edges)
    return chosen, decision, dict(node_count=len(nodes), node_ids=nodes,
        execution_mode='single_node' if len(nodes) == 1 else 'multi_node',
        selected_policy=policy, detection='observed_graph_node_identity_not_rank_count',
        limitations=['Known-sample validated selection, not calibrated physical-fault accuracy.',
                     'Communication contention, RoCE localization and normal false alarms remain limited.'])


def _retain_unlinked_waits(report, edges):
    """Keep slow Wait facts even when Top1 selects no source explaining them."""
    from collections import defaultdict
    from .local_slow_clusters import ClusterOptions
    from .significant_regions import slow
    options = ClusterOptions(source_factor=report['options']['slowdown_factor'],
                             mad_multiplier=report['options']['mad_multiplier'])
    producers = defaultdict(list)
    for edge in edges:
        if 'notify_sync' in edge['kind']:
            producers[edge['dst']].append(edge)
    linked = {target for root in report['root_causes'] for target, path in root.get('evidence_paths', {}).items() if path}
    waits = [t for t in report['tasks'] if t['task_kind'] == 'notify_wait'
             and slow(t, options.propagation_factor, options)]
    observations = []
    for task in waits:
        if task['graph_id'] in linked:
            continue
        pairs = producers[task['graph_id']]
        pairing = ('unpaired' if not pairs else 'ambiguous' if len(pairs) != 1 else
                   'paired' if pairs[0]['confidence'] in {'observed', 'exact'} else 'unsupported_evidence')
        fields = ('graph_id', 'node_id', 'user_rank', 'device_id', 'stream_id', 'task_id', 'operation_scope',
            'stage', 'iteration', 'group_id', 'call_site', 'occurrence', 'block', 'bucket', 'phase', 'step',
            'event', 'task_kind', 'observed_start_ns', 'observed_stop_ns', 'duration_ns', 'reference_count',
            'reference_iterations', 'reference_graph_ids', 'reference_mean_ns', 'reference_mad_ns', 'delta_ns', 'slowdown_factor')
        observations.append(dict({key: task.get(key) for key in fields}, kind='slow_wait_observation',
            status='slow_wait_not_linked_to_selected_source', notify_pairing_status=pairing,
            reason='Observed slow Wait is not linked to the selected source; no additional backtrace or physical cause is inferred.'))
    report['unresolved_observations'] = list(report.get('unresolved_observations', [])) + observations
    report['coverage'] = dict(report.get('coverage', {}), observed_slow_wait_count=len(waits),
        selected_source_linked_slow_wait_count=sum(t['graph_id'] in linked for t in waits),
        not_linked_to_selected_source_slow_wait_count=len(observations))
    if not report['root_causes'] and observations:
        report['diagnosis_status'] = 'unresolved_waits'
