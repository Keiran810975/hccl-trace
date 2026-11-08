"""Wait for the existing multi-node queue, then measure one protected native benchmark."""
from __future__ import annotations

import argparse
import csv
import fcntl
import json
import os
from pathlib import Path
import shlex
import shutil
import signal
import socket
import subprocess
import sys
import time

if __package__:
    from .hccl_test_overhead import plan, parse_results, summarize, OPERATORS, ORDERS, SIZES
    from .node03_device_guard import Guard, HCCL_TEST_OVERHEAD_ROOT, PACKAGE, write
    from .run_gpt_overhead import ASSETS, PYTHON, digest, validate_mapping
else:
    from hccl_test_overhead import plan, parse_results, summarize, OPERATORS, ORDERS, SIZES
    from node03_device_guard import Guard, HCCL_TEST_OVERHEAD_ROOT, PACKAGE, write
    from run_gpt_overhead import ASSETS, PYTHON, digest, validate_mapping

PARENT=Path('/home/commTeam/zjy/zjy-new-workspace')
ROOT=PARENT/HCCL_TEST_OVERHEAD_ROOT
MULTI=PARENT/'hccl-diagnose-node03-20261106-1000/remaining8-20261107'


def launcher_entry(base,name,command):
    return ("import json,os;from pathlib import Path;"
        "assert os.getpgid(0)==os.getpid() and os.getsid(0)==os.getpid();"
        "p=Path("+repr(base+'/numerics/'+name+'/launcher.json')+");p.parent.mkdir(parents=True,exist_ok=True);"
        "p.write_text(json.dumps(dict(pid=os.getpid(),start_ticks=Path('/proc/self/stat').read_text().rsplit(')',1)[1].split()[19])));"
        "argv="+repr(command)+";os.execvp(argv[0],argv)")


def validate_probe_checkpoint(previous,probe):
    evidence=probe.get('profile_evidence',{})
    if (previous.get('status')!='failed' or previous.get('requested')!=27 or previous.get('completed')!=[]
            or previous.get('probes')!=[] or probe.get('name')!='probe-all_reduce'
            or probe.get('operator')!='all_reduce' or probe.get('no_npu_rerun') is not True
            or probe.get('original_source_snapshot_sha256')!=previous.get('source_snapshot_sha256')
            or evidence.get('eligible') is not True or evidence.get('profiler_db_count')!=4
            or not evidence.get('semantic_total') or evidence.get('exact_matched')!=evidence['semantic_total']
            or len(probe.get('db_sha256_before_after',{}))!=4):
        raise ValueError('only the original successfully replayed probe and zero performance samples may continue')
    return probe


def wait_previous(root,state, *, verified_quiescent_multinode=False):
    deadline=time.monotonic()+48*3600
    while True:
        previous=json.loads((MULTI/'state.json').read_text())
        launch=json.loads((MULTI/'launch.json').read_text())
        process=Path('/proc')/str(launch['pid']);alive=False
        if process.exists():
            fields=(process/'stat').read_text().rsplit(')',1)[1].split()
            if int(fields[19])==launch['start_ticks'] and fields[0]!='Z':
                assert str(MULTI/'run_multinode8_resume.py').encode() in (process/'cmdline').read_bytes()
                alive=True
        if previous['status'] in {'completed','ineffective_injection'} and not alive:
            break
        if verified_quiescent_multinode and previous['status']=='stopped' and not alive:
            if (previous.get('completed')!=1 or previous.get('error')!='90-minute verified archive deadline; no next capture'):
                raise ValueError('only the reviewed restored archive-timeout checkpoint may yield to the benchmark')
            receipt=json.loads((PARENT/'hccl-diagnose-node03-20261106-1013/offload-receipt.json').read_text())
            if receipt.get('status')!='verified' or receipt.get('file_hashes_verified') is not True:
                raise ValueError('completed1013 must archive before using the quiescent interval')
            break
        if not alive and previous['status']!='stopped':
            raise RuntimeError('previous queue identity disappeared before a terminal state')
        state.update(previous_status=previous['status'],previous_completed=previous['completed'],checked_unix_ns=time.time_ns())
        state['previous_requires_attention']=previous['status']=='stopped'
        write(root/'state.json',state)
        if time.monotonic()>deadline:raise TimeoutError('bounded wait for multi-node completion expired')
        time.sleep(60)
    lock=(MULTI.parent/'queue.lock').open('a');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    # A predecessor failure remains a failure, but cannot leave a lease for this test to inherit.
    from run_multinode20 import node_execute
    for node,parent in ((0,str(PARENT)),(3,'/home/zjy-new/workspace')):
        code=r'''
import pathlib,json,sys
parent=pathlib.Path(PARENT);assert not (parent/'.hccl-diagnose-device-active.json').exists()
sys.path.insert(0,str(parent/'hccl-diagnose-node03-20261106-1000/src/test'))
from node03_device_guard import Guard
snapshots=[]
for index in range(1002,1021):
 p=parent/('hccl-diagnose-node03-20261106-'+str(index))/'security/snapshot.json'
 if not p.exists():continue
 s=json.loads(p.read_text());assert s['phase']=='restored';g=Guard(p.parent.parent)
 for suffix in ('','-probe'):
  assert g.run(['systemctl','is-active',s['unit']+suffix+'.timer'],check=False).strip() in ('inactive','unknown')
 snapshots.append((s['created_unix_ns'],g,s))
_,g,s=max(snapshots,key=lambda v:v[0]);g.verify_original(s)
print('verified')
'''
        assert node_execute(node,['python3','-c','PARENT='+repr(parent)+'\n'+code],timeout=240).strip()=='verified'
    from node03_roce_window import Window
    snapshots=[p for p in PARENT.glob('hccl-diagnose-node03-20261106-*/network/snapshot.json') if p.parent.parent.name.rsplit('-',1)[1].isdigit()]
    for p in snapshots:
        s=json.loads(p.read_text());w=Window(p.parent.parent)
        assert json.loads((p.parent/'restored.json').read_text())['restored_verified']
        for suffix in ('','-probe'):
            assert w.run(['systemctl','is-active',s['unit']+suffix+'.timer'],check=False).strip() in ('inactive','unknown')
        assert {str(d):w.shaping(d) for d in (8,9)}==s['original']
    write(root/'previous-queue-restoration.json',dict(verified=True,previous=previous,launch=launch,unix_ns=time.time_ns()))
    return lock


