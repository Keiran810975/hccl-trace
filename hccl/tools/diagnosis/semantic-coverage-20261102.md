# Notify semantic coverage repair and three-rank validation

## Scope

Repair HCOMM producer coverage first, prioritizing local Notify handshakes and
preserving physical exact matching, one-shot snapshots and delayed/cache replay
identity. Extend Inline Reduce / RDMA submission labels where the producer knows
the role; do not describe a doorbell as completed RDMA transfer. Missing roles
remain explicit and duplicate coordinates remain ambiguous.

Consumer regression must distinguish an uncomparable intermediate Wait from a
measured normal Wait, without inventing edges or relaxing timestamp gates.

## Device Validation

Only Node0's own nonprivileged zjy-new, physical NPU5,6,7 (one chip / one Rank
per card). Verify both chips of each whole card idle before any device change.
Keep other cards and external tasks untouched. Use a fresh source/build/run
directory, matching Host/Device hashes, saved policy/package originals and an
independent tested restoration timer. Restore and read back on all exits.

Workload: three ranks, 128 MiB FP32 SUM AllReduce, one call per iteration,
10 warmup + 30 measured iterations. First accept new semantic/DB association and
dependency coverage on a small capture. Then capture a normal run and a stronger
single background D2D competition run. Record actual device overlap, not just a
Host trigger; preserve negative results if the effect is weak. Do not feed
injection truth to the analyzer or change thresholds to manufacture a hit.

Overhead: interleave trace-off, semantic-only and semantic+msprof repetitions
with identical workload/device settings and no fault injection. Report measured
iteration times separately from launch/export/offline costs and retain samples.

## Precheck History

2026-11-02: inspected nf working tree and current producer/consumer paths.
Node0 initially has no listed NPU processes and NPU5..7 HBM near 2.9/3.2 GiB
baseline; zjy-new running, nonprivileged. This is a read-only precheck, not a
started experiment or a producer repair acceptance result.

Producer and consumer changes are now implemented. The C++ trace-source test
passes, including coexisting control/semantic snapshots, nested location
restoration, one-shot consumption and delayed reporting. All 372 diagnosis tests
pass; the finite Copy worker and existing guard regressions also pass. Both new
Host and Device builds completed in the owned container; all three Host libraries
must come from that build, not the old deployment.

The first guarded start was rejected before a policy snapshot, timer, package
replacement or workload: NPU5 chip0 acquired external `ek-worker` PID1637402,
about15028MiB process memory (18136MiB HBM). NPU6/7 remain idle in that check.
No external task was stopped. Do not relax the whole-card gate just because the
selected chip1 is idle. The device semantic coverage, diagnosis effect and
overhead are **not measured yet**.

New build/run root on Node0:
`/home/commTeam/zjy/zjy-new-workspace/semantic-coverage-20261102`.
The new package and libraries are private to this root. `validation-state.json`
retains the resource rejection. Once resources are available, the runner supports
an explicit `--resume-precheck` only for this never-activated rejection; it cannot
restart a captured/activated experiment. It archives the failed precheck instead
of deleting it. All raw inputs will be retained on an actual run.

Frozen experiment:128MiB FP32 SUM AllReduce, three ranks,10+30; formal measured
iteration15 (0-based), Rank0, one worker performing four2048MiB D2D copies after
AllReduce submission. Actual per-copy device intervals must be audited later;
Host envelopes are not hardware durations, and overhang beyond the collective
must be reported rather than hidden. The next iteration waits after the timed
collective so this burst does not silently inject into another collective.
Overhead modes rotate across five repetitions: trace-off, semantic-only,
semantic+msprof, with identical public SDK logging/workload/numerical checking.

## Completed Validation

The external NPU5 job later released. A short capture succeeded after fixing two
packaging/configuration issues (Python test-package marker and AI_CPU spelling).
Its report succeeded; a runner-only result-path error was fixed offline and the
successful short capture was reused. All rejected attempts and restoration
receipts remain archived. Normal and strong-Copy 10+30 captures and fifteen
overhead runs completed, without stopping external jobs.

The producer labels alone leave framework controls without fine algorithm
coordinates. A same-capture-only consumer comparison now uses complete exact
Notify channels. Reused channels are separated only by their unique semantic
frontiers on a complete real stream-order chain. An unannotated Copy/Inline
Reduce/RDMA submission also needs a unique kind/size in that region. Missing,
disconnected, repeated or ambiguous regions are rejected, never assigned local
ordinals, nearest timestamps or invented phase/step values. Physical channel
fields are not used for cross-capture baseline matching.

Three retained versions were replayed, not selectively recaptured. Every replay
verifies raw inputs and execution node/edge CSV hashes unchanged. Final v3:

| Kind | Comparable / eligible, measured iterations5..29, three ranks |
| --- | --- |
| Notify Wait |2250/2250|
| Notify Record |2250/2250|
| SDMA |600/600|
| Inline Reduce |300/300|
| AI_CPU parent |0/75; deliberately opaque, not counted twice as fine work|

Each formal capture has3600Waits, all paired. Eligibility excludes warmup and
the first five measured iterations, which cannot have five measured references.
This is comparison coverage, not a claim that every row has producer phase labels.
The single-node capture contains no RDMA tasks: the submission fallback is built
and unit-tested, not newly device-validated on a multi-node RDMA sample.

Normal has0internal candidates. Strong Copy has2, both Rank0, measured15,
stream90:task1225(153.077us vs67.0066us,2.2845x) andtask1203(142.677us vs
61.9426us,2.3034x). The latter has explicit RS copy semantics; the former uses
an evidenced semantic-anchor region and keeps its unknown phase blank. Both
have positive overlap with actual background SDMA intervals,2/2under the user's
same-Node/Rank rule, with six recorded propagation chains. No fault truth was
passed to the analyzer. This is one exploratory example, not general precision
or a multi-node result.

The four actual device copies span about14.41ms; their overlap with the target
4.111138mscommunication is4.003820ms. They overhang the collective, explicitly
not the earlier short-burst contract. The next collective waits until the finite
worker finishes. Rank0comparable work overlaps12tasks,5slow; median1.0573x,
max5.3804x(the latter includes small helper work). Outside,288tasks,0slow,
max1.2097x. Thus key data copies clearly slowed about2.3x, but not every task in
the window slowed significantly. Parallel Wait excess is not summed as workload
loss, and full-call slowdown is not proved by the two local candidates.

Five rotating paired repetitions, per-iteration maximum across three ranks:
semantic-only mean+11.8353%(range8.5994..17.1819%); semantic+msprof
mean+20.7091%(18.6072..22.7786%). Identical public SDK logging remains in all
modes; startup/export/offline diagnosis excluded. These are measured overheads
of the new complete AI_CPU path, not the old near-zero estimate with no semantics.

Final native reports are `reports/coverage-v3-{normal,strong-copy}/` under the
server root. Each contains execution.html,root_causes.json,propagation.html.
Raw captures, numerics, prior versions, receipts and `experiment-summary-v3.json`
are retained. Node0NPU5..7False/5 and the official Device package were read back;
the timer is inactive and registry absent. Local source changes are not committed
or pushed. C++source tests,378diagnosis tests and8worker/guard tests pass.
