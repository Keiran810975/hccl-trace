# Commit 5 审查报告：Duplicate 修复、device_id 对齐与语义去重

- **Commit**: `ceab0d2`（相对 `f01e756`，后者为 device id 对齐中间态）
- **变更规模**: 9 个文件，+102/-26
- **性质**: Bug 修复 + 数据质量改进 + 消费者端默认策略调整
- **关联**: 修复测试记录-0630中识别的 `duplicate_semantic_keys=84` / `match_rate=0%` 问题

---

## 1. 主要功能实现

本轮修改聚焦于两个核心问题：(1) 生产端 `device_id` 缺失导致 merge 匹配失败；(2) `TaskSemanticEventScope` 的一次 scope 覆盖多个 task 导致 duplicate merge keys。同时消费端工具引入了默认语义去重策略与显式 fallback 机制。

### 1.1 生产端：device_id 端到端注入（4 文件）

#### 1.1.1 `ReportTaskSemanticTrace` 签名变更

[task_semantic_trace.h:39](hcomm/src/common/debug/profiling/inc/task_semantic_trace.h#L39)

```cpp
// 旧签名
HcclResult ReportTaskSemanticTrace(u32 streamId, u32 taskId, TaskType taskType);

// 新签名
HcclResult ReportTaskSemanticTrace(u32 deviceId, u32 streamId, u32 taskId, TaskType taskType);
```

`TaskProfiling::Run()` 在调用时传入真实的 `deviceLogicId_`（[task_profiling.cc:225](hcomm/src/common/debug/profiling/task_profiling.cc#L225)）：

```cpp
CHK_RET(ReportTaskSemanticTrace(deviceLogicId_, taskData.streamID, taskData.taskID, taskData.taskType));
```

#### 1.1.2 plog 输出新增 `device_id` 字段

[task_semantic_trace.cc:119-134](hcomm/src/common/debug/profiling/task_semantic_trace.cc#L119-L134)

- **Probe 记录**（无 context）：新增 `device_id[%u]` 字段
- **完整记录**（有 context）：新增 `device_id[%u]` 字段（位于 `semantic` 与 `stream_id` 之间）

此前 probe 记录仅输出 `stream_id/task_id/task_type/task_kind`，merge 时因 `device_id=-1` 无法匹配 profiler 侧 `(node_id, device_id, stream_id, task_id)` 四元组。现在 `device_id` 由 `TaskProfiling` 从 `deviceLogicId_` 成员提供，与 msprof 的 `Device_id` 字段直接对齐。

### 1.2 生产端：oneShot 机制消除 duplicate semantic keys（2 文件）

#### 1.2.1 结构体新增 `oneShot` 字段

[task_semantic_trace.h:32](hcomm/src/common/debug/profiling/inc/task_semantic_trace.h#L32)

```cpp
struct TaskSemanticTraceInfo {
    // ... 13 个原有字段 ...
    bool oneShot{false};  // 新增
};
```

#### 1.2.2 `TaskSemanticEventScope` 自动设置 `oneShot = true`

[task_semantic_scope.cc:61](hcomm/src/algorithm/base/alg_template/component/task_semantic_scope.cc#L61)

```cpp
TaskSemanticEventScope::TaskSemanticEventScope(const char *event, const char *semantic)
{
    // ...
    nextInfo.oneShot = true;  // 新增
    SetTaskSemanticTraceInfo(nextInfo);
    // ...
}
```

#### 1.2.3 `ReportTaskSemanticTrace` 消费 `oneShot`

[task_semantic_trace.cc:135-137](hcomm/src/common/debug/profiling/task_semantic_trace.cc#L135-L137)

```cpp
if (g_taskSemanticInfo.oneShot) {
    g_taskSemanticValid = false;
}
```

在输出完整 `[HcclTaskSemantic]` 记录后，若当前 context 标记为 `oneShot`，立即将 `g_taskSemanticValid` 置为 false。下一个 task 提交时将走 "report without context" 分支，不会复用相同的 `(stream_id, task_id, event, phase)` merge key。

**设计原理**：

- `TaskSemanticScope`（外层 executor/模板 scope）：`oneShot = false`（默认），context 在 scope 生命周期内持续有效，覆盖 scope 内所有 task
- `TaskSemanticEventScope`（内层 leaf task scope）：`oneShot = true`，context 仅对一个 task 有效，输出后立即失效

此前 `TaskSemanticEventScope` 析构时恢复父 context，但在析构前如果有多个 task 提交（例如 sender 的 `TxAsync` + `Post`），它们会共享相同的 `(event, semantic)` → 产生相同的 merge key → 形成 duplicate。`oneShot` 确保每个 event scope 只匹配一个 task。

### 1.3 消费端：语义去重引擎（merge_timeline.py）

[merge_timeline.py:24-131](hccl/tools/diagnosis/merge_timeline.py#L24-L131)

本轮对 merge 引擎做了三方面重构：

#### 1.3.1 事件优先级评分与自动去重

```python
EVENT_PRIORITY = {
    "rx_payload_reduce_start": 90,
    "rx_payload_copy_start": 85,
    "tx_payload_start": 80,
    "copy_start": 75,
    "tx_data_signal_start": 70,
    "rx_data_signal_start": 70,
    "tx_ack_start": 60,
    "rx_ack_start": 60,
    "allreduce_start": 10,
}
```

`_dedupe_semantics()` 函数在 `merge_records()` 中**默认启用**（`dedupe_semantic_keys=True`），处理逻辑：

1. 按 `merge_key` 分组语义记录
2. 若一组有多条记录，统计 `duplicate_semantic_keys_input` 和 `duplicate_semantic_rows_input`
3. 按 `_semantic_specificity()` 评分选择"最佳"记录，评分规则：
   - `event` 在 `EVENT_PRIORITY` 中得分（payload/reduce 事件高于 coarse executor 事件）
   - `phase` 非 `allreduce_executor` → +100（子阶段比顶层更具体）
   - `semantic` 非 `allreduce_executor` → +30
   - 有 `slice` 值 → +5
   - 有 `peer_rank` 值 → +5
   - 同分时取**后出现**的记录（`-index` 作为 tiebreaker）
4. 保留得分最高的一条，其余丢弃；输出按 `(node_id, device_id, stream_id, task_id)` 排序

#### 1.3.2 显式 fallback 策略

旧版（commit 2）中，`device_id=-1` 时自动使用 `rank` 作为 fallback。新版将 fallback 拆分为两层显式机制：

**第一层（自动）**：`semantic.device_id >= 0` 且 `semantic.node_id` 为空时，用 `(device_id, stream_id, task_id)` 作为 fallback 键匹配 profiler（仅当匹配唯一时生效）。统计 `node_id_fallback_matches`。

**第二层（显式 opt-in）**：`--rank-as-device-fallback` flag。仅当 semantic 侧 `device_id < 0`（旧版数据），且 `semantic.node_id` 为空时，尝试用 `user_rank` / `comm_rank` 作为 candidate device_id 匹配 profiler。统计 `rank_device_fallback_matches`。

```python
# 核心约束：rank fallback 仅匹配唯一 profiler 行
def _rank_as_device_match(profiler_by_device_task_key, semantic):
    # 1. 收集 candidate device_ids（user_rank, comm_rank 去重）
    # 2. 对每个 candidate 做 _unique_device_task_match
    # 3. 仅在最终 unique_matches 数量 == 1 时返回
    return unique_matches if len(unique_matches) == 1 else []
```

#### 1.3.3 `--keep-duplicate-semantic-keys` 开关

提供 opt-out 选项，用于检查原始生产者端 duplicate 行为：

```bash
# 默认：自动去重
python -m tools.diagnosis.merge_timeline ...

# 保留原始 duplicate
python -m tools.diagnosis.merge_timeline --keep-duplicate-semantic-keys ...
```

### 1.4 消费端：parse_plog.py device_id 解析简化

[parse_plog.py:94](hccl/tools/diagnosis/parse_plog.py#L94)

```python
# 旧：5 层 fallback
device_id=parse_int(data.get("device_id", data.get("device", data.get("rank",
    data.get("user_rank", data.get("comm_rank"))))))

# 新：仅 2 层
device_id=parse_int(data.get("device_id", data.get("device")))
```

**动机**：生产端（HCOMM）现在始终输出 `device_id`，不应再静默 fallback 到 rank。旧版数据（无 `device_id`）如需匹配，应显式使用 `--rank-as-device-fallback`。这消除了 commit 2 中引入的"隐式 rank→device_id 映射在非单机场景下可能错误"的风险。

### 1.5 Fixture 与测试更新

**sample.plog**：2 条 fixture 记录均新增 `device_id[0]` 字段，反映新版生产端输出格式。

**test_diagnosis.py**：新增 2 个测试方法：

| 方法 | 验证内容 |
|------|---------|
| `test_rank_as_device_fallback_is_explicit` | 无 `device_id` 的旧版数据默认不匹配；`rank_as_device_fallback=True` 时匹配成功 |
| `test_duplicate_semantic_keys_are_deduped_by_default` | 同一 merge key 的 2 条记录（`allreduce_start` vs `copy_start`）默认去重为 1 条，保留更具体的 `copy_start` |

### 1.6 README 更新

[README.md](hccl/tools/diagnosis/README.md) 新增描述：
- `device_id` 为默认必需字段
- `--rank-as-device-fallback` 仅用于旧版单机数据
- 默认语义去重行为
- `--keep-duplicate-semantic-keys` 调试选项
- Timeline 可视化入口

---

## 2. 代码模块与架构

```
hcomm/                                          hccl/
├── src/common/debug/profiling/                 └── tools/diagnosis/
│   ├── inc/task_semantic_trace.h    [修改 +1]      ├── merge_timeline.py   [修改 +65]
│   ├── task_semantic_trace.cc       [修改 +13]     ├── parse_plog.py       [修改 +3]
│   ├── task_profiling.cc            [修改 +2]      ├── test_diagnosis.py   [修改 +28]
│   └── ...                                        ├── README.md           [修改 +9]
└── src/algorithm/base/alg_template/               └── fixtures/
    └── component/                                     └── sample.plog      [修改 +4]
        └── task_semantic_scope.cc   [修改 +1]
```

数据流（端到端改进）：

```text
[生产端]                              [消费端]
TaskProfiling::Run()                  merge_timeline.py
  → deviceLogicId_ ────────────────────→ device_id (直接对齐)
  → ReportTaskSemanticTrace(deviceId)

TaskSemanticEventScope
  → oneShot = true                    merge_timeline.py (default)
  → ReportTaskSemanticTrace             → _dedupe_semantics()
    → 输出后立即清除 context              → 按 EVENT_PRIORITY 保留最具体行
    → 每个 event scope 仅匹配 1 task     → duplicate_semantic_keys → 0
```

---

## 3. 在整体目标中的进度

对照迁移方案和测试记录-0630 判定标准：

| 标准 | 状态 | 备注 |
|------|------|------|
| `device_id` 端到端对齐 | ✅ **本轮完成** | 生产端输出 → 解析 → merge_key 匹配，全链路打通 |
| `duplicate_semantic_keys` → 0 | ✅ **本轮完成** | oneShot + 默认去重双重保障 |
| `match_rate_percent >= 95` | ⚠️ 工具就绪，待真实数据验证 | 旧 fixture 测试 100% 通过 |
| `duplicate_profiler_rows == 0` | ⚠️ 工具报告，待验证 | merge 统计中包含此指标 |
| 算法插桩全链路 | ❌ | 仅 single-ring executor 有插桩（commit 4），默认 PyTorch 路径仍走 fullmesh |

**进度评估**：本轮解决了测试记录-0630 中识别的两个数据质量问题（device_id 对齐、duplicate keys），使离线工具管道在 fixture 级别达到 100% 匹配。但核心瓶颈——算法插桩未在默认 executor 路径激活——仍需后续解决。

---

## 4. 可能的风险

### 4.1 高风险

1. **`oneShot` 机制可能过于激进**
   - 当前 `TaskSemanticEventScope` 始终设置 `oneShot = true`，这意味着即使将来有场景需要 event scope 覆盖多个 task（如同一 event 下的多条 TxAsync），也会被静默截断为仅第一条
   - `sender.cc` 和 `reducer.cc` 中每个 event scope 包裹的是**单个** task 提交（`TxAsync`、`RxAsync` 等），当前场景下 oneShot 语义正确
   - 但如果未来有人写了 `{ eventScope; task1; task2; }` 的模式，task2 将走 probe 分支，不易排查
   - **建议**：在 AGENTS.md 或 `TaskSemanticEventScope` 头文件中文档化 oneShot 行为

2. **`device_id` 强制依赖破坏旧版数据兼容**
   - 旧版 plog（无 `device_id`）的 `SemanticRecord.device_id` 为 -1，新 merge 引擎默认不做 rank fallback
   - 用户必须知道并显式传入 `--rank-as-device-fallback` 才能匹配旧版数据
   - 如果用户不知此 flag，merge 结果将是 100% `unmatched_semantic`，但管道不会报错
   - **建议**：当检测到大量 `semantic_missing_device_id` 时，merge 工具应输出 warning 提示用户使用 `--rank-as-device-fallback`
   - 管理员批注：不必兼容旧版。

### 4.2 中等风险

3. **语义去重的"最具体"启发式可能不符合所有场景**
   - `EVENT_PRIORITY` 和 `_semantic_specificity()` 的评分规则基于当前 single-ring AllReduce 的语义结构设计
   - 例如 `copy_start`（75）优先级低于 `tx_payload_start`（80），但如果 future executor 的 local copy 事件语义更丰富，此规则可能误淘汰
   - `allreduce_start` 得分最低（10），子阶段事件总是胜出——这在当前正确，但在某些 debug 场景可能需要查看顶层 executor 事件
   - **缓解**：`--keep-duplicate-semantic-keys` 提供了绕过机制

4. **`node_id_fallback_matches` 与 `rank_device_fallback_matches` 的区分**
   - 前者用于有 `device_id` 但无 `node_id` 的场景（新版单机数据）
   - 后者用于无 `device_id` 的旧版单机数据
   - 两种 fallback 都要求匹配唯一，但两者的适用边界清晰
   - 如果新版多机数据中某个 node 的 `device_id` 恰好与其他 node 的 profiler task 唯一匹配（虽然概率极低），会产生静默错误匹配

5. **`_dedupe_semantics` 同分 tiebreaker 取后者**
   - `max(items, key=lambda item: (_semantic_specificity(item[1]), -item[0]))` 中 `-index` 使同分时取后出现的记录
   - 这意味着 plog 中靠后的记录胜出，而非靠前的。这在大多数场景下合理（靠后的 event 通常更具体），但非确定性顺序时可能不一致

### 4.3 低风险

6. **`deviceLogicId_` 未在 `TaskProfiling::Run(const StepData&)` 中使用**
   - `StepData` 版本的 `Run` 仍返回 `HCCL_SUCCESS`（空实现），未接入 semantic trace
   - 与 commit 3 中的风险评估一致，当前无影响但需后续评估

7. **Fixture `device_id[0]` 硬编码**
   - 两条 fixture 记录的 `device_id` 均为 0（单 rank 场景），未覆盖多 device_id 的匹配场景
   - 新增的 `test_duplicate_semantic_keys_are_deduped_by_default` 测试仅覆盖 2 条 duplicate 记录

8. **`EVENT_PRIORITY` 缺少 `tx_payload_reduce_start`**
   - sender 中 RDMA Reduce 路径使用 `tx_payload_start`（已覆盖），但 `tx_payload_reduce_start` 未在优先级表中
   - 如果后续引入此事件名，其得分将落在 fallback 的 `40 if record.event else 0` 区间，可能被错误淘汰

---

## 5. 与测试记录-0630 的符合度检查

测试记录第 4 节"判定标准"：

| 标准 | 当前状态 |
|------|---------|
| 脚本退出码为 0 | ✅ fixture 测试通过 |
| `semantic_total > 0` | ⚠️ 仅在 fixture 和强制 ring 场景下满足 |
| `match_rate_percent >= 95` | ✅ fixture 测试 100%；⚠️ 真实数据待验证 |
| `duplicate_semantic_rows == 0` | ✅ oneShot 消除生产者端 duplicate；去重引擎消除残留 |
| `duplicate_profiler_rows == 0` | ⚠️ 依赖 profiler 数据质量，工具可报告但无法修复 |
| 开销测试 overhead 可接受 | ✅ commit 3/4 阶段已通过（0.50%） |

测试记录第 8.4 节"结论"中识别的**剩余工作**对照：

| 剩余工作 | 本轮状态 |
|---------|---------|
| duplicate keys（`duplicate_semantic_keys=84`） | ✅ 已解决（oneShot + 默认去重） |
| device_id 对齐 | ✅ 已解决（端到端注入） |
| 算法插桩未在默认路径激活 | ❌ 未解决（需基类 Orchestrate 插桩） |

---

## 6. 未来预期

### 6.1 立即

1. **算法插桩扩展到基类**：按测试记录方案 A，在 `CollAllReduceExecutor::Orchestrate()` 添加 `TaskSemanticScope`，使默认 fullmesh 路径也能产生完整语义记录
2. **真实数据端到端验证**：用 msprof 采集 8 卡 AllReduce plog + task_time.csv，运行 merge → validate pipeline，验证 `match_rate >= 95%`

### 6.2 短期

3. **merge 工具增强**：
   - 当 `semantic_missing_device_id > 0` 时自动输出 warning 建议使用 `--rank-as-device-fallback`
   - 考虑增加 `--min-specificity` 阈值参数，允许用户控制去重激进程度
   - 在 summary 中增加 `match_rate_percent` 字段以便快速评估

4. **补充 `EVENT_PRIORITY` 覆盖**：审查 sender/reducer 中所有实际使用的 event 名，补全优先级表

5. **`TaskProfiling::Run(const StepData&)` 评估**：确认 StepData 路径是否需要接入 `ReportTaskSemanticTrace`

### 6.3 中期

6. **扩展 executor 覆盖矩阵**：double ring、zero-copy、AIV 等 executor
7. **多机场景验证**：`node_id` fallback 的准确性在多 node 环境下测试
8. **`build_dependency_graph.py` 和 `diagnose.py`** 离线工具实现（迁移方案阶段 3）

### 6.4 代码质量改进建议

9. 在 `TaskSemanticEventScope` 头文件中文档化 `oneShot` 行为
10. 将去重统计字段（`duplicate_semantic_keys_input`、`duplicate_semantic_rows_input`、`deduped_semantic_rows`）加入 `merge_timeline.py` 的 help 文本
11. 考虑将 `EVENT_PRIORITY` 和 `_semantic_specificity` 抽取到 `schema.py` 便于跨模块复用

---

## 7. diff 统计

| 文件 | 变更量 | 关键改动 |
|------|--------|---------|
| `merge_timeline.py` | +65/-18 | 语义去重引擎 + 显式 fallback 策略 + `--keep-duplicate-semantic-keys` |
| `test_diagnosis.py` | +28/-0 | 2 个新测试：fallback 显式化 + 默认去重 |
| `task_semantic_trace.cc` | +13/-5 | `deviceId` 参数 + oneShot 消费 + plog 新字段 |
| `README.md` | +9/-3 | device_id、去重、visualize 说明 |
| `fixtures/sample.plog` | +4/-2 | 新增 `device_id[0]` 字段 |
| `parse_plog.py` | +3/-3 | device_id fallback 简化 |
| `task_profiling.cc` | +2/-1 | 传入 `deviceLogicId_` |
| `task_semantic_scope.cc` | +1/-0 | `nextInfo.oneShot = true` |
| `task_semantic_trace.h` | +3/-1 | `oneShot` 字段 + 签名变更 |