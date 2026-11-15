"""Synthetic clock tests and a real localhost probe/collector round trip."""
from __future__ import annotations

from collections import Counter
from io import StringIO
import json
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from hccl_trace import Trace
from hccl_trace.online_probe import OnlineProbe
from .dependency_model import stable_id
from .online_replay import replay_bound
from .online_service import Collector
from .online_tracker import OnlineTracker


SEC = 1_000_000_000


class Fixture:
    def __init__(self, **options):
        self.measured = []
        self.tracker = OnlineTracker("fixture", observe_measurement=self.measured.append, **options)
        self.sequence, self.counter = Counter(), Counter()
        self.now = SEC
        for r in (0, 1):
            self.push(r, "register", participants=[0, 1], device_timing_expected=True)

    def push(self, rank, event, *, generation=0, dropped=0, **fields):
        self.sequence[rank] += 1
        self.tracker.ingest(dict(version=1, job_id="fixture", rank_id=rank, session_id=f"s{rank}",
            seq=self.sequence[rank], dropped=dropped, event=event, communicator_id="comm",
            communicator_generation=generation, **fields), self.now)

    def enter(self, rank, iteration, *, stage="measured", generation=0, kind="allreduce", bucket="bucket"):
        self.counter[rank, generation] += 1
        counter = self.counter[rank, generation]
        self.push(rank, "enter", generation=generation, op_counter=counter, op_type=kind, tensor_bytes=256,
            host_entry_ts=self.now + rank, host_clock_domain=f"host_raw:node{rank}", stage=stage,
            iteration=iteration, bucket_id=bucket, occurrence=0)
        return counter

    def hb(self, rank, **fields):
        self.push(rank, "heartbeat", counters=[["comm", g, c] for (r, g), c in self.counter.items() if r == rank]
                  or [["comm", 0, 0]], **fields)

    def both(self, at):
        self.now = at*SEC
        self.hb(0)
        self.hb(1)
        self.tracker.tick(self.now)
        return self.tracker.drain()

    def span(self, rank, counter, duration, *, role="ring", domain=None, definition="main_stream"):
        self.push(rank, "device_span", op_counter=counter, device_start_ts=20_000+rank*9_000,
            device_end_ts=20_000+rank*9_000+duration, device_clock_domain=domain or f"device:{rank}",
            timing_definition=definition, timing_source="device_collective_boundary", evidence_ref=f"proof{rank}",
            rank_role=role, algorithm="ring")

    def complete(self, iteration, durations, *, stage="measured", roles=("ring", "ring"), bucket="bucket"):
        for rank in (0, 1):
            self.span(rank, self.enter(rank, iteration, stage=stage, bucket=bucket), durations[rank], role=roles[rank])
        return self.tracker.drain()


