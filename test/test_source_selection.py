from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from hccl.tools.diagnosis.local_slow_clusters import analyze
from hccl.tools.diagnosis.test_local_slow_clusters import fork
from hccl.tools.diagnosis.test_source_events import capture
from . import diagnose_gpt_local_clusters as live
from .replay_source_selection import replay
from .evaluate_source_selection import evaluate
from .replay_significant_regions import digest


class SourceSelectionScriptTests(unittest.TestCase):
    def test_live_strict_replay_to_public_host_candidate_and_typed_evaluation(self):
        rows, edges, coords, preps = capture(host_delay=True)
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            manifest, coordinates, preparations = [directory / name for name in ('manifest.json', 'coords.json', 'preps.json')]
            manifest.write_text('{}')
            coordinates.write_text('{}')
            preparations.write_text(json.dumps(dict(schema_version=1, preparations=preps)))
            analysis = directory / 'strict'
            analysis.mkdir()
            for name in ('merge_summary.csv', 'run_summary.csv', 'dep_graph_summary.csv'):
                (analysis / name).write_text('status\npassed\n')
            with patch.object(live, 'replay_manifest', return_value=(analysis, True)), \
                    patch.object(live.graph, 'read_graph_artifact_nodes', return_value=rows), \
                    patch.object(live.graph, 'read_graph_artifact_edges', return_value=edges), \
                    patch.object(live.rolling, 'load_coordinates', return_value=coords):
                output = directory / 'dual'
                live.diagnose(manifest, coordinates, preparations, output)
            report = json.loads((output/'report.json').read_text())
            self.assertEqual(report['selected_mechanism'], 'host_preparation_late')
            self.assertEqual(report['summary']['candidate_count'], 1)
            self.assertTrue(report['quality']['strict_replay_passed'])
            self.assertTrue(report['host_support_chains'][0]['endpoint_facts'])
            self.assertEqual(report['host_support_chains'][0]['support_provenance'], 'original_endpoint_facts')
            truth = directory / 'separate-evaluation-input.json'
            truth.write_text(json.dumps(dict(actual_windows=[dict(node_id='run/node0', target_ranks=[0], start_ns=5010000, stop_ns=5090000)])))
            scored = evaluate(output/'report.json', truth)
            self.assertEqual(scored['host_intervals']['hits'], 1)
            self.assertEqual(scored['execution_tasks']['count'], 0)
            truth.write_text(json.dumps(dict(actual_windows=[dict(node_id='run/node0', target_ranks=[1], start_ns=5010000, stop_ns=5090000)])))
            self.assertEqual(evaluate(output/'report.json', truth)['host_intervals']['hits'], 0)
            report['candidates'][0]['observed_stop_ns'] += 1
            (output/'report.json').write_text(json.dumps(report))
            with self.assertRaises(ValueError):
                evaluate(output/'report.json', truth)

    def test_replay_seal_no_overwrite_and_no_original_mutation(self):
        values, edges = fork()
        report = analyze(values, edges)
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            path = directory / 'report.json'
            path.write_text(json.dumps(report))
            original_hash = digest(path)
            (directory/'sealed.json').write_text(json.dumps(dict(report_sha256=original_hash, truth_accessed=False)))
            output = directory / 'replay'
            result = replay(path, output)
            self.assertEqual(result['candidates'], report['candidates'])
            self.assertEqual(digest(path), original_hash)
            with self.assertRaises(FileExistsError):
                replay(path, output)
            path.write_text('{}')
            with self.assertRaises(ValueError):
                replay(path, directory/'bad')

    def test_failed_strict_gate_cannot_publish_a_source(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            public = directory / 'public.json'
            public.write_text('{}')
            with patch.object(live, 'replay_manifest', return_value=(directory, False)), self.assertRaises(ValueError):
                live.diagnose(public, public, public, directory/'output')
            self.assertFalse((directory/'output/report.json').exists())


if __name__ == '__main__':
    unittest.main()
