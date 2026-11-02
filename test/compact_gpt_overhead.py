"""Losslessly archive only this experiment's six completed overhead captures."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import shutil
import tarfile


def compact(root):
    state = json.loads((root / 'state.json').read_text())
    if state['status'] != 'failed' or state.get('restoration_verified') is not True:
        raise ValueError('capture must be stopped and fully restored before archiving')
    destination = root / 'retained-archives'
    destination.mkdir(exist_ok=False)
    for case in state['completed']:
        name = case['name']
        if not name.startswith('overhead-'):
            continue
        source = root / 'captures' / name
        if source.is_symlink() or any(p.is_symlink() for p in source.rglob('*')):
            raise ValueError('refuse linked input')
        files = {str(p.relative_to(source)): hashlib.sha256(p.read_bytes()).hexdigest()
                 for p in source.rglob('*') if p.is_file()}
        archive = destination / (name + '.tar.gz')
        with tarfile.open(archive, 'w:gz', compresslevel=1) as target:
            for relative in sorted(files):
                target.add(source / relative, arcname=relative, recursive=False)
        restored = {}
        with tarfile.open(archive, 'r:gz') as target:
            for member in target:
                if not member.isfile():
                    raise ValueError('unexpected archive entry')
                restored[member.name] = hashlib.sha256(target.extractfile(member).read()).hexdigest()
        if restored != files:
            raise ValueError('lossless archive did not verify')
        receipt = dict(original_capture=str(source), file_sha256=files,
                       archive_sha256=hashlib.sha256(archive.read_bytes()).hexdigest(),
                       verified_all_original_files=True, normal_and_intervention_untouched=True)
        (destination / (name + '-verified.json')).write_text(json.dumps(receipt, indent=2) + '\n')
        shutil.rmtree(source)
        print(name + ': all original files retained in verified archive', flush=True)


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    args = parser.parse_args()
    if args.root.resolve() != Path('/home/commTeam/zjy/zjy-new-workspace/gpt2-semantic-20261102-001'):
        raise ValueError('only this new owned experiment may be compacted')
    compact(args.root)
