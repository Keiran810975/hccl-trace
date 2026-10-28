"""Keep one artifact-backed HTML excerpt after fixed diagnosis and evaluation."""
from __future__ import annotations

from decimal import Decimal
import hashlib
import json
from pathlib import Path
import shutil
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "hccl/tools"))
from diagnosis import analyze_waits as waits
from diagnosis import visualize_dependency_graph as graph
from diagnosis import visualize_html as view


def digest(path):
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def overlaps(row, lower, upper):
    start, stop = waits.ns(row, "start"), waits.ns(row, "stop")
    return lower <= start <= upper if start == stop else start <= upper and stop >= lower


def build_excerpt(rows, edges, operations, coordinates, report, diagnosis, case, windows):
    """Truth selects display context only, never the primary source or evaluation."""
    if len({r["_node_id"] for r in rows}) != 1:
        raise ValueError("single-node retention cannot mix independent node clocks")
    injection = case["injection"]
    coord = {c["operation_scope"]: c for c in coordinates}
    normal = injection["kind"] == "normal"
    display_iteration = min(25, max(c["iteration"] for c in coordinates if c["stage"] == "measured")) if normal else None
    selected_coord = (dict(iteration=display_iteration, block=0, bucket=0) if normal else injection)
    anchor_scopes = {scope for scope, c in coord.items() if c["stage"] == "measured"
                     and all(c[k] == selected_coord[k] for k in ("iteration", "block", "bucket"))}
    if len(anchor_scopes) != 1:
        raise ValueError("retention needs one independently bound anchor call")
    anchor_scope = next(iter(anchor_scopes))
    if normal:
        frame_scopes = {scope for scope, c in coord.items() if c["stage"] == "measured" and c["iteration"] == display_iteration}
        frame = [r for r in rows if r.get("_operation_scope") in frame_scopes]
        lower = min(waits.ns(r, "start") for r in frame)
        upper = max(waits.ns(r, "stop") for r in frame)
    else:
        if not windows:
            raise ValueError("anomaly retention requires captured injection windows")
        lower, upper = min(w["start_ns"] for w in windows), max(w["stop_ns"] for w in windows)
    lower, upper = max(0, lower - 20000000), upper + 20000000
    scopes = {r.get("_operation_scope") for r in rows if overlaps(r, lower, upper)} - {"", None}
    scopes.add(anchor_scope)
    primary = next((r for r in report["root_causes"] if r["root_id"] == report["primary_source_candidate_id"]), None)
    path_ids, path_nodes = set(), set()
    if primary:
        scopes.add(primary["operation_scope"])
        path_ids = {edge_id for path in primary["evidence_paths"].values() for edge_id in path}
        path_nodes = {key for edge in edges if edge["edge_id"] in path_ids for key in (edge["src"], edge["dst"])}
        scopes.update(r.get("_operation_scope") for r in rows if r["_graph_id"] in path_nodes and r.get("_operation_scope"))
    selected = [r for r in rows if r.get("_operation_scope") in scopes
                or r["_graph_id"] in path_nodes
                or not r.get("_operation_scope") and overlaps(r, lower, upper)]
    ids = {r["_graph_id"] for r in selected}
    links = [e for e in edges if e["src"] in ids and e["dst"] in ids]
    if path_ids - {e["edge_id"] for e in links}:
        raise ValueError("retention clipped a selected source-to-Wait evidence path")
    display_ops = [r for r in operations if r.get("_operation_scope") in scopes]
    model = view.build_execution_dependency_model(selected, links, display_ops)
    origin = min(waits.ns(r, "start") for r in selected + display_ops)
    local_waits = [w for w in diagnosis["waits"] if w["wait_graph_id"] in ids]
    candidates = [c for c in diagnosis["candidates"] if c["graph_id"] in ids]
    local_diagnosis = dict(diagnosis, waits=local_waits, candidates=candidates)
    model.update(graphView="waits", issueCount=None, waits=[])
    view.attach_diagnosis(model, local_diagnosis, local_waits, "waits")
    locations = []
    for window in windows:
        for rank in window["target_ranks"]:
            anchor = [r for r in selected if r["_user_rank"] == rank and r.get("_operation_scope") == anchor_scope]
            active = [r for r in selected if r["_user_rank"] == rank
                      and overlaps(r, window["start_ns"], window["stop_ns"])]
            streams = sorted({r["_stream_id"] for r in active if r["_stream_id"] >= 0})
            anchor_streams = sorted({r["_stream_id"] for r in anchor if r["_stream_id"] >= 0})
            locations.append(dict(node_id=window["node_id"], rank=rank,
                                  chart_start_ms=format(Decimal(window["start_ns"] - origin) / 1000000, "f"),
                                  chart_stop_ms=format(Decimal(window["stop_ns"] - origin) / 1000000, "f"),
                                  start_ns=window["start_ns"], stop_ns=window["stop_ns"],
                                  active_foreground_stream_ids=streams, anchor_collective_stream_ids=anchor_streams,
                                  anchor_operation_scope=anchor_scope,
                                  stream_meaning="Foreground streams in this HTML; a host sleep has no device stream. Background stream IDs are not inferred."))
    scope_note = "Recorded dependency excerpt; full measured run used for diagnosis"
    notes = [scope_note, "0 = first retained task/operation, not iteration start"]
    for location in locations:
        notes.append("Injected node0 rank {}: {}..{} ms; active foreground streams {}; anchor call streams {}".format(
            location["rank"], location["chart_start_ms"], location["chart_stop_ms"],
            location["active_foreground_stream_ids"], location["anchor_collective_stream_ids"]))
    model["clockLabel"] = "single-node recorded dependency excerpt"
    model["caseNote"] = ". ".join(notes)
    model["caseInfo"] = dict(case_id=case["case_id"], injection=injection, injection_locations=locations,
                             chart_origin_ns=origin, primary_source_candidate_id=report["primary_source_candidate_id"],
                             complete_workload_graph=False, clipped_edge_count=len(edges) - len(links))
    if primary:
        model["initialSelection"] = primary["graph_id"]
        model["focusEdgeIds"] = list(dict.fromkeys(e for path in primary["evidence_paths"].values() for e in path))
        if primary["component"] == "host_preparation":
            model["observedHostSource"] = dict(nodeId=primary["node_id"], rank=primary["user_rank"], device=primary["device_id"],
                startUs=(primary["observed_start_ns"] - origin) / 1000,
                stopUs=(primary["observed_stop_ns"] - origin) / 1000, durationUs=primary["duration_ns"] / 1000)
            model["caseNote"] += ". Red bracket = diagnosed public Host preparation interval, not a device kernel; selected task is its device dependency anchor."
    summary = dict(injection_locations=locations, chart_origin_ns=origin, primary_source=primary,
                   original_node_count=len(rows), retained_node_count=len(selected), retained_edge_count=len(links),
                   anchor_operation_scope=anchor_scope, complete_workload_graph=False,
                   baseline_display_iteration=display_iteration)
    return model, summary


