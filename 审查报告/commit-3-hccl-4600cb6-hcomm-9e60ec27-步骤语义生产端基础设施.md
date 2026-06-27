# Commit 3 审查报告：步骤语义生产端基础设施

- **hccl Commit**: `4600cb6`（`28946c2..4600cb6`，1 文件，+2/-1）
- **hcomm Commit**: `9e60ec27`（`2981ffa7..9e60ec27`，7 文件，+251/-2）
- **分支**: `dev-innerDia`（双仓同步）
- **性质**: 横跨 HCOMM（生产端）与 HCCL（消费端工具）的基础设施新功能

---

## 1. 主要功能实现

本次 commit 实现了迁移方案（[step-trace-causal-diagnosis-migration-plan.md](../hccl/docs/help/step-trace-causal-diagnosis-migration-plan.md)）第 5.1 节“任务语义基础设施”和第 5.3 节“Dispatcher 关联”中规划的 **Host Dispatcher 步骤语义生产端闭环**。核心思路是：

```text
算法层 TaskSemanticScope（RAII）
  → thread-local context（SetTaskSemanticTraceInfo）
  → Profiling 回调获得真实 stream_id/task_id/task_type
  → ReportTaskSemanticTrace() 输出 versioned [HcclTaskSemantic] plog
  → 离线工具解析消费
```

### 1.1 HCOMM 侧：语义基础设施（4 新文件，3 修改文件）

#### 1.1.1 `task_semantic_trace.h` — 公共接口定义

[task_semantic_trace.h](../hcomm/src/common/debug/profiling/inc/task_semantic_trace.h)

定义了 `TaskSemanticTraceInfo` 结构体，包含 13 个语义字段：

| 字段 | 类型 | 说明 |
|---|---|---|
| `opType` | `const char*` | 算子类型 |
| `algorithm` | `const char*` | 算法/模板标识 |
| `event` | `const char*` | 事件名 |
| `phase` | `const char*` | 阶段名 |
| `semantic` | `const char*` | 语义类别 |
| `source` | `const char*` | 来源（默认 `"host"`） |
| `opId` | `u64` | 算子实例 ID |
| `step` | `u32` | 步骤序号 |
| `slice` | `u32` | 分片 ID |
| `userRank` | `u32` | 用户 rank |
| `commRank` | `u32` | 通信域 rank |
| `rankSize` | `u32` | 通信域大小 |
| `peerRank` | `u32` | 对端 rank（默认 `INVALID_VALUE_RANKID`） |

对外 API：

| 函数 | 用途 |
|---|---|
| `IsTaskSemanticTraceEnabled()` | 读取环境开关 |
| `GetTaskSemanticTraceInfo()` | 获取当前 thread-local context |
| `SetTaskSemanticTraceInfo()` | 设置当前 thread-local context |
| `ClearTaskSemanticTraceInfo()` | 清除当前 thread-local context |
| `ReportTaskSemanticTrace()` | 在真实 task 回调点输出完整 `[HcclTaskSemantic]` 日志 |

#### 1.1.2 `task_semantic_trace.cc` — 核心实现

[task_semantic_trace.cc](../hcomm/src/common/debug/profiling/task_semantic_trace.cc)

关键实现细节：

**环境开关**（`IsTaskSemanticTraceEnabled()`）：
- 优先检查 `HCCL_STEP_TRACE=1`
- 兼容旧名 `HCCL_TASK_SEMANTIC_TRACE=1`
- 使用 `static const` 一次性初始化，热路径无重复 `getenv` 开销
- 与迁移方案 5.1 节的环境开关设计一致

**Thread-local context**：
- `thread_local bool g_taskSemanticValid` 标记 context 有效性
- `thread_local TaskSemanticTraceInfo g_taskSemanticInfo` 存储当前 context
- 所有 set/get/clear 均先检查开关，关闭时零副作用

**Probe 日志限流**：
- `SetTaskSemanticTraceInfo()`、`ClearTaskSemanticTraceInfo()` 和 `ReportTaskSemanticTrace()` 的无 context 分支均输出 `[HcclTaskSemanticProbe]` 诊断日志
- 使用 `static std::atomic<u32> logCount` 限流到前 32 条，避免日志爆炸

**TaskType 到语义名映射**（`TaskTypeToName()`）：
- 覆盖 10 种 `TaskType`：`sdma`、`rdma`、`reduce_inline`、`reduce_tbe`、`notify_record`、`notify_wait`、`host`、`graph_launch`、`batch_report`、`flip`
- `default` → `"unknown"`

