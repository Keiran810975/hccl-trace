#!/usr/bin/env python3
"""Exactly three guarded Node0 captures, frozen Top1 diagnosis, receipts then cleanup."""
from __future__ import annotations

import argparse
from copy import deepcopy
import csv
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

if __package__:
    from .node03_device_guard import Guard, write
    from .gpt2_diagnosis_suite import WORKLOAD
    from .single_node_capture import bind, actual_windows
else:
    from node03_device_guard import Guard, write
    from gpt2_diagnosis_suite import WORKLOAD
    from single_node_capture import bind, actual_windows


PARENT = Path('/home/commTeam/zjy/zjy-new-workspace')
ROOT = PARENT/'gpt2-three-anomalies-20261102-100'
PREVIOUS = PARENT/'gpt2-semantic-20261102-001'
ASSETS = '/workspace/gpt2-single-node0-50-20261029-001'
PYTHON = '/project/venvs/hccl-py311/bin/python'
CASE_NAMES = ('progress-delay', 'communication-contention', 'compute-contention')


def digest(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for value in iter(lambda: stream.read(1024*1024), b''):
            h.update(value)
    return h.hexdigest()


def cases():
    common = dict(schema_version=1, topology=dict(nnodes=1, ranks_per_node=4),
        workload=dict(WORKLOAD, iters=50), workload_seed=20261028,
        experiment_contract=dict(profile='gpt-three-anomalies-v1', source_selection='frozen-local-top1',
            numeric_reference='previous-five-measured-mean', warmup=10, measured=50))
    result = []
    for i,name in enumerate(CASE_NAMES, 101):
        case = deepcopy(common)
        kind = name.replace('-', '_')
        if kind == 'progress_delay':
            params = dict(delay_ms=500, actual_injection_layer='host_before_collective_not_device_task')
        elif kind == 'communication_contention':
            params = dict(buffer_mib=1024, peer_rank=1, background_processes=1,
                worker_mode='single_process_two_device', declared_affected_ranks=[0,1])
        else:
            params = dict(matrix_size=8192, background_processes=1, gemm_backend='grouped', declared_affected_ranks=[0])
        case.update(case_id=name, injection=dict(kind=kind, target_rank=0, iteration=25,
            bucket_selector_seed=20261102, duration_iters=1, **params))
        result.append((i,case))
    return result


def prepare(root):
    if (root/'plan.json').exists():
        raise ValueError('never replace a frozen three-case plan')
    source = root/'src'
    build = json.loads((PREVIOUS/'build-receipt.json').read_text())
    expected = build['verified_current_producer_files']
    if build['status'] != 'built' or any(digest(source/p) != value for p,value in expected.items()):
        raise ValueError('producer files must match the attested build used by the preceding GPT experiment')
    configs = []
    for number,case in cases():
        attempt = PARENT/('gpt2-three-anomalies-20261102-'+str(number))
        attempt.mkdir(exist_ok=False)
        shutil.copytree(source, attempt/'src')
        shutil.copytree(PREVIOUS/'deploy', attempt/'deploy')
        (attempt/'input').mkdir()
        shutil.copy2(PREVIOUS/'input/aicpu_hcomm.tar.gz', attempt/'input/aicpu_hcomm.tar.gz')
        for name,value in build['host_libraries'].items():
            if digest(attempt/'deploy/lib64'/name) != value:
                raise ValueError('matching Host trio changed')
        if digest(attempt/'input/aicpu_hcomm.tar.gz') != build['device_sha256']:
            raise ValueError('matching Device package changed')
        write(attempt/'build-receipt.json', build)
        write(attempt/'input/case.json', case)
        write(attempt/'owned-attempt.json', dict(root=str(attempt), case_id=case['case_id'], suite=str(root)))
        for name in ('logs','bin'):
            (attempt/name).mkdir()
        configs.append(dict(root=str(attempt), case=case))
    write(root/'plan.json', dict(schema_version=1, cases=configs, new_baseline=False,
        reused_normal_reference=str(PREVIOUS), analyzer_reads_injection_truth=False,
        restore_each_capture_before_cpu_analysis=True, cleanup_only_after_verified_retention=True,
        cards=[4,5,6,7], runtime_devices=[1,3,5,7], created_unix_ns=time.time_ns()))


def shell_for(base):
    return ('source /usr/local/Ascend/ascend-toolkit/set_env.sh\n'
        'export ASCEND_OPP_PATH='+ASSETS+'/a3-runtime/opp\n'
        'export LD_LIBRARY_PATH='+base+'/deploy/lib64:'+ASSETS+'/a3-runtime/aarch64-linux/lib64:'
        +ASSETS+'/a3-runtime/opp/built-in/op_impl/ai_core/tbe/op_tiling/lib/linux/aarch64:${LD_LIBRARY_PATH:-}\n'
        'export PYTHONPATH='+base+'/src:'+ASSETS+'/deps\n'
        'export HCCL_OP_EXPANSION_MODE=AI_CPU HCCL_ALGO="level0:ring;level1:ring;level2:ring"\n'
        'export HCCL_EXEC_TIMEOUT=120 HCCL_CONNECT_TIMEOUT=120 OMP_NUM_THREADS=1\n'
        'export ASCEND_GLOBAL_LOG_LEVEL=1 ASCEND_SLOG_PRINT_TO_STDOUT=0\n'
        'unset ASCEND_RT_VISIBLE_DEVICES\n')


def execute(attempt, label, command, seconds):
    base = '/workspace/'+attempt.name
    with (attempt/'logs'/(label+'.log')).open('x') as log:
        process = subprocess.Popen(['docker','exec','zjy-new','timeout','--signal=TERM','--kill-after=30s',
            str(seconds),'bash','-lc',shell_for(base)+command], stdout=log, stderr=subprocess.STDOUT)
        deadline = time.monotonic()+seconds+40
        try:
            while process.poll() is None:
                if time.monotonic()>deadline or shutil.disk_usage(attempt).free < 8*1024**3:
                    raise RuntimeError('bounded execution or 8GiB emergency disk reserve reached')
                time.sleep(2)
            if process.returncode:
                raise RuntimeError(label+' failed; retained log: '+str(attempt/'logs'/(label+'.log')))
        except BaseException:
            if label in {'capture', 'diagnose'}:
                cleanup = subprocess.run(['docker','exec','zjy-new',PYTHON,
                    base+'/src/test/stop_owned_capture.py','--base',base], capture_output=True,text=True,timeout=60)
                write(attempt/(label+'-stop.json'), dict(returncode=cleanup.returncode,stdout=cleanup.stdout,stderr=cleanup.stderr))
                if cleanup.returncode:
                    raise RuntimeError('owned capture cleanup failed; retain independent restore timer')
            process.terminate()
            try:
                process.wait(timeout=60)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=10)
            raise


