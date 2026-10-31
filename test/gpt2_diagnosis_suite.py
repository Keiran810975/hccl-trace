"""Frozen GPT-2 case plans and evaluator-only all-candidate overlap metrics."""
from __future__ import annotations

from collections import Counter
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import random

KINDS = ("progress_delay", "copy_contention", "communication_contention", "compute_contention")
WORKLOAD = dict(model="gpt2-small", n_layer=12, n_head=12, n_embd=768, seq_length=1024,
                batch_per_rank=4, warmup=10, iters=100, bucket_cap_mb=25,
                precision="bf16_autocast_fp32_parameters", optimizer="AdamW", gradient_accumulation=1)
CANDIDATE_STATUSES = {"dependency_supported_candidate", "isolated_slow_task"}


def validate_case(case):
    expected = dict(WORKLOAD)
    continuation = case.get("execution_cohort")
    if continuation:
        if (continuation.get("physical_node") not in {"node0", "node3"} or continuation.get("measured_iterations") != 50
                or continuation.get("parent_measured_iterations") != 100):
            raise ValueError("unexpected continuation cohort")
        expected["iters"] = 50
    if case.get("workload") != expected or case.get("topology") != dict(nnodes=1, ranks_per_node=4):
        raise ValueError("unexpected GPT-2 formal workload")
    injection = case["injection"]
    if injection["kind"] != "normal":
        start, duration = injection["iteration"], injection["duration_iters"]
        if injection["kind"] not in KINDS or start < 5 or duration < 1 or start + duration > expected["iters"]:
            raise ValueError("injection must fit formal iterations with five preceding references")


def cases(seed=20261028):
    rng = random.Random(seed)
    base = dict(schema_version=1, topology=dict(nnodes=1, ranks_per_node=4), workload=deepcopy(WORKLOAD),
                workload_seed=seed, case_id="gpt2-4r-normal", injection=dict(kind="normal"))
    result = [base]
    for kind in KINDS:
        for index in range(10):
            item = deepcopy(base)
            inj = dict(kind=kind, target_rank=rng.randrange(4), iteration=rng.randrange(10, 90),
                       bucket_selector_seed=rng.randrange(2**31), duration_iters=1 if kind == "progress_delay" else 3)
            if kind == "progress_delay":
                inj["delay_ms"] = rng.randrange(10, 2001) / 10
            else:
                inj["background_processes"] = 1
                if kind == "copy_contention":
                    inj.update(buffer_mib=rng.randrange(64, 513, 16), copy_backend="acl_memcpy_async")
                elif kind == "compute_contention":
                    inj["matrix_size"] = rng.randrange(2048, 6145, 256)
                else:
                    inj.update(buffer_mib=rng.randrange(32, 257, 16),
                               peer_rank=rng.choice(sorted(set(range(4)) - {inj["target_rank"]})),
                               worker_mode="single_process_two_device")
            item.update(case_id="gpt2-4r-{}-{:02d}".format(kind, index + 1), injection=inj)
            result.append(item)
    return result


def write_plan(root, seed=20261028):
    root = Path(root)
    root.mkdir(parents=True, exist_ok=False)
    entries = []
    for case in cases(seed):
        name = case["case_id"] + ".json"
        (root / name).write_text(json.dumps(case, indent=2) + "\n", encoding="utf-8")
        entries.append(dict(case_id=case["case_id"], path=name))
    data = dict(schema_version=1, requested_runs=41, seed=seed, cases=entries,
                rule="same node/rank plus positive overlap of diagnosed source and actual injection window",
                metrics=["candidate_hits / candidate_count", "cases_with_any_hit / 10", "primary_hit"],
                cleanup="Persist compact diagnosis and evaluator receipts before deleting this attempt's raw/generated artifacts")
    (root / "suite.json").write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    return data


