from __future__ import annotations

import sys
from pathlib import Path
import unittest

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from diagnosis.multi_node_trace import single_node_sync_connected
else:
    from .multi_node_trace import single_node_sync_connected


class SingleNodeGateTests(unittest.TestCase):
    def test_requires_notify_connected_all_declared_ranks(self):
        rows = [dict(_graph_id=str(r), _user_rank=r, _node_id="node0") for r in range(4)]
        edges = [dict(src=str(r), dst=str(r + 1), kind="direct_notify_sync_exact", confidence="exact")
                 for r in range(3)]
        self.assertTrue(single_node_sync_connected(rows, edges, dict.fromkeys(range(4))))
        self.assertFalse(single_node_sync_connected(rows, edges[:2], dict.fromkeys(range(4))))
        self.assertFalse(single_node_sync_connected(rows, [dict(e, kind="direct_stream_order_observed")
                                                          for e in edges], dict.fromkeys(range(4))))
        self.assertFalse(single_node_sync_connected(rows, [dict(e, confidence="semantic")
                                                          for e in edges], dict.fromkeys(range(4))))

    def test_one_rank_or_other_node_does_not_pass(self):
        self.assertFalse(single_node_sync_connected([], [], {0: None}))
        rows = [dict(_graph_id=str(r), _user_rank=r, _node_id="node" + str(r)) for r in range(2)]
        edge = dict(src="0", dst="1", kind="direct_notify_sync_exact", confidence="exact")
        self.assertFalse(single_node_sync_connected(rows, [edge], {0: None, 1: None}))


if __name__ == "__main__":
    unittest.main()
