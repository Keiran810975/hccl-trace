"""Time checks on existing dependencies, never a source of new graph edges."""
from __future__ import annotations


def edge_observation(edge, source, target, clocks):
    if "ffts" in edge["kind"]:
        return dict(status="ffts_not_complete_hardware_dag")
    remote = source["node_id"] != target["node_id"]
    if not remote:
        if edge["kind"] == "direct_stream_order_observed":
            return dict(status="accepted" if source["observed_stop_ns"] <= target["observed_start_ns"] else "incompatible_stream_order_timestamps")
        if source["task_kind"] != "notify_record" or target["task_kind"] != "notify_wait":
            return dict(status="unsupported_or_unmeasured_notify_release")
        if source["observed_stop_ns"] > target["observed_stop_ns"]:
            return dict(status="incompatible_notify_timestamps")
        return dict(status="signal_precedes_wait_start" if source["observed_stop_ns"] <= target["observed_start_ns"] else "accepted")
    if (edge["kind"] != "cross_node_notify_sync_observed" or edge.get("confidence") != "observed"
            or source["task_kind"] not in {"notify_record", "rdma"} or target["task_kind"] != "notify_wait"):
        return dict(status="unsupported_cross_node_dependency")
    a, b = (clocks.get((t["node_id"], t["device_id"])) for t in (source, target))
    if a is None or b is None:
        return dict(status="uncalibrated_cross_node_boundary")
    ss, se = (a.map_ns(source[k]) for k in ("observed_start_ns", "observed_stop_ns"))
    ts, te = (b.map_ns(target[k]) for k in ("observed_start_ns", "observed_stop_ns"))
    error = a.estimated_error_ns + b.estimated_error_ns
    facts = dict(timing_domain="independent_network_probe_estimate", estimated_error_ns=error,
        source_mapped_ns=[ss, se], target_mapped_ns=[ts, te],
        source_profiler_interval_ns=[source["observed_start_ns"], source["observed_stop_ns"]],
        target_profiler_interval_ns=[target["observed_start_ns"], target["observed_stop_ns"]],
        hardware_completion_observed=False, physical_causal_contribution_ns=None)
    if ss - a.estimated_error_ns > te + b.estimated_error_ns:
        return dict(facts, status="incompatible_calibrated_notify_timestamps")
    if source["task_kind"] == "notify_record" and se + a.estimated_error_ns <= ts - b.estimated_error_ns:
        return dict(facts, status="signal_precedes_wait_start")
    # A doorbell can finish before a remote Wait starts without proving data was ready.
    return dict(facts, status="accepted", evidence_kind="cross_node_protocol_topology_and_slow_wait_not_hardware_release")
