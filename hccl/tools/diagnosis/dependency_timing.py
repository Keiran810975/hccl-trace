"""Time checks on existing dependencies, never a source of new graph edges."""
from __future__ import annotations

from collections import defaultdict

from . import analyze_waits as waits
from .clock_alignment import models_from_report


ORDER = "direct_stream_order_observed"
EVENT = "local_event_sync_exact"
WAIT = frozenset({"event_wait", "notify_wait"})
NOTIFY = {"direct_notify_sync_exact": "exact", "local_notify_sync_exact": "exact",
          "cross_node_notify_sync_observed": "observed", "same_node_rdma_notify_sync_observed": "observed"}


def _event_identity(edge):
    context, obj, generation = (edge.get(k) for k in ("event_context_id", "event_id", "event_generation"))
    if isinstance(generation, str) and generation.isascii() and generation.isdecimal():
        generation = int(generation)
    if (isinstance(context, str) and context.strip() and isinstance(obj, str) and obj.strip()
            and type(generation) is int and generation >= 0):
        return context, obj, generation
    return None


class EvidenceGraph:
    """Strict local blocking checks over the already constructed execution graph."""

    def __init__(self, rows, edges, alignment=None, local_clocks=None):
        self.nodes = {r["_graph_id"]: r for r in rows}
        self.clocks = models_from_report(alignment)
        self.local_clocks = local_clocks or {}
        self.outgoing = defaultdict(list)
        self.signals, self.orders = defaultdict(list), defaultdict(list)
        self.event_records = defaultdict(set)
        for e in edges:
            kind = e["kind"]
            if kind == ORDER:
                self.orders[e["dst"]].append(e)
            elif "notify_sync" in kind or "event_sync" in kind:
                self.signals[e["dst"]].append(e)
                if kind == EVENT and e.get("confidence") == "exact" and (token := _event_identity(e)) is not None:
                    self.event_records[self.endpoint(self.nodes[e["src"]]), token].add(e["src"])
            else:
                continue
            self.outgoing[e["src"]].append(e)

    @staticmethod
    def endpoint(row):
        return row["_node_id"], row["_device_id"]

    def endpoints(self, edge):
        return self.nodes[edge["src"]], self.nodes[edge["dst"]]

    def proof(self, edge):
        src, dst = self.endpoints(edge)
        kind, confidence = edge["kind"], edge.get("confidence")
        p, q = self.endpoint(src), self.endpoint(dst)
        sk, dk = (r["profiler_task_kind"] for r in (src, dst))
        base = dict(edge_id=edge["edge_id"], kind=kind, confidence=confidence,
                    src=edge["src"], dst=edge["dst"], verified=False,
                    hardware_completion_observed=None)

        def result(status, **fields):
            return dict(base, status=status, **fields)

        if any(r.get("_node_kind") == "boundary" for r in (src, dst)):
            return result("missing_exact_endpoint")
        if any(r.get("_subtask_id", -1) >= 0 for r in (src, dst)) or "ffts" in kind:
            return result("ffts_timing_not_verified")
        b = waits.ns(src, "stop")
        c, d = (waits.ns(dst, s) for s in ("start", "stop"))
        if kind == ORDER:
            if (len(self.orders[edge["dst"]]) != 1 or confidence != "observed"
                    or p != q or src["_stream_id"] != dst["_stream_id"] or b > c):
                return result("unverified_stream_order")
            return dict(base, status="verified_stream_order", verified=True,
                        timing_domain="same_profiler_device", slack_ns=c-b, estimated_error_ns=0,
                        source_done_ns=b, target_interval_ns=[c, d])
        if len(self.signals[edge["dst"]]) != 1:
            return result("ambiguous_sync_producer")
        if kind == EVENT:
            token = _event_identity(edge)
            if (confidence != "exact" or p != q or (sk, dk) != ("event_record", "event_wait")
                    or token is None or len(self.event_records[p, token]) != 1):
                return result("unresolved_event_dependency")
            base["event_identity"] = dict(zip(("context_id", "event_id", "generation"), token))
        elif (confidence != NOTIFY.get(kind) or kind not in NOTIFY
              or dk != "notify_wait" or sk not in {"notify_record", "rdma"}
              or (p[0] != q[0]) != (kind == "cross_node_notify_sync_observed")):
            return result("unverified_notify_identity")
        if sk == "rdma":
            return dict(base, status="rdma_submission_not_payload_completion",
                        hardware_completion_observed=False)
        error = 0
        domain = "same_profiler_device"
        if p != q:
            local = p[0] == q[0] and p in self.local_clocks and q in self.local_clocks
            clocks = self.local_clocks if local else self.clocks
            if p not in clocks or q not in clocks:
                return result("missing_cross_device_clock")
            left, right = clocks[p], clocks[q]
            try:
                b, c, d = left.map_ns(b), right.map_ns(c), right.map_ns(d)
            except ValueError:
                return result("clock_coverage_boundary")
            error = left.estimated_error_ns + right.estimated_error_ns
            domain = "same_node_monotonic_raw" if local else "calibrated_estimate"
        timing = dict(timing_domain=domain, estimated_error_ns=error,
                      source_done_ns=b, target_interval_ns=[c, d])
        if b + error <= c:
            return result("producer_already_ready", **timing)
        if b - error > d:
            return result("producer_after_wait_release", **timing)
        if b - error <= c or b + error > d:
            return result("clock_order_uncertain", **timing)
        return dict(base, status="verified_producer_during_wait", verified=True, **timing,
                    slack_ns=d-b)

    def wait_proof(self, task):
        signals = self.signals[task]
        if len(signals) == 1:
            return self.proof(signals[0])
        kind = self.nodes[task]["profiler_task_kind"]
        return dict(verified=False, status=("ambiguous_sync_producer" if signals else
                    "unresolved_event_dependency" if kind == "event_wait" else "unpaired_notify_wait"))


