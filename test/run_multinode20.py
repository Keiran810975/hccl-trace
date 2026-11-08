"""One persistent twenty-run queue, with idle admission, bounded recovery and archive ACKs."""
from __future__ import annotations

import argparse
import csv
import ctypes
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import signal
import socket
import subprocess
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parent))
from multinode20_suite import ROOT_NAME, PROFILE, KINDS, plan, effect_evidence, CONTINUATION_ROOT, queue_plan
from run_node03_preflight import LOCAL_PARENT, PEER_PARENT, PYTHON, container_command, execute, ssh, write, own_container
from run_communication_calibration import protected_run
from node03_roce_window import card_processes
from run_tool_smoke import available


def sha(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for b in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(b)
    return h.hexdigest()


def read(path):
    return json.loads(path.read_text())


def node_execute(node, argv, timeout=60):
    return execute(ssh(shlex.join(argv)) if node == 3 else argv, timeout=timeout)


def resources(node):
    parent = PEER_PARENT if node == 3 else str(LOCAL_PARENT)
    code = ('import json,shutil,subprocess;from pathlib import Path;p=Path(' + repr(parent) + ');'
        "print(json.dumps(dict(npu=subprocess.check_output(['npu-smi','info'],text=True),"
        "free=shutil.disk_usage(p).free,registry=(p/'.hccl-diagnose-device-active.json').exists())))")
    return json.loads(node_execute(node, ['python3', '-c', code]))


def idle(observation, cards):
    healthy = {int(c) for c, state in re.findall(r'\|\s*(\d+)\s+Ascend910\s*\|\s*(\w+)\s*\|', observation['npu']) if state == 'OK'}
    return not observation['registry'] and set(cards) <= healthy and available(observation['npu'], list(cards))


def admission(root):
    observations = {str(n): resources(n) for n in (0, 3)}
    write(root / 'last-resources.json', dict(checked_unix_ns=time.time_ns(), nodes=observations))
    return idle(observations['0'], range(8)) and idle(observations['3'], range(4, 8))


def release_node3(root):
    """Only exact target-NPU PIDs, once; never containers, process-name matches or CPU services."""
    if socket.gethostname().split('.')[0] != 'liteserver-560t-3' or root != Path(PEER_PARENT) / ROOT_NAME:
        raise ValueError('Node3 stop action outside this exact authorized queue')
    auth = read(root / 'authorization.json')
    if not auth.get('node3_target_process_stop_user_confirmed') or auth.get('nodes') != [0, 3]:
        raise ValueError('explicit current Node3 task-stop authorization required')
    receipt = root / 'node3-stop.json'
    if receipt.exists() or (root.parent / '.hccl-diagnose-device-active.json').exists():
        raise ValueError('do not repeat a stop or interfere with an active experiment lease')
    text = execute(['npu-smi', 'info'])
    pids = sorted(set().union(*(card_processes(text, card) for card in range(4, 8))))
    owned = execute(['docker', 'inspect', '--format', '{{.Id}}', 'zjy-new']).strip()
    selected = {}
    for pid in pids:
        path = Path('/proc') / str(pid)
        group = (path / 'cgroup').read_text()
        identities = set(re.findall(r'/docker/([a-f0-9]{64})', group))
        if len(identities) != 1 or owned in identities:
            raise ValueError('unknown or own experimental process; stop requires assistance')
        identity = identities.pop()
        name = execute(['docker', 'inspect', '--format', '{{.Name}}', identity]).strip()
        stat = (path / 'stat').read_text().rsplit(')', 1)[1].split()
        selected[str(pid)] = dict(start_ticks=stat[19], cgroup=group, container_id=identity, container_name=name,
                                  comm=(path / 'comm').read_text().strip())
    state = dict(created_unix_ns=time.time_ns(), scope='Node3 NPU4..7 exact current PIDs',
                 selected=selected, signals=[], external_cpu_processes_not_selected=True)
    write(receipt, state)
    for sig, seconds in ((signal.SIGTERM, 30), (signal.SIGKILL, 15)):
        for pid, metadata in selected.items():
            path = Path('/proc') / pid
            try:
                stat = (path / 'stat').read_text().rsplit(')', 1)[1].split()
                if stat[0] == 'Z':
                    continue
                if stat[19] != metadata['start_ticks'] or (path / 'cgroup').read_text() != metadata['cgroup']:
                    raise RuntimeError('PID identity changed; refuse signal')
                state['signals'].append(dict(pid=int(pid), signal=int(sig), start_ticks=stat[19]))
                write(receipt, state)
                os.kill(int(pid), sig)
            except FileNotFoundError:
                pass
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            text = execute(['npu-smi', 'info'])
            remaining = set().union(*(card_processes(text, card) for card in range(4, 8)))
            if not remaining:
                break
            if not remaining <= {int(p) for p in selected}:
                raise RuntimeError('Node3 workload restarted; do not pursue or kill a new job')
            time.sleep(2)
        if not remaining:
            break
    state.update(target_processes_released=not remaining, finished_unix_ns=time.time_ns())
    write(receipt, state)
    if remaining:
        raise RuntimeError('Node3 did not release in the bounded stop window')


def verify_prepared(root, *, runtime=False):
    snapshot = read(root / 'source-snapshot.json')
    if read(root / 'plan.json') != queue_plan(root):
        raise ValueError('frozen twenty-case plan changed')
    for name, digest in snapshot['files'].items():
        if sha(root / 'src' / name) != digest:
            raise ValueError('source snapshot changed: ' + name)
    for n in (0, 1):
        own_container(n)
    if not runtime:
        return
    for node in (0, 3):
        parent = PEER_PARENT if node == 3 else str(LOCAL_PARENT)
        code = ('import json,socket,subprocess;from pathlib import Path;r=Path(' + repr(parent + '/' + root.name) + ');'
            "assert not (r.parent/'.hccl-diagnose-device-active.json').exists();"
            "p=subprocess.check_output(['ss','-H','-ltn'],text=True);"
            "ports={int(s.rsplit(':',1)[-1]) for l in p.splitlines() for s in [l.split()[3]] if s.rsplit(':',1)[-1].isdigit()};"
            "assert not ports.intersection({29773,29774,29775,29776});"
            "assert not any(55000<=p<=55327 or 57000<=p<=57327 for p in ports);print('ok')")
        node_execute(node, ['python3', '-c', code])
        if resources(node)['free'] < 35 * 1024**3:
            raise RuntimeError('35GiB minimum per-node free space is required before a new capture')


def inspect_case(current, case, *, effect_source=None):
    base = '/workspace/' + current.name
    evaluated = json.loads(execute(container_command(base, 0, shlex.join([
        PYTHON, base + '/src/test/node03_evaluate.py', '--root', base])), timeout=180))
    write(current / 'evaluation.json', evaluated)
    consumer = '/workspace/' + (effect_source or current).name
    program = ("import sys,json;from pathlib import Path;r=Path(" + repr(base) + ");"
               "sys.path.insert(0," + repr(consumer + '/src/test') + ");from run_multinode20 import evaluate_effect;"
               "print(json.dumps(evaluate_effect(r)))")
    effect = json.loads(execute(container_command(base, 0, shlex.join([PYTHON, '-c', program])), timeout=240))
    write(current/'effect-source-revision.json',dict(
        effect_source_snapshot_sha256=sha((effect_source or current)/'source-snapshot.json'),
        native_case_source_snapshot_sha256=sha(current/'source-snapshot.json'),
        native_reports_unchanged=True,postseal_evaluator_only=effect_source is not None))
    for node in (0, 3):
        location = (str(LOCAL_PARENT) if node == 0 else PEER_PARENT) + '/' + current.name
        code = ("import sys,json;from pathlib import Path;r=Path(" + repr(location) + ");sys.path.insert(0,str(r/'src/test'));"
                "from node03_device_guard import Guard;g=Guard(r);s=json.loads(g.snapshot.read_text());"
                "assert s['phase']=='restored';g.verify_original(s);"
                "assert not g.registry.exists();assert g.run(['systemctl','is-active',s['unit']+'.timer'],check=False).strip() in {'inactive','unknown'}")
        from run_node03_authorized import root_command
        execute(root_command(node, ['python3', '-c', code]), timeout=180)
    write(current / 'restoration-verified.json', dict(restored=True, nodes=[0, 3], unix_ns=time.time_ns()))
    write(current / 'effect-evidence.json', effect)
    return dict(evaluated, effect_gate_passed=effect['effect_gate_passed'], directory=str(current),
                full_raw_replay_requires_verified_archive=True)


def evaluate_effect(root):
    case, evaluation = read(root / 'input/case.json'), read(root / 'evaluation.json')
    report = read(root / 'report/root_causes.json')
    seal = read(root / 'diagnosis-seal.json')
    if seal.get('truth_accessed') is not False or any(sha(root / 'report' / n) != h for n, h in seal['sha256'].items()):
        raise ValueError('effect evaluation must follow sealed diagnosis')
    activities, delay = [], None
    for w in evaluation['windows']:
        data = root / ('gpt-output' if w['user_rank'] < 4 else 'peer-preflight/gpt-output')
        kind = case['injection']['kind']
        if kind == 'progress_delay':
            rank = w['user_rank']
            private = [json.loads(s) for s in (data / 'private' / ('rank-%d.jsonl' % rank)).read_text().splitlines()]
            a = [r for r in private if r['event'] == 'injection_start']
            b = [r for r in private if r['event'] == 'injection_stop' and r.get('actual_hit')]
            assert len(a) == len(b) == 1
            calls = [json.loads(s) for s in (data / 'public' / ('rank-%d.jsonl' % rank)).read_text().splitlines()]
            matching = [c for c in calls if c['stage'] == 'measured' and c['iteration'] == case['injection']['iteration']
                        and c['bucket'] == a[0]['call']]
            assert len(matching) == 1
            call = matching[0]
            assert call['preparation_before']['raw_ns'] <= a[0]['clocks']['raw_ns'] < b[0]['clocks']['raw_ns'] <= call['before']['raw_ns']
            delay = dict(actual_delay_ns=b[0]['clocks']['raw_ns'] - a[0]['clocks']['raw_ns'],
                         call_site='ddp.gradient.' + call['bucket_signature'])
        else:
            activities.append(read(data / 'private' / ('network-result.json' if kind == 'bandwidth_limit' else 'result.json')))
    with (root / 'report.debug/analysis' / report['run_id'] / 'rolling/task_comparison.csv').open(newline='') as stream:
        return effect_evidence(case, evaluation, csv.DictReader(stream), activities, delay)


def summarize(root, state):
    groups = {}
    for kind in KINDS:
        entries = [c for c in state['cases'] if c['injection']['kind'] == kind]
        units = {}
        for entry in entries:
            for unit in set(entry['source_units']):
                candidates = [c for c in entry['candidates'] if c.get('source_unit', 'execution') == unit]
                value = units.setdefault(unit, dict(hits=0, candidates=0))
                value['candidates'] += len(candidates)
                value['hits'] += sum(c['id'] in entry['hit_candidate_ids'] for c in candidates)
        requested = sum(c['injection']['kind'] == kind for c in queue_plan(root)['cases'])
        groups[kind] = dict(requested=requested, completed=len(entries), unrun=requested-len(entries), units=units,
            hits=sum(c['candidate_hit_count'] for c in entries), candidates=sum(c['candidate_count'] for c in entries),
            any_hit_cases=sum(c['any_candidate_hit'] for c in entries), primary_hit_cases=sum(c['primary_hit'] for c in entries),
            effective_cases=sum(c['effect_gate_passed'] for c in entries))
    write(root / 'summary.json', dict(status=state['status'], requested=state['requested'], completed=state['completed'], groups=groups,
        prior_result_included=False if root.name == CONTINUATION_ROOT else None))


def verify_continuation_origin(root):
    provenance = read(root / 'origin.json')
    old = root.parent / ROOT_NAME
    if provenance.get('origin_queue') != str(old) or provenance.get('training_repeated') is not False:
        raise ValueError('manual continuation must identify the unchanged stopped queue')
    for name, digest in provenance['files'].items():
        if Path(name).is_absolute() or '..' in Path(name).parts or sha(old / name) != digest:
            raise ValueError('prior evidence changed')
    previous = read(old / 'state.json')
    if (previous.get('status') != 'stopped' or previous.get('completed') != 1
            or previous.get('active_case') is not None or previous.get('active_directory') is not None
            or len(previous.get('cases', [])) != 1 or previous['cases'][0]['case_id'] != plan()['cases'][0]['case_id']):
        raise ValueError('only the exact stopped one-case queue can be continued')
    launch = read(old / 'launch.json')
    proc = Path('/proc') / str(launch['pid'])
    if proc.exists():
        stat = (proc / 'stat').read_text().rsplit(')', 1)[1].split()
        if stat[0] != 'Z' and int(stat[19]) == launch['start_ticks']:
            raise ValueError('old supervisor is still alive')
    with (old / 'queue.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    completed = old.parent / 'hccl-diagnose-node03-20261105-901'
    if read(completed / 'offload-receipt.json').get('status') != 'verified':
        raise ValueError('the prior completed case must have a real verified archive')
    for index in range(902, 921):
        current = old.parent / ('hccl-diagnose-node03-20261105-' + str(index))
        if any((current / name).exists() for name in ('authorized-state.json', 'preflight-state.json', 'capture', 'security', 'report')):
            raise ValueError('a remaining original attempt was already used; do not duplicate it')
    return previous


def validate_prestart_resume(root):
    previous = read(root / 'state.json')
    if (previous.get('status') != 'stopped' or previous.get('completed') != 0 or previous.get('cases')
            or previous.get('active_case') is not None or previous.get('active_directory') is not None
            or previous.get('error') != 'target resources changed after Node3 release; no repeated stop'
            or (root / 'prestart-resume.json').exists()):
        raise ValueError('only one zero-training admission continuation is permitted')
    if (root.parent / '.hccl-diagnose-device-active.json').exists():
        raise ValueError('cannot resume with an active Device lease')
    for index in range(901, 921):
        current = root.parent / ('hccl-diagnose-node03-20261105-' + str(index))
        if any((current / name).exists() for name in ('authorized-state.json', 'capture', 'security', 'report')):
            raise ValueError('a protected attempt has already started; no prestart continuation allowed')
    return previous


def validate_evaluated_resume(root):
    previous=read(root/'state.json')
    current=root.parent/'hccl-diagnose-node03-20261106-1002'
    if (root.name!=CONTINUATION_ROOT or previous.get('status')!='stopped' or previous.get('completed')!=0
            or previous.get('cases') or previous.get('active_directory')!=str(current)
            or (root/'evaluation-continuation.json').exists() or (root.parent/'.hccl-diagnose-device-active.json').exists()):
        raise ValueError('only one CPU evaluation continuation of the completed first low-log capture is permitted')
    if read(current/'authorized-state.json').get('status')!='passed' or read(current/'preflight-state.json').get('status')!='passed':
        raise ValueError('training and the original diagnosis must already be passed')
    seal=read(current/'diagnosis-seal.json')
    if seal.get('truth_accessed') is not False or any(sha(current/'report'/name)!=value for name,value in seal['sha256'].items()):
        raise ValueError('the original sealed reports must not change')
    return previous


def run(root, *, resume_prestart=False, recover_captured=False, recover_evaluated=False):
    continuation = root == LOCAL_PARENT / CONTINUATION_ROOT
    if root not in {LOCAL_PARENT / ROOT_NAME, LOCAL_PARENT / CONTINUATION_ROOT} or socket.gethostname().split('.')[0] != 'liteserver-560t-0':
        raise ValueError('only the exact fresh reviewed Node0 queue is allowed')
    if continuation and (resume_prestart or recover_captured):
        raise ValueError('the manual low-log continuation is fresh, never a recovery or restart')
    path = root / 'state.json'
    if recover_evaluated:
        previous=validate_evaluated_resume(root)
    elif recover_captured:
        from recover_multinode20_capture import validate_captured_resume
        previous = validate_captured_resume(root)
    else:
        previous = validate_prestart_resume(root) if resume_prestart else None
    if path.exists() and not (resume_prestart or recover_captured or recover_evaluated):
        raise ValueError('queue already used: inspect it, never restart')
    ctypes.CDLL(None).prctl(15, b'hccl-diagnose', 0, 0, 0)
    state = dict(status='waiting_node0', requested=queue_plan(root)['requested_runs'], completed=0, active_case=None,
                 active_directory=None, cases=[], started_unix_ns=time.time_ns(),
                 plan_sha256=sha(root / 'plan.json'), source_snapshot_sha256=sha(root / 'source-snapshot.json'))
    if resume_prestart:
        write(root / 'prestart-resume.json', dict(previous_state=previous, continued_unix_ns=time.time_ns(),
              reason='all training attempts untouched; process exit preceded delayed HBM reclamation',
              original_plan_unchanged=True, no_node3_stop_repeated=True))
        state['prestart_continuation_count'] = 1
        state['node3_stop_decision_completed'] = bool(previous.get('node3_stop_decision_completed'))
    if recover_captured:
        marker = 'cpu-transfer-repair.json' if (root / 'captured-input-continuation.json').exists() else 'captured-input-continuation.json'
        write(root / marker, dict(previous_state=previous, continued_unix_ns=time.time_ns(),
            training_not_resubmitted=True, node3_stop_not_repeated=True, original_capture_reused=True))
        state.update(prestart_continuation_count=1, captured_input_continuation_count=1,
                     node3_stop_decision_completed=True, original_started_unix_ns=previous['started_unix_ns'])
    if recover_evaluated:
        write(root/'evaluation-continuation.json',dict(previous_state=previous,continued_unix_ns=time.time_ns(),
            training_not_resubmitted=True,diagnosis_not_repeated=True,original_reports_unchanged=True,
            reason='effect evaluator parsed an unused empty control-task ratio'))
        state['original_started_unix_ns']=previous['started_unix_ns']
    write(path, state)
    def interrupted(signum, frame):
        raise InterruptedError('queue interrupted by signal ' + str(signum))
    for sig in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP):
        signal.signal(sig, interrupted)
    try:
        verify_prepared(root)
        if continuation:
            verify_continuation_origin(root)
            state.update(origin_queue=ROOT_NAME, prior_completed=1, prior_result_included=False,
                         capture_policy=queue_plan(root)['capture_policy'], node3_stop_decision_completed=True)
        elapsed = (time.time_ns() - previous['started_unix_ns']) / 1e9 if previous else 0
        wait_deadline = time.monotonic() + max(0, 48 * 3600 - elapsed)
        stop_decided = continuation or bool(previous and previous.get('node3_stop_decision_completed'))
        for index, case in enumerate(queue_plan(root)['cases'], 1002 if continuation else 901):
            if recover_evaluated and index==1002:
                current=root.parent/'hccl-diagnose-node03-20261106-1002'
                state.update(status='recovering_evaluation',active_case=case['case_id'],active_directory=str(current))
                write(path,state)
                result=inspect_case(current,case,effect_source=root)
                state['cases'].append(dict(result,recovered_original_evaluation=True))
                state.update(completed=1,status='awaiting_verified_archive')
                write(path,state);summarize(root,state)
                deadline=time.monotonic()+5400
                while not (current/'offload-receipt.json').exists():
                    if time.monotonic()>deadline:raise TimeoutError('90-minute verified-archive deadline after evaluation recovery')
                    time.sleep(5)
                receipt=read(current/'offload-receipt.json')
                if (receipt.get('status')!='verified' or receipt.get('case_directory')!=str(current)
                        or len(receipt.get('local_archive_sha256',[]))!=2 or not receipt.get('file_hashes_verified')
                        or not receipt.get('owned_raw_removed')):
                    raise ValueError('recovered evaluation archive ACK is incomplete')
                state.update(active_case=None,active_directory=None)
                if not result['effect_gate_passed']:
                    state.update(status='ineffective_injection',reason='original effect gate failed; no replacement')
                    break
                continue
            if recover_captured and index == 901:
                current = root.parent / 'hccl-diagnose-node03-20261105-901'
                state.update(status='recovering_cpu', active_case=case['case_id'], active_directory=str(current))
                write(path, state)
                from recover_multinode20_capture import recover
                recover(current)
                result = inspect_case(current, case)
                state['cases'].append(dict(result, recovered_original_capture=True))
                state.update(completed=1, status='awaiting_verified_archive')
                write(path, state)
                summarize(root, state)
                deadline = time.monotonic() + 5400
                while not (current / 'offload-receipt.json').exists():
                    if time.monotonic() > deadline:
                        raise TimeoutError('90-minute verified-archive deadline after CPU recovery')
                    time.sleep(5)
                receipt = read(current / 'offload-receipt.json')
                if (receipt.get('status') != 'verified' or receipt.get('case_directory') != str(current)
                        or len(receipt.get('local_archive_sha256', [])) != 2
                        or not receipt.get('file_hashes_verified') or not receipt.get('owned_raw_removed')):
                    raise ValueError('recovered capture archive ACK is incomplete')
                state.update(active_case=None, active_directory=None)
                if not result['effect_gate_passed']:
                    state.update(status='ineffective_injection', reason='original recovered capture has insufficient effect; no replacement')
                    break
                continue
            while True:
                before = resources(0)
                state.update(status='waiting_node0', active_case=None, active_directory=None, next_case=case['case_id'],
                             checked_unix_ns=time.time_ns())
                write(root / 'last-node0-resources.json', before)
                write(path, state)
                if not idle(before, range(8)):
                    if time.monotonic() >= wait_deadline:
                        raise TimeoutError('48-hour resource wait expired; no automatic resubmission')
                    time.sleep(1800)
                    continue
                verify_prepared(root, runtime=True)
                if not stop_decided:
                    if not idle(resources(3), range(4, 8)):
                        if not idle(resources(0), range(8)):
                            continue
                        peer_root = str(Path(PEER_PARENT) / ROOT_NAME)
                        node_execute(3, ['python3', peer_root + '/src/test/run_multinode20.py', '--root', peer_root, '--release-node3'], timeout=180)
                    stop_decided = True
                    state['node3_stop_decision_completed'] = True
                # Driver HBM accounting can lag process exit; never treat missing PIDs alone as idle.
                settle_deadline = time.monotonic() + 120
                while not admission(root):
                    observed = read(root / 'last-resources.json')['nodes']
                    if any(card_processes(observed['3']['npu'], c) for c in range(4, 8)):
                        raise RuntimeError('new target process appeared; do not repeat Node3 stop')
                    if not idle(observed['0'], range(8)):
                        break
                    if time.monotonic() > settle_deadline:
                        raise RuntimeError('HBM did not settle after process exit; do not bypass the idle gate')
                    time.sleep(10)
                if not idle(read(root / 'last-resources.json')['nodes']['0'], range(8)):
                    continue
                time.sleep(30)
                if not admission(root):
                    observed = read(root / 'last-resources.json')['nodes']
                    if not idle(observed['0'], range(8)) and idle(observed['3'], range(4, 8)):
                        continue
                    raise RuntimeError('resources changed during the second admission check')
                break
            verify_prepared(root, runtime=True)
            current = root.parent / (('hccl-diagnose-node03-20261106-' if continuation else 'hccl-diagnose-node03-20261105-') + str(index))
            if read(current / 'input/case.json') != case or (current / 'authorized-state.json').exists():
                raise ValueError('attempt conflict; never restart a used case')
            state.update(status='running', active_case=case['case_id'], active_directory=str(current))
            write(path, state)
            with (root / (case['case_id'] + '.log')).open('x') as log:
                protected_run([sys.executable, str(current / 'src/test/run_node03_authorized.py'), '--root', str(current),
                    '--gpt', '--formal-case', str(current / 'input/case.json')], log, timeout=6500)
            result = inspect_case(current, case)
            state['cases'].append(result)
            state.update(completed=len(state['cases']), status='awaiting_verified_archive')
            write(path, state)
            summarize(root, state)
            deadline = time.monotonic() + 5400
            while not (current / 'offload-receipt.json').exists():
                if time.monotonic() > deadline:
                    raise TimeoutError('90-minute verified-archive deadline; no next training started')
                time.sleep(5)
            receipt = read(current / 'offload-receipt.json')
            if (receipt.get('status') != 'verified' or receipt.get('case_directory') != str(current)
                    or len(receipt.get('local_archive_sha256', [])) != 2
                    or not receipt.get('file_hashes_verified') or not receipt.get('owned_raw_removed')):
                raise ValueError('incomplete two-node verified archive ACK')
            state.update(active_case=None, active_directory=None)
            if not result['effect_gate_passed']:
                state.update(status='ineffective_injection', reason='effect gate failed; retained and archived, no replacement run')
                break
        else:
            state.update(status='completed')
    except BaseException as error:
        state.update(status='stopped', error=str(error), no_automatic_resubmission=True)
        raise
    finally:
        state['finished_unix_ns'] = time.time_ns()
        write(path, state)
        summarize(root, state)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--release-node3', action='store_true')
    parser.add_argument('--resume-prestart', action='store_true', help='one audited continuation only before any protected training attempt')
    parser.add_argument('--recover-captured', action='store_true', help='finish the existing first capture on CPU, never repeat its training')
    parser.add_argument('--recover-evaluated', action='store_true', help='one CPU-only effect evaluation continuation after the first low-log diagnosis passed')
    args = parser.parse_args()
    if sum((args.release_node3, args.resume_prestart, args.recover_captured, args.recover_evaluated)) > 1:
        raise ValueError('continuation modes cannot be combined')
    if args.release_node3:
        release_node3(args.root.resolve())
    else:
        with (args.root / 'queue.lock').open('a' if args.resume_prestart or args.recover_captured or args.recover_evaluated else 'x') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            run(args.root.resolve(), resume_prestart=args.resume_prestart, recover_captured=args.recover_captured, recover_evaluated=args.recover_evaluated)
