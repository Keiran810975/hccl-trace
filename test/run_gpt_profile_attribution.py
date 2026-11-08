"""One frozen, counterbalanced Node0 collector-cost ablation; not a diagnostic preset."""
from __future__ import annotations

import argparse
import collections
import fcntl
import json
import os
from pathlib import Path
import shlex
import shutil
import signal
import socket
import sqlite3
import statistics
import subprocess
import time

if __package__:
    from .gpt2_diagnosis_suite import WORKLOAD
    from .node03_device_guard import Guard, OVERHEAD_ATTRIBUTION_ROOT, OVERHEAD_LOGFILTER_ROOT, LOWLOG_ROOT, PACKAGE, write
    from .run_gpt_overhead import ASSETS, PYTHON, digest, entry_code, metrics, validate_mapping
    from .run_gpt_profile_trim import cancel_owned
else:
    from gpt2_diagnosis_suite import WORKLOAD
    from node03_device_guard import Guard, OVERHEAD_ATTRIBUTION_ROOT, OVERHEAD_LOGFILTER_ROOT, LOWLOG_ROOT, PACKAGE, write
    from run_gpt_overhead import ASSETS, PYTHON, digest, entry_code, metrics, validate_mapping
    from run_gpt_profile_trim import cancel_owned

ROOT = Path('/home/commTeam/zjy/zjy-new-workspace')/OVERHEAD_ATTRIBUTION_ROOT
LOGFILTER_ROOT = ROOT.with_name(OVERHEAD_LOGFILTER_ROOT)
LOWLOG_DIRECTORY = ROOT.with_name(LOWLOG_ROOT)
# Actual readback tables, not these flag names, determine what was collected.
MODES = {
    'off_warn': dict(profile=False, acl=False, hccl=False, trace=False, log_level=2),
    'task_warn': dict(profile=True, acl=False, hccl=False, trace=False, log_level=2),
    'api_warn': dict(profile=True, acl=True, hccl=False, trace=False, log_level=2),
    'hccl_warn': dict(profile=True, acl=True, hccl=True, trace=False, log_level=2),
    'semantic_warn': dict(profile=True, acl=True, hccl=True, trace=True, log_level=2),
    'hccl_info': dict(profile=True, acl=True, hccl=True, trace=False, log_level=1),
    'off_info': dict(profile=False, acl=False, hccl=False, trace=False, log_level=1),
}
ORDERS = (tuple(MODES), tuple(reversed(MODES)))
CONTRASTS = {
    'task_collection': ('task_warn', 'off_warn'),
    'acl_increment': ('api_warn', 'task_warn'),
    'hccl_increment': ('hccl_warn', 'api_warn'),
    'semantic_increment': ('semantic_warn', 'hccl_warn'),
    'ordinary_logs_with_profiler': ('hccl_info', 'hccl_warn'),
    'ordinary_logs_without_profiler': ('off_info', 'off_warn'),
    'profiler_warning_logs': ('hccl_warn', 'off_warn'),
    'profiler_info_logs': ('hccl_info', 'off_info'),
}
LOGFILTER_MODES = {
    'off_hcclinfo': dict(profile=False, acl=False, hccl=False, trace=False, log_level=2, module_log_level='HCCL=1'),
    'profile_hcclinfo': dict(profile=True, acl=True, hccl=True, trace=True, log_level=2, module_log_level='HCCL=1'),
}
LOGFILTER_ORDERS = (tuple(LOGFILTER_MODES), tuple(reversed(LOGFILTER_MODES)))
LOGFILTER_CONTRASTS = {'profiler_plus_semantic': ('profile_hcclinfo', 'off_hcclinfo')}
LOWLOG_MODES = {
    'off_warn': dict(profile=False, acl=False, hccl=False, trace=False, log_level=2),
    'semantic_warn': dict(profile=False, acl=False, hccl=False, trace=True, log_level=2),
    'capture_warn': dict(profile=True, acl=True, hccl=True, trace=True, log_level=2),
    'capture_info': dict(profile=True, acl=True, hccl=True, trace=True, log_level=1),
}
LOWLOG_ORDERS = (tuple(LOWLOG_MODES), tuple(reversed(LOWLOG_MODES)),
    ('semantic_warn','off_warn','capture_info','capture_warn'))
