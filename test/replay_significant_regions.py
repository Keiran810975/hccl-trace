#!/usr/bin/env python3
"""Replay region diagnosis from rolling facts and exact artifact edges; no truth input."""
from __future__ import annotations

import argparse
import csv
from dataclasses import asdict
import hashlib
import html
import json
from pathlib import Path
import sys

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from hccl.tools.diagnosis.significant_regions import RegionOptions, analyze


class JsonReader:
    """Read top-level array entries without materializing a multi-GB report."""
    def __init__(self, path):
        self.stream = path.open(encoding="utf-8-sig")
        self.buffer, self.offset, self.decoder = "", 0, json.JSONDecoder()

    def fill(self):
        self.buffer = self.buffer[self.offset:]
        self.offset = 0
        chunk = self.stream.read(65536)
        self.buffer += chunk
        return bool(chunk)

    def peek(self):
        while True:
            while self.offset < len(self.buffer) and self.buffer[self.offset].isspace():
                self.offset += 1
            if self.offset < len(self.buffer):
                return self.buffer[self.offset]
            if not self.fill():
                raise ValueError("unexpected JSON EOF")

    def expect(self, value):
        if self.peek() != value:
            raise ValueError("unexpected JSON delimiter")
        self.offset += 1

    def value(self):
        self.peek()
        while True:
            try:
                value, end = self.decoder.raw_decode(self.buffer, self.offset)
            except json.JSONDecodeError:
                if not self.fill():
                    raise
                continue
            if end == len(self.buffer):
                if self.fill():
                    continue
                self.offset = len(self.buffer)
                return value
            if self.buffer[end] not in ',]}: \t\r\n':
                if not self.fill():
                    raise ValueError("invalid JSON value terminator")
                continue
            self.offset = end
            return value

    def entries(self):
        try:
            self.expect("{")
            while self.peek() != "}":
                key = self.value()
                self.expect(":")
                if self.peek() == "[":
                    self.expect("[")
                    while self.peek() != "]":
                        yield key, self.value()
                        if self.peek() != "]":
                            self.expect(",")
                    self.expect("]")
                else:
                    yield key, self.value()
                if self.peek() != "}":
                    self.expect(",")
            self.expect("}")
        finally:
            self.stream.close()


FIELDS = ("graph_id", "node_id", "user_rank", "device_id", "stream_id", "task_id", "operation_scope",
    "stage", "iteration", "call_site", "task_kind", "task_domain", "phase", "step", "event",
    "duration_ns", "observed_start_ns", "observed_stop_ns", "reference_count", "reference_mean_ns",
    "reference_mad_ns", "delta_ns", "slowdown_factor", "reference_iterations", "comparison_status")
CLUSTER_FIELDS = FIELDS + ("reference_graph_ids",)


def digest(path):
    result = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024*1024), b""):
            result.update(chunk)
    return result.hexdigest()


