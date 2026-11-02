from __future__ import annotations

import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from .replay_significant_regions import JsonReader
from .evaluate_significant_regions import evaluate


class RegionReplayTests(unittest.TestCase):
    def test_stream_reader_handles_root_keys_and_array_values(self):
        value = dict(metadata={"x": [1, 2]}, tasks=[{"key": "汉字", "number": 123456}, {"key": "z"}])
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/"report.json"
            path.write_text(json.dumps(value, ensure_ascii=False))
            reader = JsonReader(path)
            original = reader.fill
            def tiny_fill():
                reader.buffer = reader.buffer[reader.offset:]
                reader.offset = 0
                chunk = reader.stream.read(3)
                reader.buffer += chunk
                return bool(chunk)
            reader.fill = tiny_fill
            self.assertEqual(list(reader.entries()), [("metadata", value["metadata"]),
                ("tasks", value["tasks"][0]), ("tasks", value["tasks"][1])])

    def test_independent_evaluation_uses_positive_overlap_and_same_rank(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            base = dict(status="unexplained_execution_growth", candidate_id="x", node_id="node", user_rank=0,
                graph_id="x", stream_id=1, task_id=1, iteration=5, task_kind="sdma")
            report = dict(candidates=[dict(base, observed_start_ns=10, observed_stop_ns=20),
                dict(base, observed_start_ns=20, observed_stop_ns=30),
                dict(base, observed_start_ns=11, observed_stop_ns=19, user_rank=1)], chains=[])
            path = root/"report.json"
            path.write_text(json.dumps(report))
            (root/"sealed.json").write_text(json.dumps(dict(report_sha256=hashlib.sha256(path.read_bytes()).hexdigest(), truth_accessed=False)))
            truth = root/"truth.json"
            truth.write_text(json.dumps(dict(strong_copy=dict(profiler_host_envelope_ns=[10, 20]))))
            result = evaluate(path, truth, "node", 0)
            self.assertEqual(result["all_candidates"], dict(hits=1, total=3, precision=1/3))
            path.write_text("{}")
            with self.assertRaises(ValueError):
                evaluate(path, truth, "node", 0)


if __name__ == "__main__":
    unittest.main()
