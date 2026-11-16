from __future__ import annotations

import unittest
from dataclasses import asdict

from . import online_followup
from .clock_alignment import DeviceClock
from .dependency_timing import EVENT, ORDER
from .rolling_diagnosis import RollingOptions
from .source_propagation_view import render_html


class Capture:
    def __init__(self):
        self.rows, self.edges, self.timings, self.tasks = [], [], {}, []
        self.origins = {}

    def op(self, scope, rank, start, *, node=None):
        node = node or f"node{rank}"
        self.origins[scope, rank] = start
        self.timings[scope, rank] = dict(operation_scope=scope, node_id=node,
            device_id=rank, user_rank=rank, start_ns=start, end_ns=start+1000, duration_ns=1000)

    def task(self, name, scope, rank, stream, kind, span, *, history=None,
             late=False, epoch=6, node=None):
        node = node or f"node{rank}"
        start, end = span
        row = dict(_graph_id=name, _node_id=node, _user_rank=rank, _device_id=rank,
            _stream_id=stream, _task_id=len(self.rows), _subtask_id=-1, _operation_scope=scope,
            algorithm="Ring", phase="rs", step="0", event=kind, profiler_task_kind=kind,
            _peer_rank=-1, _start_ns=start, _stop_ns=end)
        self.rows.append(row)
        refs = []
        if history:
            a, b = history
            for i in range(3):
                ref_scope, ref = f"{scope}-hist{i}", f"{name}-hist{i}"
                off = i * 1000
                self.op(ref_scope, rank, off, node=node)
                self.rows.append(dict(row, _graph_id=ref, _operation_scope=ref_scope, _start_ns=off+a, _stop_ns=off+b))
                refs.append(ref)
        self.tasks.append(dict(graph_id=name, node_id=node, user_rank=rank, stream_id=stream,
            task_id=row["_task_id"], operation_scope=scope, task_kind=kind, stage="measured", iteration=epoch,
            observed_start_ns=start, observed_stop_ns=end, duration_ns=end-start, reference_count=len(refs),
            reference_mean_ns=str(history[1]-history[0]) if history else None, reference_graph_ids=refs,
            reference_iterations=[1, 2, 3] if refs else [],
            delta_ns=str(end-start-(history[1]-history[0])) if history else None,
            duration_slow=bool(history and end-start > 1.5*(history[1]-history[0])), iteration_start_late=late))

    def edge(self, src, dst, kind=ORDER, conf="observed", **fields):
        self.edges.append(dict(src=src, dst=dst, kind=kind, confidence=conf, edge_id=f"{src}-{dst}", **fields))

    def analyze(self, route, ranks, *, suspect=None, alignment=None, host=(), roles=None):
        event = dict(event_id="alert", route=route, event_type=next(k for k, v in online_followup.ROUTES.items() if v == route),
            operation_scope="target", ranks=ranks, suspected_ranks=suspect, iteration=6, bucket="grad", op_counter=9,
            binding_status="bound_exact", online_metrics=dict(R=5, P=0.1, timing_boundary_verified=False),
            rank_roles=roles or {})
        _, (result,) = online_followup.focus_report(
            dict(tasks=self.tasks, root_causes=[], unresolved_observations=list(host)), [event],
            rows=self.rows, edges=self.edges, timings=self.timings.values(), options=RollingOptions(), alignment=alignment)
        return result


def clocks(count, error=0):
    return dict(schema_version=3, status="network_probe_estimate",
                models=[asdict(DeviceClock(f"node{r}", r, 0, 0, 0, 1, 1, 0, 100_000, error)) for r in range(count)])


