"""Bounded, retained Node0 NPU5-7 producer validation and overhead experiment."""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import fcntl
import json
from pathlib import Path
import re
import shlex
import socket
import statistics
import subprocess
import time

from node03_device_guard import Guard, write


ROOT = Path('/home/commTeam/zjy/zjy-new-workspace/semantic-coverage-20261102')
PYTHON = '/project/venvs/hccl-py311/bin/python'


def run(root, *, resume_precheck=False, resume_preflight=False, resume_after_preflight=False):
    if root != ROOT or socket.gethostname().split('.')[0] != 'liteserver-560t-0':
        raise ValueError('only the owned Node0 validation directory is allowed')
    state_path = root / 'validation-state.json'
    completed = []
    if state_path.exists():
        previous = json.loads(state_path.read_text())
        rejected = (resume_precheck and previous.get('error') == 'both chips of every authorized card must be idle'
                    and not (root / 'security/snapshot.json').exists())
        restored_preflight = resume_preflight and previous.get('active') == 'preflight' and previous.get('restoration_verified') is True
        accepted_preflight = (resume_after_preflight and previous.get('active') == 'preflight'
            and previous.get('restoration_verified') is True
            and [r['name'] for r in previous.get('completed', [])] == ['preflight'])
        if (previous.get('status') != 'failed' or not (rejected or restored_preflight or accepted_preflight)
                or previous.get('completed') and not accepted_preflight):
            raise ValueError('only a resource-rejected, never-activated precheck can be resumed')
        if restored_preflight or accepted_preflight:
            old_guard = Guard(root)
            snapshot = json.loads(old_guard.snapshot.read_text())
            if snapshot['phase'] != 'restored' or old_guard.registry.exists():
                raise ValueError('failed preflight must be fully restored')
            old_guard.verify_original(snapshot)
        if accepted_preflight:
            result = json.loads((root / 'reports/preflight/root_causes.json').read_text())
            if not result['quality']['pipeline_passed']:
                raise ValueError('the retained preflight report must have passed')
            completed = previous['completed']
        archive = root / ('rejected-precheck-' + str(time.time_ns()))
        archive.mkdir()
        write(archive / 'validation-state.json', previous)
        if (root / 'security').exists():
            (root / 'security').rename(archive / 'security')
        if restored_preflight:
            for name in ('captures', 'numerics', 'reports'):
                if (root / name).exists():
                    (root / name).rename(archive / name)
            for path in (root / 'logs').glob('preflight*.log'):
                path.rename(archive / path.name)
    state = dict(status='prechecking', completed=completed, retained_all_inputs=True,
                 cards=[5, 6, 7], runtime_devices=[3, 5, 7], started_unix_ns=time.time_ns())
    write(state_path, state)
    base = '/workspace/' + root.name
    guard = Guard(root)
    runtime = '/workspace/gpt2-single-node0-50-20261029-001/a3-runtime'
    shell = ('source /usr/local/Ascend/ascend-toolkit/set_env.sh\n'
             'export ASCEND_OPP_PATH=' + runtime + '/opp\n'
             'export LD_LIBRARY_PATH=' + base + '/deploy/lib64:' + runtime + '/aarch64-linux/lib64:'
             + runtime + '/opp/built-in/op_impl/ai_core/tbe/op_tiling/lib/linux/aarch64:${LD_LIBRARY_PATH:-}\n'
             'export PYTHONPATH=' + base + '/src\n'
             'export HCCL_OP_EXPANSION_MODE=AI_CPU HCCL_ALGO="level0:ring;level1:ring;level2:ring"\n'
             'export HCCL_EXEC_TIMEOUT=120 HCCL_CONNECT_TIMEOUT=120 OMP_NUM_THREADS=1\n'
             'export ASCEND_GLOBAL_LOG_LEVEL=1 ASCEND_SLOG_PRINT_TO_STDOUT=0\n'
             'unset ASCEND_RT_VISIBLE_DEVICES\n')

    def execute(name, command, seconds=300):
        with (root / 'logs' / (name + '.log')).open('x') as log:
            start = time.monotonic_ns()
            subprocess.run(['docker', 'exec', 'zjy-new', 'timeout', '--signal=TERM', '--kill-after=20s',
                            str(seconds), 'bash', '-lc', shell + command], check=True,
                           stdout=log, stderr=subprocess.STDOUT, timeout=seconds + 35)
            return time.monotonic_ns() - start

    def capture(name, *, warmup=10, iterations=30, trace=True, profile=False, copy=0):
        guard.idle()
        state.update(status='capturing', active=name)
        write(state_path, state)
        directory = base + '/captures/' + name
        output = base + '/numerics/' + name
        app = [PYTHON, '-m', 'torch.distributed.run', '--nnodes=1', '--nproc-per-node=3',
               '--max-restarts=0', '--master-addr=127.0.0.1', '--master-port=29872',
               base + '/src/test/semantic_allreduce_probe.py', '--output', output,
               '--warmup', str(warmup), '--iterations', str(iterations), '--size-mib', '128',
               '--copy-mib', str(copy)]
        flags = ('export HCCL_STEP_TRACE=' + str(int(trace)) + ' HCCL_TASK_SEMANTIC_TRACE=' + str(int(trace)) + '\n'
                 'export HCCL_TRACE_RUN_ID=' + name + ' HCCL_TRACE_NODE_ID=node0\n'
                 'export HCCL_TRACE_CALLS_DIR=' + directory + '/nodes/node0/calls\n'
                 'export ASCEND_PROCESS_LOG_PATH=' + directory + '/nodes/node0/plog\n')
        launch = (['msprof', '--application=' + shlex.join(app), '--output=' + directory + '/nodes/node0/msprof',
                   '--hccl=on', '--task-time=on', '--type=db'] if profile else app)
        wall = execute(name, flags + shlex.join(launch))
        samples = [json.loads((root / 'numerics' / name / ('rank-' + str(r) + '.json')).read_text()) for r in range(3)]
        if any(r['status'] != 'passed' or len(r['samples']) != warmup + iterations for r in samples):
            raise ValueError('numerical/completion gate failed')
        for sample in samples:
            if set(sample['loaded_hcomm_libraries']) != {base + '/deploy/lib64/' + name for name in
                    ('libhcomm.so', 'libhccl_alg.so', 'libhccl_plf.so')}:
                raise ValueError('rank did not load exactly the newly built Host library trio')
        result = dict(name=name, trace=trace, profile=profile, copy_mib=copy, wall_ns=wall,
                      rank_mean_ns=[statistics.mean(s['elapsed_ns'] for s in r['samples'] if s['stage']=='measured') for r in samples])
        state['completed'].append(result)
        write(state_path, state)

    def diagnose(name):
        state.update(status='diagnosing', active=name)
        write(state_path, state)
        if not (root / 'reports' / name).exists():
            execute(name + '-analyze', shlex.join([PYTHON, '-m', 'hccl.tools.diagnosis.cli', 'analyze',
                    '--capture', base + '/captures/' + name, '--mode', 'rolling', '--output', base + '/reports/' + name,
                    '--keep-debug', '--allow-uncalibrated-clock']), seconds=600)
        public = json.loads((root / 'reports' / name / 'root_causes.json').read_text())
        if not public['quality']['pipeline_passed']:
            raise ValueError('diagnosis gate did not pass')
        paths = list((root / 'reports' / (name + '.debug')).glob('**/rolling/report.json'))
        if len(paths) != 1:
            raise ValueError('exactly one retained rolling analysis required')
        report = json.loads(paths[0].read_text())
        groups = defaultdict(Counter)
        for task in report['tasks']:
            if task.get('stage') == 'measured' and task.get('iteration', -1) >= 5:
                groups[task['task_kind']][task['comparison_status']] += 1
        write(root / (name + '-coverage.json'), {kind: dict(counts) for kind, counts in groups.items()})

    try:
        with socket.socket() as port:
            port.bind(('127.0.0.1', 29872))
        mapping = guard.docker('npu-smi', 'info', '-m')
        (root / 'logs/runtime-mapping.txt').write_text(mapping)
        for logical, physical in ((3, 11), (5, 13), (7, 15)):
            if not any(re.match(r'\s*\d+\s+\d+\s+' + str(logical) + r'\s+' + str(physical) + r'\s+Ascend910', line)
                       for line in mapping.splitlines()):
                raise ValueError('runtime/physical device mapping changed')
        guard.prepare(1800)
        guard.activate()
        if not completed:
            capture('preflight', warmup=1, iterations=7, profile=True)
        diagnose('preflight')
        capture('normal', profile=True)
        diagnose('normal')
        capture('strong-copy', profile=True, copy=2048)
        # These repetitions are fixed beforehand, not chosen by their results.
        for repeat in range(5):
            modes = [('off', False, False), ('semantic', True, False), ('profile', True, True)]
            for name, trace, profile in modes[repeat % 3:] + modes[:repeat % 3]:
                capture('overhead-' + str(repeat) + '-' + name, trace=trace, profile=profile)
        state.update(status='restoring', active=None)
        write(state_path, state)
    except BaseException as error:
        state.update(status='failed', error=str(error))
        raise
    finally:
        if guard.snapshot.exists():
            guard.restore()
            state['restoration_verified'] = True
        write(state_path, state)
    diagnose('strong-copy')
    state.update(status='completed', active=None, finished_unix_ns=time.time_ns())
    write(state_path, state)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--resume-precheck', action='store_true')
    parser.add_argument('--resume-preflight', action='store_true')
    parser.add_argument('--resume-after-preflight', action='store_true')
    args = parser.parse_args()
    with (args.root / 'validation.lock').open('a' if args.resume_precheck or args.resume_preflight or args.resume_after_preflight else 'x') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        run(args.root.resolve(), resume_precheck=args.resume_precheck, resume_preflight=args.resume_preflight,
            resume_after_preflight=args.resume_after_preflight)