class TrackerTests(unittest.TestCase):
    def test_idle_and_late_before_deadline(self):
        f = Fixture()
        self.assertEqual(f.both(40), [])
        f.enter(0, 0)
        self.assertEqual(f.both(69), [])
        f.enter(1, 0)
        self.assertEqual(f.both(72), [])

    def test_h1_counter_freshness_transport_grace_and_dedup(self):
        f = Fixture()
        f.enter(0, 0)
        self.assertEqual(f.both(32), [])
        event, = f.both(34)
        self.assertEqual(event["event_type"], "NOT_ENTERED_HANG")
        self.assertEqual(event["suspected_ranks"], [1])
        self.assertEqual(event["ranks"][1]["telemetry"]["counter"], 0)
        self.assertEqual(f.both(35), [])

    def test_loss_disconnection_and_all_entered_are_not_h1(self):
        for situation in ("loss", "disconnect", "all_entered", "stale_queue"):
            with self.subTest(situation=situation):
                f = Fixture()
                f.enter(0, 0)
                if situation == "all_entered":
                    f.enter(1, 0)
                f.now = 40*SEC
                f.hb(0)
                f.hb(1, dropped=int(situation == "loss"), sender_queue_ns=9*SEC if situation == "stale_queue" else 0)
                if situation == "disconnect":
                    f.tracker.disconnect(1, "s1")
                f.tracker.tick(f.now)
                event, = f.tracker.drain()
                self.assertEqual(event["event_type"], "STALLED_UNKNOWN" if situation == "all_entered" else "INCOMPLETE_DATA")

    def test_generations_and_signature_mismatch(self):
        f = Fixture()
        for r in (0, 1):
            f.push(r, "register", generation=1, participants=[0, 1], device_timing_expected=False)
        self.assertEqual(f.enter(0, 0, generation=1), 1)
        self.assertEqual(f.enter(0, 0), 1)
        f.enter(1, 0, kind="broadcast")
        event, = f.tracker.drain()
        self.assertEqual(event["communicator_generation"], 0)
        self.assertEqual(event["reason"], "collective_signature_or_order_mismatch")
        self.assertIn(("comm", 1, 1), f.tracker.operations)

    def test_counter_gap_is_not_h1(self):
        f = Fixture()
        f.enter(0, 0)
        f.sequence[1] += 1
        event, = f.both(34)
        self.assertEqual(event["event_type"], "INCOMPLETE_DATA")

    def test_async_completion_keeps_original_identity_and_time_domains(self):
        f = Fixture()
        for r in (0, 1):
            f.enter(r, 0, stage="warmup", bucket="a")
            f.enter(r, 0, stage="warmup", bucket="b")
            f.span(r, 2, 200)
            f.span(r, 1, 100)
        event, = f.complete(0, (401, 400), bucket="a")
        self.assertEqual(event["event_type"], "COMMUNICATION_SLOW")
        self.assertEqual(event["metrics"]["t_base_ns"], 100)
        self.assertEqual(event["metrics"]["t_max_ns"], 401)
        self.assertEqual(event["time"]["clock_domain"], "unavailable")
        self.assertIsNone(event["suspected_ranks"])

    def test_slow_threshold_and_baseline_contamination(self):
        f = Fixture(baseline_window=2)
        for i, d in enumerate((100, 110, 90, 100)):
            self.assertEqual(f.complete(i, (d, d), stage="warmup"), [])
        self.assertEqual(f.complete(0, (300, 300)), [])
        self.assertEqual(f.measured[-1]["sample_count"], 4)
        event, = f.complete(1, (701, 701))
        self.assertEqual(event["metrics"]["t_base_ns"], 200)
        self.assertEqual(event["metrics"]["history_mad_ns"], 100)
        self.assertEqual(f.complete(2, (100, 100)), [])
        self.assertEqual(f.measured[-1]["t_base_ns"], 200)

    def test_computation_and_unclassified_bounds(self):
        for duration, roles, expected, suspects in (
                (110, ("ring", "ring"), "COMPUTATION_SLOW", [1]),
                (280, ("ring", "ring"), "SLOW_UNCLASSIFIED", None),
                (220, ("ring", "ring"), "SLOW_UNCLASSIFIED", None),
                (90, ("ring", "ring"), "SLOW_UNCLASSIFIED", None),
                (110, ("root", "leaf"), "SLOW_UNCLASSIFIED", None)):
            with self.subTest(duration=duration, roles=roles):
                f = Fixture()
                f.complete(0, (100, 100), stage="warmup", roles=roles)
                event, = f.complete(0, (400, duration), roles=roles)
                self.assertEqual((event["event_type"], event["suspected_ranks"]), (expected, suspects))

    def test_future_sample_and_mixed_definitions_do_not_become_baseline(self):
        f = Fixture()
        for rank in (0, 1):
            f.enter(rank, 0, stage="warmup")
            f.enter(rank, 0)
            f.span(rank, 2, 100)
        event, = f.tracker.drain()
        self.assertEqual(event["event_type"], "INSUFFICIENT_BASELINE")
        f.span(0, 1, 100)
        f.span(1, 1, 100, definition="different_boundary")
        event, = f.tracker.drain()
        self.assertEqual(event["reason"], "rank_timing_boundaries_not_comparable")
        event, = f.complete(1, (400, 400))
        self.assertEqual(event["event_type"], "INSUFFICIENT_BASELINE")

    def test_host_clock_cannot_be_used_for_device_span(self):
        f = Fixture()
        f.enter(0, 0)
        with self.assertRaisesRegex(ValueError, "device-domain"):
            f.span(0, 1, 50, domain="host_raw:node0")


