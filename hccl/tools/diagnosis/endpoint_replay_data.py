"""Read-only inputs and stage evidence for the optional dual-endpoint analysis."""
from __future__ import annotations

from collections import defaultdict, deque
from contextlib import closing
import json
from statistics import median

from .capture_discovery import discover_capture, prepare_capture_identity, read_json
from .clock_alignment import build, models_from_report
from .cross_node_path import _witnesses
from .dependency_model import stable_id
from .multi_node_trace import replay_manifest
from .parse_msprof_db import _readonly_connection, discover_db_files
from .workload_binder import bind_capture, operation_type


ORDER = "direct_stream_order_observed"


def load_capture(source, work):
    capture = prepare_capture_identity(discover_capture(source, work/"discovery"), work/"identity")
    bound = bind_capture(capture, work/"binding", mode="rolling")
    manifest = read_json(bound.manifest)
    clocks = models_from_report(build(manifest))
    if not clocks:
        raise ValueError("dual-endpoint replay requires before/after clock evidence")
    coordinates = {r["operation_scope"]: r for r in bound.coordinates if r["stage"] == "measured"}
    if not coordinates or not bound.preparation_map or not capture.call_logs:
        raise ValueError("dual-endpoint replay requires bound formal iterations and SDK call observations")
    ranks = {(r["node_id"],r["device_id"]): r["user_rank"] for r in manifest["ranks"]}
    facts = dict(manifest=manifest, coordinates=coordinates, ranks=ranks,
                 preparations=read_json(bound.preparation_map)["preparations"])
    classes = collop_metrics(facts, clocks, capture.call_logs)
    live = {}
    _, valid = replay_manifest(bound.manifest, work/"graph", 95, live=live, keep_debug=False)
    if not valid:
        raise ValueError("execution graph did not pass coverage gates")
    original_rows, original_edges = live["graph"]
    rows = [r for r in original_rows if r.get("_operation_scope") in coordinates]
    ids = {r["_graph_id"] for r in rows}
    edges = [e for e in original_edges if (e["src"] in ids and e["dst"] in ids)
             or ("notify_sync" in e["kind"] and (e["src"] in ids or e["dst"] in ids))]
    return facts, dict(classes=classes, clocks=clocks), rows, edges


