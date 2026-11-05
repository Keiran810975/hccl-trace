from __future__ import annotations

import csv
import io
import hashlib
import json
from pathlib import Path
import tarfile
import tempfile
import unittest

from .audit_multinode_dual import audit, collect, region, HashedReader, outgoing_effect


class EffectAuditTests(unittest.TestCase):
    def test_same_rank_positive_overlap_excludes_touching_boundaries(self):
        windows = [dict(node_id="n", user_rank=4, start_ns=10, stop_ns=20)]
        self.assertEqual(region("n", 4, 8, 11, windows), "inside_owner_window")
        self.assertEqual(region("n", 4, 0, 10, windows), "outside_owner_window")
        self.assertEqual(region("n", 4, 20, 21, windows), "outside_owner_window")
        self.assertEqual(region("n", 5, 10, 20, windows), "other_ranks")
        self.assertEqual(region("other", 4, 10, 20, windows), "other_ranks")

    def test_csv_statistics_keep_measurement_units_and_history_separate(self):
        keys = ["reference_count", "task_kind", "node_id", "user_rank", "observed_start_ns", "observed_stop_ns",
                "duration_ns", "reference_mean_ns", "duration_slow"]
        stream = io.StringIO()
        writer = csv.DictWriter(stream, keys)
        writer.writeheader()
        base = dict(zip(keys, [5, "sdma", "n", 4, 11, 19, 30, 10, True]))
        writer.writerow(base)
        writer.writerow(dict(base, reference_count=4))
        writer.writerow(dict(base, task_kind="kernel_mix_aic"))
        writer.writerow(dict(base, observed_start_ns=20, observed_stop_ns=28, duration_ns=8, duration_slow=False))
        stream.seek(0)
        result = collect(stream, [dict(node_id="n", user_rank=4, start_ns=10, stop_ns=20)])
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0]["comparable_count"], 1)
        self.assertEqual(result[0]["mean_increase_percent"], 200)
        self.assertEqual(result[1]["mean_increase_percent"], -20)

    def test_hashing_reader_does_not_change_csv_bytes(self):
        data = b"a,b\n1,2\n"
        source = HashedReader(io.BytesIO(data))
        self.assertEqual(io.BufferedReader(source).read(), data)
        self.assertEqual(source.digest.hexdigest(), hashlib.sha256(data).hexdigest())

    def test_archive_facts_and_evaluation_are_both_verified(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "node0").mkdir()
            expected = dict(case_id="sample", windows=[], candidate_hit_count=0, candidate_count=1)
            prefix = "report.debug/analysis/sample/"
            entries = {prefix + "rolling/task_comparison.csv": b"reference_count,task_kind\n",
                       prefix + "cross_node/segments.csv": b"reference_count\n",
                       "evaluation.json": json.dumps(expected).encode()}
            manifest = dict(files={name: dict(size=len(data), sha256=hashlib.sha256(data).hexdigest())
                                   for name, data in entries.items()})
            (root / "node0/manifest.json").write_text(json.dumps(manifest))
            (root / "node0/verified.json").write_text(json.dumps(dict(file_hashes_verified=True,
                manifest_sha256=hashlib.sha256(json.dumps(manifest, sort_keys=True).encode()).hexdigest())))
            with tarfile.open(root / "node0/replay.tar.gz", "w:gz") as target:
                for name, data in entries.items():
                    member = tarfile.TarInfo(name)
                    member.size = len(data)
                    target.addfile(member, io.BytesIO(data))
            result = audit(root, expected)
            self.assertEqual(set(result["verified_fact_files"]), set(entries))
            with self.assertRaisesRegex(ValueError, "evaluation"):
                audit(root, dict(expected, candidate_hit_count=1))

    def test_outgoing_effect_uses_actual_iterations_and_sender_not_receiver(self):
        rows = [dict(sender_node_id="n0", sender_rank=0, iteration=i, increase_percent=100 if i == 33 else 0)
                for i in (25, 32, 33)]
        rows.append(dict(sender_node_id="n3", sender_rank=4, iteration=33, increase_percent=900))
        control = dict(applied_verified=True, restored_verified=True, foreground_path_verified=True,
                       measurement_window=dict(completed_iterations=[33]))
        result = outgoing_effect(rows, [dict(node_id="n0", user_rank=0)], control)
        self.assertEqual(result["inside_verified_full_iterations"]["mean_increase_percent"], 100)
        self.assertEqual(result["outside_verified_full_iterations"]["count"], 2)
        with self.assertRaisesRegex(ValueError, "coverage"):
            outgoing_effect([], [dict(node_id="n0", user_rank=0)], control)
