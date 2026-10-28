from __future__ import annotations

import json
import csv
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from test.anomaly_injection.single_node_control import PublicCalls, SingleControl
from test.run_single_node_suite import host_is_idle, write_results, write_formal_summary
from test.single_node_random_suite import generate_cases


class RuntimeTests(unittest.TestCase):
    def test_communication_background_has_its_own_port_ranges(self):
        case = next(c for c in generate_cases() if c["injection"]["kind"] == "communication_contention")
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            config = root / "case.json"
            config.write_text(json.dumps(case))
            control = SingleControl(config, root / "private", case["injection"]["target_rank"],
                                    [1, 3, 5, 7], Path("/own/native-worker"))
            with patch("test.anomaly_injection.single_node_control.subprocess.Popen", return_value=Mock(pid=123, poll=Mock(return_value=0))) as popen:
                with patch.object(control, "wait"):
                    control.prepare()
                env = popen.call_args.kwargs["env"]
                self.assertEqual(env["HCCL_IF_BASE_PORT"], "53000")
                self.assertEqual(env["HCCL_HOST_SOCKET_PORT_RANGE"], "53000-53063")
                self.assertEqual(env["HCCL_NPU_SOCKET_PORT_RANGE"], "53100-53163")
            control.close()

    def test_success_rates_do_not_report_partial_runs_as_a_complete_group(self):
        cases = [dict(case_id=str(i), injection=dict(kind="progress_delay"), injection_locations=[],
                      temporal_evaluation=dict(diagnosis_success=i < 2)) for i in range(5)]
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            write_formal_summary(root, cases[:1])
            group = json.loads((root / "success-rates.json").read_text())["groups"][0]
            self.assertIsNone(group["success_rate_percent"])
            write_formal_summary(root, cases)
            groups = json.loads((root / "success-rates.json").read_text())["groups"]
            self.assertEqual(groups[0]["success_rate_percent"], 40)
            self.assertEqual(groups[0]["correct"], 2)
            self.assertTrue(all(g["success_rate_percent"] is None for g in groups[1:]))

    def test_results_csv_preserves_rank_time_failures_and_unevaluable(self):
        evaluations = [dict(status="evaluated_rank_time_criterion", diagnosis_success=False,
                            temporal_hit=True, target_rank_hit=False, rank_time_hit=False,
                            classification="rank_mismatch", evaluation_rule="primary_source_same_rank_and_time_overlap"),
                       dict(status="not_evaluable", diagnosis_success=None, classification="not_evaluable")]
        cases = [dict(case_id=str(i), execution_success=True, strict_diagnosis_success=True,
                      diagnosis_directory="diagnosis", temporal_evaluation=e) for i, e in enumerate(evaluations)]
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "results.csv"
            write_results(path, cases)
            with path.open(newline="") as stream:
                rows = list(csv.DictReader(stream))
            self.assertEqual(rows[0]["diagnosis_success"], "False")
            self.assertEqual(rows[0]["temporal_hit"], "True")
            self.assertEqual(rows[0]["target_rank_hit"], "False")
            self.assertEqual(rows[0]["classification"], "rank_mismatch")
            self.assertEqual(rows[1]["diagnosis_success"], "")
            self.assertEqual(rows[1]["classification"], "not_evaluable")

    def test_compute_worker_receives_selected_backend_and_one_process(self):
        case = next(c for c in generate_cases() if c["injection"]["kind"] == "compute_contention")
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            config = root / "case.json"
            config.write_text(json.dumps(case))
            control = SingleControl(config, root / "private", case["injection"]["target_rank"],
                                    [1, 3, 5, 7], gemm_backend="grouped")
            worker = Mock(pid=123, poll=Mock(return_value=0))
            with patch("test.anomaly_injection.single_node_control.subprocess.Popen", return_value=worker) as popen:
                with patch.object(control, "wait"):
                    control.prepare()
                popen.assert_called_once()
                command = popen.call_args.args[0]
                self.assertEqual(command[command.index("--gemm-backend") + 1], "grouped")
                self.assertEqual(int(command[command.index("--matrix-size") + 1]), case["injection"]["matrix_size"])
            control.close()

    def test_idle_needs_all_chips_base_memory_and_no_processes(self):
        text = "\n".join("| {} {} | x | 0 | 0 / 0 | 3200 / 65536 |".format(i // 2, i) for i in range(16))
        text += "\n" + "\n".join("| No running processes found in NPU {} |".format(i) for i in range(8))
        self.assertTrue(host_is_idle(text))
        self.assertFalse(host_is_idle(text.replace("3200 /", "60000 /", 1)))
        self.assertFalse(host_is_idle(text.replace("No running processes found in NPU 0", "0 | 1234 | python")))
        self.assertFalse(host_is_idle(text.replace("| 7 15 | x | 0 | 0 / 0 | 3200 / 65536 |", "")))

    def test_public_recorder_has_only_neutral_coordinates(self):
        with tempfile.TemporaryDirectory() as temporary:
            recorder = PublicCalls(temporary, 2, 5)
            recorder.begin(-1, 1, 2, 4096)
            recorder.end()
            recorder.begin(5, 1, 2, 4096)
            recorder.end()
            recorder.close()
            text = (Path(temporary) / "rank-2.jsonl").read_text()
            records = [json.loads(line) for line in text.splitlines()]
            self.assertEqual([(r["stage"], r["iteration"], r["sequence"]) for r in records],
                             [("warmup", 0, 0), ("measured", 5, 1)])
            self.assertNotIn("injection", text)
            self.assertNotIn("target", text)
            self.assertLessEqual(records[0]["before"]["raw_ns"], records[0]["after"]["raw_ns"])

    def test_public_preparation_covers_all_calls_and_is_not_an_injection_marker(self):
        with tempfile.TemporaryDirectory() as temporary:
            recorder = PublicCalls(temporary, 2, 5)
            for i in range(3):
                recorder.prepare(i, 0, 1, 4096)
                recorder.begin(i, 0, 1, 4096)
                recorder.end()
            recorder.close()
            records = [json.loads(line) for line in (Path(temporary) / "rank-2.jsonl").read_text().splitlines()]
            self.assertEqual(len(records), 3)
            self.assertTrue(all(r["preparation_before"]["raw_ns"] <= r["before"]["raw_ns"] for r in records))
            self.assertTrue(all("injection" not in str(r) and "target" not in str(r) for r in records))

    def test_public_preparation_cannot_be_reused_or_bound_to_another_call(self):
        with tempfile.TemporaryDirectory() as temporary:
            recorder = PublicCalls(temporary, 2, 5)
            self.addCleanup(recorder.close)
            recorder.prepare(5, 0, 0, 4096)
            with self.assertRaises(ValueError):
                recorder.prepare(5, 0, 0, 4096)
            with self.assertRaises(ValueError):
                recorder.begin(5, 0, 1, 4096)

    def test_delay_fires_once_only_on_exact_selected_call_and_rank(self):
        case = generate_cases()[1]
        inj = case["injection"]
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            config = root / "case.json"
            config.write_text(json.dumps(case))
            control = SingleControl(config, root / "private", inj["target_rank"], [1, 3, 5, 7])
            with patch("test.anomaly_injection.single_node_control.time.sleep") as sleep:
                control.before_collective(-1, inj["block"], inj["bucket"])
                sleep.assert_not_called()
                control.before_collective(inj["iteration"], inj["block"], inj["bucket"])
                sleep.assert_called_once_with(inj["delay_ms"] / 1000)
                with self.assertRaises(RuntimeError):
                    control.before_collective(inj["iteration"], inj["block"], inj["bucket"])
            control.finish()
            truth = [json.loads(line) for line in (root / "private" / ("rank-{}.jsonl".format(inj["target_rank"]))).read_text().splitlines()]
            self.assertEqual([r["event"] for r in truth], ["injection_start", "injection_stop"])
            control.close()


if __name__ == "__main__":
    unittest.main()
