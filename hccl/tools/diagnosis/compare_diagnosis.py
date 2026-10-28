#!/usr/bin/env python3
"""Baseline deltas, evidence-bounded source candidates and paired trace windows."""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict, deque
from dataclasses import asdict, dataclass
from decimal import Decimal
import html
import json
import os
from pathlib import Path
import sys
import xml.etree.ElementTree as ET

if __package__ in (None, ""):
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from diagnosis import analyze_waits as waits
    from diagnosis import visualize_dependency_graph as graph
    from diagnosis import visualize_html as view
    from diagnosis.dependency_model import stable_id
    from diagnosis.schema import write_csv
else:
    from . import analyze_waits as waits
    from . import visualize_dependency_graph as graph
    from . import visualize_html as view
    from .dependency_model import stable_id
    from .schema import write_csv


@dataclass(frozen=True)
class ComparisonOptions:
    min_increase_ns: int = 10000
    slowdown_factor: str = "1.5"
    context_ns: int = 100000
    max_figures: int = 5
    traversal_limit: int = 4096

    def validate(self):
        factor = Decimal(self.slowdown_factor)
        if not factor.is_finite() or factor <= 1:
            raise ValueError("comparison slowdown factor must be finite and > 1")
        if self.min_increase_ns <= 0 or self.context_ns < 0 or self.max_figures < 0 or self.traversal_limit <= 0:
            raise ValueError("invalid comparison thresholds/window/limits")


def task_signature(row):
    # Never use physical task IDs, stream IDs, Notify IDs or timestamps across runs.
    return tuple(str(row.get(key, "")) for key in (
        "_user_rank", "_peer_rank", "algorithm", "phase", "step", "slice", "event",
        "semantic", "profiler_task_kind", "profiler_size_bytes"))


def operation_groups(rows):
    result = defaultdict(list)
    for row in rows:
        if row.get("_operation_scope"):
            result[row["_operation_scope"]].append(row)
    return result


def operation_shape(rows):
    return stable_id("comparison_shape", tuple(sorted(Counter(task_signature(row) for row in rows).items())))