def collop_metrics(facts, clocks, call_logs):
    manifest, coordinates, ranks = (facts[k] for k in ("manifest", "coordinates", "ranks"))
    run = manifest["run_id"]
    names = {}
    expected = defaultdict(set)
    for op in manifest["operations"]:
        scope = stable_id("op", (run, op["operation_id"]))
        if scope not in coordinates:
            continue
        for member in op["members"]:
            key = tuple(member[k] for k in ("node_id", "device_id", "group_name", "op_name"))
            if key in names:
                raise ValueError("duplicate DB operation identity")
            names[key] = scope
            expected[scope].add(ranks[key[:2]])
    if set(expected) != set(coordinates):
        raise ValueError("missing measured operation members")
    timings, shapes = defaultdict(dict), defaultdict(set)
    seen = set()
    for node in manifest["nodes"]:
        n = node["node_id"]
        for path in discover_db_files(node["msprof_db_dir"]):
            with closing(_readonly_connection(str(path))) as db:
                for dev, group, name, start, stop, kind, dtype, count in db.execute(
                        "SELECT o.deviceId,g.value,n.value,o.startNs,o.endNs,t.value,o.dataType,o.count "
                        "FROM COMMUNICATION_OP o JOIN STRING_IDS g ON g.id=o.groupName "
                        "JOIN STRING_IDS n ON n.id=o.opName JOIN STRING_IDS t ON t.id=o.opType"):
                    key = n, dev, group, name
                    if key not in names:
                        continue
                    if key in seen or stop <= start:
                        raise ValueError("ambiguous DB operation span")
                    seen.add(key)
                    scope, model = names[key], clocks[run+"/"+n, dev]
                    timings[scope][ranks[n,dev]] = model.map_ns(start), model.map_ns(stop)
                    shapes[scope].add((operation_type(kind), dtype, count))
    if seen != set(names):
        raise ValueError("missing DB operation spans")
    host = {}
    identity = ("group_id", "iteration", "call_site", "occurrence")
    for path in call_logs:
        with path.open(encoding="utf-8") as stream:
            for line in stream:
                if not line.strip():
                    continue
                row = json.loads(line)
                if row["event"] != "call" or row["stage"] != "measured":
                    continue
                key = tuple(row[k] for k in (*identity, "user_rank"))
                if key in host:
                    raise ValueError("duplicate Host observation for bound collective")
                model = clocks[run+"/"+row["node_id"], row["device_id"]]
                host[key] = model.map_ns(row["before"]["raw_ns"]+model.profiler_to_raw_offset_ns)
    history = defaultdict(lambda: deque(maxlen=15))
    error = 2*max(m.estimated_error_ns for m in clocks.values())
    classes = []
    for scope, c in sorted(coordinates.items(),key=lambda v:(v[1]["iteration"],min(t[0] for t in timings[v[0]].values()))):
        members = timings[scope]
        if set(members) != expected[scope] or len(shapes[scope]) != 1:
            raise ValueError("incomplete or inconsistent collective")
        position = (c["group_id"], c["call_site"], c["occurrence"], next(iter(shapes[scope])))
        last = max(members,key=lambda r:members[r][0])
        first = min(members,key=lambda r:members[r][0])
        earliest, latest = members[first][0], members[last][0]
        spans = dict(arrival=latest-earliest, tail=max(t[1] for t in members.values())-latest)
        metrics = {}
        for axis, value in spans.items():
            prior = history[position,axis]
            center = median(prior) if len(prior)>=5 else None
            flagged = False
            if center is not None:
                p90 = sorted(prior)[(9*len(prior)+9)//10-1]
                mad = median(abs(p-center) for p in prior)
                flagged = (value>p90 and value-center>=max(100_000,3*mad,2*error)
                           and (value>=2*center if axis=="arrival" else 60*value>=100*center))
            if not flagged:
                prior.append(value)
            metrics[axis] = dict(ns=value, reference_ns=center, flagged=flagged)
        axes = [axis for axis in metrics if metrics[axis]["flagged"]]
        category = "both" if len(axes)==2 else axes[0] if axes else (
            "normal" if all(v["reference_ns"] is not None for v in metrics.values()) else "insufficient")
        result = dict(scope=scope, iteration=c["iteration"], site=c["call_site"], category=category,
                      last_rank=last, metrics=metrics, rank_spans=members)
        if metrics["arrival"]["flagged"]:
            key = tuple(c[k] for k in identity)
            a,b = host.get((*key,first)), host.get((*key,last))
            if a is not None and b is not None:
                host_delta = b-a
                residual = spans["arrival"]-host_delta
                result["arrival_evidence"] = (
                    "mostly_present_at_host_submit" if host_delta>=.7*spans["arrival"]+error else
                    "mostly_after_host_submit" if residual>=.7*spans["arrival"]+error else "mixed_or_unresolved")
        classes.append(result)
    return classes

def comparison(value, history, *, ratio=1.5, floor=100_000):
    if len(history) < 5 or any(v < 0 for v in history):
        return None
    ref = median(history)
    mad = median(abs(v - ref) for v in history)
    delta = value - ref
    return dict(actual_ns=value, reference_ns=ref, delta_ns=delta,
                significant=value >= ratio * ref and delta >= max(floor, 3 * mad))

def local_fact_tables(facts, clocks):
    from hccl.tools.diagnosis.dependency_model import stable_id

    inputs = facts["manifest"]
    run = inputs["run_id"]
    preparations = {(x["operation_scope"], x["user_rank"]): x for x in facts["preparations"]}
    by_device = defaultdict(dict)
    for o in inputs["operations"]:
        scope = stable_id("op", (run, o["operation_id"]))
        if scope not in facts["coordinates"]:
            continue
        for v in o["members"]:
            by_device[v["node_id"], v["device_id"]][v["group_name"], v["op_name"]] = scope
    measurements = defaultdict(dict)
    for node in inputs["nodes"]:
        name = node["node_id"]
        for path in discover_db_files(node["msprof_db_dir"]):
            with closing(_readonly_connection(str(path))) as db:
                dev, = db.execute("SELECT deviceId FROM TASK LIMIT 1").fetchone()
                rank = facts["ranks"][name, dev]
                clock = clocks[run + "/" + name, dev]
                pairs = by_device[name, dev]
                records = [tuple(row) for row in db.execute("SELECT t.startNs,t.endNs,t.streamId,t.taskId,s.value,t.connectionId "
                    "FROM TASK t JOIN STRING_IDS s ON t.taskType=s.id WHERE s.value IN "
                    "('EVENT_RECORD','EVENT_WAIT','NOTIFY_RECORD','NOTIFY_WAIT') ORDER BY t.startNs,t.taskId")]
                tasks, streams = defaultdict(list), defaultdict(list)
                for rec in records:
                    tasks[rec[5], rec[4]].append(rec)
                    streams[rec[2]].append(rec)
                stream_ord = {(r[2], r[3], r[0]): i for stream in streams.values() for i, r in enumerate(stream)}
                launches = [tuple(row) for row in db.execute(
                    "SELECT a.startNs,a.endNs,a.globalTid,a.connectionId,n.value FROM CANN_API a "
                    "JOIN STRING_IDS n ON a.name=n.id WHERE n.value IN ('aclrtRecordEvent','aclrtStreamWaitEvent') "
                    "OR n.value LIKE 'hcom%' ORDER BY a.startNs")]
                native = defaultdict(set)
                for s, e, tid, _, api_name in launches:
                    if api_name.lower().startswith("hcom"):
                        native[s, e].add(tid)
                api_by_thread = defaultdict(list)
                for row in launches:
                    api_by_thread[row[2]].append(row)
                for start, end, conn, group, op in db.execute("SELECT o.startNs,o.endNs,o.connectionId,g.value,n.value FROM COMMUNICATION_OP o "
                        "JOIN STRING_IDS g ON g.id=o.groupName JOIN STRING_IDS n ON n.id=o.opName"):
                    scope = pairs.get((group, op))
                    if scope is None:
                        continue
                    p = preparations[scope, rank]
                    launch = tasks[conn, "NOTIFY_RECORD"]
                    begins = [r for r in launch if r[0] == start]
                    d = dict(begin=start, end=end, api_end=p["api_stop_ns"], aligned_start=clock.map_ns(start),
                             aligned_end=clock.map_ns(end), clock=clock, scope=scope,
                             api_start=p["api_start_ns"], hook_entry=p["stop_ns"], launch_connection_id=conn)
                    if scope in measurements[rank]:
                        raise ValueError("duplicate bound operation")
                    measurements[rank][scope] = d
                    tids = native[p["api_start_ns"], p["api_stop_ns"]]
                    if len(begins)!=1 or len(tids)!=1:
                        continue
                    begin = begins[0]
                    api = [r for r in api_by_thread[next(iter(tids))] if p["stop_ns"]<=r[0]<=r[1]<=p["api_start_ns"]]
                    evt = [tasks[c, "EVENT_RECORD" if typ=="aclrtRecordEvent" else "EVENT_WAIT"]
                           for _,_,_,c,typ in api if typ in {"aclrtRecordEvent","aclrtStreamWaitEvent"}]
                    if len(evt)!=2 or any(len(x)!=1 for x in evt):
                        continue
                    record, wait = evt[0][0],evt[1][0]
                    if not (record[4]=="EVENT_RECORD" and wait[4]=="EVENT_WAIT" and record[2]!=wait[2]==begin[2]):
                        continue
                    j = stream_ord[begin[2],begin[3],begin[0]]
                    chain = streams[begin[2]]
                    if not j or chain[j-1]!=wait or wait[1]>start or start-wait[1]>5_000:
                        continue
                    d.update(record=record, wait=wait, previous_notify=next((r for r in reversed(chain[max(0,j-8):j-1]) if r[4]=="NOTIFY_WAIT"),None),
                             bound_pair=abs(wait[1]-max(wait[0],record[1]))<=5_000)
    return measurements


def recent(scopes, current):
    return [scopes[i] for i in range(current-5,current) if i in scopes]


def arrival_evidence(ops, loc, measured, flags):
    """Follow device-ready and previous main-stream work; do not infer an Event handle."""
    history = defaultdict(dict)
    for s,c in loc.items():
        history[c["group_id"],c["call_site"],c["occurrence"]][c["iteration"]] = s
    all_spans = defaultdict(list)
    for rank, supports in measured.items():
        for s,x in supports.items():
            if "record" in x:
                c=loc[s]
                all_spans[rank,c["iteration"],x["record"][2]].append(x)
    predecessors = {}
    for values in all_spans.values():
        previous = None
        for x in sorted(values,key=lambda x:x["record"][0]):
            if previous and previous["end"]<=x["wait"][0] and previous["wait"][2]==x["wait"][2]:
                predecessors[x["scope"],x["clock"].node_id,x["clock"].device_id]=previous
            previous=x
    for event in ops:
        if not event["metrics"]["arrival"]["flagged"]:
            continue
        s = event["scope"]
        coord = loc[s]
        rank = event["last_rank"]
        x=measured[rank][s]
        if not x.get("bound_pair"):
            continue
        rs, re, stream, record_id,*_ = x["record"]
        ws, we, comm_stream, wait_id,*_ = x["wait"]
        older = recent(history[coord["group_id"],coord["call_site"],coord["occurrence"]],coord["iteration"])
        old = [sample for a in older if (sample := measured[rank].get(a)) and sample.get("bound_pair")]
        prev = predecessors.get((s,x["clock"].node_id,x["clock"].device_id))
        older_prev=[predecessors.get((a["scope"],x["clock"].node_id,x["clock"].device_id)) for a in old]
        slack = 5_000
        factor = dict(ratio=1.5, floor=max(100_000,x["clock"].estimated_error_ns*2))
        common = dict(axis="arrival", rank=rank, target_scope=s, node=x["clock"].node_id,
                      uncertainty_ns=x["clock"].estimated_error_ns)
        wait_growth=comparison(we-ws,[p["wait"][1]-p["wait"][0] for p in old],**factor)
        if prev and all(older_prev):
            endprev=prev["record"][1]
            ready=comparison(re-endprev,[q["record"][1]-p["record"][1] for q,p in zip(old,older_prev)],**factor)
            # Sources before the target's physical main-stream start only.
            if ready and (ready["significant"] or (wait_growth and wait_growth["significant"])):
                flags[s].append(dict(common, stage="compute_readiness", start_ns=x["clock"].map_ns(endprev),
                    stop_ns=x["clock"].map_ns(re), statistical=ready["significant"],
                    temporal=endprev<re<=we<=x["begin"], dependency=x["bound_pair"],
                    mechanism=(event.get("arrival_evidence")=="mostly_after_host_submit" and wait_growth is not None
                               and wait_growth["significant"] and we-ws>slack
                               and ready["delta_ns"]>=0.5*event["metrics"]["arrival"]["ns"]),
                    metrics=ready, wait=wait_growth, event_pair="api_and_timing_corroborated_no_event_handle",
                    streams=dict(compute=stream,communication=comm_stream), event_tasks=[record_id,wait_id],
                    ready_start=list(prev["record"]),ready_end=list(x["record"]),
                    stage_references=[dict(iteration=loc[q["scope"]]["iteration"],scope=q["scope"],
                        ready_ns=q["record"][1]-p["record"][1],wait_ns=q["wait"][1]-q["wait"][0],
                        ready_start=list(p["record"]),ready_end=list(q["record"])) for q,p in zip(old,older_prev)]))
            pred_growth=comparison(prev["end"]-prev["begin"], [p["end"]-p["begin"] for p in older_prev],**factor)
            if pred_growth and pred_growth["significant"]:
                notify=x["previous_notify"]
                preceding=notify and notify[0]>=prev["begin"] and abs(notify[1]-prev["end"])<=slack
                flags[s].append(dict(common,stage="preceding_collective",start_ns=prev["aligned_start"],
                    stop_ns=prev["aligned_end"], statistical=True,
                    temporal=prev["end"]<=ws and prev["end"]+slack>=re,
                    dependency=bool(preceding and ws-prev["end"]<=slack),
                    mechanism=bool(pred_growth["delta_ns"]>=0.5*event["metrics"]["arrival"]["ns"] and we-ws<=slack),
                    metrics=pred_growth, preceding_scope=prev["scope"], previous_notify_task=notify[3] if notify else None))
            prefix = comparison(ws-x["api_end"], [q["wait"][0]-q["api_end"] for q in old],
                                ratio=1.1, floor=500_000)
            if prefix and prefix["significant"]:
                flags[s].append(dict(common,stage="preceding_progress",start_ns=x["clock"].map_ns(x["api_end"]),
                    stop_ns=x["clock"].map_ns(ws), statistical=True, temporal=x["api_end"]<=ws,
                    dependency=True,mechanism=False,metrics=prefix,
                    wait=wait_growth,preceding_scope=prev["scope"],
                    reason="mixed prefix of same-stream previous work; does not identify the blocking dependency"))
        if wait_growth and wait_growth["significant"] and not any(f["stage"]=="compute_readiness" for f in flags[s]):
            flags[s].append(dict(common,stage="compute_readiness",start_ns=x["clock"].map_ns(ws),
                    stop_ns=x["clock"].map_ns(we),statistical=True,temporal=we<=x["begin"],dependency=x["bound_pair"],
                    mechanism=False, metrics=wait_growth, reason="waiting increased but no comparable ready-to-ready interval"))

def stream_table(facts, node, device, stream):
    spec=next(n for n in facts["manifest"]["nodes"] if n["node_id"]==node)
    for path in discover_db_files(spec["msprof_db_dir"]):
        with closing(_readonly_connection(str(path))) as db:
            actual = db.execute("SELECT deviceId FROM TASK LIMIT 1").fetchone()
            if actual is None or actual[0] != device:
                continue
            return [tuple(row) for row in db.execute(
                "SELECT t.startNs,t.endNs,t.streamId,t.taskId,s.value,t.connectionId FROM TASK t "
                "JOIN STRING_IDS s ON s.id=t.taskType WHERE t.streamId=? ORDER BY t.taskId,t.startNs",(stream,))]
    raise ValueError("missing device DB for physical stream")


def serial_records(table, begin, end):
    groups=defaultdict(list)
    for r in table:
        if begin<=r[0]<=r[1]<=end:
            groups[r[2],r[3],r[5]].append(r)
    ordered=[]
    for entries in groups.values():
        # Some mixed kernels expose a nested kernel measurement for the
        # same submitted stream/task/connection. Only use a recorded outer
        # interval, never synthesize a dependency edge from the nesting.
        outer=[r for r in entries if all(r[0]<=x[0]<=x[1]<=r[1] for x in entries)]
        unique={(r[0],r[1],r[2],r[3],r[5]) for r in outer}
        if len(unique)!=1:raise ValueError("ambiguous physical task bounds")
        ordered.append((outer[0],len(entries)-1))
    ordered.sort(key=lambda x:(x[0][0],x[0][3]))
    if not ordered or ordered[0][0][0]!=begin or ordered[-1][0][1]!=end:
        raise ValueError("missing physical endpoints")
    gaps=[b[0][0]-a[0][1] for a,b in zip(ordered,ordered[1:])]
    if any(g<0 for g in gaps):raise ValueError("overlapping distinct physical tasks on compute stream")
    return dict(physical_tasks=len(ordered), nested_timing_rows=sum(n for _,n in ordered),
                gap_sum_ns=sum(gaps), largest_gap_ns=max(gaps,default=0))

def add_main_stream(rows, edges, measured, facts):
    by_id={r["_graph_id"]:r for r in rows}
    starts=defaultdict(list)
    finishes=defaultdict(list)
    physical=defaultdict(list)
    for r in rows:
        s,k=r["_operation_scope"],r["_user_rank"]
        stamp=(k,r["_stream_id"],r["_task_id"],r["_start_ns"],r["_stop_ns"])
        physical[stamp].append(r["_graph_id"])
        x=measured.get(k,{}).get(s)
        if not x:continue
        if r["profiler_task_kind"]=="notify_record" and r["_start_ns"]==x["begin"]:
            starts[s,k].append(r["_graph_id"])
        if r["profiler_task_kind"]=="notify_wait" and r["_stop_ns"]==x["end"]:
            finishes[s,k].append(r["_graph_id"])
    anchors={}
    bins=defaultdict(list)
    for (s,k),a in starts.items():
        if len(a)!=1:continue
        start=by_id[a[0]]
        stream=start["_stream_id"]
        end=[x for x in finishes[s,k] if by_id[x]["_stream_id"]==stream]
        anchors[s,k]=dict(open=a[0],close=end[0] if len(end)==1 else None)
        bins[k,start["_node_id"],start["_device_id"],stream].append((s,start,end))
    existing={(e["src"],e["dst"],e["kind"]) for e in edges}
    for (rank,node,device,stream),parts in bins.items():
        raw=stream_table(facts,node.rsplit("/",1)[-1],device,stream)
        chunks=sorted(set(raw),key=lambda t:(t[0],t[3],t[1]))
        where=defaultdict(list)
        for i,t in enumerate(chunks):
            where[t[2],t[3],t[0],t[1]].append(i)
        def locate(r):
            key=(r["_stream_id"],r["_task_id"],r["_start_ns"],r["_stop_ns"])
            values=where[key]
            return values[0] if len(values)==1 else None
        def identity(t,s):
            a,b,st,task,kind,conn=t
            key=rank,st,task,a,b
            values=physical[key]
            if len(values)>1:return None
            if values:return values[0]
            if kind not in {"EVENT_WAIT","EVENT_RECORD"}:return None
            mark=f"raw:{node}:{device}:{st}:{task}:{a}:{conn}"
            by_id[mark]=dict(_graph_id=mark,_operation_scope=s,_user_rank=rank,_node_id=node,_device_id=device,
                             _stream_id=st,_task_id=task,_start_ns=a,_stop_ns=b,_subtask_id=-1,
                             profiler_task_kind=kind.lower(),raw_connection_id=conn)
            return mark
        previous=None
        for s,start,ends in sorted(parts,key=lambda p:p[1]["_start_ns"]):
            end=by_id[ends[0]] if len(ends)==1 else None
            j=locate(start)
            if j is None:
                previous=end
                continue
            old=locate(previous) if previous is not None else None
            # The capture contains the exact API-bound next EventWait even if
            # the previous completed operation is outside the selected graph.
            obs=measured[rank][s].get("wait")
            k=j
            if old is not None and 0<j-old<=32:k=old
            elif obs and j and chunks[j-1][:4]==obs[:4]:k=j-1
            seq=chunks[k:j+1]
            if all(a[1]<=b[0] and a[0]<b[0] for a,b in zip(seq,seq[1:])):
                ids=[identity(t,s) for t in seq]
                if all(ids):
                    for a,b in zip(ids,ids[1:]):
                        if (a,b,ORDER) not in existing:
                            edges.append(dict(src=a,dst=b,kind=ORDER,confidence="observed",
                                edge_id=f"raw-order:{a}:{b}",
                                evidence="adjacent tasks in the full raw device main stream"))
                            existing.add((a,b,ORDER))
            previous=end
    return by_id,anchors

def group_events(candidates):
    """Group only abnormal, verified serial intervals sharing a real milestone."""
    buckets=defaultdict(list)
    events=[]
    for r in candidates:
        if not r["metrics"]["significant"]:
            continue
        if not (r["stage"]=="compute_readiness" and r.get("serial_verified") and
                (r.get("wait") or {}).get("significant")):
            events.append([r])
            continue
        key=(r["node"],r["rank"],r["iteration"],r["streams"]["compute"],r["streams"]["communication"])
        buckets[key].append(r)
    for records in buckets.values():
        group=[]
        for r in sorted(records,key=lambda x:x["start_ns"]):
            if group and not (group[-1]["ready_end"]==r["ready_start"] and group[-1]["stop_ns"]==r["start_ns"]):
                events.append(group)
                group=[]
            group.append(r)
        if group:events.append(group)
    return events

def protocol_evidence(ops, loc, rows, edges, clocks, flags):

    triggered={e["scope"]:e for e in ops if e["category"] in {"arrival","tail","both"}}
    def interval(r):return r["_start_ns"],r["_stop_ns"]
    def clock(r):return clocks[r["_node_id"],r["_device_id"]]
    def position(r):
        c=loc[r["_operation_scope"]]
        return c["group_id"],c["call_site"],c["occurrence"]
    def epoch(r):return loc[r["_operation_scope"]]["iteration"]

    paths=defaultdict(lambda:defaultdict(list))
    for tx, ready, ack, done, path in _witnesses(rows,edges):
        scope=tx["_operation_scope"]
        a,b=clock(tx),clock(done)
        uncertainty=a.estimated_error_ns+b.estimated_error_ns+2
        send_start,posted=map(a.map_ns,interval(tx))
        ready_start=b.map_ns(interval(ready)[0]); received=b.map_ns(interval(done)[1])
        pre=interval(tx)[0]-interval(ack)[1]
        valid=ready_start<=send_start+uncertainty and pre>=0 and send_start<=posted<received
        receiver_local=interval(done)[1]-interval(ready)[0]
        if receiver_local<=0:continue
        key=(position(tx),tx["_user_rank"],done["_user_rank"],tx["phase"],tx["step"],tx["slice"],tx["profiler_size_bytes"],done["semantic"])
        paths[key][epoch(tx)].append((scope,posted,received,pre,interval(done)[1]-interval(done)[0],uncertainty,
                                      tx,done,path,valid,receiver_local,ready_start-send_start,ready_start))
    for group in paths.values():
        for i,entries in group.items():
            if len(entries)!=1:continue
            scope,posted,received,pre,wait,u,tx,done,path,valid,receiver_local,ready_skew,ready_start=entries[0]
            event=triggered.get(scope)
            if not event or not event["metrics"]["tail"]["flagged"]:continue
            refs=[group[j][0] for j in range(i-5,i) if len(group.get(j,()))==1]
            clock_refs=[r for r in refs if r[9]]
            detail=comparison(received-posted,[r[2]-r[1] for r in clock_refs],floor=max(100_000,u*2))
            receiver=comparison(receiver_local,[r[10] for r in refs])
            if not ((detail and detail["significant"]) or (receiver and receiver["significant"])):continue
            ready=comparison(pre,[r[3] for r in clock_refs]); wake=comparison(wait,[r[4] for r in refs],ratio=1.2)
            excess=event["metrics"]["tail"]["ns"]-event["metrics"]["tail"]["reference_ns"]
            tail_start=max(a for a,b in event["rank_spans"].values()); last_end=max(b for a,b in event["rank_spans"].values())
            post_anomalous=bool(detail and detail["significant"])
            flags[scope].append(dict(stage="cross_node_protocol",axis="tail",start_ns=posted if post_anomalous else ready_start,stop_ns=received,
                uncertainty_ns=u,statistical=True,temporal=valid and posted<received<=last_end+u and received>tail_start,
                dependency=True,mechanism=bool(valid and detail and detail["significant"] and ready and not ready["significant"] and
                wake and wake["significant"] and detail["delta_ns"]>=max(u,0.5*excess)),
                metrics=detail if post_anomalous else receiver,
                interval_basis="submission_end_to_data_notification" if post_anomalous else "receiver_local_ready_to_data_notification",
                receiver_interval=receiver,post_submission_interval=detail,comparable_cross_clock_refs=len(clock_refs),
                receiver_ready_minus_submit_ns=ready_skew,phase=tx["phase"],step=tx["step"],
                sender_rank=tx["_user_rank"],sender_node_id=tx["_node_id"],receiver_rank=done["_user_rank"],
                payload_graph_id=tx["_graph_id"],wait_graph_id=done["_graph_id"],edge_ids=[e["edge_id"] for e in path]))
