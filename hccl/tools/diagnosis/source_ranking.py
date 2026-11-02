"""Rank observed source regions without treating path reachability as impact."""
from __future__ import annotations

from collections import defaultdict
from decimal import Decimal

from .dependency_model import stable_id
from .task_classifier import CATEGORIES, INTERNAL


def rank_regions(roots, slow_waits):
    """A ranking budget is not measured causal contribution or workload loss.

    Use the lesser of source growth and supported Wait growth as a conservative
    priority score, not a causal bound. Count each source execution once even
    when it reaches several concurrent Waits. Adjacent iterations form a display
    region, not a claim that all its tasks share a physical failure.
    """
    waits = {w["graph_id"]: w for w in slow_waits
             if w.get("duration_slow") and w.get("reference_count") == 5
             and w.get("delta_ns") is not None}
    groups = defaultdict(list)
    for root in roots:
        for field in ("source_region_id", "source_region_rank", "source_region_budget_ns"):
            root.pop(field, None)
        delta = max(Decimal(0), Decimal(root.get("delta_ns") or 0))
        supported = [waits[key] for key in set(root.get("affected_wait_graph_ids", [])) if key in waits]
        growth = max((max(Decimal(0), Decimal(w["delta_ns"])) for w in supported), default=Decimal(0))
        local = root.get("local_completion_evidence", {})
        completion_growth = max(Decimal(0), Decimal(local.get("delta_ns") or 0)) if local.get("validated") else Decimal(0)
        budget = min(delta, max(growth, completion_growth)) if root.get("diagnosis_category") == INTERNAL else Decimal(0)
        root.update(ranking_execution_budget_ns=str(budget), supported_wait_max_excess_ns=str(growth),
                    supported_wait_excess_beyond_source_growth_ns=str(max(Decimal(0), growth - delta)),
                    ranking_metric="bounded_execution_and_local_completion_excess_not_workload_loss" if completion_growth else "bounded_execution_excess_not_workload_loss")
        if root.get("diagnosis_category") == INTERNAL and root.get("primary_eligible"):
            location = (("named", root["group_id"]) if root.get("group_id") is not None else
                        ("legacy", root.get("block"), root.get("bucket")))
            groups[(root["node_id"], root["user_rank"], str(location))].append(root)
    regions = []
    for key, items in sorted(groups.items()):
        iterations = sorted({r["iteration"] for r in items})
        runs = []
        for iteration in iterations:
            if runs and iteration == runs[-1][-1] + 1:
                runs[-1].append(iteration)
            else:
                runs.append([iteration])
        for run in runs:
            selected = [r for r in items if r["iteration"] in run]
            # Multiple observations of the same execution must not multiply its budget.
            by_task = defaultdict(list)
            for root in selected:
                by_task[root["graph_id"]].append(Decimal(root["ranking_execution_budget_ns"]))
            budget = sum((max(values) for values in by_task.values()), Decimal(0))
            identifier = stable_id("source_region", (*key, *run))
            region = dict(id=identifier, node_id=key[0], user_rank=key[1], iterations=run,
                grouping_scope="same_node_rank_communication_group_adjacent_iterations",
                group_id=selected[0].get("group_id"), block=selected[0].get("block"), bucket=selected[0].get("bucket"),
                candidate_ids=sorted(r["root_id"] for r in selected), unique_execution_count=len(by_task),
                ranking_execution_budget_ns=str(budget),
                observed_start_ns=min(r["observed_start_ns"] for r in selected),
                observed_stop_ns=max(r["observed_stop_ns"] for r in selected),
                physical_cause_proven=False, workload_loss_ns=None)
            regions.append(region)
            for root in selected:
                root.update(source_region_id=identifier, source_region_budget_ns=str(budget))
    regions.sort(key=lambda r: (-Decimal(r["ranking_execution_budget_ns"]), -r["unique_execution_count"], r["id"]))
    for rank, region in enumerate(regions, 1):
        region["rank"] = rank
        for root in roots:
            if root.get("source_region_id") == region["id"]:
                root["source_region_rank"] = rank

    def priority(root):
        category = root["diagnosis_category"]
        if category == INTERNAL:
            return (CATEGORIES.index(category), not root["primary_eligible"],
                    -Decimal(root.get("source_region_budget_ns") or 0),
                    -Decimal(root["ranking_execution_budget_ns"]), -Decimal(root.get("delta_ns") or 0), root["root_id"])
        return (CATEGORIES.index(category), not root.get("external_clue_supported", False),
                -Decimal(root.get("delta_ns") or 0), Decimal(0), Decimal(0), root["root_id"])
    roots.sort(key=priority)
    return regions
