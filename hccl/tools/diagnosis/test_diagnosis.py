#!/usr/bin/env python3
"""Unit tests for HCCL step trace diagnosis helpers."""

from __future__ import annotations

import csv
import os
import sys
import unittest

if __package__ in (None, ""):
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from diagnosis.merge_timeline import merge_records
    from diagnosis.parse_msprof import parse_task_time_rows
    from diagnosis.parse_plog import parse_legacy_block
    from diagnosis.validate_trace import validate_rows
    from diagnosis.visualize_dependency_graph import build_edges, build_nodes, infer_rank_size
else:
    from .merge_timeline import merge_records
    from .parse_msprof import parse_task_time_rows
    from .parse_plog import parse_legacy_block
    from .validate_trace import validate_rows
    from .visualize_dependency_graph import build_edges, build_nodes, infer_rank_size


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


if __name__ == "__main__":
    unittest.main()
