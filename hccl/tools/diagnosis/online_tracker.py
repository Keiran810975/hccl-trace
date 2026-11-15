"""Collective identity, telemetry health and device-duration detection (V1)."""
from __future__ import annotations

from dataclasses import dataclass, field
from math import isfinite
from statistics import median
from uuid import uuid4


TIMING_SOURCES = {"cann_communication_op", "device_collective_boundary"}
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


class OnlineTracker:
    """Single-owner state machine; callers supply collector monotonic times."""

    def __init__(self, job_id, *, hang_timeout=30., heartbeat_ttl=5., transport_grace=2.,
                 baseline_window=20, max_pending=8192, observe_measurement=None):
        if not (_name(job_id) and all(isfinite(x) for x in (hang_timeout, heartbeat_ttl, transport_grace))
                and hang_timeout > 0 and heartbeat_ttl > 0 and transport_grace >= 0
                and type(baseline_window) is int and baseline_window > 0
                and type(max_pending) is int and max_pending > 0):
            raise ValueError("invalid online detector configuration")
        self.job_id = job_id
        self.collector_id = uuid4().hex
        self.timeout, self.ttl, self.grace = (int(_NS * x) for x in
                                                (hang_timeout, heartbeat_ttl, transport_grace))
        self.baseline_window, self.max_pending = baseline_window, max_pending
        self.observe_measurement = observe_measurement
        self.streams, self.groups, self.operations, self.history = {}, {}, {}, {}
        self.events = []
        self.counts = {}

    def drain(self):
        events, self.events = self.events, []
        return events

    def disconnect(self, rank, session):
        s = self.streams.get(rank)
        if s is not None and s.session == session:
            s.connected = False
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
        self.events.append(dict(version=1, event_id=digest, event_type=kind, job_id=self.job_id,
            communicator_id=key[0], communicator_generation=key[1], op_counter=key[2],
            stage=coordinate.get("stage"), iteration=coordinate.get("iteration"),
            bucket_id=coordinate.get("bucket_id"), occurrence=coordinate.get("occurrence"),
            op_type=coordinate.get("op_type"), tensor_bytes=coordinate.get("tensor_bytes"),
            time=dict(start_ns=None, end_ns=None, clock_domain="unavailable"),
            collector=dict(clock_domain=f"collector_monotonic:{self.collector_id}",
                           first_entry_seen_ns=op.first_seen, all_entered_seen_ns=op.all_entered,
                           detected_ns=now, elapsed_since_first_entry_ns=now-op.first_seen,
                           hang_timeout_ns=self.timeout, transport_grace_ns=self.grace),
            reason=reason, status=op.status, ranks=ranks, offline_analysis="pending", **details))
        self.counts[kind] = self.counts.get(kind, 0) + 1

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
        if s.session != session:
            s.valid = False
            return
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
        if event == "heartbeat":
            counters = {}
            for comm, gen, count in row["counters"]:
                if not (_name(comm) and _nat(gen) and _nat(count)) or (comm, gen) in counters:
                    raise ValueError("invalid heartbeat counter")
                counters[comm, gen] = count
            s.valid &= counters == s.counters
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
                    and (row.get("iteration") is None or _nat(row["iteration"]))):
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
                                    host_entry_source=row.get("host_entry_source"), raw_event=ref)
            if not group.consistent or rank not in group.ranks or any(
                    any(e[x] != signature[x] for x in fields) for e in op.entries.values()):
                self._finalize(key, op, "INCOMPLETE_DATA", now, "collective_signature_or_order_mismatch")
            elif len(op.entries) == len(group.ranks):
                op.all_entered, op.status = now, "ALL_ENTERED"
            return
        if event not in {"host_completion_bound", "device_span", "call_failed"}:
            raise ValueError("unknown online event")
        op = self.operations.get(key)
        if op is None:
            return
        if rank not in op.entries:
            raise ValueError("completion without this Rank's entry")
        if event == "call_failed":
            self._finalize(key, op, "INCOMPLETE_DATA", now, "collective_call_failed", failure_event=ref)
        elif event == "host_completion_bound":
            entry = op.entries[rank]
            if not (_nat(row.get("host_observed_ts")) and row["host_observed_ts"] >= entry["host_entry_ts"]
                    and row.get("host_clock_domain") == entry["host_clock_domain"]):
                raise ValueError("invalid Host completion upper bound")
            op.host_bounds[rank] = dict(observed_ns=row["host_observed_ts"],
                                        clock_domain=row["host_clock_domain"], raw_event=ref)
            if len(op.host_bounds) == len(group.ranks) and not all(group.registered.values()):
                self._finalize(key, op, "INCOMPLETE_DATA", now, "device_timing_unavailable")
        elif event == "device_span":
            self._span(row, now, rank, key, op, ref)

    def _span(self, row, now, rank, key, op, ref):
        start, end = row.get("device_start_ts"), row.get("device_end_ts")
        domain, definition, source = (row.get(x) for x in
                                     ("device_clock_domain", "timing_definition", "timing_source"))
        error = row.get("uncertainty_ns")
        if not (_nat(start) and _nat(end) and end > start and _name(domain)
                and domain.startswith("device:") and _name(definition) and source in TIMING_SOURCES
                and _name(row.get("evidence_ref")) and (error is None or _nat(error))
                and all(row.get(x) is None or _name(row[x]) for x in ("rank_role", "algorithm"))):
            raise ValueError("device span requires device-domain start/end and trusted timing evidence")
        if rank in op.spans:
            raise ValueError("duplicate Rank device span")
        op.spans[rank] = dict(start_ns=start, end_ns=end, duration_ns=end-start, clock_domain=domain,
            timing_definition=definition, timing_source=source, evidence_ref=row["evidence_ref"], raw_event=ref,
            rank_role=row.get("rank_role"), algorithm=row.get("algorithm"), uncertainty_ns=error)
        group = self.groups[key[:2]]
        if len(op.spans) == len(group.ranks):
            self.operations.pop(key)
            if not group.consistent or not all(self.streams[r].valid for r in group.ranks):
                self._report(key, op, "INCOMPLETE_DATA", now, "invalid_rank_telemetry_at_completion")
            elif len({(v["timing_definition"], v["timing_source"]) for v in op.spans.values()}) != 1:
                self._report(key, op, "INCOMPLETE_DATA", now, "rank_timing_boundaries_not_comparable")
            else:
                self.counts["COMPLETED"] = self.counts.get("COMPLETED", 0) + 1
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
                spans[0]["timing_definition"], spans[0]["timing_source"],
                tuple((s["algorithm"], s["rank_role"]) for s in spans))
        history = self.history.setdefault(hkey, [])
        eligible = sorted((h for h in history if h[0] < key[2] and
                           (h[1] == "warmup" if stage == "measured" and iteration == 0 else
                            ((h[1] == "warmup" and stage == "measured") or
                             (h[1] == stage and h[2] < iteration)))), key=lambda h: h[0])
        if stage == "warmup":
            history.append((key[2], stage, iteration, maximum))
            self.counts["WARMUP_ACCEPTED"] = self.counts.get("WARMUP_ACCEPTED", 0) + 1
            return
        if iteration != 0:
            eligible = eligible[-self.baseline_window:]
        if not eligible:
            self._report(key, op, "INSUFFICIENT_BASELINE", now, "no_prior_comparable_healthy_sample")
            return
        values = [h[3] for h in eligible]
        base = median(values)
        delta = maximum-base
        if self.observe_measurement is not None:
            self.observe_measurement(dict(communicator_id=key[0], communicator_generation=key[1],
                op_counter=key[2], stage=stage, iteration=iteration, bucket_id=entry["bucket_id"],
                occurrence=entry["occurrence"], t_base_ns=base, t_max_ns=maximum, t_min_ns=minimum,
                sample_count=len(values), R=delta/base, slow=maximum > 3*base))
        if maximum <= 3*base:
            self.counts["NORMAL"] = self.counts.get("NORMAL", 0) + 1
            history.append((key[2], stage, iteration, maximum))
            # Keep all warmups (iteration 0 may complete out of order) and the latest normal observations.
            formal = sorted((h for h in history if h[1] == "measured"), key=lambda h: h[0])
            if len(formal) > self.baseline_window:
                history[:] = [h for h in history if h[1] == "warmup"] + formal[-self.baseline_window:]
            return
        p = (maximum-minimum)/delta
        comparable = (len(group.ranks) > 1 and all(s["rank_role"] and s["algorithm"] for s in spans)
                      and len({(s["rank_role"], s["algorithm"]) for s in spans}) == 1)
        shortest = [r for r, d in zip(group.ranks, durations) if d == minimum]
        longest = [r for r, d in zip(group.ranks, durations) if d == maximum]
        kind, reason, suspect, attribution = "SLOW_UNCLASSIFIED", "p_in_ambiguous_range", None, "undetermined"
        if not comparable or not 0 <= p <= 1:
            reason = "rank_roles_not_proven_comparable" if not comparable else "p_outside_interpretation_range"
        elif p > .6:
            kind, reason, suspect, attribution = "COMPUTATION_SLOW", "p_above_computation_threshold", shortest, "heuristic"
            if len({e["host_clock_domain"] for e in op.entries.values()}) == 1:
                latest = max(e["host_entry_ts"] for e in op.entries.values())
                latest_ranks = [r for r in group.ranks if op.entries[r]["host_entry_ts"] == latest]
                if len(latest_ranks) == 1 and latest_ranks == shortest:
                    attribution = "host_entry_order_supports_heuristic"
                elif len(latest_ranks) == 1 and not set(shortest).intersection(latest_ranks):
                    kind, reason, suspect, attribution = "SLOW_UNCLASSIFIED", "p_conflicts_with_host_entry_order", None, "undetermined"
        elif p < .4:
            kind, reason = "COMMUNICATION_SLOW", "p_below_communication_threshold"
        self._report(key, op, kind, now, reason, suspected_ranks=suspect, rank_attribution=attribution,
            metrics=dict(t_base_ns=base, t_max_ns=maximum, t_min_ns=minimum, delta_ns=delta,
                         history_mad_ns=median(abs(v-base) for v in values), history_max_ns=max(values),
                         sample_count=len(values), samples=[dict(op_counter=c, stage=s, iteration=i, max_ns=m)
                                                           for c, s, i, m in eligible],
                         R=delta/base, P=p, shortest_ranks=shortest, longest_ranks=longest))

    def tick(self, now):
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
            self._finalize(key, op, "INCOMPLETE_DATA", now, "device_timing_unavailable" if healthy and not missing
                           else "telemetry_cannot_confirm_missing_rank", suspected_ranks=None)
