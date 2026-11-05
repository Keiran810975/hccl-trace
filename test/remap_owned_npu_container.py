"""Reversible remapping of the idle owned zjy-new container to authorized NPU0-3."""
from __future__ import annotations

import argparse
from copy import deepcopy
import http.client
import json
from pathlib import Path
import re
import shutil
import socket
import subprocess
import time


ROOT = Path('/home/commTeam/zjy/zjy-new-workspace/sdma-npu03-container-20261104')
ORIGINAL = 'cbc48d7657a43ee37be7cb3af08d2f1cb867536d5295bbf30c2d744e884dd62d'
BACKUP = 'zjy-new-npu47-backup-20261104'
FINISHED = 'zjy-new-npu03-finished-20261104'
PACKAGE = '/usr/local/Ascend/cann-8.5.1/opp/built-in/op_impl/aicpu/kernel/aicpu_hcomm.tar.gz'
TIMER = 'hccl-container-npu03-20261104'
ALLOCATION = '01566eeb97bb37f72c26e29a8598b1bc439cc12e87f58b90a6b0cf9d7e13521a'
ALLOCATION_NAME = 'zjy-gpt2-node0-50'


def command(*args, timeout=90):
    return subprocess.check_output(list(args), text=True, stderr=subprocess.STDOUT, timeout=timeout).strip()


def write(path, value):
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(value, indent=2)+'\n')
    temporary.replace(path)


def inspect(name):
    return json.loads(command('docker','inspect',name))[0]


def clone_spec(info, image):
    host = deepcopy(info['HostConfig'])
    if (host['Privileged'] or host.get('DeviceCgroupRules') or host.get('DeviceRequests')
            or info['Config'].get('Labels',{}).get('owner') != 'zjy'
            or info['Config'].get('Labels',{}).get('project') != 'hccl-trace'):
        raise ValueError('only the existing owned nonprivileged container may be remapped')
    numeric = {d['PathOnHost'] for d in host['Devices'] if re.fullmatch(r'/dev/davinci\d+',d['PathOnHost'])}
    if numeric != {'/dev/davinci'+str(i) for i in range(8,16)}:
        raise ValueError('original container mapping changed')
    if any(Path(PACKAGE).is_relative_to(Path(m['Destination'])) for m in info['Mounts']):
        raise ValueError('CANN must be private, not a host/shared package mount')
    host['Devices'] = [d for d in host['Devices'] if d['PathOnHost'] not in numeric] + [
        dict(PathOnHost='/dev/davinci'+str(i),PathInContainer='/dev/davinci'+str(i),CgroupPermissions='rwm') for i in range(8)]
    config = deepcopy(info['Config'])
    config['Labels'] = dict(config['Labels'],hccl_remap_parent=ORIGINAL,hccl_remap_run='sdma-npu03-20261104')
    # No runtime visibility override existed in the inspected source container.
    if any(e.split('=',1)[0] in {'ASCEND_VISIBLE_DEVICES','ASCEND_RT_VISIBLE_DEVICES'} for e in config.get('Env',[])):
        raise ValueError('unexpected visibility environment; do not guess a runtime mapping')
    config.update(Image=image,HostConfig=host)
    return config


class Engine(http.client.HTTPConnection):
    def connect(self):
        self.sock = socket.socket(socket.AF_UNIX,socket.SOCK_STREAM)
        self.sock.settimeout(self.timeout)
        self.sock.connect('/var/run/docker.sock')


def create(spec):
    version = command('docker','version','--format','{{.Server.APIVersion}}')
    connection = Engine('localhost',timeout=120)
    try:
        connection.request('POST','/v'+version+'/containers/create?name=zjy-new',json.dumps(spec),{'Content-Type':'application/json'})
        response = connection.getresponse();body = json.loads(response.read())
        if response.status != 201:
            raise RuntimeError('owned container creation failed: '+str(body))
        return body['Id']
    finally:
        connection.close()


def ensure_idle_container(name):
    lines = command('docker','top',name,'-eo','pid,ppid,comm,args').splitlines()[1:]
    if any(len(line.split(None,3)) != 4 or line.split(None,3)[3] != 'sleep infinity' for line in lines if line.strip()):
        raise ValueError('own container has an unexpected active process; refuse stop/recreate')


