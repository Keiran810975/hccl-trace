from __future__ import annotations

from copy import deepcopy
import csv
from decimal import Decimal
import json
from pathlib import Path
import tempfile
import unittest

from . import rdma_timing as timing


def fixture():
    rows = []
    # The sender clock is deliberately unrelated to the receiver clock.
    values = [("ready", "receiver", 3, 1, "rdma", "link_tx_ack", 100, 101),
              ("ack", "sender", 1, 3, "notify_wait", "link_rx_ack", 900000, 900002),
              ("payload", "sender", 1, 3, "rdma", "link_tx_payload", 900002, 900003),
              ("signal", "sender", 1, 3, "rdma", "", 900003, 900004),
              ("done", "receiver", 3, 1, "notify_wait", "link_rx_payload_copy", 102, 120)]
    for index, (key, node, rank, peer, kind, semantic, start, stop) in enumerate(values):
        rows.append(dict(_graph_id=key, _node_id=node, _device_id=rank, _user_rank=rank, _peer_rank=peer,
            _stream_id=90, _task_id=index+10, _subtask_id=-1, _operation_scope="call0",
            _operation_scope_status="unique", match_status="matched", profiler_task_kind=kind,
            semantic=semantic, event=semantic, phase="allgather", step="0", profiler_size_bytes="2097152",
            _start_order=Decimal(start), _stop_order=Decimal(stop), task_start=str(start), task_stop=str(stop)))
    edges = [dict(edge_id="ready-ack", src="ready", dst="ack", kind=timing.CROSS_SYNC, confidence="observed"),
             dict(edge_id="ack-payload", src="ack", dst="payload", kind=timing.ORDER, confidence="observed"),
             dict(edge_id="payload-signal", src="payload", dst="signal", kind=timing.ORDER, confidence="observed"),
             dict(edge_id="signal-done", src="signal", dst="done", kind=timing.CROSS_SYNC, confidence="observed")]
    return rows, edges


