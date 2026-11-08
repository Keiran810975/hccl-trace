"""Sealed public-fact selection replay, separate from truth evaluation and DAG replay."""
from __future__ import annotations

# Archived experiment; supported diagnosis uses hccl-diag analyze.

import argparse
from collections import Counter
import csv
import gzip
import hashlib
import io
import json
from pathlib import Path
import sys
import tarfile

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from hccl.tools.diagnosis.parallel_sources import execution_calls
from hccl.tools.diagnosis.significant_regions import RegionOptions, slow
from hccl.tools.diagnosis.wait_backtrace import WORK_KINDS
from test.refine_multinode_sources import digest


INTEGERS = {"user_rank", "device_id", "stream_id", "iteration", "duration_ns", "reference_count",
            "observed_start_ns", "observed_stop_ns", "occurrence", "block", "bucket"}
LISTS = {"reference_graph_ids", "reference_iterations"}
FIELDS = INTEGERS | LISTS | {"graph_id", "node_id", "task_id", "operation_scope", "task_kind", "stage",
    "task_domain", "reference_mean_ns", "reference_mad_ns", "group_id", "call_site", "delta_ns",
    "phase", "step", "event", "algorithm", "slowdown_factor", "comparison_status", "comparison_basis"}


class HashedReader(io.RawIOBase):
    def __init__(self, source):
        self.source, self.hasher = source, hashlib.sha256()

    def readable(self):
        return True

    def readinto(self, buffer):
        data = self.source.read(len(buffer))
        self.hasher.update(data)
        buffer[:len(data)] = data
        return len(data)


def read_facts(stream, target):
    rows = []
    with gzip.open(target, "xt", encoding="utf-8") as cache:
        for raw in csv.DictReader(stream):
            if raw.get("task_domain") != "hccl_internal" or raw["task_kind"] not in WORK_KINDS:
                continue
            item = {k: v for k, v in raw.items() if k in FIELDS}
            for k in INTEGERS & item.keys():
                item[k] = int(item[k]) if item[k] else None
            for k in LISTS & item.keys():
                item[k] = json.loads(item[k]) if item[k] else []
            for k in ("group_id", "call_site"):
                item[k] = item.get(k) or None
            cache.write(json.dumps(item, separators=(",", ":")) + "\n")
            rows.append(item)
    return rows


def replay(directory, output):
    """Only original public comparisons are read; evaluation.json is never opened."""
    if output.exists():
        raise FileExistsError(output)
    output.mkdir(parents=True)
    archive = directory / "node0/replay.tar.gz"
    if archive.is_file():
        verified = json.loads((directory / "node0/verified.json").read_text())
        archive_hash = digest(archive)
        if archive_hash != verified["archive_sha256"]:
            raise ValueError("original archive SHA mismatch")
        manifest = json.loads((directory / "node0/manifest.json").read_text())["files"]
        wanted = {k: v for k, v in manifest.items() if k.endswith("/rolling/task_comparison.csv")}
        if len(wanted) != 1:
            raise ValueError("need exactly one original task comparison artifact")
        name, record = next(iter(wanted.items()))
        found = False
        with tarfile.open(archive, "r|gz") as tar:
            for member in tar:
                entry = manifest.get(member.name, {})
                if entry.get("sha256") != record["sha256"] or not member.isfile():
                    continue
                if member.size != record["size"]:
                    raise ValueError("comparison size mismatch")
                raw = HashedReader(tar.extractfile(member))
                stream = io.TextIOWrapper(io.BufferedReader(raw), encoding="utf-8-sig", newline="")
                tasks = read_facts(stream, output / "work-facts.jsonl.gz")
                if raw.hasher.hexdigest() != record["sha256"]:
                    raise ValueError("comparison member SHA mismatch")
                found = True
                break
        if not found:
            raise ValueError("comparison member unavailable, including earlier deduplicated regular members")
        inputs = dict(archive=str(archive), archive_sha256=archive_hash,
                      comparison_member=name, comparison_sha256=record["sha256"])
    else:
        receipt = json.loads((directory / "public-inputs.json").read_text())
        path = directory / "rolling/task_comparison.csv"
        sha = digest(path)
        if receipt.get("truth_accessed") is not False or sha != receipt["files"]["rolling/task_comparison.csv"]["sha256"]:
            raise ValueError("cached public comparison SHA mismatch")
        with path.open(encoding="utf-8-sig", newline="") as stream:
            tasks = read_facts(stream, output / "work-facts.jsonl.gz")
        inputs = dict(comparison=str(path), comparison_sha256=sha,
                      archive_sha256=receipt["original_archive_sha256"])
    regions, admission = execution_calls(tasks)
    identifiers = {k for r in regions for k in r["preliminary_graph_ids"]}
    candidates = [t for t in tasks if t["graph_id"] in identifiers]
    candidates.sort(key=lambda t: (t["iteration"], t["node_id"], t["user_rank"], t["observed_start_ns"], t["graph_id"]))
    options = RegionOptions()
    isolated = [t for t in tasks if slow(t, options.source_factor, options)]
    result = dict(policy="multinode_parallel_v1", candidate_relationship="parallel", truth_accessed=False,
        scope="public_task_selection_only_no_new_DB_parse_or_propagation_validation",
        inputs=inputs, candidates=candidates, call_admission=admission,
        summary=dict(candidate_count=len(candidates), admitted_call_count=len(regions),
            preliminary_slow_task_count=len(isolated),
            admitted_epochs=sorted({t["iteration"] for t in candidates}),
            admission_reason_counts=dict(Counter(d["reason"] for d in admission))),
        exclusions=[], limits=["Known-data development, not held-out accuracy or a three-report DAG replay.",
            "No case is excluded using injection position, competing jitter or a missed diagnosis."])
    target = output / "selection.json"
    target.write_text(json.dumps(result, indent=2) + "\n")
    root = Path(__file__).resolve().parents[3]
    consumers = ("hccl/tools/diagnosis/parallel_sources.py", "hccl/tools/diagnosis/significant_regions.py",
                 "hccl/tools/diagnosis/source_events.py", "test/archive/diagnosis_20261108/replay_parallel_sources.py")
    (output / "sealed.json").write_text(json.dumps(dict(truth_accessed=False, selection_sha256=digest(target),
        public_cache_sha256=digest(output / "work-facts.jsonl.gz"),
        consumer_sha256={name: digest(root / name) for name in consumers}), indent=2) + "\n")
    return result


