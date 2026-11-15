from __future__ import annotations

from collections import defaultdict
import unittest

from .stage_events import StageEvents, statistics, temporal_status


def ref(*values):
    return [{"iteration": i, "duration_ns": v} for i,v in enumerate(values)]


class StageEventTests(unittest.TestCase):
    def test_statistics_checks_mad_and_the_historical_maximum(self):
        low = ref(101_000,102_000,90_000,100_000,98_000)
        severe = statistics(2_000_000,low)
        self.assertTrue(severe["strong"])
        self.assertEqual(severe["median_ns"],100_000)
        self.assertEqual(severe["historical_max_ns"],102_000)
        self.assertEqual(severe["mad_ns"],2_000)
        self.assertIsNone(statistics(2_000_000,ref(100_000,100_000,100_000,100_000,1_950_000)))
        self.assertIsNone(statistics(2_000_000,low[:4]))

    def test_only_positive_overlap_counts_and_uncertainty_is_not_a_hit(self):
        a = (10,30)
        self.assertEqual(temporal_status(a,(30,40),0),"disjoint")
        self.assertEqual(temporal_status(a,(29,40),0),"definite")
        self.assertEqual(temporal_status(a,(29,40),2),"possible")
        self.assertEqual(temporal_status(a,(31,40),2),"possible")
        self.assertEqual(temporal_status(a,(32,40),2),"disjoint")
        self.assertEqual(temporal_status(a,(15,20),None),"undetermined")

    def test_merge_requires_physical_link_and_weak_stage_needs_support(self):
        r = StageEvents.__new__(StageEvents)
        r.by_anchor = {}
        def stage(a,b,strong,downstream=()):
            return dict(node_id="n",device_id=0,rank=0,iteration=2,kind="task_execution",
                        interval_ns=(a,b),uncertainty_ns=0,statistics=dict(strong=strong),
                        downstream=downstream)
        r.stages = {
            0:stage(100,200,True), 1:stage(150,220,True),
            2:stage(220,300,False,("proof",)), 3:stage(300,400,False),
        }
        r.links=defaultdict(dict,{1:{2:dict(kind="physical",evidence="shared")},
                                  2:{1:dict(kind="physical",evidence="shared")}})
        events = r.report()
        self.assertEqual([e["interval_ns"] for e in events],[(100,200),(150,300)])
        self.assertEqual([len(e["stages"]) for e in events],[1,2])


if __name__ == "__main__":
    unittest.main()
