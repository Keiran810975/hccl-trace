"""Finish CPU processing of the already completed 901 capture; never rerun training."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import shlex
import shutil
import subprocess
import tarfile
import time

if __package__:
    from .run_node03_preflight import LOCAL_PARENT, PEER_PARENT, PYTHON, container_command, execute, ssh, write
else:
    from run_node03_preflight import LOCAL_PARENT, PEER_PARENT, PYTHON, container_command, execute, ssh, write


def read(path):
    return json.loads(path.read_text())


def digest(path):
    value = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            value.update(block)
    return value.hexdigest()


def verify_numeric(results):
    if (len(results) != 8 or {r['rank'] for r in results} != set(range(8))
            or any(r['status'] != 'passed' or r['world_size'] != 8 or r['warmup'] != 10 or r['iters'] != 50
                   or not r['parameter_update_observed'] or len(r['losses']) != 50 for r in results)
            or any(r['initialization'] != results[0]['initialization'] or r['parameter_samples'] != results[0]['parameter_samples'] for r in results)):
        raise ValueError('all original eight-rank 10+50 numerical results must agree')


def validate_captured_resume(root):
    previous = read(root / 'state.json')
    current = root.parent / 'hccl-diagnose-node03-20261105-901'
    continuing_transfer = ((root / 'captured-input-continuation.json').exists()
        and previous.get('error') == "[Errno 7] Argument list too long: 'ssh'"
        and (current / 'cpu-recovery.json').exists()
        and read(current / 'cpu-recovery.json').get('status') == 'assembling_original_capture'
        and not (root / 'cpu-transfer-repair.json').exists())
    if (previous.get('status') != 'stopped' or previous.get('completed') != 0 or previous.get('cases')
            or previous.get('active_directory') != str(current)
            or (root / 'captured-input-continuation.json').exists() and not continuing_transfer):
        raise ValueError('only one continuation of this stopped first capture is permitted')
    authorized, failed = read(current / 'authorized-state.json'), read(current / 'preflight-state.json')
    log = (current / 'authorized.log').read_text()
    if (authorized.get('restored_nodes') != [0, 3] or failed.get('status') != 'failed'
            or 'network_after = json.loads(execute(root_command(0, query)))' not in log
            or 'exit status 255' not in log or len(list((current / 'capture').rglob('msprof_*.db'))) != 4
            or len(list((current / 'gpt-output/workload_results').glob('rank-*.json'))) != 4
            or (current / 'report').exists() or (root.parent / '.hccl-diagnose-device-active.json').exists()):
        raise ValueError('the exact post-capture SSH failure and original local facts are required')
    return previous


def verify_peer_files(current, peer_files):
    code = """import hashlib,json,sys
from pathlib import Path
r=Path(ROOT)
def digest(path):
 h=hashlib.sha256()
 with path.open('rb') as stream:
  for block in iter(lambda:stream.read(8*1024*1024),b''):h.update(block)
 return h.hexdigest()
expected=json.load(sys.stdin)
assert all(digest(r/n)==h for n,h in expected.items())
print('verified')
""".replace('ROOT', repr(PEER_PARENT + '/' + current.name))
    result = subprocess.run(ssh(shlex.join(['python3', '-c', code])), input=json.dumps(peer_files),
                            text=True, capture_output=True, check=True, timeout=180)
    if result.stdout.strip() != 'verified':
        raise ValueError('peer verification acknowledgment missing')


def recover(current):
    if current != LOCAL_PARENT / 'hccl-diagnose-node03-20261105-901':
        raise ValueError('CPU recovery is limited to the one retained capture')
    receipt_path = current / 'cpu-recovery.json'
    if receipt_path.exists():
        previous = read(receipt_path)
        marker = current.parent / 'hccl-diagnose-node03-20261105-900/cpu-transfer-repair.json'
        if previous['status'] != 'assembling_original_capture' or not marker.exists():
            raise ValueError('only the recorded pre-analysis transfer checkpoint may continue')
        original = previous['original_local_file_sha256']
        if any(digest(current / n) != h for n, h in original.items()):
            raise ValueError('original capture changed before transfer continuation')
    else:
        original = {str(p.relative_to(current)): digest(p) for folder in ('capture', 'gpt-output')
                    for p in (current / folder).rglob('*') if p.is_file()}
        write(receipt_path, dict(status='assembling_original_capture', training_restarted=False,
                                original_local_file_sha256=original, started_unix_ns=time.time_ns()))
    base = '/workspace/' + current.name
    archive = current / 'node3-preflight.tar'
    if not archive.exists():
        with archive.open('xb') as stream:
            subprocess.run(ssh(shlex.join(['docker', 'exec', 'zjy-new', 'tar', '-cf', '-', '-C', base,
                 'capture/nodes/node3', 'gpt-output'])), stdout=stream, check=True, timeout=180)
    unpack = current / 'peer-preflight'
    if not unpack.exists():
        unpack.mkdir()
        with tarfile.open(archive) as source:
            for member in source.getmembers():
                path = (unpack / member.name).resolve()
                if unpack not in path.parents or not (member.isfile() or member.isdir()):
                    raise ValueError('unsafe peer capture member')
            source.extractall(unpack)
    results = [read(p) for folder in (current / 'gpt-output/workload_results', unpack / 'gpt-output/workload_results')
               for p in folder.glob('rank-*.json')]
    verify_numeric(results)
    if len(list((unpack / 'capture/nodes/node3').rglob('msprof_*.db'))) != 4:
        raise ValueError('four original peer-device profiler databases required')
    peer_files = {str(p.relative_to(unpack)): digest(p) for p in unpack.rglob('*') if p.is_file()}
    verify_peer_files(current, peer_files)
    shutil.copytree(unpack / 'capture/nodes/node3', current / 'capture/nodes/node3')
    # No retrospective counters: this ancillary observation failed after the Copy capture.
    write(current / 'network-observation-unavailable.json', dict(network_injection=False,
          reason='post-capture query SSH exit 255', retrospective_counter_values_not_fabricated=True))
    write(current / 'cpu-recovery-transport.json', dict(peer_file_sha256=peer_files,
          numeric_ranks_verified=8, original_peer_files_verified=True, collection_repeated=False))
    state = read(receipt_path)
    state.update(status='analyzing_original_capture', original_peer_files_verified=True)
    write(receipt_path, state)
    command = [PYTHON, '-m', 'hccl.tools.diagnosis.cli', 'analyze', '--capture', base + '/capture',
               '--mode', 'rolling', '--output', base + '/report', '--source-policy', 'dual-v2',
               '--require-clock-alignment', '--selected-iteration-view', '--keep-debug']
    with (current / 'logs/diagnosis-recovery.log').open('x') as log:
        subprocess.run(container_command(base, 0, shlex.join(command), 2400), stdout=log,
                       stderr=subprocess.STDOUT, check=True, timeout=2430)
    write(current / 'diagnosis-seal.json', dict(truth_accessed=False,
          sha256={n: digest(current / 'report' / n) for n in ('execution.html', 'root_causes.json', 'propagation.html')}))
    if any(digest(current / n) != h for n, h in original.items()):
        raise ValueError('an original local capture file changed during CPU recovery')
    state.update(status='passed', finished_unix_ns=time.time_ns(), numeric_ranks_verified=8,
                 original_local_files_unchanged=True, original_consumer_snapshot_used=True)
    write(receipt_path, state)
