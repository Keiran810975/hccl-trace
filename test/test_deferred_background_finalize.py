"""Lifecycle tests only; native SDK stubs are not a device performance test."""
from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import time
import unittest
from unittest.mock import Mock, patch

from test.anomaly_injection.npu_background_load import wait_for_finalize
from test.anomaly_injection.single_node_control import SingleControl
from test.single_node_random_suite import generate_cases


class DeferredFinalizeTests(unittest.TestCase):
    def control(self, root):
        case = next(c for c in generate_cases() if c["injection"]["kind"] == "copy_contention")
        path = root / "case.json"
        path.write_text(json.dumps(case))
        return SingleControl(path, root / "private", case["injection"]["target_rank"], [1, 3, 5, 7])

    def test_stop_only_requests_pause_and_never_waits_in_the_workload(self):
        with tempfile.TemporaryDirectory() as temporary:
            control = self.control(Path(temporary))
            control.started = True
            process = Mock()
            control.process = process
            try:
                control.stop()
                process.wait.assert_not_called()
                self.assertTrue((control.directory / "stop").exists())
                self.assertFalse((control.directory / "finalize").exists())
                self.assertFalse(control.stopped)
                self.assertTrue(control.stop_requested)
            finally:
                control.process = None

    def test_finalization_is_authorized_only_after_measurement_finish(self):
        with tempfile.TemporaryDirectory() as temporary:
            control = self.control(Path(temporary))
            control.started = True
            control.process = Mock(returncode=0)
            (control.directory / "paused").touch()
            activity = dict(started_raw_ns=1, finished_raw_ns=2, operations=7)
            (control.directory / "activity-window.json").write_text(json.dumps(activity))
            (control.directory / "result.json").write_text(json.dumps(dict(activity, finalize_deferred=True, max_error=0, finalize_authorized_raw_ns=10**30)))
            try:
                control.stop()
                control.finish()
                self.assertTrue((control.directory / "finalize").is_file())
                self.assertTrue(control.stopped)
                control.process.wait.assert_called_once_with(timeout=180)
                events = [json.loads(line)["event"] for line in (control.directory / ("rank-{}.jsonl".format(control.rank))).read_text().splitlines()]
                self.assertEqual(events, ["injection_stop_requested", "measurement_finished_finalize_authorized", "injection_stop"])
            finally:
                control.process = None

    def test_background_gate_is_bounded(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary)
            with self.assertRaises(TimeoutError):
                wait_for_finalize(path, 0)
            with patch("test.anomaly_injection.npu_background_load.time.sleep", side_effect=lambda _: (path / "finalize").touch()):
                wait_for_finalize(path, time.monotonic() + 10)

    def test_invalid_activity_or_early_finalization_is_rejected(self):
        for invalid in ({"finished_raw_ns": 3}, {"finalize_authorized_raw_ns": 1}, {"finalize_deferred": False}):
            with self.subTest(invalid=invalid), tempfile.TemporaryDirectory() as temporary:
                control = self.control(Path(temporary))
                control.started = True
                control.process = Mock(returncode=0)
                (control.directory / "paused").touch()
                activity = dict(started_raw_ns=1, finished_raw_ns=2, operations=7)
                (control.directory / "activity-window.json").write_text(json.dumps(activity))
                result = dict(activity, finalize_deferred=True, max_error=0, finalize_authorized_raw_ns=10**30)
                result.update(invalid)
                (control.directory / "result.json").write_text(json.dumps(result))
                try:
                    with self.assertRaises(ValueError):
                        control.finish()
                    self.assertFalse(control.stopped)
                finally:
                    control.process = None

    def test_native_worker_pauses_before_validation_and_cleanup_with_sdk_stubs(self):
        compiler = shutil.which("c++")
        if not compiler:
            self.skipTest("C++ compiler unavailable; no native SDK-stub check")
        root = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary)
            binary, log = path / "worker", path / "cleanup.log"
            compiled = subprocess.run([compiler, "-std=c++14", "-pthread", "-I" + str(root / "test/fixtures/native_worker_stubs"),
                                       str(root / "test/anomaly_injection/single_process_comm_load.cc"), "-o", str(binary)],
                                      capture_output=True, text=True, timeout=60)
            self.assertEqual(compiled.returncode, 0, compiled.stderr)
            process = subprocess.Popen([str(binary), "0", "1", "32", str(path), "--defer-finalize"],
                                       env=dict(os.environ, HCCL_WORKER_STUB_LOG=str(log)), stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            try:
                def wait_for(name):
                    deadline = time.monotonic() + 20
                    while not (path / name).exists():
                        if process.poll() is not None or time.monotonic() >= deadline:
                            self.fail("stub worker did not reach " + name)
                        time.sleep(.01)
                wait_for("ready")
                (path / "start").touch()
                wait_for("active")
                (path / "stop").touch()
                wait_for("paused")
                self.assertIsNone(process.poll())
                self.assertFalse(log.exists())
                self.assertFalse((path / "result.json").exists())
                window = json.loads((path / "activity-window.json").read_text())
                self.assertGreater(window["operations"], 0)
                (path / "finalize").touch()
                _, errors = process.communicate(timeout=20)
                self.assertEqual(process.returncode, 0, errors)
                result = json.loads((path / "result.json").read_text())
                self.assertTrue(result["finalize_deferred"])
                self.assertGreaterEqual(result["finalize_authorized_raw_ns"], result["finished_raw_ns"])
                self.assertEqual(result["max_error"], 0)
                self.assertTrue(log.exists())
            finally:
                if process.poll() is None:
                    process.kill()
                    process.communicate(timeout=10)


if __name__ == "__main__":
    unittest.main()
