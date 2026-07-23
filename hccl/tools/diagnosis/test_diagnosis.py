#!/usr/bin/env python3
"""Unit tests for the DB-backed HCCL trace diagnosis pipeline."""

from __future__ import annotations

import os
import sqlite3
import sys
import tempfile
import unittest

if __package__ in (None, ""):
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from diagnosis.merge_timeline import merge_records, parse_plog_inputs
    from diagnosis.parse_msprof_db import (
        MsprofDbError,
        parse_file as parse_msprof_db_file,
        parse_inputs as parse_msprof_db_inputs,
    )
    from diagnosis.parse_plog import parse_graph_correlation_lines, parse_plog_lines
    from diagnosis.schema import GraphCorrelation, ProfilerTask
    from diagnosis.validate_trace import validate_rows
    from diagnosis.visualize_dependency_graph import build_execution_edges
    from diagnosis.visualize_html import build_execution_dependency_model
    from diagnosis.visualize_timeline import assign_time_slots
else:
    from .merge_timeline import merge_records, parse_plog_inputs
    from .parse_msprof_db import (
        MsprofDbError,
        parse_file as parse_msprof_db_file,
        parse_inputs as parse_msprof_db_inputs,
    )
    from .parse_plog import parse_graph_correlation_lines, parse_plog_lines
    from .schema import GraphCorrelation, ProfilerTask
    from .validate_trace import validate_rows
    from .visualize_dependency_graph import build_execution_edges
    from .visualize_html import build_execution_dependency_model
    from .visualize_timeline import assign_time_slots


def profiler_task(
    name,
    stream,
    task,
    start,
    subtask=0xFFFFFFFF,
    connection=77,
    duration=1,
):
    normalized = name.strip().upper().replace(" ", "_")
    kinds = {
        "SDMA": "sdma",
        "MEMCPY_ASYNC": "sdma",
        "WRITE_VALUE": "notify_record",
        "NOTIFY_RECORD": "notify_record",
        "NOTIFY_WAIT": "notify_wait",
    }
    return ProfilerTask(
        node_id="node0",
        device_id=0,
        stream_id=stream,
        task_id=task,
        task_kind=kinds.get(normalized, name.strip().lower()),
        task_start=str(start),
        task_stop=str(start + duration),
        duration=str(duration),
        event_name=name,
        subtask_id=-1 if subtask == 0xFFFFFFFF else subtask,
        connection_id=connection,
        model_id=0,
    )


def create_msprof_db(path, schema_version="1.2.0", device_id=0):
    connection = sqlite3.connect(path)
    connection.executescript(
        """
        CREATE TABLE META_DATA(name TEXT, value TEXT);
        CREATE TABLE STRING_IDS(id INTEGER PRIMARY KEY, value TEXT);
        CREATE TABLE TASK(
            startNs INTEGER, endNs INTEGER, deviceId INTEGER, connectionId INTEGER,
            globalTaskId INTEGER, taskType INTEGER, contextId INTEGER, streamId INTEGER,
            taskId INTEGER, modelId INTEGER
        );
        CREATE TABLE COMMUNICATION_TASK_INFO(
            globalTaskId INTEGER, notifyId INTEGER, srcRank INTEGER, dstRank INTEGER,
            opId INTEGER
        );
        CREATE TABLE COMMUNICATION_OP(
            opName INTEGER, connectionId INTEGER, groupName INTEGER, opId INTEGER,
            deviceId INTEGER
        );
        CREATE TABLE COMPUTE_TASK_INFO(name INTEGER, globalTaskId INTEGER);
        """
    )
    connection.execute(
        "INSERT INTO META_DATA VALUES('SCHEMA_VERSION', ?)", (schema_version,))
    connection.executemany(
        "INSERT INTO STRING_IDS VALUES(?, ?)",
        (
            (1, "MEMCPY_ASYNC"),
            (2, "STARS_COMMON"),
            (3, "NOTIFY_RECORD"),
            (4, "hcom_allReduce__fixture_0"),
            (5, "group_fixture"),
            (6, "fixture_compute_kernel"),
        ),
    )
    connection.executemany(
        "INSERT INTO TASK VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            (1001, 2002, device_id, 77, 10, 1, 0xFFFFFFFF, 13, 1, 0),
            (3003, 4004, device_id, 78, 11, 2, 0xFFFFFFFF, 47, 2, 0),
            (5005, 6006, device_id, 79, 12, 3, 8, 45, 3, 0),
        ),
    )
    connection.execute("INSERT INTO COMPUTE_TASK_INFO VALUES(6, 11)")
    connection.execute(
        "INSERT INTO COMMUNICATION_TASK_INFO VALUES(12, 99, 0, 1, 7)")
    connection.execute("INSERT INTO COMMUNICATION_OP VALUES(4, 79, 5, 7, ?)", (device_id,))
    connection.commit()
    connection.close()


