"""One dependency cluster supported by a complete public work-population context."""
from __future__ import annotations

from collections import Counter, defaultdict
from decimal import Decimal

from .dependency_model import stable_id
from .local_slow_clusters import ClusterOptions, build_clusters
from .multinode_source_refinement import _host_proposals, _resource_proposals, finalize as finalize_original
from .source_selection import SelectionOptions
from .wait_backtrace import WORK_KINDS


POLICY = "dependency_cluster_cohort_v1"


def _cohort_key(task):
    fields = ("node_id", "device_id", "user_rank", "group_id", "iteration")
    if (task.get("stage") != "measured" or type(task.get("iteration")) is not int
            or any(task.get(k) in (None, "") for k in fields)):
        return None
    return tuple(task[k] for k in fields)


def cohort_contexts(tasks):
    """Include normal work; never compute the population quantile on slow tasks alone."""
    nodes = {t["graph_id"]: t for t in tasks}
    if len(nodes) != len(tasks):
        raise ValueError("duplicate public task identity")
    populations = defaultdict(list)
    for task in tasks:
        key = _cohort_key(task)
        if (key is not None and task.get("task_domain") == "hccl_internal"
                and task.get("task_kind") in WORK_KINDS and task.get("operation_scope")):
            populations[key].append(task)
    contexts = {}
    identity = ("node_id", "device_id", "user_rank", "group_id", "task_kind", "call_site", "phase", "step", "event")
    for key, members in populations.items():
        context = dict(node_id=key[0], device_id=key[1], user_rank=key[2], group_id=key[3], iteration=key[4],
            population_count=len(members), comparable_count=0, p95_factor=None, multiplier="1",
            status="population_below_twenty", meaning="public_population_context_not_a_causal_edge_or_new_candidate_group")
        contexts[key] = context
        # At n < 20 nearest-rank P95 is the maximum, not a robust population tail.
        if len(members) < 20:
            continue
        factors = []
        for task in members:
            refs = task.get("reference_graph_ids", [])
            epochs = list(range(task["iteration"] - 5, task["iteration"]))
            if (task.get("reference_count") != 5 or task.get("reference_iterations") != epochs
                    or len(refs) != 5 or len(set(refs)) != 5):
                continue
            history = [nodes.get(identifier) for identifier in refs]
            if any(h is None or h.get("stage") != "measured" or h.get("iteration") != epoch
                   or any(h.get(k) != task.get(k) for k in identity) for h, epoch in zip(history, epochs)):
                continue
            mean = Decimal(task["reference_mean_ns"])
            duration = Decimal(task["duration_ns"])
            if not mean.is_finite() or not duration.is_finite() or mean <= 0 or duration < 0:
                raise ValueError("cohort context requires finite positive references and nonnegative durations")
            if duration != task["observed_stop_ns"] - task["observed_start_ns"]:
                raise ValueError("cohort duration differs from the original task timestamps")
            factors.append(duration / mean)
        context["comparable_count"] = len(factors)
        if len(factors) != len(members):
            context["status"] = "incomplete_verified_previous_five_population"
            continue
        factors.sort()
        p95 = factors[(95 * len(factors) + 99) // 100 - 1]
        context.update(p95_factor=str(p95), multiplier=str(1 + max(Decimal(1), p95).ln()),
            status="complete_public_population", quantile="nearest_rank_p95_of_own_previous_five_duration_factors")
    return contexts


def rank(tasks, edges, hosts=(), options=ClusterOptions()):
    if options.selection_policy != "top1":
        raise ValueError("cohort source selection retains exactly one winning proposal")
    preliminary, clusters, quality = build_clusters(tasks, edges, options)
    contexts = cohort_contexts(tasks)
    nodes = {t["graph_id"]: t for t in tasks}
    candidates = [dict(t, candidate_id=stable_id("region_root", (t["graph_id"],))) for t in preliminary]
    selection = dict(execution_proposal=dict(regions=clusters, candidates=candidates, deferred_candidates=[]),
        external_host_observations=list(hosts))
    thresholds = SelectionOptions(options.source_factor, options.mad_multiplier)
    # Empty protocol cadence disables the old time-neighbour count multiplier.
    resources = _resource_proposals(selection, thresholds, [])
    for proposal in resources:
        cluster = proposal["source_region"]
        context = contexts.get(_cohort_key(nodes[cluster["preliminary_graph_ids"][0]]),
            dict(status="public_cohort_identity_unavailable", population_count=0, comparable_count=0,
                 p95_factor=None, multiplier="1"))
        base = Decimal(proposal["score"])
        score = base * Decimal(context["multiplier"])
        proposal.update(score=str(score), relative_base_score=str(base), cohort_context=context,
            local_burst_context=dict(multiplier="1", status="disabled_time_neighbours_not_source_evidence"))
        cluster.update(score=str(score), relative_base_score=str(base), cohort_context=context, selected=False)
    host_proposals, host_decisions = _host_proposals(selection, thresholds)
    proposals = resources + host_proposals
    proposals.sort(key=lambda p: (-Decimal(p["score"]), p["proposal_id"]))
    chosen = proposals[0] if proposals and Decimal(proposals[0]["score"]) > 0 else None
    selected_id = chosen["proposal_id"] if chosen else None
    for cluster in clusters:
        cluster["selected"] = cluster["region_id"] == selected_id
    return dict(policy=POLICY, selected_mechanism=chosen["mechanism"] if chosen else "unlocalized",
        primary_proposal={k: v for k, v in chosen.items() if k not in {"candidates", "source_region"}} if chosen else None,
        candidates=chosen["candidates"] if chosen else [], source_region=chosen.get("source_region") if chosen else None,
        proposals=[dict({k:v for k,v in p.items() if k not in {"candidates", "source_region"}},
            node_id=p["candidates"][0]["node_id"], user_rank=p["candidates"][0]["user_rank"],
            iteration=p["candidates"][0]["iteration"],
            candidate_graph_ids=[c["graph_id"] for c in p["candidates"]]) for p in proposals],
        clusters=clusters, cohort_quality=dict(Counter(c["status"] for c in contexts.values())),
        cluster_quality=quality, host_admission=host_decisions, outgoing_path_candidates=[],
        options=dict(source_factor=options.source_factor, mad_multiplier=options.mad_multiplier), truth_accessed=False,
        candidate_relationship="parallel", cluster_selection=dict(policy="top1", selected_cluster_id=selected_id,
            selected_cluster_count=int(chosen is not None), selected_mechanism=chosen["mechanism"] if chosen else "unlocalized",
            selected_score=chosen["score"] if chosen else None,
            cohort_context=chosen.get("cohort_context") if chosen else None,
            ranking_metric="relative_cluster_score_without_burst_times_one_plus_log_full_cohort_p95"),
        limits=["Experimental known-sample development; default and original cluster membership are unchanged.",
            "Only the winning original dependency cluster or evidenced Host interval is published; members are peers.",
            "Public cohort P95 includes normal comparable work, not only preselected slow tasks; it does not merge clusters.",
            "Incomplete, missing-identity or fewer-than-twenty populations receive neutral support, not inferred observations.",
            "P95 context is not a hard admission gate; original 1.5x/3MAD history and directed dependency gates remain.",
            "No time-neighbour count bonus, injection truth, target rank or physical resource cause is used.",
            "Relative scores and population tails are not workload delay, independent sample counts or calibrated false-alarm probabilities."])


def finalize(report, decision, edges, alignment=None):
    chosen, result = finalize_original(report, decision, edges, alignment)
    for source in chosen["root_causes"]:
        source["source_selection_policy"] = POLICY
    chosen.update(primary_source_candidate_id=None, source_selection_policy=POLICY,
        source_policy_version=POLICY, candidate_relationship="parallel", limits=decision["limits"])
    result["summary"]["selected_cluster_count"] = decision["cluster_selection"]["selected_cluster_count"]
    return chosen, result


def select(report, edges, alignment=None):
    options = ClusterOptions(source_factor=report["options"]["slowdown_factor"],
                             mad_multiplier=report["options"]["mad_multiplier"])
    hosts = [r for r in report["root_causes"] if r.get("component") == "host_preparation"]
    return finalize(report, rank(report["tasks"], edges, hosts, options), edges, alignment)
