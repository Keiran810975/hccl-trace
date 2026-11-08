"""Explicitly authorized eight-case continuation, retaining the stopped nineteen-case ledger."""
from __future__ import annotations

import argparse
import fcntl
import json
from pathlib import Path
import signal
import socket
import sys
import time

if __package__:
    from .run_multinode20 import (admission, idle, inspect_case, node_execute, protected_run,
                                 read, resources, sha, verify_prepared, write)
    from .multinode20_suite import continuation_plan
else:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src/test"))
    from run_multinode20 import (admission, idle, inspect_case, node_execute, protected_run,
                                read, resources, sha, verify_prepared, write)
    from multinode20_suite import continuation_plan


ORIGIN = Path('/home/commTeam/zjy/zjy-new-workspace/hccl-diagnose-node03-20261106-1000')
CONTROL_NAME = 'remaining8-20261107'
INDICES = tuple(range(1013, 1021))


def validate_previous(previous, plan):
    if (previous.get('status') != 'stopped' or previous.get('completed') != 10
            or len(previous.get('cases', [])) != 10
            or previous.get('active_directory') != str(ORIGIN.parent / 'hccl-diagnose-node03-20261106-1012')
            or [c['case_id'] for c in previous['cases']] != [c['case_id'] for c in plan['cases'][:10]]
            or previous.get('active_case') != plan['cases'][10]['case_id']):
        raise ValueError('only the exact ten-complete/one-failed checkpoint may continue')
    return list(zip(INDICES, plan['cases'][11:]))


def receipt_verified(receipt, current):
    return (receipt.get('status') == 'verified' and receipt.get('case_directory') == str(current)
            and len(receipt.get('local_archive_sha256', [])) == 2
            and receipt.get('file_hashes_verified') is True and receipt.get('owned_raw_removed') is True)


def validate_archived_checkpoint(state, receipt, plan):
    count = state.get('completed')
    if type(count) is not int or not 1 <= count < len(INDICES):
        raise ValueError('archive checkpoint must leave at least one never-run case')
    current = ORIGIN.parent / ('hccl-diagnose-node03-20261106-' + str(1012 + count))
    cases = state.get('cases', [])
    expected = [c['case_id'] for c in plan['cases'][11:11 + count]]
    if (state.get('status') != 'stopped' or state.get('requested') != 8
            or state.get('error') != '90-minute verified archive deadline; no next capture'
            or [c.get('case_id') for c in cases] != expected
            or any(c.get('effect_gate_passed') is not True for c in cases)
            or state.get('aggregate_completed') != 10 + count
            or state.get('active_directory') != str(current) or not receipt_verified(receipt, current)):
        raise ValueError('only a complete prefix, restored and now archived checkpoint may continue')
    return cases


def consume_archived_checkpoint(root, state, receipt, plan):
    completed = validate_archived_checkpoint(state, receipt, plan)
    digest = sha(root / 'state.json')
    authorization = read(root / 'checkpoint-authorizations' / (digest + '.json'))
    pending = list(INDICES[len(completed):])
    if (authorization.get('user_confirmed') is not True
            or authorization.get('checkpoint_sha256') != digest
            or authorization.get('only_unused_cases') != pending
            or authorization.get('no_training_repeated') is not True):
        raise ValueError('this exact archived checkpoint needs a new user continuation grant')
    backup = root / 'archive-checkpoints' / digest
    if read(backup / 'state.json') != state:
        raise ValueError('preserved archive checkpoint differs from current state')
    with (backup / 'used.json').open('x') as marker:
        json.dump(dict(checkpoint_sha256=digest, only_unused=pending,
                       no_training_repeated=True), marker, indent=2)
    return completed, digest


def verify_unused(root, index, case):
    proof = read(root / 'resume-manifest.json')
    for node, parent in ((0, str(ORIGIN.parent)), (3, '/home/zjy-new/workspace')):
        location = parent + '/hccl-diagnose-node03-20261106-' + str(index)
        code = r'''
import hashlib,json,pathlib
r=pathlib.Path(ROOT)
assert not any((r/n).exists() for n in ('authorized-state.json','preflight-state.json','capture','security','report'))
assert json.loads((r/'input/case.json').read_text())==CASE
snapshot=json.loads((r/'source-snapshot.json').read_text())
assert hashlib.sha256((r/'source-snapshot.json').read_bytes()).hexdigest()==MANIFEST
assert all(hashlib.sha256((r/'src'/n).read_bytes()).hexdigest()==v for n,v in snapshot['files'].items())
print('verified')
'''
        code = ('ROOT=' + repr(location) + '\nCASE=' + repr(case) + '\nMANIFEST='
                + repr(proof['case_source_snapshot_sha256']) + '\n' + code)
        if node_execute(node, ['python3', '-c', code], timeout=240).strip() != 'verified':
            raise ValueError('remaining case did not verify')


