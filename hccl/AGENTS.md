# Repository Guide

## Scope

This repository is the open HCCL operator repository. In the current tree, the
new operator architecture is implemented mainly under `src/ops`, with Scatter
as the complete reference operator. Most mature collective implementations,
including the legacy Ascend 910 AllReduce paths, are provided by the sibling
HCOMM repository rather than this repository.

Relevant repositories used by this workspace:

- `../hcomm`: matching HCOMM 8.5 source. Mature collective algorithms live
  under `src/algorithm`.
- `../../cann-hccl`: older HCCL source and the prototype implementation of
  step-level semantic tracing and causal diagnosis.

Do not edit a sibling repository unless the user explicitly asks for changes
there. When a task crosses repositories, state which repository owns each
change.

## Layout

- `src/ops`: operator framework, registries, channels, topology, and Scatter.
- `src/common`: logging, environment configuration, ACL adapters, and helpers.
- `include`: public HCCL APIs.
- `test`: unit and system tests for this repository.
- `docs`: public documentation.
- `docs/help`: investigation notes and implementation plans maintained for the
  tracing and diagnosis migration.

For mature collective algorithms in HCOMM, the corresponding locations are:

- `../hcomm/src/algorithm`
- `../hcomm/src/framework`
- `../hcomm/src/common/debug/profiling`
- `../hcomm/src/platform`

## Build And Test

The supported Linux build entry point is:

```bash
bash build.sh --pkg
```

Unit and system tests are enabled with:

```bash
bash build.sh --ut
bash build.sh --st
```

The build depends on a matching CANN Toolkit and third-party dependencies.
Windows is suitable for source investigation and document/tool validation, but
not for claiming a successful HCCL binary build.

For changes owned by HCOMM, run validation from `../hcomm` with its own
`build.sh`; do not treat a successful build of this repository as validation
of HCOMM algorithm changes.

## Change Rules

- Preserve the existing C++14 style, Huawei copyright header, logging macros,
  `CHK_RET` error propagation, and local CMake source-list patterns.
- Keep public API changes exceptional. Prefer internal profiling helpers and
  opt-in environment switches.
- Add sources to every applicable target. HCOMM code may build into `hccl_alg`,
  `hcomm`, and/or `ccl_kernel`; host-only code must not leak into device
  targets.
- Keep tracing disabled by default and make the disabled path cheap.
- Do not infer an executed algorithm from a class name alone. Check operator
  selection, executor overrides, topology, device type, workflow mode, and
  host/device execution path.
- Do not rely on log timestamps for device-task duration. Semantic events must
  be correlated with profiler tasks through device/rank, stream ID, and task
  ID where available.
- Treat local rank, user/global rank, sub-communicator rank, and profiler
  `Device_id` as distinct fields. Record mappings explicitly.

## Trace Migration Conventions

The effective prototype data path in `../../cann-hccl` is:

```text
algorithm semantic scope
  -> thread-local semantic context
  -> HCCL profiling callback for the real task
  -> stream_id/task_id/task_kind semantic log
  -> msprof task_time.csv join
```

Do not migrate `aclprofMarkEx`. The post-processing pipeline does not consume
its `PROFILER_TRACE_EX` rows and explicitly skips them. A semantic event must
describe a real HCCL task and be reported when that task's stream ID and task
ID are available.

The semantic schema should include:

```text
operation, phase, step, slice, rank, rank_size, peer, semantic, stream_id, task_id
```

`_start` sets the semantic context for the following real task; `_end` clears
it. Do not claim that this produces an independent end timestamp. If a pure
boundary is required, bind it to an existing real notify/copy task or add an
explicit profiling record with a documented consumer.

New event names should be stable, lower snake case, and paired with
`_start`/`_end` when they represent an interval. Keep the schema versioned
rather than teaching post-processing scripts one-off log formats.

Before adding semantic scopes, enumerate all runtime paths that implement the same
semantic phase, especially base executors and optimized overrides such as
single ring, fast double ring, aligned double ring, zero-copy, NHR, and AICPU
paths.

## Validation Expectations

For tracing or diagnosis changes, validation should cover:

- disabled-by-default behavior;
- environment parsing and malformed values;
- exact event serialization;
- context set/clear behavior and nested scopes;
- task type to semantic-name mapping;
- operation boundary detection;
- matching coverage for `(device_id, stream_id, task_id)`;
- duplicate and unmatched task reporting;
- single-rank and 8-rank single-ring traces;
- at least one optimized executor path;
- multi-node clock/rank mapping before causal claims;
- no material performance regression when tracing is disabled.

Python post-processing tools should use only the standard library unless a new
dependency is justified and documented. Validate them with `python -m
py_compile` and small deterministic fixtures.

## Reference Documents

- `docs/help/repository-differences.md`
- `docs/help/step-trace-causal-diagnosis-migration-plan.md`
