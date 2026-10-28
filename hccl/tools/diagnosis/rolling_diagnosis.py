#!/usr/bin/env python3
"""Past-five-iteration comparison over evidenced workload call coordinates."""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from decimal import Decimal
import html
import json
import os
from pathlib import Path
import sys

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from diagnosis import compare_diagnosis as comparison
    from diagnosis import analyze_waits as waits
    from diagnosis import visualize_dependency_graph as graph
    from diagnosis import visualize_html as view
    from diagnosis import source_events
    from diagnosis import wait_backtrace
    from diagnosis.schema import write_csv
else:
    from . import compare_diagnosis as comparison
    from . import analyze_waits as waits
    from . import visualize_dependency_graph as graph
    from . import visualize_html as view
    from . import source_events
    from . import wait_backtrace
    from .schema import write_csv


@dataclass(frozen=True)
class RollingOptions:
    window: int = 5
    slowdown_factor: str = "1.5"
    mad_multiplier: str = "3"
    context_ns: int = 100000
    max_figures: int = 5
    traversal_limit: int = 4096

    def validate(self):
        if self.window != 5:
            raise ValueError("the rolling reference requires exactly five iterations")
        factor, multiplier = Decimal(self.slowdown_factor), Decimal(self.mad_multiplier)
        if not factor.is_finite() or factor <= 1 or not multiplier.is_finite() or multiplier < 0:
            raise ValueError("finite slowdown > 1 and nonnegative MAD multiplier required")
        if self.context_ns < 0 or self.max_figures < 0 or self.traversal_limit <= 0:
            raise ValueError("invalid rolling report limits")


def validate_coordinates(records):
    result, slots = {}, set()
    allowed = {"operation_scope", "stage", "iteration", "block", "bucket", "evidence"}
    for item in records:
        if set(item) - allowed:
            raise ValueError("call coordinates must contain only public workload binding fields")
        scope = item.get("operation_scope")
        stage = item.get("stage")
        if not scope or scope in result or stage not in {"warmup", "measured"}:
            raise ValueError("unique scopes and explicit warmup/measured stage required")
        if any(type(item.get(k)) is not int or item[k] < 0 for k in ("iteration", "block", "bucket")):
            raise ValueError("call coordinates must be nonnegative integers")
        if not str(item.get("evidence", "")).strip():
            raise ValueError("workload-to-DB binding needs independent capture evidence")
        slot = (stage, item["iteration"], item["block"], item["bucket"])
        if slot in slots:
            raise ValueError("more than one operation bound to one workload call")
        slots.add(slot)
        result[scope] = dict(item)
    return result


def load_coordinates(path):
    data = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    if set(data) != {"schema_version", "operations"} or data["schema_version"] != 1:
        raise ValueError("expected public call map schema 1, without injection information")
    return validate_coordinates(data["operations"])


def _statistics(values):
    values = [Decimal(v) for v in values]
    center = sum(values) / len(values)
    median = comparison.median(values)
    return center, comparison.median([abs(v - median) for v in values])


def _slow(value, center, mad, options):
    # No absolute increase floor. The current value never enters its reference.
    value = Decimal(value)
    return (value > center and value >= center * Decimal(options.slowdown_factor)
            and value - center >= Decimal(options.mad_multiplier) * mad)


