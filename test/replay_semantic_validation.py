"""Replay frozen facts with the independent control-comparison consumer snapshot."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import time

from hccl.tools.diagnosis.cli import analyze_capture


def hashes(root):
    return {str(p.relative_to(root)):hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(root.rglob('*')) if p.is_file()}


def run(root, *, prefix='coverage-v2-', source_folder='offline-src'):
    state=json.loads((root/'validation-state.json').read_text())
    if state['status']!='completed' or not state.get('restoration_verified'):
        raise ValueError('capture/overhead and verified restoration must finish first')
    for name in ('preflight','normal','strong-copy'):
        capture=root/'captures'/name
        original=hashes(capture)
        output=root/'reports'/(prefix+name)
        started=time.time_ns()
        analyze_capture(capture,output,mode='rolling',keep_debug=True,allow_uncalibrated_clock=True)
        old=list((root/'reports'/(name+'.debug')).glob('**/rolling/report.json'))
        new=list(output.with_name(output.name+'.debug').glob('**/rolling/report.json'))
        if len(old)!=1 or len(new)!=1:
            raise ValueError('one old/new rolling result required')
        graphs={}
        for filename in ('dep_graph_nodes.csv','dep_graph_edges.csv'):
            left=hashlib.sha256((old[0].parent.parent/filename).read_bytes()).hexdigest()
            right=hashlib.sha256((new[0].parent.parent/filename).read_bytes()).hexdigest()
            if left!=right:
                raise ValueError('physical/semantic graph changed during comparison-only replay')
            graphs[filename]=left
        if original!=hashes(capture):
            raise ValueError('capture input changed during read-only replay')
        receipt=dict(input_sha256=original,graph_sha256=graphs,graph_unchanged=True,
                     analysis_used_injection_truth=False,started_unix_ns=started,finished_unix_ns=time.time_ns(),
                     consumer_sha256=hashes(root/source_folder/'hccl/tools/diagnosis'))
        (root/(prefix+name+'-receipt.json')).write_text(json.dumps(receipt,indent=2)+'\n')
        print(name+': replay passed; inputs and graphs unchanged',flush=True)


if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',type=Path,required=True)
    parser.add_argument('--prefix',default='coverage-v2-')
    parser.add_argument('--source-folder',default='offline-src')
    args=parser.parse_args()
    run(args.root,prefix=args.prefix,source_folder=args.source_folder)
