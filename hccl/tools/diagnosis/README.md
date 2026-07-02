# HCCL Step Trace Diagnosis Tools

This directory contains the offline tooling for step-level trace data described
in `docs/help/step-trace-causal-diagnosis-migration-plan.md`.

Current scope:

- parse `[HcclTaskSemantic]` plog rows;
- support both `field=value` rows and legacy `field[value]` rows from the
  verified `cann-hccl` prototype;
- parse msprof `task_time.csv` rows;
- skip `PROFILER_TRACE_EX` marker rows;
- merge records by `(node_id, device_id, stream_id, profiler_seq)` when the
  producer provides `profiler_seq`, and fall back to legacy `semantic_seq`
  or `(node_id, device_id, stream_id, task_id)` for older logs;
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

# Multi-rank runs usually produce one plog per worker and one task_time*.csv per
# profiler process. Use directory inputs to merge all ranks at once.
python -m tools.diagnosis.merge_timeline \
  --plog-dir /path/to/plog_dir \
  --task-time-dir /path/to/msprof_final \
  --node-id node0 \
  -o merged.csv \
  --summary summary.csv

python -m tools.diagnosis.visualize_timeline \
  tools/diagnosis/fixtures/merged.csv \
  --output tools/diagnosis/fixtures/timeline.svg

python -m tools.diagnosis.visualize_dependency_graph \
  tools/diagnosis/fixtures/merged.csv \
  --output tools/diagnosis/fixtures/dependency.svg

# For dense real traces, prefer HTML/canvas output. It avoids creating tens of
# thousands of SVG DOM nodes and supports wheel/keyboard/minimap navigation plus hover details.
python -m tools.diagnosis.visualize_html \
  tools/diagnosis/fixtures/merged.csv \
  --view timeline \
  --layout time \
  --output tools/diagnosis/fixtures/timeline_time.html

python -m tools.diagnosis.visualize_html \
  tools/diagnosis/fixtures/merged.csv \
  --view dependency \
  --output tools/diagnosis/fixtures/dependency.html

# If semantic user_rank collapses to one value while Device_id spans multiple
# cards, the default --rank-field auto renders rows by device/card. Force a
# field explicitly when needed:
python -m tools.diagnosis.visualize_dependency_graph \
  tools/diagnosis/fixtures/merged.csv \
  --rank-field device_id \
  --output tools/diagnosis/fixtures/dependency_by_card.svg

# Time layout stacks overlapping tasks inside each lane. The default
# --time-scale minimum keeps at least --min-px-per-us, so the SVG may become
# wider than --max-width; use --time-scale fit when a capped overview is needed.
python -m tools.diagnosis.visualize_timeline \
  tools/diagnosis/fixtures/merged.csv \
  --layout time \
  --output tools/diagnosis/fixtures/timeline_time.svg

python -m tools.diagnosis.validate_trace \
  tools/diagnosis/fixtures/merged.csv \
  --min-match-rate 95
```

Producer plog rows should include two stream-local sequence numbers:

- `profiler_seq`: zero-based position among all task profiling reports on the
  `(device_id, stream_id)` stream, including tasks without semantic context.
  This is the primary key used to align semantic rows with msprof task_time
  stream order.
- `semantic_seq`: zero-based position among rows that actually emit
  `[HcclTaskSemantic]`. This is for semantic ordering and diagnostics, not for
  matching the full profiler stream.

The semantic context should be captured when `TaskData` is created and later
reported from that task-owned snapshot; reading the current thread semantic
scope in `TaskProfiling::Run` can mix unrelated events such as ACK, data-signal,
and payload work. Logs without `profiler_seq` remain supported through the
legacy `semantic_seq` and `task_id` merge paths.

`AI_CORE` profiler rows are kept while building per-stream sequence numbers
because `profiler_seq` is an absolute profiler-stream position. They are treated
as ignored unmatched profiler rows in the main summary, and dependency graph
rendering stays focused on communication events: rx/tx ACK, rx/tx data signal,
and payload copy/reduce. `merge_timeline` also validates the semantic
`task_kind` against profiler `kernel_type`; incompatible sequence hits are
reported as `type_mismatch`. `task_id` and graph `ctxId` are diagnostic fields
only for modern producer logs because they can be unavailable, local to a graph,
or reused across repeated graph execution.

Use `--keep-duplicate-semantic-keys` on `merge_timeline` only when inspecting
raw producer-side duplicate behavior. The default merged CSV is intended for
validation and visualization.

`visualize_dependency_graph` currently infers dependencies from the merged task
rows only. It does not require the legacy prototype's interval or flow-order CSV
files, so it can run directly after `merge_timeline`. The default `--rank-field
auto` uses `user_rank` when it is usable, and falls back to `device_id` for
visual rows when all semantic rows report the same user rank but multiple
profiler devices are present. The default `--node-mode compact` keeps one RxAck,
one Signal, and one payload representative per phase/rank/step; use
`--node-mode task` only when inspecting every matched slice/task row. Deeper
wait-interval and multi-node NHR edges should be added as separate analysis
layers when those intermediate artifacts are available.

The tools use only the Python standard library.
