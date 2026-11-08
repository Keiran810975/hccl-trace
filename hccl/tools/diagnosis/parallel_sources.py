"""Public dependency-cluster Top1; historical all-call prototype helpers below."""
from __future__ import annotations

from collections import defaultdict
from copy import deepcopy
from decimal import Decimal

from .dependency_model import stable_id
from .significant_regions import RegionOptions, analyze_selected_tasks, slow
from .source_events import statistics
from .source_selection import SelectionOptions, _validate_host
from .wait_backtrace import WORK_KINDS


POLICY = "multinode_parallel_v1"


def _owner(task):
    return task["node_id"], task["device_id"], task["user_rank"]


def _call(task):
    return (*_owner(task), task["operation_scope"], *(task.get(k) or "" for k in ("algorithm", "phase", "event", "task_kind")))


def _position(task):
    if task.get("group_id") is not None:
        return task["group_id"], task.get("call_site"), task.get("occurrence")
    return task.get("block"), task.get("bucket")


def call_spans(tasks):
    """Local device-task envelopes of evidenced calls, not iteration wall times."""
    spans = {}
    for task in tasks:
        if task.get("stage") != "measured" or not task.get("operation_scope"):
            continue
        key = (*_owner(task), task["operation_scope"])
        start, stop = task["observed_start_ns"], task["observed_stop_ns"]
        if key in spans:
            start, stop = min(start, spans[key][0]), max(stop, spans[key][1])
        spans[key] = start, stop
    return spans


def qualify_call_spans(regions, spans, options=RegionOptions()):
    selected, decisions = [], []
    for region in regions:
        key = (*_owner(region), region["operation_scope"])
        history = [(*_owner(region), scope) for scope in region["reference_operation_scopes"]]
        if key not in spans or any(k not in spans for k in history):
            decisions.append(dict(region_id=region["region_id"], admitted=False, reason="missing_full_call_envelope"))
            continue
        values = [spans[k][1] - spans[k][0] for k in history]
        mean, mad = statistics(values)
        observed = spans[key][1] - spans[key][0]
        admitted = (mean > 0 and observed > mean
                    and observed - mean >= mad * Decimal(options.mad_multiplier))
        evidence = dict(region_id=region["region_id"], admitted=admitted,
            reason="observed_call_also_slow" if admitted else "call_envelope_not_slow",
            observed_duration_ns=observed, reference_mean_ns=str(mean), reference_mad_ns=str(mad),
            reference_durations_ns=values, reference_operation_scopes=region["reference_operation_scopes"],
            meaning="same_rank_local_observed_HCCL_task_envelope_not_global_workload_latency",
            rule="positive_call_growth_beyond_3MAD_not_a_second_1.5x_task_threshold")
        decisions.append(evidence)
        if admitted:
            selected.append(dict(region, call_span_evidence=evidence))
    return selected, decisions


