# HCCL 新旧版本与 HCOMM 仓库差异总结

## 1. 调研范围

本文基于 2026-06-14 的本地工作区快照，对以下三个仓库进行对比：

| 角色 | 路径 | 分支/提交 | 版本信息 |
|---|---|---|---|
| 当前 HCCL | `hccl` | `init` / `8d6ed05e` | `8.5.0-beta.1` |
| 旧版原型 | `../../cann-hccl` | `my-hccl-8.2rc1` / `f2da6eb7` | `8.2.0.0` |
| 当前 HCOMM | `../hcomm` | `8.5.0` / `2981ffa7` | `8.5.0-beta.1` |

当前 HCCL 的 `version.info` 要求 HCOMM `>=8.5.0`，本地 HCOMM
`version.info` 为 `8.5.0-beta.1`，二者处于同一 8.5 配套基线。实施时仍应
固定具体提交、Toolkit、驱动和 profiler 版本，避免后续分支移动影响结果。

## 2. 总体架构变化

### 2.1 旧版 `cann-hccl`

旧仓库同时包含：

- 通信框架；
- 完整通信算法与 executor；
- 平台任务下发与 profiling；
- AllReduce、ReduceScatter、AllGather 等成熟算子；
- 本次功能原型的源码打点与离线分析工具。

核心路径为：

```text
src/domain/collective_communication/
├── algorithm
├── common/debug/profiling
├── framework
└── platform
```

旧版功能可在同一个仓库内修改算法模板、executor、dispatcher 和 profiling
模块，因此原型提交跨越了 32 个文件，新增约 7,392 行。

### 2.2 当前 `hccl`

当前仓库采用新的通信算子开发架构，主要代码位于：

```text
src/
├── common
└── ops
    ├── channel
    ├── registry
    ├── scatter
    └── topo
```

当前公开实现以 Scatter 为完整参考。`src/ops/interface/hccl_collective_op.cc`
中的 AllReduce 等 API 主要转发到 HCOMM 的 `*Inner` 接口。构建目标
`libhccl.so` 也显式链接 `hcomm`。

因此，旧版 AllReduce 步骤级打点不能直接迁入当前 `hccl/src/ops`：

- 当前仓没有对应的 Ring AllReduce 模板和 executor；
- 当前仓无法在 HCOMM 内部任务创建处取得完整语义；
- 只在公共 API 外层打点只能得到算子级边界，无法区分 ACK、Signal、
  payload、reduce 等步骤。

### 2.3 当前 `hcomm`

`../hcomm/src` 保留了与旧仓高度对应的传统实现：

```text
src/
├── algorithm
│   ├── base/alg_template
│   └── impl/coll_executor
├── common/debug/profiling
├── framework
└── platform
```

例如下列文件均存在直接对应关系：

| 旧版 `cann-hccl` | 当前 HCOMM |
|---|---|
| `algorithm/base/alg_template/component/sender.cc` | `src/algorithm/base/alg_template/component/sender.cc` |
| `algorithm/base/alg_template/component/reducer.cc` | `src/algorithm/base/alg_template/component/reducer.cc` |
| `temp_reduce_scatter/reduce_scatter_ring_concurrent_direct.cc` | 同名 HCOMM 文件 |
| `temp_all_gather/all_gather_ring_concurrent_direct.cc` | 同名 HCOMM 文件 |
| `coll_all_reduce_ring_for_910_93_executor.cc` | 同名 HCOMM 文件 |
| `common/debug/profiling` | `src/common/debug/profiling` |

这些文件并非逐字相同。HCOMM 已发生接口、代码风格、算法选择与功能演进，
例如 `coll_all_reduce_ring_for_910_93_executor.cc` 的新旧文件行数分别约为
585 和 554，差异接近 500 行。因此迁移应以当前 HCOMM 为基线重新插桩，
不能直接套用旧 patch。

## 3. 旧版功能组成与有效数据链路

进一步核查旧版代码和后处理脚本后，可以确认：步骤级时间线与因果诊断的
有效数据链路只有“thread-local 语义上下文 + HCCL Profiling 回调”这一条。
`aclprofMarkEx` 虽然存在于原型中，但不属于最终分析所需链路。

### 3.1 thread-local 任务语义

`MarkAlgCustomTracePoint` 实际承担了两个不同职责：

1. 调用 `UpdateTaskSemanticTrace`，把 `event/phase/step/rank/slice/semantic`
   写入 thread-local `TaskSemanticTraceInfo`；
2. 当 `HCCL_CUSTOM_PROF_TRACE=1` 时，额外调用 `aclprofMarkEx` 提交 marker。

