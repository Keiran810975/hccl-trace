# Commit 4 审查报告：算法插桩——single-ring AllReduce 步骤语义

- **hcomm Commit**: `7db54477`（`9e60ec27..7db54477`）
- **变更规模**: 7 个文件，+261/-49
- **性质**: 在上一轮基础设施之上，对 single-ring AllReduce 链路进行算法层插桩

---

## 1. 主要功能实现

本轮将前次 commit 的基础设施（`TaskSemanticScope`、`TaskSemanticEventScope`、`ReportTaskSemanticTrace`）实际应用到 single-ring AllReduce 的完整执行路径，使真实 task 提交时能携带正确的步骤语义 context。

插桩覆盖了迁移方案第 5.5 节规划的五个层级中的四个：

| 层级 | 插桩位置 | 状态 |
|---|---|---|
| Executor 入口 | `coll_all_reduce_ring_for_910_93_executor.cc` | ✅ |
| RS/AG 模板入口 | `reduce_scatter_ring_concurrent_direct.cc` / `all_gather_ring_concurrent_direct.cc` | ✅ |
| Step/Slice/Peer | 同上（step 内 ACK、sender/receiver、local copy） | ✅ |
| 具体 task 事件 | `sender.cc` / `reducer.cc` | ✅ |

### 1.1 Scope 层扩展（[task_semantic_scope.h/cc](../hcomm/src/algorithm/base/alg_template/component/task_semantic_scope.h)）

#### 1.1.1 `MakeTaskSemanticTraceInfo()` 工厂函数

```cpp
TaskSemanticTraceInfo MakeTaskSemanticTraceInfo(
    const char *phase, u32 step, u32 userRank, u32 rankSize,
    u32 slice, const char *event = nullptr, const char *semantic = nullptr,
    u32 peerRank = INVALID_VALUE_RANKID, const char *algorithm = "single_ring_direct",
    u32 commRank = INVALID_VALUE_RANKID);
```

关键设计：
- `event`/`semantic` 可选（默认 `nullptr`），允许调用者只设置 coarse 信息，leaf task 再通过 `TaskSemanticEventScope` 覆盖
- `commRank` 默认 `INVALID_VALUE_RANKID`，此时 fallback 为 `userRank`，避免混淆
- `algorithm` 默认 `"single_ring_direct"`
- 一次性构造 13 个字段，避免算法代码中逐个赋值

#### 1.1.2 `TaskSemanticEventScope` 轻量级 Scope

```cpp
class TaskSemanticEventScope {
public:
    TaskSemanticEventScope(const char *event, const char *semantic);
    ~TaskSemanticEventScope();
    // ...
};
```

- 仅覆盖 `event` 和 `semantic` 字段，**继承父 scope 的所有其他字段**（phase、step、slice、rank、peer 等）
- 构造时通过 `GetTaskSemanticTraceInfo` 读取父 context，修改 `event`/`semantic` 后 `Set`
- 析构时恢复父 context
- `active_` 标记：仅在启用且父 context 存在时才激活

这是本轮最重要的设计决策：**两层 scope 配合使用**——

```cpp
// 外层：设置完整的 phase/step/slice/rank context
TaskSemanticScope semanticScope(MakeTaskSemanticTraceInfo(
    "reduce_scatter_direct", step, userRank_, rankSize, txSlice,
    nullptr, nullptr, rightLink_->GetRemoteRank()));

// 内层：仅覆盖 event/semantic
TaskSemanticEventScope eventScope("tx_payload_start", "link_tx_payload");
CHK_RET(rightLink_->TxAsync(txMems, stream_));
// eventScope 析构 → 恢复外层 context（phase/step/slice 仍在）
// semanticScope 析构 → 清空
```

### 1.2 Sender 插桩（[sender.cc](../hcomm/src/algorithm/base/alg_template/component/sender.cc)）

覆盖发送端三种链路类型的所有 task 提交路径：