def work_units(tasks, options=RegionOptions()):
    """Compare a full semantic work unit, not just its already-slow tasks.

    The work sum is an accounting statistic over potentially parallel tasks, not
    elapsed communication time or estimated workload loss.
    """
    options.validate()
    nodes = {t["graph_id"]: t for t in tasks}
    if len(nodes) != len(tasks):
        raise ValueError("duplicate task identity")
    calls = defaultdict(list)
    for task in tasks:
        if (task.get("stage") == "measured" and task.get("operation_scope")
                and task.get("task_domain") == "hccl_internal" and task.get("task_kind") in WORK_KINDS):
            calls[_call(task)].append(task)
    regions, decisions = [], []
    for key, members in sorted(calls.items()):
        iterations = {t.get("iteration") for t in members}
        if len(iterations) != 1 or None in iterations:
            raise ValueError("one evidenced call must belong to one measured iteration")
        iteration = next(iter(iterations))
        if iteration < 5:
            continue
        reason, history_calls, history_ids = None, [None] * 5, [set() for _ in range(5)]
        sums = [0] * 5
        for task in members:
            identifiers = task.get("reference_graph_ids", [])
            if (task.get("reference_count") != 5 or len(identifiers) != 5 or len(set(identifiers)) != 5
                    or task.get("reference_iterations") != list(range(iteration - 5, iteration))):
                reason = "incomplete_or_ambiguous_task_history"
                break
            for index, identifier in enumerate(identifiers):
                prior = nodes.get(identifier)
                if (prior is None or _owner(prior) != _owner(task) or _position(prior) != _position(task)
                        or prior.get("task_kind") != task["task_kind"] or prior.get("stage") != "measured"
                        or prior.get("iteration") != iteration - 5 + index or identifier in history_ids[index]):
                    reason = "history_identity_or_position_mismatch"
                    break
                call = _call(prior)
                if history_calls[index] is not None and history_calls[index] != call:
                    reason = "history_crossed_call_boundary"
                    break
                history_calls[index] = call
                history_ids[index].add(identifier)
                sums[index] += prior["duration_ns"]
            if reason:
                break
        if not reason and any(history_ids[i] != {t["graph_id"] for t in calls.get(call, [])}
                              for i, call in enumerate(history_calls)):
            reason = "work_population_changed"
        record = dict(node_id=key[0], device_id=key[1], user_rank=key[2], operation_scope=key[3],
                      algorithm=key[4], phase=key[5], event=key[6], task_kind=key[7],
                      **{k: members[0].get(k) for k in ("group_id", "call_site", "occurrence", "block", "bucket")},
                      iteration=iteration, task_count=len(members), admitted=False)
        if reason:
            decisions.append(dict(record, reason=reason))
            continue
        mean, mad = statistics(sums)
        observed = sum(t["duration_ns"] for t in members)
        intrinsic = [t for t in members if slow(t, options.source_factor, options)]
        record.update(work_sum_ns=observed, reference_work_sums_ns=sums,
            reference_mean_ns=str(mean), reference_mad_ns=str(mad),
            reference_iterations=list(range(iteration - 5, iteration)),
            reference_operation_scopes=[c[3] for c in history_calls],
            work_sum_factor=str(Decimal(observed) / mean) if mean > 0 else None,
            intrinsic_slow_count=len(intrinsic),
            meaning="full_identical_semantic_work_unit_not_elapsed_time_or_causal_loss")
        if mean <= 0 or observed <= mean:
            reason = "no_positive_work_growth"
        elif observed < mean * Decimal(options.source_factor) or observed - mean < mad * Decimal(options.mad_multiplier):
            reason = "whole_call_work_not_slow"
        elif len(intrinsic) < 2:
            reason = "isolated_task_not_coherent_call_slowdown"
        else:
            reason = "coherent_call_work_growth"
        record.update(reason=reason, admitted=reason == "coherent_call_work_growth")
        decisions.append(record)
        if record["admitted"]:
            regions.append(dict(region_id=stable_id("parallel_call", key), **record, selected=True,
                preliminary_graph_ids=sorted(t["graph_id"] for t in intrinsic),
                start_ns=min(t["observed_start_ns"] for t in members),
                stop_ns=max(t["observed_stop_ns"] for t in members), score="0"))
    return regions, decisions


def execution_calls(tasks, options=RegionOptions()):
    regions, decisions = work_units(tasks, options)
    epochs = defaultdict(lambda: defaultdict(list))
    for record in decisions:
        if "work_sum_factor" not in record:
            continue
        key = (*_owner(record), record["group_id"], record["algorithm"], record["phase"], record["event"], record["task_kind"])
        epochs[key][record["iteration"]].append(record)
    accepted, observations = set(), {}
    for values in epochs.values():
        for iteration, members in values.items():
            identity = lambda r: _call(r)
            current = [r for r in members if r["admitted"]]
            reason, evidence = None, dict(iteration=iteration, slow_call_count=len(current))
            positions = {_position(r) for r in members}
            if len(positions) != len(members):
                reason = "ambiguous_public_call_population"
            elif len(current) < 2:
                reason = "not_repeated_across_public_calls"
            else:
                totals = [sum(r["reference_work_sums_ns"][i] for r in members) for i in range(5)]
                observed = sum(r["work_sum_ns"] for r in members)
                mean, mad = statistics(totals)
                evidence.update(work_sum_ns=observed, reference_work_sums_ns=totals,
                    reference_mean_ns=str(mean), reference_mad_ns=str(mad),
                    reference_iterations=list(range(iteration - 5, iteration)), compared_call_count=len(members))
                if (mean <= 0 or observed <= mean or observed < mean * Decimal(options.propagation_factor)
                        or observed - mean < mad * Decimal(options.mad_multiplier)):
                    reason = "rank_semantic_work_not_above_own_history"
                else:
                    reason = "corroborated_semantic_work_growth"
                    accepted.update(identity(r) for r in current)
            for record in current:
                observations[identity(record)] = dict(evidence, reason=reason,
                    meaning="same_rank_iteration_public_call_corroboration_not_new_causal_edges")
    chosen = []
    for region in regions:
        if _call(region) in accepted:
            chosen.append(dict(region, burst_evidence=observations[_call(region)]))
    updated = [dict(r, local_unit_slow=r["admitted"], admitted=_call(r) in accepted,
                    reason=observations[_call(r)]["reason"], burst_evidence=observations[_call(r)])
               if r["admitted"] else r for r in decisions]
    return chosen, updated


