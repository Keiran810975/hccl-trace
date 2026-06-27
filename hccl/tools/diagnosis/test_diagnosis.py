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


if __name__ == "__main__":
    unittest.main()