| 链路类型 | Task | Event | Semantic |
|---|---|---|---|
| RDMA Reduce / Standard RoCE | `TxWithReduce` | `tx_payload_start` | `link_tx_payload` |
| Inline Reduce | `TxDataSignal` | `tx_data_signal_start` | `link_tx_data_signal` |
| 普通发送 | `TxAsync` | `tx_payload_start` | `link_tx_payload` |
| Notify 后发送 | `Post` (+ `TxAsync`) | `tx_payload_start` / `tx_data_signal_start` | 同上 |

覆盖三个 `run()` 重载：单 buffer、多 buffer（with transport reduce）、多 buffer（with notify）。

### 1.3 Reducer 插桩（[reducer.cc](../hcomm/src/algorithm/base/alg_template/component/reducer.cc)）

覆盖接收端四种链路类型的所有 task 提交路径，变更量最大（+110/-49）：

| 链路类型 | Task | Event | Semantic |
|---|---|---|---|
| RDMA Reduce | `RxAsync` | `rx_payload_copy_start` | `link_rx_payload_copy` |
| RDMA Reduce 后 copy | `HcclD2DMemcpyAsync` | `rx_payload_copy_start` | `link_rx_payload_copy` |
| Standard RoCE | `RxWithReduce` | `rx_payload_reduce_start` | `link_rx_payload_reduce` |
| Inline Reduce | `RxDataSignal` | `rx_data_signal_start` | `link_rx_data_signal` |
| Inline Reduce 本体 | `HcclReduceAsync` | `rx_payload_reduce_start` | `link_rx_payload_reduce` |
| Inline Reduce 后 copy | `HcclD2DMemcpyAsync` | `rx_payload_copy_start` | `link_rx_payload_copy` |
| 普通接收 | `RxAsync` | `rx_payload_copy_start` | `link_rx_payload_copy` |
| 普通 Reduce | `HcclReduceAsync` | `rx_payload_reduce_start` | `link_rx_payload_reduce` |
| Wait notify | `link->Wait` | `rx_data_signal_start` | `link_rx_data_signal` |

覆盖三个 `run()` 重载：单 buffer（`ReduceRun`）、多 buffer RDMA/Inline（`ReduceRunSp`）、多 buffer SDMA。

**所有路径均使用 `TaskSemanticEventScope`**，仅覆盖 event/semantic，依赖外层模板传入的 phase/step/slice/rank context。

### 1.4 ReduceScatter 模板插桩（[reduce_scatter_ring_concurrent_direct.cc](../hcomm/src/algorithm/base/alg_template/temp_reduce_scatter/reduce_scatter_ring_concurrent_direct.cc)）

在模板层使用 `TaskSemanticScope`（全量 context）+ `TaskSemanticEventScope`（事件覆盖）两层配合：

| 位置 | Phase | Step | Slice | Event/Semantic |
|---|---|---|---|---|
| `OneRankMemcpy` | `reduce_scatter_direct` | 0 | sliceIdx | `copy_start` / `hccl_local_copy` |
| `RunInitStep` | `reduce_scatter_direct` | 0 | initSlice | `copy_start` / `hccl_local_copy` |
| `RunMainStream` TxAck | `reduce_scatter_direct` | step | rxSlice | `tx_ack_start` / `link_tx_ack` |
| `RunMainStream` RxAck | `reduce_scatter_direct` | step | txSlice | `rx_ack_start` / `link_rx_ack` |
| `RunMainStream` sender | `reduce_scatter_direct` | step | txSlice | (继承，sender 内事件覆盖) |
| `RunMainStream` reducer | `reduce_scatter_direct` | step | rxSlice | (继承，reducer 内事件覆盖) |
| `RunSubStream` copy | `reduce_scatter_direct` | step | copySlice | `copy_start` / `hccl_local_copy` |
| Last step copy | `reduce_scatter_direct` | rankSize-1 | rank | `copy_start` / `hccl_local_copy` |

同时修复了一个小问题：`RunMainStream` 和 `RunSubStream` 原来有 `(void) rank;`（未使用的参数），现在 rank 被用于计算 `txSlice`/`rxSlice`/`copySlice`。

模板内的 `ReducerRunSpInlineReduce` 和 `ReducerRunNoSpInlineReduce` helper 函数中也新增了 `TaskSemanticEventScope` 包裹 leaf task（如 `RxDataSignal`、`RxAsync`、`HcclReduceAsync`）。

