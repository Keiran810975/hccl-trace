"""Publish exactly three self-contained reports; never remove capture inputs."""
from __future__ import annotations

from html.parser import HTMLParser
import json
from pathlib import Path
import shutil
import tempfile

from . import visualize_dependency_graph as graph
from . import visualize_html as view
from . import analyze_waits as waits
from . import source_propagation as propagation
from . import source_propagation_view as presentation
from .capture_discovery import read_json, write_json


FINAL_FILES = {"execution.html", "root_causes.json", "propagation.html"}


def host_source_displays(roots, rows, model, alignment=None):
    facts = {r["_graph_id"]: r for r in rows}
    displays = {n["id"]: n for n in model["nodes"]}
    clocks = {}
    if alignment is not None:
        from .clock_alignment import models_from_report
        clocks = models_from_report(alignment)
    result = {}
    for root in roots:
        if root["component"] != "host_preparation":
            continue
        anchor, shown = facts[root["graph_id"]], displays[root["graph_id"]]
        start, stop, origin = root["observed_start_ns"], root["observed_stop_ns"], waits.ns(anchor, "start")
        clock = clocks.get((root["node_id"], root["device_id"]))
        convert = clock.map_ns if clock is not None else lambda value: value
        result[root["graph_id"]] = dict(nodeId=root["node_id"], rank=root["user_rank"], device=root["device_id"],
            anchorRelative=True, startUs=shown["relativeStart"] + (convert(start) - convert(origin)) / 1000,
            stopUs=shown["relativeStart"] + (convert(stop) - convert(origin)) / 1000,
            durationUs=(stop - start) / 1000, startNs=str(start), stopNs=str(stop))
    return result


class _References(HTMLParser):
    def handle_starttag(self, tag, attrs):
        for key, value in attrs:
            if key not in {"src", "href"} or value is None:
                continue
            if value.startswith("#") or value.startswith("data:"):
                continue
            if value.split("#", 1)[0] not in FINAL_FILES:
                raise ValueError("report references a missing/external resource: " + value)


def validate_final(directory):
    if {p.name for p in directory.iterdir()} != FINAL_FILES:
        raise ValueError("final report must contain exactly three files")
    result = read_json(directory / "root_causes.json")
    if result.get("schema_version") != 1 or not isinstance(result.get("candidates"), list):
        raise ValueError("invalid normalized root-cause report")
    for name in ("execution.html", "propagation.html"):
        text = (directory / name).read_text(encoding="utf-8")
        if "<!doctype html>" not in text.lower() or "<script" not in text:
            raise ValueError("report is not a standalone HTML document")
        _References().feed(text)


def publish_final_report(directory, output, normalized, roots, comparisons):
    directory, output = Path(directory), Path(output)
    if output.exists() or output.is_symlink():
        raise FileExistsError("refusing to overwrite existing report: " + str(output))
    rows = graph.read_graph_artifact_nodes(directory / "dep_graph_nodes.csv")
    edges = graph.read_graph_artifact_edges(directory / "dep_graph_edges.csv")
    report = propagation.build_report(rows, edges, roots, comparisons,
        primary_source_candidate_id=normalized["primary_candidate_id"], reference=normalized["reference"])
    by_id = {c["candidate_id"]: c for c in report["candidates"]}
    for candidate in normalized["candidates"]:
        candidate["chain_ids"] = [c["chain_id"] for c in by_id[candidate["id"]]["chains"]]
    normalized["propagation"] = dict(report["summary"], exhaustive_downstream_search=False,
                                     physical_causation_proven=False)
    diagnosis = read_json(directory / "diagnosis.json")
    diagnosis.update(candidates=[dict(r, id=r["root_id"], category=r["component"], evidence=r["reason"]) for r in roots],
                     coverage=normalized["coverage"], diagnosis_status=normalized["diagnosis_status"],
                     primary_source_candidate_id=normalized["primary_candidate_id"])
    related = {}
    for root in roots:
        for target in root.get("affected_wait_graph_ids", []):
            related.setdefault(target, []).append(root)
    for wait in diagnosis["waits"]:
        sources = related.get(wait["wait_graph_id"], [])
        wait.update(candidate_ids=";".join(r["root_id"] for r in sources),
            candidate_graph_ids=";".join(r["graph_id"] for r in sources),
            evidence_path_edge_ids=";".join(dict.fromkeys(e for r in sources
                for e in r["evidence_paths"].get(wait["wait_graph_id"], []))))
        if sources:
            wait["classification"] = "upstream_slow_candidate"
    alignment = read_json(directory / "clock_alignment.json") if (directory / "clock_alignment.json").is_file() else None
    model = view.build_execution_dependency_model(rows, edges,
        view.read_operation_timings(directory / "operation_timings.csv"), alignment=alignment)
    model.update(graphView="execution", issueCount=len(waits.read_csv(directory / "dep_graph_notify_ambiguities.csv")))
    normalized["quality"]["notify_ambiguity_count"] = model["issueCount"]
    view.attach_diagnosis(model, diagnosis, diagnosis["waits"], "execution")
    model["waits"] = diagnosis["waits"]
    node_roles, paths = {}, {}
    for root in report["candidates"]:
        anchor = root["anchor_graph_id"]
        paths.setdefault(anchor, [])
        for chain in root["chains"]:
            paths[anchor].extend(chain["edge_ids"])
            for key in chain["node_ids"]:
                node_roles.setdefault(key, "chain")
            node_roles[chain["target_wait_graph_id"]] = "wait"
        node_roles[anchor] = "host_anchor" if root["source"]["component"] == "host_preparation" else "candidate"
    for node in model["nodes"]:
        if node["id"] in node_roles:
            node["diagnosisRole"] = node_roles[node["id"]]
    model["candidatePathEdges"] = {key: list(dict.fromkeys(value)) for key, value in paths.items()}
    model["observedHostSources"] = host_source_displays(roots, rows, model, alignment)
    primary = next((r for r in roots if r["root_id"] == normalized["primary_candidate_id"]), None)
    if primary:
        model["initialSelection"] = primary["graph_id"]
    model["caseNote"] = "Reference: " + ("previous five measured iteration mean" if normalized["mode"] == "rolling" else "independent baseline median (explicit or structural reference)")
    output.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix="." + output.name + "-", dir=str(output.parent)))
    try:
        write_json(stage / "root_causes.json", normalized)
        view.write_html(stage / "execution.html", "HCCL execution", model)
        (stage / "propagation.html").write_text(presentation.render_html(report, standalone=True), encoding="utf-8")
        validate_final(stage)
        if output.exists() or output.is_symlink():
            raise FileExistsError("report appeared during analysis; refusing to overwrite it")
        # mkdtemp is private (0700); publication should respect the destination
        # parent's read/traverse policy without granting additional write access.
        stage.chmod(output.parent.stat().st_mode & 0o755)
        stage.rename(output)
    finally:
        if stage.exists():
            shutil.rmtree(stage)
    return normalized
