"""Report measured anomalous stages without claiming a physical root cause."""
from __future__ import annotations

from collections import defaultdict
from statistics import median

from .cross_node_path import _witnesses
from .endpoint_replay_data import ORDER, serial_records, stream_table


MIN_GROWTH_NS = 450_000
STRONG_GROWTH_NS = 1_500_000
SERIAL_GAP_NS = 100_000
KINDS = {"sdma", "reduce_inline", "kernel_aicore", "kernel_aivec",
         "kernel_mix_aiv", "kernel_mix_aic", "notify_wait"}


def statistics(value, references):
    if len(references) != 5:
        return None
    samples = [r["duration_ns"] for r in references]
    center = median(samples)
    mad = median(abs(s-center) for s in samples)
    high = max(samples)
    delta = value-center
    if not (value >= 1.3*center and delta >= max(MIN_GROWTH_NS, 6*mad)
            and value-high >= max(MIN_GROWTH_NS//3, 2*mad)):
        return None
    strong = (value >= 1.8*center and delta >= max(STRONG_GROWTH_NS, 8*mad)
              and value-high >= STRONG_GROWTH_NS//3)
    return dict(current_ns=value, median_ns=center, mad_ns=mad, historical_max_ns=high,
                delta_ns=delta, ratio=value/center if center>0 else None, strong=strong,
                references=references)


def stage_position(c):
    return c["group_id"], c["call_site"], c["occurrence"]


def temporal_status(a, b, uncertainty_ns):
    """Positive intersection, with a conservative relative clock error budget."""
    if (uncertainty_ns is None or a[1] <= a[0] or b[1] <= b[0]):
        return "undetermined"
    margin = min(a[1]-b[0], b[1]-a[0])
    if margin > uncertainty_ns:
        return "definite"
    return "possible" if margin+uncertainty_ns > 0 else "disjoint"


class StageEvents:
    def __init__(self, facts, clocks, measured, rows, edges, nodes, backward):
        self.facts, self.clocks, self.nodes = facts, clocks, nodes
        self.backward = backward
        self.coordinates = facts["coordinates"]
        self.ordinal = {}
        self.stages, self.by_anchor = {}, defaultdict(list)
        self.links = defaultdict(dict)
        self._tasks(rows)
        self._readiness(measured)
        self._protocol(rows, edges)
        self._link_stages(edges)

    def _stage(self, kind, scope, serial, node, device, rank, a, b, *, anchor=None, **evidence):
        c = self.coordinates[scope]
        return dict(kind=kind, scope=scope, iteration=c["iteration"], bucket=c["call_site"],
                    node_id=node, device_id=device, rank=rank, serial=serial, local_span_ns=(a,b),
                    anchor=anchor, evidence=evidence)

    def _register(self, cohorts):
        for group in cohorts.values():
            for epoch, current in sorted(group.items()):
                if len(current)!=1:
                    continue
                s = current[0]
                a,b = s["local_span_ns"]
                past = [group[i][0] for i in range(epoch-5,epoch) if len(group.get(i,()))==1]
                samples = [dict(iteration=p["iteration"], graph_id=p["anchor"], scope=p["scope"],
                                interval_ns=p["local_span_ns"], duration_ns=p["local_span_ns"][1]-p["local_span_ns"][0])
                           for p in past]
                metrics = statistics(b-a, samples)
                if not metrics:
                    continue
                clock = self.clocks[s["node_id"],s["device_id"]]
                s.update(statistics=metrics, interval_ns=(clock.map_ns(a),clock.map_ns(b)),
                         uncertainty_ns=clock.estimated_error_ns, downstream=[])
                seq = len(self.stages)
                self.stages[seq] = s
                if s["anchor"] is not None:
                    self.by_anchor[s["anchor"]].append(seq)

    def _tasks(self, rows):
        cohorts = defaultdict(lambda:defaultdict(list))
        for r in rows:
            kind, scope = r["profiler_task_kind"], r["_operation_scope"]
            if (kind not in KINDS or r.get("match_status")!="matched" or
                    r.get("_operation_scope_status")!="unique" or not r.get("algorithm") or not r.get("event")):
                continue
            n,d,k,st = (r[f"_{key}"] for key in ("node_id","device_id","user_rank","stream_id"))
            c = self.coordinates[scope]
            key = (*stage_position(c), n,d,k,kind,
                   *(r.get(x) for x in ("algorithm","phase","step","slice","event","semantic","_peer_rank","profiler_size_bytes")))
            s = self._stage("notify_wait" if kind=="notify_wait" else "task_execution",
                scope, st, n,d,k,r["_start_ns"],r["_stop_ns"],anchor=r["_graph_id"],
                task_kind=kind, task_id=r["_task_id"], stream_id=st, semantic=r.get("semantic"))
            if s["local_span_ns"][1]>s["local_span_ns"][0]:
                cohorts[key][c["iteration"]].append(s)
        self._register(cohorts)

    def _readiness(self, measured):
        candidates = defaultdict(lambda:defaultdict(list))
        actual = {(r["_node_id"],r["_device_id"],r["_stream_id"],r["_task_id"],r["_start_ns"],r["_stop_ns"]):gid
                  for gid,r in self.nodes.items() if r["profiler_task_kind"]=="event_wait"}
        sequences = defaultdict(list)
        for rank, ops in measured.items():
            for scope, m in ops.items():
                if not m.get("bound_pair"):
                    continue
                c = self.coordinates[scope]
                n,d = m["clock"].node_id,m["clock"].device_id
                record,wait = m["record"],m["wait"]
                a,b,st,task,*_ = wait
                anchor = actual.get((n,d,st,task,a,b))
                key = (*stage_position(c),n,d,rank,"event_wait")
                candidates[key][c["iteration"]].append(self._stage(
                    "event_wait",scope,st,n,d,rank,a,b,anchor=anchor,
                    runtime_connection_id=wait[5],task_id=task,stream_id=st,
                    pair_status="host_api_and_device_timing_only"))
                sequences[n,d,rank,c["iteration"],record[2]].append((scope,m,anchor))
        for (node,device,rank,epoch,stream), members in sequences.items():
            ordered = sorted(members,key=lambda v:(v[1]["record"][0],v[0]))
            for (previous,pre,_), (scope,cur,anchor) in zip(ordered,ordered[1:]):
                a,b = pre["record"],cur["record"]
                if a[1]>=b[1] or pre["end"]>cur["wait"][0]:
                    continue
                c,p = self.coordinates[scope],self.coordinates[previous]
                key = (*stage_position(c),*stage_position(p),node,device,rank,"compute_readiness")
                candidates[key][epoch].append(self._stage(
                    "compute_readiness",scope,stream,node,device,rank,a[1],b[1],anchor=anchor,
                    ready_start=a,ready_end=b,event_wait=cur["wait"],stream_id=stream,
                    pair_status="host_api_and_device_timing_only"))
        old = set(self.stages)
        self._register(candidates)
        streams = {}
        for seq in set(self.stages)-old:
            s = self.stages[seq]
            if s["kind"] != "compute_readiness":
                continue
            key = s["node_id"].rsplit("/",1)[-1],s["device_id"],s["serial"]
            if key not in streams:
                streams[key] = stream_table(self.facts,*key)
            a,b = s["evidence"]["ready_start"],s["evidence"]["ready_end"]
            try:
                serial = serial_records(streams[key],a[0],b[1])
            except ValueError:
                continue
            if serial["physical_tasks"]>1 and serial["largest_gap_ns"]<=SERIAL_GAP_NS:
                s["evidence"]["serial_order"] = serial

    def _protocol(self, rows, edges):
        cohorts = defaultdict(lambda:defaultdict(list))
        for tx,ready,_,done,path in _witnesses(rows,edges):
            scope = done["_operation_scope"]
            c = self.coordinates[scope]
            a,b = ready["_start_ns"],done["_stop_ns"]
            if b<=a:
                continue
            n,d,r,st = (done[f"_{key}"] for key in ("node_id","device_id","user_rank","stream_id"))
            peer = dict(node_id=tx["_node_id"],device_id=tx["_device_id"],rank=tx["_user_rank"])
            key = (*stage_position(c),n,d,r,tx["_user_rank"],tx["phase"],tx["step"],tx["slice"],
                   tx["profiler_size_bytes"],done["semantic"])
            cohorts[key][c["iteration"]].append(self._stage(
                "protocol_receive",scope,st,n,d,r,a,b,anchor=done["_graph_id"],
                peer=peer,phase=tx["phase"],receive_wait=done["_graph_id"],
                ready=ready["_graph_id"],edge_ids=[e["edge_id"] for e in path],
                interval_basis="receiver_local_ready_to_data_notification"))
        self._register(cohorts)

    def _link(self, a, b, kind, evidence):
        x,y = self.stages[a],self.stages[b]
        loc = lambda s:(s["node_id"],s["device_id"],s["rank"],s["iteration"])
        if a!=b and loc(x)==loc(y):
            self.links[a][b] = self.links[b][a] = dict(kind=kind, evidence=evidence)

    def _link_stages(self, edges):
        compute = defaultdict(list)
        for k,s in self.stages.items():
            if s["kind"]=="compute_readiness" and "serial_order" in s["evidence"]:
                compute[s["node_id"],s["device_id"],s["rank"],s["iteration"],s["serial"]].append(k)
        for group in compute.values():
            group.sort(key=lambda k:self.stages[k]["local_span_ns"])
            for a,b in zip(group,group[1:]):
                x,y = (self.stages[k]["evidence"] for k in (a,b))
                if x["ready_end"]==y["ready_start"]:
                    self._link(a,b,"shared_physical_compute_record",x["ready_end"])
        for parents in self.by_anchor.values():
            for i,a in enumerate(parents):
                for b in parents[i+1:]:
                    kinds = {self.stages[x]["kind"] for x in (a,b)}
                    if kinds=={"protocol_receive","notify_wait"}:
                        self._link(a,b,"shared_observed_receive_completion",self.stages[a]["anchor"])
        for e in edges:
            a,b = e["src"],e["dst"]
            if e["kind"]!=ORDER or not self.by_anchor.get(a) or not self.by_anchor.get(b):
                continue
            proof,error = self.backward.edge(e)
            if error or proof["slack_ns"]>SERIAL_GAP_NS:
                continue
            for x in self.by_anchor[a]:
                for y in self.by_anchor[b]:
                    if {self.stages[z]["kind"] for z in (x,y)} & {"compute_readiness","protocol_receive"}:
                        continue
                    if self.stages[x]["local_span_ns"][1]<=self.stages[y]["local_span_ns"][0]:
                        self._link(x,y,"adjacent_physical_stream_tasks",e["edge_id"])

    def observe(self, info, scope, side, rank):
        paths = info["paths"]
        if not callable(paths):
            return
        for gid in self.by_anchor.keys() & info["visited_ids"]:
            path = paths(gid)
            if not all(e["causal"] for e in path):
                continue
            budget = sum(e["slack_ns"]+e["error_ns"] for e in path)
            for key in self.by_anchor[gid]:
                s = self.stages[key]
                if budget>=s["statistics"]["delta_ns"] or len(s["downstream"])>=2:
                    continue
                s["downstream"].append(dict(scope=scope, axis=side, rank=rank, delay_budget_ns=budget,
                    path_edges=[e["edge_id"] for e in path],
                    at_endpoint=not path, starts_at_linked_wait=s["kind"]=="compute_readiness"))

    def report(self):
        # Bound together by a physical edge or the same receive completion, never by overlap alone.
        corroborated = {k for k,s in self.stages.items() if self.links[k] and
                        (s["downstream"] or any(self.stages[v]["downstream"] for v in self.links[k]))}
        selected = {k for k,s in self.stages.items() if s["statistics"]["strong"] or k in corroborated}
        # A preparation interval may be corroborated by its associated main-stream Wait,
        # but the two are not merged unless there is a verified physical dependency.
        for anchor, keys in self.by_anchor.items():
            kinds = {self.stages[k]["kind"] for k in keys}
            if kinds!={"compute_readiness","event_wait"}:
                continue
            for k in keys:
                s = self.stages[k]
                if (s["kind"]=="compute_readiness" and s["downstream"] and "serial_order" in s["evidence"]):
                    selected.add(k)
                    s["evidence"]["anomalous_bound_wait"] = anchor
        result = []
        while selected:
            seed = min(selected)
            selected.remove(seed)
            group, work = [seed], [seed]
            while work:
                for q in self.links[work.pop()]:
                    if q in selected:
                        group.append(q)
                        work.append(q)
                        selected.remove(q)
            group.sort(key=lambda k:(self.stages[k]["interval_ns"],k))
            members = [self.stages[k] for k in group]
            first = members[0]
            a = min(s["interval_ns"][0] for s in members)
            b = max(s["interval_ns"][1] for s in members)
            links = [dict(a=i,b=j,**self.links[x][y]) for i,x in enumerate(group)
                     for j,y in enumerate(group) if i<j and y in self.links[x]]
            kinds = sorted({s["kind"] for s in members})
            result.append(dict(node_id=first["node_id"], rank=first["rank"], device_id=first["device_id"],
                iteration=first["iteration"], interval_ns=(a,b), duration_ns=b-a,
                uncertainty_ns=first["uncertainty_ns"], types=kinds,
                alignment="estimated_reference_clock", stages=members, dependency_links=links))
        return sorted(result,key=lambda s:(s["interval_ns"],s["node_id"],s["rank"],s["types"]))
