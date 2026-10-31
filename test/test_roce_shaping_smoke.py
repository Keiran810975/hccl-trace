from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from subprocess import CompletedProcess

from test.roce_shaping_smoke import parse_shaping, require_idle_card, require_zero_traffic, restore, stop_timer


class RoceShapingSmokeTests(unittest.TestCase):
    def test_shaping(self):
        self.assertEqual(parse_shaping("bw_limit[100000 Mbps], bw_max[200000 Mbps], bw_cur[100000 Mbps]\n"),
                         dict(limit_mbps=100000, maximum_mbps=200000, current_mbps=100000))

    def test_reject_missing_and_duplicate_query_fields(self):
        value = "bw_limit[200000 Mbps], bw_max[200000 Mbps], bw_cur[200000 Mbps]"
        for text in ("", value.replace("bw_cur", "unexpected"), value + value):
            with self.subTest(text=text), self.assertRaises(ValueError):
                parse_shaping(text)

    def test_reject_invalid_range(self):
        for limit, maximum in ((0, 200000), (200000, 100000), (200000, 400000)):
            with self.subTest(limit=limit, maximum=maximum), self.assertRaises(ValueError):
                parse_shaping(f"bw_limit[{limit} Mbps], bw_max[{maximum} Mbps], bw_cur[200000 Mbps]")

    def test_zero_traffic(self):
        require_zero_traffic("Bandwidth TX:     0.00 MB/sec\nBandwidth RX:     0.00 MB/sec\n")

    def test_reject_traffic_or_incomplete_query(self):
        for text in ("", "Bandwidth TX: 0.00 MB/sec", "Bandwidth TX: 0.00 MB/sec\nBandwidth TX: 0.00 MB/sec",
                     "Bandwidth TX: 1.00 MB/sec\nBandwidth RX: 0.00 MB/sec"):
            with self.subTest(text=text), self.assertRaises(ValueError):
                require_zero_traffic(text)

    @staticmethod
    def card_text(first=3159, second=2881):
        return (f"| 3 Ascend910 |\n| 0 6 | 62000 / 65536 |\n"
                f"| 4 Ascend910 |\n| 0 8 | {first} / 65536 |\n"
                f"| 4 Ascend910 |\n| 1 9 | {second} / 65536 |\n"
                "| 5 Ascend910 |\n| 0 10 | 62000 / 65536 |\n"
                "| No running processes found in NPU 4 |\n")

    def test_target_card_only(self):
        require_idle_card(self.card_text())

    def test_reject_occupied_or_missing_chip(self):
        for text in (self.card_text().replace("No running processes found in NPU 4", "4 1 123 VLLM"),
                     self.card_text(second=4096), self.card_text(first=50000),
                     self.card_text().replace("| 1 9 | 2881 / 65536 |", "")):
            with self.subTest(text=text), self.assertRaises(ValueError):
                require_idle_card(text)

    def check_restoration(self, queries, expected_calls, error=None):
        original = dict(limit_mbps=200000, maximum_mbps=200000, current_mbps=200000)
        with tempfile.TemporaryDirectory() as name:
            out = Path(name)
            snapshot = out / "snapshot.json"
            snapshot.write_text(json.dumps(dict(device=9, original={"8": original, "9": original})))
            with patch("test.roce_shaping_smoke.safe_directory", return_value=out), \
                 patch("test.roce_shaping_smoke.query", side_effect=queries), \
                 patch("test.roce_shaping_smoke.run") as setter:
                if error:
                    with self.assertRaises(error):
                        restore(snapshot, out / "restored.json")
                else:
                    restore(snapshot, out / "restored.json")
                    self.assertTrue(json.loads((out / "restored.json").read_text())["restored"])
                self.assertEqual(setter.call_count, expected_calls)
                if expected_calls:
                    self.assertEqual(setter.call_args.args[0],
                        ["/usr/local/Ascend/driver/tools/hccn_tool", "-i", "9", "-shaping", "-s", "bw_limit", "200000"])

    def test_restoration_is_noop_when_original(self):
        original = dict(limit_mbps=200000, maximum_mbps=200000, current_mbps=200000)
        self.check_restoration([original] * 4, 0)

    def test_restore_only_requested_change(self):
        original = dict(limit_mbps=200000, maximum_mbps=200000, current_mbps=200000)
        limited = dict(limit_mbps=100000, maximum_mbps=200000, current_mbps=100000)
        self.check_restoration([limited, original, original, original], 1)

    def test_do_not_overwrite_unrelated_configuration(self):
        unrelated = dict(limit_mbps=50000, maximum_mbps=200000, current_mbps=50000)
        self.check_restoration([unrelated], 0, RuntimeError)

    def test_collected_timer_is_already_stopped(self):
        for state in ("inactive", "unknown"):
            with patch("test.roce_shaping_smoke.run", side_effect=[
                    CompletedProcess([], 5, "", "Unit not loaded"), CompletedProcess([], 3, state, "")]):
                stop_timer(Path("/unused"), "test-unit")

    def test_active_timer_cannot_be_reported_as_stopped(self):
        with patch("test.roce_shaping_smoke.run", side_effect=[
                CompletedProcess([], 1, "", "permission denied"), CompletedProcess([], 0, "active", "")]):
            with self.assertRaises(RuntimeError):
                stop_timer(Path("/unused"), "test-unit")


if __name__ == "__main__":
    unittest.main()
