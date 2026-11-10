"""One public result contract, without changing detector rules or candidate order."""
from __future__ import annotations

from collections import Counter, defaultdict
from decimal import Decimal
from . import analyze_waits as waits
from .report_contract import rolling_reference
from .task_classifier import classify_task, source_category, INTERNAL, EXTERNAL, UNRESOLVED


def normalize(report, *, mode, run_id, rows, edges, pipeline, binding_evidence, merge_metrics=()):
    lookup = {r["_graph_id"]: r for r in rows}
    links = {e["edge_id"]: e for e in edges}
    participants = defaultdict(set)
    for row in rows:
        if row["_user_rank"] >= 0 and row.get("_operation_scope"):
            participants[(row["_operation_scope"], row["_user_rank"])].add((row["_node_id"], row["_device_id"]))
    metric = "mean" if mode == "rolling" else "median"
    reference = (rolling_reference(report.get("reference_mode"))
                 if mode == "rolling" else dict(kind="independent_baseline", statistic="median", matching="explicit_or_structural"))
    roots, candidates, external = [], [], []
    unresolved = [dict(item, diagnosis_category=UNRESOLVED) for item in report.get('unresolved_observations', [])]
    for original in report["root_causes"]:
        source = dict(original)
        node = lookup[source["graph_id"]]
        if source["component"] == "execution":
            peer = node.get("_peer_rank", -1)
            locations = participants.get((node.get("_operation_scope"), peer), set())
            context = dict(executing_rank=node["_user_rank"], peer_rank=peer,
                           semantic=node.get("semantic", ""), peer_identity_status="unavailable",
                           peer_is_proven_fault_location=False)
            if node.get("match_status") == "matched" and peer >= 0 and len(locations) == 1:
                peer_node, peer_device = next(iter(locations))
                context.update(peer_node_id=peer_node, peer_device_id=peer_device,
                               peer_identity_status="matched_semantic_peer_and_unique_operation_participant")
            source["communication_context"] = context
        category = source_category(source, node)
        source.update(diagnosis_category=category)
        source.setdefault("task_domain", classify_task(node)["task_domain"])
        if category == UNRESOLVED:
            unresolved.append({k: source.get(k) for k in (
                "root_id", "graph_id", "node_id", "user_rank", "device_id", "stream_id", "task_id", "operation_scope",
                "iteration", "group_id", "call_site", "phase", "step", "component", "status", "reason", "duration_ns",
                "observed_start_ns", "observed_stop_ns", "reference_mean_ns", "delta_ns", "task_domain", "diagnosis_category")})
            continue
        value = source.get("reference_mean_ns" if mode == "rolling" else "baseline_median_ns")
        source.update(reference_value_ns=value, reference_metric=metric)
        if source.get("slowdown_factor") is None and value is not None and Decimal(str(value)) > 0:
            source["slowdown_factor"] = str(Decimal(source["duration_ns"]) / Decimal(str(value)))
        source.setdefault("observed_start_ns", waits.ns(node, "start"))
        source.setdefault("observed_stop_ns", waits.ns(node, "stop"))
        paths = source.get("evidence_paths", {})
        edge_ids = [e for path in paths.values() for e in path]
        edge_ids.extend(source.get("local_completion_evidence", {}).get("edge_ids", []))
        levels = {'unavailable': -1, 'semantic': 0, 'observed': 1, 'exact': 2}
        confidence = min((links.get(e, {}).get('confidence', 'unavailable') for e in edge_ids),
                         key=lambda value: levels.get(value, -1), default='unavailable')
        supported = confidence in {'observed', 'exact'}
        destination = candidates if category == INTERNAL else external
        destination.append(dict(id=source["root_id"], status=source["status"], physical_cause=source.get("physical_cause", "unknown"),
            diagnosis_category=category, task_domain=source["task_domain"], category_rank=len(destination) + 1,
            cross_operation=source.get("cross_operation", False),
            evidence_supported=supported and (source["status"] in {'dependency_supported_candidate', 'unexplained_execution_growth'} and any(paths.values())
                                or source.get("local_completion_evidence", {}).get("validated") is True),
            support_kind="local_completion" if source.get("local_completion_evidence") else "slow_notify_wait" if category == INTERNAL and paths else
                         "own_execution_growth_only" if category == INTERNAL else "host_preparation",
            local_completion_evidence=source.get("local_completion_evidence"),
            dependency_timing=source.get("dependency_timing", {}),
            communication_context=source.get("communication_context"),
            workload_completion_impact_proven=False,
            component=source["component"], **{k: source.get(k) for k in ("node_id", "user_rank", "device_id", "stream_id", "task_id",
            "iteration", "group_id", "call_site", "occurrence", "block", "bucket", "phase", "step", "event", "task_kind", "graph_id")},
            operation_id=source["operation_scope"], observed_start_ns=source["observed_start_ns"], observed_stop_ns=source["observed_stop_ns"],
            observed_duration_ns=source["duration_ns"], reference_duration_ns=value, reference_statistic=metric,
            reference_count=source.get("reference_count", source.get("baseline_count", 0)),
            reference_iterations=source.get("reference_iterations", []),
            reference_graph_ids=source.get("reference_graph_ids", []),
            comparison_status=source.get("comparison_status"), delta_ns=source.get("delta_ns"),
            comparison_basis=source.get("comparison_basis", "algorithm_semantic_location"),
            reference_evidence=source.get("reference_evidence", ""),
            time_alignment_estimated_error_ns=source.get("time_alignment_estimated_error_ns"),
            slowdown_factor=source.get("slowdown_factor"), affected_wait_graph_ids=source.get("affected_wait_graph_ids", []),
            chain_ids=[], evidence_confidence=confidence, reason=source["reason"],
            limitations=["Candidate is not a proved physical fault."] +
                        (["Evidence traversal was truncated."] if source.get("traversal_truncated") else [])))
        roots.append(source)
    for trace in report.get("wait_backtraces", []):
        if trace.get("status") != "source_candidates_found":
            unresolved.append(dict(kind="wait_backtrace",
                **{k: trace.get(k) for k in ("wait_graph_id", "operation_scope", "node_id", "status", "traversal_truncated", "notify_pairing_status")},
                diagnosis_category=UNRESOLVED,
                external_clue_ids=trace.get("external_clue_ids", []),
                arrival_observation=trace.get("arrival_observation"),
                boundaries=[dict(graph_id=b["graph_id"], reason=b["reason"]) for b in trace.get("boundaries", [])],
                boundary_reason_counts=dict(Counter(b["reason"] for b in trace.get("boundaries", [])))))
    count, compared = report["task_count"], report["compared_task_count"]
    status = "analyzed" if compared else "insufficient_history" if mode == "rolling" else "not_comparable"
    coverage = dict(report.get("coverage", {}), task_count=count, comparable_task_count=compared,
                    uncomparable_task_count=count - compared,
                    comparison_status_counts=dict(Counter(t["comparison_status"] for t in report["tasks"])))
    primary = report.get("primary_source_candidate_id")
    if primary not in {c["id"] for c in candidates}:
        primary = None
    diagnosis_status = report.get("diagnosis_status")
    if not diagnosis_status or diagnosis_status == "localized_candidate" and not candidates:
        diagnosis_status = ("localized_candidate" if candidates else "external_clues" if external else
                            "unresolved_waits" if unresolved else "no_slow_task")
    normalized = dict(schema_version=2, run_id=run_id, mode=mode, status=status,
        candidate_relationship="parallel",
        source_policy_version=report.get("source_policy_version"), detection_options=report.get("options", {}),
        diagnosis_status=diagnosis_status,
        reference=reference, coverage=coverage, binding=binding_evidence,
        primary_candidate_id=primary, candidates=candidates,
        source_ranking_version=report.get("source_ranking_version", 1),
        source_regions=report.get("source_regions", []),
        recommended_candidate_ids=report.get("recommended_candidate_ids", []),
        communication_source_candidates=candidates, external_anomaly_clues=external,
        primary_external_clue_id=external[0]["id"] if external else None,
        category_counts={INTERNAL: len(candidates), EXTERNAL: len(external), UNRESOLVED: len(unresolved)},
        compatibility=dict(candidates="alias of communication_source_candidates only; schema 1 mixed candidates are not retained"),
        unresolved_observations=unresolved,
        quality=dict(pipeline_passed=pipeline["status"] == "passed", node_count=pipeline.get("node_count"),
                     rank_count=len({r["_user_rank"] for r in rows if r["_user_rank"] >= 0}),
                     execution_node_count=len(rows), execution_edge_count=len(edges),
                     edge_kind_counts=dict(Counter(e["kind"] for e in edges)),
                     wait_count=pipeline.get("wait_count"), paired_wait_count=pipeline.get("paired_wait_count"),
                     merge_metrics=list(merge_metrics), clock_alignment_available=pipeline.get("clock_alignment_available", False),
                     clock_alignment_status=pipeline.get("clock_alignment_status", "uncalibrated"),
                     clock_alignment_error=pipeline.get("clock_alignment_error"),
                     profiler_clock_validation=pipeline.get("profiler_clock_validation", []),
                     clock_alignment_estimated_error_ns=pipeline.get("clock_alignment_estimated_error_ns"),
                     global_critical_path_available=False,
                     rdma_hardware_transfer_duration_available=False),
        limitations=list(report.get("limits", [])) +
            (["Baseline source selection currently covers observed work execution, not Host preparation intervals."] if mode == "baseline" else []))
    if "peer_read_policy" in report:
        normalized.update(peer_read_policy=report["peer_read_policy"],
                          peer_read_observations=report["peer_read_observations"])
    if "input_copy_overlap_policy" in report:
        normalized.update(input_copy_overlap_policy=report["input_copy_overlap_policy"],
                          input_copy_overlap_observations=report["input_copy_overlap_observations"])
    tasks = [dict(t, **classify_task(lookup[t["graph_id"]]), reference_value_ns=t.get("reference_mean_ns" if mode == "rolling" else "baseline_median_ns"),
                  reference_metric=metric) for t in report["tasks"]]
    return normalized, roots, tasks
