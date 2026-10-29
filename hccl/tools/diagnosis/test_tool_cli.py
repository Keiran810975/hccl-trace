"""Public CLI/SDK contracts and real SQLite fixtures, not NPU validation."""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sqlite3
import shutil
import tempfile
import unittest
from unittest.mock import patch

from hccl_trace import Trace
from .capture_discovery import discover_capture, write_json
from .cli import analyze_capture, DiagnosisError, main
from .workload_binder import bind_capture, _unique_assignment
from . import rolling_diagnosis as rolling
from . import compare_diagnosis as comparison
from . import source_propagation as propagation
from . import source_propagation_view as presentation
from .result_normalizer import normalize
from .report_exporter import FINAL_FILES, validate_final, host_source_displays
from .test_multi_node_trace import create_run_fixture, NOTIFY
from .test_rolling_diagnosis import repeated
from .test_compare_diagnosis import fixture
from .multi_node_trace import operation_bindings, operation_sync_connected, load_manifest


def sdk_capture(root, *, iterations=6, kinds=None):
    folder = root / "nodes"
    folder.mkdir(parents=True)
    _, original = create_run_fixture(folder)
    metadata = dict(run_id="sdk-fixture", nodes=[], ranks=original["ranks"])
    kinds = kinds or ["AllReduce"] * iterations
    for index, rank in enumerate(original["ranks"]):
        node, device, user_rank = rank["node_id"], rank["device_id"], rank["user_rank"]
        node_dir = folder / node
        db_path = node_dir / "db/msprof_fixture.db"
        with sqlite3.connect(db_path) as db:
            tasks = db.execute("SELECT * FROM TASK ORDER BY taskId").fetchall()
            info = db.execute("SELECT * FROM COMMUNICATION_TASK_INFO ORDER BY globalTaskId").fetchall()
            db.executescript("DELETE FROM TASK; DELETE FROM COMMUNICATION_OP; DELETE FROM COMMUNICATION_TASK_INFO; "
                "ALTER TABLE COMMUNICATION_OP ADD COLUMN startNs INTEGER; "
                "ALTER TABLE COMMUNICATION_OP ADD COLUMN endNs INTEGER; "
                "ALTER TABLE COMMUNICATION_OP ADD COLUMN count INTEGER; "
                "ALTER TABLE COMMUNICATION_OP ADD COLUMN dataType INTEGER; "
                "ALTER TABLE COMMUNICATION_OP ADD COLUMN opType INTEGER; "
                "CREATE TABLE CANN_API(startNs INTEGER,endNs INTEGER,connectionId INTEGER,name INTEGER);")
            plog, events = [], [dict(event="runtime", schema_version=1, run_id="sdk-fixture", node_id=node,
                                    device_id=device, user_rank=user_rank, pid=123)]
            for iteration in range(iterations):
                before = iteration * 100000 + 100
                origin = 10**12 + before
                api_name = "hcom_" + kinds[iteration][0].lower() + kinds[iteration][1:] + "_"
                db.execute("INSERT INTO STRING_IDS VALUES(?,?)", (100 + iteration, "opaque-" + str(iteration)))
                db.execute("INSERT INTO STRING_IDS VALUES(?,?)", (1000 + iteration, api_name))
                db.execute("INSERT INTO COMMUNICATION_OP VALUES(?, ?, 5, ?, ?, ?, ?, ?, 4, ?)",
                           (100 + iteration, 100 + iteration, iteration, device, origin + 1000, origin + 2500,
                            1024, 1000 + iteration))
                db.execute("INSERT INTO CANN_API VALUES(?,?,?,?)", (origin + 100, origin + 200, 100 + iteration, 1000 + iteration))
                for offset, (task, communication) in enumerate(zip(tasks, info), 1):
                    task = list(task)
                    task[0], task[1] = origin + offset * 1000, origin + offset * 1000 + 500
                    task[3], task[4], task[8] = 100 + iteration, iteration * 100 + offset, iteration * 10 + offset
                    db.execute("INSERT INTO TASK VALUES(?,?,?,?,?,?,?,?,?,?)", task)
                    communication = list(communication)
                    communication[0], communication[-1] = task[4], iteration
                    db.execute("INSERT INTO COMMUNICATION_TASK_INFO VALUES(?,?,?,?,?)", communication)
                semantic_task = iteration * 10 + (2 if index == 0 else 1)
                plog.append("[HcclTaskSemantic] schema_version[4] device_id[{}] stream_id[13] hccl_task_id[{}] "
                    "task_kind[{}] user_rank[{}] comm_rank[{}] rank_size[2] peer_rank[{}] phase[reduce_scatter] "
                    "step[0] slice[0] event[{}] semantic[link_ack] algorithm[ring] notify_id[{}]".format(
                        device, semantic_task, "rdma" if index == 0 else "notify_wait", user_rank, index,
                        9 if index == 0 else 3, "tx_ack_start" if index == 0 else "rx_ack_start", NOTIFY))
                events.extend([dict(event="call", schema_version=1, sequence=iteration, run_id="sdk-fixture",
                    node_id=node, user_rank=user_rank, device_id=device, stage="measured", iteration=iteration,
                    group_id="dp", participants=[3, 9], db_group_name=None, call_site="grad.sync", occurrence=0,
                    operation_type=kinds[iteration], dtype="float32", element_count=1024, reduction="sum",
                    before=dict(raw_ns=before), after=dict(raw_ns=before + 300), status="submitted"),
                    dict(event="completion", schema_version=1, sequences=[iteration], clocks=dict(raw_ns=before + 9000))])
            events.append(dict(event="capture_end", schema_version=1, pending_sequences=[]))
        (node_dir / "plog/plog-fixture.log").write_text("\n".join(plog) + "\n")
        (node_dir / "calls").mkdir()
        (node_dir / "calls" / ("rank-{}.jsonl".format(user_rank))).write_text("\n".join(json.dumps(v) for v in events) + "\n")
        write_json(db_path.parent / "host/start_info", dict(collectionTimeBegin=10**9, clockMonotonicRaw=0))
        metadata["nodes"].append(dict(node_id=node, plog_dir="nodes/" + node + "/plog", msprof_db_dir="nodes/" + node + "/db"))
    write_json(root / "capture.json", metadata)
    return root