def no_active_lease():
    if (ROOT.parent/'.hccl-diagnose-device-active.json').exists():
        raise ValueError('device lease must be fully restored before container replacement')
    for number in range(801,811):
        p = ROOT.parent/('hccl-diagnose-single-20261104-'+str(number))/'security/snapshot.json'
        if p.exists():
            state = json.loads(p.read_text())
            active = subprocess.run(['systemctl','is-active',state['unit']+'.timer'],text=True,capture_output=True,timeout=30)
            if state['phase'] != 'restored' or active.stdout.strip() not in {'inactive','unknown'}:
                raise ValueError('an attempt still has an active/unverified restoration lease')


def restore(root, *, if_incomplete=False):
    state = json.loads((root/'state.json').read_text())
    if state['original_id'] != ORIGINAL:
        raise ValueError('original container identity mismatch')
    if state['phase'] == 'original_restored' or if_incomplete and state['phase'] == 'ready':
        return state
    no_active_lease()
    if state.get('mode') == 'reuse_existing_allocation':
        allocation = inspect(ALLOCATION)
        if allocation['Name'] == '/zjy-new':
            ensure_idle_container(ALLOCATION)
            if command('docker', 'exec', ALLOCATION, 'sha256sum', PACKAGE).split()[0] != state['official_sha256']:
                raise ValueError('reused private Device package has not been restored')
            command('docker', 'rename', ALLOCATION, ALLOCATION_NAME)
        elif allocation['Name'] != '/'+ALLOCATION_NAME:
            raise ValueError('existing allocation name changed unexpectedly')
        original = inspect(ORIGINAL)
        if original['Name'] == '/'+BACKUP:
            command('docker', 'rename', ORIGINAL, 'zjy-new')
        elif original['Name'] != '/zjy-new':
            raise ValueError('original container name changed unexpectedly')
        if (inspect('zjy-new')['Id'] != ORIGINAL or inspect(ALLOCATION_NAME)['Id'] != ALLOCATION
                or not inspect(ORIGINAL)['State']['Running'] or not inspect(ALLOCATION)['State']['Running']
                or command('docker', 'exec', ORIGINAL, 'sha256sum', PACKAGE).split()[0] != state['official_sha256']
                or command('docker', 'exec', ALLOCATION, 'sha256sum', PACKAGE).split()[0] != state['official_sha256']):
            raise RuntimeError('both original owned containers must be restored and verified')
        state.update(phase='original_restored', finished_unix_ns=time.time_ns(),
                     allocation_name_restored=True, neither_container_restarted=True)
        write(root/'state.json', state)
        return state
    original = inspect(ORIGINAL)
    if original['Name'] == '/zjy-new':
        if not original['State']['Running']:command('docker','start',ORIGINAL)
    else:
        found = subprocess.run(['docker','inspect','zjy-new'],text=True,capture_output=True,timeout=30)
        current = json.loads(found.stdout)[0] if found.returncode == 0 else None
        if current:
            labels = current['Config'].get('Labels',{})
            ours = (current['Id']==state.get('new_id') or labels.get('hccl_remap_parent')==ORIGINAL
                    and labels.get('hccl_remap_run')=='sdma-npu03-20261104')
            if not ours or current['HostConfig']['Privileged']:
                raise ValueError('unexpected current container; never replace another container')
            if current['State']['Running']:
                ensure_idle_container('zjy-new')
                if command('docker','exec','zjy-new','sha256sum',PACKAGE).split()[0] != state['official_sha256']:
                    raise ValueError('private official Device package has not been restored')
                command('docker','stop','--time','10',current['Id'])
            command('docker','rename',current['Id'],FINISHED)
        command('docker','rename',ORIGINAL,'zjy-new')
        command('docker','start',ORIGINAL)
    if inspect('zjy-new')['Id'] != ORIGINAL or command('docker','exec','zjy-new','sha256sum',PACKAGE).split()[0] != state['official_sha256']:
        raise RuntimeError('original container restoration did not verify')
    state.update(phase='original_restored',finished_unix_ns=time.time_ns())
    write(root/'state.json',state)
    return state


