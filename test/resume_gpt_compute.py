"""Continue only the never-started third case after the target cards are released."""
from __future__ import annotations

import argparse
import fcntl
import json
from pathlib import Path
import shlex
import signal
import socket
import time

if __package__:
    from . import run_gpt_three_anomalies as suite
else:
    import run_gpt_three_anomalies as suite


def validate_state(state):
    if (state.get('status') != 'failed' or state.get('phase') != 'capturing'
            or state.get('active') != 'compute-contention'
            or state.get('error') != 'both chips of every authorized card must be idle'
            or [c['case_id'] for c in state.get('completed',[])]
                != ['progress-delay','communication-contention']):
        raise ValueError('only the observed unused third-case resource stop may continue')


def main(*, restored_precheck=False):
    root = suite.ROOT
    if socket.gethostname().split('.')[0] != 'liteserver-560t-0':
        raise ValueError('only the existing owned Node0 queue may continue')
    with (root/'queue.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        state = json.loads((root/'state.json').read_text())
        validate_state(state)
        plan = json.loads((root/'plan.json').read_text())
        entry = plan['cases'][2]
        attempt, case = Path(entry['root']), entry['case']
        if attempt != suite.PARENT/'gpt2-three-anomalies-20261102-103':
            raise ValueError('third-case identity changed')
        guard = suite.Guard(attempt)
        if guard.registry.exists() or (attempt/'logs/capture.log').exists():
            raise ValueError('never repeat a captured case or overlap a live device lease')
        if restored_precheck:
            snapshot=json.loads(guard.snapshot.read_text())
            if (not state.get('resource_recovery_only_third_case') or snapshot['phase']!='restored'
                    or 'activated_unix_ns' in snapshot
                    or not json.loads((guard.directory/'restored.json').read_text())['restored']
                    or guard.sha('/usr/local/Ascend/cann-8.5.1/opp/built-in/op_impl/aicpu/kernel/aicpu_hcomm.tar.gz')!=snapshot['official_sha256']):
                raise ValueError('only a fully restored, never-activated precheck may be resumed')
        elif guard.snapshot.exists() or {p.name for p in guard.directory.iterdir()} != {'commands.jsonl'}:
            raise ValueError('unexpected prior device lease')
        if any(p.is_file() or p.is_symlink() for p in (attempt/'capture').rglob('*')):
            raise ValueError('the unstarted attempt contains unexpected data')
        guard.container(); guard.idle()
        if not restored_precheck:
            time.sleep(30); guard.idle()
        # capture's Guard.prepare still repeats idle checks 30 seconds apart,
        # then verifies idle again immediately before applying the device lease.
        history = root/('resource-recovery-user-continue' if restored_precheck else 'resource-recovery')
        history.mkdir(exist_ok=False)
        suite.write(history/'resource-stopped-state.json',state)
        for name in ('security','capture'):
            source = attempt/name
            if source.is_symlink():
                raise ValueError('refuse linked unused directories')
            source.rename(history/name)
        state.update(status='running',phase='capturing',error=None,
            resource_recovery_only_third_case=True,resumed_unix_ns=time.time_ns())
        suite.write(root/'state.json',state)
        base = '/workspace/'+attempt.name
        try:
            suite.capture(attempt,case,guard)
            state['phase']='binding';suite.write(root/'state.json',state)
            suite.bind_capture(attempt,case)
            state['phase']='diagnosing';suite.write(root/'state.json',state)
            suite.execute(attempt,'diagnose',shlex.join([suite.PYTHON,
                base+'/src/test/diagnose_gpt_local_clusters.py','--manifest',base+'/capture/manifest.json',
                '--coordinates',base+'/capture/iteration-map.json','--preparations',base+'/capture/preparation-map.json',
                '--output',base+'/top1']),1800)
            state['phase']='evaluating';suite.write(root/'state.json',state)
            result=suite.evaluate(attempt,case)
            suite.retain_and_cleanup(attempt)
            state['completed'].append(dict(case_id=case['case_id'],root=str(attempt),hits=result['hits'],
                candidate_count=result['candidate_count'],precision=result['precision'],
                first_candidate_hit=result['first_candidate_hit'],
                overlapping_resource_count=result['overlapping_resource_count'],
                overlapping_slow_resource_count=result['overlapping_slow_resource_count'],
                restoration_verified=True,cleanup_verified=True))
        except BaseException as error:
            state.update(status='failed',error=str(error));suite.write(root/'state.json',state)
            raise
        state.update(status='completed',phase='finished',active=None,finished_unix_ns=time.time_ns())
        suite.write(root/'state.json',state)


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--restored-precheck',action='store_true')
    args=parser.parse_args()
    def interrupted(signum,frame):
        raise InterruptedError('third-case continuation interrupted')
    signal.signal(signal.SIGTERM,interrupted)
    signal.signal(signal.SIGINT,interrupted)
    main(restored_precheck=args.restored_precheck)
