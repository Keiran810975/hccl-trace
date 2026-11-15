"""Collective identity, telemetry health and device-duration detection (V1)."""
from __future__ import annotations

from dataclasses import dataclass, field
from math import isfinite
from statistics import median
from uuid import uuid4


TIMING_SOURCES = {"cann_communication_op", "device_collective_boundary", "npu_event_elapsed"}
_NS = 1_000_000_000
_NONCOMPLETED = {"NOT_ENTERED_HANG", "STALLED_UNKNOWN", "INCOMPLETE_DATA"}


def _nat(value):
    return type(value) is int and value >= 0


def _name(value):
    return isinstance(value, str) and bool(value)


@dataclass
class Stream:
    session: str
    seq: int = 0
    heartbeat: int | None = None
    valid: bool = True
    connected: bool = True
    heartbeat_ref: dict | None = None
    counters: dict = field(default_factory=dict)
    connection_index: int | None = None
    missing_sequences: int = 0
    dropped: int = 0
    ended: bool = False
    host_log: dict = field(default_factory=dict)


@dataclass
class Group:
    ranks: tuple
    registered: dict = field(default_factory=dict)
    consistent: bool = True


@dataclass
class Operation:
    first_seen: int
    entries: dict = field(default_factory=dict)
    spans: dict = field(default_factory=dict)
    host_bounds: dict = field(default_factory=dict)
    all_entered: int | None = None
    status: str = "PENDING"
    issued: bool = False


@dataclass(frozen=True)
class Sample:
    counter: int
    stage: str
    iteration: int
    maximum: int
    preparation: dict


