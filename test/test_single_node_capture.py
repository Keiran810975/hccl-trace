from __future__ import annotations

import json
from pathlib import Path
import sqlite3
import tempfile
import unittest

from test.single_node_capture import bind, actual_windows
from test.single_node_random_suite import generate_cases, evaluate_temporal_localization
from hccl.tools.diagnosis.rolling_diagnosis import load_coordinates


class PublicBindingTests(unittest.TestCase):
    def fixture(self, root):
        (root / "public").mkdir()
        for rank, device in enumerate((1, 3, 5, 7)):
            calls = [dict(sequence=i, rank=rank, runtime_device_id=device, stage="measured", iteration=i,
                          block=0, bucket=0, count=1024, dtype="fp32", reduction="sum",
                          before=dict(raw_ns=i * 100000 + 1000), after=dict(raw_ns=i * 100000 + 90000))
                     for i in range(8)]
            (root / "public" / ("rank-{}.jsonl".format(rank))).write_text(
                "".join(json.dumps(c) + "\n" for c in calls))
            (root / "public" / ("boundaries-rank-{}.jsonl".format(rank))).write_text(
                "".join(json.dumps(dict(rank=rank, stage="measured", iteration=i, device_synchronized=True,
                                       clocks=dict(raw_ns=i * 100000 + 95000))) + "\n" for i in range(8)))
            folder = root / "msprof" / str(rank)
            (folder / "host").mkdir(parents=True)
            (folder / "host/start_info").write_text(json.dumps(dict(collectionTimeBegin="1000000", clockMonotonicRaw="0")))
            with sqlite3.connect(folder / "msprof_fixture.db") as db:
                db.executescript("CREATE TABLE STRING_IDS(id INTEGER,value TEXT);"
                                 "CREATE TABLE COMMUNICATION_OP(deviceId INTEGER,groupName INTEGER,opName INTEGER,count INTEGER,dataType INTEGER);"
                                 "CREATE TABLE CANN_API(startNs INTEGER,endNs INTEGER,name INTEGER);")
                db.executemany("INSERT INTO STRING_IDS VALUES(?,?)", [(1, "group"), (2, "hcom_allReduce_")] +
                               [(10 + i, "hcom_allReduce__612_{}_1".format(i)) for i in range(8)])
                # Deliberately reverse DB insertion order; use actual named operation counters, not DB ordinals.
                db.executemany("INSERT INTO COMMUNICATION_OP VALUES(?,?,?,?,?)",
                               [(device, 1, 10 + i, 1024, 4) for i in reversed(range(8))])
                db.executemany("INSERT INTO CANN_API VALUES(?,?,?)",
                               [(1000000000 + i * 100000 + 10000, 1000000000 + i * 100000 + 80000, 2)
                                for i in reversed(range(8))])

    def test_binds_named_counters_sizes_apis_and_four_ranks_without_truth(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.fixture(root)
            result = bind(root, "test")
            self.assertEqual(set(result), set(range(4)))
            self.assertEqual(len(list((root / "foreground-dbs").glob("msprof_*.db"))), 4)
            coordinates = load_coordinates(root / "iteration-map.json")
            self.assertEqual(len(coordinates), 8)
            self.assertEqual({v["iteration"] for v in coordinates.values()}, set(range(8)))
            self.assertNotIn("injection", (root / "iteration-map.json").read_text())

    def test_rejects_wrong_sizes_and_clock_containment(self):
        for failure in ("size", "clock"):
            with self.subTest(failure=failure), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                self.fixture(root)
                path = root / "msprof/0/msprof_fixture.db"
                with sqlite3.connect(path) as db:
                    db.execute("UPDATE COMMUNICATION_OP SET count=2048" if failure == "size" else
                               "UPDATE CANN_API SET startNs=0")
                with self.assertRaises(ValueError):
                    bind(root, "test")

    def test_background_without_communication_table_is_not_a_foreground_input(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.fixture(root)
            background = root / "msprof/background"
            background.mkdir()
            with sqlite3.connect(background / "msprof_background.db") as db:
                db.execute("CREATE TABLE BACKGROUND(value INTEGER)")
            self.assertEqual(set(bind(root, "test")), set(range(4)))
            evidence = json.loads((root / "binding-evidence.json").read_text())
            self.assertEqual(len(evidence["noncommunication_inputs"]), 1)

    def test_absent_foreground_communication_table_still_fails(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.fixture(root)
            with sqlite3.connect(root / "msprof/0/msprof_fixture.db") as db:
                db.execute("DROP TABLE COMMUNICATION_OP")
            with self.assertRaisesRegex(ValueError, "no complete unique foreground"):
                bind(root, "test")

    def test_accepts_async_api_after_python_return_but_before_device_sync(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.fixture(root)
            for path in (root / "public").glob("rank-*.jsonl"):
                rows = [json.loads(line) for line in path.read_text().splitlines()]
                for row in rows:
                    row["after"]["raw_ns"] = row["before"]["raw_ns"] + 100
                path.write_text("".join(json.dumps(r) + "\n" for r in rows))
            self.assertEqual(len(bind(root, "test")), 4)

    def test_preparations_are_exported_only_from_complete_independent_public_logs(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.fixture(root)
            for path in (root / "public").glob("rank-*.jsonl"):
                calls = [json.loads(line) for line in path.read_text().splitlines()]
                for call in calls:
                    call["preparation_before"] = dict(raw_ns=call["before"]["raw_ns"] - 500)
                path.write_text("".join(json.dumps(c) + "\n" for c in calls))
            bind(root, "test")
            result = json.loads((root / "preparation-map.json").read_text())
            self.assertEqual(len(result["preparations"]), 32)
            for item in result["preparations"]:
                self.assertEqual(item["stop_ns"] - item["start_ns"], 500)
                self.assertLessEqual(item["stop_ns"], item["api_start_ns"])
            self.assertNotIn("injection", json.dumps(result))

    def test_partial_preparation_coverage_is_not_silently_accepted(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.fixture(root)
            path = root / "public/rank-0.jsonl"
            calls = [json.loads(line) for line in path.read_text().splitlines()]
            calls[0]["preparation_before"] = dict(raw_ns=0)
            path.write_text("".join(json.dumps(c) + "\n" for c in calls))
            with self.assertRaisesRegex(ValueError, "every foreground"):
                bind(root, "test")


class InjectionWindowTests(unittest.TestCase):
    def windows(self, kind, process_count=1):
        case = next(c for c in generate_cases() if c["injection"]["kind"] == kind)
        rank = case["injection"]["target_rank"]
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "private").mkdir()
            records = [dict(event="injection_start", clocks=dict(raw_ns=100)),
                       dict(event="injection_stop", clocks=dict(raw_ns=200), actual_hit=True)]
            (root / "private" / ("rank-{}.jsonl".format(rank))).write_text(
                "".join(json.dumps(r) + "\n" for r in records))
            background = dict(operations=10, max_error=0, started_raw_ns=120, finished_raw_ns=190,
                              process_count=process_count)
            (root / "private/result.json").write_text(json.dumps(background))
            found = {r: dict(offset=(r + 1) * 1000) for r in range(4)}
            return case, found, actual_windows(root, "test-run", case, found)

    def test_delay_copy_and_compute_window_stay_on_target_rank(self):
        for kind in ("progress_delay", "copy_contention", "compute_contention"):
            with self.subTest(kind=kind):
                case, found, windows = self.windows(kind)
                rank = case["injection"]["target_rank"]
                self.assertEqual(len(windows), 1)
                self.assertEqual(windows[0]["target_ranks"], [rank])
                raw_start, raw_stop = (100, 200) if kind == "progress_delay" else (120, 190)
                self.assertEqual(windows[0]["start_ns"], raw_start + found[rank]["offset"])
                self.assertEqual(windows[0]["stop_ns"], raw_stop + found[rank]["offset"])

    def test_communication_has_only_two_actual_endpoints_with_independent_offsets(self):
        case, found, windows = self.windows("communication_contention")
        endpoints = {case["injection"]["target_rank"], case["injection"]["peer_rank"]}
        self.assertEqual({w["target_ranks"][0] for w in windows}, endpoints)
        self.assertEqual(len(windows), 2)
        for window in windows:
            rank, = window["target_ranks"]
            self.assertEqual(window["start_ns"], 120 + found[rank]["offset"])
            self.assertEqual(window["stop_ns"], 190 + found[rank]["offset"])

    def test_communication_rejects_multiple_background_processes(self):
        with self.assertRaises(ValueError):
            self.windows("communication_contention", process_count=2)

    def test_either_communication_endpoint_can_match_but_other_ranks_cannot(self):
        _, _, windows = self.windows("communication_contention")
        endpoints = {w["target_ranks"][0] for w in windows}
        for window in windows:
            rank, = window["target_ranks"]
            root = dict(root_id="primary", status="dependency_supported_candidate", traversal_truncated=False,
                        observed_start_ns=window["start_ns"], observed_stop_ns=window["stop_ns"],
                        user_rank=rank, component="execution", node_id=window["node_id"])
            report = dict(primary_source_candidate_id="primary", root_causes=[root])
            self.assertTrue(evaluate_temporal_localization(report, windows)["diagnosis_success"])
            root["user_rank"] = next(iter(set(range(4)) - endpoints))
            self.assertFalse(evaluate_temporal_localization(report, windows)["diagnosis_success"])


if __name__ == "__main__":
    unittest.main()
