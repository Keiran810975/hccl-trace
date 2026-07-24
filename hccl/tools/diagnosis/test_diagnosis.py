#!/usr/bin/env python3
"""Unit tests for the DB-backed HCCL trace diagnosis pipeline."""

from __future__ import annotations

import csv
import os
import sqlite3
import sys
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from diagnosis.dependency_model import (
        NOTIFY_SEQUENCE_DB_LOCAL_ORDINAL,
        NOTIFY_SEQUENCE_DB_ORDINAL,
        NOTIFY_SEQUENCE_FFTS_GRAPH,
        NOTIFY_SEQUENCE_TOKEN,
        NotifyRelationIdentity,
        normalize_notify_endpoint,
    )
    from diagnosis.merge_timeline import (
        PhaseConflictError,
        build_operation_scope_assignments,
        merge_records,
        parse_plog_inputs,
    )
    from diagnosis.parse_msprof_db import (
        MsprofDbError,
        parse_file as parse_msprof_db_file,
        parse_inputs as parse_msprof_db_inputs,
    )
    from diagnosis.parse_plog import parse_graph_correlation_lines, parse_plog_lines
    from diagnosis.schema import GraphCorrelation, ProfilerTask
    from diagnosis.validate_trace import collect_step_contract_errors, validate_rows
    from diagnosis.visualize_dependency_graph import (
        analyze_execution_graph,
        build_execution_edges,
        export_dependency_tables,
        read_execution_rows,
        to_int,
    )
    from diagnosis.visualize_html import build_execution_dependency_model
    from diagnosis.visualize_timeline import assign_time_slots
    from diagnosis.resource_dependency_graph import build_resource_graph
    from diagnosis.validate_dependency_graph import (
        FORBIDDEN_EDGE_KINDS,
        HARD_ZERO_METRICS,
        validate_dependency_artifacts,
    )
else:
    from .dependency_model import (
        NOTIFY_SEQUENCE_DB_LOCAL_ORDINAL,
        NOTIFY_SEQUENCE_DB_ORDINAL,
        NOTIFY_SEQUENCE_FFTS_GRAPH,
        NOTIFY_SEQUENCE_TOKEN,
        NotifyRelationIdentity,
        normalize_notify_endpoint,
    )
    from .merge_timeline import (
        PhaseConflictError,
        build_operation_scope_assignments,
        merge_records,
        parse_plog_inputs,
    )
    from .parse_msprof_db import (
        MsprofDbError,
        parse_file as parse_msprof_db_file,
        parse_inputs as parse_msprof_db_inputs,
    )
    from .parse_plog import parse_graph_correlation_lines, parse_plog_lines
    from .schema import GraphCorrelation, ProfilerTask
    from .validate_trace import collect_step_contract_errors, validate_rows
    from .visualize_dependency_graph import (
        analyze_execution_graph,
        build_execution_edges,
        export_dependency_tables,
        read_execution_rows,
        to_int,
    )
    from .visualize_html import build_execution_dependency_model
    from .visualize_timeline import assign_time_slots
    from .resource_dependency_graph import build_resource_graph
    from .validate_dependency_graph import (
        FORBIDDEN_EDGE_KINDS,
        HARD_ZERO_METRICS,
        validate_dependency_artifacts,
    )


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
        "profiler_task_kind": kind,
        "event": event,
    }


def ffts_execution_row(index, context, logical_stream, start=100, graph_instance=7):
    row = execution_row(index, 45, 9, start)
    row.update({
        "_subtask_id": context,
        "match_status": "matched",
        "ffts_ctx_id": str(context),
        "graph_instance_id": str(graph_instance),
        "stream_id": str(logical_stream),
        "pid": "123",
        "profiler_op_scope": "op_fixture",
        "profiler_op_scope_status": "unique",
        "correlation_parent_stream_id": "45",
        "correlation_parent_task_id": "9",
    })
    return row


def ffts_notify_row(
    index,
    context,
    rank,
    peer,
    kind,
    event,
    graph_instance=7,
    notify_id=99,
):
    row = ffts_execution_row(
        index,
        context,
        logical_stream=13 + rank,
        start=100 + index,
        graph_instance=graph_instance,
    )
    row.update({
        "_device_id": rank,
        "_user_rank": rank,
        "_rank": rank,
        "_peer_rank": peer,
        "_notify_id": notify_id,
        "_step": 2,
        "_slice": 5,
        "task_kind": kind,
        "profiler_task_kind": kind,
        "event": event,
        "phase": "reduce_scatter_direct",
    })
    return row


def direct_notify_row(
    index,
    rank,
    peer,
    kind,
    start,
    notify_id=99,
    stream=45,
    event="",
):
    row = execution_row(
        index,
        stream,
        index + 1,
        start,
        kind=kind,
        connection=100 + index,
        event=event,
        rank=rank,
        peer=peer,
        notify_id=notify_id,
    )
    row.update({
        "match_status": "matched" if event else "profiler_only",
        "task_kind": kind if event else "",
        "profiler_task_kind": kind,
        "profiler_op_scope": "op_fixture",
        "profiler_op_scope_status": "unique",
        "_operation_scope": "op_fixture",
        "_operation_scope_status": "unique",
        "phase": "reduce_scatter_direct" if event else "",
        "_step": 2 if event else -1,
        "_slice": 5 if event else -1,
    })
    return row


def local_notify_row(
    index,
    kind,
    start,
    stream,
    device=0,
    notify_id=99,
):
    return direct_notify_row(
        index,
        device,
        -1,
        kind,
        start,
        notify_id=notify_id,
        stream=stream,
    )


def dependency_edge(kind, src, dst, edge_id, relation_id=""):
    return {
        "graph_schema_version": "4",
        "edge_id": edge_id,
        "kind": kind,
        "src": src,
        "dst": dst,
        "reason": "fixture",
        "evidence": "fixture",
        "confidence": "exact",
        "relation_id": relation_id,
        "semantic_status": "both",
        "signal_kind": "ack",
        "phase": "reduce_scatter_direct",
        "step": "0",
        "slice": "0",
    }