class OfflineEvidenceTests(unittest.TestCase):
    def test_exact_event_release_reaches_slow_work_but_ambiguous_or_missing_handle_does_not(self):
        c = Capture()
        c.op("target", 0, 10000)
        c.op("calc", 0, 10000)
        c.task("kernel", "calc", 0, 10, "kernel_aivec", (10001, 10060), history=(1, 11))
        c.task("record", "", 0, 10, "event_record", (10060, 10061))
        c.task("wait", "target", 0, 20, "event_wait", (10020, 10062), history=(20, 30))
        c.task("other", "", 0, 11, "event_record", (10055, 10059))
        c.edge("kernel", "record")
        c.edge("record", "wait", EVENT, "exact", event_context_id="process-context",
               event_id="shared-object", event_generation="2")
        verified = c.analyze("S1", [0], suspect=[0])
        trace, = verified["blocking_waits"]
        self.assertTrue(trace["producer"]["verified"])
        self.assertEqual(trace["producer"]["event_identity"]["generation"], 2)
        self.assertEqual(trace["upstream_task_or_stage"][0]["status"], "blocking_overrun_supported")
        self.assertEqual([e["edge_id"] for e in trace["upstream_task_or_stage"][0]["path"]],
                         ["kernel-record", "record-wait"])
        c.edges[-1].pop("event_generation")
        unknown = c.analyze("S1", [0], suspect=[0])
        self.assertEqual(unknown["unresolved_event_wait_ids"], ["wait"])
        self.assertEqual(unknown["blocking_waits"][0]["upstream_task_or_stage"], [])
        c.edges[-1]["event_generation"] = 2
        c.edge("other", "wait", EVENT, "exact", event_context_id="context", event_id="other", event_generation=2)
        self.assertEqual(c.analyze("S1", [0])["blocking_waits"][0]["producer"]["status"], "ambiguous_sync_producer")

    def test_host_preparation_without_device_upstream_never_names_kernel(self):
        c = Capture()
        c.op("target", 1, 10000)
        c.task("wait", "target", 1, 20, "notify_wait", (10020, 10062), history=(20, 30))
        prep = dict(operation_scope="target", component="host_preparation", user_rank=0, node_id="node0",
            observed_start_ns=9700, observed_stop_ns=10000, api_start_ns=10000, api_stop_ns=10005,
            duration_ns=300, reference_mean_ns="10", reference_mad_ns="1", delta_ns="290",
            reference_count=5, evidence_paths={"wait": ["host-linked-signal"]}, status="dependency_supported_candidate")
        a = c.analyze("S1", [0, 1], suspect=[0], host=[prep])
        self.assertEqual(a["suspected_rank"], 0)
        self.assertEqual(a["host_preparation_observation"][0]["cpu_task"], "unknown")
        self.assertEqual(a["host_preparation_observation"][0]["related_waits"][0]["graph_id"], "wait")
        self.assertFalse(a["blocking_waits"][0]["upstream_task_or_stage"])
        undetermined = c.analyze("undetermined", [0, 1], host=[prep])
        self.assertTrue(undetermined["host_preparation_observation"])
        self.assertTrue(undetermined["slow_waits"])
        self.assertNotIn("rank_progress", undetermined)

    def test_late_short_wait_does_not_blame_its_future_release_for_start_delay(self):
        c = Capture()
        c.op("target", 0, 10000)
        c.op("calc", 0, 10000)
        c.task("compute", "calc", 0, 10, "kernel_aivec", (10010, 10071), history=(10, 20))
        c.task("record", "", 0, 10, "event_record", (10071, 10072))
        c.task("wait", "target", 0, 30, "event_wait", (10070, 10080), history=(20, 30))
        c.edge("compute", "record")
        c.edge("record", "wait", EVENT, "exact", event_context_id="ctx", event_id="known", event_generation=1)
        wait, = c.analyze("S1", [0])["blocking_waits"]
        self.assertEqual(wait["trigger"], "late_wait_start")
        self.assertTrue(wait["producer"]["verified"])
        self.assertFalse(wait["upstream_task_or_stage"])

    def test_pre_collop_event_gate_is_observed_without_inventing_identity(self):
        c = Capture()
        c.op("target", 0, 10000)
        c.task("before", "", 0, 20, "event_wait", (9980, 10000))
        c.task("start", "target", 0, 20, "notify_record", (10000, 10001), history=(0, 1))
        c.edge("before", "start")
        result = c.analyze("S1", [0])
        entry, = result["entry_wait_observations"]
        self.assertEqual(entry["stream_edge"]["edge_id"], "before-start")
        self.assertEqual(result["unresolved_event_wait_ids"], ["before"])
        self.assertEqual(result["blocking_waits"], [])

    def test_active_cross_collop_search_and_receiver_does_not_rank_first(self):
        c = Capture()
        c.op("target", 0, 10000)
        c.op("target", 1, 10000)
        c.op("next", 1, 10000)
        c.task("slow", "target", 0, 10, "sdma", (10001, 10070), history=(1, 11))
        c.task("signal", "target", 0, 10, "notify_record", (10070, 10071), history=(11, 12))
        c.task("wait", "target", 1, 20, "notify_wait", (10021, 10072), history=(21, 31))
        c.task("next-task", "next", 1, 20, "sdma", (10073, 10083), history=(33, 43), epoch=7)
        c.task("second-slow", "next", 1, 20, "sdma", (10083, 10100), history=(43, 46), epoch=7)
        c.edge("slow", "signal")
        c.edge("signal", "wait", "cross_node_notify_sync_observed")
        c.edge("wait", "next-task")
        c.edge("next-task", "second-slow")
        alert = c.analyze("S2", [0, 1], alignment=clocks(2))
        self.assertEqual(alert["unique_first_priority"], 0)
        self.assertEqual([(r["rank"], r["evidence_level"]) for r in alert["rank_progress"]], [(0, "high"), (1, "low")])
        witness = next(x for x in alert["downstream_propagation"] if x["seed"]["graph_id"] == "slow")
        impacts = [x for x in witness["downstream"] if x["task"]["graph_id"] != "signal"]
        self.assertEqual([x["change"] for x in impacts],
                         ["wait_growth", "start_displacement_with_normal_duration", "independent_execution_overrun"])
        self.assertEqual([x["edge_id"] for x in impacts[1]["path"]],
                         ["slow-signal", "signal-wait", "wait-next-task"])
        self.assertEqual(witness["affected_operation_scopes"], ["next", "target"])
        self.assertEqual(witness["downstream"][-1]["status"], "independent_not_attributed")
        self.assertEqual(witness["collop_completion_effect"], "not_determined")
        for alignment, reason in ((None, "missing_cross_device_clock"), (clocks(2, 4), "clock_order_uncertain")):
            gated = c.analyze("S2", [0, 1], alignment=alignment)
            trace = next(t for t in gated["downstream_propagation"] if t["seed"]["graph_id"] == "slow")
            self.assertFalse(any(hit["task"]["rank"] == 1 for hit in trace["downstream"]))
            self.assertIn(reason, [x["reason"] for x in trace["evidence_gaps"]])
            self.assertNotEqual(gated["rank_progress"][0]["evidence_level"], "high")
        html = render_html(dict(summary={}, candidates=[], nodes={}, online_followup=dict(
            alerts=[alert], alert_count=1, bound_count=1)))
        self.assertIn("S2 Rank 排查优先级", html)
        self.assertIn("execution.html#next-task", html)

    def test_rdma_submission_never_becomes_verified_release(self):
        c = Capture()
        c.op("target", 0, 10000)
        c.op("target", 1, 10000)
        c.task("copy", "target", 0, 1, "sdma", (10001, 10060), history=(1, 11))
        c.task("doorbell", "target", 0, 1, "rdma", (10060, 10070), history=(11, 21))
        c.task("peer-wait", "target", 1, 2, "notify_wait", (10020, 10072), history=(20, 30))
        c.edge("copy", "doorbell")
        c.edge("doorbell", "peer-wait", "cross_node_notify_sync_observed")
        alert = c.analyze("S2", [0, 1], alignment=clocks(2))
        trace = next(x for x in alert["downstream_propagation"] if x["seed"]["graph_id"] == "copy")
        self.assertIn("rdma_submission_not_payload_completion", [x["reason"] for x in trace["evidence_gaps"]])
        self.assertNotIn(1, trace["affected_ranks"])

    def test_group_degradation_can_tie_and_normal_work_does_not_propagate(self):
        c = Capture()
        roles = {}
        for rank in range(8):
            c.op("target", rank, 10000)
            c.task(f"r{rank}", "target", rank, 1, "sdma", (10004, 10035), history=(4, 14))
            roles[rank] = dict(role="same", algorithm="Ring", verified=True)
        result = c.analyze("S2", list(range(8)), roles=roles)
        self.assertEqual({r["priority_rank"] for r in result["rank_progress"]}, {1})
        self.assertIsNone(result["unique_first_priority"])
        self.assertEqual(result["detailed_rank_count"], 8)
        for t in c.tasks:
            t["duration_slow"] = False
        result = c.analyze("S2", list(range(8)), roles=roles)
        self.assertFalse(result["downstream_propagation"])
        self.assertEqual({r["priority_rank"] for r in result["rank_progress"]}, {None})


if __name__ == "__main__":
    unittest.main()
