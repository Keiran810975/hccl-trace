"""Past-only call events and local completion sensitivity for source selection."""
from __future__ import annotations

from collections import Counter, defaultdict
from decimal import Decimal
import json
from pathlib import Path

from . import analyze_waits as waits
from . import compare_diagnosis as comparison
from . import critical_path as critical
from .dependency_model import stable_id


def statistics(values):
    values = [Decimal(v) for v in values]
    center = sum(values) / len(values)
    median = comparison.median(values)
    return center, comparison.median([abs(v - median) for v in values])


def slow(value, center, mad, options):
    value = Decimal(value)
    return (value > center and value >= center * Decimal(options.slowdown_factor)
            and value - center >= Decimal(options.mad_multiplier) * mad)


def operation_events(rows, coordinates, options):
    groups = defaultdict(list)
    for row in rows:
        if row.get("_operation_scope") in coordinates:
            groups[(row["_operation_scope"], row["_node_id"])].append(row)
    events, slots = [], {}
    for (scope, node), group in sorted(groups.items()):
        coord = coordinates[scope]
        start = min(waits.ns(r, "start") for r in group)
        stop = max(waits.ns(r, "stop") for r in group)
        event = dict(event_id=stable_id("event", (node, scope)), operation_scope=scope, node_id=node,
                     **{k: coord[k] for k in ("stage", "iteration", "block", "bucket")},
                     observed_start_ns=start, observed_stop_ns=stop, duration_ns=stop - start,
                     reference_iterations=[], reference_mean_ns=None, reference_mad_ns=None,
                     delta_ns=None, is_slow=False, shape_id=comparison.operation_shape(group),
                     comparison_status="insufficient_history")
        events.append(event)
        slots[(node, coord["stage"], coord["iteration"], coord["block"], coord["bucket"])] = event
    for event in events:
        if event["stage"] != "measured" or event["iteration"] < options.window:
            continue
        iterations = list(range(event["iteration"] - options.window, event["iteration"]))
        history = [slots.get((event["node_id"], "measured", i, event["block"], event["bucket"])) for i in iterations]
        if any(item is None for item in history):
            event["comparison_status"] = "missing_previous_iteration"
            continue
        if any(item["shape_id"] != event["shape_id"] for item in history):
            event["comparison_status"] = "operation_structure_changed"
            continue
        center, mad = statistics([item["duration_ns"] for item in history])
        event.update(reference_iterations=iterations, reference_mean_ns=str(center), reference_mad_ns=str(mad),
                     delta_ns=str(Decimal(event["duration_ns"]) - center),
                     is_slow=slow(event["duration_ns"], center, mad, options),
                     comparison_status="previous_five_iteration_mean")
    return events


def validate_preparations(records, rows, coordinates):
    allowed = {"operation_scope", "node_id", "user_rank", "device_id", "start_ns", "stop_ns",
               "api_start_ns", "api_stop_ns", "evidence"}
    membership = {(r.get("_operation_scope"), r["_node_id"], r["_user_rank"], r["_device_id"]) for r in rows}
    seen = set()
    for item in records:
        if set(item) != allowed:
            raise ValueError("preparations require only the complete public observation fields")
        key = tuple(item[k] for k in ("operation_scope", "node_id", "user_rank", "device_id"))
        rank_call = key[:3]
        times = [item[k] for k in ("start_ns", "stop_ns", "api_start_ns", "api_stop_ns")]
        if (rank_call in seen or key not in membership or item["operation_scope"] not in coordinates
                or any(type(item[k]) is not int or item[k] < 0 for k in ("user_rank", "device_id"))
                or any(type(t) is not int or t < 0 for t in times) or times != sorted(times)
                or not str(item["evidence"]).strip()):
            raise ValueError("preparation must bind uniquely to a real rank/call and precede its evidenced API")
        seen.add(rank_call)
    return records


def load_preparations(path):
    if path is None:
        return []
    data = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    if set(data) != {"schema_version", "preparations"} or data["schema_version"] != 1:
        raise ValueError("expected public preparation map schema 1")
    return data["preparations"]


