"""Select between a resource Top1 proposal and evidenced Host preparation delay."""
from __future__ import annotations

from collections import defaultdict
from copy import deepcopy
from dataclasses import asdict, dataclass
from decimal import Decimal
import html

from .source_events import statistics


@dataclass(frozen=True)
class SelectionOptions:
    source_factor: str = "1.5"
    mad_multiplier: str = "3"

    def validate(self):
        if any(not Decimal(v).is_finite() or Decimal(v) < minimum for v, minimum in (
                (self.source_factor, 1), (self.mad_multiplier, 0))):
            raise ValueError("invalid source selection thresholds")


def _severity(item, options):
    mean, mad = Decimal(item["reference_mean_ns"]), Decimal(item["reference_mad_ns"])
    duration = Decimal(item["duration_ns"])
    if not all(v.is_finite() for v in (mean, mad, duration)) or mean <= 0 or mad < 0 or duration < 0:
        raise ValueError("source score needs finite positive history and nonnegative durations")
    return (duration - mean) / max(mean, Decimal(options.mad_multiplier) * mad)


def _is_slow(item, options):
    mean, mad, duration = (Decimal(item[key]) for key in ("reference_mean_ns", "reference_mad_ns", "duration_ns"))
    return (_severity(item, options) > 0 and duration >= mean * Decimal(options.source_factor)
            and duration - mean >= mad * Decimal(options.mad_multiplier))


