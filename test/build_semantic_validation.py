"""Build matching HCOMM Host/Device in a fresh, user-owned validation directory."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import time

LOWLOG_ROOT = 'gpt2-lowlog-20261106-001'

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def finalize_existing(root):
    if root != Path('/workspace/semantic-coverage-20261102'):
        raise ValueError('unexpected build directory')
    receipt = json.loads((root / 'build-receipt.json').read_text())
    if receipt['status'] != 'built':
        raise ValueError('both builds must have succeeded')
    destination = root / 'deploy/lib64'
    for name in ('libhcomm.so', 'libhccl_alg.so', 'libhccl_plf.so'):
        candidates = [p for p in (root / 'build-host').rglob(name) if not p.is_symlink()]
        if len(candidates) != 1:
            raise ValueError('missing/ambiguous Host build library: ' + name)
        shutil.copy2(candidates[0], destination / name)
    if sha(destination / 'libhcomm.so') != receipt['host_sha256']:
        raise ValueError('Host build changed')
    receipt['host_libraries'] = {p.name: sha(p) for p in destination.glob('*.so')}
    (root / 'build-receipt.json').write_text(json.dumps(receipt, indent=2) + '\n')


def build(root):
    if root.parent != Path('/workspace') or root.name not in {'semantic-coverage-20261102', LOWLOG_ROOT}:
        raise ValueError('unexpected owned build directory')
    original = root / 'src/hcomm'
    source = original
    compatibility = None
    if root.name == LOWLOG_ROOT:
        source = root / 'build-source/hcomm'
        shutil.copytree(original, source)
        patch = root / 'src/test/anomaly_injection/hcomm_gcc12_build_compat.patch'
        subprocess.run(['patch', '-p2', '-i', str(patch)], cwd=source, check=True, timeout=30)
        changed = {str(p.relative_to(original)) for p in original.rglob('*')
            if p.is_file() and sha(p) != sha(source / p.relative_to(original))}
        if changed != {'src/platform/resource/netdev/hccl_net_dev_v1.cc',
                'src/platform/resource/notify/notify_pool_impl.h',
                'src/platform/resource/transport/host/transport_direct_npu.cc'}:
            raise ValueError('unexpected compatibility patch scope')
        compatibility = dict(patch_sha256=sha(patch), files=sorted(changed),
            purpose='reuse the reviewed isolated GCC12 build compatibility patch; no communication-path change')
    metadata = [p for p in source.rglob('._*') if p.is_file()]
    for path in metadata:
        path.unlink()
    before = {str(p.relative_to(source)): sha(p) for p in source.rglob('*') if p.is_file()}
    result = dict(source_files=before, started_unix_ns=time.time_ns(), status='building',
                  ignored_archive_metadata=[str(p.relative_to(source)) for p in metadata])
    if compatibility:
        result['build_compatibility'] = compatibility
    (root / 'logs').mkdir(exist_ok=True)
    try:
        for side, targets in [('host', ['hcomm']), ('device', ['generate_device_aicpu_package'])]:
            cache = Path('/workspace/nf-20261022/build-' + side + '/CMakeCache.txt').read_text()
            flags = []
            for line in cache.splitlines():
                if ':UNINITIALIZED=' in line:
                    key, value = line.split(':UNINITIALIZED=', 1)
                    if key not in {'CMAKE_INSTALL_PREFIX'}:
                        flags.append('-D' + key + '=' + value)
            directory = root / ('build-' + side)
            with (root / 'logs' / ('build-' + side + '-' + str(time.time_ns()) + '.log')).open('x') as log:
                subprocess.run(['cmake', '-S', str(source), '-B', str(directory), *flags,
                                '-DCMAKE_INSTALL_PREFIX=' + str(root / 'deploy')],
                               stdout=log, stderr=subprocess.STDOUT, check=True, timeout=180)
                subprocess.run(['cmake', '--build', str(directory), '--target', *targets, '-j8'],
                               stdout=log, stderr=subprocess.STDOUT, check=True, timeout=2400)
        destination = root / 'deploy/lib64'
        destination.mkdir(parents=True)
        for name in ('libhcomm.so', 'libhccl_alg.so', 'libhccl_plf.so'):
            candidates = [p for p in (root / 'build-host').rglob(name) if not p.is_symlink()]
            if len(candidates) != 1:
                raise ValueError('missing/ambiguous Host library: ' + name)
            shutil.copy2(candidates[0], destination / name)
        # Runtime dependencies are copied from the previously validated owned deployment.
        for name in ('libhccl.so', 'libhcomm_rdma.so', 'libhccl_rdma.so'):
            previous = Path('/workspace/nf-20261022/deploy/lib64') / name
            if previous.exists():
                shutil.copy2(previous, destination / name)
        device = source / 'build_device/aicpu_hcomm.tar.gz'
        (root / 'input').mkdir(exist_ok=True)
        shutil.copy2(device, root / 'input/aicpu_hcomm.tar.gz')
        after = {name: sha(source / name) for name in before}
        if before != after:
            raise ValueError('source changed during build')
        result.update(status='built', host_sha256=sha(destination / 'libhcomm.so'),
                      host_libraries={p.name: sha(p) for p in destination.glob('*.so')},
                      device_sha256=sha(root / 'input/aicpu_hcomm.tar.gz'))
        if root.name == LOWLOG_ROOT:
            result['dependency_libraries'] = result['host_libraries']
            result['host_libraries'] = {name: sha(destination / name)
                for name in ('libhcomm.so', 'libhccl_alg.so', 'libhccl_plf.so')}
            result['verified_current_producer_files'] = {'hcomm/' + str(p.relative_to(original)): sha(p)
                for p in original.rglob('*') if p.is_file()}
    except BaseException as error:
        result.update(status='failed', error=str(error))
        raise
    finally:
        result['finished_unix_ns'] = time.time_ns()
        (root / 'build-receipt.json').write_text(json.dumps(result, indent=2) + '\n')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', required=True, type=Path)
    parser.add_argument('--finalize-existing', action='store_true')
    args = parser.parse_args()
    (finalize_existing if args.finalize_existing else build)(args.root)
