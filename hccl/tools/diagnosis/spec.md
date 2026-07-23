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
| 当前工作树 | 在 HEAD 之上还有 11 个已跟踪文件的未提交修改 |

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

- 14 个文件；
- 新增 4 个文件；
- 修改 10 个文件；
- 新增 875 行，删除 78 行。

当前 HEAD 相对 8.5.0 是 12 个文件、`+512/-51`；未提交层又做了
11 个文件的调整。两层存在同文件反复修改，所以不能把两组行数直接相加。

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
  -> HCCL Python 工具与 msprof JSON 物理任务合并
```

主要功能包括：

1. 新增 `HCCL_STEP_TRACE=1` 控制的步骤语义基础设施；
2. 新增支持嵌套恢复和一次性消费的 RAII scope；
3. 在 task 被创建时保存语义快照，避免延迟上报时读到已经变化的 TLS；
4. 输出物理 `device_id`、真实语义 stream、HCCL task id、提交时间和 notify 元数据；
5. 为每个 device/stream 维护 profiler 序号与 semantic 序号；
6. 覆盖 single-ring concurrent-direct AllReduce 的 ReduceScatter/AllGather 核心事件；
7. 为触发上述路径加入两处明确标记为 `[TEST PATCH]` 的算法选择改动。

最后一项会改变 910B 的正常算法选择，不应直接作为生产默认行为发布。

## 4. 逐文件 Diff 清单

| 文件 | 行数 | 改动性质 | 功能解释 |
|---|---:|---|---|
| `src/algorithm/base/alg_template/component/CMakeLists.txt` | `+2/-1` | 构建接入 | 将 `task_semantic_scope.cc` 编入 `hccl_alg`。 |
| `src/algorithm/base/alg_template/component/task_semantic_scope.h` | `+50/-0` | 新文件 | 声明语义信息工厂、完整 context scope 和事件覆盖 scope。 |
| `src/algorithm/base/alg_template/component/task_semantic_scope.cc` | `+73/-0` | 新文件 | 实现 TLS context 的保存、覆盖、恢复及 one-shot 事件。 |
| `src/algorithm/base/alg_template/component/sender.cc` | `+9/-0` | 发送叶子插桩 | 为 Tx payload、Tx data signal 提供事件语义。 |
| `src/algorithm/base/alg_template/component/reducer.cc` | `+138/-39` | 接收/归约叶子插桩 | 为 Rx payload copy/reduce、Rx data signal 提供事件语义，并限制 vector 路径只标注首个提交。 |
| `src/algorithm/base/alg_template/temp_reduce_scatter/reduce_scatter_ring_concurrent_direct.cc` | `+126/-23` | RS 模板插桩 | 注入 phase/step/slice/rank/peer、ACK、payload、signal 和 local copy 语义。 |
| `src/algorithm/base/alg_template/temp_all_gather/all_gather_ring_concurrent_direct.cc` | `+72/-9` | AG 模板插桩 | 注入 phase/step/slice/rank/peer、ACK、payload、signal 和 local copy 语义。 |
| `src/algorithm/impl/alg_configurator.cc` | `+3/-2` | 测试路径改写 | 在特定 910B 全 HCCS 条件下把默认 NP mesh 强制改为 NP single ring。 |
| `src/algorithm/impl/operator/all_reduce_operator.cc` | `+3/-0` | 测试路径改写 | 多卡 ring topology 时显式选择 `AllReduceRingFor91093Executor`。 |
| `src/common/debug/profiling/CMakeLists.txt` | `+2/-1` | 构建接入 | 将 `task_semantic_trace.cc` 编入 `hccl_alg`。 |
| `src/common/debug/profiling/inc/task_semantic_trace.h` | `+51/-0` | 新文件 | 定义语义结构、开关、TLS、捕获、probe 和上报 API。 |
| `src/common/debug/profiling/task_semantic_trace.cc` | `+218/-0` | 新文件 | 实现开关、序号、task kind 映射、one-shot 捕获和 plog 输出。 |
| `src/common/debug/profiling/inc/task_profiling_pub.h` | `+24/-1` | TaskData 扩展 | 保存语义 stream 和语义快照；构造 DMA/Reduce/Notify/AIV TaskData 时捕获 context。 |
| `src/common/debug/profiling/task_profiling.cc` | `+22/-0` | 上报链集成 | 注入 device id、submit timestamp、notify 元数据，并处理 capture stream 与物理 stream 的区别。 |
| `src/common/debug/profiling/profiler_manager_impl.cc` | `+4/-3` | 格式整理 | 仅调整空白、括号和长行换行，没有语义变化。 |

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
| `opType` | `nullptr` | 已预留，但当前工厂不赋值、日志不序列化。 |
| `algorithm` | `nullptr` | 当前为 `single_ring_direct`。 |
| `event` | `nullptr` | 叶子 task 的动作名；必须非空才可捕获。 |
| `phase` | `nullptr` | 当前为 `reduce_scatter_direct` 或 `allgather_direct`。 |
| `semantic` | `nullptr` | 对 event 的稳定语义分类；必须非空才可捕获。 |
| `source` | `"host"` | 表示语义由 Host 侧插桩产生。 |
| `opId` | `0` | 已预留，但当前没有生成 invocation id，也不写日志。 |
| `submitTs` | `0` | `hrtMsprofSysCycleTime()` 的 Host 提交周期时间。 |
| `notifyId` | `0` | Notify task 从 `TaskParaNotify.notifyID` 补齐。 |
| `notifyStage` | `-1` | Notify stage。 |
| `step` | `0` | 算法 step。 |
| `slice` | `0` | 算法分片编号。 |
| `userRank` | `0` | 用户通信域 rank。 |
| `commRank` | `0` | 算法内部通信 rank；工厂可显式传入。 |
| `rankSize` | `0` | 通信域大小。 |
| `peerRank` | `INVALID_VALUE_RANKID` | 当前动作的对端 rank。 |
| `oneShot` | `false` | 为 true 时，首个成功捕获的 TaskData 消费当前 context。 |

`MakeTaskSemanticTraceInfo()` 默认使用 `single_ring_direct`。如果调用方没有显式传
`commRank`，它回退到 `userRank`；当前多卡 RS/AG 路径显式传入模板的 `rank`，避免将
comm rank 与 user rank 混为一谈。

### 5.3 TLS 与 RAII scope

当前 context 由两个 thread-local 变量保存：

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
- 语义侧希望与 msprof JSON 中的物理 stream 对齐。

这是一个有意的身份拆分，不能再假设两个字段始终相等。

## 6. 上报与日志契约

### 6.1 Task kind

`TaskTypeToName()` 当前支持：

```text
sdma, rdma, reduce_inline, reduce_tbe, notify_record, notify_wait,
host, graph_launch, batch_report, flip, unknown
```

### 6.2 序号

代码为每个 `(device_id, stream_id)` 维护两套从 0 开始的原子序号：

- `profiler_seq`：每次进入语义 report/probe 路径都递增，包括没有语义 context 的 task；
- `semantic_seq`：仅在实际输出 `[HcclTaskSemantic]` 时递增。

正常范围限定为：

```text
0 <= device_id < 64
0 <= stream_id < 65536
```

每个首次出现的 device 会分别为 profiler 和 semantic 序号懒分配一个包含
65536 个 `atomic<u64>` 的数组。越界或分配失败时使用进程级 fallback 序号。

`semantic_seq` 可作为同 device/stream 内的语义记录身份和去重依据；
`profiler_seq` 旨在表达上报顺序，但当前不等价于 FFts 编译后 subtask id。

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
semantic_seq
profiler_seq
task_type
task_kind
ffts_ctx_id
graph_instance_id
submit_ts
notify_id
notify_stage
source
```

