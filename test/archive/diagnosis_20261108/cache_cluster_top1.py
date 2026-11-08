"""Cache verified public task/edge artifacts for unchanged dependency clustering."""
from __future__ import annotations

# Archived experiment; supported diagnosis uses hccl-diag analyze.

import argparse
import csv
import gzip
import io
import json
from pathlib import Path
import subprocess
import sys
import tarfile

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from test.refine_multinode_sources import digest
from test.archive.diagnosis_20261108.replay_parallel_sources import HashedReader, FIELDS, INTEGERS


def cache(original, work_cache, output):
    if output.exists():
        raise FileExistsError(output)
    output.mkdir(parents=True)
    work_seal = json.loads((work_cache / "sealed.json").read_text())
    if digest(work_cache / "work-facts.jsonl.gz") != work_seal["public_cache_sha256"]:
        raise ValueError("original verified work cache changed")
    with gzip.open(work_cache / "work-facts.jsonl.gz", "rt") as stream:
        tasks = [json.loads(line) for line in stream]
    for task in tasks:
        task["task_id"] = int(task["task_id"]) if task.get("task_id") is not None else None
    identifiers = {t["graph_id"] for t in tasks}
    archive = original / "node0/replay.tar.gz"
    proof = json.loads((original / "node0/verified.json").read_text())
    archive_sha = digest(archive)
    if archive_sha != proof["archive_sha256"]:
        raise ValueError("original archive changed")
    manifest = json.loads((original / "node0/manifest.json").read_text())["files"]
    suffixes = ("/rolling/task_comparison.csv", "/dep_graph_edges.csv", "/source_selection.json", "/clock_alignment.json")
    wanted = {k: v for k, v in manifest.items() if any(k.endswith(s) for s in suffixes)
              and "/selected-iteration-view/" not in k}
    if len(wanted) != 4:
        raise ValueError("expected full comparison, edges, original selection and clock alignment")
    found = set()
    with tarfile.open(archive, "r|gz") as tar:
        for member in tar:
            record = manifest.get(member.name, {})
            matches = [k for k, v in wanted.items() if k not in found and v["sha256"] == record.get("sha256")]
            if not matches or not member.isfile():
                continue
            name = matches[0]
            expected = wanted[name]
            if member.size != expected["size"]:
                raise ValueError("original artifact size mismatch")
            raw = HashedReader(tar.extractfile(member))
            stream = io.TextIOWrapper(io.BufferedReader(raw), encoding="utf-8-sig", newline="")
            if name.endswith(".json"):
                if member.size > 8 * 1024**2:
                    raise ValueError("bounded JSON artifact exceeded")
                (output / Path(name).name).write_text(stream.read())
            elif name.endswith("dep_graph_edges.csv"):
                with gzip.open(output / "supported-edges.jsonl.gz", "xt", compresslevel=3) as target:
                    for edge in csv.DictReader(stream):
                        if edge["confidence"] in {"exact", "observed"} and (
                                edge["kind"] == "direct_stream_order_observed" or "notify_sync" in edge["kind"]):
                            target.write(json.dumps({k: edge[k] for k in ("edge_id", "src", "dst", "kind", "confidence")}, separators=(",", ":")) + "\n")
            else:
                for row in csv.DictReader(stream):
                    if (row["graph_id"] in identifiers or row.get("stage") != "measured"
                            or not row.get("operation_scope")):
                        continue
                    task = {k: v for k, v in row.items() if k in FIELDS}
                    for k in (INTEGERS | {"task_id"}) & task.keys():
                        task[k] = int(task[k]) if task[k] else None
                    task["reference_iterations"] = json.loads(task.get("reference_iterations") or "[]")
                    task["reference_graph_ids"] = []
                    task["group_id"] = task.get("group_id") or None
                    task["call_site"] = task.get("call_site") or None
                    tasks.append(task)
                    identifiers.add(task["graph_id"])
            if raw.hasher.hexdigest() != expected["sha256"]:
                raise ValueError("original artifact SHA mismatch: " + name)
            found.add(name)
            print(original.name, Path(name).name, "verified", flush=True)
            if found == set(wanted):
                break
    if found != set(wanted):
        raise ValueError("missing original public artifact")
    with gzip.open(output / "tasks.jsonl.gz", "xt", compresslevel=3) as target:
        for task in tasks:
            target.write(json.dumps(task, separators=(",", ":")) + "\n")
    edges = 0
    with gzip.open(output / "supported-edges.jsonl.gz", "rt") as source, gzip.open(output / "edges.jsonl.gz", "xt", compresslevel=3) as target:
        for line in source:
            item = json.loads(line)
            if item["src"] in identifiers and item["dst"] in identifiers:
                target.write(line)
                edges += 1
    receipt = dict(truth_accessed=False, original_archive_sha256=archive_sha,
        original_artifact_sha256={k: v["sha256"] for k, v in wanted.items()},
        work_cache_sha256=work_seal["public_cache_sha256"],
        tasks=len(tasks), edges=edges,
        files={p.name: digest(p) for p in output.iterdir() if p.is_file()},
        scope="all_original_work_and_bound_measured_controls_not_new_DB_reconstruction")
    (output / "verified.json").write_text(json.dumps(receipt, indent=2) + "\n")
    print(original.name, len(tasks), "tasks", edges, "supported edges", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--original", type=Path, required=True)
    parser.add_argument("--work-cache", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--batch", action="store_true")
    args = parser.parse_args()
    if args.batch:
        for original in sorted(args.original.glob("hccl-diagnose-node03-20261106-*")):
            case = original.name.rsplit("-", 1)[-1]
            target = args.output / case
            if (target / "verified.json").is_file():
                continue
            subprocess.run([sys.executable, __file__, "--original", str(original), "--work-cache",
                str(args.work_cache / case), "--output", str(target)], check=True)
    else:
        cache(args.original, args.work_cache, args.output)