def median(values):
    values = sorted(Decimal(value) for value in values)
    n = len(values)
    return (values[(n - 1) // 2] + values[n // 2]) / 2


def load_operation_map(path):
    if path is None:
        return []
    data = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    if data.get("schema_version") != 1 or not isinstance(data.get("operation_pairs"), list):
        raise ValueError("operation map requires schema_version=1 and operation_pairs")
    return data["operation_pairs"]


def local_gaps(rows, edges):
    nodes = {row["_graph_id"]: row for row in rows}
    predecessors = defaultdict(list)
    for edge in edges:
        if edge["kind"] != "direct_stream_order_observed" or edge.get("confidence") not in ("observed", "exact"):
            continue
        src, dst = nodes[edge["src"]], nodes[edge["dst"]]
        if (src.get("_operation_scope") and src["_operation_scope"] == dst.get("_operation_scope")
                and all(src[k] == dst[k] for k in ("_node_id", "_device_id", "_stream_id"))):
            predecessors[edge["dst"]].append(src)
    return {key: waits.ns(nodes[key], "start") - waits.ns(group[0], "stop")
            for key, group in predecessors.items() if len(group) == 1
            and waits.ns(nodes[key], "start") >= waits.ns(group[0], "stop")}


def compare_tasks(rows, baseline_rows, options, operation_pairs=(), current_gaps=None, baseline_gaps=None):
    options.validate()
    current_gaps, baseline_gaps = current_gaps or {}, baseline_gaps or {}
    current_ops, baseline_ops = operation_groups(rows), operation_groups(baseline_rows)
    pairs, baseline_seen = {}, set()
    for pair in operation_pairs:
        current, baseline = pair.get("current_scope"), pair.get("baseline_scope")
        if (current not in current_ops or baseline not in baseline_ops or not str(pair.get("evidence", "")).strip()
                or current in pairs or baseline in baseline_seen):
            raise ValueError("operation pairs must be evidenced, known and one-to-one")
        pairs[current] = pair
        baseline_seen.add(baseline)
    current_shapes = {key: operation_shape(value) for key, value in current_ops.items()}
    reference = defaultdict(list)
    for scope, group in baseline_ops.items():
        shape = operation_shape(group)
        for row in group:
            reference[("shape", shape, task_signature(row))].append(row)
            reference[("operation", scope, task_signature(row))].append(row)
    statistics = {}
    comparisons = []
    for row in rows:
        scope = row.get("_operation_scope", "")
        pair = pairs.get(scope)
        key = (("operation", pair["baseline_scope"], task_signature(row)) if pair else
               ("shape", current_shapes.get(scope), task_signature(row)))
        item = dict(graph_id=row["_graph_id"], node_id=row["_node_id"], user_rank=row["_user_rank"],
                    device_id=row["_device_id"], stream_id=row["_stream_id"], task_id=row["_task_id"],
                    operation_scope=scope, algorithm=row.get("algorithm", ""), phase=row.get("phase", ""),
                    step=row.get("step", ""), event=row.get("event", ""),
                    task_kind=row.get("profiler_task_kind", ""), duration_ns=waits.duration(row),
                    comparison_status="no_compatible_baseline", baseline_count=0,
                    baseline_median_ns=None, baseline_mad_ns=None, baseline_min_ns=None, baseline_max_ns=None,
                    baseline_graph_id="", baseline_operation_scope="", delta_ns=None, slowdown_factor=None,
                    duration_slow=False, gap_before_ns=current_gaps.get(row["_graph_id"]),
                    baseline_gap_median_ns=None, baseline_gap_mad_ns=None, gap_delta_ns=None,
                    baseline_gap_graph_id="", baseline_gap_operation_scope="", gap_slow=False,
                    is_slow=False, reference_evidence=pair["evidence"] if pair else "matching operation structure and task semantics; statistical reference, not task identity")
        samples = reference.get(key, []) if scope else []
        if samples:
            if key not in statistics:
                ordered = sorted(samples, key=lambda r: (waits.duration(r), r["_graph_id"]))
                values = [waits.duration(r) for r in ordered]
                center = median(values)
                gap_samples = sorted((r for r in samples if r["_graph_id"] in baseline_gaps),
                                     key=lambda r: (baseline_gaps[r["_graph_id"]], r["_graph_id"]))
                gap_center = median([baseline_gaps[r["_graph_id"]] for r in gap_samples]) if gap_samples else None
                gap_mad = median([abs(Decimal(baseline_gaps[r["_graph_id"]]) - gap_center) for r in gap_samples]) if gap_samples else None
                statistics[key] = (center, median([abs(Decimal(v) - center) for v in values]),
                                   min(values), max(values), ordered[(len(ordered) - 1) // 2],
                                   gap_center, gap_mad, gap_samples[(len(gap_samples) - 1) // 2] if gap_samples else None)
            center, mad, low, high, representative, gap_center, gap_mad, gap_representative = statistics[key]
            delta = Decimal(item["duration_ns"]) - center
            item.update(comparison_status="explicit_operation_reference" if pair else "structural_reference",
                        baseline_count=len(samples), baseline_median_ns=str(center), baseline_mad_ns=str(mad),
                        baseline_min_ns=low, baseline_max_ns=high, delta_ns=str(delta),
                        baseline_graph_id=representative["_graph_id"],
                        baseline_operation_scope=representative["_operation_scope"],
                        slowdown_factor=str(Decimal(item["duration_ns"]) / center) if center else None,
                        duration_slow=(delta >= max(Decimal(options.min_increase_ns), 3 * mad)
                                       and Decimal(item["duration_ns"]) >= center * Decimal(options.slowdown_factor)))
            if item["gap_before_ns"] is not None and gap_center is not None:
                gap_delta = Decimal(item["gap_before_ns"]) - gap_center
                item.update(baseline_gap_median_ns=str(gap_center), baseline_gap_mad_ns=str(gap_mad),
                            baseline_gap_graph_id=gap_representative["_graph_id"],
                            baseline_gap_operation_scope=gap_representative["_operation_scope"],
                            gap_delta_ns=str(gap_delta),
                            gap_slow=(gap_delta >= max(Decimal(options.min_increase_ns), 3 * gap_mad)
                                      and Decimal(item["gap_before_ns"]) >= gap_center * Decimal(options.slowdown_factor)))
            item["is_slow"] = item["duration_slow"] or item["gap_slow"]
        comparisons.append(item)
    return comparisons


def evidence_adjacency(rows, edges, *, cross_operations=False):
    nodes = {row["_graph_id"]: row for row in rows}
    stats = graph.analyze_execution_graph(rows, edges)
    graph._assert_execution_graph_integrity(stats)
    if stats["has_cycle"]:
        raise ValueError("comparison requires an acyclic execution graph")
    incoming, outgoing = defaultdict(list), defaultdict(list)
    for edge in sorted(edges, key=lambda e: e["edge_id"]):
        if (edge.get("confidence") not in ("observed", "exact")
                or not (edge["kind"] == "direct_stream_order_observed" or "notify_sync" in edge["kind"])):
            continue
        src, dst = nodes[edge["src"]], nodes[edge["dst"]]
        if not cross_operations and (not src.get("_operation_scope") or src["_operation_scope"] != dst.get("_operation_scope")):
            continue
        incoming[edge["dst"]].append((edge["src"], edge["edge_id"]))
        outgoing[edge["src"]].append((edge["dst"], edge["edge_id"]))
    return nodes, incoming, outgoing


def reachable(start, adjacency, limit):
    paths, queue = {start: []}, deque([start])
    while queue and len(paths) < limit:
        current = queue.popleft()
        for other, edge_id in adjacency[current]:
            if other not in paths:
                if len(paths) >= limit:
                    return paths, True
                paths[other] = paths[current] + [edge_id]
                queue.append(other)
    return paths, bool(queue)


def find_sources(rows, edges, comparisons, options):
    nodes, incoming, outgoing = evidence_adjacency(rows, edges)
    sync_ids = {e["edge_id"] for e in edges if "notify_sync" in e["kind"]}
    changes = {item["graph_id"]: item for item in comparisons if item["is_slow"]}
    changed_waits = {key for key in changes if changes[key]["duration_slow"] and nodes[key].get("profiler_task_kind") == "notify_wait"}
    # Kernel envelopes and RDMA doorbells cannot prove where payload execution slowed.
    changed_work = {key for key in changes if changes[key]["duration_slow"] and nodes[key].get("profiler_task_kind") in ("sdma", "reduce_inline")}
    changed_gaps = {key for key in changes if changes[key]["gap_slow"]}
    causal_changes = changed_work | changed_waits | changed_gaps
    roots, covered, roles = [], set(), {}
    for key in sorted(changed_work | changed_gaps):
        ancestors, truncated = reachable(key, incoming, options.traversal_limit)
        upstream = (set(ancestors) & causal_changes) - {key}
        paths, forward_truncated = reachable(key, outgoing, options.traversal_limit)
        incomplete = truncated or forward_truncated
        # Stream order proves reachability, not that this task produced the
        # notification being awaited. Require the final real synchronization edge.
        release_paths = {}
        for target in sorted((changed_waits & set(paths)) - {key}):
            choices = [paths[producer] + [edge_id] for producer, edge_id in incoming[target]
                       if edge_id in sync_ids and producer in paths]
            if choices:
                release_paths[target] = min(choices, key=lambda path: (len(path), tuple(path)))
        affected = sorted(release_paths)
        if key in changed_work:
            if not affected and upstream & changed_work:
                roles[key] = "downstream_slow_task"
            else:
                status = ("insufficient_evidence" if incomplete else
                          "dependency_supported_candidate" if affected else "isolated_slow_task")
                roles[key] = "source_candidate"
                roots.append(dict(changes[key], root_id=stable_id("root", (key, "execution")),
                    component="execution", status=status,
                    reason="Local execution duration increased; a producer-to-Wait path is required for dependency support; physical cause remains unknown",
                    upstream_slow_graph_ids=sorted(upstream), affected_wait_graph_ids=affected,
                    evidence_paths=release_paths, traversal_truncated=incomplete, physical_cause="unknown"))
                if status == "dependency_supported_candidate":
                    covered.update(affected)
        if key in changed_gaps:
            # A gap has no observed executing owner. It can include scheduling,
            # unrepresented work or propagated blocking; size alone cannot name a root.
            roles.setdefault(key, "unattributed_gap")
            root = dict(changes[key], root_id=stable_id("root", (key, "gap")),
                        component="pre_task_gap", status="unattributed_gap",
                        reason="Observed gap before this task; no executing owner or causal attribution is established. Retained as an observation, not a primary source",
                        upstream_slow_graph_ids=sorted(upstream), affected_wait_graph_ids=[], evidence_paths={},
                        reachable_wait_graph_ids=sorted((changed_waits & set(paths)) - {key}),
                        traversal_truncated=incomplete, physical_cause="unknown")
            root.update(duration_ns=changes[key]["gap_before_ns"], baseline_median_ns=changes[key]["baseline_gap_median_ns"],
                        delta_ns=changes[key]["gap_delta_ns"], baseline_graph_id=changes[key]["baseline_gap_graph_id"],
                        baseline_operation_scope=changes[key]["baseline_gap_operation_scope"],
                        slowdown_factor=str(Decimal(changes[key]["gap_before_ns"]) / Decimal(changes[key]["baseline_gap_median_ns"]))
                        if Decimal(changes[key]["baseline_gap_median_ns"]) else None)
            roots.append(root)
    for key in sorted(changed_waits - covered):
        producers = [(other, edge) for other, edge in incoming[key] if edge in sync_ids]
        roots.append(dict(changes[key], root_id=stable_id("boundary", (key,)),
                          component="wait_boundary",
                          status="unresolved_upstream", reason="Wait grew, but no upstream slow execution with a producer-to-Wait path was established; gaps remain unattributed and the producer is a boundary, not a proved root cause",
                          producer_graph_ids=[other for other, _ in producers],
                          affected_wait_graph_ids=[key], evidence_paths={key: [edge for _, edge in producers]},
                          traversal_truncated=False, physical_cause="unknown"))
        roles[key] = "unresolved_wait"
    for item in comparisons:
        key = item["graph_id"]
        item["role"] = roles.get(key, "propagated_wait" if key in covered else
                                 "slow_unattributed_task" if item["is_slow"] else "not_flagged")
    priority = {"dependency_supported_candidate": 0, "isolated_slow_task": 1,
                "unresolved_upstream": 2, "unattributed_gap": 3, "insufficient_evidence": 4}
    return sorted(roots, key=lambda r: (priority[r["status"]], -Decimal(r["delta_ns"]), r["root_id"]))


def analyze(rows, edges, baseline_rows, options=ComparisonOptions(), operation_pairs=(), *, baseline_edges=()):
    options.validate()
    # Rank membership/topology matters; capture-specific node names do not.
    def topology(values):
        groups = defaultdict(set)
        for row in values:
            if row["_user_rank"] >= 0:
                groups[row["_node_id"]].add(row["_user_rank"])
        return sorted(tuple(sorted(group)) for group in groups.values())
    if topology(rows) != topology(baseline_rows):
        raise ValueError("baseline and anomaly rank/node topology differ")
    if len({r["_graph_id"] for r in baseline_rows}) != len(baseline_rows):
        raise ValueError("duplicate baseline execution identity")
    tasks = compare_tasks(rows, baseline_rows, options, operation_pairs, local_gaps(rows, edges),
                          local_gaps(baseline_rows, baseline_edges))
    roots = find_sources(rows, edges, tasks, options)
    compared = sum(t["baseline_count"] > 0 for t in tasks)
    primary = next((r["root_id"] for r in roots if r["status"] == "dependency_supported_candidate"
                    and not r["traversal_truncated"]), None)
    return dict(schema_version=1, source_policy_version=2, status="analyzed" if compared else "no_comparable_tasks",
                options=asdict(options), task_count=len(tasks), compared_task_count=compared,
                uncomparable_task_count=len(tasks) - compared,
                primary_source_candidate_id=primary,
                gap_observation_count=sum(r["status"] == "unattributed_gap" for r in roots),
                supported_execution_candidate_count=sum(r["status"] == "dependency_supported_candidate" for r in roots),
                source_status_counts=dict(Counter(r["status"] for r in roots)),
                slow_duration_count=sum(t["duration_slow"] for t in tasks),
                increased_gap_count=sum(t["gap_slow"] for t in tasks),
                slow_task_count=sum(t["is_slow"] for t in tasks), tasks=tasks, root_causes=roots,
                limits=["Roots are evidence-bounded source candidates, not automatically proved physical fault types.",
                        "Statistical baseline references do not assert cross-capture task/iteration identity.",
                        "Task durations and local gaps are tested separately against the configured floor, 3*MAD and baseline factor.",
                        "Only increased work execution with a path ending at an actual producer-to-Wait synchronization is dependency supported.",
                        "Gaps have no observed owner and are observations only, never primary sources; task and gap increases are separate components.",
                        "Candidates are ordered by path evidence then local execution increase; this is not a global temporal/causal ranking.",
                        "No cross-node absolute timestamp subtraction, global first task or global completion-time gain.",
                        "Submission gaps, network completion and background resource ownership may remain unobserved.",
                        "No injection truth is consumed by this analysis."])


def focus_model(rows, edges, scope, core_ids, context_ns, gap_highlight=None, *, include_path_scopes=False):
    scopes = {scope}
    if include_path_scopes:
        scopes.update(row.get("_operation_scope") for row in rows if row["_graph_id"] in core_ids and row.get("_operation_scope"))
    group = [row for row in rows if row.get("_operation_scope") in scopes or include_path_scopes and row["_graph_id"] in core_ids]
    origins = {}
    for row in group:
        origins[row["_node_id"]] = min(origins.get(row["_node_id"], waits.ns(row, "start")), waits.ns(row, "start"))
    core = [row for row in group if row["_graph_id"] in core_ids]
    if not core:
        raise ValueError("comparison focus endpoint not in selected operation")
    start = max(0, min(waits.ns(r, "start") - origins[r["_node_id"]] for r in core) - context_ns)
    stop = max(waits.ns(r, "stop") - origins[r["_node_id"]] for r in core) + context_ns
    if gap_highlight:
        anchor = next(r for r in core if r["_graph_id"] == gap_highlight[0])
        start = min(start, max(0, waits.ns(anchor, "start") - origins[anchor["_node_id"]] - gap_highlight[1] - context_ns))
    selected = [r for r in group if waits.ns(r, "stop") - origins[r["_node_id"]] >= start
                and waits.ns(r, "start") - origins[r["_node_id"]] <= stop]
    identifiers = {r["_graph_id"] for r in selected}
    selected_edges = [e for e in edges if e["src"] in identifiers and e["dst"] in identifiers]
    model = view.build_execution_dependency_model(selected, selected_edges)
    model["multipleOperationScopes"] = len(scopes) > 1
    by_id = {r["_graph_id"]: r for r in selected}
    for node in model["nodes"]:
        node["relativeStart"] = (waits.ns(by_id[node["id"]], "start") - origins[node["nodeId"]]) / 1000
        node["relativeStop"] = node["relativeStart"] + node["duration"]
        if gap_highlight and node["id"] == gap_highlight[0]:
            node["gapHighlightUs"] = gap_highlight[1] / 1000
            node["title"] += "\nObserved gap before task: {} us; cause unattributed".format(node["gapHighlightUs"])
    ranks = {(r["_node_id"], r["_device_id"], r["_stream_id"]): r["_user_rank"] for r in selected}
    for lane in model["lanes"]:
        node, device, stream = lane["key"].rsplit("|", 2)
        lane["label"] = "{} rank {} dev {} stream {}".format(node.rsplit("/", 1)[-1], ranks[(node, int(device), int(stream))], device, stream)
    return model, (start, stop)


def frame_model(model, window, highlighted, highlighted_edges):
    start, stop = (value / 1000 for value in window)
    span = max(1, stop - start)
    left = model["contentLeft"]
    scale = 1200 / span
    model.update(timeMin=start, timeMax=stop, timeScale=scale, width=left + 1216,
                 graphView="comparison", issueCount=None, initialSelection=highlighted,
                 focusEdgeIds=sorted(highlighted_edges), initialWindow=True,
                 clockLabel="Per-node selected-context-relative time; same scale in both panels; no cross-node time alignment" if model.get("multipleOperationScopes") else
                            "Per-node operation-relative time; clocks uncalibrated; same scale in both panels")
    for node in model["nodes"]:
        node["x"] = left + (node["relativeStart"] - start) * scale
        node["w"] = max(4, node["duration"] * scale)
        if node["id"] == highlighted:
            node["stroke"] = "#c62828"
    return model


def write_focus_svg(path, title, model, selected):
    ET.register_namespace("", "http://www.w3.org/2000/svg")
    def element(parent, tag, text=None, **attrs):
        child = ET.SubElement(parent, "{http://www.w3.org/2000/svg}" + tag,
                              {key.replace("_", "-"): str(value) for key, value in attrs.items()})
        child.text = text
        return child
    width, height, left = int(model["width"]), int(model["height"]), model["contentLeft"]
    root = ET.Element("{http://www.w3.org/2000/svg}svg", width=str(width), height=str(height),
                      viewBox="0 0 {} {}".format(width, height), role="img")
    element(root, "title", title)
    element(root, "rect", width=width, height=height, fill="white")
    element(root, "text", title, x=12, y=22, font_family="Arial", font_size=15, fill="#173b57")
    divisor, unit = (1000, "ms") if model["timeMax"] - model["timeMin"] >= 1000 else (1, "us")
    element(root, "text", "Operation-relative time / {}; node clocks are NOT aligned".format(unit), x=12, y=43,
            font_family="Arial", font_size=11, fill="#566573")
    for lane in model["lanes"]:
        element(root, "rect", x=0, y=lane["y"], width=width, height=lane["height"], fill="#f5f7fa")
        element(root, "text", lane["label"], x=10, y=lane["y"] + 17, font_size=11, font_family="Arial")
    for tick in range(9):
        x = left + tick * 150
        value = model["timeMin"] + (model["timeMax"] - model["timeMin"]) * tick / 8
        element(root, "line", x1=x, x2=x, y1=72, y2=height - 30, stroke="#d9e2eb")
        element(root, "text", "{:.3f}".format(value / divisor), x=x - 2 if tick == 8 else x + 2,
                y=67, font_family="Arial", font_size=11, text_anchor="end" if tick == 8 else "start")
    defs = element(root, "defs")
    marker = element(defs, "marker", id="arrow", viewBox="0 0 10 10", refX=9, refY=5,
                     markerWidth=5, markerHeight=5, orient="auto-start-reverse")
    element(marker, "path", d="M 0 0 L 10 5 L 0 10 z", fill="#007c91")
    by_id = {n["id"]: n for n in model["nodes"]}
    clip = element(defs, "clipPath", id="plot")
    element(clip, "rect", x=left, y=72, width=1200, height=height - 102)
    plot = element(root, "g", clip_path="url(#plot)")
    for edge in model["edges"]:
        if edge["id"] not in model["focusEdgeIds"]:
            continue
        src, dst = by_id[edge["src"]], by_id[edge["dst"]]
        x1, y1 = src["x"] + src["duration"] * model["timeScale"], src["y"] + 8
        x2, y2 = dst["x"], dst["y"] + 8
        bend = max(25, abs(x2 - x1) * .3)
        line = element(plot, "path", d="M {} {} C {} {}, {} {}, {} {}".format(x1, y1, x1 + bend, y1, x2 - bend, y2, x2, y2),
                       fill="none", stroke=edge["color"], stroke_width=2, marker_end="url(#arrow)")
        element(line, "title", edge["title"])
    for node in model["nodes"]:
        if node.get("gapHighlightUs") is not None:
            element(plot, "rect", x=node["x"] - node["gapHighlightUs"] * model["timeScale"],
                    y=node["y"] - 3, width=max(2, node["gapHighlightUs"] * model["timeScale"]),
                    height=node["h"] + 6, fill="none", stroke="#c62828", stroke_width=2, stroke_dasharray="4 3")
        rectangle = element(plot, "rect", x=node["x"], y=node["y"], width=max(2, node["duration"] * model["timeScale"]),
                            height=node["h"], fill=node["fill"], stroke="#c62828" if node["id"] == selected else node["stroke"],
                            stroke_width=3 if node["id"] == selected else 1)
        element(rectangle, "title", node["title"])
        if node["duration"] * model["timeScale"] > 90:
            element(plot, "text", node["label"], x=max(left, node["x"]) + 4, y=node["y"] + 12, font_size=10, font_family="Arial")
    ET.ElementTree(root).write(path, encoding="utf-8", xml_declaration=True)


def export_figures(report, rows, edges, baseline_rows, baseline_edges, directory, options):
    current = {r["_graph_id"]: r for r in rows}
    references = {r["_graph_id"]: r for r in baseline_rows}
    baseline_gaps = local_gaps(baseline_rows, baseline_edges)
    figures = []
    for index, root in enumerate(report["root_causes"][:options.max_figures], 1):
        key, baseline_id = root["graph_id"], root["baseline_graph_id"]
        if not baseline_id:
            continue
        paths = {edge for path in root["evidence_paths"].values() for edge in path}
        core = {key} | set(root["affected_wait_graph_ids"])
        core.update(endpoint for e in edges if e["edge_id"] in paths for endpoint in (e["src"], e["dst"]))
        gap = root["component"] == "pre_task_gap"
        model, window = focus_model(rows, edges, root["operation_scope"], core, options.context_ns,
                                    (key, root["duration_ns"]) if gap else None)
        baseline_scope = references[baseline_id]["_operation_scope"]
        baseline_core = {baseline_id}
        signatures = {task_signature(current[k]) for k in core}
        # Repeated matches stay visible as reference context, not guessed one-to-one endpoints.
        baseline_core.update(r["_graph_id"] for r in baseline_rows
                             if r.get("_operation_scope") == baseline_scope and task_signature(r) in signatures)
        reference_model, reference_window = focus_model(baseline_rows, baseline_edges, baseline_scope,
                                                       baseline_core, options.context_ns,
                                                       (baseline_id, baseline_gaps[baseline_id]) if gap else None)
        common = (min(window[0], reference_window[0]), max(window[1], reference_window[1]))
        baseline_path_edges = {e["edge_id"] for e in baseline_edges
                               if e["src"] in baseline_core and e["dst"] in baseline_core}
        name = "focus-{:03d}".format(index)
        for suffix, local, selected, links in (("anomaly", model, key, paths),
                                               ("baseline", reference_model, baseline_id, baseline_path_edges)):
            frame_model(local, common, selected, links)
            view.write_html(directory / (name + "-" + suffix + ".html"), suffix, local)
            write_focus_svg(directory / (name + "-" + suffix + ".svg"), suffix, local, selected)
        root["comparison_page"] = name + ".html"
        def time_text(value):
            value = Decimal(value)
            return "{:.3f} {}".format(value / (1000000 if abs(value) >= 1000000 else 1000),
                                     "ms" if abs(value) >= 1000000 else "us")
        caption = ("rank {} / {} / step {} / {} / {}: baseline {}, anomaly {}, increase {}. {}".format(
            root["user_rank"], root["phase"], root["step"], root["component"], root["status"],
            time_text(root["baseline_median_ns"]), time_text(root["duration_ns"]),
            time_text(root["delta_ns"]), root["reference_evidence"]))
        body = "<h1>Source comparison</h1><p>{}</p><p>Baseline image is one recorded representative, not the aggregate median. Both panels use the same scale. Node-local origins are independent; arrows show topology, not cross-node elapsed time.</p>".format(html.escape(caption))
        for suffix in ("baseline", "anomaly"):
            body += '<section><h2>{}</h2><a href="{}-{}.html">Interactive dependency trace</a><img alt="{} dependency window" src="{}-{}.svg"></section>'.format(suffix, name, suffix, suffix, name, suffix)
        write_page(directory / (name + ".html"), "Source comparison", body)
        figures.append(dict(root_id=root["root_id"], page=name + ".html", window_ns=common,
                            anomaly_graph_id=key, baseline_graph_id=baseline_id,
                            baseline_operation_scope=baseline_scope, reference_kind=root["comparison_status"]))
    return figures


def write_page(path, title, body):
    path.write_text('<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{}</title><style>body{{font:14px Arial,sans-serif;margin:24px;color:#203746;background:white}}h1{{font-size:24px}}h2{{font-size:18px}}p{{line-height:1.5}}section{{border-top:1px solid #d6e1ea;margin-top:24px;padding-top:12px}}img{{display:block;width:100%;height:auto;margin-top:12px}}table{{border-collapse:collapse;width:100%}}th,td{{text-align:left;border-bottom:1px solid #d6e1ea;padding:8px;overflow-wrap:anywhere}}th{{background:#edf4fa}}a{{color:#0063a4}}.scroll{{overflow-x:auto}}</style><body>{}</body></html>'.format(html.escape(title), body), encoding="utf-8")


def export_report(report, rows, edges, baseline_rows, baseline_edges, directory, options):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=False)
    report["figures"] = export_figures(report, rows, edges, baseline_rows, baseline_edges, directory, options)
    slow = sorted((r for r in report["tasks"] if r["is_slow"]), key=lambda r: (-Decimal(r["delta_ns"]), r["graph_id"]))
    for name, records in (("task_comparison", report["tasks"]), ("slow_tasks", slow), ("root_causes", report["root_causes"])):
        fields = list(dict.fromkeys(key for row in records for key in row)) if records else ["graph_id", "status"]
        values = [{key: json.dumps(value, ensure_ascii=False) if isinstance(value, (list, dict)) else value
                   for key, value in row.items()} for row in records]
        write_csv(str(directory / (name + ".csv")), fields, values)
    (directory / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    summary = ["# Baseline comparison", "", "Compared {} / {} tasks; {} flagged tasks/gaps.".format(
        report["compared_task_count"], report["task_count"], report["slow_task_count"]), "",
        "Source candidates are not proved physical causes. Full results: report.json and CSV.", ""]
    for root in report["root_causes"]:
        summary.append("- Rank {} / {} / step {} / task {} / {}: {} -> {} us (+{} us); {}. {}".format(
            root["user_rank"], root["phase"], root["step"], root["task_id"], root["component"],
            Decimal(root["baseline_median_ns"]) / 1000, Decimal(root["duration_ns"]) / 1000,
            Decimal(root["delta_ns"]) / 1000, root["status"], root.get("comparison_page", "no figure")))
    (directory / "summary.md").write_text("\n".join(summary) + "\n", encoding="utf-8")
    body = '<h1>Baseline diagnosis comparison</h1><p>Status: {}. Compared {} / {} tasks; {} flagged slow. {} tasks have no compatible reference.</p><p><a href="report.json">Structured report</a> | <a href="task_comparison.csv">All tasks</a> | <a href="slow_tasks.csv">Slow tasks</a> | <a href="root_causes.csv">Source candidates</a></p>'.format(
        report["status"], report["compared_task_count"], report["task_count"], report["slow_task_count"], report["uncomparable_task_count"])
    body += "<ul>" + "".join("<li>{}</li>".format(html.escape(limit)) for limit in report["limits"]) + "</ul><h2>Source candidates / unresolved boundaries</h2>"
    for root in report["root_causes"]:
        label = "rank {} / {} / step {} / task {} / {}".format(root["user_rank"], root["phase"], root["step"], root["task_id"], root["status"])
        link = '<a href="{}">{}</a>'.format(root["comparison_page"], html.escape(label)) if root.get("comparison_page") else html.escape(label)
        body += "<p>{}: {} ({} affected waits)</p>".format(link, html.escape(root["reason"]), len(root["affected_wait_graph_ids"]))
    if not report["root_causes"]:
        body += "<p>No source established. No flagged task is not proof of absence of faults.</p>"
    body += '<h2>Slow tasks / increased local gaps</h2><p>Showing at most 500 entries; CSV and JSON contain all results. Times below are microseconds. Gap increase is separate from task duration.</p><div class="scroll"><table><thead><tr><th>Rank / task</th><th>Phase / event</th><th>Baseline median</th><th>Anomaly</th><th>Duration increase</th><th>Factor</th><th>Gap increase</th><th>Role</th></tr></thead><tbody>'
    for task in slow[:500]:
        cells = ["{} / {}".format(task["user_rank"], task["task_id"]), "{} / {}".format(task["phase"], task["event"]),
                 str(Decimal(task["baseline_median_ns"]) / 1000), str(Decimal(task["duration_ns"]) / 1000),
                 str(Decimal(task["delta_ns"]) / 1000), task["slowdown_factor"] or "zero baseline",
                 str(Decimal(task["gap_delta_ns"]) / 1000) if task["gap_delta_ns"] is not None else "unmeasured", task["role"]]
        body += "<tr>" + "".join("<td>{}</td>".format(html.escape(value)) for value in cells) + "</tr>"
    write_page(directory / "index.html", "Baseline comparison", body + "</tbody></table></div>")
    return directory


def run_comparison(current_dir, baseline_dir, output_dir, options=ComparisonOptions(), operation_map=None):
    def load(directory):
        directory = Path(directory)
        gate = directory / "pipeline_result.json"
        if gate.exists() and json.loads(gate.read_text(encoding="utf-8-sig")).get("status") != "passed":
            raise ValueError("refusing a failed diagnosis artifact: {}".format(directory))
        rows = graph.read_graph_artifact_nodes(directory / "dep_graph_nodes.csv")
        edges = graph.read_graph_artifact_edges(directory / "dep_graph_edges.csv")
        evidence_adjacency(rows, edges)
        return rows, edges
    rows, edges = load(current_dir)
    baseline_rows, baseline_edges = load(baseline_dir)
    report = analyze(rows, edges, baseline_rows, options, load_operation_map(operation_map), baseline_edges=baseline_edges)
    report.update(anomaly_artifact_dir=str(Path(current_dir).resolve()), baseline_artifact_dir=str(Path(baseline_dir).resolve()))
    export_report(report, rows, edges, baseline_rows, baseline_edges, output_dir, options)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("artifact_dir", type=Path)
    parser.add_argument("--baseline-dir", type=Path, required=True)
    parser.add_argument("-o", "--output-dir", type=Path, required=True)
    parser.add_argument("--operation-map", type=Path)
    parser.add_argument("--min-increase-us", type=Decimal, default=Decimal(10))
    parser.add_argument("--slowdown-factor", type=Decimal, default=Decimal("1.5"))
    parser.add_argument("--context-us", type=Decimal, default=Decimal(100))
    parser.add_argument("--max-figures", type=int, default=5)
    args = parser.parse_args()
    try:
        for value in (args.min_increase_us, args.context_us):
            if not value.is_finite() or value * 1000 != (value * 1000).to_integral_value():
                raise ValueError("comparison times must be finite integer nanoseconds")
        options = ComparisonOptions(int(args.min_increase_us * 1000), str(args.slowdown_factor),
                                    int(args.context_us * 1000), args.max_figures)
        report = run_comparison(args.artifact_dir, args.baseline_dir, args.output_dir, options, args.operation_map)
    except (ValueError, OSError, KeyError, ArithmeticError) as error:
        parser.exit(1, "comparison failed: {}\n".format(error))
    print("compared={} slow={} sources={} report={}".format(report["compared_task_count"], report["slow_task_count"],
          len(report["root_causes"]), args.output_dir / "index.html"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
