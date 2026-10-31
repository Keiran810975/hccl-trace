"""Opt-in complete group controls bracketed by independently bound SDK calls."""
from __future__ import annotations

from collections import defaultdict

from .dependency_model import stable_id


def bind_auxiliary(bound, inventory, allowed):
    if allowed != ["Broadcast"]:
        raise ValueError("only the explicit Broadcast auxiliary policy is currently supported")
    groups = defaultdict(lambda: defaultdict(list))
    used = defaultdict(set)
    for key, entries in bound.items():
        for entry in entries:
            endpoint = entry["node_id"], entry["device_id"]
            groups[key[0]][entry["user_rank"]].append((key, entry))
            used[endpoint].add(entry["op"]["connectionId"])
    operations, evidence = [], []
    for group_id, ranks in groups.items():
        ordered = {rank: sorted(items, key=lambda item: item[1]["call"]["sequence"]) for rank, items in ranks.items()}
        first = next(iter(ordered.values()))
        if any([key for key, _ in items] != [key for key, _ in first] for items in ordered.values()):
            raise ValueError("auxiliary controls require complete identical public group order")
        for index in range(len(first) - 1):
            per_rank = {}
            for rank, items in ordered.items():
                left, right = items[index][1], items[index + 1][1]
                endpoint = left["node_id"], left["device_id"]
                if left["op"]["group_name"] != right["op"]["group_name"]:
                    raise ValueError("auxiliary bracket changes its actual communicator")
                choices = {}
                for op in inventory[endpoint[0]][endpoint[1]]["operations"]:
                    if (op["connectionId"] in used[endpoint] or op["kind"] != "broadcast"
                            or op["group_name"] != left["op"]["group_name"]):
                        continue
                    if not left["op"]["api"]["endNs"] <= op["api"]["startNs"] <= op["api"]["endNs"] <= right["op"]["api"]["startNs"]:
                        continue
                    shape = op["kind"], op["dataType"], op["count"]
                    if shape in choices:
                        raise ValueError("duplicate-shape auxiliary controls in one bracket are ambiguous")
                    choices[shape] = dict(node_id=endpoint[0], device_id=endpoint[1], op=op)
                per_rank[rank] = choices
            signatures = set(next(iter(per_rank.values())))
            if any(set(choices) != signatures for choices in per_rank.values()):
                raise ValueError("missing or inconsistent auxiliary group participant")
            for shape in sorted(signatures):
                entries = [per_rank[rank][shape] for rank in sorted(per_rank)]
                identity = stable_id("aux", (first[index][0], first[index + 1][0], shape))
                proof = ("Capture-owner Broadcast policy; previously SDK/API-bound actual communicator and complete membership; "
                         "one unique type/dtype/count in the same two globally identified public-call brackets on every member; "
                         "each auxiliary uses its own exact named API connection; no name-only, task-offset, nearest-time or ordinal fallback")
                operations.append(dict(operation_id=identity, participants=sorted(per_rank), evidence=proof,
                    members=[dict(node_id=e["node_id"], device_id=e["device_id"], group_name=e["op"]["group_name"],
                                  op_name=e["op"]["op_name"]) for e in entries]))
                evidence.append(dict(operation_id=identity, participants=sorted(per_rank), group_id=group_id,
                                     operation_type=shape[0], dtype=shape[1], element_count=shape[2],
                                     auxiliary_control=True, public_bracket=[first[index][0], first[index + 1][0]],
                                     evidence=proof, reduction_verified_in_database=False))
                for entry in entries:
                    used[(entry["node_id"], entry["device_id"])].add(entry["op"]["connectionId"])
    return operations, evidence
