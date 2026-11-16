from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from . import online_followup as followup
from . import report_exporter
from .source_propagation_view import render_html
from .workload_binder import _certain_pairs


class FollowupTests(unittest.TestCase):
    def setUp(self):
        self.alert = dict(version=1, event_id="alert", job_id="job", event_type="COMPUTATION_SLOW",
            communicator_id="dp", communicator_generation=2, op_counter=41, stage="measured", iteration=6,
            bucket_id="grad", occurrence=0, op_type="allreduce", tensor_bytes=32, suspected_ranks=[1],
            ranks=[dict(rank_id=r, entry=dict(host_entry_ts=100+r)) for r in (0, 1)],
            metrics=dict(R=5, P=1.01, timing_boundary_verified=False))
        self.location = dict(group_id="dp", stage="measured", iteration=6, call_site="grad", occurrence=0)
        self.call = dict(self.location, dtype="float32", element_count=8, operation_type="allreduce", participants=[0, 1],
                         online_op_counter=41, online_communicator_generation=2)

    def resolved(self, *, bound=True):
        inputs = [(dict(user_rank=r, run_id="job"), [dict(self.call, before=dict(raw_ns=100+r))]) for r in (0, 1)]
        with patch.object(followup, "_read_calls", side_effect=inputs):
            return followup.resolve([self.alert], ["rank0", "rank1"],
                [dict(self.location, operation_scope="s1")] if bound else [])

    def test_alert_matches_token_not_ordinal_and_ambiguous_binding_is_reported(self):
        self.assertEqual(self.resolved()[0]["binding_status"], "bound_exact")
        self.assertEqual(self.resolved(bound=False)[0]["binding_status"], "profiler_operation_not_uniquely_bound")
        self.alert["op_counter"] += 1
        self.assertEqual(self.resolved()[0]["binding_status"], "incomplete_sdk_token")
        self.alert["op_counter"] -= 1
        self.alert["bucket_id"] = "another_bucket"
        with self.assertRaisesRegex(ValueError, "disagrees with SDK location"):
            self.resolved()

    def test_wrong_run_and_non_slow_events(self):
        with TemporaryDirectory() as folder:
            capture = Path(folder) / "capture"
            directory = Path(folder) / "online"
            directory.mkdir()
            path = directory / "events.jsonl"
            path.write_text(json.dumps(self.alert) + "\n" + json.dumps(dict(self.alert, event_type="NOT_ENTERED_HANG")) + "\n")
            self.assertEqual(followup.alert_path(capture), path.resolve())
            self.assertEqual(followup.load_alerts(path, "job"), [self.alert])
            with self.assertRaisesRegex(ValueError, "job ID"):
                followup.load_alerts(path, "different")

    def test_partial_binder_keeps_only_independent_exact_matches(self):
        self.assertEqual(_certain_pairs({0: {20}, 1: {30, 31}, 2: {30}, 3: set()}), {0: 20})

    def test_s1_keeps_host_to_wait_and_s2_keeps_outgoing_path(self):
        s1, = self.resolved()
        s2 = dict(s1, route="communication", operation_scope="s2", op_counter=42, bucket="other")

        def task(g, scope, kind, *, late=False):
            return dict(graph_id=g, operation_scope=scope, task_kind=kind, node_id="node", user_rank=1,
                        stream_id=1, task_id=10, observed_start_ns=10, observed_stop_ns=30, duration_ns=20,
                        reference_mean_ns=10, delta_ns=10, reference_count=5, duration_slow=True, iteration_start_late=late)

        tasks = [task("prep-device", "s1", "notify_record", late=True), task("slow-wait", "s1", "notify_wait"),
                 task("event-wait", "s1", "event_wait"), task("slow-copy", "s2", "sdma"),
                 task("tail-wait", "elsewhere", "notify_wait")]

        def root(g, scope, component, **paths):
            return dict(root_id=g, graph_id=g+"-anchor", operation_scope=scope, component=component, evidence_paths=paths)

        report = dict(tasks=tasks, root_causes=[root("host", "s1", "host_preparation", **{"slow-wait": ["edge1"]}),
            root("execution", "s2", "execution", **{"tail-wait": ["edge2", "edge3"]}),
            root("out", "irrelevant", "execution", **{"no-target": ["edge4"]})],
            wait_backtraces=[dict(wait_graph_id="slow-wait", operation_scope="s1", boundaries=[]),
                             dict(wait_graph_id="tail-wait", operation_scope="elsewhere", boundaries=[])])
        focused, (one, two) = followup.focus_report(report, [s1, s2], preparations=[
            dict(operation_scope="s1", user_rank=1, start_ns=100, stop_ns=800)])
        self.assertEqual([r["root_id"] for r in focused["root_causes"]], ["host", "execution"])
        self.assertEqual(focused["root_causes"][1]["evidence_paths"], {"tail-wait": ["edge2", "edge3"]})
        self.assertEqual(one["unresolved_event_wait_ids"], ["event-wait"])
        self.assertEqual(one["host_preparation"][0]["user_rank"], 1)
        self.assertEqual(one["late_task_observations"][0]["graph_id"], "prep-device")
        self.assertEqual(two["slow_tasks"][0]["graph_id"], "slow-copy")
        self.assertEqual(two["dependency_paths"][0]["wait_scope"], "elsewhere")
        html = render_html(dict(summary={}, candidates=[], nodes={}, online_followup=dict(
            alerts=[one, two], alert_count=2, bound_count=2)))
        self.assertIn("在线告警离线追查", html)
        self.assertIn("execution.html#slow-copy", html)
        self.assertIn("EVENT_WAIT 缺少可验证的生产者", html)

    def test_execution_slice_retains_downstream_evidence_outside_alert_iteration(self):
        rows = [dict(_graph_id=g, _operation_scope=g) for g in ('seed', 'next', 'wait', 'unrelated')]
        edges = [dict(src='seed', dst='next', edge_id='1'), dict(src='next', dst='wait', edge_id='2')]
        tasks = [dict(graph_id=row['_graph_id'], stage='measured', iteration=epoch)
                 for row, epoch in zip(rows, (6, 7, 7, 8))]
        roots = [dict(graph_id='seed', evidence_paths={'wait': ['1', '2']})]
        normalized = dict(candidates=[], online_followup=dict(alerts=[dict(operation_scope='seed', iteration=6)]))
        with TemporaryDirectory() as folder:
            work = Path(folder)
            (work/'operation_timings.csv').write_text('operation_scope\nseed\nnext\nwait\n')
            (work/'dep_graph_notify_ambiguities.csv').touch()
            with patch.object(report_exporter.waits, 'analyze', return_value={}), patch.object(
                    report_exporter, 'publish_final_report') as publish:
                report_exporter.publish_selected_iteration_report(work, work/'report', normalized, roots, tasks,
                                                                 graph_data=(rows, edges))
            archived, kept_edges = publish.call_args.kwargs['graph_data']
            self.assertEqual({row['_graph_id'] for row in archived}, {'seed', 'next', 'wait'})
            self.assertEqual(kept_edges, edges)


if __name__ == "__main__":
    unittest.main()
