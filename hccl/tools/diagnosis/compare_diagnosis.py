#!/usr/bin/env python3
"""Baseline deltas, evidence-bounded source candidates and paired trace windows."""
from __future__ import annotations

from collections import Counter, defaultdict, deque
from dataclasses import asdict, dataclass
from decimal import Decimal
import json
from pathlib import Path

from . import analyze_waits as waits
from . import visualize_dependency_graph as graph
from .dependency_model import stable_id


@dataclass(frozen=True)
class ComparisonOptions:
    min_increase_ns: int = 10000
    slowdown_factor: str = "1.5"
    traversal_limit: int = 4096

    def validate(self):
        factor = Decimal(self.slowdown_factor)
        if not factor.is_finite() or factor <= 1:
            raise ValueError("comparison slowdown factor must be finite and > 1")
        if self.min_increase_ns <= 0 or self.traversal_limit <= 0:
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
