from __future__ import annotations

import json
from pathlib import Path
import sqlite3
import tempfile
import unittest

from test.node03_evaluate import evaluate


class EvaluateTests(unittest.TestCase):
    def write(self, path, value):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value))

    def test_only_same_rank_positive_overlap_counts_and_truth_is_not_analyzer_input(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.write(root / "input/case.json", dict(case_id="delay", injection=dict(kind="progress_delay", target_rank=4)))
            data = root / "peer-preflight/gpt-output"
            self.write(data / "runtime/rank-4.json", dict(runtime_device_id=1))
            private = data / "private/rank-4.jsonl"
            private.parent.mkdir()
            private.write_text("\n".join(json.dumps(row) for row in (
                dict(event="injection_start", clocks=dict(raw_ns=1000)),
                dict(event="injection_stop", actual_hit=True, clocks=dict(raw_ns=1100)))))
            profiler = root / "capture/nodes/node3/msprof/p"
            self.write(profiler / "host/start_info", dict(collectionTimeBegin=1000, clockMonotonicRaw=100))
            with sqlite3.connect(profiler / "msprof_1.db") as db:
                db.execute("CREATE TABLE TASK(deviceId INTEGER)")
                db.execute("INSERT INTO TASK VALUES(1)")
            candidate = dict(id="hit", node_id="run/node3", user_rank=4, observed_start_ns=1000950, observed_stop_ns=1000990)
            other = dict(candidate, id="wrong-rank", user_rank=5)
            boundary = dict(candidate, id="only-touches", observed_start_ns=1001000, observed_stop_ns=1001100)
            report = dict(run_id="run", quality=dict(pipeline_passed=True, rank_count=8),
                          diagnosis_status="candidates", candidates=[other, candidate, boundary],
                          primary_candidate_id="wrong-rank", propagation=dict(chain_count=2))
            self.write(root / "report/root_causes.json", report)
            result = evaluate(root)
            self.assertEqual(result["hit_candidate_ids"], ["hit"])
            self.assertFalse(result["primary_hit"])
            self.assertAlmostEqual(result["candidate_hit_fraction"], 1 / 3)
            self.assertEqual(json.loads((root / "report/root_causes.json").read_text()), report)

    def test_normal_counts_candidates_as_false_positives_without_injection_window(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.write(root / "input/case.json", dict(case_id="normal", injection=dict(kind="normal")))
            self.write(root / "report/root_causes.json", dict(run_id="run", quality=dict(pipeline_passed=True, rank_count=8),
                candidates=[], primary_candidate_id=None, diagnosis_status="no_candidates", propagation=dict(chain_count=0)))
            result = evaluate(root)
            self.assertEqual(result["normal_false_positive_candidate_count"], 0)
            self.assertEqual(result["windows"], [])

    def test_injection_window_uses_cann_offset_even_without_network_alignment(self):
        from fractions import Fraction

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.write(root / "input/case.json", dict(case_id="delay", injection=dict(kind="progress_delay", target_rank=4)))
            data = root / "peer-preflight/gpt-output"
            self.write(data / "runtime/rank-4.json", dict(runtime_device_id=1))
            p0, r0, delta = 1000000, 100, 1000000000
            r1 = r0 + 1000100000
            public = root / "capture/nodes/node3/calls/rank-4.jsonl"
            header = dict(event="runtime", schema_version=1, run_id="run", node_id="node3", user_rank=4, device_id=1)
            samples = [dict(before=dict(unix_ns=p0 + round(Fraction(delta * i, 15)),
                        raw_ns=r0 + round(Fraction((r1 - r0) * i, 15)))) for i in range(16)]
            public.parent.mkdir(parents=True)
            public.write_text("\n".join(json.dumps(row) for row in [header] + samples))
            private = data / "private/rank-4.jsonl"
            private.parent.mkdir()
            begin = r0 + (r1 - r0) // 2
            private.write_text("\n".join(json.dumps(row) for row in (
                dict(event="injection_start", clocks=dict(raw_ns=begin)),
                dict(event="injection_stop", actual_hit=True, clocks=dict(raw_ns=begin + 100)))))
            profiler = root / "capture/nodes/node3/msprof/p"
            self.write(profiler / "host/start_info", dict(collectionTimeBegin=p0 // 1000, clockMonotonicRaw=r0))
            self.write(profiler / "host/end_info", dict(collectionTimeEnd=(p0 + delta) // 1000, clockMonotonicRaw=r1))
            with sqlite3.connect(profiler / "msprof_1.db") as db:
                db.execute("CREATE TABLE TASK(deviceId INTEGER)")
                db.execute("INSERT INTO TASK VALUES(1)")
            candidate = dict(id="hit", node_id="run/node3", user_rank=4,
                             observed_start_ns=p0 + begin - r0 + 10, observed_stop_ns=p0 + begin - r0 + 90)
            wrong_clock = dict(candidate, id="realtime-only",
                               observed_start_ns=p0 + delta // 2 + 10, observed_stop_ns=p0 + delta // 2 + 90)
            self.write(root / "report/root_causes.json", dict(run_id="run",
                quality=dict(pipeline_passed=True, rank_count=8, clock_alignment_available=False),
                diagnosis_status="candidates", candidates=[candidate, wrong_clock], primary_candidate_id="hit", propagation=dict(chain_count=1)))
            result = evaluate(root)
            self.assertEqual(result["hit_candidate_ids"], ["hit"])
            self.assertEqual(result["windows"][0]["clock_conversion"], "cann_start_offset")
            self.assertEqual(result["windows"][0]["start_ns"], p0 + begin - r0)
            header["user_rank"] = 5
            public.write_text("\n".join(json.dumps(row) for row in [header] + samples))
            with self.assertRaisesRegex(ValueError, "identity mismatch"):
                evaluate(root)


if __name__ == "__main__":
    unittest.main()
