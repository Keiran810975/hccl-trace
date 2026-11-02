"""Exploratory candidate admission over public observations, never fault labels.

This does not rewrite source discovery. Every rejected candidate and its reason
remain in the audit. A small selected set is not, by itself, improved accuracy.
"""
from __future__ import annotations

from collections import defaultdict
from decimal import Decimal

from . import critical_path as critical
from .task_classifier import INTERNAL


POLICIES = ("all", "critical_path", "wait_critical_path", "history_envelope", "envelope_dominant_region")
REGION_SEPARATION = Decimal(3)


def _decimal(value):
    try:
        result = Decimal(str(value))
        return result if result.is_finite() else None
    except ArithmeticError:
        return None


def select_candidates(roots, tasks=(), *, policy="all", wait_impacts=None):
    """Select, but never mutate, already evidenced internal source candidates.

    History admission uses the original preceding-five task IDs. It is an extra
    guard against a mean-based alarm inside a previously observed high range;
    it is not a significance test or an independent causal attribution.
    Region dominance is a declared heuristic, not a posterior probability.
    """
    if policy not in POLICIES:
        raise ValueError("unknown candidate policy")
    lookup = {t["graph_id"]: t for t in tasks}
    if len(lookup) != len(tasks):
        raise ValueError("candidate screening requires unique task observations")
    candidates = [r for r in roots if r.get("diagnosis_category") == INTERNAL]
    if len({r["root_id"] for r in candidates}) != len(candidates):
        raise ValueError("candidate screening requires unique source IDs")
    decisions = []
    for root in candidates:
        item = dict(candidate_id=root["root_id"], graph_id=root["graph_id"],
                    selected=True, reason="original_evidenced_candidate")
        if policy == "critical_path":
            slack = root.get("critical_path_slack_ns")
            valid = root.get("critical_path_status") in {"observed_model", "partial_evidence"}
            item.update(selected=valid and slack == 0,
                        reason="zero_local_slack" if valid and slack == 0 else
                               "local_critical_path_unavailable" if not valid or slack is None else "positive_local_slack",
                        slack_ns=slack, model_status=root.get("critical_path_status"),
                        partial_model=bool(valid and root.get("critical_path_status") == "partial_evidence"))
        elif policy == "wait_critical_path":
            evidence = (wait_impacts or {}).get(root["root_id"], {})
            item.update(selected=evidence.get("max_modeled_wait_gain_ns", 0) > 0,
                        reason="positive_local_wait_endpoint_gain" if evidence.get("max_modeled_wait_gain_ns", 0) > 0
                               else "no_local_wait_endpoint_gain" if evidence.get("checked_wait_count", 0)
                               else "local_wait_impact_unavailable",
                        wait_endpoint_evidence=evidence)
        elif policy in {"history_envelope", "envelope_dominant_region"}:
            source = lookup.get(root["graph_id"], root)
            identifiers = source.get("reference_graph_ids", [])
            history = [lookup.get(key) for key in identifiers]
            expected = list(range(root["iteration"] - 5, root["iteration"]))
            valid = (len(identifiers) == len(set(identifiers)) == 5 and all(history)
                     and source.get("reference_count") == 5
                     and source.get("reference_iterations") == expected)
            if valid:
                for previous, iteration in zip(history, expected):
                    valid = valid and all(previous.get(k) == root.get(k) for k in
                                          ("node_id", "user_rank", "device_id", "phase", "step", "event", "task_kind"))
                    valid = valid and previous.get("iteration") == iteration and previous.get("stage") == "measured"
            durations = [_decimal(h.get("duration_ns")) for h in history] if valid else []
            value = _decimal(source.get("duration_ns"))
            valid = bool(valid and value is not None and all(d is not None and d >= 0 for d in durations))
            peak = max(durations) if valid else None
            item.update(selected=bool(valid and value > peak),
                        reason="above_previous_five_maximum" if valid and value > peak else
                               "inside_previous_five_envelope" if valid else "missing_or_incompatible_history",
                        reference_max_ns=str(peak) if peak is not None else None,
                        history_graph_ids=identifiers, reference_iterations=expected)
        decisions.append(item)
    dominance = None
    if policy == "envelope_dominant_region":
        accepted = {d["candidate_id"] for d in decisions if d["selected"]}
        budgets = defaultdict(dict)
        for root in candidates:
            if root["root_id"] not in accepted or not root.get("source_region_id"):
                continue
            budget = _decimal(root.get("ranking_execution_budget_ns"))
            if budget is not None and budget > 0:
                by_task = budgets[root["source_region_id"]]
                by_task[root["graph_id"]] = max(by_task.get(root["graph_id"], Decimal(0)), budget)
        ranked = sorted(((sum(values.values()), key) for key, values in budgets.items()), reverse=True)
        top = ranked[0][0] if ranked else Decimal(0)
        second = ranked[1][0] if len(ranked) > 1 else Decimal(0)
        unique = bool(ranked and top > 0 and top > second and top >= REGION_SEPARATION * second)
        chosen = ranked[0][1] if unique else None
        dominance = dict(selected_region_id=chosen, separation_factor=str(REGION_SEPARATION),
                         largest_budget_ns=str(top), second_budget_ns=str(second),
                         separated=unique, physical_cause_proven=False)
        by_id = {r["root_id"]: r for r in candidates}
        for item in decisions:
            if item["selected"] and by_id[item["candidate_id"]].get("source_region_id") != chosen:
                item.update(selected=False, reason="non_dominant_region" if chosen else "no_separated_positive_region")
            elif item["selected"] and chosen is None:
                item.update(selected=False, reason="no_separated_positive_region")
    selected = [d["candidate_id"] for d in decisions if d["selected"]]
    return dict(schema_version=1, policy=policy, selected_candidate_ids=selected,
                original_candidate_count=len(candidates), selected_candidate_count=len(selected),
                deferred_candidate_count=len(candidates) - len(selected), decisions=decisions, dominance=dominance,
                truth_consumed=False, original_candidates_changed=False,
                evidence_class="exploratory_candidate_admission_not_validated_accuracy",
                limitations=["No source/edge/time is reconstructed or reassigned.",
                             "Local criticality is not global workload criticality or causal proof.",
                             "History envelope and region dominance are heuristics, not statistical confidence.",
                             "Abstention is not success; evaluate misses and normal controls separately."])


