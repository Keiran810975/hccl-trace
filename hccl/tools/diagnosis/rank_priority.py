"""Evidence tiers and partial ordering; never rank by total or summed Wait time."""
from __future__ import annotations

from collections import defaultdict
from decimal import Decimal

from .rank_progress import abnormal, first_by_stream


def _position(m):
    return tuple(m[k] for k in ("algorithm", "phase", "step", "slice", "event", "task_kind"))


def _dominates(left, right):
    # Unverified roles, parallel frontiers and different stage positions are incomparable.
    a, b = left["first_abnormal_frontier"], right["first_abnormal_frontier"]
    if (not left["role_verified"] or not right["role_verified"] or left["role"] != right["role"]
            or len(a) != 1 or len(b) != 1 or not a[0]["phase"] or not a[0]["event"]
            or _position(a[0]) != _position(b[0])):
        return False
    pa, pb = a[0]["completion_progress"], b[0]["completion_progress"]
    if not pa or not pb or not pa["anomalous"] or not pb["anomalous"]:
        return False
    da, db = (Decimal(p["delta_ns"]) for p in (pa, pb))
    margin = 3 * sum(Decimal(p["historical_mad_ns"]) for p in (pa, pb))
    coverage_a = left["progress_comparable_count"] * right["milestone_count"]
    coverage_b = right["progress_comparable_count"] * left["milestone_count"]
    witnesses_a, witnesses_b = (r["outgoing_verified_dependents"] for r in (left, right))
    return (da > db + margin and witnesses_a >= witnesses_b and coverage_a >= coverage_b
            and (witnesses_a > witnesses_b or coverage_a > coverage_b))


def summarize(ranks, milestones, searches, roles, protocol_observations=()):
    traced = defaultdict(list)
    protocol_by_receiver = defaultdict(list)
    for item in protocol_observations:
        protocol_by_receiver[item["receiver_rank"]].append(item)
    explained_waits = set()
    protocol_witnesses = set()
    for search in searches:
        traced[search["seed"]["rank"]].extend(search["downstream"])
        explained_waits.update(h["task"]["graph_id"] for h in search["downstream"]
                               if h["status"] == "verified_blocking_path")
        if search["seed"]["completion_late"] and any(h["change"] == "wait_growth" for h in search["downstream"]):
            protocol_witnesses.add(search["seed"]["graph_id"])
    rows = []
    for rank in ranks:
        items = milestones.get(rank, [])
        changed = [m for m in items if abnormal(m)]
        frontier = first_by_stream(changed)
        witnessed = {hit["task"]["graph_id"] for hit in traced[rank] if hit["status"] == "verified_blocking_path"}
        local_slow = [m["graph_id"] for m in items if m["intrinsic_work_slow"]]
        paired_waits = [m["graph_id"] for m in items if m["slow_wait"] and m["wait_producer"]["verified"]]
        protocol = [m["graph_id"] for m in items if m["graph_id"] in protocol_witnesses
                    or (m["slow_wait"] and m["completion_late"] and m["wait_producer"]["verified"]
                        and m["graph_id"] not in explained_waits)]
        receiver_intervals = protocol_by_receiver[rank]
        protocol_support = protocol or any(m["wait_graph_id"] not in explained_waits for m in receiver_intervals)
        if local_slow and witnessed:
            level, reason = "high", "independent_work_growth_and_verified_downstream_wait"
        elif local_slow or protocol_support:
            level, reason = "medium", ("independent_work_growth_without_verified_downstream_wait" if local_slow
                                      else "paired_protocol_progress_late_physical_source_unknown")
        elif paired_waits:
            level, reason = "low", "incoming_wait_growth_no_independent_work_evidence"
        else:
            level, reason = "undetermined", "no_distinguishing_evidence_or_missing_history_or_dependencies"
        role = roles.get(rank, {})
        rows.append(dict(rank=rank, role=role.get("role"), role_verified=bool(role.get("verified")),
            algorithm=role.get("algorithm"), evidence_level=level, ranking_reason=reason,
            priority_rank=None, first_abnormal_frontier=frontier, milestone_count=len(items),
            progress_comparable_count=sum(m["progress_status"] == "comparable" for m in items),
            duration_comparable_count=sum(m["duration_comparable"] for m in items),
            intrinsic_work_slow_ids=local_slow, incoming_paired_slow_wait_ids=paired_waits,
            outgoing_verified_dependents=len(witnessed), milestones=items,
            observed_receive_protocol_intervals=receiver_intervals))
    ordered = []
    position = 1
    for level in ("high", "medium", "low"):
        remaining = [r for r in rows if r["evidence_level"] == level]
        while remaining:
            frontier = [r for r in remaining if not any(_dominates(other, r) for other in remaining if other is not r)]
            for r in frontier:
                r["priority_rank"] = position
            ordered.extend(frontier)
            position += len(frontier)
            remaining = [r for r in remaining if r["priority_rank"] is None]
    ordered.extend(r for r in rows if r["priority_rank"] is None)
    leaders = [r for r in ordered if r["priority_rank"] == 1]
    return dict(rank_progress=ordered, unique_first_priority=(leaders[0]["rank"] if len(leaders) == 1 and
                 leaders[0]["evidence_level"] in {"high", "medium"} else None),
                ranking_meaning="investigation_priority_not_physical_fault_or_simultaneous_rank_progress")