def reuse_existing(root):
    from run_tool_smoke import available
    no_active_lease()
    previous = json.loads((root/'state.json').read_text())
    if previous['phase'] != 'original_restored':
        raise ValueError('previous container transition must be completely restored')
    if (root.parent/'hccl-diagnose-single-20261104-800/state.json').exists():
        raise ValueError('never change containers after this queue has started')
    original, allocation = inspect('zjy-new'), inspect(ALLOCATION_NAME)
    if original['Id'] != ORIGINAL or allocation['Id'] != ALLOCATION:
        raise ValueError('only the two attested owned containers may exchange names')
    if (not original['State']['Running'] or not allocation['State']['Running']
            or allocation['HostConfig']['Privileged']
            or allocation['HostConfig'].get('DeviceCgroupRules') or allocation['HostConfig'].get('DeviceRequests')
            or allocation['Config'].get('Labels', {}).get('hccl-trace.experiment') != 'gpt2-single-node0-50-20261029-001'):
        raise ValueError('the earlier owned allocation must remain nonprivileged and running')
    old_queue = json.loads((root.parent/'gpt2-single-node0-50-20261029-001/state.json').read_text())
    if (old_queue['status'] != 'completed' or old_queue['completed'] != 31
            or old_queue['requested'] != 31 or old_queue.get('active_case') is not None):
        raise ValueError('the old experiment must have fully completed')
    if any(Path(PACKAGE).is_relative_to(Path(m['Destination'])) for m in allocation['Mounts']):
        raise ValueError('the reused CANN must be private')
    numeric = {d['PathOnHost'] for d in allocation['HostConfig']['Devices']
               if re.fullmatch(r'/dev/davinci\d+', d['PathOnHost'])}
    if numeric != {'/dev/davinci'+str(i) for i in range(8)}:
        raise ValueError('the existing allocation must contain exactly physical NPU0-3')
    for identity in (ORIGINAL, ALLOCATION):
        ensure_idle_container(identity)
        if command('docker', 'exec', identity, 'sha256sum', PACKAGE).split()[0] != previous['official_sha256']:
            raise ValueError('both private packages must be the original official package')
    mapping = command('docker', 'exec', ALLOCATION, 'npu-smi', 'info', '-m')
    for logical in (1, 3, 5, 7):
        if not any(re.match(r'\s*\d+\s+\d+\s+'+str(logical)+r'\s+'+str(logical)+r'\s+Ascend910', line)
                   for line in mapping.splitlines()):
            raise ValueError('existing allocation runtime mapping must be observed')
    if not available(command('npu-smi', 'info'), [0, 1, 2, 3]):
        raise ValueError('both chips of every target card must be idle')
    if subprocess.run(['docker', 'inspect', BACKUP], capture_output=True, timeout=30).returncode == 0:
        raise ValueError('original backup name is occupied')
    history = root/'before-existing-allocation.json'
    with history.open('x') as stream:
        json.dump(previous, stream, indent=2)
    shutil.copy2(Path(__file__), root/Path(__file__).name)
    state = dict(previous, mode='reuse_existing_allocation', phase='allocation_prepared', new_id=ALLOCATION,
                 existing_allocation_original_name=ALLOCATION_NAME, new_mapping=mapping,
                 allocation_reuse_started_ns=time.time_ns(), namespaces_unchanged=True)
    write(root/'state.json', state)
    command('systemd-run', '--unit='+TIMER, '--on-active=600s', '--timer-property=AccuracySec=1s',
            '--property=Type=oneshot', '/usr/bin/python3', str(root/Path(__file__).name), 'restore',
            '--root', str(root), '--if-incomplete')
    if command('systemctl', 'is-active', TIMER+'.timer') != 'active':
        raise RuntimeError('independent alias recovery timer not active')
    try:
        no_active_lease()
        ensure_idle_container(ORIGINAL)
        ensure_idle_container(ALLOCATION)
        command('docker', 'rename', ORIGINAL, BACKUP)
        state['phase'] = 'original_renamed'
        write(root/'state.json', state)
        command('docker', 'rename', ALLOCATION, 'zjy-new')
        if inspect('zjy-new')['Id'] != ALLOCATION:
            raise RuntimeError('existing allocation alias failed')
        state.update(phase='ready', verified_unix_ns=time.time_ns(), neither_container_restarted=True)
        write(root/'state.json', state)
    except BaseException:
        restore(root)
        raise
    finally:
        subprocess.run(['systemctl', 'stop', TIMER+'.timer'], capture_output=True, timeout=30)
    return state


