"""Forty independent, interleaved single-node GPT interventions with sealed evaluation."""
from __future__ import annotations

import argparse
import csv
from decimal import Decimal
import fcntl
import json
from pathlib import Path
import random
import shlex
import shutil
import signal
import socket
import subprocess
import time

if __package__:
    from .run_gpt_three_anomalies import PARENT, PREVIOUS, PYTHON, capture, execute, bind_capture, digest
    from .gpt2_diagnosis_suite import WORKLOAD
    from .node03_device_guard import Guard, write
    from .run_tool_smoke import available
    from .single_node_capture import actual_windows
else:
    from run_gpt_three_anomalies import PARENT, PREVIOUS, PYTHON, capture, execute, bind_capture, digest
    from gpt2_diagnosis_suite import WORKLOAD
    from node03_device_guard import Guard, write
    from run_tool_smoke import available
    from single_node_capture import actual_windows


ROOT = PARENT / "hccl-diagnose-single-20261103-600"
KINDS = ("copy_contention", "communication_contention", "compute_contention", "progress_delay")


def plan(seed=20261103):
    rng = random.Random(seed)
    entries = []
    for repeat in range(1, 11):
        for kind in KINDS:
            rank = rng.randrange(4)
            injection = dict(kind=kind, target_rank=rank, iteration=rng.randrange(10, 40),
                bucket_selector_seed=rng.randrange(2**31), duration_iters=1)
            profile = "gpt-three-anomalies-v1"
            if kind == "copy_contention":
                profile = "gpt-finite-copy-v1"
                injection.update(finite_copy_burst=True, buffer_mib=2048, operations=4, declared_affected_ranks=[rank])
            elif kind == "communication_contention":
                peer = rng.choice(sorted(set(range(4)) - {rank}))
                injection.update(buffer_mib=1024, peer_rank=peer, background_processes=1,
                    worker_mode="single_process_two_device", declared_affected_ranks=sorted([rank, peer]))
            elif kind == "compute_contention":
                injection.update(matrix_size=8192, gemm_backend="grouped", background_processes=1,
                    declared_affected_ranks=[rank])
            else:
                injection.update(delay_ms=500, actual_injection_layer="host_before_collective_not_device_task",
                    declared_affected_ranks=[rank])
            index = len(entries) + 601
            case = dict(schema_version=1, case_id="single-gpt40-{}-{:02d}".format(kind,repeat),
                topology=dict(nnodes=1, ranks_per_node=4), workload=dict(WORKLOAD,iters=50), workload_seed=20261028,
                injection=injection, experiment_contract=dict(profile=profile, source_selection="frozen-single-dual-v1",
                    numeric_reference="previous-five-measured-mean", warmup=10, measured=50))
            entries.append(dict(root=str(PARENT / ("hccl-diagnose-single-20261103-"+str(index))), case=case))
    return dict(schema_version=1, profile="single-gpt40-v1", seed=seed, requested=40, cases=entries,
        cards=[4,5,6,7], runtime_devices=[1,3,5,7], new_baseline=False,
        detector=dict(source_factor="1.5", mad_multiplier="3", propagation_factor="1.2", selection="single-dual-top1"),
        analyzer_reads_injection_truth=False, evaluation="same predeclared Node/Rank and positive actual overlap",
        communication_both_endpoints_declared_before_execution=True, primary_target_rank_also_reported=True)


def verify_snapshot(root):
    snapshot=json.loads((root / "source-snapshot.json").read_text())
    if any(digest(root / "src" / name) != value for name,value in snapshot["files"].items()):
        raise ValueError("frozen source snapshot changed")
    return snapshot


def prepare(root):
    verify_snapshot(root)
    build=json.loads((PREVIOUS / "build-receipt.json").read_text())
    if build["status"] != "built" or any(digest(root / "src" / name) != value
            for name,value in build["verified_current_producer_files"].items()):
        raise ValueError("current producer must match the existing attested Host/Device build")
    frozen=plan()
    for entry in frozen["cases"]:
        attempt=Path(entry["root"])
        attempt.mkdir(exist_ok=False)
        shutil.copytree(root / "src",attempt / "src")
        shutil.copytree(PREVIOUS / "deploy",attempt / "deploy")
        (attempt / "input").mkdir()
        shutil.copy2(PREVIOUS / "input/aicpu_hcomm.tar.gz",attempt / "input/aicpu_hcomm.tar.gz")
        if digest(attempt / "input/aicpu_hcomm.tar.gz") != build["device_sha256"] or any(
                digest(attempt / "deploy/lib64" / name) != value for name,value in build["host_libraries"].items()):
            raise ValueError("matching Host/Device files changed")
        write(attempt / "build-receipt.json",build)
        write(attempt / "deployment.json",dict(profile="single-gpt40-v1",cards=frozen["cards"]))
        write(attempt / "input/case.json",entry["case"])
        write(attempt / "owned-attempt.json",dict(root=str(attempt),suite=str(root),case_id=entry["case"]["case_id"]))
        for name in ("logs","bin"):
            (attempt / name).mkdir()
    write(root / "plan.json",frozen)
    write(root / "prepared.json",dict(prepared=True,plan_sha256=digest(root / "plan.json"),
        cases=40,no_device_changes=True,created_unix_ns=time.time_ns()))


