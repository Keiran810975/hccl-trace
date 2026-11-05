#!/usr/bin/env python3
"""Decision-layer replay of sealed Top1 facts; does not reconstruct deleted graphs."""
from __future__ import annotations

import argparse
from dataclasses import asdict
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from hccl.tools.diagnosis.source_selection import SelectionOptions, select_sources, render
from test.replay_significant_regions import digest


def replay(report_path, output, host_observations_path=None):
    seal = json.loads(report_path.with_name('sealed.json').read_text())
    original_hash = digest(report_path)
    if original_hash != seal['report_sha256'] or seal.get('truth_accessed') is not False:
        raise ValueError('input must be the original pre-evaluation sealed report')
    original = json.loads(report_path.read_text())
    inputs = dict(report_sha256=original_hash, report=str(report_path.resolve()),
        truth_accessed=False, replay_scope='decision_layer_only_not_DB_or_dependency_replay',
        inherited_support_explicitly_allowed=True, options=asdict(SelectionOptions()))
    hosts = original.get('external_host_observations', [])
    if host_observations_path:
        # A public diagnosis has no private injection records; keep the full source hash.
        public = json.loads(host_observations_path.read_text())
        if public.get('schema_version') != 2 or 'external_anomaly_clues' not in public:
            raise ValueError('expected public diagnosis schema 2 for optional old Host observations')
        hosts = [h for h in public['external_anomaly_clues'] if h.get('component') == 'host_preparation']
        inputs.update(host_observations_path=str(host_observations_path.resolve()),
                      host_observations_sha256=digest(host_observations_path))
    root = Path(__file__).resolve().parents[1]
    inputs['consumer_sha256'] = {name: digest(root/name) for name in (
        'hccl/tools/diagnosis/source_selection.py', 'hccl/tools/diagnosis/source_events.py',
        'test/replay_source_selection.py')}
    report = select_sources(original, hosts, allow_inherited_support=True)
    report['inputs'] = inputs
    output.mkdir(parents=True, exist_ok=False)
    target = output/'report.json'
    target.write_text(json.dumps(report, indent=2, ensure_ascii=False)+'\n')
    (output/'report.html').write_text(render(report), encoding='utf-8')
    (output/'sealed.json').write_text(json.dumps(dict(report_sha256=digest(target),
        html_sha256=digest(output/'report.html'), truth_accessed=False, inputs=inputs), indent=2)+'\n')
    if digest(report_path) != original_hash:
        raise ValueError('original report changed during read-only replay')
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--report', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--host-observations', type=Path)
    args = parser.parse_args()
    result = replay(args.report, args.output, args.host_observations)
    print(json.dumps(dict(mechanism=result['selected_mechanism'], **result['summary'])))
