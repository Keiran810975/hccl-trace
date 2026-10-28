from __future__ import annotations

from collections import Counter
from contextlib import redirect_stderr, redirect_stdout
from copy import deepcopy
import io
import json
from pathlib import Path
import tempfile
import unittest

from test import single_node_random_suite as suite
from test.evaluate_single_node_diagnosis import main as evaluate_main
from hccl.tools.diagnosis import rolling_diagnosis as rolling
from hccl.tools.diagnosis.test_rolling_diagnosis import repeated


class RandomSingleNodeTests(unittest.TestCase):
    def test_exactly_twenty_anomalies_and_one_normal(self):
        cases = suite.generate_cases()
        self.assertEqual(len(cases), 21)
        self.assertEqual(Counter(c["injection"]["kind"] for c in cases), {"normal": 1, **{k: 5 for k in suite.KINDS}})
        self.assertEqual(len({c["case_id"] for c in cases}), 21)
        self.assertTrue(all(c["execution_status"] == "not_run" for c in cases))

    def test_reproducible_and_private(self):
        self.assertEqual(suite.generate_cases(7), suite.generate_cases(7))
        self.assertNotEqual(suite.generate_cases(7), suite.generate_cases(8))
        self.assertEqual(len({c["injection_seed"] for c in suite.generate_cases()[1:]}), 20)
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "plan"
            plan = suite.generate(output)
            self.assertTrue(all(entry["path"].startswith("private/") for entry in plan["cases"]))
            with self.assertRaises(FileExistsError):
                suite.generate(output)

    def test_random_ranges_windows_and_one_process(self):
        for seed in range(20):
            for case in suite.generate_cases(seed):
                suite.validate_case(case)
                inj = case["injection"]
                if inj["kind"] not in {"normal", "progress_delay"}:
                    self.assertEqual(inj["background_processes"], 1)
                    self.assertEqual(inj["duration_calls"], 36)

    def test_injected_first_five_or_truncated_window_is_rejected(self):
        case = suite.generate_cases()[6]
        for slot in (0, 59, 565):
            changed = deepcopy(case)
            changed["injection"].update(start_call=slot, **suite.coordinates(slot))
            with self.assertRaises(ValueError):
                suite.validate_case(changed)

    def report(self):
        report = rolling.analyze(*repeated())
        root = next(r for r in report["root_causes"] if r["root_id"] == report["primary_source_candidate_id"])
        window = dict(source="captured_injection_window", actual_hit=True, clock_evidence="synthetic same-clock fixture",
                      clock_domain="profiler_node_ns", node_id=root["node_id"], target_ranks=[root["user_rank"]],
                      start_ns=root["observed_start_ns"], stop_ns=root["observed_stop_ns"])
        return report, window

    def test_success_uses_primary_source_actual_interval(self):
        report, window = self.report()
        result = suite.evaluate_temporal_localization(report, [window])
        self.assertTrue(result["diagnosis_success"])
        self.assertTrue(result["target_rank_hit"])
        self.assertTrue(result["rank_time_hit"])
        self.assertEqual(result["classification"], "correct")
        self.assertEqual(result["evaluation_rule"], suite.LOCALIZATION_RULE)
        window["start_ns"] += 100000
        window["stop_ns"] += 100000
        result = suite.evaluate_temporal_localization(report, [window])
        self.assertFalse(result["diagnosis_success"])
        self.assertTrue(result["target_rank_hit"])
        self.assertFalse(result["temporal_hit"])
        self.assertEqual(result["classification"], "time_mismatch")

    def test_same_time_wrong_rank_is_not_success(self):
        report, window = self.report()
        window["target_ranks"] = [(window["target_ranks"][0] + 1) % 4]
        result = suite.evaluate_temporal_localization(report, [window])
        self.assertTrue(result["temporal_hit"])
        self.assertFalse(result["target_rank_hit"])
        self.assertFalse(result["diagnosis_success"])
        self.assertEqual(result["classification"], "rank_mismatch")

    def test_rank_and_time_cannot_match_different_windows(self):
        report, window = self.report()
        same_time = dict(window, target_ranks=[(window["target_ranks"][0] + 1) % 4])
        same_rank = dict(window, start_ns=window["start_ns"] + 100000, stop_ns=window["stop_ns"] + 100000)
        result = suite.evaluate_temporal_localization(report, [same_time, same_rank])
        self.assertTrue(result["temporal_hit"])
        self.assertTrue(result["target_rank_hit"])
        self.assertFalse(result["rank_time_hit"])
        self.assertFalse(result["diagnosis_success"])
        self.assertEqual(result["classification"], "rank_time_window_mismatch")

    def test_partial_overlap_counts_but_touching_boundaries_does_not(self):
        report, window = self.report()
        start, stop = window["start_ns"], window["stop_ns"]
        for lower, upper, expected in [(start - 100, start + 1, True), (stop - 1, stop + 100, True),
                                        (start - 100, start, False), (stop, stop + 100, False)]:
            with self.subTest(bounds=(lower, upper)):
                result = suite.evaluate_temporal_localization(report, [dict(window, start_ns=lower, stop_ns=upper)])
                self.assertEqual(result["diagnosis_success"], expected)

    def test_zero_duration_source_uses_point_containment(self):
        report, window = self.report()
        root = next(r for r in report["root_causes"] if r["root_id"] == report["primary_source_candidate_id"])
        root["observed_stop_ns"] = root["observed_start_ns"]
        self.assertTrue(suite.evaluate_temporal_localization(report, [window])["diagnosis_success"])
        root["observed_start_ns"] = root["observed_stop_ns"] = window["stop_ns"]
        self.assertFalse(suite.evaluate_temporal_localization(report, [window])["diagnosis_success"])

    def test_gap_source_evaluates_gap_instead_of_following_task(self):
        report, window = self.report()
        root = next(r for r in report["root_causes"] if r["root_id"] == report["primary_source_candidate_id"])
        root.update(component="pre_task_gap", gap_before_ns=1000)
        gap_window = dict(window, start_ns=root["observed_start_ns"] - 1000, stop_ns=root["observed_start_ns"])
        self.assertTrue(suite.evaluate_temporal_localization(report, [gap_window])["diagnosis_success"])
        self.assertFalse(suite.evaluate_temporal_localization(report, [window])["diagnosis_success"])

    def test_no_complete_supported_source_is_not_localized(self):
        report, window = self.report()
        for status, truncated in [("dependency_supported_candidate", True), ("unresolved_upstream", False),
                                  ("isolated_slow_task", False), (None, False)]:
            with self.subTest(status=status, truncated=truncated):
                changed = deepcopy(report)
                root = next(r for r in changed["root_causes"] if r["root_id"] == changed["primary_source_candidate_id"])
                root.update(status=status, traversal_truncated=truncated)
                if status is None:
                    changed["primary_source_candidate_id"] = None
                result = suite.evaluate_temporal_localization(changed, [window])
                self.assertFalse(result["diagnosis_success"])
                self.assertEqual(result["classification"], "not_localized")

    def test_wrong_rank_and_time_are_reported_separately(self):
        report, window = self.report()
        wrong = dict(window, target_ranks=[(window["target_ranks"][0] + 1) % 4],
                     start_ns=window["start_ns"] + 100000, stop_ns=window["stop_ns"] + 100000)
        result = suite.evaluate_temporal_localization(report, [wrong])
        self.assertFalse(result["diagnosis_success"])
        self.assertEqual(result["classification"], "rank_and_time_mismatch")

    def test_invalid_time_bounds_are_rejected(self):
        report, window = self.report()
        for lower, upper in [(1, 1), (2, 1), (-1, 2), (True, 2), ("1", 2)]:
            with self.subTest(bounds=(lower, upper)), self.assertRaises(ValueError):
                suite.evaluate_temporal_localization(report, [dict(window, start_ns=lower, stop_ns=upper)])

    def test_missing_or_invalid_rank_truth_is_not_evaluable(self):
        report, window = self.report()
        for ranks in (None, [], ["0"], [True], [-1]):
            result = suite.evaluate_temporal_localization(report, [dict(window, target_ranks=ranks)])
            self.assertIsNone(result["diagnosis_success"])
            self.assertEqual(result["classification"], "not_evaluable")

    def test_same_rank_and_time_on_another_node_is_not_compared(self):
        report, window = self.report()
        result = suite.evaluate_temporal_localization(report, [dict(window, node_id="another-node")])
        self.assertIsNone(result["diagnosis_success"])

    def test_planned_or_uncalibrated_windows_are_not_success(self):
        report, window = self.report()
        for changed in (dict(window, source="case_configuration"), dict(window, clock_evidence=""),
                        dict(window, clock_domain="host_monotonic"), dict(window, actual_hit=False)):
            self.assertIsNone(suite.evaluate_temporal_localization(report, [changed])["diagnosis_success"])

    def test_evaluation_does_not_select_candidate_using_truth(self):
        report, window = self.report()
        extra = deepcopy(report["root_causes"][0])
        extra.update(root_id="secondary", observed_start_ns=window["start_ns"] + 100000,
                     observed_stop_ns=window["stop_ns"] + 100000)
        report["root_causes"].append(extra)
        shifted = dict(window, start_ns=extra["observed_start_ns"], stop_ns=extra["observed_stop_ns"])
        self.assertFalse(suite.evaluate_temporal_localization(report, [shifted])["diagnosis_success"])

    def test_offline_evaluator_exports_without_modifying_diagnosis_or_overwriting(self):
        report, window = self.report()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            report_path, window_path, output = root / "report.json", root / "windows.json", root / "evaluation.json"
            report_path.write_text(json.dumps(report))
            window_path.write_text(json.dumps([window]))
            original = report_path.read_bytes()
            args = ["--report", str(report_path), "--actual-windows", str(window_path), "--output", str(output)]
            with redirect_stdout(io.StringIO()):
                self.assertEqual(evaluate_main(args), 0)
            saved = json.loads(output.read_text())
            self.assertTrue(saved["diagnosis_success"])
            self.assertEqual(saved["classification"], "correct")
            self.assertEqual(report_path.read_bytes(), original)
            with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as error:
                evaluate_main(args)
            self.assertEqual(error.exception.code, 1)


if __name__ == "__main__":
    unittest.main()
