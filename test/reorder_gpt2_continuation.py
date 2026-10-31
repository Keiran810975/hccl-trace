#!/usr/bin/env python3
"""Interleave an unused continuation plan without changing any case inputs."""
from __future__ import annotations

import argparse
from copy import deepcopy
import fcntl
import hashlib
import json
from pathlib import Path

if __package__:
    from .gpt2_diagnosis_suite import validate_plan
else:
    from gpt2_diagnosis_suite import validate_plan


KINDS = ("copy_contention", "communication_contention", "compute_contention")


def reorder(root):
    root = Path(root).resolve()
    with (root / "suite.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if ((root / "state.json").exists() or any((root / "records").glob("*/result.json"))
                or any((root / "attempts").glob("*/owned-attempt.json"))):
            raise ValueError("only a never-started continuation may change its frozen order")
        directory = root / "plan"
        path = directory / "suite.json"
        if path.is_symlink():
            raise ValueError("plan cannot be a symlink")
        original = path.read_bytes()
        plan = json.loads(original)
        validate_plan(plan, directory)
        if not plan.get("execution_cohort") or plan["requested_runs"] != 31:
            raise ValueError("expected one normal control and thirty continuation cases")
        hashes, groups = {}, {kind: [] for kind in KINDS}
        for entry in plan["cases"]:
            case_path = directory / entry["path"]
            if case_path.is_symlink():
                raise ValueError("case cannot be a symlink")
            raw = case_path.read_bytes()
            hashes[entry["path"]] = hashlib.sha256(raw).hexdigest()
            kind = json.loads(raw)["injection"]["kind"]
            if kind != "normal":
                groups[kind].append(entry)
        order = [plan["cases"][0]] + [groups[kind][index] for index in range(10) for kind in KINDS]
        if plan.get("case_order") == "round_robin":
            if plan["cases"] != order:
                raise ValueError("round-robin metadata disagrees with actual order")
            return plan
        updated = deepcopy(plan)
        updated.update(cases=order, case_order="round_robin", round_robin_kinds=list(KINDS),
                       grouped_plan_sha256=hashlib.sha256(original).hexdigest())
        validate_plan(updated, directory)
        encoded = (json.dumps(updated, indent=2) + "\n").encode("utf-8")
        backup = directory / "suite.grouped-before-round-robin.json"
        with backup.open("xb") as stream:
            stream.write(original)
        temporary = directory / ".suite-round-robin.tmp"
        with temporary.open("xb") as stream:
            stream.write(encoded)
        for name, digest in hashes.items():
            if hashlib.sha256((directory / name).read_bytes()).hexdigest() != digest:
                raise ValueError("case inputs changed while reordering")
        if path.read_bytes() != original:
            raise ValueError("plan changed while reordering")
        temporary.replace(path)
        receipt = dict(case_inputs_unchanged=True, case_sha256=hashes,
                       original_plan_sha256=hashlib.sha256(original).hexdigest(),
                       reordered_plan_sha256=hashlib.sha256(encoded).hexdigest(),
                       case_order=[entry["case_id"] for entry in order])
        with (root / "round-robin-receipt.json").open("x", encoding="utf-8") as stream:
            json.dump(receipt, stream, indent=2)
            stream.write("\n")
        return updated


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    plan = reorder(parser.parse_args().root)
    print(json.dumps(dict(status="prepared", requested=plan["requested_runs"],
                          order=[entry["case_id"] for entry in plan["cases"]])))


if __name__ == "__main__":
    main()