def edge_observation(edge, source, target, clocks):
    if "ffts" in edge["kind"]:
        return dict(status="ffts_not_complete_hardware_dag")
    remote = source["node_id"] != target["node_id"]
    if not remote:
        if edge["kind"] == "direct_stream_order_observed":
            return dict(status="accepted" if source["observed_stop_ns"] <= target["observed_start_ns"] else "incompatible_stream_order_timestamps")
        if source["task_kind"] != "notify_record" or target["task_kind"] != "notify_wait":
            return dict(status="unsupported_or_unmeasured_notify_release")
        if source["observed_stop_ns"] > target["observed_stop_ns"]:
            return dict(status="incompatible_notify_timestamps")
        return dict(status="signal_precedes_wait_start" if source["observed_stop_ns"] <= target["observed_start_ns"] else "accepted")
    if (edge["kind"] != "cross_node_notify_sync_observed" or edge.get("confidence") != "observed"
            or source["task_kind"] not in {"notify_record", "rdma"} or target["task_kind"] != "notify_wait"):
        return dict(status="unsupported_cross_node_dependency")
    a, b = (clocks.get((t["node_id"], t["device_id"])) for t in (source, target))
    if a is None or b is None:
        return dict(status="uncalibrated_cross_node_boundary")
    ss, se = (a.map_ns(source[k]) for k in ("observed_start_ns", "observed_stop_ns"))
    ts, te = (b.map_ns(target[k]) for k in ("observed_start_ns", "observed_stop_ns"))
    error = a.estimated_error_ns + b.estimated_error_ns
    facts = dict(timing_domain="independent_network_probe_estimate", estimated_error_ns=error,
        source_mapped_ns=[ss, se], target_mapped_ns=[ts, te],
        source_profiler_interval_ns=[source["observed_start_ns"], source["observed_stop_ns"]],
        target_profiler_interval_ns=[target["observed_start_ns"], target["observed_stop_ns"]],
        hardware_completion_observed=False, physical_causal_contribution_ns=None)
    if ss - a.estimated_error_ns > te + b.estimated_error_ns:
        return dict(facts, status="incompatible_calibrated_notify_timestamps")
    if source["task_kind"] == "notify_record" and se + a.estimated_error_ns <= ts - b.estimated_error_ns:
        return dict(facts, status="signal_precedes_wait_start")
    # A doorbell can finish before a remote Wait starts without proving data was ready.
    return dict(facts, status="accepted", evidence_kind="cross_node_protocol_topology_and_slow_wait_not_hardware_release")
