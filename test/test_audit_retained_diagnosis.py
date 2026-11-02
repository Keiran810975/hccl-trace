from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest

from hccl.tools.diagnosis.test_source_ranking import root, wait
from . import audit_retained_diagnosis as audit


class RetainedAuditTests(unittest.TestCase):
    def test_requires_one_native_json_payload(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "propagation.html"
            path.write_text('<script id="propagation-data">{"nodes": {}}</script>')
            self.assertEqual(audit.read_propagation(path), {"nodes": {}})
            path.write_text(path.read_text() * 2)
            with self.assertRaises(ValueError):
                audit.read_propagation(path)

    def test_rerank_preserves_input_and_candidate_membership(self):
        roots = [root("small"), root("large", delta=30)]
        data = dict(roots=roots, slow_waits=[wait()], original_candidate_ids=["small", "large"],
                    original_primary_id="small", expected_slow_wait_count=1,
                    retained_slow_wait_count=1, run_id="test")
        before = deepcopy(data)
        result = audit.rerank(data)
        self.assertEqual(data, before)
        self.assertEqual(result["primary_candidate_id"], "large")
        self.assertFalse(result["candidate_membership_changed"])
        self.assertEqual({r["root_id"] for r in result["roots"]}, {"small", "large"})
        data["original_candidate_ids"] = ["small"]
        with self.assertRaises(ValueError):
            audit.rerank(data)

    def test_refuses_incomplete_retained_coverage(self):
        with self.assertRaises(ValueError):
            audit.rerank(dict(expected_slow_wait_count=2, retained_slow_wait_count=1))

    def test_conflicting_wait_facts_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory)
            unresolved = dict(graph_id="w", component="wait_boundary", observed_start_ns=0,
                              observed_stop_ns=50, delta_ns="30")
            report = dict(schema_version=2, quality=dict(pipeline_passed=True),
                          unresolved_observations=[unresolved])
            (target / "root_causes.json").write_text(json.dumps(report))
            model = dict(candidates=[], nodes=dict(w=dict(task_kind="notify_wait", start_ns="0", stop_ns="50",
                         comparison=dict(duration_slow=True, delta_ns="31", reference_count=5))))
            (target / "propagation.html").write_text('<script id="propagation-data">' + json.dumps(model) + '</script>')
            with self.assertRaises(ValueError):
                audit.retained_observations(target)


if __name__ == "__main__":
    unittest.main()
