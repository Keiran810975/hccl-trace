"""Readable source-first views of already reported dependency evidence paths."""
from __future__ import annotations

import argparse
import ast
from collections import Counter
import csv
import json
from pathlib import Path
import sys

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from diagnosis import analyze_waits as waits
    from diagnosis import visualize_dependency_graph as graph
    from diagnosis import source_propagation_view as presentation
    from diagnosis.dependency_model import stable_id
    from diagnosis.schema import write_csv
    from diagnosis.task_classifier import source_category, INTERNAL, EXTERNAL, UNRESOLVED
else:
    from . import analyze_waits as waits
    from . import visualize_dependency_graph as graph
    from . import source_propagation_view as presentation
    from .dependency_model import stable_id
    from .schema import write_csv
    from .task_classifier import source_category, INTERNAL, EXTERNAL, UNRESOLVED


METRIC_FIELDS = ("comparison_status", "reference_count", "reference_iterations", "reference_mean_ns",
                 "reference_value_ns", "reference_metric", "delta_ns", "slowdown_factor", "duration_slow", "role")
SOURCE_FIELDS = ("root_id", "component", "node_id", "user_rank", "device_id", "stream_id", "task_id",
                 "source_activity_id",
                 "operation_scope", "iteration", "block", "bucket", "phase", "step", "event", "observed_start_ns",
                 "observed_stop_ns", "duration_ns", "reference_mean_ns", "delta_ns", "slowdown_factor",
                 "reference_iterations", "reference_count", "reason",
                 "physical_cause", "modeled_execution_gain_ns", "impact_status", "traversal_truncated",
                 "other_backtrace_branches_truncated")
SOURCE_FIELDS += ("group_id", "call_site", "occurrence", "reference_value_ns", "reference_metric", "baseline_median_ns")
SOURCE_FIELDS += ("diagnosis_category", "task_domain", "category_rank", "cross_operation")
LIMITS = [
    "Paths start at reported candidates, not at independently inferred physical faults.",
    "Only existing reported evidence paths are expanded; downstream descendants are not exhaustively searched.",
    "A path and a Wait duration increase do not measure the candidate's individual causal contribution.",
    "Concurrent Wait increases must not be summed as workload completion loss.",
    "Cross-node clocks are not aligned; no cross-node timestamp subtraction or global latency sum is performed.",
    "Host preparation is an observed interval. Its device anchor is not a fabricated Host-to-device edge.",
    "Missing/disconnected paths and incompatible local timestamps stay explicit, without inferred repair.",
]


def node_fact(row, comparison):
    start, stop = waits.ns(row, "start"), waits.ns(row, "stop")
    return dict(graph_id=row["_graph_id"], node_id=row["_node_id"], user_rank=row["_user_rank"],
        device_id=row["_device_id"], stream_id=row["_stream_id"], task_id=row["_task_id"],
        subtask_id=row.get("_subtask_id", -1), operation_scope=row.get("_operation_scope", ""),
        task_kind=row.get("profiler_task_kind", ""), event=row.get("event") or row.get("event_name", ""),
        phase=row.get("phase", ""), step=row.get("step", ""), slice=row.get("slice", ""),
        iteration=comparison.get("iteration"), block=comparison.get("block"), bucket=comparison.get("bucket"),
        group_id=comparison.get("group_id"), call_site=comparison.get("call_site"), occurrence=comparison.get("occurrence"),
        start_ns=start, stop_ns=stop, duration_ns=stop-start,
        comparison={k:comparison.get(k) for k in METRIC_FIELDS})


def timing_check(edge, src, dst):
    if "ffts" in edge["kind"] or any(n["subtask_id"]>=0 for n in (src,dst)):
        return "ffts_not_complete_hardware_dag"
    if src["node_id"] != dst["node_id"]:
        return "cross_node_uncalibrated"
    if edge["kind"] == "direct_stream_order_observed":
        return "compatible_stream_order" if src["stop_ns"] <= dst["start_ns"] else "overlapping_stream_tasks"
    if src["task_kind"] == "rdma":
        return "rdma_submission_not_completion"
    if src["stop_ns"] > dst["stop_ns"]:
        return "record_after_wait_end"
    if src["stop_ns"] <= dst["start_ns"]:
        return "signal_precedes_wait_start"
    return "producer_observed_during_wait"


