"""Frozen single-node HCCL Test comparisons and strict native-result accounting."""
from __future__ import annotations

import csv
from decimal import Decimal
import re
import statistics

OPERATORS = ('all_reduce', 'all_gather', 'reduce_scatter')
ORDERS = (('off', 'semantic', 'profile'), ('profile', 'off', 'semantic'), ('semantic', 'profile', 'off'))
SIZES = tuple(8192 * 4**i for i in range(9))


def plan():
    return dict(profile='hccl-test-overhead-v1', nodes=[0], physical_cards=[4, 5, 6, 7],
        runtime_devices=[1, 3, 5, 7], operators=list(OPERATORS), dtype='fp32', reduce_op='sum',
        bytes=list(SIZES), warmup_iters=20, measured_iters=100, result_check=True,
        mode_order_by_block=[list(o) for o in ORDERS], requested_samples=27,
        capture_flags=['--hccl=on', '--task-time=l1', '--ascendcl=on', '--ai-core=off', '--type=db'],
        log_level=2, scope='same attested low-log Host/Device; incremental trace and profiler cost, not an unmodified vendor-library comparison')


def parse_results(text, expected_sizes=SIZES):
    if re.search(r'local rank_id.*check result failed|This is an error|\[ERROR\]|hccl_opbase execute failed', text):
        raise ValueError('native rank failure must not be hidden by a successful root row')
    rows=[]
    for line in text.splitlines():
        cells=([v.strip() for v in next(csv.reader([line],delimiter='|'))] if '|' in line else line.split())
        if not cells or not cells[0].isdigit():
            continue
        if len(cells) != 4:
            raise ValueError('truncated HCCL Test numeric result')
        size=int(cells[0])
        if size not in expected_sizes:
            raise ValueError('unplanned HCCL Test message size')
        if cells[-1].lower() != 'success':
            raise ValueError('HCCL Test correctness check did not pass')
        try:
            duration, bandwidth=Decimal(cells[1]), Decimal(cells[2])
        except Exception as error:
            raise ValueError('invalid HCCL Test metrics') from error
        if not duration.is_finite() or duration<=0 or not bandwidth.is_finite() or bandwidth<=0:
            raise ValueError('nonpositive HCCL Test metrics')
        rows.append(dict(bytes=size,average_us=str(duration),algorithm_bandwidth_gbps=str(bandwidth),check='success'))
    if [r['bytes'] for r in rows] != list(expected_sizes):
        raise ValueError('all expected unique message sizes must pass in native order')
    return rows


def summarize(samples):
    expected={(block,op,mode) for block,order in enumerate(ORDERS) for op in OPERATORS for mode in order}
    seen={(r['block'],r['operator'],r['mode']) for r in samples}
    if len(samples)!=len(expected) or seen!=expected:
        raise ValueError('all 27 unique frozen samples are required; failures remain incomplete')
    results=[]
    for op in OPERATORS:
        for size in SIZES:
            pairs=[]
            for block in range(3):
                entries={s['mode']:next(r for r in s['results'] if r['bytes']==size)
                         for s in samples if s['block']==block and s['operator']==op}
                values={m:Decimal(r['average_us']) for m,r in entries.items()}
                pairs.append(dict(block=block,off_us=float(values['off']),semantic_us=float(values['semantic']),
                    profile_us=float(values['profile']),semantic_percent=float(100*(values['semantic']/values['off']-1)),
                    profile_percent=float(100*(values['profile']/values['off']-1)),
                    profile_vs_semantic_percent=float(100*(values['profile']/values['semantic']-1))))
            baseline=[p['off_us'] for p in pairs]
            results.append(dict(operator=op,bytes=size,pairs=pairs,
                median_us={m:statistics.median(p[m+'_us'] for p in pairs) for m in ORDERS[0]},
                median_paired_percent={m:statistics.median(p[m+'_percent'] for p in pairs) for m in ('semantic','profile','profile_vs_semantic')},
                baseline_max_over_min=max(baseline)/min(baseline),baseline_unstable=max(baseline)/min(baseline)>1.25))
    return dict(completed_samples=27,repetitions_per_mode=3,results=results,scope=plan()['scope'],
        caveat='Exploratory root-rank device-event averages, not per-call percentiles or end-to-end GPT. Semantic-only means the trace switch is enabled without msprof; callback emission can depend on profiler subscription, so profile-versus-semantic is not pure profiler-only cost.')
