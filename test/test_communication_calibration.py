from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from . import communication_calibration as plan
from . import communication_impact as impact
from .communication_impact import assess, comparison_path
from .node03_gpt2_control import MultiNodeControl


class CommunicationCalibrationTests(unittest.TestCase):
    def test_frozen_bounded_plan_excludes_pre_call_sleep(self):
        cases = plan.cases()
        self.assertEqual(cases, plan.cases())
        self.assertEqual(len(cases), 11)
        self.assertFalse(any(c["injection"]["kind"] == "progress_delay" for c in cases))
        for case in cases:
            plan.validate_case(case)
            self.assertEqual(case["workload"]["iters"], 50)
        changed = deepcopy(cases[1])
        changed["injection"]["buffer_mib"] = 111
        with self.assertRaises(ValueError):
            plan.validate_case(changed)

    def test_levels_are_not_chosen_based_on_localization_hits(self):
        self.assertEqual(plan.advance([], "copy_contention")["level"], 512)
        history = [dict(kind="copy_contention", level=512, status="no_measurable_intrinsic_communication_slowdown")]
        self.assertEqual(plan.advance(history, "copy_contention")["level"], 1024)
        history += [dict(kind="copy_contention", level=1024, status="communication_effect_observed")]
        self.assertEqual(plan.advance(history, "copy_contention")["action"], "freeze_and_validate")
        self.assertEqual(plan.advance([], "progress_delay")["action"], "blocked")
        self.assertEqual(plan.advance([dict(kind="copy_contention", level=512, status="technical_failure")],
                                     "copy_contention")["action"], "stop")

    def test_exhaustion_is_inconclusive_not_an_infinite_retry(self):
        history = [dict(kind="compute_contention", level=n, status="no_measurable_intrinsic_communication_slowdown")
                   for n in plan.LEVELS["compute_contention"]]
        self.assertEqual(plan.advance(history, "compute_contention")["action"], "inconclusive")

    def test_activation_is_after_an_observed_submit_without_ack_wait(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "case.json"
            path.write_text(json.dumps(plan.cases()[1]))
            control = MultiNodeControl(path, Path(tmp) / "private", 4, {4: 1})
            call = dict(stage="measured", iteration=20, sequence=300,
                        bucket_signature="a" * 64, input_buffer_ptr=123)
            with patch.object(control, "wait", side_effect=AssertionError("must not wait in foreground")):
                control.after_collective(dict(call, stage="warmup"))
                self.assertFalse(control.started)
                control.after_collective(call)
                self.assertTrue(control.started)
                control.after_collective(call)
            events = [json.loads(s)["event"] for s in (control.directory / "rank-4.jsonl").read_text().splitlines()]
            self.assertEqual(events.count("injection_start"), 1)
            self.assertEqual(events[0], "communication_activation_request")
            control.close()


class CommunicationImpactTests(unittest.TestCase):
    def test_cli_reads_a_real_cli_debug_directory_layout(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            report = dict(run_id="normal-run", quality=dict(pipeline_passed=True), candidates=[])
            evaluation = dict(case_id="normal-run", injection=dict(kind="normal"), pipeline_passed=True,
                              windows=[], hit_candidate_ids=[], primary_hit=False)
            (root / "report").mkdir()
            (root / "report/root_causes.json").write_text(json.dumps(report))
            (root / "evaluation.json").write_text(json.dumps(evaluation))
            comparison = root / "report.debug/analysis/normal-run/rolling/task_comparison.csv"
            comparison.parent.mkdir(parents=True)
            comparison.write_text("graph_id,stage,task_domain\nwork,measured,hccl_internal\n")
            with patch("sys.argv", ["communication_impact", "--root", str(root)]), patch("builtins.print"):
                impact.main()
            result = json.loads((root / "communication-impact.json").read_text())
            self.assertEqual(result["case_id"], "normal-run")
            self.assertEqual(result["slow_execution_count"], 0)

    def test_comparison_is_bound_to_the_report_run_id(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            expected = root / "report.debug/analysis/actual-run/rolling/task_comparison.csv"
            expected.parent.mkdir(parents=True)
            expected.write_text("graph_id,status\n")
            self.assertEqual(comparison_path(root, dict(run_id="actual-run")), expected)
            with self.assertRaisesRegex(ValueError, "missing task comparison"):
                comparison_path(root, dict(run_id="another-run"))
            for run_id in ("..", ".", "../actual-run", "a/b", "a\\b", "", None):
                with self.assertRaisesRegex(ValueError, "one path component"):
                    comparison_path(root, dict(run_id=run_id))

    def inputs(self):
        window = dict(node_id="run/node3", user_rank=4, start_ns=1000, stop_ns=2000)
        task = dict(graph_id="copy", node_id=window["node_id"], user_rank=4, observed_start_ns=1100,
                    observed_stop_ns=1200, stage="measured", reference_count=5, task_kind="sdma",
                    task_domain="hccl_internal", duration_slow=True, delta_ns="40")
        report = dict(quality=dict(pipeline_passed=True), candidates=[])
        evaluation = dict(case_id="copy", injection=dict(kind="copy_contention"), pipeline_passed=True,
                          windows=[window], hit_candidate_ids=[], primary_hit=False)
        return task, report, evaluation

    def test_only_owned_work_not_wait_doorbell_or_compute_counts(self):
        task, report, evaluation = self.inputs()
        tasks = [dict(task, task_kind="notify_wait"), dict(task, task_kind="rdma"),
                 dict(task, task_domain="unknown"), dict(task, user_rank=5)]
        self.assertEqual(assess(tasks, report, evaluation)["slow_execution_count"], 0)
        result = assess([task], report, evaluation)
        self.assertEqual(result["status"], "communication_effect_observed")
        self.assertFalse(result["physical_cause_proven"])
        self.assertEqual(result["localization"]["hit_count"], 0)

    def test_incomplete_history_and_touching_window_do_not_count(self):
        task, report, evaluation = self.inputs()
        missing = dict(task, reference_count=0, comparison_status="unannotated_task_location")
        touching = dict(task, observed_start_ns=2000, observed_stop_ns=2100)
        result = assess([missing, touching], report, evaluation)
        self.assertEqual(result["slow_execution_count"], 0)
        self.assertEqual(result["overlapping_communication_facts"]["incomparable_unannotated_task_location"], 1)

    def test_evaluator_cannot_silently_change_hit_definition(self):
        task, report, evaluation = self.inputs()
        report["candidates"] = [dict(task, id="root")]
        with self.assertRaises(ValueError):
            assess([task], report, evaluation)


if __name__ == "__main__":
    unittest.main()
