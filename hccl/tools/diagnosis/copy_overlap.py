"""Account for the observed two-stream input-copy mode without creating edges."""
from __future__ import annotations

from bisect import bisect_left, bisect_right
from collections import defaultdict
from dataclasses import dataclass
from itertools import combinations

from .analyze_waits import ns


POLICY = "single_node_ring_input_copy_overlap_v1"
VISIBLE_WORK = frozenset({
    "sdma", "reduce_inline", "reduce_tbe", "rdma",
    "kernel_aicore", "kernel_aivec", "kernel_mix_aic", "kernel_mix_aiv",
})
MIN_SOLO_SAMPLES = 3


@dataclass(frozen=True)
class CopyPair:
    device: tuple[str, int]
    members: tuple[str, str]
    start_ns: int
    stop_ns: int
    overlap_ns: int
    size_bytes: int


def _input_copy(row):
    return ((row.get("algorithm"), row.get("phase"), row.get("_step"), row.get("event"),
             row.get("semantic"), row.get("profiler_task_kind"), row.get("event_name"), row.get("source")) ==
            ("single_ring_direct", "reduce_scatter_direct", 0, "copy_start",
             "user_to_ccl_copy", "sdma", "SDMA_SQE", "aicpu")
            and row.get("match_status") == "matched" and row.get("match_confidence") == "exact"
            and row.get("_operation_scope_status") == "unique" and row.get("_subtask_id") == -1
            and row.get("_rank_size") == 4 and row.get("_peer_rank") == 0xffffffff
            and all(row.get(key, -1) >= 0 for key in ("_device_id", "_user_rank", "_stream_id", "_slice")))


def discover(rows, measured_scopes):
    """Find an unambiguous pair on one device, never infer cross-device timing."""
    if len({r["_node_id"] for r in rows}) != 1:
        return [], set()
    groups = defaultdict(list)
    for r in rows:
        scope = r.get("_operation_scope")
        if scope not in measured_scopes or not _input_copy(r):
            continue
        a, b = ns(r, "start"), ns(r, "stop")
        if a < b:
            groups[scope, (r["_node_id"], r["_device_id"]), r["_user_rank"]].append((r, a, b))
    pairs, overlapping = [], set()
    for (_, device, _), members in groups.items():
        intersections = []
        for (x, a, b), (y, c, d) in combinations(members, 2):
            joint = min(b, d) - max(a, c)
            if joint <= 0:
                continue
            ids = tuple(sorted((x["_graph_id"], y["_graph_id"])))
            overlapping.update(ids)
            intersections.append((x, y, ids, a, b, c, d, joint))
        if len(intersections) != 1:
            continue
        x, y, ids, a, b, c, d, joint = intersections[0]
        size = str(x.get("profiler_size_bytes", ""))
        if (x["_stream_id"] == y["_stream_id"] or x["_slice"] == y["_slice"]
                or not size.isascii() or not size.isdecimal() or int(size) <= 0
                or size != str(y.get("profiler_size_bytes")) or 2 * joint < max(b - a, d - c)):
            continue
        pairs.append(CopyPair(device, ids, min(a, c), max(b, d), joint, int(size)))
    return pairs, overlapping


def _visible_confounds(pairs, tasks):
    by_device = defaultdict(list)
    for pair in sorted(pairs, key=lambda p: p.start_ns):
        by_device[pair.device].append(pair)
    windows = {}
    for device, ordered in by_device.items():
        ends = []
        for pair in ordered:
            ends.append(max(ends[-1], pair.stop_ns) if ends else pair.stop_ns)
        windows[device] = (ordered, [p.start_ns for p in ordered], ends)
    confounds = {}
    for task in tasks:
        if task["task_kind"] not in VISIBLE_WORK:
            continue
        device = task["node_id"], task["device_id"]
        a, b = task["observed_start_ns"], task["observed_stop_ns"]
        if device not in windows or a >= b:
            continue
        ordered, starts, ends = windows[device]
        for i in range(bisect_right(ends, a), bisect_left(starts, b)):
            pair = ordered[i]
            if pair.stop_ns > a and task["graph_id"] not in pair.members:
                confounds.setdefault(pair, task["graph_id"])
    return confounds


def explain(pairs, tasks):
    """Keep raw slow flags; qualify only intrinsic duration, not gaps or dependencies."""
    if not pairs:
        return []
    ids = {key for pair in pairs for key in pair.members}
    lookup = {t["graph_id"]: t for t in tasks if t["graph_id"] in ids}
    confounds = _visible_confounds(pairs, tasks)
    results = []
    for pair in sorted(pairs, key=lambda p: (p.device, p.start_ns, p.members)):
        members = [lookup[key] for key in pair.members]
        if not any(t["duration_slow"] for t in members):
            continue
        span = pair.stop_ns - pair.start_ns
        budget = None
        if all(t["reference_count"] >= MIN_SOLO_SAMPLES and t.get("copy_solo_max_ns", 0) > 0 for t in members):
            # Add the two observed solo maxima, not the ordinary slowdown threshold.
            budget = sum(t["copy_solo_max_ns"] for t in members)
        if pair in confounds:
            disposition = "retained_other_visible_device_work"
        elif budget is None:
            disposition = "retained_insufficient_solo_history"
        elif span > budget:
            disposition = "retained_pair_completion_exceeds_solo_budget"
        elif not all(t["duration_slow"] for t in members):
            disposition = "retained_asymmetric_slowdown"
        else:
            disposition = "explained_by_input_copy_overlap"
            for task in members:
                task["copy_overlap_explained"] = True
        first = members[0]
        results.append(dict(node_id=first["node_id"], device_id=first["device_id"], user_rank=first["user_rank"],
            operation_scope=first["operation_scope"], iteration=first["iteration"], size_bytes_per_copy=pair.size_bytes,
            disposition=disposition, overlap_ns=pair.overlap_ns, pair_span_ns=span, solo_budget_ns=budget,
            other_visible_work_graph_id=confounds.get(pair), physical_cause_proven=False,
            members=[{k: t.get(k) for k in ("graph_id", "stream_id", "task_id", "observed_start_ns",
                "observed_stop_ns", "duration_ns", "duration_slow", "reference_iterations",
                "reference_graph_ids", "copy_solo_max_ns")} for t in members]))
    return results