def run(root, *, continue_after_archive=False, continue_archived_checkpoint=False):
    if root != ORIGIN / CONTROL_NAME or socket.gethostname().split('.')[0] != 'liteserver-560t-0':
        raise ValueError('continuation is limited to the reviewed control directory')
    if continue_after_archive and continue_archived_checkpoint:
        raise ValueError('choose one continuation checkpoint entry')
    if (root / 'state.json').exists() and not (continue_after_archive or continue_archived_checkpoint):
        raise ValueError('continuation already used; never restart it')
    proof = read(root / 'resume-manifest.json')
    auth = read(root / 'authorization.json')
    if (auth.get('continue_only_unused_1013_to_1020') is not True or auth.get('no_external_task_stop') is not True
            or auth.get('physical_cards') != [4, 5, 6, 7] or auth.get('nodes') != [0, 3]):
        raise ValueError('explicit current continuation authorization required')
    if sha(ORIGIN / 'state.json') != proof['origin_state_sha256'] or sha(ORIGIN / 'plan.json') != proof['origin_plan_sha256']:
        raise ValueError('original stopped ledger changed')
    pending = validate_previous(read(ORIGIN / 'state.json'), continuation_plan())
    launch = read(ORIGIN / 'launch.json')
    proc = Path('/proc') / str(launch['pid'])
    if proc.exists():
        fields = (proc / 'stat').read_text().rsplit(')', 1)[1].split()
        if fields[0] != 'Z' and int(fields[19]) == launch['start_ticks']:
            raise ValueError('original supervisor is still alive')
    completed = []
    checkpoint_digest = None
    if continue_after_archive:
        previous = read(root / 'archive-timeout-v1/state.json')
        if read(root / 'state.json') != previous:
            raise ValueError('archive continuation checkpoint changed or already used')
        current = ORIGIN.parent / 'hccl-diagnose-node03-20261106-1013'
        completed = validate_archived_checkpoint(previous, read(current / 'offload-receipt.json'), continuation_plan())
        with (root / 'archive-continuation.json').open('x') as marker:
            json.dump(dict(checkpoint_sha256=sha(root / 'state.json'),receipt_sha256=sha(current / 'offload-receipt.json'),
                           only_unused=list(range(1014,1021)),no_training_repeated=True),marker,indent=2)
        pending = pending[len(completed):]
    elif continue_archived_checkpoint:
        previous = read(root / 'state.json')
        current = Path(previous['active_directory'])
        completed, checkpoint_digest = consume_archived_checkpoint(
            root, previous, read(current / 'offload-receipt.json'), continuation_plan())
        pending = pending[len(completed):]
    state = dict(status='waiting_node0', requested=8, completed=len(completed), cases=list(completed), active_case=None,
                 active_directory=None, started_unix_ns=time.time_ns(), origin_queue=str(ORIGIN),
                 aggregate_requested=19, prior_completed=10, prior_failed=[1012],
                 aggregate_completed=10+len(completed), no_external_task_stop=True, failed_case_not_repeated=True,
                 resumed_only_after_verified_archive=continue_after_archive or continue_archived_checkpoint,
                 parent_archive_checkpoint_sha256=checkpoint_digest)
    path = root / 'state.json'
    write(path, state)

    def interrupted(signum, frame):
        raise InterruptedError('continuation interrupted by signal ' + str(signum))

    for sig in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP):
        signal.signal(sig, interrupted)
    wait_deadline = time.monotonic() + 48 * 3600
    try:
        verify_prepared(ORIGIN)
        for index, case in pending:
            verify_unused(root, index, case)
            while True:
                before = resources(0)
                state.update(status='waiting_node0', next_case=case['case_id'], checked_unix_ns=time.time_ns())
                write(root / 'last-node0-resources.json', before)
                write(path, state)
                if not idle(before, range(8)):
                    if time.monotonic() >= wait_deadline:
                        raise TimeoutError('bounded 48-hour resource wait expired')
                    time.sleep(1800)
                    continue
                verify_prepared(ORIGIN, runtime=True)
                if not admission(root):
                    if time.monotonic() >= wait_deadline:
                        raise TimeoutError('bounded target resource wait expired; no process stop')
                    state.update(status='waiting_resources', checked_unix_ns=time.time_ns())
                    write(path, state)
                    time.sleep(1800)
                    continue
                time.sleep(30)
                if admission(root):
                    break
                if time.monotonic() >= wait_deadline:
                    raise TimeoutError('resources did not remain idle')
            verify_prepared(ORIGIN, runtime=True)
            current = ORIGIN.parent / ('hccl-diagnose-node03-20261106-' + str(index))
            state.update(status='running', active_case=case['case_id'], active_directory=str(current))
            write(path, state)
            with (root / (str(index) + '.log')).open('x') as log:
                protected_run([sys.executable, str(current / 'src/test/run_node03_authorized.py'),
                    '--root', str(current), '--gpt', '--formal-case', str(current / 'input/case.json')], log, timeout=6500)
            result = inspect_case(current, case)
            state['cases'].append(result)
            state.update(completed=len(state['cases']), aggregate_completed=10 + len(state['cases']), status='awaiting_verified_archive')
            write(path, state)
            deadline = time.monotonic() + 5400
            while not (current / 'offload-receipt.json').exists():
                if time.monotonic() >= deadline:
                    raise TimeoutError('90-minute verified archive deadline; no next capture')
                time.sleep(5)
            if not receipt_verified(read(current / 'offload-receipt.json'), current):
                raise ValueError('two-node archive ACK is incomplete')
            state.update(active_case=None, active_directory=None)
            if not result['effect_gate_passed']:
                state.update(status='ineffective_injection', reason='effect gate failed; no replacement')
                break
        else:
            state.update(status='completed')
    except BaseException as error:
        state.update(status='stopped', error=str(error), no_automatic_resubmission=True)
        raise
    finally:
        state['finished_unix_ns'] = time.time_ns()
        write(path, state)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    continuation = parser.add_mutually_exclusive_group()
    continuation.add_argument('--continue-after-archive', action='store_true')
    continuation.add_argument('--continue-archived-checkpoint', action='store_true')
    args = parser.parse_args()
    is_continuation = args.continue_after_archive or args.continue_archived_checkpoint
    with (ORIGIN / 'queue.lock').open('a') as original_lock, (args.root / 'queue.lock').open('a' if is_continuation else 'x') as lock:
        fcntl.flock(original_lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        run(args.root.resolve(), continue_after_archive=args.continue_after_archive,
            continue_archived_checkpoint=args.continue_archived_checkpoint)