代码执行顺序是先更新语义上下文，再判断 `IsAlgCustomTraceEnabled()`。因此
只设置：

```text
HCCL_TASK_SEMANTIC_TRACE=1
```

而不设置 `HCCL_CUSTOM_PROF_TRACE` 时，函数会在更新 thread-local 后直接
返回，完全不调用 `aclprofMarkEx`，步骤语义链路仍然成立。

`task_semantic_trace.{h,cc}` 使用线程局部上下文，在 dispatcher 分配真实
`stream_id/task_id` 后输出：

```text
[HcclTaskSemantic]
stream_id task_id task_type task_kind
event phase step rank ranksize slice semantic
```

作用：

- 将源码语义绑定到真实硬件任务，而非日志打印时间；
- 后处理可用 `(Device_id, stream_id, task_id)` 对齐 `task_time.csv`；
- 支持区分 `sdma`、`rdma`、`reduce_inline`、`notify_record`、
  `notify_wait` 等任务类型。

关键连接点位于 `TaskProfiling::Run(const TaskData&)`：

```text
ReportTaskSemanticTrace(taskData.streamID, taskData.taskID, taskData.taskType)
```

这说明 `stream_id/task_id` 来自 HCCL 自身 Profiling 保存真实任务的回调，
不是来自 `aclprofMarkEx`。

### 3.2 `aclprofMarkEx` 未被核心后处理消费

`tools/hccl_merge_rank_step_timeline.py` 的行为进一步证明：

- plog 只解析包含 `[HcclTaskSemantic]` 的行；
- 合并键为 `(Device_id, stream_id, task_id)`；
- 读取 `task_time.csv` 时明确跳过 `kernel_type == PROFILER_TRACE_EX`；
- 没有解析 `aclprofMarkEx` 消息内容的逻辑。

因此 `aclprofMarkEx` 生成的 marker 行不会进入 merged timeline、rank-step
interval 或 ACK/Signal 依赖图。对当前目标而言，它既不提供必要字段，也不
提供被消费的时间信息，可以从新版设计中删除。

需要区分旧原型后期新增的 `comm_topo_exchange_hw_marker`：它使用两次真实
D2D copy 作为多 profiling 会话的本地时间锚点，不是 `aclprofMarkEx`
marker。该能力只服务跨会话时间基实验，不是单机步骤级因果分析的前置
条件，且会提交额外设备任务。

### 3.3 语义 scope 的边界含义

旧实现中：

- `_start` 事件设置 thread-local context；
- 随后的真实 HCCL task 在 Profiling 回调中读取并上报该 context；
- `_end` 事件清理 context。

所以 `_end` 不会天然产生一个独立的硬件结束时间。当前分析使用真实 task
自身的 `task_start/task_stop` 构造 interval，已经足够。若未来需要没有
真实任务对应的纯边界，应绑定现有 notify/copy task，或设计有明确消费者
的 profiling 记录，而不是恢复 `aclprofMarkEx`。

### 3.4 算法插桩

旧版已在以下层级放置语义点：

- executor：AllReduce 起止、机内/机间/level2 分支；
- Ring/NHR 模板：phase、step、slice；
- `sender.cc`：payload 与 data signal 发送；
- `reducer.cc`：payload 接收、copy、reduce；
- direct Ring：ACK、data signal、payload、local copy；
- AICPU dispatcher：RDMA doorbell 等实际 SQE；
- communicator 初始化：主机等待语义；跨会话硬件时间锚点属于实验项。

典型事件包括：

```text
allreduce_start/end
tx_ack_start/end
rx_ack_start/end
tx_data_signal_start/end
rx_data_signal_start/end
tx_payload_start/end
rx_payload_reduce_start/end
rx_payload_copy_start/end
copy_start/end
```

### 3.5 后处理与因果图

旧仓 `tools` 下有 10 个 Python 脚本，形成以下流程：

```text
plog + task_time.csv
  -> 按 device/stream/task 合并
  -> 生成 rank-step interval
  -> 校验匹配覆盖率与时钟对齐
  -> 构建 ACK、Signal、payload 依赖图
  -> 输出 CSV/SVG
```

主体脚本：

| 脚本 | 作用 |
|---|---|
| `hccl_merge_rank_step_timeline.py` | 合并语义日志和硬件任务时间 |
| `hccl_ack_signal_dependency_graph.py` | 生成 Ring ACK/Signal 依赖图 |
| `hccl_semantic_task_timeline_graph.py` | 生成语义任务时间线 |
| `hccl_stage_dependency_graph.py` | 生成阶段级依赖关系 |
| `hccl_nhr_dependency_graph.py` | NHR 依赖建模 |
| `hccl_clock_alignment_check.py` | 检查跨 rank 时间基质量 |
| `hccl_calibrate_intranode_offsets.py` | 实验性机内偏移校准 |

