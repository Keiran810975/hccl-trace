# 910B 单机 HCCL 异常诊断 Demo 测试报告

## 1. 这次测试做了什么

本次在一台 910B 服务器上运行 3-rank HCCL AllReduce，先采集一份正常 baseline，再对一个明确的通信步骤注入 200 ms 延迟。诊断工具使用 HCCL plog 中的语义记录和 msprof DB 中的真实任务时间，生成 execution graph、resource graph，并比较正常组与异常组。

为补齐“真实资源任务变慢”样例，另外运行了一组独立实验：在 NPU 0 上启动 4 个持续 D2D copy 负载，与 64 MiB AllReduce 竞争 SDMA/HBM 资源，再比较 msprof 中物理 SDMA task 的执行时长及下游依赖。这个实验没有修改 trace，也没有在 HCCL 源码中给设备任务人为加时。

另外使用 baseline 的原始数据副本构造了三种 trace 数据质量异常：

1. 删除 HCCL plog 语义记录；
2. 删除 msprof TASK 记录；
3. 把一个 FFts context 的 profiler task kind 改成不兼容类型。

测试目标是验证以下五项能力：定位指定 Rank/phase/step/task 的通信停顿、识别真实 SDMA 资源任务变慢、识别 Notify 等待异常、还原阻塞传播、拒绝缺失或错误匹配的数据。

## 2. 测试环境

| 项目 | 实际环境 |
|---|---|
| 服务器 | `kunlun-02`，单机 8 x Ascend 910B3 |
| 使用设备 | NPU 0、1、2，共 3 ranks |
| 容器 | `cann-8.5.1-910b-cyx` |
| CANN | 8.5.1 |
| Python | 3.11.14 |
| PyTorch | 2.8.0+cpu |
| torch_npu | 2.8.0.post2 |
| HCCL 路径 | `AllReduceRingFor91093Executor`，实际 level-0 为 `single_ring_direct` concurrent-direct RS/AG |
| 消息大小 | 延迟注入实验每 rank 4 MiB；资源竞争实验每 rank 64 MiB |
| 采集方式 | 每个 rank 一份 consolidated `msprof_*.db`，同时采集 schema-v4 semantic plog |

实验目录位于容器内：

```text
/tmp/zjy-hccl-anomaly-20260923-115850
```

异常注入使用默认关闭的测试补丁 [hcomm_rank_step_delay.patch](../test/anomaly_injection/hcomm_rank_step_delay.patch)。baseline 和异常组使用同一份 `libhccl_alg.so`，SHA256 均为：

```text
ac58b3036f5f72e597a077c9b4efcbb57f849a4bdce1aa415889ef405c8c8e15
```

因此两组之间唯一的实验变量是异常组设置的注入环境变量。

## 3. Baseline

baseline workload 是 3-rank fp32 AllReduce。每个 rank 先填入 `rank + 1`，AllReduce 后每个元素都应为 `1 + 2 + 3 = 6`。

实际结果：

| Rank | AllReduce 时间 | max error | 结果 |
|---:|---:|---:|---|
| 0 | 15.538 ms | 0 | PASS |
| 1 | 14.934 ms | 0 | PASS |
| 2 | 14.529 ms | 0 | PASS |

baseline 诊断产物：

| 指标 | 结果 |
|---|---:|
| semantic rows | 209 |
| exact matched | 189 |
| exact match rate | 90.43% |
| unmatched semantic | 20 |
| execution graph | 482 nodes / 541 edges |
| resource graph | 136 nodes / 192 edges |
| direct Notify exact edges | 54 |
| local Notify exact edges | 54 |
| 图缺失端点、环、禁止边 | 0 |
| dependency graph gate | PASS |

当前 910B concurrent-direct 路径中有 20 条 FFts copy/reduce 语义缺少 graph correlation，所以 `95%` 门槛不能通过；本次对比实验使用 `90%` 门槛，baseline 和异常组均为 90.43%。这不是把异常结果放宽，因为两组的匹配统计完全相同，但它是当前实现需要继续修复的采集限制。

