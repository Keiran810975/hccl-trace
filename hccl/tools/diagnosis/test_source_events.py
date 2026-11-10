"""Source-policy tests use public observations, never fault labels or windows."""
from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict
from decimal import Decimal
import unittest

from . import rolling_diagnosis as rolling
from . import source_events
from .clock_alignment import DeviceClock
from .result_normalizer import normalize
from .test_compare_diagnosis import fixture


def capture(*, host_delay=False, execution_delay=False):
    original, original_edges, _, _ = fixture()
    rows, edges, coords, preparations = [], [], [], []
    for iteration in range(6):
        base = iteration * 1000
        preparation_us = 100 if host_delay and iteration == 5 else 1
        work_us = 40 if execution_delay and iteration == 5 else 10
        begin = base + preparation_us + 2
        end = begin + work_us
        times = [(begin, end), (end, end + .001), (base + 4, end + .1), (end + .1, end + .3)]
        group = deepcopy(original)
        for index, (row, (start, stop)) in enumerate(zip(group, times)):
            row.update(_graph_id="i{}p{}".format(iteration, index), _node_id="run/node0",
                       _device_id=row["_user_rank"], _operation_scope="op-{}".format(iteration),
                       _start_order=Decimal(str(start)), _stop_order=Decimal(str(stop)),
                       _start=start, _stop=stop, _duration=stop - start)
        rows.extend(group)
        edges.extend(dict(e, src="i{}{}".format(iteration, e["src"]), dst="i{}{}".format(iteration, e["dst"]),
                          edge_id="i{}{}".format(iteration, e["edge_id"]),
                          kind="direct_notify_sync_exact" if "notify_sync" in e["kind"] else e["kind"],
                          confidence="exact" if "notify_sync" in e["kind"] else "observed") for e in original_edges)
        coords.append(dict(operation_scope="op-{}".format(iteration), stage="measured", iteration=iteration,
                           block=0, bucket=0, evidence="fixture public call-to-DB binding"))
        preparations.append(dict(operation_scope="op-{}".format(iteration), node_id="run/node0", user_rank=0,
                                 device_id=0, start_ns=base * 1000, stop_ns=(base + preparation_us) * 1000,
                                 api_start_ns=(base + preparation_us + 1) * 1000,
                                 api_stop_ns=(base + preparation_us + 2) * 1000,
                                 evidence="fixture public preparation/API binding"))
    return rows, edges, rolling.validate_coordinates(coords), preparations


def cross_node_capture(*, error_ns=100):
    rows, edges, coords, preparations = capture(host_delay=True)
    offset = 10**15
    for row in rows:
        if row["_user_rank"] == 1:
            row["_node_id"] = "run/node1"
            for key in ("_start_order", "_stop_order"):
                row[key] += Decimal(offset) / 1000
            row["_start"], row["_stop"] = float(row["_start_order"]), float(row["_stop_order"])
        elif row["profiler_task_kind"] == "notify_record":
            row["profiler_task_kind"] = "rdma"
    for edge in edges:
        if "notify_sync" in edge["kind"]:
            edge.update(kind="cross_node_notify_sync_observed", confidence="observed")
    clocks = [DeviceClock("run/node0", 0, 0, 0, 0, 1, 1, 0, 10**9, error_ns),
              DeviceClock("run/node1", 1, offset, 0, 0, 1, 1, 0, 10**9, error_ns)]
    alignment = dict(schema_version=3, status="network_probe_estimate", models=list(map(asdict, clocks)))
    return rows, edges, coords, preparations, alignment


