from __future__ import annotations

import hashlib
import io
from pathlib import Path
import tarfile
import tempfile
import unittest

from .calibration_offload import case_name, verify_archive, command


class CalibrationOffloadTests(unittest.TestCase):
    def archive(self, root, entries):
        archive = root / "sample.tar.gz"
        with tarfile.open(archive, "w:gz") as target:
            for name, value in entries:
                member = tarfile.TarInfo(name)
                member.size = len(value)
                target.addfile(member, io.BytesIO(value))
        return archive

    def test_content_verified_and_only_native_reports_extracted(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            entries = [("capture/profiler.db", b"db"), ("report/execution.html", b"native html")]
            manifest = dict(files={k: dict(size=len(v), sha256=hashlib.sha256(v).hexdigest()) for k, v in entries})
            archive = self.archive(root, entries)
            self.assertEqual(verify_archive(archive, manifest, root / "report"), set(manifest["files"]))
            self.assertEqual((root / "report/execution.html").read_bytes(), b"native html")
            self.assertFalse((root / "report/profiler.db").exists())

    def test_wrong_hash_missing_member_and_path_escape_are_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            archive = self.archive(root, [("a", b"x")])
            bad = dict(files=dict(a=dict(size=1, sha256="bad")))
            with self.assertRaisesRegex(ValueError, "content hash"):
                verify_archive(archive, bad)
            missing = dict(files={k: dict(size=1, sha256=hashlib.sha256(b"x").hexdigest()) for k in ("a", "b")})
            with self.assertRaisesRegex(ValueError, "incomplete"):
                verify_archive(archive, missing)
            escaped = self.archive(root, [("../other", b"x")])
            with self.assertRaisesRegex(ValueError, "unsafe"):
                verify_archive(escaped, dict(files={}))

    def test_scope_excludes_old_experiments_and_master_directory(self):
        for name in ("hccl-diagnose-node03-20261031-101", "hccl-diagnose-node03-20261101-200", "../201"):
            with self.assertRaises(ValueError):
                case_name(name)
        self.assertEqual(case_name("hccl-diagnose-node03-20261101-201"), "hccl-diagnose-node03-20261101-201")

    def test_peer_uses_strict_host_keys_and_no_private_key_contents(self):
        value = command(3, ["docker", "exec", "zjy-new", "true"])
        self.assertIn("StrictHostKeyChecking=yes", value)
        self.assertIn("StrictHostKeyChecking=yes", value[-1])
        with self.assertRaises(ValueError):
            command(2, ["true"])


if __name__ == "__main__":
    unittest.main()