def write_continuation(parent, output, seed=20261029, physical_node="node3"):
    """New cohort: preserve completed Node0 cases, resample only remaining iteration positions."""
    parent, output = Path(parent), Path(output)
    state_bytes, plan_bytes = (parent / "state.json").read_bytes(), (parent / "plan/suite.json").read_bytes()
    state, plan = json.loads(state_bytes), json.loads(plan_bytes)
    completed = state.get("cases", [])
    if (state.get("status") != "stopped" or state.get("active_case") is not None
            or state.get("completed") != 11 or len(completed) != 11 or plan.get("requested_runs") != 41
            or [x["case_id"] for x in completed] != [x["case_id"] for x in plan["cases"][:11]]
            or any(x["status"] != "diagnosed" for x in completed)
            or Counter(x["injection"]["kind"] for x in completed) != {"normal": 1, "progress_delay": 10}):
        raise ValueError("expected stopped, completed normal plus ten delay cases; do not duplicate active work")
    original = []
    for entry in [plan["cases"][0]] + plan["cases"][11:]:
        if entry["path"] != entry["case_id"] + ".json":
            raise ValueError("unexpected parent case path")
        raw = (parent / "plan" / entry["path"]).read_bytes()
        case = json.loads(raw)
        validate_case(case)
        if case.get("execution_cohort") or case["case_id"] != entry["case_id"]:
            raise ValueError("parent must be the original frozen 100-iteration plan")
        original.append((case, hashlib.sha256(raw).hexdigest()))
    if Counter(x[0]["injection"]["kind"] for x in original) != dict(normal=1, copy_contention=10,
            communication_contention=10, compute_contention=10):
        raise ValueError("expected exactly thirty unexecuted competition cases")
    rng = random.Random(seed)
    if physical_node not in {"node0", "node3"}:
        raise ValueError("unsupported continuation node")
    cohort = dict(physical_node=physical_node, measured_iterations=50, parent_measured_iterations=100,
                  parent_experiment=str(parent), parent_completed_anomalies=10,
                  injection_position_seed=seed, injection_iteration_range=[10, 39],
                  allocation="node0-cards0-3" if physical_node == "node0" else "whole-host",
                  validation_mode="formal-control-first" if physical_node == "node0" else "short-preflight-first",
                  limitation="Original 100-iteration and continuation 50-iteration results are separate cohorts; shared host resources may interfere.")
    output.mkdir(parents=True, exist_ok=False)
    entries = []
    for previous, digest in original:
        case = deepcopy(previous)
        case["workload"]["iters"] = 50
        case["execution_cohort"] = dict(cohort, original_case_sha256=digest,
                                       original_iteration=previous["injection"].get("iteration"))
        if case["injection"]["kind"] != "normal":
            case["injection"]["iteration"] = rng.randrange(10, 40)
        validate_case(case)
        name = case["case_id"] + ".json"
        (output / name).write_text(json.dumps(case, indent=2) + "\n", encoding="utf-8")
        entries.append(dict(case_id=case["case_id"], path=name))
    result = dict(schema_version=1, requested_runs=31, seed=plan["seed"], cases=entries, execution_cohort=cohort,
                  parent_state_sha256=hashlib.sha256(state_bytes).hexdigest(),
                  parent_plan_sha256=hashlib.sha256(plan_bytes).hexdigest(),
                  completed_parent_case_ids=[x["case_id"] for x in completed],
                  rule=plan["rule"], metrics=plan["metrics"], cleanup=plan["cleanup"])
    (output / "suite.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    return result


def validate_plan(plan, directory):
    expected = 31 if plan.get("execution_cohort") else 41
    entries = plan.get("cases", [])
    if plan.get("requested_runs") != expected or len(entries) != expected or len({x["case_id"] for x in entries}) != expected:
        raise ValueError("unexpected GPT-2 suite size or duplicate cases")
    kinds = Counter()
    for index, entry in enumerate(entries):
        if entry["path"] != entry["case_id"] + ".json" or "/" in entry["path"]:
            raise ValueError("unexpected case path")
        case = json.loads((Path(directory) / entry["path"]).read_text())
        validate_case(case)
        cohort = case.get("execution_cohort")
        if (case["case_id"] != entry["case_id"] or bool(cohort) != bool(plan.get("execution_cohort"))
                or cohort and any(cohort.get(k) != v for k, v in plan["execution_cohort"].items())):
            raise ValueError("case and plan cohort differ")
        kind = case["injection"]["kind"]
        if (index == 0) != (kind == "normal"):
            raise ValueError("exactly one clean control must run first")
        kinds[kind] += 1
    expected_kinds = dict(normal=1, **{k: 10 for k in KINDS if expected == 41 or k != "progress_delay"})
    if kinds != expected_kinds:
        raise ValueError("unexpected anomaly groups")
    return kinds


def evaluate(report, windows, *, normal=False):
    selected = [r for r in report["root_causes"] if r["status"] in CANDIDATE_STATUSES]
    if not normal and (not windows or any(w.get("actual_hit") is not True or int(w["stop_ns"]) <= int(w["start_ns"]) for w in windows)):
        raise ValueError("successful actual injection evidence required")
    ids = [r["root_id"] for r in selected]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate source candidate IDs")
    results = []
    for root in selected:
        start, stop = int(root["observed_start_ns"]), int(root["observed_stop_ns"])
        hits = [w for w in windows if root["node_id"] == w["node_id"] and root["user_rank"] in w["target_ranks"]
                and min(stop, int(w["stop_ns"])) > max(start, int(w["start_ns"]))]
        results.append(dict(root_id=root["root_id"], graph_id=root["graph_id"], hit=bool(hits),
                            overlap_ns=max([min(stop, int(w["stop_ns"])) - max(start, int(w["start_ns"])) for w in hits] or [0])))
    count, hit_count = len(selected), sum(r["hit"] for r in results)
    return dict(rule="all_source_candidates_same_rank_and_positive_time_overlap", candidate_count=count,
                candidate_hit_count=hit_count, candidate_hit_fraction=hit_count / count if count and not normal else None,
                any_candidate_hit=bool(hit_count) if not normal else None,
                primary_hit=next((r["hit"] for r in results if r["root_id"] == report["primary_source_candidate_id"]), False) if not normal else None,
                normal_has_candidates=bool(count) if normal else None, candidates=results,
                candidate_status_counts=dict(Counter(r["status"] for r in selected)),
                diagnostic_status=report["diagnosis_status"], source_status_counts=dict(Counter(r["status"] for r in report["root_causes"])),
                limitation="Time overlap is the requested operational metric, not proof of physical causation. Empty candidate lists count as misses, not perfect precision.")


def summarize(results, plan=None):
    groups = []
    for kind in KINDS:
        requested = (sum(entry["case_id"].startswith("gpt2-4r-" + kind + "-") for entry in plan["cases"])
                     if plan else 10)
        group = [r for r in results if r["injection"]["kind"] == kind]
        valid = [r for r in group if r.get("status") == "diagnosed"]
        hits = sum(r["evaluation"]["any_candidate_hit"] for r in valid)
        candidates = sum(r["evaluation"]["candidate_count"] for r in valid)
        candidate_hits = sum(r["evaluation"]["candidate_hit_count"] for r in valid)
        groups.append(dict(kind=kind, requested=requested, completed=len(group), diagnosed=len(valid), hit_cases=hits,
                           case_hit_rate=hits / requested if requested and len(group) == requested else None,
                           candidate_count=candidates, candidate_hits=candidate_hits,
                           pooled_candidate_hit_fraction=candidate_hits / candidates if candidates else None))
    return dict(requested_runs=plan["requested_runs"] if plan else 41, completed_runs=len(results), groups=groups,
                execution_cohort=plan.get("execution_cohort") if plan else None)
