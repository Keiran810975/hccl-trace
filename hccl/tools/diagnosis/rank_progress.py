"""Milestones compared to each Rank's own uniquely matched history."""
from __future__ import annotations

from collections import defaultdict
from decimal import Decimal

from . import analyze_waits as waits
from .compare_diagnosis import median
from .dependency_timing import WAIT


MIN_SAMPLES = 3
SIGNALS = {"event_record", "notify_record"}
WORK = {"sdma", "reduce_inline", "reduce_tbe", "kernel_aicore", "kernel_aivec", "kernel_mix_aic", "kernel_mix_aiv"}


def s2_growth(item):
    """A duration inventory, not an attribution decision."""
    reference = item.get("reference_mean_ns")
    if not item["duration_comparable"] or reference is None or Decimal(reference) <= 0:
        return None
    mean = Decimal(reference)
    current = Decimal(item["duration_ns"])
    if current < 2 * mean:
        return None
    return dict(item, duration_delta_ns=str(current - mean),
                duration_increase_percent=str((current-mean)*100/mean))


def task_evidence(row, task):
    return dict(graph_id=row["_graph_id"], node_id=row["_node_id"], device_id=row["_device_id"],
        rank=row["_user_rank"], stream_id=row["_stream_id"], task_id=row["_task_id"],
        operation_scope=row.get("_operation_scope"), iteration=task.get("iteration"),
        algorithm=row.get("algorithm"), phase=row.get("phase"), step=row.get("step"),
        slice=row.get("slice"), peer_rank=row.get("_peer_rank"), event=row.get("event"),
        task_domain=task.get("task_domain", "unknown"),
        task_kind=row["profiler_task_kind"], start_ns=waits.ns(row, "start"), stop_ns=waits.ns(row, "stop"),
        duration_ns=waits.duration(row), observed_stop_meaning=(
            "local_submission_not_payload_completion" if row["profiler_task_kind"] == "rdma" else "profiler_task_stop"),
        duration_delta_ns=task.get("delta_ns"), reference_mean_ns=task.get("reference_mean_ns"),
        reference_mad_ns=task.get("reference_mad_ns"), reference_count=task.get("reference_count", 0),
        reference_graph_ids=task.get("reference_graph_ids", []), reference_iterations=task.get("reference_iterations", []),
        comparison_status=task.get("comparison_status"), comparison_basis=task.get("comparison_basis"),
        duration_slow=bool(task.get("duration_slow")), iteration_start_late=bool(task.get("iteration_start_late")),
        iteration_start_delta_ns=task.get("iteration_start_delta_ns"))