格式为 HCCL 现有的 `field[value]` 风格。字段精简后当前 semantic schema version 为 3。
消费端接受已经完成设备验证的 version 2 和当前 version 3，明确拒绝 version 1、无版本记录
以及旧空格 token 格式。version 2 中多出的 `execution_mode/notify_remote_rank/notify_ctx_id`
会被忽略。`[HcclTaskGraphCorrelation]` 使用独立的 version 1 schema，不属于 semantic v1。

字段删除由 `test/out` 的 28,502 条 matched semantic 和 44,008 条物理 execution 验证：

- `execution_mode` 与 `ffts_ctx_id >= 0` 的判断 28,502/28,502 一致；
- 18,779 条 Notify semantic 的 `notify_remote_rank` 与通用 `peer_rank` 全部一致；
- 9,380 条有效 `notify_ctx_id` 与通用 `ffts_ctx_id` 全部一致；
- 44,008 条 profiler row 的 `kernel_type` 与 `event_name` 全部一致。

因此删除这四列不会减少当前匹配或语义信息，merged CSV 从 47 列降为 43 列。

没有写入日志的已预留字段是 `opType` 和 `opId`。`node_id` 不由 HCOMM 生成，
由离线工具在输入边界补齐；`pid` 由 plog 行前缀解析。

### 6.4 Probe

没有有效语义快照时只使用 `HCCL_DEBUG` 输出 `[HcclTaskSemanticProbe]`。
Probe 会推进 `profiler_seq`，但不会进入离线语义数据集。

AIV 的专用 `Save()` 当前只调用 probe，不输出完整语义记录；传入 probe 的 `taskId`
当前也没有被写入 probe 文本。

### 6.5 submit 与 notify 元数据

`TaskProfiling::Run()` 在已有 profiler 数据准备完成后：

