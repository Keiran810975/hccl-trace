#!/usr/bin/env python3
"""Rolling task comparison over evidenced workload call coordinates."""
from __future__ import annotations

from collections import Counter, defaultdict, deque
from dataclasses import asdict, dataclass
from decimal import Decimal
from itertools import chain
import json
from pathlib import Path

from . import analyze_waits as waits
from . import compare_diagnosis as comparison
from . import peer_read, source_events, wait_backtrace
from .notify_comparison import comparison_keys
from .report_contract import CLEAN_TASK_REFERENCE
from .task_classifier import classify_task, source_category, INTERNAL, EXTERNAL, UNRESOLVED
from .workload_coordinates import position, location_fields


@dataclass(frozen=True)
class RollingOptions:
    window: int = 5
    slowdown_factor: str = "1.5"
    mad_multiplier: str = "3"
    traversal_limit: int = 4096
    wait_slowdown_factor: str = "1.2"
    calibrated_release_intervals: bool = False

    def validate(self):
        if self.window != 5:
            raise ValueError("the rolling reference requires exactly five iterations")
        factor, multiplier = Decimal(self.slowdown_factor), Decimal(self.mad_multiplier)
        if not factor.is_finite() or factor <= 1 or not multiplier.is_finite() or multiplier < 0:
            raise ValueError("finite slowdown > 1 and nonnegative MAD multiplier required")
        if self.traversal_limit <= 0:
            raise ValueError("invalid rolling report limits")
        if self.wait_slowdown_factor is not None:
            wait_factor = Decimal(self.wait_slowdown_factor)
            if not wait_factor.is_finite() or wait_factor <= 1:
                raise ValueError("wait slowdown factor must be finite and greater than one")


def validate_coordinates(records):
    result, slots = {}, set()
    allowed = {"operation_scope", "stage", "iteration", "block", "bucket", "evidence",
               "group_id", "call_site", "occurrence"}
    for item in records:
        if set(item) - allowed:
            raise ValueError("call coordinates must contain only public workload binding fields")
        scope = item.get("operation_scope")
        stage = item.get("stage")
        if not scope or scope in result or stage not in {"warmup", "measured"}:
            raise ValueError("unique scopes and explicit warmup/measured stage required")
        named = "group_id" in item
        if named and (any(not isinstance(item.get(k), str) or not item[k].strip() for k in ("group_id", "call_site"))
                      or any(item.get(k) is not None for k in ("block", "bucket"))):
            raise ValueError("named locations require group_id/call_site and no legacy block/bucket")
        if not named and any(k in item for k in ("call_site", "occurrence")):
            raise ValueError("partial named workload location")
        if any(type(item.get(k)) is not int or item[k] < 0 for k in
               (("iteration", "occurrence") if named else ("iteration", "block", "bucket"))):
            raise ValueError("call coordinates must be nonnegative integers")
        if not str(item.get("evidence", "")).strip():
            raise ValueError("workload-to-DB binding needs independent capture evidence")
        slot = (stage, item["iteration"], position(item))
        if slot in slots:
            raise ValueError("more than one operation bound to one workload call")
        slots.add(slot)
        result[scope] = dict(item)
    return result


def load_coordinates(path):
    data = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    if set(data) != {"schema_version", "operations"} or data["schema_version"] not in {1, 2}:
        raise ValueError("expected public call map schema 1/2, without injection information")
    if any(("group_id" in item) != (data["schema_version"] == 2) for item in data["operations"]):
        raise ValueError("workload coordinate schema and location fields disagree")
    return validate_coordinates(data["operations"])


def _statistics(values):
    values = [Decimal(v) for v in values]
    center = sum(values) / len(values)
    median = comparison.median(values)
    return center, comparison.median([abs(v - median) for v in values])


