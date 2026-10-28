from __future__ import annotations

import time
import unittest

from test.multinode_clock_probe import ProbeServer, probe_batch


@unittest.skipUnless(hasattr(time, "CLOCK_MONOTONIC_RAW"), "Linux/raw clock required")
class MultinodeClockProbeTests(unittest.TestCase):
    def test_real_loopback_exchange_records_causality_and_both_phases(self):
        with ProbeServer("127.0.0.1", 0, "capture", "node0", ["node2"]) as server:
            before = probe_batch("127.0.0.1", server.port, "capture", "node2", "node0", "before", samples=4, timeout=2)
            after = probe_batch("127.0.0.1", server.port, "capture", "node2", "node0", "after", samples=4, timeout=2)
            self.assertTrue(server.wait_for_after(1))
            for sample in before + after:
                self.assertLessEqual(sample["local_send_ns"], sample["reference_recv_ns"])
                self.assertLessEqual(sample["reference_recv_ns"], sample["reference_send_ns"])
                self.assertLessEqual(sample["reference_send_ns"], sample["local_recv_ns"])

    def test_wrong_capture_or_peer_cannot_supply_calibration(self):
        with ProbeServer("127.0.0.1", 0, "capture", "node0", ["node2"]) as server:
            for capture, peer in (("other", "node2"), ("capture", "node3")):
                with self.assertRaises(ValueError):
                    probe_batch("127.0.0.1", server.port, capture, peer, "node0", "before", samples=4, timeout=2)


if __name__ == "__main__":
    unittest.main()