## 4. 通信延迟异常样例

### 4.1 注入位置

异常组只命中一次以下语义位置：

```text
rank=0
phase=allgather_direct
step=0
event=tx_payload_start
occurrence=1
delay=200000 us
```

测试脚本在测量 AllReduce 前有一次 barrier，因此 `occurrence=1` 精确选择被测 AllReduce，而不是前置同步。真值日志确认只注入一次：

```text
[HcclDiagInject] type[task_launch_delay] delay_us[200000]
user_rank[0] phase[allgather_direct] step[0]
event[tx_payload_start] occurrence[1] hit[0]
```

延迟发生在语义 scope 建立后、真实任务创建前，不新增设备任务，也不修改 trace schema。这一设计能在现有 execution/resource graph 中形成可解释的任务间隙和下游等待。

### 4.2 工作负载结果

| Rank | 注入后时间 | max error | 结果 |
|---:|---:|---:|---|
| 0 | 214.823 ms | 0 | PASS |
| 1 | 214.526 ms | 0 | PASS |
| 2 | 213.524 ms | 0 | PASS |

通信结果仍然正确，但所有 rank 的完成时间增加约 200 ms，符合单个 rank 阻塞后 collective 整体等待的预期。

### 4.3 诊断结果

目标任务在同一物理 stream 上的前驱为 `rank 0 / allgather_direct / step 0 / rx_ack_start`，当前任务为 `tx_payload_start`。

| 指标 | Baseline | 异常组 | 增量 |
|---|---:|---:|---:|
| 目标任务入边间隙 | 87.5 us | 199,627.75 us | 199.540 ms |

resource graph 中出现 5 条超过 50 ms 的等待边，其中最关键的传播链为：

| 依赖 | Baseline | 异常组 | 证据 |
|---|---:|---:|---|
| device 0 -> Rank 1，`allgather_direct step 0` data-signal 等待 | 0.095 ms | 199.011 ms | exact |
| Rank 0 -> Rank 2，`allgather_direct step 1` ACK 等待 | 0.334 ms | 198.833 ms | exact |
| Rank 0 本地后续 copy 等待 | 0.601 ms | 199.960 ms | exact |
| Rank 1 本地后续 copy 等待 | 0.605 ms | 199.630 ms | exact |
| Rank 2 本地后续 copy 等待 | 0.600 ms | 199.107 ms | exact |

结论：

| 验证项 | 结果 | 判断依据 |
|---|---|---|
| 指定通信任务停顿定位 | PASS | 精确定位 `rank 0 / allgather_direct / step 0 / tx_payload_start`，间隙增量 199.540 ms |
| Notify / 同步等待异常 | PASS | 出现 199.011 ms 和 198.833 ms 的 exact Notify 等待边 |
| 阻塞传播 | PASS | 异常从 Rank 0 的 step 0 传播到 Rank 1，并在 step 1 继续传播到 Rank 2 |
| 计算正确性 | PASS | 三个 rank 的 `max_error` 均为 0 |

这里诊断的是“通信任务发起/进度停顿”，不是设备 kernel 本身执行 200 ms。现有数据可以定位停顿位置和传播链，但不能单凭这份 trace 判断根因是网络拥塞、CPU 调度还是硬件竞争。

## 5. SDMA/HBM 资源竞争异常样例

### 5.1 构造方法

资源竞争组与 baseline 使用同一份 HCCL 库、同一套 3-rank concurrent-direct AllReduce 和相同输入。唯一变量是在 NPU 0 上并发启动 4 个背景进程，每个进程持续对两个 512 MiB NPU buffer 做异步 D2D copy，每批 8 次后同步，持续 75 秒。

4 个负载进程均正确结束，单进程实测约 148.3 GiB/s，合计约 593.4 GiB/s。这里的 ground truth 是“对 NPU 0 注入了持续 D2D copy 竞争”；HCCL 诊断结果负责验证这种竞争是否表现为物理 SDMA task 变慢，不能进一步把它泛化成任意硬件故障。

