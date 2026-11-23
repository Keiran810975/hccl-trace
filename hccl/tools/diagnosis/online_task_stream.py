"""First S2 observations from sealed, pre-associated device Task batches."""
from __future__ import annotations

from collections import Counter, deque
from dataclasses import dataclass, field
from decimal import Decimal
from functools import lru_cache
import json
import os
import time

from .dependency_timing import WAIT
from .online_followup import operation_token
from .online_reports import MAX_PENDING, _complete_lines
from .rank_progress import MIN_SAMPLES
from .rolling_diagnosis import RollingOptions, _slow, _statistics


LOCATION = ("algorithm", "phase", "step", "slice", "event", "semantic", "task_kind", "peer_rank", "size_bytes")
SITE = ("communicator_id", "communicator_generation", "bucket_id", "occurrence",
        "op_type", "tensor_bytes", "dtype", "reduction")
MAX_BATCH_BYTES = 2 * 1024**2
LOOKBACK = 10
FIRST_REPORT_SECONDS = 5
MAX_WAIT_SECONDS = 60


def _nat(value):
    return type(value) is int and value >= 0


def _label(value):
    return isinstance(value, str) and bool(value.strip())


class Batches:
    def __init__(self, root, job_id):
        self.root, self.job_id = root, job_id
        self._cached_read = lru_cache(maxsize=32)(self._read)

    @staticmethod
    def version(stat):
        return stat.st_dev, stat.st_ino, stat.st_mtime_ns, stat.st_size

    def _read(self, path, iteration, rank, version):
        with path.open("rb") as stream:
            if self.version(os.fstat(stream.fileno())) != version:
                raise FileNotFoundError("Task batch replaced during read")
            raw = stream.read(MAX_BATCH_BYTES + 1)
        if len(raw) > MAX_BATCH_BYTES:
            raise ValueError("task batch exceeds size limit")
        data = json.loads(raw)
        if (not isinstance(data, dict) or data.get("schema_version") != 1
                or data.get("run_id") != self.job_id or not _nat(data.get("iteration"))
                or not _nat(data.get("rank")) or data["iteration"] != iteration
                or data["rank"] != rank or data.get("complete") is not True
                or data.get("source") != "exact_device_task_association"
                or not _label(data.get("node_id")) or not _nat(data.get("device_id"))
                or not isinstance(data.get("operations"), list)):
            raise ValueError("foreign or incomplete device Task batch")
        sites, tokens = {}, set()
        for op in data["operations"]:
            site, token = tuple(op[k] for k in SITE), operation_token(op)
            if (not all(_label(op[k]) for k in ("communicator_id", "bucket_id", "op_type", "dtype"))
                    or not all(_nat(op[k]) for k in ("communicator_generation", "occurrence", "tensor_bytes",
                                                     "op_counter", "host_entry_ts"))
                    or not (op["reduction"] is None or _label(op["reduction"]))
                    or op["op_counter"] == 0 or site in sites or token in tokens
                    or not isinstance(op["tasks"], list)):
                raise ValueError("invalid or ambiguous Task batch operation")
            sites[site] = dict(op, durations=_durations(op["tasks"]))
            tokens.add(token)
        return data["node_id"], data["device_id"], sites

    def get(self, iteration, rank):
        path = self.root/f"iter-{iteration}"/f"rank-{rank}.json"
        try:
            return self._cached_read(path, iteration, rank, self.version(path.stat()))
        except FileNotFoundError:
            return None  # The producer may atomically publish this file later.


def _durations(tasks):
    durations, seen = {}, set()
    shapes = Counter()
    for task in tasks:
        key = tuple(task[k] for k in LOCATION)
        if (not all(_label(task[k]) for k in ("algorithm", "phase", "event", "semantic", "task_kind"))
                or not all(_nat(task[k]) for k in ("step", "start_ns", "stop_ns", "stream_id", "task_id"))
                or not all(type(task[k]) is int and task[k] >= -1 for k in ("slice", "peer_rank", "size_bytes"))
                or not _label(task["execution_id"]) or task["execution_id"] in seen
                or task["stop_ns"] < task["start_ns"]):
            raise ValueError("invalid or duplicate completed device Task")
        seen.add(task["execution_id"])
        shapes[key] += 1
        durations[key] = (task["stop_ns"] - task["start_ns"], task)
    return shapes, {k: v for k, v in durations.items() if shapes[k] == 1}


