from __future__ import annotations

from copy import deepcopy
from decimal import Decimal
import unittest

from . import rolling_diagnosis as rolling
from .test_source_events import capture
from .task_classifier import INTERNAL
from .source_propagation import build_report
from .source_propagation_view import build_view_model


class CompletionSourceTests(unittest.TestCase):
    def without_wait_growth(self):
        rows, edges, coords, _ = capture(execution_delay=True)
        for i in range(6):
            record, wait, tail = rows[i * 4 + 1:i * 4 + 4]
            start = record["_stop"] + 1
            wait.update(_start=start, _stop=start + 1, _duration=1,
                        _start_order=Decimal(str(start)), _stop_order=Decimal(str(start + 1)))
            tail.update(_start=start + 1, _stop=start + 1.2,
                        _start_order=Decimal(str(start + 1)), _stop_order=Decimal(str(start + 1.2)))
        return rows, edges, coords

    def test_execution_can_be_retained_without_slow_wait_with_completion_evidence(self):
        rows, edges, coords = self.without_wait_growth()
        old = rolling.analyze(rows, edges, coords)
        new = rolling.analyze(rows, edges, coords, rolling.RollingOptions(completion_fallback=True, wait_slowdown_factor="1.1"))
        self.assertIsNone(old["primary_source_candidate_id"])
        root = next(r for r in new["root_causes"] if r["root_id"] == new["primary_source_candidate_id"])
        self.assertEqual(root["status"], "local_completion_supported_candidate")
        self.assertEqual(root["diagnosis_category"], INTERNAL)
        self.assertFalse(root["affected_wait_graph_ids"])
        self.assertTrue(root["local_completion_evidence"]["edge_ids"])
        exported = build_report(rows, edges, [root], new["tasks"])
        self.assertEqual(exported["summary"]["chain_count"], 0)
        proof = exported["candidates"][0]["completion_path"]
        self.assertTrue(proof["path_complete"])
        self.assertFalse(proof["slow_wait_propagation_claimed"])
        self.assertIn(proof["node_ids"][-1], exported["nodes"])
        self.assertEqual(len(build_view_model(exported)["candidates"]), 1)

    def test_slack_and_missing_paths_do_not_promote_every_isolated_task(self):
        rows, edges, coords = self.without_wait_growth()
        for i in range(6):
            extra = deepcopy(rows[i * 4])
            extra.update(_graph_id="independent-{}".format(i), _stream_id=99, event="independent_copy",
                         _start=i * 1000, _stop=i * 1000 + 200, _duration=200,
                         _start_order=Decimal(i * 1000), _stop_order=Decimal(i * 1000 + 200))
            rows.append(extra)
        report = rolling.analyze(rows, edges, coords, rolling.RollingOptions(completion_fallback=True))
        self.assertIsNone(report["primary_source_candidate_id"])
        rows, edges, coords = self.without_wait_growth()
        edges = [edge for edge in edges if not (edge["src"] == "i5p0" and edge["dst"] == "i5p1")]
        report = rolling.analyze(rows, edges, coords, rolling.RollingOptions(completion_fallback=True))
        self.assertIsNone(report["primary_source_candidate_id"])
