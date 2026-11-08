from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from test.archive.diagnosis_20261108.adopt_cluster_top1 import adopt
from test.refine_multinode_sources import digest


class StableTop1ReplayTests(unittest.TestCase):
    def fixture(self, root):
        cache = root / "cache"
        cache.mkdir()
        original = dict(policy="multinode_dual_v2", candidates=[dict(root_id="root", graph_id="task")],
            chains=[], options={}, summary=dict(candidate_count=1), limits=[], selected_mechanism="communication_execution_growth",
            primary_proposal=dict(proposal_id="cluster", score="2"),
            source_region=dict(region_id="cluster", preliminary_graph_ids=["task"]))
        source = cache / "source_selection.json"
        source.write_text(json.dumps(original))
        proof = dict(truth_accessed=False, original_archive_sha256="archive",
                     files={source.name: digest(source)})
        (cache / "verified.json").write_text(json.dumps(proof))
        return cache, original, proof

    def test_original_members_and_score_preserved_without_a_task_priority(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            cache, old, _ = self.fixture(root)
            result = adopt(cache, root / "new")
            self.assertEqual(result["candidates"], old["candidates"])
            self.assertEqual(result["cluster_selection"]["selected_score"], old["primary_proposal"]["score"])
            self.assertEqual(result["cluster_selection"]["selected_cluster_count"], 1)
            self.assertEqual(result["candidate_relationship"], "parallel")
            with self.assertRaises(FileExistsError):
                adopt(cache, root / "new")

    def test_changed_or_inconsistent_original_never_published(self):
        for failure in ("hash", "membership"):
            with self.subTest(failure=failure), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                cache, old, proof = self.fixture(root)
                old["source_region"]["preliminary_graph_ids"] = ["different"]
                source = cache / "source_selection.json"
                source.write_text(json.dumps(old))
                if failure == "membership":
                    proof["files"][source.name] = digest(source)
                    (cache / "verified.json").write_text(json.dumps(proof))
                with self.assertRaises(ValueError):
                    adopt(cache, root / "new")
                self.assertFalse((root / "new").exists())


if __name__ == "__main__":
    unittest.main()
