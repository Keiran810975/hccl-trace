#!/usr/bin/env python3
"""Generate the requested 1+4*5 single-node cases without starting devices."""
from __future__ import annotations

import argparse
from copy import deepcopy
from decimal import Decimal
import json
import math
from pathlib import Path
import random


KINDS = ("progress_delay", "copy_contention", "communication_contention", "compute_contention")
WORKLOAD = dict(blocks=4, tokens=2048, hidden_size=4096, ffn_size=16384,
                bucket_mib=[64, 128, 256], warmup=10, iters=50)
LOCALIZATION_RULE = "primary_source_same_rank_and_time_overlap"


def coordinates(slot):
    iteration, local = divmod(slot, 12)
    block, bucket = divmod(local, 3)
    return dict(iteration=iteration, block=block, bucket=bucket)


def validate_case(case):
    if case.get("schema_version") != 1 or case.get("topology") != {"nnodes": 1, "ranks_per_node": 4}:
        raise ValueError("expected the single-node four-rank schema")
    if case["workload"] != WORKLOAD:
        raise ValueError("all 21 cases must use the identical frozen workload")
    inj = case["injection"]
    if inj["kind"] == "normal":
        if inj != {"kind": "normal"}:
            raise ValueError("normal run must not contain a fault configuration")
        return
    if inj["kind"] not in KINDS or type(inj["target_rank"]) is not int or not 0 <= inj["target_rank"] < 4:
        raise ValueError("invalid fault kind or rank")
    slot, length = inj["start_call"], inj["duration_calls"]
    if type(slot) is not int or type(length) is not int or slot < 60 or slot + length > 600:
        raise ValueError("injection needs five prior measured iterations and a complete measured window")
    if {k: inj[k] for k in ("iteration", "block", "bucket")} != coordinates(slot):
        raise ValueError("injection call index conflicts with its workload coordinates")
    if inj["kind"] == "progress_delay":
        value = Decimal(str(inj["delay_ms"]))
        if length != 1 or not Decimal(1) <= value <= 200 or value * 10 != (value * 10).to_integral_value():
            raise ValueError("delay must be 1..200ms at 0.1ms resolution, once")
        return
    if length != 36 or inj.get("background_processes") != 1:
        raise ValueError("competition uses one background process and a fixed three-iteration call window")
    if inj["kind"] == "copy_contention" and inj.get("copy_backend", "tensor") not in {"tensor", "acl_memcpy_async"}:
        raise ValueError("unknown D2D Copy backend")
    if inj["kind"] == "compute_contention":
        value = inj["matrix_size"]
        if type(value) is not int or not 2048 <= value <= 6144 or value % 256:
            raise ValueError("invalid random GEMM shape")
    else:
        value, low, high = inj["buffer_mib"], (64 if inj["kind"] == "copy_contention" else 32), (512 if inj["kind"] == "copy_contention" else 256)
        if type(value) is not int or not low <= value <= high or value % 16:
            raise ValueError("invalid random message size")
    if inj["kind"] == "communication_contention":
        if inj.get("peer_rank") not in set(range(4)) - {inj["target_rank"]}:
            raise ValueError("background communication needs two distinct devices")
        if inj.get("worker_mode") != "single_process_two_device":
            raise ValueError("two extra endpoint processes do not satisfy this suite")


def generate_cases(seed=20261024):
    source = random.Random(seed)
    normal = dict(schema_version=1, case_id="single-910c-4r-normal", purpose="formal_experiment_plan",
                  topology=dict(nnodes=1, ranks_per_node=4), workload=deepcopy(WORKLOAD),
                  workload_seed=seed, injection_seed=None, injection=dict(kind="normal"),
                  execution_status="not_run")
    cases = [normal]
    for kind in KINDS:
        for index in range(5):
            injection_seed = source.randrange(1, 2**63)
            rng = random.Random(injection_seed)
            length = 1 if kind == "progress_delay" else 36
            slot = rng.randrange(60, 600 - length + 1)
            inj = dict(kind=kind, target_rank=rng.randrange(4), start_call=slot,
                       duration_calls=length, **coordinates(slot))
            if kind == "progress_delay":
                inj.update(mode="arrival", delay_ms=round(math.exp(rng.uniform(0, math.log(200))) * 10) / 10)
            else:
                inj["background_processes"] = 1
                if kind == "compute_contention":
                    inj["matrix_size"] = rng.randrange(2048, 6145, 256)
                else:
                    inj["buffer_mib"] = (rng.randrange(64, 513, 16) if kind == "copy_contention"
                                         else rng.randrange(32, 257, 16))
                if kind == "communication_contention":
                    inj.update(peer_rank=rng.choice(sorted(set(range(4)) - {inj["target_rank"]})),
                               worker_mode="single_process_two_device")
            case = deepcopy(normal)
            case.update(case_id="single-910c-4r-{}-{:02d}".format(kind, index + 1),
                        injection_seed=injection_seed, injection=inj)
            validate_case(case)
            cases.append(case)
    return cases


