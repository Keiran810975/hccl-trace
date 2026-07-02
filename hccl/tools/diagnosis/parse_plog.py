#!/usr/bin/env python3
"""Parse HCCL step semantic records from plog text."""

from __future__ import annotations

import argparse
import os
import re
import shlex
import sys
from typing import Dict, Iterable, Iterator, List

if __package__ in (None, ""):
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from diagnosis.schema import SCHEMA_VERSION, SEMANTIC_FIELDS, TRACE_TAG, SemanticRecord, parse_int, write_csv
else:
    from .schema import SCHEMA_VERSION, SEMANTIC_FIELDS, TRACE_TAG, SemanticRecord, parse_int, write_csv


KEY_VALUE_RE = re.compile(r"([A-Za-z_][A-Za-z0-9_]*)=([^,\s]+)")
BRACKET_VALUE_RE = re.compile(r"([A-Za-z_][A-Za-z0-9_]*)\[([^\]]*)\]")
PID_TS_RE = re.compile(
    r"HCCL\((?P<pid>\d+),(?P<process>[^)]*)\):"
    r"(?P<log_ts>\d{4}-\d{2}-\d{2}-\d{2}:\d{2}:\d{2}\.\d+\.\d+)"
)


def parse_plog_lines(lines: Iterable[str]) -> Iterator[SemanticRecord]:
    pending_header = None
    for line in lines:
        if TRACE_TAG not in line:
            continue
        after_tag = line.split(TRACE_TAG, 1)[1].strip()
        bracket_fields = _parse_bracket_values(after_tag)
        if bracket_fields:
            yield semantic_from_mapping(_with_line_metadata(bracket_fields, line))
            pending_header = None
            continue
        if "=" in after_tag:
            yield semantic_from_mapping(_with_line_metadata(_parse_key_values(after_tag), line))
            pending_header = None
            continue
        pending_header = after_tag.split()
        if len(pending_header) >= 4:
            continue

        # Legacy records can be split across the tag line plus one value line.
        pending_header = pending_header or []

    if pending_header:
        yield semantic_from_legacy_tokens(pending_header)


def parse_legacy_block(lines: Iterable[str]) -> Iterator[SemanticRecord]:
    iterator = iter(lines)
    for line in iterator:
        if TRACE_TAG not in line:
            continue
        after_tag = line.split(TRACE_TAG, 1)[1].strip()
        bracket_fields = _parse_bracket_values(after_tag)
        if bracket_fields:
            yield semantic_from_mapping(_with_line_metadata(bracket_fields, line))
            continue
        if "=" in after_tag:
            yield semantic_from_mapping(_with_line_metadata(_parse_key_values(after_tag), line))
            continue
        header = after_tag.split()
        try:
            values = next(iterator).strip().split()
        except StopIteration:
            values = []
        yield semantic_from_legacy_tokens(header + values)


def semantic_from_mapping(data: Dict[str, str]) -> SemanticRecord:
    return SemanticRecord(
        schema_version=parse_int(data.get("schema_version"), SCHEMA_VERSION),
        op_id=data.get("op_id", ""),
        op_type=data.get("op_type", data.get("operation", "")),
        algorithm=data.get("algorithm", ""),
        phase=data.get("phase", ""),
        step=parse_int(data.get("step")),
        slice=parse_int(data.get("slice")),
        user_rank=parse_int(data.get("user_rank", data.get("rank"))),
        comm_rank=parse_int(data.get("comm_rank", data.get("rank"))),
        rank_size=parse_int(data.get("rank_size", data.get("ranksize"))),
        peer_rank=parse_int(data.get("peer_rank", data.get("peer"))),
        event=data.get("event", ""),
        semantic=data.get("semantic", ""),
        stream_id=parse_int(data.get("stream_id")),
        task_id=parse_int(data.get("task_id")),
        semantic_seq=parse_int(data.get("semantic_seq", data.get("task_seq", data.get("submit_seq")))),
        task_kind=data.get("task_kind", data.get("task_type", "")),
        source=data.get("source", ""),
        device_id=parse_int(data.get("device_id", data.get("device"))),
        node_id=data.get("node_id", ""),
        pid=parse_int(data.get("pid")),
    )


def semantic_from_legacy_tokens(tokens: List[str]) -> SemanticRecord:
    values = list(tokens)
    if len(values) < 11:
        values.extend([""] * (11 - len(values)))
    stream_id, task_id, task_kind, event, phase, step, rank, rank_size, slice_id, semantic, peer = values[:11]
    return SemanticRecord(
        stream_id=parse_int(stream_id),
        task_id=parse_int(task_id),
        task_kind=task_kind,
        event=event,
        phase=phase,
        step=parse_int(step),
        user_rank=parse_int(rank),
        comm_rank=parse_int(rank),
        rank_size=parse_int(rank_size),
        slice=parse_int(slice_id),
        semantic=semantic,
        peer_rank=parse_int(peer),
    )


def _parse_key_values(text: str) -> Dict[str, str]:
    result = {}
    for match in KEY_VALUE_RE.finditer(text):
        result[match.group(1)] = match.group(2).strip("\"'")
    if result:
        return result
    for token in shlex.split(text.replace(",", " ")):
        if "=" not in token:
            continue
        key, value = token.split("=", 1)
        result[key] = value.strip("\"'")
    return result


def _parse_bracket_values(text: str) -> Dict[str, str]:
    return {match.group(1): match.group(2) for match in BRACKET_VALUE_RE.finditer(text)}


def _with_line_metadata(data: Dict[str, str], line: str) -> Dict[str, str]:
    if "pid" in data:
        return data
    match = PID_TS_RE.search(line)
    if not match:
        return data
    enriched = dict(data)
    enriched["pid"] = match.group("pid")
    return enriched


def parse_file(path: str) -> List[SemanticRecord]:
    with open(path, "r", encoding="utf-8", errors="replace") as source:
        return list(parse_legacy_block(source))


def main() -> int:
    parser = argparse.ArgumentParser(description="Parse [HcclTaskSemantic] plog records into CSV.")
    parser.add_argument("plog")
    parser.add_argument("-o", "--output", required=True)
    args = parser.parse_args()
    records = parse_file(args.plog)
    write_csv(args.output, list(SEMANTIC_FIELDS), (record.to_row() for record in records))
    print("semantic_records={}".format(len(records)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
