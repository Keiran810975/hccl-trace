"""Verified normal-input archive while independent abnormal analysis continues."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import shutil
import tarfile


def compact(root):
    public = json.loads((root / 'reports/normal/root_causes.json').read_text())
    state = json.loads((root / 'state.json').read_text())
    if not public['quality']['pipeline_passed'] or not state.get('restoration_verified'):
        raise ValueError('completed normal diagnosis and restored devices required')
    paths = list((root / 'reports/normal.debug').glob('**/rolling/report.json'))
    if len(paths) != 1:
        raise ValueError('unique finished normal analysis required')
    retained = paths[0].read_bytes()
    selected = [root / 'captures/normal', root / 'reports/normal.debug']
    files = {}
    for source in selected:
        if source.is_symlink() or any(p.is_symlink() for p in source.rglob('*')):
            raise ValueError('refuse linked input')
        for p in source.rglob('*'):
            if p.is_file():
                files[str(p.relative_to(root))] = hashlib.sha256(p.read_bytes()).hexdigest()
    archive = root / 'retained-archives/normal-raw-and-debug.tar.gz'
    with tarfile.open(archive, 'x:gz', compresslevel=1) as target:
        for name in sorted(files):
            target.add(root / name, arcname=name, recursive=False)
    actual = {}
    with tarfile.open(archive, 'r:gz') as target:
        for member in target:
            actual[member.name] = hashlib.sha256(target.extractfile(member).read()).hexdigest()
    if actual != files:
        raise ValueError('normal archive verification failed')
    receipt = dict(file_sha256=files, archive_sha256=hashlib.sha256(archive.read_bytes()).hexdigest(),
                   every_original_file_verified=True, strong_copy_inputs_untouched=True,
                   normal_original_reports_untouched=True, retained_rolling_report_sha256=hashlib.sha256(retained).hexdigest())
    (archive.parent / 'normal-raw-and-debug-verified.json').write_text(json.dumps(receipt, indent=2)+'\n')
    for source in selected:
        shutil.rmtree(source)
    keep = root / 'reports/normal.debug/retained/rolling/report.json'
    keep.parent.mkdir(parents=True)
    keep.write_bytes(retained)
    print('normal inputs and debug retained in fully verified archive; original final reports unchanged', flush=True)


if __name__ == '__main__':
    root = Path('/home/commTeam/zjy/zjy-new-workspace/gpt2-semantic-20261102-001')
    compact(root)