class TransportTests(unittest.TestCase):
    def test_real_probe_transport_and_trace_host_bound(self):
        raw, reports = StringIO(), StringIO()
        tracker = OnlineTracker("test")
        with Collector(("127.0.0.1", 0), tracker=tracker, telemetry=raw, events=reports, token="local-test") as server:
            serve = threading.Thread(target=server.serve_forever, daemon=True)
            serve.start()
            try:
                with tempfile.TemporaryDirectory() as scratch:
                    for rank in (0, 1):
                        probe = OnlineProbe(server.server_address, job_id="test", rank_id=rank,
                                            host_clock_domain="host_raw:n0", auth_token="local-test")
                        with patch("hccl_trace._clocks", side_effect=lambda: dict(raw_ns=time.monotonic_ns(), unix_ns=time.time_ns())):
                            with Trace(scratch, node_id="n0", user_rank=rank, device_id=9+rank, run_id="test", online_probe=probe) as trace:
                                trace.group("comm", (0, 1))
                                with trace.iteration(0), trace.collective(group="comm", call_site="a", operation_type="AllReduce",
                                                                           element_count=32, dtype="fp32"):
                                    self.assertEqual(trace.online_token.op_counter, 1)
                                trace.completion_boundary()
                        call, = [json.loads(x) for x in (Path(scratch)/f"rank-{rank}.jsonl").read_text().splitlines()
                                 if json.loads(x)["event"] == "call"]
                        self.assertEqual(call["online_op_counter"], 1)
                deadline = time.monotonic()+2
                while not reports.getvalue() and time.monotonic() < deadline:
                    time.sleep(.01)
                report, = map(json.loads, reports.getvalue().splitlines())
                self.assertEqual(report["reason"], "device_timing_unavailable")
                self.assertTrue(all(r["device"] is None and r["host_completion_bound"] for r in report["ranks"]))
                self.assertNotIn("local-test", raw.getvalue())
                self.assertNotIn("auth", raw.getvalue())
            finally:
                server.shutdown()
                serve.join()

    def test_real_probe_heartbeat_identifies_missing_rank(self):
        raw, reports = StringIO(), StringIO()
        tracker = OnlineTracker("test", hang_timeout=.2, transport_grace=.05, heartbeat_ttl=1)
        with Collector(("127.0.0.1", 0), tracker=tracker, telemetry=raw, events=reports) as server:
            serve = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": .02}, daemon=True)
            serve.start()
            probes = []
            try:
                for r in (0, 1):
                    probe = OnlineProbe(server.server_address, job_id="test", rank_id=r,
                                        host_clock_domain="host_raw:n0", heartbeat_seconds=.05)
                    probes.append(probe)
                    probe.register("comm", 0, [0, 1])
                probes[0].enter("comm", 0, op_type="allreduce", tensor_bytes=128, host_entry_ts=time.monotonic_ns())
                limit = time.monotonic()+3
                while not reports.getvalue() and time.monotonic() < limit:
                    time.sleep(.01)
                event, = map(json.loads, reports.getvalue().splitlines())
                self.assertEqual(event["event_type"], "NOT_ENTERED_HANG")
                self.assertEqual(event["suspected_ranks"], [1])
            finally:
                for probe in probes:
                    probe.close()
                server.shutdown()
                serve.join()


class ReplayTests(unittest.TestCase):
    def test_bound_replay_uses_warmup_without_claiming_live_times_or_roles(self):
        ranks, operations, coordinates, spans, rank_calls = [], [], [], [], []
        durations = (100, 90, 401)
        for i, duration in enumerate(durations):
            operations.append(dict(operation_id=str(i), members=[]))
            coordinates.append(dict(group_id="train", stage="warmup" if i < 2 else "measured",
                iteration=i if i < 2 else 0, call_site="grad", occurrence=0,
                operation_scope=stable_id("op", ("archive", str(i)))))
        for rank in (0, 1):
            identity = dict(node_id=f"node{rank}", device_id=10+rank, user_rank=rank)
            ranks.append(identity)
            calls = []
            for i, duration in enumerate(durations):
                calls.append(dict({k:v for k,v in coordinates[i].items() if k != "operation_scope"},
                    sequence=i, participants=[0, 1], operation_type="AllReduce", dtype="fp32", element_count=32,
                    before=dict(raw_ns=1+i)))
                member = dict(node_id=identity["node_id"], device_id=identity["device_id"], group_name="g", op_name=f"op{i}")
                operations[i]["members"].append(member)
                spans.append(dict(member, start_ns=1000+rank*50+i, end_ns=1000+rank*50+i+duration, op_id=i))
            rank_calls.append((identity, calls))
        payload = dict(manifest=dict(run_id="archive", operations=operations, ranks=ranks),
                       coordinates=coordinates, rank_calls=rank_calls, spans=spans)
        result = replay_bound(payload)
        self.assertEqual(result["counts"]["WARMUP_ACCEPTED"], 2)
        report, = result["events"]
        self.assertEqual(report["metrics"]["t_base_ns"], 95)
        self.assertEqual(report["event_type"], "SLOW_UNCLASSIFIED")
        self.assertNotIn("collector", report)
        rank_calls[1][1][0]["sequence"], rank_calls[1][1][1]["sequence"] = 1, 0
        with self.assertRaisesRegex(ValueError, "order differs"):
            replay_bound(payload)


if __name__ == "__main__":
    unittest.main()
