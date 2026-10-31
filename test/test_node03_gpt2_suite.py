from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from test.node03_gpt2_suite import build_plan, validate_plan, adapt_ddp_public
from hccl.tools.diagnosis.workload_binder import _read_calls
from test.node03_gpt2_control import MultiNodeControl, worker_environment
from test.gpt2_train import verify_replicated_initialization


class Node03SuiteTests(unittest.TestCase):
    def test_exactly_six_independent_full_workloads(self):
        plan = build_plan()
        validate_plan(plan)
        self.assertEqual(plan, build_plan())
        self.assertEqual(len({c["case_id"] for c in plan["cases"]}), 6)
        self.assertTrue(all(c["workload"]["warmup"] == 10 and c["workload"]["iters"] == 50 for c in plan["cases"]))
        plan["cases"][-1]["injection"]["iteration"] = 49
        with self.assertRaises(ValueError):
            validate_plan(plan)

    def test_bandwidth_is_a_real_verified_port_setting_not_tc(self):
        case = build_plan()["cases"][-1]
        self.assertTrue(case["injection"]["query_apply_verify_restore_required"])
        self.assertEqual(case["injection"]["limit_mbps"], 20000)

    def public(self, root):
        calls = [dict(sequence=0, rank=4, runtime_device_id=1, stage="measured", iteration=20,
                      count=1024, dtype="fp32", reduction="sum", bucket_signature="a" * 64,
                      before=dict(raw_ns=100), after=dict(raw_ns=120), preparation_before=dict(raw_ns=90))]
        boundaries = [dict(rank=4, stage="measured", iteration=20, device_synchronized=True, clocks=dict(raw_ns=200))]
        (root / "rank-4.jsonl").write_text("\n".join(json.dumps(c) for c in calls))
        (root / "boundaries-rank-4.jsonl").write_text("\n".join(json.dumps(b) for b in boundaries))

    def test_adapter_preserves_observed_clocks_and_explicit_members(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.public(root)
            output = adapt_ddp_public(root, root / "sdk", run_id="r", node_id="node3", rank=4, device=1, pid=42, participants=list(range(8)))
            header, calls = _read_calls(output)
            self.assertEqual(header["device_id"], 1)
            self.assertEqual(calls[0]["before"]["raw_ns"], 100)
            self.assertEqual(calls[0]["completion_raw_ns"], 200)
            self.assertEqual(calls[0]["participants"], list(range(8)))
            self.assertEqual(calls[0]["call_site"], "ddp.gradient." + "a" * 64)

    def test_adapter_rejects_missing_completion_and_wrong_device(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.public(root)
            with self.assertRaises(ValueError):
                adapt_ddp_public(root, root / "sdk", run_id="r", node_id="node3", rank=4, device=3, pid=42, participants=list(range(8)))
            (root / "boundaries-rank-4.jsonl").write_text("")
            with self.assertRaises(ValueError):
                adapt_ddp_public(root, root / "sdk", run_id="r", node_id="node3", rank=4, device=1, pid=42, participants=list(range(8)))
            self.assertFalse((root / "sdk").exists())

    def test_eight_ranks_verify_cpu_parameter_hashes_without_shared_filesystem(self):
        fingerprint = dict(parameter_sha256="a" * 64, parameter_count=124439808)

        class Store:
            def __init__(self):
                self.values = {"hccl-diagnose/model-initialization/" + str(r): json.dumps(dict(rank=r, **fingerprint))
                               for r in range(8)}

            def set(self, key, value):
                self.values[key] = value

            def get(self, key):
                return self.values[key].encode()

        with tempfile.TemporaryDirectory() as tmp:
            store = Store()
            verify_replicated_initialization(tmp, 4, fingerprint, world_size=8, store=store)
            self.assertEqual(len(list(Path(tmp).glob("initialization-rank-*.json"))), 1)
            store.values["hccl-diagnose/model-initialization/7"] = json.dumps(dict(rank=7, parameter_sha256="b" * 64))
            with self.assertRaisesRegex(ValueError, "differ"):
                verify_replicated_initialization(tmp, 4, fingerprint, world_size=8, store=store)

    def test_background_environment_does_not_mutate_foreground(self):
        original = dict(PROFILING_MODE="true", MSPROF_CONFIG="private", HCCL_IF_IP="192.169.0.220",
                        HCCL_WORKLOAD_RESULT_DIR="foreground", ASCEND_OPP_PATH="owned-runtime")
        result = worker_environment(original)
        self.assertEqual(original["PROFILING_MODE"], "true")
        self.assertNotIn("PROFILING_MODE", result)
        self.assertNotIn("MSPROF_CONFIG", result)
        self.assertNotIn("HCCL_WORKLOAD_RESULT_DIR", result)
        self.assertEqual(result["HCCL_STEP_TRACE"], "0")
        self.assertEqual(result["ASCEND_OPP_PATH"], "owned-runtime")
        self.assertEqual(result["HCCL_IF_IP"], "192.169.0.220")

    def test_background_start_does_not_wait_for_active_and_uses_global_rank_mapping(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            case = build_plan()["cases"][2]
            path = root / "case.json"
            path.write_text(json.dumps(case))
            controller = MultiNodeControl(path, root / "private", 4, {4: 1, 5: 3, 6: 5, 7: 7})
            with patch.object(controller, "wait", side_effect=AssertionError("must not hold the foreground for active ACK")):
                controller.start(2)
            self.assertTrue((controller.directory / "start").exists())
            self.assertEqual(controller.devices[controller.rank], 1)
            controller.close()

    def test_communication_has_one_worker_per_node_and_no_unrelated_rank(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / "case.json"
            path.write_text(json.dumps(build_plan()["cases"][3]))
            for rank, owner in ((0, True), (4, True), (1, False), (7, False)):
                controller = MultiNodeControl(path, root / str(rank), rank, {rank: 1})
                self.assertEqual(controller.owner, owner)
                controller.close()


if __name__ == "__main__":
    unittest.main()
