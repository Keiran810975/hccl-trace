"""Frozen exploratory communication interventions; no outcome-driven case edits."""
from __future__ import annotations

import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path

if __package__:
    from .node03_gpt2_suite import build_plan
else:
    from node03_gpt2_suite import build_plan


PROFILE = "communication-calibration-v1"
LEVELS = {"copy_contention": (512, 1024, 2048),
          "communication_contention": (256, 512, 1024),
          "compute_contention": (6144, 8192, 12288),
          "bandwidth_limit": (20000,)}
CONTRACT = dict(profile=PROFILE, evidence_class="exploratory",
                activation="after_selected_allreduce_submit", keep_debug=True,
                no_foreground_ack_wait=True, tuning_seed=20261101,
                truth_is_evaluator_only=True)


def cases():
    originals = {c["injection"]["kind"]: c for c in build_plan()["cases"]}
    result = []
    normal = deepcopy(originals["normal"])
    normal.update(case_id="hccl-diagnose-comm-calibration-normal", experiment_contract=deepcopy(CONTRACT))
    result.append(normal)
    for kind, levels in LEVELS.items():
        for level in levels:
            case = deepcopy(originals[kind])
            injection = case["injection"]
            injection.update(iteration=20, bucket_selector_seed=20261101, duration_iters=3)
            if kind == "compute_contention":
                injection["matrix_size"] = level
            elif kind == "bandwidth_limit":
                injection.update(limit_mbps=level, duration_iters=5)
            else:
                injection["buffer_mib"] = level
            case.update(case_id="hccl-diagnose-comm-calibration-{}-{}".format(kind, level),
                        experiment_contract=deepcopy(CONTRACT))
            result.append(case)
    return result


def validate_case(case):
    if case not in cases():
        raise ValueError("case is not in the frozen exploratory communication calibration plan")


def advance(history, kind):
    """Explicit finite exploration, not retrying until the hit metric looks good."""
    if kind not in LEVELS:
        return dict(action="blocked", reason="communication-internal delay hook is not device-validated")
    attempts = [h for h in history if h["kind"] == kind]
    for attempt in attempts:
        if attempt["status"] in {"technical_failure", "restoration_failed"}:
            return dict(action="stop", reason="technical failure requires investigation; do not resubmit")
        if attempt["status"] == "communication_effect_observed":
            return dict(action="freeze_and_validate", level=attempt["level"],
                        reason="freeze the intervention before independent replication; a tuning hit is not accuracy")
    index = len(attempts)
    if index >= len(LEVELS[kind]):
        return dict(action="inconclusive", reason="all predefined strengths exhausted; preserve negative results")
    return dict(action="run", level=LEVELS[kind][index])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    entries = []
    for case in cases():
        name = case["case_id"] + ".json"
        value = (json.dumps(case, sort_keys=True, indent=2) + "\n").encode()
        (args.output / name).write_bytes(value)
        entries.append(dict(case_id=case["case_id"], path=name, sha256=hashlib.sha256(value).hexdigest()))
    plan = dict(schema_version=1, profile=PROFILE, evidence_class="exploratory", cases=entries,
                maximum_runs=len(entries),
                blocked=[dict(kind="progress_delay", reason="Python pre-call sleep excluded; native communication hook required")],
                success_rule="same-node/rank positive-overlap evaluator unchanged; also report top1 and candidate fraction",
                prior_results="101/102/103/111/112 retained as historical negative and positive evidence, not replaced",
                hidden_truth="case/private injection data excluded from diagnostic input",
                replication="freeze strength and consumer before a separate fixed-seed validation cohort")
    (args.output / "plan.json").write_text(json.dumps(plan, indent=2) + "\n")
    print(json.dumps(dict(output=str(args.output), maximum_runs=len(entries), excluded="pre-call sleep")))


if __name__ == "__main__":
    main()