def build_report(rows, edges, candidates, comparisons=(), *, primary_source_candidate_id=None, reference=None,
                 unresolved_observations=()):
    nodes = {r["_graph_id"]:r for r in rows}
    links = {e["edge_id"]:e for e in edges}
    if len(nodes) != len(rows) or len(links) != len(edges):
        raise ValueError("propagation export requires unique artifact node/edge IDs")
    metrics = {t["graph_id"]:t for t in comparisons}
    facts, exported = {}, []

    def fact(identifier):
        if identifier not in facts:
            facts[identifier] = node_fact(nodes[identifier], metrics.get(identifier, {}))
        return facts[identifier]

    for rank, root in enumerate(candidates, 1):
        if root["component"] not in {"execution", "host_preparation"}:
            raise ValueError("only execution and observed Host candidates are supported; not legacy gap roots")
        anchor = root["graph_id"]
        category = source_category(root, nodes.get(anchor, {}))
        if category == UNRESOLVED:
            continue
        item = dict(candidate_id=root["root_id"], candidate_rank=rank,
            diagnosis_category=category,
            primary=category == INTERNAL and root["root_id"] == primary_source_candidate_id,
            source={k:root.get(k) for k in SOURCE_FIELDS}, anchor_graph_id=anchor,
            anchor_meaning="observed_device_anchor_only" if root["component"]=="host_preparation" else "source_execution",
            status=root["status"], chains=[])
        for target in dict.fromkeys(root.get("affected_wait_graph_ids", [])):
            path = root.get("evidence_paths", {}).get(target)
            chain = dict(chain_id=stable_id("propagation", (root["root_id"], target)), target_wait_graph_id=target,
                         node_ids=[], edge_ids=[], hops=[], boundaries=[], path_complete=False)
            cursor = anchor
            if root["component"]=="host_preparation" and isinstance(path,list) and path and path[0] in links:
                branch_anchor = nodes.get(links[path[0]]["src"])
                if branch_anchor and all(branch_anchor[k]==root[field] for k,field in
                    (("_node_id","node_id"),("_user_rank","user_rank"),("_device_id","device_id"),("_operation_scope","operation_scope"))) and branch_anchor.get("profiler_task_kind") in {"notify_record", "rdma"}:
                    cursor=branch_anchor["_graph_id"]
                else:
                    chain["boundaries"].append(dict(reason="invalid_host_branch_anchor",edge_id=path[0]))
            chain["anchor_graph_id"]=cursor
            if target in nodes:
                fact(target)
            if cursor in nodes:
                fact(cursor)
                chain["node_ids"].append(cursor)
            else:
                chain["boundaries"].append(dict(reason="missing_source_anchor", graph_id=cursor))
            if not isinstance(path, list) or not path:
                chain["boundaries"].append(dict(reason="missing_reported_evidence_path", graph_id=target))
            else:
                seen = {cursor}
                for identifier in path:
                    edge = links.get(identifier)
                    reason = ("missing_artifact_edge" if edge is None else
                              "disconnected_path" if edge["src"] != cursor else
                              "missing_artifact_endpoint" if edge["src"] not in nodes or edge["dst"] not in nodes else
                              "repeated_path_node" if edge["dst"] in seen else
                              "unsupported_evidence" if edge.get("confidence") not in {"observed", "exact"} or
                              not (edge["kind"]=="direct_stream_order_observed" or "notify_sync" in edge["kind"]) else None)
                    if reason:
                        chain["boundaries"].append(dict(reason=reason, edge_id=identifier))
                        break
                    src, dst = fact(edge["src"]), fact(edge["dst"])
                    chain["hops"].append(dict(edge_id=identifier, src=edge["src"], dst=edge["dst"],
                        kind=edge["kind"], confidence=edge["confidence"], reason=edge.get("reason", ""),
                        timing_status=timing_check(edge, src, dst)))
                    chain["edge_ids"].append(identifier)
                    cursor = edge["dst"]
                    seen.add(cursor)
                    chain["node_ids"].append(cursor)
                chain["path_complete"] = (not chain["boundaries"] and cursor==target and
                                           fact(target)["task_kind"]=="notify_wait")
                if not chain["path_complete"] and not chain["boundaries"]:
                    chain["boundaries"].append(dict(reason="path_does_not_end_at_declared_wait", graph_id=cursor))
            chain["evidence_confidence"] = ("observed" if any(h["confidence"]=="observed" for h in chain["hops"])
                                             else "exact" if chain["hops"] else "unavailable")
            chain["timing_warnings"] = [h["edge_id"] for h in chain["hops"] if h["timing_status"] not in
                                        {"compatible_stream_order", "producer_observed_during_wait"}]
            chain["status"] = ("incomplete_evidence" if not chain["path_complete"] else
                               "complete_with_timing_limits" if chain["timing_warnings"] else "complete_observed_path")
            item["chains"].append(chain)
        item["chains"].sort(key=lambda c:(len(c["edge_ids"]), c["target_wait_graph_id"]))
        exported.append(item)
    chains = [c for root in exported for c in root["chains"]]
    return dict(schema_version=2, kind="source_first_dependency_evidence", primary_source_candidate_id=primary_source_candidate_id,
        summary=dict(candidate_count=sum(c["diagnosis_category"] == INTERNAL for c in exported),
            result_entry_count=len(exported), chain_count=len(chains),
            unique_target_wait_count=len({c["target_wait_graph_id"] for c in chains}),
            complete_chain_count=sum(c["path_complete"] for c in chains),
            communication_source_count=sum(c["diagnosis_category"] == INTERNAL for c in exported),
            external_clue_count=sum(c["diagnosis_category"] == EXTERNAL for c in exported),
            unresolved_observation_count=len(unresolved_observations),
            chain_status_counts=dict(Counter(c["status"] for c in chains))),
        candidates=exported, nodes=facts, unresolved_observations=list(unresolved_observations), limits=LIMITS, candidate_order_changed=False,
        exhaustive_downstream_search=False, physical_causation_proven=False,
        reference=reference or dict(kind="previous_five_measured", statistic="mean", window=5))