def render(report):
    esc = lambda v: html.escape(str(v))
    def table(headers, rows):
        return "<table><thead><tr>"+"".join("<th>"+esc(h)+"</th>" for h in headers)+"</tr></thead><tbody>"+"".join(
            "<tr>"+"".join("<td>"+esc(v)+"</td>" for v in row)+"</tr>" for row in rows)+"</tbody></table>"
    regions = [r for r in report["regions"] if r["selected"]]
    body = "<h1>Significant communication regions</h1>" + table(
        ["Node", "Rank", "Iteration", "Operation", "Increase", "Slow work", "Selection"],
        [(r["node_id"], r["user_rank"], r["iteration"], r["operation_scope"],
          "{:.1%}".format(float(r["mean_increase"])), r["preliminary_count"], ", ".join(r["selection_reasons"])) for r in regions])
    if report.get("policy") == "local_dependency_clusters_v1":
        body += "<p>Cluster selection: {}. Ranking is not calibrated fault confidence.</p>".format(
            esc(report.get("cluster_selection", {}).get("policy", "score-band")))
        def cluster_table(items):
            return table(["Rank", "Iteration", "Tasks", "Evidence units", "Span (us)", "Density", "Core score", "With propagation", "Selected"],
                [(r["user_rank"], r["iteration"], r["preliminary_count"], r["evidence_unit_count"],
                  (r["stop_ns"]-r["start_ns"])/1000, "{:.1%}".format(float(r["temporal_density"])),
                  "{:.4f}".format(float(r["core_score"])), "{:.4f}".format(float(r["score"])), r["selected"]) for r in items])
        body += "<h2>Local cluster scores</h2>" + cluster_table(regions)
        body += "<details><summary>All clusters, including deferred observations</summary>"+cluster_table(report["regions"])+"</details>"
        body += "<p>Unexplained Wait observations: {}. They are retained, not execution-source candidates.</p>".format(
            report["summary"]["unexplained_wait_observation_count"])
    body += "<h2>Source candidates</h2>" + table(
        ["Rank", "Iteration", "Stream / Task", "Kind", "Duration (us)", "Previous five (us)", "Factor", "Status", "Slow Waits"],
        [(c["user_rank"], c["iteration"], "{} / {}".format(c["stream_id"], c["task_id"]), c["task_kind"],
          c["duration_ns"]/1000, float(c["reference_mean_ns"])/1000, c["slowdown_factor"], c["status"],
          len(c.get("affected_wait_graph_ids", []))) for c in report["candidates"]])
    links = {e["edge_id"]: e for e in report["edges"]}
    body += "<h2>Observed propagation paths</h2>"
    for chain in report["chains"]:
        source, target = report["nodes"][chain["source_graph_id"]], report["nodes"][chain["target_graph_id"]]
        ids = [chain["source_graph_id"]]+[links[key]["dst"] for key in chain["edge_ids"]]
        body += "<details><summary>Rank {} Task {} → Rank {} Wait {} ({:.2f}x), {} edges</summary>".format(
            source["user_rank"], esc(source["task_id"]), target["user_rank"], esc(target["task_id"]),
            float(chain["target_factor"]), len(chain["edge_ids"]))
        body += table(["Rank", "Stream / Task", "Kind", "Event", "Duration (us)", "Reference (us)", "Factor", "Incoming evidence"],
            [(report["nodes"][key]["user_rank"], "{} / {}".format(report["nodes"][key]["stream_id"], report["nodes"][key]["task_id"]),
              report["nodes"][key]["task_kind"], report["nodes"][key].get("event", ""), report["nodes"][key]["duration_ns"]/1000,
              float(report["nodes"][key]["reference_mean_ns"])/1000 if report["nodes"][key].get("reference_mean_ns") is not None else "unknown",
              report["nodes"][key].get("slowdown_factor"), links[chain["edge_ids"][i-1]]["kind"] if i else "source") for i,key in enumerate(ids)])
        body += "</details>"
    body += "<h2>Limits</h2><ul>" + "".join("<li>"+esc(s)+"</li>" for s in report["limits"])+"</ul>"
    return '<!doctype html><meta charset="utf-8"><title>Region diagnosis</title><style>body{font:14px system-ui;margin:24px;color:#17232a}table{border-collapse:collapse;width:100%;margin-bottom:24px}td,th{padding:8px;border-bottom:1px solid #d8dee3;text-align:left;overflow-wrap:anywhere}th{background:#edf3f7}details{margin:12px 0}summary{cursor:pointer;padding:8px;background:#edf3f7}</style>'+body


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rolling-report", type=Path, required=True)
    parser.add_argument("--edges", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--score-population", choices=("preliminary_work", "all_comparable_work"), default="preliminary_work")
    parser.add_argument("--region-mode", choices=("call", "local-clusters"), default="call")
    parser.add_argument("--cluster-selection", choices=("top1", "score-band"))
    args = parser.parse_args()
    if args.cluster_selection is not None and args.region_mode != "local-clusters":
        parser.error("cluster-selection requires local-clusters mode")
    args.out.mkdir(parents=True, exist_ok=False)
    runner = analyze
    fields = FIELDS
    modules = [Path(__file__).parents[1]/"hccl/tools/diagnosis/significant_regions.py"]
    if args.region_mode == "local-clusters":
        if args.score_population != "preliminary_work":
            parser.error("score-population is a call-region option, not a local-cluster option")
        from hccl.tools.diagnosis.local_slow_clusters import ClusterOptions, analyze as cluster_analyze
        options = ClusterOptions(selection_policy=args.cluster_selection or "top1")
        runner, fields = cluster_analyze, CLUSTER_FIELDS
        modules.append(Path(__file__).parents[1]/"hccl/tools/diagnosis/local_slow_clusters.py")
    else:
        options = RegionOptions(score_population=args.score_population)
    source = dict(rolling_report=str(args.rolling_report.resolve()), edges=str(args.edges.resolve()),
        rolling_sha256=digest(args.rolling_report), edges_sha256=digest(args.edges), options=asdict(options),
        algorithm_sha256={str(path): digest(path) for path in modules}, region_mode=args.region_mode,
        truth_accessed=False)
    (args.out/"input-manifest.json").write_text(json.dumps(source, indent=2)+"\n")
    tasks = []
    for key, item in JsonReader(args.rolling_report).entries():
        if key == "tasks":
            tasks.append({k: item.get(k) for k in fields})
    print("loaded {} immutable task comparisons".format(len(tasks)), flush=True)
    with args.edges.open(encoding="utf-8-sig", newline="") as stream:
        edges = [{k: e[k] for k in ("edge_id", "src", "dst", "kind", "confidence")} for e in csv.DictReader(stream)]
    print("loaded {} original edges".format(len(edges)), flush=True)
    report = runner(tasks, edges, options)
    report["inputs"] = source
    path = args.out/"report.json"
    path.write_text(json.dumps(report, indent=2, ensure_ascii=False)+"\n", encoding="utf-8")
    (args.out/"report.html").write_text(render(report), encoding="utf-8")
    print(json.dumps(report["summary"], ensure_ascii=False), flush=True)
    (args.out/"sealed.json").write_text(json.dumps(dict(report_sha256=digest(path), truth_accessed=False), indent=2)+"\n")


if __name__ == "__main__":
    main()
