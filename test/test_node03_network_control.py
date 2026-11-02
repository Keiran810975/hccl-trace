from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from test.node03_gpt2_control import MultiNodeControl
from test.node03_gpt2_suite import build_plan
from test.node03_roce_window import Window, DEVICE, SIBLING, LIMIT, COUNTERS
from test.node03_evaluate import validate_network_window


class NetworkControlTests(unittest.TestCase):
    def controller(self, root):
        case = build_plan()["cases"][-1]
        (root / "input").mkdir()
        config = root / "input/case.json"
        config.write_text(json.dumps(case))
        return MultiNodeControl(config, root / "gpt-output/private", 0, {0: 1})

    def acknowledge(self, control):
        (control.directory / "network-active.json").write_text(json.dumps(dict(schema_version=1,
            case_id=control.case["case_id"], applied_verified=True, device=9, limit_mbps=20000, started_raw_ns=100)))

    def test_request_never_blocks_and_only_five_full_verified_iterations_stop_it(self):
        with tempfile.TemporaryDirectory() as tmp:
            control = self.controller(Path(tmp))
            with patch.object(control, "wait", side_effect=AssertionError("do not delay the foreground")):
                control.start(2)
                for iteration in range(28, 35):
                    control.before_iteration(iteration, 50)
                    control.after_iteration(iteration)
                self.assertFalse((control.directory / "stop").exists())
                self.acknowledge(control)
                for iteration in range(35, 40):
                    control.before_iteration(iteration, 50)
                    self.assertFalse((control.directory / "stop").exists())
                    control.after_iteration(iteration)
                self.assertTrue((control.directory / "stop").exists())
                window = json.loads((control.directory / "network-measured-window.json").read_text())
                self.assertEqual(window["requested_iteration"], 28)
                self.assertEqual(window["completed_iterations"], list(range(35, 40)))
            control.close()

    def test_too_late_ack_wrong_identity_and_premature_failure_are_rejected(self):
        for reason in ("late", "wrong_case", "failed"):
            with self.subTest(reason=reason), tempfile.TemporaryDirectory() as tmp:
                control = self.controller(Path(tmp))
                control.start(2)
                self.acknowledge(control)
                if reason == "wrong_case":
                    p = control.directory / "network-active.json"
                    ack = json.loads(p.read_text()); ack["case_id"] = "different"
                    p.write_text(json.dumps(ack))
                elif reason == "failed":
                    (control.directory / "network-result.json").write_text(json.dumps(dict(error="apply failed")))
                with self.assertRaises((RuntimeError, ValueError)):
                    control.before_iteration(47 if reason == "late" else 35, 50)
                self.assertFalse((control.directory / "stop").exists())
                control.close()
                self.assertTrue((control.directory / "abort").exists())

    def test_incomplete_window_cannot_pass_finish(self):
        with tempfile.TemporaryDirectory() as tmp:
            control = self.controller(Path(tmp)); control.start(2); self.acknowledge(control)
            control.before_iteration(35, 50); control.after_iteration(35)
            with self.assertRaisesRegex(RuntimeError, "complete formal iterations"):
                control.finish()
            self.assertTrue((control.directory / "abort").exists())
            control.close()

    def fake_window(self, root, control, *, readback_failure=False):
        before = dict.fromkeys(COUNTERS, 0)
        proof = dict(node_id="node0", user_rank=0, physical_device_id=9, runtime_device_id=1,
                     foreground_only=True, numerics_passed=True, before=before,
                     after=dict(before, mac_tx_total_oct_num=2 * 1024**2, roce_tx_all_pkt_num=10))
        (root / "input/network-baseline.json").write_text(json.dumps(proof))
        window = object.__new__(Window)
        window.root, window.directory, window.control = root, root / "network", control.directory
        window.snapshot = window.directory / "snapshot.json"
        ports = {d: dict(limit_mbps=200000, maximum_mbps=200000, current_mbps=200000) for d in (DEVICE, SIBLING)}
        def shape(device):
            value = dict(ports[device])
            if readback_failure and device == DEVICE and value["limit_mbps"] == LIMIT:
                # Fail one readback, but let the finally block inspect and restore the actual original.
                shape.failed = getattr(shape, "failed", False)
                if not shape.failed:
                    shape.failed = True
                    value["limit_mbps"] = 1
            return value
        def set_limit(device, limit):
            ports[device] = dict(ports[device], limit_mbps=limit)
        def run(command, check=True):
            if command[0] == "systemd-run" and "--on-active=2s" in command:
                window.restore()
            return "active\n"
        def own():
            # Reproduce the original race: more than the original five iterations
            # elapse during safety checks, before any port setting is attempted.
            for iteration in range(28, 34):
                control.before_iteration(iteration, 50); control.after_iteration(iteration)
        window.shaping, window.set, window.run = shape, Mock(side_effect=set_limit), run
        window.stop_timer, window.own_processes = Mock(), Mock(side_effect=own)
        window.query = Mock(side_effect=[before, dict(before, mac_tx_total_oct_num=1024**2, roce_tx_all_pkt_num=5)])
        return window, ports

    def test_native_guard_waits_for_ack_coverage_and_restores_after_original_race(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); control = self.controller(root); control.start(2)
            window, ports = self.fake_window(root, control)
            iteration = iter(range(34, 39))
            def advance(seconds):
                current = next(iteration)
                control.before_iteration(current, 50); control.after_iteration(current)
            with patch("test.node03_roce_window.time.sleep", side_effect=advance):
                window.watch()
            result = json.loads((control.directory / "network-result.json").read_text())
            self.assertTrue(result["applied_verified"] and result["restored_verified"])
            self.assertEqual(result["measurement_window"]["completed_iterations"], list(range(34, 39)))
            self.assertEqual(ports[DEVICE]["limit_mbps"], 200000)
            self.assertEqual(ports[SIBLING]["limit_mbps"], 200000)
            control.finish(); control.close()

    def test_native_readback_failure_never_publishes_ack_and_still_restores(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); control = self.controller(root); control.start(2)
            window, ports = self.fake_window(root, control, readback_failure=True)
            with self.assertRaisesRegex(RuntimeError, "did not verify"):
                window.watch()
            self.assertFalse((control.directory / "network-active.json").exists())
            result = json.loads((control.directory / "network-result.json").read_text())
            self.assertFalse(result["applied_verified"])
            self.assertTrue(result["restored_verified"])
            self.assertEqual(ports[DEVICE]["limit_mbps"], 200000)
            control.close()

    def test_independent_evaluation_checks_public_calls_not_only_private_ack(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); control = self.controller(root)
            public = root / "public"; public.mkdir()
            window = dict(schema_version=1, case_id=control.case["case_id"], requested_iteration=28,
                          first_full_iteration=35, completed_iterations=list(range(35, 40)))
            activity = dict(started_raw_ns=100, finished_raw_ns=200, measurement_window=window)
            calls = [dict(rank=0, stage="measured", iteration=i, preparation_before=dict(raw_ns=110 + i)) for i in range(35, 40)]
            done = [dict(rank=0, stage="measured", iteration=i, device_synchronized=True, clocks=dict(raw_ns=120 + i)) for i in range(35, 40)]
            (public / "rank-0.jsonl").write_text("\n".join(map(json.dumps, calls)))
            (public / "boundaries-rank-0.jsonl").write_text("\n".join(map(json.dumps, done)))
            self.assertEqual(validate_network_window(root, control.case, activity), window)
            calls[0]["preparation_before"]["raw_ns"] = 99
            (public / "rank-0.jsonl").write_text("\n".join(map(json.dumps, calls)))
            with self.assertRaisesRegex(ValueError, "public calls"):
                validate_network_window(root, control.case, activity)
            control.close()


if __name__ == "__main__":
    unittest.main()