def replay_completed(live, output):
    import subprocess
    for directory in sorted(live.glob("hccl-diagnose-node03-20261106-*")):
        case = directory.name.rsplit("-", 1)[-1]
        target = output / case
        if (target / "sealed.json").is_file():
            print(case, "already sealed; not changed", flush=True)
            continue
        print(case, "reading verified original public facts", flush=True)
        subprocess.run([sys.executable, __file__, "--input", str(directory), "--output", str(target)], check=True)


def replay_cached(source, output, spans_path=None):
    import shutil
    seal = json.loads((source / "sealed.json").read_text())
    if digest(source / "work-facts.jsonl.gz") != seal["public_cache_sha256"]:
        raise ValueError("verified public-fact cache changed")
    if digest(source / "selection.json") != seal["selection_sha256"]:
        raise ValueError("prior selection changed")
    output.mkdir(parents=True, exist_ok=False)
    with gzip.open(source / "work-facts.jsonl.gz", "rt") as stream:
        tasks = [json.loads(line) for line in stream]
    regions, decisions = execution_calls(tasks)
    span_admission = []
    if spans_path is not None:
        from hccl.tools.diagnosis.parallel_sources import qualify_call_spans
        payload = json.loads(spans_path.read_text())
        old = json.loads((source / "selection.json").read_text())
        if payload["truth_accessed"] is not False or payload["archive_sha256"] != old["inputs"]["archive_sha256"]:
            raise ValueError("call envelopes and work facts belong to different captures")
        spans = {tuple(r["key"]): (r["start_ns"], r["stop_ns"]) for r in payload["spans"]}
        regions, span_admission = qualify_call_spans(regions, spans)
        shutil.copy2(spans_path, output / "call-spans.json")
    wanted = {key for r in regions for key in r["preliminary_graph_ids"]}
    selected = sorted((t for t in tasks if t["graph_id"] in wanted),
                      key=lambda t: (t["iteration"], t["node_id"], t["user_rank"], t["observed_start_ns"], t["graph_id"]))
    old = json.loads((source / "selection.json").read_text())
    result = dict(old, candidates=selected, call_admission=decisions,
                  call_span_admission=span_admission,
                  inputs=dict(old["inputs"], verified_cache=str(source.resolve()),
                              verified_cache_sha256=seal["public_cache_sha256"]),
                  summary=dict(candidate_count=len(selected), admitted_unit_count=len(regions),
                      admitted_call_count=len({(r["node_id"], r["device_id"], r["operation_scope"]) for r in regions}),
                      admitted_epochs=sorted({t["iteration"] for t in selected}),
                      admission_reason_counts=dict(Counter(d["reason"] for d in decisions))))
    shutil.copy2(source / "work-facts.jsonl.gz", output / "work-facts.jsonl.gz")
    target = output / "selection.json"
    target.write_text(json.dumps(result, indent=2) + "\n")
    root = Path(__file__).resolve().parents[3]
    (output / "sealed.json").write_text(json.dumps(dict(truth_accessed=False, selection_sha256=digest(target),
        public_cache_sha256=seal["public_cache_sha256"],
        call_spans_sha256=digest(output / "call-spans.json") if spans_path is not None else None,
        consumer_sha256={name: digest(root / name) for name in seal["consumer_sha256"]}), indent=2) + "\n")
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--completed", action="store_true", help="replay every completed archived case, without exclusions")
    parser.add_argument("--cached", action="store_true", help="use only a previously SHA-verified public work-fact cache")
    parser.add_argument("--call-spans", type=Path, help="verified full-comparison call envelopes, or their directory in batch mode")
    args = parser.parse_args()
    if args.cached:
        import subprocess
        if args.completed:
            for directory in sorted(args.input.iterdir()):
                if (directory / "sealed.json").is_file():
                    if (args.output / directory.name / "sealed.json").is_file():
                        print(directory.name, "already sealed; unchanged", flush=True)
                        continue
                    print(directory.name, flush=True)
                    command = [sys.executable, __file__, "--cached", "--input", str(directory),
                               "--output", str(args.output / directory.name)]
                    if args.call_spans is not None:
                        command.extend(["--call-spans", str(args.call_spans / (directory.name + ".json"))])
                    subprocess.run(command, check=True)
        else:
            print(json.dumps(replay_cached(args.input, args.output, args.call_spans)["summary"]))
    elif args.completed:
        replay_completed(args.input, args.output)
    else:
        result = replay(args.input, args.output)
        print(json.dumps(result["summary"]))
