"""Run experimental dual-endpoint backtrace without changing default analyze."""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from contextlib import redirect_stdout
import hashlib
from heapq import heappop, heappush
import json
import os
from pathlib import Path
import sys
from tempfile import TemporaryDirectory

from .endpoint_replay_data import (
    ORDER, add_main_stream, arrival_evidence, comparison, group_events, load_capture,
    local_fact_tables, protocol_evidence, serial_records, stream_table,
)
from .stage_events import StageEvents

NOTIFY = {"local_notify_sync_exact", "direct_notify_sync_exact", "cross_node_notify_sync_observed"}
EVENT = "local_event_sync_exact"
SIGNALS = NOTIFY | {EVENT}
WORK = {"sdma", "reduce_inline", "kernel_aicore", "kernel_aivec", "kernel_mix_aiv", "kernel_mix_aic"}
WAIT = {"event_wait", "notify_wait"}


def possible_last(timings, side):
    key="aligned_start" if side=="arrival" else "aligned_end"
    latest_lower=max(v[key]-v["clock"].estimated_error_ns for v in timings.values())
    return sorted(k for k,v in timings.items() if v[key]+v["clock"].estimated_error_ns>=latest_lower)


def task_controls(nodes, coord):
    samples=defaultdict(lambda:defaultdict(list))
    for gid,r in nodes.items():
        scope=r["_operation_scope"]
        if scope not in coord or r.get("match_status")!="matched" or r.get("_operation_scope_status")!="unique":continue
        kind=r["profiler_task_kind"]
        if kind not in WORK|WAIT or not r.get("algorithm") or not r.get("event"):continue
        c=coord[scope]
        key=(c["group_id"],c["call_site"],c["occurrence"],r["_node_id"],r["_device_id"],r["_user_rank"],
             *(r.get(k) for k in ("algorithm","phase","step","slice","event","semantic","_peer_rank","profiler_size_bytes")),kind)
        samples[key][c["iteration"]].append((gid,r["_stop_ns"]-r["_start_ns"]))
    found={}
    for key,epochs in samples.items():
        for i,curr in epochs.items():
            old=[(k,*epochs[k][0]) for k in range(i-5,i) if len(epochs.get(k,()))==1]
            if len(curr)!=1 or len(old)!=5:continue
            gid,value=curr[0]
            d=comparison(value,[x[2] for x in old],ratio=1.2 if key[-1] in WAIT else 1.5,floor=50_000)
            if d and d["significant"]:
                found[gid]=dict(d,reference_iterations=[x[0] for x in old],reference_graph_ids=[x[1] for x in old],
                                reference_samples_ns=[x[2] for x in old],comparison="unique_same_semantic_position")
    return found


