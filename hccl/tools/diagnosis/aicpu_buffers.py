"""Observed buffer addresses anchored to the exact reported runtime task IDs."""
from __future__ import annotations

import re
from collections import defaultdict

from .merge_timeline import _semantic_log_paths


THREAD = re.compile(r"HCCL\((\d+),[^)]*\):.*?\[[^\]]+\.cc:\d+\]\s*\[(\d+)\]")
ANCHOR = re.compile(r"\[ReportMainStreamTask\] aicpuKernelStreamId = (\d+), aicpuKernelTaskId = (\d+)")
MAIN = re.compile(r"\[ReportMainStreamTask\] streamId:(\d+), taskId:(\d+), type:(\d+)")
OP = re.compile(r"\[OrchestrateHcclOp\] opUnfoldIdx_\[\d+\] opType\[(\d+)\] curRank\[(\d+)\] rankSize\[(\d+)\]")
BUFFER = re.compile(r"\[OrchestrateHcclOp\] inputPtr\[(0x[0-9a-fA-F]+)\] inputSize\[(\d+)\] outputPtr\[(0x[0-9a-fA-F]+)\] outputSize\[(\d+)\]")
ROTATION = re.compile(r"device-(\d+)_(\d{17})\.log")


def parse_buffers(lines, *, active=None, source=None):
    active = {} if active is None else active
    for number, line in enumerate(lines, 1):
        if not any(t in line for t in ("[ReportMainStreamTask]", "[OrchestrateHcclOp]")):
            continue
        thread = THREAD.search(line)
        if thread is None:
            continue
        key = tuple(map(int, thread.groups()))
        anchor, main, op, buffer = ANCHOR.search(line), MAIN.search(line), OP.search(line), BUFFER.search(line)
        if anchor:
            active[key] = dict(kernel=tuple(map(int, anchor.groups())))
        elif main:
            if key in active and int(main[3]) == 0:
                active[key]["anchor"] = int(main[1]), int(main[2])
                active[key]["anchor_evidence"] = str(source) + ":" + str(number) if source else ""
        elif op:
            if key in active:
                active[key]["op"] = tuple(map(int, op.groups()))
        elif buffer:
            context = active.pop(key, {})
            if "op" not in context or "anchor" not in context:
                continue
            kind, rank, ranks = context.pop("op")
            if kind != 2:  # HCCL_CMD_ALLREDUCE, independently checked against the DB type and byte count.
                continue
            pointer, size, output, output_size = buffer.groups()
            yield dict(user_rank=rank, rank_size=ranks, anchor_stream_id=context["anchor"][0],
                       anchor_task_id=context["anchor"][1], input_buffer_ptr=int(pointer, 16),
                       input_buffer_bytes=int(size), output_buffer_ptr=int(output, 16),
                       output_buffer_bytes=int(output_size), line=number,
                       anchor_evidence=context.get("anchor_evidence", ""))


def read_buffers(directory):
    facts = {}
    chains = defaultdict(list)
    for path in _semantic_log_paths(directory):
        rotation = ROTATION.fullmatch(path.name)
        # Native rotation belongs to one physical log directory and host process.
        # Never carry a device-local scheduler PID across devices or unrelated files.
        key = (path.parent, rotation[1]) if rotation else (path, None)
        chains[key].append(path)
    for paths in chains.values():
        active = {}
        for path in sorted(paths, key=lambda p: p.name):
            with path.open(encoding="utf-8", errors="replace") as stream:
                for fact in parse_buffers(stream, active=active, source=path):
                    key = fact["user_rank"], fact["rank_size"], fact["anchor_stream_id"], fact["anchor_task_id"]
                    value = {k: v for k, v in fact.items() if k not in {"line", "anchor_evidence"}}
                    if key in facts and facts[key][0] != value:
                        raise ValueError("ambiguous reused AI_CPU buffer anchor; no offset/time fallback")
                    facts[key] = value, str(path) + ":" + str(fact["line"]) + "; exact main-stream anchor " + fact["anchor_evidence"]
    return facts
