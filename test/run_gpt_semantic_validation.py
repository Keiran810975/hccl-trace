"""One retained four-rank GPT intervention and predeclared paired overhead runs."""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from copy import deepcopy
import fcntl
import hashlib
import json
from pathlib import Path
import shlex
import shutil
import signal
import socket
import statistics
import subprocess
import time

from node03_device_guard import Guard, write
from gpt2_diagnosis_suite import WORKLOAD


ROOT = Path('/home/commTeam/zjy/zjy-new-workspace/gpt2-semantic-20261102-001')
OLD = ROOT.parent / 'semantic-coverage-20261102'
ASSETS = '/workspace/gpt2-single-node0-50-20261029-001'
PYTHON = '/project/venvs/hccl-py311/bin/python'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def prepare(root):
    receipt = json.loads((OLD / 'build-receipt.json').read_text())
    expected = json.loads((root / 'producer-files.json').read_text())
    if receipt['status'] != 'built' or any(sha(OLD / 'src' / p) != digest for p, digest in expected.items()):
        raise ValueError('current producer does not match the previously built source')
    for name in ('deploy', 'input'):
        shutil.copytree(OLD / name, root / name)
    for name, digest in receipt['host_libraries'].items():
        if sha(root / 'deploy/lib64' / name) != digest:
            raise ValueError('reused Host build changed')
    if sha(root / 'input/aicpu_hcomm.tar.gz') != receipt['device_sha256']:
        raise ValueError('reused Device build changed')
    write(root / 'build-receipt.json', dict(receipt, reused_build=str(OLD), verified_current_producer_files=expected))
    for folder in ('logs', 'captures', 'numerics', 'reports'):
        (root / folder).mkdir()
    normal = dict(schema_version=1, topology=dict(nnodes=1, ranks_per_node=4),
                  workload=dict(WORKLOAD, iters=50), workload_seed=20261028,
                  case_id='gpt2-4r-normal', injection=dict(kind='normal'))
    strong = deepcopy(normal)
    strong.update(case_id='gpt2-4r-strong-copy', injection=dict(kind='copy_contention',
        finite_copy_burst=True, buffer_mib=2048, operations=4, duration_iters=1,
        target_rank=0, iteration=25, bucket_selector_seed=20261102))
    write(root / 'input/normal.json', normal)
    write(root / 'input/strong-copy.json', strong)
    write(root / 'plan.json', dict(normal=normal, intervention=strong, overhead_repeats=3,
        modes=['off', 'semantic', 'profile'], keep_all_raw_inputs=True,
        analyzer_reads_injection_truth=False, candidate_policy='all', slowdown_factor='1.5', mad_multiplier='3',
        device_cards=[4, 5, 6, 7], runtime_devices=[1, 3, 5, 7], created_unix_ns=time.time_ns()))


