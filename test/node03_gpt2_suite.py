"""Six independent two-node GPT-2 runs and an evidence-only public DDP adapter."""
from __future__ import annotations

import argparse
from copy import deepcopy
import json
from pathlib import Path
import random
import re

if __package__:
    from .gpt2_diagnosis_suite import WORKLOAD
else:
    from gpt2_diagnosis_suite import WORKLOAD


KINDS = ("normal", "progress_delay", "copy_contention", "communication_contention", "compute_contention", "bandwidth_limit")


def build_plan(seed=20261029):
    rng = random.Random(seed)
    workload = dict(WORKLOAD, warmup=10, iters=50)
    cases = []
    for kind in KINDS:
        injection = dict(kind=kind)
        if kind != "normal":
            injection.update(target_rank=4, iteration=rng.randrange(15, 36),
                             bucket_selector_seed=rng.randrange(2**31), duration_iters=1 if kind == "progress_delay" else 3)
        if kind == "progress_delay":
            injection["delay_ms"] = 100
        elif kind == "copy_contention":
            injection.update(buffer_mib=512, copy_backend="acl_memcpy_async", background_processes=1)
        elif kind == "compute_contention":
            injection.update(matrix_size=6144, background_processes=1)
        elif kind == "communication_contention":
            injection.update(buffer_mib=256, peer_rank=0, background_jobs=1, processes_per_node=1,
                             worker_mode="cross_node_two_process_allreduce")
        elif kind == "bandwidth_limit":
            injection.update(target_rank=0, duration_iters=5, limit_mbps=20000, port_selection="verify_foreground_active_RoCE_path_first",
                             physical_node="node0", physical_device_id=9, runtime_device_id=1,
                             original_limit_required_mbps=200000, query_apply_verify_restore_required=True)
        cases.append(dict(schema_version=1, case_id="hccl-diagnose-" + kind, job_name="hccl-diagnose",
                          workload=deepcopy(workload), workload_seed=seed,
                          topology=dict(nnodes=2, ranks_per_node=4, physical_nodes=["node0", "node3"]), injection=injection))
    return dict(schema_version=1, job_name="hccl-diagnose", seed=seed, requested_runs=6, cases=cases,
                hold=dict(keep_contexts_during_diagnosis=True, busy_compute_loop=False, exclusive_device_lock=False),
                diagnosis=dict(mode="rolling", reference_window=5, read_injection_truth=False),
                network_limit_is_blocked_until_verified=True)


def validate_plan(plan):
    if plan.get("requested_runs") != 6 or [c["injection"]["kind"] for c in plan["cases"]] != list(KINDS):
        raise ValueError("exactly one clean run and one of each five anomaly types required")
    for case in plan["cases"]:
        if (case["topology"] != dict(nnodes=2, ranks_per_node=4, physical_nodes=["node0", "node3"])
                or case["workload"] != dict(WORKLOAD, warmup=10, iters=50)):
            raise ValueError("the declared eight-rank GPT-2 10+50 workload cannot be changed silently")
        injection = case["injection"]
        if injection["kind"] != "normal" and not (5 <= injection["iteration"] < injection["iteration"] + injection["duration_iters"] <= 50):
            raise ValueError("injection must fit formal iterations with five preceding references")


