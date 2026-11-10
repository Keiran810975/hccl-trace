"""Past-only call events and local completion sensitivity for source selection."""
from __future__ import annotations

from collections import Counter, defaultdict
from decimal import Decimal
import json
from pathlib import Path

from . import analyze_waits as waits
from . import compare_diagnosis as comparison
from .dependency_model import stable_id
from .clock_alignment import models_from_report
from .workload_coordinates import position, location_fields


def statistics(values):
    values = [Decimal(v) for v in values]
    center = sum(values) / len(values)
    median = comparison.median(values)
    return center, comparison.median([abs(v - median) for v in values])


def slow(value, center, mad, options):
    value = Decimal(value)
    return (value > center and value >= center * Decimal(options.slowdown_factor)
            and value - center >= Decimal(options.mad_multiplier) * mad)


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


def preparation_sources(records, rows, edges, coordinates, tasks, options, *, alignment=None):
    """Host preparation is an observed interval, never a fabricated device task."""
    if not records:
        return []
    validate_preparations(records, rows, coordinates)
    clocks = models_from_report(alignment)
    lookup = {r["_graph_id"]: r for r in rows}
    rank_rows = defaultdict(list)
    for row in rows:
        if row.get("_operation_scope") in coordinates:
            rank_rows[(row["_operation_scope"], row["_node_id"], row["_user_rank"])].append(row)
    task_by_id = {t["graph_id"]: t for t in tasks}
    slots = {}
    for item in records:
        coord = coordinates[item["operation_scope"]]
        slots[(item["node_id"], item["user_rank"], coord["stage"], coord["iteration"], position(coord))] = item
    syncs = defaultdict(list)
    producer_counts = Counter(e["dst"] for e in edges if "notify_sync" in e["kind"])
    for edge in edges:
        if "notify_sync" not in edge["kind"] or producer_counts[edge["dst"]] != 1:
            continue
        src, dst = lookup[edge["src"]], lookup[edge["dst"]]
        local = (src["_node_id"] == dst["_node_id"] and edge.get("confidence") == "exact"
                 and src.get("profiler_task_kind") == "notify_record")
        remote = (src["_node_id"] != dst["_node_id"] and edge["kind"] == "cross_node_notify_sync_observed"
                  and edge.get("confidence") == "observed" and src.get("profiler_task_kind") in {"rdma", "notify_record"})
        if ((local or remote) and src.get("_operation_scope") == dst.get("_operation_scope")
                and dst.get("profiler_task_kind") == "notify_wait"
                and src["_user_rank"] != dst["_user_rank"]):
            syncs[(src.get("_operation_scope"), src["_node_id"], src["_user_rank"])].append(edge)
    roots = []
    for item in records:
        coord = coordinates[item["operation_scope"]]
        if coord["stage"] != "measured" or coord["iteration"] < options.window:
            continue
        iterations = list(range(coord["iteration"] - options.window, coord["iteration"]))
        history = [slots.get((item["node_id"], item["user_rank"], "measured", i, position(coord))) for i in iterations]
        if any(h is None for h in history):
            continue
        center, mad = statistics([h["stop_ns"] - h["start_ns"] for h in history])
        duration = item["stop_ns"] - item["start_ns"]
        if not slow(duration, center, mad, options):
            continue
        supported, overlaps, clock_errors, support_facts = [], {}, [], []
        for edge in syncs[(item["operation_scope"], item["node_id"], item["user_rank"])]:
            src, dst = lookup[edge["src"]], lookup[edge["dst"]]
            changed = task_by_id.get(edge["dst"], {})
            if (not changed.get("duration_slow") or src["_device_id"] != item["device_id"]
                    or not item["stop_ns"] <= item["api_start_ns"] <= waits.ns(src, "start")):
                continue
            if src["_node_id"] == dst["_node_id"]:
                if not waits.ns(dst, "start") < item["stop_ns"] or waits.ns(src, "stop") > waits.ns(dst, "stop"):
                    continue
                overlap = max(0, min(item["stop_ns"], waits.ns(dst, "stop")) - max(item["start_ns"], waits.ns(dst, "start")))
            else:
                sender = clocks.get((src["_node_id"], src["_device_id"]))
                receiver = clocks.get((dst["_node_id"], dst["_device_id"]))
                if sender is None or receiver is None:
                    continue
                hs, he = (sender.map_ns(item[k]) for k in ("start_ns", "stop_ns"))
                ws, we = (receiver.map_ns(waits.ns(dst, side)) for side in ("start", "stop"))
                es, er = sender.estimated_error_ns, receiver.estimated_error_ns
                # The protocol edge supplies the dependency, not an RDMA hardware
                # completion timestamp. Require overlap beyond both clock margins.
                if he - es <= ws + er or he + es > we - er:
                    continue
                overlap = max(0, min(he - es, we - er) - max(hs + es, ws + er))
                clock_errors.append(es + er)
            if overlap:
                supported.append(edge)
                overlaps[edge["dst"]] = overlap
                def endpoint(row):
                    return dict(graph_id=row["_graph_id"], node_id=row["_node_id"],
                        user_rank=row["_user_rank"], device_id=row["_device_id"],
                        stream_id=row["_stream_id"], task_id=row["_task_id"],
                        operation_scope=row.get("_operation_scope"), task_kind=row["profiler_task_kind"],
                        observed_start_ns=waits.ns(row, "start"), observed_stop_ns=waits.ns(row, "stop"))
                support_facts.append(dict(edge=dict(edge), producer=endpoint(src), wait=endpoint(dst),
                    wait_comparison={key: changed.get(key) for key in (
                        "duration_ns", "duration_slow", "reference_count", "reference_iterations",
                        "reference_mean_ns", "reference_mad_ns")},
                    overlap_ns=overlap, unique_notify_producer=True,
                    time_domain="same_node" if src["_node_id"] == dst["_node_id"] else "aligned_estimate",
                    alignment=(None if src["_node_id"] == dst["_node_id"] else dict(
                        preparation_ns=[hs, he], wait_ns=[ws, we], sender_error_ns=es, receiver_error_ns=er))))
        anchor = min(supported, key=lambda e: (waits.ns(lookup[e["src"]], "start"), e["edge_id"])) if supported else None
        candidates = rank_rows[(item["operation_scope"], item["node_id"], item["user_rank"])]
        anchor_row = lookup[anchor["src"]] if anchor else min(candidates, key=lambda r: (waits.ns(r, "start"), r["_graph_id"]))
        affected = sorted({e["dst"] for e in supported})
        overlap = max(overlaps.values(), default=0)
        references = []
        for previous in history:
            anchors = [r for r in rank_rows[(previous["operation_scope"], previous["node_id"], previous["user_rank"])]
                       if comparison.task_signature(r) == comparison.task_signature(anchor_row)]
            references.append(dict(previous, anchor_graph_id=anchors[0]["_graph_id"] if len(anchors) == 1 else None))
        roots.append(dict(root_id=stable_id("host_source", (item["node_id"], item["user_rank"], item["operation_scope"])),
            graph_id=anchor_row["_graph_id"], anchor_graph_id=anchor_row["_graph_id"],
            source_activity_id=stable_id("host_prepare", (item["node_id"], item["user_rank"], item["operation_scope"])),
            node_id=item["node_id"], user_rank=item["user_rank"], device_id=item["device_id"], stream_id=None, task_id=None,
            operation_scope=item["operation_scope"], **location_fields(coord),
            algorithm="host", phase="call_preparation", step="", event="prepare_collective", task_kind="host_interval",
            observed_start_ns=item["start_ns"], observed_stop_ns=item["stop_ns"], duration_ns=duration,
            api_start_ns=item["api_start_ns"], api_stop_ns=item["api_stop_ns"],
            component="host_preparation", status="dependency_supported_candidate" if supported else "unresolved_host_preparation",
            reason=("Observed Host preparation grew before this call's bound Notify producer and overlaps a slow peer Wait; cross-node support uses an observed protocol dependency and estimated clock-error margins, not RDMA hardware completion; graph_id is a device anchor, not the Host activity"
                    if supported else "Observed Host preparation grew, but no unique late Notify producer/slow peer Wait overlap is established with available clock evidence"),
            reference_iterations=iterations, reference_graph_ids=[], reference_preparations=references, reference_count=5,
            reference_operation_scopes=[h["operation_scope"] for h in history], reference_mean_ns=str(center), reference_mad_ns=str(mad),
            delta_ns=str(Decimal(duration) - center), affected_wait_graph_ids=affected,
            evidence_paths={k: [e["edge_id"] for e in supported if e["dst"] == k] for k in affected},
            host_call_evidence=item["evidence"], upstream_slow_graph_ids=[], traversal_truncated=False,
            observed_wait_overlap_ns=overlap, time_alignment_estimated_error_ns=max(clock_errors, default=None),
            support_evidence_version=1, supporting_dependencies=support_facts,
            physical_cause="unknown"))
        roots[-1].update(task_domain="host_preparation", task_domain_evidence="public_preparation_and_bound_api")
    return roots
