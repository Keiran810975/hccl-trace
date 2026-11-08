"""One isolated GPT RoCE attempt; never resume the old queue or stop foreign work."""
from __future__ import annotations

import argparse
import csv
import fcntl
import json
import os
from pathlib import Path
import socket
import signal
import subprocess
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parent))
from roce_single_collective import ROOT_NAME, PROFILE, case, validate_case, read, audit_public_window
from run_node03_preflight import LOCAL_PARENT, PEER_PARENT, write, execute
from run_node03_authorized import root_command
from run_multinode20 import resources, idle, sha
from run_communication_calibration import protected_run


def inspect_effect(root, evaluation):
    seal = read(root / 'diagnosis-seal.json')
    if (seal.get('truth_accessed') is not False
            or set(seal.get('sha256', {})) != {'execution.html', 'root_causes.json', 'propagation.html'}
            or any(sha(root / 'report' / n) != h for n, h in seal['sha256'].items())):
        raise ValueError('independent effect audit requires the original sealed diagnosis')
    value = read(root / 'input/case.json')
    activity = read(root / 'gpt-output/private/network-result.json')
    public = audit_public_window(root, value, activity)
    expected = public['identity']
    site = 'ddp.gradient.' + expected['bucket_signature']
    analysis = root / 'report.debug/analysis' / value['case_id']
    with (analysis / 'rolling/task_comparison.csv').open(newline='', encoding='utf-8-sig') as source:
        tasks = [r for r in csv.DictReader(source) if r['stage'] == 'measured'
                 and int(r['iteration']) == expected['iteration'] and r['call_site'] == site
                 and r['node_id'] == value['case_id'] + '/node0' and int(r['user_rank']) == 0]
    rdma = [r for r in tasks if r['task_kind'] == 'rdma' and any(
        min(int(r['observed_stop_ns']), w['stop_ns']) > max(int(r['observed_start_ns']), w['start_ns'])
        for w in evaluation['windows'] if w['user_rank'] == 0)]
    with (analysis / 'cross_node/segments.csv').open(newline='', encoding='utf-8-sig') as source:
        paths = [r for r in csv.DictReader(source) if r['status'] == 'protocol_interval_observed'
                 and r['stage'] == 'measured' and int(r['iteration']) == expected['iteration']
                 and r['call_site'] == site and r['sender_rank'] == '0'
                 and r['sender_node_id'] == value['case_id'] + '/node0']
    if len({r['transfer_id'] for r in paths}) != len(paths):
        raise ValueError('duplicate protocol intervals cannot inflate effect evidence')
    references = [r for r in paths if r['reference_count'] == '5'
                  and json.loads(r['reference_iterations']) == list(range(expected['iteration'] - 5, expected['iteration']))]
    slow = [r for r in references if r['is_slow'] == 'True']
    return dict(effect_gate_passed=bool(rdma) and len(slow) >= 2, public_window=public,
        target_rdma_submission_task_count=len(rdma), comparable_protocol_intervals=len(references),
        slow_protocol_interval_count=len(slow), public_history_is_previous_five=True,
        protocol_intervals_are_not_hardware_wire_durations=True, physical_causation_proven=False,
        no_resampling=True, original_candidate_hits=evaluation['candidate_hit_count'])


def require_quiescent_queue(parent):
    root = parent / 'hccl-diagnose-node03-20261106-1000'
    candidates = [root, *root.glob('remaining*')]
    for current in candidates:
        launch = current / 'launch.json'
        if not launch.exists():
            continue
        value = read(launch)
        proc = Path('/proc') / str(value['pid'])
        if proc.exists():
            fields = (proc / 'stat').read_text().rsplit(')', 1)[1].split()
            if fields[0] != 'Z' and fields[19] == str(value['start_ticks']):
                raise RuntimeError('prior queue is still alive; do not race it or stop it implicitly')


