"""Arrival observations over existing Notify pairs, not additional source candidates."""
from __future__ import annotations

from decimal import Decimal

from . import analyze_waits as waits
from . import compare_diagnosis as comparison


def local_origins(rows, clocks):
    origins = {}
    for row in rows:
        clock = clocks.get((row["_node_id"], row["_device_id"]))
        if clock is not None and row.get("_operation_scope"):
            key = row["_operation_scope"], row["_node_id"]
            start = waits.ns(row, "start") - clock.profiler_to_raw_offset_ns
            origins[key] = min(origins.get(key, start), start)
    return origins


def observe(wait, producer, task, nodes, syncs, clocks, quantization, origins):
    if (producer["_node_id"] != wait["_node_id"] or producer.get("profiler_task_kind") != "notify_record"
            or producer.get("_operation_scope") != wait.get("_operation_scope") or task["reference_count"] != 5):
        return None
    history = [nodes[key] for key in task["reference_graph_ids"]]
    if len(history) != 5 or any(len(syncs[r["_graph_id"]]) != 1 for r in history):
        return None
    producers = [nodes[syncs[row["_graph_id"]][0][0]] for row in history]
    if any(p["_node_id"] != w["_node_id"] or p.get("_operation_scope") != w.get("_operation_scope")
           or p.get("profiler_task_kind") != "notify_record"
           or comparison.task_signature(p) != comparison.task_signature(producer)
           for p, w in zip(producers, history)):
        return None
    pairs = [(producer, wait), *zip(producers, history)]
    if any(r.get("_subtask_id", -1) >= 0 for pair in pairs for r in pair):
        return None
    if any((r["_node_id"], r["_device_id"]) not in clocks
           or (r["_node_id"], r["_device_id"]) not in quantization for pair in pairs for r in pair):
        return None

    def raw(row, side):
        clock = clocks[(row["_node_id"], row["_device_id"])]
        clock.map_ns(waits.ns(row, side))
        return waits.ns(row, side) - clock.profiler_to_raw_offset_ns

    def uncertainty(p, w):
        keys = [(r["_node_id"], r["_device_id"]) for r in (p, w)]
        return 0 if keys[0] == keys[1] else sum(quantization[k] for k in keys)

    # Do not explain a logically paired but temporally contradictory channel.
    if any(raw(p, "start") - uncertainty(p, w) > raw(w, "stop")
           or raw(p, "stop") + uncertainty(p, w) <= raw(w, "start") for p, w in pairs):
        return None

    def offset(row, side):
        return Decimal(raw(row, side) - origins[(row["_operation_scope"], row["_node_id"])])

    def delta(row, previous, side):
        return offset(row, side) - sum(offset(r, side) for r in previous) / 5

    waiter_delta = delta(wait, history, "start")
    producer_start_delta = delta(producer, producers, "start")
    producer_stop_delta = delta(producer, producers, "stop")
    margin = uncertainty(producer, wait) + max(uncertainty(p, w) for p, w in zip(producers, history))
    if (waiter_delta < -margin and max(producer_start_delta, producer_stop_delta) <= margin
            and producer_stop_delta - waiter_delta > margin):
        status = "waiter_advanced_without_observed_producer_delay"
    elif producer_start_delta > margin:
        status = "producer_later_observed"
    else:
        status = "mixed_or_within_timing_resolution"
    return dict(status=status, wait_graph_id=wait["_graph_id"], producer_graph_id=producer["_graph_id"],
        timing_domain="same_node_monotonic_raw_call_offsets", reference_count=5,
        reference_wait_graph_ids=task["reference_graph_ids"],
        reference_producer_graph_ids=[p["_graph_id"] for p in producers],
        waiter_start_delta_ns=str(waiter_delta), producer_start_delta_ns=str(producer_start_delta),
        producer_stop_delta_ns=str(producer_stop_delta), observed_wait_growth_ns=task["delta_ns"],
        metadata_uncertainty_ns=margin, source_candidate_created=False, physical_cause_proven=False,
        limitation="Arrival shifts are observations, not proof of a resource fault or a complete decomposition of Wait growth.")
