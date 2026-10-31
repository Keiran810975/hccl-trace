from __future__ import annotations

from pathlib import Path
import unittest
from unittest.mock import Mock

from test.node03_device_guard import CARDS, Guard, policy, scope, own_transition


class DeviceGuardTests(unittest.TestCase):
    def test_scope_does_not_expand_to_other_nodes_or_card_sets(self):
        self.assertEqual(CARDS, (4, 5, 6, 7))
        for host, parent in (("liteserver-560t-0", "/home/commTeam/zjy/zjy-new-workspace"),
                             ("liteserver-560t-3", "/home/zjy-new/workspace")):
            root = Path(parent) / "hccl-diagnose-node03-20261029-006"
            self.assertEqual(scope(root, host), root.resolve())
            for other in ("liteserver-560t-1", "liteserver-560t-2"):
                with self.assertRaises(ValueError):
                    scope(root, other)
        with self.assertRaises(ValueError):
            scope(Path("/tmp/hccl-diagnose-node03-20261029-006"), "liteserver-560t-0")

    def test_original_policy_requires_both_chips(self):
        enable = "Custom-op-secverify-enable : False\n" * 2
        mode = "Custom-op-secverify-mode : 5\n" * 2
        self.assertEqual(policy(enable, mode), dict(enable=False, mode=5))
        for a, b in ((enable.splitlines()[0], mode), (enable, mode.replace("5", "0", 1))):
            with self.assertRaises(ValueError):
                policy(a, b)

    def test_partial_apply_can_restore_but_unknown_admin_change_is_not_clobbered(self):
        original = dict(enable=False, mode=5)
        for current in (original, dict(enable=True, mode=5), dict(enable=True, mode=0)):
            self.assertTrue(own_transition(current, original))
        self.assertFalse(own_transition(dict(enable=True, mode=3), original))

    def test_expired_transient_timer_can_already_be_unloaded(self):
        guard = object.__new__(Guard)
        for status in ("unknown\n", "inactive\n"):
            guard.run = Mock(side_effect=["", status])
            guard.stop_timer("owned")
            self.assertEqual(guard.run.call_args.kwargs, dict(check=False))
        guard.run = Mock(side_effect=["", "active\n"])
        with self.assertRaises(RuntimeError):
            guard.stop_timer("owned")


if __name__ == "__main__":
    unittest.main()
