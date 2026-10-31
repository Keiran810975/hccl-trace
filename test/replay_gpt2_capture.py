#!/usr/bin/env python3
"""Replay a retained GPT-2 capture into a fresh directory, without NPU work."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "hccl/tools"))
from diagnosis.export_msprof_identity import export_identity
from diagnosis.run_diagnosis import run_pipeline
from diagnosis.rolling_diagnosis import RollingOptions

if __package__:
    from .run_gpt2_case import gate_failure_evidence, retain, write_json
else:
    from run_gpt2_case import gate_failure_evidence, retain, write_json


def replay(attempt: Path, output: Path):
    output.mkdir(parents=True, exist_ok=False)
    bindings = json.loads((attempt / "binding-evidence.json").read_text())
    manifest = json.loads((attempt / "manifest.json").read_text())
    if len(manifest["nodes"]) != 1 or len(bindings["ranks"]) != 4:
        raise ValueError("expected one-node four-rank retained GPT-2 capture")
    selected = output / "foreground-dbs"
    identities, found = [], {}
    for entry in bindings["ranks"]:
        source = Path(entry["source_db"])
        rank = int(entry["rank"])
        evidence = export_identity(source, source.parent, selected / ("msprof_rank-{}-".format(rank) + source.name))
        identities.append(dict(rank=rank, **evidence))
        found[rank] = dict(offset=entry["raw_to_profiler_offset_ns"])
        print("IDENTITY_EXPORTED rank={} tasks={}".format(rank, evidence["correlated_tasks"]), flush=True)
    manifest["nodes"][0]["msprof_db_dir"] = str(selected)
    write_json(output / "manifest.json", manifest)
    write_json(output / "identity-export.json", identities)
    diagnosis, passed = run_pipeline(output / "manifest.json", output / "diagnosis",
        iteration_map=attempt / "iteration-map.json", preparation_map=attempt / "preparation-map.json",
        html_views=(), rolling_options=RollingOptions(max_figures=0), include_critical_path=False)
    if not passed:
        write_json(output / "gate-failure.json", gate_failure_evidence(diagnosis))
        raise ValueError("repaired capture failed the unchanged strict diagnosis gates")
    numerics = [json.loads(p.read_text()) for p in sorted((attempt / "workload_results").glob("rank-*.json"))]
    case = json.loads((attempt / "private/case.json").read_text())
    result = retain(attempt, output / "records", case, diagnosis, found, numerics)
    write_json(output / "result.json", dict(status="passed", fresh_npu_run=False,
        original_attempt=str(attempt), diagnosis=str(diagnosis), evaluation=result["evaluation"],
        raw_capture_preserved=True, gates_relaxed=False))
    return diagnosis


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--attempt", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        print(replay(args.attempt.resolve(), args.output.resolve()), flush=True)
    except BaseException as error:
        if args.output.is_dir():
            write_json(args.output / "failure.json", dict(error=str(error), type=type(error).__name__))
        raise


if __name__ == "__main__":
    main()
