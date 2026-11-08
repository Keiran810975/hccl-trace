from __future__ import annotations

from copy import deepcopy
import unittest

from .parallel_sources import work_units as execution_calls, execution_calls as corroborated_calls, qualify_call_spans, select_all_calls_prototype as select
from .test_local_slow_clusters import history
from .test_significant_regions import task, edge


def observed(values):
    tasks = history(values)
    for t in tasks:
        t["reference_iterations"] = list(range(t["iteration"] - 5, t["iteration"])) if t["reference_count"] == 5 else []
    return tasks


class ParallelSourceTests(unittest.TestCase):
    def test_whole_call_elapsed_growth_is_required_besides_intrinsic_task_growth(self):
        regions, _ = execution_calls(observed([task("a"), task("b")]))
        region = regions[0]
        keys = [(region["node_id"], region["device_id"], region["user_rank"], scope)
                for scope in region["reference_operation_scopes"]]
        current = (region["node_id"], region["device_id"], region["user_rank"], region["operation_scope"])
        spans = {key: (i * 10000, i * 10000 + duration) for i, (key, duration) in enumerate(zip(keys, [980, 990, 1000, 1010, 1020]))}
        spans[current] = (90000, 91010)
        self.assertFalse(qualify_call_spans(regions, spans)[0])
        spans[current] = (90000, 91050)
        self.assertEqual(len(qualify_call_spans(regions, spans)[0]), 1)
        del spans[keys[0]]
        self.assertEqual(qualify_call_spans(regions, spans)[1][0]["reason"], "missing_full_call_envelope")

    def test_call_envelopes_keep_the_same_mad_gate_and_local_owner(self):
        regions, _ = execution_calls(observed([task("a"), task("b")]))
        r = regions[0]
        spans = {(r["node_id"], r["device_id"], r["user_rank"], scope): (0, duration)
                 for scope, duration in zip(r["reference_operation_scopes"], [600, 800, 1000, 1200, 1400])}
        spans[(r["node_id"], r["device_id"], r["user_rank"], r["operation_scope"])] = (0, 1500)
        selected, decisions = qualify_call_spans(regions, spans)
        self.assertFalse(selected)
        self.assertEqual(decisions[0]["reference_mad_ns"], "200")

    def test_two_different_calls_remain_peers_even_with_very_different_magnitudes(self):
        values = observed([task("a"), task("b"), task("c", stop=1000, operation="other"),
                           task("d", stop=2000, operation="other")])
        # The history fixture uses one operation name; retain distinct call identity.
        for t in values:
            if t["graph_id"].startswith(("c-history", "d-history")):
                t["operation_scope"] += "-other"
        before = deepcopy(values)
        regions, _ = execution_calls(values)
        self.assertEqual({r["operation_scope"] for r in regions}, {"op", "other"})
        self.assertEqual(values, before)

    def test_tiny_high_ratio_tasks_do_not_outvote_the_full_work_population(self):
        values = observed([task("tiny-a", stop=100, mean="1"), task("tiny-b", stop=100, mean="1"),
                           task("normal", stop=100000, mean="100000")])
        regions, decisions = execution_calls(values)
        self.assertFalse(regions)
        self.assertEqual(decisions[0]["reason"], "whole_call_work_not_slow")

    def test_one_extreme_task_is_an_observation_not_a_coherent_multi_task_call(self):
        regions, decisions = execution_calls(observed([task("a", stop=1000)]))
        self.assertFalse(regions)
        self.assertEqual(decisions[0]["reason"], "isolated_task_not_coherent_call_slowdown")

    def test_a_normal_algorithm_phase_does_not_dilute_another_slow_phase(self):
        a, b, normal = task("a"), task("b"), task("normal", stop=100000, mean="100000")
        a["phase"] = b["phase"] = "reduce_scatter"
        normal["phase"] = "allgather"
        regions, _ = execution_calls(observed([a, b, normal]))
        self.assertEqual(len(regions), 1)
        self.assertEqual(regions[0]["preliminary_graph_ids"], ["a", "b"])

    def test_missing_or_reused_history_is_not_filled_by_ordinal_or_time(self):
        for change in ("missing", "reused", "wrong-iteration", "foreign-position", "extra-work"):
            values = observed([task("a"), task("b")])
            a, b = values[:2]
            if change == "missing":
                a["reference_graph_ids"][0] = "absent"
            elif change == "reused":
                b["reference_graph_ids"][0] = a["reference_graph_ids"][0]
            elif change == "wrong-iteration":
                values[2]["iteration"] += 1
            elif change == "foreign-position":
                values[2]["bucket"] = 9
            else:
                values.append(dict(values[2], graph_id="extra"))
            if change == "wrong-iteration":
                with self.assertRaises(ValueError):
                    execution_calls(values)
            else:
                self.assertFalse(execution_calls(values)[0], change)

    def test_real_edges_not_temporal_overlap_establish_propagation(self):
        values = observed([task("a"), task("b", start=31, stop=61),
            task("record", "notify_record", start=61, stop=62, mean="1"),
            task("wait", "notify_wait", start=20, stop=63, mean="20", rank=1)])
        report = dict(tasks=values, root_causes=[], options=dict(slowdown_factor="1.5", mad_multiplier="3"))
        from .significant_regions import analyze_selected_tasks, RegionOptions
        regions, _ = execution_calls(values)
        roots = [t for t in values if t["graph_id"] in {"a", "b"}]
        self.assertFalse(analyze_selected_tasks(values, [], roots, regions, RegionOptions())["chains"])
        result = analyze_selected_tasks(values, [edge("b", "record"), edge("record", "wait", True)], roots, regions, RegionOptions())
        self.assertEqual(result["chains"][0]["edge_ids"], ["b-record", "record-wait"])

    def test_warmup_future_or_incomplete_calls_do_not_create_references(self):
        values = observed([task("a"), task("b")])
        values[2]["stage"] = "warmup"
        self.assertFalse(execution_calls(values)[0])

    def test_repeated_public_calls_need_a_new_alarm_epoch_not_chronic_jitter(self):
        from .source_events import statistics
        values, lookup = [], {}
        for iteration in range(16):
            for call in range(3):
                for slot in range(2):
                    key = "{}-{}-{}".format(iteration, call, slot)
                    row = task(key, stop=30 if iteration == 12 else 10, operation="op-{}-{}".format(iteration, call))
                    refs = [lookup[(i, call, slot)] for i in range(iteration - 5, iteration)] if iteration >= 5 else []
                    mean, mad = statistics([r["duration_ns"] for r in refs]) if refs else (0, 0)
                    row.update(iteration=iteration, block=0, bucket=call, reference_count=len(refs),
                        reference_graph_ids=[r["graph_id"] for r in refs], reference_iterations=[r["iteration"] for r in refs],
                        reference_mean_ns=str(mean), reference_mad_ns=str(mad))
                    lookup[(iteration, call, slot)] = row
                    values.append(row)
        regions, decisions = corroborated_calls(values)
        self.assertEqual({r["iteration"] for r in regions}, {12})
        self.assertEqual(len(regions), 3)
        self.assertEqual(regions[0]["burst_evidence"]["reference_work_sums_ns"], [60] * 5)
        report = dict(tasks=values, root_causes=[], options=dict(slowdown_factor="1.5", mad_multiplier="3"))
        chosen, decision = select(report, [])
        self.assertEqual(len(chosen["root_causes"]), 6)
        self.assertIsNone(chosen["primary_source_candidate_id"])
        self.assertEqual(decision["candidate_relationship"], "parallel")
        record = task("signal", "notify_record", start=31, stop=32, mean="1", operation="op-12-0")
        wait = task("peer-wait", "notify_wait", start=20, stop=63, mean="20", operation="op-12-0", rank=1)
        record["iteration"] = wait["iteration"] = 12
        supported = dict(report, tasks=values + [record, wait])
        chosen, decision = select(supported, [edge("12-0-1", "signal"), edge("signal", "peer-wait", True)])
        self.assertEqual(len(chosen["root_causes"]), 6)
        source = next(r for r in chosen["root_causes"] if r["graph_id"] == "12-0-1")
        self.assertEqual(source["evidence_paths"]["peer-wait"], ["12-0-1-signal", "signal-peer-wait"])
        before = deepcopy((values, regions))
        self.assertEqual(corroborated_calls(values)[0], regions)
        self.assertEqual((values, regions), before)


if __name__ == "__main__":
    unittest.main()
