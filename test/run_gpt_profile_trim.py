"""Frozen Node0 profiling ablation, preserving the original workload and recovery."""
from __future__ import annotations

import argparse
import collections
import fcntl
import hashlib
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
import sys
import time

if __package__:
    from .gpt2_diagnosis_suite import WORKLOAD
    from .node03_device_guard import Guard, OVERHEAD_TRIM_ROOT, OVERHEAD_BENCHMARK_ROOT, PACKAGE, write
    from .run_gpt_overhead import ASSETS, PYTHON, digest, entry_code, metrics, validate_mapping
else:
    from gpt2_diagnosis_suite import WORKLOAD
    from node03_device_guard import Guard, OVERHEAD_TRIM_ROOT, OVERHEAD_BENCHMARK_ROOT, PACKAGE, write
    from run_gpt_overhead import ASSETS, PYTHON, digest, entry_code, metrics, validate_mapping

ROOT = Path('/home/commTeam/zjy/zjy-new-workspace') / OVERHEAD_TRIM_ROOT
BENCHMARK_ROOT = ROOT.with_name(OVERHEAD_BENCHMARK_ROOT)
CONFIGS = {
    'full': ('--hccl=on', '--task-time=on', '--type=db'),
    'no_pmu': ('--hccl=on', '--task-time=l1', '--ai-core=off', '--ascendcl=on', '--type=db'),
    'no_task': ('--hccl=on', '--task-time=off', '--ai-core=off', '--ascendcl=on', '--type=db'),
    'no_acl': ('--hccl=on', '--task-time=l1', '--ai-core=off', '--ascendcl=off', '--type=db'),
}
PROBES = ('no_pmu', 'no_task', 'no_acl')
ORDERS = (('off', 'semantic', 'full_nosem', 'full', 'trim'),
          ('trim', 'full', 'off', 'semantic', 'full_nosem'),
          ('full_nosem', 'trim', 'semantic', 'off', 'full'))


def choose_probe(rows):
    valid = [r for r in rows if r.get('eligible')]
    if not valid:
        raise ValueError('no reduced configuration preserves the diagnostic contract')
    return min(valid, key=lambda r: (r['counts'].get('COMPUTE_TASK_INFO', 0),
        r['counts'].get('TASK', 0), r['counts'].get('CANN_API', 0),
        r['counts'].get('TASK_PMU_INFO', 0), PROBES.index(r['configuration'])))['configuration']


def verified_prior_selection(audit):
    if (audit.get('status') != 'verified_probe_only_benchmark_blocked'
            or audit.get('training_runs') != 3 or audit.get('numerical_ranks_passed') != 12
            or audit.get('benchmark_runs') != 0 or audit.get('unrun_benchmark_samples') != 15
            or [p.get('configuration') for p in audit.get('probes', [])] != list(PROBES)):
        raise ValueError('only the verified three probes and fifteen unrun samples can be continued')
    selected = choose_probe(audit['probes'])
    valid = next(p for p in audit['probes'] if p['configuration'] == selected)
    if (selected != audit.get('selected_configuration') or selected != 'no_pmu'
            or valid['merge_stats'].get('semantic_total') != 224840
            or valid['merge_stats'].get('exact_matched') != 224840
            or valid['binding'].get('sdk_bound_calls') != 3072):
        raise ValueError('prior reduced configuration must preserve all diagnostic evidence')
    return selected


def summarize(rows):
    expected = {(b, mode) for b, order in enumerate(ORDERS) for mode in order}
    if len(rows) != len(expected) or {(r['block'], r['mode']) for r in rows} != expected:
        raise ValueError('all fifteen frozen benchmark samples are required')
    pairs = []
    for block in range(3):
        values = {r['mode']: r['maximum_rank_mean_ns'] for r in rows if r['block'] == block}
        pairs.append(dict(block=block,
            **{m + '_vs_off_percent': 100*(values[m]/values['off']-1) for m in values if m != 'off'},
            trim_vs_full_percent=100*(values['trim']/values['full']-1),
            full_vs_semantic_percent=100*(values['full']/values['semantic']-1),
            msprof_without_semantic_ns=values['full_nosem']-values['off'],
            interaction_ns=(values['full']-values['semantic'])-(values['full_nosem']-values['off'])))
    off = [r['maximum_rank_mean_ns'] for r in rows if r['mode'] == 'off']
    return dict(mode_mean_ms={m: statistics.mean(r['maximum_rank_mean_ns'] for r in rows if r['mode'] == m)/1e6
            for m in ORDERS[0]}, pairs=pairs,
        paired_means={key: statistics.mean(p[key] for p in pairs) for key in pairs[0] if key != 'block'},
        baseline_max_over_min=max(off)/min(off), baseline_unstable=max(off)/min(off)>1.25,
        repetitions_per_mode=3, scope='exploratory paired 10+50 GPT; same attested libraries and SDK; not native DDP or general performance')


