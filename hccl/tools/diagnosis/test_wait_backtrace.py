from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict
from decimal import Decimal
import unittest

from . import rolling_diagnosis as rolling
from .test_source_events import capture
from .clock_alignment import DeviceClock


def cross_call_capture():
    rows, edges, coordinates, _ = capture(execution_delay=True)
    coords = []
    for i in range(6):
        for bucket in (0, 1):
            coords.append(dict(operation_scope="op-{}-{}".format(i, bucket), stage="measured", iteration=i,
                               block=0, bucket=bucket, evidence="fixture: two independently bound calls"))
        for row in rows[i * 4:(i + 1) * 4]:
            row["_operation_scope"] = "op-{}-{}".format(i, 0 if row["_graph_id"].endswith("p0") else 1)
    return rows, edges, rolling.validate_coordinates(coords)


class WaitBacktraceTests(unittest.TestCase):
    def test_backtrace_keeps_disconnected_explaining_sources_without_clustering(self):
        rows, edges, coords, _ = capture(execution_delay=True)
        extra = [dict(r, _graph_id="other-" + r["_graph_id"], _operation_scope="other-" + r["_operation_scope"])
                 for r in rows]
        links = [dict(e, src="other-" + e["src"], dst="other-" + e["dst"], edge_id="other-" + e["edge_id"])
                 for e in edges]
        other = {"other-" + k: dict(v, operation_scope="other-" + k, bucket=1) for k, v in coords.items()}
        report = rolling.analyze(rows + extra, edges + links, dict(coords, **other),
                                 rolling.RollingOptions())
        self.assertEqual({r["graph_id"] for r in report["root_causes"]}, {"i5p0", "other-i5p0"})
        self.assertTrue(all(r["task_kind"] != "notify_wait" for r in report["root_causes"]))
        self.assertIsNone(report["primary_source_candidate_id"])
        self.assertEqual(report["source_regions"], [])
        self.assertEqual({t["graph_id"] for t in report["tasks"] if t["role"] == "propagated_wait"},
                         {"i5p2", "other-i5p2"})

    def test_backtrace_needs_cross_node_calibration_for_explanation(self):
        rows, edges, coords, _ = capture(execution_delay=True)
        for row in rows:
            if row["_user_rank"] == 1:
                row["_node_id"] = "run/node1"
        for edge in edges:
            if "notify_sync" in edge["kind"]:
                edge.update(kind="cross_node_notify_sync_observed", confidence="observed")
        options = rolling.RollingOptions()
        report = rolling.analyze(rows, edges, coords, options)
        self.assertEqual(report["root_causes"], [])
        self.assertIn("uncalibrated_cross_node_boundary", report["coverage"]["boundary_reason_counts"])
        clocks = self.clocks()
        clocks["models"][1].update(node_id="run/node1", estimated_error_ns=1)
        report = rolling.analyze(rows, edges, coords, options, alignment=clocks)
        self.assertEqual({r["graph_id"] for r in report["root_causes"]}, {"i5p0"})
        self.assertEqual(report["root_causes"][0]["evidence_paths"]["i5p2"], ["i5e0", "i5e1"])

    def test_backtrace_keeps_supported_host_without_making_wait_a_root(self):
        rows, edges, coords, preparations = capture(host_delay=True)
        report = rolling.analyze(rows, edges, coords, rolling.RollingOptions(),
                                 preparations=preparations)
        self.assertEqual([r["component"] for r in report["root_causes"]], ["host_preparation"])
        self.assertFalse(any(r["graph_id"] == "i5p2" for r in report["unresolved_observations"]))

    def test_uncomparable_intermediate_wait_is_not_assumed_normal(self):
        from . import wait_backtrace
        rows, edges, coords, _ = capture(execution_delay=True)
        tasks = rolling.compare_tasks(rows, edges, coords, rolling.RollingOptions())
        # The real producer of this Wait must remain reachable even when the
        # intermediate Wait has no cross-iteration semantic label.
        middle = deepcopy(next(r for r in rows if r['_graph_id'] == 'i5p2'))
        middle.update(_graph_id='intermediate', _stream_id=77, event='', phase='', algorithm='',
                      _stop=5044, _stop_order=Decimal(5044))
        rows.append(middle)
        record = next(r for r in rows if r['_graph_id'] == 'i5p1')
        producer = deepcopy(record)
        producer['_graph_id'] = 'middle-producer'
        rows.append(producer)
        record.update(_start=5044, _stop=5044.001, _start_order=Decimal(5044), _stop_order=Decimal('5044.001'))
        incoming = next(e for e in edges if e['edge_id'] == 'i5e0')
        incoming['dst'] = 'middle-producer'
        edges.append(dict(edge_id='middle-to-record', src='intermediate', dst='i5p1',
                          kind='direct_stream_order_observed', confidence='observed'))
        target = next(r for r in rows if r['_graph_id'] == 'i5p2')
        target.update(_stop=5044.1, _stop_order=Decimal('5044.1'))
        edges.append(dict(edge_id='middle-pair', src='middle-producer', dst='intermediate',
                          kind='direct_notify_sync_exact', confidence='exact'))
        unknown = dict(next(t for t in tasks if t['graph_id'] == 'i5p2'), graph_id='intermediate',
                       comparison_status='unannotated_task_location', reference_count=0,
                       duration_slow=False, start_late=None, gap_slow=False)
        tasks.append(unknown)
        tasks.append(dict(next(t for t in tasks if t['graph_id'] == 'i5p1'), graph_id='middle-producer'))
        before = deepcopy((rows, edges))
        roots, traces = wait_backtrace.trace_sources(rows, edges, tasks, rolling.RollingOptions())
        trace = next(t for t in traces if t['wait_graph_id'] == 'i5p2')
        self.assertTrue(any('notify_wait_not_comparable:' in b['reason'] for b in trace['boundaries']))
        self.assertTrue(any(r['graph_id'] == 'i5p0' for r in roots))
        self.assertEqual((rows, edges), before)

    def test_early_call_start_does_not_cut_a_real_upstream_overrun(self):
        rows, edges, coords, _ = capture(execution_delay=True)
        for i in range(6):
            base = i * 1000
            shift = 200 if i < 5 else 0
            for row in rows[i * 4:i * 4 + 4]:
                for key in ("_start", "_stop", "_start_order", "_stop_order"):
                    row[key] += shift
            anchor = deepcopy(rows[i * 4])
            anchor.update(_graph_id="origin-{}".format(i), _stream_id=99, event="independent_origin",
                          _start=base, _stop=base + 1, _duration=1,
                          _start_order=Decimal(base), _stop_order=Decimal(base + 1))
            rows.append(anchor)
        report = rolling.analyze(rows, edges, coords)
        record = next(t for t in report["tasks"] if t["graph_id"] == "i5p1")
        self.assertFalse(record["start_late"])
        self.assertFalse(record["duration_slow"])
        root = next(r for r in report["root_causes"] if r["graph_id"] == "i5p0")
        self.assertEqual(root["graph_id"], "i5p0")
        self.assertEqual(root["evidence_paths"]["i5p2"], ["i5e0", "i5e1"])

    def clocks(self, offset=0):
        models = [DeviceClock("run/node0", device, offset if device == 0 else 0,
                              0, 0, 1, 1, 0, 10**9, 1000) for device in (0, 1)]
        return dict(schema_version=3, status="network_probe_estimate", capture_id="run",
                    models=[asdict(model) for model in models],
                    profiler_calibrations=[dict(node_id="node0", device_id=device, metadata_quantization_ns=1000)
                                           for device in (0, 1)])

    def test_record_can_release_before_its_profiled_execution_ends(self):
        rows, edges, coords, _ = capture(execution_delay=True)
        record = next(r for r in rows if r["_graph_id"] == "i5p1")
        record.update(_stop=5043.2, _stop_order=Decimal("5043.2"), _duration=.2)
        before = deepcopy((rows, edges))
        original = rolling.analyze(rows, edges, coords)
        changed = rolling.analyze(rows, edges, coords, rolling.RollingOptions(calibrated_release_intervals=True),
                                  alignment=self.clocks())
        self.assertIsNone(original["primary_source_candidate_id"])
        self.assertTrue(changed["root_causes"])
        self.assertEqual((rows, edges), before)
        checks = [c for t in changed["wait_backtraces"] for c in t["release_checks"]]
        self.assertTrue(any(c["timing_status"] == "producer_release_interval_compatible" for c in checks))
        from .source_propagation import build_report
        root = next(r for r in changed["root_causes"] if r["graph_id"] == "i5p0")
        report = build_report(rows, edges, [root], changed["tasks"])
        self.assertEqual(report["candidates"][0]["chains"][0]["hops"][-1]["timing_status"],
                         "producer_release_interval_compatible")
        self.assertEqual(report["candidates"][0]["chains"][0]["status"], "complete_with_timing_limits")

    def test_device_start_offsets_are_removed_for_same_node_release_checks(self):
        rows, edges, coords, _ = capture(execution_delay=True)
        for row in rows:
            if row["_device_id"] == 0:
                for key in ("_start", "_stop", "_start_order", "_stop_order"):
                    row[key] += 5
        changed = rolling.analyze(rows, edges, coords, rolling.RollingOptions(calibrated_release_intervals=True),
                                  alignment=self.clocks(offset=5000))
        self.assertTrue(changed["root_causes"])

    def test_calibrated_mode_does_not_force_a_truly_incompatible_release(self):
        rows, edges, coords, _ = capture(execution_delay=True)
        record = next(r for r in rows if r["_graph_id"] == "i5p1")
        record.update(_start=5060, _stop=5061, _start_order=Decimal(5060), _stop_order=Decimal(5061), _duration=1)
        changed = rolling.analyze(rows, edges, coords, rolling.RollingOptions(calibrated_release_intervals=True),
                                  alignment=self.clocks())
        self.assertIsNone(changed["primary_source_candidate_id"])
        self.assertIn("incompatible_notify_timestamps", changed["coverage"]["boundary_reason_counts"])

    def test_cross_call_order_is_kept_without_creating_an_edge(self):
        rows, edges, coords = cross_call_capture()
        before = deepcopy(edges)
        report = rolling.analyze(rows, edges, coords)
        root = next(r for r in report["root_causes"] if r["graph_id"] == "i5p0")
        self.assertEqual(root["graph_id"], "i5p0")
        self.assertEqual(root["operation_scope"], "op-5-0")
        self.assertEqual(root["evidence_paths"]["i5p2"], ["i5e0", "i5e1"])
        self.assertEqual(edges, before)
        trace = next(t for t in report["wait_backtraces"] if t["wait_graph_id"] == "i5p2")
        self.assertEqual(trace["status"], "source_candidates_found")

    def test_normal_execution_that_starts_late_is_not_the_root(self):
        rows, edges, coords, _ = capture(execution_delay=True)
        for i in range(6):
            source, record, wait, tail = rows[i * 4:(i + 1) * 4]
            middle = deepcopy(source)
            middle.update(_graph_id="middle-{}".format(i), _task_id=100 + i, event="forward_copy",
                          _start_order=Decimal(str(source["_stop"])), _stop_order=Decimal(str(source["_stop"])) + 1,
                          _start=source["_stop"], _stop=source["_stop"] + 1, _duration=1)
            for row in (record, tail):
                for key in ("_start", "_stop"):
                    row[key] += 1
                row["_start_order"] += 1
                row["_stop_order"] += 1
            wait["_stop"] += 1
            wait["_stop_order"] += 1
            wait["_duration"] += 1
            rows.append(middle)
            old = next(e for e in edges if e["edge_id"] == "i{}e0".format(i))
            old["dst"] = middle["_graph_id"]
            edges.append(dict(old, src=middle["_graph_id"], dst=record["_graph_id"], edge_id="middle-record-{}".format(i)))
        report = rolling.analyze(rows, edges, coords)
        middle = next(t for t in report["tasks"] if t["graph_id"] == "middle-5")
        self.assertTrue(middle["start_late"])
        self.assertFalse(middle["duration_slow"])
        root = next(r for r in report["root_causes"] if r["graph_id"] == "i5p0")
        self.assertEqual(root["graph_id"], "i5p0")
        self.assertIn("middle-record-5", root["evidence_paths"]["i5p2"])

    def test_signal_already_recorded_stops_at_residual_wait_boundary(self):
        rows, edges, coords, _ = capture(execution_delay=True)
        wait = next(r for r in rows if r["_graph_id"] == "i5p2")
        wait.update(_start=5050, _stop=5100, _duration=50, _start_order=Decimal(5050), _stop_order=Decimal(5100))
        tail = next(r for r in rows if r["_graph_id"] == "i5p3")
        tail.update(_start=5100, _stop=5100.2, _duration=.2, _start_order=Decimal(5100), _stop_order=Decimal("5100.2"))
        report = rolling.analyze(rows, edges, coords)
        self.assertIsNone(report["primary_source_candidate_id"])
        self.assertGreater(report["coverage"]["boundary_reason_counts"]["signal_precedes_wait_start"], 0)

    def test_incompatible_notify_time_is_not_repaired(self):
        rows, edges, coords, _ = capture(execution_delay=True)
        record = next(r for r in rows if r["_graph_id"] == "i5p1")
        record.update(_start=5044, _stop=5045, _duration=1, _start_order=Decimal(5044), _stop_order=Decimal(5045))
        report = rolling.analyze(rows, edges, coords)
        self.assertIsNone(report["primary_source_candidate_id"])
        self.assertIn("incompatible_notify_timestamps", report["coverage"]["boundary_reason_counts"])

    def test_incompatible_stream_order_is_not_traversed(self):
        rows, edges, coords, _ = capture(execution_delay=True)
        record = next(r for r in rows if r["_graph_id"] == "i5p1")
        record.update(_start=5042, _stop=5042.001, _duration=.001,
                      _start_order=Decimal(5042), _stop_order=Decimal("5042.001"))
        report = rolling.analyze(rows, edges, coords)
        self.assertIsNone(report["primary_source_candidate_id"])
        self.assertIn("incompatible_stream_order_timestamps", report["coverage"]["boundary_reason_counts"])

    def test_tied_slow_paths_keep_both_sources(self):
        rows, edges, coords, _ = capture(execution_delay=True)
        extra_rows = []
        for row in rows:
            copy = deepcopy(row)
            copy.update(_graph_id=row["_graph_id"] + "b", _user_rank=row["_user_rank"] + 2, _device_id=row["_device_id"] + 2)
            extra_rows.append(copy)
        rows.extend(extra_rows)
        edges.extend(dict(e, src=e["src"] + "b", dst=e["dst"] + "b", edge_id=e["edge_id"] + "b") for e in list(edges))
        report = rolling.analyze(rows, edges, coords)
        sources = report["root_causes"]
        self.assertEqual({r["graph_id"] for r in sources}, {"i5p0", "i5p0b"})

    def test_ambiguous_notify_producers_stay_a_boundary(self):
        rows, edges, coords, _ = capture(execution_delay=True)
        for i in range(6):
            extra = deepcopy(next(r for r in rows if r["_graph_id"] == "i{}p1".format(i)))
            extra.update(_graph_id="extra-record-{}".format(i), _stream_id=99, _task_id=999 + i, event="other_record")
            rows.append(extra)
        edges.append(dict(next(e for e in edges if e["edge_id"] == "i5e1"), src="extra-record-5", edge_id="ambiguous"))
        report = rolling.analyze(rows, edges, coords)
        self.assertIsNone(report["primary_source_candidate_id"])
        self.assertIn("ambiguous_notify_producers", report["coverage"]["boundary_reason_counts"])

    def test_traversal_limit_is_explicit_and_does_not_claim_a_source(self):
        rows, edges, coords, _ = capture(execution_delay=True)
        report = rolling.analyze(rows, edges, coords, rolling.RollingOptions(traversal_limit=1))
        self.assertIsNone(report["primary_source_candidate_id"])
        self.assertGreater(report["coverage"]["truncated_wait_backtrace_count"], 0)

    def test_coverage_separates_missing_semantics_from_healthy_tasks(self):
        rows, edges, coords, _ = capture(execution_delay=True)
        next(r for r in rows if r["_graph_id"] == "i5p0")["algorithm"] = ""
        report = rolling.analyze(rows, edges, coords)
        self.assertIsNone(report["primary_source_candidate_id"])
        self.assertIn("unannotated_task_location", report["coverage"]["comparison_status_counts"])

    def test_remote_clock_is_not_subtracted(self):
        rows, edges, coords, _ = capture(execution_delay=True)
        for row in rows:
            if row["_user_rank"] == 0:
                row["_node_id"] = "remote/node0"
                row["_start_order"] += 1000000000
                row["_stop_order"] += 1000000000
                row["_start"] += 1000000000
                row["_stop"] += 1000000000
        for edge in edges:
            if "notify_sync" in edge["kind"]:
                edge.update(kind="cross_node_notify_sync_observed", confidence="observed")
        report = rolling.analyze(rows, edges, coords)
        self.assertFalse(report["root_causes"])
        self.assertTrue(any(c["timing_status"] == "uncalibrated_cross_node_boundary" for t in report["wait_backtraces"] for c in t["release_checks"]))


if __name__ == "__main__":
    unittest.main()
