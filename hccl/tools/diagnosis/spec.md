# HCOMM 8.5.0 差异调查与步骤语义 Trace 规格

## 1. 文档目的

本文记录当前工作区 `hccl-trace/hcomm` 相对相邻 8.5.0 源码仓
`../hcomm` 的净源码差异，并解释这些改动形成的运行时行为、数据契约、覆盖范围与已知风险。

本文是对当前工作树的静态快照，不代表这些改动已经通过 HCOMM 构建、设备功能测试或性能验收。
后续实施任务见同目录的 `task.md`。

## 2. 比较边界与基线

### 2.1 两侧版本

| 项目 | 路径/状态 |
|---|---|
| 基线 | `C:\Users\Admin\Desktop\ATC\hcomm` |
| 基线分支 | `8.5.0`，与 `origin/8.5.0` 同步 |
| 基线提交 | `2981ffa77fd5a7bfe7e64055eb3ec4fe762c0b9f` |
| 基线工作树 | 干净 |
| 当前源码 | `C:\Users\Admin\Desktop\ATC\hccl-trace\hcomm` |
| 当前分支 | `dev-innerDia` |
| 当前 HEAD | `7db54477d156efaa45e3caf7f8cd5d0caa195d64` |
| 当前工作树 | 在 HEAD 之上还有 18 个已跟踪文件的未提交修改 |

相邻基线仓的 HEAD 与当前仓内 `8.5.0` ref 指向同一个提交。因此，以下两种比较在源码内容上等价：

```text
../hcomm/src  <->  hcomm/src 当前工作树
2981ffa7      <->  hcomm 当前工作树
```

### 2.2 比较方法

目录级主检查使用：

```powershell
git diff --no-index --stat -- ..\hcomm\src hcomm\src
```

再使用当前仓的 Git diff 审阅每个 hunk、区分已提交层与未提交层：

```powershell
git -C hcomm diff 8.5.0
git -C hcomm diff 8.5.0 HEAD
git -C hcomm diff HEAD
```

比较范围为 `hcomm/src` 内源码和源码 CMake 清单；不包含 `.git`、构建产物、部署包或其他生成文件。

### 2.3 总体规模

当前工作树相对 `../hcomm` 的净差异为：

- 20 个文件；
- 新增 4 个文件；
- 修改 16 个文件；
- 新增 1,023 行，删除 79 行。

统计使用 `git diff 8.5.0 --numstat` 对当前工作树取净值；HEAD 已提交层与未提交层存在
同文件反复修改，不能把两层行数直接相加。

特别说明：当前 Git 状态将
`coll_all_reduce_ring_for_910_93_executor.cc` 标记为相对 HEAD 已修改，是因为工作树撤回了
HEAD 中新增的 4 行 executor 粗粒度 scope。该文件当前内容与 `../hcomm` 相同，因此不属于最终净 diff。

## 3. 改动结论

8.5.0 原始 HCOMM 不生产步骤级 task 语义。当前源码增加了一条 Host 侧语义生产链：

```text
RS/AG 算法模板建立 phase/step/slice/rank context
  -> Sender/Reducer 或模板叶子操作补充 event/semantic
  -> TaskData 构造时捕获 TLS 语义快照
  -> TaskProfiling 获得 device/stream/task/type/submit timestamp
  -> plog 输出 versioned [HcclTaskSemantic]
  -> HCCL Python 工具与 msprof DB 物理 TASK 合并
```

主要功能包括：

1. 新增 `HCCL_STEP_TRACE=1` 控制的步骤语义基础设施；
2. 新增支持嵌套恢复和一次性消费的 RAII scope；
3. 在 task 被创建时保存语义快照，避免延迟上报时读到已经变化的 TLS；
4. 输出物理 `device_id`、真实语义 stream、HCCL task id、提交时间和 notify 元数据；
5. 在离线 exact 合并后使用 msprof DB 的 `(group_name, op_name)` 标识 collective
   invocation，不在 HCOMM 重复生成实例身份；
6. 覆盖 single-ring concurrent-direct AllReduce 的 ReduceScatter/AllGather 核心事件；
7. 为触发上述路径加入两处明确标记为 `[TEST PATCH]` 的算法选择改动。

最后一项会改变 910B 的正常算法选择，不应直接作为生产默认行为发布。

## 4. 逐文件 Diff 清单

| 文件 | 行数 | 改动性质 | 功能解释 |
|---|---:|---|---|
| `src/algorithm/base/alg_template/component/CMakeLists.txt` | `+2/-1` | 构建接入 | 将 `task_semantic_scope.cc` 编入 `hccl_alg`。 |
| `src/algorithm/base/alg_template/component/task_semantic_scope.h` | 新文件 | semantic scope | 声明完整 semantic 与事件覆盖两层 scope。 |
| `src/algorithm/base/alg_template/component/task_semantic_scope.cc` | 新文件 | semantic TLS | 实现 semantic TLS 的保存恢复及 one-shot 事件。 |
| `src/algorithm/base/alg_template/component/sender.cc` | `+9/-0` | 发送叶子插桩 | 为 Tx payload、Tx data signal 提供事件语义。 |
| `src/algorithm/base/alg_template/component/reducer.cc` | `+138/-39` | 接收/归约叶子插桩 | 为 Rx payload copy/reduce、Rx data signal 提供事件语义，并限制 vector 路径只标注首个提交。 |
| `src/algorithm/base/alg_template/temp_reduce_scatter/reduce_scatter_ring_concurrent_direct.cc` | `+126/-23` | RS 模板插桩 | 注入 phase/step/slice/rank/peer、ACK、payload、signal 和 local copy 语义。 |
| `src/algorithm/base/alg_template/temp_all_gather/all_gather_ring_concurrent_direct.cc` | `+72/-9` | AG 模板插桩 | 注入 phase/step/slice/rank/peer、ACK、payload、signal 和 local copy 语义。 |
| `src/algorithm/impl/alg_configurator.cc` | `+3/-2` | 测试路径改写 | 在特定 910B 全 HCCS 条件下把默认 NP mesh 强制改为 NP single ring。 |
| `src/algorithm/impl/operator/all_reduce_operator.cc` | `+3/-0` | 测试路径改写 | 多卡 ring topology 时显式选择 `AllReduceRingFor91093Executor`。 |
| `src/common/debug/profiling/CMakeLists.txt` | `+2/-1` | 构建接入 | 将 `task_semantic_trace.cc` 编入 `hccl_alg`。 |
| `src/common/debug/profiling/inc/task_semantic_trace.h` | 新文件 | 语义接口 | 定义语义结构、开关、TLS、捕获、probe 和上报 API。 |
| `src/common/debug/profiling/task_semantic_trace.cc` | 新文件 | 语义实现 | 实现开关、task kind、one-shot、FFts correlation 和 schema v4 plog 输出。 |
| `src/common/debug/profiling/inc/task_profiling_pub.h` | `+41/-1` | TaskData 扩展 | 保存语义 stream 和语义快照；构造 DMA/Reduce/Notify/AIV TaskData 时捕获 context。 |
| `src/common/debug/profiling/task_profiling.cc` | `+22/-2` | 上报链集成 | 注入 device id、submit timestamp、notify 元数据，并处理 capture stream 与物理 stream 的区别。 |

## 5. 步骤语义基础设施

### 5.1 开关

`IsTaskSemanticTraceEnabled()` 在第一次调用时缓存结果：

1. `HCCL_STEP_TRACE=1` 时启用；
2. 否则兼容检查 `HCCL_TASK_SEMANTIC_TRACE=1`；
3. 其他值或未设置时禁用。

开关使用函数静态常量，只在进程内初始化一次。因此运行中修改环境变量不会动态改变状态。

关闭时，scope 的 set/get/clear 和语义上报快速返回，不输出 `[HcclTaskSemantic]`。

### 5.2 `TaskSemanticTraceInfo`

新增结构体包含以下信息：

