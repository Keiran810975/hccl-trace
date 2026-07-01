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
else:
    from .merge_timeline import merge_records
    from .parse_msprof import parse_task_time_rows
    from .parse_plog import parse_legacy_block
    from .validate_trace import validate_rows


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


if __name__ == "__main__":
    unittest.main()