def adapt_ddp_public(public, destination, *, run_id, node_id, rank, device, pid, participants):
    """Convert observed hook boundaries, never DB ordinal or injection metadata."""
    public, destination = Path(public), Path(destination)
    calls = [json.loads(s) for s in (public / ("rank-{}.jsonl".format(rank))).read_text().splitlines() if s.strip()]
    boundaries = [json.loads(s) for s in (public / ("boundaries-rank-{}.jsonl".format(rank))).read_text().splitlines() if s.strip()]
    if (not calls or [c["sequence"] for c in calls] != list(range(len(calls)))
            or any(c["rank"] != rank or c["runtime_device_id"] != device or c["dtype"] != "fp32"
                   or c["reduction"] != "sum" or not re.fullmatch(r"[0-9a-f]{64}", c.get("bucket_signature", "")) for c in calls)):
        raise ValueError("complete observed DDP calls, actual device and parameter bucket signatures required")
    done = {(b["stage"], b["iteration"]): b for b in boundaries}
    locations = {(c["stage"], c["iteration"]) for c in calls}
    if len(done) != len(boundaries) or set(done) != locations or any(b.get("device_synchronized") is not True for b in boundaries):
        raise ValueError("every iteration requires its actual device completion boundary")
    if rank not in participants or participants != sorted(set(participants)):
        raise ValueError("explicit unique actual communication group membership required")
    header = dict(schema_version=1, run_id=run_id, node_id=node_id, user_rank=rank, device_id=device)
    events = [dict(header, event="runtime", pid=pid)]
    groups, seen = {}, {}
    for call in calls:
        location = call["stage"], call["iteration"]
        boundary = done[location]
        before, after, finish = call["before"]["raw_ns"], call["after"]["raw_ns"], boundary["clocks"]["raw_ns"]
        if not all(type(v) is int for v in (before, after, finish)) or not 0 <= before <= after <= finish:
            raise ValueError("Python submit return is not a device completion boundary")
        site = "ddp.gradient." + call["bucket_signature"]
        key = (*location, site)
        occurrence = seen.get(key, 0)
        seen[key] = occurrence + 1
        event = dict(header, event="call", sequence=call["sequence"], stage=call["stage"], iteration=call["iteration"],
                     group_id="gpt2-data-parallel", participants=participants, db_group_name=None,
                     call_site=site, occurrence=occurrence, operation_type="AllReduce", element_count=call["count"],
                     dtype="float32", reduction="sum", before=call["before"], after=call["after"], status="submitted")
        if "input_buffer_ptr" in call:
            if type(call["input_buffer_ptr"]) is not int or not 0 < call["input_buffer_ptr"] < 2**64:
                raise ValueError("invalid observed tensor address")
            event["input_buffer_ptr"] = call["input_buffer_ptr"]
        if "preparation_before" in call:
            start = call["preparation_before"]["raw_ns"]
            if type(start) is not int or not 0 <= start <= before:
                raise ValueError("invalid observed public preparation interval")
            event["preparation_start_raw_ns"] = start
        groups.setdefault(location, []).append(event)
    for location, records in groups.items():
        events.extend(records)
        events.append(dict(event="completion", schema_version=1, sequences=[r["sequence"] for r in records], clocks=done[location]["clocks"]))
    events.append(dict(event="capture_end", schema_version=1, pending_sequences=[]))
    destination.mkdir(parents=True, exist_ok=True)
    path = destination / ("rank-{}.jsonl".format(rank))
    with path.open("x", encoding="utf-8") as stream:
        for event in events:
            stream.write(json.dumps(event, sort_keys=True) + "\n")
    return path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    choice = parser.add_mutually_exclusive_group(required=True)
    choice.add_argument("--plan", type=Path)
    choice.add_argument("--smoke-case", type=Path)
    args = parser.parse_args()
    plan = build_plan()
    validate_plan(plan)
    if args.smoke_case:
        case = deepcopy(plan["cases"][0])
        case["case_id"] = "hccl-diagnose-gpt-smoke"
        case["workload"]["iters"] = 7
        args.smoke_case.parent.mkdir(parents=True, exist_ok=True)
        with args.smoke_case.open("x", encoding="utf-8") as stream:
            stream.write(json.dumps(case, indent=2) + "\n")
        return
    args.plan.mkdir(parents=True, exist_ok=False)
    for case in plan["cases"]:
        (args.plan / (case["case_id"] + ".json")).write_text(json.dumps(case, indent=2) + "\n")
    (args.plan / "suite.json").write_text(json.dumps(plan, indent=2) + "\n")


if __name__ == "__main__":
    main()
