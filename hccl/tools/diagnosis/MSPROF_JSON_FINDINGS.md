# HCCL 细粒度语义、聚合与依赖图设计审查

## 总结

当前方案已经能完整读取 msprof JSON 的物理执行单元，但生产端还没有为 FFts graph
subtask 提供共同 correlation id。因此普通任务可以精确关联，AI_CORE 内部只能做明确
标注的启发式关联。依赖图已改成以物理执行为节点，并区分观测边、语义边和推断边。

`task_time.csv` 路径及其 CLI、fallback 和测试已删除，消费链现在是 JSON-only。

## 1. 精确关联与 FFts 启发式关联

### 精确关联

普通非 composite task 同时满足：

```text
(node_id, device_id, physical_stream_id, task_id) 唯一一致
semantic task_kind 与 JSON hardware event 兼容
同一 JSON execution 没有被其他 semantic 认领
```

输出为 `match_method=json_task_id, match_confidence=exact`。这里“精确”表示身份键唯一，
不表示语义内容本身一定正确。

### 启发式关联

FFts 把一个父 AI_CORE task 展开为多个带 `Subtask Id` 的 SDMA、Write Value 和 Notify
Wait。plog 只有 HCOMM 上报序 `profiler_seq`，没有编译后的 subtask id。当前 direct-ring
样本只能：

1. 用 `semantic.task_id + 1` 找到父 composite task；
2. 识别本轮图开头 3 个无语义 task；
3. 按图内相对序选择 JSON subtask。

输出为 `json_composite_profiler_seq / heuristic`。固定偏移和相对序只对当前已验证图结构
成立；算法、固件、编译器或 task 展开改变后必须重新验证。

## 2. 为什么删除 CSV 兼容

`task_time.csv` 将每轮 ReduceScatter 的 49 个执行单元压成一个 `AI_CORE` 父行，无法
回答哪个 Notify Wait 阻塞、两个 SDMA 是否重叠、从流何时被唤醒等问题。保留它会让
schema、匹配 fallback、测试和 CLI 同时维护两套语义，却不能服务细粒度诊断。

本次已删除：

- `parse_msprof.py` 与 task_time fixture；
- `--task-time*`、rank-as-device fallback、duplicate-dedupe 调试参数；
- CSV sequence fallback 及相应旧测试。

中间结果仍使用 CSV，是因为它只是本项目内部的扁平 artifact，不是 msprof
`task_time.csv` 数据源。

## 3. 当前匹配流程与时间戳结论

当前优先级：

```text
FFts composite structural match
  → ordinary exact task-id match
  → unmatched_semantic
```

JSON 中没有被 semantic 认领的执行保留为 `profiler_only`，以保证物理时间线和依赖图
不丢任务。

上一提交增加的 `device_ts` 来自 `hrtMsprofSysCycleTime()`，它记录 TaskProfiling 上报/
提交时刻，并不是设备开始执行时间。本次已改名为 `submit_ts`。它的合理用途是：

- 缩小候选时间窗口；
- 检查匹配结果是否出现明显逆序或超大提交延迟；
- 在同一 host 时钟域内辅助区分 invocation。

它不能作为主匹配键：重叠 SDMA 可以有相同/相近时间，host submit 与 device execute
之间存在排队，跨节点时钟也未对齐。精确匹配仍需要 graph/subtask correlation id。

## 4. JSON 解析开销

真实 8 卡数据约 100 MB：

- 单卡约 11 MB JSON 解析并写规范化任务约 0.22 秒；
- 原实现整套 merge 约 31.47 秒；
- 修复 node fallback 的近二次扫描后约 2.13 秒；
- 44,008 节点依赖 HTML 构建约 1.43 秒。

因此主要问题曾是合并算法，不是 JSON 解码。当前在输入边界一次性填充 `node_id`，所有
常规查找回到哈希 O(1)。进一步优化可采用：

- 缓存 JSON 文件 hash/mtime 对应的规范化 task artifact；
- 多 PROF 文件进程级并行解析；
- 若 msprof 提供稳定数据库 schema，直接读取 device task DB，避免 Chrome JSON 展示层；
- 超大采集使用流式 JSON parser 降低峰值内存。

在当前 100 MB 规模下，缓存的收益大于引入第三方流式依赖，暂不增加依赖。

## 5. 依赖关系模型与可视化（重点）

### 依赖的证据层级

1. **物理 stream 程序序 — observed**

   同一 `(node, device, physical_stream)` 上相邻 JSON execution 建立
   `stream_order_observed`。这表示提交/执行序，不强行解释重叠引擎任务的完成先后。

2. **stream 间 notify 同步 — observed / inferred**

   HCOMM `TaskParaNotify` 已有 `notifyID/stage/remoteUserRank/ctxId`。本次将这些字段加入
   semantic plog。新采集数据中相同 notify id 的 record→wait 形成
   `notify_sync_observed`。

   旧样本没有 notify id，只能在同 device/connection 中，按跨 stream 的 record/wait
   类型和 wait 完成前的唯一最近 producer 建立 `notify_sync_inferred`。若候选不唯一则
   不画边。

3. **rank 间协议边 — semantic**

   `tx_ack↔rx_ack`、`tx_data_signal↔rx_data_signal`、`tx_payload↔rx_payload` 使用显式
   `user_rank/peer_rank/phase/step/slice`，并按 occurrence 顺序配对，分别形成
   `peer_signal_semantic` 和 `peer_payload_semantic`。它们比 ring 邻居公式可靠，但仍依赖
   semantic 正确性和完整性。

