# 集合通信步骤级打点与因果诊断迁移方案

## 1. 目标

在当前 HCCL/HCOMM 代码体系中建立可维护的步骤级观测能力，使一次集合
通信可以被还原为：

```text
operation
  -> hierarchy/phase
  -> rank
  -> step
  -> slice
  -> wait/transfer/reduce/copy task
  -> causal dependency
```

第一阶段以 Atlas A2/A3 的传统 Ascend 910 单机 8 卡 single-ring
AllReduce 为验收场景，稳定后扩展到 double-ring、跨机 NHR 和新 HCCL
算子架构。

## 2. 设计原则

1. 语义与时间解耦

   算法层描述“这是什么”，profiler 描述“何时发生、耗时多久”。

2. 真实 task 优先

   使用 profiler 的 `Device_id + stream_id + task_id` 对齐，不用 plog
   打印时间替代设备时间。

3. 默认关闭

   未开启功能时不新增设备任务，热路径只保留可预测的快速判断。

4. 不生成合成 marker

   步骤语义绑定到 HCCL 已经创建的真实通信任务。新版不迁移
   `aclprofMarkEx`，也不为步骤分析额外提交 copy/notify task。

5. schema 先行

   先固定字段和语义，再插桩和写脚本，避免每条路径自定义日志。

6. 覆盖实际执行路径

   必须按 executor 选择矩阵检查基类、派生类和 host/AICPU 路径。

7. 诊断结论带置信度

   匹配不完整、时钟未对齐、rank 映射不确定时，只输出候选原因。

## 3. 仓库职责

### 3.1 HCOMM

HCOMM 是传统 AllReduce 的主要实现与打点位置，负责：

- trace context 和任务语义上报；
- Ring/NHR 模板步骤语义；
- executor 阶段边界；
- host dispatcher 与 AICPU SQE 的 task ID 关联；
- HCOMM 内部 UT/ST。

建议根路径：

```text
../hcomm/src/
```

### 3.2 当前 HCCL

当前 HCCL 负责：

- schema 和用户文档；
- 离线解析、覆盖率校验、诊断、制图工具；
- HCOMM 功能的端到端采集说明；
- 为 `src/ops` 新架构提供相同观测接口；
- HCCL API 级 operation 元数据补充。

建议工具路径：

```text
tools/diagnosis/
```

### 3.3 版本基线

实施前必须锁定：

```text
HCCL commit/tag
HCOMM commit/tag
CANN Toolkit
driver/firmware
msprof version
device type
workflow mode
```

当前本地 HCCL 与 HCOMM 均为 `8.5.0-beta.1` 基线，但仍需固定具体提交。
本次调研使用 HCCL `8d6ed05e` 与 HCOMM `2981ffa7`。

## 4. 统一语义模型

### 4.1 必选字段

建议定义 `schema_version=1`，每条事件至少包含：

| 字段 | 含义 |
|---|---|
| `op_id` | 进程内稳定的集合通信实例 ID |
| `op_type` | `allreduce`、`reduce_scatter` 等 |
| `algorithm` | 实际 executor/template 标识 |
| `phase` | `reduce_scatter`、`allgather`、`level1` 等 |
| `step` | phase 内步骤序号 |
| `slice` | 数据分片 ID，未知时为 `-1` |
| `user_rank` | 全局用户 rank |
| `comm_rank` | 当前子通信域 local rank |
| `rank_size` | 当前子通信域大小 |
| `peer_rank` | 依赖或通信对端，未知时为 `-1` |
| `event` | 稳定事件名 |
| `semantic` | `link_rx_ack`、`link_rx_payload_reduce` 等 |
| `stream_id` | 实际设备 stream |
| `task_id` | 实际设备 task |
| `task_kind` | `sdma`、`rdma`、`notify_wait` 等 |
| `source` | `host`、`aicpu`、`ccu` 等 |

建议保留 `node_id/device_id/pid` 作为采集侧补充字段。

### 4.2 事件命名

事件名采用 lower snake case：

```text
op_start/op_end
phase_start/phase_end
tx_ack_start/tx_ack_end
rx_ack_start/rx_ack_end
tx_data_signal_start/tx_data_signal_end
rx_data_signal_start/rx_data_signal_end
tx_payload_start/tx_payload_end
rx_payload_reduce_start/rx_payload_reduce_end
rx_payload_copy_start/rx_payload_copy_end
local_copy_start/local_copy_end
```

`event` 表示边界，`semantic` 表示任务类别。不要仅通过 event 子串推断
semantic；允许调用者显式传入。

