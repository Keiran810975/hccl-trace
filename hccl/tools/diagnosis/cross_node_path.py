"""Detect slow data-notification paths, not NIC faults or wire time."""
from __future__ import annotations

from collections import Counter, defaultdict, deque
from decimal import Decimal

from .analyze_waits import ns
from .clock_alignment import models_from_report
from .dependency_model import stable_id
from .source_events import statistics
from .workload_coordinates import position


ORDER = "direct_stream_order_observed"
CROSS = "cross_node_notify_sync_observed"
DATA_WAIT = frozenset({"link_rx_data_signal", "link_rx_payload_copy", "link_rx_payload_reduce"})


def _endpoint(row):
    return row["_node_id"], row["_device_id"], row["_user_rank"]


def _witnesses(rows, edges):
    # Index only operations with an annotated payload and only their real edges.
    payloads = [r for r in rows if r.get("profiler_task_kind") == "rdma"
                and r.get("semantic") == "link_tx_payload" and r.get("match_status") == "matched"
                and r.get("_operation_scope_status") == "unique" and r.get("_subtask_id", -1) < 0]
    scopes = {r["_operation_scope"] for r in payloads}
    if not scopes:
        return
    nodes = {r["_graph_id"]: r for r in rows if r.get("_operation_scope") in scopes}
    before, after, sync_in, sync_out = (defaultdict(list) for _ in range(4))
    for e in edges:
        src, dst, kind = e["src"], e["dst"], e["kind"]
        if "notify_sync" in kind:
            if dst in nodes:
                sync_in[dst].append(e)
            if src in nodes:
                sync_out[src].append(e)
        elif kind == ORDER and src in nodes and dst in nodes:
            before[dst].append(e)
            after[src].append(e)

    def walk(payload, backwards):
        current, path = payload, []
        stream = before if backwards else after
        sync = sync_in if backwards else sync_out
        for _ in range(257):
            key = current["_graph_id"]
            if sync.get(key):
                return current, list(reversed(path)) if backwards else path
            steps = stream.get(key, ())
            if len(steps) != 1:
                break
            edge = steps[0]
            a, b = nodes[edge["src"]], nodes[edge["dst"]]
            other = a if backwards else b
            if (edge.get("confidence") not in {"observed", "exact"}
                    or _endpoint(other) != _endpoint(payload) or other["_stream_id"] != payload["_stream_id"]
                    or other["_operation_scope"] != payload["_operation_scope"]
                    or other.get("_subtask_id", -1) >= 0 or other.get("semantic") == "link_tx_payload"
                    or ns(a, "stop") > ns(b, "start")):
                break
            path.append(edge)
            current = other
        return None, []

    def cross(edge, scope):
        a, b = nodes.get(edge["src"]), nodes.get(edge["dst"])
        return (a is not None and b is not None and edge["kind"] == CROSS
                and edge.get("confidence") == "observed" and a["_node_id"] != b["_node_id"]
                and a["_operation_scope"] == b["_operation_scope"] == scope
                and a["_user_rank"] == b.get("_peer_rank") and b["_user_rank"] == a.get("_peer_rank")
                and a.get("profiler_task_kind") == "rdma" and b.get("profiler_task_kind") == "notify_wait"
                and all(r.get("_subtask_id", -1) < 0 and r.get("_operation_scope_status") == "unique"
                        for r in (a, b)))

    for payload in payloads:
        scope = payload["_operation_scope"]
        ack, prefix = walk(payload, True)
        signal, suffix = walk(payload, False)
        if ack is None or signal is None or ack.get("semantic") != "link_rx_ack":
            continue
        inbound, outbound = sync_in[ack["_graph_id"]], sync_out[signal["_graph_id"]]
        if len(inbound) != 1 or len(outbound) != 1 or not all(cross(e, scope) for e in inbound + outbound):
            continue
        ready, done = nodes[inbound[0]["src"]], nodes[outbound[0]["dst"]]
        if (ready.get("semantic") != "link_tx_ack" or done.get("semantic") not in DATA_WAIT
                or _endpoint(ready) != _endpoint(done) or done["_user_rank"] != payload.get("_peer_rank")
                or len(sync_in[done["_graph_id"]]) != 1):
            continue
        yield payload, ready, ack, done, inbound + prefix + suffix + outbound