### 1.5 AllGather 模板插桩（[all_gather_ring_concurrent_direct.cc](../hcomm/src/algorithm/base/alg_template/temp_all_gather/all_gather_ring_concurrent_direct.cc)）

结构与 RS 模板对称：

| 位置 | Phase | Step | Slice | Event/Semantic |
|---|---|---|---|---|
| `OneRankMemcpy` | `allgather_direct` | 0 | sliceIdx | `copy_start` / `hccl_local_copy` |
| `RunInitStep` | `allgather_direct` | 0 | initSliceIdx | `copy_start` / `hccl_local_copy` |
| `RunAllGather` local copy | `allgather_direct` | step | txSliceIdx | `copy_start` / `hccl_local_copy` |
| `RunAllGather` TxAck | `allgather_direct` | step | rxSliceIdx | `tx_ack_start` / `link_tx_ack` |
| `RunAllGather` RxAck | `allgather_direct` | step | txSliceIdx | `rx_ack_start` / `link_rx_ack` |
| `RunAllGather` TxAsync | `allgather_direct` | step | (txTraceInfo 继承) | `tx_payload_start` / `link_tx_payload` |
| `RunAllGather` RxAsync | `allgather_direct` | step | (rxTraceInfo 继承) | `rx_payload_copy_start` / `link_rx_payload_copy` |
| `RunAllGather` SDMA path | `allgather_direct` | step | (rxTraceInfo) | `rx_data_signal_start` / `link_rx_data_signal` |
| Last step copy | `allgather_direct` | rankSize-1 | rank | `copy_start` / `hccl_local_copy` |

AG 模板额外预构造了 `txTraceInfo` 和 `rxTraceInfo` 两个 `TaskSemanticTraceInfo` 对象（第 416-419 行），在 step 循环内复用，避免每条 task 都重新构造。

### 1.6 Executor 入口插桩（[coll_all_reduce_ring_for_910_93_executor.cc](../hcomm/src/algorithm/impl/coll_executor/coll_all_reduce/coll_all_reduce_ring_for_910_93_executor.cc)）

仅 4 行新增：

```cpp
HcclResult CollAllReduceRingFor91093Executor::KernelRun(const OpParam &param, ExecMem &execMem)
{
    TaskSemanticScope semanticScope(MakeTaskSemanticTraceInfo("allreduce_executor", 0, topoAttr_.userRank,
        topoAttr_.userRankSize, 0, "allreduce_start", "allreduce_executor", INVALID_VALUE_RANKID,
        "AllReduceRingFor91093Executor"));
    // ... 原有代码 ...
```

- 这是整个 AllReduce operation 的**最外层 scope**
- event=`allreduce_start`，semantic=`allreduce_executor`
- algorithm 标识为 `AllReduceRingFor91093Executor`（与迁移方案 5.6 节的"路径自描述"意图一致）
- 模板内各 phase（RS/AG）的 scope 会嵌套覆盖 phase 和 event 字段

---

## 2. 代码模块与架构

```
hcomm/src/
├── algorithm/base/alg_template/component/
│   ├── task_semantic_scope.h        [修改 +37]  ← 新增 MakeTaskSemanticTraceInfo、TaskSemanticEventScope
│   ├── task_semantic_scope.cc       [修改 +37]  ← 对应实现
│   ├── sender.cc                    [修改 +9]   ← 插桩：tx_payload、tx_data_signal
│   └── reducer.cc                   [修改 +110] ← 插桩：rx_payload_copy、rx_payload_reduce、rx_data_signal
├── algorithm/base/alg_template/
│   ├── temp_reduce_scatter/
│   │   └── reduce_scatter_ring_concurrent_direct.cc  [修改 +86] ← 模板级 scope：phase/step/slice/peer
│   └── temp_all_gather/
│       └── all_gather_ring_concurrent_direct.cc      [修改 +46] ← 模板级 scope：phase/step/slice/peer
└── algorithm/impl/coll_executor/coll_all_reduce/
    └── coll_all_reduce_ring_for_910_93_executor.cc   [修改 +4]  ← Executor scope
```

数据流（已闭环）：