def _validate_host(host, options, allow_inherited_support):
    if host.get("status") != "dependency_supported_candidate":
        return "no_slow_peer_wait_support"
    if (host.get("task_domain") != "host_preparation" or host.get("task_kind") != "host_interval"
            or host.get("task_id") is not None or host.get("stream_id") is not None
            or not host.get("source_activity_id") or host.get("traversal_truncated")
            or host.get("stage") != "measured" or host.get("reference_count") != 5):
        return "invalid_host_activity_identity_or_history"
    iteration = host["iteration"]
    if host.get("reference_iterations") != list(range(iteration - 5, iteration)) or iteration < 5:
        return "invalid_previous_five_boundary"
    references = host.get("reference_preparations", [])
    if (len(references) != 5 or len({p["operation_scope"] for p in references}) != 5
            or [p["operation_scope"] for p in references] != host.get("reference_operation_scopes")
            or any((p["node_id"], p["user_rank"], p["device_id"])
                != (host["node_id"], host["user_rank"], host["device_id"])
                or not p["start_ns"] <= p["stop_ns"] <= p["api_start_ns"] <= p["api_stop_ns"]
                or not p.get("evidence") for p in references)):
        return "invalid_public_preparation_references"
    mean, mad = statistics([p["stop_ns"] - p["start_ns"] for p in references])
    duration = host["observed_stop_ns"] - host["observed_start_ns"]
    if (duration != host["duration_ns"] or mean != Decimal(host["reference_mean_ns"])
            or mad != Decimal(host["reference_mad_ns"]) or mean <= 0
            or duration <= mean or duration < mean * Decimal(options.source_factor)
            or duration - mean < mad * Decimal(options.mad_multiplier)):
        return "preparation_not_slow_under_frozen_rule"
    affected, paths = host.get("affected_wait_graph_ids", []), host.get("evidence_paths", {})
    if (not affected or len(set(affected)) != len(affected) or set(paths) != set(affected)
            or any(len(paths[key]) != 1 for key in affected) or host.get("observed_wait_overlap_ns", 0) <= 0):
        return "incomplete_notify_support_claim"
    if "support_evidence_version" not in host:
        return None if allow_inherited_support else "original_endpoint_facts_unavailable"
    if host["support_evidence_version"] != 1:
        return "unsupported_evidence_version"
    facts = host.get("supporting_dependencies", [])
    if len(facts) != len(affected):
        return "incomplete_notify_endpoint_facts"
    for fact in facts:
        edge, producer, wait = fact["edge"], fact["producer"], fact["wait"]
        wc = fact["wait_comparison"]
        if (wait["graph_id"] not in paths or paths[wait["graph_id"]] != [edge["edge_id"]]
                or edge["src"] != producer["graph_id"] or edge["dst"] != wait["graph_id"]
                or not fact.get("unique_notify_producer") or fact["overlap_ns"] <= 0
                or (producer["node_id"], producer["device_id"], producer["user_rank"], producer["operation_scope"])
                   != (host["node_id"], host["device_id"], host["user_rank"], host["operation_scope"])
                or producer["operation_scope"] != wait["operation_scope"]
                or producer["user_rank"] == wait["user_rank"] or wait["task_kind"] != "notify_wait"
                or not host["observed_stop_ns"] <= host["api_start_ns"] <= host["api_stop_ns"]
                or host["api_start_ns"] > producer["observed_start_ns"]
                or not wc["duration_slow"] or wc["reference_count"] != 5
                or wc["reference_iterations"] != host["reference_iterations"]
                or wc["duration_ns"] != wait["observed_stop_ns"] - wait["observed_start_ns"]
                or not _is_slow(wc, options)
                or producer["observed_stop_ns"] < producer["observed_start_ns"]):
            return "notify_support_identity_or_timing_failed"
        if producer["node_id"] == wait["node_id"]:
            overlap = min(host["observed_stop_ns"], wait["observed_stop_ns"]) - max(
                host["observed_start_ns"], wait["observed_start_ns"])
            if (edge["confidence"] != "exact" or "notify_sync" not in edge["kind"]
                    or producer["task_kind"] != "notify_record" or overlap != fact["overlap_ns"]
                    or producer["observed_stop_ns"] > wait["observed_stop_ns"]):
                return "local_notify_support_failed"
        else:
            alignment = fact.get("alignment")
            if (edge["kind"] != "cross_node_notify_sync_observed" or edge["confidence"] != "observed"
                    or not alignment or producer["task_kind"] not in {"rdma", "notify_record"}):
                return "uncalibrated_cross_node_support"
            hs, he = alignment["preparation_ns"]
            ws, we = alignment["wait_ns"]
            es, er = alignment["sender_error_ns"], alignment["receiver_error_ns"]
            if min(es, er) < 0 or he - es <= ws + er or he + es > we - er or fact["overlap_ns"] != (
                    min(he - es, we - er) - max(hs + es, ws + er)):
                return "uncertain_cross_node_overlap"
    if len({f["wait"]["graph_id"] for f in facts}) != len(affected):
        return "duplicate_notify_support"
    if (host.get("anchor_graph_id") not in {f["producer"]["graph_id"] for f in facts}
            or host["observed_wait_overlap_ns"] != max(f["overlap_ns"] for f in facts)):
        return "invalid_notify_anchor_or_overlap_summary"
    return None