def cancel_owned(guard,base,name):
    directory=base+'/numerics/'+name
    code=r'''
import json,pathlib,os,signal,time
p=pathlib.Path(DIRECTORY)/'launcher.json';s=json.loads(p.read_text());proc=pathlib.Path('/proc')/str(s['pid'])
for sig in (signal.SIGTERM,signal.SIGKILL):
 try:
  fields=(proc/'stat').read_text().rsplit(')',1)[1].split()
  if fields[19]!=str(s['start_ticks']) or fields[0]=='Z':break
  cmd=(proc/'cmdline').read_bytes().replace(b'\0',b' ').decode()
  assert DIRECTORY.split('/numerics/')[0] in cmd and os.getpgid(s['pid'])==s['pid']
  os.killpg(s['pid'],sig)
 except FileNotFoundError:break
 time.sleep(10)
'''
    guard.docker(PYTHON,'-c','DIRECTORY='+repr(directory)+'\n'+code)


def check_profile(guard,base,name):
    code=r'''
import sys,json,pathlib
r=pathlib.Path(BASE);sys.path.insert(0,str(r/'src'))
from hccl.tools.diagnosis.merge_timeline import parse_plog_inputs,parse_msprof_inputs,parse_graph_correlation_inputs,merge_records,apply_control_inputs
capture=r/'runs'/NAME/'capture';dbs=list((capture/'msprof').rglob('msprof_*.db'))
assert len(dbs)==4,'four native profiler DBs required'
semantics=parse_plog_inputs(plog_dir=str(capture/'plog'),node_id='node0')
profilers=parse_msprof_inputs(msprof_db_dir=str(capture/'msprof'),node_id='node0')
profilers,controls=apply_control_inputs(profilers,plog_dir=str(capture/'plog'),node_id='node0')
rows,stats=merge_records(semantics,profilers,parse_graph_correlation_inputs(plog_dir=str(capture/'plog'),node_id='node0'))
assert stats['semantic_total']>0 and stats['exact_matched']==stats['semantic_total']
assert stats['duplicate_semantic_keys']==stats['duplicate_profiler_execution_keys']==0
assert {s.device_id for s in semantics}=={1,3,5,7},'observed deviceLogicId must match the native runtime IDs'
print(json.dumps(dict(stats,profiler_db_count=4,eligible=True)))
'''
    return json.loads(subprocess.check_output(['docker','exec','zjy-new',PYTHON,'-c',
        'BASE='+repr(base)+'\nNAME='+repr(name)+'\n'+code],text=True,timeout=300))