### 5.2 Workload 与采集质量

不带 profiler 的 20 次烟测用于确认宏观性能变化，采集实验则各运行 1 次并由 msprof 记录 task 时间。

| 指标 | Baseline | 资源竞争组 | 结果 |
|---|---:|---:|---|
| 20 次 AllReduce 平均时间 | 4.46 ms | 7.53 ms | 增加约 68.7% |
| 等效通信带宽 | 20.05 GB/s | 11.88 GB/s | 下降约 40.7% |
| 三个 Rank `max_error` | 0 | 0 | PASS |
| semantic rows | 75 | 75 | 一致 |
| exact match rate | 100% | 100% | PASS |
| resource task nodes | 42 | 42 | 一致 |
| dependency graph gate | PASS | PASS | PASS |

### 5.3 诊断结果

工具按 `rank/phase/step/slice/event/task_kind` 对 baseline 和异常组的物理资源任务逐一配对，共配对 27 个 SDMA task，未配对 occurrence 为 0。NPU 0 上有两个细粒度 local-copy 任务同时超过 `1.5x` 和 `20 us` 门槛：

| Rank / phase / step / slice / event | Baseline | 资源竞争组 | 增量 | 倍率 |
|---|---:|---:|---:|---:|
| Rank 0 / `reduce_scatter_direct` / 0 / 1 / `copy_start` | 61.25 us | 123.50 us | 62.25 us | 2.016x |
| Rank 0 / `reduce_scatter_direct` / 0 / 2 / `copy_start` | 61.25 us | 123.00 us | 61.75 us | 2.008x |

依赖图还找到了从变慢资源任务出发的两条下游 Notify 关系：

| 传播关系 | Baseline Wait | 资源竞争组 Wait | 增量 | 证据 |
|---|---:|---:|---:|---|
| Rank 0 slice 1 copy -> Rank 1 slice 2 reduce | 0.020 us | 53.101 us | 53.081 us | observed |
| Rank 0 slice 1 copy -> Rank 2 slice 0 reduce | 0 us | 50.681 us | 50.681 us | observed |

结论：真实资源竞争样例 **PASS**。工具定位到了 `Rank 0 / reduce_scatter_direct / step 0 / copy_start / sdma` 的具体慢任务，并解释了它如何让 Rank 1、Rank 2 的下游任务等待。聚合 P95 只有 1.003x，说明只看整个 Rank 的分位数会掩盖局部异常；本项目的细粒度语义配对正好解决了这个问题。

## 6. Trace 数据质量异常

三组数据均从同一 baseline 复制，只修改副本，不重新占用 NPU。

| 样例 | 构造方式 | 诊断结果 | 90% 门禁 |
|---|---|---|---|
| plog 缺失 | 删除 12 条 `[HcclTaskSemantic]` | semantic 209 -> 197；`profiler_only` 293 -> 302 | PASS |
| profiler 缺失 | 删除测量 AllReduce 中 Rank 0 的 12 条 TASK | `unmatched_semantic` 20 -> 32；匹配率 90.43% -> 84.69% | FAIL，符合预期 |
| kind mismatch | 将一个 FFts SDMA context 改成 Notify Wait | `ffts_ctx_kind_mismatches=1`，`invalid_matches=1` | FAIL，符合预期 |

plog 缺失样例说明了当前门禁的一个缺口：删除语义行后，剩余语义的匹配率反而从 90.43% 上升到 91.37%，因此单次 `validate_trace` 不会失败。不过与 baseline 比较时，semantic 总数减少 12、`profiler_only` 增加 9，工具仍能发现数据缺失。正式数据集应同时检查匹配率和相对 baseline 的行数/覆盖率，不能只检查百分比。

## 7. 没有纳入成功结果的尝试

曾尝试通过测试开关把 910B executor 从 concurrent-direct 强制切到 standard Ring。烟测中三个 rank 的输出仍分别停留在 1、2、3，`max_error` 为 5、4、3，说明仅把 `opInfo` 置空不能保证当前 executor 的内存语义正确。该改动已撤回，没有用于 baseline 或异常结论。