def compare_tasks(rows, edges, coordinates, options):
    groups, by_slot = comparison.operation_groups(rows), {}
    unknown = set(coordinates) - set(groups)
    if unknown:
        raise ValueError("call map references unknown execution operations")
    for scope, coord in coordinates.items():
        if coord["stage"] == "measured":
            by_slot[(coord["iteration"], coord["block"], coord["bucket"])] = scope
    gaps = comparison.local_gaps(rows, edges)
    origins = {}
    for row in rows:
        key = row.get("_operation_scope", ""), row["_node_id"]
        origins[key] = min(origins.get(key, waits.ns(row, "start")), waits.ns(row, "start"))
    signatures = {scope: defaultdict(list) for scope in groups}
    shapes = {scope: comparison.operation_shape(group) for scope, group in groups.items()}
    for scope, group in groups.items():
        for row in group:
            signatures[scope][comparison.task_signature(row)].append(row)
    tasks = []
    for row in rows:
        scope, key = row.get("_operation_scope", ""), comparison.task_signature(row)
        coord = coordinates.get(scope)
        task = dict(graph_id=row["_graph_id"], node_id=row["_node_id"],
                    user_rank=row["_user_rank"], device_id=row["_device_id"],
                    stream_id=row["_stream_id"], task_id=row["_task_id"], operation_scope=scope,
                    algorithm=row.get("algorithm", ""), phase=row.get("phase", ""),
                    step=row.get("step", ""), event=row.get("event", ""),
                    task_kind=row.get("profiler_task_kind", ""),
                    observed_start_ns=waits.ns(row, "start"), observed_stop_ns=waits.ns(row, "stop"),
                    duration_ns=waits.duration(row), gap_before_ns=gaps.get(row["_graph_id"]),
                    start_offset_ns=waits.ns(row, "start") - origins[(scope, row["_node_id"])],
                    reference_start_offset_mean_ns=None, reference_start_offset_mad_ns=None,
                    start_delta_ns=None, start_late=None,
                    stage=coord["stage"] if coord else "unbound", iteration=coord["iteration"] if coord else None,
                    block=coord["block"] if coord else None, bucket=coord["bucket"] if coord else None,
                    comparison_status="unbound_operation", reference_iterations=[], reference_graph_ids=[],
                    reference_operation_scopes=[], reference_count=0, reference_mean_ns=None,
                    reference_mad_ns=None, reference_gap_mean_ns=None, reference_gap_mad_ns=None,
                    reference_graph_id="", reference_operation_scope="", reference_evidence="",
                    delta_ns=None, gap_delta_ns=None, slowdown_factor=None,
                    duration_slow=False, gap_slow=False, is_slow=False)
        tasks.append(task)
        if not coord:
            continue
        if coord["stage"] != "measured":
            task["comparison_status"] = "warmup_excluded"
            continue
        if coord["iteration"] < options.window:
            task["comparison_status"] = "insufficient_history"
            continue
        if not all(row.get(field, "") for field in ("algorithm", "phase", "event")):
            task["comparison_status"] = "unannotated_task_location"
            continue
        if len(signatures[scope][key]) != 1:
            task["comparison_status"] = "ambiguous_task_location"
            continue
        iterations = list(range(coord["iteration"] - options.window, coord["iteration"]))
        history_scopes = [by_slot.get((i, coord["block"], coord["bucket"])) for i in iterations]
        if any(s is None for s in history_scopes):
            task["comparison_status"] = "missing_previous_iteration"
            continue
        if any(shapes[s] != shapes[scope] for s in history_scopes):
            task["comparison_status"] = "operation_structure_changed"
            continue
        candidates = [signatures[s].get(key, []) for s in history_scopes]
        if any(len(items) != 1 for items in candidates):
            task["comparison_status"] = "ambiguous_history_location"
            continue
        history = [items[0] for items in candidates]
        center, mad = _statistics([waits.duration(r) for r in history])
        start_center, start_mad = _statistics([waits.ns(r, "start") - origins[(r["_operation_scope"], r["_node_id"])] for r in history])
        representative = min(history, key=lambda r: (abs(Decimal(waits.duration(r)) - center), r["_graph_id"]))
        task.update(comparison_status="previous_five_iteration_mean", reference_count=5,
                    reference_iterations=iterations, reference_graph_ids=[r["_graph_id"] for r in history],
                    reference_operation_scopes=history_scopes,
                    reference_mean_ns=str(center), reference_mad_ns=str(mad),
                    reference_start_offset_mean_ns=str(start_center), reference_start_offset_mad_ns=str(start_mad),
                    start_delta_ns=str(Decimal(task["start_offset_ns"]) - start_center),
                    start_late=_slow(task["start_offset_ns"], start_center, start_mad, options),
                    reference_graph_id=representative["_graph_id"],
                    reference_operation_scope=representative["_operation_scope"],
                    reference_evidence="Public evidenced call coordinates; exactly the previous five measured iterations; unique semantic location; no task ordinal or injection truth",
                    delta_ns=str(Decimal(task["duration_ns"]) - center),
                    slowdown_factor=str(Decimal(task["duration_ns"]) / center) if center else None,
                    duration_slow=_slow(task["duration_ns"], center, mad, options))
        if task["gap_before_ns"] is not None and all(r["_graph_id"] in gaps for r in history):
            gap_center, gap_mad = _statistics([gaps[r["_graph_id"]] for r in history])
            task.update(reference_gap_mean_ns=str(gap_center), reference_gap_mad_ns=str(gap_mad),
                        gap_delta_ns=str(Decimal(task["gap_before_ns"]) - gap_center),
                        gap_slow=_slow(task["gap_before_ns"], gap_center, gap_mad, options))
        task["is_slow"] = task["duration_slow"] or task["gap_slow"]
    return tasks


