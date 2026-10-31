"""Read-only binding diagnostics; never selects or supplies an assignment."""
from __future__ import annotations

import argparse
import inspect
import json
from pathlib import Path

from hccl.tools.diagnosis import workload_binder as binder
from hccl.tools.diagnosis.capture_discovery import discover_capture, prepare_capture_identity


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--capture", type=Path, required=True)
    parser.add_argument("--work", type=Path, required=True)
    args = parser.parse_args()
    args.work.mkdir()
    capture = discover_capture(args.capture, args.work / "discover")
    capture = prepare_capture_identity(capture, args.work / "identity")
    original = binder._unique_assignment

    def diagnostic(candidates):
        context = inspect.currentframe().f_back.f_locals
        calls, ops, offset = context["calls"], context["ops"], context["offset"]
        missing = [sequence for sequence, choices in candidates.items() if not choices]
        report = dict(node=context["node"], rank=context["rank"], calls=len(calls),
                      candidate_union=len(set().union(*candidates.values())), missing=missing,
                      op_count=len(ops), pointer_op_count=sum("input_buffer_ptr" in op for op in ops))
        report["examples"] = []
        for sequence in missing[:5]:
            call = calls[sequence]
            rows = [dict(name=op["op_name"], pointer=op.get("input_buffer_ptr"),
                         api_start_delta_ns=op["api"]["startNs"] - call["before"]["raw_ns"] - offset,
                         completion_delta_ns=op["endNs"] - call["completion_raw_ns"] - offset)
                    for op in ops if op["count"] == call["element_count"]
                    and call["before"]["raw_ns"] + offset <= op["api"]["startNs"] <= call["completion_raw_ns"] + offset]
            report["examples"].append(dict(sequence=sequence, iteration=call["iteration"], stage=call["stage"],
                pointer=call["input_buffer_ptr"], count=call["element_count"], clock_envelope_matches=rows[:20]))
        print(json.dumps(report), flush=True)
        return original(candidates)

    binder._unique_assignment = diagnostic
    binder.bind_capture(capture, args.work / "bound", mode="rolling")


if __name__ == "__main__":
    main()