**Report 输出格式**（`ReportTaskSemanticTrace()`）：
- 有 context 时输出 22 个字段：`schema_version[1] op_id[...] op_type[...] algorithm[...] event[...] phase[...] step[...] slice[...] rank[...] ranksize[...] user_rank[...] comm_rank[...] rank_size[...] peer_rank[...] semantic[...] stream_id[...] task_id[...] task_type[...] task_kind[...] source[...]`
- 使用 `field[value]` 格式（`[]` 而非 `=`），与旧版 cann-hccl 格式对齐
- 同时输出 `rank[%u] ranksize[%u]`（旧别名）和 `user_rank[%u] comm_rank[%u] rank_size[%u]`（新字段），兼容旧脚本和当前离线工具
- 无 context 时输出限流 probe 日志（`report without context`）

**schema_version = 1**，与离线工具的 `SCHEMA_VERSION` 一致。

#### 1.1.3 `task_semantic_scope.h` / `task_semantic_scope.cc` — RAII Scope

[task_semantic_scope.h](../hcomm/src/algorithm/base/alg_template/component/task_semantic_scope.h)
[task_semantic_scope.cc](../hcomm/src/algorithm/base/alg_template/component/task_semantic_scope.cc)

实现了迁移方案 5.1 节要求的 RAII scope：

- 构造函数：保存当前 context（`hadPrevious_` + `previousInfo_`），设置新 context
- 析构函数：如果之前有 context 则恢复，否则清除
- **支持嵌套**：内部 scope 退出时恢复外部 scope 的 context
- 不可拷贝/赋值（`= delete`）
- 关闭开关时构造/析构均为空操作（`enabled_` 标记提前缓存）

#### 1.1.4 `task_profiling.cc` — Host Dispatcher 关联点

[task_profiling.cc](../hcomm/src/common/debug/profiling/task_profiling.cc)

在 `TaskProfiling::Run(const TaskData &taskData, bool isCapture)` 的**第一行**插入了：

```cpp
CHK_RET(ReportTaskSemanticTrace(taskData.streamID, taskData.taskID, taskData.taskType));
```

关键设计决策：
- 调用位置在 `profilingManager.GetAddtionInfoState()` 检查**之前**，确保 semantic report 不依赖 msprof addition-info 订阅状态
- 与迁移方案 5.3 节的设计一致："语义上报必须发生在检查 msprof 是否订阅之前"
- 覆盖了 `TaskProfiling::Run` 处理的所有 task 类型：SDMA copy、reduce inline/TBE、notify record/wait、RDMA 等

#### 1.1.5 CMakeLists.txt 变更

- [profiling/CMakeLists.txt](../hcomm/src/common/debug/profiling/CMakeLists.txt)：`task_semantic_trace.cc` 加入 `hccl_alg` target
- [component/CMakeLists.txt](../hcomm/src/algorithm/base/alg_template/component/CMakeLists.txt)：`task_semantic_scope.cc` 加入 `hccl_alg` target
- 两者均编入 `hccl_alg`，仅 host 侧，无 device 依赖泄漏（与迁移方案 5.2 节一致）

### 1.2 HCCL 侧：工具侧适配

[parse_plog.py](../hccl/tools/diagnosis/parse_plog.py) 的 `device_id` fallback 链扩展：

```python
# 旧 chain（commit 1-2）
device_id=parse_int(data.get("device_id", data.get("device", data.get("rank"))))

# 新 chain（commit 3）
device_id=parse_int(data.get("device_id", data.get("device", data.get("rank",
    data.get("user_rank", data.get("comm_rank"))))))
```

动机：新版 HCOMM 日志包含 `user_rank` 和 `comm_rank` 字段，但旧版单机数据无 `device_id` 且 `rank` 字段可能与 profiler `Device_id` 对应。扩展 fallback 链使新版 HCOMM 日志可在单机场景正确匹配。

---

## 2. 代码模块与架构

```
hcomm/                                          hccl/
├── src/common/debug/profiling/                 └── tools/diagnosis/
│   ├── inc/task_semantic_trace.h    [新增]         └── parse_plog.py  [修改]
│   ├── task_semantic_trace.cc       [新增]
│   ├── task_profiling.cc            [修改]
│   └── CMakeLists.txt               [修改]
└── src/algorithm/base/alg_template/component/
    ├── task_semantic_scope.h        [新增]
    ├── task_semantic_scope.cc       [新增]
    └── CMakeLists.txt               [修改]
```

