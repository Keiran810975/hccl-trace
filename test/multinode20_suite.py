"""Frozen twenty-case replication plan; private effect checks run after sealing."""
from __future__ import annotations

from copy import deepcopy
from decimal import Decimal

if __package__:
    from .multinode_dual_suite import plan as previous_plan
else:
    from multinode_dual_suite import plan as previous_plan


PROFILE = "multinode20-v1"
ROOT_NAME = "hccl-diagnose-node03-20261105-900"
CONTINUATION_ROOT = "hccl-diagnose-node03-20261106-1000"
CONTINUATION_PROFILE = "multinode19-lowlog-v1"
CONTINUATION_CASES = frozenset('hccl-diagnose-node03-20261106-' + str(i) for i in range(1002, 1021))
LOWLOG_CAPTURE = dict(global_log_level=2, module_override=False, task_time='l1', ai_core='off', hccl='on', ascendcl='on')
KINDS = ("copy_contention", "communication_contention", "progress_delay", "bandwidth_limit")


def plan():
    old = previous_plan()
    templates = {c['injection']['kind']: c for c in old['cases']}
    cases = []
    for repeat, iteration in enumerate((12, 17, 22, 27, 32)):
        target = 4 + repeat % 4
        for kind in KINDS:
            case = deepcopy(templates[kind])
            case.update(case_id='multinode20-{}-{:02d}'.format(kind, repeat + 1),
                        workload_seed=20261103)
            case['experiment_contract'].update(profile=PROFILE, source_policy='dual-v2',
                replication=repeat + 1, no_resampling=True, selected_iteration_view=True)
            inj = case['injection']
            inj.update(iteration=iteration, bucket_selector_seed=20261105 + repeat * 101,
                       target_rank=0 if kind == 'bandwidth_limit' else target)
            if kind == 'copy_contention':
                inj.update(declared_affected_ranks=[target], active_timeout_seconds=5)
            elif kind == 'communication_contention':
                inj.update(peer_rank=target - 4, declared_affected_ranks=[target - 4, target])
            cases.append(case)
    return dict(schema_version=1, profile=PROFILE, seed=20261105, requested_runs=20,
                cases=cases, diagnosis=dict(source_policy='dual-v2', reference_window=5,
                source_factor='1.5', downstream_factor='1.2', read_injection_truth=False),
                normal_reference='hccl-diagnose-node03-20261103-521',
                resource_scope=dict(node0_whole_host_idle=True, physical_cards=[4, 5, 6, 7],
                runtime_devices=[1, 3, 5, 7], stop_node3_target_processes_once_after_node0_idle=True))


def validate_case(case):
    if case not in plan()['cases']:
        raise ValueError('case differs from the frozen twenty-run plan')


def continuation_plan():
    value = plan()
    value.update(profile=CONTINUATION_PROFILE, requested_runs=19, cases=value['cases'][1:],
        origin_queue=ROOT_NAME, origin_completed_case=plan()['cases'][0]['case_id'],
        origin_result_included=False, capture_policy=dict(LOWLOG_CAPTURE))
    value['resource_scope']['stop_node3_target_processes_once_after_node0_idle'] = False
    return value


def queue_plan(root):
    if root.name == ROOT_NAME:
        return plan()
    if root.name == CONTINUATION_ROOT:
        return continuation_plan()
    raise ValueError('unknown reviewed queue')


def lowlog_capture(root):
    if root.name == 'hccl-diagnose-node03-20261108-1101':
        import json
        deployment = json.loads((root / 'deployment.json').read_text())
        if (deployment.get('profile') != 'roce-single-collective-v1'
                or deployment.get('capture_policy') != LOWLOG_CAPTURE):
            raise ValueError('single-collective RoCE requires its explicit low-log deployment')
        return True
    if root.name not in CONTINUATION_CASES:
        return False
    import json
    deployment = json.loads((root / 'deployment.json').read_text())
    if deployment.get('profile') != CONTINUATION_PROFILE or deployment.get('capture_policy') != LOWLOG_CAPTURE:
        raise ValueError('low-log capture requires its exact frozen deployment policy')
    return True


def intersects(row, window):
    return (row['node_id'] == window['node_id'] and int(row['user_rank']) == window['user_rank']
            and min(int(row['observed_stop_ns']), window['stop_ns']) >
            max(int(row['observed_start_ns']), window['start_ns']))


def effect_evidence(case, evaluation, rows, activities, public_delay=None):
    """This evaluator cannot change diagnosis, thresholds, candidates or graph edges."""
    validate_case(case)
    kind = case['injection']['kind']
    strong, waits = [], []
    for row in rows:
        if (row.get('task_domain') != 'hccl_internal' or row.get('stage') != 'measured'
                or int(row.get('reference_count') or 0) != 5 or row.get('duration_slow') not in (True, 'True')):
            continue
        if kind == 'progress_delay':
            overlap = (public_delay is not None and int(row['iteration']) == case['injection']['iteration']
                       and row.get('call_site') == public_delay['call_site'])
        else:
            overlap = any(intersects(row, w) for w in evaluation['windows'])
        if not overlap:
            continue
        if row['task_kind'] == 'notify_wait':
            waits.append(row['graph_id'])
        if row['task_kind'] not in {'sdma', 'reduce_inline'} or not row.get('slowdown_factor'):
            continue
        factor = Decimal(row['slowdown_factor'])
        if not factor.is_finite():
            continue
        if row['task_kind'] in {'sdma', 'reduce_inline'} and factor >= (2 if kind == 'copy_contention' else Decimal('1.5')):
            if kind == 'copy_contention':
                window = evaluation['windows'][0]
                activity = activities[0]
                offset = window['start_ns'] - activity['started_raw_ns']
                spans = activity.get('copy_host_envelopes_raw_ns', [])
                if not spans or not any(min(int(row['observed_stop_ns']), b + offset) >
                                       max(int(row['observed_start_ns']), a + offset) for a, b in spans):
                    continue
                if row['task_kind'] != 'sdma':
                    continue
            strong.append(row['graph_id'])
    numeric = all(a.get('operations', 0) > 0 and a.get('max_error') == 0 for a in activities)
    if kind == 'progress_delay':
        passed = public_delay is not None and public_delay['actual_delay_ns'] >= 450000000 and bool(waits)
    elif kind == 'bandwidth_limit':
        passed = bool(activities) and all(all(a.get(k) for k in
            ('applied_verified', 'restored_verified', 'foreground_path_verified')) and
            len(a.get('measurement_window', {}).get('completed_iterations', [])) == 5 for a in activities)
        passed = passed and (len(strong) >= 2 or bool(waits))
    else:
        passed = numeric and len(strong) >= 2
    return dict(case_id=case['case_id'], effect_gate_passed=passed,
                strong_internal_execution_count=len(strong), strong_internal_execution_ids=strong,
                slow_wait_count=len(waits), slow_wait_ids=waits, public_delay=public_delay,
                activity_operations=[a.get('operations') for a in activities],
                physical_causation_proven=False, rdma_hardware_duration_available=False,
                note='Copy uses individual API/sync spans; protocol waits are not intrinsic transfer durations.')
