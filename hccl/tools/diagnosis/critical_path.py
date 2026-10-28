#!/usr/bin/env python3
"""Measured-schedule critical paths over exported execution evidence.

Notify synchronizes completion, not the start of a wait. Its blocked interval
must not be charged again after the producer. Idle gaps remain explicit and
unattributed; counterfactuals hold those gaps and all other work fixed.
"""

from __future__ import annotations

import argparse
import csv
import heapq
import json
import os
import sys
from collections import defaultdict
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from diagnosis import visualize_dependency_graph as graph
    from diagnosis.schema import write_csv
else:
    from . import visualize_dependency_graph as graph
    from .schema import write_csv


SOURCE = ("", "source")
SINK = ("", "sink")
ORDER_KIND = "direct_stream_order_observed"
SYNC_KINDS = frozenset({"direct_notify_sync_exact", "local_notify_sync_exact"})


@dataclass(frozen=True)
class Activity:
    activity_id: str
    src: tuple[str, str]
    dst: tuple[str, str]
    weight_ns: int
    kind: str
    graph_id: str = ""
    execution_edge_id: str = ""


def _ns(row: dict, side: str) -> int:
    value = row.get("task_" + side)
    number = Decimal(str(value)) if value not in (None, "") else graph.execution_time_order_value(row, side)
    number *= 1000
    if not number.is_finite() or number != number.to_integral_value():
        raise ValueError("task timestamps must be finite integer nanoseconds")
    return int(number)


def _topology(activities):
    outgoing, indegree = defaultdict(list), defaultdict(int)
    for activity in activities:
        outgoing[activity.src].append(activity)
        indegree[activity.src] += 0
        indegree[activity.dst] += 1
    ready = [event for event, degree in indegree.items() if not degree]
    heapq.heapify(ready)
    order = []
    while ready:
        event = heapq.heappop(ready)
        order.append(event)
        for activity in outgoing[event]:
            indegree[activity.dst] -= 1
            if not indegree[activity.dst]:
                heapq.heappush(ready, activity.dst)
    if len(order) != len(indegree):
        raise ValueError("critical-path event graph contains a cycle")
    return order, outgoing


def _forward(order, outgoing, zero_activity="", reductions=None):
    earliest, predecessor = {SOURCE: 0}, {}
    for event in order:
        if event not in earliest:
            continue
        for activity in outgoing[event]:
            weight = (0 if activity.activity_id == zero_activity else
                      activity.weight_ns - (reductions or {}).get(activity.activity_id, 0))
            finish = earliest[event] + weight
            previous = predecessor.get(activity.dst)
            if (activity.dst not in earliest or finish > earliest[activity.dst]
                    or (finish == earliest[activity.dst] and previous is not None
                        and activity.activity_id < previous.activity_id)):
                earliest[activity.dst] = finish
                predecessor[activity.dst] = activity
    return earliest, predecessor


def execution_reduction_gains(report, reductions):
    """Local completion sensitivity when ONE measured execution excess is removed.

    Unlike zeroing a Wait, this preserves the Notify join, residual waits,
    unexplained releases and all other work in the observed schedule.
    """
    activities = [Activity(item["activity_id"], (item["src_graph_id"], item["src_event"]),
                           (item["dst_graph_id"], item["dst_event"]), item["weight_ns"],
                           item["kind"], item["graph_id"], item["execution_edge_id"])
                  for item in report["activities"]]
    order, outgoing = _topology(activities)
    lookup = {a.graph_id: a for a in activities if a.kind == "task_execution"}
    result = {}
    for key, amount in reductions.items():
        if key not in lookup or type(amount) is not int or not 0 <= amount <= lookup[key].weight_ns:
            raise ValueError("reduction requires a known execution and bounded integer duration")
        changed, _ = _forward(order, outgoing, reductions={lookup[key].activity_id: amount})
        result[key] = report["makespan_ns"] - changed[SINK]
    return result


