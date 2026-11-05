"""Read the existing queue; optionally archive one restored completed case, never launch training."""
from __future__ import annotations

import argparse
import fcntl
import json
from pathlib import Path
import shlex
import subprocess
import time

if __package__:
    from .calibration_offload import SSH, offload
    from .multinode20_suite import ROOT_NAME
else:
    from calibration_offload import SSH, offload
    from multinode20_suite import ROOT_NAME


ROOT = '/home/commTeam/zjy/zjy-new-workspace/' + ROOT_NAME


def snapshot():
    code = r'''
import json,subprocess,time,socket
from pathlib import Path
assert socket.gethostname().split('.')[0]=='liteserver-560t-0'
r=Path(ROOT)
def read(p):return json.loads(p.read_text()) if p.exists() else None
s=read(r/'state.json');launch=read(r/'launch.json')
o=dict(checked_unix_ns=time.time_ns(),state=s,launch=launch,registry=read(r.parent/'.hccl-diagnose-device-active.json'))
p=Path('/proc')/str(launch['pid'])
o['supervisor']=dict(alive=False,identity_matches=False)
if p.exists():
 stat=(p/'stat').read_text().rsplit(')',1)[1].split()
 if int(stat[19])==launch['start_ticks']:
  cmd=(p/'cmdline').read_bytes().replace(b'\0',b' ').decode()
  o['supervisor']=dict(alive=stat[0]!='Z',identity_matches=str(r/'src/test/run_multinode20.py') in cmd,start_ticks=int(stat[19]))
o['last_resources']=read(r/'last-resources.json') or read(r/'last-node0-resources.json')
o['current_preflight']=read(Path(s['active_directory'])/'preflight-state.json') if s.get('active_directory') else None
o['current_authorized']=read(Path(s['active_directory'])/'authorized-state.json') if s.get('active_directory') else None
o['cpu_recovery']=read(Path(s['active_directory'])/'cpu-recovery.json') if s.get('active_directory') else None
o['tail']=(r/'supervisor.log').read_text()[-1800:]
print(json.dumps(o))
'''.replace('ROOT', repr(ROOT))
    result = subprocess.run(SSH + [shlex.join(['python3', '-c', code])], capture_output=True, text=True, timeout=90)
    if result.returncode:
        raise RuntimeError('bounded queue query failed: ' + result.stderr[-1500:])
    return json.loads(result.stdout)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--offload-ready', action='store_true')
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    with (args.output / 'monitor.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        value = snapshot()
        state = value['state']
        if state['status'] not in {'completed', 'stopped', 'ineffective_injection'} and not value['supervisor']['identity_matches']:
            raise RuntimeError('supervisor identity missing or reused; do not start another queue')
        (args.output / 'latest.json').write_text(json.dumps(value, indent=2) + '\n')
        (args.output / 'state.json').write_text(json.dumps(state, indent=2) + '\n')
        with (args.output / 'checks.jsonl').open('a') as stream:
            stream.write(json.dumps(dict(checked_unix_ns=value['checked_unix_ns'],status=state['status'],
                completed=state['completed'],active=state['active_case'],supervisor=value['supervisor'])) + '\n')
        if args.offload_ready and state['status'] == 'awaiting_verified_archive':
            current = Path(state['active_directory'])
            if current.parent != Path(ROOT).parent or value['registry'] is not None:
                raise ValueError('archive admission requires the exact restored completed case')
            receipt = offload(current.name, args.output / 'live', remove_remote=True)
            print(json.dumps(dict(archive_verified=True,case=current.name,sha256=receipt['local_archive_sha256'])))
        print(json.dumps(dict(status=state['status'],completed=state['completed'],requested=state['requested'],
            active_case=state['active_case'],supervisor=value['supervisor'],
            preflight=(value['current_preflight'] or {}).get('status'),
            cpu_recovery=(value.get('cpu_recovery') or {}).get('status'),
            registry_active=value['registry'] is not None), indent=2))


if __name__ == '__main__':
    main()
