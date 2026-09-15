# Repository Guide

## Scope And References

This is the HCCL operator repository for the matching 8.5 HCCL/HCOMM workspace.
`src/ops` contains the new operator architecture, with Scatter as the complete
reference. Traditional AllReduce algorithms and trace production live in
`../hcomm/src/algorithm` and `../hcomm/src/common/debug/profiling`.

Follow the workspace [AGENTS.md](../AGENTS.md). The diagnosis objective is to
explain waits and slow communication tasks through dependency evidence, then
validate the result with multi-node and abnormal workloads.

Read these documents before changing diagnosis behavior:

- [task.md](tools/diagnosis/task.md): the only active development plan.
- [spec.md](tools/diagnosis/spec.md): current implementation contracts.
- [Stage archive](tools/diagnosis/arch-94a1ab31c3ee.md): branch state, implemented work and validation limits.
- [Branch review](tools/diagnosis/branch-review-2026-09-15.md): remote implementations, evidence and approval candidates.
- [Diagnosis README](tools/diagnosis/README.md): CLI and artifact usage.

`arch-*.md`, `archive/`, and the early plans in `docs/help` are historical
records. Their proposed schemas and task lists do not override the active plan.
`../../cann-hccl` is read-only reference unless the user explicitly requests edits.
Changes in HCOMM must remain within the user's authorized task; identify which
repository owns each change.

## Git And Layout

The workspace root and both source directories have independent Git metadata.
The root also tracks source files directly. As of the 2026-09-15 review, this
repository is on `dev-innerDia@4600cb6`, with later implementation present as
working-tree changes and untracked files relative to that HEAD. Check root and
child status before editing or committing; preserve existing changes.

Also inspect remote heads and relevant branch records. The root remote has
standard Ring, Mesh, NHR and RHD implementations, and its master includes the
captured-semantic early-return fix. Do not classify them as unimplemented based
on this old checkout. The approved remote master, standard Ring and NHR merges
are now integrated into the root master (`2f26033`, `360d650`, `638e94c`).
Mesh normal Tx/Rx fix `286ef99` is also integrated into master via `f30a90a`.
Build/device validation remains; follow the root
[test handoff](../test/prompts/integrated-master-device-test.md).
RHD is abandoned
by user decision; retain its history but exclude it from development plans.
The user confirms NHR/Mesh/standard Ring were tested.
Parent-directory HTML captures add
partial evidence; preserve that confirmation and record missing provenance
separately instead of requiring all device tests to be repeated.

- `src/ops`: operator framework, registry, channels, topology and Scatter.
- `src/common`, `include`: shared helpers and public APIs.
- `tools/diagnosis`: standard-library Python parsing, merge, graphs and views.
- `test`: HCCL unit/system tests; workspace `../test`: trace data and runbooks.
- `docs/help`: historical migration and repository investigation notes.

## Trace And Dependency Contracts

- Production inputs are HCOMM semantic/graph-correlation plog and consolidated
  `msprof_*.db` (DB schema 1.2.0, read-only SQLite). Do not restore JSON,
  `task_time.csv`, `aclprofMarkEx`, or task-sequence heuristics.
- Semantic output is v4; the reader accepts v2/v3/v4. Graph correlation is v1;
  merged CSV has 42 columns and graph artifacts currently use v4.
- Direct matching uses `(node_id, device_id, stream_id, task_id)` plus compatible
  task kind. FFts matching uses graph-parent correlation plus context ID.
  Never infer device ID from rank or duration from host `submit_ts`.
- Keep node/device, user rank, communicator rank, and peer rank distinct.
  Operation scope comes from DB `(group_name, op_name)` within one profile run;
  process-local IDs are not shared multi-node identities.
- TaskData captures a one-shot semantic snapshot before reporting. Scope exit
  restores its parent. An event named `_start` is not an independent interval
  marker; task duration comes from DB start/end timestamps.
- Execution graphs preserve physical/control tasks. Resource graphs derive
  from execution artifacts and retain source IDs; visualization reads artifacts
  without reconstructing dependencies.
- Use only supported stream-order and unique Notify evidence. Keep incomplete
  relations explicit. Do not restore nearest-time or peer-payload causal edges.
- Derived confidence must not exceed source confidence. The current FFts/mixed
  resource-order promotion to observed is a known pending fix, not a precedent.
- Cross-node topology does not require comparable clocks when shared identity
  is proven. Cross-node time differences require calibration; local wait
  durations remain useful without it.

## Implementation And Validation

Preserve C++14 style, copyright headers, logging, `CHK_RET`, and existing CMake
source lists. Trace is opt-in and must not change algorithm selection or submit
extra device tasks. Check the actual executor/transport for the target workload;
do not require every unrelated algorithm to be covered first.

Python tools use only the standard library, future annotations, existing
module/script entry patterns, frozen data models, and CSV readers/writers.
Preserve integer nanoseconds and wide Notify IDs; use UTF-8 output and accept
UTF-8 BOM on CSV input.

Prefer small changes that reuse existing parsers and artifacts. Add fields only
when a real sample demonstrates a missing fact. Test the changed rule and a
representative failure case; documentation-only changes need factual/link/diff
checks, not a fresh build or full device matrix.

From the workspace root:

```bash
python -m unittest hccl.tools.diagnosis.test_diagnosis
```

Linux builds require a matching CANN Toolkit:

```bash
bash build.sh --pkg
# Use --ut / --st when relevant to the change.
```

HCOMM changes must be built in `../hcomm`; a successful HCCL build does not
validate them. Windows checks and old-data replay are not a new device run.
The archived local 8-device single-ring sample is not the whole project's
evidence: Ring/NHR branch notes also report device investigations. Check each
tested commit and path; multi-node support and abnormal cases remain active work.
