from __future__ import annotations

import importlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

with patch.object(sys, "path", [str(Path(__file__).parent)] + sys.path):
    runner = importlib.import_module("run_communication_calibration")


class CalibrationRunnerTests(unittest.TestCase):
    def root(self, parent):
        root = parent / "hccl-diagnose-node03-20261101-200"
        (root / "src").mkdir(parents=True)
        (root / "deployment.json").write_text(json.dumps(dict(source_files={})))
        return root

    def test_busy_host_never_starts_or_prepares_an_attempt(self):
        with tempfile.TemporaryDirectory() as tmp:
            parent = Path(tmp)
            root = self.root(parent)
            with patch.object(runner, "LOCAL_PARENT", parent), patch.object(runner.socket, "gethostname", return_value="liteserver-560t-0"), \
                    patch.object(runner, "resources", side_effect=RuntimeError("external task")), \
                    patch.object(runner, "prepare_attempt") as prepare:
                with self.assertRaisesRegex(RuntimeError, "external task"):
                    runner.run(root)
                prepare.assert_not_called()
            state = json.loads((root / "calibration-state.json").read_text())
            self.assertEqual(state["attempts"], [])
            self.assertEqual(state["status"], "stopped")
            self.assertTrue(state["no_automatic_resubmission"])

    def test_effect_without_correct_top1_stops_with_replay_retained(self):
        with tempfile.TemporaryDirectory() as tmp:
            parent = Path(tmp)
            root = self.root(parent)
            selected = []

            def prepare(unused_root, index, case, normal):
                selected.append(case)
                path = parent / ("case" + str(index))
                path.mkdir()
                return path

            evaluation = dict(primary_hit=False, any_candidate_hit=True, candidate_hit_count=1, candidate_count=5)
            with patch.object(runner, "LOCAL_PARENT", parent), patch.object(runner.socket, "gethostname", return_value="liteserver-560t-0"), \
                    patch.object(runner, "resources"), patch.object(runner.time, "sleep"), \
                    patch.object(runner, "execute", return_value=str(150 * 1024**3)), \
                    patch.object(runner, "prepare_attempt", side_effect=prepare), patch.object(runner, "protected_run"), \
                    patch.object(runner, "inspect_case", side_effect=[(evaluation, dict(status="no_measurable_intrinsic_communication_slowdown")),
                                                                     (evaluation, dict(status="communication_effect_observed"))]):
                runner.run(root)
            self.assertEqual([c["injection"]["kind"] for c in selected], ["normal", "copy_contention"])
            state = json.loads((root / "calibration-state.json").read_text())
            self.assertEqual(state["status"], "diagnosis_refinement_needed")
            self.assertTrue(state["attempts"][-1]["raw_and_debug_retained"])
            self.assertFalse(state["attempts"][-1]["primary_hit"])

    def test_partial_card_authorization_does_not_change_default_scope(self):
        with tempfile.TemporaryDirectory() as tmp:
            parent = Path(tmp)
            root = self.root(parent)
            with patch.object(runner, "LOCAL_PARENT", parent), patch.object(runner.socket, "gethostname", return_value="liteserver-560t-0"), \
                    patch.object(runner, "resources", side_effect=RuntimeError("stop at read-only gate")) as check:
                with self.assertRaises(RuntimeError):
                    runner.run(root, allow_other_cards=True)
                self.assertEqual(check.call_args.kwargs["cards"], (4, 5, 6, 7))

    def test_subprocess_stderr_is_retained_without_resubmission(self):
        with tempfile.TemporaryDirectory() as tmp:
            parent = Path(tmp)
            root = self.root(parent)
            error = runner.subprocess.CalledProcessError(1, ["offline-audit"], stderr="missing comparison file")
            with patch.object(runner, "LOCAL_PARENT", parent), patch.object(runner.socket, "gethostname", return_value="liteserver-560t-0"), \
                    patch.object(runner, "resources", side_effect=error), patch.object(runner, "prepare_attempt") as prepare:
                with self.assertRaises(runner.subprocess.CalledProcessError):
                    runner.run(root)
                prepare.assert_not_called()
            state = json.loads((root / "calibration-state.json").read_text())
            self.assertEqual(state["command_exit_code"], 1)
            self.assertEqual(state["command_stderr"], "missing comparison file")
            self.assertTrue(state["no_automatic_resubmission"])

    def test_low_disk_reserve_terminates_protected_wrapper(self):
        from unittest.mock import MagicMock
        process = MagicMock()
        process.poll.return_value = None
        with patch.object(runner.subprocess, "Popen", return_value=process), \
                patch.object(runner, "free_space", return_value=7 * 1024**3):
            with self.assertRaisesRegex(RuntimeError, "emergency reserve"):
                runner.protected_run(["owned-wrapper"], None)
        process.terminate.assert_called_once()
        process.wait.assert_called_once_with(timeout=650)

    def normal(self, parent):
        previous = parent / "hccl-diagnose-node03-20261101-201"
        (previous / "input").mkdir(parents=True)
        (previous / "src").mkdir()
        (previous / "report").mkdir()
        case = runner.cases()[0]
        data = {"input/case.json": case,
                "report/root_causes.json": dict(run_id=case["case_id"], candidates=[]),
                "authorized-state.json": dict(status="passed"),
                "evaluation.json": dict(case_id=case["case_id"], pipeline_passed=True, windows=[],
                                        candidate_count=0, candidate_hit_count=0, any_candidate_hit=False, primary_hit=False),
                "communication-impact.json": dict(injection_kind="normal", actual_windows=[], status="no_measurable_intrinsic_communication_slowdown"),
                "offload-receipt.json": dict(status="verified", file_hashes_verified=True, local_archive_sha256=["a", "b"])}
        for name, value in data.items():
            (previous / name).write_text(json.dumps(value))
        return previous

    def test_archived_normal_reuse_does_not_rerun_training(self):
        with tempfile.TemporaryDirectory() as tmp:
            parent = Path(tmp)
            previous = self.normal(parent)
            frozen = {"hccl/tools/diagnosis/cli.py": "same", "test/run_communication_calibration.py": "new"}
            with patch.object(runner, "LOCAL_PARENT", parent), patch.object(runner, "verify_report"), \
                    patch.object(runner, "source_hashes", return_value=dict(frozen, **{"test/run_communication_calibration.py": "old"})), \
                    patch.object(runner, "execute") as execute:
                result = runner.reuse_completed_normal(previous, frozen)
            self.assertTrue(result["reused_completed_normal"])
            self.assertEqual(execute.call_count, 2)

    def test_normal_reuse_rejects_changed_consumer_or_missing_backup(self):
        with tempfile.TemporaryDirectory() as tmp:
            parent = Path(tmp)
            previous = self.normal(parent)
            with patch.object(runner, "LOCAL_PARENT", parent), patch.object(runner, "source_hashes", return_value={"hccl/tools/diagnosis/cli.py": "old"}):
                with self.assertRaisesRegex(ValueError, "identical"):
                    runner.reuse_completed_normal(previous, {"hccl/tools/diagnosis/cli.py": "new"})
            (previous / "offload-receipt.json").write_text(json.dumps(dict(status="incomplete")))
            with patch.object(runner, "LOCAL_PARENT", parent), patch.object(runner, "source_hashes", return_value={}), patch.object(runner, "verify_report"):
                with self.assertRaisesRegex(ValueError, "archives"):
                    runner.reuse_completed_normal(previous, {})


if __name__ == "__main__":
    unittest.main()
