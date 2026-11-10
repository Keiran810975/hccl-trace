"""Past-only references and evidence-bounded sources without injection truth."""
from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import sys
import unittest

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from diagnosis import rolling_diagnosis as rolling
    from diagnosis.test_compare_diagnosis import fixture
else:
    from . import rolling_diagnosis as rolling
    from .test_compare_diagnosis import fixture


def repeated(durations=(1, 1, 1, 1, 1, 2)):
    original, original_edges, _, _ = fixture()
    rows, edges, coords = [], [], []
    for iteration, length in enumerate(durations):
        group = deepcopy(original)
        origin = iteration * 10000 + 100
        times = [(origin, origin + length), (origin + length, origin + length + .001),
                 (origin + .1, origin + length + .1), (origin + length + .1, origin + length + .3)]
        for index, (row, (start, stop)) in enumerate(zip(group, times)):
            row.update(_graph_id="i{}p{}".format(iteration, index), _operation_scope="op-{}".format(iteration),
                       _start=start, _stop=stop, _duration=stop - start)
        rows.extend(group)
        edges.extend(dict(e, src="i{}{}".format(iteration, e["src"]),
                          dst="i{}{}".format(iteration, e["dst"]),
                          edge_id="i{}{}".format(iteration, e["edge_id"])) for e in original_edges)
        coords.append(dict(operation_scope="op-{}".format(iteration), stage="measured", iteration=iteration,
                           block=0, bucket=0, evidence="synthetic public call-to-DB binding"))
    return rows, edges, rolling.validate_coordinates(coords)


class RollingTests(unittest.TestCase):
    def test_backtrace_replaces_flagged_history_for_only_the_affected_task(self):
        rows, edges, coords = repeated((1, 1, 1, 1, 1, 4, 1, 2))
        tasks = {t["graph_id"]: t for t in rolling.compare_tasks(
            list(reversed(rows)), edges, coords, rolling.RollingOptions())}
        self.assertTrue(tasks["i5p0"]["duration_slow"])
        self.assertEqual(tasks["i6p0"]["reference_iterations"], [0, 1, 2, 3, 4])
        self.assertEqual(tasks["i7p0"]["reference_iterations"], [1, 2, 3, 4, 6])
        self.assertEqual(tasks["i7p0"]["reference_mean_ns"], "1000")
        self.assertEqual(tasks["i7p1"]["reference_iterations"], [2, 3, 4, 5, 6])

    def test_backtrace_uses_fewer_samples_and_excludes_warmup(self):
        rows, edges, coords = repeated((99, 1, 4, 1, 2))
        coords["op-0"]["stage"] = "warmup"
        tasks = {t["graph_id"]: t for t in rolling.compare_tasks(
            rows, edges, coords, rolling.RollingOptions())}
        self.assertEqual(tasks["i0p0"]["comparison_status"], "warmup_excluded")
        self.assertEqual(tasks["i1p0"]["reference_count"], 0)
        self.assertEqual(tasks["i2p0"]["reference_count"], 1)
        self.assertTrue(tasks["i2p0"]["duration_slow"])
        self.assertEqual(tasks["i3p0"]["reference_graph_ids"], ["i1p0"])
        self.assertEqual(tasks["i4p0"]["reference_graph_ids"], ["i1p0", "i3p0"])

    def test_backtrace_excludes_flagged_gap_even_when_execution_is_normal(self):
        rows, edges, coords = repeated((1, 1, 1, 1, 1, 1, 1))
        row = next(r for r in rows if r["_graph_id"] == "i5p3")
        row["_start"] += 10
        row["_stop"] += 10
        tasks = {t["graph_id"]: t for t in rolling.compare_tasks(
            rows, edges, coords, rolling.RollingOptions())}
        self.assertFalse(tasks["i5p3"]["duration_slow"])
        self.assertTrue(tasks["i5p3"]["gap_slow"])
        self.assertEqual(tasks["i6p3"]["reference_iterations"], [0, 1, 2, 3, 4])

    def test_backtrace_does_not_backfill_with_a_different_operation_shape(self):
        rows, edges, coords = repeated((1, 1, 1, 4, 1, 1))
        row = next(r for r in rows if r["_graph_id"] == "i2p3")
        row["event"] = "different_structure"
        tasks = {t["graph_id"]: t for t in rolling.compare_tasks(
            rows, edges, coords, rolling.RollingOptions())}
        self.assertEqual(tasks["i2p0"]["reference_count"], 0)
        self.assertEqual(tasks["i5p0"]["reference_graph_ids"], ["i0p0", "i1p0", "i4p0"])

    def test_sub_ten_microsecond_increase_is_detected(self):
        rows, edges, coords = repeated()
        tasks = rolling.compare_tasks(rows, edges, coords, rolling.RollingOptions())
        task = next(t for t in tasks if t["graph_id"] == "i5p0")
        self.assertEqual(task["reference_mean_ns"], "1000")
        self.assertEqual(task["delta_ns"], "1000")
        self.assertTrue(task["duration_slow"])
        self.assertEqual(task["reference_iterations"], [0, 1, 2, 3, 4])

    def test_zero_reference_does_not_flag_all_zero_tasks(self):
        options = rolling.RollingOptions()
        self.assertFalse(rolling._slow(0, 0, 0, options))
        self.assertTrue(rolling._slow(1, 0, 0, options))

    def test_duplicate_semantic_location_is_not_ordinal_matched(self):
        rows, edges, coords = repeated()
        for i in range(6):
            duplicate = deepcopy(rows[i * 4])
            duplicate["_graph_id"] = "duplicate{}".format(i)
            rows.append(duplicate)
        report = rolling.analyze(rows, edges, coords)
        self.assertEqual(next(t for t in report["tasks"] if t["graph_id"] == "i5p0")["comparison_status"], "ambiguous_task_location")

    def test_truth_and_duplicate_binding_are_rejected(self):
        _, _, coords = repeated()
        values = list(coords.values())
        with self.assertRaises(ValueError):
            rolling.validate_coordinates([dict(values[0], injection_kind="delay")])
        with self.assertRaises(ValueError):
            rolling.validate_coordinates(values + [dict(values[0], operation_scope="another")])

if __name__ == "__main__":
    unittest.main()
