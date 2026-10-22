#!/usr/bin/env python3
"""Hand-computable critical paths and artifact/CLI regression tests."""

from __future__ import annotations

import csv
import json
import os
import subprocess
import sys
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from diagnosis.critical_path import analyze_critical_path, export_report
    from diagnosis.schema import write_csv
else:
    from .critical_path import analyze_critical_path, export_report
    from .schema import write_csv


def task(key, start, stop, stream=0, kind="sdma", node="node0", subtask=-1):
    return dict(_graph_id=key, _node_id=node, _device_id=0, _stream_id=stream,
        _task_id=ord(key[0]), _user_rank=stream, _subtask_id=subtask,
        _operation_scope="op0", _node_kind="execution", profiler_task_kind=kind,
        task_start=str(start), task_stop=str(stop), _start_order=Decimal(str(start)),
        _stop_order=Decimal(str(stop)))


def order(src, dst):
    return dict(edge_id=src + "_" + dst, src=src, dst=dst,
        kind="direct_stream_order_observed", confidence="observed")


def sync(src, dst):
    return dict(edge_id=src + "_" + dst, src=src, dst=dst,
        kind="direct_notify_sync_exact", confidence="exact")


def by_task(report):
    return {row["graph_id"]: row for row in report["tasks"]}


class CriticalPathTests(unittest.TestCase):
    def test_workspace_module_survives_cann_package_on_pythonpath(self):
        with tempfile.TemporaryDirectory() as temporary:
            package = Path(temporary) / "hccl"
            package.mkdir()
            (package / "__init__.py").write_text("# Installed CANN package.\n")
            (package / "cann_helper.py").write_text("VALUE = 7\n")
            env = dict(os.environ, PYTHONPATH=temporary)
            done = subprocess.run([sys.executable, "-c",
                "import hccl.tools.diagnosis.critical_path; "
                "from hccl.cann_helper import VALUE; assert VALUE == 7"],
                env=env, capture_output=True, text=True, cwd=Path(__file__).resolve().parents[3])
            self.assertEqual(done.returncode, 0, done.stderr)

    def test_longest_task_need_not_be_critical(self):
        result = analyze_critical_path(
            [task("a", 0, 6), task("b", 6, 12), task("c", 0, 10, 1)], [order("a", "b")])
        tasks = by_task(result)
        self.assertEqual(result["makespan_ns"], 12000)
        self.assertEqual(tasks["c"]["slack_ns"], 2000)
        self.assertEqual(tasks["c"]["critical"], 0)
        self.assertEqual(tasks["a"]["modeled_gain_if_work_zero_ns"], 2000)
        self.assertEqual(tasks["b"]["modeled_gain_if_work_zero_ns"], 2000)
        self.assertEqual(sum(row["weight_ns"] for row in result["representative_path"]), 12000)

    def test_notify_wait_is_completion_join_not_serial_duration(self):
        rows = [task("r", 0, 10, 0, "notify_record"), task("w", 2, 12, 1, "notify_wait"),
                task("d", 12, 15, 1)]
        result = analyze_critical_path(rows, [sync("r", "w"), order("w", "d")])
        tasks = by_task(result)
        self.assertEqual(result["makespan_ns"], 15000)
        self.assertEqual(tasks["w"]["observed_duration_ns"], 10000)
        self.assertEqual(tasks["w"]["effective_work_ns"], 2000)
        self.assertEqual(tasks["w"]["cost_kind"], "notify_residual")
        self.assertEqual(tasks["r"]["modeled_gain_if_work_zero_ns"], 8000)
        self.assertEqual(tasks["w"]["modeled_gain_if_work_zero_ns"], 2000)
        path_edges = {row["execution_edge_id"] for row in result["representative_path"]}
        self.assertIn("r_w", path_edges)
        self.assertIn("w_d", path_edges)
        self.assertEqual(sum(row["weight_ns"] for row in result["representative_path"]), 15000)

    def test_signal_before_wait_does_not_make_producer_critical(self):
        result = analyze_critical_path([task("r", 0, 1, kind="notify_record"),
                                       task("w", 5, 8, 1, "notify_wait")], [sync("r", "w")])
        tasks = by_task(result)
        self.assertEqual(tasks["w"]["effective_work_ns"], 3000)
        self.assertEqual(tasks["r"]["slack_ns"], 4000)
        self.assertEqual(tasks["r"]["critical"], 0)

    def test_multiple_waiters_are_not_summed(self):
        result = analyze_critical_path([task("r", 0, 10, kind="notify_record"),
            task("w", 0, 11, 1, "notify_wait"), task("v", 0, 12, 2, "notify_wait")],
            [sync("r", "w"), sync("r", "v")])
        self.assertEqual(result["makespan_ns"], 12000)
        self.assertEqual(by_task(result)["w"]["slack_ns"], 1000)

    def test_equal_critical_paths_and_zero_individual_gain(self):
        result = analyze_critical_path([task("a", 0, 10), task("b", 0, 10, 1)], [])
        for row in result["tasks"]:
            self.assertEqual(row["critical"], 1)
            self.assertEqual(row["modeled_gain_if_work_zero_ns"], 0)
        self.assertEqual(sum(row["on_representative_path"] for row in result["tasks"]), 1)

    def test_injected_gap_is_not_mislabeled_as_kernel_work(self):
        result = analyze_critical_path([task("a", 0, 1), task("b", 101, 102),
                                       task("c", 0, 50, 1)], [order("a", "b")])
        b = by_task(result)["b"]
        self.assertEqual(b["effective_work_ns"], 1000)
        self.assertEqual(b["gap_before_ns"], 100000)
        self.assertEqual(b["modeled_gain_if_gap_zero_ns"], 52000)
        self.assertEqual(result["impacts"][0]["kind"], "unattributed_gap")

    def test_gap_is_after_latest_predecessor_not_each_predecessor(self):
        rows = [task("a", 0, 5), task("b", 0, 8), task("c", 10, 12)]
        result = analyze_critical_path(rows, [order("a", "c"), order("b", "c")])
        tasks = by_task(result)
        self.assertEqual(tasks["a"]["slack_ns"], 3000)
        self.assertEqual(tasks["c"]["gap_before_ns"], 2000)
        self.assertEqual(tasks["b"]["critical"], 1)

    def test_explicit_completion_ignores_unrelated_background(self):
        result = analyze_critical_path([task("a", 0, 5), task("b", 0, 100, 1)], [], completion_ids=["a"])
        self.assertEqual(result["makespan_ns"], 5000)
        self.assertIsNone(by_task(result)["b"]["slack_ns"])
        self.assertEqual(by_task(result)["b"]["critical"], 0)
        self.assertEqual(result["completion_scope"], "explicit_tasks")

    def test_impact_limit_does_not_silently_report_untested_as_zero(self):
        result = analyze_critical_path([task("a", 0, 5)], [], impact_limit=0)
        self.assertEqual(result["impacts"], [])
        self.assertIsNone(by_task(result)["a"]["modeled_gain_if_work_zero_ns"])

    def test_zero_cost_tasks_and_zero_makespan(self):
        result = analyze_critical_path([task("a", 0, 0), task("b", 0, 0)], [order("a", "b")])
        self.assertEqual(result["makespan_ns"], 0)
        self.assertEqual(result["critical_task_count"], 2)
        self.assertEqual(result["impacts"], [])

    def test_empty_selection_unknown_completion_and_negative_limit(self):
        for rows, options in (([], {}), ([task("a", 0, 1)], {"completion_ids": ["missing"]}),
                              ([task("a", 0, 1)], {"impact_limit": -1})):
            with self.subTest(options=options), self.assertRaises(ValueError):
                analyze_critical_path(rows, [], **options)

    def test_large_absolute_time_preserves_one_nanosecond(self):
        result = analyze_critical_path([task("a", "1790434686486924.709", "1790434686486924.710")], [])
        self.assertEqual(result["makespan_ns"], 1)
        self.assertEqual(result["time_origin_ns"], 1790434686486924709)

    def test_reject_invalid_timestamps(self):
        for start, stop in ((2, 1), (0, "NaN"), (0, "Infinity"), (0, "0.0001")):
            with self.subTest(start=start, stop=stop), self.assertRaises(ValueError):
                analyze_critical_path([task("a", start, stop)], [])

    def test_reject_missing_endpoint_duplicate_identity_self_loop_and_cycle(self):
        rows = [task("a", 0, 1), task("b", 1, 2)]
        for current_rows, edges in ((rows, [order("a", "c")]),
                (rows + [rows[0]], []), (rows, [order("a", "a")]),
                (rows, [order("a", "b"), order("b", "a")]),
                (rows, [order("a", "b"), order("a", "b")])):
            with self.subTest(edges=edges), self.assertRaises(ValueError):
                analyze_critical_path(current_rows, edges)

    def test_reject_uncalibrated_multi_node(self):
        with self.assertRaisesRegex(ValueError, "uncalibrated"):
            analyze_critical_path([task("a", 0, 1), task("b", 0, 2, node="node1")], [])

    def test_reject_resource_artifact(self):
        row = task("a", 0, 1)
        row["_node_kind"] = "resource"
        with self.assertRaisesRegex(ValueError, "execution artifacts"):
            analyze_critical_path([row], [])

    def test_stream_edge_cannot_cross_lanes(self):
        with self.assertRaisesRegex(ValueError, "crosses physical streams"):
            analyze_critical_path([task("a", 0, 1), task("b", 2, 3, 1)], [order("a", "b")])

    def test_overlapping_stream_order_is_reported_not_timed(self):
        result = analyze_critical_path([task("a", 0, 10), task("b", 2, 3)], [order("a", "b")])
        self.assertEqual(result["status"], "partial_evidence")
        self.assertIn("incompatible_order_timestamps", {item["code"] for item in result["issues"]})

    def test_weak_edges_and_non_record_sync_do_not_enter_timed_dag(self):
        result = analyze_critical_path([task("a", 0, 1), task("w", 2, 3, 1, "notify_wait")],
                                      [dict(sync("a", "w"), confidence="heuristic")])
        self.assertEqual(by_task(result)["w"]["cost_kind"], "unresolved_wait")
        self.assertIn("unsupported_sync_endpoint", {item["code"] for item in result["issues"]})

    def test_do_not_time_ffts_declaration_order_as_hardware_dag(self):
        edge = dict(order("a", "b"), kind="ffts_logical_stream_order", confidence="semantic")
        result = analyze_critical_path([task("a", 0, 10, subtask=0),
                                       task("b", 0, 8, subtask=1)], [edge])
        self.assertEqual(result["makespan_ns"], 10000)
        self.assertEqual(result["status"], "partial_evidence")
        self.assertIn("unsupported_dependency", {row["code"] for row in result["issues"]})

    def test_missing_and_conflicting_signals_remain_opaque(self):
        rows = [task("r", 0, 12, kind="notify_record"), task("w", 0, 10, 1, "notify_wait")]
        result = analyze_critical_path(rows, [sync("r", "w")])
        self.assertEqual(by_task(result)["w"]["cost_kind"], "unresolved_wait")
        self.assertIn("incompatible_notify_timestamps", {item["code"] for item in result["issues"]})

    def test_ambiguous_producers_do_not_become_and_join(self):
        result = analyze_critical_path([task("r", 0, 1, kind="notify_record"),
            task("s", 0, 2, 2, "notify_record"), task("w", 0, 3, 1, "notify_wait")],
            [sync("r", "w"), sync("s", "w")])
        self.assertEqual(by_task(result)["w"]["cost_kind"], "unresolved_wait")
        self.assertIn("ambiguous_notify_producers", {row["code"] for row in result["issues"]})

    def test_rdma_submission_not_network_completion(self):
        result = analyze_critical_path([task("a", 0, 5, kind="rdma")], [])
        self.assertEqual(result["status"], "partial_evidence")
        self.assertEqual(by_task(result)["a"]["cost_kind"], "rdma_submission")

    def test_reports_are_invariant_to_row_order_and_time_shift(self):
        rows = [task("a", 0, 5), task("b", 6, 8)]
        first = analyze_critical_path(rows, [order("a", "b")])
        shifted = [dict(row, task_start=str(Decimal(row["task_start"]) + 1000000),
                        task_stop=str(Decimal(row["task_stop"]) + 1000000)) for row in reversed(rows)]
        second = analyze_critical_path(shifted, [order("a", "b")])
        for key in ("tasks", "activities", "representative_path", "impacts"):
            self.assertEqual(first[key], second[key])

    def test_slack_matches_explicit_path_enumeration(self):
        result = analyze_critical_path([task("r", 0, 10, kind="notify_record"),
            task("w", 2, 12, 1, "notify_wait"), task("d", 12, 15, 1)],
            [sync("r", "w"), order("w", "d")])
        # Only this tiny fixture is enumerated; production uses DAG dynamic programming.
        activities = result["activities"]
        paths, pending = [], [(("", "source"), 0, [])]
        while pending:
            event, cost, ids = pending.pop()
            if event == ("", "sink"):
                paths.append((cost, ids))
            for row in activities:
                if (row["src_graph_id"], row["src_event"]) == event:
                    pending.append(((row["dst_graph_id"], row["dst_event"]),
                        cost + row["weight_ns"], ids + [row["activity_id"]]))
        self.assertEqual(max(cost for cost, _ in paths), result["makespan_ns"])
        for row in activities:
            through = [cost for cost, ids in paths if row["activity_id"] in ids]
            self.assertEqual(row["slack_ns"], result["makespan_ns"] - max(through))
            if row["modeled_gain_if_zero_ns"] is not None:
                changed = max(cost - (row["weight_ns"] if row["activity_id"] in ids else 0)
                              for cost, ids in paths)
                self.assertEqual(row["modeled_gain_if_zero_ns"], result["makespan_ns"] - changed)

    def test_export_and_both_cli_entry_points(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            nodes, edges = root / "dep_graph_nodes.csv", root / "dep_graph_edges.csv"
            node_rows = [dict(graph_schema_version=4, graph_id="a", node_id="node0", device_id=0,
                profiler_stream_id=0, profiler_task_id=1, task_start="0", task_stop="5",
                duration="5", subtask_id=-1, profiler_task_kind="sdma")]
            write_csv(str(nodes), list(node_rows[0]), node_rows)
            write_csv(str(edges), ["graph_schema_version", "edge_id", "src", "dst", "kind", "confidence"], [])
            write_csv(str(root / "dep_graph_notify_ambiguities.csv"), ["relation_id", "status"], [])
            module = [sys.executable, "-m", "hccl.tools.diagnosis.critical_path"]
            script = [sys.executable, str(Path(__file__).with_name("critical_path.py"))]
            for entry in (module, script):
                command = entry + [str(nodes), "--edges-csv", str(edges), "-o", str(root / "report")]
                completed = subprocess.run(command, capture_output=True, text=True,
                    cwd=Path(__file__).resolve().parents[3])
                self.assertEqual(completed.returncode, 0, completed.stderr)
                report = json.loads((root / "report.json").read_text())
                self.assertEqual(report["makespan_ns"], 5000)
                self.assertEqual(report["status"], "observed_model")
            export_report(analyze_critical_path([task("a", 0, 1)], [], impact_limit=0), root / "empty")
            with (root / "empty_impacts.csv").open(newline="") as source:
                self.assertEqual(list(csv.DictReader(source)), [])
            output = export_report(report, root / "run.v1")
            self.assertEqual(output.name, "run.v1.json")

    def test_cli_requires_local_selection_and_preserves_cut_edges(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            nodes, edges = root / "dep_graph_nodes.csv", root / "dep_graph_edges.csv"
            common = dict(graph_schema_version=4, device_id=0, profiler_stream_id=0,
                profiler_task_id=1, task_start="0", task_stop="5", duration="5", subtask_id=-1)
            node_rows = [dict(common, graph_id="a", node_id="node0", profiler_task_kind="notify_record"),
                         dict(common, graph_id="w", node_id="node1", profiler_task_kind="notify_wait")]
            edge = dict(sync("a", "w"), graph_schema_version=4)
            write_csv(str(nodes), list(node_rows[0]), node_rows)
            write_csv(str(edges), list(edge), [edge])
            command = [sys.executable, str(Path(__file__).with_name("critical_path.py")),
                str(nodes), "--edges-csv", str(edges), "-o", str(root / "local")]
            rejected = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(rejected.returncode, 2)
            self.assertIn("uncalibrated", rejected.stderr)
            local = subprocess.run(command + ["--node-id", "node1", "--completion-task", "w"],
                                   capture_output=True, text=True)
            self.assertEqual(local.returncode, 0, local.stderr)
            report = json.loads((root / "local.json").read_text())
            self.assertEqual([row["graph_id"] for row in report["tasks"]], ["w"])
            self.assertIn("selection_boundary", {row["code"] for row in report["issues"]})


if __name__ == "__main__":
    unittest.main()
