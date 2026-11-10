from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict
from decimal import Decimal
import unittest

from . import rolling_diagnosis as rolling
from .clock_alignment import DeviceClock
from .result_normalizer import normalize
from .test_source_events import capture


def clocks():
    return dict(schema_version=3, status="network_probe_estimate", capture_id="run",
        models=[asdict(DeviceClock("run/node0", device, 0, 0, 0, 1, 1, 0, 10**9, 1000)) for device in (0, 1)],
        profiler_calibrations=[dict(node_id="node0", device_id=device, metadata_quantization_ns=1000) for device in (0, 1)])


class WaitArrivalTests(unittest.TestCase):
    def early_waiter(self):
        rows, edges, coordinates, _ = capture()
        for i in range(6):
            for row in rows[i * 4:i * 4 + 4]:
                for key in ("_start", "_stop", "_start_order", "_stop_order"):
                    row[key] += 100
            anchor = deepcopy(rows[i * 4])
            anchor.update(_graph_id="origin-{}".format(i), _stream_id=99, event="independent_origin",
                _start=i * 1000, _stop=i * 1000 + 1, _duration=1,
                _start_order=Decimal(i * 1000), _stop_order=Decimal(i * 1000 + 1))
            rows.append(anchor)
        wait = next(r for r in rows if r["_graph_id"] == "i5p2")
        wait.update(_start=5084, _start_order=Decimal(5084), _duration=wait["_stop"] - 5084)
        return rows, edges, coordinates

    def test_earlier_waiter_is_an_observation_not_a_source(self):
        rows, edges, coordinates = self.early_waiter()
        before = deepcopy((rows, edges))
        report = rolling.analyze(rows, edges, coordinates,
            rolling.RollingOptions(calibrated_release_intervals=True), alignment=clocks())
        self.assertIsNone(report["primary_source_candidate_id"])
        trace = next(t for t in report["wait_backtraces"] if t["wait_graph_id"] == "i5p2")
        observation = trace["arrival_observation"]
        self.assertEqual(observation["status"], "waiter_advanced_without_observed_producer_delay")
        self.assertEqual(Decimal(observation["waiter_start_delta_ns"]), -20000)
        self.assertEqual(Decimal(observation["producer_stop_delta_ns"]), 0)
        self.assertFalse(observation["source_candidate_created"])
        self.assertEqual((rows, edges), before)
        public, _, _ = normalize(report, mode="rolling", run_id="fixture", rows=rows, edges=edges,
                                 pipeline=dict(status="passed"), binding_evidence={})
        self.assertEqual(public["candidates"], [])
        self.assertTrue(any(r.get("arrival_observation") for r in public["unresolved_observations"]))
        self.assertEqual(public["coverage"]["unpaired_or_ambiguous_slow_wait_count"], 0)
        self.assertEqual(public["coverage"]["paired_slow_wait_count"], 1)

    def test_no_calibration_or_slow_producer_reference_does_not_explain_wait(self):
        rows, edges, coordinates = self.early_waiter()
        report = rolling.analyze(rows, edges, coordinates)
        self.assertFalse(any(t.get("arrival_observation") for t in report["wait_backtraces"]))
        producer = next(r for r in rows if r["_graph_id"] == "i4p1")
        producer.update(_start=4300, _stop=4301, _start_order=Decimal(4300), _stop_order=Decimal(4301))
        report = rolling.analyze(rows, edges, coordinates,
            rolling.RollingOptions(calibrated_release_intervals=True), alignment=clocks())
        arrival = next(t for t in report["wait_backtraces"] if t["wait_graph_id"] == "i5p2")["arrival_observation"]
        self.assertNotIn("i4p1", arrival["reference_producer_graph_ids"])
        self.assertEqual(arrival["reference_count"], 4)
        self.assertFalse(arrival["source_candidate_created"])

    def test_communication_peer_is_not_reassigned_as_fault_rank(self):
        rows, edges, coordinates, _ = capture(execution_delay=True)
        # Give all historical locations the same semantic peer before comparing.
        for row in rows:
            if row["_graph_id"].endswith("p0"):
                row.update(_peer_rank=1, match_status="matched")
        report = rolling.analyze(rows, edges, coordinates)
        public, _, _ = normalize(report, mode="rolling", run_id="fixture", rows=rows, edges=edges,
                                 pipeline=dict(status="passed"), binding_evidence={})
        candidate = public["candidates"][0]
        context = candidate["communication_context"]
        self.assertEqual(candidate["user_rank"], 0)
        self.assertEqual(context["peer_rank"], 1)
        self.assertEqual(context["peer_device_id"], 1)
        self.assertFalse(context["peer_is_proven_fault_location"])
        self.assertFalse(candidate["workload_completion_impact_proven"])
        ambiguous = deepcopy(next(r for r in rows if r["_graph_id"] == "i5p2"))
        ambiguous.update(_graph_id="ambiguous-peer", _node_id="other-node")
        public, _, _ = normalize(report, mode="rolling", run_id="fixture", rows=rows + [ambiguous], edges=edges,
                                 pipeline=dict(status="passed"), binding_evidence={})
        self.assertEqual(public["candidates"][0]["communication_context"]["peer_identity_status"], "unavailable")
