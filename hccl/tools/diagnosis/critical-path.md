# nf: measured-schedule critical path

`nf` is based on `master@fb4fbc8`, with the AI_CPU and Ring/NHR diagnosis chain
integrated on 2026-10-22. This standard-library-only analysis consumes execution
artifacts without reconstructing dependencies or changing resource-edge weights.
`--multi-node` analyzes node-local paths and exports actual remote dependency
boundaries; it never adds uncalibrated node times into a global critical path.
The complete workflow is `python3 -m hccl.tools.diagnosis.run_diagnosis run.json -o replay`.

## What The Result Means

The question is: under the **observed dependencies and a fixed-gap replay model**,
which tasks constrain completion of the selected capture or explicit endpoints?
This is not a claim that every zero-slack task is abnormal, or that the captured
communication trace contains the entire training application.

- Default completion waits for **all selected physical tasks**. Initialization,
  profiler control and teardown tasks count if present. This is capture completion,
  not automatically workload completion.
- `--operation-scope` restricts analysis to one exact DB operation scope.
- Repeat `--completion-task GRAPH_ID` to specify actual workload completion
  endpoints and avoid treating unrelated background streams as the workload.
- An endpoint outside the selection is an error. Tasks not reaching explicit
  endpoints have blank slack and are not reported critical.

## Accounting

The model uses task readiness/start/finish events, not a simple sum of task
durations. All calculations use integer nanoseconds from DB timestamps; no
floating-point time comparisons, host `submit_ts` or nearest-time pairing.

For ordinary task `v`, given the accepted physical stream-order predecessors:

```text
ready(v)  = max(finish(p) for p in stream_predecessors(v))
gap(v)    = observed_start(v) - max(observed_stop(p))
start(v)  = ready(v) + gap(v)
finish(v) = start(v) + observed_duration(v)
```

Roots are released at their observed start relative to the earliest selected
task. Gaps and root releases are explicit activities, not new causal edges.
They remain **unattributed time**: a 200 ms gap before a Notify Record is not
automatically a 200 ms kernel or proof of a particular software fault.

For a paired Notify Wait `w` and its Record `r`:

```text
signal_ready(w) = max(start(w), finish(r))
residual(w)     = observed_stop(w) - max(observed_start(w), observed_stop(r))
finish(w)       = signal_ready(w) + residual(w)
```

The producer and the wait run concurrently. The blocking part already explained
by the producer is **not charged again as the full wait duration**. The residual
is an observation around Record completion, not a hardware signal propagation
latency. Record/Wait timestamp conflicts are reported; the sync edge is excluded
from timing rather than clamped or silently corrected. Multiple producer edges
for one Wait remain unresolved, not a fabricated AND join.

Example: producer finishes at 10 us, Wait spans 2--12 us, downstream work spans
12--15 us. The critical path costs 10 + 2 + 3 = 15 us, not 10 + 10 + 3 = 23 us.
Two peers waiting for the same producer do not add two copies of its delay.

## Finding Critical Tasks

1. Topologically sort the event DAG. Cycles, duplicate IDs, missing endpoints
   and self-loops are errors.
2. A forward maximum computes earliest event times and the selected completion
   time `M`. The reconstructed start/finish of every selected task must match
   its observed timestamps exactly.
3. A reverse maximum computes each event's remaining longest distance to the
   completion sink. For activity `u -> v` with weight `w`:

   `slack = M - earliest(u) - w - remaining(v)`.

4. Zero-slack activities lie on at least one critical path. Report **all** such
   tasks, plus one deterministic representative path; do not hide tied paths.
5. By default, replay the 20 largest positive-cost critical activities, setting
   **one** activity to zero each time and recomputing `M`. Report the modeled
   reduction, not the activity's duration as an assumed performance benefit.

With two parallel 10 ms paths, both are critical, but accelerating either one
alone gives zero improvement because the other path still takes 10 ms. With
parallel paths of 12 ms and 10 ms, eliminating 6 ms from the longer path saves
only 2 ms. This distinguishes criticality from achievable individual speedup.

The what-if model holds other task costs, dependencies, gaps and root releases
fixed. It does not simulate changing contention, transport bandwidth, host
scheduling or data-dependent algorithm choices. Gains are not additive. Untested
activities have blank gain, **not zero**. Use `--impact-limit 0` to disable replay,
or raise it to inspect more candidates. One forward/reverse pass is linear after
sorting; bounded replay costs O(K * (V + E)).

## Evidence Limits

