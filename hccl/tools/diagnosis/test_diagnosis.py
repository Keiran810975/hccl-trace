#!/usr/bin/env python3
"""Unit tests for the JSON-only HCCL trace diagnosis pipeline."""

from __future__ import annotations

import os
import sys
import tempfile
import unittest

if __package__ in (None, ""):
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from diagnosis.merge_timeline import merge_records, parse_plog_inputs
    from diagnosis.parse_msprof_json import parse_events
    from diagnosis.parse_plog import parse_graph_correlation_lines, parse_legacy_block
    from diagnosis.schema import GraphCorrelation
    from diagnosis.validate_trace import validate_rows
    from diagnosis.visualize_dependency_graph import build_execution_edges
    from diagnosis.visualize_html import build_execution_dependency_model
    from diagnosis.visualize_timeline import assign_time_slots
else:
    from .merge_timeline import merge_records, parse_plog_inputs
    from .parse_msprof_json import parse_events
    from .parse_plog import parse_graph_correlation_lines, parse_legacy_block
    from .schema import GraphCorrelation
    from .validate_trace import validate_rows
    from .visualize_dependency_graph import build_execution_edges
    from .visualize_html import build_execution_dependency_model
    from .visualize_timeline import assign_time_slots


def json_event(name, stream, task, start, subtask=0xFFFFFFFF, connection=77, duration=1):
    return {
        "name": name,
        "ph": "X",
        "ts": str(start),
        "dur": duration,
        "args": {
            "Task Type": name,
            "Physic Stream Id": stream,
            "Task Id": task,
            "Subtask Id": subtask,
            "connection_id": connection,
            "Model Id": 0,
        },
    }


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

    def test_legacy_composite_heuristic_is_disabled_by_default(self):
        events = [
            json_event(name, 45, 1, 100 + subtask, subtask=subtask)
            for subtask, name in enumerate(("SDMA", "SDMA", "SDMA", "Write Value", "Notify Wait"))
        ]
        events.append(json_event("MEMCPY_ASYNC", 45, 2, 200, duration=2))
        profilers = list(parse_events(events, device_id=0, default_node_id="node0"))
        semantics = list(parse_legacy_block([
            "[HcclTaskSemantic] device_id[0] stream_id[45] task_id[0] semantic_seq[0] profiler_seq[3] "
            "task_kind[sdma] event[copy_start] phase[reduce_scatter_direct] step[0] "
            "user_rank[0] comm_rank[0] rank_size[2]\n",
            "[HcclTaskSemantic] device_id[0] stream_id[45] task_id[2] semantic_seq[1] profiler_seq[5] "
            "task_kind[sdma] event[rx_payload_copy_start] phase[allgather_direct] step[0] "
            "user_rank[0] comm_rank[0] rank_size[2]\n",
        ]))

        rows, stats = merge_records(semantics, profilers)
        matched = [row for row in rows if row["match_status"] == "matched"]

        self.assertEqual(stats["matched"], 1)
        self.assertEqual(stats["unmatched_semantic"], 1)
        self.assertEqual(matched[0]["profiler_task_id"], 2)
        self.assertEqual(matched[0]["match_confidence"], "exact")

        legacy_rows, legacy_stats = merge_records(
            semantics, profilers, allow_legacy_composite_heuristic=True)
        self.assertEqual(legacy_stats["legacy_composite_kind_mismatches"], 1)
        self.assertEqual(
            [row for row in legacy_rows if row["match_status"] == "invalid_heuristic"][0]
            ["subtask_id"],
            3,
        )

    def test_ffts_parent_ctx_correlation_matches_exact_subtask(self):
        events = [
            json_event("Write Value", 45, 1, 100, subtask=8),
            json_event("SDMA", 45, 1, 101, subtask=13),
        ]
        profilers = list(parse_events(events, device_id=0, default_node_id="node0"))
        semantics = list(parse_legacy_block([
            "[HcclTaskSemantic] schema_version[2] device_id[0] stream_id[45] task_id[0] "
            "semantic_seq[0] profiler_seq[6] task_kind[notify_record] event[tx_ack_start] "
            "phase[reduce_scatter_direct] execution_mode[ffts] ffts_ctx_id[8] "
            "graph_instance_id[7]\n",
            "[HcclTaskSemantic] schema_version[2] device_id[0] stream_id[13] task_id[0] "
            "semantic_seq[0] profiler_seq[3] task_kind[reduce_inline] "
            "event[rx_payload_reduce_start] phase[reduce_scatter_direct] execution_mode[ffts] "
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

        self.assertEqual(stats["json_ffts_parent_ctx_matches"], 2)
        self.assertEqual(stats["matched"], 2)
        self.assertEqual({row["subtask_id"] for row in matched}, {8, 13})
        self.assertEqual({row["match_method"] for row in matched}, {"json_ffts_parent_ctx"})
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

    def test_v1_and_invalid_ffts_fields_are_backward_compatible(self):
        semantics = list(parse_legacy_block([
            "[HcclTaskSemantic] schema_version[1] device_id[0] stream_id[45] task_id[2] "
            "task_kind[sdma] event[copy_start] phase[allgather_direct]\n",
            "[HcclTaskSemantic] schema_version[2] device_id[0] stream_id[45] task_id[3] "
            "task_kind[sdma] event[copy_start] phase[allgather_direct] "
            "ffts_ctx_id[4294967295] graph_instance_id[18446744073709551615]\n",
        ]))
        self.assertEqual(semantics[0].schema_version, 1)
        self.assertEqual(semantics[0].ffts_ctx_id, -1)
        self.assertEqual(semantics[0].graph_instance_id, -1)
        self.assertEqual(semantics[1].ffts_ctx_id, -1)
        self.assertEqual(semantics[1].graph_instance_id, -1)

    def test_duplicate_graph_correlation_is_not_used(self):
        profilers = list(parse_events(
            [json_event("Write Value", 45, 1, 100, subtask=8)], 0, "node0"))
        semantics = list(parse_legacy_block([
            "[HcclTaskSemantic] schema_version[2] device_id[0] stream_id[45] task_id[0] "
            "semantic_seq[0] task_kind[notify_record] event[tx_ack_start] "
            "phase[reduce_scatter_direct] execution_mode[ffts] ffts_ctx_id[8] "
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

    def test_validation_gate_counts_only_exact_matches(self):
        rows = [
            {"match_status": "matched", "match_confidence": "exact",
             "duplicate_semantic": "0", "duplicate_profiler": "0"},
            {"match_status": "matched", "match_confidence": "heuristic",
             "duplicate_semantic": "0", "duplicate_profiler": "0"},
        ]
        ok, stats = validate_rows(rows, 75.0)
        self.assertFalse(ok)
        self.assertEqual(stats["match_rate_percent"], 100.0)
        self.assertEqual(stats["exact_match_rate_percent"], 50.0)

    def test_exact_allgather_wins_reused_reduce_scatter_task_id(self):
        profilers = list(parse_events(
            [json_event("MEMCPY_ASYNC", 13, 3, 200, duration=2)], 0, "node0"))
        semantics = list(parse_legacy_block([
            "[HcclTaskSemantic] device_id[0] stream_id[13] task_id[3] semantic_seq[0] profiler_seq[1] "
            "task_kind[sdma] event[copy_start] phase[reduce_scatter_direct] step[0]\n",
            "[HcclTaskSemantic] device_id[0] stream_id[13] task_id[3] semantic_seq[1] profiler_seq[2] "
            "task_kind[sdma] event[copy_start] phase[reduce_scatter_direct] step[1]\n",
            "[HcclTaskSemantic] device_id[0] stream_id[13] task_id[3] semantic_seq[2] profiler_seq[3] "
            "task_kind[sdma] event[copy_start] phase[allgather_direct] step[0]\n",
        ]))

        rows, stats = merge_records(semantics, profilers)

        self.assertEqual(stats["matched"], 1)
        self.assertEqual(stats["unmatched_semantic"], 2)
        self.assertEqual([row for row in rows if row["match_status"] == "matched"][0]["phase"],
                         "allgather_direct")

    def test_host_to_device_flow_id_is_attached(self):
        events = [
            {"name": "HostToDevice9", "ph": "f", "cat": "HostToDevice", "id": "9", "tid": 45,
             "ts": "100"},
            json_event("SDMA", 45, 1, 100, subtask=0),
        ]
        tasks = list(parse_events(events, 0, "node0"))
        self.assertEqual(tasks[0].flow_id, "9")

    def test_plog_dir_loads_all_rank_files(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            for rank in (0, 1):
                path = os.path.join(temp_dir, f"plog-{rank}.log")
                with open(path, "w", encoding="utf-8") as output:
                    output.write(
                        f"[HcclTaskSemantic] device_id[{rank}] stream_id[12] task_id[34] "
                        f"user_rank[{rank}] comm_rank[{rank}] rank_size[2] event[rx_ack_start] "
                        "phase[reduce_scatter_direct] step[0] task_kind[notify_wait]\n"
                    )
            records = parse_plog_inputs(plog_dir=temp_dir)
        self.assertEqual({record.device_id for record in records}, {0, 1})

    def test_submit_ts_and_profiler_seq_are_parsed(self):
        semantics = list(parse_legacy_block([
            "[HcclTaskSemantic] device_id[7] stream_id[45] task_id[0] semantic_seq[0] profiler_seq[3] "
            "submit_ts[1783015731413749] notify_id[99] notify_stage[2] notify_remote_rank[6] "
            "notify_ctx_id[3] task_kind[sdma] event[copy_start] "
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
