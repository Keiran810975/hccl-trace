"""Conservative task ownership and separate diagnosis result categories."""
from __future__ import annotations


INTERNAL = "communication_source_candidate"
EXTERNAL = "external_anomaly_clue"
UNRESOLVED = "unresolved_observation"
CATEGORIES = (INTERNAL, EXTERNAL, UNRESOLVED)
DOMAIN_LABELS = {"hccl_internal": "HCCL内部", "external_compute": "已确认外部计算", "unknown": "归属未知"}
CATEGORY_LABELS = {INTERNAL: "通信内部源头候选", EXTERNAL: "外部异常线索", UNRESOLVED: "未归因观测"}


def classify_task(row):
    """Only validated semantics or unique DB communication ownership establish HCCL membership.

    Current execution artifacts contain no verified compute-operator ownership.
    In particular, an unbound mixed AIC kernel stays unknown, not external_compute.
    Host observations are handled separately and never become physical tasks.
    """
    semantic = (row.get("match_status") == "matched"
                and all(str(row.get(k, "")).strip() for k in ("algorithm", "phase", "event", "semantic")))
    owned = (bool(row.get("_operation_scope") or row.get("profiler_op_scope"))
             and row.get("_operation_scope_status", row.get("profiler_op_scope_status")) == "unique")
    if semantic or owned:
        return dict(task_domain="hccl_internal", task_domain_evidence=(
            "matched_hccl_semantics" if semantic else "unique_db_communication_operation"))
    return dict(task_domain="unknown", task_domain_evidence="no_verified_task_owner")


def source_category(source, row):
    if source.get("component") == "host_preparation":
        return EXTERNAL
    domain = classify_task(row)["task_domain"]
    if (source.get("component") == "execution" and domain == "hccl_internal"
            and source.get("status") == "dependency_supported_candidate"
            and any(source.get("evidence_paths", {}).get(w) for w in source.get("affected_wait_graph_ids", []))):
        return INTERNAL
    return UNRESOLVED