| 字段 | 默认值 | 当前来源/用途 |
|---|---|---|
| `algorithm` | `nullptr` | 当前为 `single_ring_direct`。 |
| `event` | `nullptr` | 叶子 task 的动作名；必须非空才可捕获。 |
| `phase` | `nullptr` | 当前为 `reduce_scatter_direct` 或 `allgather_direct`。 |
| `semantic` | `nullptr` | 对 event 的稳定语义分类；必须非空才可捕获。 |
| `source` | `"host"` | 表示语义由 Host 侧插桩产生。 |
| `submitTs` | `0` | `hrtMsprofSysCycleTime()` 的 Host 提交周期时间。 |
| `notifyId` | `0` | Notify task 从 `TaskParaNotify.notifyID` 补齐。 |
| `notifyStage` | `-1` | Notify stage。 |
| `step` | `0` | phase 内的逻辑因果桶；不是 physical task identity 或唯一 task 序号。 |
| `slice` | `0` | 算法 rank slice 编号；不是 vector element、字节 offset 或 primitive ordinal。 |
| `userRank` | `0` | 用户通信域 rank。 |
| `commRank` | `0` | 算法内部通信 rank；工厂可显式传入。 |
| `rankSize` | `0` | 通信域大小。 |
| `peerRank` | `INVALID_VALUE_RANKID` | 当前动作的对端 rank。 |
| `oneShot` | `false` | 为 true 时，首个成功捕获的 TaskData 消费当前 context。 |

`MakeTaskSemanticTraceInfo()` 默认使用 `single_ring_direct`。如果调用方没有显式传
`commRank`，它回退到 `userRank`；当前多卡 RS/AG 路径显式传入模板的 `rank`，避免将
comm rank 与 user rank 混为一谈。

### 5.3 TLS 与 RAII scope

semantic context 由两个 thread-local 变量保存：

```text
g_taskSemanticValid
g_taskSemanticInfo
```

`TaskSemanticScope` 的职责是：

1. 开关关闭时不做任何事；
2. 保存进入前的 context；
3. 设置新的完整 context；
4. 析构时恢复上层 context，若原先没有 context 则清空。

`TaskSemanticEventScope` 的职责是：

1. 必须已经存在父 context；
2. 继承父 context，只覆盖 `event` 和 `semantic`；
3. 设置 `oneShot=true`；
4. 析构时恢复父 context。

这种嵌套模型让模板负责 phase/step/slice/rank，Sender/Reducer 只负责动作类型。

collective invocation identity 不进入该 TLS。语义 task 与 msprof physical TASK exact
合并后，从 DB operation metadata 获取 `(group_name, op_name)`，避免在 communicator、
`OpParam` 和持久 worker 中维护第二套实例计数与跨线程状态。

### 5.4 TaskData 构造时捕获

`TaskData` 新增：

```text
semanticStreamID
hasSemanticTraceInfo
semanticTraceInfo
```

DMA、Reduce、Notify、AIV 四种构造函数都会调用 `CaptureSemanticTraceInfo()`。
捕获只有在 `event` 和 `semantic` 均为非空字符串时成功。若 context 为 one-shot，
成功捕获后立即令 TLS context 无效。

这解决了“scope 已析构或已切换，`TaskProfiling::Run()` 才读取 context”的时序问题：
上报读取 task 自己的不可变快照，而不是再次读取当前 TLS。

需要注意：结构体中的字符串仍是 `const char *` 浅拷贝。当前调用点传入字符串字面量，
生命周期安全；公共 API 尚未防止未来调用者传入短生命周期字符串。

### 5.5 Capture stream 与语义 stream

带 `captureStreamID` 的 `Save()` 重载仍以 capture stream 构造原有 TaskData，随后把
真实 `streamID` 写入 `semanticStreamID`。因此：

- 原 profiler 路径继续使用 `TaskData.streamID`；
- `[HcclTaskSemantic]` 使用 `semanticStreamID`；
- 语义侧希望与 msprof DB 中的物理 stream 对齐。

这是一个有意的身份拆分，不能再假设两个字段始终相等。

## 6. 上报与日志契约

### 6.1 Task kind

`TaskTypeToName()` 当前支持：

```text
sdma, rdma, reduce_inline, reduce_tbe, notify_record, notify_wait,
host, graph_launch, batch_report, flip, unknown
```

### 6.2 本地 task 序号已废弃

schema v4 删除 `semantic_seq/profiler_seq`。审计确认：

- 两者都不参与 direct `task_id/exact` 或 FFts `parent+context/exact` 匹配；
- 两者都不参与 operation scope、Notify relation、stream order 或质量门禁；
- producer 与 consumer 位于不同 rank/stream，两个本地序号不能作为共享同步 token；
- `profiler_seq` 原有 probe 计数不能证明 FFts lowering 后的 physical subtask 顺序。

旧实现曾为每个活跃 device 分别懒分配两套 65,536 `atomic<u64>` stream 表，并在越界或
分配失败时退化为进程级 fallback。这些状态、分配和热路径原子操作现已全部删除。
`g_nextGraphInstanceId` 仍保留，因为它标识 FFts graph occurrence，不是本地 task 序号。

语义去重改用可解释的实际身份：

```text
direct = (node_id, device_id, stream_id, task_id)
FFts   = (node_id, device_id, pid, graph_instance_id, ffts_ctx_id)
```

因此 CSV 重排不会影响去重，也不需要一个只为去重而存在的额外计数器。

### 6.3 完整日志

当 task 携带有效快照时，使用 `HCCL_RUN_INFO` 输出一条
`[HcclTaskSemantic]`，字段为：

```text
schema_version
algorithm
event
phase
step
slice
user_rank
comm_rank
rank_size
peer_rank
semantic
device_id
stream_id
hccl_task_id
task_type
task_kind
ffts_ctx_id
graph_instance_id
submit_ts
notify_id
notify_stage
source
```

格式为 HCCL 现有的 `field[value]` 风格。当前 semantic schema version 为 4。
消费端接受已完成设备验证的 version 2/3/4，明确拒绝 version 1、
无版本记录以及旧空格 token 格式。version 2/3 中多出的
`execution_mode/notify_remote_rank/notify_ctx_id/semantic_seq/profiler_seq` 会被忽略。
`[HcclTaskGraphCorrelation]` 使用独立的 version 1 schema，不属于 semantic v1。

字段删除由 `test/out` 的 28,502 条 matched semantic 和 44,008 条物理 execution 验证：

- `execution_mode` 与 `ffts_ctx_id >= 0` 的判断 28,502/28,502 一致；
- 18,779 条 Notify semantic 的 `notify_remote_rank` 与通用 `peer_rank` 全部一致；
- 9,380 条有效 `notify_ctx_id` 与通用 `ffts_ctx_id` 全部一致；
- 44,008 条 profiler row 的 `kernel_type` 与 `event_name` 全部一致。

因此删除这些重复列不会减少当前匹配或语义信息。schema v4 的 merged CSV 为 42 列。
旧 `opType/opId/op_instance_id/retry_generation` 均不进入生产日志；`node_id` 不由
HCOMM 生成，由离线工具在输入边界补齐；`pid` 由 plog 行前缀解析。

### 6.4 Probe

没有有效语义快照时只使用 `HCCL_DEBUG` 输出 `[HcclTaskSemanticProbe]`。
Probe 不进入离线语义数据集，也不再维护本地序号。probe 现在输出 `device_id`、
`stream_id`、`hccl_task_id` 和 task kind；FFts report-without-context 还输出 task type、
context 和 graph instance。

AIV 的专用 `Save()` 当前只调用 probe，不输出完整语义记录。

### 6.5 submit 与 notify 元数据

`TaskProfiling::Run()` 在已有 profiler 数据准备完成后：

1. 将 `hcclReportData.ts` 复制到 `submitTs`；
2. 对 `TASK_NOTIFY_RECORD/WAIT` 复制 `notifyID/stage`；
3. 对 DMA、Reduce 和 Notify 统一提取 TaskPara 中的 `ctxId`，有效时输出
   `ffts_ctx_id` 和 `graph_instance_id`；
4. 使用 `deviceLogicId_`、`semanticStreamID` 和 HCCL task id 输出语义；
5. 再继续原有 msprof 数据上报。

`submit_ts` 是 Host-cycle 提交时刻，不是设备执行起止时间。它只能用于顺序校验或缩小候选窗口，
task duration 必须来自 msprof DB `TASK.startNs/endNs`。

