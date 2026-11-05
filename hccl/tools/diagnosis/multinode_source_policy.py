"""Explicit dual policy over strictly replayed tasks and protocol intervals."""
from __future__ import annotations

from copy import deepcopy
from decimal import Decimal

from .local_slow_clusters import ClusterOptions, analyze
from .source_selection import SelectionOptions, select_sources, _severity
from .source_events import slow


POLICY = "multinode_dual_v1"


def select(report, rows, edges, alignment, protocol_report=None, *, refined=False):
    options = ClusterOptions(source_factor=report["options"]["slowdown_factor"],
        mad_multiplier=report["options"]["mad_multiplier"])
    execution = analyze(report["tasks"], edges, options, alignment=alignment)
    hosts = [r for r in report["root_causes"] if r["component"] == "host_preparation"]
    selection_options = SelectionOptions(options.source_factor, options.mad_multiplier)
    result = select_sources(execution, hosts, selection_options)
    if refined:
        from .multinode_source_refinement import refine, finalize, validate_protocol_witnesses
        segments = (protocol_report or {}).get("segments", [])
        signatures = validate_protocol_witnesses(segments, rows, edges)
        return finalize(report, refine(result, segments, alignment, witness_signatures=signatures), edges, alignment)
    lookup, links = {r["_graph_id"]: r for r in rows}, {e["edge_id"]: e for e in edges}
    protocol_candidates, protocol_deferred = [], []
    # Prefer an evidenced upstream execution/preparation explanation over its protocol symptom.
    explained_waits = {w for c in execution["candidates"] for w in c["affected_wait_graph_ids"]}
    explained_waits.update(w for h in hosts if h["status"] == "dependency_supported_candidate" for w in h["affected_wait_graph_ids"])
    for item in (protocol_report or {}).get("segments", []):
        if not item.get("is_slow") or item.get("reference_count") != 5 or item.get("status") != "protocol_interval_observed":
            continue
        if item["completion_graph_id"] in explained_waits:
            protocol_deferred.append(dict(transfer_id=item["transfer_id"], reason="evidenced_upstream_source_exists"))
            continue
        node_ids, edge_ids = item["evidence_node_ids"], item["evidence_edge_ids"]
        if not node_ids or len(node_ids) != len(edge_ids) + 1 or node_ids[0] != item["protocol_start_graph_id"] or node_ids[-1] != item["completion_graph_id"]:
            raise ValueError("incomplete original protocol path")
        for i, key in enumerate(edge_ids):
            if key not in links or (links[key]["src"], links[key]["dst"]) != tuple(node_ids[i:i+2]):
                raise ValueError("protocol path must use the original graph")
        a, b = lookup[node_ids[0]], lookup[node_ids[-1]]
        if (a["_node_id"], a["_device_id"], a["_user_rank"]) != (b["_node_id"], b["_device_id"], b["_user_rank"]):
            raise ValueError("protocol duration requires same receiver endpoints")
        key = "protocol_source_" + item["transfer_id"]
        candidate = dict(candidate_id=key, root_id=key, graph_id=a["_graph_id"], anchor_graph_id=a["_graph_id"],
            component="protocol_interval", task_kind="protocol_interval", task_domain="hccl_protocol",
            node_id=a["_node_id"], device_id=a["_device_id"], user_rank=a["_user_rank"], stream_id=None, task_id=None,
            operation_scope=item["operation_scope"], stage=item["stage"], iteration=item["iteration"],
            block=item.get("block"), bucket=item.get("bucket"), call_site=item.get("call_site"),
            phase=item["phase"], step=item["step"], event="receiver_readiness_to_data_notification",
            observed_start_ns=item["protocol_start_ns"], observed_stop_ns=item["protocol_stop_ns"],
            duration_ns=item["protocol_duration_ns"], reference_mean_ns=item["reference_mean_ns"],
            reference_mad_ns=item["reference_mad_ns"], reference_count=5, reference_iterations=item["reference_iterations"],
            delta_ns=item["delta_ns"], status="protocol_path_candidate", physical_cause="unknown",
            slowdown_factor=str(Decimal(item["protocol_duration_ns"])/Decimal(item["reference_mean_ns"])),
            affected_wait_graph_ids=[item["completion_graph_id"]], evidence_paths={item["completion_graph_id"]: edge_ids},
            protocol_endpoints={k: item[k] for k in ("sender_node_id", "sender_rank", "receiver_node_id", "receiver_rank")},
            reason="Receiver-local protocol interval grew without an established upstream explanation; path candidate only, not a pure RDMA duration or a proved fault on this receiver.")
        protocol_candidates.append(candidate)
    protocol_candidates.sort(key=lambda c: (-_severity(c, selection_options), c["candidate_id"]))
    if protocol_candidates:
        primary = protocol_candidates[0]
        proposal = dict(proposal_id=primary["candidate_id"], mechanism="cross_node_protocol_slow",
            score=str(_severity(primary, selection_options)), candidate_ids=[primary["candidate_id"]], support_provenance="original_protocol_path")
        result["proposals"].append(proposal)
        if result["primary_proposal"] is None or Decimal(proposal["score"]) > Decimal(result["primary_proposal"]["score"]):
            result.update(primary_proposal=proposal, selected_mechanism=proposal["mechanism"], candidates=[primary], chains=[], host_support_chains=[])
    result["protocol_observations"] = dict(eligible_count=len(protocol_candidates), deferred=protocol_deferred,
        candidates=protocol_candidates, pure_network_completion_available=False)
    result["summary"].update(candidate_count=len(result["candidates"]),
        protocol_candidate_count=sum(c["task_kind"] == "protocol_interval" for c in result["candidates"]))
    roots = []
    for original in result["candidates"]:
        root = deepcopy(original)
        root.update(root_id=root["candidate_id"], source_selection_policy=POLICY)
        if root["task_kind"] == "host_interval":
            root["graph_id"] = root["anchor_graph_id"]
        elif root["task_kind"] != "protocol_interval":
            paths = {c["target_graph_id"]: c["edge_ids"] for c in result["chains"] if c["source_graph_id"] == root["graph_id"]}
            root.update(component="execution", evidence_paths=paths,
                dependency_timing={key: value for c in result["chains"] if c["source_graph_id"] == root["graph_id"]
                    for key, value in c.get("timing_evidence", {}).items()})
        roots.append(root)
    chosen = deepcopy(report)
    chosen.update(root_causes=roots, primary_source_candidate_id=roots[0]["root_id"] if roots else None,
        candidate_admission=None, source_regions=[], recommended_candidate_ids=[r["root_id"] for r in roots],
        diagnosis_status="localized_candidate" if roots else "unlocalized", source_selection_policy=POLICY)
    return chosen, result