class Backward:
    def __init__(self,nodes,edges,clocks,coord,changes):
        self.nodes=nodes
        self.coord=coord
        self.c=clocks
        self.changes=changes
        self.incoming=defaultdict(list)
        self.times={}
        for e in edges:
            if e["dst"] in nodes and (e["kind"] in SIGNALS or e["kind"]==ORDER):
                self.incoming[e["dst"]].append(e)

    def location(self,g):
        n=self.nodes[g]
        return n["_node_id"],n["_device_id"]

    def time(self,g):
        if g not in self.times:
            n=self.nodes[g]
            m=self.c[self.location(g)]
            self.times[g]=m.map_ns(n["_start_ns"]),m.map_ns(n["_stop_ns"])
        return self.times[g]

    def edge(self,e):
        src,dst=e["src"],e["dst"]
        if src not in self.nodes:return None,"missing_producer_task"
        p,q=self.nodes[src],self.nodes[dst]
        if any(n.get("_subtask_id",-1)>=0 for n in (p,q)):return None,"ffts_timing_not_verified"
        a,b=self.time(src)
        c,d=self.time(dst)
        margin=0 if self.location(src)==self.location(dst) else sum(self.c[x].estimated_error_ns for x in (self.location(src),self.location(dst)))
        k=e["kind"]
        if k==ORDER:
            if e["confidence"]!="observed" or self.location(src)!=self.location(dst) or p["_stream_id"]!=q["_stream_id"] or b>c:
                return None,"unverified_stream_predecessor"
            return dict(causal=True,slack_ns=c-b,error_ns=0),None
        expected="observed" if k=="cross_node_notify_sync_observed" else "exact"
        if k==EVENT:
            # Future producers may export this. A pair must identify the exact
            # process-local Event object and the particular Record generation.
            if (e["confidence"]!="exact" or not e.get("event_context_id") or not e.get("event_id")
                    or type(e.get("event_generation")) is not int or e["event_generation"]<0
                    or self.location(src)!=self.location(dst)
                    or (p["profiler_task_kind"],q["profiler_task_kind"])!=("event_record","event_wait")):
                return None,"missing_shared_event_handle_or_generation"
        elif e["confidence"]!=expected or q["profiler_task_kind"]!="notify_wait":return None,"unverified_notify_identity"
        if b>d+margin:return None,"producer_after_wait_release"
        if b<=c-margin:return dict(causal=False,slack_ns=c-b,error_ns=margin),None
        if margin and (b-c<=margin or d-b<margin):
            return dict(causal=False,slack_ns=0,error_ns=margin),"clock_order_uncertain"
        # This is a bound on visible release/dispatch, not RDMA wire time.
        return dict(causal=True,slack_ns=max(0,d-b-margin),error_ns=margin),None

    def trace(self, seed, iteration, limit=20000):
        if seed is None:
            return dict(boundaries=[dict(reason="missing_exact_endpoint",blocks=True)],hits=[],gates=[],visited=0,paths={})
        best={seed:(True,0)}
        todo=[(False,0,seed)]
        settled=set()
        successor={}
        hits={};gates={};boundaries={};count=0
        def stop(g,reason,blocks):
            key=g,reason
            boundaries[key]=dict(task=g,reason=reason,blocks=blocks or boundaries.get(key,{}).get("blocks",False))
        while todo and count<limit:
            weak,budget,g=heappop(todo)
            blocking=not weak
            if best[g]!=(blocking,budget) or g in settled:continue
            settled.add(g)
            count+=1
            row=self.nodes[g]
            op=self.coord.get(row["_operation_scope"])
            if op is None or op["iteration"]!=iteration:
                stop(g,"outside_same_iteration_dependency_scope",blocking);continue
            kind=row["profiler_task_kind"]
            if g in self.changes:
                hits[g]=dict(graph_id=g,kind=kind,rank=row["_user_rank"],blocking_lineage=blocking,
                             path_slack_and_clock_ns=budget,metrics=self.changes[g])
            links=self.incoming[g]
            signals=[e for e in links if e["kind"] in SIGNALS]
            seq=[e for e in links if e["kind"]==ORDER]
            follow=[]
            early_signal=False
            if kind in WAIT:
                if len(signals)!=1:
                    stop(g,"missing_shared_event_handle_or_generation" if kind=="event_wait" else "missing_unique_notify_producer",blocking)
                    gates[g]=dict(graph_id=g,kind=kind,blocking_lineage=blocking,blocking_slack_ns=budget)
                else:
                    e=signals[0]; proof,error=self.edge(e)
                    if error:
                        stop(g,error,blocking)
                        if proof:
                            follow.append((e,False,proof))
                    else:
                        early_signal=not proof["causal"]
                        follow.append((e,blocking and proof["causal"],proof))
                        gates[g]=dict(graph_id=g,kind=kind,blocking_lineage=blocking,blocking_slack_ns=budget,producer=e["src"],
                                     producer_edge=e["edge_id"],producer_delays_wait=proof["causal"],**proof)
            order_controls=kind not in WAIT or early_signal
            if len(seq)>1:
                stop(g,"ambiguous_stream_predecessors",blocking and order_controls)
            elif len(seq)==1:
                proof,error=self.edge(seq[0])
                if error:stop(g,error,blocking and order_controls)
                else:follow.append((seq[0],blocking and order_controls,proof))
            elif order_controls:
                stop(g,"missing_stream_or_Host_dispatch_predecessor",blocking)
            for e,critical,proof in follow:
                a=e["src"]
                cost=budget+proof["slack_ns"]+proof["error_ns"]
                before=best.get(a)
                if before is not None and (not critical or before[0]) and (before[0]!=critical or before[1]<=cost):continue
                best[a]=(critical,cost)
                successor[a]=(g,e,proof)
                heappush(todo,(not critical,cost,a))
        if todo:stop(seed,"bounded_dependency_search",True)
        def path(g):
            chain=[];seen=set()
            while g!=seed and g in successor and g not in seen:
                seen.add(g)
                nxt,e,t=successor[g]
                chain.append(dict(edge_id=e["edge_id"],kind=e["kind"],confidence=e["confidence"],src=g,dst=nxt,
                                  source_stop_ns=self.time(g)[1],downstream_span_ns=self.time(nxt),**t))
                g=nxt
            return chain if g==seed else []
        return dict(boundaries=list(boundaries.values()),hits=list(hits.values()),gates=list(gates.values()),
                    visited=count,visited_ids=settled,paths=path)


