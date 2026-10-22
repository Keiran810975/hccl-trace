from __future__ import annotations

import argparse
import copy
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import types
import unittest
from unittest.mock import MagicMock, patch

from test import four_node_suite as suite
from test.anomaly_injection.four_node_control import CaseControl, load_control


class TwoNodeSuiteTests(unittest.TestCase):
    def setUp(self) -> None:
        self.cases = suite.generate_cases(["main"], [25], [20261022], nnodes=2, ranks_per_node=2)
        self.cluster = suite.read_json(suite.ROOT / "test/configs/two_node_cluster.example.json")

    def test_paired_matrix_and_large_workload(self) -> None:
        self.assertEqual(len(self.cases), 16)
        for case in self.cases:
            self.assertTrue(case["case_id"].startswith("2n4r-"))
            self.assertEqual((case["nnodes"], case["ranks_per_node"]), (2, 2))
            self.assertEqual(case["injection"]["target_rank"], 2)
            self.assertEqual(case["baseline_case_id"], self.cases[0]["case_id"])
            self.assertEqual(case["workload"], self.cases[0]["workload"])
        stats = suite.workload_stats(self.cases[0])
        self.assertEqual(stats["world_size"], 4)
        self.assertEqual(stats["allreduces_per_iteration"], 24)
        self.assertEqual(stats["allreduces_including_warmup"], 1440)
        self.assertEqual(stats["input_mib_per_rank_iteration"], 7 * 1024)
        self.assertEqual(stats["bf16_weight_bytes_per_rank"], 14 * 1024**3)

    def test_smoke_retains_full_compute_and_bucket_sizes(self) -> None:
        cases = suite.generate_cases(["main"], [0], [1], smoke=True, nnodes=2, ranks_per_node=2)
        self.assertEqual(suite.workload_stats(cases[0])["allreduces_including_warmup"], 72)
        for case in cases:
            self.assertTrue(case["case_id"].startswith("smoke-2n4r-"))
            self.assertEqual(case["purpose"], "preflight")
            self.assertEqual(case["workload"]["bucket_mib"], [128, 256, 512])
            self.assertEqual(case["workload"]["hidden_size"], 8192)

    def test_standalone_entry_generates_two_node_cases(self) -> None:
        with tempfile.TemporaryDirectory() as name:
            target = Path(name) / "plan"
            result = subprocess.run([sys.executable, str(suite.ROOT / "test/two_node_suite.py"),
                                     "generate", "--smoke", "--output", str(target)],
                                    capture_output=True, text=True, timeout=15)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(suite.read_json(target / "suite.json")["stats"]["world_size"], 4)

    def test_node_and_global_rank_bounds(self) -> None:
        case = copy.deepcopy(self.cases[0])
        case["injection"]["target_rank"] = 4
        with self.assertRaises(ValueError):
            suite.validate_case(case)
        case = copy.deepcopy(next(c for c in self.cases if c["injection"]["kind"] == "communication_contention"))
        case["injection"]["peer_rank"] = 3
        with self.assertRaises(ValueError):
            suite.validate_case(case)
        with self.assertRaises(ValueError):
            suite.build_command(self.cases[0], self.cluster, 2, Path("/tmp/case"), False)
        with self.assertRaises(ValueError):
            suite.validate_cluster(self.cluster, suite.generate_cases(["main"], [25], [1])[0], False, False, False)

    def test_command_uses_explicit_runtime_ids(self) -> None:
        command, env = suite.build_command(self.cases[0], self.cluster, 1, Path("/tmp/case"), True)
        self.assertIn("--nnodes=2", command[1])
        self.assertIn("--nproc-per-node=2", command[1])
        self.assertIn("--node-rank=1", command[1])
        self.assertIn("--type=db", command)
        self.assertEqual(env["HCCL_WORKLOAD_DEVICES"], "6,7")
        self.assertEqual(env["HCCL_OP_EXPANSION_MODE"], "AI_CPU")
        self.assertNotIn("ASCEND_RT_VISIBLE_DEVICES", env)

    def test_910c_site_example_is_explicit_but_not_executable_by_default(self) -> None:
        cluster = suite.read_json(suite.ROOT / "test/configs/two_node_910c.example.json")
        suite.validate_cluster(cluster, self.cases[0], False, False, False)
        self.assertEqual([node["devices"] for node in cluster["nodes"]], [[1, 3], [1, 3]])
        self.assertEqual([node["node_id"] for node in cluster["nodes"]], ["node0", "node2"])
        self.assertTrue(all(len(node["runtime_files"]) == 4 for node in cluster["nodes"]))
        with self.assertRaisesRegex(ValueError, "confirm resource"):
            suite.validate_cluster(cluster, self.cases[0], True, False, False)

    def test_background_runs_on_target_runtime_id_not_local_rank(self) -> None:
        case = copy.deepcopy(next(c for c in self.cases if c["injection"]["kind"] == "copy_contention"))
        case["injection"]["target_rank"] = 3
        with tempfile.TemporaryDirectory() as name:
            control = CaseControl(case, self.cluster, 3, 1, Path(name))
            worker = MagicMock(returncode=0, pid=12345)
            worker.poll.return_value = 0
            with patch.object(control, "wait_files"), patch(
                    "test.anomaly_injection.four_node_control.subprocess.Popen", return_value=worker) as start:
                control.prepare()
                argv = start.call_args.args[0]
                self.assertEqual(argv[argv.index("--device") + 1], "7")
            control.close()

    def test_configuration_agreement_uses_four_not_sixteen_ranks(self) -> None:
        with tempfile.TemporaryDirectory() as name:
            control = CaseControl(self.cases[0], self.cluster, 0, 0, Path(name))
            expected, mismatch = MagicMock(), MagicMock()
            mismatch.item.return_value = 0
            torch = types.SimpleNamespace(tensor=MagicMock(side_effect=[expected, mismatch]), int32="int32",
                any=lambda value: types.SimpleNamespace(item=lambda: False))
            dist = types.SimpleNamespace(all_reduce=MagicMock(), ReduceOp=types.SimpleNamespace(SUM="sum", MAX="max"))
            control.verify_configuration(torch, dist, "npu:6")
            expected.__mul__.assert_called_once_with(4)
            control.close()

    def test_background_communication_isolates_hccl_listeners(self) -> None:
        case = next(c for c in self.cases if c["injection"]["kind"] == "communication_contention"
                    and c["injection"]["level"] == 1)
        cluster = copy.deepcopy(self.cluster)
        cluster["nodes"][1]["background_addr"] = "192.0.2.2"
        with tempfile.TemporaryDirectory() as name:
            control = CaseControl(case, cluster, 2, 0, Path(name))
            worker = MagicMock(returncode=0, pid=12345)
            worker.poll.return_value = 0
            with patch.object(control, "wait_files"), patch(
                    "test.anomaly_injection.four_node_control.subprocess.Popen", return_value=worker) as start:
                control.prepare()
                env = start.call_args.kwargs["env"]
                self.assertEqual(env["HCCL_HOST_SOCKET_PORT_RANGE"], "auto")
                self.assertEqual(env["HCCL_NPU_SOCKET_PORT_RANGE"], "auto")
                self.assertEqual(env["HCCL_STEP_TRACE"], "0")
            control.close()

    def test_controller_checks_world_size(self) -> None:
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            suite.write_json(root / "case.json", self.cases[0])
            suite.write_json(root / "cluster.json", self.cluster)
            args = types.SimpleNamespace(**self.cases[0]["workload"], seed=20261022, delay_ms=0, no_barrier=False)
            args.bucket_mib = "128,256,512"
            with self.assertRaisesRegex(ValueError, "world size"):
                load_control(root / "case.json", root / "cluster.json", root / "events", 0, 0, 16, args)
            control = load_control(root / "case.json", root / "cluster.json", root / "events", 0, 0, 4, args)
            control.close()

    def test_runner_validates_two_results_and_clears_stale_visibility(self) -> None:
        for worker_count, expected_code in ((2, 0), (1, 1)):
            with self.subTest(worker_count=worker_count), tempfile.TemporaryDirectory() as name:
                root = Path(name)
                cluster = copy.deepcopy(self.cluster)
                runtime = root / "runtime.bin"
                runtime.write_bytes(b"test runtime")
                cluster.update(preflight_confirmed=True, master_addr="192.0.2.1", op_expansion_mode="DEFAULT")
                for node in cluster["nodes"]:
                    node["runtime_files"] = [str(runtime)]
                suite.write_json(root / "case.json", self.cases[0])
                suite.write_json(root / "cluster.json", cluster)
                args = argparse.Namespace(case=root / "case.json", cluster=root / "cluster.json", node_rank=1,
                    output=root / "runs", attempt="test", execute=True, allow_background=False,
                    allow_network_change=False, no_profile=True, timeout=1)

                def capture(command, env, log, timeout):
                    for key in ("ASCEND_RT_VISIBLE_DEVICES", "HCCL_OP_EXPANSION_MODE", "HCCL_WORKLOAD_RESULT_DIR",
                                "HCCL_DIAG_INJECT_RANK"):
                        self.assertNotIn(key, env)
                    for rank in range(2, 2 + worker_count):
                        suite.write_json(log.parent / f"events/rank{rank}/workload-result.json",
                                         dict(rank=rank, world_size=4, status="passed", max_error=0))
                    return 0

                stale = {"ASCEND_RT_VISIBLE_DEVICES": "0", "HCCL_OP_EXPANSION_MODE": "HOST",
                         "HCCL_WORKLOAD_RESULT_DIR": "/stale", "HCCL_DIAG_INJECT_RANK": "7"}
                with patch.dict(suite.os.environ, stale), patch.object(suite, "captured", return_value={"returncode": 0}), \
                     patch.object(suite, "run_capture", side_effect=capture), patch("sys.stdout", new=io.StringIO()):
                    self.assertEqual(suite.execute_node(args), expected_code)

    def test_ledger_accepts_two_nodes_without_claiming_diagnosis(self) -> None:
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            case = self.cases[0]
            suite.write_json(root / "case.json", case)
            suite.write_json(root / "suite.json", {"cases": [{"case_id": case["case_id"], "path": "case.json"}]})
            for node in (0, 1):
                suite.write_json(root / "runs" / case["case_id"] / f"try/node{node}/execution.json", {"status": "completed"})
            result = suite.summarize(root / "suite.json", root / "runs", root / "ledger.csv")[0]
            self.assertEqual(result["status"], "execution_complete")
            self.assertEqual(result["completed_nodes"], 2)
            self.assertNotIn("diagnosis_accuracy", result)


if __name__ == "__main__":
    unittest.main()