def capture(attempt, case, guard):
    base = '/workspace/'+attempt.name
    if shutil.disk_usage(attempt).free < 40*1024**3:
        raise ValueError('40GiB required before each fresh capture')
    guard.container()
    mapping = guard.docker('npu-smi','info','-m')
    (attempt/'logs/runtime-mapping.txt').write_text(mapping)
    import re
    for logical,physical in ((1,9),(3,11),(5,13),(7,15)):
        if not any(re.match(r'\s*\d+\s+\d+\s+'+str(logical)+r'\s+'+str(physical)+r'\s+Ascend910',line) for line in mapping.splitlines()):
            raise ValueError('reviewed whole-card runtime mapping changed')
    with socket.socket() as port:
        port.bind(('127.0.0.1',29876))
    if case['injection']['kind'] == 'communication_contention':
        command=['g++','-std=c++14','-O2',base+'/src/test/anomaly_injection/single_process_comm_load.cc',
            '-I/usr/local/Ascend/cann-8.5.1/include','-L'+base+'/deploy/lib64',
            '-L/usr/local/Ascend/cann-8.5.1/lib64','-lascendcl','-lhccl','-pthread','-o',base+'/bin/single_process_comm_load']
        execute(attempt,'build-worker',shlex.join(command),120)
    for name in ('public','private','workload_results'):
        (attempt/'capture'/name).mkdir(parents=True)
    app=[PYTHON,'-m','torch.distributed.run','--nnodes=1','--nproc-per-node=4','--max-restarts=0',
        '--master-addr=127.0.0.1','--master-port=29876',base+'/src/test/gpt2_train.py',
        '--case',base+'/input/case.json','--output',base+'/capture','--data',ASSETS+'/data','--devices','1,3,5,7',
        '--communication-worker',base+'/bin/single_process_comm_load']
    flags=('export HCCL_STEP_TRACE=1 HCCL_TASK_SEMANTIC_TRACE=1\n'
        'export HCCL_TRACE_RUN_ID='+case['case_id']+' HCCL_TRACE_NODE_ID=node0\n'
        'export ASCEND_PROCESS_LOG_PATH='+base+'/capture/ascend_log\n')
    command=['msprof','--application='+shlex.join(app),'--output='+base+'/capture/msprof',
        '--hccl=on','--task-time=on','--type=db']
    guard.prepare(1800)
    try:
        guard.activate()
        execute(attempt,'capture',flags+shlex.join(command),900)
        results=[json.loads((attempt/'capture/workload_results'/('rank-'+str(i)+'.json')).read_text()) for i in range(4)]
        if (any(r['status']!='passed' or r['warmup']!=10 or r['iters']!=50 or len(r['iteration_ns'])!=50
                or not r['parameter_update_observed'] for r in results)
                or any(r['initialization']!=results[0]['initialization'] or r['parameter_samples']!=results[0]['parameter_samples'] for r in results)
                or any(r['loaded_communication_libraries'].get(base+'/deploy/lib64/libhcomm.so')!=guard.host_hash for r in results)):
            raise ValueError('training, replica or loaded-library validation failed')
    finally:
        if guard.snapshot.exists():
            guard.restore()
            guard.verify_original(json.loads(guard.snapshot.read_text()))
            write(attempt/'restoration-verified.json',dict(restored=True,unix_ns=time.time_ns()))