- Only **one node clock domain** is accepted. Multi-node input without explicit
  local `--node-id` selection is rejected; no uncalibrated global path is produced.
- Time only `direct_stream_order_observed` and exact direct/local Notify edges.
  FFts declaration order is not upgraded to a full hardware DAG. FFts contexts,
  AI CPU parent spans, unsupported edges and opaque Event Waits are reported as
  incomplete evidence. No payload/nearest-time dependencies are reconstructed.
- RDMA task duration is doorbell submission, not network completion. It is
  labeled separately and makes the result partial.
- Unpaired Waits retain their full span as **unresolved wait**. A path through one
  is not proof that the Wait itself is the root cause.
- Selection boundaries and Notify ambiguities remain explicit. Existing
  `*_notify_ambiguities.csv` is discovered automatically or passed explicitly.
- `status=partial_evidence` means unsupported/missing/conflicting evidence exists.
  `status=observed_model` still only means this model over this capture, not
  completeness of an unobserved application or a proof of causation.
- Exact timestamp reconstruction checks accounting only. Missing dependencies
  can be absorbed into observed gaps/releases, so reconstruction alone cannot
  validate causal completeness.

## Usage

From the workspace root, with existing execution artifacts:

```bash
python3 -m hccl.tools.diagnosis.critical_path \
  /path/to/dep_graph_nodes.csv \
  --edges-csv /path/to/dep_graph_edges.csv \
  --operation-scope op_FROM_NODES_CSV \
  --impact-limit 20 \
  -o /path/to/report/critical_path

# Select actual workload completion tasks instead of all capture tasks:
python3 -m hccl.tools.diagnosis.critical_path \
  /path/to/dep_graph_nodes.csv \
  --edges-csv /path/to/dep_graph_edges.csv \
  --completion-task x_FIRST_ENDPOINT --completion-task x_SECOND_ENDPOINT \
  -o /path/to/report/workload_path

python3 -m unittest hccl.tools.diagnosis.test_diagnosis \
  hccl.tools.diagnosis.test_critical_path
```

The script also supports direct execution. There is no C++/HCOMM change and no
new profiling device task.

Outputs are JSON and five CSVs:

| Artifact | Meaning |
|---|---|
| `critical_path.json` | Full report, selected endpoints, clock scope, issues and assumptions |
| `*_tasks.csv` | Original task IDs/semantics, slack, effective work, gaps, modeled gains |
| `*_activities.csv` | Event arcs, their original execution edge IDs, costs and slack |
| `*_representative_path.csv` | One ordered critical path; weights sum to `makespan_ns` |
| `*_impacts.csv` | Bounded one-at-a-time zero-cost replay, sorted by modeled benefit |
| `*_issues.csv` | Missing, unsupported or temporally incompatible evidence |

The report reuses original `graph_id` and execution edge IDs, so each task and
dependency can be located in the existing dependency HTML. A separate critical
path highlighting UI is not included in this change.

## Validation Scope

Hand-computable fixtures cover joins, parallel branches, tied critical paths,
duplicate wait accounting, explicit endpoints, injected idle gaps, nanosecond
precision and malformed/incomplete evidence. Tiny-graph path enumeration checks
the dynamic-programming slack and what-if results independently.

Existing device artifacts can be replayed offline. Such replay is **not a new
910B/910C run**. Mixed FFts/direct captures and timestamp conflicts must remain
partial; no device-level accuracy or measured real-world speedup is claimed.

2026-10-17 local checks: 62 existing tests + 27 new tests passed. Offline replay
of the saved `sync-each-w5-i10` baseline and `sync-each-injected-op10-v2` capture,
selecting `op_13f1cccc5a4fc52dc3f3ebfe`, gives observed spans of 1.301711 ms and
201.377185 ms. Reports are in `test/out/nf-critical-path/{baseline,injected}-op10*`.
The injected representative path includes a 200.135999 ms unattributed gap before
Rank 0 / stream 45 / task 276 / AllGather step 0 / `tx_payload_start`.

Both reports are partial: FFts declarations/context dependencies, unresolved
Waits, cut selection edges and incompatible Notify timestamps remain. In this
incomplete model, zeroing that gap alone yields only 0.063326 ms because other
opaque waits/releases remain as competing paths. This is **not** a claim that
removing the injected delay would save only that much in reality; full hardware
dependencies are required before using the what-if result as a performance
prediction. The fixtures validate the algorithm; this replay exposes the actual
capture's coverage limits.