本次数据同时表明 `notify_id` 还不能作为 record/wait 的跨执行精确配对键：
18,779 条 Notify semantic 按 `(node_id, device_id, notify_id)` 分组后，没有任何一组同时
包含 record 和 wait，依赖图的 3,016 条本地 Notify 边仍是 connection/time inferred。
这不影响 task-level 100% exact，但意味着同步依赖仍需独立 identity 设计。

## 7. 算法插桩

### 7.1 事件字典

| Event | Semantic | 含义 |
|---|---|---|
| `copy_start` | `hccl_local_copy` | 本地 D2D copy。 |
| `tx_ack_start` | `link_tx_ack` | 向对端发送 ACK。 |
| `rx_ack_start` | `link_rx_ack` | 等待/接收对端 ACK。 |
| `tx_payload_start` | `link_tx_payload` | 发送 payload。 |
| `rx_payload_copy_start` | `link_rx_payload_copy` | 接收 payload 或把远端数据复制到本地。 |
| `rx_payload_reduce_start` | `link_rx_payload_reduce` | 接收数据参与 reduce。 |
| `tx_data_signal_start` | `link_tx_data_signal` | 发送 inline-reduce 数据就绪信号。 |
| `rx_data_signal_start` | `link_rx_data_signal` | 等待/接收数据就绪信号。 |

### 7.2 通用 Sender

`Sender::run()` 的多个重载按链路能力标注：

- `TxWithReduce` 和普通 `TxAsync` -> `tx_payload_start`；
- inline-reduce 的 `TxDataSignal` -> `tx_data_signal_start`；
- `Post()` 根据 inline-reduce 条件标注 data signal 或 payload。

Sender 只覆盖 event/semantic，phase/step/slice/rank 必须由外层模板提供。
如果没有父 `TaskSemanticScope`，事件 scope 不激活。

### 7.3 通用 Reducer

`Reducer::run()` 的不同链路分支标注：

- `RxAsync`、远端到本地 D2D -> `rx_payload_copy_start`；
- `RxWithReduce`、`HcclReduceAsync` -> `rx_payload_reduce_start`；
- `RxDataSignal` 或 inline-reduce `Wait` -> `rx_data_signal_start`。

对一次 vector 调用内部的循环，当前用 `traceReduce`、`traceCopy`、`traceRxCopy` 等布尔量，
只给第一个 reduce/copy 提交建立 event scope。这样降低同一粗粒度语义重复覆盖多个 task 的概率，
但也意味着当前不是完整的逐 slice/逐 subtask 覆盖。

### 7.4 ReduceScatter concurrent-direct

phase 固定为 `reduce_scatter_direct`，algorithm 固定为 `single_ring_direct`。

覆盖点包括：

- 单 rank copy；
- 初始化阶段主流和从流首个 copy；
- 每一步主流 `TxAck(left)` 与 `RxAck(right)`；
- 向右发送的 payload；
- 从左接收的 data signal、payload copy 和 payload reduce；
- 从流首个 local copy；
- 非 SDMA 路径最终输出 copy。

模板显式传入 `commRank=rank`。主流中按 ring 公式分别计算 tx slice 与 rx slice，
peer rank 来自实际 `leftLink_`/`rightLink_` 的 remote rank。

当前初始化 copy 使用 `step=0`，虽然原注释把它描述为“第 -1 步”；最终 copy 使用
`step=rankSize-1`。这里的 step 按 7.6 的因果桶合同解释，不是对原算法注释的严格直译。

### 7.5 AllGather concurrent-direct

phase 固定为 `allgather_direct`，algorithm 固定为 `single_ring_direct`。

覆盖点包括：

- 单 rank copy；
- 初始化阶段首个 local copy；
- 每一步从流首个 local copy；
- 主流 `TxAck(left)` 与 `RxAck(right)`；
- 向右发送 payload；
- 从左接收 data signal 和 payload copy；
- 非 SDMA 路径最终首个 local copy。

与 RS 一样，模板维护 tx/rx 各自的 slice 和 peer context，再由叶子事件 scope 补全动作。

### 7.6 step 语义合同与门禁（SEM-006）

`step` 的正式定义是：

> `step` 是一个 phase 内、从 0 开始的逻辑因果桶（causal bucket / round anchor），
> 用于把准备、通信和收尾 task 关联到相应算法进度。它不是 physical task identity，
> 也不保证一个 step 只有一个 task。

对 `rank_size=N` 的当前 single-ring direct RS/AG：

```text
step 0       = round 0 的 init/prelude task + main communication round 0
step 1..N-2  = main communication round 1..N-2
step N-1     = 所有 main round 完成后的 final/epilogue task
```

因此同一个 step 可以包含不同 stream、event、slice 和 task kind；例如 RS 的 step 0
同时包含主/从流 init copy 和 main round-0 task。这是合法的并行/准备关系，不是
duplicate。step 只有放在以下作用域中才有意义：

```text
collective/graph occurrence + phase + step
```

relation 还必须结合 `slice`、producer/consumer rank、event/signal kind 及其精确
sequence。不得单独使用 step 建边或推断物理顺序；物理顺序仍来自 direct stream、
FFts context 和 Notify relation evidence。

`validate_trace.py` 对已明确合同的 `reduce_scatter_direct/allgather_direct` 执行硬门禁：

1. `rank_size` 必须为正整数；
2. `0 <= step < rank_size`；
3. ACK、payload、data-signal 等 main-round event 只能位于 `0..rank_size-2`；
4. `rank_size-1` 只作为 final/epilogue 桶，不接受 main-round link event；
5. 错误输出 CSV 行号、physical task 坐标及 phase/step/rank_size/slice/event；
6. 未定义合同的 phase 不套用 Ring 规则，不使用邻接或时间进行猜测。

当前 `test/out/function/merged.csv` 中 28,502 条 RS/AG semantic 全部通过该合同，
`step_contract_violations=0`。本任务没有增加 `stage_kind`、没有修改 HCOMM schema，
也没有改变 exact merge 或依赖边 identity。

如果后续真实数据证明同一因果桶内存在无法由 event/slice/rank/sequence 区分的
init/main 关系，再单独设计 `stage_kind=init|main|final`；在此之前不预设该问题。

### 7.7 算法选择测试补丁

当前有两处净差异明确写有 `[TEST PATCH]`：

1. `AlgConfigurator::GetDefaultAlgoLevel0Module()`：
   对满足全 HCCS 条件的 910B，把默认 `ALG_LEVEL0_NP_MESH` 改为
   `ALG_LEVEL0_NP_SINGLE_RING`。
2. `AllReduceOperator::SelectAlgfor910B()`：
   对多卡 ring topology 直接选择 `AllReduceRingFor91093Executor`，不再落入
   `AllReduceComm`。

两处组合用于让测试 workload 进入已插桩的 single-ring direct 路径，但会改变正常算法选择、
性能和覆盖面。它们不是纯 trace 改动，发布前必须移出生产默认路径。

## 8. 与离线诊断工具的契约

当前 HCCL 工具将 HCOMM 日志解析为 `SemanticRecord`，核心身份为：

```text
(node_id, device_id, stream_id, task_id)
```

其中：

- `device_id` 来自 HCOMM `deviceLogicId_`，不能由 rank 推断；
- `stream_id` 使用 `semanticStreamID`；
- `task_id` 解析自 `hccl_task_id`；
- `node_id` 由离线 CLI 在输入边界补齐。

普通非 composite task 可以按上述键和 task kind 与 msprof DB 精确匹配。
FFts graph 使用 `graph_instance_id` 将构图期语义与 graph launch 关联，再使用 launch
记录中的 `(parent_stream_id, parent_task_id)` 和语义记录中的 `ffts_ctx_id` 精确匹配
DB `TASK.contextId`。精确键为：

```text
(node_id, device_id, pid, graph_instance_id)
  -> (parent_stream_id, parent_task_id)
  + ffts_ctx_id
```

schema v4 不再输出或消费 `semantic_seq/profiler_seq`。FFts semantic 按
graph/context identity 去重，direct semantic 按 physical merge key 去重。
Notify record/wait 的物理资源可由相同 `notify_id` 识别，但 record/wait 通常位于不同
device；精确 relation 还必须包含 operation、graph/protocol sequence 和规范化 rank 角色。