def run(root, *, continue_after_probe=False, verified_quiescent_multinode=False):
    if root!=ROOT or os.geteuid()!=0 or socket.gethostname().split('.')[0]!='liteserver-560t-0':
        raise ValueError('only the reviewed Node0 benchmark root is authorized')
    if (root/'state.json').exists() and not continue_after_probe:raise ValueError('never restart a used benchmark')
    if json.loads((root/'plan.json').read_text())!=plan():raise ValueError('frozen benchmark plan changed')
    snapshot=json.loads((root/'source-snapshot.json').read_text())
    assert all(digest(root/'src'/n)==h for n,h in snapshot['files'].items())
    probes=[]
    if continue_after_probe:
        previous=json.loads((root/'probe-v1/state.json').read_text())
        if json.loads((root/'state.json').read_text())!=previous:raise ValueError('probe checkpoint changed or already used')
        probe=validate_probe_checkpoint(previous,json.loads((root/'probe-replay-evidence.json').read_text()))
        for name,expected in probe['db_sha256_before_after'].items():
            if digest(root/name)!=expected:raise ValueError('original probe DB changed')
        with (root/'probe-continuation.json').open('x') as marker:
            json.dump(dict(previous_state_sha256=digest(root/'state.json'),original_probe_reused=True,
                performance_samples_previously_run=0,maximum_new_performance_samples=27),marker,indent=2)
        probes=[probe]
    state=dict(status='waiting_multinode',completed=[],requested=27,active=None,probes=probes,
        started_unix_ns=time.time_ns(),restoration_verified=False,plan_sha256=digest(root/'plan.json'),
        source_snapshot_sha256=digest(root/'source-snapshot.json'),scope=plan()['scope'])
    write(root/'state.json',state)
    prior_lock=None;guard=Guard(root);base='/workspace/'+root.name
    for name in ('logs','numerics','runs'):(root/name).mkdir(exist_ok=continue_after_probe)
    shell=('set -e\nsource /usr/local/Ascend/ascend-toolkit/set_env.sh\n'
        'export ASCEND_OPP_PATH='+ASSETS+'/a3-runtime/opp\n'
        'export LD_LIBRARY_PATH='+base+'/deploy/lib64:'+base+'/mpi/lib:'+ASSETS+'/a3-runtime/aarch64-linux/lib64:'
        +ASSETS+'/a3-runtime/opp/built-in/op_impl/ai_core/tbe/op_tiling/lib/linux/aarch64:${LD_LIBRARY_PATH:-}\n'
        'export HCCL_OP_EXPANSION_MODE=AI_CPU HCCL_ALGO="level0:ring;level1:ring;level2:ring"\n'
        'export HCCL_TEST_USE_DEVS=1,3,5,7 HCCL_TEST_PROFILING=0 HCCL_EXEC_TIMEOUT=120 HCCL_CONNECT_TIMEOUT=120 OMP_NUM_THREADS=1\n'
        'export HYDRA_IFACE=lo MPICH_INTERFACE_HOSTNAME=127.0.0.1\n'
        'export ASCEND_GLOBAL_LOG_LEVEL=2 ASCEND_SLOG_PRINT_TO_STDOUT=0\nunset ASCEND_MODULE_LOG_LEVEL ASCEND_RT_VISIBLE_DEVICES\n')
    try:
        prior_lock=wait_previous(root,state,verified_quiescent_multinode=verified_quiescent_multinode)
        deadline=time.monotonic()+48*3600
        from run_multinode20 import resources,idle
        while not idle(resources(0),range(8)):
            if time.monotonic()>deadline:raise TimeoutError('bounded whole-Node0 idle wait expired')
            state.update(status='waiting_node0',checked_unix_ns=time.time_ns());write(root/'state.json',state);time.sleep(300)
        guard.idle();time.sleep(30);guard.idle()
        validate_mapping(guard.docker('npu-smi','info','-m'))
        if shutil.disk_usage(root).free<35*1024**3:raise RuntimeError('35GiB free required')
        guard.prepare(7200);guard.activate();deadline=time.monotonic()+5400

        def sample(name,op,mode,probe=False):
            if shutil.disk_usage(root).free<35*1024**3 or time.monotonic()>deadline-650:
                raise RuntimeError('bounded time or disk budget reached')
            guard.idle()
            state.update(status='probing' if probe else 'measuring',active=name);write(root/'state.json',state)
            capture=base+'/runs/'+name+'/capture';(root/'runs'/name/'capture/plog').mkdir(parents=True)
            native=[base+'/hccl-test/bin/'+op+'_test','-b','8M' if probe else '8K','-e','8M' if probe else '512M',
                    '-f','4','-p','4','-d','fp32','-o','sum','-w','10' if probe else '20','-n','20' if probe else '100','-c','1']
            wrapper=[PYTHON,base+'/src/test/hccl_test_rank.py','--root',base,'--sample',name,'--mode',mode,*native]
            app=[base+'/mpi/bin/mpiexec','-launcher','fork','-iface','lo','-n','4',*wrapper]
            flags=('export HCCL_STEP_TRACE={0} HCCL_TASK_SEMANTIC_TRACE={0}\n'.format(int(mode!='off'))
                   +'export HCCL_TRACE_RUN_ID='+name+' HCCL_TRACE_NODE_ID=node0\n'
                   +'export ASCEND_PROCESS_LOG_PATH='+capture+'/plog\n')
            launch=['timeout','--signal=TERM','--kill-after=30s','600s','bash','-lc',shell+flags+'exec '+shlex.join(app)]
            started=time.monotonic_ns()
            with (root/'logs'/(name+'.log')).open('x') as log:
                process=subprocess.Popen(['docker','exec','zjy-new',PYTHON,'-c',launcher_entry(base,name,launch)],stdout=log,stderr=subprocess.STDOUT)
                try:
                    process.wait(timeout=650)
                    if process.returncode:raise RuntimeError('native benchmark failed; preserve without retry: '+name)
                except BaseException:
                    cancel_owned(guard,base,name);process.wait(timeout=180);raise
            results=parse_results((root/'logs'/(name+'.log')).read_text(),(8*1024**2,) if probe else SIZES)
            ranks=[json.loads((root/'runs'/name/'runtime'/('rank-'+str(i)+'.json')).read_text()) for i in range(4)]
            assert {r['rank'] for r in ranks}==set(range(4)) and all(r['returncode']==0 for r in ranks)
            assert all(r['loaded_libraries']==guard.host_libraries for r in ranks)
            evidence=dict(name=name,operator=op,mode=mode,results=results,wall_ns=time.monotonic_ns()-started,
                          checked_ranks=4,actual_library_loading_verified=True)
            if probe:evidence['profile_evidence']=check_profile(guard,base,name)
            return evidence

        for op in OPERATORS:
            if any(p['operator']==op for p in state['probes']):continue
            state['probes'].append(sample('probe-'+op,op,'profile',True));write(root/'state.json',state)
        for block,order in enumerate(ORDERS):
            operators=OPERATORS[block:]+OPERATORS[:block]
            for op in operators:
                for mode in order:
                    evidence=sample('b%d-%s-%s'%(block,op,mode),op,mode)
                    evidence['block']=block;state['completed'].append(evidence)
                    state.update(active=None);write(root/'state.json',state);time.sleep(3)
        state.update(status='restoring')
    except BaseException as error:
        state.update(status='failed',error=repr(error));raise
    finally:
        try:
            if guard.snapshot.exists():
                guard.restore();saved=json.loads(guard.snapshot.read_text());policies=guard.verify_original(saved)
                timer=guard.run(['systemctl','is-active',saved['unit']+'.timer'],check=False).strip()
                assert timer in ('inactive','unknown') and not guard.registry.exists()
                state['restoration_verified']=True
                write(root/'restoration-verified.json',dict(policies=policies,official_sha256=guard.sha(PACKAGE),timer=timer,registry_absent=True,unix_ns=time.time_ns()))
        except BaseException as error:
            state.update(status='restoration_requires_attention',restoration_error=repr(error));raise
        finally:
            state.update(active=None,finished_device_unix_ns=time.time_ns());write(root/'state.json',state)
            if prior_lock is not None:prior_lock.close()
    state.update(status='checking_profile_evidence');write(root/'state.json',state)
    try:
        checks={r['name']:check_profile(guard,base,r['name']) for r in state['completed'] if r['mode']=='profile'}
        write(root/'profile-evidence.json',checks)
        summary=summarize(state['completed']);write(root/'summary.json',summary)
        state.update(status='completed',profile_evidence_verified=True,finished_unix_ns=time.time_ns())
    except BaseException as error:
        state.update(status='measurement_completed_evidence_failed',error=repr(error));raise
    finally:write(root/'state.json',state)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--root',type=Path,required=True)
    parser.add_argument('--continue-after-probe',action='store_true')
    parser.add_argument('--verified-quiescent-multinode',action='store_true');args=parser.parse_args()
    if args.verified_quiescent_multinode and not args.continue_after_probe:
        parser.error('quiescent scheduling is limited to this exact verified original-probe continuation')
    for sig in (signal.SIGTERM,signal.SIGINT,signal.SIGHUP):
        signal.signal(sig,lambda signum,frame:(_ for _ in ()).throw(InterruptedError('benchmark interrupted: '+str(signum))))
    with (args.root/'benchmark.lock').open('a' if args.continue_after_probe else 'x') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB);run(args.root.resolve(),continue_after_probe=args.continue_after_probe,
            verified_quiescent_multinode=args.verified_quiescent_multinode)