def export_report(report, directory):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=False)
    (directory/"report.json").write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    chains, steps = [], []
    for root in report["candidates"]:
        source = root["source"]
        for chain in root["chains"]:
            target = report["nodes"].get(chain["target_wait_graph_id"])
            chains.append(dict(candidate_id=root["candidate_id"],candidate_rank=root["candidate_rank"],primary=root["primary"],
                chain_id=chain["chain_id"],source_rank=source["user_rank"],source_task_id=source["task_id"],
                source_duration_ns=source["duration_ns"],source_reference_mean_ns=source["reference_mean_ns"],source_delta_ns=source["delta_ns"],
                wait_graph_id=chain["target_wait_graph_id"],wait_rank=target["user_rank"] if target else None,
                wait_task_id=target["task_id"] if target else None,wait_duration_ns=target["duration_ns"] if target else None,
                wait_reference_mean_ns=target["comparison"]["reference_mean_ns"] if target else None,
                wait_delta_ns=target["comparison"]["delta_ns"] if target else None,
                edge_count=len(chain["edge_ids"]),path_complete=chain["path_complete"],status=chain["status"],
                evidence_confidence=chain["evidence_confidence"],edge_ids=json.dumps(chain["edge_ids"])))
            for position, identifier in enumerate(chain["node_ids"]):
                node = report["nodes"][identifier]
                hop = chain["hops"][position-1] if position else None
                steps.append(dict(candidate_id=root["candidate_id"],chain_id=chain["chain_id"],position=position,
                    **{k:node[k] for k in ("graph_id","node_id","user_rank","device_id","stream_id","task_id","iteration","block","bucket","phase","step","event","task_kind","start_ns","stop_ns","duration_ns")},
                    reference_mean_ns=node["comparison"]["reference_mean_ns"],delta_ns=node["comparison"]["delta_ns"],
                    incoming_edge_id=hop["edge_id"] if hop else "",incoming_edge_kind=hop["kind"] if hop else "",
                    evidence_confidence=hop["confidence"] if hop else "",timing_status=hop["timing_status"] if hop else "source"))
    for name, items in (("chains",chains),("steps",steps)):
        fields = list(dict.fromkeys(k for item in items for k in item)) if items else ["candidate_id","chain_id","status"]
        write_csv(str(directory/(name+".csv")),fields,items)
    (directory/"chains.md").write_text(presentation.render_markdown(report),encoding="utf-8")
    (directory/"index.html").write_text(presentation.render_html(report),encoding="utf-8")