def _slow(value, center, mad, options, *, propagation=False):
    # No absolute increase floor. The current value never enters its reference.
    value = Decimal(value)
    factor = options.wait_slowdown_factor if propagation else options.slowdown_factor
    return (value > center and value >= center * Decimal(factor)
            and value - center >= Decimal(options.mad_multiplier) * mad)


def compare_tasks(rows, edges, coordinates, options):
    groups, by_slot = comparison.operation_groups(rows), {}
    unknown = set(coordinates) - set(groups)
    if unknown:
        raise ValueError("call map references unknown execution operations")
    for scope, coord in coordinates.items():
        if coord["stage"] == "measured":
            by_slot[(coord["iteration"], position(coord))] = scope
    gaps = comparison.local_gaps(rows, edges)
    origins = {}
    for row in rows:
        key = row.get("_operation_scope", ""), row["_node_id"]
        origins[key] = min(origins.get(key, waits.ns(row, "start")), waits.ns(row, "start"))
    signatures = {scope: defaultdict(list) for scope in groups}
    notify_keys = comparison_keys(rows, edges)
    def signature(row):
        if not all(row.get(field, '') for field in ('algorithm', 'phase', 'event')):
            return notify_keys.get(row['_graph_id'], comparison.task_signature(row))
        return comparison.task_signature(row)
    shapes = {scope: comparison.operation_shape(group) for scope, group in groups.items()}
    for scope, group in groups.items():
        for row in group:
            signatures[scope][signature(row)].append(row)
    accepted = defaultdict(lambda: deque(maxlen=options.window))
    # Admit observations in measured-iteration order, not graph row order.
    measured = set(by_slot.values())
    scopes = sorted(by_slot.values(), key=lambda scope: coordinates[scope]["iteration"])
    ordered_rows = chain((row for row in rows if row.get("_operation_scope") not in measured),
                             (row for scope in scopes for row in groups[scope]))
    tasks = []
    for row in ordered_rows:
        scope, key = row.get("_operation_scope", ""), signature(row)
        physical_notify = key[0] in {'same_capture_unique_notify_channel','same_capture_anchored_notify_channel','same_capture_anchored_task'}
        coord = coordinates.get(scope)
        task = dict(graph_id=row["_graph_id"], node_id=row["_node_id"],
                    user_rank=row["_user_rank"], device_id=row["_device_id"],
                    stream_id=row["_stream_id"], task_id=row["_task_id"], operation_scope=scope,
                    algorithm=row.get("algorithm", ""), phase=row.get("phase", ""),
                    step=row.get("step", ""), event=row.get("event", ""),
                    task_kind=row.get("profiler_task_kind", ""),
                    observed_start_ns=waits.ns(row, "start"), observed_stop_ns=waits.ns(row, "stop"),
                    duration_ns=waits.duration(row), gap_before_ns=gaps.get(row["_graph_id"]),
                    start_offset_ns=waits.ns(row, "start") - origins[(scope, row["_node_id"])],
                    reference_start_offset_mean_ns=None, reference_start_offset_mad_ns=None,
                    start_delta_ns=None, start_late=None,
                    **(location_fields(coord) if coord else dict(stage="unbound", iteration=None, block=None, bucket=None)),
                    comparison_status="unbound_operation", reference_iterations=[], reference_graph_ids=[],
                    reference_operation_scopes=[], reference_count=0, reference_mean_ns=None,
                    reference_mad_ns=None, reference_gap_mean_ns=None, reference_gap_mad_ns=None,
                    reference_graph_id="", reference_operation_scope="", reference_evidence="",
                    delta_ns=None, gap_delta_ns=None, slowdown_factor=None,
                    duration_slow=False, gap_slow=False, is_slow=False)
        task['comparison_basis'] = key[0] if physical_notify else 'algorithm_semantic_location'
        task.update(classify_task(row))
        tasks.append(task)
        if not coord:
            continue
        if coord["stage"] != "measured":
            task["comparison_status"] = "warmup_excluded"
            continue
        if not physical_notify and not all(row.get(field, "") for field in ("algorithm", "phase", "event")):
            task["comparison_status"] = "unannotated_task_location"
            continue
        if len(signatures[scope][key]) != 1:
            task["comparison_status"] = "ambiguous_task_location"
            continue
        buffer = accepted[(position(coord), shapes[scope], key, row["_node_id"], row["_device_id"])]
        if not buffer:
            task["comparison_status"] = "no_prior_comparable_sample"
            buffer.append((coord["iteration"], row))
            continue
        iterations, history = map(list, zip(*buffer))
        history_scopes = [r["_operation_scope"] for r in history]
        evidence = ("Public call coordinates; up to five earlier comparable formal samples not flagged for "
                    "duration or gap growth; {}; no ordinal, inferred phase or injection truth").format(
                        "unique same-capture physical channel or typed task between unique semantic anchors"
                        if physical_notify else "unique semantic location")
        center, mad = _statistics([waits.duration(r) for r in history])
        start_center, start_mad = _statistics([waits.ns(r, "start") - origins[(r["_operation_scope"], r["_node_id"])] for r in history])
        representative = min(history, key=lambda r: (abs(Decimal(waits.duration(r)) - center), r["_graph_id"]))
        task.update(comparison_status=CLEAN_TASK_REFERENCE,
                    reference_count=len(history),
                    reference_iterations=iterations, reference_graph_ids=[r["_graph_id"] for r in history],
                    reference_operation_scopes=history_scopes,
                    reference_mean_ns=str(center), reference_mad_ns=str(mad),
                    reference_start_offset_mean_ns=str(start_center), reference_start_offset_mad_ns=str(start_mad),
                    start_delta_ns=str(Decimal(task["start_offset_ns"]) - start_center),
                    start_late=_slow(task["start_offset_ns"], start_center, start_mad, options, propagation=True),
                    reference_graph_id=representative["_graph_id"],
                    reference_operation_scope=representative["_operation_scope"],
                    reference_evidence=evidence,
                    delta_ns=str(Decimal(task["duration_ns"]) - center),
                    slowdown_factor=str(Decimal(task["duration_ns"]) / center) if center else None,
                    duration_slow=_slow(task["duration_ns"], center, mad, options,
                                        propagation=task["task_kind"] == "notify_wait"))
        if task["gap_before_ns"] is not None and all(r["_graph_id"] in gaps for r in history):
            gap_center, gap_mad = _statistics([gaps[r["_graph_id"]] for r in history])
            task.update(reference_gap_mean_ns=str(gap_center), reference_gap_mad_ns=str(gap_mad),
                        gap_delta_ns=str(Decimal(task["gap_before_ns"]) - gap_center),
                        gap_slow=_slow(task["gap_before_ns"], gap_center, gap_mad, options))
        task["is_slow"] = task["duration_slow"] or task["gap_slow"]
        if not task["is_slow"]:
            buffer.append((coord["iteration"], row))
    return tasks