def analyze(rows, edges, coordinates, options=RollingOptions(), *, preparations=()):
    options.validate()
    coordinates = validate_coordinates(list(coordinates.values()))
    comparison.evidence_adjacency(rows, edges)
    tasks = compare_tasks(rows, edges, coordinates, options)
    roots, traces = wait_backtrace.trace_sources(rows, edges, tasks, options)
    host_roots = source_events.preparation_sources(preparations, rows, edges, coordinates, tasks, options)
    roots.extend(host_roots)
    traces_by_wait = {t["wait_graph_id"]: t for t in traces}
    for root in host_roots:
        if root["status"] != "dependency_supported_candidate":
            continue
        for key in root["affected_wait_graph_ids"]:
            trace = traces_by_wait[key]
            trace["source_root_ids"] = sorted(set(trace["source_root_ids"]) | {root["root_id"]})
            trace.setdefault("host_activity_ids", []).append(root["source_activity_id"])
            trace["status"] = "source_candidates_found"
    events, primary = source_events.rank_sources(roots, rows, edges, coordinates, options)
    compared = sum(t["reference_count"] == 5 for t in tasks)
    return dict(schema_version=1, source_policy_version=4, reference_mode="previous_five_iteration_mean", options=asdict(options),
                status="analyzed" if compared else "no_comparable_history",
                diagnosis_status="localized_candidate" if primary else "no_comparable_history" if not compared else "unresolved_slow_event" if any(e["is_slow"] for e in events) else "unresolved_waits" if traces else "no_slow_event",
                events=events, slow_event_count=sum(e["is_slow"] for e in events),
                wait_backtraces=traces, coverage=wait_backtrace.coverage(tasks, traces),
                public_preparation_count=len(preparations),
                primary_eligible_count=sum(r["primary_eligible"] for r in roots),
                task_count=len(tasks), compared_task_count=compared,
                slow_task_count=sum(t["is_slow"] for t in tasks),
                gap_observation_count=sum(r["status"] == "unattributed_gap" for r in roots),
                supported_execution_candidate_count=sum(r["status"] == "dependency_supported_candidate" and r["component"] == "execution" for r in roots),
                supported_host_candidate_count=sum(r["status"] == "dependency_supported_candidate" and r["component"] == "host_preparation" for r in roots),
                source_status_counts=dict(Counter(r["status"] for r in roots)),
                primary_source_candidate_id=primary, tasks=tasks, root_causes=roots,
                limits=["Only the preceding five measured iterations are used; warmup, current and future iterations are excluded.",
                        "The reference is an arithmetic mean; MAD is median absolute deviation around the five-sample median.",
                        "No absolute increase floor; a zero reference requires strictly positive observed increase.",
                        "Missing or nonunique semantic task locations stay uncomparable; no ordinal matching.",
                        "Root candidates require actual dependency evidence; temporal overlap alone does not prove physical causation.",
                        "Source localization follows a slow Wait's actual producer and observed prerequisites across calls; no guessed edges or gap roots.",
                        "Call-span growth and critical-path gain are impact annotations, not mandatory source-localization thresholds.",
                        "Host sources need public preparation intervals, independently verified call/API bindings and an exact late producer-to-peer-Wait relation; the device graph anchor is not a Host task.",
                        "Event and critical-path effects are local to the selected call and node, not a calibrated global workload gain; fixed releases can conceal real effects.",
                        "Absent public preparation observations cannot be reconstructed from injection truth or arbitrary idle gaps; GEMM/device completion ownership may remain unresolved.",
                        "No injection truth or external baseline is consumed. Rolling references may adapt to a sustained slowdown.",
                        "Public iteration bindings must be verified against capture evidence; configuration alone is not a binding."])


