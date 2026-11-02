from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from . import follow_communication_calibration as client


class CalibrationFollowerTests(unittest.TestCase):
    def test_new_queue_is_followed_explicitly_not_by_restarting_the_old_one(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(client, "snapshot", return_value=dict(status="exploration_complete")) as snapshot:
            result = client.follow(Path(tmp), .01, client.ROOTS[1])
            self.assertEqual(result["remote_root"], client.ROOTS[1])
            snapshot.assert_called_once_with(client.ROOTS[1])
            with self.assertRaisesRegex(ValueError, "reviewed"):
                client.follow(Path(tmp), .01, "/another/queue")
    def test_finished_queue_does_not_submit_jobs_or_delete_data(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(client, "snapshot", return_value=dict(status="exploration_complete")), \
                patch.object(client, "offload") as offload:
            result = client.follow(Path(tmp), .01)
            self.assertEqual(result["status"], "exploration_complete")
            offload.assert_not_called()

    def test_diagnosis_miss_is_backed_up_without_remote_deletion(self):
        remote = dict(status="diagnosis_refinement_needed", attempts=[dict(directory="/own/hccl-diagnose-node03-20261101-202")])
        with tempfile.TemporaryDirectory() as tmp, patch.object(client, "snapshot", return_value=remote), \
                patch.object(client, "offload", return_value=dict(verified=True)) as offload:
            result = client.follow(Path(tmp), .01)
            self.assertEqual(result["status"], "needs_offline_diagnosis_refinement")
            self.assertFalse(offload.call_args.kwargs["remove_remote"])

    def test_stopped_attempt_is_backed_up_without_cleanup_or_resubmission(self):
        remote = dict(status="stopped", active_directory="/own/hccl-diagnose-node03-20261101-201")
        with tempfile.TemporaryDirectory() as tmp, patch.object(client, "snapshot", return_value=remote), \
                patch.object(client, "offload", return_value=dict(verified=True)) as offload:
            result = client.follow(Path(tmp), .01)
            self.assertEqual(result["status"], "stopped")
            self.assertEqual(len(result["backups"]), 1)
            offload.assert_called_once_with("hccl-diagnose-node03-20261101-201", Path(tmp), remove_remote=False)

    def test_unrestored_stopped_attempt_cannot_be_declared_archived(self):
        remote = dict(status="stopped", active_directory="/own/hccl-diagnose-node03-20261101-201")
        with tempfile.TemporaryDirectory() as tmp, patch.object(client, "snapshot", return_value=remote), \
                patch.object(client, "offload", side_effect=ValueError("restore receipt absent")):
            with self.assertRaisesRegex(ValueError, "restore receipt absent"):
                client.follow(Path(tmp), .01)
            state = json.loads((Path(tmp) / "follower-state.json").read_text())
            self.assertEqual(state["status"], "backing_up_stopped_attempt")
            self.assertEqual(state["backups"], [])

    def test_archive_ack_is_followed_by_next_snapshot_not_resubmission(self):
        remote = dict(status="awaiting_verified_archive", active_directory="/own/hccl-diagnose-node03-20261101-201")
        with tempfile.TemporaryDirectory() as tmp, patch.object(client, "snapshot", side_effect=[remote, dict(status="exploration_complete")]), \
                patch.object(client.time, "sleep"), patch.object(client, "offload", return_value=dict(verified=True)) as offload:
            result = client.follow(Path(tmp), .01)
            self.assertTrue(offload.call_args.kwargs["remove_remote"])
            self.assertEqual(len(result["backups"]), 1)
            self.assertEqual(json.loads((Path(tmp) / "follower-state.json").read_text())["status"], "exploration_complete")


if __name__ == "__main__":
    unittest.main()
