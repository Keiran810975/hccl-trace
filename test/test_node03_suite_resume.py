from __future__ import annotations

import hashlib
import importlib
import json
import shlex
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

with patch.object(sys, "path", [str(Path(__file__).parent)] + sys.path):
    suite = importlib.import_module("run_node03_suite")


class ResumeTests(unittest.TestCase):
    def setup(self, parent, wrong_hash=False):
        root, normal = (parent / ("hccl-diagnose-node03-20261030-" + suffix) for suffix in ("040", "021"))
        for directory in (root, normal):
            (directory / "input").mkdir(parents=True)
        source = root / "src/hccl/tools/diagnosis/a.py"
        source.parent.mkdir(parents=True)
        source.write_text("value = 1\n")
        (root / "input/aicpu_hcomm.tar.gz").write_bytes(b"fixture-only")
        (normal / "input/case.json").write_text(json.dumps(suite.build_plan()["cases"][0]))
        (normal / "authorized-state.json").write_text(json.dumps(dict(status="failed", restored_nodes=[0, 3])))
        digest = "wrong" if wrong_hash else hashlib.sha256(source.read_bytes()).hexdigest()
        (normal / "diagnosis-consumer.json").write_text(json.dumps(dict(pipeline_passed=True,
            files={"hccl/tools/diagnosis/a.py": digest})))
        return root, normal

    def execute(self, command, **kwargs):
        if "node03_evaluate.py" in str(command):
            return json.dumps(dict(case_id="hccl-diagnose-normal", pipeline_passed=True, candidate_count=0))
        return "validated-normal"

    def test_reuses_normal_then_only_attempts_new_anomaly(self):
        with tempfile.TemporaryDirectory() as directory:
            parent = Path(directory).resolve()
            root, normal = self.setup(parent)
            argv = ["suite", "--root", str(root), "--reuse-normal", str(normal)]
            with patch.object(sys, "argv", argv), patch.object(suite, "LOCAL_PARENT", parent), \
                    patch.object(suite.socket, "gethostname", return_value="liteserver-560t-0"), \
                    patch.object(suite.ctypes, "CDLL"), patch.object(suite, "execute", side_effect=self.execute) as execute, \
                    patch.object(suite.subprocess, "run", side_effect=RuntimeError("stop before any real launch")) as launch:
                with self.assertRaisesRegex(RuntimeError, "before any real launch"):
                    suite.main()
            state = json.loads((root / "suite-state.json").read_text())
            self.assertEqual(state["completed"], 1)
            self.assertEqual(state["cases"][0]["directory"], str(normal))
            self.assertTrue(state["cases"][0]["reused_completed_normal"])
            self.assertEqual(launch.call_count, 1)
            self.assertIn("hccl-diagnose-node03-20261030-042", str(launch.call_args))
            self.assertNotIn("hccl-diagnose-node03-20261030-041", str(launch.call_args))
            self.assertIn("x['iters']==50", shlex.split(execute.call_args_list[0].args[0][-1])[-1])
            evaluation = next(call.args[0][-1] for call in execute.call_args_list
                              if "node03_evaluate.py" in str(call.args[0]))
            self.assertIn("export PYTHONPATH=/workspace/" + root.name + "/src:", evaluation)
            self.assertNotIn("export PYTHONPATH=/workspace/" + normal.name + "/src:", evaluation)
            self.assertIn("--root /workspace/" + normal.name, evaluation)

    def test_consumer_mismatch_refuses_before_launch(self):
        with tempfile.TemporaryDirectory() as directory:
            parent = Path(directory).resolve()
            root, normal = self.setup(parent, wrong_hash=True)
            with patch.object(sys, "argv", ["suite", "--root", str(root), "--reuse-normal", str(normal)]), \
                    patch.object(suite, "LOCAL_PARENT", parent), \
                    patch.object(suite.socket, "gethostname", return_value="liteserver-560t-0"), \
                    patch.object(suite.ctypes, "CDLL"), patch.object(suite, "execute", return_value="validated"), \
                    patch.object(suite.subprocess, "run") as launch:
                with self.assertRaisesRegex(ValueError, "consumer differs"):
                    suite.main()
            launch.assert_not_called()
            self.assertFalse((root / "suite-state.json").exists())


if __name__ == "__main__":
    unittest.main()
