"""Resolve separate alert and report roots from the flat YAML configuration."""
from __future__ import annotations

from dataclasses import dataclass
from itertools import combinations
import json
import os
from pathlib import Path
import re


DEFAULTS = {
    "online_output_dir": "reports/online",
    "online_report_output_dir": "reports/online-details",
    "offline_output_dir": "reports/offline",
}


@dataclass(frozen=True)
class ReportPaths:
    online: Path
    online_reports: Path
    offline: Path

    def for_run(self, kind, run_id):
        from .multi_node_trace import _name

        return getattr(self, kind) / _name(run_id)


def require_separate(*directories):
    for left, right in combinations((directory.resolve() for directory in directories), 2):
        if left == right or left in right.parents or right in left.parents:
            raise ValueError(f"alert and report directories must be separate: {left} and {right}")


def _scalar(value):
    value = value.strip()
    if value.startswith('"'):
        parsed, end = json.JSONDecoder().raw_decode(value)
        rest = value[end:].lstrip()
        if rest and not rest.startswith("#"):
            raise ValueError("unexpected text after quoted path")
        value = parsed
    elif value.startswith("'"):
        match = re.fullmatch(r"'((?:[^']|'')*)'\s*(?:#.*)?", value)
        if not match:
            raise ValueError("invalid single-quoted path")
        value = match[1].replace("''", "'")
    else:
        value = re.split(r"\s+#", value, maxsplit=1)[0].rstrip()
        if value.startswith(("#", "[", "{", "&", "*", "!", "|", ">")) or value in {"null", "Null", "NULL", "~"}:
            raise ValueError("expected a path, not a YAML collection or special value")
    if not value or any(ord(c) < 32 for c in value):
        raise ValueError("expected a nonempty path without control characters")
    return value


def load_paths(config=None):
    explicit = config if config is not None else os.environ.get("HCCL_TRACE_CONFIG")
    path = Path(explicit if explicit is not None else "config.yaml").expanduser().absolute()
    values = {}
    try:
        lines = path.read_text(encoding="utf-8-sig").splitlines()
    except FileNotFoundError:
        if explicit is not None or path.is_symlink():
            raise ValueError(f"configuration does not exist: {path}") from None
        lines = []
    for index, line in enumerate(lines, 1):
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        key, separator, value = line.partition(":")
        try:
            if not separator or key.rstrip() not in DEFAULTS:
                raise ValueError("expected one of " + ", ".join(DEFAULTS))
            key = key.rstrip()
            if key in values:
                raise ValueError(f"duplicate key {key}")
            values[key] = _scalar(value)
        except ValueError as error:
            raise ValueError(f"{path}:{index}: {error}") from error
    directories = tuple((path.parent / Path(values.get(key, default)).expanduser()).resolve()
                        for key, default in DEFAULTS.items())
    require_separate(*directories)
    return ReportPaths(*directories)
