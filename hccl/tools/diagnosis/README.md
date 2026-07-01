# HCCL Step Trace Diagnosis Tools

This directory contains the offline tooling for step-level trace data described
in `docs/help/step-trace-causal-diagnosis-migration-plan.md`.

Current scope:

- parse `[HcclTaskSemantic]` plog rows;
- support both `field=value` rows and legacy `field[value]` rows from the
  verified `cann-hccl` prototype;
- parse msprof `task_time.csv` rows;
- skip `PROFILER_TRACE_EX` marker rows;
- merge records by `(node_id, device_id, stream_id, task_id)`;
- require semantic `device_id` by default instead of inferring it from rank;
- dedupe duplicate semantic merge keys by default while reporting the input
  duplicate counts in the merge summary;
- for single-node legacy plog rows without `device_id`,
  `--rank-as-device-fallback` can explicitly use semantic `rank` as the msprof
  `Device_id` when the profiler task match is unique;
- render matched merged rows as a standalone SVG timeline; default layout uses
  logical phase/step/event columns to avoid dense task rectangles collapsing
  into one another;
- render inferred task dependency edges as a standalone SVG graph, including
  same-rank program order, right-neighbor ACK dependencies, upstream data-signal
  dependencies, same-rank/upstream payload step edges, RS-to-AG phase bridge
  edges, and ack/signal/payload edges when the events are present;
- report duplicate, unmatched semantic, and unmatched profiler records.

Example:

```bash
python -m tools.diagnosis.merge_timeline \
  --plog tools/diagnosis/fixtures/sample.plog \
  --task-time tools/diagnosis/fixtures/task_time.csv \
  --node-id node0 \
  -o tools/diagnosis/fixtures/merged.csv \
  --summary tools/diagnosis/fixtures/summary.csv

python -m tools.diagnosis.visualize_timeline \
  tools/diagnosis/fixtures/merged.csv \
  --output tools/diagnosis/fixtures/timeline.svg

python -m tools.diagnosis.visualize_dependency_graph \
  tools/diagnosis/fixtures/merged.csv \
  --output tools/diagnosis/fixtures/dependency.svg

# Use the raw time-scaled view only when the span is small enough to inspect.
python -m tools.diagnosis.visualize_timeline \
  tools/diagnosis/fixtures/merged.csv \
  --layout time \
  --output tools/diagnosis/fixtures/timeline_time.svg

python -m tools.diagnosis.validate_trace \
  tools/diagnosis/fixtures/merged.csv \
  --min-match-rate 95
```

Use `--keep-duplicate-semantic-keys` on `merge_timeline` only when inspecting
raw producer-side duplicate behavior. The default merged CSV is intended for
validation and visualization.

`visualize_dependency_graph` currently infers dependencies from the merged task
rows only. It does not require the legacy prototype's interval or flow-order CSV
files, so it can run directly after `merge_timeline`; deeper wait-interval and
multi-node NHR edges should be added as separate analysis layers when those
intermediate artifacts are available.

The tools use only the Python standard library.