def local_wait_impacts(roots, rows, edges):
    """What-if only the reported local Wait endpoints, not unrelated call tails.

    Cross-call/node evidence is not silently timed as a local path. All endpoint
    checks are retained, including unavailable models and zero gains.
    """
    nodes = {r["_graph_id"]: r for r in rows}
    links = {e["edge_id"]: e for e in edges}
    groups, group_edges = defaultdict(list), defaultdict(list)
    for row in rows:
        groups[(row.get("_operation_scope"), row["_node_id"])].append(row)
    for edge in edges:
        source, target = nodes[edge["src"]], nodes[edge["dst"]]
        key = source.get("_operation_scope"), source["_node_id"]
        if key == (target.get("_operation_scope"), target["_node_id"]):
            group_edges[key].append(edge)
    result = {}
    for root in roots:
        if root.get("diagnosis_category") != INTERNAL:
            continue
        key = root["operation_scope"], root["node_id"]
        checks = []
        for identifier in root.get("affected_wait_graph_ids", []):
            target = nodes.get(identifier)
            path = root.get("evidence_paths", {}).get(identifier, [])
            check = dict(wait_graph_id=identifier, modeled_gain_ns=None)
            cursor = root["graph_id"]
            valid = bool(target and path and key == (target.get("_operation_scope"), target["_node_id"]))
            for edge_id in path:
                edge = links.get(edge_id)
                if not edge or edge["src"] != cursor:
                    valid = False
                    break
                cursor = edge["dst"]
                row = nodes[cursor]
                valid = valid and key == (row.get("_operation_scope"), row["_node_id"])
            valid = valid and cursor == identifier
            if not valid:
                check["status"] = "path_outside_local_call_or_incomplete"
            else:
                try:
                    model = critical.analyze_critical_path(groups[key], group_edges[key],
                                                           completion_ids=(identifier,), impact_limit=0)
                    delta = _decimal(root.get("delta_ns"))
                    if delta is None or delta <= 0:
                        raise ValueError("source has no positive execution increment")
                    gain = critical.execution_reduction_gains(model, {root["graph_id"]: int(delta)})[root["graph_id"]]
                    check.update(status=model["status"], modeled_gain_ns=gain,
                                 interpretation="fixed_schedule_model_not_measured_causal_contribution")
                except (ValueError, KeyError) as error:
                    check.update(status="unavailable", detail=str(error))
            checks.append(check)
        result[root["root_id"]] = dict(checks=checks,
            checked_wait_count=sum(c["modeled_gain_ns"] is not None for c in checks),
            max_modeled_wait_gain_ns=max((c["modeled_gain_ns"] for c in checks if c["modeled_gain_ns"] is not None), default=0),
            global_workload_impact_proven=False)
    return result
