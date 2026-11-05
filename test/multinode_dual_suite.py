"""Frozen eight-rank GPT validation of the explicitly selected dual source policy."""
from __future__ import annotations

from copy import deepcopy

if __package__:
    from .node03_gpt2_suite import build_plan
else:
    from node03_gpt2_suite import build_plan


PROFILE = "multinode-dual-v1"


def plan():
    original = build_plan(seed=20261103)
    entries = {c["injection"]["kind"]: deepcopy(c) for c in original["cases"]}
    order = ("normal", "copy_contention", "communication_contention", "compute_contention", "progress_delay", "bandwidth_limit")
    for kind, case in entries.items():
        case["case_id"] = "hccl-diagnose-dual-" + kind
        case["experiment_contract"] = dict(profile=PROFILE, source_policy="dual", truth_is_evaluator_only=True,
            bounded_interference=True, activation="pre_call" if kind == "progress_delay" else "after_selected_allreduce_submit")
        inj = case["injection"]
        if kind == "normal":
            continue
        inj.update(iteration=25, bucket_selector_seed=20261102, duration_iters=5 if kind == "bandwidth_limit" else 1)
        if kind == "copy_contention":
            inj.update(buffer_mib=2048, declared_affected_ranks=[4])
        elif kind == "communication_contention":
            inj.update(buffer_mib=1024, declared_affected_ranks=[0, 4])
        elif kind == "compute_contention":
            inj.update(matrix_size=8192, declared_affected_ranks=[4])
        elif kind == "progress_delay":
            inj.update(delay_ms=500, actual_injection_layer="host_before_collective_not_device_task")
    return dict(original, profile=PROFILE, seed=20261103, cases=[entries[k] for k in order],
        keep_debug=True, retain_raw_until_verified_archive=True)


def validate_case(case):
    if case not in plan()["cases"]:
        raise ValueError("case differs from the frozen six-run multi-node dual profile")
