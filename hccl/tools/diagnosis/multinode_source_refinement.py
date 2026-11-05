"""Source-first refinement of public observations, not injection-labelled examples."""
from __future__ import annotations

from collections import Counter, defaultdict
from bisect import bisect_left, bisect_right
from copy import deepcopy
from decimal import Decimal
from fractions import Fraction
from math import ceil

from .clock_alignment import models_from_report
from .dependency_model import stable_id
from .source_events import statistics
from .source_selection import SelectionOptions, _severity, _validate_host
from .analyze_waits import ns


POLICY = "multinode_dual_v2"
SATURATION = Decimal("1.5")


def validate_protocol_witnesses(segments, rows, edges):
    nodes = {r["_graph_id"]: r for r in rows}
    links = {e["edge_id"]: e for e in edges}
    incoming = Counter(e["dst"] for e in edges if "notify_sync" in e["kind"])
    signatures = {}
    for item in segments:
        if item.get("status") != "protocol_interval_observed":
            continue
        identifiers, path = item["evidence_node_ids"], item["evidence_edge_ids"]
        if (not identifiers or len(identifiers) != len(path) + 1 or len(set(identifiers)) != len(identifiers)
                or identifiers[0] != item["protocol_start_graph_id"] or identifiers[-1] != item["completion_graph_id"]
                or item["payload_graph_id"] not in identifiers):
            raise ValueError("invalid original protocol witness identity")
        for i, key in enumerate(path):
            e = links.get(key)
            if (e is None or (e["src"], e["dst"]) != tuple(identifiers[i:i+2])
                    or e.get("confidence") not in {"exact", "observed"}
                    or not (e["kind"] == "direct_stream_order_observed" or "notify_sync" in e["kind"])):
                raise ValueError("protocol witness must follow original supported directed edges")
            a, b = nodes[e["src"]], nodes[e["dst"]]
            if a.get("_operation_scope") != item["operation_scope"] or b.get("_operation_scope") != item["operation_scope"]:
                raise ValueError("protocol witness crossed an operation boundary")
            if "notify_sync" in e["kind"] and (incoming[e["dst"]] != 1 or b.get("profiler_task_kind") != "notify_wait"):
                raise ValueError("protocol wait has an ambiguous producer")
        payload = nodes[item["payload_graph_id"]]
        done = nodes[item["completion_graph_id"]]
        ready = nodes[identifiers[0]]
        if ((payload["_node_id"], payload["_user_rank"], payload["_device_id"], payload["_stream_id"], payload["_task_id"])
                != tuple(item[k] for k in ("sender_node_id", "sender_rank", "sender_device_id", "sender_stream_id", "sender_task_id"))
                or (done["_node_id"], done["_user_rank"], done["_device_id"]) != tuple(
                    item[k] for k in ("receiver_node_id", "receiver_rank", "receiver_device_id"))):
            raise ValueError("protocol endpoint differs from the original physical task")
        if (payload.get("semantic") != "link_tx_payload" or ready.get("semantic") != "link_tx_ack"
                or done.get("semantic") not in {"link_rx_data_signal", "link_rx_payload_copy", "link_rx_payload_reduce"}
                or ns(payload, "start") != item["submission_start_ns"] or ns(payload, "stop") != item["submission_stop_ns"]
                or ns(ready, "start") != item["protocol_start_ns"] or ns(done, "stop") != item["protocol_stop_ns"]):
            raise ValueError("protocol observations differ from original endpoint timestamps or roles")
        signatures[item["transfer_id"]] = tuple((nodes[k]["_node_id"], nodes[k]["_user_rank"],
            nodes[k].get("profiler_task_kind"), nodes[k].get("semantic")) for k in identifiers)
    return signatures


def _log_strength(value, *, bounded=True):
    value = max(Decimal(0), Decimal(value))
    return (1 + (min(value, SATURATION) if bounded else value)).ln()


def _inverse(clock, reference_ns):
    raw = clock.local_anchor_ns + round(Fraction((reference_ns - clock.reference_anchor_ns)
        * clock.rate_denominator, clock.rate_numerator))
    timestamp = raw + clock.profiler_to_raw_offset_ns
    clock.map_ns(timestamp)
    return timestamp


