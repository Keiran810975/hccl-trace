from __future__ import annotations

import hashlib
import io
import json
from pathlib import Path
import tarfile
import tempfile
import unittest

from .cache_multinode_public import PUBLIC_FACTS, extract


class PublicCacheTests(unittest.TestCase):
    def test_only_public_verified_facts_are_extracted(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source"
            source.mkdir()
            data = {"report.debug/analysis/sample/" + name: b"public" for name in PUBLIC_FACTS}
            data["gpt-output/private/injection.json"] = b"DO NOT READ"
            data["evaluation.json"] = b"DO NOT READ"
            manifest = dict(files={k: dict(size=len(v), sha256=hashlib.sha256(v).hexdigest()) for k, v in data.items()})
            (source / "manifest.json").write_text(json.dumps(manifest))
            (source / "verified.json").write_text(json.dumps(dict(file_hashes_verified=True, archive_sha256="original",
                manifest_sha256=hashlib.sha256(json.dumps(manifest, sort_keys=True).encode()).hexdigest())))
            with tarfile.open(source / "replay.tar.gz", "w:gz") as archive:
                for name, value in data.items():
                    info = tarfile.TarInfo(name)
                    info.size = len(value)
                    archive.addfile(info, io.BytesIO(value))
            result = extract(source, root / "public")
            self.assertEqual(set(result["files"]), set(PUBLIC_FACTS))
            self.assertFalse(result["truth_accessed"])
            self.assertFalse((root / "public/evaluation.json").exists())
            with self.assertRaises(FileExistsError):
                extract(source, root / "public")
