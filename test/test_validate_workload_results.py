from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from validate_workload_results import validate


class WorkloadResultTests(unittest.TestCase):
    def test_missing_worker_is_not_msprof_success(self):
        with tempfile.TemporaryDirectory() as temporary:
            with self.assertRaisesRegex(ValueError, "missing successful"):
                validate(Path(temporary), 0, 4, 2)

    def test_only_complete_local_rank_set_passes(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            for rank in (4, 5):
                (directory / f"rank-{rank}.json").write_text(json.dumps(
                    dict(rank=rank, world_size=8, status="passed", max_error=0)))
            validate(directory, 2, 4, 2)
            (directory / "rank-5.json").write_text(json.dumps(
                dict(rank=5, world_size=8, status="passed", max_error=float("nan"))))
            with self.assertRaisesRegex(ValueError, "invalid workload"):
                validate(directory, 2, 4, 2)


if __name__ == "__main__":
    unittest.main()
