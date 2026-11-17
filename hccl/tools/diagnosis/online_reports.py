"""Produce one complete captured-iteration report per group of slow alerts."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import signal
import time

from .capture_discovery import read_json
from .online_followup import CALL_TOKEN, SLOW, operation_token
from .workload_binder import _read_observations


MAX_PENDING = 32
POLL_SECONDS = .25


def _complete_lines(file):
    while True:
        start = file.tell()
        line = file.readline()
        if not line.endswith(b"\n"):
            file.seek(start)
            return
        if line.strip():
            yield json.loads(line)


def _json_if_ready(path):
    try:
        return read_json(path)
    except (FileNotFoundError, json.JSONDecodeError):
        return None


def ready_source(capture, snapshots, job_id, epoch):
    if snapshots is not None:
        segment = snapshots / f"iter-{epoch}"
        marker = _json_if_ready(segment / "online-ready.json")
        if marker is not None:
            if marker != dict(schema_version=1, run_id=job_id, iteration=epoch, complete=True):
                raise ValueError("sealed iteration marker disagrees with job or iteration")
            return segment, "sealed_iteration"
    nodes = capture / "nodes"
    entries = sorted(p for p in nodes.iterdir() if p.is_dir()) if nodes.is_dir() else []
    states = [_json_if_ready(node / "collection.json") for node in entries]
    if (states and all(st is not None and st.get("run_id") == job_id and
                      st.get("status") == "captured_not_yet_diagnosed" for st in states)):
        return capture, "final_capture"
    assembly = _json_if_ready(capture / "assembly.json")
    if assembly and assembly.get("status") == "assembled" and assembly.get("run_id") == job_id:
        return capture, "final_capture"
    return None, None


def closed_tokens(capture, job_id, epoch, expected_ranks):
    manifest = _json_if_ready(capture / "capture.json") or {}
    declarations = {n["node_id"]: n for n in manifest.get("nodes", ())}
    seen, sizes, has_marker, members = set(), set(), set(), {}
    for node in sorted((capture/"nodes").iterdir()):
        if not node.is_dir():
            continue
        directory = capture / declarations.get(node.name, {}).get("calls_dir", str(node.relative_to(capture)/"calls"))
        for path in sorted(directory.glob("rank-*.jsonl")):
            runtime, calls, markers = _read_observations(path)
            rank = runtime["user_rank"]
            if runtime["run_id"] != job_id or runtime["node_id"] != node.name or rank in seen:
                raise ValueError("sealed SDK logs contain duplicate or foreign Rank identities")
            seen.add(rank)
            if "world_size" in runtime:
                size = runtime["world_size"]
                if type(size) is not int or size <= rank:
                    raise ValueError("invalid expected world size in SDK log")
                sizes.add(size)
            if any(marker["stage"] == "measured" and marker["iteration"] == epoch for marker in markers):
                has_marker.add(rank)
            for call in calls:
                if (call["stage"], call["iteration"]) != ("measured", epoch):
                    continue
                token = operation_token(call, CALL_TOKEN)
                participants = frozenset(call["participants"])
                expected, actual = members.setdefault(token, (participants, set()))
                if rank in actual or rank not in expected or participants != expected:
                    raise ValueError("iteration calls disagree on collective participants")
                actual.add(rank)
    if len(sizes) > 1 or (expected_ranks is not None and sizes and sizes != {expected_ranks}):
        raise ValueError("collector and SDK world sizes disagree")
    expected_count = expected_ranks if expected_ranks is not None else next(iter(sizes), None)
    if expected_count is None:
        raise ValueError("whole-iteration coverage needs SDK WORLD_SIZE or collector --expected-ranks")
    if seen != set(range(expected_count)):
        return None
    if has_marker != seen or not members or any(expected != actual for expected, actual in members.values()):
        raise ValueError("sealed iteration is missing finished Rank markers or complete collective calls")
    return set(members)


def measurement_states(path, job_id, epoch, wanted):
    states = {}
    with path.open("rb") as stream:
        for row in _complete_lines(stream):
            if (row.get("job_id"), row.get("stage"), row.get("iteration")) == (job_id, "measured", epoch):
                token = operation_token(row)
                if token in wanted:
                    states[token] = row["status"]
    return states


def _diagnose(source, output, *, epoch, alerts):
    from .cli import DiagnosisError, analyze_capture

    try:
        return analyze_capture(source, output, mode="rolling", target_iteration=epoch,
                               online_records=alerts, allow_uncalibrated_clock=True)
    except DiagnosisError as error:
        raise ValueError(str(error)) from error


def run_reports(directory, job_id, capture, snapshots, stop, expected_ranks, *, drain_seconds=120,
                poll_seconds=POLL_SECONDS, parent_pid=None):
    pending, done, tokens_cache = {}, set(), {}
    last_state = {}

    with (directory/"events.jsonl").open("rb") as events, (directory/"diagnostics.jsonl").open(
            "x", encoding="utf-8", buffering=1) as log:
        def status(epoch, state, **details):
            if last_state.get(epoch) == state:
                return
            last_state[epoch] = state
            log.write(json.dumps(dict(run_id=job_id, iteration=epoch, status=state, **details),
                                 ensure_ascii=False) + "\n")

        def finish(epoch, name, **details):
            status(epoch, name, **details)
            done.add(epoch)
            pending.pop(epoch, None)
            tokens_cache.pop(epoch, None)
            last_state.pop(epoch, None)

        deadline = None
        while True:
            for event in _complete_lines(events):
                epoch = event.get("iteration")
                if (event.get("job_id") != job_id or event.get("stage") != "measured"
                        or event.get("event_type") not in SLOW or type(epoch) is not int or epoch < 0
                        or epoch in done):
                    continue
                if epoch not in pending and len(pending) >= MAX_PENDING:
                    finish(epoch, "skipped_queue_full")
                    continue
                bucket = pending.setdefault(epoch, {})
                bucket.setdefault(operation_token(event), event)
            if (parent_pid is not None and os.getppid() != parent_pid) and deadline is None:
                deadline = time.monotonic()
            if stop.is_file() and deadline is None:
                deadline = time.monotonic()+drain_seconds
            if deadline is not None and (not pending or time.monotonic() >= deadline):
                for epoch in list(pending):
                    finish(epoch, "unfinished_on_shutdown", reason=last_state.get(epoch, "not_ready"))
                return
            started = False
            for epoch, alerts in sorted(pending.items()):
                try:
                    source, source_kind = ready_source(capture, snapshots, job_id, epoch)
                    if source is None:
                        status(epoch, "waiting_for_sealed_trace")
                        continue
                    cached = tokens_cache.get(epoch)
                    if cached is not None and cached[0] == source:
                        wanted = cached[1]
                    else:
                        wanted = closed_tokens(source, job_id, epoch, expected_ranks)
                        if wanted is not None:
                            tokens_cache[epoch] = source, wanted
                    if wanted is None:
                        status(epoch, "waiting_for_all_ranks")
                        continue
                    states = measurement_states(directory/"measurements.jsonl", job_id, epoch, wanted)
                    if set(states) != wanted or {t for t, s in states.items() if s in SLOW} != set(alerts):
                        status(epoch, "waiting_for_final_online_results")
                        continue
                    report = directory/"iterations"/f"iter-{epoch}"
                    status(epoch, "diagnosing", alert_count=len(alerts), trace_source=source_kind)
                    started = True
                    result = _diagnose(source, report, epoch=epoch, alerts=list(alerts.values()))
                    finish(epoch, "published", alert_count=len(alerts), report=str(report.relative_to(directory)),
                           trace_source=source_kind, diagnosis_status=result["diagnosis_status"])
                except (ValueError, KeyError, TypeError, AttributeError, OSError, RuntimeError) as error:
                    finish(epoch, "failed", reason=str(error))
                if started:
                    break  # Refresh newly written alarms before deciding the next iteration.
            if not started:
                time.sleep(poll_seconds)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("directory", "capture", "stop"):
        parser.add_argument("--"+name, type=Path, required=True)
    parser.add_argument("--snapshots", type=Path, default=None)
    parser.add_argument("--job-id", required=True)
    parser.add_argument("--expected-ranks", type=int)
    parser.add_argument("--drain-seconds", type=float, required=True)
    parser.add_argument("--parent-pid", type=int)
    args = parser.parse_args(argv)
    signal.signal(signal.SIGTERM, signal.default_int_handler)
    try:
        run_reports(**vars(args))
    except KeyboardInterrupt:
        return


if __name__ == "__main__":
    main()
