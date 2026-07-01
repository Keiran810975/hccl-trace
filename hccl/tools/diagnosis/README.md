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
- for single-node legacy plog rows without `device_id`,
  `--rank-as-device-fallback` can explicitly use semantic `rank` as the msprof
  `Device_id` when the profiler task match is unique;
- report duplicate, unmatched semantic, and unmatched profiler records.

Example:

```bash
python -m tools.diagnosis.merge_timeline \
  --plog tools/diagnosis/fixtures/sample.plog \
  --task-time tools/diagnosis/fixtures/task_time.csv \
  --node-id node0 \
  -o tools/diagnosis/fixtures/merged.csv \
  --summary tools/diagnosis/fixtures/summary.csv

python -m tools.diagnosis.validate_trace \
  tools/diagnosis/fixtures/merged.csv \
  --min-match-rate 95
```

The tools use only the Python standard library.