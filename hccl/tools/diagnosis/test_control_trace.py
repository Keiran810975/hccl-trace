"""Control gaps observed in the two-node Single Ring/NHR capture."""
from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import os
import sys
import tempfile
import unittest

if __package__ in (None, ""):
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from diagnosis.control_trace import ControlTask, enrich_control_tasks, parse_control_inputs, parse_build_spans, INVALID_U64
    from diagnosis.schema import ProfilerTask
else:
    from .control_trace import ControlTask, enrich_control_tasks, parse_control_inputs, parse_build_spans, INVALID_U64
    from .schema import ProfilerTask


def sample():
    post = ProfilerTask(node_id="node0", device_id=12, stream_id=45, task_id=1,
        task_kind="notify_record", op_name="allreduce-call", group_name="group", profiler_op_id=3,
        profiler_op_connection_id=288, profiler_notify_id=(1 << 64) - 4294179540,
        profiler_src_rank=2)
    kernel = replace(post, stream_id=12, task_id=1, task_kind="kernel_aicpu",
        op_name="", group_name="", profiler_op_id=-1, profiler_notify_id=-1)
    order = replace(kernel, stream_id=91, task_id=0, task_kind="notify_record")
    control = ControlTask("node0", 12, 45, 1, "notify_record", 6475,
                          post.profiler_notify_id, 45, 1)
    binding = replace(control, stream_id=12, task_kind="kernel_aicpu",
                      notify_id=INVALID_U64, db_notify_id=INVALID_U64)
    record = replace(control, stream_id=91, task_id=0, notify_id=6478,
                     db_notify_id=INVALID_U64, anchor_stream_id=12, anchor_task_id=1)
    return [post, kernel, order], [control, binding, record]


class ControlTraceTest(unittest.TestCase):
    def test_cpu_span_requires_exact_kernel_and_separate_clock(self):
        tasks, controls = sample()
        tasks, _ = enrich_control_tasks(tasks, controls)
        text = ("[HcclTaskBuildSpan] schema_version[1] device_id[12] kernel_stream_id[12] "
                "kernel_task_id[1] user_rank[2] algorithm[nhr] phase[reduce_scatter] "
                "step[0] slice[0] duration_ns[40000001] threshold_ns[1000000] "
                "timing_domain[aicpu_build_cpu]\n")
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "plog.log"
            path.write_text(text, encoding="utf-8")
            span, = parse_build_spans([path], "node0", tasks)
            self.assertEqual(span["duration_ns"], 40000001)
            self.assertEqual(span["op_name"], "allreduce-call")
            for invalid in (text.replace("schema_version[1]", "schema_version[2]"),
                            text.replace("aicpu_build_cpu", "device"),
                            text.replace("duration_ns[40000001]", "duration_ns[999]"),
                            text.replace("kernel_task_id[1]", "kernel_task_id[2]")):
                path.write_text(invalid, encoding="utf-8")
                with self.assertRaises(ValueError):
                    parse_build_spans([path], "node0", tasks)
            path.write_text(text, encoding="utf-8")
            with self.assertRaises(ValueError):
                parse_build_spans([path], "node1", tasks)
            with self.assertRaises(ValueError):
                parse_build_spans([path], "node0", tasks + [tasks[1]])

    def test_exact_alias_and_two_hop_operation_anchor(self):
        tasks, controls = sample()
        result, audit = enrich_control_tasks(tasks, reversed(controls))
        self.assertEqual([t.op_name for t in result], ["allreduce-call"] * 3)
        self.assertEqual([t.profiler_notify_id for t in result], [6475, -1, 6478])
        self.assertEqual(result[2].execution_key, tasks[2].execution_key)
        self.assertEqual(len(audit), 3)
        self.assertEqual(tasks[0].profiler_notify_id, (1 << 64) - 4294179540)

    def test_missing_duplicate_and_ambiguous_execution_fail(self):
        tasks, controls = sample()
        cases = [(tasks[:-1], controls), (tasks, controls + controls[:1]),
                 (tasks + tasks[:1], controls), (tasks, controls[::2])]
        for raw, evidence in cases:
            with self.subTest(raw=len(raw), evidence=len(evidence)), self.assertRaises(ValueError):
                enrich_control_tasks(raw, evidence)

    def test_identity_kind_notify_and_scope_conflicts_fail(self):
        tasks, controls = sample()
        changes = [dict(device_id=2), dict(task_kind="notify_wait"),
                   dict(db_notify_id=123), dict(anchor_stream_id=90)]
        for change in changes:
            with self.subTest(change=change), self.assertRaises(ValueError):
                enrich_control_tasks(tasks, [replace(controls[0], **change), *controls[1:]])
        with self.assertRaises(ValueError):
            enrich_control_tasks([tasks[0], replace(tasks[1], op_name="other", group_name="group"), tasks[2]], controls)

    def test_cycle_and_cross_node_anchor_cannot_borrow_scope(self):
        tasks, controls = sample()
        with self.assertRaises(ValueError):
            enrich_control_tasks(tasks, [controls[0], replace(controls[1], anchor_stream_id=91, anchor_task_id=0), controls[2]])
        with self.assertRaises(ValueError):
            enrich_control_tasks(tasks, [replace(c, node_id="node1") for c in controls])

    def test_clock_shift_preserves_identity_and_resource_mapping(self):
        tasks, controls = sample()
        shifted = [replace(t, task_start="9999999999999.999", task_stop="99999999999999.123") for t in tasks]
        result, audit = enrich_control_tasks(shifted, controls)
        original, original_audit = enrich_control_tasks(tasks, controls)
        self.assertEqual(audit, original_audit)
        self.assertEqual([t.profiler_notify_id for t in result], [t.profiler_notify_id for t in original])

    def test_strict_parser_and_wide_alias(self):
        text = ("[HcclTaskControl] schema_version[1] device_id[12] stream_id[45] task_id[1] "
                "task_kind[notify_record] notify_id[6475] db_notify_id[18446744069415372076] "
                "anchor_stream_id[45] anchor_task_id[1]\n")
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "plog.log"
            path.write_text(text, encoding="utf-8")
            record, = parse_control_inputs([path], "node0")
            self.assertEqual(record.db_notify_id, 18446744069415372076)
            for invalid in (text.replace("schema_version[1]", "schema_version[2]"),
                            text.replace("notify_id[6475]", "notify_id[-1]"),
                            text + "[HcclTaskControl] schema_version[1]\n"):
                path.write_text(invalid, encoding="utf-8")
                with self.assertRaises(ValueError):
                    parse_control_inputs([path], "node0")


if __name__ == "__main__":
    unittest.main()
