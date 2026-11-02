from __future__ import annotations

import importlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

from . import calibration_offload

with patch.object(sys, "path", [str(Path(__file__).parent)] + sys.path):
    runner = importlib.import_module("run_fixed_trace_capture")


class FixedTraceCaptureTests(unittest.TestCase):
    def prepare(self, parent):
        root = parent / "hccl-diagnose-node03-20261101-230"
        (root / "src").mkdir(parents=True)
        (root / "deployment.json").write_text(json.dumps(dict(source_files={})))
        return root

    def test_exactly_one_capture_retains_all_data_even_when_not_localized(self):
        with tempfile.TemporaryDirectory() as tmp:
            parent = Path(tmp)
            root = self.prepare(parent)
            current = parent / "hccl-diagnose-node03-20261101-231"
            current.mkdir()
            with patch.object(runner, "LOCAL_PARENT", parent), patch.object(runner.socket, "gethostname", return_value="liteserver-560t-0"), \
                    patch.object(runner, "resources"), patch.object(runner.time, "sleep"), \
                    patch.object(runner, "prepare_attempt", return_value=current) as prepare, \
                    patch.object(runner, "execute"), patch.object(runner, "protected_run") as capture, \
                    patch.object(runner, "inspect_case", return_value=({"primary_hit": False}, {"status": "no_effect"})):
                runner.run(root)
            self.assertEqual(prepare.call_args.args[2]["injection"]["buffer_mib"], 1024)
            capture.assert_called_once()
            self.assertTrue(json.loads((current / "retain-all-evidence.json").read_text())["automatic_cleanup_forbidden"])
            state = json.loads((root / "fixed-trace-state.json").read_text())
            self.assertEqual(state["status"], "capture_complete")
            self.assertEqual(state["completed_runs"], 1)
            with patch.object(runner, "LOCAL_PARENT", parent), patch.object(runner.socket, "gethostname", return_value="liteserver-560t-0"):
                with self.assertRaisesRegex(ValueError, "never restart"):
                    runner.run(root)

    def test_busy_targets_never_start_or_prepare(self):
        with tempfile.TemporaryDirectory() as tmp:
            parent = Path(tmp)
            root = self.prepare(parent)
            with patch.object(runner, "LOCAL_PARENT", parent), patch.object(runner.socket, "gethostname", return_value="liteserver-560t-0"), \
                    patch.object(runner, "resources", side_effect=RuntimeError("busy")), patch.object(runner, "prepare_attempt") as prepare:
                with self.assertRaisesRegex(RuntimeError, "busy"):
                    runner.run(root)
                prepare.assert_not_called()

    def test_offload_cleanup_honors_retention_lock_before_touching_raw_inputs(self):
        captured = []
        def check(node, code, timeout):
            captured.append(code)
            raise ValueError("retained")
        with patch.object(calibration_offload, "remote_json", side_effect=check):
            with self.assertRaisesRegex(ValueError, "retained"):
                calibration_offload.cleanup(0, "hccl-diagnose-node03-20261101-231", {"manifest_sha256": "a"})
        self.assertLess(captured[0].index("retain-all-evidence.json"), captured[0].index("shutil.rmtree"))


if __name__ == "__main__":
    unittest.main()