def retain_case(directory):
    if Path(directory).is_symlink():
        raise ValueError("refusing a symlink attempt")
    directory = Path(directory).resolve()
    if (not (directory / "runner.json").is_file()
            or json.loads((directory / "runner.json").read_text()).get("output") != str(directory)):
        raise ValueError("retention only accepts a newly generated owned attempt")
    result = json.loads((directory / "result.json").read_text())
    if not result.get("strict_diagnosis_success") or not result.get("execution_success"):
        raise ValueError("cannot prune a failed or incomplete case")
    diagnosis_dir = Path(result["diagnosis_directory"]).resolve()
    if directory not in diagnosis_dir.parents:
        raise ValueError("diagnosis is outside this attempt")
    case = json.loads((directory / "private/case.json").read_text())
    windows = json.loads((directory / "private/actual-windows.json").read_text())
    coordinates = json.loads((directory / "iteration-map.json").read_text())["operations"]
    report = json.loads((diagnosis_dir / "rolling/report.json").read_text())
    diagnosis = json.loads((diagnosis_dir / "diagnosis.json").read_text())
    rows = graph.read_graph_artifact_nodes(diagnosis_dir / "dep_graph_nodes.csv")
    edges = graph.read_graph_artifact_edges(diagnosis_dir / "dep_graph_edges.csv")
    operations = view.read_operation_timings(diagnosis_dir / "operation_timings.csv")
    model, summary = build_excerpt(rows, edges, operations, coordinates, report, diagnosis, case, windows)
    output = directory / "retained"
    output.mkdir(exist_ok=False)
    summary.update(case_id=case["case_id"], injection_kind=case["injection"]["kind"],
                   evaluation=result["temporal_evaluation"], pipeline=json.loads((diagnosis_dir / "pipeline_result.json").read_text()),
                   retention_policy="baseline_full_capture_preserved" if case["injection"]["kind"] == "normal" else "html_and_small_evidence_only")
    view.write_html(output / "dependency.html", case["case_id"], model)
    # Validate that the native self-contained view contains the exact selected graph, not an external data reference.
    page = (output / "dependency.html").read_text()
    payload = json.JSONDecoder().raw_decode(page.split("const model=", 1)[1])[0]
    payload_ids = {n["id"] for n in payload["nodes"]}
    if (len(payload["nodes"]) != len(model["nodes"]) or len(payload["edges"]) != len(model["edges"])
            or not payload["edges"] or any(e["src"] not in payload_ids or e["dst"] not in payload_ids for e in payload["edges"])):
        raise ValueError("retained HTML model integrity failed; raw inputs retained")
    summary["html_sha256"] = digest(output / "dependency.html")
    summary["source_input_sha256"] = {str(p.relative_to(directory)): digest(p)
                                      for p in (directory / "foreground-dbs").glob("*.db")}
    shutil.copy2(diagnosis_dir / "merge_summary.csv", output / "merge_summary.csv")
    shutil.copy2(diagnosis_dir / "dep_graph_summary.csv", output / "graph_summary.csv")
    summary["propagation_files"] = []
    for name in ("report.json", "chains.csv", "steps.csv", "chains.md"):
        source = diagnosis_dir / "propagation" / name
        if source.is_file():
            destination = output / ("propagation-" + name)
            shutil.copy2(source, destination)
            summary["propagation_files"].append(destination.name)
    for name, data in (("case-summary.json", summary), ("primary-source.json", summary["primary_source"])):
        (output / name).write_text(json.dumps(data, indent=2) + "\n")
    if case["injection"]["kind"] != "normal":
        cleanup_names = ["msprof", "ascend_log", "foreground-dbs", "diagnosis"]
        recovered = diagnosis_dir.relative_to(directory).parts[0]
        if recovered != "diagnosis":
            if not recovered.startswith("diagnosis-recovered-"):
                raise ValueError("unexpected recovered diagnosis directory")
            cleanup_names.append(recovered)
        for name in cleanup_names:
            path = directory / name
            if not path.is_dir() or path.is_symlink() or directory not in path.resolve().parents:
                raise ValueError("refusing cleanup outside the owned attempt")
        for name in cleanup_names:
            shutil.rmtree(directory / name)
    return summary