def transfer_progress(segments, alignment, options=SelectionOptions(), *, witness_signatures=None):
    """Submission-to-data-notification estimates; never hardware wire durations."""
    clocks = models_from_report(alignment)
    observed, failures = {}, Counter()
    if witness_signatures is None:
        return [], dict(observed_count=0, compared_count=0, slow_count=0,
                        boundaries=dict(original_artifact_witness_validation_required=len(segments)))
    for item in segments:
        if item.get("status") != "protocol_interval_observed":
            continue
        key = item["transfer_id"]
        if key in observed:
            raise ValueError("duplicate original transfer identity")
        a = clocks.get((item["sender_node_id"], item["sender_device_id"]))
        b = clocks.get((item["receiver_node_id"], item["receiver_device_id"]))
        if a is None or b is None:
            failures["uncalibrated_transfer_boundary"] += 1
            continue
        try:
            a.map_ns(item["submission_start_ns"])
            stop = _inverse(a, b.map_ns(item["protocol_stop_ns"]))
        except ValueError:
            failures["outside_independent_probe_coverage"] += 1
            continue
        error = ceil(Fraction((a.estimated_error_ns + b.estimated_error_ns + 2)
                             * a.rate_denominator, a.rate_numerator))
        duration = stop - item["submission_start_ns"]
        if duration < 0:
            failures["uncertain_or_contradictory_transfer_interval"] += 1
            continue
        node_ids, edge_ids = item["evidence_node_ids"], item["evidence_edge_ids"]
        if len(node_ids) != len(edge_ids) + 1 or len(set(node_ids)) != len(node_ids):
            raise ValueError("invalid original protocol witness")
        position = node_ids.index(item["payload_graph_id"])
        if node_ids[-1] != item["completion_graph_id"] or not edge_ids[position:]:
            raise ValueError("missing submission-to-notification witness")
        observed[key] = dict(item, forward_duration_ns=duration, forward_stop_ns=stop,
            forward_error_ns=error, forward_edge_ids=edge_ids[position:],
            forward_node_ids=node_ids[position:], forward_slow=False,
            forward_comparison_status="insufficient_or_ambiguous_public_history")
    compared = []
    for item in observed.values():
        if item.get("stage") != "measured" or item.get("reference_count") != 5:
            continue
        references = [observed.get(key) for key in item["reference_transfer_ids"]]
        identity = ("sender_node_id", "sender_rank", "sender_device_id", "receiver_node_id", "receiver_rank",
                    "receiver_device_id", "group_id", "call_site", "occurrence", "block", "bucket",
                    "phase", "step", "payload_size_bytes")
        if (len(references) != 5 or any(r is None for r in references)
                or item.get("reference_iterations") != list(range(item["iteration"] - 5, item["iteration"]))
                or [r.get("iteration") for r in references] != item["reference_iterations"]
                or any(r.get("stage") != "measured" or any(r.get(k) != item.get(k) for k in identity)
                    or witness_signatures.get(r["transfer_id"]) != witness_signatures.get(item["transfer_id"])
                    for r in references)):
            continue
        mean, mad = statistics([r["forward_duration_ns"] for r in references])
        delta = Decimal(item["forward_duration_ns"]) - mean
        uncertainty = item["forward_error_ns"] + max(r["forward_error_ns"] for r in references)
        is_slow = (mean > 0 and item["forward_duration_ns"] >= mean * Decimal(options.source_factor)
                   and delta >= Decimal(options.mad_multiplier) * mad and delta > uncertainty)
        item.update(forward_reference_mean_ns=str(mean), forward_reference_mad_ns=str(mad),
            forward_delta_ns=str(delta), forward_comparison_error_ns=uncertainty, forward_slow=is_slow,
            forward_comparison_status="previous_five_with_clock_uncertainty")
        compared.append(item)
    return compared, dict(observed_count=len(observed), compared_count=len(compared),
                         slow_count=sum(r["forward_slow"] for r in compared), boundaries=dict(failures))


