from __future__ import annotations

import json
import hashlib
from pathlib import Path
import tempfile
import unittest

from .export_multinode_dual_results import evaluate, export
from .multinode_dual_suite import plan


class ResultExportTests(unittest.TestCase):
    def fixture(self, root):
        cases = []
        for index, specification in enumerate(plan()["cases"], 521):
            name = "case-" + str(index)
            directory = root / "live-test" / name
            directory.mkdir(parents=True)
            case_id = specification["case_id"]
            windows = [] if index == 521 else [dict(node_id="n", user_rank=4, start_ns=10, stop_ns=20)]
            candidate = dict(id="source", source_unit="execution_task", node_id="n", user_rank=4,
                             observed_start_ns=11, observed_stop_ns=12)
            case = dict(case_id=case_id, injection=specification["injection"], directory="/server/" + name,
                        windows=windows, candidate_count=1, hit_candidate_ids=["source"] if windows else [],
                        candidate_hit_count=int(bool(windows)), primary_hit=bool(windows), selected_mechanism="execution")
            cases.append(case)
            report = dict(run_id=case_id, quality=dict(pipeline_passed=True), source_candidates=[candidate],
                          candidates=[candidate], primary_source_id="source", primary_candidate_id="source")
            report_directory = directory / "report"
            report_directory.mkdir()
            for name in ("execution.html", "propagation.html", "root_causes.json"):
                (report_directory / name).write_text(json.dumps(report) if name.endswith("json") else "<html></html>")
            for node in (0, 3):
                node_directory = directory / ("node" + str(node))
                node_directory.mkdir()
                archive = b"retained original facts"
                (node_directory / "replay.tar.gz").write_bytes(archive)
                facts = {"evaluation.json": dict(sha256=hashlib.sha256(
                    (json.dumps(case, indent=2, ensure_ascii=False) + "\n").encode()).hexdigest())}
                if node == 0:
                    facts.update({"report/" + p.name: dict(sha256=hashlib.sha256(p.read_bytes()).hexdigest())
                                  for p in report_directory.iterdir()})
                manifest = dict(files=facts)
                (node_directory / "manifest.json").write_text(json.dumps(manifest))
                (node_directory / "verified.json").write_text(json.dumps(dict(node=node, file_hashes_verified=True,
                    manifest_sha256=hashlib.sha256(json.dumps(manifest, sort_keys=True).encode()).hexdigest(),
                    archive_sha256=hashlib.sha256(archive).hexdigest(), file_count=len(facts))))
            (directory / "offload-receipt.json").write_text(json.dumps(dict(status="verified", file_hashes_verified=True)))
        state = root / "follower.json"
        state.write_text(json.dumps(dict(last_remote=dict(status="completed", completed=6, requested_runs=6, cases=cases))))
        return state

    def test_sources_require_same_node_rank_and_positive_overlap(self):
        base = dict(node_id="n", user_rank=4, observed_start_ns=10, observed_stop_ns=20)
        sources = [dict(base,id="hit"),dict(base,id="rank",user_rank=0),dict(base,id="node",node_id="else"),
                   dict(base,id="boundary",observed_start_ns=20,observed_stop_ns=30)]
        report = dict(source_candidates=sources,candidates=[],primary_source_id="rank",primary_candidate_id=None)
        selected, hits, primary = evaluate(report,[dict(node_id="n",user_rank=4,start_ns=10,stop_ns=20)])
        self.assertEqual(len(selected),4)
        self.assertEqual(hits,["hit"])
        self.assertFalse(primary)

    def test_incomplete_runs_cannot_be_exported_as_complete(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary)
            state=root/"state.json"
            state.write_text(json.dumps(dict(last_remote=dict(status="running",completed=5,requested_runs=6))))
            with self.assertRaisesRegex(ValueError,"six actual"):
                export(root,state,root/"report")
            self.assertFalse((root/"report").exists())

    def test_complete_export_keeps_normal_false_positive_separate(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            state = self.fixture(root)
            result = export(root, state, root / "results")
            self.assertEqual(result["hit_count"], 5)
            self.assertEqual(result["candidate_count"], 5)
            self.assertEqual(result["baseline_false_positive_sources"], 1)
            self.assertEqual(len(result["cases"]), 6)
            self.assertTrue((root / "results/injection-windows.csv").is_file())

    def test_report_tampering_cannot_be_exported(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            state = self.fixture(root)
            (root / "live-test/case-522/report/root_causes.json").write_text("{}")
            with self.assertRaisesRegex(ValueError, "sealed original"):
                export(root, state, root / "results")
            self.assertFalse((root / "results").exists())
