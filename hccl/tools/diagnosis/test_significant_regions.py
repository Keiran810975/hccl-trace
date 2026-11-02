from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
import unittest

from .significant_regions import RegionOptions, analyze, select_regions, slow


def task(key, kind="sdma", start=0, stop=30, mean="10", operation="op", rank=0):
    return dict(graph_id=key, node_id="node0", user_rank=rank, device_id=rank,
        stream_id=0, task_id=key, operation_scope=operation, stage="measured", iteration=5,
        task_kind=kind, task_domain="hccl_internal", reference_count=5,
        reference_mean_ns=mean, reference_mad_ns="0", duration_ns=stop-start,
        observed_start_ns=start, observed_stop_ns=stop,
        slowdown_factor=str((stop-start)/float(mean)), delta_ns=str(stop-start-float(mean)))


def edge(a, b, sync=False):
    return dict(edge_id=a+"-"+b, src=a, dst=b,
        kind="local_notify_sync_exact" if sync else "direct_stream_order_observed",
        confidence="exact" if sync else "observed")


class SignificantRegionTests(unittest.TestCase):
    def test_secondary_is_150_percent_increase_not_150_percent_total(self):
        values = [task("a", stop=30), task("b", stop=20, operation="other")]
        _, regions = select_regions(values)
        self.assertEqual({r["operation_scope"] for r in regions if r["selected"]}, {"op"})
        self.assertEqual(RegionOptions().secondary_factor, "2.5")

    def test_similar_and_above_secondary_regions_are_retained(self):
        values = [task("a", stop=100), task("b", stop=92, operation="b"),
                  task("c", stop=30, operation="c"), task("d", stop=16, operation="d")]
        _, regions = select_regions(values)
        self.assertEqual({r["operation_scope"] for r in regions if r["selected"]}, {"op", "b", "c"})

    def test_reference_duration_weights_not_tiny_helper_ratio(self):
        _, regions = select_regions([task("a", stop=200, mean="100"), task("b", stop=10, mean="1")])
        self.assertEqual(regions[0]["reference_sum_ns"], "101")
        self.assertTrue(1 < float(regions[0]["mean_increase"]) < 1.1)

    def test_zero_reference_is_not_given_infinite_priority(self):
        value = task("zero")
        value.update(reference_mean_ns="0", slowdown_factor=None)
        _, regions = select_regions([value])
        self.assertFalse(regions[0]["selected"])
        self.assertEqual(regions[0]["selection_reasons"], ["zero_reference_cannot_rank"])

    def test_full_population_suppresses_selection_on_a_tiny_outlier(self):
        values = [task("tiny", stop=100, mean="1"), task("normal", stop=100000, mean="100000"),
                  task("coherent", stop=300, mean="100", operation="other")]
        _, regions = select_regions(values, replace(RegionOptions(), score_population="all_comparable_work"))
        self.assertEqual({r["operation_scope"] for r in regions if r["selected"]}, {"other"})
        self.assertEqual(next(r for r in regions if r["operation_scope"] == "op")["score_population_count"], 2)

    def test_range_spans_the_public_call_not_only_its_slow_tasks(self):
        _, regions = select_regions([task("slow", start=100, stop=130), task("normal", start=0, stop=10)])
        self.assertEqual((regions[0]["start_ns"], regions[0]["stop_ns"]), (0, 130))

    def test_no_slow_wait_is_needed_to_admit_execution_source(self):
        report = analyze([task("copy")], [])
        self.assertEqual(report["summary"]["execution_candidate_count"], 1)
        self.assertFalse(report["candidates"][0]["affected_wait_graph_ids"])

    def test_twenty_percent_propagation_and_upstream_exclusion(self):
        values = [task("copy", stop=30), task("record", "notify_record", start=30, stop=31, mean="1"),
                  task("wait", "notify_wait", start=10, stop=35, mean="20", rank=1)]
        edges = [edge("copy", "record"), edge("record", "wait", True)]
        before = deepcopy((values, edges))
        report = analyze(values, edges)
        self.assertEqual(report["summary"]["propagation_chain_count"], 1)
        self.assertEqual(report["chains"][0]["edge_ids"], ["copy-record", "record-wait"])
        self.assertEqual((values, edges), before)
        strict = analyze(values, edges, replace(RegionOptions(), propagation_factor="1.5"))
        self.assertEqual(strict["summary"]["propagation_chain_count"], 0)

    def test_slow_wait_in_selected_region_explained_by_actual_upstream(self):
        values = [task("copy", stop=30), task("record", "notify_record", start=30, stop=31, mean="1"),
                  task("wait", "notify_wait", start=1, stop=32, mean="10")]
        report = analyze(values, [edge("copy", "record"), edge("record", "wait", True)])
        self.assertEqual(report["summary"]["upstream_explained_wait_count"], 1)
        self.assertEqual(report["summary"]["candidate_count"], 1)

    def test_unexplained_wait_is_uncertain_candidate_not_hidden(self):
        values = [task("copy"), task("wait", "notify_wait", start=1, stop=100, mean="10")]
        report = analyze(values, [])
        self.assertEqual(report["summary"]["unexplained_wait_candidate_count"], 1)
        self.assertEqual(report["candidates"][-1]["status"], "unexplained_wait_candidate")

    def test_order_alone_does_not_explain_another_execution_overrun(self):
        values = [task("a"), task("b", start=30, stop=60)]
        report = analyze(values, [edge("a", "b")])
        self.assertEqual(report["summary"]["execution_candidate_count"], 2)
        self.assertTrue(all(not c["upstream_explained"] for c in report["candidates"]))

    def test_incompatible_clock_and_short_wait_are_not_forced_through(self):
        values = [task("copy"), task("record", "notify_record", start=30, stop=31, mean="1"),
                  task("wait", "notify_wait", start=1, stop=29, mean="10", rank=1)]
        report = analyze(values, [edge("copy", "record"), edge("record", "wait", True)])
        self.assertFalse(report["chains"])
        self.assertEqual(report["summary"]["boundary_counts"]["incompatible_notify_timestamps"], 1)

    def test_mad_history_and_future_boundary_unchanged(self):
        value = task("a", stop=20)
        value["reference_mad_ns"] = "4"
        self.assertFalse(slow(value, "1.5", RegionOptions()))
        value["reference_count"] = 4
        self.assertFalse(slow(value, "1.2", RegionOptions()))
        with self.assertRaises(ValueError):
            RegionOptions(propagation_factor="2").validate()


if __name__ == "__main__":
    unittest.main()
