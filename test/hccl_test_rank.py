"""Run an unchanged native HCCL Test rank and attest its loaded libraries."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shlex
import subprocess
import time


def descendants(pid):
    pending=[pid];seen=set()
    while pending:
        current=pending.pop()
        if current in seen:continue
        seen.add(current)
        path=Path('/proc')/str(current)
        try:
            pending.extend(int(p) for p in (path/'task'/str(current)/'children').read_text().split())
        except FileNotFoundError:
            continue
    return seen


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',type=Path,required=True)
    parser.add_argument('--sample',required=True)
    parser.add_argument('--mode',choices=('off','semantic','profile'),required=True)
    parser.add_argument('command',nargs=argparse.REMAINDER)
    args=parser.parse_args();root=args.root.resolve();rank=int(os.environ['PMI_RANK'])
    if rank not in range(4) or not args.command or Path(args.command[0]).parent!=root/'hccl-test/bin':
        raise ValueError('only the reviewed four-rank native test is allowed')
    output=root/'runs'/args.sample;runtime=output/'runtime';runtime.mkdir(parents=True,exist_ok=True)
    path=runtime/('rank-'+str(rank)+'.json')
    if path.exists():raise ValueError('used rank must never restart')
    command=args.command
    if args.mode=='profile':
        capture=output/'capture/msprof'/('rank-'+str(rank))
        command=['msprof','--application='+shlex.join(command),'--output='+str(capture),
                 '--hccl=on','--task-time=l1','--ascendcl=on','--ai-core=off','--type=db']
    start_ticks=lambda pid:(Path('/proc')/str(pid)/'stat').read_text().rsplit(')',1)[1].split()[19]
    state=dict(rank=rank,runtime_device=[1,3,5,7][rank],pid=os.getpid(),start_ticks=start_ticks(os.getpid()),
        role='native_hccl_test_wrapper',started_unix_ns=time.time_ns(),command=command)
    path.write_text(json.dumps(state,indent=2)+'\n')
    process=subprocess.Popen(command,close_fds=False)
    state.update(child_pid=process.pid,child_start_ticks=start_ticks(process.pid))
    path.write_text(json.dumps(state,indent=2)+'\n')
    required={str(root/'deploy/lib64'/name) for name in ('libhcomm.so','libhccl_alg.so','libhccl_plf.so')}
    deadline=time.monotonic()+180
    while process.poll() is None and time.monotonic()<deadline:
        for pid in descendants(process.pid):
            proc=Path('/proc')/str(pid)
            try:
                cmd=(proc/'cmdline').read_bytes().split(b'\0')
                if str(args.command[0]).encode() not in cmd:continue
                maps=(proc/'maps').read_text()
                loaded={line.split()[-1] for line in maps.splitlines() if len(line.split())>=6 and line.split()[-1] in required}
                if loaded!=required:continue
                state.update(native_pid=pid,native_start_ticks=start_ticks(pid),
                    loaded_libraries={name:hashlib.sha256(Path(name).read_bytes()).hexdigest() for name in sorted(loaded)})
                break
            except FileNotFoundError:
                continue
        if state.get('loaded_libraries'):break
        time.sleep(.01)
    returncode=process.wait()
    state.update(returncode=returncode,finished_unix_ns=time.time_ns())
    path.write_text(json.dumps(state,indent=2)+'\n')
    if returncode or not state.get('loaded_libraries'):
        raise RuntimeError('native test failed or actual matched library loading was not observed')


if __name__=='__main__':main()