class DiagnosisToolTest(unittest.TestCase):
    def test_dependency_reader_preserves_uint64_notify_identity(self):
        first = 18446744069414978848
        second = 18446744069414978852

        self.assertEqual(to_int(str(first)), first)
        self.assertEqual(to_int(str(second)), second)
        self.assertNotEqual(to_int(str(first)), to_int(str(second)))

    def test_notify_endpoint_roles_normalize_tx_and_rx_to_same_relation(self):
        producer = normalize_notify_endpoint(
            "notify_record", "tx_ack_start", 3, 2
        )
        consumer = normalize_notify_endpoint(
            "notify_wait", "rx_ack_start", 2, 3
        )
        self.assertEqual(producer, ("producer", 3, 2, "ack"))
        self.assertEqual(consumer, ("consumer", 3, 2, "ack"))

        direct_producer = normalize_notify_endpoint(
            "notify_record", "tx_payload_start", 3, 4
        )
        direct_consumer = normalize_notify_endpoint(
            "notify_wait", "rx_data_signal_start", 4, 3
        )
        self.assertEqual(direct_producer, ("producer", 3, 4, "data_signal"))
        self.assertEqual(direct_consumer, ("consumer", 3, 4, "data_signal"))

    def test_notify_relation_identity_separates_reused_resource_by_sequence(self):
        common = {
            "node_id": "node0",
            "operation_scope": "op_fixture",
            "rank_domain": "user",
            "producer_rank": 3,
            "consumer_rank": 4,
            "signal_kind": "data_signal",
            "phase": "reduce_scatter_direct",
            "step": 2,
            "slice_id": 5,
            "notify_id": 99,
            "sequence_kind": NOTIFY_SEQUENCE_FFTS_GRAPH,
        }
        first = NotifyRelationIdentity(sequence_value="7", **common)
        second = NotifyRelationIdentity(sequence_value="8", **common)

        self.assertTrue(first.complete)
        self.assertTrue(second.complete)
        self.assertEqual(first.resource.stable_id, second.resource.stable_id)
        self.assertNotEqual(first.stable_id, second.stable_id)

    def test_notify_relation_requires_sequence_and_never_uses_time(self):
        relation = NotifyRelationIdentity(
            node_id="node0",
            operation_scope="op_fixture",
            rank_domain="user",
            producer_rank=0,
            consumer_rank=1,
            signal_kind="ack",
            phase="reduce_scatter_direct",
            step=0,
            slice_id=7,
            notify_id=99,
            sequence_kind=NOTIFY_SEQUENCE_TOKEN,
            sequence_value="",
        )

        self.assertFalse(relation.complete)
        self.assertIn("sequence_value", relation.missing_fields)
        self.assertNotIn("task_start", relation.__dataclass_fields__)
        self.assertNotIn("task_stop", relation.__dataclass_fields__)

        invalid_graph_sequence = replace(
            relation,
            sequence_kind=NOTIFY_SEQUENCE_FFTS_GRAPH,
            sequence_value="-1",
        )
        self.assertFalse(invalid_graph_sequence.complete)
        self.assertIn("sequence_value", invalid_graph_sequence.missing_fields)

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
        self.assertEqual(model["edges"][0]["kind"], "direct_stream_order_observed")
        self.assertIn("direct execution", model["edges"][0]["reason"])

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
            replace(
                profiler_task("Write Value", 45, 1, 100, subtask=8),
                profiler_notify_id=99,
                profiler_src_rank=0,
                profiler_dst_rank=1,
            ),
            profiler_task("SDMA", 45, 1, 101, subtask=13),
        ]
        semantics = list(parse_plog_lines([
            "[HcclTaskSemantic] schema_version[2] device_id[0] stream_id[45] hccl_task_id[0] "
            "semantic_seq[0] profiler_seq[6] task_kind[notify_record] event[tx_ack_start] "
            "phase[reduce_scatter_direct] ffts_ctx_id[8] "
            "graph_instance_id[7] notify_id[99] user_rank[0] peer_rank[1]\n",
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

    def test_ring_step_contract_accepts_causal_buckets(self):
        rows = [
            {
                "match_status": "matched", "duplicate_semantic": "0",
                "duplicate_profiler": "0", "phase": "reduce_scatter_direct",
                "step": "0", "rank_size": "8", "event": "copy_start",
            },
            {
                "match_status": "matched", "duplicate_semantic": "0",
                "duplicate_profiler": "0", "phase": "reduce_scatter_direct",
                "step": "0", "rank_size": "8", "event": "tx_ack_start",
            },
            {
                "match_status": "matched", "duplicate_semantic": "0",
                "duplicate_profiler": "0", "phase": "allgather_direct",
                "step": "6", "rank_size": "8", "event": "tx_payload_start",
            },
            {
                "match_status": "matched", "duplicate_semantic": "0",
                "duplicate_profiler": "0", "phase": "allgather_direct",
                "step": "7", "rank_size": "8", "event": "copy_start",
            },
            {
                "match_status": "matched", "duplicate_semantic": "0",
                "duplicate_profiler": "0", "phase": "allgather_direct",
                "step": "0", "rank_size": "1", "event": "copy_start",
            },
        ]
        ok, stats = validate_rows(rows, 100.0)
        self.assertTrue(ok)
        self.assertEqual(stats["step_contract_rows"], 5)
        self.assertEqual(stats["step_contract_violations"], 0)

    def test_ring_step_contract_rejects_invalid_coordinates(self):
        rows = [
            {
                "match_status": "matched", "duplicate_semantic": "0",
                "duplicate_profiler": "0", "node_id": "node0",
                "device_id": "0", "stream_id": "45", "task_id": "7",
                "phase": "reduce_scatter_direct", "step": "-1",
                "rank_size": "8", "slice": "2", "event": "copy_start",
            },
            {
                "match_status": "matched", "duplicate_semantic": "0",
                "duplicate_profiler": "0", "phase": "allgather_direct",
                "step": "8", "rank_size": "8", "event": "copy_start",
            },
            {
                "match_status": "matched", "duplicate_semantic": "0",
                "duplicate_profiler": "0", "phase": "allgather_direct",
                "step": "7", "rank_size": "8", "event": "rx_ack_start",
            },
        ]
        ok, stats = validate_rows(rows, 100.0)
        self.assertFalse(ok)
        self.assertEqual(stats["step_contract_violations"], 3)
        self.assertEqual(stats["step_contract_step_out_of_range"], 2)
        self.assertEqual(stats["step_contract_main_event_in_epilogue"], 1)

        errors = collect_step_contract_errors(rows)
        self.assertEqual(len(errors), 3)
        self.assertIn(
            "row 2: reason=step_out_of_range node_id='node0' "
            "device_id='0' stream_id='45' task_id='7'",
            errors[0],
        )
        self.assertIn("phase='reduce_scatter_direct'", errors[0])
        self.assertIn("step='-1'", errors[0])

    def test_ring_step_contract_does_not_guess_for_unknown_phase(self):
        rows = [
            {
                "match_status": "matched", "duplicate_semantic": "0",
                "duplicate_profiler": "0", "phase": "mesh_phase",
                "step": "99", "rank_size": "8", "event": "tx_payload_start",
            },
        ]
        ok, stats = validate_rows(rows, 100.0)
        self.assertTrue(ok)
        self.assertEqual(stats["step_contract_rows"], 0)
        self.assertEqual(stats["step_contract_violations"], 0)

    def test_direct_rs_ag_reuse_raises_phase_conflict(self):
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

        with self.assertRaisesRegex(
            PhaseConflictError,
            "phase conflict.*stream_id=13.*task_id=3.*"
            "reduce_scatter_direct.*allgather_direct",
        ):
            merge_records(semantics, profilers)

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
        self.assertEqual(tasks[2].profiler_op_id, 7)
        self.assertEqual(tasks[2].profiler_op_connection_id, 79)
        self.assertEqual(tasks[2].profiler_notify_id, 99)
        self.assertEqual(tasks[2].profiler_src_rank, 0)
        self.assertEqual(tasks[2].profiler_dst_rank, 1)

    def test_merge_canonicalizes_profiler_only_notify_metadata(self):
        task = replace(
            profiler_task("NOTIFY_RECORD", 45, 1, 100),
            profiler_notify_id=99,
            profiler_src_rank=0,
            profiler_dst_rank=1,
            op_name="hcom_allReduce__fixture_0",
            group_name="group_fixture",
            profiler_op_id=7,
        )

        rows, _ = merge_records([], [task])

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["match_status"], "profiler_only")
        self.assertEqual(rows[0]["task_kind"], "notify_record")
        self.assertEqual(rows[0]["notify_id"], 99)
        self.assertEqual(rows[0]["user_rank"], 0)
        self.assertEqual(rows[0]["peer_rank"], 1)
        self.assertEqual(rows[0]["profiler_op_scope_status"], "unique")

    def test_merge_rejects_semantic_db_notify_identity_mismatch(self):
        task = replace(
            profiler_task("NOTIFY_RECORD", 45, 1, 100),
            profiler_notify_id=99,
            profiler_src_rank=0,
            profiler_dst_rank=1,
            op_name="hcom_allReduce__fixture_0",
            group_name="group_fixture",
            profiler_op_id=7,
        )
        semantics = list(parse_plog_lines([
            "[HcclTaskSemantic] schema_version[4] device_id[0] stream_id[45] "
            "hccl_task_id[1] task_kind[notify_record] event[tx_ack_start] "
            "phase[reduce_scatter_direct] step[0] slice[1] user_rank[0] "
            "peer_rank[1] notify_id[98]\n",
        ]))

        rows, stats = merge_records(semantics, [task])

        self.assertEqual(rows[0]["match_status"], "notify_metadata_mismatch")
        self.assertEqual(rows[0]["match_confidence"], "invalid")
        self.assertEqual(stats["notify_id_mismatch"], 1)
        self.assertEqual(stats["invalid_matches"], 1)

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

    def test_submit_ts_is_parsed_and_legacy_sequences_are_discarded(self):
        semantics = list(parse_plog_lines([
            "[HcclTaskSemantic] schema_version[3] device_id[7] stream_id[45] hccl_task_id[0] "
            "semantic_seq[0] profiler_seq[3] submit_ts[1783015731413749] "
            "notify_id[99] notify_stage[2] task_kind[sdma] event[copy_start] "
            "phase[reduce_scatter_direct] step[0]\n",
        ]))
        self.assertEqual(semantics[0].submit_ts, 1783015731413749)
        self.assertEqual(semantics[0].notify_id, 99)
        self.assertEqual(semantics[0].notify_stage, 2)
        self.assertNotIn("semantic_seq", semantics[0].__dataclass_fields__)
        self.assertNotIn("profiler_seq", semantics[0].__dataclass_fields__)
        self.assertNotIn("op_instance_id", semantics[0].__dataclass_fields__)
        self.assertNotIn("retry_generation", semantics[0].__dataclass_fields__)

        current = list(parse_plog_lines([
            "[HcclTaskSemantic] schema_version[4] device_id[7] stream_id[45] hccl_task_id[1] "
            "submit_ts[1783015731413750] task_kind[sdma] event[copy_start] "
            "phase[reduce_scatter_direct] step[0]\n",
        ]))
        self.assertEqual(current[0].schema_version, 4)
        self.assertEqual(current[0].task_id, 1)

    def test_default_dependency_graph_excludes_connection_time_notify(self):
        rows = [
            execution_row(0, 45, 1, 0),
            execution_row(1, 45, 2, 2, kind="notify_record"),
            execution_row(2, 13, 1, 1, kind="notify_wait"),
            execution_row(3, 13, 2, 4),
        ]
        rows[2]["_stop"] = 3.0
        edges = build_execution_edges(rows)
        kinds = {edge["kind"] for edge in edges}
        self.assertIn("direct_stream_order_observed", kinds)
        self.assertNotIn("notify_sync_inferred", kinds)

    def test_signal_semantic_does_not_create_time_zipped_control_edge(self):
        tx = execution_row(0, 45, 1, 0, event="tx_ack_start", rank=0, peer=1, step=0, slice_id=6)
        rx = execution_row(1, 45, 1, 1, event="rx_ack_start", rank=1, peer=0, step=0, slice_id=6)
        edges = build_execution_edges([tx, rx])
        self.assertFalse(any(
            edge["kind"] == "peer_signal_semantic" for edge in edges
        ))

    def test_peer_payload_semantic_does_not_create_causal_edge(self):
        tx = execution_row(
            0,
            45,
            1,
            0,
            kind="notify_record",
            event="tx_payload_start",
            rank=0,
            peer=1,
            step=0,
            slice_id=6,
        )
        rx = execution_row(
            1,
            45,
            1,
            1,
            event="rx_payload_copy_start",
            rank=1,
            peer=0,
            step=0,
            slice_id=6,
        )

        edges = build_execution_edges([tx, rx])

        self.assertFalse(any(
            edge["kind"] == "peer_payload_semantic" for edge in edges
        ))
        self.assertIn("peer_payload_semantic", FORBIDDEN_EDGE_KINDS)
        self.assertIn("resource_payload_semantic", FORBIDDEN_EDGE_KINDS)

    def test_direct_notify_db_ordinal_builds_exact_edges_without_cross_device_time(self):
        records = [
            direct_notify_row(0, 0, 1, "notify_record", 10),
            direct_notify_row(1, 0, 1, "notify_record", 20),
        ]
        waits = [
            direct_notify_row(2, 1, 0, "notify_wait", 9),
            direct_notify_row(3, 1, 0, "notify_wait", 19),
        ]
        ambiguities = []
        edges = build_execution_edges(
            records + waits,
            notify_ambiguities=ambiguities,
        )
        exact = [
            edge for edge in edges
            if edge["kind"] == "direct_notify_sync_exact"
        ]
        self.assertEqual(len(exact), 2)
        self.assertEqual(
            {
                edge["sequence_value"]: (edge["src"], edge["dst"])
                for edge in exact
            },
            {"0": ("p0", "p2"), "1": ("p1", "p3")},
        )
        self.assertEqual(
            {edge["sequence_kind"] for edge in exact},
            {NOTIFY_SEQUENCE_DB_ORDINAL},
        )
        self.assertEqual(
            {edge["semantic_status"] for edge in exact},
            {"none"},
        )
        self.assertEqual(ambiguities, [])

    def test_direct_notify_unequal_counts_are_not_partially_zipped(self):
        rows = [
            direct_notify_row(0, 0, 1, "notify_record", 10),
            direct_notify_row(1, 0, 1, "notify_record", 20),
            direct_notify_row(2, 1, 0, "notify_wait", 19),
        ]
        ambiguities = []
        edges = build_execution_edges(rows, notify_ambiguities=ambiguities)

        self.assertFalse(any(
            edge["kind"] == "direct_notify_sync_exact" for edge in edges
        ))
        direct = [
            row for row in ambiguities
            if row["sequence_kind"] == NOTIFY_SEQUENCE_DB_ORDINAL
        ]
        self.assertEqual(len(direct), 1)
        self.assertEqual(direct[0]["status"], "ambiguous")
        self.assertEqual((direct[0]["producer_count"], direct[0]["consumer_count"]), (2, 1))

    def test_direct_notify_semantics_are_annotations_on_exact_relation(self):
        record = direct_notify_row(
            0, 0, 1, "notify_record", 10, event="tx_ack_start"
        )
        wait = direct_notify_row(
            1, 1, 0, "notify_wait", 9, event="rx_ack_start"
        )
        edges = build_execution_edges([record, wait])
        exact = [
            edge for edge in edges
            if edge["kind"] == "direct_notify_sync_exact"
        ]

        self.assertEqual(len(exact), 1)
        self.assertEqual(exact[0]["semantic_status"], "both")
        self.assertEqual(exact[0]["signal_kind"], "ack")
        self.assertEqual(exact[0]["phase"], "reduce_scatter_direct")
        self.assertEqual(exact[0]["step"], 2)
        self.assertEqual(exact[0]["slice"], 5)

    def test_direct_notify_semantic_conflict_is_explicit_without_losing_physical_edge(self):
        record = direct_notify_row(
            0, 0, 1, "notify_record", 10, event="tx_ack_start"
        )
        wait = direct_notify_row(
            1, 1, 0, "notify_wait", 9, event="rx_data_signal_start"
        )
        ambiguities = []

        edges = build_execution_edges(
            [record, wait],
            notify_ambiguities=ambiguities,
        )

        exact = [
            edge for edge in edges
            if edge["kind"] == "direct_notify_sync_exact"
        ]
        self.assertEqual(len(exact), 1)
        self.assertEqual(exact[0]["semantic_status"], "conflict")
        conflicts = [
            row for row in ambiguities if row["status"] == "conflict"
        ]
        self.assertEqual(len(conflicts), 1)
        self.assertEqual(conflicts[0]["relation_id"], exact[0]["relation_id"])

    def test_local_notify_db_ordinal_builds_exact_cross_stream_edges(self):
        records = [
            local_notify_row(0, "notify_record", 10, 45),
            local_notify_row(1, "notify_record", 20, 45),
        ]
        waits = [
            local_notify_row(2, "notify_wait", 9, 13),
            local_notify_row(3, "notify_wait", 19, 13),
        ]
        ambiguities = []

        edges = build_execution_edges(
            records + waits,
            notify_ambiguities=ambiguities,
        )
        exact = [
            edge for edge in edges
            if edge["kind"] == "local_notify_sync_exact"
        ]

        self.assertEqual(len(exact), 2)
        self.assertEqual(
            {
                edge["sequence_value"]: (edge["src"], edge["dst"])
                for edge in exact
            },
            {"0": ("p0", "p2"), "1": ("p1", "p3")},
        )
        self.assertEqual(
            {edge["sequence_kind"] for edge in exact},
            {NOTIFY_SEQUENCE_DB_LOCAL_ORDINAL},
        )
        self.assertEqual({edge["confidence"] for edge in exact}, {"exact"})
        self.assertEqual(ambiguities, [])

    def test_local_notify_supports_slave_to_main_direction(self):
        record = local_notify_row(0, "notify_record", 10, 13)
        wait = local_notify_row(1, "notify_wait", 9, 45)

        edges = build_execution_edges([record, wait])
        exact = [
            edge for edge in edges
            if edge["kind"] == "local_notify_sync_exact"
        ]

        self.assertEqual(len(exact), 1)
        self.assertEqual(
            (exact[0]["src_stream"], exact[0]["dst_stream"]),
            (13, 45),
        )

    def test_local_notify_unequal_counts_are_not_partially_zipped(self):
        rows = [
            local_notify_row(0, "notify_record", 10, 45),
            local_notify_row(1, "notify_record", 20, 45),
            local_notify_row(2, "notify_wait", 9, 13),
        ]
        ambiguities = []

        edges = build_execution_edges(rows, notify_ambiguities=ambiguities)

        self.assertFalse(any(
            edge["kind"] == "local_notify_sync_exact" for edge in edges
        ))
        local = [
            row for row in ambiguities
            if row["sequence_kind"] == NOTIFY_SEQUENCE_DB_LOCAL_ORDINAL
        ]
        self.assertEqual(len(local), 1)
        self.assertEqual(local[0]["status"], "ambiguous")
        self.assertEqual(
            (local[0]["producer_count"], local[0]["consumer_count"]),
            (2, 1),
        )

    def test_local_notify_multiple_role_streams_are_ambiguous(self):
        rows = [
            local_notify_row(0, "notify_record", 10, 45),
            local_notify_row(1, "notify_record", 20, 46),
            local_notify_row(2, "notify_wait", 9, 13),
            local_notify_row(3, "notify_wait", 19, 13),
        ]
        ambiguities = []

        edges = build_execution_edges(rows, notify_ambiguities=ambiguities)

        self.assertFalse(any(
            edge["kind"] == "local_notify_sync_exact" for edge in edges
        ))
        self.assertEqual(len(ambiguities), 1)
        self.assertEqual(ambiguities[0]["status"], "ambiguous")
        self.assertEqual(ambiguities[0]["producer_stream_count"], 2)

    def test_local_and_cross_rank_notify_channels_do_not_mix(self):
        rows = [
            local_notify_row(0, "notify_record", 10, 45),
            local_notify_row(1, "notify_wait", 9, 13),
            direct_notify_row(2, 0, 1, "notify_record", 10),
            direct_notify_row(3, 1, 0, "notify_wait", 9),
        ]

        edges = build_execution_edges(rows)

        self.assertEqual(
            sum(edge["kind"] == "local_notify_sync_exact" for edge in edges),
            1,
        )
        self.assertEqual(
            sum(edge["kind"] == "direct_notify_sync_exact" for edge in edges),
            1,
        )

    def test_ffts_notify_unique_relation_builds_observed_edge(self):
        producer = ffts_notify_row(
            0, 8, 0, 1, "notify_record", "tx_ack_start"
        )
        consumer = ffts_notify_row(
            1, 9, 1, 0, "notify_wait", "rx_ack_start"
        )
        ambiguities = []

        edges = build_execution_edges(
            [producer, consumer],
            notify_ambiguities=ambiguities,
        )
        observed = [
            edge for edge in edges
            if edge["kind"] == "ffts_notify_sync_observed"
        ]

        self.assertEqual(len(observed), 1)
        self.assertEqual((observed[0]["src"], observed[0]["dst"]), ("p0", "p1"))
        self.assertEqual(observed[0]["confidence"], "observed")
        self.assertTrue(observed[0]["relation_id"].startswith("nr_"))
        self.assertEqual(ambiguities, [])

    def test_ffts_notify_single_endpoint_is_explicit(self):
        producer = ffts_notify_row(
            0, 8, 0, 1, "notify_record", "tx_ack_start"
        )
        ambiguities = []

        edges = build_execution_edges(
            [producer],
            notify_ambiguities=ambiguities,
        )

        self.assertFalse(any(
            edge["kind"] == "ffts_notify_sync_observed"
            for edge in edges
        ))
        self.assertEqual(len(ambiguities), 1)
        self.assertEqual(ambiguities[0]["status"], "single")
        self.assertEqual(ambiguities[0]["missing_role"], "consumer")
        self.assertEqual(ambiguities[0]["endpoint_graph_ids"], "p0")

    def test_ffts_notify_multiple_endpoints_are_not_sorted_or_zipped(self):
        first = ffts_notify_row(
            0, 8, 0, 1, "notify_record", "tx_ack_start"
        )
        second = ffts_notify_row(
            1, 10, 0, 1, "notify_record", "tx_ack_start"
        )
        consumer = ffts_notify_row(
            2, 9, 1, 0, "notify_wait", "rx_ack_start"
        )
        ambiguities = []

        edges = build_execution_edges(
            [first, second, consumer],
            notify_ambiguities=ambiguities,
        )

        self.assertFalse(any(
            edge["kind"] == "ffts_notify_sync_observed"
            for edge in edges
        ))
        self.assertEqual(len(ambiguities), 1)
        self.assertEqual(ambiguities[0]["status"], "ambiguous")
        self.assertEqual(ambiguities[0]["producer_count"], 2)
        self.assertEqual(ambiguities[0]["consumer_count"], 1)

    def test_ffts_notify_reused_resource_is_separated_by_graph_instance(self):
        rows = []
        for graph_instance, offset in ((7, 0), (8, 2)):
            rows.extend((
                ffts_notify_row(
                    offset,
                    8,
                    0,
                    1,
                    "notify_record",
                    "tx_ack_start",
                    graph_instance=graph_instance,
                ),
                ffts_notify_row(
                    offset + 1,
                    9,
                    1,
                    0,
                    "notify_wait",
                    "rx_ack_start",
                    graph_instance=graph_instance,
                ),
            ))
        ambiguities = []

        edges = build_execution_edges(rows, notify_ambiguities=ambiguities)
        observed = [
            edge for edge in edges
            if edge["kind"] == "ffts_notify_sync_observed"
        ]

        self.assertEqual(len(observed), 2)
        self.assertEqual(len({edge["relation_id"] for edge in observed}), 2)
        self.assertEqual(ambiguities, [])

    def test_direct_stream_builder_excludes_ffts_execution(self):
        first = execution_row(0, 45, 1, 0)
        ffts = ffts_execution_row(1, 0, 13, start=1)
        last = execution_row(2, 45, 2, 2)

        edges = build_execution_edges([first, ffts, last])
        stream_edges = [
            edge for edge in edges
            if edge["kind"] in (
                "direct_stream_order_observed",
                "ffts_logical_stream_order",
            )
        ]

        self.assertEqual(len(stream_edges), 1)
        self.assertEqual(stream_edges[0]["kind"], "direct_stream_order_observed")
        self.assertEqual((stream_edges[0]["src"], stream_edges[0]["dst"]), ("p0", "p2"))

    def test_direct_equal_start_is_an_unordered_bucket(self):
        rows = [
            execution_row(0, 45, 1, 0),
            execution_row(1, 45, 2, 2),
            execution_row(2, 45, 3, 2),
            execution_row(3, 45, 4, 4),
        ]

        edges = build_execution_edges(list(reversed(rows)))
        stream_pairs = {
            (edge["src"], edge["dst"])
            for edge in edges
            if edge["kind"] == "direct_stream_order_observed"
        }

        self.assertEqual(
            stream_pairs,
            {("p0", "p1"), ("p0", "p2"), ("p1", "p3"), ("p2", "p3")},
        )
        self.assertNotIn(("p1", "p2"), stream_pairs)
        self.assertNotIn(("p2", "p1"), stream_pairs)

    def test_dependency_edge_id_is_stable_across_input_reorder(self):
        rows = [
            execution_row(0, 45, 1, 0),
            execution_row(1, 45, 2, 2),
            execution_row(2, 45, 3, 4),
        ]

        forward = build_execution_edges(rows)
        reverse = build_execution_edges(list(reversed(rows)))

        self.assertEqual(forward, reverse)
        self.assertEqual(len({edge["edge_id"] for edge in forward}), 2)
        self.assertTrue(all(
            edge["edge_id"].startswith("e_") for edge in forward
        ))

    def test_execution_graph_quality_reports_cycles_isolation_and_missing_endpoints(self):
        rows = [
            execution_row(0, 45, 1, 0),
            execution_row(1, 45, 2, 2),
            execution_row(2, 13, 1, 0),
            execution_row(3, 13, 2, 2),
        ]
        edges = [
            {"edge_id": "e_a", "src": "p0", "dst": "p1"},
            {"edge_id": "e_b", "src": "p1", "dst": "p0"},
            {"edge_id": "e_c", "src": "missing", "dst": "p2"},
        ]

        stats = analyze_execution_graph(rows, edges)

        self.assertEqual(stats["node_count"], 4)
        self.assertEqual(stats["edge_count"], 3)
        self.assertEqual(stats["missing_edge_sources"], 1)
        self.assertEqual(stats["missing_edge_destinations"], 0)
        self.assertEqual(stats["isolated_nodes"], 2)
        self.assertEqual(stats["cycle_residual_nodes"], 2)
        self.assertEqual(stats["has_cycle"], 1)

    def test_execution_graph_export_writes_fixed_schema_and_summary(self):
        source_rows = [
            {
                "match_status": "profiler_only",
                "node_id": "node0",
                "device_id": "0",
                "profiler_stream_id": "45",
                "profiler_task_id": str(task_id),
                "subtask_id": "-1",
                "connection_id": "77",
                "task_start": str(start),
                "task_stop": str(start + 1),
                "duration": "1",
            }
            for task_id, start in ((1, 100), (2, 102))
        ]
        with tempfile.TemporaryDirectory() as temp_dir:
            merged = Path(temp_dir) / "merged.csv"
            with merged.open("w", encoding="utf-8", newline="") as output:
                writer = csv.DictWriter(
                    output, fieldnames=list(source_rows[0])
                )
                writer.writeheader()
                writer.writerows(source_rows)
            result = export_dependency_tables(
                merged, Path(temp_dir) / "dependency"
            )
            nodes_path, edges_path, _, summary_path = result[:4]
            with nodes_path.open(
                "r", encoding="utf-8", newline=""
            ) as source:
                node_fields = next(csv.reader(source))
            with edges_path.open(
                "r", encoding="utf-8", newline=""
            ) as source:
                edge_rows = list(csv.DictReader(source))
            with summary_path.open(
                "r", encoding="utf-8", newline=""
            ) as source:
                summary = {
                    row["metric"]: row["value"]
                    for row in csv.DictReader(source)
                }

        self.assertEqual(node_fields[:3], [
            "graph_schema_version", "graph_id", "match_status"
        ])
        self.assertEqual(len(edge_rows), 1)
        self.assertTrue(edge_rows[0]["edge_id"].startswith("e_"))
        self.assertEqual(summary["node_count"], "2")
        self.assertEqual(summary["edge_count"], "1")
        self.assertEqual(summary["missing_edge_sources"], "0")
        self.assertEqual(summary["cycle_residual_nodes"], "0")

    def test_resource_graph_contracts_notify_control_chain_and_metrics(self):
        resource_before = execution_row(0, 45, 1, 0)
        record = execution_row(1, 45, 2, 2, kind="notify_record")
        wait = execution_row(2, 13, 1, 1, kind="notify_wait")
        wait["_stop"] = 4.0
        wait["_duration"] = 3.0
        resource_after = execution_row(3, 13, 2, 5)
        edges = [
            dependency_edge(
                "direct_stream_order_observed", "p0", "p1", "e_order_a"
            ),
            dependency_edge(
                "direct_notify_sync_exact",
                "p1",
                "p2",
                "e_notify",
                "dnr_fixture",
            ),
            dependency_edge(
                "direct_stream_order_observed", "p2", "p3", "e_order_b"
            ),
        ]

        nodes, resource_edges, ambiguities = build_resource_graph(
            [resource_before, record, wait, resource_after],
            edges,
        )

        self.assertEqual({row["_graph_id"] for row in nodes}, {"p0", "p3"})
        self.assertEqual(ambiguities, [])
        self.assertEqual(len(resource_edges), 1)
        edge = resource_edges[0]
        self.assertEqual(edge["kind"], "resource_notify_sync_exact")
        self.assertEqual((edge["src"], edge["dst"]), ("p0", "p3"))
        self.assertEqual(edge["relation_id"], "dnr_fixture")
        self.assertEqual(edge["wait_span_ns"], "3000")
        self.assertEqual(edge["remote_block_ns"], "2000")
        self.assertEqual(edge["post_signal_ns"], "1000")
        self.assertEqual(edge["handoff_gap_ns"], "1000")
        self.assertEqual(edge["weight_ns"], "3000")
        self.assertEqual(edge["timing_status"], "same_node_observed")
        self.assertEqual(
            set(edge["source_execution_edge_ids"].split(";")),
            {"e_order_a", "e_notify", "e_order_b"},
        )
        self.assertEqual(
            set(edge["control_graph_ids"].split(";")),
            {"p1", "p2"},
        )

    def test_resource_graph_preserves_local_notify_kind_and_metrics(self):
        resource_before = execution_row(0, 45, 1, 0)
        record = execution_row(1, 45, 2, 2, kind="notify_record")
        wait = execution_row(2, 13, 1, 1, kind="notify_wait")
        wait["_stop"] = 4.0
        wait["_duration"] = 3.0
        resource_after = execution_row(3, 13, 2, 5)
        edges = [
            dependency_edge(
                "direct_stream_order_observed", "p0", "p1", "e_order_a"
            ),
            dependency_edge(
                "local_notify_sync_exact",
                "p1",
                "p2",
                "e_local_notify",
                "lnr_fixture",
            ),
            dependency_edge(
                "direct_stream_order_observed", "p2", "p3", "e_order_b"
            ),
        ]

        _, resource_edges, ambiguities = build_resource_graph(
            [resource_before, record, wait, resource_after],
            edges,
        )

        self.assertEqual(ambiguities, [])
        self.assertEqual(len(resource_edges), 1)
        edge = resource_edges[0]
        self.assertEqual(edge["kind"], "resource_local_notify_sync_exact")
        self.assertEqual((edge["src"], edge["dst"]), ("p0", "p3"))
        self.assertEqual(edge["relation_id"], "lnr_fixture")
        self.assertEqual(edge["wait_span_ns"], "3000")
        self.assertEqual(edge["weight_ns"], "3000")
        self.assertEqual(edge["timing_status"], "same_node_observed")

    def test_resource_graph_cross_node_does_not_compare_remote_timestamps(self):
        before = execution_row(0, 45, 1, 0)
        record = execution_row(1, 45, 2, 2, kind="notify_record")
        wait = execution_row(2, 13, 1, 1, kind="notify_wait")
        after = execution_row(3, 13, 2, 5)
        wait["_node_id"] = "node1"
        after["_node_id"] = "node1"
        edges = [
            dependency_edge(
                "direct_stream_order_observed", "p0", "p1", "e_order_a"
            ),
            dependency_edge(
                "direct_notify_sync_exact",
                "p1",
                "p2",
                "e_notify",
                "dnr_fixture",
            ),
            dependency_edge(
                "direct_stream_order_observed", "p2", "p3", "e_order_b"
            ),
        ]

        _, resource_edges, _ = build_resource_graph(
            [before, record, wait, after], edges
        )
        edge = resource_edges[0]

        self.assertEqual(edge["timing_status"], "cross_node_uncalibrated")
        self.assertEqual(edge["wait_span_ns"], "1000")
        self.assertEqual(edge["weight_ns"], "1000")
        self.assertEqual(edge["remote_block_ns"], "")
        self.assertEqual(edge["post_signal_ns"], "")
        self.assertEqual(edge["handoff_gap_ns"], "3000")

    def test_resource_graph_uses_boundary_for_missing_resource_endpoint(self):
        record = execution_row(0, 45, 1, 2, kind="notify_record")
        wait = execution_row(1, 13, 1, 1, kind="notify_wait")
        after = execution_row(2, 13, 2, 5)
        edges = [
            dependency_edge(
                "direct_notify_sync_exact",
                "p0",
                "p1",
                "e_notify",
                "dnr_fixture",
            ),
            dependency_edge(
                "direct_stream_order_observed", "p1", "p2", "e_order_b"
            ),
        ]

        nodes, resource_edges, ambiguities = build_resource_graph(
            [record, wait, after], edges
        )

        boundaries = [
            row for row in nodes if row.get("_node_kind") == "boundary"
        ]
        self.assertEqual(len(boundaries), 1)
        self.assertEqual(boundaries[0]["_boundary_side"], "upstream")
        self.assertEqual(len(resource_edges), 1)
        self.assertEqual(resource_edges[0]["src"], boundaries[0]["_graph_id"])
        self.assertEqual(resource_edges[0]["dst"], "p2")
        self.assertEqual(ambiguities, [])

    def test_resource_graph_does_not_cross_product_multiple_frontiers(self):
        first = execution_row(0, 45, 1, 0)
        second = execution_row(1, 46, 1, 0)
        record = execution_row(2, 47, 1, 2, kind="notify_record")
        wait = execution_row(3, 13, 1, 1, kind="notify_wait")
        after = execution_row(4, 13, 2, 5)
        edges = [
            dependency_edge(
                "direct_stream_order_observed", "p0", "p2", "e_order_a"
            ),
            dependency_edge(
                "direct_stream_order_observed", "p1", "p2", "e_order_b"
            ),
            dependency_edge(
                "direct_notify_sync_exact",
                "p2",
                "p3",
                "e_notify",
                "dnr_fixture",
            ),
            dependency_edge(
                "direct_stream_order_observed", "p3", "p4", "e_order_c"
            ),
        ]

        _, resource_edges, ambiguities = build_resource_graph(
            [first, second, record, wait, after], edges
        )

        self.assertFalse(any(
            edge["kind"] == "resource_notify_sync_exact"
            for edge in resource_edges
        ))
        self.assertEqual(len(ambiguities), 1)
        self.assertEqual(ambiguities[0]["upstream_resource_count"], 2)
        self.assertEqual(ambiguities[0]["downstream_resource_count"], 1)

    def test_dependency_gate_rejects_forbidden_inference_edge(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            execution_summary = root / "execution_summary.csv"
            resource_summary = root / "resource_summary.csv"
            execution_edges = root / "execution_edges.csv"
            resource_edges = root / "resource_edges.csv"
            summary_fields = ["metric", "value"]
            for path, rows in (
                (
                    execution_summary,
                    [
                        {"metric": metric, "value": "0"}
                        for metric in (
                            *HARD_ZERO_METRICS,
                            "notify_relation_ambiguous",
                            "notify_relation_incomplete",
                            "notify_relation_conflict",
                        )
                    ],
                ),
                (
                    resource_summary,
                    [
                        {"metric": metric, "value": "0"}
                        for metric in (
                            *HARD_ZERO_METRICS,
                            "contraction_ambiguities",
                            "boundary_nodes",
                        )
                    ],
                ),
            ):
                with path.open("w", encoding="utf-8", newline="") as output:
                    writer = csv.DictWriter(output, fieldnames=summary_fields)
                    writer.writeheader()
                    writer.writerows(rows)
            with execution_edges.open(
                "w", encoding="utf-8", newline=""
            ) as output:
                writer = csv.DictWriter(
                    output, fieldnames=["edge_id", "kind", "src", "dst"]
                )
                writer.writeheader()
                writer.writerow({
                    "edge_id": "e_forbidden",
                    "kind": "notify_sync_inferred",
                    "src": "a",
                    "dst": "b",
                })
            with resource_edges.open(
                "w", encoding="utf-8", newline=""
            ) as output:
                writer = csv.DictWriter(
                    output, fieldnames=["edge_id", "kind", "src", "dst"]
                )
                writer.writeheader()
            ok, stats, failures = validate_dependency_artifacts(
                execution_summary,
                execution_edges,
                resource_summary,
                resource_edges,
            )

        self.assertFalse(ok)
        self.assertEqual(stats["forbidden_edge_count"], 1)
        self.assertTrue(any("forbidden_edge_count" in item for item in failures))

    def test_ffts_order_is_rebuilt_per_semantic_logical_stream(self):
        rows = [
            ffts_execution_row(0, 0, 13),
            ffts_execution_row(1, 1, 45),
            ffts_execution_row(2, 2, 13),
            ffts_execution_row(3, 3, 45),
        ]

        edges = build_execution_edges(rows)
        logical_edges = [
            edge for edge in edges
            if edge["kind"] == "ffts_logical_stream_order"
        ]

        self.assertEqual(
            {(edge["src"], edge["dst"]) for edge in logical_edges},
            {("p0", "p2"), ("p1", "p3")},
        )
        self.assertEqual(
            {edge["confidence"] for edge in logical_edges},
            {"semantic"},
        )

    def test_ffts_duplicate_context_in_one_logical_stream_is_hard_error(self):
        first = ffts_execution_row(0, 3, 13)
        second = ffts_execution_row(1, 3, 13)
        with self.assertRaisesRegex(ValueError, "duplicate FFts context IDs"):
            build_execution_edges([first, second])

    def test_operation_scope_is_cross_device_and_local_ids_are_not_identity(self):
        first = replace(
            profiler_task("SDMA", 45, 1, 100),
            op_name="hcom_allReduce__fixture_0",
            group_name="group_fixture",
            profiler_op_id=7,
            profiler_op_connection_id=70,
        )
        second = replace(
            profiler_task("SDMA", 45, 1, 100),
            device_id=1,
            op_name="hcom_allReduce__fixture_0",
            group_name="group_fixture",
            profiler_op_id=41,
            profiler_op_connection_id=99,
        )
        rows, stats = merge_records([], [first, second])

        self.assertEqual(stats["profiler_operation_scope_unique"], 2)
        self.assertEqual(stats["profiler_operation_scope_distinct"], 1)
        self.assertEqual(
            {row["profiler_op_scope_status"] for row in rows},
            {"unique"},
        )
        self.assertEqual(len({row["profiler_op_scope"] for row in rows}), 1)

    def test_operation_scope_is_cross_node_for_one_profile_run(self):
        first = replace(
            profiler_task("SDMA", 45, 1, 100),
            node_id="node0",
            op_name="hcom_allReduce__612_0_1",
            group_name="group_name_0",
            profiler_op_id=7,
        )
        second = replace(
            profiler_task("SDMA", 45, 1, 100),
            node_id="node1",
            op_name="hcom_allReduce__612_0_1",
            group_name="group_name_0",
            profiler_op_id=41,
        )
        rows, stats = merge_records([], [first, second])

        self.assertEqual(stats["profiler_operation_scope_distinct"], 1)
        self.assertEqual(len({row["profiler_op_scope"] for row in rows}), 1)

    def test_operation_scope_uses_full_group_name_with_op_name(self):
        first = replace(
            profiler_task("SDMA", 45, 1, 100),
            op_name="hcom_allReduce__612_0_1",
            group_name="group_name_0",
            profiler_op_id=7,
        )
        second = replace(
            profiler_task("SDMA", 45, 2, 102),
            op_name="hcom_allReduce__612_0_1",
            group_name="group_name_1",
            profiler_op_id=8,
        )
        rows, stats = merge_records([], [first, second])

        self.assertEqual(stats["profiler_operation_scope_distinct"], 2)
        self.assertEqual(len({row["profiler_op_scope"] for row in rows}), 2)

    def test_operation_scope_rejects_two_local_op_ids_for_one_scope(self):
        first = replace(
            profiler_task("SDMA", 45, 1, 100),
            op_name="reused_name",
            group_name="group_fixture",
            profiler_op_id=7,
        )
        second = replace(
            profiler_task("SDMA", 45, 2, 102),
            op_name="reused_name",
            group_name="group_fixture",
            profiler_op_id=8,
        )
        assignments, stats = build_operation_scope_assignments([first, second])

        self.assertEqual(stats["profiler_operation_scope_ambiguous"], 2)
        self.assertEqual(stats["profiler_operation_scope_distinct"], 0)
        self.assertEqual(
            {value for value in assignments.values()},
            {("", "ambiguous")},
        )

    def test_execution_graph_id_survives_csv_reorder(self):
        source_rows = [
            {
                "match_status": "profiler_only",
                "node_id": "node0",
                "device_id": "0",
                "profiler_stream_id": "45",
                "profiler_task_id": "1",
                "subtask_id": "8",
                "connection_id": "77",
                "task_start": "100.001",
                "task_stop": "101.001",
            },
            {
                "match_status": "profiler_only",
                "node_id": "node0",
                "device_id": "0",
                "profiler_stream_id": "13",
                "profiler_task_id": "2",
                "subtask_id": "-1",
                "connection_id": "78",
                "task_start": "102.001",
                "task_stop": "103.001",
            },
        ]
        fieldnames = list(source_rows[0])
        with tempfile.TemporaryDirectory() as temp_dir:
            paths = [Path(temp_dir) / "forward.csv", Path(temp_dir) / "reverse.csv"]
            for path, values in zip(paths, (source_rows, list(reversed(source_rows)))):
                with path.open("w", encoding="utf-8", newline="") as output:
                    writer = csv.DictWriter(output, fieldnames=fieldnames)
                    writer.writeheader()
                    writer.writerows(values)
            forward = read_execution_rows(paths[0])
            reverse = read_execution_rows(paths[1])

        forward_ids = {
            (row["_stream_id"], row["_task_id"]): row["_graph_id"]
            for row in forward
        }
        reverse_ids = {
            (row["_stream_id"], row["_task_id"]): row["_graph_id"]
            for row in reverse
        }
        self.assertEqual(forward_ids, reverse_ids)
        self.assertTrue(all(value.startswith("x_") for value in forward_ids.values()))

    def test_direct_order_preserves_db_nanoseconds_at_large_absolute_time(self):
        source_rows = [
            {
                "match_status": "profiler_only",
                "node_id": "node0",
                "device_id": "0",
                "profiler_stream_id": "45",
                "profiler_task_id": str(task_id),
                "subtask_id": "-1",
                "connection_id": "77",
                "task_start": timestamp,
                "task_stop": stop,
                "duration": "0.001",
            }
            for task_id, timestamp, stop in (
                (1, "1783015731413.001", "1783015731413.002"),
                (2, "1783015731413.003", "1783015731413.004"),
            )
        ]
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "nanosecond.csv"
            with path.open("w", encoding="utf-8", newline="") as output:
                writer = csv.DictWriter(output, fieldnames=list(source_rows[0]))
                writer.writeheader()
                writer.writerows(source_rows)
            rows = read_execution_rows(path)

        edges = build_execution_edges(rows)
        stream_edges = [
            edge for edge in edges
            if edge["kind"] == "direct_stream_order_observed"
        ]
        self.assertEqual(len(stream_edges), 1)
        self.assertNotEqual(rows[0]["_start_order"], rows[1]["_start_order"])
        self.assertEqual(rows[0]["_duration"], 0.001)

    def test_duplicate_execution_identity_is_hard_error(self):
        duplicate = {
            "match_status": "profiler_only",
            "node_id": "node0",
            "device_id": "0",
            "profiler_stream_id": "45",
            "profiler_task_id": "1",
            "subtask_id": "8",
            "connection_id": "77",
            "task_start": "100",
            "task_stop": "101",
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "duplicate.csv"
            with path.open("w", encoding="utf-8", newline="") as output:
                writer = csv.DictWriter(output, fieldnames=list(duplicate))
                writer.writeheader()
                writer.writerows((duplicate, dict(duplicate)))
            with self.assertRaisesRegex(ValueError, "duplicate physical execution identity"):
                read_execution_rows(path)

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