def inspect_capture(root, name):
    from hccl.tools.diagnosis.merge_timeline import (parse_plog_inputs, parse_msprof_inputs,
        apply_control_inputs, parse_graph_correlation_inputs, merge_records)
    from hccl.tools.diagnosis.capture_discovery import discover_capture, prepare_capture_identity
    from hccl.tools.diagnosis.workload_binder import bind_capture
    capture = root / 'captures' / name
    node = capture / 'nodes/node0'
    result = dict(eligible=False, counts={}, name=name)
    try:
        files = sorted((node/'msprof').rglob('msprof_*.db'))
        if len(files) != 4:
            raise ValueError('four consolidated profiler DBs are required')
        counts = collections.Counter()
        types = collections.Counter()
        for path in files:
            with sqlite3.connect(path.as_uri()+'?mode=ro', uri=True) as db:
                tables = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
                for table in ('TASK', 'COMPUTE_TASK_INFO', 'COMMUNICATION_TASK_INFO',
                              'COMMUNICATION_OP', 'CANN_API', 'TASK_PMU_INFO'):
                    if table in tables:
                        counts[table] += db.execute('SELECT count(*) FROM '+table).fetchone()[0]
                result['counts'] = dict(counts)
                if 'TASK' in tables:
                    for kind, number in db.execute('SELECT s.value,count(*) FROM TASK t JOIN STRING_IDS s ON s.id=t.taskType GROUP BY s.value'):
                        types[kind] += number
        result.update(counts=dict(counts), task_types=dict(types))
        semantics = parse_plog_inputs(plog_dir=str(node/'plog'), node_id='node0')
        profilers = parse_msprof_inputs(msprof_db_dir=str(node/'msprof'), node_id='node0')
        profilers, controls = apply_control_inputs(profilers, plog_dir=str(node/'plog'), node_id='node0')
        rows, stats = merge_records(semantics, profilers,
            parse_graph_correlation_inputs(plog_dir=str(node/'plog'), node_id='node0'))
        result.update(merge_stats=dict(stats), controls=len(controls))
        if stats['semantic_total'] != 224840 or stats['exact_matched'] != stats['semantic_total']:
            raise ValueError('unchanged complete semantic trace must retain 100 percent exact association')
        if stats['duplicate_semantic_keys'] or stats['duplicate_profiler_execution_keys']:
            raise ValueError('duplicate physical or semantic identities')
        del rows, semantics, profilers
        work = root/'checks'/name
        work.mkdir(parents=True)
        capture_info = discover_capture(capture, work)
        capture_info = prepare_capture_identity(capture_info, work/'identity')
        binding = bind_capture(capture_info, work, mode='rolling')
        if binding.evidence['sdk_bound_calls'] != 3072:
            raise ValueError('all original DDP calls must bind exactly')
        result.update(eligible=True, binding=binding.evidence)
    except (ValueError, sqlite3.Error, OSError) as error:
        result['error'] = repr(error)
    return result


def cancel_owned(guard, base, name):
    code = """import json,os,signal,time
from pathlib import Path
base=Path(BASE);name=NAME
for sig in (signal.SIGTERM,signal.SIGKILL):
 p=base/'numerics'/name/'launcher.json'
 if p.exists():
  d=json.loads(p.read_text());q=Path('/proc')/str(d['pid'])
  try:
   ticks=q.joinpath('stat').read_text().split(') ',1)[1].split()[19]
   argv=q.joinpath('cmdline').read_text()
   if ticks==d['start_ticks'] and str(base/'numerics'/name) in argv and os.getpgid(d['pid'])==d['pid']:
    os.killpg(d['pid'],sig)
  except (ProcessLookupError,FileNotFoundError):pass
 for p in (base/'numerics'/name/'runtime').glob('rank-*.json'):
  d=json.loads(p.read_text());q=Path('/proc')/str(d['pid'])
  try:
   ticks=q.joinpath('stat').read_text().split(') ',1)[1].split()[19]
   argv=q.joinpath('cmdline').read_text().split(chr(0))
   if ticks==d['process_start_ticks'] and str(base/'src/test/gpt2_train.py') in argv and str(base/'numerics'/name) in argv:
    os.kill(d['pid'],sig)
  except (ProcessLookupError,FileNotFoundError):pass
 time.sleep(5)
""".replace('BASE', repr(base)).replace('NAME', repr(name))
    guard.docker(PYTHON, '-c', code)