def observe(batches, alert, rank, entry):
    epoch = alert["iteration"]
    current = batches.get(epoch, rank)
    if current is None:
        return None
    node, device, operations = current
    site = tuple(alert[k] if k in alert else entry[k] for k in SITE)
    op = operations.get(site)
    if op is None:
        return None  # Other calls in the same Rank/iteration may have completed first.
    if (operation_token(op) != operation_token(alert) or op["host_entry_ts"] != entry["host_entry_ts"]
            or entry["host_clock_domain"] != "host_raw:"+node):
        raise ValueError("device Task batch does not match the alert's Rank call")
    shape, tasks = op["durations"]
    history, missing = [], []
    for previous in range(max(0, epoch-LOOKBACK), epoch):
        older = batches.get(previous, rank)
        if older is None:
            missing.append(previous)
            continue
        before = older[2].get(site)
        if before is None:
            missing.append(previous)
            continue
        if (older[:2] == current[:2] and before["op_counter"] < op["op_counter"]
                and before["host_entry_ts"] < op["host_entry_ts"] and before["durations"][0] == shape):
            history.append((previous, before["durations"][1]))
    options = RollingOptions()
    results, comparable = [], 0
    for location, (duration, task) in tasks.items():
        clean = deque(maxlen=options.window)
        for previous, entries in history:
            sample = entries[location][0]
            if not clean or not _slow(sample, *_statistics(v for _, v in clean), options,
                                      propagation=task["task_kind"] in WAIT):
                clean.append((previous, sample))
        if len(clean) < MIN_SAMPLES:
            continue
        mean, _ = _statistics(v for _, v in clean)
        if mean <= 0:
            continue
        comparable += 1
        if duration >= 2 * mean:
            observation = {k: task[k] for k in ("stream_id", "task_id", "task_kind", "phase", "step", "event")}
            results.append(dict(observation, duration_ns=duration, reference_mean_ns=str(mean),
                                increase_ns=str(duration-mean), increase_percent=str((duration-mean)*100/mean),
                                reference_iterations=[i for i, _ in clean], is_wait=task["task_kind"] in WAIT))
    results.sort(key=lambda row: Decimal(row["increase_ns"]), reverse=True)
    return dict(rank=rank, node_id=node, device_id=device, comparable_tasks=comparable,
                annotated_tasks=sum(shape.values()), missing_history_iterations=missing,
                status=("slow_tasks_observed" if results else "no_task_over_threshold"
                        if comparable else "insufficient_history"), slow_count=len(results),
                top_tasks=[t for t in results if not t["is_wait"]][:3],
                top_waits=[t for t in results if t["is_wait"]][:3])


@dataclass
class Pending:
    alert: dict
    entries: dict
    seen_ns: int
    reported: set = field(default_factory=set)
    observed_slow: bool = False
    warned: bool = False


def run(events, output, source, job_id, stop, *, drain_seconds=120, parent_pid=None, poll_seconds=.05):
    batches = Batches(source, job_id)
    pending, done = {}, set()
    deadline = None
    with events.open("rb") as incoming, (output/"slow_tasks.jsonl").open("x", encoding="utf-8", buffering=1) as log:
        def emit(item, **fields):
            now = time.monotonic_ns()
            event = item.alert
            log.write(json.dumps(dict(schema_version=1, run_id=job_id, event_id=event["event_id"],
                iteration=event["iteration"], bucket_id=event["bucket_id"], op_counter=event["op_counter"],
                observed_latency_ms=(now-item.seen_ns)/1e6, **fields), separators=(",", ":"))+"\n")

        while True:
            for event in _complete_lines(incoming):
                if ((event.get("job_id"), event.get("stage"), event.get("event_type")) !=
                        (job_id, "measured", "COMMUNICATION_SLOW") or not _nat(event.get("iteration"))):
                    continue
                key = event["event_id"]
                if key in done or key in pending:
                    continue
                entries = {r["rank_id"]:r["entry"] for r in event["ranks"]}
                if (not entries or len(entries) != len(event["ranks"])
                        or any(not _nat(rank) or not isinstance(entry, dict) for rank, entry in entries.items())):
                    raise ValueError("S2 alert requires all Rank call identities")
                item = Pending(event, entries, time.monotonic_ns())
                if len(pending) >= MAX_PENDING:
                    emit(item, status="skipped_queue_full")
                    done.add(key)
                else:
                    pending[key] = item
            if deadline is None:
                if parent_pid is not None and os.getppid() != parent_pid:
                    deadline = time.monotonic_ns()
                elif stop.is_file():
                    deadline = time.monotonic_ns()+int(drain_seconds*1e9)
            for key, item in list(pending.items()):
                for rank in sorted(item.entries.keys() - item.reported):
                    try:
                        result = observe(batches, item.alert, rank, item.entries[rank])
                    except (ValueError, TypeError, KeyError, OSError) as error:
                        result = dict(rank=rank, status="invalid_task_batch", reason=str(error))
                    if result is None:
                        continue
                    item.reported.add(rank)
                    item.observed_slow |= bool(result.get("slow_count"))
                    emit(item, resolved_ranks=len(item.reported), expected_ranks=len(item.entries), **result)
                unresolved = sorted(item.entries.keys() - item.reported)
                now = time.monotonic_ns()
                elapsed = now-item.seen_ns
                if not unresolved or elapsed >= MAX_WAIT_SECONDS*1e9 or (deadline is not None and now >= deadline):
                    if unresolved:
                        emit(item, status="task_batches_incomplete", pending_ranks=unresolved)
                    done.add(key)
                    del pending[key]
                elif elapsed >= FIRST_REPORT_SECONDS*1e9 and not item.warned:
                    emit(item, status="waiting_for_device_task_batches", pending_ranks=unresolved,
                         slow_task_already_reported=item.observed_slow)
                    item.warned = True
            if deadline is not None and not pending:
                return
            time.sleep(poll_seconds)