def windows_for(attempt, case):
    binding=json.loads((attempt / "capture/binding-evidence.json").read_text())
    found={r["rank"]:dict(offset=r["raw_to_profiler_offset_ns"]) for r in binding["ranks"]}
    if case.get("experiment_contract", {}).get("profile") == "gpt-copy-window-v1":
        if case["injection"].get("copy_backend") != "acl_memcpy_async":
            raise ValueError("sustained Copy requires actual ACL activity evidence")
        return actual_windows(attempt / "capture",case["case_id"],case,found)
    if case["injection"]["kind"] != "copy_contention":
        return actual_windows(attempt / "capture",case["case_id"],case,found)
    data=json.loads((attempt / "capture/private/injection.json").read_text())
    if (data.get("validation_passed") is not True or data.get("operations") != 4 or data.get("buffer_mib") != 2048
            or not data["started_raw_ns"] < data["finished_raw_ns"]):
        raise ValueError("finite Copy intervention did not complete its declared four operations")
    rank=case["injection"]["target_rank"]
    return [dict(node_id=case["case_id"]+"/node0",target_ranks=[rank],
        start_ns=data["started_raw_ns"]+found[rank]["offset"],stop_ns=data["finished_raw_ns"]+found[rank]["offset"],
        clock_domain="profiler_node_ns",source="validated_finite_copy_actual_activity",
        hardware_duration_claimed=False)]


def overlap(source, windows):
    return sum(max(0,min(int(source["observed_stop_ns"]),w["stop_ns"])-max(int(source["observed_start_ns"]),w["start_ns"]))
        for w in windows if source["node_id"] == w["node_id"] and int(source["user_rank"]) in w["target_ranks"])


def evaluate(attempt, case):
    directory=attempt / "diagnosis"
    seal=json.loads((directory / "sealed.json").read_text())
    if seal.get("truth_accessed") is not False or any(digest(directory / name) != value for name,value in seal["files"].items()):
        raise ValueError("all source reports must be sealed before evaluation reads truth")
    report=json.loads((directory / "report/root_causes.json").read_text())
    if report["run_id"] != case["case_id"] or report["quality"].get("pipeline_passed") is not True:
        raise ValueError("complete, correctly identified diagnosis required")
    windows=windows_for(attempt,case)
    sources=report["source_candidates"]
    candidates=[dict(candidate_id=c["id"],node_id=c["node_id"],user_rank=c["user_rank"],device_id=c["device_id"],
        stream_id=c["stream_id"],task_id=c["task_id"],iteration=c["iteration"],source_unit=c["source_unit"],
        observed_start_ns=c["observed_start_ns"],observed_stop_ns=c["observed_stop_ns"],slowdown_factor=c["slowdown_factor"],
        overlap_ns=overlap(c,windows),hit=overlap(c,windows)>0,chain_ids=c["chain_ids"]) for c in sources]
    resources=[]
    with (directory / "resource-comparisons.csv").open(newline="") as stream:
        for row in csv.DictReader(stream):
            if overlap(row,windows)>0:
                resources.append(row)
    origin=None
    with (directory / "view/dep_graph_nodes.csv").open(newline="") as stream:
        for row in csv.DictReader(stream):
            value=int(Decimal(row["task_start"])*1000)
            origin=value if origin is None else min(origin,value)
    for window in windows:
        window["html_time_origin_ns"]=origin
        window["html_relative_start_ns"]=window["start_ns"]-origin if origin is not None else None
        window["html_relative_stop_ns"]=window["stop_ns"]-origin if origin is not None else None
        window["overlapping_stream_ids"]=sorted({int(r["stream_id"]) for r in resources
            if int(r["user_rank"]) in window["target_ranks"]})
    def counts(unit):
        values=[c for c in candidates if c["source_unit"]==unit]
        hits=sum(c["hit"] for c in values)
        return dict(hits=hits,count=len(values),fraction=hits/len(values) if values else None)
    hits=sum(c["hit"] for c in candidates)
    result=dict(case_id=case["case_id"],kind=case["injection"]["kind"],injection=case["injection"],windows=windows,
        candidates=candidates,hits=hits,candidate_count=len(candidates),candidate_hit_fraction=hits/len(candidates) if candidates else None,
        any_candidate_hit=hits>0,primary_hit=bool(candidates and candidates[0]["hit"]),
        primary_target_rank_hits=sum(c["hit"] and c["user_rank"]==case["injection"]["target_rank"] for c in candidates),
        execution_tasks=counts("execution_task"),host_intervals=counts("host_preparation"),
        overlapping_resource_count=len(resources),overlapping_slow_resource_count=sum(r["duration_slow"]=="True" for r in resources),
        actual_communication_slowing_observed=any(r["duration_slow"]=="True" for r in resources),
        propagation=report["propagation"],quality=report["quality"],source_report_sha256=seal["files"]["report/root_causes.json"],
        analyzer_reads_injection_truth=False,evaluation_after_sealing=True)
    write(attempt / "evaluation.json",result)
    return result


