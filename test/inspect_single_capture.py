#!/usr/bin/env python3
"""Read-only capture inventory for the single-node runtime preflight."""
from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
import sqlite3


def inspect(directory):
    directory = Path(directory)
    markers = Counter()
    for path in (directory / "ascend_log").rglob("*"):
        if path.is_file() and path.suffix in {".log", ".txt"}:
            for line in path.open(encoding="utf-8", errors="replace"):
                for tag in ("[HcclTaskSemantic]", "[HcclTaskControl]", "[HcclTaskGraphCorrelation]"):
                    if tag in line:
                        markers[tag] += 1
    result = dict(markers=markers, databases=[], clocks=[])
    for path in sorted((directory / "msprof").rglob("msprof_*.db")):
        with sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True) as db:
            db.row_factory = sqlite3.Row
            tables = [r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")]
            item = dict(path=str(path), tables=tables)
            if "COMMUNICATION_OP" in tables:
                item["operation_columns"] = [r[1] for r in db.execute("PRAGMA table_info(COMMUNICATION_OP)")]
                item["operations"] = [dict(r) for r in db.execute(
                    "SELECT o.*, g.value AS group_name, n.value AS op_name FROM COMMUNICATION_OP o "
                    "LEFT JOIN STRING_IDS g ON g.id=o.groupName LEFT JOIN STRING_IDS n ON n.id=o.opName LIMIT 5")]
            result["databases"].append(item)
    for path in (directory / "msprof").rglob("*"):
        if path.is_file() and (path.name.startswith("start_info") or path.name.startswith("host_start.log")):
            if path.stat().st_size < 20000:
                result["clocks"].append(dict(path=str(path), text=path.read_text(errors="replace")[:3000]))
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    print(json.dumps(inspect(parser.parse_args().directory), indent=2))