def analyze_critical_path(rows, edges, *, completion_ids=(), impact_limit=20, issues=()):
    """Return paths/slack and bounded what-if tests for one node's capture.

    This is an observation-constrained replay, not a hardware simulator or an
    assertion that the captured dependency graph covers the whole application.
    """
    if not rows:
        raise ValueError("no execution tasks selected")
    if impact_limit < 0:
        raise ValueError("impact_limit must be non-negative")
    nodes = {row["_graph_id"]: row for row in rows}
    if any(not key for key in nodes):
        raise ValueError("missing graph_id")
    if len(nodes) != len(rows):
        raise ValueError("duplicate execution graph_id")
    if len({row["_node_id"] for row in rows}) != 1:
        raise ValueError("uncalibrated multi-node critical paths are unsupported; select --node-id")
    if any(row.get("_node_kind", "execution") != "execution" for row in rows):
        raise ValueError("use execution artifacts, not contracted resource/boundary artifacts")
    stats = graph.analyze_execution_graph(rows, edges)
    graph._assert_execution_graph_integrity(stats)
    if stats["has_cycle"]:
        raise ValueError("execution graph contains a cycle")
    times = {key: (_ns(row, "start"), _ns(row, "stop")) for key, row in nodes.items()}
    if any(stop < start for start, stop in times.values()):
        raise ValueError("task stop precedes start")
    origin = min(start for start, _ in times.values())
    completions = sorted(set(completion_ids) if completion_ids else nodes)
    if any(key not in nodes for key in completions):
        raise ValueError("completion graph_id is not in the selected execution tasks")
    diagnostics = list(issues)

    def issue(code, graph_id="", edge_id="", detail=""):
        diagnostics.append(dict(code=code, graph_id=graph_id, execution_edge_id=edge_id, detail=detail))

    incoming_order, incoming_sync = defaultdict(list), defaultdict(list)
    for edge in sorted(edges, key=lambda item: item["edge_id"]):
        src, dst = nodes[edge["src"]], nodes[edge["dst"]]
        kind, identifier = edge["kind"], edge["edge_id"]
        if kind != ORDER_KIND and kind not in SYNC_KINDS:
            issue("unsupported_dependency", edge_id=identifier, detail=kind)
            continue
        if any(row.get("_subtask_id", -1) >= 0 for row in (src, dst)):
            issue("ffts_timing_not_a_complete_dag", edge_id=identifier)
            continue
        if kind == ORDER_KIND:
            if edge.get("confidence") not in ("observed", "exact"):
                issue("unsupported_confidence", edge_id=identifier)
                continue
            lane = lambda row: (row["_node_id"], row["_device_id"], row["_stream_id"])
            if lane(src) != lane(dst):
                raise ValueError("stream-order edge crosses physical streams: " + identifier)
            if times[edge["src"]][1] > times[edge["dst"]][0]:
                issue("incompatible_order_timestamps", edge_id=identifier)
                continue
            incoming_order[edge["dst"]].append(edge)
        else:
            if (edge.get("confidence") != "exact"
                    or src.get("profiler_task_kind") != "notify_record"
                    or dst.get("profiler_task_kind") != "notify_wait"):
                issue("unsupported_sync_endpoint", edge_id=identifier)
                continue
            if times[edge["src"]][1] > times[edge["dst"]][1]:
                # A valid identity need not provide a comparable signal timestamp.
                issue("incompatible_notify_timestamps", edge_id=identifier,
                      detail="record.stop exceeds wait.stop; no hardware signal visibility timestamp")
                continue
            incoming_sync[edge["dst"]].append(edge)

    for key, syncs in list(incoming_sync.items()):
        if len(syncs) > 1:
            issue("ambiguous_notify_producers", key, detail="multiple producers; no artificial AND join")
            incoming_sync[key] = []
    activities, task_work, task_gap = [], {}, {}

    def add(key, src, dst, weight, kind, graph_id="", edge_id=""):
        activity = Activity(key, src, dst, weight, kind, graph_id, edge_id)
        activities.append(activity)
        return activity

    for key, row in sorted(nodes.items()):
        start, stop = times[key]
        ready, begin, end = (key, "ready"), (key, "start"), (key, "finish")
        orders = incoming_order[key]
        latest = max((times[edge["src"]][1] for edge in orders), default=origin)
        if orders:
            for edge in orders:
                add("dependency:" + edge["edge_id"], (edge["src"], "finish"), ready, 0,
                    "stream_dependency", key, edge["edge_id"])
        else:
            add("release:" + key, SOURCE, ready, 0, "capture_boundary", key)
        task_gap[key] = add("gap:" + key, ready, begin, start - latest,
                            "unattributed_gap" if orders else "capture_release", key)
        kind = row.get("profiler_task_kind", "")
        if kind == "notify_wait" and incoming_sync[key]:
            signal_ready = (key, "signal_ready")
            add("wait_start:" + key, begin, signal_ready, 0, "wait_started", key)
            for edge in incoming_sync[key]:
                add("dependency:" + edge["edge_id"], (edge["src"], "finish"), signal_ready,
                    0, "notify_dependency", key, edge["edge_id"])
            release = max(start, max(times[edge["src"]][1] for edge in incoming_sync[key]))
            task_work[key] = add("work:" + key, signal_ready, end, stop - release,
                                 "notify_residual", key)
        else:
            work_kind = "task_execution"
            if kind in ("notify_wait", "event_wait"):
                work_kind = "unresolved_wait"
                issue("unresolved_wait", key, detail="full wait retained as opaque time, not a root cause")
            elif kind == "rdma":
                work_kind = "rdma_submission"
                issue("rdma_completion_unmeasured", key)
            elif kind == "kernel_aicpu" or row.get("_subtask_id", -1) >= 0:
                work_kind = "opaque_execution"
                issue("incomplete_execution_dependencies", key)
            task_work[key] = add("work:" + key, begin, end, stop - start, work_kind, key)
    for key in completions:
        add("completion:" + key, (key, "finish"), SINK, 0, "completion", key)

    order, outgoing = _topology(activities)
    earliest, predecessor = _forward(order, outgoing)
    makespan = earliest[SINK]
    for key, (start, stop) in times.items():
        if earliest[(key, "start")] != start - origin or earliest[(key, "finish")] != stop - origin:
            raise ValueError("measured schedule cannot be reconstructed for " + key)
    remaining = {SINK: 0}
    for event in reversed(order):
        values = [activity.weight_ns + remaining[activity.dst] for activity in outgoing[event]
                  if activity.dst in remaining]
        if values:
            remaining[event] = max(values)

    def slack(activity):
        if activity.dst not in remaining:
            return None
        return makespan - earliest[activity.src] - activity.weight_ns - remaining[activity.dst]

    path, cursor = [], SINK
    while cursor != SOURCE:
        activity = predecessor[cursor]
        path.append(activity.activity_id)
        cursor = activity.src
    path.reverse()
    path_set = set(path)
    impact_candidates = sorted(
        (activity for activity in activities if activity.weight_ns > 0 and slack(activity) == 0),
        key=lambda activity: (-activity.weight_ns, activity.activity_id),
    )[:impact_limit]
    gains = {}
    for activity in impact_candidates:
        changed, _ = _forward(order, outgoing, zero_activity=activity.activity_id)
        gains[activity.activity_id] = makespan - changed[SINK]
    activity_rows = []
    for activity in activities:
        activity_rows.append(dict(activity_id=activity.activity_id, kind=activity.kind,
            graph_id=activity.graph_id, execution_edge_id=activity.execution_edge_id,
            src_graph_id=activity.src[0], src_event=activity.src[1],
            dst_graph_id=activity.dst[0], dst_event=activity.dst[1],
            weight_ns=activity.weight_ns, modeled_start_ns=earliest[activity.src],
            modeled_finish_ns=earliest[activity.src] + activity.weight_ns,
            slack_ns=slack(activity), critical=int(slack(activity) == 0),
            on_representative_path=int(activity.activity_id in path_set),
            modeled_gain_if_zero_ns=gains.get(activity.activity_id)))
    activity_by_id = {row["activity_id"]: row for row in activity_rows}
    task_rows = []
    for key, row in sorted(nodes.items()):
        work, gap = task_work[key], task_gap[key]
        start, stop = times[key]
        task_rows.append(dict(graph_id=key, node_id=row["_node_id"], device_id=row["_device_id"],
            user_rank=row.get("_user_rank", -1), stream_id=row["_stream_id"], task_id=row["_task_id"],
            operation_scope=row.get("_operation_scope", ""), phase=row.get("phase", ""),
            step=row.get("step", ""), event=row.get("event", ""),
            task_kind=row.get("profiler_task_kind", ""), cost_kind=work.kind,
            start_ns=start - origin, finish_ns=stop - origin, observed_duration_ns=stop - start,
            effective_work_ns=work.weight_ns, gap_before_ns=gap.weight_ns,
            slack_ns=slack(work), critical=int(slack(work) == 0),
            on_representative_path=int(work.activity_id in path_set),
            modeled_gain_if_work_zero_ns=gains.get(work.activity_id),
            modeled_gain_if_gap_zero_ns=gains.get(gap.activity_id)))
    impacts = [activity_by_id[activity.activity_id] for activity in impact_candidates]
    impacts.sort(key=lambda item: (-item["modeled_gain_if_zero_ns"], -item["weight_ns"], item["activity_id"]))
    return dict(schema_version=1, analysis_kind="observed_schedule_critical_path",
        status="partial_evidence" if diagnostics else "observed_model",
        node_id=rows[0]["_node_id"], time_origin_ns=origin,
        completion_scope="explicit_tasks" if completion_ids else "all_selected_tasks",
        completion_graph_ids=completions, makespan_ns=makespan,
        critical_task_count=sum(task["critical"] for task in task_rows),
        tasks=task_rows, activities=activity_rows,
        representative_path=[dict(activity_by_id[key], path_index=index) for index, key in enumerate(path)],
        impacts=impacts, issues=diagnostics,
        assumptions=[
            "Only one node clock domain; no cross-node absolute-time subtraction.",
            "Completion means the selected capture/tasks, not unobserved application completion.",
            "Only observed direct stream order and exact direct/local Notify edges are timed.",
            "Notify completion joins wait.start and record.stop; only the observed residual is charged.",
            "Gaps/releases are unexplained observed time, not inferred dependencies or proved root causes.",
            "What-if sets ONE activity to zero, keeping other work, releases, gaps and dependencies fixed.",
            "Zero slack is schedule sensitivity, not an anomaly label; tied critical paths may give zero gain.",
            "Reconstructing timestamps does not prove dependency completeness or hardware causality.",
        ])