1. 将 `hcclReportData.ts` 复制到 `submitTs`；
2. 对 `TASK_NOTIFY_RECORD/WAIT` 复制 `notifyID/stage`；
3. 对 DMA、Reduce 和 Notify 统一提取 TaskPara 中的 `ctxId`，有效时输出
   `ffts_ctx_id` 和 `graph_instance_id`；
4. 使用 `deviceLogicId_`、`semanticStreamID` 和 HCCL task id 输出语义；
5. 再继续原有 msprof 数据上报。

`submit_ts` 是 Host-cycle 提交时刻，不是设备执行起止时间。它只能用于顺序校验或缩小候选窗口，
task duration 必须来自 msprof JSON。

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
`step=rankSize-1`。因此 step 是展示/配对用逻辑编号，不是对原算法注释的严格直译。

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

### 7.6 算法选择测试补丁

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

普通非 composite task 可以按上述键和 task kind 与 msprof JSON 精确匹配。
FFts graph 使用 `graph_instance_id` 将构图期语义与 graph launch 关联，再使用 launch
记录中的 `(parent_stream_id, parent_task_id)` 和语义记录中的 `ffts_ctx_id` 精确匹配
JSON `Subtask Id`。精确键为：

```text
(node_id, device_id, pid, graph_instance_id)
  -> (parent_stream_id, parent_task_id)
  + ffts_ctx_id
```

`profiler_seq` 只保留为提交顺序和旧数据调查字段，不再作为默认 composite 匹配键。

`semantic_seq` 用于语义记录去重；它不表示物理设备 subtask 顺序。
Notify record/wait 可以利用相同 `notify_id` 建立同 device 的观测同步边。

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
| 设备执行 | parent stream/task + `Subtask Id` | msprof JSON 中真正执行的 FFts 父任务和其内部 context。 |

同一个 graph 内的多条语义可能具有相同 `hccl_task_id`，不同 graph 的 `ctxId` 又会从头复用。
所以 `task_id` 或 `ctxId` 单独都不唯一，必须先锁定 graph parent，再使用 context id。

### 8.2 为什么 `ctxId` 对应 `Subtask Id`

FFts graph 添加接口返回 `ctxIdx`。HCOMM 创建 `TaskParaDMA/Reduce/Notify` 时保存
`ctxIdx - 1`：

```text
GraphAdd*Task(..., &ctxIdx)
TaskPara*.ctxId = ctxIdx - 1
```

`ctxIdx` 是 graph constructor 为 context 分配的编号；减一后的值是零基 context id。
msprof 展开同一 FFts parent 时，将这个零基 context id 输出为 JSON `Subtask Id`。
两者描述的是同一个 graph context 在“构图侧”和“执行侧”的编号，因此在同一个 parent
范围内满足：

```text
TaskPara.ctxId == msprof JSON Subtask Id
```

`test/out` 的新采集提供了端到端证据：14,405 条 FFts semantic 全部通过
parent correlation + `ffts_ctx_id` 精确映射到同 `Subtask Id`，kind mismatch 为 0。

这个等式有两个边界：

1. `ctxId` 只在所属 graph 内唯一，不是进程级或 stream 级全局 id；
2. 语义侧的 stream 可能是构图时的逻辑/捕获 stream，而 FFts subtask 最终集中在另一个
   parent physical stream 上，不能要求两者 stream id 相等。

这正是必须同时输出 graph parent correlation 的原因。

### 8.3 schema v3 的关联机制

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
`(node_id, device_id, parent_stream_id, parent_task_id, ffts_ctx_id)` 查找 JSON execution。
匹配还会验证 FFts lowering 后的物理 kind：

- `notify_record -> Write Value`
- `notify_wait -> Notify Wait`
- `sdma -> SDMA`
- `reduce_inline -> SDMA`

只有 parent、ctx 和兼容 kind 全部满足时才输出
`match_method=json_ffts_parent_ctx, match_confidence=exact`。

当前 pending graph 使用 thread-local 生命周期，符合 `DispatcherGraph` 同线程同步构图并
launch 的现有调用链。如果未来允许跨线程构图、嵌套未 launch graph 或同线程交错构建多个
graph，必须把 pending 状态下沉到 `DispatcherGraph` 实例或显式 graph handle，不能继续依赖
thread-local 单 pending slot。

### 8.4 版本与精确匹配规则

- semantic v1、无 `schema_version` 和旧空格 token 记录直接拒绝；
- semantic v2 仅作为已验证数据的迁移输入，新增生产端统一输出 v3；
- `task_id + 1`、固定 ordinal 和 `profiler_seq` composite heuristic 已从代码及 CLI 删除；
- direct task 只允许 `json_task_id/exact`；
- FFts task 只允许 `json_ffts_parent_ctx/exact`；
- kind mismatch 输出 `correlation_kind_mismatch` 并使质量门禁失败。

