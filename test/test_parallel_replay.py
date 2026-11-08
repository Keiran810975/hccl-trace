from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from test.archive.diagnosis_20261108.evaluate_parallel_sources import evaluate, overlap
from test.refine_multinode_sources import digest


class ParallelReplayTests(unittest.TestCase):
    def test_overlap_needs_same_node_rank_and_positive_not_touching_time(self):
        task = dict(node_id="a", user_rank=4, observed_start_ns=100, observed_stop_ns=120)
        self.assertEqual(overlap(task, [dict(node_id="a", user_rank=4, start_ns=120, stop_ns=200)]), 0)
        self.assertEqual(overlap(task, [dict(node_id="b", user_rank=4, start_ns=100, stop_ns=200)]), 0)
        self.assertEqual(overlap(task, [dict(node_id="a", user_rank=5, start_ns=100, stop_ns=200)]), 0)
        self.assertEqual(overlap(task, [dict(node_id="a", user_rank=4, start_ns=110, stop_ns=200)]), 10)

    def test_evaluation_handles_span_filtered_empty_units_and_never_counts_no_candidates_as_success(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "live/hccl-diagnose-node03-20261106-1002").mkdir(parents=True)
            folder = root / "replays/1002"
            folder.mkdir(parents=True)
            target = folder / "selection.json"
            target.write_text(json.dumps(dict(candidates=[], inputs=dict(archive_sha256="archive"),
                call_admission=[dict(admitted=True, node_id="a", user_rank=4, operation_scope="filtered")])))
            (folder / "sealed.json").write_text(json.dumps(dict(truth_accessed=False,
                selection_sha256=digest(target), consumer_sha256={"hccl/tools/diagnosis/parallel_sources.py": "policy"})))
            old = dict(windows=[], injection=dict(kind="copy_contention", target_rank=4),
                candidate_hit_count=0, candidate_count=3, any_candidate_hit=False)
            with patch("test.archive.diagnosis_20261108.evaluate_parallel_sources.original_evaluation", return_value=old):
                result = evaluate(root / "live", root / "replays", root / "summary.json")
            self.assertFalse(result["cases"][0]["any_hit"])
            self.assertIsNone(result["cases"][0]["candidate_overlap_fraction"])
            self.assertEqual(result["excluded_cases"], [])
            target.write_text("{}")
            with patch("test.archive.diagnosis_20261108.evaluate_parallel_sources.original_evaluation") as truth:
                with self.assertRaises(ValueError):
                    evaluate(root / "live", root / "replays", root / "bad.json")
                truth.assert_not_called()


if __name__ == "__main__":
    unittest.main()