def run(root):
    if (root != LOCAL_PARENT / ROOT_NAME or os.geteuid() != 0
            or socket.gethostname().split('.')[0] != 'liteserver-560t-0'):
        raise ValueError('only the explicit Node0 one-call root is accepted')
    if any((root / name).exists() for name in ('state.json', 'launch.json', 'authorized-state.json')):
        raise ValueError('do not repeat a used experiment; preserve its input')
    validate_case(read(root / 'input/case.json'))
    deployment = read(root / 'deployment.json')
    if deployment.get('profile') != PROFILE:
        raise ValueError('explicit single-collective deployment is required')
    files = read(root / 'source-snapshot.json')['files']
    if not {'test/gpt2_train.py', 'test/roce_single_collective.py', 'test/node03_roce_window.py',
            'test/run_roce_single_collective.py', 'test/node03_device_guard.py'} <= set(files):
        raise ValueError('single-collective source manifest is incomplete')
    for name, expected in files.items():
        if Path(name).is_absolute() or '..' in Path(name).parts or sha(root / 'src' / name) != expected:
            raise ValueError('one-call source snapshot changed')
    require_quiescent_queue(root.parent)
    locks = []
    for name in ('.hccl-diagnose-single-probe.lock', 'hccl-diagnose-node03-20261106-1000/queue.lock'):
        lock = (root.parent / name).open('a')
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        locks.append(lock)
    require_quiescent_queue(root.parent)
    observations = {str(n): resources(n) for n in (0, 3)}
    write(root / 'admission.json', dict(checked_unix_ns=time.time_ns(), nodes=observations))
    if (not idle(observations['0'], range(8)) or not idle(observations['3'], range(4, 8))
            or any(o['free'] < 35 * 1024**3 for o in observations.values())):
        raise RuntimeError('whole Node0 and Node3 target cards must be idle with 35GiB free; no automatic retry')
    state = dict(status='running', requested=1, completed=0, active_case=case()['case_id'],
        started_unix_ns=time.time_ns(), training_overhead_not_comparable=True)
    write(root / 'launch.json', dict(pid=os.getpid(),
        start_ticks=int(Path('/proc/self/stat').read_text().rsplit(')', 1)[1].split()[19]),
        root=str(root), role='single_collective_probe', source_snapshot_sha256=sha(root/'source-snapshot.json')))
    write(root / 'state.json', state)
    def interrupted(signum, frame):
        raise InterruptedError('single-collective probe interrupted by signal ' + str(signum))
    for signum in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP):
        signal.signal(signum, interrupted)
    try:
        with (root / 'supervisor.log').open('x') as log:
            protected_run([sys.executable, str(root / 'src/test/run_node03_authorized.py'), '--root', str(root),
                '--gpt', '--formal-case', str(root / 'input/case.json')], log)
        # Run the evaluator in the already matched training environment, after restoration.
        from run_node03_preflight import PYTHON, container_command
        import shlex
        base = '/workspace/' + root.name
        evaluation = json.loads(execute(container_command(base, 0, shlex.join([
            PYTHON, base + '/src/test/node03_evaluate.py', '--root', base])), timeout=240))
        write(root / 'evaluation.json', evaluation)
        effect = inspect_effect(root, evaluation)
        write(root / 'effect-evidence.json', effect)
        state.update(status='completed' if effect['effect_gate_passed'] else 'ineffective_injection',
            completed=1, active_case=None, candidate_hits=evaluation['candidate_hit_count'],
            candidate_count=evaluation['candidate_count'], effect_gate_passed=effect['effect_gate_passed'])
    except BaseException as error:
        state.update(status='failed', error=str(error), no_automatic_retry=True)
        raise
    finally:
        restored = []
        for node, parent in ((0, LOCAL_PARENT), (3, Path(PEER_PARENT))):
            location = str(parent / root.name)
            code = ("import sys,json;from pathlib import Path;r=Path(" + repr(location) + ");"
                "sys.path.insert(0,str(r/'src/test'));from node03_device_guard import Guard;g=Guard(r);"
                "s=json.loads(g.snapshot.read_text());assert s['phase']=='restored';g.verify_original(s);"
                "assert not g.registry.exists();"
                "assert all(g.run(['systemctl','is-active',s['unit']+x+'.timer'],check=False).strip()"
                "in {'inactive','unknown'} for x in ('','-probe'));print('verified')")
            try:
                if execute(root_command(node, ['python3', '-c', code]), timeout=240).strip() != 'verified':
                    raise RuntimeError('restoration output mismatch')
                restored.append(node)
            except Exception as error:
                state.setdefault('restoration_errors', []).append(str(error))
        try:
            if (root / 'network/snapshot.json').exists():
                from node03_roce_window import Window
                window = Window(root)
                snapshot = read(window.snapshot)
                if {str(d): window.shaping(d) for d in (8, 9)} != snapshot['original']:
                    raise RuntimeError('native port values differ from the saved snapshot')
                for suffix in ('', '-probe', '-active'):
                    if window.run(['systemctl', 'is-active', snapshot['unit'] + suffix + '.timer'], check=False).strip() not in {'inactive', 'unknown'}:
                        raise RuntimeError('network recovery timer is still active')
                state['network_restoration_verified'] = True
            else:
                state['network_window_not_armed'] = True
        except Exception as error:
            state.setdefault('restoration_errors', []).append(str(error))
        state.update(restored_nodes=restored, finished_unix_ns=time.time_ns())
        if len(restored) != 2 or state.get('restoration_errors'):
            state['status'] = 'needs_restoration_assistance'
        write(root / 'state.json', state)
        if len(restored) != 2 or state.get('restoration_errors'):
            raise RuntimeError('device restoration needs assistance; do not retry')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    run(parser.parse_args().root.resolve())