对 `test/out` 从原始 plog/msprof 复算结果为：28,502/28,502 semantic exact，
其中 14,405/14,405 FFts semantic 使用 parent+ctx exact；335 条 graph correlation，
duplicate 和 invalid 均为 0。精简字段后复算结果保持不变，merged 列数由 47 降至 43。

## 9. 兼容性与非目标

当前实现没有引入旧版 marker 路径：

```text
aclprofMarkEx
HCCL_CUSTOM_PROF_TRACE
libmsprofiler
MarkAlgCustomTracePoint
PROFILER_TRACE_EX
```

它通过 HCCL plog 输出语义，通过 msprof JSON 获取物理执行时间，两者在离线阶段合并。

当前改动也没有：

- 为所有 ring/mesh/hierarchical/NHR/RDMA/AIV 算法补齐 phase scope；
- 生成跨节点统一的 collective invocation id；
- 提供跨节点时钟校准；
- 生成 wait interval、NHR dependency 或 critical path artifact。

## 10. 已知风险与审查发现

### P0：发布阻断

1. **测试补丁改变生产算法选择。** 两处 `[TEST PATCH]` 会强制 910B 进入 ring 路径，
   必须在发布前撤回或移入独立测试控制面。
2. **存在提前返回导致语义丢失的窗口。**
   `TaskData` 构造时可能已消费 one-shot context，但 `TaskProfiling::Run()` 在
   `GetAddtionInfoState()`、OP_BASE、非 capture 条件下会在语义上报前直接返回。
   结果是语义被消费却没有日志，同时 `profiler_seq` 也不会推进。

### P1：正确性与精确关联

1. **缺少 op instance。** `opId/opType` 虽存在于结构体，但当前不赋值、不序列化，
   多轮 AllReduce 的语义配对可能串轮。
2. **FFts correlation 已通过 v2 设备数据验收，v3 仍需构建确认。** `test/out` 已证明
   `graph_instance_id/ffts_ctx_id` 和 graph parent correlation 能 100% exact；
   v3 只删除冗余日志字段，但仍需 HCOMM 构建和一轮短采集确认格式。
3. **vector 只标首任务。** `traceXxx` 布尔量牺牲了完整 slice/subtask 语义覆盖。
4. **AIV 只有 probe。** 专用 AIV Save 路径不会产生完整 `[HcclTaskSemantic]`。
5. **空 task 未计序。** 返回成功但不执行 report/probe 的 Save 重载不会推进
   `profiler_seq`，序号不一定覆盖所有实际 graph 节点。
6. **phase 归属可能重叠。** RS/AG 对共享或竞争的物理 memcpy 可能给出不同 phase 声明，
   需要 correlation 后按物理 task 验证唯一归属。

### P2：可维护性与资源

1. **字符串是裸指针。** 当前字面量安全，但 API 没有表达或强制生命周期要求。
2. **序号表内存固定。** 每个活跃 device、每套序号分配 65536 个原子计数器，
   且按进程生命周期保留；应以实测 stream 范围评估内存。
3. **fallback 序号改变作用域。** device/stream 越界或分配失败后退化为进程级全局序号，
   不再满足严格的 per-device/per-stream 语义。
4. **当前没有 C++ 单元测试。** 开关缓存、嵌套恢复、one-shot、capture stream、
   并发序号和提前返回均缺少直接回归测试。
5. **`profiler_manager_impl.cc` 是无功能格式变更。** 应避免与功能提交混合，降低审查噪声。

## 11. 当前可验证的验收口径

P0 消费端止错和 P1 correlation 代码已经实现，但新 schema 尚未经过 HCOMM 构建和设备侧
重新采集，因此当前实现仍应视为 single-ring direct 的实验性生产端。设备验收至少需要满足：

1. HCOMM 自身构建通过；
2. `HCCL_STEP_TRACE=0` 时无语义日志且功能结果与 8.5.0 一致；
3. `HCCL_STEP_TRACE=1` 时 `semantic_total > 0`，且 Ring FFts 路径应满足
   `ffts_semantic_total > 0`、`graph_correlation_total > 0`；
4. `device_id/stream_id/hccl_task_id` 能与 JSON 物理身份对齐；
5. duplicate semantic/profiler execution/graph correlation key 均为 0；
6. `ffts_semantic_missing_correlation == 0`、
   `json_ffts_ctx_kind_mismatches == 0`，并且
   `json_ffts_parent_ctx_matches > 0`；
7. 普通 task 和新采集 composite task 均必须 exact；工具不再提供 ordinal heuristic；
8. 测试算法强制逻辑不进入生产默认选择；
9. 开销测试覆盖开关关闭与开启两种状态。