### 8.1 FFts 是什么

这里的 FFts 是一种图式任务下发方式。普通 direct 模式下，Host 每调用一次 memcpy、
notify 或 reduce，运行时通常在设备 stream 上形成一个可以单独看到的 task：

```text
Host primitive -> physical stream/task
```

FFts 模式不会立刻逐个下发这些 primitive。`DispatcherGraph` 先通过
`GraphAddMemcpyTask`、`GraphAddRecordTask`、`GraphAddWaitTask`、
`GraphAddInlineReduceTask` 等接口，把多个 primitive 添加到一个 graph context 列表；
最后一次 `LaunchGraph` 把整张图作为一个父任务提交：

```text
Host primitive A --\
Host primitive B ----> FFts graph -> parent stream/task -> subtask 0..N
Host primitive C --/
```

因此 FFts 同时存在三层身份：

| 层次 | 字段 | 含义 |
|---|---|---|
| 构图调用 | logical/semantic stream、anchor task | Host 添加 context 时可见的流和当时最后一个 task；不是最终物理子任务身份。 |
| graph 实例 | `graph_instance_id` | 将一批构图调用和随后一次 launch 绑定起来的进程内唯一编号。 |
| 设备执行 | parent stream/task + `contextId` | msprof DB 中真正执行的 FFts 父任务和其内部 context。 |

同一个 graph 内的多条语义可能具有相同 `hccl_task_id`，不同 graph 的 `ctxId` 又会从头复用。
所以 `task_id` 或 `ctxId` 单独都不唯一，必须先锁定 graph parent，再使用 context id。

### 8.2 为什么 `ctxId` 对应 DB `TASK.contextId`

FFts graph 添加接口返回 `ctxIdx`。HCOMM 创建 `TaskParaDMA/Reduce/Notify` 时保存
`ctxIdx - 1`：

```text
GraphAdd*Task(..., &ctxIdx)
TaskPara*.ctxId = ctxIdx - 1
```

`ctxIdx` 是 graph constructor 为 context 分配的编号；减一后的值是零基 context id。
msprof 展开同一 FFts parent 时，将这个零基 context id 写入 DB `TASK.contextId`。
两者描述的是同一个 graph context 在“构图侧”和“执行侧”的编号，因此在同一个 parent
范围内满足：

```text
TaskPara.ctxId == msprof DB TASK.contextId
```

`test/out` 的新采集提供了端到端证据：14,405 条 FFts semantic 全部通过
parent correlation + `ffts_ctx_id` 精确映射到同 `contextId`，kind mismatch 为 0。

这个等式有两个边界：

1. `ctxId` 只在所属 graph 内唯一，不是进程级或 stream 级全局 id；
2. 语义侧的 stream 可能是构图时的逻辑/捕获 stream，而 FFts subtask 最终集中在另一个
   parent physical stream 上，不能要求两者 stream id 相等。

这正是必须同时输出 graph parent correlation 的原因。

### 8.3 schema v3～v4 的关联机制

生产端在首个有效 FFts context 上创建 thread-local pending graph，分配
`graph_instance_id`。同一构图批次的每条语义输出：

```text
ffts_ctx_id[ctxId]
graph_instance_id[N]
```

`LaunchGraph` 完成后，TaskProfiling 从 runtime 获取真实 parent stream/task，并输出：

```text
[HcclTaskGraphCorrelation]
schema_version[1]
graph_instance_id[N]
device_id[D]
anchor_task_id[A]
parent_stream_id[S]
parent_task_id[T]
```

离线端先按 `(node_id, device_id, pid, graph_instance_id)` 连接 correlation，再按
`(node_id, device_id, parent_stream_id, parent_task_id, ffts_ctx_id)` 查找 DB execution。
匹配还会验证 FFts lowering 后的物理 kind：

- `notify_record -> Write Value`
- `notify_wait -> Notify Wait`
- `sdma -> SDMA`
- `reduce_inline -> SDMA`

只有 parent、ctx 和兼容 kind 全部满足时才输出
`match_method=ffts_parent_ctx, match_confidence=exact`。

当前 pending graph 使用 thread-local 生命周期，符合 `DispatcherGraph` 同线程同步构图并
launch 的现有调用链。如果未来允许跨线程构图、嵌套未 launch graph 或同线程交错构建多个
graph，必须把 pending 状态下沉到 `DispatcherGraph` 实例或显式 graph handle，不能继续依赖
thread-local 单 pending slot。

### 8.4 版本与精确匹配规则

- semantic v1、无 `schema_version` 和旧空格 token 记录直接拒绝；
- semantic v2/v3 作为已验证数据的迁移输入，生产端统一输出 v4；
- `task_id + 1`、固定 ordinal 和本地序号 composite heuristic 已从代码及 CLI 删除；
- direct task 只允许 `task_id/exact`；
- FFts task 只允许 `ffts_parent_ctx/exact`；
- kind mismatch 输出 `correlation_kind_mismatch` 并使质量门禁失败。

对 `test/out` 从原始 plog/msprof 复算结果为：28,502/28,502 semantic exact，
其中 14,405/14,405 FFts semantic 使用 parent+ctx exact；335 条 graph correlation，
duplicate 和 invalid 均为 0。精简字段后复算结果保持不变。DB 主输入不再需要 Chrome
HostToDevice `flow_id`，schema v4 的 merged 合同为 42 列。原始
`op_name/group_name/opId` 不写入 merged CSV；`(group_name, op_name)` 只生成稳定的
`profiler_op_scope` 摘要。

### 8.5 msprof DB 主输入合同

环境固定输出每个 `PROF_*` 根目录下的 consolidated `msprof_*.db`，因此消费端直接读取
SQLite，不再经过 Chrome-trace JSON 展示层。当前支持 DB schema `1.2.0`，必需关系为：

```text
TASK.taskType -> STRING_IDS.id
TASK.globalTaskId -> COMMUNICATION_TASK_INFO.globalTaskId
COMMUNICATION_TASK_INFO.opId -> COMMUNICATION_OP.opId
TASK.globalTaskId -> COMPUTE_TASK_INFO.globalTaskId
```

其中：

- `TASK` 提供 device、physical stream/task、FFts context、connection 和 `startNs/endNs`；
- `COMMUNICATION_TASK_INFO` 提供 profiler notify、src/dst rank 和 operation join；
- `COMMUNICATION_OP + STRING_IDS` 提供 `op_name/group_name`；
- `COMPUTE_TASK_INFO + STRING_IDS` 将 `STARS_COMMON` 补充为真实 compute name。

consolidated `TASK` 中额外存在 FFts `AI_CORE` 父级展示行；它不携带可与当前 semantic
一一对应的内部 primitive 身份，因此 DB parser 与旧细粒度输入口径一致，不把该父行作为
目标 physical execution，实际 SDMA/Notify context 仍按独立 TASK 行保留。

DB 使用 SQLite URI `mode=ro` 打开。未知 schema、缺表/列、重复 device 和一对多
communication metadata 都是硬错误。时间在解析和运算阶段保持整数纳秒，到现有 CSV
边界才无损表示为十进制微秒，避免大绝对 JSON 时间戳经 `float/.15g` 产生舍入。

当前 8 卡 `test/out` 对 DB 路径的复算结果为 44,008 个目标 physical task，
28,502/28,502 semantic exact，其中 FFts 14,405/14,405 parent+ctx exact。
task-level identity 与旧输入完全一致；但旧 connection/time Notify heuristic 会因纳秒时间
消除 JSON 舍入并列而从 3,016 条变化为 5,094 条。这一差异进一步证明时间最近关系不是
稳定因果证据，依赖图迁移必须按 DEP-008 删除该默认推断，不能为保持旧边数而重新舍入时间。

### 8.6 单机依赖图合同（DEP-001）

依赖分析采用两层图，而不是让一个节点模型同时承担事实记录和性能解释：

