import sqlite3
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from .endpoint_replay import Backward, merge_source_events, possible_last
from .endpoint_replay_data import add_main_stream, local_fact_tables
from .dependency_model import stable_id


def node(g, a, b, kind, stream, device=0):
    return dict(_graph_id=g,_node_id="n",_device_id=device,_user_rank=device,_operation_scope="op",
                _subtask_id=-1,_start_ns=a,_stop_ns=b,_stream_id=stream,_task_id=len(g),profiler_task_kind=kind)


def edge(a,b,kind,confidence):
    return dict(src=a,dst=b,kind=kind,confidence=confidence,edge_id=a+"->"+b)


class DualEndpointTests(unittest.TestCase):
    def test_which_rank_is_last_is_axis_specific_and_uncertain(self):
        def t(s,e):return dict(aligned_start=s,aligned_end=e,clock=SimpleNamespace(estimated_error_ns=3))
        times={0:t(50,80),1:t(44,100),2:t(10,98)}
        self.assertEqual(possible_last(times,"arrival"),[0,1])
        self.assertEqual(possible_last(times,"tail"),[1,2])

    def test_producer_which_is_waiting_is_recursively_traced(self):
        ns=[node("work",0,12,"sdma",1),node("r1",13,14,"notify_record",1),
            node("w1",1,15,"notify_wait",2),node("r2",16,17,"notify_record",2),
            node("w2",2,18,"notify_wait",3),node("done",19,21,"notify_record",3)]
        es=[edge("work","r1","direct_stream_order_observed","observed"),
            edge("r1","w1","local_notify_sync_exact","exact"),
            edge("w1","r2","direct_stream_order_observed","observed"),
            edge("r2","w2","local_notify_sync_exact","exact"),
            edge("w2","done","direct_stream_order_observed","observed")]
        m=SimpleNamespace(map_ns=lambda x:x,estimated_error_ns=0)
        graph=Backward({n["_graph_id"]:n for n in ns},es,{("n",0):m},{"op":{"iteration":1}},
                       {"work":dict(delta_ns=10)})
        replay=graph.trace("done",1)
        self.assertEqual([e["kind"] for e in replay["paths"]("work")], [e["kind"] for e in es])
        self.assertTrue(replay["hits"][0]["blocking_lineage"])
        self.assertEqual(len(replay["gates"]),2)

    def test_early_notify_does_not_block_wait(self):
        ns=[node("p",1,2,"notify_record",1),node("w",20,23,"notify_wait",4)]
        e=edge("p","w","local_notify_sync_exact","exact")
        m=SimpleNamespace(map_ns=lambda x:x,estimated_error_ns=0)
        g=Backward({r["_graph_id"]:r for r in ns},[e],{("n",0):m},{"op":{"iteration":1}},{})
        replay=g.trace("w",1)
        self.assertFalse(replay["gates"][0]["producer_delays_wait"])

    def test_event_is_not_linked_by_proximity(self):
        ns=[node("e",8,9,"event_record",1),node("w",2,10,"event_wait",4)]
        e=edge("e","w","local_event_sync_exact","exact")
        m=SimpleNamespace(map_ns=lambda x:x,estimated_error_ns=0)
        make=lambda es:Backward({r["_graph_id"]:r for r in ns},es,{("n",0):m},{"op":{"iteration":1}},{})
        self.assertFalse(make([e]).trace("w",1)["paths"]("e"))
        verified=dict(e,event_context_id="ctx",event_id="ev",event_generation=1)
        self.assertTrue(make([verified]).trace("w",1)["paths"]("e"))

    def test_cross_node_reversed_release_stays_unresolved(self):
        p=node("p",8,10,"rdma",1); p["_node_id"]="peer"
        w=node("w",2,5,"notify_wait",4)
        e=edge("p","w","cross_node_notify_sync_observed","observed")
        m=SimpleNamespace(map_ns=lambda x:x,estimated_error_ns=1)
        g=Backward({"p":p,"w":w},[e],{("n",0):m,("peer",0):m},{"op":{"iteration":1}},{})
        result=g.trace("w",1)
        self.assertIn("producer_after_wait_release", {b["reason"] for b in result["boundaries"]})
        self.assertEqual(result["paths"]("p"),[])

    def test_unordered_cross_node_release_keeps_only_context(self):
        p=node("p",8,10,"notify_record",1); p["_node_id"]="peer"
        w=node("w",2,11,"notify_wait",4)
        q=node("q",0,1,"sdma",4)
        signals=edge("p","w","cross_node_notify_sync_observed","observed")
        order=edge("q","w","direct_stream_order_observed","observed")
        m=SimpleNamespace(map_ns=lambda x:x,estimated_error_ns=1)
        g=Backward({"p":p,"w":w,"q":q},[signals,order],{("n",0):m,("peer",0):m},
                   {"op":{"iteration":1}},{"q":{"delta_ns":100}})
        result=g.trace("w",1)
        self.assertIn("clock_order_uncertain", {b["reason"] for b in result["boundaries"] if b["blocks"]})
        self.assertEqual(len(result["paths"]("p")),1)
        self.assertFalse(result["hits"][0]["blocking_lineage"])

    def test_source_events_join_only_adjacent_abnormal_physical_stages(self):
        ns=[node("a",0,9,"sdma",1),node("b",9,11,"sdma",1),
            node("c",11,13,"sdma",1),node("d",13,15,"sdma",1)]
        es=[edge(a,b,"direct_stream_order_observed","observed") for a,b in zip("abc","bcd")]
        m=SimpleNamespace(map_ns=lambda x:x,estimated_error_ns=0)
        graph=Backward({r["_graph_id"]:r for r in ns},es,{("n",0):m},{"op":{"iteration":1}},{})
        self.assertEqual(merge_source_events({"a":[1],"b":[2],"d":[4]},graph),{"a":[1,2],"d":[4]})

    def test_raw_main_stream_uses_adjacent_rows_and_wait_identity(self):
        n=node("s",10,11,"notify_record",2)
        n["_task_id"]=9
        seq=[(4,10,2,8,"EVENT_WAIT",5),(10,11,2,9,"NOTIFY_RECORD",6)]
        es=[]
        with patch("hccl.tools.diagnosis.endpoint_replay_data.stream_table",return_value=seq):
            raw,anchors=add_main_stream([n],es,{0:{"op":dict(begin=10,end=20,wait=seq[0])}}, {})
        self.assertEqual(anchors["op",0]["open"],"s")
        self.assertEqual(len(es),1)
        self.assertEqual(raw[es[0]["src"]]["profiler_task_kind"],"event_wait")
        self.assertEqual(es[0]["dst"],"s")

    def test_native_api_does_not_replace_node_identity_for_the_next_device(self):
        def make(dev):
            db=sqlite3.connect(":memory:")
            db.row_factory=sqlite3.Row
            db.executescript("""
                CREATE TABLE TASK(deviceId, startNs, endNs, streamId, taskId, taskType, connectionId);
                CREATE TABLE STRING_IDS(id, value);
                CREATE TABLE CANN_API(startNs, endNs, globalTid, connectionId, name);
                CREATE TABLE COMMUNICATION_OP(startNs,endNs,connectionId,groupName,opName);
                INSERT INTO STRING_IDS VALUES(1,'NOTIFY_RECORD'),(2,'hcom_allReduce_'),(3,'g'),(4,'op');
                INSERT INTO CANN_API VALUES(1,2,100,10,2);
                INSERT INTO COMMUNICATION_OP VALUES(3,4,10,3,4);
            """)
            db.execute("INSERT INTO TASK VALUES(?,3,4,1,1,1,10)",(int(dev),))
            return db
        scope=stable_id("op",("run","op"))
        facts=dict(manifest=dict(run_id="run",nodes=[dict(node_id="n",msprof_db_dir="unused")],
                                 operations=[dict(operation_id="op",members=[dict(node_id="n",device_id=x,
                                     group_name="g",op_name="op") for x in (1,2)])]),
                   ranks={("n",x):x for x in (1,2)},coordinates={scope:{}},
                   preparations=[dict(operation_scope=scope,user_rank=x,api_stop_ns=2,
                                      api_start_ns=1,stop_ns=0) for x in (1,2)])
        clocks={("run/n",x):SimpleNamespace(map_ns=lambda ns:ns) for x in (1,2)}
        with patch("hccl.tools.diagnosis.endpoint_replay_data.discover_db_files",return_value=[1,2]), \
                patch("hccl.tools.diagnosis.endpoint_replay_data._readonly_connection",side_effect=make):
            records=local_fact_tables(facts,clocks)
        self.assertEqual({k:v[scope]["aligned_start"] for k,v in records.items()},{1:3,2:3})


if __name__=="__main__":unittest.main()