LOWLOG_CONTRASTS = {
    'capture_vs_off': ('capture_warn','off_warn'),
    'semantic_vs_off': ('semantic_warn','off_warn'),
    'msprof_vs_semantic': ('capture_warn','semantic_warn'),
    'lowlog_vs_info': ('capture_warn','capture_info'),
}


def profiler_flags(mode, modes=MODES):
    value = modes[mode]
    return ('--task-time=l1', '--ai-core=off', '--type=db',
            '--ascendcl='+('on' if value['acl'] else 'off'),
            '--hccl='+('on' if value['hccl'] else 'off'))


def summarize(rows, orders=ORDERS, modes=MODES, contrasts=CONTRASTS):
    expected = {(b, m) for b, order in enumerate(orders) for m in order}
    if len(rows) != len(expected) or {(r['block'], r['mode']) for r in rows} != expected:
        raise ValueError('all complete frozen blocks are required; keep partial results separate')
    pairs = []
    for block in range(len(orders)):
        values = {r['mode']: r['maximum_rank_mean_ns'] for r in rows if r['block'] == block}
        pairs.append(dict(block=block, contrasts={key: dict(ns=values[a]-values[b],
            percent=100*(values[a]/values[b]-1)) for key, (a, b) in contrasts.items()}))
    return dict(mode_mean_ms={m: statistics.mean(r['maximum_rank_mean_ns'] for r in rows if r['mode']==m)/1e6
        for m in modes}, pairs=pairs, mean_contrasts={key:dict(
            ms=statistics.mean(p['contrasts'][key]['ns'] for p in pairs)/1e6,
            percent=statistics.mean(p['contrasts'][key]['percent'] for p in pairs)) for key in contrasts},
        repetitions_per_mode=len(orders), interpretation='conditional configuration contrasts, not additive function-level CPU costs')


def inventory(root, name, profiled):
    node = root/'captures'/name/'nodes/node0'
    paths = sorted((node/'msprof').rglob('msprof_*.db'))
    if len(paths) != (4 if profiled else 0):
        raise ValueError('unexpected consolidated DB count')
    counts, dbs, configs = collections.Counter(), [], []
    for path in paths:
        with sqlite3.connect(path.as_uri()+'?mode=ro', uri=True) as db:
            tables = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            for table in ('TASK','COMPUTE_TASK_INFO','COMMUNICATION_TASK_INFO','COMMUNICATION_OP','CANN_API','TASK_PMU_INFO'):
                if table in tables:
                    counts[table] += db.execute('SELECT count(*) FROM '+table).fetchone()[0]
        dbs.append(dict(path=str(path.relative_to(root)), bytes=path.stat().st_size, sha256=digest(path)))
    for path in sorted((node/'msprof').rglob('host/sample.json')):
        values = json.loads(path.read_text())
        configs.append(dict(path=str(path.relative_to(root)), values={k:values[k] for k in
            ('profLevel','ai_core_profiling','aiv_profiling','ai_core_metrics','aiv_metrics','host_profiling') if k in values}))
    if counts['TASK_PMU_INFO']:
        raise ValueError('PMU must be disabled in every attribution arm')
    logs, markers = [], collections.Counter()
    for path in sorted((node/'plog').rglob('*')):
        if not path.is_file():
            continue
        h = __import__('hashlib').sha256()
        with path.open('rb') as stream:
            for line in stream:
                h.update(line)
                for token in (b'[HcclTaskSemantic]', b'[HcclTaskControl]', b'[ReportTaskInfo]', b'report sqe profiling'):
                    markers[token.decode()] += line.count(token)
        logs.append(dict(path=str(path.relative_to(root)), bytes=path.stat().st_size, sha256=h.hexdigest()))
    return dict(counts=dict(counts), dbs=dbs, configs=configs, log_markers=dict(markers),
        plog_bytes=sum(v['bytes'] for v in logs), logs=logs)


