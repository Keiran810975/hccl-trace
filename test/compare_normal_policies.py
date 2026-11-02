"""Compare archived and current consumers on the same fixed normal graph windows."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys


CHILD = r'''
import json,sys,hashlib
from pathlib import Path
engine,base,end,output,intervals=sys.argv[1:]
sys.path.insert(0,engine)
from hccl.tools.diagnosis import rolling_diagnosis as rolling
from hccl.tools.diagnosis import visualize_dependency_graph as graph
base=Path(base);end=int(end);folder=base/('iteration-'+str(end))
rows=graph.read_graph_artifact_nodes(folder/'dep_graph_nodes.csv')
edges=graph.read_graph_artifact_edges(folder/'dep_graph_edges.csv')
current=base/'inputs/report.debug/current'
coords={k:v for k,v in rolling.load_coordinates(current/'iteration-map.json').items()
        if v['stage']=='measured' and end-5<=v['iteration']<=end}
clock=next((base/'inputs/report.debug/analysis').glob('*/clock_alignment.json'))
options=rolling.RollingOptions(max_figures=0,**({'calibrated_release_intervals':True} if intervals=='1' else {}))
report=rolling.analyze(rows,edges,coords,options,preparations=(),alignment=json.loads(clock.read_text()))
roots=[r for r in report['root_causes'] if r['diagnosis_category']=='communication_source_candidate']
comparisons=sorted((t['graph_id'],t['comparison_status'],t['reference_count'],t['reference_mean_ns'],
                   t['reference_mad_ns'],t['duration_slow'],t['gap_slow'],t['observed_start_ns'],t['observed_stop_ns']) for t in report['tasks'])
result=dict(engine=rolling.__file__,source_policy_version=report['source_policy_version'],selected_iteration=end,
            root_count=len(roots),root_ids=[r['root_id'] for r in roots],
            roots=roots,coverage=report['coverage'],
            task_comparisons_sha256=hashlib.sha256(json.dumps(comparisons).encode()).hexdigest())
Path(output).write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps({k:v for k,v in result.items() if k not in {'roots','root_ids'}}),flush=True)
'''


def compare(base, output):
    output.mkdir(parents=True, exist_ok=False)
    repository = Path(__file__).resolve().parents[1]
    snapshot = output / "current-engine"
    hashes = {}
    sources = [repository / "hccl/__init__.py", *sorted((repository / "hccl/tools/diagnosis").glob("*.py"))]
    for source in sources:
        relative = source.relative_to(repository)
        target = snapshot / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        hashes[str(relative)] = hashlib.sha256(target.read_bytes()).hexdigest()
        if hashes[str(relative)] != hashlib.sha256(source.read_bytes()).hexdigest():
            raise ValueError("consumer changed while making audit snapshot")
    (output / "consumer-snapshot.json").write_text(json.dumps(hashes, indent=2) + "\n")
    engines = [("archived-policy6", base / "frozen-policy6/src", False),
               ("current-strict", snapshot, False),
               ("current-calibrated", snapshot, True)]
    results = []
    for name, engine, intervals in engines:
        for end in (10, 45):
            path = output / (name + "-" + str(end) + ".json")
            subprocess.run([sys.executable, "-c", CHILD, str(engine.resolve()), str(base.resolve()), str(end),
                            str(path.resolve()), str(int(intervals))], check=True, timeout=240)
            result = json.loads(path.read_text())
            results.append(dict(variant=name, iteration=end, count=result["root_count"],
                                task_comparisons_sha256=result["task_comparisons_sha256"]))
    for end in (10, 45):
        if len({r["task_comparisons_sha256"] for r in results if r["iteration"] == end}) != 1:
            raise ValueError("task detector observations differ; policies cannot be compared as backtrace-only variants")
    receipt = dict(full_workload_replay=False, normal_windows=[10, 45], original_detector_results_identical=True,
                   truth_consumed=False, results=results)
    (output / "summary.json").write_text(json.dumps(receipt, indent=2) + "\n")
    return receipt


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    compare(args.base, args.output)