class RdmaTimingTests(unittest.TestCase):
    def test_measures_receiver_protocol_interval_not_sender_or_network_duration(self):
        rows,edges=fixture()
        before=deepcopy((rows,edges))
        report=timing.analyze(rows,edges)
        item,=report["transfers"]
        self.assertEqual(item["status"],"protocol_interval_observed")
        self.assertEqual(item["submission_duration_ns"],1000)
        self.assertEqual(item["protocol_duration_ns"],20000)
        self.assertIsNone(item["network_transfer_duration_ns"])
        self.assertEqual(item["evidence_node_ids"],["ready","ack","payload","signal","done"])
        self.assertEqual(item["evidence_edge_ids"],[e["edge_id"] for e in edges])
        self.assertFalse(report["cross_node_time_subtraction"])
        self.assertFalse(report["hardware_transfer_duration_available"])
        self.assertEqual(report["new_execution_edges"],0)
        self.assertEqual((rows,edges),before)

    def test_sender_clock_offset_does_not_change_measured_interval(self):
        rows,edges=fixture()
        for row in rows:
            if row["_node_id"]=="sender":
                row["_start_order"]+=Decimal("1700000000000000.123")
                row["_stop_order"]+=Decimal("1700000000000000.123")
        item,=timing.analyze(rows,edges)["transfers"]
        self.assertEqual(item["protocol_duration_ns"],20000)

    def test_missing_sync_is_not_repaired(self):
        rows,edges=fixture()
        report=timing.analyze(rows,[e for e in edges if e["edge_id"]!="signal-done"])
        item,=report["transfers"]
        self.assertEqual(item["status"],"unresolved_protocol_interval")
        self.assertIsNone(item["protocol_duration_ns"])
        self.assertEqual(item["evidence_edge_ids"],[])

    def test_combined_payload_notify_uses_its_actual_sync_edge(self):
        rows,edges=fixture()
        edges=[edge for edge in edges if edge["edge_id"]!="payload-signal"]
        edges[-1].update(src="payload",edge_id="payload-done")
        item,=timing.analyze(rows,edges)["transfers"]
        self.assertEqual(item["status"],"protocol_interval_observed")
        self.assertEqual(item["evidence_node_ids"],["ready","ack","payload","done"])
        self.assertEqual(item["evidence_edge_ids"],["ready-ack","ack-payload","payload-done"])

    def test_ambiguous_notify_pair_is_not_partially_selected(self):
        rows,edges=fixture()
        edges.append(dict(edges[0],edge_id="second-ready"))
        item,=timing.analyze(rows,edges)["transfers"]
        self.assertEqual(item["issues"],["ambiguous_handshake_sync"])

    def test_local_order_fork_is_not_resolved_by_timestamps(self):
        rows,edges=fixture()
        extra=deepcopy(rows[1]);extra["_graph_id"]="other-ack";rows.append(extra)
        edges.append(dict(edges[1],src="other-ack",edge_id="other-order"))
        item,=timing.analyze(rows,edges)["transfers"]
        self.assertIn("ambiguous_stream_order",item["issues"])

    def test_receiver_device_rank_and_protocol_roles_must_match(self):
        for change in ({"_device_id":4},{"_user_rank":4},{"semantic":"link_rx_ack"}):
            with self.subTest(change=change):
                rows,edges=fixture();rows[-1].update(change)
                item,=timing.analyze(rows,edges)["transfers"]
                self.assertIsNone(item["protocol_duration_ns"])

    def test_wrong_operation_cannot_be_joined(self):
        rows,edges=fixture();rows[-1]["_operation_scope"]="other-call"
        item,=timing.analyze(rows,edges)["transfers"]
        self.assertIn("unsupported_cross_node_sync",item["issues"])

    def test_repeated_payload_is_not_assigned_individual_completion(self):
        rows,edges=fixture()
        extra=deepcopy(rows[2]);extra.update(_graph_id="another-payload",_start_order=Decimal(900003),_stop_order=Decimal(900003))
        rows.append(extra);edges[2]["dst"]="another-payload"
        edges.append(dict(edges[2],edge_id="batch-end",src="another-payload",dst="signal"))
        item=next(t for t in timing.analyze(rows,edges)["transfers"] if t["payload_graph_id"]=="payload")
        self.assertIn("another_payload_before_handshake_endpoint",item["issues"])

    def test_ffts_or_unsupported_confidence_stays_unresolved(self):
        for position,change in ((0,{"_subtask_id":0}),(2,{"_subtask_id":0}),(3,{"_subtask_id":0})):
            rows,edges=fixture();rows[position].update(change)
            self.assertEqual(timing.analyze(rows,edges)["summary"]["protocol_interval_count"],0)
        rows,edges=fixture();edges[-1]["confidence"]="semantic"
        self.assertEqual(timing.analyze(rows,edges)["summary"]["protocol_interval_count"],0)

    def test_reversed_receiver_time_and_local_overlap_are_rejected(self):
        for index,change in ((4,{"_start_order":Decimal(80),"_stop_order":Decimal(90)}),
                             (2,{"_start_order":Decimal(900001)})):
            rows,edges=fixture();rows[index].update(change)
            self.assertEqual(timing.analyze(rows,edges)["summary"]["protocol_interval_count"],0)

    def test_only_evidenced_payload_semantics_are_supported(self):
        rows,edges=fixture();rows[2]["semantic"]=""
        report=timing.analyze(rows,edges)
        self.assertEqual(report["summary"]["annotated_payload_count"],0)
        self.assertEqual(report["transfers"],[])

    def test_truncation_is_an_explicit_unresolved_reason(self):
        rows,edges=fixture()
        extra=deepcopy(rows[3]);extra.update(_graph_id="middle",semantic="",_start_order=Decimal(900003),_stop_order=Decimal(900003))
        rows.append(extra);edges[2]["dst"]="middle"
        edges.append(dict(edges[2],edge_id="middle-signal",src="middle",dst="signal"))
        item,=timing.analyze(rows,edges,max_hops=1)["transfers"]
        self.assertIn("stream_traversal_truncated",item["issues"])
        with self.assertRaises(ValueError):timing.analyze(rows,edges,max_hops=0)

    def test_duplicate_ids_and_missing_endpoints_are_errors(self):
        rows,edges=fixture()
        with self.assertRaises(ValueError):timing.analyze(rows+[rows[0]],edges)
        with self.assertRaises(ValueError):timing.analyze(rows,edges+[edges[0]])
        edges[0]["src"]="missing"
        with self.assertRaises(ValueError):timing.analyze(rows,edges)

    def test_exports_precise_time_and_safely_escaped_html(self):
        rows,edges=fixture();rows[0]["event"]="<script>alert(1)</script>"
        offset=Decimal("1700000000000000.123")
        for row in (rows[0],rows[-1]):
            row["_start_order"]+=offset;row["_stop_order"]+=offset
        report=timing.analyze(rows,edges)
        with tempfile.TemporaryDirectory() as temporary:
            directory=Path(temporary)/"new"
            timing.export_report(report,directory)
            decoded=json.loads((directory/"report.json").read_text())
            self.assertEqual(decoded["transfers"][0]["protocol_start_ns"],1700000000000100123)
            with (directory/"transfers.csv").open() as stream: item,=csv.DictReader(stream)
            self.assertEqual(item["protocol_duration_ns"],"20000")
            self.assertEqual(item["network_transfer_duration_ns"],"")
            page=(directory/"index.html").read_text()
            self.assertIn("不是纯 RDMA",page)
            self.assertNotIn("<script>alert",page)
            self.assertIn("&lt;script&gt;",page)
            self.assertNotIn("../execution.html",page)
            with self.assertRaises(FileExistsError):timing.export_report(report,directory)


if __name__=="__main__":
    unittest.main()