### 4.3 operation ID

不再以固定 stream 的 local copy 作为首选 operation 边界。建议在算子进入
HCOMM 时生成单调 `op_id`，并通过 `OpParam` 或内部 context 向 executor 和
模板传播。

若短期内修改参数结构风险过大，可先使用：

```text
process-local atomic counter + user rank + op type
```

并在 executor 入口设置线程局部 operation context。旧 fallback 仅用于解析
历史数据。

## 5. HCOMM 实现方案

### 5.1 任务语义基础设施

在以下位置新增内部模块：

```text
src/common/debug/profiling/inc/task_semantic_trace.h
src/common/debug/profiling/task_semantic_trace.cc
src/algorithm/base/alg_template/component/task_semantic_scope.h
src/algorithm/base/alg_template/component/task_semantic_scope.cc
```

`task_semantic_scope` 负责把算法层的
`event/phase/step/rank/slice/semantic` 写入 thread-local context；
`task_semantic_trace` 负责在 HCCL Profiling 获得真实
`stream_id/task_id/task_type` 后输出完整记录。

为了降低首批迁移改动量，也可以暂时保留
`MarkAlgCustomTracePoint` 这个旧函数名作为兼容 facade，但其实现只更新或
清理语义 context，不再接收或使用 `Stream`，也不调用 profiler marker API。

相较旧原型需要改进：

- 使用 schema version；
- context 使用 RAII scope，避免异常返回后未 clear；
- 支持嵌套 context，至少保存前一层；
- 缓存环境开关；
- 明确 `_start` 设置 context、`_end` 清理 context；
- 检测一次 scope 内没有真实 task 回调的情况；
- 检测一个 scope 意外匹配多个 task 的情况；
- 敏感地址和 payload 内容不得进入日志。

建议开关：

```text
HCCL_STEP_TRACE=0|1
HCCL_STEP_TRACE_DETAIL=operation|phase|step|task
```

兼容期可将 `HCCL_TASK_SEMANTIC_TRACE=1` 映射到 `HCCL_STEP_TRACE=1`。
`HCCL_CUSTOM_PROF_TRACE` 不再支持，因为它只控制旧版 `aclprofMarkEx`
分支。

### 5.2 构建目标隔离

HCOMM 的 profiling CMake 当前同时服务 `hccl_alg` 与 `ccl_kernel`。建议：

- 纯 context/schema 代码可编入 host 和 device；
- 不引入 `dlopen`、`libmsprofiler.so` 或 `aclprofMarkEx`；
- AICPU/device 通过已有 SQE/task 信息输出语义；
- CMake 分别列出 host/device source，避免依赖泄漏。

需要更新：

```text
common/debug/profiling/CMakeLists.txt
algorithm/base/alg_template/component/CMakeLists.txt
相关 include 目录
```

### 5.3 Dispatcher 关联

旧原型只覆盖了部分 dispatcher。新实现应建立统一上报点：

#### Host dispatcher

旧版已在 `TaskProfiling::Run(const TaskData&)` 入口调用：

```text
ReportTaskSemanticTrace(stream_id, task_id, task_type)
```

新版应保留这一连接方式：语义上报必须发生在检查 msprof 是否订阅、workflow
是否提前返回之前，使步骤语义功能不依赖 addition-info 上报状态。

覆盖：

- SDMA copy；
- reduce inline/TBE；
- notify record/wait；
- RDMA 相关任务。

#### AICPU dispatcher

在 `GetNextSqeBufferAddr` 或等价接口返回 task ID 后、SQE 写入成功处上报。
重点检查：

- `SignalWait`；
- `SignalRecord`；
- `CopyData`；
- `RdmaSend`；
- cache hit/replay；
- placeholder 和 task ID 翻转。

不能只迁移旧版 `RdmaSend` 的特例，否则大部分 AICPU task 仍无法对齐。

### 5.4 不迁移 `aclprofMarkEx`

不新增以下旧版内容：

```text
AclprofMarkExFunc
GetAclprofMarkExFunc
dlopen("libmsprofiler.so")
dlopen("libascendcl.so")
HCCL_CUSTOM_PROF_TRACE
PROFILER_TRACE_EX marker
```

理由：

1. 算法语义在调用 marker API 前已写入 thread-local；
2. HCCL Profiling 回调直接提供真实 task 的 stream/task ID；
3. 合并脚本只解析 `[HcclTaskSemantic]`；
4. 合并脚本明确跳过 `PROFILER_TRACE_EX`；
5. 核心 interval 使用真实 task 的 start/stop，不需要合成 marker。

