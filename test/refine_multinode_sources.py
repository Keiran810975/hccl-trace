"""Replay source decisions from verified public facts, sealing before evaluation."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from hccl.tools.diagnosis.multinode_source_refinement import refine


def digest(path):
    result = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(8 * 1024 * 1024), b""):
            result.update(chunk)
    return result.hexdigest()


def load_segments(path):
    integer_fields = {"sender_rank", "sender_device_id", "sender_stream_id", "sender_task_id", "receiver_rank",
        "receiver_device_id", "payload_size_bytes", "submission_start_ns", "submission_stop_ns", "submission_duration_ns",
        "protocol_start_ns", "protocol_stop_ns", "protocol_duration_ns", "iteration", "reference_count", "occurrence"}
    lists = {"evidence_node_ids", "evidence_edge_ids", "issues", "reference_iterations", "reference_transfer_ids", "source_root_ids"}
    result = []
    with path.open(encoding="utf-8-sig", newline="") as source:
        for row in csv.DictReader(source):
            item = dict(row)
            for key in integer_fields & item.keys():
                item[key] = int(item[key]) if item[key] else None
            for key in lists & item.keys():
                item[key] = json.loads(item[key]) if item[key] else []
            item["is_slow"] = item.get("is_slow") == "True"
            result.append(item)
    return result


def replay(public, output):
    receipt = json.loads((public / "public-inputs.json").read_text())
    names = ("source_selection.json", "clock_alignment.json", "cross_node/segments.csv")
    hashes = {name: digest(public / name) for name in names}
    if receipt.get("truth_accessed") is not False or any(hashes[n] != receipt["files"][n]["sha256"] for n in names):
        raise ValueError("verified public facts changed")
    selection = json.loads((public / names[0]).read_text())
    alignment = json.loads((public / names[1]).read_text())
    segments = load_segments(public / names[2])
    result = refine(selection, segments, alignment)
    root = Path(__file__).resolve().parents[1]
    result["inputs"] = dict(public_facts=hashes, truth_accessed=False,
        replay_scope="source_decision_from_previously_verified_facts_not_new_DB_replay",
        original_archive_sha256=receipt["original_archive_sha256"],
        consumer_sha256={name: digest(root / name) for name in ("hccl/tools/diagnosis/multinode_source_refinement.py",
            "hccl/tools/diagnosis/source_selection.py", "test/refine_multinode_sources.py")})
    output.mkdir(parents=True, exist_ok=False)
    target = output / "selection.json"
    target.write_text(json.dumps(result, indent=2) + "\n")
    (output / "sealed.json").write_text(json.dumps(dict(selection_sha256=digest(target), truth_accessed=False,
        consumer_sha256=result["inputs"]["consumer_sha256"]), indent=2) + "\n")
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--public", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = replay(args.public, args.output)
    print(json.dumps(dict(mechanism=result["selected_mechanism"], candidates=result["source_count"],
                          primary=result["primary_proposal"], coverage=result["transfer_coverage"])))