def hashes(root):
    return {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest() for p in root.rglob("*") if p.is_file()}


class ToolCliTests(unittest.TestCase):
    def test_uneven_nodes_and_independent_groups_share_one_code_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            first = sdk_capture(root / "first")
            second = sdk_capture(root / "second")
            combined = root / "capture"
            metadata = dict(run_id="sdk-fixture", nodes=[], ranks=[])
            for node in ("node0", "node1"):
                for child in ("plog", "db", "calls"):
                    (combined / "nodes" / node / child).mkdir(parents=True)
                metadata["nodes"].append(dict(node_id=node, plog_dir="nodes/" + node + "/plog", msprof_db_dir="nodes/" + node + "/db"))
            for source, old_node, node, rank, device, group in (
                    (first, "node0", "node0", 3, 6, "dp"), (first, "node1", "node1", 9, 2, "dp"),
                    (second, "node0", "node0", 21, 5, "tp"), (second, "node1", "node0", 28, 7, "tp")):
                original = source / "nodes" / old_node
                destination = combined / "nodes" / node
                old_rank = 3 if old_node == "node0" else 9
                old_device = 6 if old_node == "node0" else 2
                db_path = destination / "db" / ("msprof_rank-{}.db".format(rank))
                shutil.copy2(original / "db/msprof_fixture.db", db_path)
                with sqlite3.connect(db_path) as db:
                    db.execute("UPDATE TASK SET deviceId=?", (device,))
                    db.execute("UPDATE COMMUNICATION_OP SET deviceId=?", (device,))
                    if group == "tp":
                        db.execute("UPDATE COMMUNICATION_TASK_INFO SET srcRank=CASE srcRank WHEN 3 THEN 21 ELSE 28 END, "
                                   "dstRank=CASE dstRank WHEN 3 THEN 21 ELSE 28 END, notifyId=CASE WHEN notifyId>=0 THEN ? ELSE notifyId END",
                                   ((28 << 32) | 128,))
                shutil.copytree(original / "db/host", destination / "db/host", dirs_exist_ok=True)
                plog = (original / "plog/plog-fixture.log").read_text().replace("device_id[{}]".format(old_device), "device_id[{}]".format(device))
                if group == "tp":
                    plog = plog.replace("user_rank[{}]".format(old_rank), "user_rank[{}]".format(rank))
                    plog = plog.replace("peer_rank[{}]".format(9 if old_rank == 3 else 3), "peer_rank[{}]".format(28 if rank == 21 else 21))
                    plog = plog.replace("notify_id[{}]".format(NOTIFY), "notify_id[{}]".format((28 << 32) | 128))
                (destination / "plog" / ("plog-{}.log".format(rank))).write_text(plog)
                events = [json.loads(s) for s in (original / "calls" / ("rank-{}.jsonl".format(old_rank))).read_text().splitlines()]
                for event in events:
                    if "node_id" in event:
                        event.update(node_id=node, user_rank=rank, device_id=device)
                    if event["event"] == "call":
                        event.update(group_id=group, participants=[3, 9] if group == "dp" else [21, 28])
                (destination / "calls" / ("rank-{}.jsonl".format(rank))).write_text("\n".join(json.dumps(e) for e in events) + "\n")
                metadata["ranks"].append(dict(node_id=node, user_rank=rank, device_id=device))
            write_json(combined / "capture.json", metadata)
            result = analyze_capture(combined, root / "report", mode="rolling")
            self.assertEqual(result["quality"]["node_count"], 2)
            self.assertEqual(result["quality"]["paired_wait_count"], 12)
            self.assertEqual(result["binding"]["bound_operation_count"], 12)

    def test_baseline_legacy_input_is_read_only_and_publishes_exactly_three_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            capture = root / "capture"
            capture.mkdir()
            manifest, _ = create_run_fixture(capture)
            before = hashes(capture)
            result = analyze_capture(manifest, root / "report", mode="baseline", baseline=manifest)
            self.assertEqual(hashes(capture), before)
            self.assertEqual({p.name for p in (root / "report").iterdir()}, FINAL_FILES)
            self.assertEqual(result["candidates"], [])
            self.assertEqual(result["reference"]["statistic"], "median")
            page = (root / "report/propagation.html").read_text()
            self.assertNotIn('href="report.json"', page)
            self.assertNotIn('href="steps.csv"', page)
            self.assertNotIn("前5轮均值", page)
            self.assertFalse((root / "report.debug").exists())
            validate_final(root / "report")

    def test_host_overlay_anchors_local_interval_without_inventing_device_tasks(self):
        rows, _, _, _ = fixture()
        anchor = rows[0]
        from .analyze_waits import ns
        origin = ns(anchor, "start")
        root = dict(component="host_preparation", graph_id=anchor["_graph_id"],
            node_id=anchor["_node_id"], device_id=anchor["_device_id"], user_rank=anchor["_user_rank"],
            observed_start_ns=origin - 2000, observed_stop_ns=origin - 500)
        model = dict(nodes=[dict(id=anchor["_graph_id"], relativeStart=8)])
        display = host_source_displays([root], rows, model)[anchor["_graph_id"]]
        self.assertEqual((display["startUs"], display["stopUs"], display["durationUs"]), (6, 7.5, 1.5))
        self.assertEqual(display["startNs"], str(origin - 2000))
        self.assertEqual(len(model["nodes"]), 1)

    def test_published_directory_uses_parent_read_traverse_permissions(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            root.chmod(0o750)
            capture = sdk_capture(root / "capture")
            analyze_capture(capture, root / "report", mode="rolling")
            self.assertEqual((root / "report").stat().st_mode & 0o777, 0o750)

    def test_conflicting_explicit_rank_mapping_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            capture = sdk_capture(root / "capture")
            topology = root / "topology.json"
            write_json(topology, dict(ranks=[dict(node_id="node0", device_id=6, user_rank=4)]))
            with self.assertRaisesRegex(ValueError, "conflicts"):
                discover_capture(capture, root / "work", topology=topology)

    def test_sdk_noncontiguous_ranks_rolling_end_to_end(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            capture = sdk_capture(root / "capture")
            before = hashes(capture)
            result = analyze_capture(capture, root / "report", mode="rolling")
            self.assertEqual(hashes(capture), before)
            self.assertEqual(result["binding"]["sdk_bound_calls"], 12)
            self.assertEqual(result["quality"]["paired_wait_count"], 6)
            self.assertGreater(result["coverage"]["comparable_task_count"], 0)
            self.assertEqual(result["reference"]["statistic"], "mean")
            validate_final(root / "report")

    def test_insufficient_history_is_not_claimed_healthy(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            result = analyze_capture(sdk_capture(root / "capture", iterations=2), root / "report", mode="rolling")
            self.assertEqual(result["status"], "insufficient_history")
            self.assertEqual(result["candidates"], [])

    def test_sdk_baseline_pairs_are_independent_of_db_operation_names(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            current = sdk_capture(root / "current")
            baseline = sdk_capture(root / "normal")
            result = analyze_capture(current, root / "report", mode="baseline", baseline=baseline)
            self.assertEqual(result["status"], "analyzed")
            self.assertEqual(result["coverage"]["comparison_status_counts"], {"explicit_operation_reference": 24})

    def test_different_collectives_do_not_require_allreduce_counter_names(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            capture = sdk_capture(root / "capture", iterations=3, kinds=["AllReduce", "AllGather", "ReduceScatter"])
            discovered = discover_capture(capture, root / "discovery")
            bound = bind_capture(discovered, root / "bound", mode="rolling")
            self.assertEqual(bound.evidence["bound_operation_count"], 3)
            manifest = load_manifest(bound.manifest)
            self.assertEqual(manifest["operations"][0]["participants"], [3, 9])
            self.assertEqual({r["user_rank"] for r in manifest["ranks"]}, {3, 9})

    def test_host_runtime_launch_bridge_requires_exact_thread_and_interval(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            capture = sdk_capture(root / "capture")
            for path in capture.rglob("msprof_*.db"):
                with sqlite3.connect(path) as db:
                    db.execute("ALTER TABLE CANN_API ADD COLUMN globalTid INTEGER")
                    db.execute("UPDATE CANN_API SET globalTid=12345")
                    db.execute("INSERT INTO STRING_IDS VALUES(9000,'launch')")
                    db.execute("INSERT INTO CANN_API SELECT startNs,endNs,connectionId+10000,9000,globalTid FROM CANN_API")
                    db.execute("UPDATE COMMUNICATION_OP SET connectionId=connectionId+10000")
            bound = bind_capture(discover_capture(capture, root / "discovery"), root / "bound", mode="rolling")
            evidence = json.loads((bound.manifest.parent / "binding-evidence.json").read_text())
            self.assertTrue(all("exact_named_api_interval" in kind for item in evidence["operations"] for kind in item["api_binding_methods"]))
            path = next(capture.rglob("msprof_*.db"))
            with sqlite3.connect(path) as db:
                db.execute("UPDATE CANN_API SET startNs=startNs+1 WHERE name=9000")
            with self.assertRaisesRegex(ValueError, "no unique named"):
                bind_capture(discover_capture(capture, root / "discovery-bad"), root / "bound-bad", mode="rolling")

    def test_ambiguous_bijection_is_rejected_not_sorted_by_ordinal(self):
        with self.assertRaisesRegex(ValueError, "ambiguous"):
            _unique_assignment({0: {0, 1}, 1: {0, 1}})
        self.assertEqual(_unique_assignment({0: {0, 1}, 1: {1}}), {1: 1, 0: 0})

    def test_missing_completion_fails_and_cannot_fall_back_to_baseline(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            capture = sdk_capture(root / "capture")
            path = capture / "nodes/node0/calls/rank-3.jsonl"
            events = [json.loads(s) for s in path.read_text().splitlines()]
            events[-1]["pending_sequences"] = [5]
            path.write_text("\n".join(json.dumps(e) for e in events) + "\n")
            with self.assertRaises(DiagnosisError) as error:
                analyze_capture(capture, root / "report", mode="rolling", keep_debug=True)
            self.assertEqual(error.exception.code, 2)
            self.assertFalse((root / "report").exists())
            self.assertTrue((root / "report.debug").is_dir())

    def test_python_return_is_not_accepted_as_device_completion(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            capture = sdk_capture(root / "capture")
            path = capture / "nodes/node0/calls/rank-3.jsonl"
            events = [json.loads(s) for s in path.read_text().splitlines()]
            for event in events:
                if event["event"] == "completion":
                    event["clocks"]["raw_ns"] -= 7800
            path.write_text("\n".join(json.dumps(e) for e in events) + "\n")
            with self.assertRaises(DiagnosisError) as error:
                analyze_capture(capture, root / "report", mode="rolling")
            self.assertEqual(error.exception.code, 2)
            self.assertFalse((root / "report").exists())

    def test_failed_semantic_gate_is_not_published(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            capture = root / "capture"
            capture.mkdir()
            manifest, _ = create_run_fixture(capture)
            (capture / "node0/plog/plog-fixture.log").write_text("")
            with self.assertRaises(DiagnosisError) as error:
                analyze_capture(manifest, root / "report", mode="baseline", baseline=manifest)
            self.assertEqual(error.exception.code, 3)
            self.assertFalse((root / "report").exists())

    def test_input_and_existing_output_protection(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            capture = sdk_capture(root / "capture")
            with self.assertRaises(DiagnosisError):
                analyze_capture(capture, capture / "report", mode="rolling")
            (root / "report").mkdir()
            (root / "report/keep.txt").write_text("existing")
            with self.assertRaises(DiagnosisError):
                analyze_capture(capture, root / "report", mode="rolling")
            self.assertEqual((root / "report/keep.txt").read_text(), "existing")

    def test_report_failure_cleans_own_temporary_data_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            capture = root / "capture"
            capture.mkdir()
            manifest, _ = create_run_fixture(capture)
            before = hashes(capture)
            temporary_paths = []
            from . import cli
            original = tempfile.TemporaryDirectory
            def directory(*args, **kwargs):
                instance = original(*args, **kwargs)
                temporary_paths.append(Path(instance.name))
                return instance
            with patch.object(cli.tempfile, "TemporaryDirectory", side_effect=directory), patch.object(cli, "publish_final_report", side_effect=RuntimeError("renderer failed")):
                with self.assertRaises(DiagnosisError) as error:
                    analyze_capture(manifest, root / "report", mode="baseline", baseline=manifest)
            self.assertEqual(error.exception.code, 5)
            self.assertTrue(all(not p.exists() for p in temporary_paths))
            self.assertEqual(hashes(capture), before)

    def test_new_named_positions_keep_groups_isolated(self):
        rows, edges, coordinates = repeated()
        named = [dict(operation_scope=c["operation_scope"], stage=c["stage"], iteration=c["iteration"],
                      group_id="dp", call_site="layer.grad", occurrence=0, evidence=c["evidence"]) for c in coordinates.values()]
        before = rolling.analyze(rows, edges, coordinates)
        after = rolling.analyze(rows, edges, rolling.validate_coordinates(named))
        self.assertEqual([r["graph_id"] for r in after["root_causes"]], [r["graph_id"] for r in before["root_causes"]])
        self.assertEqual(after["tasks"][-4]["group_id"], "dp")
        named[2]["group_id"] = "tp"
        changed = rolling.analyze(rows, edges, rolling.validate_coordinates(named))
        self.assertEqual(changed["tasks"][-4]["comparison_status"], "missing_previous_iteration")

    def test_baseline_sources_use_median_without_fabricating_chains(self):
        rows, edges, normal, normal_edges = fixture()
        report = comparison.analyze(rows, edges, normal, baseline_edges=normal_edges)
        unified, roots, tasks = normalize(report, mode="baseline", run_id="r", rows=rows, edges=edges,
            pipeline=dict(status="passed"), binding_evidence={})
        chain = propagation.build_report(rows, edges, roots, tasks, reference=unified["reference"])
        self.assertGreater(chain["summary"]["complete_chain_count"], 0)
        page = presentation.render_html(chain, standalone=True)
        self.assertIn("Baseline 中位数", page)
        self.assertNotIn("前5轮", page)
        self.assertEqual(unified["candidates"][0]["reference_statistic"], "median")

    def test_cli_mode_contract(self):
        self.assertEqual(main(["analyze", "--capture", "missing", "--mode", "baseline", "-o", "absent-result"]), 2)


class PublicSdkTests(unittest.TestCase):
    def test_sdk_never_syncs_and_records_pending_incomplete_work(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch("hccl_trace._clocks", return_value=dict(raw_ns=123, unix_ns=456)):
                trace = Trace(tmp, node_id="worker", user_rank=9, device_id=2)
                trace.group("dp", [3, 9])
                with trace.iteration(0):
                    with trace.collective(group="dp", call_site="grad", operation_type="AllReduce", element_count=8, dtype="fp32"):
                        pass
                trace.close()
            events = [json.loads(line) for line in (Path(tmp) / "rank-9.jsonl").read_text().splitlines()]
            self.assertEqual(events[-1]["pending_sequences"], [0])
            self.assertFalse(any(e["event"] == "completion" for e in events))

    def test_device_is_never_inferred_from_rank(self):
        with patch.dict("os.environ", {"HCCL_TRACE_CALLS_DIR": "/not-created", "RANK": "9", "LOCAL_RANK": "0"}, clear=True):
            with self.assertRaisesRegex(ValueError, "not inferred"):
                Trace.from_environment()


if __name__ == "__main__":
    unittest.main()