def execution_row(index, stream, task, start, kind="sdma", connection=77, event="", rank=-1, peer=-1,
                  step=-1, slice_id=-1, notify_id=-1):
    return {
        "_source_row": index,
        "_graph_id": f"p{index}",
        "_node_id": "node0",
        "_device_id": rank if rank >= 0 else 0,
        "_user_rank": rank,
        "_rank": rank if rank >= 0 else 0,
        "_rank_size": 2,
        "_stream_id": stream,
        "_task_id": task,
        "_subtask_id": -1,
        "_connection_id": connection,
        "_peer_rank": peer,
        "_notify_id": notify_id,
        "_step": step,
        "_slice": slice_id,
        "_start": float(start),
        "_stop": float(start + 1),
        "_duration": 1.0,
        "_phase_group": "reduce_scatter",
        "profiler_task_kind": kind,
        "event": event,
    }


class DiagnosisToolTest(unittest.TestCase):
    def test_dependency_html_model_keeps_fixed_track_metadata(self):
        zero = execution_row(2, 45, 3, 104)
        zero["_stop"] = zero["_start"]
        zero["_duration"] = 0.0
        rows = [execution_row(0, 45, 1, 100), execution_row(1, 45, 2, 102), zero]
        edges = build_execution_edges(rows)
        model = build_execution_dependency_model(rows, edges)
        self.assertEqual(model["lanes"][0]["taskCount"], 3)
        self.assertEqual(model["timeMin"], 100.0)
        self.assertGreater(model["timeScale"], 0)
        self.assertFalse(model["nodes"][0]["zeroDuration"])
        self.assertTrue(model["nodes"][2]["zeroDuration"])
        self.assertEqual(model["edges"][0]["kind"], "stream_order_observed")
        self.assertIn("adjacent executions", model["edges"][0]["reason"])

    def test_composite_without_correlation_remains_unmatched(self):
        profilers = [
            profiler_task(name, 45, 1, 100 + subtask, subtask=subtask)
            for subtask, name in enumerate(("SDMA", "SDMA", "SDMA", "Write Value", "Notify Wait"))
        ]
        profilers.append(profiler_task("MEMCPY_ASYNC", 45, 2, 200, duration=2))
        semantics = list(parse_plog_lines([
            "[HcclTaskSemantic] schema_version[2] device_id[0] stream_id[45] hccl_task_id[0] "
            "semantic_seq[0] profiler_seq[3] "
            "task_kind[sdma] event[copy_start] phase[reduce_scatter_direct] step[0] "
            "user_rank[0] comm_rank[0] rank_size[2]\n",
            "[HcclTaskSemantic] schema_version[2] device_id[0] stream_id[45] hccl_task_id[2] "
            "semantic_seq[1] profiler_seq[5] "
            "task_kind[sdma] event[rx_payload_copy_start] phase[allgather_direct] step[0] "
            "user_rank[0] comm_rank[0] rank_size[2]\n",
        ]))

        rows, stats = merge_records(semantics, profilers)
        matched = [row for row in rows if row["match_status"] == "matched"]

        self.assertEqual(stats["matched"], 1)
        self.assertEqual(stats["unmatched_semantic"], 1)
        self.assertEqual(matched[0]["profiler_task_id"], 2)
        self.assertEqual(matched[0]["match_confidence"], "exact")

    def test_ffts_parent_ctx_correlation_matches_exact_subtask(self):
        profilers = [
            profiler_task("Write Value", 45, 1, 100, subtask=8),
            profiler_task("SDMA", 45, 1, 101, subtask=13),
        ]
        semantics = list(parse_plog_lines([
            "[HcclTaskSemantic] schema_version[2] device_id[0] stream_id[45] hccl_task_id[0] "
            "semantic_seq[0] profiler_seq[6] task_kind[notify_record] event[tx_ack_start] "
            "phase[reduce_scatter_direct] ffts_ctx_id[8] "
            "graph_instance_id[7]\n",
            "[HcclTaskSemantic] schema_version[2] device_id[0] stream_id[13] hccl_task_id[0] "
            "semantic_seq[0] profiler_seq[3] task_kind[reduce_inline] "
            "event[rx_payload_reduce_start] phase[reduce_scatter_direct] "
            "ffts_ctx_id[13] graph_instance_id[7]\n",
        ]))
        correlations = [
            GraphCorrelation(
                graph_instance_id=7,
                device_id=0,
                anchor_task_id=0,
                parent_stream_id=45,
                parent_task_id=1,
                node_id="node0",
            )
        ]

        rows, stats = merge_records(semantics, profilers, correlations)
        matched = [row for row in rows if row["match_status"] == "matched"]

        self.assertEqual(stats["ffts_parent_ctx_matches"], 2)
        self.assertEqual(stats["matched"], 2)
        self.assertEqual({row["subtask_id"] for row in matched}, {8, 13})
        self.assertEqual({row["match_method"] for row in matched}, {"ffts_parent_ctx"})
        self.assertEqual({row["match_confidence"] for row in matched}, {"exact"})
        self.assertEqual({row["profiler_stream_id"] for row in matched}, {45})

    def test_graph_correlation_plog_is_parsed(self):
        records = list(parse_graph_correlation_lines([
            "[INFO] HCCL(123,python):2026-07-15-16:32:01.129.303 "
            "[HcclTaskGraphCorrelation] schema_version[1] graph_instance_id[9] "
            "device_id[2] anchor_task_id[40] parent_stream_id[45] parent_task_id[41]\n"
        ]))
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0].graph_instance_id, 9)
        self.assertEqual(records[0].parent_stream_id, 45)
        self.assertEqual(records[0].parent_task_id, 41)
        self.assertEqual(records[0].pid, 123)

    def test_v1_is_rejected_and_v2_invalid_ffts_sentinels_are_normalized(self):
        unsupported = (
            "[HcclTaskSemantic] schema_version[1] device_id[0] stream_id[45] "
            "hccl_task_id[2] task_kind[sdma] event[copy_start] phase[allgather_direct]\n",
            "[HcclTaskSemantic] device_id[0] stream_id[45] hccl_task_id[2] "
            "task_kind[sdma] event[copy_start] phase[allgather_direct]\n",
        )
        for line in unsupported:
            with self.subTest(line=line), self.assertRaises(ValueError):
                list(parse_plog_lines([line]))
        semantics = list(parse_plog_lines([
            "[HcclTaskSemantic] schema_version[2] device_id[0] stream_id[45] hccl_task_id[3] "
            "task_kind[sdma] event[copy_start] phase[allgather_direct] "
            "ffts_ctx_id[4294967295] graph_instance_id[18446744073709551615]\n",
        ]))
        self.assertEqual(semantics[0].ffts_ctx_id, -1)
        self.assertEqual(semantics[0].graph_instance_id, -1)

    def test_duplicate_graph_correlation_is_not_used(self):
        profilers = [profiler_task("Write Value", 45, 1, 100, subtask=8)]
        semantics = list(parse_plog_lines([
            "[HcclTaskSemantic] schema_version[2] device_id[0] stream_id[45] hccl_task_id[0] "
            "semantic_seq[0] task_kind[notify_record] event[tx_ack_start] "
            "phase[reduce_scatter_direct] ffts_ctx_id[8] "
            "graph_instance_id[7]\n",
        ]))
        correlations = [
            GraphCorrelation(graph_instance_id=7, device_id=0, parent_stream_id=45,
                             parent_task_id=1, node_id="node0"),
            GraphCorrelation(graph_instance_id=7, device_id=0, parent_stream_id=45,
                             parent_task_id=2, node_id="node0"),
        ]
        rows, stats = merge_records(semantics, profilers, correlations)
        self.assertEqual(stats["duplicate_graph_correlation_keys"], 1)
        self.assertEqual(stats["matched"], 0)
        self.assertEqual(
            [row for row in rows if row["match_status"] == "unmatched_semantic"][0]
            ["ffts_ctx_id"],
            8,
        )

    def test_validation_gate_rejects_invalid_matches(self):
        rows = [
            {"match_status": "matched", "match_confidence": "exact",
             "duplicate_semantic": "0", "duplicate_profiler": "0"},
            {"match_status": "correlation_kind_mismatch", "match_confidence": "invalid",
             "duplicate_semantic": "0", "duplicate_profiler": "0"},
        ]
        ok, stats = validate_rows(rows, 50.0)
        self.assertFalse(ok)
        self.assertEqual(stats["invalid_matches"], 1)
        self.assertEqual(stats["exact_match_rate_percent"], 50.0)

    def test_exact_allgather_wins_reused_reduce_scatter_task_id(self):
        profilers = [profiler_task("MEMCPY_ASYNC", 13, 3, 200, duration=2)]
        semantics = list(parse_plog_lines([
            "[HcclTaskSemantic] schema_version[2] device_id[0] stream_id[13] hccl_task_id[3] "
            "semantic_seq[0] profiler_seq[1] "
            "task_kind[sdma] event[copy_start] phase[reduce_scatter_direct] step[0]\n",
            "[HcclTaskSemantic] schema_version[2] device_id[0] stream_id[13] hccl_task_id[3] "
            "semantic_seq[1] profiler_seq[2] "
            "task_kind[sdma] event[copy_start] phase[reduce_scatter_direct] step[1]\n",
            "[HcclTaskSemantic] schema_version[2] device_id[0] stream_id[13] hccl_task_id[3] "
            "semantic_seq[2] profiler_seq[3] "
            "task_kind[sdma] event[copy_start] phase[allgather_direct] step[0]\n",
        ]))

        rows, stats = merge_records(semantics, profilers)

        self.assertEqual(stats["matched"], 1)
        self.assertEqual(stats["unmatched_semantic"], 2)
        self.assertEqual([row for row in rows if row["match_status"] == "matched"][0]["phase"],
                         "allgather_direct")

    def test_msprof_db_preserves_integer_time_and_enriches_metadata(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = os.path.join(temp_dir, "msprof_fixture.db")
            create_msprof_db(path)
            tasks = parse_msprof_db_file(path, "node0")
        self.assertEqual(len(tasks), 3)
        self.assertEqual(tasks[0].task_start, "1.001")
        self.assertEqual(tasks[0].task_stop, "2.002")
        self.assertEqual(tasks[0].duration, "1.001")
        self.assertEqual(tasks[1].event_name, "fixture_compute_kernel")
        self.assertEqual(tasks[2].subtask_id, 8)
        self.assertEqual(tasks[2].op_name, "hcom_allReduce__fixture_0")
        self.assertEqual(tasks[2].group_name, "group_fixture")
        self.assertEqual(tasks[2].profiler_notify_id, 99)
        self.assertEqual(tasks[2].profiler_src_rank, 0)
        self.assertEqual(tasks[2].profiler_dst_rank, 1)

    def test_msprof_db_rejects_unknown_schema(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = os.path.join(temp_dir, "msprof_fixture.db")
            create_msprof_db(path, schema_version="9.9.9")
            with self.assertRaisesRegex(MsprofDbError, "unsupported msprof DB schema"):
                parse_msprof_db_file(path, "node0")

    def test_msprof_db_rejects_missing_required_table(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = os.path.join(temp_dir, "msprof_fixture.db")
            create_msprof_db(path)
            connection = sqlite3.connect(path)
            connection.execute("DROP TABLE COMPUTE_TASK_INFO")
            connection.commit()
            connection.close()
            with self.assertRaisesRegex(MsprofDbError, "missing table COMPUTE_TASK_INFO"):
                parse_msprof_db_file(path, "node0")

    def test_msprof_db_directory_discovers_one_profile(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            profile_dir = os.path.join(temp_dir, "PROF_fixture")
            os.mkdir(profile_dir)
            create_msprof_db(os.path.join(profile_dir, "msprof_fixture.db"), device_id=3)
            tasks = parse_msprof_db_inputs(
                msprof_db_dir=temp_dir, default_node_id="node0")
        self.assertEqual(len(tasks), 3)
        self.assertEqual({task.device_id for task in tasks}, {3})

    def test_msprof_db_rejects_duplicate_device_inputs(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            create_msprof_db(os.path.join(temp_dir, "msprof_a.db"))
            create_msprof_db(os.path.join(temp_dir, "msprof_b.db"))
            with self.assertRaisesRegex(MsprofDbError, "duplicate device 0"):
                parse_msprof_db_inputs(msprof_db_dir=temp_dir, default_node_id="node0")

    def test_msprof_db_rejects_ambiguous_communication_metadata(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = os.path.join(temp_dir, "msprof_fixture.db")
            create_msprof_db(path)
            connection = sqlite3.connect(path)
            connection.execute(
                "INSERT INTO COMMUNICATION_TASK_INFO VALUES(12, 100, 0, 1, 7)")
            connection.commit()
            connection.close()
            with self.assertRaisesRegex(MsprofDbError, "ambiguous COMMUNICATION_TASK_INFO"):
                parse_msprof_db_file(path, "node0")

    def test_plog_dir_loads_all_rank_files(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            for rank in (0, 1):
                path = os.path.join(temp_dir, f"plog-{rank}.log")
                with open(path, "w", encoding="utf-8") as output:
                    output.write(
                        f"[HcclTaskSemantic] schema_version[2] device_id[{rank}] stream_id[12] "
                        "hccl_task_id[34] "
                        f"user_rank[{rank}] comm_rank[{rank}] rank_size[2] event[rx_ack_start] "
                        "phase[reduce_scatter_direct] step[0] task_kind[notify_wait]\n"
                    )
            records = parse_plog_inputs(plog_dir=temp_dir)
        self.assertEqual({record.device_id for record in records}, {0, 1})

    def test_submit_ts_and_profiler_seq_are_parsed(self):
        semantics = list(parse_plog_lines([
            "[HcclTaskSemantic] schema_version[3] device_id[7] stream_id[45] hccl_task_id[0] "
            "semantic_seq[0] profiler_seq[3] submit_ts[1783015731413749] "
            "notify_id[99] notify_stage[2] task_kind[sdma] event[copy_start] "
            "phase[reduce_scatter_direct] step[0]\n",
        ]))
        self.assertEqual(semantics[0].submit_ts, 1783015731413749)
        self.assertEqual(semantics[0].profiler_seq, 3)
        self.assertEqual(semantics[0].notify_id, 99)
        self.assertEqual(semantics[0].notify_stage, 2)

    def test_physical_dependency_stream_order_and_notify_sync(self):
        rows = [
            execution_row(0, 45, 1, 0),
            execution_row(1, 45, 2, 2, kind="notify_record"),
            execution_row(2, 13, 1, 1, kind="notify_wait"),
            execution_row(3, 13, 2, 4),
        ]
        rows[2]["_stop"] = 3.0
        edges = build_execution_edges(rows)
        kinds = {edge["kind"] for edge in edges}
        self.assertIn("stream_order_observed", kinds)
        self.assertIn("notify_sync_inferred", kinds)
        notify = next(edge for edge in edges if edge["kind"] == "notify_sync_inferred")
        self.assertEqual(notify["confidence"], "inferred")

    def test_physical_dependency_peer_semantic_pair(self):
        tx = execution_row(0, 45, 1, 0, event="tx_ack_start", rank=0, peer=1, step=0, slice_id=6)
        rx = execution_row(1, 45, 1, 1, event="rx_ack_start", rank=1, peer=0, step=0, slice_id=6)
        edges = build_execution_edges([tx, rx])
        peer = [edge for edge in edges if edge["kind"] == "peer_signal_semantic"]
        self.assertEqual(len(peer), 1)
        self.assertEqual(peer[0]["confidence"], "semantic")

    def test_notify_id_builds_observed_cross_stream_edge(self):
        record = execution_row(0, 45, 1, 0, kind="notify_record", notify_id=99)
        wait = execution_row(1, 13, 1, 1, kind="notify_wait", notify_id=99)
        record["task_kind"] = "notify_record"
        wait["task_kind"] = "notify_wait"
        edges = build_execution_edges([record, wait])
        observed = [edge for edge in edges if edge["kind"] == "notify_sync_observed"]
        self.assertEqual(len(observed), 1)
        self.assertEqual(observed[0]["confidence"], "observed")

    def test_timeline_stacks_overlapping_tasks(self):
        def row(index, start, stop):
            return {
                "_node_id": "node0", "_device_id": 0, "_rank": 0, "_stream_id": 10,
                "_task_id": index, "_phase": "reduce_scatter_direct", "_step": 0,
                "_event": "rx_payload_reduce_start", "_slice": index,
                "_start": start, "_stop": stop,
            }
        rows = [row(0, 0.0, 10.0), row(1, 5.0, 12.0), row(2, 12.0, 14.0)]
        slot_counts = assign_time_slots(rows)
        self.assertEqual(slot_counts[("node0", 0, 0, 10)], 2)
        self.assertEqual([item["_time_slot"] for item in rows], [0, 1, 0])


if __name__ == "__main__":
    unittest.main()
