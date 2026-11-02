from __future__ import annotations

import unittest

from .stop_owned_capture import owned_processes, terminate


class StopOwnedCaptureTests(unittest.TestCase):
    def test_exact_attempt_paths_not_names_or_other_users_are_selected(self):
        base = "/workspace/hccl-diagnose-node03-20261101-121"
        observations = {
            10: dict(parent=1, ticks="10", argv=["python", base + "/src/test/gpt2_train.py"]),
            11: dict(parent=10, ticks="11", argv=["npu-worker"]),
            12: dict(parent=11, ticks="12", argv=["spawn-child"]),
            20: dict(parent=1, ticks="20", argv=["hccl-diagnose"]),
            21: dict(parent=1, ticks="21", argv=["python", base + "0/src/test/gpt2_train.py"]),
            22: dict(parent=1, ticks="22", argv=["python", "-c", "print('" + base + "/src/test/gpt2_train.py')"]),
        }
        self.assertEqual(set(owned_processes(observations, base)), {10, 11, 12})

    def test_unsafe_base_is_rejected_before_process_inspection(self):
        for base in ("/workspace", "/", "/workspace/hccl-diagnose-node03-../", "/workspace/other"):
            with self.subTest(base=base), self.assertRaises(ValueError):
                terminate(base)


if __name__ == "__main__":
    unittest.main()