def evaluate(attempt, case):
    top = attempt/'top1'
    path = top/'report.json'
    seal = json.loads((top/'sealed.json').read_text())
    if digest(path)!=seal['report_sha256'] or digest(top/'resource-comparisons.csv')!=seal['resource_comparisons_sha256']:
        raise ValueError('diagnosis must be sealed before injection truth evaluation')
    report = json.loads(path.read_text())
    binding = json.loads((attempt/'capture/binding-evidence.json').read_text())
    found = {r['rank']:dict(offset=r['raw_to_profiler_offset_ns']) for r in binding['ranks']}
    windows = actual_windows(attempt/'capture',case['case_id'],case,found)
    def overlap(task):
        rank=int(task['user_rank'])
        return sum(max(0,min(int(task['observed_stop_ns']),w['stop_ns'])-max(int(task['observed_start_ns']),w['start_ns']))
            for w in windows if rank in w['target_ranks'] and task['node_id']==w['node_id'])
    evaluated = [dict(candidate_id=c['candidate_id'],node_id=c['node_id'],rank=c['user_rank'],
        stream=c['stream_id'],task=c['task_id'],iteration=c['iteration'],kind=c['task_kind'],
        overlap_ns=overlap(c),hit=overlap(c)>0) for c in report['candidates']]
    inside=[]
    with (top/'resource-comparisons.csv').open(newline='',encoding='utf-8') as stream:
        for item in csv.DictReader(stream):
            if int(item['reference_count'])==5 and overlap(item)>0:
                inside.append(item)
    host = [dict(node_id=c['node_id'],rank=c['user_rank'],iteration=c['iteration'],status=c['status'],
        start_ns=c['observed_start_ns'],stop_ns=c['observed_stop_ns'],delta_ns=c['delta_ns'],
        overlap_ns=overlap(c),supported_waits=len(c['affected_wait_graph_ids'])) for c in report['external_host_observations']]
    hits=sum(c['hit'] for c in evaluated)
    result=dict(case_id=case['case_id'],injection=case['injection'],actual_windows=windows,
        criterion='same declared injection Node/Rank and strictly positive actual-activity overlap',
        communication_evaluates_both_predeclared_endpoints=True if case['injection']['kind']=='communication_contention' else False,
        candidate_count=len(evaluated),hits=hits,precision=hits/len(evaluated) if evaluated else None,
        first_candidate_hit=evaluated[0]['hit'] if evaluated else False,candidates=evaluated,
        primary_target_rank_hits=sum(c['hit'] and c['rank']==case['injection']['target_rank'] for c in evaluated),
        overlapping_resource_count=len(inside),overlapping_slow_resource_count=sum(c['duration_slow']=='True' for c in inside),
        overlapping_resource_factors=[c['slowdown_factor'] for c in inside],
        external_host_observations=host,host_observation_hits=sum(c['overlap_ns']>0 for c in host),
        host_observations_not_counted_as_execution_hits=True,quality=report['quality'],
        report_sha256=seal['report_sha256'],analyzer_reads_injection_truth=False,
        evaluator_reads_truth_after_sealed_diagnosis=True,hardware_interference_duration_claimed=False)
    write(attempt/'evaluation.json',result)
    return result


