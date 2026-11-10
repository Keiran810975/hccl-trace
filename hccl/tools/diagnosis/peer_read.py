"""Directional payload evidence, separate from execution/Notify dependencies."""
from __future__ import annotations

from collections import defaultdict
from decimal import Decimal


POLICY = "single_ring_direct_peer_read_v1"
READS = {
    ("allgather_direct", "rx_payload_copy_start", "link_rx_payload_copy", "sdma"),
    ("reduce_scatter_direct", "rx_payload_reduce_start", "link_rx_payload_reduce", "reduce_inline"),
}
INPUT_COPY = ("reduce_scatter_direct", "copy_start", "user_to_ccl_copy", "sdma")


def _location(row):
    return tuple(row.get(k) for k in ("phase", "event", "semantic", "profiler_task_kind"))


def _size(row):
    value = str(row.get("profiler_size_bytes", ""))
    return int(value) if value.isascii() and value.isdecimal() else 0


def _comparable(task):
    return task["reference_count"] > 0 and Decimal(task["reference_mean_ns"]) > 0


def _fact(row, task):
    return dict(graph_id=row["_graph_id"], node_id=row["_node_id"], user_rank=row["_user_rank"],
                device_id=row["_device_id"], stream_id=row["_stream_id"], task_id=row["_task_id"],
                peer_rank=row["_peer_rank"], duration_ns=task["duration_ns"],
                reference_mean_ns=task["reference_mean_ns"], slowdown_factor=task["slowdown_factor"],
                reference_count=task["reference_count"], reference_iterations=task["reference_iterations"],
                duration_slow=task["duration_slow"])


def observe(rows, tasks, candidates, options):
    """Use a same-call Ring cohort and local input copies as controls, not a DAG edge."""
    by_id = {row["_graph_id"]: row for row in rows}
    by_task = {task["graph_id"]: task for task in tasks}
    targets = {source["graph_id"]: source for source in candidates
               if source["component"] == "execution" and _location(by_id[source["graph_id"]]) in READS}
    scopes = {by_id[key]["_operation_scope"] for key in targets}
    if not scopes:
        return []
    reads, local = defaultdict(list), defaultdict(list)
    for row in rows:
        scope = row.get("_operation_scope")
        if (scope not in scopes or row.get("algorithm") != "single_ring_direct"
                or row.get("match_status") != "matched" or row.get("match_confidence") != "exact"
                or row.get("_subtask_id", -1) != -1 or row.get("_operation_scope_status") != "unique"):
            continue
        loc, size = _location(row), _size(row)
        if not size:
            continue
        if loc in READS:
            reads[scope, loc, row.get("_step"), size].append(row)
        elif loc == INPUT_COPY and row.get("_peer_rank") == 0xffffffff:
            local[scope, row["_node_id"], row["_device_id"], row["_user_rank"], size].append(row)

    observations = []
    for (scope, loc, step, size), cohort in reads.items():
        if step is None or step < 0:
            continue
        # A Ring step rotates slice IDs. Compare equal-sized payloads across
        # ranks, and reject an incomplete or ambiguous per-rank cohort.
        count = len(cohort)
        by_ring_rank = {str(row.get("comm_rank", "")): row for row in cohort}
        if (count < 3 or set(by_ring_rank) != {str(i) for i in range(count)}
                or len({r["_node_id"] for r in cohort}) != 1
                or len({r["_device_id"] for r in cohort if r["_device_id"] >= 0}) != count
                or len({r["_user_rank"] for r in cohort if r["_user_rank"] >= 0}) != count
                or not all(r.get("_rank_size") == count for r in cohort)):
            continue
        ordered = [by_ring_rank[str(i)] for i in range(count)]
        if any(r["_peer_rank"] != ordered[i-1]["_user_rank"] for i, r in enumerate(ordered)):
            continue
        facts = [by_task[r["_graph_id"]] for r in ordered]
        if not all(_comparable(t) for t in facts):
            continue
        slow = [i for i, t in enumerate(facts) if t["duration_slow"]]
        if len(slow) != 1:
            continue
        i, = slow
        reader, task, peer = ordered[i], facts[i], ordered[i-1]
        root = targets.get(reader["_graph_id"])
        controls = [t for j, t in enumerate(facts) if j != i]
        if not root or task["duration_ns"] < max(t["duration_ns"] for t in controls) * Decimal(options.slowdown_factor):
            continue
        def input_copies(rank):
            copies = local[scope, rank["_node_id"], rank["_device_id"], rank["_user_rank"], size]
            return [(r, by_task[r["_graph_id"]]) for r in copies]

        peer_witnesses = [_fact(r, t) for r, t in input_copies(peer) if _comparable(t) and t["duration_slow"]]
        if not peer_witnesses:
            continue
        copies = input_copies(reader)
        compared = [_fact(r, t) for r, t in copies if _comparable(t)]
        if any(f["duration_slow"] for f in compared):
            disposition = "retained_reader_local_slowdown"
        elif not compared or len(compared) != len(copies):
            disposition = "retained_reader_local_control_incomplete"
        else:
            disposition = "reported_as_suspected_peer_read_impact"
        observations.append(dict(
            graph_id=reader["_graph_id"], original_candidate_id=root["root_id"], operation_scope=scope,
            iteration=task["iteration"], call_site=task.get("call_site"), bucket=task.get("bucket"),
            phase=loc[0], event=loc[1], step=step, size_bytes=size, disposition=disposition,
            reader=_fact(reader, task),
            peer=dict(node_id=peer["_node_id"], user_rank=peer["_user_rank"], device_id=peer["_device_id"]),
            other_receivers=[_fact(r, t) for j, (r, t) in enumerate(zip(ordered, facts)) if j != i],
            peer_local_slow_copies=peer_witnesses, reader_local_copies=compared,
            reader_local_copy_count=len(copies), affected_wait_graph_ids=root["affected_wait_graph_ids"],
            downstream_wait_paths=root["evidence_paths"], physical_cause_proven=False))
    return sorted(observations, key=lambda o: (o["iteration"], o["operation_scope"], o["graph_id"]))
