"""Retain isolated execution growth only with local completion and path evidence."""
from __future__ import annotations

from collections import defaultdict, deque
from decimal import Decimal

from . import analyze_waits as waits
from . import compare_diagnosis as comparison
from .task_classifier import classify_task


def support_local_completion(roots, rows, edges, options):
    groups = defaultdict(list)
    for row in rows:
        groups[(row.get("_operation_scope"), row["_node_id"], row["_user_rank"])].append(row)
    _, _, outgoing = comparison.evidence_adjacency(rows, edges, cross_operations=True)
    lookup = {row["_graph_id"]: row for row in rows}
    for root in roots:
        if root["status"] != "isolated_slow_task" or classify_task(lookup[root["graph_id"]])["task_domain"] != "hccl_internal":
            continue
        key = root["operation_scope"], root["node_id"], root["user_rank"]
        current = groups[key]
        previous = [groups.get((scope, key[1], key[2])) for scope in root["reference_operation_scopes"]]
        if len(previous) != 5 or not all(previous):
            continue
        span = lambda group: max(waits.ns(r, "stop") for r in group) - min(waits.ns(r, "start") for r in group)
        values = list(map(span, previous))
        center = sum(map(Decimal, values)) / 5
        median = comparison.median(values)
        mad = comparison.median([abs(Decimal(v) - median) for v in values])
        duration = span(current)
        factor = Decimal(options.wait_slowdown_factor or options.slowdown_factor)
        if not (duration > center and duration >= center * factor and duration - center >= Decimal(options.mad_multiplier) * mad):
            continue
        finish = max(waits.ns(r, "stop") for r in current)
        tails = {r["_graph_id"] for r in current if waits.ns(r, "stop") == finish}
        queue, seen, evidence = deque([(root["graph_id"], [])]), set(), None
        while queue and len(seen) < options.traversal_limit:
            identifier, path = queue.popleft()
            if identifier in seen:
                continue
            seen.add(identifier)
            if identifier in tails:
                evidence = dict(validated=True, terminal_graph_id=identifier, edge_ids=path,
                                same_node_rank_operation=True, observed_span_ns=duration,
                                reference_mean_ns=str(center), reference_mad_ns=str(mad), delta_ns=str(Decimal(duration) - center))
                break
            for target, edge_id in outgoing.get(identifier, []):
                row = lookup[target]
                if (row.get("_operation_scope"), row["_node_id"], row["_user_rank"]) == key:
                    queue.append((target, path + [edge_id]))
        if evidence is not None:
            root.update(status="local_completion_supported_candidate", local_completion_evidence=evidence,
                        reason="HCCL execution grew and reaches the same rank/call's observed completion through real dependencies; local completion also grew beyond reference noise. No slow Notify Wait propagation or physical cause is claimed.")