def generate(output, seed=20261024):
    cases = generate_cases(seed)
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    (output / "private/cases").mkdir(parents=True)
    entries = []
    for case in cases:
        path = "private/cases/" + case["case_id"] + ".json"
        (output / path).write_text(json.dumps(case, indent=2) + "\n", encoding="utf-8")
        entries.append(dict(case_id=case["case_id"], path=path, status="not_run"))
    plan = dict(schema_version=1, status="planned_not_executed", seed=seed, run_count=21,
                cases=entries, reference_rule=dict(mode="previous_five_iteration_mean", window=5,
                slowdown_factor="1.5", mad_multiplier="3", absolute_increase_floor=None),
                validation_rule="primary source interval overlaps an actual injection window on the same rank; truth is evaluator-only",
                requirements=["Four free physical cards and verified container mapping",
                              "Authorized compatible Host/Device loading where needed, with rollback",
                              "Single-node random-window runner and single-process two-device communication worker validation",
                              "Public measured call-to-DB bindings independent of injection configuration",
                              "Actual injection-window timestamps in a verified comparable clock domain"],
                limits=["This generator does not launch, schedule, install or change verification settings.",
                        "A case file is not proof of injection, semantic collection or diagnosis success."])
    (output / "suite.json").write_text(json.dumps(plan, indent=2) + "\n", encoding="utf-8")
    return plan


def evaluate_temporal_localization(report, actual_windows):
    """Evaluator-only: windows must already be independently tied to profiler time.

    Success requires rank and time to match the SAME actual window. This does not
    prove physical causation. Truth never selects the primary source candidate.
    """
    identifier = report.get("primary_source_candidate_id")
    result = dict(evaluation_rule=LOCALIZATION_RULE, primary_source_candidate_id=identifier,
                  diagnosis_success=None, temporal_hit=None, target_rank_hit=None,
                  rank_time_hit=None, classification="not_evaluable")
    root = next((r for r in report.get("root_causes", []) if r["root_id"] == identifier), None)
    if root is None or root.get("status") != "dependency_supported_candidate" or root.get("traversal_truncated"):
        return dict(result, status="no_supported_primary_source", diagnosis_success=False,
                    classification="not_localized", reason="no complete dependency-supported primary source")
    if not actual_windows or any(w.get("source") != "captured_injection_window"
                                 or not w.get("clock_evidence") or w.get("actual_hit") is not True
                                 for w in actual_windows):
        return dict(result, status="not_evaluable",
                    reason="actual injection and comparable profiler-clock evidence are required")
    start, stop = root["observed_start_ns"], root["observed_stop_ns"]
    rank = root.get("user_rank")
    if type(rank) is not int or rank < 0:
        return dict(result, status="not_evaluable", reason="primary source needs an explicit nonnegative rank")
    if type(start) is not int or type(stop) is not int or start < 0 or stop < start:
        raise ValueError("primary source requires ordered nonnegative integer-nanosecond bounds")
    if root["component"] == "pre_task_gap":
        gap = root["gap_before_ns"]
        if type(gap) is not int or gap < 0 or gap > start:
            raise ValueError("primary source gap requires a nonnegative integer duration within its clock domain")
        start, stop = start - gap, start
    matching = [w for w in actual_windows if w["node_id"] == root["node_id"]
                and w["clock_domain"] == "profiler_node_ns"]
    if not matching:
        return dict(result, status="not_evaluable", reason="no verified local profiler clock window")
    for window in matching:
        if (any(type(window[k]) is not int for k in ("start_ns", "stop_ns"))
                or window["start_ns"] < 0 or window["stop_ns"] <= window["start_ns"]):
            raise ValueError("actual windows require increasing nonnegative integer-nanosecond bounds")
        ranks = window.get("target_ranks")
        if (not isinstance(ranks, list) or not ranks
                or any(type(value) is not int or value < 0 for value in ranks)):
            return dict(result, status="not_evaluable", reason="actual injection window needs explicit target ranks")
    hits = [w for w in matching if (w["start_ns"] <= start < w["stop_ns"] if start == stop
                                   else start < w["stop_ns"] and stop > w["start_ns"])]
    rank_hit = any(rank in w["target_ranks"] for w in matching)
    rank_time_hits = [w for w in hits if rank in w["target_ranks"]]
    classification = ("correct" if rank_time_hits else
                      "rank_time_window_mismatch" if hits and rank_hit else
                      "rank_mismatch" if hits else
                      "time_mismatch" if rank_hit else "rank_and_time_mismatch")
    return dict(result, status="evaluated_rank_time_criterion", diagnosis_success=bool(rank_time_hits),
                temporal_hit=bool(hits), target_rank_hit=rank_hit, rank_time_hit=bool(rank_time_hits),
                classification=classification, reason=classification,
                evaluated_source_interval_ns=[start, stop], evaluated_user_rank=rank,
                matching_injection_windows=[{k: w[k] for k in ("node_id", "target_ranks", "start_ns", "stop_ns")}
                                            for w in rank_time_hits],
                limitation="Same-rank time overlap is the requested metric, not proof of direct physical causation or a propagation/unrelated classification.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--seed", default=20261024, type=int)
    args = parser.parse_args()
    try:
        plan = generate(args.output, args.seed)
    except (OSError, ValueError) as error:
        parser.exit(1, str(error) + "\n")
    print("cases={} status={} output={}".format(plan["run_count"], plan["status"], args.output / "suite.json"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