数据流：

```text
[算法层]                          [Profiling层]                    [离线层]
TaskSemanticScope("event/phase")   TaskProfiling::Run()             parse_plog.py
  → SetTaskSemanticTraceInfo()       → ReportTaskSemanticTrace()      → bracket parser
  → (真实 task 提交)                  → HCCL_RUN_INFO("[HcclTask      → merge_timeline.py
  → ~TaskSemanticScope()              Semantic]...")
```

---

## 3. 在整体目标中的进度

对照迁移方案各阶段：

| 阶段 | 关键项 | 状态 |
|---|---|---|
| 阶段 0 | 锁定基线与样本 | ✅ 前期完成 |
| 阶段 1 | HCOMM schema + context + 开关 + task 上报 | ✅ **本轮完成** |
| 阶段 1 | Host dispatcher 最小闭环 | ✅ **本轮完成** |
| 阶段 1 | 序列化和 context UT | ❌ 未包含 |
| 阶段 2 | 算法插桩（RS/AG/sender/reducer） | ❌ 未开始（scope 已就绪） |
| 阶段 2 | 离线工具对接新版日志格式 | ✅ parse_plog 已适配 |
| 阶段 2 | 8 卡 AllReduce 端到端验证 | ❌ 待进行 |

**进度评估**：阶段 1 的核心基础设施已落地——开关、thread-local context、RAII scope、host dispatcher 关联点、versioned 日志输出。下一步需要在具体算法文件中使用 `TaskSemanticScope` 进行插桩（阶段 2）。

---

## 4. 可能的风险

### 4.1 高风险

1. **仅覆盖 Host Dispatcher，AICPU 路径未接入**（[task_profiling.cc](../hcomm/src/common/debug/profiling/task_profiling.cc) 仅修改了 `TaskProfiling::Run(const TaskData&, bool)`）
   - AICPU dispatcher 的 `GetNextSqeBufferAddr`、`SignalWait`、`SignalRecord`、`CopyData`、`RdmaSend` 等路径**尚未**调用 `ReportTaskSemanticTrace`
   - 迁移方案 5.3.2 节明确要求覆盖 AICPU dispatcher，本轮未实现
   - **影响**：AICPU workflow 下的 task 将全部以 "report without context" 输出，匹配率将显著偏低
   - **管理员批注**： 可先不考虑 AICPU 方式，先考虑常用方式

2. **`TaskProfiling::Run(const StepData& stepData)` 未接入**
   - 文件中有两个 `Run` 重载，仅 `const TaskData&` 版本被修改
   - `StepData` 版本可能覆盖步骤级 profiling 回调，如果该路径也产生 task，将缺失 semantic 上报

3. **开销位于 task 调度热路径**（[task_profiling.cc 第 225 行](../hcomm/src/common/debug/profiling/task_profiling.cc) 的 `CHK_RET` 在函数入口第一行）
   - 关闭开关时：`IsTaskSemanticTraceEnabled()` 使用 `static const bool` 缓存，仅一次 `getenv` + 快速 `false` 返回 → **开销可忽略**
   - 开启开关但无 context 时：`ReportTaskSemanticTrace` 走 "report without context" 分支，执行 `HCCL_RUN_INFO` 宏 → **每次 task 提交额外一次日志 I/O**
   - 开启开关且有 context 时：额外构造 22 字段的 formatted string → **每次 task 提交额外日志 I/O**
   - **建议**：后续性能测试需对比 trace 关闭时的延迟/带宽基线

### 4.2 中等风险

4. **Thread-local context 无 RAII 强制保护**
   - `SetTaskSemanticTraceInfo`/`ClearTaskSemanticTraceInfo` 是公开 API，算法代码可直接调用
   - 如果算法代码手动调用 `Set` 但忘记 `Clear`（绕过 `TaskSemanticScope`），context 会泄漏到后续 task
   - `TaskSemanticScope` 的 `= delete` copy/move 无法阻止手动调用

5. **`TaskSemanticScope` 未在当前算法代码中使用**
   - Scope 已定义并编入 `hccl_alg`，但本次 commit 未在任何 executor 或 template 中实例化 `TaskSemanticScope`
   - 这意味着当前代码路径中 thread-local context 永远为 invalid → 所有 task 都会走 "report without context"
   - **实际上本次 commit 只完成了基础设施，尚未产生有效的语义数据**。需要下一轮算法插桩才能验证闭环