def analyze(rows, edges, coordinates, alignment, options, *, coverage=None):
    """Compare matched readiness and post-submission intervals using past clean samples."""
    if not any(e["kind"] == CROSS for e in edges):
        if coverage is not None:
            coverage.update(status="no_cross_node_notify_edges", candidate_count=0)
        return []
    clocks = models_from_report(alignment)
    if len({node for node, _ in clocks}) < 2:
        if coverage is not None:
            coverage.update(status="insufficient_cross_node_clock_evidence", candidate_count=0)
        return []
    counts = Counter()
    groups = defaultdict(lambda: defaultdict(list))
    for payload, ready, ack, done, path in _witnesses(rows, edges):
        counts["protocol_witnesses"] += 1
        scope = payload["_operation_scope"]
        coord = coordinates.get(scope)
        a, b = (clocks.get((r["_node_id"], r["_device_id"])) for r in (payload, done))
        size = str(payload.get("profiler_size_bytes", ""))
        if not coord or coord["stage"] != "measured" or not size.isdecimal() or int(size) <= 0 or not a or not b:
            counts["missing_comparable_location_or_clock"] += 1
            continue
        try:
            ready_at, submit, posted, received = (
                clock.map_ns(ns(row, side)) for clock, row, side in
                ((b, ready, "start"), (a, payload, "start"), (a, payload, "stop"), (b, done, "stop")))
        except ValueError:
            counts["outside_clock_coverage"] += 1
            continue
        error = a.estimated_error_ns + b.estimated_error_ns + 2
        pre = ns(payload, "start") - ns(ack, "stop")
        if (ready_at > submit + error or not submit <= posted <= received
                or pre < 0):
            counts["incompatible_protocol_time"] += 1
            continue
        key = (_endpoint(payload), _endpoint(done), position(coord), payload.get("phase"), payload.get("step"),
               payload.get("slice"), done.get("semantic"), size, tuple(e["kind"] for e in path))
        groups[key][coord["iteration"]].append(
            (pre, received-posted, ns(done, "stop")-ns(done, "start"), error,
             posted, received, payload, done, ready, path, coord))

    def slow(value, refs, factor, uncertainty):
        mean, mad = statistics(refs)
        delta = Decimal(value) - mean
        return delta > uncertainty and value >= mean * Decimal(factor) and delta >= Decimal(options.mad_multiplier) * mad, mean

    candidates = []
    for epochs in groups.values():
        history = deque(maxlen=options.window)
        for epoch, entries in sorted(epochs.items()):
            if len(entries) != 1:
                counts["ambiguous_iteration_location"] += 1
                continue  # Identical protocol shapes in one call are not ordered by timestamp.
            pre, post, wait, error, start, stop, payload, done, ready, path, coord = entries[0]
            if len(history) < options.window:
                counts["reference_seed_count"] += 1
                history.append((epoch, pre, post, wait, error))
                continue
            uncertainty = error + max(x[4] for x in history)
            counts["compared_count"] += 1
            pre_slow, pre_mean = slow(pre, [x[1] for x in history], options.slowdown_factor, 0)
            post_slow, post_mean = slow(post, [x[2] for x in history], options.slowdown_factor, uncertainty)
            wait_slow, _ = slow(wait, [x[3] for x in history], options.wait_slowdown_factor or options.slowdown_factor, 0)
            if not (pre_slow or post_slow or wait_slow):
                history.append((epoch, pre, post, wait, error))
            counts["post_submission_slow_count"] += post_slow
            counts["post_slow_but_sender_late_count"] += post_slow and pre_slow
            counts["post_slow_without_slow_wait_count"] += post_slow and not wait_slow
            if not post_slow or not wait_slow or pre_slow:
                continue
            candidates.append(dict(id=stable_id("cross_path", (payload["_graph_id"], done["_graph_id"])),
                source_unit="cross_node_protocol_interval", iteration=epoch, group_id=coord.get("group_id"),
                call_site=coord.get("call_site"), occurrence=coord.get("occurrence"), phase=payload.get("phase"),
                step=payload.get("step"), payload_size_bytes=int(payload["profiler_size_bytes"]),
                sender_node_id=payload["_node_id"], sender_rank=payload["_user_rank"],
                sender_device_id=payload["_device_id"], sender_stream_id=payload["_stream_id"],
                sender_task_id=payload["_task_id"],
                receiver_node_id=done["_node_id"], receiver_rank=done["_user_rank"],
                receiver_device_id=done["_device_id"], receiver_stream_id=done["_stream_id"],
                payload_graph_id=payload["_graph_id"], wait_graph_id=done["_graph_id"], wait_task_id=done["_task_id"],
                readiness_graph_id=ready["_graph_id"], evidence_edge_ids=[e["edge_id"] for e in path],
                start_aligned_ns=start, stop_aligned_ns=stop, duration_ns=post, reference_ns=str(post_mean),
                delta_ns=str(Decimal(post)-post_mean), sender_ack_to_submit_ns=pre,
                sender_ack_to_submit_reference_ns=str(pre_mean),
                wait_duration_ns=wait, comparison_clock_error_ns=uncertainty, reference_iterations=[x[0] for x in history],
                hardware_transfer_duration_available=False, physical_cause="unknown"))
    if coverage is not None:
        coverage.update(counts, status="analyzed" if counts["compared_count"] else "no_comparable_path",
                        candidate_count=len(candidates))
    return sorted(candidates, key=lambda c: (c["iteration"], c["sender_rank"], c["receiver_rank"], c["id"]))
