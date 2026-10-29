"""Read-only capture discovery. Directory names never imply rank/device IDs."""
from __future__ import annotations

from dataclasses import dataclass, replace
from contextlib import closing
import json
from pathlib import Path
import shutil

from .multi_node_trace import load_manifest, _name
from .parse_msprof_db import discover_db_files, _readonly_connection, _validate_contract, _device_ids, _table_columns, TASK_BATCH_TABLE


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def write_json(path, data):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


@dataclass(frozen=True)
class Capture:
    manifest: dict
    call_logs: tuple
    iteration_map: Path | None = None
    preparation_map: Path | None = None
    operation_map: Path | None = None
    identity_exports: tuple = ()


def prepare_capture_identity(capture, work):
    """Export only necessary authoritative HOST batches into owned temporary DBs."""
    from .merge_timeline import _semantic_log_paths
    from .parse_plog import parse_plog_lines
    from .export_msprof_identity import export_identity
    nodes, evidence = [], []
    for original in capture.manifest["nodes"]:
        node = dict(original)
        paths = discover_db_files(node["msprof_db_dir"])
        unprepared = set()
        for path in paths:
            with closing(_readonly_connection(str(path))) as db:
                device, = _device_ids(db)
                if not _table_columns(db, TASK_BATCH_TABLE):
                    unprepared.add(device)
        pending = set()
        if unprepared:
            for path in _semantic_log_paths(node["plog_dir"]):
                with path.open(encoding="utf-8", errors="replace") as stream:
                    for record in parse_plog_lines(stream):
                        if record.device_id in unprepared and record.source == "host" and record.task_id >= 65535:
                            pending.add(record.device_id)
        if pending:
            selected = Path(work) / node["node_id"]
            for path in paths:
                with closing(_readonly_connection(str(path))) as db:
                    device, = _device_ids(db)
                target = selected / str(device) / path.name
                target.parent.mkdir(parents=True, exist_ok=True)
                if device in pending:
                    fact = export_identity(path, path.parent, target)
                    evidence.append({k: fact[k] for k in ("device_id", "encoding", "correlated_tasks", "batch_counts",
                        "source_sha256", "vendor_sha256", "semantic_input_used", "temporal_matching_used")} | {"node_id": node["node_id"]})
                else:
                    shutil.copy2(path, target)
                for name in ("start_info", "end_info"):
                    metadata = path.parent / "host" / name
                    if metadata.is_file():
                        (target.parent / "host").mkdir(exist_ok=True)
                        shutil.copy2(metadata, target.parent / "host" / name)
            node["msprof_db_dir"] = str(selected.resolve())
        nodes.append(node)
    return replace(capture, manifest=dict(capture.manifest, nodes=nodes), identity_exports=tuple(evidence))


def _sdk_logs(directory):
    records = []
    if directory.is_dir():
        for path in sorted(directory.glob("rank-*.jsonl")):
            with path.open(encoding="utf-8-sig") as stream:
                first = next((line for line in stream if line.strip()), "")
            if first:
                first = json.loads(first)
                if first.get("event") == "runtime" and first.get("schema_version") == 1:
                    records.append((path.resolve(), first))
    return records


