"""Verify and retain both nodes' short-capture inputs; never delete remote data."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import tarfile

from test import calibration_offload as archive


def backup(case, output):
    if case not in ("hccl-diagnose-node03-20261101-240", "hccl-diagnose-node03-20261101-241"):
        raise ValueError("only the two explicitly retained short attempts are allowed")
    output.mkdir(parents=True, exist_ok=True)
    archive.MEMBERS += ("preflight-report", "preflight-report.debug", "numerics", "short-window-audit.json",
                        "recovery-verification.json", "authorized.log", "supervisor.log", "watchdog.log", "launch.json")
    archive.REPORTS = {"preflight-report/" + name for name in ("execution.html", "root_causes.json", "propagation.html")}
    receipts = [archive.backup(node, case, output) for node in (0, 3)]
    for node in (0, 3):
        directory = output / ("node" + str(node))
        destination = directory / "facts"
        if destination.exists():
            raise FileExistsError("inspect existing extraction before repeating backup")
        destination.mkdir()
        manifest = json.loads((directory / "manifest.json").read_text())
        archive.verify_archive(directory / "replay.tar.gz", manifest)
        with tarfile.open(directory / "replay.tar.gz", "r:gz") as stream:
            for member in stream:
                if member.isdir():
                    continue
                if member.name not in manifest["files"] or not member.isfile():
                    raise ValueError("unverified member")
                path = destination / member.name
                path.parent.mkdir(parents=True, exist_ok=True)
                with stream.extractfile(member) as source, path.open("xb") as target:
                    import shutil
                    shutil.copyfileobj(source, target)
    result = dict(verified=True, receipts=receipts, remote_deleted=False,
                  retained_all_raw_inputs=True, no_cleanup_ack_sent=True)
    (output / "retention-receipt.json").write_text(json.dumps(result, indent=2) + "\n")
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", required=True)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    print(json.dumps(backup(args.case, args.output)))
