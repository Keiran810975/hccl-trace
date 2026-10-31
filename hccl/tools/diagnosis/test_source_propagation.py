from __future__ import annotations

from copy import deepcopy
import csv
from decimal import Decimal
import json
from pathlib import Path
import tempfile
import unittest

from . import rolling_diagnosis as rolling
from . import source_propagation as propagation
from . import source_propagation_view as presentation
from .test_source_events import capture
from .test_wait_backtrace import cross_call_capture


def diagnosed(host=False):
    rows, edges, coordinates, preparations = capture(host_delay=host, execution_delay=not host)
    result = rolling.analyze(rows,edges,coordinates,preparations=preparations if host else ())
    roots = [r for r in result["root_causes"] if r["diagnosis_category"] != "unresolved_observation"]
    return rows,edges,roots,result["tasks"],result["primary_source_candidate_id"]


class SourcePropagationTests(unittest.TestCase):
    def build(self, values):
        rows,edges,roots,tasks,primary=values
        return propagation.build_report(rows,edges,roots,tasks,primary_source_candidate_id=primary)

    def test_starts_at_source_and_preserves_real_order_and_metrics(self):
        values=diagnosed()
        before=deepcopy(values)
        report=self.build(values)
        self.assertEqual(values,before)
        chain=report["candidates"][0]["chains"][0]
        self.assertEqual(chain["node_ids"],["i5p0","i5p1","i5p2"])
        self.assertEqual(chain["edge_ids"],["i5e0","i5e1"])
        self.assertTrue(chain["path_complete"])
        self.assertEqual(chain["evidence_confidence"],"observed")
        self.assertEqual(report["nodes"]["i5p0"]["comparison"]["reference_mean_ns"],"10000")
        self.assertFalse(report["physical_causation_proven"])

    def test_all_branches_are_kept_without_a_new_downstream_search(self):
        rows,edges,roots,tasks,primary=diagnosed()
        extra=deepcopy(next(r for r in rows if r["_graph_id"]=="i5p2"))
        extra.update(_graph_id="branch",_user_rank=2,_device_id=2)
        rows.append(extra)
        edge=deepcopy(next(e for e in edges if e["edge_id"]=="i5e1"))
        edge.update(edge_id="branch-sync",dst="branch")
        edges.append(edge)
        roots[0]["affected_wait_graph_ids"].append("branch")
        roots[0]["evidence_paths"]["branch"]=["i5e0","branch-sync"]
        report=self.build((rows,edges,roots,tasks,primary))
        self.assertEqual(report["summary"]["chain_count"],2)
        self.assertEqual(set(report["nodes"]),{"i5p0","i5p1","i5p2","branch"})
        self.assertFalse(report["exhaustive_downstream_search"])

    def test_existing_cross_call_path_is_not_clipped(self):
        rows,edges,coordinates=cross_call_capture()
        diagnosis=rolling.analyze(rows,edges,coordinates)
        roots=[r for r in diagnosis["root_causes"] if r["primary_eligible"]]
        report=propagation.build_report(rows,edges,roots,diagnosis["tasks"])
        chain=report["candidates"][0]["chains"][0]
        self.assertTrue(chain["path_complete"])
        self.assertNotEqual(report["nodes"][chain["node_ids"][0]]["operation_scope"],
                            report["nodes"][chain["node_ids"][-1]]["operation_scope"])

    def test_missing_edge_stays_a_boundary_and_is_not_repaired(self):
        rows,edges,roots,tasks,primary=diagnosed()
        edges=[e for e in edges if e["edge_id"]!="i5e1"]
        report=self.build((rows,edges,roots,tasks,primary))
        chain=report["candidates"][0]["chains"][0]
        self.assertFalse(chain["path_complete"])
        self.assertEqual(chain["node_ids"],["i5p0","i5p1"])
        self.assertEqual(chain["boundaries"][0]["reason"],"missing_artifact_edge")

    def test_disconnected_path_is_not_reordered(self):
        rows,edges,roots,tasks,primary=diagnosed()
        roots[0]["evidence_paths"]["i5p2"].reverse()
        chain=self.build((rows,edges,roots,tasks,primary))["candidates"][0]["chains"][0]
        self.assertEqual(chain["boundaries"][0]["reason"],"disconnected_path")
        self.assertEqual(chain["node_ids"],["i5p0"])

    def test_incompatible_notify_timestamps_are_shown(self):
        rows,edges,roots,tasks,primary=diagnosed()
        record=next(r for r in rows if r["_graph_id"]=="i5p1")
        record.update(_stop_order=Decimal("6000"),_stop=6000)
        chain=self.build((rows,edges,roots,tasks,primary))["candidates"][0]["chains"][0]
        self.assertTrue(chain["path_complete"])
        self.assertEqual(chain["status"],"complete_with_timing_limits")
        self.assertEqual(chain["hops"][-1]["timing_status"],"record_after_wait_end")

    def test_cross_node_clock_is_not_subtracted(self):
        rows,edges,roots,tasks,primary=diagnosed()
        for r in rows:
            if r["_user_rank"]==1:
                r["_node_id"]="run/node1"
                r["_start_order"]+=1000000000
                r["_stop_order"]+=1000000000
        chain=self.build((rows,edges,roots,tasks,primary))["candidates"][0]["chains"][0]
        self.assertTrue(chain["path_complete"])
        self.assertEqual(chain["hops"][-1]["timing_status"],"cross_node_uncalibrated")
        self.assertNotIn("end_to_end_latency_ns",chain)

    def test_ffts_path_is_not_presented_as_complete_hardware_timing(self):
        rows,edges,roots,tasks,primary=diagnosed()
        next(e for e in edges if e["edge_id"]=="i5e1")["kind"]="ffts_notify_sync_observed"
        chain=self.build((rows,edges,roots,tasks,primary))["candidates"][0]["chains"][0]
        self.assertTrue(chain["path_complete"])
        self.assertEqual(chain["status"],"complete_with_timing_limits")
        self.assertEqual(chain["hops"][-1]["timing_status"],"ffts_not_complete_hardware_dag")

    def test_host_interval_has_only_an_actual_device_anchor(self):
        report=self.build(diagnosed(host=True))
        root=report["candidates"][0]
        self.assertEqual(root["source"]["component"],"host_preparation")
        self.assertIsNone(root["source"]["task_id"])
        self.assertEqual(root["anchor_meaning"],"observed_device_anchor_only")
        self.assertEqual(root["chains"][0]["node_ids"],["i5p1","i5p2"])
        self.assertFalse(any(n["task_kind"]=="host_interval" for n in report["nodes"].values()))

    def test_host_branches_keep_their_distinct_actual_records(self):
        rows,edges,roots,tasks,primary=diagnosed(host=True)
        record=deepcopy(next(r for r in rows if r["_graph_id"]=="i5p1"))
        record.update(_graph_id="other-record",_stream_id=99)
        wait=deepcopy(next(r for r in rows if r["_graph_id"]=="i5p2"))
        wait.update(_graph_id="other-wait",_user_rank=2,_device_id=2)
        rows.extend([record,wait])
        edge=deepcopy(next(e for e in edges if e["edge_id"]=="i5e1"))
        edge.update(edge_id="other-sync",src="other-record",dst="other-wait")
        edges.append(edge)
        roots[0]["affected_wait_graph_ids"].append("other-wait")
        roots[0]["evidence_paths"]["other-wait"]=["other-sync"]
        report=self.build((rows,edges,roots,tasks,primary))
        chain=next(c for c in report["candidates"][0]["chains"] if c["target_wait_graph_id"]=="other-wait")
        self.assertTrue(chain["path_complete"])
        self.assertEqual(chain["node_ids"],["other-record","other-wait"])
        self.assertEqual(chain["edge_ids"],["other-sync"])
        self.assertEqual(report["candidates"][0]["anchor_graph_id"],"i5p1")

    def test_exports_readable_chain_and_structured_steps_without_overwrite(self):
        report=self.build(diagnosed())
        with tempfile.TemporaryDirectory() as temporary:
            directory=Path(temporary)/"out"
            propagation.export_report(report,directory)
            self.assertEqual(json.loads((directory/"report.json").read_text())["summary"]["complete_chain_count"],1)
            with (directory/"steps.csv").open() as stream:
                steps=list(csv.DictReader(stream))
            self.assertEqual([r["graph_id"] for r in steps],["i5p0","i5p1","i5p2"])
            self.assertIn("前5轮均值",(directory/"chains.md").read_text())
            page=(directory/"index.html").read_text()
            self.assertIn('id="flow"',page)
            self.assertIn('id="evidence"',page)
            self.assertIn("异常传播诊断",page)
            self.assertIn("等待",(directory/"chains.md").read_text())
            with self.assertRaises(FileExistsError):
                propagation.export_report(report,directory)

    def test_empty_candidate_report_is_an_explicit_empty_result(self):
        report=propagation.build_report([],[],[])
        self.assertEqual(report["summary"]["chain_count"],0)
        with tempfile.TemporaryDirectory() as temporary:
            propagation.export_report(report,Path(temporary)/"empty")

    def test_legacy_candidate_csv_literal_paths_are_parsed_not_evaluated(self):
        with tempfile.TemporaryDirectory() as temporary:
            path=Path(temporary)/"candidates.csv"
            with path.open("w",newline="") as stream:
                writer=csv.DictWriter(stream,fieldnames=["root_id","affected_wait_graph_ids","evidence_paths"])
                writer.writeheader()
                writer.writerow(dict(root_id="a",affected_wait_graph_ids=["wait"],evidence_paths={"wait":["a-b","b-w"]}))
            row,=propagation.load_csv_records(path,candidates=True)
            self.assertEqual(row["evidence_paths"],{"wait":["a-b","b-w"]})

    def test_display_retains_real_sync_endpoints_and_every_folded_node(self):
        report=self.build(diagnosed())
        chain=report["candidates"][0]["chains"][0]
        segments=presentation.compact_path(report,chain)
        self.assertEqual([identifier for segment in segments for identifier in segment["node_ids"]],chain["node_ids"])
        displayed={identifier for segment in segments if segment["kind"]=="task" for identifier in segment["node_ids"]}
        self.assertTrue({"i5p0","i5p1","i5p2"} <= displayed)
        self.assertIn("Rank 1",presentation.branch_summary(report,chain))
        self.assertIn("Rank 0",presentation.branch_summary(report,chain))

    def test_display_folds_only_ordinary_stream_interiors(self):
        report=self.build(diagnosed())
        chain=report["candidates"][0]["chains"][0]
        original=deepcopy(report["nodes"]["i5p0"])
        original["comparison"]["duration_slow"]=False
        for index in range(3):
            report["nodes"]["middle-{}".format(index)]=dict(original,graph_id="middle-{}".format(index))
        chain["node_ids"][1:1]=["middle-{}".format(i) for i in range(3)]
        chain["hops"][:1]=[dict(edge_id="fold-{}".format(i),src=src,dst=dst,
            kind="direct_stream_order_observed",confidence="observed")
            for i,(src,dst) in enumerate(zip(chain["node_ids"][:4],chain["node_ids"][1:5]))]
        segments=presentation.compact_path(report,chain)
        folded=[segment for segment in segments if segment["kind"]=="group"]
        self.assertEqual(folded[0]["node_ids"],["middle-0","middle-1","middle-2"])
        report["nodes"]["middle-1"]["comparison"]=dict(original["comparison"],duration_slow=True)
        self.assertTrue(any(segment["node_ids"]==["middle-1"] and segment["kind"]=="task"
                            for segment in presentation.compact_path(report,chain)))

    def test_display_never_connects_a_missing_target(self):
        rows,edges,roots,tasks,primary=diagnosed()
        report=self.build((rows,[e for e in edges if e["edge_id"]!="i5e1"],roots,tasks,primary))
        before=deepcopy(report)
        model=presentation.build_view_model(report)
        chain=model["candidates"][0]["chains"][0]
        self.assertNotIn("i5p2",[i for segment in chain["segments"] for i in segment["node_ids"]])
        self.assertIn("不能确认",chain["sentence"])
        self.assertEqual(report,before)

    def test_display_keeps_host_source_separate_from_record_anchor(self):
        report=self.build(diagnosed(host=True))
        model=presentation.build_view_model(report)
        self.assertEqual(model["candidates"][0]["source_label"],"Host 准备区间")
        chain=model["candidates"][0]["chains"][0]
        self.assertEqual(chain["segments"][0]["node_ids"],["i5p1"])
        self.assertIn("观测关联",presentation.render_html(report))

    def test_display_preserves_nanosecond_precision_and_escapes_script_data(self):
        report=self.build(diagnosed())
        value=1792985584867300411
        node=report["nodes"]["i5p0"]
        node.update(start_ns=value,stop_ns=value+99298,event="</script><img src=x onerror=alert(1)>")
        report["candidates"][0]["source"]["observed_start_ns"]=value
        model=presentation.build_view_model(report)
        self.assertEqual(model["nodes"]["i5p0"]["start_ns"],str(value))
        self.assertEqual(model["candidates"][0]["source"]["observed_start_ns"],str(value))
        page=presentation.render_html(report)
        self.assertNotIn("</script><img",page)
        self.assertIn("\\u003c/script\\u003e",page)
        self.assertEqual(page.count("</script>"),2)

    def test_display_keeps_cross_node_warning_and_no_latency_sum(self):
        rows,edges,roots,tasks,primary=diagnosed()
        next(row for row in rows if row["_graph_id"]=="i5p2")["_node_id"]="run/node2"
        report=self.build((rows,edges,roots,tasks,primary))
        model=presentation.build_view_model(report)
        chain=model["candidates"][0]["chains"][0]
        self.assertEqual(chain["status_label"],"路径连通 · 时间证据受限")
        self.assertEqual(chain["hops"][-1]["timing_status"],"cross_node_uncalibrated")
        self.assertNotIn("end_to_end_latency_ns",chain)
        self.assertIn("跨节点时钟未校准",model["timing_labels"][chain["hops"][-1]["timing_status"]])

    def test_concise_text_report_preserves_branches_and_limits(self):
        report=self.build(diagnosed())
        before=deepcopy(report)
        text=presentation.render_markdown(report)
        self.assertEqual(text.count("### 分支"),report["summary"]["chain_count"])
        self.assertIn("Rank 0",text)
        self.assertIn("Rank 1",text)
        self.assertIn("物理因果",text)
        self.assertIn("steps.csv",text)
        self.assertEqual(report,before)


if __name__=="__main__":
    unittest.main()
