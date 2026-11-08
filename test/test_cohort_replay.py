from __future__ import annotations

import gzip
import json
from pathlib import Path
import tempfile
import unittest

from hccl.tools.diagnosis.local_slow_clusters import build_clusters
from hccl.tools.diagnosis.test_local_slow_clusters import fork
from test.refine_multinode_sources import digest
from test.archive.diagnosis_20261108.replay_cohort_sources import replay


class CohortReplayTests(unittest.TestCase):
    def fixture(self, root):
        cache = root / "cache"
        cache.mkdir()
        tasks, edges = fork()
        for name, rows in (("tasks.jsonl.gz", tasks), ("edges.jsonl.gz", edges)):
            with gzip.open(cache / name, "wt") as out:
                for row in rows:
                    out.write(json.dumps(row) + "\n")
        clusters = build_clusters(tasks, edges)[1]
        original = dict(candidates=[], source_region=clusters[0],
            proposals=[dict(proposal_id=c["region_id"], mechanism="communication_execution_growth", score="1") for c in clusters])
        (cache / "source_selection.json").write_text(json.dumps(original))
        (cache / "clock_alignment.json").write_text("null")
        names = ("tasks.jsonl.gz", "edges.jsonl.gz", "source_selection.json", "clock_alignment.json")
        (cache / "verified.json").write_text(json.dumps(dict(truth_accessed=False,
            original_archive_sha256="fixture", files={n:digest(cache/n) for n in names})))
        return cache

    def test_public_replay_preserves_cluster_and_seals_before_truth(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            value = replay(self.fixture(root), root / "result")
            self.assertEqual(len(value["candidates"]), 3)
            self.assertEqual(value["cluster_selection"]["selected_cluster_count"], 1)
            self.assertTrue(value["original_cluster_ids_identical"])
            seal = json.loads((root / "result/sealed.json").read_text())
            self.assertFalse(seal["truth_accessed"])
            self.assertEqual(seal["selection_sha256"], digest(root / "result/selection.json"))
            with self.assertRaises(FileExistsError):
                replay(root / "cache", root / "result")

    def test_changed_public_cache_is_never_published(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            cache = self.fixture(root)
            (cache / "clock_alignment.json").write_text("{}")
            with self.assertRaises(ValueError):
                replay(cache, root / "result")
            self.assertFalse((root / "result").exists())


if __name__ == "__main__":
    unittest.main()
