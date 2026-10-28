from __future__ import annotations

import unittest

from test.audit_single_node_injection_effects import copy_ratios, delay_pairs, fully_inside, kernel_medians, ns


def node(key, rank, start, stop, kind="sdma", size="64"):
    return dict(id=key, nodeKind="execution", rank=rank, relativeStart=start, relativeStop=stop,
                duration=stop - start, taskKind=kind, algorithm="ring", phase="allgather", step="0",
                event="copy_start", semantic="copy", sizeBytes=size, operationScope="op0")


class RetainedEffectAuditTests(unittest.TestCase):
    def test_local_times_are_not_rounded_to_repair_fractional_nanoseconds(self):
        self.assertEqual(ns(node("a", 0, 1.001, 2), "start"), 1001)
        with self.assertRaises(ValueError):
            ns(node("a", 0, 1.0001, 2), "start")

    def test_only_complete_active_tasks_enter_duration_distribution(self):
        self.assertTrue(fully_inside(node("a", 0, 10, 12), 10000, 20000))
        self.assertFalse(fully_inside(node("a", 0, 9, 12), 10000, 20000))
        self.assertFalse(fully_inside(node("a", 0, 19, 21), 10000, 20000))

    def test_copy_reference_does_not_mix_rank_bytes_or_future_samples(self):
        nodes = [node("before", 0, 0, 1), node("before-other-size", 0, 0, 10, size="128"),
                 node("active", 0, 10, 12), node("other-rank", 1, 12, 14),
                 node("future", 0, 25, 35)]
        result = copy_ratios(nodes, 10000, 20000)
        self.assertEqual(set(result), {0})
        self.assertEqual(result[0]["median_normalized_duration"], 2)
        self.assertEqual(result[0]["active_task_count"], 1)
        self.assertEqual(result[0]["minimum_reference_count_per_cohort"], 1)

    def test_kernel_metric_is_an_explicit_type_distribution(self):
        nodes = [node("a", 0, 0, 3, "kernel_mix_aic"), node("b", 0, 4, 9, "kernel_mix_aic"),
                 node("not-kernel", 0, 0, 100)]
        result = kernel_medians(nodes)
        self.assertEqual(result, {0: dict(median_us=4, count=2)})

    def test_notify_timestamp_incompatibility_is_reported_not_fixed(self):
        src = node("r", 0, 121, 121.1, "notify_record")
        dst = node("w", 1, 20, 121.05, "notify_wait")
        value = dict(nodes=[src, dst], edges=[dict(id="e", src="r", dst="w", kind="direct_notify_sync_exact", confidence="exact")])
        pairs = delay_pairs(value, "op0", 0, 10000, 120000)
        self.assertEqual(len(pairs), 1)
        self.assertFalse(pairs[0]["endpoint_timing_compatible"])
        self.assertEqual(pairs[0]["window_wait_overlap_ms"], .1)
        self.assertEqual(dst["relativeStop"], 121.05)

    def test_wait_outside_injection_is_not_window_blocking_evidence(self):
        src = node("r", 0, 121, 121.1, "notify_record")
        dst = node("w", 1, 120.5, 121.2, "notify_wait")
        value = dict(nodes=[src, dst], edges=[dict(id="e", src="r", dst="w", kind="direct_notify_sync_exact", confidence="exact")])
        self.assertEqual(delay_pairs(value, "op0", 0, 10000, 120000), [])


if __name__ == "__main__":
    unittest.main()