def retain_and_cleanup(attempt):
    owned=json.loads((attempt/'owned-attempt.json').read_text())
    if owned['root']!=str(attempt.resolve()) or owned['suite']!=str(ROOT) or not (attempt/'restoration-verified.json').is_file():
        raise ValueError('cleanup requires exact ownership and verified restoration')
    result=json.loads((attempt/'evaluation.json').read_text())
    if not result['quality']['strict_replay_passed'] or digest(attempt/'top1/report.json')!=result['report_sha256']:
        raise ValueError('cannot clean incomplete or unsealed diagnosis')
    retained=attempt/'retained'
    retained.mkdir(exist_ok=False)
    for name in ('public','private','workload_results','runtime'):
        shutil.copytree(attempt/'capture'/name,retained/name,ignore=shutil.ignore_patterns('background.log'))
    for name in ('binding-evidence.json','iteration-map.json','preparation-map.json','manifest.json'):
        shutil.copy2(attempt/'capture'/name,retained/name)
    files={}
    for folder in (retained,attempt/'top1'):
        for p in folder.rglob('*'):
            if p.is_file() and not p.is_relative_to(attempt/'top1/analysis'):
                files[str(p.relative_to(attempt))]=digest(p)
    receipt=dict(retained_sha256=files,diagnosis_complete=True,independent_evaluation_complete=True,
        restoration_verified=True,only_this_new_capture_removed=True,created_unix_ns=time.time_ns())
    write(attempt/'retention-receipt.json',receipt)
    for name,value in files.items():
        if digest(attempt/name)!=value:raise ValueError('retained evidence checksum failed')
    removed=[]
    for directory in (attempt/'capture',attempt/'top1/analysis'):
        if directory.is_symlink() or any(p.is_symlink() for p in directory.rglob('*')):
            raise ValueError('refuse linked raw-artifact cleanup')
        size=sum(p.stat().st_size for p in directory.rglob('*') if p.is_file())
        shutil.rmtree(directory)
        removed.append(dict(path=str(directory),bytes=size))
    write(attempt/'cleanup.json',dict(removed=removed,raw_inputs_no_longer_replayable=True,
        retained='Top1 facts/paths, compact resource comparisons, public logs, truth and restoration receipts',unix_ns=time.time_ns()))


def bind_capture(attempt, case):
    # AI_CPU SQEs already carry the physical identity; the legacy Host batch
    # adapter does not describe their child streams. Keep the normal strict merge.
    base='/workspace/'+attempt.name
    return execute(attempt,'bind',shlex.join([PYTHON,base+'/src/test/single_node_capture.py',
        base+'/capture','--run-id',case['case_id'],'--ddp-capture']),300)


def recover_binding(root):
    state_path = root/'state.json'
    previous = json.loads(state_path.read_text())
    if (previous.get('status') != 'failed' or previous.get('phase') != 'binding'
            or previous.get('active') != 'progress-delay' or previous.get('completed') != []
            or previous.get('error') != 'missing/ambiguous vendor batch for exact communication task: (90, 0, 4294967295, -1)'):
        raise ValueError('only the attested first-case legacy adapter failure may continue')
    attempt = PARENT/'gpt2-three-anomalies-20261102-101'
    guard = Guard(attempt)
    snapshot = json.loads(guard.snapshot.read_text())
    if snapshot['phase'] != 'restored' or guard.registry.exists():
        raise ValueError('binding continuation requires completed device restoration')
    guard.verify_original(snapshot)
    exported = attempt/'capture/foreground-dbs'
    if exported.is_symlink() or not exported.is_dir() or any(exported.iterdir()):
        raise ValueError('do not replace existing exported DBs on continuation')
    history = root/'binding-adapter-recovery'
    history.mkdir(exist_ok=False)
    write(history/'failed-state.json', previous)
    shutil.copy2(root/'supervisor.log',history/'failed-supervisor.log')
    exported.rmdir()
    return dict(previous, status='running',error=None,binding_recovery_without_recapture=True,
        resumed_unix_ns=time.time_ns())