| 图层 | 节点 | 用途 | 无损要求 |
|---|---|---|---|
| execution graph | 每个 msprof physical execution，包括 Notify record/wait | 保存设备真实执行、控制原语和全部证据 | DB 中每个目标 TASK 必须恰好出现一次 |
| resource graph | 实际消耗数据通路资源的 SDMA/RDMA/Reduce/Compute execution | 关键路径、瓶颈与资源竞争分析 | 每条派生边必须能反查 execution 节点、控制节点及收缩规则 |

execution graph 是规范事实层；resource graph 是它的确定性派生视图。Notify 不会从事实层
删除。只有在 producer/consumer 与控制节点关系均已唯一确认时，resource graph 才可把
`payload_before -> notify_record -> notify_wait -> payload_after` 收缩为一条同步边。收缩边
至少保留原始 control node ID、relation identity、evidence 和 ambiguity 状态；缺失、多候选
或冲突时不猜测收缩。控制节点始终保留在 execution artifact；resource artifact 对缺失端
生成稳定 boundary，对多候选输出 ambiguity 并禁止候选笛卡尔积。

#### 8.6.1 稳定身份

单机 physical execution identity 定义为：

```text
(node_id, device_id, physical_stream_id, task_id, subtask_id, connection_id)
```

其 `graph_id` 是上述规范元组的版本化稳定摘要。CSV 行号、开始/结束时间、
`globalTaskId`、本地 operation `opId` 和 operation connection 均不进入身份：

- 行号和时间是输出顺序/观测值，重排或提高时间精度不能改变节点；
- `globalTaskId`、operation `opId`、operation connection 都是单 DB 的本地引用，
  不得用于跨 device/rank 连接；
- 同一输入中重复 execution identity 是硬错误，不能用行号静默拆成两个节点。

operation scope 来源于 DB 的 `(group_name, op_name)`，输出为不暴露原始名称的
`profiler_op_scope` 稳定摘要。`group_name` 防止仅凭 `op_name` 中通信域 hash 后三位
发生短 ID 碰撞；`op_name` 按 opaque 值使用，不解析后缀作为私有格式合同。`opId` 仅在
同一 `(node_id, device_id)` 内验证
`opId <-> (group_name, op_name)` 是否一一映射。每个 physical execution 同时输出：

- `unique`：本地引用与 scope 一一对应，可作为后续 operation 分区证据；
- `missing`：该 TASK 没有 operation metadata，仍保留为 execution 节点；
- `ambiguous`：名称不完整、缺少本地引用或一对多/多对一，不得参与 exact 分区。

operation scope 状态与 semantic-profiler 的 `match_status/match_confidence` 正交：一个
semantic 可以 exact 匹配 physical task，但 operation scope 仍可能 missing/ambiguous。
同一次分析输入必须只包含同一个 profile run；跨多次采集汇总时，需要由输入 manifest
额外提供统一的 `profile_run_id` 作为外层边界，不能让每个节点独立生成。

#### 8.6.2 边、证据与歧义

规范边身份为：

```text
(graph_schema_version, edge_kind, src_graph_id, dst_graph_id, relation_identity)
```

证据强度从高到低为：

1. `observed`：同一硬件执行域内的直接顺序或唯一、共享同步 token；
2. `semantic`：生产端显式声明的 peer/phase/protocol 关系；
3. `inferred`：由受约束元数据唯一推导，但生产端未显式声明；
4. `heuristic`：时间最近、出现顺序 zip 等研究性猜测。

`heuristic` 永远不能标为 exact/observed，也不能默认进入因果图。多个候选必须输出
ambiguity（候选及原因），不能通过“最近时间”选一个。DEP-011 已将 edge ID 实现为上述
规范元组的稳定摘要；reason、evidence、时间、CSV 行号和构造顺序不进入 identity。同一
`(kind, src, dst)` 出现不同 relation ID 是硬冲突，稳定摘要碰撞也是硬错误。nodes/edges
按稳定 ID 排序，消费端不得依赖 CSV 行序表达 ordinal；Notify ordinal 保存在
`sequence_value`。

execution artifact 使用固定列合同，并额外输出 `*_summary.csv`：

- node/edge 总数及各 edge kind 数量；
- duplicate node/edge ID；
- missing source/destination 与 self-loop；
- root、leaf、isolated node；
- Kahn 拓扑处理后的 `cycle_residual_nodes/has_cycle`；
- Notify relation ambiguity 状态计数。

duplicate、missing endpoint 或 self-loop 会阻止 artifact 导出。cycle residual 与 isolated
先作为事实统计，不在 DEP-011 阶段推断删除；门禁策略属于 DEP-015。

#### 8.6.3 边权与控制收缩

execution graph 的执行节点保存 `task_start/task_stop/duration`，顺序/同步边本身不把
`duration` 重复解释为耗时。resource graph 的边权按以下口径生成：

- 普通顺序边不输出等待权重；
- `wait_span_ns = max(0, wait.stop - wait.start)`，来自 wait 所在设备的本地 DB 时间；
  当前 Notify 同步边的 `weight_ns` 使用该值；
- 同节点时，以 `record.stop` 将 wait span 截断分成
  `remote_block_ns` 与 `post_signal_ns`。两者是围绕 record 完成时刻的观测分解，
  不宣称等价于硬件内部 Notify 可见时刻；
- `handoff_gap_ns = max(0, downstream_resource.start - wait.stop)`，只在 wait 与
  下游资源任务同节点且下游端真实存在时输出；
- 跨节点且没有时钟校准 artifact 时，`timing_status=cross_node_uncalibrated`，
  `remote_block_ns/post_signal_ns` 留空，不比较不同节点的绝对时间。wait 本地 duration
  仍可报告，但不能与其他节点的 wall-clock 权重直接比较。

`wait_span_ns` 是控制等待的显式边权；关键路径实现不得再同时把已经收缩的 Notify wait
节点 duration 加入 resource 图，否则会重复计费。稳定 edge identity、资源收缩和边权合同
落地后，图 artifact 使用 `graph_schema_version=4`；未来更改 identity、收缩或权重语义必须
升级版本。

当前 DB replay 的 execution artifact 为 44,008 nodes、56,675 edges、2,059 isolated、
2,753 roots、2,753 leaves；duplicate node/edge、missing source/destination、self-loop 和
cycle residual 均为 0。resource artifact 为 11,432 个真实资源节点和 8 个 boundary、
25,479 条边：10,051 条顺序边和 15,428 条 Notify 同步边；
收缩 ambiguity 为 0，cycle residual 为 0。8 个 boundary 分别表示每个 device 最初一条
slave→main local Notify relation 没有可达的上游资源任务。32,576 个控制/辅助 execution
不作为 resource 节点，但其稳定 ID 通过 `control_graph_ids/source_execution_edge_ids`
保留在派生边中。

#### 8.6.4 resource 收缩算法与 artifact

资源任务采用显式白名单 `sdma/rdma/reduce_inline/reduce_tbe`。算法只在 execution graph
的两种顺序边上搜索首个资源 frontier：

1. 从同步边的 record 端沿顺序边反向搜索，遇到资源任务即停止；
2. 从 wait 端沿顺序边正向搜索，遇到资源任务即停止；
3. 两侧各恰好一个 frontier 时生成资源同步边，并合并所有经过的顺序边 ID 和控制节点 ID；
4. 某侧为零时生成按 `(source edge, relation, side)` 稳定命名的 boundary；
5. 任一侧多于一个资源 frontier 时写入 `*_resource_ambiguities.csv`，不生成候选组合边。

局部顺序链也按相同“遇到下一个资源任务即停止”规则收缩，派生为
`resource_stream_order_observed` 或 `resource_ffts_order_observed`。Notify 边分别映射为
`resource_notify_sync_exact/resource_local_notify_sync_exact/resource_notify_sync_observed`。
实际资源节点沿用 execution `graph_id`，因此两种视图可以直接
互相定位。

导出合同包含：

- `*_resource_nodes.csv`：真实资源节点与必要 boundary；
- `*_resource_edges.csv`：稳定边、原 execution edge/control node、Notify relation 和时间指标；
- `*_resource_ambiguities.csv`：多 frontier 候选和不收缩原因；
- `*_resource_summary.csv`：结构完整性、边类型、boundary、歧义与 timing status。