4. **多节点依赖 — 尚未精确**

   缺少 collective instance id 与跨节点时钟校准时，不能仅凭时间连接不同节点。未来
   必须引入 `(op_instance_id, src_rank, dst_rank, protocol_seq)` 或 wait-relation artifact。

旧图中的 `same_rank_step`、`right_neighbor_ack_dep`、`upstream_prev_step`、`phase_bridge`
等规则边已从默认实现删除，因为它们是算法假设，不是物理观测。

### 当前样本结果

44,008 个物理节点得到：

- `stream_order_observed`：43,976；
- `notify_sync_observed`：0（旧样本没有新字段）；
- `notify_sync_inferred`：2,953；
- `peer_signal_semantic`：7,056；
- `peer_payload_semantic`：2,352。

每条 edge CSV 都包含 `evidence` 与 `confidence`。依赖 HTML 可按 edge kind、device、rank、
stream、event、时间范围和文本动态过滤。

## 6. 生产端覆盖与改进计划（重点）

### 当前覆盖

- `TaskData` 创建时捕获 DMA、Reduce、Notify、AIV 的 one-shot semantic snapshot；
- `TaskProfiling::Run` 使用 task 自己的 snapshot，避免读取已经变化的 TLS；
- 通用 sender/reducer 覆盖 tx payload、data signal、rx payload copy/reduce；
- single-ring concurrent-direct ReduceScatter/AllGather 覆盖：
  - 主/从流本地 copy；
  - TxAck/RxAck；
  - Tx/Rx data signal；
  - Tx payload、Rx reduce、Rx copy；
  - phase、step、slice、user/comm/peer rank。

### 已确认缺口

- phase scope 主要集中在 single-ring concurrent-direct；其他 ring/mesh/hierarchical、
  RDMA、NHR、多节点路径没有同等覆盖；
- `traceCopy/traceReduce/traceSubCopy` 只标记 vector 中第一个 task，不能称为完整 slice 级；
- `opId` 字段未形成可用的 AllReduce invocation id；
- graph 编译前 semantic 与编译后 parent task/subtask 没有映射 artifact；
- 从流 ReduceScatter 的 7 条 `copy_start` 与 AllGather copy 竞争同一物理 memcpy，说明
  phase 语义存在重叠声明；
- 当前旧样本中 12,096 个 composite 命中全部发生 semantic kind 与硬件 event kind 转换。

### 改进优先级

P0：

1. 生成全局/进程内唯一 `op_instance_id`，贯穿 RS/AG 和所有 stream；
2. 在 graph finalize/compile mapping 处输出
   `(op_instance_id, semantic_seq, parent_task_id, subtask_id, physical_stream_id, connection_id)`；
3. 使用本次新增的 notify id 字段生成精确 stream-sync 边；
4. 消除 RS/AG 对同一物理 memcpy 的双重 phase 声明。

P1：

1. 用明确的 slice/task ordinal 取代 `traceXxx` 首元素布尔量；
2. 将 phase/event context 下沉到所有算法模板共享的 primitive dispatch 边界；
3. 增加每种算法/transport 的覆盖矩阵与 golden trace。

P2：

1. 输出跨节点 protocol sequence/wait relation；
2. 引入时钟校准与误差区间；
3. 再构建 critical path、wait interval 和 NHR 依赖。

## 7. Timeline 与 Dependency HTML

Dependency HTML 现在以物理 stream 为固定高度轨道、真实时间为横轴，展示全部 JSON
execution。水平缩放与纵向轨道已经解耦，默认不再同时绘制所有依赖边；选择任务后才
显示该任务的直接前驱、直接后继和对应证据分级边。

依赖图不聚合任务。零时长任务使用菱形 marker；非零任务如果在当前缩放下真实宽度不足
2 个屏幕像素，也临时使用 marker，放大后恢复为真实时长矩形。同一可见位置存在多个
任务时，右侧详情列出候选任务。这样避免用固定最小矩形宽度夸大极短任务。

Timeline HTML 和 Dependency HTML 均新增：

- device、rank、stream、event 下拉筛选；
- task/event/match 文本搜索；
- Dependency edge kind 筛选、全局 overview 和时间标尺；
- 单击选择、双击聚焦，右侧面板沿 predecessor/successor 导航；
- hover 中展示 semantic task、profiler task、subtask、hardware event、匹配方式和置信度；
- Timeline 仍提供相对时间 start/stop 范围筛选。

依赖图是主要诊断入口；Timeline 保留为执行事实浏览器。对于 4 万级节点，HTML canvas
比 SVG 更合适，静态输出只保留 node/edge CSV。

## `test/out` 聚合质量

- semantic：28,560；JSON execution：44,008；
- exact：14,112（49.41%）；
- composite heuristic：12,096（42.35%）；
- unmatched semantic：2,352（8.24%）；
- profiler-only：17,800；duplicate execution key：0；
- 总匹配率：91.76%，因此 95% 门禁应失败。

要把 heuristic 升级为 exact，必须完成 P0 correlation mapping；不能靠调整时间阈值或
放宽匹配规则得到更高但不可证明的匹配率。