def export_report(report, prefix):
    prefix = Path(prefix)
    prefix.parent.mkdir(parents=True, exist_ok=True)
    output = prefix.with_name(prefix.name + ".json")
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    for name in ("tasks", "activities", "representative_path", "impacts", "issues"):
        values = report[name]
        fields = list(values[0]) if values else ["activity_id"] if name != "issues" else ["code", "graph_id", "execution_edge_id", "detail"]
        write_csv(str(prefix.with_name(prefix.name + "_" + name + ".csv")), fields, values)
    return output


def analyze_multi_node_critical_path(rows, edges, *, completion_ids=(), impact_limit=20, issues=()):
    """Local timed paths plus evidenced remote boundaries, never a global time sum.

    RDMA submission is not hardware completion. Even comparable timestamps alone
    would not justify replacing a remote wait by a doorbell-completion join.
    """
    if not rows:
        raise ValueError("no execution tasks selected")
    stats = graph.analyze_execution_graph(rows, edges)
    graph._assert_execution_graph_integrity(stats)
    if stats["has_cycle"]:
        raise ValueError("execution graph contains a cycle")
    nodes = {row["_graph_id"]: row for row in rows}
    if len(nodes) != len(rows) or any(not key for key in nodes):
        raise ValueError("duplicate or missing execution graph_id")
    if any(key not in nodes for key in completion_ids):
        raise ValueError("completion graph_id is not in selected execution tasks")
    if any(row.get("_node_kind", "execution") != "execution" for row in rows):
        raise ValueError("use execution artifacts, not contracted resource/boundary artifacts")
    if any(_ns(row, "stop") < _ns(row, "start") for row in rows):
        raise ValueError("task stop precedes start")
    groups = defaultdict(list)
    for row in rows:
        groups[row["_node_id"]].append(row)
    local_edges, local_issues, remote_edges = defaultdict(list), defaultdict(list), []
    for edge in edges:
        src, dst = nodes[edge["src"]], nodes[edge["dst"]]
        if src["_node_id"] == dst["_node_id"]:
            local_edges[src["_node_id"]].append(edge)
        else:
            remote_edges.append(edge)
            local_issues[dst["_node_id"]].append(dict(code="remote_dependency_boundary",
                graph_id=edge["dst"], execution_edge_id=edge["edge_id"],
                detail="remote producer retained in topology; no cross-clock time decomposition"))
    reports, summaries, task_results = {}, [], {}
    for node_id, node_rows in sorted(groups.items()):
        ends = [key for key in completion_ids if nodes[key]["_node_id"] == node_id]
        if completion_ids and not ends:
            summaries.append(dict(node_id=node_id, status="not_selected_completion_domain",
                makespan_ns=None, critical_task_count=None, task_count=len(node_rows)))
            continue
        local_ids = {row["_graph_id"] for row in node_rows}
        inherited = [item for item in issues if not item.get("graph_id") or item["graph_id"] in local_ids]
        report = analyze_critical_path(node_rows, local_edges[node_id], completion_ids=ends,
            impact_limit=impact_limit, issues=inherited + local_issues[node_id])
        reports[node_id] = report
        task_results.update({task["graph_id"]: task for task in report["tasks"]})
        summaries.append(dict(node_id=node_id, status=report["status"], makespan_ns=report["makespan_ns"],
            critical_task_count=report["critical_task_count"], task_count=len(node_rows)))
    bridges = []
    for edge in sorted(remote_edges, key=lambda item: item["edge_id"]):
        src, dst = nodes[edge["src"]], nodes[edge["dst"]]
        supported = (edge["kind"] == "cross_node_notify_sync_observed"
                     and edge.get("confidence") == "observed"
                     and src.get("profiler_task_kind") == "rdma"
                     and dst.get("profiler_task_kind") == "notify_wait")
        bridges.append(dict(execution_edge_id=edge["edge_id"], kind=edge["kind"],
            confidence=edge.get("confidence", ""), producer_graph_id=edge["src"],
            wait_graph_id=edge["dst"], producer_node_id=src["_node_id"], wait_node_id=dst["_node_id"],
            producer_user_rank=src.get("_user_rank", -1), wait_user_rank=dst.get("_user_rank", -1),
            producer_phase=src.get("phase", ""), wait_phase=dst.get("phase", ""),
            producer_event=src.get("event", ""), wait_event=dst.get("event", ""),
            local_wait_duration_ns=_ns(dst, "stop") - _ns(dst, "start"),
            rdma_submission_duration_ns=_ns(src, "stop") - _ns(src, "start"),
            wait_critical_in_local_scope=task_results.get(edge["dst"], {}).get("critical"),
            producer_critical_in_local_scope=task_results.get(edge["src"], {}).get("critical"),
            timing_status="cross_node_uncalibrated" if supported else "unsupported_remote_dependency",
            remote_delay_ns=None, network_transfer_ns=None, global_slack_ns=None,
            reason="Topology only; RDMA doorbell is not network completion and local criticality is not global criticality"))
    return dict(schema_version=2, analysis_kind="multi_node_local_critical_paths",
        status="partial_evidence", timing_status="cross_node_uncalibrated",
        global_makespan_ns=None, global_critical_path=None, global_critical_task_count=None,
        node_summaries=summaries, cross_node_dependencies=bridges, local_reports=reports,
        assumptions=[
            "Local paths constrain each selected node capture/endpoints, not a proven global workload completion.",
            "Different nodes have independent clocks; their starts, stops, makespans and gains are not added or ranked globally.",
            "Cross-node Notify edges retain real graph IDs but do not enter the local timed event DAG.",
            "A critical remote Wait is a symptom boundary, not proof that the Wait or its producer is a root cause.",
            "RDMA duration is submission only; unmeasured network completion cannot be replaced by doorbell timestamps.",
            "Unsupported/missing local dependencies and opaque waits remain partial evidence.",
        ])


