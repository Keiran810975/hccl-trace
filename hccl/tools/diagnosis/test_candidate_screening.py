from __future__ import annotations

from copy import deepcopy
import unittest

from .candidate_screening import select_candidates, local_wait_impacts
from .task_classifier import INTERNAL


def fixture():
    base = dict(node_id="node", user_rank=0, device_id=3, phase="reduce_scatter", step="1",
                event="reduce", task_kind="reduce_inline", stage="measured")
    history = [dict(base, graph_id="h" + str(i), duration_ns=10 + i, iteration=i) for i in range(5)]
    source = dict(base, graph_id="current", duration_ns=30, iteration=5, reference_count=5,
                  reference_graph_ids=[h["graph_id"] for h in history], reference_iterations=list(range(5)))
    root = dict(source, root_id="root", diagnosis_category=INTERNAL, critical_path_status="observed_model",
                critical_path_slack_ns=0, source_region_id="region-a", ranking_execution_budget_ns="16")
    return [root], history + [source]


class ScreeningTests(unittest.TestCase):
    def test_no_mutation_and_history_does_not_read_labels(self):
        roots, tasks = fixture()
        before = deepcopy((roots, tasks))
        result = select_candidates(roots, tasks, policy="history_envelope")
        self.assertEqual(result["selected_candidate_ids"], ["root"])
        roots[0].update(injection_rank=99, injection_start_ns=0, expected_hit=False)
        self.assertEqual(select_candidates(roots, tasks, policy="history_envelope"), result)
        roots[0] = before[0][0]
        self.assertEqual((roots, tasks), before)

    def test_mean_alarm_inside_old_peak_is_deferred(self):
        roots, tasks = fixture()
        tasks[0]["duration_ns"] = 100
        result = select_candidates(roots, tasks, policy="history_envelope")
        self.assertEqual(result["selected_candidate_count"], 0)
        self.assertEqual(result["decisions"][0]["reason"], "inside_previous_five_envelope")

    def test_history_must_be_complete_unique_past_and_same_location(self):
        for failure in ("missing", "duplicate", "future", "rank", "event", "warmup", "nan"):
            roots, tasks = fixture()
            if failure == "missing":
                tasks.pop(0)
            elif failure == "duplicate":
                tasks[-1]["reference_graph_ids"][0] = "h1"
            elif failure == "future":
                tasks[0]["iteration"] = 6
            elif failure == "warmup":
                tasks[0]["stage"] = "warmup"
            elif failure == "nan":
                tasks[0]["duration_ns"] = "NaN"
            else:
                tasks[0]["user_rank" if failure == "rank" else "event"] = 99
            with self.subTest(failure=failure):
                self.assertFalse(select_candidates(roots, tasks, policy="history_envelope")["selected_candidate_ids"])

    def test_criticality_is_not_positive_gain(self):
        roots, tasks = fixture()
        roots[0]["modeled_execution_gain_ns"] = 0
        self.assertEqual(select_candidates(roots, tasks, policy="critical_path")["selected_candidate_ids"], ["root"])
        roots[0]["critical_path_slack_ns"] = 1
        self.assertFalse(select_candidates(roots, tasks, policy="critical_path")["selected_candidate_ids"])
        roots[0]["critical_path_status"] = "unavailable"
        self.assertEqual(select_candidates(roots, tasks, policy="critical_path")["decisions"][0]["reason"], "local_critical_path_unavailable")

    def test_region_dominance_is_not_unconditional_top_one(self):
        roots, tasks = fixture()
        roots.append(dict(roots[0], root_id="second", graph_id="other", source_region_id="region-b"))
        tasks.append(dict(tasks[-1], graph_id="other"))
        result = select_candidates(roots, tasks, policy="envelope_dominant_region")
        self.assertEqual(result["selected_candidate_count"], 0)
        roots[0]["ranking_execution_budget_ns"] = "48"
        result = select_candidates(roots, tasks, policy="envelope_dominant_region")
        self.assertEqual(result["selected_candidate_ids"], ["root"])
        self.assertEqual(result["original_candidate_count"], 2)
        self.assertEqual(result["deferred_candidate_count"], 1)

    def test_missing_region_zero_budget_and_unknown_policy(self):
        roots, tasks = fixture()
        roots[0].pop("source_region_id")
        self.assertEqual(select_candidates(roots, tasks, policy="envelope_dominant_region")["selected_candidate_count"], 0)
        roots[0].update(source_region_id="r", ranking_execution_budget_ns="0")
        self.assertEqual(select_candidates(roots, tasks, policy="envelope_dominant_region")["selected_candidate_count"], 0)
        with self.assertRaises(ValueError):
            select_candidates(roots, tasks, policy="top_one")

    def test_wait_endpoint_not_unrelated_tail(self):
        from .test_source_events import capture
        from . import rolling_diagnosis as rolling
        from decimal import Decimal
        rows, edges, coords, _ = capture(execution_delay=True)
        for i in range(6):
            extra = deepcopy(rows[i * 4])
            extra.update(_graph_id="irrelevant-" + str(i), _stream_id=99, event="separate_work",
                         _start_order=Decimal(i * 1000), _stop_order=Decimal(i * 1000 + 200),
                         _start=i * 1000, _stop=i * 1000 + 200, _duration=200)
            rows.append(extra)
        report = rolling.analyze(rows, edges, coords)
        roots = [r for r in report["root_causes"] if r["diagnosis_category"] == INTERNAL]
        self.assertEqual(len(roots), 1)
        self.assertGreater(roots[0]["critical_path_slack_ns"], 0)
        result = local_wait_impacts(roots, rows, edges)
        self.assertEqual(result[roots[0]["root_id"]]["max_modeled_wait_gain_ns"], 30000)
        self.assertEqual(select_candidates(roots, report["tasks"], policy="wait_critical_path", wait_impacts=result)["selected_candidate_count"], 1)

    def test_wait_impacts_do_not_time_cross_node_paths_or_missing_edges(self):
        from .test_source_events import capture
        from . import rolling_diagnosis as rolling
        rows, edges, coords, _ = capture(execution_delay=True)
        report = rolling.analyze(rows, edges, coords)
        roots = [r for r in report["root_causes"] if r["diagnosis_category"] == INTERNAL]
        for invalid in ([], [dict(e, kind="cross_node_notify_sync_observed") for e in edges]):
            if invalid:
                next(r for r in rows if r["_graph_id"] == "i5p2")["_node_id"] = "different-node"
            evidence = local_wait_impacts(roots, rows, invalid)
            self.assertEqual(select_candidates(roots, report["tasks"], policy="wait_critical_path", wait_impacts=evidence)["selected_candidate_count"], 0)

    def test_public_result_keeps_deferred_sources_and_paths(self):
        from .test_source_events import capture
        from . import rolling_diagnosis as rolling
        from .result_normalizer import normalize
        rows, edges, coords, _ = capture(execution_delay=True)
        # A real unrelated tail removes call-level criticality, not the evidence.
        from decimal import Decimal
        for i in range(6):
            extra = deepcopy(rows[i * 4])
            extra.update(_graph_id="tail-" + str(i), _stream_id=99, event="tail",
                         _start_order=Decimal(i * 1000), _stop_order=Decimal(i * 1000 + 200),
                         _start=i * 1000, _stop=i * 1000 + 200, _duration=200)
            rows.append(extra)
        report = rolling.analyze(rows, edges, coords, rolling.RollingOptions(candidate_policy="critical_path"))
        public, sources, _ = normalize(report, mode="rolling", run_id="r", rows=rows, edges=edges,
                                      pipeline=dict(status="passed"), binding_evidence={})
        self.assertEqual(public["candidates"], [])
        self.assertEqual(sources, [])
        self.assertIsNone(public["primary_candidate_id"])
        self.assertEqual(public["diagnosis_status"], "candidate_evidence_deferred")
        self.assertEqual(len(public["deferred_communication_source_observations"]), 1)
        self.assertTrue(public["deferred_communication_source_observations"][0]["evidence_paths"])
        self.assertEqual(report["candidate_admission"]["original_candidate_count"], 1)

    def test_default_all_remains_all_and_bad_policy_is_rejected(self):
        from .test_source_events import capture
        from . import rolling_diagnosis as rolling
        from .cli import analyze_capture, DiagnosisError
        rows, edges, coords, _ = capture(execution_delay=True)
        report = rolling.analyze(rows, edges, coords)
        self.assertEqual(report["candidate_admission"]["selected_candidate_count"], 1)
        with self.assertRaises(ValueError):
            rolling.RollingOptions(candidate_policy="cheat").validate()
        with self.assertRaises(DiagnosisError):
            analyze_capture("unused", "unused", mode="baseline", baseline="unused", candidate_policy="critical_path")


if __name__ == "__main__":
    unittest.main()