def select_all_calls_prototype(report, edges, alignment=None):
    """All eligible calls are peers; scores never eliminate another call."""
    options = RegionOptions(source_factor=report["options"]["slowdown_factor"],
                            secondary_factor=str(max(Decimal("2.5"), Decimal(report["options"]["slowdown_factor"]))),
                            mad_multiplier=report["options"]["mad_multiplier"])
    regions, decisions = execution_calls(report["tasks"], options)
    regions, span_decisions = qualify_call_spans(regions, report.get("call_span_observations") or call_spans(report["tasks"]), options)
    preliminary = [t for t in report["tasks"] if t.get("task_domain") == "hccl_internal"
                   and t.get("task_kind") in WORK_KINDS and slow(t, options.source_factor, options)]
    probe = analyze_selected_tasks(report["tasks"], edges, preliminary, regions, options,
                                   include_wait_roots=False, alignment=alignment)
    roots = []
    call_evidence = {r["region_id"]: r for r in regions}
    for candidate in probe["candidates"]:
        source = dict(candidate, root_id=candidate["candidate_id"], component="execution",
                      source_unit="execution_task", source_selection_policy=POLICY)
        paths = [c for c in probe["chains"] if c["source_graph_id"] == source["graph_id"]]
        source["evidence_paths"] = {c["target_graph_id"]: c["edge_ids"] for c in paths}
        source["dependency_timing"] = {k: v for c in paths for k, v in c.get("timing_evidence", {}).items()}
        source["call_work_evidence"] = call_evidence[source["region_id"]]
        source["event_slow"] = True
        roots.append(source)
    host_decisions = []
    for original in report["root_causes"]:
        if original.get("component") != "host_preparation":
            continue
        reason = _validate_host(original, SelectionOptions(options.source_factor, options.mad_multiplier), False)
        host_decisions.append(dict(source_activity_id=original.get("source_activity_id"), reason=reason or "admitted"))
        if reason is None:
            roots.append(dict(deepcopy(original), source_selection_policy=POLICY, source_unit="host_preparation"))
    roots.sort(key=lambda r: (r["iteration"], r["node_id"], r["user_rank"], r["observed_start_ns"], r["root_id"]))
    decision = dict(schema_version=1, policy=POLICY, candidate_relationship="parallel", truth_accessed=False,
        call_admission=decisions, host_admission=host_decisions, candidates=roots,
        call_span_admission=span_decisions,
        summary=dict(candidate_count=len(roots), admitted_unit_count=len(regions),
                     admitted_call_count=len({(r["node_id"], r["device_id"], r["operation_scope"]) for r in regions}),
                     propagation_chain_count=len(probe["chains"])),
        limits=["Exploratory offline policy, not independent accuracy validation or calibrated false-alarm control.",
            "Every admitted call is retained; neither another iteration's maximum nor candidate order defines priority.",
            "Within each call, identical full algorithm/phase/event/task-kind populations use exactly five prior measured iterations, 1.5x and 3MAD by default.",
            "At least two intrinsically slow tasks are required; a genuine isolated-task fault can be missed.",
            "A semantic work unit must slow in at least two public calls in one rank/iteration; its full work population must also grow at least 20% and 3MAD over the same five original history populations.",
            "Work sums account for potentially parallel execution; they are not elapsed communication time or workload loss.",
            "Only original supported dependency edges establish propagation; no edge is added from co-slowing.",
            "Intrinsic execution growth and established downstream propagation are separate evidence claims; an execution candidate need not have a slow peer Wait path.",
            "Protocol path symptoms are not assigned to a sender or receiver physical fault."])
    chosen = dict(report, root_causes=roots, primary_source_candidate_id=None, candidate_admission=None,
        source_regions=[], recommended_candidate_ids=[r["root_id"] for r in roots],
        source_policy_version=POLICY, source_selection_policy=POLICY, candidate_relationship="parallel",
        diagnosis_status="localized_candidate" if roots else "unlocalized", limits=decision["limits"])
    return chosen, decision


def select(report, edges, alignment=None, *, rows, protocol_report=None):
    """Preserve validated dual-v2 Top1 selection; only its members are peers."""
    from .multinode_source_policy import select as select_original
    chosen, result = select_original(report, rows, edges, alignment, protocol_report, refined=True)
    proposal = result["primary_proposal"]
    result.update(candidate_relationship="parallel", host_admission=result["host_admission_decisions"],
        cluster_selection=dict(policy="top1", selected_cluster_count=int(bool(result["candidates"])),
            selected_cluster_id=proposal["proposal_id"] if proposal else None,
            selected_mechanism=result["selected_mechanism"], selected_score=proposal["score"] if proposal else None,
            ranking_metric="original_dual_v2_relative_cluster_score_unchanged"))
    chosen["primary_source_candidate_id"] = None
    return chosen, result
