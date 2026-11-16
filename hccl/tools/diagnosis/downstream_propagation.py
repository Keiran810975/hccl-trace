"""Search forward from slow work without attributing independent slow tasks to it."""
from __future__ import annotations

from decimal import Decimal
from heapq import heappop, heappush

from .dependency_timing import ORDER, WAIT


def trace_downstream(seed, graph, progress, limit):
    gid = seed["graph_id"]
    kind = "independent_execution_overrun" if seed["intrinsic_work_slow"] else "unconfirmed_protocol_stage"
    budget = Decimal(seed["duration_delta_ns"] or 0)
    if kind == "unconfirmed_protocol_stage" and not seed["slow_wait"]:
        budget = Decimal((seed["completion_progress"] or {}).get("delta_ns", 0))
    best, settled, queue, prior = {gid: 0}, set(), [(0, gid)], {}
    impacts, gaps = [], set()

    def path_to(k):
        path = []
        while k != gid:
            edge = prior[k]
            path.append(edge)
            k = edge["src"]
        return list(reversed(path))

    while queue and len(settled) < limit:
        cost, key = heappop(queue)
        if key in settled or best[key] != cost:
            continue
        settled.add(key)
        item = progress.milestone(key)
        task = progress.tasks.get(key, {})
        if key != gid:
            if (task.get("stage") == "warmup" or item["iteration"] is not None and seed["iteration"] is not None
                    and not seed["iteration"] <= item["iteration"] <= seed["iteration"] + 1):
                gaps.add((key, "outside_forward_iteration_window", None))
                continue
            edge = prior[key]
            change = None
            if item["intrinsic_work_slow"]:
                change = "independent_execution_overrun"
            elif item["slow_wait"] and edge["kind"] != ORDER:
                change = "wait_growth"
            elif item["starts_late"] and item["duration_comparable"] and not item["duration_slow"]:
                change = "start_displacement_with_normal_duration"
            if change:
                late_finish = item["completion_progress"]
                impacts.append(dict(task=item, change=change, path=path_to(key), path_slack_and_clock_ns=cost,
                    status=("independent_not_attributed" if change == "independent_execution_overrun" else
                            "verified_blocking_path" if change == "wait_growth" and kind == "independent_execution_overrun"
                            and (late_finish is None or item["completion_late"])
                            else "dependency_supported_observation")))
            if item["intrinsic_work_slow"]:
                continue
            if (item["task_kind"] in WAIT and edge["kind"] == ORDER
                    and graph.wait_proof(key)["status"] != "producer_already_ready"):
                gaps.add((key, "arrival_does_not_establish_wait_release", edge["edge_id"]))
                continue
        for e in graph.outgoing.get(key, ()):
            proof = graph.proof(e)
            target = e["dst"]
            if not proof["verified"]:
                if proof["status"] != "producer_already_ready":
                    gaps.add((target, proof["status"], e["edge_id"]))
                continue
            if e["kind"] == ORDER and graph.nodes[target]["profiler_task_kind"] in WAIT:
                target_wait = progress.milestone(target)
                if target_wait["slow_wait"] and graph.wait_proof(target)["status"] != "producer_already_ready":
                    # Arrival is not a substitute for the signal releasing a slow Wait.
                    gaps.add((target, "arrival_does_not_establish_wait_release", e["edge_id"]))
                    continue
            extra = proof["slack_ns"] + proof["estimated_error_ns"]
            if cost + extra >= budget:
                gaps.add((target, "observed_slack_or_clock_exceeds_source_growth", e["edge_id"]))
                continue
            if target not in settled and (target not in best or cost + extra < best[target]):
                best[target] = cost + extra
                prior[target] = proof
                heappush(queue, (cost + extra, target))

    truncated = any(key not in settled for _, key in queue)
    if truncated:
        gaps.add((gid, "downstream_budget_exhausted", None))
    affected = [x["task"] for x in impacts if x["status"] != "independent_not_attributed"]
    return dict(seed=seed, seed_type=kind, downstream=impacts, visited_count=len(settled),
        search_truncated=truncated,
        evidence_gaps=[dict(graph_id=g, reason=r, edge_id=e) for g, r, e in
                       sorted(gaps, key=lambda x: (x[0], x[1], x[2] or ""))],
        affected_ranks=sorted({m["rank"] for m in affected if m["rank"] >= 0}),
        affected_operation_scopes=sorted({m["operation_scope"] for m in affected if m["operation_scope"]}),
        collop_completion_effect="not_determined")
