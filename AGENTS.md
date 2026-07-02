# Agent Notes

## Workspace Scope

This workspace is `hccl-trace`. The main editable repository is the current
workspace. Treat sibling repositories as references unless the user explicitly
asks for edits there.

Relevant paths:

- `hccl/`: open HCCL operator repository and current diagnosis tools.
- `hcomm/`: matching HCOMM source; mature collective algorithms and the C++
  semantic trace producer live here.
- `../cann-hccl/`: older prototype/reference for step-trace diagnosis and SVG
  visualizations.
- `review reports/` in the workspace: commit review notes and design gaps.
- `test records 0630/` in the workspace: test plan, progress, and command records.

When a task crosses repositories, state which repository owns each change. Do
not modify `../cann-hccl` without an explicit user request.

## Diagnosis Tooling Context

Current Python diagnosis tools live under `hccl/tools/diagnosis`. They should
use only the Python standard library unless a dependency is explicitly justified.
The expected flow is:

```text
plog [HcclTaskSemantic] + msprof task_time.csv
  -> merge_timeline.py
  -> validate_trace.py
  -> visualize_timeline.py / visualize_dependency_graph.py
```

Important schema and matching rules:

- Match semantic rows to profiler tasks by `(node_id, device_id, stream_id, task_id)`.
- Do not infer `Device_id` from rank by default. Use explicit fallback only for legacy data.
- Do not rely on plog timestamps for device task duration.
- `PROFILER_TRACE_EX` marker rows are skipped by the current parser.
- `device_id`, user/global rank, comm rank, local rank, and profiler `Device_id`
  are distinct concepts.

## Visualization Expectations

Timeline visualization should stay readable for dense task traces. The default
layout is logical phase/step/event columns; raw time scaling is useful only for
small spans.

Dependency visualization should not only connect payload nodes. For single-ring
AllReduce, the useful first-order edges are:

- same-rank program order across RxAck, Signal, and Payload nodes;
- `right_neighbor_ack_dep`: RxAck wait depends on the right neighbor's previous payload;
- `upstream_data_signal_dep`: data-signal wait depends on the upstream producer's previous payload;
- simplified payload-level edges: same-rank previous step, upstream previous payload,
  and reduce_scatter-to-allgather phase bridge.

The old reference scripts in `../cann-hccl/tools` are useful when checking this:

- `hccl_semantic_task_timeline_graph.py`
- `hccl_ack_signal_dependency_graph.py`
- `hccl_stage_dependency_graph.py`
- `hccl_nhr_dependency_graph.py`

The new `hccl-trace` pipeline currently lacks old prototype interval/flow-order
CSV artifacts, so deeper wait interval, NHR, and multi-node clock-aligned causal
edges should be treated as future layers unless those artifacts are added.

## Windows / PowerShell Pitfalls

This workspace is often inspected from Windows PowerShell. Be careful with shell
syntax and encodings.

- Prefer `rg` for searches.
- `apply_patch` may intermittently fail with a Windows sandbox helper error; if
  it does, use small PowerShell text replacements or UTF-8 no-BOM writes inside
  the workspace.
- Avoid complex inline PowerShell quoting when strings contain `$`, backticks,
  or nested quotes. Use single-quoted here-strings for multi-line content.
- When writing text with PowerShell, use UTF-8 without BOM:

```powershell
$utf8NoBom = New-Object System.Text.UTF8Encoding($false)
[System.IO.File]::WriteAllText((Resolve-Path $path), $text, $utf8NoBom)
```

- The local Python launcher may point at WindowsApps placeholders. If
  `python`, `python3`, or `py -3` cannot start, report that tests could not run
  locally rather than claiming Python validation.
- `git diff --check` may only report LF/CRLF warnings on this machine; those are
  line-ending warnings, not whitespace failures.

## Validation Habits

For diagnosis-tool changes, try these checks when Python is available:

```bash
python -m py_compile hccl/tools/diagnosis/*.py
python -m unittest hccl.tools.diagnosis.test_diagnosis
bash test/run_step_trace_function_test.sh --plog <plog> --task-time <task_time>
```

On this Windows environment, at least run:

```powershell
git diff --check
git status --short
```

If tests cannot run because Python is unavailable, say so clearly in the final
response.