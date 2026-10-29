# Long HOST capture identity

2026-10-29, nf. This repairs the GPT-2 10-warmup + 100-measured capture;
it does not change anomaly thresholds or infer dependencies from task numbers.

## Evidence and Encoding

CANN 8.5.1 Runtime `rtGetTaskIdAndStreamID` returns the thread's last task
identifier. The installed static Runtime's `Notify::Record`, `Notify::Wait`
and memory submission code call `GetFlipTaskId` before `SetLastTaskId`.
`GetFlipTaskId(unsigned int, unsigned short)` constructs:

```text
runtime_task_id = task_id | (flip_number << 16)
```

Verified in `libruntime.a`, SHA256
`46071cc06a734f7ec066714dede1dfb472f1d14fb167e7c2ce4d241ae75f8ded`,
`task_manager.cc.o`, instruction `orr w19, w20, w21, lsl #16`.
This is an explicit versioned encoding, not a fitted offset or inferred wrap count.
It is not claimed for unverified Runtime versions or AI_CPU-generated identifiers.

The vendor `HCCLTaskSingleDevice` table preserves `batch_id` (flip number).
The final consolidated `TASK` omits it. For the retained GPT-2 capture, each
communication task has a unique exact vendor match using device, stream, raw
task, context and connection. Operation names are independently checked.
No semantic log, injection truth, timestamp-nearest or row-order input is used
by the exporter.

## Export and Analysis

`export_msprof_identity.py` opens both original DBs read-only, verifies the
association, and creates a new consolidated DB via SQLite backup. The copy
retains all original tables and adds `HCCL_TRACE_TASK_BATCH` schema 1, keyed
by `(globalTaskId, startNs)`. Metadata records the encoding, input hashes,
join fields and coverage. Missing/ambiguous batches or operation disagreement
fail export; originals are never edited. The consumer still reads only the
consolidated DB, not the vendor intermediate table.

The direct merge key uses the decoded full Runtime identifier when this
explicit export is present. Raw profiler task ID and batch are both retained.
Ordinary DBs without the extension keep the legacy exact rule and cannot
silently recover missing batches. Multiple matching executions are an error,
never a first-row selection.

Compute placeholders can reuse stream/task/context/connection values. New
captures retain the vendor TaskIndex `(globalTaskId, startNs)` as
`profiler_task_index`. It is an exact execution key, not a time-distance test.
Duplicate TaskIndex values remain errors. `profiler_batch_id` is also retained;
merged CSV now has 45 columns, graph artifact version is 7. Reading old
artifacts without these columns preserves the old physical identity.

The public `hccl-diag analyze` entry prepares necessary HOST batch identities
in its temporary workspace before binding and analysis. Preserve the original
PROF directory and vendor SQLite input. Advanced users can also export directly:

```bash
python3 -m hccl.tools.diagnosis.export_msprof_identity \
  --source-db /path/to/PROF_original/msprof_original.db \
  --profile /path/to/PROF_original --output /path/to/selected/msprof_original.db
```

The previous five measured iterations, slow-task thresholds, Notify pairing,
graph gates and independent injection-window evaluation are unchanged.

## Validation Boundary

Local regression covers rollover, reused placeholders, missing/ambiguous
batches, conflicting operation names, incomplete coverage, unchanged input
hashes, old inputs and duplicate execution rejection. Actual long-capture
replay and fresh NPU execution must be reported separately. Resource-busy
Node0 does not authorize using another workload's cards.

The retained 10+100 GPT-2 capture has now passed strict merge (210160/210160,
100%, no duplicate executions or invalid matches) and both graph gates.
The execution graph contains 1877989 nodes / 2035349 edges; the resource graph
contains 150290 nodes / 343418 edges. Both have zero cycles, duplicate IDs,
missing endpoints and contraction ambiguities. These are offline replay
results, not a new workload execution or anomaly-accuracy measurement.
All 193144 Waits were paired; the unchanged rolling pipeline and 158
source-to-wait branches completed. The normal capture still has 38 supported
candidates and 2250 isolated slow observations, so false alarms remain a
separate limitation. Local regressions: 292 diagnosis + 126 runner/evaluator
tests. Server `src-v9` passes its 14 new identity tests and exact mapping
equivalence/coverage checks on all four original DBs.

A fresh `src-v9` GPT-2 4-rank run (10 warmup + 100 measured) also completed:
finite/update/replica checks passed; 210160/210160 semantic exact matches;
both graph gates passed; all 193144 Waits paired; rolling diagnosis and 321
propagation branches exported. This normal run still has 49 supported
candidates / 2349 isolated slow observations. Its large artifacts were removed
only after verified small retention; the original formal capture remains.
No anomaly run or signature-policy change was performed.
