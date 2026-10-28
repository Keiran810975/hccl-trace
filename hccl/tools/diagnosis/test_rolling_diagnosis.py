"""Past-only references and evidence-bounded sources without injection truth."""
from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import sys
import tempfile
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
    def test_sub_ten_microsecond_increase_is_detected(self):
        rows, edges, coords = repeated()
        report = rolling.analyze(rows, edges, coords)
        task = next(t for t in report["tasks"] if t["graph_id"] == "i5p0")
        self.assertEqual(task["reference_mean_ns"], "1000")
        self.assertEqual(task["delta_ns"], "1000")
        self.assertTrue(task["duration_slow"])
        root = next(r for r in report["root_causes"] if r["graph_id"] == "i5p0")
        self.assertEqual(root["status"], "dependency_supported_candidate")
        self.assertEqual(root["reference_iterations"], [0, 1, 2, 3, 4])
        self.assertFalse(any(k.startswith("baseline_") for k in root))

    def test_current_future_and_warmup_do_not_enter_reference(self):
        rows, edges, coords = repeated((999, 1, 2, 3, 4, 5, 10, 999))
        coords["op-0"].update(stage="warmup", iteration=0)
        for i in range(1, 8):
            coords["op-{}".format(i)]["iteration"] = i - 1
        report = rolling.analyze(rows, edges, coords)
        task = next(t for t in report["tasks"] if t["graph_id"] == "i6p0")
        self.assertEqual(task["reference_mean_ns"], "3000")
        self.assertEqual(task["reference_graph_ids"], ["i1p0", "i2p0", "i3p0", "i4p0", "i5p0"])

    def test_first_five_measured_iterations_are_unscored(self):
        report = rolling.analyze(*repeated((1, 1, 1, 1, 100)))
        self.assertEqual(report["status"], "no_comparable_history")
        self.assertEqual(report["root_causes"], [])
        self.assertEqual({t["comparison_status"] for t in report["tasks"]}, {"insufficient_history"})

    def test_missing_iteration_does_not_fall_back_to_older_sample(self):
        rows, edges, coords = repeated((1, 1, 1, 1, 1, 1, 10))
        del coords["op-3"]
        task = next(t for t in rolling.analyze(rows, edges, coords)["tasks"] if t["graph_id"] == "i6p0")
        self.assertEqual(task["comparison_status"], "missing_previous_iteration")
        self.assertFalse(task["is_slow"])

    def test_mean_not_median_and_mad_guard_remain(self):
        report = rolling.analyze(*repeated((1, 1, 1, 1, 6, 3)))
        task = next(t for t in report["tasks"] if t["graph_id"] == "i5p0")
        self.assertEqual(task["reference_mean_ns"], "2000")
        self.assertTrue(task["duration_slow"])
        noisy = rolling.analyze(*repeated((1, 2, 3, 4, 5, 5)))
        task = next(t for t in noisy["tasks"] if t["graph_id"] == "i5p0")
        self.assertFalse(task["duration_slow"])

    def test_zero_reference_does_not_flag_all_zero_tasks(self):
        options = rolling.RollingOptions()
        self.assertFalse(rolling._slow(0, 0, 0, options))
        self.assertTrue(rolling._slow(1, 0, 0, options))

    def test_same_block_and_bucket_only(self):
        rows, edges, coords = repeated()
        coords["op-2"]["bucket"] = 1
        report = rolling.analyze(rows, edges, coords)
        self.assertFalse(next(t for t in report["tasks"] if t["graph_id"] == "i5p0")["is_slow"])

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

    def test_report_exports_actual_five_history_panels(self):
        rows, edges, coords = repeated()
        report = rolling.analyze(rows, edges, coords)
        with tempfile.TemporaryDirectory() as temporary:
            out = Path(temporary) / "rolling"
            rolling.export_report(report, rows, edges, out)
            saved = json.loads((out / "report.json").read_text())
            self.assertTrue(saved["figures"])
            self.assertTrue((out / "focus-001-current.html").exists())
            for i in range(5):
                self.assertTrue((out / "focus-001-iteration-{}.svg".format(i)).exists())
            self.assertNotIn("baseline_median_ns", (out / "report.json").read_text())
            with self.assertRaises(FileExistsError):
                rolling.export_report(report, rows, edges, out)


if __name__ == "__main__":
    unittest.main()