def analyze(rows, edges, coordinates, options=RollingOptions(), *, preparations=(), alignment=None):
    options.validate()
    coordinates = validate_coordinates(list(coordinates.values()))
    comparison.evidence_adjacency(rows, edges)
    tasks = compare_tasks(rows, edges, coordinates, options)
    roots, traces = wait_backtrace.trace_sources(rows, edges, tasks, options, alignment=alignment)
    host_roots = source_events.preparation_sources(preparations, rows, edges, coordinates, tasks, options, alignment=alignment)
    roots.extend(host_roots)
    traces_by_wait = {t["wait_graph_id"]: t for t in traces}
    for root in host_roots:
        if root["status"] != "dependency_supported_candidate":
            continue
        for key in root["affected_wait_graph_ids"]:
            trace = traces_by_wait.get(key)
            if trace is None:
                continue
            trace.setdefault("external_clue_ids", []).append(root["root_id"])
            trace.setdefault("host_activity_ids", []).append(root["source_activity_id"])
            if not trace["source_root_ids"]:
                trace["status"] = "external_clue_found"
    return backtrace_report(rows, tasks, roots, traces, preparations, options)


def backtrace_report(rows, tasks, roots, traces, preparations, options):
    lookup = {r["_graph_id"]: r for r in rows}
    explained = {key for r in roots if r["status"] == "dependency_supported_candidate"
                 for key, path in r["evidence_paths"].items() if path}
    candidates, unresolved = [], []
    for root in roots:
        if root["component"] == "wait_boundary" and root["graph_id"] in explained:
            continue
        category = source_category(root, lookup[root["graph_id"]])
        if root["status"] == "dependency_supported_candidate" and category in {INTERNAL, EXTERNAL}:
            candidates.append(dict(root, diagnosis_category=category, source_selection_policy="wait_backtrace_v1"))
        else:
            unresolved.append(dict(root, diagnosis_category=UNRESOLVED))
    peer_reads = peer_read.observe(rows, tasks, candidates, options)
    peer_impacts = {o["graph_id"] for o in peer_reads if o["disposition"] == "reported_as_suspected_peer_read_impact"}
    candidates = [r for r in candidates if r["graph_id"] not in peer_impacts]
    for task in tasks:
        if task["graph_id"] in explained:
            task["role"] = "propagated_wait"
        elif task["graph_id"] in peer_impacts:
            task["role"] = "suspected_peer_read_impact"
    counts = Counter(source_category(r, lookup[r["graph_id"]]) for r in candidates)
    compared = sum(t["reference_count"] > 0 for t in tasks)
    return dict(schema_version=1, source_policy_version=10, source_ranking_version=0,
        candidate_admission=None, source_regions=[], recommended_candidate_ids=[], primary_source_candidate_id=None,
        reference_mode=CLEAN_TASK_REFERENCE, options=asdict(options),
        status="analyzed" if compared else "no_comparable_history",
        diagnosis_status=("localized_candidate" if counts[INTERNAL] else "external_clues" if counts[EXTERNAL] else
                          "suspected_peer_read_impact" if peer_impacts else
                          "no_comparable_history" if not compared else "unresolved_waits" if unresolved else "no_slow_event"),
        events=[], slow_event_count=0, wait_backtraces=traces, coverage=wait_backtrace.coverage(tasks, traces, minimum_iteration=1),
        public_preparation_count=len(preparations), primary_eligible_count=0,
        task_count=len(tasks), compared_task_count=compared, slow_task_count=sum(t["is_slow"] for t in tasks),
        gap_observation_count=sum(r["status"] == "unattributed_gap" for r in unresolved),
        supported_execution_candidate_count=counts[INTERNAL], supported_host_candidate_count=counts[EXTERNAL],
        source_status_counts=dict(Counter(r["status"] for r in candidates + unresolved)),
        tasks=tasks, root_causes=candidates, unresolved_observations=unresolved, primary_external_clue_id=None,
        peer_read_policy=peer_read.POLICY, peer_read_observations=peer_reads,
        category_counts=dict(counts, unresolved_observation=len(unresolved)),
        limits=["All dependency-supported candidates are peers; no cluster, Top1, or primary candidate.",
                "Slow Waits and tasks that only start late are propagation evidence, not root candidates.",
                "Late release cannot explain an increase in the task's own execution duration.",
                "Directional Ring read observations are not Notify edges or proved physical causes; local confounds keep the candidate.",
                "Unpaired, ambiguous or time-incompatible dependencies and isolated slow tasks remain unresolved.",
                "Cross-node protocol evidence needs calibrated clocks and does not prove RDMA hardware completion.",
                "Device references use up to five earlier comparable formal samples; observations flagged for execution or gap growth never enter later references.",
                "With no prior comparison, the first comparable observation seeds its location. Small histories are not evidence of normality.",
                "Host preparation retains its consecutive-five reference. Injection truth is never read."])
