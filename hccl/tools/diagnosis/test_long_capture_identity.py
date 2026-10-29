"""Long HOST captures need authoritative batches and unique DB executions."""
from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import sqlite3
import tempfile
import unittest

from .export_msprof_identity import export_identity, sha256
from .merge_timeline import merge_records
from .parse_msprof_db import MsprofDbError, parse_file, TASK_BATCH_TABLE
from .schema import MERGED_FIELDS, ProfilerTask, SemanticRecord, write_csv
from .test_diagnosis import create_msprof_db
from .visualize_dependency_graph import read_execution_rows
from .capture_discovery import Capture, prepare_capture_identity


class LongCaptureIdentityTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.profile = self.root / "PROF_fixture"
        self.profile.mkdir()
        self.source = self.profile / "msprof_fixture.db"
        create_msprof_db(self.source)
        with sqlite3.connect(self.source) as db:
            db.execute("UPDATE TASK SET contextId=4294967295 WHERE globalTaskId=12")
            db.execute("INSERT INTO TASK VALUES(7007,8008,0,80,13,3,4294967295,45,3,0)")
            db.execute("INSERT INTO COMMUNICATION_TASK_INFO VALUES(13,100,0,1,8)")
            db.execute("INSERT INTO STRING_IDS VALUES(7,'hcom_allReduce__fixture_1')")
            db.execute("INSERT INTO COMMUNICATION_OP VALUES(7,80,5,8,0)")
        self.vendor = self.profile / "device_0/sqlite/hccl_single_device.db"
        self.vendor.parent.mkdir(parents=True)
        with sqlite3.connect(self.vendor) as db:
            db.execute("CREATE TABLE HCCLTaskSingleDevice(stream_id,task_id,context_id,connection_id,batch_id,op_name)")
            db.executemany("INSERT INTO HCCLTaskSingleDevice VALUES(?,?,?,?,?,?)", [
                (45,3,4294967295,79,0,"hcom_allReduce__fixture_0"),
                (45,3,4294967295,80,1,"hcom_allReduce__fixture_1")])
        self.output = self.root / "selected/msprof_fixture.db"

    def semantics(self):
        return [SemanticRecord(node_id="node0", device_id=0, stream_id=45,
            task_id=task, source="host", task_kind="notify_record", notify_id=notify,
            user_rank=0, peer_rank=1, phase="allgather", event="tx_ack_start")
            for task, notify in [(3,99),(65539,100)]]

    def identity_capture(self):
        plog = self.root / "plog"
        plog.mkdir()
        (plog / "plog-fixture.log").write_text("[HcclTaskSemantic] schema_version[4] source[host] "
            "device_id[0] stream_id[45] hccl_task_id[65539] task_kind[notify_record] user_rank[0] "
            "peer_rank[1] phase[allgather] event[tx_ack_start] notify_id[100]\n")
        return Capture(dict(nodes=[dict(node_id="node0", plog_dir=str(plog), msprof_db_dir=str(self.profile))]), ())

    def test_user_entry_exports_long_host_identity_only_in_owned_workspace(self):
        original = sha256(self.source)
        capture = self.identity_capture()
        (self.profile / "host").mkdir()
        (self.profile / "host/start_info").write_text('{"clockMonotonicRaw": 0, "collectionTimeBegin": 0}')
        prepared = prepare_capture_identity(capture, self.root / "work")
        self.assertEqual(sha256(self.source), original)
        self.assertEqual(capture.manifest["nodes"][0]["msprof_db_dir"], str(self.profile))
        selected = Path(prepared.manifest["nodes"][0]["msprof_db_dir"]) / "0/msprof_fixture.db"
        rows, stats = merge_records(self.semantics(), parse_file(str(selected), "node0"))
        self.assertEqual(stats["exact_matched"], 2)
        self.assertEqual(len(prepared.identity_exports), 1)
        self.assertFalse(prepared.identity_exports[0]["temporal_matching_used"])
        self.assertTrue((selected.parent / "host/start_info").is_file())

    def test_user_entry_missing_batch_evidence_fails_without_modifying_capture(self):
        capture = self.identity_capture()
        self.vendor.unlink()
        original = sha256(self.source)
        with self.assertRaises(MsprofDbError):
            prepare_capture_identity(capture, self.root / "work")
        self.assertEqual(sha256(self.source), original)

    def test_user_entry_does_not_apply_host_batch_encoding_to_aicpu(self):
        capture = self.identity_capture()
        path = Path(capture.manifest["nodes"][0]["plog_dir"]) / "plog-fixture.log"
        path.write_text(path.read_text().replace("source[host]", "source[aicpu]"))
        prepared = prepare_capture_identity(capture, self.root / "work")
        self.assertEqual(prepared.manifest, capture.manifest)
        self.assertEqual(prepared.identity_exports, ())

    def test_rollover_is_exact_only_with_exported_batch(self):
        _, missing = merge_records(self.semantics(), parse_file(str(self.source), "node0"))
        self.assertEqual(missing["unmatched_semantic"], 1)
        self.assertEqual(missing["ambiguous_profiler"], 1)
        self.assertEqual(missing["exact_matched"], 0)
        before = sha256(self.source)
        evidence = export_identity(self.source, self.profile, self.output)
        self.assertEqual(before, sha256(self.source))
        self.assertFalse(evidence["semantic_input_used"])
        self.assertFalse(evidence["temporal_matching_used"])
        rows, stats = merge_records(self.semantics(), parse_file(str(self.output), "node0"))
        self.assertEqual(stats["exact_matched"], 2)
        self.assertEqual(stats["invalid_matches"], 0)
        matched = [r for r in rows if r["match_status"] == "matched"]
        self.assertEqual([r["profiler_task_id"] for r in matched], [3,3])
        self.assertEqual([r["profiler_batch_id"] for r in matched], [0,1])

    def test_unrelated_stream_cannot_supply_a_batch(self):
        with sqlite3.connect(self.vendor) as db:
            db.execute("UPDATE HCCLTaskSingleDevice SET stream_id=46 WHERE batch_id=1")
        with self.assertRaisesRegex(MsprofDbError, "missing/ambiguous"):
            export_identity(self.source, self.profile, self.output)
        self.assertFalse(self.output.exists())

    def test_ambiguous_batch_is_rejected_not_ordered(self):
        with sqlite3.connect(self.vendor) as db:
            db.execute("INSERT INTO HCCLTaskSingleDevice SELECT stream_id,task_id,context_id,connection_id,2,op_name "
                       "FROM HCCLTaskSingleDevice WHERE batch_id=1")
        with self.assertRaisesRegex(MsprofDbError, "ambiguous"):
            export_identity(self.source, self.profile, self.output)

    def test_operation_conflict_is_rejected(self):
        with sqlite3.connect(self.vendor) as db:
            db.execute("UPDATE HCCLTaskSingleDevice SET op_name='another_op' WHERE batch_id=1")
        with self.assertRaisesRegex(MsprofDbError, "operation name mismatch"):
            export_identity(self.source, self.profile, self.output)

    def test_missing_vendor_data_does_not_guess_batch(self):
        self.vendor.unlink()
        with self.assertRaisesRegex(MsprofDbError, "not found"):
            export_identity(self.source, self.profile, self.output)

    def test_existing_output_never_overwritten(self):
        export_identity(self.source, self.profile, self.output)
        before = sha256(self.output)
        with self.assertRaisesRegex(MsprofDbError, "new, non-linked"):
            export_identity(self.source, self.profile, self.output)
        self.assertEqual(before, sha256(self.output))

    def test_unknown_encoding_is_rejected(self):
        export_identity(self.source, self.profile, self.output)
        with sqlite3.connect(self.output) as db:
            db.execute("UPDATE META_DATA SET value='unknown' WHERE name='HCCL_TRACE_TASK_BATCH_ENCODING'")
        with self.assertRaisesRegex(MsprofDbError, "schema/encoding"):
            parse_file(str(self.output), "node0")

    def test_orphan_batch_is_rejected(self):
        export_identity(self.source, self.profile, self.output)
        with sqlite3.connect(self.output) as db:
            db.execute("INSERT INTO " + TASK_BATCH_TABLE + " VALUES(999,1,0)")
        with self.assertRaisesRegex(MsprofDbError, "no exact TASK"):
            parse_file(str(self.output), "node0")

    def test_partial_batch_coverage_is_rejected(self):
        export_identity(self.source, self.profile, self.output)
        with sqlite3.connect(self.output) as db:
            db.execute("DELETE FROM " + TASK_BATCH_TABLE + " WHERE batchId=1")
        with self.assertRaisesRegex(MsprofDbError, "incomplete exported"):
            parse_file(str(self.output), "node0")

    def test_placeholder_reuse_keeps_all_executions(self):
        with sqlite3.connect(self.source) as db:
            db.executemany("INSERT INTO TASK VALUES(?,?,0,-1,?,2,4294967295,47,0,0)",
                           [(9009,9010,50),(9011,9012,51)])
        rows, stats = merge_records([], parse_file(str(self.source), "node0"))
        self.assertEqual(stats["duplicate_profiler_execution_keys"], 0)
        path = self.root / "merged.csv"
        write_csv(str(path), list(MERGED_FIELDS), rows)
        nodes = read_execution_rows(path)
        self.assertEqual(len(nodes), 6)
        self.assertEqual(len({r["_graph_id"] for r in nodes}), 6)
        reversed_path = self.root / "reversed.csv"
        write_csv(str(reversed_path), list(MERGED_FIELDS), reversed(rows))
        self.assertEqual({r["_graph_id"] for r in nodes},
                         {r["_graph_id"] for r in read_execution_rows(reversed_path)})

    def test_same_task_index_is_still_a_hard_duplicate(self):
        task = replace(parse_file(str(self.source), "node0")[0], task_index="10:1001")
        rows, stats = merge_records([], [task, task])
        self.assertEqual(stats["duplicate_profiler_execution_keys"], 1)
        path = self.root / "duplicate.csv"
        write_csv(str(path), list(MERGED_FIELDS), rows)
        with self.assertRaisesRegex(ValueError, "duplicate physical"):
            read_execution_rows(path)

    def test_adjacent_large_nanoseconds_are_distinct_db_keys(self):
        start = 1790000000000000000
        with sqlite3.connect(self.source) as db:
            db.executemany("INSERT INTO TASK VALUES(?,?,0,-1,50,2,4294967295,47,0,0)",
                           [(start,start+1),(start+1,start+2)])
        tasks = [t for t in parse_file(str(self.source), "node0") if t.global_task_id == 50]
        self.assertEqual({t.task_index for t in tasks}, {"50:"+str(start), "50:"+str(start+1)})
        rows, stats = merge_records([], tasks)
        self.assertEqual(stats["duplicate_profiler_execution_keys"], 0)
        path = self.root / "precise.csv"
        write_csv(str(path), list(MERGED_FIELDS), rows)
        self.assertEqual(len({r["_graph_id"] for r in read_execution_rows(path)}), 2)

    def test_wrong_batch_cannot_be_repaired_by_nearest_time(self):
        with sqlite3.connect(self.vendor) as db:
            db.execute("UPDATE HCCLTaskSingleDevice SET batch_id=2 WHERE batch_id=1")
        export_identity(self.source, self.profile, self.output)
        _, stats = merge_records(self.semantics(), parse_file(str(self.output), "node0"))
        self.assertEqual(stats["exact_matched"], 1)
        self.assertEqual(stats["unmatched_semantic"], 1)

    def test_old_task_model_keeps_legacy_exact_identity(self):
        task = ProfilerTask(node_id="node0", device_id=0, stream_id=45, task_id=3,
            task_kind="notify_record", event_name="NOTIFY_RECORD", profiler_notify_id=99,
            profiler_src_rank=0, profiler_dst_rank=1)
        _, stats = merge_records([self.semantics()[0]], [task])
        self.assertEqual(stats["exact_matched"], 1)


if __name__ == "__main__":
    unittest.main()