def run(root):
    if root not in {ROOT,LOGFILTER_ROOT,LOWLOG_DIRECTORY} or os.geteuid()!=0 or socket.gethostname().split('.')[0]!='liteserver-560t-0':
        raise ValueError('only the explicitly authorized Node0 root is allowed')
    if (root/'state.json').exists():
        raise ValueError('never restart a used attribution experiment')
    plan = json.loads((root/'plan.json').read_text())
    modes,orders,contrasts = ((LOWLOG_MODES,LOWLOG_ORDERS,LOWLOG_CONTRASTS) if root==LOWLOG_DIRECTORY
        else (LOGFILTER_MODES,LOGFILTER_ORDERS,LOGFILTER_CONTRASTS) if root==LOGFILTER_ROOT
        else (MODES,ORDERS,CONTRASTS))
    if (plan['modes']!=modes or plan['orders']!=[list(x) for x in orders]
            or plan['workload_configuration']!=dict(WORKLOAD,iters=50) or plan['physical_cards']!=[4,5,6,7]):
        raise ValueError('frozen plan changed')
    files = json.loads((root/'source-snapshot.json').read_text())['files']
    if any(digest(root/'src'/name)!=sha for name,sha in files.items()):
        raise ValueError('frozen source changed')
    guard, base = Guard(root), '/workspace/'+root.name
    state = dict(status='prechecking', requested=sum(map(len,orders)), completed=[], active=None, restoration_verified=False,
        source_sha256=digest(root/'source-snapshot.json'),plan_sha256=digest(root/'plan.json'),started_unix_ns=time.time_ns())
    write(root/'state.json', state)
    shell = ('set -e\nsource /usr/local/Ascend/ascend-toolkit/set_env.sh\n'
        'export ASCEND_OPP_PATH='+ASSETS+'/a3-runtime/opp\n'
        'export LD_LIBRARY_PATH='+base+'/deploy/lib64:'+ASSETS+'/a3-runtime/aarch64-linux/lib64:'
        +ASSETS+'/a3-runtime/opp/built-in/op_impl/ai_core/tbe/op_tiling/lib/linux/aarch64:${LD_LIBRARY_PATH:-}\n'
        'export PYTHONPATH='+base+'/src:'+ASSETS+'/deps\n'
        "export HCCL_OP_EXPANSION_MODE=AI_CPU HCCL_ALGO='level0:ring;level1:ring;level2:ring'\n"
        'export HCCL_EXEC_TIMEOUT=120 HCCL_CONNECT_TIMEOUT=120 OMP_NUM_THREADS=1\n'
        'export ASCEND_SLOG_PRINT_TO_STDOUT=0\nunset ASCEND_RT_VISIBLE_DEVICES\n')
    deadline = time.monotonic()+6300
    try:
        for folder in ('logs','numerics','captures','checks'):
            (root/folder).mkdir()
        with socket.socket() as port:
            port.bind(('127.0.0.1',29889))
        validate_mapping(guard.docker('npu-smi','info','-m'))
        guard.prepare(7200)
        guard.activate()
        for block,order in enumerate(orders):
            for mode in order:
                if shutil.disk_usage(root).free<35*1024**3 or time.monotonic()>deadline-1000:
                    raise RuntimeError('bounded disk/time budget reached')
                guard.idle()
                name='cost-{}-{}'.format(block,mode.replace('_','-'))
                flags=modes[mode]
                state.update(status='training',active=name)
                write(root/'state.json',state)
                write(root/'input'/(name+'.json'),dict(schema_version=1,case_id=name,
                    topology=dict(nnodes=1,ranks_per_node=4),workload=dict(WORKLOAD,iters=50),
                    workload_seed=20261028,injection=dict(kind='normal')))
                for folder in ('public','private','workload_results'):
                    (root/'numerics'/name/folder).mkdir(parents=True)
                (root/'captures'/name).mkdir()
                write(root/'captures'/name/'capture.json',dict(run_id=name,sdk_auxiliary_operation_types=['Broadcast']))
                dest=base+'/captures/'+name+'/nodes/node0'
                app=[PYTHON,'-m','torch.distributed.run','--nnodes=1','--nproc-per-node=4','--max-restarts=0',
                    '--master-addr=127.0.0.1','--master-port=29889',base+'/src/test/gpt2_train.py',
                    '--case',base+'/input/'+name+'.json','--output',base+'/numerics/'+name,
                    '--data',ASSETS+'/data','--devices','1,3,5,7','--sdk-observations',dest+'/calls']
                env=('export HCCL_STEP_TRACE={0} HCCL_TASK_SEMANTIC_TRACE={0}\n'.format(int(flags['trace']))
                    +'export ASCEND_GLOBAL_LOG_LEVEL='+str(flags['log_level'])+'\n'
                    +('export ASCEND_MODULE_LOG_LEVEL='+shlex.quote(flags['module_log_level'])+'\n'
                        if 'module_log_level' in flags else 'unset ASCEND_MODULE_LOG_LEVEL\n')
                    +'export HCCL_TRACE_RUN_ID='+name+' HCCL_TRACE_NODE_ID=node0\n'
                    +'export ASCEND_PROCESS_LOG_PATH='+dest+'/plog\n')
                launch=app if not flags['profile'] else ['msprof','--application='+shlex.join(app),
                    '--output='+dest+'/msprof',*profiler_flags(mode,modes)]
                timed=['timeout','--signal=TERM','--kill-after=30s','900s','bash','-lc',shell+env+'exec '+shlex.join(launch)]
                started=time.monotonic_ns()
                with (root/'logs'/(name+'.log')).open('x') as log:
                    process=subprocess.Popen(['docker','exec','zjy-new',PYTHON,'-c',entry_code(base,name,timed)],
                        stdout=log,stderr=subprocess.STDOUT)
                    try:
                        process.wait(timeout=950)
                        if process.returncode:
                            raise RuntimeError(name+' failed; no retry')
                    except BaseException:
                        cancel_owned(guard,base,name)
                        process.wait(timeout=180)
                        raise
                wall=time.monotonic_ns()-started
                samples=[json.loads((root/'numerics'/name/'workload_results'/('rank-'+str(r)+'.json')).read_text()) for r in range(4)]
                measured=metrics(samples)
                if any(s['loaded_communication_libraries'].get(base+'/deploy/lib64/libhcomm.so')!=guard.host_hash for s in samples):
                    raise ValueError('attested Host library not loaded')
                state.update(status='inventory',active=None)
                write(root/'state.json',state)
                evidence=inventory(root,name,flags['profile'])
                write(root/'checks'/(name+'.json'),evidence)
                state['completed'].append(dict(name=name,block=block,mode=mode,wall_ns=wall,
                    counts=evidence['counts'],plog_bytes=evidence['plog_bytes'],log_markers=evidence['log_markers'],**measured))
                write(root/'state.json',state)
                if root==LOWLOG_DIRECTORY and flags['profile']:
                    code='import sys,json;from pathlib import Path;sys.path.insert(0,'+repr(base+'/src')+');from test.run_gpt_profile_trim import inspect_capture;print(json.dumps(inspect_capture(Path('+repr(base)+'),'+repr(name)+')))'
                    checked=subprocess.run(['docker','exec','zjy-new',PYTHON,'-c',code],capture_output=True,text=True,timeout=600)
                    if checked.returncode:
                        raise RuntimeError('low-log evidence validator failed: '+checked.stderr[-2000:])
                    validity=json.loads(checked.stdout)
                    state['completed'][-1]['validation']=validity
                    write(root/'checks'/(name+'-compatibility.json'),validity)
                    write(root/'state.json',state)
                    if not validity['eligible']:
                        raise RuntimeError('low-log capture lost exact diagnostic evidence; retain and stop')
                time.sleep(3)
        state.update(status='restoring',summary=summarize(state['completed'],orders,modes,contrasts))
    except BaseException as error:
        state.update(status='failed',error=repr(error))
        raise
    finally:
        try:
            if guard.snapshot.exists():
                guard.restore()
                snapshot=json.loads(guard.snapshot.read_text())
                actual=guard.verify_original(snapshot)
                timers={s:guard.run(['systemctl','is-active',snapshot['unit']+s+'.timer'],check=False).strip() for s in ('','-probe')}
                if guard.registry.exists() or any(t not in ('inactive','unknown') for t in timers.values()):
                    raise RuntimeError('rollback timer or registry remains')
                state['restoration_verified']=True
                write(root/'restoration-verified.json',dict(policies=actual,official_sha256=guard.sha(PACKAGE),
                    timers=timers,registry_absent=True,container_id=guard.container(snapshot['container_id']),unix_ns=time.time_ns()))
        except BaseException as error:
            state.update(status='restoration_requires_attention',restoration_error=repr(error))
            raise
        finally:
            state.update(active=None,finished_unix_ns=time.time_ns())
            write(root/'state.json',state)
    state['status']='captured_and_restored'
    write(root/'state.json',state)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',type=Path,required=True)
    args=parser.parse_args()
    def interrupted(signum,frame):
        raise InterruptedError('attribution interrupted by signal '+str(signum))
    signal.signal(signal.SIGTERM,interrupted)
    signal.signal(signal.SIGINT,interrupted)
    with (args.root/'attribution.lock').open('x') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        run(args.root.resolve())
