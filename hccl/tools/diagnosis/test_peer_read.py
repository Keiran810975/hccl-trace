from __future__ import annotations

from decimal import Decimal
import unittest

from . import rolling_diagnosis as rolling
from .result_normalizer import normalize
from .test_source_events import capture


def ring_capture(*, reader_local_slow=False, peer_local_slow=True, split_nodes=False,
                 missing_control=False, shared_read_slow=False, reduce=False, wrong_peer=False):
    rows, edges, coordinates, _ = capture(execution_delay=True)
    for i in range(6):
        read, record, wait, tail = rows[i * 4:i * 4 + 4]
        for row, rank in ((read, 1), (record, 1), (wait, 2), (tail, 2)):
            row.update(_user_rank=rank, _device_id=rank, _peer_rank=rank-1)
        phase = "reduce_scatter_direct" if reduce else "allgather_direct"
        event = "rx_payload_reduce_start" if reduce else "rx_payload_copy_start"
        kind = "reduce_inline" if reduce else "sdma"
        semantic = "link_rx_payload_reduce" if reduce else "link_rx_payload_copy"
        read.update(algorithm="single_ring_direct", phase=phase, event=event, semantic=semantic,
                    profiler_task_kind=kind, _step=0, _rank_size=4, comm_rank="1",
                    _operation_scope_status="unique", match_confidence="exact")
        if wrong_peer:
            read["_peer_rank"] = 3
        for rank in (0, 2, 3):
            length = 40 if i == 5 and rank == 3 and shared_read_slow else 10
            rows.append(dict(read, _graph_id=f"read-{i}-{rank}", _user_rank=rank, _device_id=rank,
                _peer_rank=(rank-1) % 4, comm_rank=str(rank), slice=str(rank), _duration=length,
                _node_id="run/other" if split_nodes and rank == 3 else "run/node0",
                _stop=read["_start"]+length, _stop_order=read["_start_order"]+length))
        for rank, enabled in ((0, peer_local_slow), (1, reader_local_slow)):
            if rank == 1 and missing_control:
                continue
            length = 35 if enabled and i == 5 else 10
            start = i * 1000 + 80
            rows.append(dict(read, _graph_id=f"input-{i}-{rank}", _user_rank=rank, _device_id=rank,
                _stream_id=97, _peer_rank=0xffffffff, _duration=length,
                phase="reduce_scatter_direct", event="copy_start", semantic="user_to_ccl_copy",
                profiler_task_kind="sdma", comm_rank=str(rank), _start=start, _stop=start+length,
                _start_order=Decimal(start), _stop_order=Decimal(start+length)))
    return rows, edges, coordinates


class PeerReadTests(unittest.TestCase):
    def analyze(self, **kwargs):
        rows, edges, coordinates = ring_capture(**kwargs)
        report = rolling.analyze(rows, edges, coordinates, rolling.RollingOptions())
        return rows, edges, report

    def test_directional_read_is_separate_from_notify_causality(self):
        for reduce in (False, True):
            with self.subTest(reduce=reduce):
                rows, edges, report = self.analyze(reduce=reduce)
                observation, = report["peer_read_observations"]
                self.assertEqual(report["root_causes"], [])
                self.assertEqual(report["source_regions"], [])
                self.assertEqual(report["diagnosis_status"], "suspected_peer_read_impact")
                self.assertEqual((observation["reader"]["user_rank"], observation["peer"]["user_rank"]), (1, 0))
                self.assertEqual(observation["downstream_wait_paths"], {"i5p2": ["i5e0", "i5e1"]})
                self.assertEqual(observation["peer_local_slow_copies"][0]["graph_id"], "input-5-0")
                self.assertFalse(observation["physical_cause_proven"])
                self.assertEqual(len(edges), 18)
                normalized, roots, _ = normalize(report, mode="rolling", run_id="fixture",
                    rows=rows, edges=edges, pipeline={"status": "passed"}, binding_evidence={})
                self.assertEqual(normalized["candidates"], [])
                self.assertEqual(roots, [])
                self.assertEqual(normalized["peer_read_observations"], [observation])

    def test_reader_local_confounds_do_not_remove_candidate(self):
        for setting, reason in (("reader_local_slow", "retained_reader_local_slowdown"),
                                ("missing_control", "retained_reader_local_control_incomplete")):
            with self.subTest(setting=setting):
                _, _, report = self.analyze(**{setting: True})
                self.assertEqual([r["graph_id"] for r in report["root_causes"]], ["i5p0"])
                self.assertEqual([o["disposition"] for o in report["peer_read_observations"]], [reason])

    def test_no_inference_with_missing_peer_witness_or_direction(self):
        for settings in (dict(peer_local_slow=False), dict(split_nodes=True),
                         dict(shared_read_slow=True), dict(wrong_peer=True)):
            with self.subTest(settings=settings):
                _, _, report = self.analyze(**settings)
                self.assertEqual([r["graph_id"] for r in report["root_causes"]], ["i5p0"])
                self.assertEqual(report["peer_read_observations"], [])
