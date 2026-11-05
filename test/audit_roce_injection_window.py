"""Evaluation-only audit: first confirmed shaping state is not counter-sampling start."""
from __future__ import annotations

import argparse
import hashlib
import io
import json
from pathlib import Path
import sys
import tarfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from test.audit_multinode_dual import HashedReader
from test.roce_shaping_smoke import parse_shaping


def confirmed_start(commands, control, device, limit):
    queries = [r for r in commands if r.get("returncode") == 0 and r.get("command") == [
        "/usr/local/Ascend/driver/tools/hccn_tool", "-i", str(device), "-shaping", "-g"]
        and control["apply_returned_raw_ns"] <= r["started_raw_ns"] <= r["raw_ns"] <= control["started_raw_ns"]
        and parse_shaping(r["stdout"])["limit_mbps"] == limit]
    if not queries:
        raise ValueError("no successful limit readback before counter sampling")
    return min(queries, key=lambda r: r["raw_ns"])


def audit(source, original_case, alignment):
    manifest = json.loads((source / "manifest.json").read_text())
    receipt = json.loads((source / "verified.json").read_text())
    if (not receipt.get("file_hashes_verified") or receipt["manifest_sha256"] != hashlib.sha256(
            json.dumps(manifest, sort_keys=True).encode()).hexdigest()):
        raise ValueError("verified original manifest required")
    wanted = {"network/commands.jsonl", "network/snapshot.json", "gpt-output/private/network-result.json"}
    records, hashes = {}, {}
    with tarfile.open(source / "replay.tar.gz", "r|gz") as archive:
        for member in archive:
            if member.name not in wanted:
                continue
            hashed = HashedReader(archive.extractfile(member))
            with io.TextIOWrapper(io.BufferedReader(hashed), encoding="utf-8") as stream:
                records[member.name] = ([json.loads(line) for line in stream if line.strip()]
                    if member.name.endswith("jsonl") else json.load(stream))
            hashes[member.name] = hashed.digest.hexdigest()
            if hashes[member.name] != manifest["files"][member.name]["sha256"]:
                raise ValueError("original control evidence changed")
            if len(records) == len(wanted):
                break
    if set(records) != wanted:
        raise ValueError("complete original control evidence required")
    control, snapshot = records["gpt-output/private/network-result.json"], records["network/snapshot.json"]
    if not all(control.get(k) for k in ("applied_verified", "restored_verified", "foreground_path_verified")):
        raise ValueError("applied, foreground traffic and restoration must all be verified")
    query = confirmed_start(records["network/commands.jsonl"], control, snapshot["device"], snapshot["limit_mbps"])
    original, = original_case["windows"]
    model, = [m for m in alignment["models"] if (m["node_id"], m["device_id"]) == (
        original["node_id"], original_case["injection"]["runtime_device_id"])]
    offset = model["profiler_to_raw_offset_ns"]
    if (original["start_ns"] - offset != control["started_raw_ns"]
            or original["stop_ns"] - offset != control["finished_raw_ns"]):
        raise ValueError("original evaluation is not the recorded counter-sampling window")
    corrected = dict(original, start_ns=query["raw_ns"] + offset)
    return dict(schema_version=1, case_id=original_case["case_id"], evaluation_only=True,
        original_window_unchanged=original, separately_verified_window=corrected,
        first_confirmed_limit_query=query, earlier_confirmed_active_ns=original["start_ns"] - corrected["start_ns"],
        evidence_sha256=hashes, no_candidate_or_diagnosis_input=True,
        reason="The original window started after sibling/traffic-counter queries. Limit readback already confirmed the changed state earlier; keep the original stop and report this separately.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--original", type=Path, required=True)
    parser.add_argument("--alignment", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    case, = [c for c in json.loads(args.original.read_text())["cases"] if c["kind"] == "bandwidth_limit"]
    result = audit(args.source, case, json.loads(args.alignment.read_text()))
    with args.output.open("x") as target:
        json.dump(result, target, indent=2)
        target.write("\n")
    print(json.dumps(result))
