from __future__ import annotations

import argparse
import copy
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import types
import unittest
from unittest.mock import patch

from test import four_node_suite as suite
from test.anomaly_injection.four_node_control import CaseControl
from test.anomaly_injection.npu_background_load import communication_continue


class SuiteTests(unittest.TestCase):
    def setUp(self) -> None:
        self.cases = suite.generate_cases(["main"], [25], [20261022])
        self.cluster = suite.read_json(suite.ROOT / "test/configs/four_node_cluster.example.json")

    def find(self, kind: str) -> dict:
        return copy.deepcopy(next(c for c in self.cases if c["injection"]["kind"] == kind))

    def confirmed(self) -> dict:
        cluster = copy.deepcopy(self.cluster)
        cluster.update(preflight_confirmed=True, master_addr="192.0.2.10")
        cluster["nodes"][2]["background_addr"] = "192.0.2.12"
        return cluster

    def test_core_size_and_pairing(self) -> None:
        self.assertEqual(len(self.cases), 16)
        self.assertEqual(len({c["case_id"] for c in self.cases}), 16)
        for case in self.cases:
            self.assertEqual(case["baseline_case_id"], self.cases[0]["case_id"])
            self.assertEqual(case["workload"], self.cases[0]["workload"])
        self.assertEqual({c["injection"]["kind"] for c in self.cases}, suite.KINDS)

    def test_expanded_matrix_counts(self) -> None:
        self.assertEqual(len(suite.generate_cases(["main"], [10, 25, 40], [1, 2, 3])), 144)
        self.assertEqual(len(suite.generate_cases(list(suite.SIZES), [10, 25, 40], [1, 2, 3])), 432)

    def test_smoke_cases_are_short_and_separately_identified(self) -> None:
        cases = suite.generate_cases(["main"], [0], [1], smoke=True)
        self.assertEqual(len(cases), 16)
        for case in cases:
            self.assertTrue(case["case_id"].startswith("smoke-"))
            self.assertEqual(case["purpose"], "preflight")
            self.assertEqual(case["workload"]["iters"], 2)
            self.assertEqual(case["injection"]["duration_iters"], 1)
        self.assertEqual(suite.workload_stats(cases[0])["allreduces_including_warmup"], 72)

    def test_stats_and_weights(self) -> None:
        stats = suite.workload_stats(self.cases[0])
        self.assertEqual(stats["allreduces_including_warmup"], 1440)
        self.assertEqual(stats["input_mib_per_rank_iteration"], 7168)
        self.assertEqual(stats["input_mib_per_rank_measured"], 350 * 1024)
        self.assertEqual(stats["bf16_weight_bytes_per_rank"], 14 * 1024**3)

    def test_bad_window(self) -> None:
        for iteration in (-1, 46, 50):
            with self.subTest(iteration=iteration), self.assertRaises(ValueError):
                suite.generate_cases(["main"], [iteration], [1])

    def test_bad_sizes_and_duplicates(self) -> None:
        for sizes, positions, seeds in [(["unknown"], [25], [1]), (["main", "main"], [25], [1]),
                                        (["main"], [25, 25], [1]), (["main"], [25], [1, 1]), ([], [25], [1])]:
            with self.subTest(sizes=sizes, positions=positions), self.assertRaises(ValueError):
                suite.generate_cases(sizes, positions, seeds)

    def test_rank_validation_and_same_node_peer(self) -> None:
        case = self.find("communication_contention")
        case["injection"]["peer_rank"] = 9
        with self.assertRaises(ValueError):
            suite.validate_case(case)
        case["injection"]["target_rank"] = 16
        with self.assertRaises(ValueError):
            suite.validate_case(case)

    def test_internal_selector_is_explicit_and_not_scaled(self) -> None:
        selector = {"phase": "allgather_direct", "step": 0, "event": "tx_ack_start",
                    "skip_matches": 851, "evidence": "example only; device hit calibration required"}
        cases = suite.generate_cases(["main"], [25], [1], selector)
        self.assertEqual(cases[1]["injection"]["mode"], "library_task")
        with self.assertRaises(ValueError):
            suite.generate_cases(["main", "large"], [25], [1], selector)
        selector["evidence"] = ""
        with self.assertRaises(ValueError):
            suite.generate_cases(["main"], [25], [1], selector)

    def test_example_is_dry_run_only(self) -> None:
        suite.validate_cluster(self.cluster, self.cases[0], False, False, False)
        with self.assertRaises(ValueError):
            suite.validate_cluster(self.cluster, self.cases[0], True, False, False)

    def test_background_and_network_permissions(self) -> None:
        cluster = self.confirmed()
        for kind in ("copy_contention", "compute_contention", "communication_contention"):
            with self.subTest(kind=kind), self.assertRaises(ValueError):
                suite.validate_cluster(cluster, self.find(kind), True, False, False)
        with self.assertRaises(ValueError):
            suite.validate_cluster(cluster, self.find("nic_limit"), True, True, False)
        with self.assertRaises(ValueError):
            suite.validate_cluster(cluster, self.find("nic_limit"), True, True, True)
        with self.assertRaises(ValueError):
            suite.validate_cluster(cluster, self.find("communication_contention"), True, True, False)
        cluster["shared_path_evidence"] = "operator verified foreground/background share port; counters still needed"
        suite.validate_cluster(cluster, self.find("communication_contention"), True, True, False)

    def test_bad_device_mapping_and_port_overlap(self) -> None:
        cluster = self.confirmed()
        cluster["nodes"][0]["devices"] = [0, 0, 2, 3]
        with self.assertRaises(ValueError):
            suite.validate_cluster(cluster, self.cases[0], False, False, False)
        cluster = self.confirmed()
        cluster["background_port_base"] = cluster["master_port"]
        with self.assertRaises(ValueError):
            suite.validate_cluster(cluster, self.cases[0], False, False, False)

    def test_commands_use_four_nodes_and_db_only(self) -> None:
        command, env = suite.build_command(self.cases[0], self.cluster, 2, Path("/tmp/four-node-test"), True)
        self.assertEqual(command[0], "msprof")
        self.assertIn("--type=db", command)
        self.assertIn("--nnodes=4", command[1])
        self.assertIn("--node-rank=2", command[1])
        self.assertIn("--max-restarts=0", command[1])
        self.assertEqual(env["HCCL_WORKLOAD_DEVICES"], "0,2,4,6")
        self.assertNotIn("ASCEND_RT_VISIBLE_DEVICES", env)
        self.assertFalse(any(key.startswith("HCCL_DIAG_INJECT") for key in env))

    def test_internal_environment_requires_native_hit_review(self) -> None:
        selector = {"phase": "ag", "step": 1, "event": "tx", "skip_matches": 10, "evidence": "checked"}
        case = suite.generate_cases(["main"], [25], [1], selector)[1]
        _, env = suite.build_command(case, self.cluster, 2, Path("/tmp/test-case"), False)
        self.assertEqual(env["HCCL_DIAG_INJECT_DELAY_US"], "1000")
        self.assertEqual(env["HCCL_DIAG_INJECT_MAX_HITS"], "1")
        with self.assertRaises(ValueError):
            suite.validate_cluster(self.confirmed(), case, True, False, False)

    def test_profiler_rejects_whitespace_paths(self) -> None:
        with self.assertRaises(ValueError):
            suite.build_command(self.cases[0], self.cluster, 0, Path("/tmp/path with spaces"), True)

    def test_failed_preflight_is_recorded_without_starting_workload(self) -> None:
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            suite.write_json(root / "case.json", self.cases[0])
            suite.write_json(root / "cluster.json", self.cluster)
            args = argparse.Namespace(case=root / "case.json", cluster=root / "cluster.json", node_rank=0,
                                      output=root / "runs", attempt="attempt-001", execute=True,
                                      allow_background=False, allow_network_change=False, no_profile=False, timeout=1)
            with patch.object(suite, "run_capture") as run:
                with patch("sys.stdout", new=io.StringIO()):
                    self.assertEqual(suite.execute_node(args), 1)
                run.assert_not_called()
            state = suite.read_json(root / "runs" / self.cases[0]["case_id"] / "attempt-001/node0/execution.json")
            self.assertEqual(state["status"], "preflight_failed")

    def test_output_paths_cannot_escape(self) -> None:
        for value in ("..", "../other", "/tmp/other", "x/y", "a b"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                suite.identifier(value)

    def test_timeout_terminates_owned_process(self) -> None:
        with tempfile.TemporaryDirectory() as name:
            with self.assertRaises(subprocess.TimeoutExpired):
                suite.run_capture([sys.executable, "-c", "import time; time.sleep(60)"],
                                  {}, Path(name) / "capture.log", 0.05)

    def test_nic_apply_failure_still_restores_original_snapshot(self) -> None:
        hooks = {name: ["site-nic-tool", name, "{percent}", "{snapshot}"]
                 for name in ("query", "apply", "verify", "restore")}
        replies = [subprocess.CompletedProcess([], 0, '{"original_rate": 123}', ""),
                   subprocess.CompletedProcess([], 1, "", "apply failed"),
                   subprocess.CompletedProcess([], 0, "", "")]
        with tempfile.TemporaryDirectory() as name, patch.object(suite.subprocess, "run", side_effect=replies) as run:
            limit = suite.NicLimit(hooks, 50, Path(name))
            try:
                with self.assertRaises(subprocess.CalledProcessError):
                    limit.apply()
            finally:
                limit.restore()
            self.assertEqual(suite.read_json(Path(name) / "nic-original.json"), {"original_rate": 123})
            self.assertEqual(run.call_count, 3)
            self.assertEqual(run.call_args.args[0][1], "restore")

    def test_nic_wrong_cap_is_not_success(self) -> None:
        hooks = {name: ["site-tool", name] for name in ("query", "apply", "verify", "restore")}
        replies = [subprocess.CompletedProcess([], 0, '{}', ''), subprocess.CompletedProcess([], 0, '', ''),
                   subprocess.CompletedProcess([], 0, '{"configured_percent": 75}', '')]
        with tempfile.TemporaryDirectory() as name, patch.object(suite.subprocess, "run", side_effect=replies):
            with self.assertRaises(ValueError):
                suite.NicLimit(hooks, 50, Path(name)).apply()

    def test_ledger_retains_missing_failed_and_retried_cases(self) -> None:
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            cases = self.cases[:2]
            entries = []
            for case in cases:
                path = "cases/" + case["case_id"] + ".json"
                suite.write_json(root / path, case)
                entries.append({"case_id": case["case_id"], "path": path})
            suite.write_json(root / "suite.json", {"cases": entries})
            run_root = root / "runs" / cases[0]["case_id"]
            suite.write_json(run_root / "attempt-001/node0/execution.json", {"status": "timeout"})
            for node in range(4):
                suite.write_json(run_root / f"attempt-002/node{node}/execution.json", {"status": "completed"})
            rows = suite.summarize(root / "suite.json", root / "runs", root / "ledger.csv")
            self.assertEqual([r["status"] for r in rows], ["execution_failed", "execution_complete", "not_run"])
            self.assertTrue((root / "ledger.csv").read_text(encoding="utf-8").startswith("case_id,"))

    def test_controller_delay_only_matches_selected_slot_and_rank(self) -> None:
        with tempfile.TemporaryDirectory() as name:
            case = self.find("progress_delay")
            control = CaseControl(case, self.cluster, 8, 0, Path(name))
            with patch("test.anomaly_injection.four_node_control.time.sleep") as sleep:
                control.before_collective(-1, 3, 1)
                control.before_collective(25, 2, 1)
                control.before_collective(25, 3, 1)
                sleep.assert_called_once_with(0.001)
            control.close()
            events = [json.loads(line) for line in (Path(name) / "rank8/events.jsonl").read_text().splitlines()]
            self.assertEqual(sum(e["event"] == "arrival_delay_applied" for e in events), 1)

    def test_normal_control_has_same_window_barriers(self) -> None:
        with tempfile.TemporaryDirectory() as name:
            control = CaseControl(self.cases[0], self.cluster, 0, 0, Path(name))
            self.assertEqual([i for i in range(50) if control.transition(i)], [25, 30])
            control.close()

    def test_native_hit_is_checked_without_claiming_physical_identity(self) -> None:
        selector = {"phase": "ag", "step": 0, "event": "tx", "skip_matches": 10, "evidence": "calibrated"}
        case = suite.generate_cases(["main"], [25], [1], selector)[1]
        message = ("[HcclDiagInject] type[task_launch_delay] delay_us[1000] user_rank[8] "
                   "comm_rank[8] phase[ag] step[0] event[tx] occurrence[10] hit[0]\n")
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            self.assertEqual(suite.injection_observation(case, root), "native_hit_not_observed")
            logs = root / "node2/ascend_log"
            logs.mkdir(parents=True)
            (logs / "plog.log").write_text(message, encoding="utf-8")
            capture = root / "node2/private/capture.log"
            capture.parent.mkdir()
            capture.write_text(message, encoding="utf-8")
            self.assertEqual(suite.injection_observation(case, root),
                             "native_hit_observed_task_identity_and_effect_unverified")
            with (logs / "plog.log").open("a") as handle:
                handle.write(message.replace("occurrence[10] hit[0]", "occurrence[11] hit[1]"))
            self.assertEqual(suite.injection_observation(case, root), "invalid_multiple_native_hits")

    def test_wrong_native_target_is_not_a_hit(self) -> None:
        selector = {"phase": "ag", "step": 0, "event": "tx", "skip_matches": 0, "evidence": "calibrated"}
        case = suite.generate_cases(["main"], [25], [1], selector)[1]
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            path = root / "node2/private/capture.log"
            path.parent.mkdir(parents=True)
            path.write_text("[HcclDiagInject] type[task_launch_delay] user_rank[9] delay_us[1000] "
                            "phase[ag] step[0] event[tx]\n", encoding="utf-8")
            self.assertEqual(suite.injection_observation(case, root), "native_hit_not_observed")

    def test_worker_completion_does_not_prove_contention(self) -> None:
        case = self.find("copy_contention")
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            self.assertEqual(suite.injection_observation(case, root), "not_observed")
            suite.write_json(root / "node2/private/events/rank8/worker0/result.json", {"operations": 12})
            self.assertEqual(suite.injection_observation(case, root), "background_executed_effect_unverified")

    def test_optional_workload_callback_keeps_collective_order(self) -> None:
        torch = types.ModuleType("torch")
        dist = types.ModuleType("torch.distributed")
        nn = types.ModuleType("torch.nn")
        functional = types.ModuleType("torch.nn.functional")
        torch.distributed, torch.nn, nn.functional = dist, nn, functional
        calls = []
        class Tensor:
            def numel(self) -> int:
                return 1024
            def fill_(self, value: int) -> None:
                calls.append("fill")
            def mul_(self, value: float) -> None:
                pass
        dist.all_reduce = lambda *args, **kwargs: calls.append("allreduce")
        dist.ReduceOp = types.SimpleNamespace(SUM="sum")
        modules = {"torch": torch, "torch.distributed": dist, "torch.nn": nn,
                   "torch.nn.functional": functional, "torch_npu": types.ModuleType("torch_npu")}
        path = suite.ROOT / "test/multinode_commmix_train.py"
        with patch.dict(sys.modules, modules):
            spec = importlib.util.spec_from_file_location("commmix_for_test", path)
            workload = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(workload)
            backends = []
            def compute(activation, weight, backend="matmul"):
                backends.append(backend)
                return activation
            workload.compute_block = compute
            slots = []
            def before(iteration: int, block: int, bucket: int) -> None:
                slots.append((iteration, block, bucket))
                calls.append("before")
            workload.run_transformer_step(25, 8, Tensor(), [(None,) * 4] * 2, [Tensor() for _ in range(3)],
                                          -1, 0, -1, -1, 0, before, gemm_backend="grouped")
            self.assertEqual(slots, [(25, block, bucket) for block in range(2) for bucket in range(3)])
            self.assertEqual(calls, ["fill", "before", "allreduce"] * 6)
            self.assertEqual(backends, ["grouped"] * 8)
            calls.clear()
            recorder = types.SimpleNamespace(
                prepare=lambda *args: calls.append("prepare"),
                begin=lambda *args: calls.append("begin"), end=lambda: calls.append("end"))
            workload.compute_block = lambda activation, *args: (calls.append("compute"), activation)[1]
            workload.run_transformer_step(25, 8, Tensor(), [(None,) * 4], [Tensor() for _ in range(3)],
                                          -1, 0, -1, -1, 0, before, recorder, gemm_backend="grouped")
            self.assertEqual(calls, ["prepare", "compute", "fill", "before", "begin", "allreduce", "end"] * 2 +
                                   ["prepare", "compute", "compute", "fill", "before", "begin", "allreduce", "end"])


class Store:
    def __init__(self) -> None:
        self.values = {}
        self.condition = threading.Condition()

    def set(self, key: str, value: str) -> None:
        with self.condition:
            self.values[key] = value.encode()
            self.condition.notify_all()

    def get(self, key: str) -> bytes:
        with self.condition:
            if not self.condition.wait_for(lambda: key in self.values, timeout=2):
                raise TimeoutError("test store peer missing")
            return self.values[key]


class BackgroundProtocolTests(unittest.TestCase):
    def test_continue_and_peer_stop_are_symmetric(self) -> None:
        for flags, expected in [([False, False], [True, True]), ([False, True], [False, False]),
                                ([True, False], [False, False]), ([True, True], [False, False])]:
            with self.subTest(flags=flags):
                store, result = Store(), [None, None]
                def worker(rank: int) -> None:
                    result[rank] = communication_continue(store, 0, rank, flags[rank])
                threads = [threading.Thread(target=worker, args=(rank,)) for rank in range(2)]
                for thread in threads:
                    thread.start()
                for thread in threads:
                    thread.join(timeout=3)
                    self.assertFalse(thread.is_alive())
                self.assertEqual(result, expected)


if __name__ == "__main__":
    unittest.main()