def remap(root):
    from run_tool_smoke import available
    no_active_lease()
    info = inspect('zjy-new')
    if info['Id'] != ORIGINAL or not info['State']['Running']:
        raise ValueError('expected idle original container required')
    ensure_idle_container('zjy-new')
    for name in (BACKUP,FINISHED):
        if subprocess.run(['docker','inspect',name],capture_output=True,timeout=30).returncode==0:
            raise ValueError('reserved backup name is already occupied')
    if not available(command('npu-smi','info'),[0,1,2,3]):
        raise ValueError('both chips of NPU0-3 must be idle')
    clone_spec(info,'validation_only')
    if shutil.disk_usage(root.parent).free < 40*1024**3:
        raise ValueError('at least 40GiB reserve required')
    root.mkdir(mode=0o700,exist_ok=False)
    shutil.copy2(Path(__file__),root/Path(__file__).name)
    shutil.copy2(Path(__file__).with_name('run_tool_smoke.py'),root/'run_tool_smoke.py')
    state = dict(phase='backing_up',original_id=ORIGINAL,original_image=info['Image'],backup_name=BACKUP,
        official_sha256=command('docker','exec','zjy-new','sha256sum',PACKAGE).split()[0],
        new_cards=[0,1,2,3],original_cards=[4,5,6,7],new_id=None,created_unix_ns=time.time_ns(),
        user_authorized_npu03_mapping_and_temporary_signature=True,other_containers_not_modified=True)
    write(root/'state.json',state)
    command('systemd-run','--unit='+TIMER,'--on-active=600s','--timer-property=AccuracySec=1s',
        '--property=Type=oneshot','/usr/bin/python3',str(root/Path(__file__).name),'restore','--root',str(root),'--if-incomplete')
    if command('systemctl','is-active',TIMER+'.timer') != 'active':
        raise RuntimeError('independent container-switch recovery timer not active')
    try:
        image = command('docker','commit',ORIGINAL,'hccl-trace/zjy-new:npu03-20261104',timeout=540)
        state.update(phase='image_preserved',preserved_image=image);write(root/'state.json',state)
        no_active_lease();ensure_idle_container('zjy-new')
        command('docker','stop','--time','10',ORIGINAL)
        command('docker','rename',ORIGINAL,BACKUP)
        state['phase']='original_renamed';write(root/'state.json',state)
        identity = create(clone_spec(info,image))
        state.update(new_id=identity,phase='new_created');write(root/'state.json',state)
        command('docker','start',identity)
        new = inspect('zjy-new')
        expected = {'/dev/davinci'+str(i) for i in range(8)}
        actual = {d['PathOnHost'] for d in new['HostConfig']['Devices'] if re.fullmatch(r'/dev/davinci\d+',d['PathOnHost'])}
        if (new['Id']!=identity or new['HostConfig']['Privileged'] or actual!=expected
                or new['HostConfig']['Runtime']!=info['HostConfig']['Runtime']
                or new['HostConfig']['PidMode']!=info['HostConfig']['PidMode']
                or command('docker','exec','zjy-new','sha256sum',PACKAGE).split()[0]!=state['official_sha256']):
            raise RuntimeError('new mapping/private runtime differs from the approved clone')
        mapping = command('docker','exec','zjy-new','npu-smi','info','-m')
        for logical,physical in [(1,1),(3,3),(5,5),(7,7)]:
            if not any(re.match(r'\s*\d+\s+\d+\s+'+str(logical)+r'\s+'+str(physical)+r'\s+Ascend910',line) for line in mapping.splitlines()):
                raise ValueError('NPU0-3 mapping must be observed, not assumed')
        state.update(phase='ready',new_mapping=mapping,verified_unix_ns=time.time_ns())
        write(root/'state.json',state)
    except BaseException:
        restore(root)
        raise
    finally:
        subprocess.run(['systemctl','stop',TIMER+'.timer'],capture_output=True,text=True,timeout=30)
    return state


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=['remap','restore','reuse-existing'])
    parser.add_argument('--root',type=Path,required=True)
    parser.add_argument('--if-incomplete',action='store_true')
    args=parser.parse_args()
    if args.root.resolve()!=ROOT or socket.gethostname().split('.')[0]!='liteserver-560t-0':
        raise ValueError('only the authorized owned Node0 container transition is allowed')
    print(json.dumps(remap(ROOT) if args.action=='remap' else reuse_existing(ROOT)
                     if args.action=='reuse-existing' else restore(ROOT,if_incomplete=args.if_incomplete)))
