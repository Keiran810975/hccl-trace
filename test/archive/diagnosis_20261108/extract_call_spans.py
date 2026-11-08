"""Read full original comparison envelopes without reading injection truth."""
from __future__ import annotations

# Archived experiment; supported diagnosis uses hccl-diag analyze.

import argparse
import csv
import io
import json
from pathlib import Path
import sys
import tarfile

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from test.refine_multinode_sources import digest
from test.archive.diagnosis_20261108.replay_parallel_sources import HashedReader


def extract(directory, output):
    if output.exists():
        raise FileExistsError(output)
    archive = directory / "node0/replay.tar.gz"
    receipt = json.loads((directory / "node0/verified.json").read_text())
    if digest(archive) != receipt["archive_sha256"]:
        raise ValueError("archive SHA mismatch")
    manifest = json.loads((directory / "node0/manifest.json").read_text())["files"]
    wanted = [(k, v) for k, v in manifest.items() if k.endswith("/rolling/task_comparison.csv")]
    if len(wanted) != 1:
        raise ValueError("expected unique full comparison input")
    name, record = wanted[0]
    spans = {}
    with tarfile.open(archive, "r|gz") as tar:
        for member in tar:
            if not member.isfile() or manifest.get(member.name, {}).get("sha256") != record["sha256"]:
                continue
            raw = HashedReader(tar.extractfile(member))
            source = io.TextIOWrapper(io.BufferedReader(raw), encoding="utf-8-sig", newline="")
            for row in csv.DictReader(source):
                if row.get("stage") != "measured" or not row.get("operation_scope"):
                    continue
                key = row["node_id"], int(row["device_id"]), int(row["user_rank"]), row["operation_scope"]
                start, stop = int(row["observed_start_ns"]), int(row["observed_stop_ns"])
                if key in spans:
                    start, stop = min(start, spans[key][0]), max(stop, spans[key][1])
                spans[key] = start, stop
            if raw.hasher.hexdigest() != record["sha256"]:
                raise ValueError("original comparison SHA mismatch")
            break
        else:
            raise ValueError("comparison not found")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(dict(truth_accessed=False, archive_sha256=receipt["archive_sha256"],
        comparison_member=name, comparison_sha256=record["sha256"],
        spans=[dict(key=list(k), start_ns=v[0], stop_ns=v[1]) for k, v in sorted(spans.items())]), indent=2) + "\n")
    print(directory.name, len(spans), "verified call envelopes", flush=True)


if __name__ == "__main__":
    import subprocess
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--one", action="store_true")
    args = parser.parse_args()
    if args.one:
        extract(args.live, args.output)
    else:
        for directory in sorted(args.live.glob("hccl-diagnose-node03-20261106-*")):
            target = args.output / (directory.name.rsplit("-", 1)[-1] + ".json")
            if not target.exists():
                subprocess.run([sys.executable, __file__, "--one", "--live", str(directory), "--output", str(target)], check=True)