def recover_analysis(root):
    previous=json.loads((root/'state.json').read_text())
    attempt=PARENT/'gpt2-three-anomalies-20261102-101'
    if (previous.get('status')!='failed' or previous.get('phase')!='diagnosing'
            or previous.get('active')!='progress-delay' or previous.get('completed')!=[]
            or previous.get('error')!='diagnose failed; retained log: '+str(attempt/'logs/diagnose.log')):
        raise ValueError('only the attested container-path analysis failure may continue')
    guard=Guard(attempt)
    snapshot=json.loads(guard.snapshot.read_text())
    if snapshot['phase']!='restored' or guard.registry.exists():
        raise ValueError('offline continuation requires completed device restoration')
    guard.verify_original(snapshot)
    history=root/'analysis-adapter-recovery';history.mkdir(exist_ok=False)
    write(history/'failed-state.json',previous)
    for name in ('top1','logs/diagnose.log'):
        source=attempt/name
        if source.is_symlink():raise ValueError('refuse linked failed outputs')
        target=history/name;target.parent.mkdir(parents=True,exist_ok=True);source.rename(target)
    path=attempt/'capture/manifest.json'
    shutil.copy2(path,history/'host-path-manifest.json')
    manifest=json.loads(path.read_text())
    for node in manifest['nodes']:
        for field in ('plog_dir','msprof_db_dir'):
            suffix=Path(node[field]).relative_to(attempt)
            node[field]=str(Path('/workspace')/attempt.name/suffix)
    write(path,manifest)
    return dict(previous,status='running',error=None,analysis_recovery_without_recapture=True,
        resumed_unix_ns=time.time_ns())


def run(root, *, resume_binding=False, resume_analysis=False):
    state_path=root/'state.json'
    if state_path.exists() and not (resume_binding or resume_analysis):
        raise ValueError('do not restart or duplicate this three-case queue')
    plan=json.loads((root/'plan.json').read_text())
    state=(recover_analysis(root) if resume_analysis else recover_binding(root) if resume_binding else
        dict(status='running',completed=[],active=None,requested=3,started_unix_ns=time.time_ns()))
    write(state_path,state)
    try:
        for index,entry in enumerate(plan['cases']):
            attempt=Path(entry['root']);case=entry['case'];base='/workspace/'+attempt.name
            state.update(active=case['case_id'],phase='capturing');write(state_path,state)
            if not ((resume_binding or resume_analysis) and index == 0):
                capture(attempt,case,Guard(attempt))
            state['phase']='binding';write(state_path,state)
            if not (resume_analysis and index == 0):
                bind_capture(attempt,case)
            state['phase']='diagnosing';write(state_path,state)
            execute(attempt,'diagnose',shlex.join([PYTHON,base+'/src/test/diagnose_gpt_local_clusters.py',
                '--manifest',base+'/capture/manifest.json','--coordinates',base+'/capture/iteration-map.json',
                '--preparations',base+'/capture/preparation-map.json','--output',base+'/top1']),1800)
            state['phase']='evaluating';write(state_path,state)
            result=evaluate(attempt,case)
            retain_and_cleanup(attempt)
            state['completed'].append(dict(case_id=case['case_id'],root=str(attempt),hits=result['hits'],
                candidate_count=result['candidate_count'],precision=result['precision'],first_candidate_hit=result['first_candidate_hit'],
                overlapping_resource_count=result['overlapping_resource_count'],
                overlapping_slow_resource_count=result['overlapping_slow_resource_count'],restoration_verified=True,cleanup_verified=True))
            state.update(active=None,phase='between_cases');write(state_path,state)
    except BaseException as error:
        state.update(status='failed',error=str(error));write(state_path,state)
        raise
    state.update(status='completed',active=None,phase='finished',finished_unix_ns=time.time_ns());write(state_path,state)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',type=Path,required=True)
    parser.add_argument('--prepare',action='store_true')
    parser.add_argument('--resume-binding',action='store_true')
    parser.add_argument('--resume-analysis',action='store_true')
    args=parser.parse_args()
    if args.root.resolve()!=ROOT or socket.gethostname().split('.')[0]!='liteserver-560t-0':
        raise ValueError('only the reviewed Node0 owned suite is allowed')
    if args.prepare:
        prepare(ROOT)
    else:
        def interrupted(signum,frame):raise InterruptedError('three-case queue interrupted')
        signal.signal(signal.SIGTERM,interrupted);signal.signal(signal.SIGINT,interrupted)
        with (ROOT/'queue.lock').open('a' if args.resume_binding or args.resume_analysis else 'x') as stream:
            fcntl.flock(stream,fcntl.LOCK_EX|fcntl.LOCK_NB)
            run(ROOT,resume_binding=args.resume_binding,resume_analysis=args.resume_analysis)