若跨多个独立 `msprof` 会话确实需要时间基校准，应作为单独的采集/校准
课题设计。旧版 `comm_topo_exchange_hw_marker` 使用真实 D2D copy，和
`aclprofMarkEx` 不是同一机制，也不应混入步骤 trace API。

### 5.5 第一批算法插桩

以 single-ring AllReduce 为主线：

```text
coll_all_reduce_ring_for_910_93_executor.cc
reduce_scatter_ring_concurrent_direct.cc
all_gather_ring_concurrent_direct.cc
sender.cc
reducer.cc
```

插桩层级：

1. executor 入口和出口：确定 `op_id`、algorithm、总边界；
2. RS/AG 入口和出口：确定 phase；
3. 每个 step：计算 tx/rx slice 和 peer；
4. ACK 与 data signal：标记等待对象；
5. payload/reduce/copy：标记实际数据任务；
6. local copy：标记初始化和尾部回填。

### 5.6 executor 覆盖矩阵

第一批实现完成后，必须检查并补齐：

```text
CollAllReduceRingFor91093Executor
CollAllReduceFastDoubleRingFor91093Executor
CollAlignedAllReduceDoubleRingFor91093Executor
CollAllReduceRingZerocopyExecutor
其他由 alg_configurator/operator 可能选择的 executor
```

建议增加“路径自描述”事件：

```text
algorithm_selected
executor_enter
template_enter
```

这样采集数据能直接证明实际路径，无需从配置反推。

### 5.7 新 HCCL 架构适配

传统链路稳定后，在当前 HCCL 中抽取同一 schema 的轻量实现，接入：

```text
src/ops/executor_base.*
src/ops/alg_template_base.*
src/ops/scatter/algo/template/*
src/ops/channel/*
```

新架构使用 `ThreadHandle` 和 `HcommChannel*OnThread`，若无法直接取得真实
task ID，应优先推动 HCOMM primitive 返回或回调 task token，而不是退回到
仅靠主机日志时间。

## 6. 离线工具迁移与完善

### 6.1 目录与模块

建议将旧脚本重构为：

```text
tools/diagnosis/
├── schema.py
├── parse_plog.py
├── parse_msprof.py
├── merge_timeline.py
├── validate_trace.py
├── build_dependency_graph.py
├── diagnose.py
└── fixtures/
```

保留命令行兼容 wrapper，避免现有采集流程立即失效。

### 6.2 合并规则

首选键：

```text
(node_id, device_id, stream_id, task_id)
```

必须输出：

- 总语义行数；
- 可匹配行数与覆盖率；
- duplicate key；
- unmatched semantic；
- unmatched profiler task；
- 每种 task kind 的覆盖率；
- 每个 rank/op/phase 的完整性。

低于配置阈值时，诊断命令应失败或明确标记结果不可信。

### 6.3 依赖建模

Ring 场景至少包含：

```text
same_stream_order
same_rank_program_order
ack_dependency
data_ready_dependency
payload_producer_consumer
phase_dependency
```

边的建立应使用明确的：

```text
op_id + phase + step + slice + rank + peer
```

不再只依靠 `rank-1/rank+1` 推断。拓扑推断可作为 fallback，并在输出中标注。

### 6.4 因果诊断

第一版规则引擎可输出：

| 现象 | 候选原因 |
|---|---|
| `rx_ack_wait` 长 | 下游接收准备或前序 payload 延迟 |
| `rx_data_signal_wait` 长 | 上游数据尚未 ready |
| payload 短但前置等待长 | 通信本身正常，延迟由依赖传播 |
| payload/reduce 本体长 | 链路、数据量、reduce 或资源竞争 |
| 多 rank 同时拉长 | 公共资源、阶段切换或时间基问题 |
| 因果边出现负间隔 | 时钟未对齐、rank 映射错误或匹配错误 |

输出应包含：

```text
suspect node
critical predecessor chain
dominant wait type
source rank/step/slice
evidence rows
confidence
data-quality warnings
```

## 7. 分阶段实施

### 阶段 0：锁定基线与样本

- 确定配套 HCCL/HCOMM/CANN 版本；
- 保存旧版单机 8 卡可复现实验及输出；
- 固化 1 至 3 组 plog、`task_time.csv` 和期望图；
- 记录实际 executor 选择条件。

完成标准：同一输入可重复生成旧版基准结果。

### 阶段 1：迁移基础设施

- 在 HCOMM 加入 schema、context、开关和 task 上报；
- 完成 host dispatcher 最小闭环；
- 增加序列化和 context UT；
- 不修改算法语义。