6. **`task_semantic_scope.cc` 中的 `GetTaskSemanticTraceInfo` 在未启用时行为**
   - 若 `IsTaskSemanticTraceEnabled()` 返回 false，`GetTaskSemanticTraceInfo` 返回 false 且不修改 `info` 参数
   - 此时 `hadPrevious_` 为 false，析构时走 `ClearTaskSemanticTraceInfo()` → 但 `Clear` 内部也检查 enabled 且 context 本就不存在 — 逻辑正确但多一层调用

### 4.3 低风险

7. **`rank` 与 `user_rank`/`comm_rank` 同时输出可能导致字段歧义**
   - Report 中同时输出 `rank[%u]`（= userRank）和 `user_rank[%u]`（= userRank）以及 `comm_rank[%u]`（= commRank）
   - 这是故意为之的兼容设计，但离线工具解析时 `parse_plog.py` 的 `BRACKET_VALUE_RE` 会以最后出现的匹配为准（dict 覆盖）
   - 由于 `user_rank` 在 `rank` 之后出现在日志中，`user_rank` 会覆盖 `rank` 的值 → 两个值相同，无实际影响

8. **`parse_plog.py` device_id fallback 链越来越长**
   - `data.get("device_id", data.get("device", data.get("rank", data.get("user_rank", data.get("comm_rank")))))` 
   - 深层嵌套的 `dict.get` 链可读性降低。若后续需要区分 user_rank 和 comm_rank 的优先级，建议显式处理

---

## 5. 与迁移方案的符合度检查

| 方案要求 | 实现状态 | 备注 |
|---|---|---|
| schema_version 标记 | ✅ | `TASK_SEMANTIC_SCHEMA_VERSION = 1` |
| 环境开关 `HCCL_STEP_TRACE` | ✅ | 兼容 `HCCL_TASK_SEMANTIC_TRACE` |
| thread-local context | ✅ | `thread_local TaskSemanticTraceInfo` |
| RAII scope 嵌套 | ✅ | `hadPrevious_` + `previousInfo_` 保存恢复 |
| task 回调点上报 | ✅ | `TaskProfiling::Run` 入口第一行 |
| 不依赖 addition-info 订阅 | ✅ | 在 `GetAddtionInfoState()` 之前调用 |
| 不引入 `aclprofMarkEx` | ✅ | 完全未涉及 |
| 不引入 `dlopen` | ✅ | 无动态加载 |
| `_start` set / `_end` clear | ✅ | Scope 构造/析构 |
| scope 未覆盖 task 检测 | ✅ | probe 日志 "report without context" |
| 禁用时热路径快速返回 | ✅ | `static const bool` 缓存 + 空函数 |

---

## 6. 未来预期

### 6.1 立即（下一轮 commit）

1. **算法插桩**：在以下文件中使用 `TaskSemanticScope` 设置 context：
   - `coll_all_reduce_ring_for_910_93_executor.cc`（executor 入口 → op_id/algorithm）
   - `reduce_scatter_ring_concurrent_direct.cc`（RS 入口/出口 → phase）
   - `all_gather_ring_concurrent_direct.cc`（AG 入口/出口 → phase）
   - `sender.cc` / `reducer.cc`（step/slice/peer → event/semantic）

2. **端到端验证**：用真实 8 卡 AllReduce 运行，采集完整 plog + task_time.csv，执行 merge → validate pipeline，确认匹配率 ≥ 95%

### 6.2 短期（阶段 1 收尾）

3. **AICPU dispatcher 适配**：在 `GetNextSqeBufferAddr` 或等价接口处添加 `ReportTaskSemanticTrace` 调用
4. **StepData 版本的 `Run` 评估**：确认是否需要接入
5. **UT**：context set/clear、嵌套恢复、开关解析、TaskType 映射覆盖
6. **性能测试**：trace 关闭时的延迟/带宽基线

### 6.3 中期（阶段 2）

7. 扩展 executor 覆盖矩阵（double ring、aligned double ring、zero-copy）
8. `build_dependency_graph.py` 和 `diagnose.py` 离线工具实现

### 6.4 代码质量改进建议

9. 添加 `HCCL_STEP_TRACE_DETAIL`（operation/phase/step/task）级别过滤
10. 为 `TaskSemanticScope` 添加 scope-without-task 和 multi-task 检测计数（迁移方案 5.1 节要求）
11. 考虑将 `parse_plog.py` 的 `device_id` fallback 逻辑重构为显式的优先级列表
