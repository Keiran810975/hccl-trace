from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict
import unittest

from .clock_alignment import DeviceClock
from .local_slow_clusters import analyze
from .multinode_source_refinement import refine, transfer_progress, validate_protocol_witnesses, _burst_context
from .test_local_slow_clusters import fork


def fixture(*, delayed=True, call_count=3):
    segments = []
    for iteration in range(8):
        for call in range(call_count):
            key = "transfer-{}-{}".format(iteration, call)
            start = iteration * 1000 + call * 100 + 50
            duration = 500 if delayed and iteration == 7 else 20
            segments.append(dict(transfer_id=key, payload_graph_id=key + "-payload",
                sender_node_id="a", sender_rank=0, sender_device_id=0, sender_stream_id=2, sender_task_id=iteration * 10 + call,
                receiver_node_id="b", receiver_rank=1, receiver_device_id=1, operation_scope=key + "-op",
                phase="allgather", step="0", payload_size_bytes=1024, submission_start_ns=start, submission_stop_ns=start + 1,
                protocol_stop_ns=start + duration, protocol_duration_ns=duration + 30, completion_graph_id=key + "-done",
                status="protocol_interval_observed", evidence_node_ids=[key + "-ready", key + "-payload", key + "-done"],
                evidence_edge_ids=[key + "-first", key + "-last"], stage="measured", iteration=iteration,
                reference_count=5 if iteration >= 5 else 0, call_site="site-" + str(call), occurrence=0,
                reference_iterations=list(range(iteration - 5, iteration)) if iteration >= 5 else [],
                reference_transfer_ids=["transfer-{}-{}".format(i, call) for i in range(iteration - 5, iteration)] if iteration >= 5 else []))
    clocks = [DeviceClock("a", 0, 0, 0, 0, 1, 1, 0, 100000, 1),
              DeviceClock("b", 1, 0, 0, 0, 1, 1, 0, 100000, 1)]
    alignment = dict(schema_version=3, status="network_probe_estimate", models=list(map(asdict, clocks)))
    execution = dict(candidates=[], deferred_candidates=[], regions=[])
    selection = dict(options=dict(source_factor="1.5", mad_multiplier="3"),
                     execution_proposal=execution, external_host_observations=[])
    return selection, segments, alignment


class MultiNodeRefinementTests(unittest.TestCase):
    def test_burst_context_uses_past_call_cadence_not_foreign_groups_or_future_records(self):
        group = dict(node_id="n", user_rank=0, device_id=2, iteration=15, start_ns=15060, stop_ns=15080,
                     preliminary_graph_ids=["source"], preliminary_count=1)
        source = dict(node_id="n", user_rank=0, device_id=2, group_id="dp", iteration=15,
                      observed_start_ns=15060, observed_stop_ns=15080)
        candidates = dict(source=source, neighbour=dict(source, observed_start_ns=15090, observed_stop_ns=15100),
                          foreign=dict(source, group_id="other"), distant=dict(source, observed_start_ns=19000, observed_stop_ns=19010))
        segments = [dict(status="protocol_interval_observed", stage="measured", receiver_node_id="n", receiver_rank=0,
            receiver_device_id=2, group_id="dp", iteration=i, call_site="site-" + str(j), occurrence=0,
            protocol_start_ns=i * 1000 + j * 100, protocol_stop_ns=i * 1000 + j * 100 + 20)
            for i in range(10, 15) for j in range(2)]
        before = deepcopy((group, candidates, segments))
        context = _burst_context(group, candidates, segments)
        self.assertEqual(context["radius_ns"], 100)
        self.assertEqual(context["neighbour_count"], 1)
        self.assertEqual((group, candidates, segments), before)
        self.assertEqual(context, _burst_context(group, candidates, segments + [dict(segments[-1], iteration=16, protocol_start_ns=1)]))
        self.assertEqual(_burst_context(dict(group, iteration=7), candidates, segments)["multiplier"], "1")

    def test_readiness_delay_is_not_relabelled_as_network_transfer(self):
        selection, segments, alignment = fixture(delayed=False)
        for item in segments:
            if item["iteration"] == 7:
                item["protocol_duration_ns"] += 1000000
        result = refine(selection, segments, alignment)
        self.assertFalse(result["candidates"])
        self.assertTrue(result["protocol_symptoms_are_not_roots"])

    def test_multiple_calls_beyond_clock_error_support_an_outgoing_progress_cohort(self):
        selection, segments, alignment = fixture()
        before = deepcopy((selection, segments, alignment))
        result = refine(selection, segments, alignment, witness_signatures={r["transfer_id"]: ("same original path roles",) for r in segments})
        self.assertEqual(result["selected_mechanism"], "unlocalized")
        self.assertFalse(result["candidates"])
        self.assertEqual(len(result["outgoing_path_candidates"]), 3)
        for root in result["outgoing_path_candidates"]:
            self.assertEqual(root["source_unit"], "submission_to_notification_interval")
            self.assertEqual(root["duration_ns"], root["observed_stop_ns"] - root["observed_start_ns"])
            self.assertEqual(root["reference_iterations"], [2, 3, 4, 5, 6])
            self.assertEqual(root["physical_cause"], "unknown")
        self.assertEqual((selection, segments, alignment), before)

    def test_original_witness_direction_time_and_unique_producer_are_required(self):
        from .test_cross_node_diagnosis import capture
        from . import rdma_timing, cross_node_diagnosis
        from .rolling_diagnosis import RollingOptions
        rows, edges, coords = capture()
        segments = cross_node_diagnosis.analyze(rdma_timing.analyze(rows, edges), rows, edges, coords, RollingOptions())["segments"]
        self.assertEqual(len(validate_protocol_witnesses(segments, rows, edges)), 8)
        forged = deepcopy(segments)
        forged[0]["submission_start_ns"] += 1
        with self.assertRaises(ValueError):
            validate_protocol_witnesses(forged, rows, edges)
        with self.assertRaises(ValueError):
            validate_protocol_witnesses(segments, rows, edges + [dict(edges[-1], edge_id="other-producer")])

    def test_isolated_protocol_outlier_stays_a_symptom(self):
        selection, segments, alignment = fixture(call_count=1)
        self.assertFalse(refine(selection, segments, alignment)["candidates"])

    def test_clock_uncertainty_and_missing_calibration_do_not_get_ignored(self):
        selection, segments, alignment = fixture()
        alignment["models"][1]["estimated_error_ns"] = 1000
        self.assertFalse(refine(selection, segments, alignment)["candidates"])
        self.assertFalse(refine(selection, segments, None)["candidates"])

    def test_isolated_execution_without_propagation_is_still_eligible(self):
        from .test_local_slow_clusters import history
        from .test_significant_regions import task
        selection, _, _ = fixture()
        selection["execution_proposal"] = analyze(history([task("work")]), [])
        result = refine(selection, [], None)
        self.assertEqual(result["selected_mechanism"], "communication_execution_growth")
        self.assertEqual(len(result["candidates"]), 1)
        self.assertFalse(result["candidates"][0]["affected_wait_graph_ids"])

    def test_resource_coherence_does_not_let_an_extreme_protocol_ratio_erase_sources(self):
        selection, segments, alignment = fixture(call_count=1)
        values, edges = fork()
        selection["execution_proposal"] = analyze(values, edges)
        for item in segments:
            if item["iteration"] == 7:
                item["protocol_stop_ns"] += 90000
        result = refine(selection, segments, alignment)
        self.assertEqual(result["selected_mechanism"], "communication_execution_growth")
        self.assertEqual(len(result["candidates"]), 3)