## 4. 当前仓库已有能力与缺口

### 4.1 当前 `hccl` 已有能力

- 公共 HCCL API 和 HCOMM 转发；
- 新算子架构的 `ExecutorBase`、`AlgTemplateBase`、registry、channel；
- Scatter Ring、NHR、Mesh 等模板，可作为未来新架构插桩范例；
- `ThreadHandle` 与 `HcommChannel*OnThread` 原语；
- LLT/ST 框架和模拟通信组件。

### 4.2 当前 `hccl` 缺口

- 没有传统 AllReduce Ring executor 源码；
- 没有旧版 `alg_custom_trace`；
- 没有 `task_semantic_trace`；
- 没有步骤语义日志 schema；
- 没有合并、覆盖率校验和依赖图工具；
- 没有针对该功能的测试 fixture 与使用文档。

### 4.3 当前 HCOMM 已有能力

- 完整的传统 Ascend 910 算法和 executor；
- host 与 AICPU/device 两种任务下发路径；
- profiler、dispatcher、stream/task ID 分配逻辑；
- `hccl_alg`、`hcomm`、`ccl_kernel` 多目标构建；
- 更完整的 UT/ST 与 legacy 算法测试；
- 现有 ATrace、profiling 和任务异常基础设施。

### 4.4 当前 HCOMM 缺口

本地检索未发现以下原型能力：

```text
alg_custom_trace
MarkAlgCustomTracePoint
task_semantic_trace
HcclTaskSemantic
HCCL_TASK_SEMANTIC_TRACE
```

`HCCL_CUSTOM_PROF_TRACE`/`aclprofMarkEx` 属于旧版冗余 marker 分支，不作为
新版缺口。也就是说，最合适的算法插桩落点存在，但有效观测基础设施尚未迁入。

## 5. 构建与发布边界变化

旧仓中的功能曾同时修改算法库和框架库。当前拆仓后应按所有权处理：

| 内容 | 建议归属 |
|---|---|
| 传统 AllReduce/RS/AG 算法语义点 | HCOMM |
| HCOMM dispatcher 的 task ID 语义上报 | HCOMM |
| HCOMM profiling 上下文 | HCOMM |
| 当前 HCCL 新 Scatter 架构的通用 trace API | 当前 HCCL，后续阶段 |
| 离线合并、诊断和绘图工具 | 当前 HCCL 的 `tools/diagnosis` 或独立工具包 |
| 用户文档、schema、样例 | 当前 HCCL |
| 公共 API 级 operation 边界 | 可在当前 HCCL 增补，但不能替代 HCOMM 内部打点 |

HCOMM 中同一源码可能参与 `hccl_alg` 与 `ccl_kernel`。新版只需迁移
thread-local context、语义序列化和真实 task 回调，不引入 `dlopen`、
`libmsprofiler.so` 或 `aclprofMarkEx`，因此也减少了 host/device 构建分支
和运行时动态符号依赖。

## 6. 原型中的已知限制

1. 事件 schema 依赖正则解析日志，缺少显式版本。
2. 部分 operation 边界依赖固定 stream 47 的 fallback，移植性有限。
3. thread-local 单层上下文不支持可靠嵌套。
4. `aclprofMarkEx` 与核心语义链路重复，增加设备 marker 和动态加载复杂度，
   但后处理明确不消费其输出。
5. optimized executor 覆盖方法曾造成“基类有点、实际路径无点”的问题。
6. 多节点 trace 的时钟基、local/global rank、slice 映射仍未完全收敛。
7. `read+reduce` 在某些实现中是远端读取与本地 reduce 的组合窗口，不能
   简单解释为纯计算耗时。
8. AICPU SQE cache 命中、重放或 placeholder 可能改变 task ID 与源码调用
   的一一对应关系，需要在当前 HCOMM 重新验证。

## 7. 结论

迁移的主要目标仓不是当前 `hccl` 单仓，而是：

```text
HCOMM：产生可靠的步骤语义和真实 task 关联
HCCL：承载公开文档、离线工具，并为新架构建立同一套协议
```

旧版源码仍有很高参考价值，因为 HCOMM 8.5 保留了直接对应结构；但由于
代码已演进，正确做法是迁移“语义模型与机制”，而不是迁移文件或整块
patch。