class OnlineTracker:
    """Single-owner state machine; callers supply collector monotonic times."""

    def __init__(self, job_id, *, hang_timeout=30., heartbeat_ttl=5., transport_grace=2.,
                 baseline_window=20, warmup_iterations=10, max_pending=8192, observe_measurement=None):
        if not (_name(job_id) and all(isfinite(x) for x in (hang_timeout, heartbeat_ttl, transport_grace))
                and hang_timeout > 0 and heartbeat_ttl > 0 and transport_grace >= 0
                and type(baseline_window) is int and baseline_window > 0
                and type(warmup_iterations) is int and warmup_iterations > 0
                and type(max_pending) is int and max_pending > 0):
            raise ValueError("invalid online detector configuration")
        self.job_id = job_id
        self.collector_id = uuid4().hex
        self.timeout, self.ttl, self.grace = (int(_NS * x) for x in
                                                (hang_timeout, heartbeat_ttl, transport_grace))
        self.baseline_window, self.max_pending = baseline_window, max_pending
        self.warmup_indices = set(range(warmup_iterations))
        self.observe_measurement = observe_measurement
        self.streams, self.groups, self.operations, self.history = {}, {}, {}, {}
        self.events = []
        self.counts = {}
        self.awaiting_baseline, self.invalid_baselines, self.measured_baselines = {}, set(), set()

    def _count(self, key):
        self.counts[key] = self.counts.get(key, 0) + 1

    def drain(self):
        events, self.events = self.events, []
        return events

    def disconnect(self, rank, session):
        s = self.streams.get(rank)
        if s is not None and s.session == session:
            s.connected = False
            s.valid &= s.ended
            s.heartbeat = None
            s.heartbeat_ref = None

    def _report(self, key, op, kind, now, reason, **details):
        if op.issued:
            return
        op.issued = True
        op.status = kind if kind in _NONCOMPLETED else "COMPLETED"
        group = self.groups[key[:2]]
        coordinate = next(iter(op.entries.values()))
        ranks = []
        for rank in group.ranks:
            s = self.streams.get(rank)
            ranks.append(dict(rank_id=rank, entry=op.entries.get(rank), device=op.spans.get(rank),
                              host_completion_bound=op.host_bounds.get(rank),
                              telemetry=dict(registered=rank in group.registered,
                                             valid=bool(s and s.valid),
                                             connected=bool(s and s.connected),
                                             counter=s.counters.get(key[:2]) if s else None,
                                             last_heartbeat_ns=s.heartbeat if s else None,
                                             heartbeat_event=s.heartbeat_ref if s else None)))
        digest = f"{self.collector_id}:{key[0]}:{key[1]}:{key[2]}"
        report = dict(version=1, event_id=digest, event_type=kind, job_id=self.job_id,
            communicator_id=key[0], communicator_generation=key[1], op_counter=key[2],
            stage=coordinate.get("stage"), iteration=coordinate.get("iteration"),
            bucket_id=coordinate.get("bucket_id"), occurrence=coordinate.get("occurrence"),
            op_type=coordinate.get("op_type"), tensor_bytes=coordinate.get("tensor_bytes"),
            time=dict(start_ns=None, end_ns=None, clock_domain="unavailable"),
            collector=dict(clock_domain=f"collector_monotonic:{self.collector_id}",
                           first_entry_seen_ns=op.first_seen, all_entered_seen_ns=op.all_entered,
                           detected_ns=now, elapsed_since_first_entry_ns=now-op.first_seen,
                           hang_timeout_ns=self.timeout, transport_grace_ns=self.grace),
            reason=reason, status=op.status, ranks=ranks, offline_analysis="pending", **details)
        if kind != "TIMING_UNAVAILABLE":
            self.events.append(report)
        if kind in _NONCOMPLETED or kind in {"INSUFFICIENT_BASELINE", "TIMING_UNAVAILABLE"}:
            self._measurement(key, op, kind, reason=reason)
        self._count(kind)

    def _measurement(self, key, op, status, **fields):
        if self.observe_measurement is None:
            return
        entry = next(iter(op.entries.values()))
        self.observe_measurement(dict(job_id=self.job_id, communicator_id=key[0], communicator_generation=key[1],
            op_counter=key[2], status=status, stage=entry["stage"], iteration=entry["iteration"],
            bucket_id=entry["bucket_id"], occurrence=entry["occurrence"], op_type=entry["op_type"],
            tensor_bytes=entry["tensor_bytes"], device_by_rank=op.spans, **fields))

    def _finalize(self, key, op, kind, now, reason, **details):
        self._report(key, op, kind, now, reason, **details)
        self.operations.pop(key, None)

    def ingest(self, row, now):
        rank, session, seq, dropped = (row.get(x) for x in ("rank_id", "session_id", "seq", "dropped"))
        if not (row.get("job_id") == self.job_id and type(row.get("version")) is int
                and row["version"] == 1 and _nat(rank) and _name(session)
                and _nat(seq) and seq > 0 and _nat(dropped)):
            raise ValueError("invalid online telemetry envelope")
        s = self.streams.setdefault(rank, Stream(session))
        if s.session != session or s.ended:
            s.valid = False
            return
        connection = row.get("connection_index", 1)
        if not _nat(connection) or connection < 1:
            raise ValueError("invalid collector connection index")
        s.valid &= connection == 1 and s.connection_index in {None, connection}
        s.connection_index = connection
        s.missing_sequences += max(0, seq - s.seq - 1)
        s.dropped = max(s.dropped, dropped)
        s.connected = True
        s.valid &= seq == s.seq + 1 and dropped == 0
        if seq <= s.seq:
            return
        s.seq = seq
        try:
            self._ingest(row, now, rank, s)
        except (ValueError, TypeError, KeyError) as exc:
            s.valid = False
            raise ValueError(str(exc)) from exc

    def _ingest(self, row, now, rank, s):
        event = row.get("event")
        if event in {"heartbeat", "run_end"}:
            counters = {}
            for comm, gen, count in row["counters"]:
                if not (_name(comm) and _nat(gen) and _nat(count)) or (comm, gen) in counters:
                    raise ValueError("invalid heartbeat counter")
                counters[comm, gen] = count
            s.valid &= counters == s.counters
            if event == "run_end":
                host_log = row.get("host_log")
                pending = row.get("pending_calls")
                if not (isinstance(host_log, dict) and all(_nat(host_log.get(k, 0)) for k in ("writes", "elapsed_ns"))
                        and _nat(pending)):
                    raise ValueError("invalid final Rank audit")
                s.ended, s.host_log = True, host_log
                s.valid &= pending == 0
                return
            age = row.get("sender_queue_ns", 0)
            if not _nat(age):
                raise ValueError("invalid heartbeat queue age")
            s.heartbeat = max(0, now-age)
            s.heartbeat_ref = dict(session_id=s.session, seq=s.seq)
            return
        comm, gen = row.get("communicator_id"), row.get("communicator_generation")
        if not (_name(comm) and _nat(gen)):
            raise ValueError("invalid communicator identity")
        gid = comm, gen
        if event == "register":
            members = row.get("participants")
            expected = row.get("device_timing_expected")
            if not (isinstance(members, list) and all(_nat(r) for r in members)
                    and len(set(members)) == len(members) and rank in members and type(expected) is bool):
                raise ValueError("invalid participants or timing capability")
            ranks = tuple(sorted(members))
            group = self.groups.setdefault(gid, Group(ranks))
            group.consistent &= group.ranks == ranks and rank not in group.registered
            group.registered[rank] = expected
            s.counters.setdefault(gid, 0)
            return
        count = row.get("op_counter")
        if not (_nat(count) and count > 0 and gid in s.counters):
            raise ValueError("invalid or unregistered operation identity")
        group, key = self.groups[gid], (*gid, count)
        ref = dict(session_id=s.session, seq=s.seq)
        if event == "enter":
            if not (_name(row.get("op_type")) and _nat(row.get("tensor_bytes"))
                    and _nat(row.get("host_entry_ts")) and _name(row.get("host_clock_domain"))
                    and _nat(row.get("occurrence"))
                    and all(row.get(x) is None or _name(row[x]) for x in ("stage", "bucket_id", "dtype", "reduction"))
                    and (row.get("iteration") is None or _nat(row["iteration"]))
                    and ((row.get("preparation_ns") is None and row.get("preparation_definition") is None)
                         or (_nat(row.get("preparation_ns")) and _name(row.get("preparation_definition"))))):
                raise ValueError("invalid collective entry")
            if count != s.counters[gid] + 1:
                s.valid = False
                return
            s.counters[gid] = count
            if key not in self.operations and any(
                    self.streams[r].counters.get(gid, 0) >= count for r in group.ranks
                    if r != rank and r in self.streams):
                # A monotone counter cannot reopen an already finalized operation.
                return
            if key not in self.operations and len(self.operations) >= self.max_pending:
                oldest, pending = next(iter(self.operations.items()))
                self._finalize(oldest, pending, "INCOMPLETE_DATA", now, "collector_pending_limit")
            op = self.operations.setdefault(key, Operation(now))
            fields = ("op_type", "tensor_bytes", "dtype", "reduction", "stage", "iteration", "bucket_id", "occurrence")
            signature = {x: row.get(x) for x in fields}
            op.entries[rank] = dict(signature, host_entry_ts=row["host_entry_ts"],
                                    host_clock_domain=row["host_clock_domain"],
                                    host_entry_source=row.get("host_entry_source"), raw_event=ref,
                                    preparation_ns=row.get("preparation_ns"),
                                    preparation_definition=row.get("preparation_definition"))
            if not group.consistent or rank not in group.ranks or any(
                    any(e[x] != signature[x] for x in fields) for e in op.entries.values()):
                self._finalize(key, op, "INCOMPLETE_DATA", now, "collective_signature_or_order_mismatch")
            elif len(op.entries) == len(group.ranks):
                op.all_entered, op.status = now, "ALL_ENTERED"
                self._count("ALL_ENTERED")
            return
        if event not in {"host_completion_bound", "device_span", "device_duration", "timing_failed", "call_failed"}:
            raise ValueError("unknown online event")
        if event == "timing_failed":
            self._count("INVALID_TIMING")
        op = self.operations.get(key)
        if op is None:
            if event in {"device_span", "device_duration"}:
                self._count("INVALID_TIMING")
            return
        if rank not in op.entries:
            raise ValueError("completion without this Rank's entry")
        if event == "call_failed":
            self._finalize(key, op, "INCOMPLETE_DATA", now, "collective_call_failed", failure_event=ref)
        elif event == "timing_failed":
            self._finalize(key, op, "INCOMPLETE_DATA", now, "device_timing_adapter_failed", failure_event=ref)
        elif event == "host_completion_bound":
            entry = op.entries[rank]
            if not (_nat(row.get("host_observed_ts")) and row["host_observed_ts"] >= entry["host_entry_ts"]
                    and row.get("host_clock_domain") == entry["host_clock_domain"]):
                raise ValueError("invalid Host completion upper bound")
            op.host_bounds[rank] = dict(observed_ns=row["host_observed_ts"],
                                        clock_domain=row["host_clock_domain"], raw_event=ref)
            if len(op.host_bounds) == len(group.ranks) and not all(group.registered.values()):
                self._finalize(key, op, "TIMING_UNAVAILABLE", now, "device_timing_unavailable")
        else:
            try:
                self._span(row, now, rank, key, op, ref)
            except ValueError:
                self._count("INVALID_TIMING")
                self._finalize(key, op, "INCOMPLETE_DATA", now, "invalid_device_timing", failure_event=ref)
                raise

    def _span(self, row, now, rank, key, op, ref):
        group = self.groups[key[:2]]
        if not group.registered.get(rank):
            raise ValueError("unexpected device timing from a Rank without a timing declaration")
        start, end = row.get("device_start_ts"), row.get("device_end_ts")
        domain, definition, source = (row.get(x) for x in
                                     ("device_clock_domain", "timing_definition", "timing_source"))
        error = row.get("uncertainty_ns")
        duration = row.get("device_duration_ns")
        if row["event"] == "device_span":
            if not (_nat(start) and _nat(end) and end > start and _name(domain) and domain.startswith("device:")
                    and source != "npu_event_elapsed" and (duration is None or duration == end-start)):
                raise ValueError("device span requires device-domain start/end and trusted timing evidence")
            duration = end-start
        elif any(v is not None for v in (start, end, domain)):
            raise ValueError("device_duration cannot supply unverified absolute timestamps")
        profile, proof = row.get("timing_profile_id"), row.get("boundary_evidence")
        if not (_nat(duration) and duration > 0 and _name(definition) and _name(source) and source in TIMING_SOURCES
                and _name(row.get("evidence_ref")) and (error is None or _nat(error))
                and ((profile is None and proof is None) or (_name(profile) and _name(proof)))
                and all(row.get(x) is None or _name(row[x]) for x in ("rank_role", "algorithm"))):
            raise ValueError("device timing requires a positive duration and trusted timing evidence")
        if source == "npu_event_elapsed" and definition != "consumer_stream_collective_v1":
            raise ValueError("NPU Event timing must use its explicit consumer-stream definition")
        if source == "npu_event_elapsed" and rank not in op.host_bounds:
            raise ValueError("NPU Event readback requires a preceding existing completion boundary")
        if rank in op.spans:
            raise ValueError("duplicate Rank device span")
        op.spans[rank] = dict(start_ns=start, end_ns=end, duration_ns=duration, clock_domain=domain,
            timing_definition=definition, timing_source=source, evidence_ref=row["evidence_ref"], raw_event=ref,
            rank_role=row.get("rank_role"), algorithm=row.get("algorithm"), uncertainty_ns=error,
            timing_profile_id=profile, boundary_evidence=proof)
        if len(op.spans) == len(group.ranks):
            self.operations.pop(key)
            if not group.consistent or not all(self.streams[r].valid for r in group.ranks):
                self._report(key, op, "INCOMPLETE_DATA", now, "invalid_rank_telemetry_at_completion")
            elif len({(v["timing_definition"], v["timing_source"], v["timing_profile_id"], v["boundary_evidence"])
                      for v in op.spans.values()}) != 1:
                self._count("INVALID_TIMING")
                self._report(key, op, "INCOMPLETE_DATA", now, "rank_timing_boundaries_not_comparable")
            else:
                self._count("COMPLETED")
                if source != "npu_event_elapsed" or (profile and all(v["algorithm"] and v["rank_role"] for v in op.spans.values())):
                    self._count("VERIFIED_TIMING")
                if not op.issued:
                    op.status = "COMPLETED"
                    self._slow(key, group, op, now)

    def _slow(self, key, group, op, now):
        entry = op.entries[group.ranks[0]]
        stage, iteration = entry["stage"], entry["iteration"]
        spans = [op.spans[r] for r in group.ranks]
        durations = [s["duration_ns"] for s in spans]
        maximum, minimum = max(durations), min(durations)
        if stage not in {"measured", "warmup"} or iteration is None or entry["bucket_id"] is None:
            self._report(key, op, "INSUFFICIENT_BASELINE", now, "no_stable_semantic_coordinate")
            return
        hkey = (*key[:2], group.ranks, *(entry[x] for x in
                ("op_type", "tensor_bytes", "dtype", "reduction", "bucket_id", "occurrence")),
                spans[0]["timing_definition"], spans[0]["timing_source"], spans[0]["timing_profile_id"],
                tuple((s["algorithm"], s["rank_role"]) for s in spans))
        history = self.history.setdefault(hkey, [])
        preparation = {r: (e["preparation_definition"], e["preparation_ns"]) for r, e in op.entries.items()}
        if stage == "warmup":
            if iteration not in self.warmup_indices or any(h.stage == "warmup" and h.iteration == iteration for h in history):
                self.invalid_baselines.add(hkey)
                self._report(key, op, "INSUFFICIENT_BASELINE", now, "unexpected_or_duplicate_warmup_iteration")
                return
            history.append(Sample(key[2], stage, iteration, maximum, preparation))
            self._count("WARMUP_ACCEPTED")
            warm = [h.maximum for h in history if h.stage == "warmup"]
            if len(warm) == len(self.warmup_indices) and max(warm) > 3 * median(warm):
                self.invalid_baselines.add(hkey)
            self._measurement(key, op, "WARMUP", t_max_ns=maximum, t_min_ns=minimum,
                              baseline_ready=self._warmup_ready(hkey), R=None, P=None)
            for waiting_key, (lane, pending, _) in sorted(self.awaiting_baseline.items()):
                if lane == hkey and self._resolve_baseline(waiting_key, hkey, pending, now):
                    self.awaiting_baseline.pop(waiting_key)
            return
        self.measured_baselines.add(hkey)
        if not self._resolve_baseline(key, hkey, op, now):
            if len(self.awaiting_baseline) >= self.max_pending:
                oldest = next(iter(self.awaiting_baseline))
                _, pending, _ = self.awaiting_baseline.pop(oldest)
                self._report(oldest, pending, "INSUFFICIENT_BASELINE", now, "collector_baseline_limit")
            self.awaiting_baseline[key] = hkey, op, now

    def _warmup_ready(self, hkey, before=None):
        return hkey not in self.invalid_baselines and {h.iteration for h in self.history[hkey]
            if h.stage == "warmup" and (before is None or h.counter < before)} == self.warmup_indices

    def _resolve_baseline(self, key, hkey, op, now):
        if not all(self.streams[r].valid for r in self.groups[key[:2]].ranks):
            self._report(key, op, "INCOMPLETE_DATA", now, "invalid_rank_telemetry_at_baseline_resolution")
            return True
        if hkey in self.invalid_baselines:
            self._report(key, op, "INSUFFICIENT_BASELINE", now, "warmup_invalid_or_unstable")
            return True
        if not self._warmup_ready(hkey, key[2]):
            return False
        group, history = self.groups[key[:2]], self.history[hkey]
        entry = op.entries[group.ranks[0]]
        stage, iteration = entry["stage"], entry["iteration"]
        spans = [op.spans[r] for r in group.ranks]
        durations = [s["duration_ns"] for s in spans]
        maximum, minimum = max(durations), min(durations)
        eligible = sorted((h for h in history if h.counter < key[2] and
                           (h.stage == "warmup" or (iteration > 0 and h.iteration < iteration))),
                          key=lambda h: h.counter)
        if iteration != 0:
            eligible = eligible[-self.baseline_window:]
        values = [h.maximum for h in eligible]
        base = median(values)
        delta = maximum-base
        p = (maximum-minimum)/delta if delta > 0 else None
        metrics = dict(t_base_ns=base, t_max_ns=maximum, t_min_ns=minimum, delta_ns=delta,
                       history_mad_ns=median(abs(v-base) for v in values), history_max_ns=max(values),
                       sample_count=len(values), samples=[dict(op_counter=h.counter, stage=h.stage,
                           iteration=h.iteration, max_ns=h.maximum) for h in eligible], R=delta/base, P=p)
        preparation = {r: (e["preparation_definition"], e["preparation_ns"]) for r, e in op.entries.items()}
        if maximum <= 3*base:
            self._count("NORMAL")
            self._measurement(key, op, "NORMAL", slow=False, baseline_ready=True, **metrics)
            history.append(Sample(key[2], stage, iteration, maximum, preparation))
            formal = sorted((h for h in history if h.stage == "measured"), key=lambda h: h.counter)
            if len(formal) > self.baseline_window:
                history[:] = [h for h in history if h.stage == "warmup"] + formal[-self.baseline_window:]
            return True
        comparable = (len(group.ranks) > 1 and all(s["rank_role"] and s["algorithm"] for s in spans)
                      and len({(s["rank_role"], s["algorithm"]) for s in spans}) == 1)
        shortest = [r for r, d in zip(group.ranks, durations) if d == minimum]
        longest = [r for r, d in zip(group.ranks, durations) if d == maximum]
        prep = self._preparation(group.ranks, eligible, preparation)
        kind, reason, suspect, attribution = "SLOW_UNCLASSIFIED", "p_in_ambiguous_range", None, "undetermined"
        if spans[0]["timing_source"] == "npu_event_elapsed" and not spans[0]["timing_profile_id"]:
            reason = "consumer_stream_boundary_not_validated"
        elif not comparable or not 0 <= p <= 1:
            reason = "rank_roles_not_proven_comparable" if not comparable else "p_outside_interpretation_range"
        elif p > .6:
            if prep is not None and len(shortest) == 1 and [r for r in group.ranks if prep[r]["anomalous"]] == shortest:
                kind, reason, suspect, attribution = ("COMPUTATION_SLOW", "p_and_independent_preparation_delay",
                                                      shortest, "preparation_supported_suspect")
                same_clock = len({e["host_clock_domain"] for e in op.entries.values()}) == 1
                if same_clock and op.entries[shortest[0]]["host_entry_ts"] < max(e["host_entry_ts"] for e in op.entries.values()):
                    kind, reason, suspect, attribution = "SLOW_UNCLASSIFIED", "p_conflicts_with_host_entry_order", None, "undetermined"
            else:
                reason = "no_independent_preparation_delay_for_unique_shortest_rank"
        elif p < .4:
            kind, reason = "COMMUNICATION_SLOW", "p_below_communication_threshold"
        metrics.update(shortest_ranks=shortest, longest_ranks=longest, preparation_by_rank=prep)
        self._report(key, op, kind, now, reason, suspected_ranks=suspect, rank_attribution=attribution,
                     metrics=metrics)
        self._measurement(key, op, kind, reason=reason, slow=True, baseline_ready=True, **metrics)
        return True

    @staticmethod
    def _preparation(ranks, samples, current):
        definitions = {definition for definition, _ in current.values()}
        if len(definitions) != 1 or None in definitions:
            return None
        evidence = {}
        for rank in ranks:
            definition, duration = current[rank]
            history = [h.preparation[rank][1] for h in samples if h.preparation[rank][0] == definition]
            if len(history) != len(samples):
                return None
            base = median(history)
            mad = median(abs(v-base) for v in history)
            threshold = max(1_000_000, .5*base, 3*mad)
            evidence[rank] = dict(definition=definition, current_ns=duration, median_ns=base, mad_ns=mad,
                                  delta_ns=duration-base, minimum_excess_ns=threshold,
                                  anomalous=duration-base > threshold)
        return evidence

    def health(self, expected_ranks=None, expected_collectives=None):
        actual = {r for g in self.groups.values() for r in g.registered}
        ended = {r for r, s in self.streams.items() if s.ended}
        bad = sorted(r for r, s in self.streams.items() if not s.valid)
        missing = sum(s.missing_sequences for s in self.streams.values())
        dropped = sum(s.dropped for s in self.streams.values())
        counts = self.counts
        baseline_ready = bool(self.measured_baselines) and not self.awaiting_baseline and not self.invalid_baselines and all(
            self._warmup_ready(k) for k in self.measured_baselines)
        expected_set = set(range(expected_ranks)) if expected_ranks is not None else None
        complete = expected_set is not None and actual == ended == expected_set and not (bad or missing or dropped)
        device_complete = expected_collectives is not None and expected_collectives == counts.get("ALL_ENTERED", 0) == counts.get("COMPLETED", 0) == counts.get("VERIFIED_TIMING", 0)
        passed = complete and device_complete and baseline_ready and not self.operations and not any(counts.get(key) for key in (
            "INVALID_TIMING", "INSUFFICIENT_BASELINE", "INCOMPLETE_DATA"))
        return dict(event="RUN_HEALTH", job_id=self.job_id, collector_id=self.collector_id, acceptance_ready=passed,
            rank_streams_complete=complete, device_timing_complete=device_complete, baseline_ready=baseline_ready,
            registered_ranks=len(actual), expected_ranks=expected_ranks, expected_collectives=expected_collectives,
            missing_ranks=sorted(expected_set-actual) if expected_set is not None else None,
            unacknowledged_ranks=sorted(actual-ended), invalid_ranks=bad, missing_sequences=missing, dropped_events=dropped,
            invalid_timing=counts.get("INVALID_TIMING", 0), entered_collectives=counts.get("ALL_ENTERED", 0),
            completed_collectives=counts.get("COMPLETED", 0), collectives_with_valid_timing=counts.get("VERIFIED_TIMING", 0),
            pending_collectives=len(self.operations), pending_baselines=len(self.awaiting_baseline),
            host_log_by_rank={r: s.host_log for r, s in self.streams.items() if s.ended}, counts=dict(counts))

    def finish(self, now):
        for key, (_, op, _) in list(self.awaiting_baseline.items()):
            self._report(key, op, "INSUFFICIENT_BASELINE", now, "incomplete_warmup_at_run_end")
        self.awaiting_baseline.clear()
        for key, op in list(self.operations.items()):
            self._finalize(key, op, "INCOMPLETE_DATA", now, "unresolved_collective_at_run_end")

    def tick(self, now):
        for key, (_, op, first) in list(self.awaiting_baseline.items()):
            if now > first+self.timeout+self.grace:
                self._report(key, op, "INSUFFICIENT_BASELINE", now, "incomplete_warmup_after_timeout")
                self.awaiting_baseline.pop(key)
        for key, op in list(self.operations.items()):
            group = self.groups[key[:2]]
            if op.issued:
                if now >= op.first_seen + 2*(self.timeout+self.grace+self.ttl):
                    self.operations.pop(key)
                continue
            anchor = op.first_seen if op.all_entered is None else op.all_entered
            deadline = anchor + self.timeout + self.grace
            if now <= deadline:
                continue
            healthy = group.consistent and all(r in group.registered and r in self.streams
                and self.streams[r].valid and self.streams[r].connected and self.streams[r].heartbeat is not None
                and now-self.streams[r].heartbeat <= self.ttl for r in group.ranks)
            missing = sorted(set(group.ranks)-op.entries.keys())
            if missing and healthy and all(self.streams[r].counters.get(key[:2]) == key[2]-1 for r in missing):
                if all(self.streams[r].heartbeat >= deadline for r in missing):
                    self._report(key, op, "NOT_ENTERED_HANG", now, "missing_rank_heartbeat_counter_confirmed",
                                 suspected_ranks=missing)
                    continue
                if now < deadline+self.ttl:
                    continue
            if healthy and not missing and len(op.host_bounds) < len(group.ranks):
                self._report(key, op, "STALLED_UNKNOWN", now, "no_verified_completion_after_all_entered")
                continue
            self._finalize(key, op, "INCOMPLETE_DATA", now, "expected_device_timing_missing" if healthy and not missing
                           else "telemetry_cannot_confirm_missing_rank", suspected_ranks=None)