HTML/SVG 读取这些固定 artifact，不调用构边函数。`validate_dependency_graph.py` 同时读取
execution/resource summary 与 edge CSV，要求 duplicate、missing endpoint、self-loop、
cycle residual、Notify ambiguous/incomplete/conflict、resource contraction ambiguity、
`ffts_physical_stream_order`、默认 time-inferred 和旧 inferred Notify 边为 0。boundary
默认作为事实统计，可用 `--max-boundary-nodes` 收紧；`--golden-summary` 对指定统计做精确
比较，统计变化必须先在 spec 中解释再更新 golden。

### 8.7 单机 stream 顺序规则（DEP-003/DEP-004）

direct 与 FFts 使用不同的顺序证据，禁止再把所有 context 按 parent physical stream
混成一条链：

| 类型 | 进入条件 | 分组 identity | 排序证据 | 边类型/强度 |
|---|---|---|---|---|
| direct | `subtask_id < 0` | `(node, device, physical_stream)` | DB 精确 start/stop | `direct_stream_order_observed / observed` |
| FFts | exact matched、scope unique、parent/ctx 完整 | `(node, device, pid, op_scope, graph_instance, parent_stream, parent_task, semantic_stream)` | `contextId` 声明序 | `ffts_logical_stream_order / semantic` |

direct 时间排序使用 CSV 十进制微秒的 `Decimal` 值，不把大绝对时间先转成 `float`。绘图仍可
使用 float，但不能让浮点舍入改变构边。同一 start 的 execution 构成无序 bucket：

- bucket 内不建边；
- 相邻 start bucket 之间只对 `src.stop <= dst.start` 的 pair 建边；
- 因此重复时间处理与 CSV 行顺序、`graph_id` 哈希顺序无关；
- 该边表示 direct 子序列中的可证明先后，不宣称中间不存在未标注 execution。

FFts builder 不读取 start/stop 来决定先后。候选必须同时满足：

1. `match_status=matched` 且 `ffts_ctx_id/subtask_id >= 0`；
2. `ffts_ctx_id == subtask_id`；
3. `profiler_op_scope_status=unique`；
4. pid、graph instance、parent stream/task 和 semantic logical stream 全部有效；
5. 同一逻辑流组内 context id 唯一。

组内按 context id 连接相邻声明。该边表达“同一 logical stream 的 graph context 声明序”，
证据等级是 semantic，不声称两个 context 在设备上不重叠。重复 context 是硬错误；缺少
semantic、operation 或 parent evidence 的 profiler-only FFts context 保留为 execution node，
但不猜测 stream 顺序。

`test/out` DB 回放结果：

| 指标 | 结果 |
|---|---:|
| direct execution / physical stream group / edge | 27,544 / 32 / 27,512 |
| FFts exact context / logical stream group / edge | 14,405 / 670 / 13,735 |
| 新 stream-order edge 合计 | 41,247 |
| 旧 physical-stream edge | 43,976 |
| 旧边保留 / 删除 / 新增 | 36,556 / 7,420 / 4,691 |
| 旧 FFts 双向跨 logical-stream 伪边 | 4,690 |
| 新跨 logical-stream 边 | 0 |

任务清单中的 2,352 条是旧输入阶段的估计。当前 consolidated DB 逐端点复核得到 4,690 条：
`stream 45 -> 13` 和 `13 -> 45` 各 2,345 条；两类都不能代表 FFts 内部依赖，现已全部删除。

### 8.8 Notify relation identity（DEP-005）

Notify resource 与一次同步 relation 是两个不同对象：

```text
resource identity = (node_id, notify_id)
```

resource 只回答“使用哪块 Notify 存储”。它会跨 step、graph launch 和 collective operation
复用，不能直接生成 record→wait 边。FFts 同步 occurrence 的规范 identity 为：

```text
(
  graph_schema_version,
  node_id,
  operation_scope,
  rank_domain,
  producer_rank,
  consumer_rank,
  signal_kind,
  phase,
  step,
  slice,
  notify_id,
  sequence_kind,
  sequence_value
)
```

其中：

- `operation_scope` 隔离 collective invocation；
- `rank_domain` 当前固定为 `user`，禁止把 user rank 与 comm rank 混用；
- producer/consumer 是规范化方向，不使用“本地/远端”这种随端点变化的描述；
- `signal_kind` 当前为 `ack` 或 `data_signal`；
- phase/step/slice 隔离同一 operation 内的算法位置；
- `notify_id` 保留物理资源证据，但不是 occurrence sequence；
- `sequence_kind/value` 隔离同一资源在同一算法位置的多次复用。

sequence 支持四种合同：

| `sequence_kind` | 来源 | 适用范围 |
|---|---|---|
| `ffts_graph_instance` | HCOMM `graph_instance_id` | 当前单机 FFts graph occurrence |
| `db_notify_ordinal` | DB 完整 channel 的两侧本地序号 | 当前单机 direct |
| `protocol_sequence` | 后续生产端协议序号 | 无 consolidated DB 的 direct |
| `dependency_token` | 后续生产端显式共享 token | 无可靠自然序号的同步关系 |

当前 FFts graph instance 仍是进程内生成值，只能在相同 node、operation scope 和规范 rank
角色下作为单机候选 sequence，不能当成跨节点全局 ID。如果各 rank graph 序列不一致，
端点必须进入 single/ambiguous 状态，禁止按时间补配。

direct 使用独立、物理优先的 relation identity：

```text
channel = (
  graph_schema_version,
  node_id,
  operation_scope,
  rank_domain,
  producer_rank,
  consumer_rank,
  notify_id
)
relation = (channel, db_notify_ordinal)
```

`signal_kind/phase/step/slice` 对 direct 是可选 annotation，不进入稳定 ID；因此
profiler-only 端点不会因为语义覆盖率变化而改变 relation identity。

#### 8.8.1 端点角色归一化

| task kind / event | 角色 | producer | consumer | signal |
|---|---|---|---|---|
| `notify_record / tx_ack_start` | producer | `user_rank` | `peer_rank` | `ack` |
| `notify_wait / rx_ack_start` | consumer | `peer_rank` | `user_rank` | `ack` |
| `notify_record / tx_data_signal_start` | producer | `user_rank` | `peer_rank` | `data_signal` |
| `notify_record / tx_payload_start` | producer | `user_rank` | `peer_rank` | `data_signal` |
| `notify_wait / rx_data_signal_start` | consumer | `peer_rank` | `user_rank` | `data_signal` |

`tx_payload_start` 只有在 task kind 为 `notify_record` 时才归一化为 payload-ready
data signal；SDMA/RDMA payload execution 不属于 Notify endpoint。

#### 8.8.2 完整性与歧义

relation identity 不包含 `task_start/task_stop/submit_ts`、`connection_id`、本地 opId 或
operation connection。完整 identity 必须具有有效 op scope、rank 角色、signal、
phase/step/slice、Notify resource 和 sequence。按完整 identity 分组后：

- 恰好一个 producer record 和一个 consumer wait：`unique`；
- 只有一端：`single`，保留候选和缺失角色；
- 任一角色多于一个或身份字段冲突：`ambiguous`；
- 缺少 sequence/op/rank/algorithm position：`incomplete`。

只有 `unique` 才允许后续生成精确同步边；其他状态不得使用最近时间、出现顺序 zip 或
`connection_id` 自动消歧。

当前 `test/out` FFts 数据包含 9,380 个 Notify endpoint 和 16 个可复用 resource。完整
identity 产生 4,704 个 candidate：4,676 个 `producer+consumer`、14 个 producer-only、
14 个 consumer-only。若去掉 graph sequence，同一个 key 会聚合 11～12 个端点，直接证明
resource/op/step/slice 仍不足以避免跨 graph 串轮。

### 8.9 FFts Notify 精确配对（DEP-006）

消费端只对 `matched` FFts physical execution 提取 Notify endpoint。候选必须满足：

1. `subtask_id >= 0`，且 semantic `task_kind/event` 命中规范端点角色表；
2. `profiler_op_scope_status=unique`；
3. node、producer/consumer user rank、signal、phase/step/slice、notify resource 完整；
4. sequence 固定使用 `ffts_graph_instance`，值为有效 `graph_instance_id`。

随后按完整 `NotifyRelationIdentity.stable_id` 分组，规则是：

