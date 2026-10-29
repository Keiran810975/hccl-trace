"""One public result contract, without changing detector rules or candidate order."""
from __future__ import annotations

from collections import Counter
from decimal import Decimal
from . import analyze_waits as waits


CANDIDATE_STATUSES = {"dependency_supported_candidate", "isolated_slow_task"}


def normalize(report, *, mode, run_id, rows, edges, pipeline, binding_evidence, merge_metrics=()):
    lookup = {r["_graph_id"]: r for r in rows}
    links = {e["edge_id"]: e for e in edges}
    metric = "mean" if mode == "rolling" else "median"
    reference = (dict(kind="previous_five_measured", statistic="mean", window=5)
                 if mode == "rolling" else dict(kind="independent_baseline", statistic="median", matching="explicit_or_structural"))
    roots, candidates, unresolved = [], [], []
    for original in report["root_causes"]:
        source = dict(original)
        if source["status"] not in CANDIDATE_STATUSES or source.get("component") not in {"execution", "host_preparation"}:
            unresolved.append({k: source.get(k) for k in ("root_id", "graph_id", "node_id", "user_rank", "operation_scope",
                "iteration", "group_id", "call_site", "phase", "step", "component", "status", "reason", "duration_ns", "delta_ns")})
            continue
        node = lookup[source["graph_id"]]
        value = source.get("reference_mean_ns" if mode == "rolling" else "baseline_median_ns")
        source.update(reference_value_ns=value, reference_metric=metric)
        if source.get("slowdown_factor") is None and value is not None and Decimal(str(value)) > 0:
            source["slowdown_factor"] = str(Decimal(source["duration_ns"]) / Decimal(str(value)))
        source.setdefault("observed_start_ns", waits.ns(node, "start"))
        source.setdefault("observed_stop_ns", waits.ns(node, "stop"))
        paths = source.get("evidence_paths", {})
        used = [links[e] for path in paths.values() for e in path if e in links]
        confidence = "observed" if any(e["confidence"] == "observed" for e in used) else "exact" if used else "unavailable"
        candidates.append(dict(id=source["root_id"], status=source["status"], physical_cause=source.get("physical_cause", "unknown"),
            component=source["component"], **{k: source.get(k) for k in ("node_id", "user_rank", "device_id", "stream_id", "task_id",
            "iteration", "group_id", "call_site", "occurrence", "block", "bucket", "phase", "step", "event", "task_kind", "graph_id")},
            operation_id=source["operation_scope"], observed_start_ns=source["observed_start_ns"], observed_stop_ns=source["observed_stop_ns"],
            observed_duration_ns=source["duration_ns"], reference_duration_ns=value, reference_statistic=metric,
            reference_count=source.get("reference_count", source.get("baseline_count", 0)),
            comparison_status=source.get("comparison_status"), delta_ns=source.get("delta_ns"),
            slowdown_factor=source.get("slowdown_factor"), affected_wait_graph_ids=source.get("affected_wait_graph_ids", []),
            chain_ids=[], evidence_confidence=confidence, reason=source["reason"],
            limitations=["Candidate is not a proved physical fault."] +
                        (["Evidence traversal was truncated."] if source.get("traversal_truncated") else [])))
        roots.append(source)
    for trace in report.get("wait_backtraces", []):
        if trace.get("status") != "source_candidates_found":
            unresolved.append(dict(kind="wait_backtrace",
                **{k: trace.get(k) for k in ("wait_graph_id", "operation_scope", "node_id", "status", "traversal_truncated")},
                boundary_reason_counts=dict(Counter(b["reason"] for b in trace.get("boundaries", [])))))
    count, compared = report["task_count"], report["compared_task_count"]
    status = "analyzed" if compared else "insufficient_history" if mode == "rolling" else "not_comparable"
    coverage = dict(report.get("coverage", {}), task_count=count, comparable_task_count=compared,
                    uncomparable_task_count=count - compared,
                    comparison_status_counts=dict(Counter(t["comparison_status"] for t in report["tasks"])))
    normalized = dict(schema_version=1, run_id=run_id, mode=mode, status=status,
        diagnosis_status=report.get("diagnosis_status", "localized_candidate" if report.get("primary_source_candidate_id") else
                                    "unresolved_waits" if unresolved else "no_slow_task"),
        reference=reference, coverage=coverage, binding=binding_evidence,
        primary_candidate_id=report.get("primary_source_candidate_id"), candidates=candidates,
        unresolved_observations=unresolved,
        quality=dict(pipeline_passed=pipeline["status"] == "passed", node_count=pipeline.get("node_count"),
                     rank_count=len({r["_user_rank"] for r in rows if r["_user_rank"] >= 0}),
                     execution_node_count=len(rows), execution_edge_count=len(edges),
                     edge_kind_counts=dict(Counter(e["kind"] for e in edges)),
                     wait_count=pipeline.get("wait_count"), paired_wait_count=pipeline.get("paired_wait_count"),
                     merge_metrics=list(merge_metrics), clock_alignment_available=pipeline.get("clock_alignment_available", False),
                     clock_alignment_estimated_error_ns=pipeline.get("clock_alignment_estimated_error_ns"),
                     global_critical_path_available=False,
                     rdma_hardware_transfer_duration_available=False),
        limitations=list(report.get("limits", [])) +
            (["Baseline source selection currently covers observed work execution, not Host preparation intervals."] if mode == "baseline" else []))
    tasks = [dict(t, reference_value_ns=t.get("reference_mean_ns" if mode == "rolling" else "baseline_median_ns"),
                  reference_metric=metric) for t in report["tasks"]]
    return normalized, roots, tasks