def retain_and_cleanup(attempt, root, *, keep_raw=False):
    owned=json.loads((attempt / "owned-attempt.json").read_text())
    if owned["root"] != str(attempt.resolve()) or owned["suite"] != str(root) or not (attempt / "restoration-verified.json").exists():
        raise ValueError("cleanup requires exact ownership and restoration proof")
    evaluation=json.loads((attempt / "evaluation.json").read_text())
    if digest(attempt / "diagnosis/report/root_causes.json") != evaluation["source_report_sha256"]:
        raise ValueError("evaluated source report changed")
    retained=attempt / "retained"
    retained.mkdir(exist_ok=False)
    for name in ("public","private","workload_results","runtime"):
        shutil.copytree(attempt / "capture" / name,retained / name,ignore=shutil.ignore_patterns("background.log"))
    for name in ("binding-evidence.json","iteration-map.json","preparation-map.json","manifest.json"):
        shutil.copy2(attempt / "capture" / name,retained / name)
    evidence=[p for p in retained.rglob("*") if p.is_file()]
    evidence.extend(p for p in (attempt / "diagnosis").iterdir() if p.is_file())
    evidence.extend((attempt / "diagnosis/report").iterdir())
    evidence.extend([attempt / "evaluation.json",attempt / "restoration-verified.json"])
    hashes={str(p.relative_to(attempt)):digest(p) for p in evidence}
    write(attempt / "retention-receipt.json",dict(files=hashes,diagnosis_and_evaluation_complete=True,restoration_verified=True))
    if any(digest(attempt / name) != value for name,value in hashes.items()):
        raise ValueError("retained evidence checksum changed")
    removed=[]
    if keep_raw:
        write(attempt / "cleanup.json",dict(removed=[],only_this_attempt=True,raw_inputs_no_longer_replayable=False,
            raw_retained_for_effect_or_diagnosis_review=True))
        return
    for folder in (attempt / "capture",attempt / "diagnosis/analysis",attempt / "diagnosis/view"):
        if folder.is_symlink() or not folder.is_dir() or any(p.is_symlink() for p in folder.rglob("*")):
            raise ValueError("refuse linked or missing cleanup directory")
        size=sum(p.stat().st_size for p in folder.rglob("*") if p.is_file())
        shutil.rmtree(folder)
        removed.append(dict(path=str(folder),bytes=size))
    write(attempt / "cleanup.json",dict(removed=removed,only_this_attempt=True,raw_inputs_no_longer_replayable=True,
        retained="three native reports, all selection proposals, resource comparisons, public/truth/numerical/restore receipts"))


def summarize(root, completed):
    groups={}
    for kind in KINDS:
        values=[r for r in completed if r["kind"]==kind]
        count=sum(r["candidate_count"] for r in values); hits=sum(r["hits"] for r in values)
        groups[kind]=dict(completed=len(values),requested=10,hits=hits,candidate_count=count,
            candidate_hit_fraction=hits/count if count else None,
            cases_with_any_hit=sum(r["any_candidate_hit"] for r in values),
            primary_hit_cases=sum(r["primary_hit"] for r in values),
            zero_candidate_cases=sum(not r["candidate_count"] for r in values),
            communication_slowing_observed_cases=sum(r["actual_communication_slowing_observed"] for r in values),
            candidate_units={unit:dict(hits=sum(r[key]["hits"] for r in values),count=sum(r[key]["count"] for r in values))
                for unit,key in (("execution_task","execution_tasks"),("host_preparation","host_intervals"))})
    summary=dict(status="completed" if len(completed)==40 else "partial",completed=len(completed),requested=40,groups=groups,
        criterion="same predeclared Node/Rank plus positive actual overlap",all_cases=completed,
        communication_two_endpoints_predeclared=True,primary_target_rank_metric_separate=True,
        training_runs_are_independent_of_the_prior_development_captures=True)
    write(root / "summary.json",summary)
    with (root / "results.csv").open("w",newline="") as stream:
        fields=["case_id","kind","hits","candidate_count","candidate_hit_fraction","any_candidate_hit","primary_hit","primary_target_rank_hits"]
        writer=csv.DictWriter(stream,fields,extrasaction="ignore");writer.writeheader();writer.writerows(completed)
    return summary