def preparation_sources(records, rows, edges, coordinates, tasks, options):
    """Host preparation is an observed interval, never a fabricated device task."""
    if not records:
        return []
    validate_preparations(records, rows, coordinates)
    lookup = {r["_graph_id"]: r for r in rows}
    rank_rows = defaultdict(list)
    for row in rows:
        if row.get("_operation_scope") in coordinates:
            rank_rows[(row["_operation_scope"], row["_node_id"], row["_user_rank"])].append(row)
    task_by_id = {t["graph_id"]: t for t in tasks}
    slots = {}
    for item in records:
        coord = coordinates[item["operation_scope"]]
        slots[(item["node_id"], item["user_rank"], coord["stage"], coord["iteration"], coord["block"], coord["bucket"])] = item
    syncs = defaultdict(list)
    producer_counts = Counter(e["dst"] for e in edges if "notify_sync" in e["kind"])
    for edge in edges:
        if "notify_sync" not in edge["kind"] or edge.get("confidence") != "exact" or producer_counts[edge["dst"]] != 1:
            continue
        src, dst = lookup[edge["src"]], lookup[edge["dst"]]
        if (src["_node_id"] == dst["_node_id"] and src.get("_operation_scope") == dst.get("_operation_scope")
                and src.get("profiler_task_kind") == "notify_record" and dst.get("profiler_task_kind") == "notify_wait"
                and src["_user_rank"] != dst["_user_rank"]):
            syncs[(src.get("_operation_scope"), src["_node_id"], src["_user_rank"])].append(edge)
    roots = []
    for item in records:
        coord = coordinates[item["operation_scope"]]
        if coord["stage"] != "measured" or coord["iteration"] < options.window:
            continue
        iterations = list(range(coord["iteration"] - options.window, coord["iteration"]))
        history = [slots.get((item["node_id"], item["user_rank"], "measured", i, coord["block"], coord["bucket"])) for i in iterations]
        if any(h is None for h in history):
            continue
        center, mad = statistics([h["stop_ns"] - h["start_ns"] for h in history])
        duration = item["stop_ns"] - item["start_ns"]
        if not slow(duration, center, mad, options):
            continue
        supported = []
        for edge in syncs[(item["operation_scope"], item["node_id"], item["user_rank"])]:
            src, dst = lookup[edge["src"]], lookup[edge["dst"]]
            changed = task_by_id.get(edge["dst"], {})
            # Host preparation must still be running AFTER the peer Wait began.
            # Record is an actual endpoint of this exact call, after its verified API.
            if (changed.get("duration_slow") and src["_device_id"] == item["device_id"]
                    and waits.ns(dst, "start") < item["stop_ns"] <= item["api_start_ns"] <= waits.ns(src, "start")
                    and waits.ns(src, "stop") <= waits.ns(dst, "stop")):
                supported.append(edge)
        anchor = min(supported, key=lambda e: (waits.ns(lookup[e["src"]], "start"), e["edge_id"])) if supported else None
        candidates = rank_rows[(item["operation_scope"], item["node_id"], item["user_rank"])]
        anchor_row = lookup[anchor["src"]] if anchor else min(candidates, key=lambda r: (waits.ns(r, "start"), r["_graph_id"]))
        affected = sorted({e["dst"] for e in supported})
        overlap = max((max(0, min(item["stop_ns"], waits.ns(lookup[k], "stop")) -
                               max(item["start_ns"], waits.ns(lookup[k], "start"))) for k in affected), default=0)
        references = []
        for previous in history:
            anchors = [r for r in rank_rows[(previous["operation_scope"], previous["node_id"], previous["user_rank"])]
                       if comparison.task_signature(r) == comparison.task_signature(anchor_row)]
            references.append(dict(previous, anchor_graph_id=anchors[0]["_graph_id"] if len(anchors) == 1 else None))
        roots.append(dict(root_id=stable_id("host_source", (item["node_id"], item["user_rank"], item["operation_scope"])),
            graph_id=anchor_row["_graph_id"], anchor_graph_id=anchor_row["_graph_id"],
            source_activity_id=stable_id("host_prepare", (item["node_id"], item["user_rank"], item["operation_scope"])),
            node_id=item["node_id"], user_rank=item["user_rank"], device_id=item["device_id"], stream_id=None, task_id=None,
            operation_scope=item["operation_scope"], **{k: coord[k] for k in ("stage", "iteration", "block", "bucket")},
            algorithm="host", phase="call_preparation", step="", event="prepare_collective", task_kind="host_interval",
            observed_start_ns=item["start_ns"], observed_stop_ns=item["stop_ns"], duration_ns=duration,
            component="host_preparation", status="dependency_supported_candidate" if supported else "unresolved_host_preparation",
            reason="Observed Host preparation grew and overlapped a peer Wait before this call's exact Notify producer; graph_id is a device anchor, not the Host activity",
            reference_iterations=iterations, reference_graph_ids=[], reference_preparations=references, reference_count=5,
            reference_operation_scopes=[h["operation_scope"] for h in history], reference_mean_ns=str(center), reference_mad_ns=str(mad),
            delta_ns=str(Decimal(duration) - center), affected_wait_graph_ids=affected,
            evidence_paths={k: [e["edge_id"] for e in supported if e["dst"] == k] for k in affected},
            host_call_evidence=item["evidence"], upstream_slow_graph_ids=[], traversal_truncated=False,
            observed_wait_overlap_ns=overlap, physical_cause="unknown"))
    return roots