class SourceEventTests(unittest.TestCase):
    def test_host_preparation_is_localized_without_any_injection_input(self):
        rows, edges, coords, preparations = capture(host_delay=True)
        report = rolling.analyze(rows, edges, coords, preparations=preparations)
        self.assertIsNone(report["primary_source_candidate_id"])
        primary = next(r for r in report["root_causes"] if r["component"] == "host_preparation")
        self.assertEqual(primary["component"], "host_preparation")
        self.assertEqual(primary["user_rank"], 0)
        self.assertEqual((primary["observed_start_ns"], primary["observed_stop_ns"]), (5000000, 5100000))
        self.assertIsNone(primary["task_id"])
        self.assertIsNone(primary["stream_id"])
        self.assertEqual(primary["anchor_graph_id"], "i5p1")
        self.assertEqual(primary["evidence_paths"], {"i5p2": ["i5e1"]})
        self.assertEqual(primary["reference_iterations"], [0, 1, 2, 3, 4])

    def test_host_delay_without_public_observation_stays_unresolved(self):
        rows, edges, coords, _ = capture(host_delay=True)
        report = rolling.analyze(rows, edges, coords)
        self.assertIsNone(report["primary_source_candidate_id"])
        self.assertEqual(report["diagnosis_status"], "unresolved_waits")

    def test_cross_node_host_source_uses_existing_observed_notify_and_clock_margins(self):
        rows, edges, coords, preparations, alignment = cross_node_capture()
        before = deepcopy((rows, edges))
        report = rolling.analyze(rows, edges, coords, preparations=preparations, alignment=alignment)
        root = next(r for r in report["root_causes"] if r["component"] == "host_preparation")
        self.assertEqual(root["status"], "dependency_supported_candidate")
        self.assertEqual(root["evidence_paths"], {"i5p2": ["i5e1"]})
        self.assertEqual(root["time_alignment_estimated_error_ns"], 200)
        self.assertGreater(root["observed_wait_overlap_ns"], 0)
        self.assertEqual((rows, edges), before)
        public, _, _ = normalize(report, mode="rolling", run_id="run", rows=rows, edges=edges,
                                 pipeline=dict(status="passed"), binding_evidence={})
        self.assertEqual(public["candidates"], [])
        candidate = next(c for c in public["external_anomaly_clues"] if c["component"] == "host_preparation")
        self.assertEqual(candidate["evidence_confidence"], "observed")
        self.assertEqual(candidate["time_alignment_estimated_error_ns"], 200)

    def test_cross_node_host_source_needs_alignment_and_complete_unique_protocol_edge(self):
        for failure in ("no_alignment", "missing_device", "uncertain_overlap", "missing_edge", "two_producers"):
            with self.subTest(failure=failure):
                rows, edges, coords, preparations, alignment = cross_node_capture(error_ns=100000 if failure == "uncertain_overlap" else 100)
                if failure == "no_alignment":
                    alignment = None
                elif failure == "missing_device":
                    alignment["models"].pop()
                elif failure == "missing_edge":
                    edges = [e for e in edges if e["edge_id"] != "i5e1"]
                elif failure == "two_producers":
                    edges.append(dict(next(e for e in edges if e["edge_id"] == "i5e1"), edge_id="duplicate-producer"))
                report = rolling.analyze(rows, edges, coords, preparations=preparations, alignment=alignment)
                root = next(r for r in report["unresolved_observations"] if r["component"] == "host_preparation")
                self.assertEqual(root["status"], "unresolved_host_preparation")

    def test_host_interval_without_exact_peer_notify_does_not_gain_support(self):
        rows, edges, coords, preparations = capture(host_delay=True)
        edges = [e for e in edges if e["edge_id"] != "i5e1"]
        report = rolling.analyze(rows, edges, coords, preparations=preparations)
        self.assertIsNone(report["primary_source_candidate_id"])
        root = next(r for r in report["unresolved_observations"] if r["component"] == "host_preparation")
        self.assertEqual(root["status"], "unresolved_host_preparation")

    def test_host_interval_finished_before_wait_began_is_not_attributed(self):
        rows, edges, coords, preparations = capture(host_delay=True)
        preparations[-1].update(start_ns=4900000, stop_ns=5000000)
        report = rolling.analyze(rows, edges, coords, preparations=preparations)
        self.assertIsNone(report["primary_source_candidate_id"])

    def test_preparation_truth_unknown_device_duplicate_and_bad_clock_are_rejected(self):
        rows, _, coords, preparations = capture()
        bad_items = [dict(preparations[0], injection_kind="delay"), dict(preparations[0], device_id=999),
                     dict(preparations[0], stop_ns=999999999)]
        for item in bad_items:
            with self.subTest(item=item), self.assertRaises(ValueError):
                source_events.validate_preparations([item], rows, coords)
        with self.assertRaises(ValueError):
            source_events.validate_preparations([preparations[0]] * 2, rows, coords)


if __name__ == "__main__":
    unittest.main()