| 端点构成 | 状态/产物 | 是否构边 |
|---|---|---|
| 1 producer + 1 consumer | `ffts_notify_sync_observed`，保存 relation ID | 是 |
| 只有 1 个端点 | `single`，记录缺失角色 | 否 |
| producer 或 consumer 任一侧多于 1 | `ambiguous`，记录全部 endpoint graph ID | 否 |
| identity 缺字段 | `incomplete`，逐端点记录缺失字段 | 否 |

配对过程不读取 `task_start/task_stop`，不按 source row、task id 或 occurrence order 排序，
也不做 `zip`。因此增加时间精度、CSV 重排或 producer/consumer 执行先后变化不会改变
relation；证据不足只会增加 ambiguity，不会生成猜测边。

`visualize_dependency_graph.py` 现在同时输出：

```text
<prefix>_nodes.csv
<prefix>_edges.csv
<prefix>_notify_ambiguities.csv
```

ambiguity artifact 保留 relation 字段、状态、两侧计数、缺失角色/字段和全部 endpoint
`graph_id`，可直接定位未闭合或重复的控制关系。当前 DB golden replay 结果为：

| 指标 | 数量 |
|---|---:|
| FFts Notify endpoint | 9,380 |
| `ffts_notify_sync_observed` | 4,676 |
| `single` | 28 |
| `ambiguous` | 0 |
| `incomplete` | 0 |

28 个 single 中 producer-only 与 consumer-only 各 14 个；它们保持显式边界，不按相邻
graph、时间或 resource 猜测另一端。

#### 8.9.1 28 个 single 的来源

这里的 single 不是“只有一端的边”，而是只有一个可观测 endpoint 的 relation candidate，
所以不会生成 dependency edge。28 条全部集中在：

```text
rank 7
reduce_scatter_direct
graph_instance_id = 16
step = 0..6
signal = ack / data_signal
```

rank 7 的 plog 中 graph instance 序列为 `1..15, 17..42`，没有 16；graph correlation
也只有 41 条。相邻 rank 0 和 rank 6 的 graph 16 则各有完整 43 条 semantic context。
因此 rank 7 整个 FFts launch 缺少可关联 semantic/correlation，产生四组边界：

| 已观测端点 | 缺失端点 | 每个 step | 合计 |
|---|---|---:|---:|
| rank 0 → 7 ACK producer | rank 7 consumer | 1 | 7 |
| rank 0 的 data-signal consumer | rank 7 producer | 1 | 7 |
| rank 6 的 ACK consumer | rank 7 producer | 1 | 7 |
| rank 6 → 7 data-signal producer | rank 7 consumer | 1 | 7 |

即 `7 steps × 2 signals × 2 neighbor directions = 28`。这说明缺失单位是一整个 rank-7
graph launch，而不是 28 次独立配对算法失败。可能原因位于生产端 graph observation/
correlation 生命周期或日志缺失，需要新设备采集检查同一时刻的
`HcclTaskSemanticProbe`、`launch without pending semantic graph` 和 plog 丢弃信息；
现有离线证据不足以在这些可能性之间定责。

### 8.10 删除 connection/time 默认推断（DEP-008）

旧 builder 在同一 `(node, device, connection_id)` 内选择 wait 完成前“时间最近”的
Notify record。相同设备数据在 JSON 浮点时间下得到 3,016 条，在 DB 整数纳秒下得到
5,094 条，证明结果依赖展示精度而不是稳定身份。

默认 builder、edge vocabulary 和 HTML 图例现已完全删除 `notify_sync_inferred`：

- `connection_id` 仍作为 physical execution identity 的组成部分保留；
- 时间仍用于 direct physical stream 的可证明顺序；
- 两者不再组合成跨 stream Notify 因果边；
- 当前没有隐式 research fallback。未来若需要研究模式，必须提供独立显式入口，并把边
  标为 `heuristic`，不得写入默认 artifact。

DB replay 中 inferred 从 5,094 降为 0，总边数从 58,871 降为 53,777；节点 44,008、
FFts exact Notify 4,676、single 28 均不变。

### 8.11 direct Notify DB ordinal（DEP-007～DEP-010）

生产端不需要新增同步 token。consolidated msprof DB 已为所有 matched 与 profiler-only
Notify task 提供 `notifyId/srcRank/dstRank`，可恢复物理资源的完整状态序列。merge 将其
规范化到现有字段，不增加重复列：

| merged 字段 | matched | profiler-only Notify |
|---|---|---|
| `notify_id` | semantic 与 DB 相等后保留一个值 | DB `notifyId` |
| `user_rank` | semantic 与 DB `srcRank` 一致 | DB `srcRank` |
| `peer_rank` | semantic 与有效 DB `dstRank` 一致 | DB `dstRank` |
| `task_kind` | semantic/DB 一致 | DB task kind |

任何 matched Notify 的 ID、rank 或 kind 冲突都标记
`notify_metadata_mismatch/invalid`，不得进入 exact 合并统计。当前采集的 18,779 条
matched Notify 上述字段全部一致。

direct channel identity 为：

```text
(
  node_id,
  operation_scope,
  notify_id,
  producer_rank,
  consumer_rank
)
```

Record 使用 `producer=srcRank, consumer=dstRank`；Wait 归一化为
`producer=dstRank, consumer=srcRank`。`dstRank=-1` 是本地控制 Notify，不进入跨 rank
builder。同一 channel 的 Record 和 Wait 分别只在各自本地 physical stream 内排序：

```text
Record[ordinal] -> Wait[ordinal]
sequence_kind = db_notify_ordinal
```

该规则来自 Notify 的 `record: 0->1`、`wait-and-reset: 1->0` 状态机。跨设备
`task_start/task_stop` 不参与 identity：远端信号可见点可能早于源端 Record task 的 profiler
结束点，设备间时间也可能有偏差。当前语义完整的 4,650 对中有 2,048 对原始
`wait_stop < record_stop`，反向差值为 0.25～132.5 ns，因此“最近的后续 wait”不能作为
配对规则。

严格门禁要求 producer/consumer 各自只有一个 local stream、数量相等、顺序唯一且
operation scope 唯一。任何计数不等、多 stream 或顺序冲突都使整个 channel 进入
ambiguity，禁止 `zip(min)`。稳定 direct relation ID 只包含 channel 与 ordinal；语义
`signal_kind/phase/step/slice` 是 annotation，分为：

- `both`：两端都有语义且坐标一致；
- `partial`：只有一端有语义；
- `none`：两端均为 profiler-only；
- `conflict`：语义方向或坐标冲突，保留物理边并输出冲突 artifact。

当前 DB replay 得到 16 个跨 rank Notify resource、7 个 operation scope、112 个 direct
channel；每个 channel 均为 48 Record + 48 Wait，且两端各自只有一个 stream。最终生成
5,376 条 `direct_notify_sync_exact/exact`：both 4,695、partial 9、none 672、conflict 0。
原 `peer_signal_semantic` 时间排序边已删除；ACK/data-signal 语义只附着到 exact Notify
relation。

原有 2,142 条 `peer_payload_semantic` 在移除自身后，全部仍可通过
`direct_notify_sync_exact -> direct_stream_order_observed × 3` 的最短路径到达；没有一条
纯 stream 可达，也没有一条依赖 local Notify。它既不增加可达关系，occurrence 又只按语义
坐标和出现顺序配对，因此 `peer_payload_semantic/resource_payload_semantic` 已从默认因果图
正式删除并加入禁用 edge kind。`tx/rx_payload_*` 事件仍作为节点语义保留。

#### 8.11.1 主从流 local Notify DB ordinal（DEP-020）

msprof DB 用 `dstRank=-1` 表示 device 内本地控制 Notify。它不进入 8.11 的跨 rank
channel，而按以下 identity 独立分组：

```text
LocalNotifyChannel = (
  node_id,
  operation_scope,
  device_id,
  notify_id
)

LocalNotifyRelation = (
  LocalNotifyChannel,
  db_local_notify_ordinal
)
```