class Progress:
    def __init__(self, graph, tasks, timings, options):
        self.graph = graph
        self.tasks = tasks
        self.options = options
        self.by_scope = defaultdict(list)
        for gid, row in graph.nodes.items():
            if row.get("_operation_scope"):
                self.by_scope[row["_operation_scope"]].append(gid)
        self.intervals = {}
        for row in timings:
            key = row["operation_scope"], row["node_id"], int(row["device_id"]), int(row["user_rank"])
            start, end = int(row["start_ns"]), int(row["end_ns"])
            if key in self.intervals or end < start or int(row["duration_ns"]) != end - start:
                raise ValueError("invalid/duplicate Rank CollOp timing")
            self.intervals[key] = start, end
        self.cache = {}

    def offsets(self, gid):
        row = self.graph.nodes[gid]
        interval = self.intervals.get((row.get("_operation_scope"), row["_node_id"],
                                       row["_device_id"], row["_user_rank"]))
        if interval is None:
            return None, "missing_rank_collop_interval"
        origin, end = interval
        start, stop = (waits.ns(row, side) for side in ("start", "stop"))
        if not origin <= start <= stop <= end:
            return None, "task_outside_rank_collop_interval"
        return (start-origin, stop-origin), None

    def statistic(self, value, previous):
        if not previous:
            return None
        center = median(previous)
        mad = median(abs(v-center) for v in previous)
        delta = Decimal(value) - center
        late = (len(previous) >= MIN_SAMPLES and delta > 0 and value > max(previous)
                and value >= center * Decimal(self.options.wait_slowdown_factor)
                and delta >= mad * Decimal(self.options.mad_multiplier))
        return dict(value_ns=value, historical_median_ns=str(center), historical_mad_ns=str(mad),
                    historical_max_ns=max(previous), delta_ns=str(delta), sample_count=len(previous),
                    anomalous=late)

    def milestone(self, gid):
        if gid in self.cache:
            return self.cache[gid]
        graph, task = self.graph, self.tasks.get(gid, {})
        row = graph.nodes[gid]
        item = task_evidence(row, task)
        ids = list(dict.fromkeys(item["reference_graph_ids"]))
        local_ids = [g for g in ids if g in graph.nodes and all(
            graph.nodes[g][k] == row[k] for k in ("_node_id", "_device_id", "_user_rank"))]
        durations = [waits.duration(graph.nodes[g]) for g in local_ids]
        offsets, reason = self.offsets(gid)
        samples = [(g, period) for g in local_ids if (period := self.offsets(g)[0]) is not None]
        start = self.statistic(offsets[0], [p[0] for _, p in samples]) if offsets is not None else None
        stop = self.statistic(offsets[1], [p[1] for _, p in samples]) if offsets is not None else None
        kind = item["task_kind"]
        comparable = (item["reference_count"] >= MIN_SAMPLES and len(durations) >= MIN_SAMPLES)
        verified_wait = graph.wait_proof(gid) if kind in WAIT else None
        item.update(start_progress=start, completion_progress=stop, progress_reference_graph_ids=[g for g, _ in samples],
                    progress_status=reason or ("comparable" if len(samples) >= MIN_SAMPLES else "insufficient_history"),
                    duration_history=self.statistic(item["duration_ns"], durations),
                    duration_comparable=comparable, wait_producer=verified_wait,
                    intrinsic_work_slow=(comparable and item["duration_slow"] and kind in WORK
                        and not task.get("copy_overlap_explained") and not task.get("overlap_explained")
                        and task.get("role") != "suspected_peer_read_impact"),
                    slow_wait=(comparable and item["duration_slow"] and kind in WAIT),
                    starts_late=bool((start or {}).get("anomalous") or
                                     (comparable and item["iteration_start_late"])),
                    completion_late=bool((stop or {}).get("anomalous")))
        self.cache[gid] = item
        return item

    def for_scope(self, scope):
        result = defaultdict(list)
        for gid in self.by_scope.get(scope, ()):
            milestone = self.milestone(gid)
            result[milestone["rank"]].append(milestone)
        for items in result.values():
            items.sort(key=lambda m: (m["node_id"], m["device_id"], m["start_ns"], m["graph_id"]))
        return result

    def entry_waits(self, scope):
        """Observe pre-CollOp gates only when on the verified path into the DB start."""
        seen, result = set(), []
        for gid in self.by_scope.get(scope, ()):
            row = self.graph.nodes[gid]
            offsets, _ = self.offsets(gid)
            if offsets is None or offsets[0] != 0:
                continue
            links = self.graph.orders.get(gid, ())
            if len(links) != 1:
                continue
            edge = self.graph.proof(links[0])
            pred = self.graph.nodes[edge["src"]]
            if (edge["verified"] and pred["profiler_task_kind"] in WAIT and edge["src"] not in seen):
                seen.add(edge["src"])
                result.append(dict(wait=self.milestone(edge["src"]), entry_task=self.milestone(gid), stream_edge=edge))
        return result

    def latest_entry(self, scope, ranks):
        entries = defaultdict(list)
        for (op, node, device, rank), (start, _) in self.intervals.items():
            if op == scope and rank in ranks:
                entries[rank].append((node, device, start))
        starts = {r: entries[r][0] for r in ranks if len(entries[r]) == 1}

        def possible(items, local):
            mapped = {}
            for rank, (node, device, start) in items.items():
                clocks = self.graph.local_clocks if local else self.graph.clocks
                clock = clocks.get((node, device))
                if clock is None:
                    return []
                try:
                    mapped[rank] = clock.map_ns(start), clock.estimated_error_ns
                except ValueError:
                    return []
            lower = max((start-error for start, error in mapped.values()), default=0)
            return sorted(r for r, (start, error) in mapped.items() if start+error >= lower)

        all_present = len(starts) == len(ranks)
        nodes = sorted({item[0] for item in starts.values()})
        per_node = {node: possible({r: v for r, v in starts.items() if v[0] == node}, True) for node in nodes}
        group = possible(starts, False) if all_present else []
        if not group and all_present and len(nodes) == 1:
            group = per_node[nodes[0]]
        return dict(latest_rank=group[0] if len(group) == 1 else None, possible_latest_ranks=group,
            latest_by_node=per_node, missing_start_ranks=sorted(set(ranks)-starts.keys()),
            profiler_starts=[dict(rank=r, node_id=node, device_id=device, start_ns=ts)
                             for r, (node, device, ts) in starts.items()],
            status="verified_latest_rank" if len(group) == 1 else "latest_rank_not_unique" if group else
            "missing_shared_clock_or_rank_start")


def abnormal(milestone):
    return any(milestone[k] for k in ("intrinsic_work_slow", "slow_wait", "starts_late", "completion_late"))


def first_by_stream(items):
    """One first anomaly per physical stream, not a global linear Step index."""
    first = {}
    for item in items:
        stream = item["node_id"], item["device_id"], item["stream_id"]
        first.setdefault(stream, item)
    return list(first.values())