def export_multi_node_report(report, prefix):
    prefix = Path(prefix)
    prefix.parent.mkdir(parents=True, exist_ok=True)
    summary = {key: value for key, value in report.items() if key != "local_reports"}
    summary["local_report_files"] = {}
    for index, (node_id, local) in enumerate(sorted(report["local_reports"].items())):
        local_prefix = prefix.with_name(prefix.name + "_node" + str(index))
        summary["local_report_files"][node_id] = export_report(local, local_prefix).name
    for name in ("node_summaries", "cross_node_dependencies"):
        values = report[name]
        fields = list(values[0]) if values else ["execution_edge_id"]
        write_csv(str(prefix.with_name(prefix.name + "_" + name + ".csv")), fields, values)
    output = prefix.with_name(prefix.name + ".json")
    output.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("nodes_csv", type=Path)
    parser.add_argument("--edges-csv", type=Path, required=True)
    parser.add_argument("--notify-ambiguities-csv", type=Path)
    parser.add_argument("--node-id", help="Select one local clock domain; never a global multi-node path")
    parser.add_argument("--multi-node", action="store_true", help="Analyze each node locally and retain remote dependency boundaries; not a global timed path")
    parser.add_argument("--operation-scope", help="Exact profiler_op_scope to select; default is the entire capture")
    parser.add_argument("--completion-task", action="append", default=[], help="Completion graph_id; repeat for multiple endpoints")
    parser.add_argument("--impact-limit", type=int, default=20, help="What-if tests for the N largest critical activities; 0 disables")
    parser.add_argument("-o", "--output-prefix", type=Path)
    args = parser.parse_args()
    if args.multi_node and args.node_id:
        parser.error("--multi-node and --node-id are mutually exclusive")
    try:
        all_rows = graph.read_graph_artifact_nodes(args.nodes_csv)
        all_edges = graph.read_graph_artifact_edges(args.edges_csv)
        # Validate before filtering, so missing endpoints are not hidden by selection.
        graph._assert_execution_graph_integrity(graph.analyze_execution_graph(all_rows, all_edges))
        rows = [row for row in all_rows
                if (args.node_id is None or row["_node_id"] == args.node_id)
                and (args.operation_scope is None or row.get("_operation_scope") == args.operation_scope)]
        selected = {row["_graph_id"] for row in rows}
        edges, issues = [], []
        for edge in all_edges:
            if edge["src"] in selected and edge["dst"] in selected:
                edges.append(edge)
            elif edge["dst"] in selected:
                issues.append(dict(code="selection_boundary", graph_id=edge["dst"],
                    execution_edge_id=edge["edge_id"], detail="upstream task outside selected node/operation"))
        ambiguity_path = args.notify_ambiguities_csv
        if ambiguity_path is None and args.nodes_csv.stem.endswith("_nodes"):
            ambiguity_path = args.nodes_csv.with_name(args.nodes_csv.stem[:-6] + "_notify_ambiguities.csv")
        if ambiguity_path is not None and ambiguity_path.exists():
            with ambiguity_path.open(encoding="utf-8-sig", newline="") as source:
                for row in csv.DictReader(source):
                    issues.append(dict(code="notify_ambiguity", graph_id="", execution_edge_id="",
                        detail="{}:{}".format(row.get("relation_id", ""), row.get("status", ""))))
        else:
            issues.append(dict(code="notify_ambiguities_not_provided", graph_id="", execution_edge_id="", detail="coverage not checked"))
        prefix = args.output_prefix or args.nodes_csv.with_name("critical_path")
        if args.multi_node:
            report = analyze_multi_node_critical_path(rows, edges, completion_ids=args.completion_task,
                                                      impact_limit=args.impact_limit, issues=issues)
            output = export_multi_node_report(report, prefix)
        else:
            report = analyze_critical_path(rows, edges, completion_ids=args.completion_task,
                                           impact_limit=args.impact_limit, issues=issues)
            output = export_report(report, prefix)
    except (ValueError, OSError, ArithmeticError) as error:
        parser.exit(2, "critical-path error: {}\n".format(error))
    if args.multi_node:
        print("status=partial_evidence nodes={} remote_dependencies={} global_makespan_ns=unavailable report={}".format(
            len(report["node_summaries"]), len(report["cross_node_dependencies"]), output))
    else:
        print("status={} makespan_ns={} critical_tasks={} issues={} report={}".format(
            report["status"], report["makespan_ns"], report["critical_task_count"], len(report["issues"]), output))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
