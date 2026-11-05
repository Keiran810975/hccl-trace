"""CPU-only deployment of the frozen 20-run batch; no device or service changes."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shlex
import shutil
import socket
import subprocess
import sys
import tarfile

sys.path.insert(0, str(Path(__file__).resolve().parent))
from multinode20_suite import ROOT_NAME, PROFILE, plan
from run_multinode20 import sha, read
from run_node03_preflight import LOCAL_PARENT, PEER_PARENT, execute, ssh, write


def prepare(root):
    if root != LOCAL_PARENT / ROOT_NAME or socket.gethostname().split('.')[0] != 'liteserver-560t-0':
        raise ValueError('only the reviewed fresh twenty-case root is accepted')
    if (root / 'prepared.json').exists() or (root / 'state.json').exists():
        raise ValueError('deployment already used; inspect without restarting')
    snapshot = read(root / 'source-snapshot.json')
    assert all(sha(root / 'src' / n) == h for n, h in snapshot['files'].items())
    previous = LOCAL_PARENT / 'gpt2-semantic-20261102-001'
    receipt = read(previous / 'build-receipt.json')
    assert receipt['status'] == 'built'
    assert all(sha(root / 'src' / n) == h for n, h in receipt['verified_current_producer_files'].items())
    shutil.copytree(previous / 'deploy', root / 'deploy')
    (root / 'input').mkdir()
    shutil.copy2(previous / 'input/aicpu_hcomm.tar.gz', root / 'input/aicpu_hcomm.tar.gz')
    assert sha(root / 'input/aicpu_hcomm.tar.gz') == receipt['device_sha256']
    assert all(sha(root / 'deploy/lib64' / n) == h for n, h in receipt['host_libraries'].items())
    write(root / 'build-receipt.json', receipt)
    write(root / 'deployment.json', dict(profile=PROFILE, source_commit=snapshot['commit'],
        source_manifest_sha256=sha(root / 'source-snapshot.json'), cards=[4, 5, 6, 7], producer_files_verified=True))
    write(root / 'plan.json', plan())
    proof = read(LOCAL_PARENT / plan()['normal_reference'] / 'network-port-evidence.json')
    from node03_roce_window import baseline_active
    baseline_active(proof)
    write(root / 'input/network-baseline.json', proof)
    write(root / 'network-reference-audit.json', dict(source=plan()['normal_reference'], sha256=sha(root / 'input/network-baseline.json'),
        previous_foreground_only_observation=True, current_apply_verify_restore_and_foreground_traffic_still_required=True,
        normal_training_not_repeated=True))
    names = ('src', 'input', 'deploy', 'build-receipt.json', 'deployment.json', 'source-snapshot.json', 'authorization.json', 'plan.json')
    bundle = root / 'peer-deployment.tar.gz'
    with tarfile.open(bundle, 'w:gz') as archive:
        for name in names:
            archive.add(root / name, arcname=name)
    target = str(Path(PEER_PARENT) / (ROOT_NAME + '.tar.gz'))
    subprocess.run(['scp', '-i', '/home/commTeam/.ssh/KeyPair-f1dd.pem', '-o', 'BatchMode=yes',
        '-o', 'StrictHostKeyChecking=yes', str(bundle), 'root@192.169.0.220:' + target], check=True, timeout=300)
    code = ("import hashlib,json,tarfile;from pathlib import Path;r=Path(" + repr(PEER_PARENT + '/' + ROOT_NAME) + ");r.mkdir();"
        'p=Path(' + repr(target) + ');assert hashlib.sha256(p.read_bytes()).hexdigest()==' + repr(sha(bundle)) + ';'
        "a=tarfile.open(p);m=a.getmembers();assert all((x.isfile() or x.isdir()) and not Path(x.name).is_absolute() and '..' not in Path(x.name).parts for x in m);"
        "a.extractall(r);s=json.loads((r/'source-snapshot.json').read_text());assert all(hashlib.sha256((r/'src'/n).read_bytes()).hexdigest()==v for n,v in s['files'].items());print('verified')")
    execute(ssh(shlex.join(['python3', '-c', code])), timeout=180)
    for node in (0, 3):
        parent = str(LOCAL_PARENT) if node == 0 else PEER_PARENT
        source = r'''
import hashlib,json,os,shutil
from pathlib import Path
root=Path(ROOT)
plan=json.loads((root/'plan.json').read_text())
snapshot=json.loads((root/'source-snapshot.json').read_text())
for index,case in enumerate(plan['cases'],901):
 r=root.parent/('hccl-diagnose-node03-20261105-'+str(index));r.mkdir()
 shutil.copytree(root/'src',r/'src')
 shutil.copytree(root/'deploy',r/'deploy',copy_function=os.link)
 (r/'input').mkdir()
 for n in ('aicpu_hcomm.tar.gz','network-baseline.json'):os.link(root/'input'/n,r/'input'/n)
 for n in ('build-receipt.json','deployment.json','source-snapshot.json','authorization.json'):shutil.copy2(root/n,r/n)
 (r/'input/case.json').write_text(json.dumps(case,indent=2)+'\n')
 assert all(hashlib.sha256((r/'src'/n).read_bytes()).hexdigest()==v for n,v in snapshot['files'].items())
print(json.dumps(dict(prepared_cases=20,source_files=len(snapshot['files']))))
'''.replace('ROOT', repr(parent + '/' + ROOT_NAME))
        output = execute(ssh(shlex.join(['python3', '-c', source])) if node == 3 else ['python3', '-c', source], timeout=300)
        write(root / ('prepared-node%d.json' % node), json.loads(output))
    write(root / 'prepared.json', dict(prepared=True, cases=20, source_files=len(snapshot['files']),
        no_device_or_service_changes=True, source_snapshot_sha256=sha(root / 'source-snapshot.json'),
        plan_sha256=sha(root / 'plan.json'), host_libraries=receipt['host_libraries'], device_sha256=receipt['device_sha256']))
    print(json.dumps(read(root / 'prepared.json')))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    prepare(parser.parse_args().root.resolve())