def coverage_event(stage, prior, stream_cache, facts):
    if not (all(stage.get(k) for k in ("statistical","temporal","dependency","mechanism")) and stage.get("ready_start")):return False
    a,b=stage["ready_start"],stage["ready_end"]
    key=(stage["node"].rsplit("/",1)[-1],prior["clock"].device_id,a[2])
    if a[2]!=b[2]:return False
    if key not in stream_cache:stream_cache[key]=stream_table(facts,*key)
    try:
        order=serial_records(stream_cache[key],a[0],b[1])
    except ValueError:
        return False
    stage["serial_order"]=order
    return order["physical_tasks"]>1 and order["largest_gap_ns"]<=100_000


def readiness_context(hits, gates, backward, measured, coordinate, history, paths):
    """Corroborate late peer readiness upstream of a measured ACK Wait."""
    found={}
    for hit in hits:
        gid=hit["graph_id"]
        wait=backward.nodes[gid]
        g=gates.get(gid,{})
        if wait.get("semantic")!="link_rx_ack" or not g.get("producer_delays_wait"):continue
        tx=backward.nodes[g["producer"]]
        if tx.get("semantic")!="link_tx_ack":continue
        scope=tx["_operation_scope"]; rank=tx["_user_rank"]
        c=coordinate[scope]; i=c["iteration"]
        p=measured[rank][scope]
        if not p.get("bound_pair"):continue
        refs=[]
        pos=(c["group_id"],c["call_site"],c["occurrence"])
        for j in range(i-5,i):
            other=measured[rank].get(history[pos].get(j))
            if other and other.get("bound_pair"):refs.append(other["record"][1]-other["api_end"])
        ready=p["record"][1]; mapped=p["clock"].map_ns(ready)
        ack=backward.time(g["producer"])
        readiness=comparison(ready-p["api_end"],refs,ratio=1.05,floor=250_000)
        local_proof=paths(gid)
        if not readiness or not readiness["significant"] or not (mapped<=p["aligned_start"]<=ack[0]<=ack[1]) or not local_proof:continue
        lag=ack[1]-mapped
        if lag>hit["metrics"]["delta_ns"]:continue
        val=dict(scope=scope,bucket=c["call_site"],iteration=i,waiting_rank=wait["_user_rank"],
                 producer_rank=rank,wait_graph_id=gid,producer_graph_id=g["producer"],
                 exact_ack_edge=g["producer_edge"],wait_span_ns=backward.time(gid),ack_span_ns=ack,ready_aligned_ns=mapped,
                 bound_ready_task=list(p["record"]),bound_event_wait=list(p["wait"]),ready_to_ack_done_ns=lag,
                 readiness=readiness,reference_samples_ns=refs,ack_wait_stats=hit["metrics"],
                 path_edges=[e["edge_id"] for e in local_proof],
                 limitation="Event Record/Wait generation not exported; path to target can include context, not unique cause")
        key=scope,rank
        if key not in found or val["ack_wait_stats"]["delta_ns"]>found[key]["ack_wait_stats"]["delta_ns"]:found[key]=val
    return sorted(found.values(),key=lambda e:(e["wait_span_ns"][0],-e["ack_wait_stats"]["delta_ns"]))


def merge_source_events(sources, backward):
    """Share a source across CollOps or join adjacent verified abnormal stages."""
    groups = {}
    for gid in sorted(sources,key=lambda g:(backward.time(g)[0],g)):
        root = gid
        candidates = [e for e in backward.incoming[gid] if e["kind"]==ORDER]
        if len(candidates)==1:
            edge = candidates[0]
            prev = edge["src"]
            if prev in groups and backward.nodes[prev]["_operation_scope"] in backward.coord:
                now = backward.nodes[gid]["_operation_scope"]
                before = backward.nodes[prev]["_operation_scope"]
                proof, error = backward.edge(edge)
                if (not error and proof["slack_ns"]<=100_000 and now in backward.coord
                        and backward.coord[now]["iteration"]==backward.coord[before]["iteration"]):
                    root = groups[prev]
        groups[gid] = root
    events = defaultdict(list)
    for gid, root in groups.items():
        events[root].extend(sources[gid])
    return dict(events)