完成标准：人为设置 context 后可稳定关联真实 task ID。

### 阶段 2：单机 single-ring AllReduce

- 插桩 executor、direct RS/AG、sender/reducer；
- 迁移合并工具；
- 生成 rank-step timeline；
- 验证 8 卡所有 rank 和 step 的覆盖率。

完成标准：

- operation 边界不依赖固定 stream fallback；
- 关键语义匹配覆盖率建议不低于 95%；
- 可重建 `RxAck -> Signal -> payload`。

### 阶段 3：因果图与自动诊断

- 重构依赖图；
- 实现关键前驱链与等待归因；
- 增加数据质量检查；
- 用注入延迟或模拟任务验证归因方向。

完成标准：已知慢 rank/step 能被定位，且证据链可回查 CSV。

### 阶段 4：优化路径

- fast/aligned double ring；
- zero-copy；
- host/AICPU 两种 workflow；
- cache/replay 场景。

完成标准：算法选择变化不会导致整段语义消失。

### 阶段 5：多机与 NHR

- 明确 node、global rank、sub-comm rank 映射；
- 为跨节点 profiler 建立统一时间基或相对因果模型；
- 将 slice 纳入回填路径；
- 扩展 NHR 依赖规则。

完成标准：不存在未解释的负依赖间隔，跨节点结论带时间基证明。

### 阶段 6：新 HCCL 算子架构

- 将 schema 和 API 适配到 `src/ops`；
- 先覆盖 Scatter；
- 为后续公开 AllReduce 新实现预留统一接口。

## 8. 测试方案

### 8.1 单元测试

HCOMM：

- 环境开关；
- context 嵌套与 RAII；
- schema 序列化；
- task type 映射；
- disabled path；
- dispatcher task ID 上报；
- AICPU task ID 翻转与 cache 场景。

工具：

- plog 字段顺序变化；
- CSV BOM 和列名变化；
- duplicate/unmatched；
- operation ID；
- rank 映射；
- Ring 边和关键路径；
- 不完整数据的置信度降级。

### 8.2 集成测试

建议矩阵：

| 维度 | 最小覆盖 |
|---|---|
| rank | 1、2、8 |
| device | A2、A3 |
| topology | single ring、double ring |
| workflow | host、AICPU |
| data size | 小、中、大 |
| profiler | 开/关 |
| trace | 开/关 |

### 8.3 性能测试

分别测量：

- trace 关闭时的延迟与带宽；
- operation/phase 级语义；
- step 级语义；
- task 级完整语义。

所有级别都复用已有真实 device task，不得为了打点提交额外任务。trace
关闭时性能差异应处于测试噪声范围。

## 9. 风险与控制

| 风险 | 控制措施 |
|---|---|
| HCCL/HCOMM 版本不配套 | 实施前锁定 tag，文档记录矩阵 |
| 优化 executor 漏点 | 建立选择矩阵和路径自描述事件 |
| task ID 与源码调用错位 | 在实际 task/SQE 分配点上报 |
| cache/replay 改变 task ID | 单独建模 cache hit 与重放 |
| scope 未覆盖任何真实 task | 计数并报告 unmatched semantic scope |
| scope 覆盖多个真实 task | 显式声明 one-shot 或 multi-task scope 语义 |
| 多机时钟不统一 | 先做质量检测，不满足条件不输出强因果 |
| local/global rank 混淆 | schema 同时记录 user/comm/peer rank |
| 日志量过大 | detail 级别、op/rank 过滤和采样 |

## 10. 预期交付物

1. HCOMM 内部步骤 trace 基础设施与算法插桩。
2. HCOMM host/AICPU task ID 语义关联。
3. 当前 HCCL 中的 schema、采集说明与离线工具。
4. 单机 Ring AllReduce rank-step 时间线和依赖图。
5. 自动因果诊断报告及数据质量报告。
6. UT、ST、性能对比和多版本兼容说明。

## 11. 推荐的首个开发切片

首个可合入切片应保持小而完整：

1. 在配套 HCOMM 分支新增 versioned semantic context。
2. 只接入 host dispatcher 的 SDMA、notify、reduce task。
3. 只插桩 single-ring direct RS/AG。
4. 在当前 HCCL 迁移并重构 merge/validate 工具。
5. 用单机 8 卡 AllReduce 验证 operation、rank、step、task 对齐。

该切片完成后再扩展 AICPU、double ring 和多机，能够显著
降低同时修改算法、框架、平台和分析脚本带来的定位难度。
