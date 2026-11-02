from __future__ import annotations

import json
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import Mock

from .short_copy_burst import ShortCopyBurst, GptCopyBurstControl


class ShortCopyBurstTests(unittest.TestCase):
    def test_gpt_burst_only_activates_after_selected_formal_submit(self):
        case = dict(injection=dict(kind='copy_contention', finite_copy_burst=True,
                    buffer_mib=2048, operations=4, duration_iters=1, target_rank=0, iteration=25))
        with tempfile.TemporaryDirectory() as tmp:
            factory = Mock()
            control = GptCopyBurstControl(case, tmp, 0, [1, 3, 5, 7], factory=factory)
            control.prepare()
            call = dict(stage='measured', iteration=24, sequence=3, bucket=2, bucket_signature='test')
            control.after_collective(call)
            factory.return_value.start.assert_not_called()
            control.after_collective(dict(call, iteration=25))
            control.after_collective(dict(call, iteration=25))
            factory.return_value.start.assert_called_once()
            control.after_iteration(25)
            factory.return_value.wait_finished.assert_called_once()
            control.finish()
            control.close()
            factory.return_value.close.assert_called_once()

    def test_finite_stronger_burst_still_has_only_one_worker(self):
        copies = Mock()
        factory = Mock(return_value=copies)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'burst.json'
            burst = ShortCopyBurst(3, 2048, path, operations=4, factory=factory)
            burst.start()
            burst.wait_finished(2)
            self.assertEqual(copies.copy.call_count, 4)
            copies.validate.assert_not_called()
            burst.close()
            self.assertEqual(json.loads(path.read_text())['operations'], 4)
        factory.assert_called_once()

    def test_exactly_one_copy_and_validation_after_measurement(self):
        copies = Mock()
        factory = Mock(return_value=copies)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "burst.json"
            burst = ShortCopyBurst(1, 64, path, factory=factory)
            factory.assert_called_once_with(1, 64, initialize_runtime=False)
            copies.copy.assert_not_called()
            burst.start()
            deadline = time.monotonic() + 2
            while not path.exists() and time.monotonic() < deadline:
                time.sleep(.001)
            copies.copy.assert_called_once()
            copies.validate.assert_not_called()
            with self.assertRaises(ValueError):
                burst.start()
            burst.close()
            data = json.loads(path.read_text())
            self.assertEqual(data["operations"], 1)
            self.assertTrue(data["validation_passed"])
            self.assertFalse(data["hardware_duration_claimed"])
            copies.close.assert_called_once()

    def test_cancellation_before_trigger_cannot_inject(self):
        copies = Mock()
        with tempfile.TemporaryDirectory() as tmp:
            burst = ShortCopyBurst(1, 64, Path(tmp) / "burst.json", factory=Mock(return_value=copies))
            burst.close()
        copies.copy.assert_not_called()
        copies.close.assert_called_once()