```text
Executor scope "allreduce_executor"
  → RS template scope "reduce_scatter_direct", step=N, slice=M, peer=P
    → sender scope (继承 phase/step/slice/peer)
      → TaskSemanticEventScope "tx_payload_start" / "link_tx_payload"
        → link->TxAsync() → TaskProfiling::Run() → ReportTaskSemanticTrace()
          → plog: schema_version[1] ... phase[reduce_scatter_direct] step[N]
             slice[M] peer_rank[P] event[tx_payload_start] semantic[link_tx_payload]
             stream_id[X] task_id[Y] task_kind[sdma] source[host]
```

---

## 3. 在整体目标中的进度

对照迁移方案：

| 阶段 | 关键项 | 状态 |
|---|---|---|
| 阶段 0 | 锁定基线与样本 | ✅ |
| 阶段 1 | HCOMM schema + context + 开关 + task 上报 | ✅ |
| 阶段 1 | Host dispatcher 最小闭环 | ✅ |
| 阶段 1 | 序列化和 context UT | ❌ |
| 阶段 2 | RS/AG 模板插桩 | ✅ **本轮完成** |
| 阶段 2 | Sender/Reducer 组件插桩 | ✅ **本轮完成** |
| 阶段 2 | Executor 入口插桩 | ✅ **本轮完成** |
| 阶段 2 | 离线工具对接新版日志格式 | ✅ 前期完成 |
| 阶段 2 | 8 卡 AllReduce 端到端验证 | ❌ 待进行 |
| 阶段 2 | Double ring 扩展 | ❌ |
| 阶段 2 | AICPU 路径 | ❌（标注为暂缓） |
| 阶段 3 | 依赖图与诊断 | ❌ |

**进度评估**：阶段 2（单机 single-ring AllReduce）的插桩部分已基本完成。生产端（HCOMM）和消费端（HCCL tools）均已就绪，下一步需要在真实设备上运行 8 卡 AllReduce 并验证覆盖率。

---

## 4. 可能的风险

### 4.1 中等风险

1. **Scope 未覆盖所有可能的代码路径**
   - `reducer.cc` 约有 300 行代码，多个 `if/else` 分支。虽然本次在每个真实 task 提交处都添加了 scope，但某些条件分支可能仍有遗漏
   - 验证方式：遍历 `reducer.cc` 和 `sender.cc` 中所有 `link->Xxx()` 和 `HcclXxxAsync()` 调用，确保每个都被 scope 包裹

2. **`TaskSemanticEventScope` 仅在父 context 存在时激活**
   - 如果 `TaskSemanticEventScope` 构造时 `GetTaskSemanticTraceInfo` 返回 false（即上层模板忘记设置 scope），event scope 静默失效（`active_ = false`）
   - 此时 task 仍会提交，但 `ReportTaskSemanticTrace` 走 "report without context" 分支输出 probe 日志
   - **这是安全的设计**（不会崩溃），但可能导致 debug 时困惑

3. **`MakeTaskSemanticTraceInfo` 默认值 `algorithm = "single_ring_direct"`**
   - 该函数定义在 component 层，但被 executor、RS、AG 等不同调用方复用
   - 如果未来 double ring 路径也调用此函数但忘记显式传 algorithm，会导致 algorithm 字段错误标识为 single_ring_direct
   - AG 和 RS 模板调用时正确覆盖了此默认值，executor 也覆盖了

4. **RS 模板 `ReducerRunSpInlineReduce` 使用的 scope 粒度不一致**
   - 函数内 `RxDataSignal` 和 `HcclReduceAsync` 使用 `TaskSemanticEventScope`（仅事件覆盖）
   - 但 `HcclD2DMemcpyAsync`（copy path）使用 `TaskSemanticEventScope` 且未包裹在 `TaskSemanticScope` 中
   - 这意味着 local copy 的 context 直接继承自调用者的 scope，而非显式的 copy context
   - 这在大部分情况下是正确的（copy 是 reducer 的一部分），但在某些条件下可能与预期语义不完全一致

### 4.2 低风险