def discover_capture(source, work, *, topology=None, manifest_path=None):
    source, work = Path(source).resolve(), Path(work)
    if not source.exists():
        raise ValueError("capture input does not exist")
    root = source.parent if source.is_file() else source
    selected = Path(manifest_path).resolve() if manifest_path else (
        source if source.is_file() else root / "manifest.json")
    logs, runtimes = [], []
    if selected.is_file():
        manifest = load_manifest(selected)
        for node in manifest["nodes"]:
            calls = Path(node.get("calls_dir", str(Path(node["plog_dir"]).parent / "calls")))
            if not calls.is_absolute():
                calls = selected.parent / calls
            logs.extend(_sdk_logs(calls))
    else:
        metadata = read_json(root / "capture.json") if (root / "capture.json").is_file() else {}
        node_items = metadata.get("nodes")
        if node_items is None:
            folder = root / "nodes"
            if not folder.is_dir():
                raise ValueError("provide nodes/<node>/plog + msprof, or --manifest for legacy data")
            node_items = [dict(node_id=p.name) for p in sorted(folder.iterdir()) if p.is_dir()]
        nodes = []
        for item in node_items:
            name = _name(item["node_id"])
            folder = root / "nodes" / name
            node = dict(item, plog_dir=str((root / item["plog_dir"]).resolve()) if "plog_dir" in item else str(folder / "plog"),
                        msprof_db_dir=str((root / item["msprof_db_dir"]).resolve()) if "msprof_db_dir" in item else str(folder / "msprof"))
            if "clock_probe_files" in node:
                node["clock_probe_files"] = [str((root / p).resolve()) for p in node["clock_probe_files"]]
            nodes.append(node)
            calls = root / item["calls_dir"] if "calls_dir" in item else folder / "calls"
            logs.extend(_sdk_logs(calls))
            if (folder / "runtime.json").is_file():
                runtime = read_json(folder / "runtime.json")
                runtimes.extend(dict(r, node_id=name) for r in runtime["ranks"])
        ranks = metadata.get("ranks", runtimes)
        if not ranks and logs:
            ranks = [{k: r[k] for k in ("node_id", "user_rank", "device_id")} for _, r in logs]
        ids = {r["run_id"] for _, r in logs}
        if len(ids) > 1:
            raise ValueError("SDK logs belong to different runs")
        run_id = metadata.get("run_id", next(iter(ids)) if ids else root.name)
        if ids and ids != {run_id}:
            raise ValueError("capture run_id disagrees with SDK runtime observations")
        manifest = dict(run_id=_name(run_id), nodes=nodes, ranks=ranks, operations=metadata.get("operations", []))
    if topology:
        explicit = read_json(topology)
        if "ranks" not in explicit:
            raise ValueError("topology needs explicit ranks, not a machine/card count")
        observed = {(r["node_id"], r["user_rank"], r["device_id"]) for r in manifest["ranks"]}
        supplied = {(r["node_id"], r["user_rank"], r["device_id"]) for r in explicit["ranks"]}
        if observed and observed != supplied:
            raise ValueError("topology conflicts with capture rank/device observations")
        manifest["ranks"] = explicit["ranks"]
        if "operations" in explicit:
            if manifest.get("operations") and explicit["operations"] != manifest["operations"]:
                raise ValueError("conflicting operation bindings")
            manifest["operations"] = explicit["operations"]
    if not manifest["ranks"]:
        raise ValueError("rank/device evidence missing: record SDK/runtime metadata or provide --topology")
    identities = {(r["node_id"], r["user_rank"], r["device_id"]) for r in manifest["ranks"]}
    seen_logs = set()
    for path, runtime in logs:
        key = tuple(runtime[k] for k in ("node_id", "user_rank", "device_id"))
        if key not in identities or key in seen_logs or runtime["run_id"] != manifest["run_id"]:
            raise ValueError("SDK runtime identity conflicts with capture metadata")
        seen_logs.add(key)
    for node in manifest["nodes"]:
        if not Path(node["plog_dir"]).is_dir():
            raise ValueError("missing semantic plog directory for " + node["node_id"])
        devices = set()
        for db_path in discover_db_files(node["msprof_db_dir"]):
            with closing(_readonly_connection(str(db_path))) as db:
                _validate_contract(db, str(db_path))
                ids = _device_ids(db)
                if len(ids) != 1 or devices.intersection(ids):
                    raise ValueError("need unique foreground per-device DBs; do not mix background captures")
                devices.update(ids)
        declared = {r["device_id"] for r in manifest["ranks"] if r["node_id"] == node["node_id"]}
        if declared != devices:
            raise ValueError("declared devices differ from actual DB devices on " + node["node_id"])
    path = work / "discovered.json"
    write_json(path, manifest)
    manifest = load_manifest(path)
    return Capture(manifest, tuple(path for path, _ in logs),
                   root / "iteration-map.json" if (root / "iteration-map.json").is_file() else None,
                   root / "preparation-map.json" if (root / "preparation-map.json").is_file() else None,
                   root / "operation-map.json" if (root / "operation-map.json").is_file() else None)