def run(root):
    if (root / "state.json").exists():
        raise ValueError("never restart an existing forty-case queue")
    frozen=json.loads((root / "plan.json").read_text())
    if frozen != plan() or digest(root / "plan.json") != json.loads((root / "prepared.json").read_text())["plan_sha256"]:
        raise ValueError("frozen forty-case plan changed")
    snapshot=verify_snapshot(root)
    state=dict(status="running",requested=40,completed=0,cases=[],active=None,started_unix_ns=time.time_ns(),
        plan_sha256=digest(root / "plan.json"),source_snapshot_sha256=digest(root / "source-snapshot.json"))
    deadline=time.monotonic()+24*3600
    write(root / "state.json",state)
    try:
        for entry in frozen["cases"]:
            attempt=Path(entry["root"]);case=entry["case"];base="/workspace/"+attempt.name
            while True:
                if time.monotonic()>deadline:
                    raise TimeoutError("bounded 24-hour queue deadline reached")
                if (root / "STOP").exists():
                    raise InterruptedError("suite stop requested")
                text=subprocess.check_output(["npu-smi","info"],text=True,timeout=30)
                if available(text,[4,5,6,7]):
                    break
                state.update(status="waiting_resources",active=None,next_case=case["case_id"])
                write(root / "state.json",state)
                time.sleep(300)
            if (PARENT / ".hccl-diagnose-device-active.json").exists():
                raise ValueError("another owned device lease is active")
            if digest(attempt / "input/case.json") != digest_case(case):
                raise ValueError("case input changed")
            if any(digest(attempt / "src" / name) != value for name,value in snapshot["files"].items()):
                raise ValueError("per-case consumer snapshot changed during the frozen batch")
            state.update(status="running",active=case["case_id"],active_root=str(attempt),phase="capturing")
            write(root / "state.json",state)
            capture(attempt,case,Guard(attempt))
            state["phase"]="binding";write(root / "state.json",state)
            bind_capture(attempt,case)
            state["phase"]="diagnosing";write(root / "state.json",state)
            execute(attempt,"diagnose",shlex.join([PYTHON,base+"/src/test/diagnose_single_gpt40.py",
                "--capture",base+"/capture","--output",base+"/diagnosis"]),1800)
            state["phase"]="evaluating";write(root / "state.json",state)
            result=evaluate(attempt,case)
            retain_and_cleanup(attempt,root)
            state["cases"].append(dict(result,root=str(attempt),restoration_verified=True,cleanup_verified=True))
            state.update(completed=len(state["cases"]),active=None,phase="between_cases")
            summarize(root,state["cases"])
            write(root / "state.json",state)
    except BaseException as error:
        state.update(status="failed",error=str(error),finished_unix_ns=time.time_ns())
        write(root / "state.json",state)
        raise
    state.update(status="completed",active=None,phase="finished",finished_unix_ns=time.time_ns())
    summarize(root,state["cases"])
    write(root / "state.json",state)


def digest_case(case):
    import hashlib
    return hashlib.sha256((json.dumps(case,indent=2)+"\n").encode()).hexdigest()


if __name__ == "__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root",type=Path,required=True)
    parser.add_argument("--prepare",action="store_true")
    args=parser.parse_args()
    if args.root.resolve()!=ROOT or socket.gethostname().split(".")[0]!="liteserver-560t-0":
        raise ValueError("this queue is limited to the reviewed owned Node0 directory")
    if args.prepare:
        prepare(ROOT)
    else:
        def interrupted(signum,frame):
            raise InterruptedError("forty-case queue interrupted")
        signal.signal(signal.SIGTERM,interrupted);signal.signal(signal.SIGINT,interrupted)
        with (ROOT / "queue.lock").open("x") as lock:
            fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
            run(ROOT)