5. **冗余 scope 构造**
   - AG 模板中 `RunAllGather` 的 SDMA 路径，在 `for (auto& mem : rxMems)` 循环内每轮都构造 `TaskSemanticScope(rxTraceInfo)` + `TaskSemanticEventScope`，而 rxTraceInfo 在循环间不变
   - 开销极低（仅 struct copy + thread_local 读写），不影响功能

6. **`RunMainStream` 和 `RunSubStream` 参数 `rank` 原为 `(void) rank;` 抑制未使用警告，现已被使用**
   - 这表明 `rank` 参数之前没有被使用，本轮开始使用它是正确的
   - 但需要确认上游调用方传入的 `rank` 值确实是当前通信域的 local rank 而非 user rank

---

## 5. 与迁移方案的符合度检查

| 方案要求 | 实现状态 |
|---|---|
| Executor 入口 `op_id`/algorithm | ✅ algorithm 已设置，`op_id` 未设置（`TaskSemanticTraceInfo.opId` 默认为 0） |
| RS/AG 入口 phase | ✅ `reduce_scatter_direct` / `allgather_direct` |
| Step 级 tx/rx slice + peer | ✅ slice + peerRank 正确传入 |
| ACK 与 data signal | ✅ `tx_ack_start`/`rx_ack_start`/`tx_data_signal_start`/`rx_data_signal_start` |
| Payload/reduce/copy | ✅ `tx_payload_start`/`rx_payload_reduce_start`/`rx_payload_copy_start` |
| Local copy | ✅ `copy_start` / `hccl_local_copy` |
| 路径自描述 `algorithm_selected` | ✅ `AllReduceRingFor91093Executor` / `single_ring_direct` |
| 不引入 `aclprofMarkEx` / `PROFILER_TRACE_EX` | ✅ 无引入 |
| 不依赖 msprof addition-info 订阅 | ✅ 在 `GetAddtionInfoState` 之前上报 |
| 事件命名 lower snake case + `_start`/`_end` 配对 | ⚠️ 仅有 `_start` 事件，未添加对应的 `_end` 事件 |

### 关于缺少 `_end` 事件的说明

迁移方案 5.1 节要求 "`_start` 设置 context，`_end` 清理 context"，且 AGENTS.md 规定 "`_start`/`_end` when they represent an interval"。

本轮所有事件均为 `_start` 形式（`tx_payload_start`、`rx_payload_reduce_start` 等），**没有对应的 `_end` 事件**。当前设计是：

- `_start` scope 覆盖一个真实 task 的提交
- 该 task 的 start/stop timestamp 由 msprof `task_time.csv` 提供

这意味着工具的 interval 重建依赖 profiler 时间戳而非语义 `_end` 事件。这在方案 2.1 节"语义与时间解耦"的框架下是合理的，但：
- 如果一个 scope 覆盖了多个 task（未来的 multi-task scope），`_start`/`_end` 边界将不再适用
- 迁移方案 5.1 节明确要求 "检测一个 scope 意外匹配多个 task 的情况"，当前未实现

---

## 6. 未来预期

1. **立即**：
   - 在真实 910/93 设备上开启 `HCCL_STEP_TRACE=1`，运行 8 卡 single-ring AllReduce
   - 采集 plog + task_time.csv，执行 merge → validate pipeline
   - 验证匹配率 ≥ 95%，检查各 phase/step 的覆盖率

2. **短期**：
   - 补充 `op_id` 生成逻辑（当前为 0），或明确如果当前无 `op_id` 机制则以 pid+timestamp 作为 operation 标识
   - 考虑是否需要为 ACK 和 data signal 添加 `_end` 配对事件
   - 补充 scope-without-task 和 multi-task 检测（迁移方案 5.1 节要求）

3. **中期**：
   - 扩展至 double ring executor（`CollAllReduceFastDoubleRingFor91093Executor`、`CollAlignedAllReduceDoubleRingFor91093Executor`）
   - `build_dependency_graph.py` 和 `diagnose.py` 离线工具实现

4. **代码质量**：
   - `reducer.cc` 的 scope 包装导致大量 `{ ... }` 块，可读性有所下降。后续可考虑将常见的 event/semantic 对封装为 helper
   - `TaskSemanticEventScope` 与 `TaskSemanticScope` 的两层配合模式可在 AGENTS.md 或代码注释中文档化