def load_csv_records(path, *, candidates=False, graph_ids=None):
    integer_fields = {"user_rank","device_id","stream_id","task_id","iteration","block","bucket","observed_start_ns","observed_stop_ns","duration_ns","reference_count","modeled_execution_gain_ns"}
    boolean_fields = {"duration_slow","traversal_truncated","other_backtrace_branches_truncated", "primary_eligible"}
    records=[]
    with Path(path).open(encoding="utf-8-sig",newline="") as stream:
        for row in csv.DictReader(stream):
            if graph_ids is not None and row.get("graph_id") not in graph_ids:
                continue
            for key in integer_fields & row.keys():
                row[key]=int(row[key]) if row[key] else None
            for key in boolean_fields & row.keys():
                if row[key] not in {"True","False",""}:
                    raise ValueError("invalid CSV boolean: "+key)
                row[key]=row[key]=="True"
            for key in ({"affected_wait_graph_ids","evidence_paths","reference_iterations"} if candidates else {"reference_iterations"}) & row.keys():
                if row[key]:
                    try:
                        value=json.loads(row[key])
                    except json.JSONDecodeError:
                        # Older diagnosis CSVs used DictWriter's Python literal representation.
                        value=ast.literal_eval(row[key])
                    if not isinstance(value,dict if key=="evidence_paths" else list):
                        raise ValueError("invalid structured CSV field: "+key)
                    row[key]=value
                else:
                    row[key]=None
            records.append(row)
    return records


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("artifact_dir",type=Path)
    parser.add_argument("-o","--output-dir",type=Path,required=True)
    args=parser.parse_args()
    try:
        directory=args.artifact_dir
        gate=json.loads((directory/"pipeline_result.json").read_text(encoding="utf-8-sig"))
        if gate.get("status")!="passed" or not gate.get("analysis_completed") or gate.get("source_policy_version") not in {4, 5, 6}:
            raise ValueError("source-first export requires a passed source-policy 4/5/6 diagnosis artifact")
        if args.output_dir.exists():
            raise FileExistsError("refusing to overwrite propagation output")
        if gate.get("source_policy_version") == 6:
            entries=load_csv_records(directory/"rolling/root_causes.csv",candidates=True)
            unresolved=[r for r in entries if r.get("diagnosis_category")==UNRESOLVED]
            roots=[r for r in entries if r.get("diagnosis_category") in {INTERNAL, EXTERNAL}]
            primary=next((r["root_id"] for r in roots if r.get("primary_eligible")), None)
        else:
            roots=load_csv_records(directory/"diagnosis_candidates.csv",candidates=True)
            primary=roots[0]["root_id"] if roots else None
            unresolved=[]
        rows=graph.read_graph_artifact_nodes(directory/"dep_graph_nodes.csv")
        edges=graph.read_graph_artifact_edges(directory/"dep_graph_edges.csv")
        path_ids={key for root in roots for path in root["evidence_paths"].values() for key in path}
        needed={root["graph_id"] for root in roots}
        needed.update(key for edge in edges if edge["edge_id"] in path_ids for key in (edge["src"],edge["dst"]))
        tasks=load_csv_records(directory/"rolling/task_comparison.csv",graph_ids=needed)
        report=build_report(rows,edges,roots,tasks,primary_source_candidate_id=primary, unresolved_observations=unresolved)
        export_report(report,args.output_dir)
    except (OSError,ValueError,KeyError,ArithmeticError) as error:
        parser.exit(1,"propagation export failed: "+str(error)+"\n")
    print(json.dumps(report["summary"]))
    return 0


if __name__=="__main__":
    raise SystemExit(main())
