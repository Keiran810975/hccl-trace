from __future__ import annotations

import json
from pathlib import Path
import sqlite3
import tempfile
import unittest

from .aicpu_buffers import parse_buffers, read_buffers
from .capture_discovery import discover_capture
from .test_tool_cli import sdk_capture
from .workload_binder import bind_capture


def logs(rank, stream, task, pointer, tid=24, size=4096):
    prefix = "[INFO] HCCL(100,aicpu_scheduler):2026-10-30-00:22:15.189.550 [aicpu_communicator.cc:3571] [" + str(tid) + "]"
    return [prefix + "[ReportMainStreamTask] aicpuKernelStreamId = {}, aicpuKernelTaskId = {}".format(stream, task),
            prefix + "[ReportMainStreamTask] streamId:{}, taskId:{}, type:0".format(stream, task),
            prefix + "[OrchestrateHcclOp] opUnfoldIdx_[999] opType[2] curRank[{}] rankSize[2]".format(rank),
            prefix + "[OrchestrateHcclOp] inputPtr[{}] inputSize[{}] outputPtr[{}] outputSize[{}]".format(hex(pointer), size, hex(pointer), size)]


class BufferTests(unittest.TestCase):
    def test_context_is_thread_local_and_requires_an_observed_anchor(self):
        first, second = logs(3, 8, 10, 4096), logs(9, 12, 20, 8192, tid=25)
        records = list(parse_buffers(first[:3] + second[:3] + first[3:] + second[3:]))
        self.assertEqual([r["input_buffer_ptr"] for r in records], [4096, 8192])
        self.assertEqual([r["anchor_task_id"] for r in records], [10, 20])
        self.assertEqual(list(parse_buffers(first[1:])), [])

    def test_native_rotation_keeps_incomplete_anchor_but_never_crosses_device_or_process(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            device = root / "debug/device-7"
            device.mkdir(parents=True)
            rows = logs(3, 90, 26152, 4096)
            first = device / "device-77_20261029190416000.log"
            second = device / "device-77_20261029190417000.log"
            first.write_text("\n".join(rows[:2]))
            second.write_text("\n".join(rows[2:]))
            other = root / "debug/device-5"
            other.mkdir()
            (other / second.name).write_text("\n".join(logs(9, 90, 26152, 8192)[2:]))
            (device / "device-88_20261029190417000.log").write_text("\n".join(logs(9, 90, 26152, 8192)[2:]))
            facts = read_buffers(root)
            self.assertEqual(set(facts), {(3, 2, 90, 26152)})
            value, proof = facts[(3, 2, 90, 26152)]
            self.assertEqual(value["input_buffer_ptr"], 4096)
            self.assertIn(str(first), proof)
            self.assertIn(str(second), proof)

    def test_consumed_anchor_cannot_be_reused_by_an_unanchored_next_operation(self):
        rows = logs(3, 8, 10, 4096)
        self.assertEqual(len(list(parse_buffers(rows + logs(3, 8, 11, 8192)[2:]))), 1)

    def test_same_size_async_calls_use_exact_buffer_and_task_connection_not_order(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            capture = sdk_capture(root / "capture", iterations=2)
            for node, rank in (("node0", 3), ("node1", 9)):
                path = capture / "nodes" / node / "calls" / ("rank-{}.jsonl".format(rank))
                events = [json.loads(s) for s in path.read_text().splitlines()]
                for event in events:
                    if event["event"] == "call":
                        # Both real envelopes cover both same-size APIs: timing alone must still fail.
                        event["before"]["raw_ns"] = 100
                        event["after"]["raw_ns"] = 400
                    if event["event"] == "completion":
                        event["clocks"]["raw_ns"] = 200000
                path.write_text("\n".join(map(json.dumps, events)))
                extra = logs(rank, 13, 11, 8192) + logs(rank, 13, 1, 4096)
                (capture / "nodes" / node / "plog/device-buffers.log").write_text("\n".join(extra))
                with sqlite3.connect(capture / "nodes" / node / "db/msprof_fixture.db") as db:
                    db.execute("ALTER TABLE COMMUNICATION_TASK_INFO ADD COLUMN groupName INTEGER")
                    db.execute("UPDATE COMMUNICATION_TASK_INFO SET groupName=5")
            with self.assertRaisesRegex(ValueError, "ambiguous"):
                bind_capture(discover_capture(capture, root / "discover"), root / "unbound", mode="rolling")
            for path in capture.glob("nodes/*/calls/rank-*.jsonl"):
                events = [json.loads(s) for s in path.read_text().splitlines()]
                for event in events:
                    if event["event"] == "call":
                        event["input_buffer_ptr"] = 4096 * (event["sequence"] + 1)
                path.write_text("\n".join(map(json.dumps, events)))
            result = bind_capture(discover_capture(capture, root / "discover2"), root / "bound", mode="rolling")
            self.assertEqual(result.evidence["sdk_bound_calls"], 4)
            path = capture / "nodes/node0/plog/device-buffers.log"
            path.write_text(path.read_text().replace("taskId:11, type:0", "taskId:99, type:0"))
            with self.assertRaisesRegex(ValueError, "exact TASK"):
                bind_capture(discover_capture(capture, root / "discover3"), root / "bad", mode="rolling")


if __name__ == "__main__":
    unittest.main()
