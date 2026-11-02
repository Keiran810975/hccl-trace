# Four-rank GPT validation, 2026-11-02

## Configuration

- Node0 / owned nonprivileged `zjy-new`, physical NPU4..7.
- Physical chips9/11/13/15, runtime1/3/5/7, one Rank per whole card.
- GPT-2 Small: 124439808 parameters, 12 layers, hidden768, 12 heads,
  sequence1024, batch4 per Rank, DDP data parallel, AdamW.
- BF16 autocast, FP32 parameters and gradient AllReduce; 10 warmup + 50 measured.
- The measured workload has 13 stable gradient buckets. Bucket sizes are recorded,
  not inferred from the bucket-cap parameter.
- Current AI_CPU semantic producer reuses the matching 2026-11-02 Host/Device build;
  all eight changed producer files match the built snapshot hashes.

## Intervention

Exactly one background thread on Rank0, measured iteration25 (zero-based).
It starts after the selected gradient bucket submission and executes four
2048MiB ACL D2D copies on an independent stream. Initialization precedes training;
full validation and resource cleanup follow measurement. API return is not device
completion, so the selected submission does not prove which device bucket overlaps.

The actual worker envelope is 19.468260ms, including API and stream synchronization.
Four copies and numerical validation completed. Individual background device tasks
were not uniquely resolved by the conservative independent evaluator; this envelope
must not be called pure SDMA hardware duration.

## Diagnosis

Unchanged previous-five-measured-iteration arithmetic mean, 1.5x/3MAD, no absolute
floor, candidate policy `all`. The analyzer never reads injection truth.

Both runs: 224840/224840 semantic matches exact; all 117064 Notify Waits paired.
Normal: 231 communication-source candidates. Strong Copy: 306 candidates,
same Node/Rank positive actual-envelope overlap 0/306; primary did not hit.

Three real HCCL work tasks inside the intervention envelope did slow:

| Task | Reference | Observed | Factor |
| --- | --- | --- | --- |
| Rank0 stream90 task27611 SDMA |19.0796us|53.459us|2.8019x|
| Rank0 stream50 task10691 SDMA |18.5114us|52.419us|2.8317x|
| Rank0 stream90 task27609 Inline Reduce |2.9958us|14.300us|4.7733x|

These are retained as `isolated_slow_task`, not public source candidates.
The same call has 15 slow Waits, but no accepted backtrace established these work
tasks as their source. Across the entire abnormal run there are 6192 incompatible
Notify timestamp boundaries. This does not prove every boundary affected these
three tasks, nor that actual propagation was absent. No edges or thresholds were
changed to obtain a positive result. This GPT test did not reproduce the preceding
three-rank AllReduce example's 2/2 candidate precision.

## Overhead

Three rotating paired repetitions; every mode is a no-fault 10+50 training run.
For each measured iteration take the maximum elapsed time across four Ranks, then
average 50 iterations. Public call logging and checks are present in all modes.
Startup, profiler export, offline diagnosis and HTML generation are excluded.

| Repeat | Off | Semantic | Semantic + msprof | Semantic difference | Full difference |
| --- | --- | --- | --- | --- | --- |
|0|345.97ms|369.45ms|553.86ms|+6.79%|+60.09%|
|1|650.32ms|412.79ms|747.27ms|-36.52%|+14.91%|
|2|445.86ms|502.41ms|517.05ms|+12.68%|+15.97%|

The off-mode reference varies by 1.88x. Paired arithmetic means -5.685%/+30.322%
are descriptive differences, not reliable isolated instrumentation costs. Negative
differences are not evidence of negative collection cost. The source of this drift
has not been established; do not assign it to other users without evidence.

## Retention And Restoration

Server root: `/home/commTeam/zjy/zjy-new-workspace/gpt2-semantic-20261102-001`.
Final reports: `reports/normal` and `reports/strong-copy`, each containing
`execution.html`, `root_causes.json`, `propagation.html` for complete 10+50 runs.
Independent results: `experiment-summary.json`; native source results unchanged.

A storage precheck stopped after eight captures. Those results were retained;
the six overhead captures were compressed, every file verified by SHA256, and
only the remaining three planned overhead runs resumed. Normal raw/debug inputs
were similarly archived after its diagnosis completed. Expanded normal debug
keeps the rolling JSON for evaluation; the complete original graph is in
`retained-archives/normal-raw-and-debug.tar.gz`. No old or external data was deleted.

Both lease phases saved originals and used independent 4500-second rollback.
NPU4..7 original False/5 and official Device package were restored and read back;
timer inactive, active registry absent. No external task was stopped.
No branch switch, commit or push was performed.
