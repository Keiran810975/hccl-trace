from __future__ import annotations

from collections import Counter
import csv
import hashlib
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest

from test.gpt2_diagnosis_suite import cases, evaluate, summarize, KINDS, write_plan, write_continuation, validate_case, validate_plan
from test.single_node_capture import bind
from test import test_single_node_capture as fixtures
from test.run_gpt2_case import cleanup, gate_failure_evidence
from test.run_gpt2_suite import atomic_csv, export, operator_environment, validate_host, allocation_is_idle
from test.gpt2_train import verify_replicated_initialization


class Gpt2SuiteTests(unittest.TestCase):
    @staticmethod
    def continuation_parent(root):
        write_plan(root / "plan")
        completed = [dict(case_id=c["case_id"], injection=c["injection"], status="diagnosed") for c in cases()[:11]]
        (root / "state.json").write_text(json.dumps(dict(status="stopped", active_case=None, completed=11,
                                                        cases=completed)))

    def test_continuation_preserves_parent_and_random_strengths(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            self.continuation_parent(root)
            before = {str(p): p.read_bytes() for p in root.rglob("*.json")}
            plan = write_continuation(root, root / "new-plan")
            second = write_continuation(root, root / "same-seed-plan")
            self.assertEqual(plan, second)
            self.assertEqual(plan["requested_runs"], 31)
            self.assertEqual(validate_plan(plan, root / "new-plan"),
                             dict(normal=1, copy_contention=10, communication_contention=10, compute_contention=10))
            for entry in plan["cases"]:
                original = json.loads((root / "plan" / entry["path"]).read_text())
                changed = json.loads((root / "new-plan" / entry["path"]).read_text())
                self.assertEqual(changed["workload"], dict(original["workload"], iters=50))
                self.assertEqual(changed["execution_cohort"]["physical_node"], "node3")
                if original["injection"]["kind"] != "normal":
                    self.assertTrue(10 <= changed["injection"]["iteration"] <= 39)
                    self.assertEqual(changed["execution_cohort"]["original_iteration"], original["injection"]["iteration"])
                    self.assertEqual({k: v for k, v in changed["injection"].items() if k != "iteration"},
                                     {k: v for k, v in original["injection"].items() if k != "iteration"})
            for path, content in before.items():
                self.assertEqual(Path(path).read_bytes(), content)
            summary = summarize([], plan)
            self.assertEqual(summary["requested_runs"], 31)
            self.assertEqual([g["requested"] for g in summary["groups"]], [0, 10, 10, 10])

    def test_continuation_refuses_active_parent_and_overwrite(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            self.continuation_parent(root)
            state_path = root / "state.json"
            state = json.loads(state_path.read_text())
            state["active_case"] = "gpt2-4r-copy_contention-01"
            state_path.write_text(json.dumps(state))
            with self.assertRaisesRegex(ValueError, "stopped"):
                write_continuation(root, root / "new-plan")
            self.assertFalse((root / "new-plan").exists())
            state["active_case"] = None
            state_path.write_text(json.dumps(state))
            write_continuation(root, root / "new-plan")
            with self.assertRaises(FileExistsError):
                write_continuation(root, root / "new-plan")

    def test_fifty_iterations_require_explicit_cohort_and_fitting_window(self):
        case = cases()[11]
        case["workload"]["iters"] = 50
        with self.assertRaisesRegex(ValueError, "workload"):
            validate_case(case)
        case["execution_cohort"] = dict(physical_node="node3", measured_iterations=50, parent_measured_iterations=100)
        case["injection"]["iteration"] = 20
        validate_case(case)
        for start in (0, 49):
            case["injection"]["iteration"] = start
            with self.assertRaisesRegex(ValueError, "five preceding"):
                validate_case(case)
        case["injection"]["iteration"] = 20
        case["workload"]["n_layer"] = 6
        with self.assertRaisesRegex(ValueError, "workload"):
            validate_case(case)

    def test_node3_host_scope_cannot_be_used_on_other_nodes(self):
        root = Path("/home/zjy-new/workspace/gpt2-single-node3-20261029-001")
        validate_host(root, "node3", "liteserver-560t-3.novalocal")
        for host in ("liteserver-560t-1.novalocal", "liteserver-560t-2.novalocal"):
            with self.assertRaisesRegex(ValueError, "reviewed"):
                validate_host(root, "node3", host)
        with self.assertRaises(ValueError):
            validate_host(Path("/tmp/gpt2-single-node3-test"), "node3", "liteserver-560t-3")

    def test_node0_continuation_is_explicit_and_does_not_reuse_node3_metadata(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            self.continuation_parent(root)
            plan = write_continuation(root, root / "new-plan", physical_node="node0")
            validate_plan(plan, root / "new-plan")
            self.assertEqual(plan["execution_cohort"]["physical_node"], "node0")
            self.assertEqual(plan["execution_cohort"]["allocation"], "node0-cards0-3")
            self.assertEqual(plan["execution_cohort"]["validation_mode"], "formal-control-first")
            self.assertEqual(plan["cases"][0]["case_id"], "gpt2-4r-normal")

    def test_partial_allocation_checks_both_chips_and_default_remains_strict(self):
        text = "".join(f"| {card} Ascend910 |\n| 0 {2*card} | 3100 / 65536 |\n"
                       f"| {card} Ascend910 |\n| 1 {2*card+1} | 2900 / 65536 |\n"
                       f"| No running processes found in NPU {card} |\n" for card in range(4))
        text += "| 7 Ascend910 |\n| 1 15 | 47000 / 65536 |\n| 7 1 123 VLLMWorker |\n"
        self.assertTrue(allocation_is_idle(text, "node0-cards0-3"))
        self.assertFalse(allocation_is_idle(text, "whole-host"))
        for changed in (text.replace("No running processes found in NPU 2", "2 1 123 VLLMWorker"),
                        text.replace("| 1 3 | 2900 / 65536 |", "| 1 3 | 47000 / 65536 |"),
                        text.replace("| 1 7 | 2900 / 65536 |", "")):
            self.assertFalse(allocation_is_idle(changed, "node0-cards0-3"))

    def test_atomic_csv_preserves_previous_summary_on_write_failure(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            path = root / "results.csv"
            path.write_text("previous\n", encoding="utf-8")
            path.chmod(0o444)
            with self.assertRaisesRegex(RuntimeError, "interrupted"):
                with atomic_csv(path) as stream:
                    stream.write("incomplete\n")
                    self.assertEqual(path.read_text(), "previous\n")
                    raise RuntimeError("interrupted")
            self.assertEqual(path.read_text(), "previous\n")
            self.assertEqual(list(root.iterdir()), [path])
            with atomic_csv(path) as stream:
                stream.write("complete\n")
            self.assertEqual(path.read_text(), "complete\n")

    def test_failed_long_capture_reports_original_gate_without_relaxing_it(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "merge_summary.csv").write_text(
                "node_id,metric,value\nnode0,merge_gate_passed,0\n"
                "node0,exact_match_rate_percent,77.55\nnode0,unmatched_semantic,47172\n"
                "node0,duplicate_profiler_execution_keys,4\n")
            report = gate_failure_evidence(root)
            self.assertFalse(report["gates_relaxed"])
            self.assertTrue(report["raw_capture_retained"])
            self.assertIn("77.55%", report["reasons"][0])
            self.assertIn("47172", report["reasons"][0])
            self.assertEqual(report["merge_metrics"]["node0"]["merge_gate_passed"], "0")

    def test_skipping_ddp_init_sync_requires_all_initial_parameter_hashes_equal(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            fingerprint = dict(parameter_sha256="full-parameter-byte-hash", parameter_count=124439808)
            for rank in range(1, 4):
                (root / ("initialization-rank-{}.json".format(rank))).write_text(json.dumps(dict(rank=rank, **fingerprint)))
            verify_replicated_initialization(root, 0, fingerprint)
            (root / "initialization-rank-2.json").write_text(json.dumps(dict(rank=2, **dict(fingerprint, parameter_sha256="other"))))
            with self.assertRaisesRegex(ValueError, "differ across ranks"):
                verify_replicated_initialization(root, 0, fingerprint)
        with tempfile.TemporaryDirectory() as temporary:
            with self.assertRaises(TimeoutError):
                verify_replicated_initialization(Path(temporary), 0, fingerprint, timeout=0)

    def test_operator_runtime_is_explicit_complete_and_owned(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "gpt2-single-test"
            runtime = root / "a3-runtime"
            self.assertEqual(operator_environment(root, None), "")
            with self.assertRaisesRegex(ValueError, "inside this owned"):
                operator_environment(root, Path(temporary) / "outside")
            with self.assertRaisesRegex(ValueError, "incomplete"):
                operator_environment(root, runtime)
            (runtime / "opp/built-in").mkdir(parents=True)
            libs = runtime / "aarch64-linux/lib64"
            libs.mkdir(parents=True)
            for name in ("libopapi.so", "libopapi_math.so", "libopapi_nn.so", "libopapi_transformer.so"):
                (libs / name).touch()
            shell = operator_environment(root, runtime)
            self.assertIn("ASCEND_OPP_PATH=/workspace/gpt2-single-test/a3-runtime/opp", shell)
            self.assertIn(":${LD_LIBRARY_PATH:-}", shell)
            self.assertNotIn("install", shell)

    def test_exact_plan_sizes_windows_and_single_background(self):
        plan = cases()
        self.assertEqual(len(plan), 41)
        self.assertEqual(plan, cases())
        self.assertEqual(Counter(c["injection"]["kind"] for c in plan), dict(normal=1, **{k: 10 for k in KINDS}))
        for case in plan[1:]:
            inj = case["injection"]
            self.assertGreaterEqual(inj["iteration"], 10)
            self.assertLessEqual(inj["iteration"] + inj["duration_iters"], 100)
            if inj["kind"] != "progress_delay":
                self.assertEqual(inj["background_processes"], 1)
        self.assertTrue(all(c["workload"] == plan[0]["workload"] for c in plan))

    def test_all_candidates_are_evaluated_without_reselecting_primary(self):
        roots = [dict(root_id=str(i), graph_id="task-" + str(i), node_id="run/node0", user_rank=rank,
                      observed_start_ns=start, observed_stop_ns=stop, status=status)
                 for i, (rank, start, stop, status) in enumerate([
                     (0, 10, 20, "dependency_supported_candidate"), (1, 100, 200, "dependency_supported_candidate"),
                     (2, 100, 200, "isolated_slow_task"), (1, 200, 220, "isolated_slow_task"),
                     (1, 100, 200, "unattributed_gap")])]
        report = dict(root_causes=roots, primary_source_candidate_id="0", diagnosis_status="localized_candidate")
        windows = [dict(node_id="run/node0", target_ranks=[1], actual_hit=True, start_ns=100, stop_ns=200)]
        value = evaluate(report, windows)
        self.assertEqual(value["candidate_count"], 4)
        self.assertEqual(value["candidate_hit_count"], 1)
        self.assertEqual(value["candidate_hit_fraction"], .25)
        self.assertTrue(value["any_candidate_hit"])
        self.assertFalse(value["primary_hit"])
        self.assertEqual(report["primary_source_candidate_id"], "0")

    def test_no_candidates_and_absent_truth_are_not_successes(self):
        report = dict(root_causes=[], primary_source_candidate_id=None, diagnosis_status="unresolved_waits")
        window = dict(node_id="node0", target_ranks=[1], actual_hit=True, start_ns=100, stop_ns=200)
        value = evaluate(report, [window])
        self.assertFalse(value["any_candidate_hit"])
        self.assertIsNone(value["candidate_hit_fraction"])
        with self.assertRaises(ValueError):
            evaluate(report, [])
        self.assertFalse(evaluate(report, [], normal=True)["normal_has_candidates"])

    def test_summary_distinguishes_case_hits_and_candidate_fraction(self):
        results = []
        for case in cases()[1:]:
            results.append(dict(injection=case["injection"], status="diagnosed", evaluation=dict(any_candidate_hit=True,
                candidate_count=10, candidate_hit_count=1)))
        for group in summarize(results)["groups"]:
            self.assertEqual(group["case_hit_rate"], 1)
            self.assertEqual(group["pooled_candidate_hit_fraction"], .1)

    def test_csv_exports_every_candidate_and_actual_injection_window(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            case = cases()[1]
            source = dict(root_id="root", graph_id="task", node_id="run/node0", user_rank=case["injection"]["target_rank"],
                          status="dependency_supported_candidate", observed_start_ns=100, observed_stop_ns=200)
            report = dict(root_causes=[source], primary_source_candidate_id="root", diagnosis_status="localized_candidate")
            windows = [dict(node_id="run/node0", target_ranks=[source["user_rank"]], actual_hit=True, start_ns=100, stop_ns=200)]
            record = root / "records" / case["case_id"]
            record.mkdir(parents=True)
            (record / "diagnosis.json").write_text(json.dumps(report))
            item = dict(case_id=case["case_id"], injection=case["injection"], status="diagnosed", timings=[],
                        evaluation=evaluate(report, windows), actual_windows=windows, diagnosis_status="localized_candidate")
            export(root, [item])
            with (root / "candidates.csv").open() as f:
                rows = list(csv.DictReader(f))
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["overlap_ns"], "100")
            with (root / "results.csv").open() as f:
                result, = list(csv.DictReader(f))
            self.assertEqual(json.loads(result["actual_windows"]), windows)
            self.assertEqual(result["strength_unit"], "ms")
            for name in ("results.csv", "candidates.csv"):
                (root / name).chmod(0o444)
            export(root, [item])
            with (root / "candidates.csv").open() as f:
                self.assertEqual(len(list(csv.DictReader(f))), 1)

    def test_ddp_binder_distinguishes_initial_broadcast_and_gradient_allreduces(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            fixtures.PublicBindingTests().fixture(root)
            for path in (root / "public").glob("rank-*.jsonl"):
                records = [json.loads(line) for line in path.read_text().splitlines()]
                for item in records:
                    item["bucket_signature"] = "stable-parameter-set"
                path.write_text("".join(json.dumps(r) + "\n" for r in records))
            for path in (root / "msprof").rglob("msprof_*.db"):
                with sqlite3.connect(path) as db:
                    device = db.execute("SELECT deviceId FROM COMMUNICATION_OP LIMIT 1").fetchone()[0]
                    db.execute("INSERT INTO STRING_IDS VALUES(99,'hcom_broadcast__612_0_1')")
                    db.execute("INSERT INTO COMMUNICATION_OP VALUES(?,1,99,1024,4)", (device,))
            self.assertEqual(len(bind(root, "ddp", ddp_capture=True)), 4)
            mapping = json.loads((root / "iteration-map.json").read_text())
            self.assertEqual(len(mapping["operations"]), 8)

    def test_ddp_binder_refuses_changed_bucket_parameters(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            fixtures.PublicBindingTests().fixture(root)
            for path in (root / "public").glob("rank-*.jsonl"):
                rows = [json.loads(line) for line in path.read_text().splitlines()]
                for item in rows:
                    item["bucket_signature"] = "changed" if item["iteration"] == 7 else "usual"
                path.write_text("".join(json.dumps(r) + "\n" for r in rows))
            with self.assertRaisesRegex(ValueError, "bucket structure changed"):
                bind(root, "ddp", ddp_capture=True)

    def test_cleanup_requires_verified_retention_and_owned_directory(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            run, record = root / "attempt", root / "record"
            run.mkdir()
            record.mkdir()
            (run / "msprof").mkdir()
            (run / "msprof/raw.db").write_bytes(b"raw")
            (run / "owned-attempt.json").write_text(json.dumps(dict(case_id="normal", directory=str(run.resolve()))))
            (record / "result.json").write_text("{}")
            receipt = dict(case_id="normal", raw_artifacts_eligible_for_removal=True,
                           sha256={"result.json": hashlib.sha256(b"{}").hexdigest()})
            (record / "retention-receipt.json").write_text(json.dumps(receipt))
            (record / "result.json").write_text("tampered")
            with self.assertRaisesRegex(ValueError, "checksum"):
                cleanup(run, record)
            self.assertTrue((run / "msprof/raw.db").exists())
            (record / "result.json").write_text("{}")
            cleanup(run, record)
            self.assertFalse((run / "msprof").exists())
            self.assertTrue((record / "result.json").exists())


if __name__ == "__main__":
    unittest.main()
