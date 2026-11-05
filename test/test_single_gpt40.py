from __future__ import annotations

from collections import Counter
import json
from pathlib import Path
import tempfile
import unittest

from .run_single_gpt40 import plan, overlap, summarize, digest_case
from .node03_device_guard import scope
from .stop_owned_capture import owned_processes


class SingleGpt40Tests(unittest.TestCase):
    def test_frozen_independent_interleaved_cases_and_successful_strengths(self):
        p=plan()
        self.assertEqual(p,plan())
        self.assertEqual(len(p["cases"]),40)
        self.assertEqual(Counter(e["case"]["injection"]["kind"] for e in p["cases"]),
            dict(copy_contention=10,communication_contention=10,compute_contention=10,progress_delay=10))
        self.assertEqual(len({e["root"] for e in p["cases"]}),40)
        for i,e in enumerate(p["cases"]):
            c=e["case"]; inj=c["injection"]
            self.assertEqual(inj["kind"],p["cases"][i%4]["case"]["injection"]["kind"])
            self.assertEqual((c["workload"]["warmup"],c["workload"]["iters"]),(10,50))
            self.assertTrue(10 <= inj["iteration"] < 40)
            self.assertTrue(0 <= inj["target_rank"] < 4)
            self.assertEqual(inj["duration_iters"],1)
            if inj["kind"]=="copy_contention":
                self.assertEqual((inj["buffer_mib"],inj["operations"]),(2048,4))
            elif inj["kind"]=="communication_contention":
                self.assertEqual(inj["buffer_mib"],1024)
                self.assertEqual(set(inj["declared_affected_ranks"]),{inj["target_rank"],inj["peer_rank"]})
                self.assertNotEqual(inj["target_rank"],inj["peer_rank"])
            elif inj["kind"]=="compute_contention":
                self.assertEqual(inj["matrix_size"],8192)
            else:
                self.assertEqual(inj["delay_ms"],500)
            import hashlib
            self.assertEqual(digest_case(c),hashlib.sha256((json.dumps(c,indent=2)+"\n").encode()).hexdigest())

    def test_scope_stays_node0_and_exact_reviewed_batch(self):
        for number in (600,601,640):
            p=Path("/home/commTeam/zjy/zjy-new-workspace/hccl-diagnose-single-20261103-"+str(number))
            self.assertEqual(scope(p,"liteserver-560t-0"),p.resolve())
            with self.assertRaises(ValueError):
                scope(Path("/home/zjy-new/workspace")/p.name,"liteserver-560t-3")
        with self.assertRaises(ValueError):
            scope(Path("/home/commTeam/zjy/zjy-new-workspace/hccl-diagnose-single-20261103-700"),"liteserver-560t-0")

    def test_boundary_touch_or_wrong_rank_is_not_a_hit(self):
        source=dict(node_id="n",user_rank=1,observed_start_ns=10,observed_stop_ns=20)
        self.assertEqual(overlap(source,[dict(node_id="n",target_ranks=[1],start_ns=20,stop_ns=30)]),0)
        self.assertEqual(overlap(source,[dict(node_id="n",target_ranks=[0],start_ns=10,stop_ns=20)]),0)
        self.assertEqual(overlap(source,[dict(node_id="other",target_ranks=[1],start_ns=10,stop_ns=20)]),0)
        self.assertEqual(overlap(source,[dict(node_id="n",target_ranks=[1],start_ns=19,stop_ns=30)]),1)

    def test_native_diagnosis_cleanup_is_only_this_attempt(self):
        base="/workspace/hccl-diagnose-single-20261103-601"
        processes={1:dict(parent=0,ticks="1",argv=[base+"/src/test/diagnose_single_gpt40.py"]),
                   2:dict(parent=0,ticks="2",argv=["/workspace/other/src/test/diagnose_single_gpt40.py"])}
        self.assertEqual(set(owned_processes(processes,base)),{1})

    def test_zero_candidates_do_not_become_success_or_full_completion(self):
        with tempfile.TemporaryDirectory() as directory:
            result=summarize(Path(directory),[dict(case_id="empty",kind="copy_contention",candidate_count=0,hits=0,
                any_candidate_hit=False,primary_hit=False,primary_target_rank_hits=0,candidate_hit_fraction=None,
                actual_communication_slowing_observed=False,execution_tasks=dict(hits=0,count=0),host_intervals=dict(hits=0,count=0))])
            self.assertEqual(result["status"],"partial")
            group=result["groups"]["copy_contention"]
            self.assertEqual(group["zero_candidate_cases"],1)
            self.assertEqual(group["cases_with_any_hit"],0)
            self.assertIsNone(group["candidate_hit_fraction"])
            self.assertEqual(group["requested"],10)

    def test_batch_uses_same_single_source_selection_as_successful_development_cases(self):
        from hccl.tools.diagnosis import rolling_diagnosis as rolling, source_selection
        from hccl.tools.diagnosis.local_slow_clusters import analyze, ClusterOptions
        from hccl.tools.diagnosis.multinode_source_policy import select
        from hccl.tools.diagnosis.test_source_events import capture
        for host in (False,True):
            rows,edges,coordinates,preparations=capture(host_delay=host,execution_delay=not host)
            report=rolling.analyze(rows,edges,coordinates,rolling.RollingOptions(source_policy="dual"),
                preparations=preparations if host else ())
            observations=[r for r in report["root_causes"] if r["component"]=="host_preparation"]
            old=source_selection.select_sources(analyze(report["tasks"],edges,ClusterOptions()),observations)
            _,current=select(report,rows,edges,None)
            self.assertEqual([c["candidate_id"] for c in old["candidates"]],
                             [c["candidate_id"] for c in current["candidates"]])
            self.assertEqual(old["selected_mechanism"],current["selected_mechanism"])

    def test_native_publication_with_sqlite_facts_keeps_input_read_only(self):
        import shutil
        from hccl.tools.diagnosis.test_tool_cli import sdk_capture,hashes
        from hccl.tools.diagnosis.capture_discovery import discover_capture
        from hccl.tools.diagnosis.workload_binder import bind_capture
        from .diagnose_single_gpt40 import diagnose
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory); capture=sdk_capture(root/"capture")
            bound=bind_capture(discover_capture(capture,root/"discovery"),root/"binding",mode="rolling")
            shutil.copy2(bound.manifest,capture/"manifest.json")
            shutil.copy2(bound.iteration_map,capture/"iteration-map.json")
            (capture/"preparation-map.json").write_text(json.dumps(dict(schema_version=1,preparations=[])))
            (capture/"binding-evidence.json").write_text(json.dumps(bound.evidence))
            before=hashes(capture)
            diagnose(capture,root/"diagnosis")
            self.assertEqual(hashes(capture),before)
            self.assertEqual({p.name for p in (root/"diagnosis/report").iterdir()},
                             {"execution.html","root_causes.json","propagation.html"})


if __name__=="__main__":
    unittest.main()