def analyze(capture, *, stage_report=False):
    """Return evidence on each abnormal opening and completion independently."""
    with TemporaryDirectory(prefix="hccl-endpoints-") as tmp:
        facts, det, rows, edges = load_capture(Path(capture), Path(tmp))
    coord = facts["coordinates"]
    clocks = det["clocks"]
    measured = local_fact_tables(facts, clocks)
    provenance = "rebuilt_execution_graph"
    flags=defaultdict(list)
    arrival_evidence(det["classes"],coord,measured,flags)
    protocol_evidence(det["classes"],coord,rows,edges,clocks,flags)
    nodes,anchors=add_main_stream(rows,edges,measured,facts)
    changes=task_controls(nodes,coord)
    backward=Backward(nodes,edges,clocks,coord,changes)
    event_report=StageEvents(facts,clocks,measured,rows,edges,nodes,backward) if stage_report else None
    history=defaultdict(dict)
    for scope,c in coord.items():history[c["group_id"],c["call_site"],c["occurrence"]][c["iteration"]]=scope
    cache={}; blocks=[]; trusted=defaultdict(list); results=[]
    for op in det["classes"]:
        scope=op["scope"]; epoch=op["iteration"]
        sides=[k for k in ("arrival","tail") if op["metrics"][k]["flagged"]]
        if not sides:continue
        entry=dict(scope=scope,iteration=epoch,bucket=op["site"],axis={},stage_observations=[])
        facts_for_op={r:m[scope] for r,m in measured.items() if scope in m}
        for side in sides:
            endpoint_name="open" if side=="arrival" else "close"
            ranks=possible_last(facts_for_op,side)
            ends=[]
            qualifying=defaultdict(list)
            for rank in ranks:
                source=anchors.get((scope,rank),{}).get(endpoint_name)
                info=backward.trace(source,epoch)
                if event_report:
                    event_report.observe(info,scope,side,rank)
                fun=info["paths"]
                if not callable(fun):fun=lambda g:[]
                gaps=info["boundaries"]
                strict_gaps=[g for g in gaps if g["blocks"]]
                local=[h for h in info["hits"] if h["kind"] in WORK]
                wait=[h for h in info["hits"] if h["kind"] in WAIT]
                earlier=set()
                # A resolved earlier stage on a similar tight path makes dependent
                # slow executions explanatory observations, not new sources.
                for h in local if not strict_gaps else ():
                    trail=fun(h["graph_id"])
                    if h["blocking_lineage"] and h["metrics"]["delta_ns"]>h["path_slack_and_clock_ns"]:
                        earlier.update(e["dst"] for e in trail)
                for h in local if not strict_gaps else ():
                    g=h["graph_id"]
                    path=fun(g)
                    if (strict_gaps or g in earlier or not path or not h["blocking_lineage"]
                            or h["metrics"]["delta_ns"]<=h["path_slack_and_clock_ns"]):continue
                    qualifying[g].append(dict(h,path=path,endpoint=source,endpoint_rank=rank,
                        source_location=backward.location(g),source_span_ns=backward.time(g)))
                if side=="arrival":
                    for f in flags[scope]:
                        if f["stage"]!="compute_readiness" or f.get("rank")!=rank:continue
                        event=facts_for_op[rank].get("wait")
                        gates=[g for g in info["gates"] if g["kind"]=="event_wait" and g["blocking_lineage"] and
                               event and nodes[g["graph_id"]]["_task_id"]==event[3] and nodes[g["graph_id"]]["_start_ns"]==event[0]]
                        if len(gates)!=1 or not coverage_event(f,facts_for_op[rank],cache,facts):continue
                        gid=gates[0]["graph_id"];path=fun(gid)
                        if not path or f["wait"]["delta_ns"]<=gates[0]["blocking_slack_ns"]:continue
                        blocks.append(dict(f,iteration=epoch,scope=scope,bucket=op["site"],serial_verified=True,
                                      blocking_gate=gid,gate_to_open=path,upstream_status="undetermined_missing_shared_event_handle"))
                if side=="tail":
                    for f in flags[scope]:
                        if f["stage"]!="cross_node_protocol" or not all(f.get(x) for x in ("statistical","temporal","dependency","mechanism")):continue
                        gid=f["wait_graph_id"]
                        path=fun(gid)
                        if (path and gid not in earlier and not strict_gaps
                                and f["metrics"]["delta_ns"]>sum(e["slack_ns"]+e["error_ns"] for e in path)):
                            qualifying[gid].append(dict(f,path=path,endpoint=source,endpoint_rank=rank))
                ranked_waits=sorted(wait,key=lambda h:backward.time(h["graph_id"])[0])
                # Keep samples from the beginning and the largest regressions.
                examples={h["graph_id"]:h for h in ranked_waits[:6]+sorted(wait,key=lambda h:-h["metrics"]["delta_ns"])[:6]}
                gate_index={v["graph_id"]:v for v in info["gates"]}
                public_fields=("_node_id","_device_id","_user_rank","_stream_id","_task_id","_operation_scope",
                               "_start_ns","_stop_ns","profiler_task_kind","phase","semantic")
                examples=[dict(h,node={k:nodes[g].get(k) for k in public_fields},
                               path_edges=[e["edge_id"] for e in fun(g)],producer=gate_index.get(g))
                          for g,h in examples.items()]
                phase=readiness_context(wait,gate_index,backward,measured,coord,history,fun)
                h=facts_for_op[rank]; model=h["clock"]
                ends.append(dict(rank=rank,endpoint=source,host_dispatch=dict(hook_entry_ns=model.map_ns(h["hook_entry"]),
                    native_api_start_ns=model.map_ns(h["api_start"]),native_api_return_ns=model.map_ns(h["api_end"]),
                    launch_connection_id=h["launch_connection_id"],proof="bound CANN_API/COMMUNICATION_OP; not a hardware doorbell"),
                    actual_endpoint_ns=facts_for_op[rank]["aligned_start" if side=="arrival" else "aligned_end"],
                    visits=info["visited"],local_anomaly_ids=[h["graph_id"] for h in local],
                    propagation_ids=[h["graph_id"] for h in wait if gate_index.get(h["graph_id"],{}).get("producer_delays_wait")],
                    earlier_waits=examples,peer_readiness_context=phase,boundary_count=len(gaps),boundary_reasons=Counter(x["reason"] for x in gaps),
                    endpoint_blocking_boundaries=strict_gaps[:30]))
            # A single phase must account for every plausible last endpoint.
            qualified={g:v for g,v in qualifying.items() if set(ranks)=={x["endpoint_rank"] for x in v}}
            for g,v in qualified.items():trusted[g].append(dict(scope=scope,side=side,proof=v))
            entry["axis"][side]=dict(ranks=ranks,endpoints=ends,verified_source_graph_ids=list(qualified))
        for f in flags[scope]:
            if f["stage"]=="cross_node_protocol":entry["stage_observations"].append(f)
        results.append(entry)
    grouped=group_events(blocks)
    stages=[dict(stage="compute_readiness_wait",rank=g[0]["rank"],iteration=g[0]["iteration"],
                 scopes=[r["scope"] for r in g],members=g,root_status="undetermined_upstream_Event_identity") for g in grouped]
    data = dict(schema_version=1,run_id=facts["manifest"]["run_id"],graph=provenance,
                op_counts=Counter(e["category"] for e in det["classes"]),
                localized_ops=len({s for e in stages for s in e["scopes"]}|{p["scope"] for ops in trusted.values() for p in ops}),
                supported_stage_events=stages,trusted_source_events=merge_source_events(trusted,backward),results=results)
    if event_report is not None:
        data["stage_report"] = dict(events=event_report.report(), statistical_stage_count=len(event_report.stages))
    return data


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("capture", type=Path, help="existing hccl-diag capture with SDK and clock evidence")
    parser.add_argument("-o", "--output", type=Path, help="new JSON file outside the capture (default: stdout)")
    parser.add_argument("--stage-report", action="store_true", help="also report anomalous stages without a root-cause claim")
    args = parser.parse_args(argv)
    if args.output is not None:
        destination = args.output.resolve()
        capture = args.capture.resolve()
        source = capture.parent if capture.is_file() else capture
        if destination == source or source in destination.parents or destination.exists():
            parser.error("output must be a new file outside the capture")
    try:
        guarding = True

        def check_open(event, params):
            if (not guarding or event!="open" or not params
                    or not isinstance(params[0], (str,bytes,os.PathLike))):
                return
            path = Path(os.fsdecode(params[0]))
            if "private" in path.parts or path.name in {"case.json","evaluation-roce-path.json"}:
                raise PermissionError("diagnosis cannot read experiment labels")

        sys.addaudithook(check_open)
        try:
            with redirect_stdout(sys.stderr):
                result = analyze(args.capture, stage_report=args.stage_report)
        finally:
            guarding = False
        payload = json.dumps(result, sort_keys=True, separators=(",",":"))
        envelope = {"diagnosis": result, "diagnosis_sha256": hashlib.sha256(payload.encode()).hexdigest()}
        if args.output is None:
            print(json.dumps(envelope))
        else:
            with destination.open("x", encoding="utf-8") as stream:
                json.dump(envelope, stream)
                stream.write("\n")
    except (OSError, ValueError) as error:
        parser.exit(2, f"dual-endpoint replay: {error}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