def _burst_context(group, candidates, segments):
    """Local co-slowing context; its window is learned from prior public call cadence."""
    identity = group["node_id"], group["user_rank"], group["device_id"]
    owner_group = candidates[group["preliminary_graph_ids"][0]].get("group_id")
    if not owner_group:
        return dict(multiplier="1", status="public_communication_group_unavailable")
    iteration = group["iteration"]
    if iteration < 10:
        return dict(multiplier="1", status="five_prior_comparable_alarm_epochs_unavailable")
    history, calls = {}, defaultdict(dict)
    for item in segments:
        if (item.get("status") != "protocol_interval_observed" or item.get("stage") != "measured"
                or (item.get("receiver_node_id"), item.get("receiver_rank"), item.get("receiver_device_id")) != identity
                or item.get("group_id") != owner_group
                or item.get("iteration") not in range(iteration - 5, iteration)):
            continue
        index = item["iteration"]
        start, stop = item["protocol_start_ns"], item["protocol_stop_ns"]
        old = history.get(index, (start, stop))
        history[index] = min(old[0], start), max(old[1], stop)
        position = (item.get("group_id"), item.get("call_site"), item.get("occurrence"), item.get("block"), item.get("bucket"))
        calls[index][position] = min(calls[index].get(position, start), start)
    if len(history) != 5:
        return dict(multiplier="1", status="missing_public_cadence_history")
    gaps = [b - a for values in calls.values() for a, b in zip(sorted(values.values()), sorted(values.values())[1:]) if b > a]
    if not gaps:
        return dict(multiplier="1", status="non_unique_public_call_cadence")
    gaps.sort()
    radius = gaps[len(gaps) // 2]
    center = (group["start_ns"] + group["stop_ns"]) // 2
    relevant = [c for c in candidates.values() if (c["node_id"], c["user_rank"], c["device_id"]) == identity
                and c.get("group_id") == owner_group]
    current = sorted((c["observed_start_ns"] + c["observed_stop_ns"]) // 2 for c in relevant if c["iteration"] == iteration)
    count = bisect_right(current, center + radius) - bisect_left(current, center - radius)
    neighbours = max(0, count - group["preliminary_count"])
    prior_count = sum(c["iteration"] in history for c in relevant)
    prior_ns = sum(stop - start for start, stop in history.values())
    expected = Decimal(prior_count) * (2 * radius) / prior_ns if prior_ns > 0 else Decimal(0)
    multiplier = 1 + max(Decimal(0), ((1 + Decimal(neighbours)) / (1 + expected)).ln())
    return dict(multiplier=str(multiplier), status="public_cadence_neighbour_context",
        radius_ns=radius, neighbour_count=neighbours, previous_five_alarm_count=prior_count,
        expected_neighbours=str(expected), window_start_ns=center - radius, window_stop_ns=center + radius,
        grouping_meaning="local_density_context_only_not_added_causal_edges_or_candidate_time_extension")


def _resource_proposals(selection, options, segments):
    execution = selection["execution_proposal"]
    candidates = {c["graph_id"]: c for c in execution["candidates"] + execution["deferred_candidates"]}
    proposals = []
    for group in execution["regions"]:
        units = defaultdict(list)
        members = []
        for key in group["preliminary_graph_ids"]:
            candidate = candidates[key]
            members.append(candidate)
            alarm = Decimal(group["task_scores"][key]["history_alarm_fraction"])
            units[(candidate["stream_id"], candidate["task_kind"])].append(
                _log_strength(_severity(candidate, options)) / (1 + alarm))
        values = [sum(items) / len(items) for items in units.values()]
        score = sum(values) / Decimal(len(values)).sqrt() * Decimal(group["temporal_density"])
        context = _burst_context(group, candidates, segments)
        score *= Decimal(context["multiplier"])
        proposals.append(dict(proposal_id=group["region_id"], mechanism="communication_execution_growth",
            score=str(score), evidence_unit_count=len(units), candidates=deepcopy(members),
            source_region=group, local_burst_context=context, isolated_sources_allowed=True))
    return proposals


def _host_proposals(selection, options):
    proposals, decisions = [], []
    for host in selection["external_host_observations"]:
        reason = _validate_host(host, options, allow_inherited_support=False)
        if reason:
            decisions.append(dict(source_activity_id=host.get("source_activity_id"), reason=reason))
            continue
        supporting = host["supporting_dependencies"]
        growth = max(Decimal(f["wait_comparison"]["duration_ns"]) - Decimal(
            f["wait_comparison"]["reference_mean_ns"]) for f in supporting)
        coverage = min(Decimal(1), Decimal(host["observed_wait_overlap_ns"]) / growth) if growth > 0 else Decimal(0)
        score = _severity(host, options) * coverage * len(supporting) / (len(supporting) + 1)
        source = deepcopy(host)
        source.update(candidate_id=host["root_id"], graph_id=host["anchor_graph_id"],
            source_unit="host_preparation", source_selection_policy=POLICY)
        proposals.append(dict(proposal_id=host["source_activity_id"], mechanism="host_preparation_late",
            score=str(score), evidence_unit_count=1, wait_growth_overlap_fraction=str(coverage), candidates=[source]))
    return proposals, decisions


def _transfer_proposals(observations, options):
    groups = defaultdict(list)
    for item in observations:
        groups[(item["sender_node_id"], item["sender_rank"], item["sender_device_id"], item["iteration"], item.get("group_id"))].append(item)
    proposals, deferred = [], []
    for identity, members in groups.items():
        if any(not item.get("call_site") for item in members):
            deferred.append(dict(identity=list(identity), reason="public_call_site_unavailable"))
            continue
        units = defaultdict(list)
        for item in members:
            if not item.get("call_site"):
                continue
            unit = (item.get("group_id"), item["call_site"], item.get("occurrence"), item["receiver_node_id"], item["receiver_rank"],
                    item["phase"], item["step"], item["payload_size_bytes"])
            units[unit].append(item)
        if any(len(value) != 1 for value in units.values()):
            deferred.append(dict(identity=list(identity), reason="ambiguous_public_transfer_cohort"))
            continue
        slow = [m for m in members if m["forward_slow"]]
        if len({m["call_site"] for m in slow}) < 2:
            deferred.append(dict(identity=list(identity), reason="isolated_protocol_symptom_not_endpoint_source",
                                 slow_count=len(slow)))
            continue
        values = []
        for item in slow:
            mean, mad = Decimal(item["forward_reference_mean_ns"]), Decimal(item["forward_reference_mad_ns"])
            severity = Decimal(item["forward_delta_ns"]) / max(mean, Decimal(options.mad_multiplier) * mad,
                                                               Decimal(item["forward_comparison_error_ns"]))
            values.append(_log_strength(severity))
        score = sum(values) / Decimal(len(units)).sqrt()
        sources = []
        for item in slow:
            identifier = stable_id("transfer_progress_source", (item["payload_graph_id"],))
            sources.append(dict(candidate_id=identifier, root_id=identifier, graph_id=item["payload_graph_id"],
                anchor_graph_id=item["payload_graph_id"], component="protocol_interval", source_unit="submission_to_notification_interval",
                node_id=item["sender_node_id"], user_rank=item["sender_rank"], device_id=item["sender_device_id"],
                stream_id=item["sender_stream_id"], task_id=item["sender_task_id"], task_kind="protocol_interval",
                task_domain="hccl_protocol", operation_scope=item["operation_scope"], stage="measured",
                iteration=item["iteration"], call_site=item["call_site"], occurrence=item.get("occurrence"),
                group_id=item.get("group_id"),
                phase=item["phase"], step=item["step"], event="payload_submission_to_data_notification",
                observed_start_ns=item["submission_start_ns"], observed_stop_ns=item["forward_stop_ns"],
                duration_ns=item["forward_duration_ns"], reference_mean_ns=item["forward_reference_mean_ns"],
                reference_mad_ns=item["forward_reference_mad_ns"], reference_count=5,
                reference_iterations=item["reference_iterations"], delta_ns=item["forward_delta_ns"],
                slowdown_factor=str(Decimal(item["forward_duration_ns"]) / Decimal(item["forward_reference_mean_ns"])),
                status="protocol_path_candidate", physical_cause="unknown", source_selection_policy=POLICY,
                affected_wait_graph_ids=[item["completion_graph_id"]],
                evidence_paths={item["completion_graph_id"]: item["forward_edge_ids"]},
                protocol_endpoints={k: item[k] for k in ("sender_node_id", "sender_rank", "receiver_node_id", "receiver_rank")},
                time_alignment_estimated_error_ns=item["forward_error_ns"],
                uncertainty_increase_budget_ns=item["forward_comparison_error_ns"],
                source_ownership="outgoing_payload_progress_not_proved_sender_hardware_fault",
                reason="Multiple publicly bound outgoing calls slowed after payload submission beyond clock uncertainty; interval includes queueing, transfer and notification, not hardware wire time."))
        sources.sort(key=lambda s: (s["observed_start_ns"], s["candidate_id"]))
        proposals.append(dict(proposal_id=stable_id("transfer_progress_cohort", identity),
            mechanism="outgoing_transfer_progress", score=str(score), evidence_unit_count=len(units),
            slow_unit_count=len(slow), candidates=sources, identity=list(identity),
            grouping_meaning="same_public_sender_iteration_cohort_not_new_causal_edges"))
    return proposals, deferred


def refine(selection, segments, alignment, *, witness_signatures=None):
    """No run IDs, expected faults, target ranks or evaluation windows are options."""
    options = SelectionOptions(**selection["options"])
    options.validate()
    resources = _resource_proposals(selection, options, segments)
    hosts, host_decisions = _host_proposals(selection, options)
    observed, coverage = transfer_progress(segments, alignment, options, witness_signatures=witness_signatures)
    transfers, deferred = _transfer_proposals(observed, options)
    # A sender-anchored protocol observation is not established source ownership.
    proposals = resources + hosts
    proposals.sort(key=lambda p: (-Decimal(p["score"]), p["proposal_id"]))
    primary = proposals[0] if proposals and Decimal(proposals[0]["score"]) > 0 else None
    candidates = deepcopy(primary["candidates"]) if primary else []
    for source in candidates:
        source.update(root_id=source["candidate_id"], source_selection_policy=POLICY)
        if source["task_kind"] not in {"host_interval", "protocol_interval"}:
            source.update(component="execution", source_unit="execution_task")
    return dict(schema_version=1, policy=POLICY, selected_mechanism=primary["mechanism"] if primary else "unlocalized",
        primary_proposal={k:v for k,v in primary.items() if k not in {"candidates", "source_region"}} if primary else None,
        candidates=candidates, source_region=primary.get("source_region") if primary else None,
        proposals=[{k:v for k,v in p.items() if k not in {"candidates", "source_region"}} for p in proposals],
        host_admission_decisions=host_decisions, transfer_coverage=coverage, deferred_transfer_cohorts=deferred,
        protocol_symptoms_are_not_roots=True, outgoing_path_observations=[{k:v for k,v in p.items() if k != "candidates"} for p in transfers],
        outgoing_path_candidates=[c for p in transfers for c in p["candidates"]],
        options=dict(selection["options"], saturation_increase=str(SATURATION)),
        source_count=len(candidates), truth_accessed=False,
        limits=["Known-sample offline development, not independent accuracy validation.",
            "Only public observations, exact history identities and already-built dependency witnesses are consumed.",
            "Source threshold stays 1.5x/3MAD against precisely the previous five measured iterations; no absolute-duration threshold.",
            "Readiness-to-notification intervals remain symptoms; calibrated submission-to-notification estimates are a different unit and are not RDMA hardware completion.",
            "Outgoing cohorts need multiple distinct public call sites; sender ownership does not prove a sender NIC fault.",
            "Transfer-path observations do not compete with evidenced execution or Host roots and are not counted as localized roots.",
            "Resource burst context uses the preceding five public call cadences, not a fixed or injected time window; original task spans remain unchanged.",
            "Execution singletons remain eligible without propagation. Relative ranking is not a calibrated physical-fault alarm.",
            "Newly selected execution paths must be reconstructed from original artifacts before a propagation claim is published."])


def finalize(report, decision, edges, alignment):
    """Rebuild selected sources' evidence using original comparisons and directed edges."""
    from .local_slow_clusters import ClusterOptions
    from .significant_regions import analyze_selected_tasks, slow
    from .wait_backtrace import WORK_KINDS
    roots, chains = [], []
    if decision["selected_mechanism"] == "communication_execution_growth":
        options = ClusterOptions(source_factor=decision["options"]["source_factor"],
                                 mad_multiplier=decision["options"]["mad_multiplier"])
        preliminary = [t for t in report["tasks"] if t.get("task_domain") == "hccl_internal"
                       and t["task_kind"] in WORK_KINDS and slow(t, options.source_factor, options)]
        group = dict(decision["source_region"], selected=True)
        probe = analyze_selected_tasks(report["tasks"], edges, preliminary, [group], options,
                                       include_wait_roots=False, alignment=alignment)
        by_id = {r["graph_id"]: r for r in probe["candidates"]}
        chains = probe["chains"]
        for selected in decision["candidates"]:
            source = dict(by_id[selected["graph_id"]], root_id=selected["candidate_id"], component="execution",
                          source_unit="execution_task", source_selection_policy=POLICY)
            paths = [c for c in chains if c["source_graph_id"] == source["graph_id"]]
            source["evidence_paths"] = {c["target_graph_id"]: c["edge_ids"] for c in paths}
            source["dependency_timing"] = {key:value for c in paths for key,value in c.get("timing_evidence", {}).items()}
            roots.append(source)
    else:
        roots = deepcopy(decision["candidates"])
    result = dict(decision, candidates=roots, chains=chains,
        summary=dict(candidate_count=len(roots), execution_candidate_count=sum(r["component"] == "execution" for r in roots),
                     host_interval_candidate_count=sum(r["component"] == "host_preparation" for r in roots),
                     propagation_chain_count=len(chains)),
        protocol_observations=dict(eligible_count=len(decision["outgoing_path_candidates"]),
            candidates=decision["outgoing_path_candidates"], disposition="path_observations_not_localized_roots",
            pure_network_completion_available=False))
    chosen = dict(report, root_causes=roots, primary_source_candidate_id=roots[0]["root_id"] if roots else None,
        candidate_admission=None, source_regions=[], recommended_candidate_ids=[r["root_id"] for r in roots],
        source_selection_policy=POLICY, source_policy_version=POLICY,
        diagnosis_status="localized_candidate" if roots else "unlocalized")
    return chosen, result
