"""Post-hoc effect audit of immutable archives; never selects diagnostic sources."""
from __future__ import annotations

import argparse
from collections import defaultdict
import csv
from decimal import Decimal
import hashlib
import io
import json
from pathlib import Path
from statistics import median
import tarfile


KINDS = {"sdma", "reduce_inline", "rdma", "notify_wait", "notify_record"}


class HashedReader(io.RawIOBase):
    def __init__(self, source):
        self.source = source
        self.digest = hashlib.sha256()

    def readable(self):
        return True

    def readinto(self, buffer):
        data = self.source.read(len(buffer))
        self.digest.update(data)
        buffer[:len(data)] = data
        return len(data)


def region(node, rank, start, stop, windows):
    own = [w for w in windows if w["node_id"] == node and w["user_rank"] == rank]
    if not own:
        return "other_ranks" if windows else "normal_control"
    return ("inside_owner_window" if any(min(stop, w["stop_ns"]) > max(start, w["start_ns"])
                                       for w in own) else "outside_owner_window")


def distribution(values):
    values = sorted(values)
    return dict(count=len(values), mean_increase_percent=sum(values) / len(values) if values else None,
        median_increase_percent=median(values) if values else None,
        p90_increase_percent=values[min(len(values) - 1, (9 * len(values) + 9) // 10 - 1)] if values else None,
        max_increase_percent=values[-1] if values else None)


def collect(stream, windows, *, protocol=False, outgoing=None):
    groups = defaultdict(list)
    counts = defaultdict(int)
    for row in csv.DictReader(stream):
        if row.get("reference_count") != "5":
            continue
        if protocol:
            kind = "receiver_protocol_interval"
            node, rank = row["receiver_node_id"], int(row["receiver_rank"])
            start, stop = int(row["protocol_start_ns"]), int(row["protocol_stop_ns"])
            duration, reference = int(row["protocol_duration_ns"]), row.get("reference_mean_ns")
            flagged = row.get("is_slow") == "True"
        else:
            kind = row["task_kind"]
            if kind not in KINDS:
                continue
            node, rank = row["node_id"], int(row["user_rank"])
            start, stop = int(row["observed_start_ns"]), int(row["observed_stop_ns"])
            duration, reference = int(row["duration_ns"]), row.get("reference_mean_ns")
            flagged = row.get("duration_slow") == "True"
        key = region(node, rank, start, stop, windows), kind
        counts[key] += 1
        counts[key + ("flagged",)] += int(flagged)
        if reference and Decimal(reference) > 0:
            # Floating point is only for aggregate percentages, never timestamp matching.
            groups[key].append(float((Decimal(duration) / Decimal(reference) - 1) * 100))
            if protocol and outgoing is not None:
                outgoing.append(dict(sender_node_id=row["sender_node_id"], sender_rank=int(row["sender_rank"]),
                    iteration=int(row["iteration"]), increase_percent=groups[key][-1]))
    result = []
    for key in sorted(k for k in counts if len(k) == 2):
        values = sorted(groups[key])
        result.append(dict(region=key[0], measurement=key[1], comparable_count=counts[key],
            duration_flagged_count=counts[key + ("flagged",)], positive_reference_count=len(values),
            mean_increase_percent=sum(values) / len(values) if values else None,
            median_increase_percent=median(values) if values else None,
            p90_increase_percent=values[min(len(values) - 1, (9 * len(values) + 9) // 10 - 1)] if values else None,
            max_increase_percent=values[-1] if values else None))
    return result


def outgoing_effect(rows, windows, control):
    if not all(control.get(k) for k in ("applied_verified", "restored_verified", "foreground_path_verified")):
        raise ValueError("verified real RoCE apply, traffic and restoration required")
    measured = control["measurement_window"]["completed_iterations"]
    owners = {(w["node_id"], w["user_rank"]) for w in windows}
    selected = [r for r in rows if (r["sender_node_id"], r["sender_rank"]) in owners]
    inside = [r for r in selected if r["iteration"] in measured]
    if {r["iteration"] for r in inside} != set(measured):
        raise ValueError("outgoing protocol coverage missing in the verified full iterations")
    return dict(measured_iterations=measured,
        inside_verified_full_iterations=distribution([r["increase_percent"] for r in inside]),
        outside_verified_full_iterations=distribution([r["increase_percent"] for r in selected if r["iteration"] not in measured]),
        scope="Actual sender ownership and publicly bound full iterations; receiver-local protocol duration, not pure wire time or root-hit evaluation.")


def audit(directory, expected):
    source = directory / "node0"
    receipt = json.loads((source / "verified.json").read_text())
    manifest = json.loads((source / "manifest.json").read_text())
    if (not receipt["file_hashes_verified"] or hashlib.sha256(json.dumps(manifest, sort_keys=True).encode()).hexdigest()
            != receipt["manifest_sha256"]):
        raise ValueError("verified immutable manifest required")
    case_id = expected["case_id"]
    prefix = "report.debug/analysis/" + case_id + "/"
    wanted = {prefix + "rolling/task_comparison.csv": False, prefix + "cross_node/segments.csv": True}
    network = expected.get("injection", {}).get("kind") == "bandwidth_limit"
    network_file = "gpt-output/private/network-result.json"
    outgoing, control = ([] if network else None), None
    found, summaries, evaluation_seen = set(), [], False
    with tarfile.open(source / "replay.tar.gz", "r|gz") as archive:
        for member in archive:
            if member.name not in wanted and member.name != "evaluation.json" and not (network and member.name == network_file):
                continue
            fact = manifest["files"].get(member.name)
            if member.name in found or not member.isfile() or not fact or member.size != fact["size"]:
                raise ValueError("audit member differs from its verified manifest")
            hashed = HashedReader(archive.extractfile(member))
            with io.TextIOWrapper(io.BufferedReader(hashed), encoding="utf-8-sig", newline="") as stream:
                if member.name == "evaluation.json":
                    if json.load(stream) != expected:
                        raise ValueError("suite evaluation and sealed archive disagree")
                    evaluation_seen = True
                elif member.name == network_file:
                    control = json.load(stream)
                else:
                    summaries.extend(collect(stream, expected["windows"], protocol=wanted[member.name],
                        outgoing=outgoing if wanted[member.name] else None))
            if hashed.digest.hexdigest() != fact["sha256"]:
                raise ValueError("audit fact hash differs from the sealed file")
            found.add(member.name)
    if not evaluation_seen or not set(wanted) <= found:
        raise ValueError("archive lacks complete comparison facts or independent evaluation")
    if network and (network_file not in found or control is None):
        raise ValueError("verified actual network measurement window is missing")
    return dict(schema_version=1, case_id=case_id, original_final_hits=expected["candidate_hit_count"],
        original_final_candidate_count=expected["candidate_count"], windows=expected["windows"],
        statistics=summaries, outgoing_protocol_effect=outgoing_effect(outgoing, expected["windows"], control) if network else None,
        verified_fact_files=sorted(found), original_candidate_ids_unchanged=True,
        limitations=["Post-hoc annotation uses injection windows only after diagnosis; it is not source selection or proof of physical causation.",
            "RDMA rows measure submission, not hardware completion. Protocol intervals include synchronization.",
            "Protocol windows are receiver-local; a path's receiver is not necessarily its physical fault location.",
            "Other-rank statistics are not filtered by cross-node absolute time; no uncalibrated time subtraction.",
            "A Host sleep may contain no executing local device task; zero local task overlap is not proof of zero impact."])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, required=True)
    parser.add_argument("--follower-state", type=Path, required=True)
    parser.add_argument("--case-id", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    cases = json.loads(args.follower_state.read_text())["last_remote"]["cases"]
    matching = [case for case in cases if case["case_id"] == args.case_id]
    if len(matching) != 1:
        raise ValueError("a unique actual completed evaluation is required")
    result = audit(args.directory, matching[0])
    with args.output.open("x", encoding="utf-8") as stream:
        json.dump(result, stream, indent=2)
        stream.write("\n")
    print(json.dumps(result))


if __name__ == "__main__":
    main()