def select_sources(execution_report, host_observations, options=SelectionOptions(), *, allow_inherited_support=False):
    """No labels/windows accepted. Inherited support is only for explicitly sealed old reports."""
    options.validate()
    if (execution_report.get("policy") != "local_dependency_clusters_v1"
            or execution_report.get("options", {}).get("selection_policy") != "top1"):
        raise ValueError("dual selection requires the unchanged resource Top1 proposal")
    if (Decimal(execution_report["options"]["source_factor"]) != Decimal(options.source_factor)
            or Decimal(execution_report["options"]["mad_multiplier"]) != Decimal(options.mad_multiplier)):
        raise ValueError("source mechanisms must share detection thresholds")
    proposals, deferred = [], []
    resource_candidates = execution_report["candidates"]
    if resource_candidates:
        units = defaultdict(list)
        for task in resource_candidates:
            units[(task["stream_id"], task["task_kind"])].append(_severity(task, options))
        score = sum(sum(values) / len(values) for values in units.values()) / len(units)
        proposals.append(dict(proposal_id=execution_report["cluster_selection"]["primary_cluster_id"],
            mechanism="communication_execution_growth", score=str(score),
            candidate_ids=[c["candidate_id"] for c in resource_candidates], support_provenance="execution_report"))
    hosts = {}
    for host in host_observations:
        reason = _validate_host(host, options, allow_inherited_support)
        if reason:
            deferred.append(dict(source_activity_id=host.get("source_activity_id"), reason=reason))
            continue
        key = host["source_activity_id"]
        if key in hosts:
            raise ValueError("duplicate Host preparation activity")
        hosts[key] = host
        proposals.append(dict(proposal_id=key, mechanism="host_preparation_late", score=str(_severity(host, options)),
            candidate_ids=[host["root_id"]], support_provenance=("original_endpoint_facts" if
                host.get("support_evidence_version") == 1 else "sealed_prior_analysis")))
    proposals.sort(key=lambda p: (-Decimal(p["score"]), p["mechanism"] != "communication_execution_growth", p["proposal_id"]))
    primary = proposals[0] if proposals else None
    candidates, chains, supports = [], [], []
    if primary and primary["mechanism"] == "communication_execution_growth":
        candidates, chains = deepcopy(resource_candidates), deepcopy(execution_report["chains"])
    elif primary:
        host = deepcopy(hosts[primary["proposal_id"]])
        host.update(candidate_id=host["root_id"], graph_id=None,
            prior_support_reason=host.get("reason"),
            reason="Public preparation interval grew and has slow peer Wait support; anchor_graph_id identifies a device producer, not the Host source. Preparation lateness is a mechanism candidate, not proof of sleep or a device-kernel fault.",
            slowdown_factor=str(Decimal(host["duration_ns"]) / Decimal(host["reference_mean_ns"])))
        candidates = [host]
        for target in host["affected_wait_graph_ids"]:
            facts = [f for f in host.get("supporting_dependencies", []) if f["wait"]["graph_id"] == target]
            supports.append(dict(source_activity_id=host["source_activity_id"], target_graph_id=target,
                notify_edge_ids=host["evidence_paths"][target], support_provenance=primary["support_provenance"],
                endpoint_facts=facts, host_to_api_relation="public_call_association_not_execution_edge",
                physical_causal_contribution_ns=None))
    return dict(schema_version=1, policy="dual_source_proposals_v1", options=asdict(options),
        selected_mechanism=primary["mechanism"] if primary else "unlocalized", primary_proposal=primary,
        proposals=proposals, candidates=candidates, chains=chains, host_support_chains=supports,
        host_admission_decisions=deferred, external_host_observations=deepcopy(host_observations),
        execution_proposal=deepcopy(execution_report),
        summary=dict(candidate_count=len(candidates), execution_candidate_count=sum(c["task_kind"] != "host_interval" for c in candidates),
            host_interval_candidate_count=sum(c["task_kind"] == "host_interval" for c in candidates),
            propagation_chain_count=len(chains), host_notify_support_count=len(supports)),
        limits=["Exploratory decision-layer selection, not a calibrated fault alarm or independent accuracy test.",
            "Two-stage proposals: unchanged resource Top1, then comparison with evidenced Host intervals using common robust relative excess. Other resource clusters remain in the audit, not reranked.",
            "Host preparation includes readiness/compute/scheduling; late preparation does not identify sleep or a physical fault.",
            "Host is an interval, not a device task; its device anchor is not its graph identity. Public API association is not an invented execution edge.",
            "Sealed prior support cannot revalidate deleted original endpoints. Missing endpoint facts are explicit; no new propagation path is invented.",
            "Wait overlap is support, not a quantified physical causal contribution. No uncalibrated cross-node subtraction.",
            "Without an eligible Host proposal the old execution Top1 is unchanged, including its remaining pure-workload false-alarm risk."])