def export_report(report, rows, edges, directory, options=RollingOptions()):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=False)
    lookup = {r["_graph_id"]: r for r in rows}
    gaps = comparison.local_gaps(rows, edges)
    figures = []
    def host_panel(interval, anchor):
        model, window = comparison.focus_model(rows, edges, interval["operation_scope"], {anchor}, options.context_ns)
        source_rows = [r for r in rows if r.get("_operation_scope") == interval["operation_scope"] and r["_node_id"] == root["node_id"]]
        origin = min(waits.ns(r, "start") for r in source_rows)
        start, stop = interval["start_ns"] - origin, interval["stop_ns"] - origin
        model["observedHostSource"] = dict(nodeId=root["node_id"], rank=root["user_rank"], device=root["device_id"],
                                           startUs=start / 1000, stopUs=stop / 1000,
                                           durationUs=(stop - start) / 1000)
        model["caseNote"] = "Host preparation is a public observed interval, not a device kernel. The selected device task is only its call/dependency anchor."
        # Include the actual Host interval in the viewport without adding task nodes.
        return model, (min(window[0], start - options.context_ns), max(window[1], stop + options.context_ns))

    for index, root in enumerate(report["root_causes"][:options.max_figures], 1):
        paths = {edge for path in root["evidence_paths"].values() for edge in path}
        core = {root["graph_id"], *root["affected_wait_graph_ids"]}
        core.update(p for e in edges if e["edge_id"] in paths for p in (e["src"], e["dst"]))
        gap = root["component"] == "pre_task_gap"
        host = root["component"] == "host_preparation"
        if host:
            model, window = host_panel(dict(operation_scope=root["operation_scope"], start_ns=root["observed_start_ns"],
                                            stop_ns=root["observed_stop_ns"]), root["graph_id"])
        else:
            model, window = comparison.focus_model(rows, edges, root["operation_scope"], core,
                                                  options.context_ns, (root["graph_id"], root["duration_ns"]) if gap else None,
                                                  include_path_scopes=True)
        panels = [("current", root["graph_id"], model, window, paths)]
        if host:
            for iteration, interval in zip(root["reference_iterations"], root["reference_preparations"]):
                key = interval["anchor_graph_id"]
                if key is not None:
                    reference, bounds = host_panel(interval, key)
                    panels.append(("iteration-{}".format(iteration), key, reference, bounds, set()))
        else:
            for iteration, key in zip(root["reference_iterations"], root["reference_graph_ids"]):
                reference, bounds = comparison.focus_model(rows, edges, lookup[key]["_operation_scope"], {key},
                                                           options.context_ns, (key, gaps[key]) if gap else None)
                panels.append(("iteration-{}".format(iteration), key, reference, bounds, set()))
        common = min(p[3][0] for p in panels), max(p[3][1] for p in panels)
        name = "focus-{:03d}".format(index)
        body = "<h1>Rolling source comparison</h1><p>Reference: arithmetic mean of measured iterations {}. Mean {} ns; current {} ns. Each image is an actual recorded task, not a synthetic average.</p>".format(
            html.escape(str(root["reference_iterations"])), root["reference_mean_ns"], root["duration_ns"])
        for label, key, model, _, links in panels:
            comparison.frame_model(model, common, key, links)
            stem = name + "-" + label
            view.write_html(directory / (stem + ".html"), label, model)
            if host:
                body += '<section><h2>{}</h2><p>Red bracket: observed Host preparation, not a device task.</p><iframe title="{}" src="{}.html" style="width:100%;height:620px;border:1px solid #ddd"></iframe></section>'.format(label, label, stem)
            else:
                comparison.write_focus_svg(directory / (stem + ".svg"), label, model, key)
                body += '<section><h2>{}</h2><a href="{}.html">Interactive trace</a><img src="{}.svg" alt="{}"></section>'.format(label, stem, stem, label)
        comparison.write_page(directory / (name + ".html"), "Rolling source comparison", body)
        root["focus_page"] = name + ".html"
        figures.append(dict(root_id=root["root_id"], page=root["focus_page"], window_ns=common))
    report["figures"] = figures
    (directory / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    for name, items in (("wait_backtraces", report["wait_backtraces"]), ("events", report["events"]), ("task_comparison", report["tasks"]), ("slow_tasks", [t for t in report["tasks"] if t["is_slow"]]),
                        ("root_causes", report["root_causes"])):
        fields = list(dict.fromkeys(k for item in items for k in item)) if items else ["graph_id", "status"]
        values = [{k: json.dumps(v, ensure_ascii=False) if isinstance(v, (list, dict)) else v for k, v in item.items()} for item in items]
        write_csv(str(directory / (name + ".csv")), fields, values)
    body = "<h1>Previous-five-iteration diagnosis</h1><p>{}: {} comparable tasks, {} slow tasks/gaps. No external baseline or absolute increase floor.</p>".format(
        report["status"], report["compared_task_count"], report["slow_task_count"])
    body += '<p>{}: {} slow local call events; {} primary-eligible candidates.</p>'.format(report["diagnosis_status"], report["slow_event_count"], report["primary_eligible_count"])
    body += '<p><a href="wait_backtraces.csv">Wait-driven backtraces and evidence boundaries</a>. Comparison coverage: {} / {} history-eligible tasks.</p>'.format(report["coverage"]["comparable_task_count"], report["coverage"]["history_eligible_task_count"])
    body += '<p><a href="report.json">JSON report</a> <a href="events.csv">Call events</a> <a href="slow_tasks.csv">Slow tasks</a> <a href="root_causes.csv">Source candidates</a></p>'
    for root in report["root_causes"]:
        title = "Rank {} / iteration {} / block {} / bucket {} / {} / {}".format(
            root["user_rank"], root["iteration"], root["block"], root["bucket"], root["phase"], root["status"])
        body += '<p><a href="{}">{}</a>: {}</p>'.format(root.get("focus_page", "root_causes.csv"), html.escape(title), html.escape(root["reason"]))
    body += "<ul>" + "".join("<li>{}</li>".format(html.escape(v)) for v in report["limits"]) + "</ul>"
    comparison.write_page(directory / "index.html", "Rolling diagnosis", body)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("artifact_dir", type=Path)
    parser.add_argument("--iteration-map", required=True, type=Path)
    parser.add_argument("--preparation-map", type=Path, help="Independently bound public Host preparation intervals; no injection truth")
    parser.add_argument("-o", "--output-dir", required=True, type=Path)
    parser.add_argument("--slowdown-factor", default="1.5")
    parser.add_argument("--mad-multiplier", default="3")
    parser.add_argument("--max-figures", default=5, type=int)
    args = parser.parse_args()
    options = RollingOptions(slowdown_factor=args.slowdown_factor, mad_multiplier=args.mad_multiplier, max_figures=args.max_figures)
    try:
        gate = args.artifact_dir / "pipeline_result.json"
        if not gate.is_file() or json.loads(gate.read_text())["status"] != "passed":
            raise ValueError("rolling diagnosis requires a passed strict capture/graph pipeline")
        rows = graph.read_graph_artifact_nodes(args.artifact_dir / "dep_graph_nodes.csv")
        edges = graph.read_graph_artifact_edges(args.artifact_dir / "dep_graph_edges.csv")
        report = analyze(rows, edges, load_coordinates(args.iteration_map), options,
                         preparations=source_events.load_preparations(args.preparation_map))
        export_report(report, rows, edges, args.output_dir, options)
    except (OSError, ValueError, KeyError, ArithmeticError) as error:
        parser.exit(1, "rolling diagnosis failed: {}\n".format(error))
    print("compared={} slow={} sources={} report={}".format(report["compared_task_count"], report["slow_task_count"],
          len(report["root_causes"]), args.output_dir / "index.html"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