`Notify Record` 为 producer，`Notify Wait` 为 consumer。只有两侧各自位于唯一 physical
stream、数量相等、本地顺序唯一且 channel identity 完整时，才按各侧 stream 内 ordinal
建立 `local_notify_sync_exact/exact`。配对不比较两个 stream 的时间，也不依赖
`connection_id`；main→slave 与 slave→main 是两个独立 channel。任何数量不等、多 stream、
顺序冲突或身份缺失都整组写入 Notify ambiguity artifact，不生成部分关系。

local `notify_id` 可能是接近 `UINT64_MAX` 的十进制字符串。execution CSV reader 必须先用
整数文本解析，禁止 `int(float(value))`；后者会在 `2^53` 以上合并不同 resource identity。
回归测试固定两个仅相差 4 的宽整数 Notify ID 不发生碰撞。

当前 replay 共 112 个 local channel，每个 48 Record + 48 Wait；`stream 45→13` 与
`13→45` 各 56 个 channel，共生成 5,376 条 execution edge。resource graph 将其收缩为
5,376 条 `resource_local_notify_sync_exact`，沿用 `wait_span_ns` 权重合同。8 条最初的
slave→main relation 找不到上游资源 frontier，因此每个 device 生成一个稳定 upstream
boundary；这表示资源视图覆盖边界，不是 missing endpoint。

### 8.12 msprof operation identity 合同（ID-001～ID-005 撤销）

生产端不再生成 `op_instance_id/retry_generation`。collective invocation 在 semantic 与
physical TASK exact 合并后，由 consolidated msprof DB 提供：

```text
OperationIdentity = (group_name, op_name)
```

- `group_name`、`op_name` 来自 `COMMUNICATION_OP -> STRING_IDS`。
- `op_name` 是 msprof 的完整 opaque operation 名，例如
  `hcom_allReduce__612_0_1`；工具不依赖各后缀段的长期格式。
- 文档说明 `612` 这类第一段是通信域 hash 后三位，不能单独承担通信域唯一性；
  因此规范 identity 同时包含 `group_name`。
- 当前 `test/out` 的 `group_name` 为 `group_name_0`，不是完整 hash。工具只能验证
  DB 内本地 `opId <-> (group_name, op_name)` 一一映射，并要求同一次分析输入属于同一个
  profile run；不能声称该名称跨独立采集全局唯一。
- `opId` 和 operation connection 是单 DB 本地引用，只用于映射验证和诊断，不进入
  跨 device/rank identity。
- 名称缺失、一对多或多对一时，operation scope 标记 `missing/ambiguous`，不得按时间、
  行号或本地 ID 猜测。

物理匹配与 operation ownership 仍是两层合同：

```text
semantic <-> profiler:
(node_id, device_id, stream_id, task_id)
或 FFts parent + context

collective invocation:
(group_name, op_name)
```

当前实现把 tuple 编码为 `profiler_op_scope` 稳定摘要；同一 profile run 内跨 device/node
的相同 tuple 得到相同 scope。跨多次采集汇总时，由输入 manifest 增加统一
`profile_run_id` 外层边界。若同一采集内 graph replay 或 retry 复用了相同 `op_name`，
该 tuple 也无法区分 attempt，必须从 msprof 或设备侧获得独立 execution epoch；不得恢复
HCOMM 本地自增数冒充跨 rank 共享身份。

撤销后，HCOMM 不再承担 communicator 锁、map/set、FNV 哈希、`OpParam` 传播、
operation TLS、worker 快照或额外 plog 字段。semantic schema 保持 v4，merged 合同为
42 列。当前 `test/out` 回放为 28,502/28,502 exact、44,008 个 physical task、7 个
operation scope；当前 54 项 Python 单测覆盖跨 device/node 一致性、group 隔离、本地
映射歧义、direct Notify ordinal 和 Ring step 合同门禁。

## 9. 兼容性与非目标

当前实现没有引入旧版 marker 路径：

```text
aclprofMarkEx
HCCL_CUSTOM_PROF_TRACE
libmsprofiler
MarkAlgCustomTracePoint
PROFILER_TRACE_EX
```

它通过 HCCL plog 输出语义，通过 msprof DB 获取物理执行时间，两者在离线阶段合并。

当前改动也没有：

- 为所有 ring/mesh/hierarchical/NHR/RDMA/AIV 算法补齐 phase scope；
- 为跨节点或非 DB 输入生成 transport protocol occurrence token；
- 为 ACL graph 每次 device replay 生成执行 epoch；
- 为 graph replay/retry 提供独立 attempt identity；
- 提供跨节点时钟校准；
- 生成 wait interval、NHR dependency 或 critical path artifact。

## 10. 已知风险与审查发现

### P0：发布阻断

1. **测试补丁改变生产算法选择。** 两处 `[TEST PATCH]` 会强制 910B 进入 ring 路径，
   必须在发布前撤回或移入独立测试控制面。
2. **存在提前返回导致语义丢失的窗口。**
   `TaskData` 构造时可能已消费 one-shot context，但 `TaskProfiling::Run()` 在
   `GetAddtionInfoState()`、OP_BASE、非 capture 条件下会在语义上报前直接返回。
   结果是语义被消费却没有日志。

### P1：正确性与精确关联

1. **operation 名称有采集边界。** 当前 `group_name=group_name_0` 是导出编号，不是完整
   hash；同一次输入可按 `(group_name, op_name)` 分区，跨独立 profile run 必须增加统一
   run boundary。graph replay/retry 是否复用名字仍需专门采集验证。
2. **FFts correlation 已通过设备数据验收。** `test/out` 已证明
   `graph_instance_id/ffts_ctx_id` 和 graph parent correlation 能 100% exact；移除实例字段
   后仍需 HCOMM 构建和一轮短采集确认 schema v4 格式。
3. **vector 只标首任务。** `traceXxx` 布尔量牺牲了完整 slice/subtask 语义覆盖。
4. **AIV 只有 probe。** 专用 AIV Save 路径不会产生完整 `[HcclTaskSemantic]`。
5. **空 task 语义行为未定义。** 返回成功但不执行 report/probe 的 Save 重载是否对应
   physical execution 尚未完成逐项审计。
6. **phase 归属可能重叠。** RS/AG 对共享或竞争的物理 memcpy 可能给出不同 phase 声明，
   需要 correlation 后按物理 task 验证唯一归属。

### P2：可维护性与资源

1. **字符串是裸指针。** 当前字面量安全，但 API 没有表达或强制生命周期要求。
2. **当前没有 C++ 单元测试。** 开关缓存、one-shot、capture stream、graph instance
   并发和提前返回均缺少直接回归测试。
3. **`profiler_manager_impl.cc` 是无功能格式变更。** 应避免与功能提交混合，降低审查噪声。

## 11. 当前可验证的验收口径

P0 消费端止错、P1 correlation 和 schema v4 消费代码已经实现，但撤销实例字段后的生产端
尚未经过 HCOMM 构建和设备侧重新采集，因此当前实现仍应视为 single-ring direct 的实验性
生产端。设备验收至少需要满足：

1. HCOMM 自身构建通过；
2. `HCCL_STEP_TRACE=0` 时无语义日志且功能结果与 8.5.0 一致；
3. `HCCL_STEP_TRACE=1` 时 `semantic_total > 0`，且 Ring FFts 路径应满足
   `ffts_semantic_total > 0`、`graph_correlation_total > 0`；
4. `device_id/stream_id/hccl_task_id` 能与 DB 物理身份对齐；
5. duplicate semantic/profiler execution/graph correlation key 均为 0；
6. `ffts_semantic_missing_correlation == 0`、
   `ffts_ctx_kind_mismatches == 0`，并且
   `ffts_parent_ctx_matches > 0`；
7. 普通 task 和新采集 composite task 均必须 exact；工具不再提供 ordinal heuristic；
8. 测试算法强制逻辑不进入生产默认选择；
9. 同一 collective invocation 在各 rank/device 上得到相同 `(group_name, op_name)`，
   连续 AllReduce 的 `op_name` 不同，本地 `opId` 映射无歧义；
10. 多通信域、graph replay 与 retry 采集验证 operation 名称是否唯一；不唯一时必须
    输出 missing/ambiguous 或新增明确 execution epoch，不能按时间猜测；
11. 开销测试覆盖开关关闭与开启两种状态。