def rank_sources(roots, rows, edges, coordinates, options):
    events = operation_events(rows, coordinates, options)
    by_event = {(e["operation_scope"], e["node_id"]): e for e in events}
    grouped_rows, grouped_edges = defaultdict(list), defaultdict(list)
    lookup = {r["_graph_id"]: r for r in rows}
    for row in rows:
        grouped_rows[(row.get("_operation_scope"), row["_node_id"])].append(row)
    for edge in edges:
        src, dst = lookup[edge["src"]], lookup[edge["dst"]]
        if src["_node_id"] == dst["_node_id"] and src.get("_operation_scope") == dst.get("_operation_scope"):
            grouped_edges[(src.get("_operation_scope"), src["_node_id"])].append(edge)
    candidates = defaultdict(list)
    for root in roots:
        event = by_event.get((root["operation_scope"], root["node_id"]))
        root.update(event_id=event["event_id"] if event else None, event_slow=bool(event and event["is_slow"]),
                    primary_eligible=root["status"] == "dependency_supported_candidate" and not root["traversal_truncated"],
                    modeled_execution_gain_ns=None, impact_status="not_assessed", impact_scope="source_operation_on_node",
                    selection_reason="Source evidence is evaluated independently of call-span or critical-path impact")
        root["affected_operation_count"] = len({lookup[key].get("_operation_scope") for key in root["affected_wait_graph_ids"]})
        root["affected_rank_count"] = len({lookup[key]["_user_rank"] for key in root["affected_wait_graph_ids"]})
        if root["component"] == "host_preparation":
            root.update(primary_eligible=root["primary_eligible"] and bool(root["observed_wait_overlap_ns"]),
                        selection_reason="Measured Host interval plus actual late producer-to-peer-Wait evidence; physical cause unknown")
        elif root["component"] == "execution" and root["status"] in {"dependency_supported_candidate", "isolated_slow_task"}:
            candidates[(root["operation_scope"], root["node_id"])].append(root)
    for key, group in candidates.items():
        try:
            report = critical.analyze_critical_path(grouped_rows[key], grouped_edges[key], impact_limit=0)
            task_info = {t["graph_id"]: t for t in report["tasks"]}
            reductions = {r["graph_id"]: min(r["duration_ns"], int(Decimal(r["delta_ns"]))) for r in group
                          if task_info[r["graph_id"]]["cost_kind"] == "task_execution"}
            gains = critical.execution_reduction_gains(report, reductions)
            for root in group:
                gain = gains.get(root["graph_id"])
                root.update(modeled_execution_gain_ns=gain, critical_path_status=report["status"],
                            critical_path_slack_ns=task_info[root["graph_id"]]["slack_ns"],
                            impact_status="positive_local_model_gain" if gain else "zero_local_model_gain" if gain == 0 else "unavailable")
        except ValueError as error:
            for root in group:
                root.update(impact_detail="Local critical path unavailable: " + str(error), critical_path_status="unavailable", impact_status="unavailable")
    def priority(root):
        gain = root.get("modeled_execution_gain_ns") or root.get("observed_wait_overlap_ns", 0)
        return (not root["primary_eligible"], -root["affected_operation_count"], -root["affected_rank_count"],
                -len(root["affected_wait_graph_ids"]), -gain, -Decimal(root["delta_ns"]), root["root_id"])
    roots.sort(key=priority)
    primary = next((r["root_id"] for r in roots if r["primary_eligible"]), None)
    return events, primary
