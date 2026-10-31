from __future__ import annotations

from collections import defaultdict
import random
import unittest
from unittest.mock import patch

from . import resource_dependency_graph as graph


class ReachabilityTests(unittest.TestCase):
    def test_indexed_frontiers_equal_original_paths_for_branching_dags(self):
        rng = random.Random(20261030)
        for _ in range(25):
            rows = {str(i): dict(profiler_task_kind="sdma" if rng.random() < .25 else "notify_record") for i in range(12)}
            forward, reverse = defaultdict(list), defaultdict(list)
            for i in range(12):
                for j in range(i + 1, 12):
                    if rng.random() < .18:
                        edge = dict(src=str(i), dst=str(j), edge_id="{}-{}".format(i, j))
                        forward[str(i)].append(edge)
                        reverse[str(j)].append(edge)
            resources = {key for key, row in rows.items() if graph.is_resource_task(row)}
            for backwards, adjacency, inverse in ((False, forward, reverse), (True, reverse, forward)):
                reachable = graph._resource_reachable(resources, inverse, reverse=not backwards)
                for node in rows:
                    for stop in (True, False):
                        expected = graph._frontiers(node, adjacency, rows, backwards, stop)
                        actual = graph._frontiers(node, adjacency, rows, backwards, stop, reachable)
                        self.assertEqual(actual, expected)

    def test_resource_free_control_stream_is_not_walked_for_every_notify(self):
        rows = {str(i): dict(profiler_task_kind="notify_record") for i in range(1000)}
        with patch.object(graph, "is_resource_task", side_effect=AssertionError("dead control chain was scanned")):
            for i in range(1000):
                self.assertEqual(graph._frontiers(str(i), {}, rows, False, reachable=set()), {})


if __name__ == "__main__":
    unittest.main()
