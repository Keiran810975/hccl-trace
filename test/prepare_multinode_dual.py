"""Prepare one new owned two-node snapshot, without changing devices or services."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shlex
import shutil
import socket
import subprocess
import tarfile

from run_node03_preflight import LOCAL_PARENT, PEER_PARENT, ssh, execute, write
from multinode_dual_suite import plan


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def prepare(root):
    if (root.parent != LOCAL_PARENT or root.name not in {'hccl-diagnose-node03-20261103-500','hccl-diagnose-node03-20261103-510','hccl-diagnose-node03-20261103-520'}
            or socket.gethostname().split('.')[0]!='liteserver-560t-0'):
        raise ValueError('reviewed fresh Node0 suite directory required')
    snapshot=json.loads((root/'source-snapshot.json').read_text())
    if any(sha(root/'src'/p)!=value for p,value in snapshot['files'].items()):
        raise ValueError('source snapshot changed')
    previous=LOCAL_PARENT/'gpt2-semantic-20261102-001'
    receipt=json.loads((previous/'build-receipt.json').read_text())
    if receipt['status']!='built' or any(sha(root/'src'/p)!=value for p,value in receipt['verified_current_producer_files'].items()):
        raise ValueError('new semantic Host/Device producer does not match this source')
    (root/'input').mkdir()
    shutil.copytree(previous/'deploy',root/'deploy')
    shutil.copy2(previous/'input/aicpu_hcomm.tar.gz',root/'input/aicpu_hcomm.tar.gz')
    if sha(root/'input/aicpu_hcomm.tar.gz')!=receipt['device_sha256']:
        raise ValueError('Device hash mismatch')
    if any(sha(root/'deploy/lib64'/p)!=value for p,value in receipt['host_libraries'].items()):
        raise ValueError('Host library trio mismatch')
    write(root/'build-receipt.json',receipt)
    write(root/'deployment.json',dict(profile='multinode-dual-v1',source_commit=snapshot['commit'],
        source_manifest_sha256=sha(root/'source-snapshot.json'),producer_files_verified=True))
    write(root/'plan.json',plan())
    bundle=root/'peer-deployment.tar.gz'
    with tarfile.open(bundle,'w:gz') as archive:
        for name in ('src','input','deploy','build-receipt.json','deployment.json','source-snapshot.json'):
            archive.add(root/name,arcname=name)
    peer=Path(PEER_PARENT)/root.name
    target=str(peer)+'.tar.gz'
    subprocess.run(['scp','-i',str(Path.home()/'.ssh/KeyPair-f1dd.pem'),'-o','IdentitiesOnly=yes','-o','BatchMode=yes',
        '-o','StrictHostKeyChecking=yes',str(bundle),'root@192.169.0.220:'+target],check=True,timeout=240)
    code=('import hashlib,json,tarfile;from pathlib import Path;r=Path('+repr(str(peer))+');r.mkdir();'
        'p=Path('+repr(target)+');assert hashlib.sha256(p.read_bytes()).hexdigest()=='+repr(sha(bundle))+';'
        'a=tarfile.open(p);m=a.getmembers();assert all((x.isfile() or x.isdir()) and not Path(x.name).is_absolute() and ".." not in Path(x.name).parts for x in m);'
        'a.extractall(r);s=json.loads((r/"source-snapshot.json").read_text());'
        'assert all(hashlib.sha256((r/"src"/n).read_bytes()).hexdigest()==v for n,v in s["files"].items());'
        'print(json.dumps({"source_files":len(s["files"]),"verified":True}))')
    print(execute(ssh(shlex.join(['python3','-c',code])),timeout=120))
    # A short independent GPT validation precedes the six formal runs.
    if not root.name.endswith('-500'):
        write(root/'prepared.json',dict(prepared=True,source_files=len(snapshot['files']),
            uses_retained_smoke='hccl-diagnose-node03-20261103-501',requires_fresh_cpu_replay=True,
            host_libraries=receipt['host_libraries'],device_sha256=receipt['device_sha256'],no_device_or_service_changes=True))
        print(json.dumps(dict(root=str(root),ready_for_cpu_replay=True)))
        return
    smoke=root.parent/'hccl-diagnose-node03-20261103-501'
    smoke.mkdir()
    for name in ('src','input','deploy'):
        shutil.copytree(root/name,smoke/name)
    for name in ('build-receipt.json','deployment.json','source-snapshot.json'):
        shutil.copy2(root/name,smoke/name)
    write(smoke/'input/normal.json',plan()['cases'][0])
    peer_smoke=Path(PEER_PARENT)/smoke.name
    code=('from pathlib import Path;import shutil,json;r=Path('+repr(str(peer_smoke))+');r.mkdir();s=Path('+repr(str(peer))+');'
        '[shutil.copytree(s/n,r/n) for n in ("src","input","deploy")];'
        '[shutil.copy2(s/n,r/n) for n in ("build-receipt.json","deployment.json","source-snapshot.json")];'
        '(r/"input/normal.json").write_text('+repr(json.dumps(plan()['cases'][0]))+')')
    execute(ssh(shlex.join(['python3','-c',code])),timeout=120)
    write(root/'prepared.json',dict(prepared=True,smoke=str(smoke),peer=str(peer),source_files=len(snapshot['files']),
        host_libraries=receipt['host_libraries'],device_sha256=receipt['device_sha256'],no_device_or_service_changes=True))
    print(json.dumps(dict(root=str(root),smoke=str(smoke),ready_for_cpu_tests=True)))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',type=Path,required=True)
    prepare(parser.parse_args().root.resolve())