因此本报告只采用数值正确性已验证的 concurrent-direct 路径，不把“能生成日志但通信结果错误”的运行算作成功样例。

## 8. 产物与复现入口

本地脚本：

- workload：[multinode_hccl_allreduce.py](../test/multinode_hccl_allreduce.py)
- 延迟注入补丁：[hcomm_rank_step_delay.patch](../test/anomaly_injection/hcomm_rank_step_delay.patch)
- baseline/异常比较：[analyze_single_node_experiment.py](../test/anomaly_injection/analyze_single_node_experiment.py)
- 数据质量样例构造：[construct_trace_quality_cases.py](../test/anomaly_injection/construct_trace_quality_cases.py)
- NPU D2D 资源竞争注入：[npu_sdma_contention.py](../test/anomaly_injection/npu_sdma_contention.py)
- 资源任务对比诊断：[analyze_resource_contention.py](../test/anomaly_injection/analyze_resource_contention.py)

远端关键产物：

```text
/tmp/zjy-hccl-anomaly-20260923-115850/baseline/diagnosis
/tmp/zjy-hccl-anomaly-20260923-115850/injected/diagnosis
/tmp/zjy-hccl-anomaly-20260923-115850/analysis
/tmp/zjy-hccl-anomaly-20260923-115850/quality-cases-final3
/tmp/zjy-hccl-sdma-contention-20260923-1840
```

已下载到本地的精简结果包：

- [自动诊断摘要](../test/out/zjy-910b-anomaly-demo-20260923/analysis/RESULTS.md)
- [机器可读结果](../test/out/zjy-910b-anomaly-demo-20260923/analysis/summary.json)
- [异常等待边](../test/out/zjy-910b-anomaly-demo-20260923/analysis/slow_dependency_edges.csv)
- [baseline resource graph](../test/out/zjy-910b-anomaly-demo-20260923/baseline/dependency.html)
- [异常组 resource graph](../test/out/zjy-910b-anomaly-demo-20260923/injected/dependency.html)
- [数据质量变异清单](../test/out/zjy-910b-anomaly-demo-20260923/quality/manifest.json)

资源竞争实验结果包：

- [自动诊断摘要](../test/out/zjy-910b-sdma-contention-bundle-20260923/analysis/RESULTS.md)
- [机器可读结果](../test/out/zjy-910b-sdma-contention-bundle-20260923/analysis/summary.json)
- [SDMA 任务逐项对比](../test/out/zjy-910b-sdma-contention-bundle-20260923/analysis/resource_task_comparison.csv)
- [受影响的下游依赖边](../test/out/zjy-910b-sdma-contention-bundle-20260923/analysis/affected_dependency_edges.csv)
- [baseline resource graph](../test/out/zjy-910b-sdma-contention-bundle-20260923/baseline/dependency.html)
- [资源竞争组 resource graph](../test/out/zjy-910b-sdma-contention-bundle-20260923/contended/dependency.html)

自动比较脚本的最终判定为：

```text
workload correctness: PASS
target localization: PASS
Notify/wait anomaly: PASS
cross-rank blocking propagation: PASS
physical SDMA task slowdown: PASS
```

## 9. 总结

这次 demo 已经形成两条完整闭环：一条以精确任务发起延迟验证通信进度停顿，另一条以真实 D2D copy 竞争验证物理 SDMA 任务变慢；两条路径都经过 msprof/plog 采集、精确合并、execution/resource graph 和 baseline 对比诊断。

因此，当前单机表格中的 A、B 两类独立根因样例，C、D 两类派生等待/传播现象，以及 trace quality 健壮性样例都已在 910B 上覆盖。工具能定位 Rank、phase、step、event 和物理 task，解释下游等待，并拒绝 profiler 缺失和 FFts 类型错配。仍需改进的是旧 4 MiB 样例中 20 条 FFts graph correlation、plog 行数缺失的独立覆盖率门禁，以及更多强度和重复次数的数据集化运行。
