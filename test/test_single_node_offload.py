from __future__ import annotations

from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from run_single_node_offload import target_cards_idle


class TargetCardTests(unittest.TestCase):
    def snapshot(self):
        lines = ["| {} {} | x | 0 | 0 / 0 | {} / 65536 |".format(p % 2, p, 2800 if p >= 8 else 60000)
                 for p in range(16)]
        return "\n".join(lines + ["| No running processes found in NPU {} |".format(p) for p in (4, 5, 6, 7)])

    def test_other_cards_may_be_busy_only_when_targets_are_idle(self):
        self.assertTrue(target_cards_idle(self.snapshot()))
        self.assertFalse(target_cards_idle(self.snapshot().replace("No running processes found in NPU 4", "4 | 123 | python")))

    def test_high_target_memory_or_missing_physical_chip_prevents_launch(self):
        self.assertFalse(target_cards_idle(self.snapshot().replace("| 0 8 | x | 0 | 0 / 0 | 2800", "| 0 8 | x | 0 | 0 / 0 | 60000")))
        self.assertFalse(target_cards_idle(self.snapshot().replace("| 0 8 |", "| 0 7 |")))


if __name__ == "__main__":
    unittest.main()