def render(report):
    def table(headers, rows):
        return "<table><tr>" + "".join("<th>" + html.escape(str(h)) + "</th>" for h in headers) + "</tr>" + "".join(
            "<tr>" + "".join("<td>" + html.escape(str(v)) + "</td>" for v in row) + "</tr>" for row in rows) + "</table>"
    title = "Source diagnosis: " + report["selected_mechanism"]
    body = "<h1>" + html.escape(title) + "</h1>"
    body += table(["Node", "Rank", "Iteration / bucket", "Source", "Stream / task", "Observed ms", "Previous five ms", "Increase ms"], [
        (c["node_id"], c["user_rank"], "{} / {}".format(c["iteration"], c.get("bucket", c.get("call_site"))),
         c["task_kind"], "{} / {}".format(c["stream_id"], c["task_id"]), c["duration_ns"] / 1e6,
         str(Decimal(c["reference_mean_ns"]) / 1000000), str((Decimal(c["duration_ns"]) - Decimal(c["reference_mean_ns"])) / 1000000))
        for c in report["candidates"]])
    body += "<h2>Mechanism proposals</h2>" + table(["Mechanism", "Robust excess score", "Evidence", "Selected"], [
        (p["mechanism"], p["score"], p["support_provenance"], p == report["primary_proposal"]) for p in report["proposals"]])
    body += "<h2>Preparation / API / Notify support</h2>"
    for support in report["host_support_chains"]:
        body += "<p>Public preparation interval → bound API (association, not a graph edge); Notify producer → peer Wait.</p>"
        body += table(["Host activity", "Wait graph ID", "Original Notify edge", "Provenance"], [(
            support["source_activity_id"], support["target_graph_id"], ", ".join(support["notify_edge_ids"]), support["support_provenance"])])
        if not support["endpoint_facts"]:
            body += "<p>Original endpoints were not retained. This is an inherited sealed support claim, not a reconstructed execution path.</p>"
        for facts in support["endpoint_facts"]:
            body += table(["Role", "Node", "Rank", "Stream / task", "Start ns", "Stop ns"], [
                (role, facts[role]["node_id"], facts[role]["user_rank"], "{} / {}".format(facts[role]["stream_id"], facts[role]["task_id"]),
                 facts[role]["observed_start_ns"], facts[role]["observed_stop_ns"]) for role in ("producer", "wait")])
    body += "<h2>Execution propagation paths</h2>" + table(["Source", "Target Wait", "Original edges"], [
        (c["source_graph_id"], c["target_graph_id"], " → ".join(c["edge_ids"])) for c in report["chains"]])
    execution = report["execution_proposal"]
    links = {e["edge_id"]: e for e in execution["edges"]}
    for chain in report["chains"]:
        ids = [chain["source_graph_id"]] + [links[key]["dst"] for key in chain["edge_ids"]]
        steps = [execution["nodes"][key] for key in ids]
        body += table(["Node", "Rank", "Stream / task", "Kind / event", "Duration us", "Previous five us", "Incoming evidence"], [
            (t["node_id"], t["user_rank"], "{} / {}".format(t["stream_id"], t["task_id"]),
             "{} / {}".format(t["task_kind"], t.get("event", "")), t["duration_ns"]/1000,
             str(Decimal(t["reference_mean_ns"])/1000) if t.get("reference_mean_ns") is not None else "unavailable",
             links[chain["edge_ids"][i-1]]["kind"] if i else "source") for i, t in enumerate(steps)])
    body += "<h2>Limits</h2><ul>" + "".join("<li>" + html.escape(s) + "</li>" for s in report["limits"]) + "</ul>"
    return '<!doctype html><meta charset="utf-8"><title>Source diagnosis</title><style>body{font:14px system-ui;margin:24px;color:#17232a}table{border-collapse:collapse;width:100%;margin:16px 0}td,th{padding:8px;border-bottom:1px solid #d8dee3;text-align:left;overflow-wrap:anywhere}th{background:#edf3f7}</style>' + body
