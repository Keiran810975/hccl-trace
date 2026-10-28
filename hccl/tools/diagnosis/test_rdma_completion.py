from __future__ import annotations

import csv
from dataclasses import asdict, replace
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from . import rdma_completion as completion


def post(**changes):
    return replace(completion.CompletionEvent("run/node0", "post", backend="ibverbs", clock="process_steady_ns",
        pid=20, process_epoch=99, cq_id=100, qp_num=7, wr_id=(1 << 64) - 1, opcode="write", raw_opcode=0,
        bytes=2097152, accepted=1, result=0, start_ns=1000, post_return_ns=1100,
        local_rank=1, peer_rank=3, message_id=42, role="data_write", send_flags=2), **changes)


def cqe(**changes):
    return replace(completion.CompletionEvent("run/node0", "cqe", backend="ibverbs", clock="process_steady_ns",
        pid=20, process_epoch=99, cq_id=100, qp_num=7, wr_id=(1 << 64) - 1, wc_opcode=1, status=0,
        observed_ns=2000), **changes)


class RdmaCompletionTests(unittest.TestCase):
    def test_integer_identity_and_observed_completion_are_not_wire_time(self):
        report = completion.analyze([post(), cqe()])
        row, = report["operations"]
        self.assertEqual(row["operation_elapsed_observed_ns"], 1000)
        self.assertEqual(row["wr_id"], 18446744073709551615)
        self.assertIsNone(row["network_transfer_duration_ns"])
        self.assertIsNone(row["graph_id"])
        self.assertFalse(report["cross_node_time_subtraction"])
        self.assertFalse(report["full_transfer_and_dependency_available"])

    def test_all_native_operations_require_matching_cq_opcode(self):
        for opcode, wc in (("send", 0), ("write", 1), ("read", 2)):
            row, = completion.analyze([post(opcode=opcode), cqe(wc_opcode=wc)])["operations"]
            self.assertEqual(row["status"], "completion_observed")
        row, = completion.analyze([post(), cqe(wc_opcode=2)])["operations"]
        self.assertEqual(row["status"], "completion_opcode_mismatch")
        self.assertIsNone(row["operation_elapsed_observed_ns"])

    def test_errors_failed_posts_unknown_results_do_not_become_durations(self):
        for p, c, status in ((post(), cqe(status=5), "completion_error"),
                             (post(accepted=0, result=12), cqe(), "post_failed"),
                             (post(accepted=-1), cqe(), "unknown_post_result")):
            row, = completion.analyze([p, c])["operations"]
            self.assertEqual(row["status"], status)
            self.assertIsNone(row["operation_elapsed_observed_ns"])

    def test_missing_and_orphan_cq_remain_unresolved(self):
        self.assertEqual(completion.analyze([post()])["operations"][0]["status"], "missing_completion")
        report = completion.analyze([cqe()])
        self.assertEqual(report["summary"]["unmatched_completion_count"], 1)
        self.assertEqual(report["operations"], [])

    def test_reused_wrid_needs_complete_nonoverlapping_lifetimes(self):
        second = post(start_ns=3000, post_return_ns=3100)
        done = cqe(observed_ns=4000)
        self.assertEqual(completion.analyze([post(), second, cqe(), done])["summary"]["completion_observed_count"], 2)
        for records in ([post(), second, done], [post(), post(start_ns=1500), cqe(), done],
                        [post(), cqe(), cqe()], [post(), cqe(observed_ns=900)]):
            report = completion.analyze(records)
            self.assertEqual(report["summary"]["completion_observed_count"], 0)

    def test_node_process_epoch_cq_qp_and_wrid_partition_matching(self):
        for changes in ({"node_id": "run/node1"}, {"pid": 21}, {"process_epoch": 98},
                        {"cq_id": 101}, {"qp_num": 8}, {"wr_id": 1}):
            self.assertEqual(completion.analyze([post(), cqe(**changes)])["summary"]["completion_observed_count"], 0)

    def test_receive_cqe_cannot_be_used_as_send_completion(self):
        row, = completion.analyze([post(), cqe(wc_opcode=128)])["operations"]
        self.assertEqual(row["status"], "completion_opcode_mismatch")

    def test_strict_input_schema_and_clock(self):
        valid = asdict(post())
        self.assertEqual(completion.event_from_mapping(valid, valid["node_id"]), post())
        for changes in ({"schema_version": 2}, {"schema_version": ""}, {"clock": "device_ns"},
                        {"wr_id": -1}, {"wr_id": 1 << 64}, {"node_id": "other"}, {"start_ns": "1.5"},
                        {"accepted": 2}, {"post_return_ns": 900}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                completion.event_from_mapping(dict(valid, **changes), valid["node_id"])
        del valid["wr_id"]
        with self.assertRaises(ValueError):
            completion.event_from_mapping(valid, "run/node0")

    def test_csv_round_trip_and_escaped_html_no_fake_binding(self):
        records = [post(role="<script>bad</script>"), cqe()]
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            path = root / "events.csv"
            completion.write_csv(str(path), completion.EVENT_FIELDS, map(asdict, records))
            self.assertEqual(completion.read_events([path]), records)
            output = root / "report"
            completion.export_report(completion.analyze(records), output)
            with (output / "operations.csv").open() as stream:
                row, = csv.DictReader(stream)
            self.assertEqual(row["wr_id"], "18446744073709551615")
            self.assertEqual(row["operation_elapsed_observed_ns"], "1000")
            self.assertEqual(row["network_transfer_duration_ns"], "")
            page = (output / "index.html").read_text()
            self.assertNotIn("<script>bad", page)
            self.assertIn("&lt;script&gt;", page)
            self.assertNotIn("../execution.html", page)
            with self.assertRaises(FileExistsError):
                completion.export_report(completion.analyze(records), output)

    @unittest.skipUnless(shutil.which("c++"), "C++14 compiler unavailable")
    def test_compiled_observer_produces_consumable_facts_without_changing_wr(self):
        root = Path(__file__).resolve().parents[3]
        with tempfile.TemporaryDirectory() as temporary:
            binary = Path(temporary) / "observer"
            subprocess.run(["c++", "-std=c++14", "-Wall", "-Wextra", "-Werror",
                "-I" + str(root / "hcomm/src/platform/common/adapter"),
                str(root / "test/fixtures/rdma_completion_observer_test.cc"), "-o", str(binary)],
                check=True, capture_output=True, text=True)
            env = dict(os.environ, HCCL_RDMA_COMPLETION_TRACE="0")
            self.assertEqual(subprocess.check_output([str(binary)], env=env, text=True), "")
            env["HCCL_RDMA_COMPLETION_TRACE"] = "1"
            log = subprocess.check_output([str(binary)], env=env, text=True)
            path = Path(temporary) / "plog.log"
            path.write_text(log)
            events = completion.parse_inputs([path], "node2")
            report = completion.analyze(events)
            self.assertEqual(report["summary"]["completion_observed_count"], 1)
            self.assertEqual(report["summary"]["trace_gap_count"], 1)
            read = next(row for row in report["operations"] if row["opcode"] == "read")
            self.assertEqual((read["local_rank"], read["peer_rank"], read["bytes"]), (3, 1, 2097152))
            self.assertEqual(read["operation_elapsed_observed_ns"], 1000)
            failed = next(row for row in report["operations"] if row["wr_id"] == 2)
            self.assertEqual(failed["status"], "post_failed")


if __name__ == "__main__":
    unittest.main()