def run(root, *, resume_space=False):
    state_path = root / 'state.json'
    previous_completed = []
    if state_path.exists():
        previous = json.loads(state_path.read_text())
        expected = ['normal', 'strong-copy', 'overhead-0-off', 'overhead-0-semantic',
                    'overhead-0-profile', 'overhead-1-semantic', 'overhead-1-profile', 'overhead-1-off']
        if (not resume_space or previous.get('status') != 'failed'
                or previous.get('error') != 'at least 16GiB required before a fresh capture'
                or previous.get('restoration_verified') is not True
                or [c['name'] for c in previous['completed']] != expected):
            raise ValueError('never automatically restart a used GPT validation directory')
        old_guard = Guard(root)
        snapshot = json.loads(old_guard.snapshot.read_text())
        if snapshot['phase'] != 'restored' or old_guard.registry.exists():
            raise ValueError('storage continuation requires complete prior restoration')
        old_guard.verify_original(snapshot)
        history = root / 'storage-stop-history'
        history.mkdir()
        write(history / 'state.json', previous)
        (root / 'security').rename(history / 'security')
        previous_completed = previous['completed']
    guard = Guard(root)
    base = '/workspace/' + root.name
    deadline = time.monotonic() + 3600
    state = dict(status='prechecking', completed=previous_completed, active=None, started_unix_ns=time.time_ns(),
                 raw_retention=True, requested_captures=11)
    if resume_space:
        state['continuation_of_storage_stop'] = str(root / 'storage-stop-history/state.json')
    write(state_path, state)
    shell = ('source /usr/local/Ascend/ascend-toolkit/set_env.sh\n'
        'export ASCEND_OPP_PATH=' + ASSETS + '/a3-runtime/opp\n'
        'export LD_LIBRARY_PATH=' + base + '/deploy/lib64:' + ASSETS + '/a3-runtime/aarch64-linux/lib64:'
        + ASSETS + '/a3-runtime/opp/built-in/op_impl/ai_core/tbe/op_tiling/lib/linux/aarch64:${LD_LIBRARY_PATH:-}\n'
        'export PYTHONPATH=' + base + '/src:' + ASSETS + '/deps\n'
        'export HCCL_OP_EXPANSION_MODE=AI_CPU HCCL_ALGO="level0:ring;level1:ring;level2:ring"\n'
        'export HCCL_EXEC_TIMEOUT=120 HCCL_CONNECT_TIMEOUT=120 OMP_NUM_THREADS=1\n'
        'export ASCEND_GLOBAL_LOG_LEVEL=1 ASCEND_SLOG_PRINT_TO_STDOUT=0\n'
        'unset ASCEND_RT_VISIBLE_DEVICES\n')

    def execute(name, command, seconds):
        with (root / 'logs' / (name + '.log')).open('x') as log:
            proc = subprocess.Popen(['docker', 'exec', 'zjy-new', 'timeout', '--signal=TERM', '--kill-after=30s',
                    str(seconds), 'bash', '-lc', shell + command], stdout=log, stderr=subprocess.STDOUT)
            try:
                while proc.poll() is None:
                    if time.monotonic() >= deadline or shutil.disk_usage(root).free < 8 * 1024**3:
                        raise RuntimeError('bounded runtime or emergency free-space limit reached')
                    time.sleep(2)
                if proc.returncode:
                    raise RuntimeError(name + ' failed; see its retained log')
            except BaseException:
                # Stop only this attempt's foreground PIDs after checking start ticks.
                cleanup = ('import json,os,signal;from pathlib import Path\n'
                    'for p in Path(' + repr(base + '/numerics/' + name + '/runtime') + ').glob("rank-*.json"):\n'
                    ' d=json.loads(p.read_text()); q=Path("/proc")/str(d["pid"])\n'
                    ' if q.exists() and q.joinpath("stat").read_text().split(") ",1)[1].split()[19]==d["process_start_ticks"] and '
                    + repr(base + '/src/test/gpt2_train.py') + ' in q.joinpath("cmdline").read_text(): os.kill(d["pid"],signal.SIGTERM)\n')
                guard.docker(PYTHON, '-c', cleanup)
                try:
                    proc.wait(timeout=180)
                except subprocess.TimeoutExpired:
                    raise RuntimeError('owned foreground did not exit; retain rollback timer for recovery')
                raise

    def capture(name, case_name, trace, profile):
        if any(c['name'] == name for c in state['completed']):
            return
        guard.idle()
        if shutil.disk_usage(root).free < 16 * 1024**3:
            raise ValueError('at least 16GiB required before a fresh capture')
        state.update(status='capturing', active=name)
        write(state_path, state)
        out = root / 'numerics' / name
        for folder in ('public', 'private', 'workload_results'):
            (out / folder).mkdir(parents=True)
        destination = base + '/captures/' + name + '/nodes/node0'
        app = [PYTHON, '-m', 'torch.distributed.run', '--nnodes=1', '--nproc-per-node=4',
            '--max-restarts=0', '--master-addr=127.0.0.1', '--master-port=29874',
            base + '/src/test/gpt2_train.py', '--case', base + '/input/' + case_name + '.json',
            '--output', base + '/numerics/' + name, '--data', ASSETS + '/data', '--devices', '1,3,5,7',
            '--sdk-observations', destination + '/calls']
        flags = ('export HCCL_STEP_TRACE=' + str(int(trace)) + ' HCCL_TASK_SEMANTIC_TRACE=' + str(int(trace)) + '\n'
            'export HCCL_TRACE_RUN_ID=' + name + ' HCCL_TRACE_NODE_ID=node0\n'
            'export ASCEND_PROCESS_LOG_PATH=' + destination + '/plog\n')
        case = json.loads((root / 'input' / (case_name + '.json')).read_text())
        case['case_id'] = name
        write(root / 'input' / (name + '-runtime.json'), case)
        app[app.index('--case') + 1] = base + '/input/' + name + '-runtime.json'
        launch = (['msprof', '--application=' + shlex.join(app), '--output=' + destination + '/msprof',
                   '--hccl=on', '--task-time=on', '--type=db'] if profile else app)
        started = time.monotonic_ns()
        execute(name, flags + shlex.join(launch), 900)
        samples = [json.loads((out / 'workload_results' / ('rank-' + str(r) + '.json')).read_text()) for r in range(4)]
        if (any(r['status'] != 'passed' or r['warmup'] != 10 or r['iters'] != 50 or len(r['iteration_ns']) != 50
                    or not r['parameter_update_observed'] for r in samples)
                or any(r['parameter_samples'] != samples[0]['parameter_samples']
                       or r['initialization'] != samples[0]['initialization'] for r in samples)):
            raise ValueError('training/replica consistency gate failed')
        if any(r['loaded_communication_libraries'].get(base + '/deploy/lib64/libhcomm.so') != guard.host_hash for r in samples):
            raise ValueError('training did not load the matched HCOMM build')
        state['completed'].append(dict(name=name, trace=trace, profile=profile,
            wall_ns=time.monotonic_ns()-started, rank_mean_ns=[statistics.mean(r['iteration_ns']) for r in samples],
            maximum_rank_mean_ns=statistics.mean(max(r['iteration_ns'][i] for r in samples) for i in range(50))))
        write(state_path, state)

    try:
        with socket.socket() as port:
            port.bind(('127.0.0.1', 29874))
        guard.prepare(4500)
        guard.activate()
        capture('normal', 'normal', True, True)
        capture('strong-copy', 'strong-copy', True, True)
        for repeat in range(3):
            modes = [('off', False, False), ('semantic', True, False), ('profile', True, True)]
            for mode, trace, profile in modes[repeat:] + modes[:repeat]:
                capture('overhead-' + str(repeat) + '-' + mode, 'normal', trace, profile)
        state.update(status='restoring', active=None)
    except BaseException as error:
        state.update(status='failed', error=str(error))
        raise
    finally:
        if guard.snapshot.exists():
            guard.restore()
            state['restoration_verified'] = True
        write(state_path, state)
    state.update(status='analyzing', active=None)
    write(state_path, state)
    for name in ('normal', 'strong-copy'):
        state['active'] = name
        write(state_path, state)
        execute(name + '-analyze', shlex.join([PYTHON, '-m', 'hccl.tools.diagnosis.cli', 'analyze',
            '--capture', base + '/captures/' + name, '--mode', 'rolling', '--output', base + '/reports/' + name,
            '--keep-debug', '--allow-uncalibrated-clock']), 1800)
        public = json.loads((root / 'reports' / name / 'root_causes.json').read_text())
        if not public['quality']['pipeline_passed']:
            raise ValueError('strict diagnosis gate failed')
    state.update(status='completed', active=None, finished_unix_ns=time.time_ns())
    write(state_path, state)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--prepare', action='store_true')
    parser.add_argument('--resume-space', action='store_true')
    args = parser.parse_args()
    if args.root.resolve() != ROOT or socket.gethostname().split('.')[0] != 'liteserver-560t-0':
        raise ValueError('only the reviewed Node0 owned directory is allowed')
    if args.prepare:
        prepare(ROOT)
    else:
        def interrupted(signum, frame):
            raise InterruptedError('GPT validation interrupted')
        signal.signal(signal.SIGTERM, interrupted)
        signal.signal(signal.SIGINT, interrupted)
        with (ROOT / ('validation-recovery.lock' if args.resume_space else 'validation.lock')).open('x') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            run(ROOT, resume_space=args.resume_space)
