"""Create an explicit source-only snapshot; never include captures or credentials."""
from __future__ import annotations

import argparse
import hashlib
import io
import json
from pathlib import Path
import subprocess
import tarfile


PRODUCERS = (
    'hcomm/src/algorithm/base/alg_template/component/task_semantic_scope.cc',
    'hcomm/src/algorithm/base/alg_template/component/task_semantic_scope.h',
    'hcomm/src/algorithm/base/alg_template/temp_all_gather/all_gather_ring_concurrent_direct.cc',
    'hcomm/src/algorithm/base/alg_template/temp_reduce_scatter/reduce_scatter_ring_concurrent_direct.cc',
    'hcomm/src/common/debug/profiling/inc/task_semantic_trace.h',
    'hcomm/src/common/debug/profiling/task_semantic_aicpu.cc',
    'hcomm/src/common/debug/profiling/task_semantic_trace.cc',
    'hcomm/src/platform/task/dispatcher_aicpu.cc')


def package(destination):
    root = Path(__file__).resolve().parents[1]
    paths = set()
    for folder in ('hccl/tools/diagnosis', 'hccl_trace', 'examples', 'test'):
        paths.update(p for p in (root/folder).glob('**/*.py') if 'out' not in p.relative_to(root/folder).parts
            and '__pycache__' not in p.parts)
    for folder in ('test/fixtures', 'test/anomaly_injection'):
        paths.update((root/folder).glob('*.cc'))
    paths.update(root/p for p in PRODUCERS)
    files = {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(paths)}
    commit = subprocess.check_output(['git','rev-parse','HEAD'],cwd=root,text=True).strip()
    diff = subprocess.check_output(['git','diff','--binary'],cwd=root)
    manifest = dict(schema_version=1,profile='multinode-dual-v1',commit=commit,
        tracked_diff_sha256=hashlib.sha256(diff).hexdigest(),files=files,
        excludes=['credentials','test/out','artifacts','git metadata','model data','binary libraries'])
    with destination.open('xb') as stream, tarfile.open(fileobj=stream, mode='w:gz') as archive:
        for p in sorted(paths): archive.add(p,arcname='src/'+str(p.relative_to(root)),recursive=False)
        data=(json.dumps(manifest,indent=2)+'\n').encode()
        entry=tarfile.TarInfo('source-snapshot.json');entry.size=len(data)
        archive.addfile(entry,io.BytesIO(data))
    return dict(files=len(files),bytes=destination.stat().st_size,sha256=hashlib.sha256(destination.read_bytes()).hexdigest())


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    print(json.dumps(package(args.output)))
