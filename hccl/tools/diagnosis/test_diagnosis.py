#!/usr/bin/env python3
"""Unit tests for HCCL step trace diagnosis helpers."""

from __future__ import annotations

import csv
import os
import sys
import tempfile
import unittest

if __package__ in (None, ""):
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from diagnosis.merge_timeline import merge_records, parse_plog_inputs, parse_task_time_inputs
    from diagnosis.parse_msprof import parse_task_time_rows
    from diagnosis.parse_plog import parse_legacy_block
    from diagnosis.validate_trace import validate_rows
    from diagnosis.visualize_timeline import assign_time_slots
    from diagnosis.visualize_dependency_graph import apply_rank_field, assign_positions, build_edges, build_nodes, compact_dependency_rows, infer_rank_size
else:
    from .merge_timeline import merge_records, parse_plog_inputs, parse_task_time_inputs
    from .parse_msprof import parse_task_time_rows
    from .parse_plog import parse_legacy_block
    from .validate_trace import validate_rows
    from .visualize_timeline import assign_time_slots
    from .visualize_dependency_graph import apply_rank_field, assign_positions, build_edges, build_nodes, compact_dependency_rows, infer_rank_size


class DiagnosisToolTest(unittest.TestCase):
    def test_merge_sample_records(self):
        fixture_dir = os.path.join(os.path.dirname(__file__), "fixtures")
        with open(os.path.join(fixture_dir, "sample.plog"), "r", encoding="utf-8") as plog:
            semantics = list(parse_legacy_block(plog))
        with open(os.path.join(fixture_dir, "task_time.csv"), "r", encoding="utf-8-sig", newline="") as task_time:
            profilers = list(parse_task_time_rows(csv.DictReader(task_time), default_node_id="node0"))

        rows, stats = merge_records(semantics, profilers)
        self.assertEqual(stats["semantic_total"], 2)
        self.assertEqual(stats["profiler_total"], 2)
        self.assertEqual(stats["matched"], 2)
        self.assertEqual(stats["duplicate_semantic_keys"], 0)
        self.assertEqual(stats["duplicate_profiler_keys"], 0)
        self.assertTrue(all(row["match_status"] == "matched" for row in rows))
        self.assertEqual(semantics[0].pid, 502444)
        self.assertEqual(semantics[0].device_id, 0)
        self.assertEqual(semantics[0].task_kind, "notify_wait")

        ok, validate_stats = validate_rows([{key: str(value) for key, value in row.items()} for row in rows], 95.0)
        self.assertTrue(ok)
        self.assertEqual(validate_stats["match_rate_percent"], 100.0)

    def test_task_time_dir_loads_all_task_time_csv_files(self):
        fixture_dir = os.path.join(os.path.dirname(__file__), "fixtures")
        tasks = parse_task_time_inputs(task_time_dir=fixture_dir, node_id="node0")
        self.assertEqual(len(tasks), 2)
        self.assertEqual({task.device_id for task in tasks}, {0})

    def test_plog_dir_loads_all_plog_files(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            for rank in (0, 1):
                path = os.path.join(temp_dir, f"plog-{rank}.log")
                with open(path, "w", encoding="utf-8") as output:
                    output.write(
                        "[INFO] HCCL(502444,python):2026-01-01-00:00:00.000.000 "
                        "[task_semantic_trace.cc:126] [502444][HcclTaskSemantic] "
                        f"device_id[{rank}] stream_id[12] task_id[34] task_kind[notify_wait] "
                        f"event[rx_ack_start] phase[reduce_scatter_direct] step[0] rank[{rank}] ranksize[2] "
                        "slice[0] semantic[link_rx_ack]\n"
                    )

            records = parse_plog_inputs(plog_dir=temp_dir)

        self.assertEqual(len(records), 2)
        self.assertEqual({record.device_id for record in records}, {0, 1})

    def test_semantic_seq_matches_profiler_stream_order(self):
        semantics = list(parse_legacy_block([
            "[HcclTaskSemantic] device_id[0] stream_id[12] task_id[0] semantic_seq[0] task_kind[notify_wait] "
            "event[rx_ack_start] phase[reduce_scatter_direct] step[0] rank[0] ranksize[2] "
            "slice[0] semantic[link_rx_ack]\n",
            "[HcclTaskSemantic] device_id[0] stream_id[12] task_id[0] semantic_seq[1] task_kind[notify_wait] "
            "event[rx_ack_start] phase[reduce_scatter_direct] step[1] rank[0] ranksize[2] "
            "slice[1] semantic[link_rx_ack]\n",
        ]))
        profilers = list(parse_task_time_rows([
            {"Device_id": "0", "stream_id": "12", "task_id": "100", "kernel_type": "NOTIFY_WAIT", "task_start(us)": "10", "task_stop(us)": "11", "task_time(us)": "1"},
            {"Device_id": "0", "stream_id": "12", "task_id": "101", "kernel_type": "NOTIFY_WAIT", "task_start(us)": "12", "task_stop(us)": "13", "task_time(us)": "1"},
        ], default_node_id="node0"))

        rows, stats = merge_records(semantics, profilers)

        self.assertEqual(stats["matched"], 2)
        self.assertEqual(stats["semantic_seq_matches"], 2)
        self.assertEqual(stats["duplicate_semantic_keys"], 0)
        self.assertEqual([row["task_id"] for row in rows], [0, 0])
        self.assertEqual([row["semantic_seq"] for row in rows], [0, 1])
        self.assertEqual([row["task_start"] for row in rows], ["10", "12"])
    def test_semantic_seq_miss_does_not_fall_back_to_task_id(self):
        semantics = list(parse_legacy_block([
            "[HcclTaskSemantic] device_id[0] stream_id[12] task_id[100] semantic_seq[9] task_kind[notify_wait] "
            "event[rx_ack_start] phase[reduce_scatter_direct] step[0] rank[0] ranksize[2] "
            "slice[0] semantic[link_rx_ack]\n",
        ]))
        profilers = list(parse_task_time_rows([
            {"Device_id": "0", "stream_id": "12", "task_id": "100", "kernel_type": "NOTIFY_WAIT", "task_start(us)": "10", "task_stop(us)": "11", "task_time(us)": "1"},
        ], default_node_id="node0"))

        rows, stats = merge_records(semantics, profilers)

        self.assertEqual(stats["matched"], 0)
        self.assertEqual(stats["semantic_seq_unmatched"], 1)
        self.assertEqual(stats["unmatched_semantic"], 1)
        self.assertEqual(rows[0]["match_status"], "unmatched_semantic")
    def test_rank_as_device_fallback_is_explicit(self):
        semantics = list(parse_legacy_block([
            "[HcclTaskSemantic] stream_id[12] task_id[34] task_kind[notify_wait] "
            "event[rx_ack_start] phase[reduce_scatter_direct] step[0] rank[0] ranksize[8] "
            "slice[7] semantic[link_rx_ack]\n"
        ]))
        profilers = list(parse_task_time_rows([
            {
                "Device_id": "0",
                "stream_id": "12",
                "task_id": "34",
                "kernel_type": "NOTIFY_WAIT",
                "task_start(us)": "1000",
                "task_stop(us)": "1004",
                "task_time(us)": "4",
            }
        ], default_node_id="node0"))

        strict_rows, strict_stats = merge_records(semantics, profilers)
        self.assertEqual(strict_stats["matched"], 0)
        self.assertEqual(strict_stats["semantic_missing_device_id"], 1)
        self.assertEqual(strict_rows[0]["match_status"], "unmatched_semantic")

        fallback_rows, fallback_stats = merge_records(semantics, profilers, rank_as_device_fallback=True)
        self.assertEqual(fallback_stats["matched"], 1)
        self.assertEqual(fallback_stats["rank_device_fallback_matches"], 1)
        self.assertEqual(fallback_rows[0]["match_status"], "matched")

    def test_duplicate_semantic_keys_are_deduped_by_default(self):
        semantics = list(parse_legacy_block([
            "[HcclTaskSemantic] device_id[0] stream_id[12] task_id[34] task_kind[sdma] "
            "event[allreduce_start] phase[allreduce_executor] step[0] rank[0] ranksize[8] "
            "slice[0] semantic[allreduce_executor]\n",
            "[HcclTaskSemantic] device_id[0] stream_id[12] task_id[34] task_kind[sdma] "
            "event[copy_start] phase[reduce_scatter_direct] step[0] rank[0] ranksize[8] "
            "slice[6] semantic[hccl_local_copy]\n",
        ]))
        profilers = list(parse_task_time_rows([
            {
                "Device_id": "0",
                "stream_id": "12",
                "task_id": "34",
                "kernel_type": "SDMA",
                "task_start(us)": "1000",
                "task_stop(us)": "1008",
                "task_time(us)": "8",
            }
        ], default_node_id="node0"))

        rows, stats = merge_records(semantics, profilers)
        self.assertEqual(stats["duplicate_semantic_keys_input"], 1)
        self.assertEqual(stats["deduped_semantic_rows"], 1)
        self.assertEqual(stats["duplicate_semantic_keys"], 0)
        self.assertEqual(stats["matched"], 1)
        self.assertEqual(rows[0]["event"], "copy_start")


    def test_dependency_edges_are_inferred_from_merged_rows(self):
        rows = []

        def row(rank, phase, step, event, start):
            phase_group = "reduce_scatter" if phase.startswith("reduce_scatter") else "allgather"
            phase_order = 0 if phase_group == "reduce_scatter" else 1
            event_order = {
                "rx_ack_start": 0,
                "rx_data_signal_start": 2,
                "rx_payload_reduce_start": 4,
                "rx_payload_copy_start": 5,
            }[event]
            return {
                "node_id": "node0",
                "device_id": str(rank),
                "user_rank": str(rank),
                "rank_size": "2",
                "stream_id": "10",
                "task_id": str(100 + rank * 10 + step * 3 + event_order),
                "phase": phase,
                "event": event,
                "semantic": event,
                "step": str(step),
                "slice": "0",
                "_source_row": len(rows),
                "_phase_group": phase_group,
                "_phase_order": phase_order,
                "_event_order": event_order,
                "_node_id": "node0",
                "_device_id": rank,
                "_rank": rank,
                "_rank_size": 2,
                "_stream_id": 10,
                "_task_id": 100 + rank * 10 + step * 3 + event_order,
                "_step": step,
                "_slice": 0,
                "_start": float(start),
                "_stop": float(start + 1),
                "_duration": 1.0,
            }

        rows.append(row(0, "reduce_scatter_direct", 0, "rx_ack_start", 0))
        rows.append(row(0, "reduce_scatter_direct", 0, "rx_data_signal_start", 1))
        rows.append(row(0, "reduce_scatter_direct", 0, "rx_payload_reduce_start", 2))
        rows.append(row(0, "reduce_scatter_direct", 1, "rx_payload_reduce_start", 3))
        rows.append(row(1, "reduce_scatter_direct", 1, "rx_ack_start", 4))
        rows.append(row(1, "reduce_scatter_direct", 1, "rx_data_signal_start", 5))
        rows.append(row(1, "reduce_scatter_direct", 1, "rx_payload_reduce_start", 6))
        rows.append(row(0, "allgather_direct", 0, "rx_payload_copy_start", 7))

        build_nodes(rows)
        edges = build_edges(
            rows,
            ("same_rank_sequence", "right_neighbor_ack_dep", "upstream_data_signal_dep", "same_rank_step", "upstream_prev_step", "phase_bridge", "signal_payload"),
            infer_rank_size(rows),
            "previous",
        )
        edge_kinds = {edge["kind"] for edge in edges}
        self.assertIn("same_rank_sequence", edge_kinds)
        self.assertIn("right_neighbor_ack_dep", edge_kinds)
        self.assertIn("upstream_data_signal_dep", edge_kinds)
        self.assertIn("same_rank_step", edge_kinds)
        self.assertIn("upstream_prev_step", edge_kinds)
        self.assertIn("phase_bridge", edge_kinds)
        self.assertIn("signal_payload", edge_kinds)


    def test_dependency_rank_auto_uses_device_when_user_rank_collapses(self):
        rows = []
        for device_id in (0, 1):
            rows.append({
                "node_id": "node0",
                "device_id": str(device_id),
                "user_rank": "3",
                "rank_size": "8",
                "stream_id": "10",
                "task_id": str(100 + device_id),
                "phase": "reduce_scatter_direct",
                "event": "rx_payload_reduce_start",
                "semantic": "rx_payload_reduce_start",
                "step": "0",
                "slice": "0",
                "_source_row": device_id,
                "_phase_group": "reduce_scatter",
                "_phase_order": 0,
                "_event_order": 4,
                "_node_id": "node0",
                "_device_id": device_id,
                "_user_rank": 3,
                "_rank": 3,
                "_rank_size": 8,
                "_stream_id": 10,
                "_task_id": 100 + device_id,
                "_step": 0,
                "_slice": 0,
                "_start": float(device_id),
                "_stop": float(device_id + 1),
                "_duration": 1.0,
            })

        selected = apply_rank_field(rows, "auto")
        self.assertEqual(selected, "device_id")
        self.assertEqual({row["_rank"] for row in rows}, {0, 1})

    def test_dependency_layout_keeps_nodes_inside_column(self):
        rows = []
        for index in range(3):
            rows.append({
                "_graph_id": f"n{index}",
                "_rank": 0,
                "_phase_group": "reduce_scatter",
                "_phase_order": 0,
                "_step": 0,
                "_event_order": index,
                "_slice": index,
                "_stream_id": 10,
                "_start": float(index),
                "_task_id": index,
            })

        positions, _columns, _ranks, _rank_y, _rank_heights = assign_positions(rows, 130, 94, 40)
        left = 180
        col_width = 130
        for x, _y in positions.values():
            self.assertGreaterEqual(x, left)
            self.assertLessEqual(x + 40, left + col_width)


    def test_timeline_time_layout_stacks_overlapping_tasks(self):
        def row(index, start, stop):
            return {
                "_node_id": "node0",
                "_device_id": 0,
                "_rank": 0,
                "_stream_id": 10,
                "_task_id": index,
                "_phase": "reduce_scatter_direct",
                "_step": 0,
                "_event": "rx_payload_reduce_start",
                "_slice": index,
                "_start": start,
                "_stop": stop,
            }

        rows = [row(0, 0.0, 10.0), row(1, 5.0, 12.0), row(2, 12.0, 14.0)]
        slot_counts = assign_time_slots(rows)
        self.assertEqual(slot_counts[("node0", 0, 0, 10)], 2)
        self.assertEqual(rows[0]["_time_slot"], 0)
        self.assertEqual(rows[1]["_time_slot"], 1)
        self.assertEqual(rows[2]["_time_slot"], 0)

    def test_dependency_compact_rows_keep_one_payload_per_step(self):
        rows = []
        for index in range(3):
            rows.append({
                "event": "rx_payload_reduce_start",
                "_source_row": index,
                "_phase_group": "reduce_scatter",
                "_phase_order": 0,
                "_event_order": 4,
                "_rank": 0,
                "_step": 0,
                "_slice": index,
                "_stream_id": 10,
                "_start": float(index),
                "_task_id": index,
            })

        compact = compact_dependency_rows(rows)
        self.assertEqual(len(compact), 1)
        self.assertEqual(compact[0]["_slice"], 0)
if __name__ == "__main__":
    unittest.main()
