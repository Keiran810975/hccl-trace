from __future__ import annotations

from copy import deepcopy
import importlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

with patch.object(sys, "path", [str(Path(__file__).parent)] + sys.path):
    runner = importlib.import_module("run_node03_anomalies")


class OrderedAnomalyTests(unittest.TestCase):
    def test_sdma_first_delay_last_without_changing_frozen_inputs(self):
        original = runner.build_plan()
        cases = runner.ordered_cases()
        self.assertEqual([c["injection"]["kind"] for c in cases], list(runner.ORDER))
        self.assertEqual(cases[0]["injection"]["buffer_mib"], 512)
        self.assertEqual(cases[-1]["injection"]["delay_ms"], 100)
        self.assertTrue(all(c in original["cases"] for c in cases))
        self.assertEqual(len(cases), 5)

    def test_report_gate_does_not_require_hit_but_does_require_full_restoration(self):
        report = dict(schema_version=2, quality=dict(pipeline_passed=True, rank_count=8,
                      notify_ambiguity_count=0, wait_count=100, paired_wait_count=100))
        restored = dict(status="passed", restored_nodes=[0, 3])
        runner.verify_report(report, restored)
        for field, value in (("pipeline_passed", False), ("rank_count", 4), ("notify_ambiguity_count", 1), ("paired_wait_count", 99)):
            broken = deepcopy(report)
            broken["quality"][field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                runner.verify_report(broken, restored)
        with self.assertRaises(ValueError):
            runner.verify_report(report, dict(status="passed", restored_nodes=[0]))

    def test_effect_report_distinguishes_localization_from_pipeline_pass(self):
        report = dict(candidates=[dict(id="a"), dict(id="b")], external_anomaly_clues=[],
                      unresolved_observations=[{}], propagation=dict(chain_count=3))
        evaluation = dict(case_id="copy", hit_candidate_ids=["b"], primary_hit=False, windows=[dict(user_rank=4)])
        effect = runner.effect_summary(report, evaluation)
        self.assertTrue(effect["pipeline_passed"])
        self.assertFalse(effect["primary_hit"])
        self.assertEqual(effect["matching_sources"], [dict(id="b")])
        self.assertFalse(effect["physical_cause_proven"])

    def test_new_attempt_only_runs_pending_cases_and_keeps_consumer_identity(self):
        with tempfile.TemporaryDirectory() as tmp:
            parent = Path(tmp); previous = parent / "old"; previous.mkdir()
            frozen = {"hccl/tools/diagnosis/rolling_diagnosis.py": "same", "test/node03_roce_window.py": "new"}
            completed = []
            for i, case in enumerate(runner.ordered_cases()[:3], 1):
                directory = parent / ("hccl-diagnose-node03-001-" + str(i))
                (directory / "input").mkdir(parents=True); (directory / "report").mkdir()
                quality = dict(pipeline_passed=True, rank_count=8, notify_ambiguity_count=0,
                               wait_count=100, paired_wait_count=100)
                values = {"input/case.json": case, "report/root_causes.json": dict(schema_version=2, quality=quality, candidates=[]),
                          "authorized-state.json": dict(status="passed", restored_nodes=[0, 3]),
                          "evaluation.json": dict(pipeline_passed=True, case_id=case["case_id"], candidate_count=0),
                          "cleanup-receipt.json": dict(restored_before_cleanup=True)}
                for name, value in values.items():
                    (directory / name).write_text(json.dumps(value))
                for name in ("execution.html", "propagation.html"):
                    (directory / "report" / name).write_text("retained")
                completed.append(dict(case_id=case["case_id"], directory=str(directory)))
            state = dict(status="stopped", completed=3, cases=completed, source_files=dict(frozen, **{"test/node03_roce_window.py": "old"}))
            (previous / "suite-state.json").write_text(json.dumps(state))
            pending, inherited = runner.select_remaining(previous, frozen)
            self.assertEqual([c["injection"]["kind"] for c in pending], ["bandwidth_limit", "progress_delay"])
            self.assertEqual(inherited, completed)
            with self.assertRaisesRegex(ValueError, "different diagnosis"):
                runner.select_remaining(previous, dict(frozen, **{"hccl/tools/diagnosis/rolling_diagnosis.py": "changed"}))
            state["cases"] = completed[::-1]
            (previous / "suite-state.json").write_text(json.dumps(state))
            with self.assertRaisesRegex(ValueError, "ordered completed prefix"):
                runner.select_remaining(previous, frozen)


if __name__ == "__main__":
    unittest.main()
