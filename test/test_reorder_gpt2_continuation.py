from __future__ import annotations

import fcntl
import json
from pathlib import Path
import tempfile
import unittest

from test.gpt2_diagnosis_suite import cases, write_plan, write_continuation
from test.reorder_gpt2_continuation import reorder, KINDS


class ReorderTests(unittest.TestCase):
    def prepare(self, parent):
        write_plan(parent / "plan")
        completed = [dict(case_id=c["case_id"], injection=c["injection"], status="diagnosed") for c in cases()[:11]]
        (parent / "state.json").write_text(json.dumps(dict(status="stopped", active_case=None,
                                                          completed=11, cases=completed)))
        root = parent / "continuation"
        write_continuation(parent, root / "plan", physical_node="node0")
        return root

    def test_interleaves_ten_cycles_and_preserves_every_case_byte(self):
        with tempfile.TemporaryDirectory() as directory:
            root = self.prepare(Path(directory))
            before = {p.name: p.read_bytes() for p in (root / "plan").glob("*.json")}
            result = reorder(root)
            self.assertEqual(result["cases"][0]["case_id"], "gpt2-4r-normal")
            for index in range(10):
                self.assertEqual([e["case_id"] for e in result["cases"][1 + index * 3:4 + index * 3]],
                                 ["gpt2-4r-{}-{:02d}".format(kind, index + 1) for kind in KINDS])
            for name, raw in before.items():
                actual = root / "plan" / ("suite.grouped-before-round-robin.json" if name == "suite.json" else name)
                self.assertEqual(actual.read_bytes(), raw)
            self.assertEqual(reorder(root), result)
            self.assertTrue(json.loads((root / "round-robin-receipt.json").read_text())["case_inputs_unchanged"])

    def test_refuses_any_started_plan_and_live_queue_lock(self):
        with tempfile.TemporaryDirectory() as directory:
            root = self.prepare(Path(directory))
            before = (root / "plan/suite.json").read_bytes()
            state = root / "state.json"
            state.write_text(json.dumps(dict(status="stopped", completed=0)))
            with self.assertRaisesRegex(ValueError, "never-started"):
                reorder(root)
            state.unlink()
            with (root / "suite.lock").open("a") as stream:
                fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
                with self.assertRaises(BlockingIOError):
                    reorder(root)
            self.assertEqual((root / "plan/suite.json").read_bytes(), before)
            self.assertFalse((root / "round-robin-receipt.json").exists())


if __name__ == "__main__":
    unittest.main()