def run(root):
    benchmark_only = root == BENCHMARK_ROOT
    if root not in {ROOT, BENCHMARK_ROOT} or os.geteuid() != 0 or socket.gethostname().split('.')[0] != 'liteserver-560t-0':
        raise ValueError('only the explicitly authorized Node0 root is allowed')
    if (root/'state.json').exists():
        raise ValueError('never restart this experiment')
    plan = json.loads((root/'plan.json').read_text())
    if (plan['probes'] != ([] if benchmark_only else list(PROBES)) or plan['benchmark_orders'] != [list(x) for x in ORDERS]
            or plan['configurations'] != {k:list(v) for k,v in CONFIGS.items()}
            or plan['workload_configuration'] != dict(WORKLOAD,iters=50)):
        raise ValueError('frozen plan differs from the runner')
    source = json.loads((root/'source-snapshot.json').read_text())['files']
    if any(digest(root/'src'/n) != h for n,h in source.items()):
        raise ValueError('source snapshot changed')
    selected = None
    if benchmark_only:
        if digest(root/'probe-receipt.json') != plan['probe_receipt_sha256']:
            raise ValueError('verified prior probe receipt changed')
        selected = verified_prior_selection(json.loads((root/'probe-receipt.json').read_text()))
    guard, base = Guard(root), '/workspace/'+root.name
    state = dict(status='prechecking', probes=[], completed=[], active=None, requested_benchmarks=15,
        restoration_verified=False, source_sha256=digest(root/'source-snapshot.json'),
        plan_sha256=digest(root/'plan.json'), started_unix_ns=time.time_ns(),
        benchmark_only=benchmark_only, prior_probe_receipt_sha256=plan.get('probe_receipt_sha256'))
    write(root/'state.json', state)
    deadline = time.monotonic()+6300
    shell = ('set -e\nsource /usr/local/Ascend/ascend-toolkit/set_env.sh\n'
        'export ASCEND_OPP_PATH='+ASSETS+'/a3-runtime/opp\n'
        'export LD_LIBRARY_PATH='+base+'/deploy/lib64:'+ASSETS+'/a3-runtime/aarch64-linux/lib64:'
        +ASSETS+'/a3-runtime/opp/built-in/op_impl/ai_core/tbe/op_tiling/lib/linux/aarch64:${LD_LIBRARY_PATH:-}\n'
        'export PYTHONPATH='+base+'/src:'+ASSETS+'/deps\n'
        "export HCCL_OP_EXPANSION_MODE=AI_CPU HCCL_ALGO='level0:ring;level1:ring;level2:ring'\n"
        'export HCCL_EXEC_TIMEOUT=120 HCCL_CONNECT_TIMEOUT=120 OMP_NUM_THREADS=1\n'
        'export ASCEND_GLOBAL_LOG_LEVEL=1 ASCEND_SLOG_PRINT_TO_STDOUT=0\n'
        'unset ASCEND_RT_VISIBLE_DEVICES\n')

    def sample(name, configuration, trace):
        if shutil.disk_usage(root).free < 35*1024**3 or time.monotonic()>deadline-1050:
            raise RuntimeError('bounded disk or time budget reached')
        guard.idle()
        state.update(status='training', active=name)
        write(root/'state.json',state)
        case = dict(schema_version=1,case_id=name,topology=dict(nnodes=1,ranks_per_node=4),
            workload=dict(WORKLOAD,iters=50),workload_seed=20261028,injection=dict(kind='normal'))
        write(root/'input'/(name+'.json'),case)
        out=root/'numerics'/name
        for folder in ('public','private','workload_results'):
            (out/folder).mkdir(parents=True)
        dest=base+'/captures/'+name+'/nodes/node0'
        (root/'captures'/name).mkdir()
        write(root/'captures'/name/'capture.json',dict(run_id=name,sdk_auxiliary_operation_types=['Broadcast']))
        app=[PYTHON,'-m','torch.distributed.run','--nnodes=1','--nproc-per-node=4','--max-restarts=0',
            '--master-addr=127.0.0.1','--master-port=29887',base+'/src/test/gpt2_train.py',
            '--case',base+'/input/'+name+'.json','--output',base+'/numerics/'+name,
            '--data',ASSETS+'/data','--devices','1,3,5,7','--sdk-observations',dest+'/calls']
        flags=('export HCCL_STEP_TRACE={0} HCCL_TASK_SEMANTIC_TRACE={0}\n'.format(int(trace))
            +'export HCCL_TRACE_RUN_ID='+name+' HCCL_TRACE_NODE_ID=node0\n'
            +'export ASCEND_PROCESS_LOG_PATH='+dest+'/plog\n')
        launch=app if configuration is None else ['msprof','--application='+shlex.join(app),'--output='+dest+'/msprof',*CONFIGS[configuration]]
        timed=['timeout','--signal=TERM','--kill-after=30s','900s','bash','-lc',shell+flags+'exec '+shlex.join(launch)]
        started=time.monotonic_ns()
        with (root/'logs'/(name+'.log')).open('x') as log:
            process=subprocess.Popen(['docker','exec','zjy-new',PYTHON,'-c',entry_code(base,name,timed)],stdout=log,stderr=subprocess.STDOUT)
            try:
                process.wait(timeout=950)
                if process.returncode:raise RuntimeError(name+' failed; retain attempt without retry')
            except BaseException:
                cancel_owned(guard,base,name)
                process.wait(timeout=180)
                raise
        samples=[json.loads((out/'workload_results'/('rank-'+str(r)+'.json')).read_text()) for r in range(4)]
        measured=metrics(samples)
        if any(s['loaded_communication_libraries'].get(base+'/deploy/lib64/libhcomm.so')!=guard.host_hash for s in samples):
            raise ValueError('attested Host library not loaded')
        state.update(active=None,status='checking_capture')
        write(root/'state.json',state)
        return dict(name=name,configuration=configuration,trace=trace,wall_ns=time.monotonic_ns()-started,**measured)

    def inspect(name):
        command=['docker','exec','zjy-new',PYTHON,base+'/src/test/run_gpt_profile_trim.py',
            '--root',base,'--inspect',name]
        value=subprocess.run(command,capture_output=True,text=True,timeout=600)
        if value.returncode:raise RuntimeError('CPU capture validator failed: '+value.stderr[-2000:])
        result=json.loads(value.stdout)
        write(root/'checks'/(name+'.json'),result)
        return result

    try:
        for folder in ('logs','numerics','captures','checks'):(root/folder).mkdir()
        with socket.socket() as port:port.bind(('127.0.0.1',29887))
        validate_mapping(guard.docker('npu-smi','info','-m'))
        guard.prepare(7200)
        guard.activate()
        for configuration in (() if benchmark_only else PROBES):
            name='probe-'+configuration.replace('_','-')
            measured=sample(name,configuration,True)
            check=inspect(name)
            check['configuration']=configuration
            state['probes'].append(dict(measured=measured,**check))
            write(root/'state.json',state)
        if not benchmark_only:selected=choose_probe(state['probes'])
        state['selected_configuration']=selected
        write(root/'selection.json',dict(configuration=selected,rule='verified prior selection' if benchmark_only else 'least compute metadata, task rows, API rows, then PMU; never timing-selected',
            probes=state['probes'],prior_probe_receipt_sha256=plan.get('probe_receipt_sha256')))
        for block,order in enumerate(ORDERS):
            for mode in order:
                configuration=selected if mode=='trim' else 'full' if mode in ('full','full_nosem') else None
                name='bench-{}-{}'.format(block,mode.replace('_','-'))
                measured=sample(name,configuration,mode not in ('off','full_nosem'))
                measured.update(block=block,mode=mode)
                if configuration and mode!='full_nosem':
                    check=inspect(name)
                    if not check['eligible']:raise RuntimeError('benchmark lost diagnostic evidence: '+repr(check))
                    measured['validation']=check
                state['completed'].append(measured)
                write(root/'state.json',state)
                time.sleep(3)
        state['summary']=summarize(state['completed'])
        state['status']='restoring'
    except BaseException as error:
        state.update(status='failed',error=repr(error))
        raise
    finally:
        try:
            if guard.snapshot.exists():
                guard.restore()
                snapshot=json.loads(guard.snapshot.read_text())
                actual=guard.verify_original(snapshot)
                timers={suffix:guard.run(['systemctl','is-active',snapshot['unit']+suffix+'.timer'],check=False).strip()
                    for suffix in ('','-probe')}
                if guard.registry.exists() or any(x not in ('inactive','unknown') for x in timers.values()):
                    raise RuntimeError('registry/timer remains active')
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
    write(root/'summary.json',state['summary'])


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',type=Path,required=True)
    parser.add_argument('--inspect')
    args=parser.parse_args()
    if args.inspect:
        if args.root.name not in {OVERHEAD_TRIM_ROOT, OVERHEAD_BENCHMARK_ROOT} or '/' in args.inspect or not args.inspect.startswith(('probe-','bench-')):
            raise ValueError('only this owned capture can be inspected')
        sys.path.insert(0,str(args.root/'src'))
        signal.alarm(540)
        print(json.dumps(inspect_capture(args.root.resolve(),args.inspect)))
    else:
        def interrupted(signum,frame):raise InterruptedError('trim test interrupted by signal '+str(signum))
        signal.signal(signal.SIGTERM,interrupted)
        signal.signal(signal.SIGINT,interrupted)
        with (args.root/'trim.lock').open('x') as lock:
            fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
            run(args.root.resolve())
