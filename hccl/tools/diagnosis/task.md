# HCCL Step Trace 任务清单

历史归档见 [`arch-988653fc0037.md`](arch-988653fc0037.md)；当前依赖图实现归档见
[`arch-4600cb628104.md`](arch-4600cb628104.md)。本文件只保留活动任务及仍有未来约束的
阻塞项；完成项在用户指定归档后从活动清单删除。

## 1. 约定与里程碑

- 一个任务只解决一个可独立验证的问题。
- HCOMM 生产端与 HCCL 消费端分开提交。
- 未声明依赖的任务可并行。
- 状态：`[ ]` 未开始，`[-]` 进行中，`[x]` 已完成，`[!]` 阻塞。

| 里程碑 | 目标 | 完成条件 |
|---|---|---|
| M0 发布卫生 | 移除 Ring 测试强制 | HYG-001～002 |
| M1 单机可靠语义 | 不丢记录、上下文机制可回归 | CTX-002、TST-001～005 |
| M2 语义质量 | step 合同明确且可验证 | SEM-006 |
| M4 依赖图增量 | 证据不增强、local Notify 与 FFts 边界完善 | DEP-016～017、DEP-020～027 |
| M5 覆盖扩展 | 逐算法、逐 transport 可审计覆盖 | COV |
| M6 多节点因果诊断 | protocol、profile run、clock、跨节点精确边 | MNT |
| M7 诊断分析层 | critical path、等待归因和 rank imbalance | DIA |

## 2. M0：发布卫生

### HYG-001 撤回默认拓扑强制

- [ ] **仓库/文件**：HCOMM `src/algorithm/impl/alg_configurator.cc`
- **依赖**：无；Ring golden 已完成。
- **工作**：删除 `[TEST PATCH]`，恢复 8.5.0 默认 topology 选择。
- **验收**：trace 开关不影响算法选择；相关选择测试通过。

### HYG-002 撤回 ring executor 强制

- [ ] **仓库/文件**：HCOMM `src/algorithm/impl/operator/all_reduce_operator.cc`
- **依赖**：无；与 HYG-001 同批验证。
- **工作**：删除多卡 `isRingTopo` 强制 executor 分支，恢复 8.5.0 规则。
- **验收**：trace on/off 选择相同 executor；默认 mesh 回归通过。

## 3. M1：上报可靠性

### CTX-002 修复提前返回导致 one-shot 丢失

- [-] **仓库/文件**：HCOMM `task_profiling.cc`
- **依赖**：无
- **实现**：
  - 将已捕获 TaskData 的 semantic 上报收敛到 `ReportCapturedTaskSemantic()`；
  - OP_BASE、addition-info 未订阅、非 capture 路径在 step trace 开启时先上报 semantic，再跳过
    msprof addition-info；trace 关闭时保持原快速返回；
  - 正常 profiling 路径的 semantic 与 msprof addition-info 共用同一个 submit timestamp；
  - 将容易误读的 `is_subscribe` 状态判断改为显式的 `additionInfoEnabled`。
- **待验收**：subscribe、OP_BASE、capture 组合回归仍归入 TST-003～005；当前 HCOMM UT
  尚无 TaskProfiling/semantic 专项 fixture。

## 4. M1：基础设施测试

### TST-001 开关单元测试

- [ ] **仓库**：HCOMM
- **工作**：覆盖新旧环境变量、非 `"1"` 值和静态缓存。
- **验收**：测试互不依赖执行顺序。

### TST-002 RAII 嵌套恢复测试

- [ ] **仓库**：HCOMM
- **依赖**：无
- **工作/验收**：覆盖无父、单层、双层、事件 scope 和提前返回；退出后 TLS 完全恢复。

### TST-003 one-shot 捕获测试

- [ ] **仓库**：HCOMM
- **依赖**：无
- **工作/验收**：首个 TaskData 捕获成功、第二个失败，外层后续 event 可重新捕获。

### TST-004 capture stream 身份测试

- [ ] **仓库**：HCOMM
- **依赖**：无
- **工作/验收**：覆盖 `captureStreamID != streamID` 的 DMA/Reduce/Notify Save。

### TST-005 Notify 元数据测试

- [ ] **仓库**：HCOMM
- **依赖**：CTX-002
- **工作**：验证 record/wait 的 notify id、stage、通用 peer 和 FFts context 字段。
- **验收**：非 Notify task 不被误分类，不恢复已删除的重复字段。

## 5. M2：现有语义质量

### SEM-006 固化并校验 step 语义合同

- [x] **仓库**：HCCL 文档/测试；未修改 HCOMM 生产 schema
- **依赖**：无
- **完成**：
  - 定义 `step` 为 phase 内逻辑因果桶：step 0 包含 init/prelude 与 main round 0，
    `1..N-2` 为后续 main round，`N-1` 为 final/epilogue；
  - `validate_trace.py` 对 RS/AG 校验 step/rank-size 范围，并禁止 main-round link event
    进入 epilogue；未知 phase 不套用 Ring 假设；
  - 冲突输出 CSV 行号、physical task 坐标及 phase/step/rank_size/slice/event，不进行
    最近时间、邻接或自动重编号；
  - 合同同步到 `spec.md`、诊断 README 和依赖关系文档。
- **验收**：54 项 Python 单测通过；当前 golden 28,502 条 RS/AG semantic 全部通过，
  `step_contract_violations=0`；未增加 `stage_kind`，未改变 schema、exact merge 或图 identity。

## 6. M4：单机精确依赖图增量

### DEP-016 定义派生边证据传播合同

- [ ] **仓库**：HCCL 文档/测试
- **依赖**：无；graph v4 基线见 `arch-4600cb628104.md`
- **工作**：
  - 定义 `exact > observed > semantic > inferred > heuristic` 的证据格；
  - 明确派生边 confidence 等于所有 source edge 中的最弱证据；
  - 明确 kind 命名不得暗示强于实际 confidence 的证据；
  - 确定 graph schema v5 的迁移范围。
- **验收**：文档覆盖 direct、FFts、mixed order 和 Notify 收缩；单测表达
  “收缩不得增强证据”的不变量。

### DEP-017 修正 resource order 证据增强

- [ ] **仓库**：HCCL
- **依赖**：DEP-016
- **工作**：
  - `resource_dependency_graph.py` 按路径最弱 evidence/confidence 传播；
  - 将 FFts resource order 从当前错误的 observed 表达调整为 semantic；
  - mixed path 保存 source evidence 集合并取最弱等级；
  - 升级 graph schema，避免新旧 edge identity 混用。
- **验收**：
  - direct resource order 仍为 observed；
  - FFts resource order 不高于 semantic；
  - 当前 10,051 条 resource order 总量不因纯证据修正改变；
  - gate 拒绝任何 derived confidence 强于 source confidence 的边。

### DEP-020 建立主从流本地 Notify 精确关系

- [x] **仓库**：HCCL
- **依赖**：无；只消费 msprof DB 已有 Notify 物理字段
- **范围**：direct task，且 DB `dstRank=-1`；不涉及 FFts context 或跨 rank Notify。
- **工作**：
  - 以 `(node_id, operation_scope, device_id, notify_id)` 定义本地 Notify channel；
  - 将 `Notify Record` 作为 producer、`Notify Wait` 作为 consumer；
  - producer/consumer 各自必须落在唯一物理 stream、数量相等且本地执行顺序唯一；
  - 分别按两侧物理 stream 内的 DB 执行顺序编号，按 ordinal 建立
    `local_notify_sync_exact`；
  - 数量不等、多 stream、顺序不唯一或 identity 不完整时不部分配对，写入现有
    Notify ambiguity artifact；
  - resource graph 保留独立的 local Notify edge kind 与 wait timing。
- **验收**：
  - 支持 main→slave 与 slave→main 两个方向；
  - 不读取跨 stream 时间先后来决定配对，不与跨 rank `direct_notify_sync_exact` 串组；
  - 当前样例的 112 个完整 local channel 形成 5,376 条 exact execution edge；
  - execution/resource graph 均无悬空端点、自环和环，重复导出 identity 稳定；
  - 单测覆盖唯一配对、数量不等、多 stream、方向与 profiler-only endpoint。
- **完成**：
  - 新增 `LocalNotifyChannelIdentity/LocalNotifyRelationIdentity` 和
    `local_notify_sync_exact`，resource graph 映射为
    `resource_local_notify_sync_exact`；
  - 修复 CSV 宽整数经 `float` 解析导致 `UINT64 notify_id` 碰撞的问题；
  - 当前样例 112 个 channel 各 48 Record + 48 Wait，生成 5,376 条 execution/resource
    local edge；main→slave 与 slave→main 各 2,688 条；
  - Notify ambiguous/incomplete/conflict 为 0；execution/resource graph 的 duplicate、
    missing endpoint、self-loop、cycle residual 均为 0；
  - resource graph 有 8 个可解释的 upstream boundary：每个 device 最初一条
    slave→main relation 之前无资源任务，不伪造端点；
  - 61 项 Python 单测通过，当前 artifact 以 `--max-boundary-nodes 8` 通过门禁。

### DEP-021 输出 FFts parent/context 覆盖审计

- [ ] **仓库**：HCCL
- **依赖**：无
- **工作**：按 physical parent 输出 context 总数、matched/profiler-only 数、语义
  `graph_instance_id` 覆盖和缺失原因；不得从时间邻近推断 graph membership。
- **验收**：每个 FFts physical subtask 恰好归属一个 parent 覆盖组；当前“部分缺语义”
  与“整组缺语义”的 parent 可区分，计数与 execution node artifact 一致。

### DEP-022 补齐 profiler-only FFts graph membership

- [ ] **仓库**：HCCL
- **依赖**：DEP-021
- **工作**：仅在同一 `(node, device, pid, operation_scope, parent_stream,
  parent_task)` 下 graph identity 唯一时，将 graph membership 传播给 profiler-only
  context；保留 `membership_source/status`，冲突时输出歧义而不选候选。
- **验收**：补齐身份不会改变 `match_status`，不会自动产生 task 语义；同 parent 多 graph
  或 operation 不唯一时零传播且有可审计原因。

### DEP-023 输出 direct↔FFts 边界审计

- [ ] **仓库**：HCCL
- **依赖**：DEP-021
- **工作**：识别 FFts parent 在 direct physical stream 中的前驱/后继以及当前被
  direct stream order 直接跨越的边；只输出 boundary candidate，不建立 entry/exit
  因果边。
- **验收**：每个候选记录 parent identity、direct 前驱/后继、FFts context 集合和缺失项；
  无 parent identity 时不使用时间邻居代替。

### DEP-024 定义 FFts 内部依赖事实合同

- [ ] **仓库**：HCOMM/HCCL 文档与 fixture
- **依赖**：无
- **工作**：确认 runtime 或 msprof 可导出的 graph arc/barrier/token；定义
  `(graph instance, src context, dst context, relation kind)` 的最小 schema、证据等级与
  不可用时的显式状态。
- **验收**：覆盖串行、并行、fan-in、fan-out 和 barrier；明确 context 编号本身不是执行顺序，
  无事实来源时不得构造内部边。

### DEP-025 消费 FFts 内部依赖事实

- [ ] **仓库**：HCCL；若 DB 不提供事实则需要 HCOMM 生产端
- **依赖**：DEP-022、DEP-024
- **工作**：解析并校验 FFts graph arc，将事实端点映射到 physical context node；
  缺端点、重复 arc、跨 graph arc 和环写入独立审计 artifact。
- **验收**：只为有明确 relation identity 的 arc 建边；并行 context 不因编号或物理时间
  被串行化；所有内部边可回溯到源记录。

### DEP-026 建立 direct↔FFts 精确 entry/exit 关系

- [ ] **仓库**：HCCL
- **依赖**：DEP-023、DEP-025
- **工作**：由 FFts 内部 DAG 的 roots/leaves 建立 direct predecessor→roots 与
  leaves→direct successor，并移除 direct stream order 对 parent 的跨越捷径。
- **验收**：边界不使用 context 最小/最大编号或时间启发式；多 root/leaf 被完整保留；
  resource contraction 后无 bypass、自环、环或证据增强。

### DEP-027 删除传递冗余的 Peer payload semantic 因果边

- [x] **仓库**：HCCL
- **依赖**：DEP-020
- **完成**：
  - 当前 2,142 条 `peer_payload_semantic` 删除自身后全部仍可达，最短替代路径统一为
    `direct_notify_sync_exact -> direct_stream_order_observed × 3`；
  - execution builder、resource contraction 与 HTML 图例不再支持
    `peer_payload_semantic/resource_payload_semantic`；
  - 门禁将两个旧 kind 作为 forbidden edge，payload event 仍作为节点语义保留；
  - 删除已无意义的 DEP-018/019 及下游依赖，不再计划用 occurrence 或 protocol token
    恢复 payload 因果边；
  - 当前 execution/resource edge 分别为 56,675/25,479，payload edge 均为 0；
    结构门禁通过，62 项 Python 单测通过。

## 7. M5：覆盖矩阵

### COV-001 建立覆盖矩阵

- [x] **仓库**：HCCL 文档/测试
- **工作**：按 device、algorithm、phase、transport、primitive、task kind 标记支持状态。
- **验收**：每个 supported 单元有 fixture 或设备测试 ID。
- **产出**：[`文档/语义追踪覆盖矩阵.md`](../../../文档/语义追踪覆盖矩阵.md)。以
  `DT-L0-RING-DIRECT-001` 建立当前 8-device Level0 concurrent-direct Ring 基线；所有
  supported 单元均关联设备测试或 fixture ID，Level1/Level2 明确延期。

### COV-002 覆盖非 concurrent-direct ring

- [-] **仓库**：HCOMM
- **依赖**：COV-001
- **工作/验收**：只覆盖标准 ring RS/AG；golden phase/step/peer 完整且无算法强制。
- **实现**：候选实现位于分支 `feat-standard-ring`，commit `d03f838`。已覆盖
  `ReduceScatterRing`/`AllGatherRing` 的 ACK、payload、reduce/copy 和单 rank copy；
  RS/AG 使用算法 round 作为 `step`，算法标识为 `ring`。
- **已验证**：静态合同断言、`git diff --check` 和 62 项诊断侧 Python 单元测试通过。
- **待验收**：HCOMM Linux 构建、910B selector 证据和设备 golden；完成前不标记为 `[x]`。

### COV-003 覆盖 mesh

- [-] **仓库**：HCOMM
- **依赖**：COV-001
- **工作/验收**：只覆盖 910B normal/atomic Mesh RS/AG 和 Mesh Direct；Mesh RS/AG 的
  `step` 固定为 0，撤回 Ring 强制后仍输出可用语义。Small-count、Oneshot、Chunk 和 AIV
  不因 executor 名称含 Mesh 而归入本任务。
- **实现**：候选实现位于分支 `feat-mesh`，commit `90dbf90`。已覆盖 normal/atomic
  Mesh RS/AG 和 `TEMPLATE_ALL_REDUCE_MESH_DIRECT`，算法标识分别为 `mesh`、
  `mesh_atomic`、`mesh_direct`；37 个新增语义上下文的 `step` 均为 0。
- **已验证**：静态合同断言、`git diff --check` 和 62 项诊断侧 Python 单元测试通过。
- **待验收**：HCOMM Linux 构建，以及 910B atomic、normal、Mesh Direct 三组 selector/device
  golden；完成前不标记为 `[x]`。

### COV-004 覆盖 hierarchical

- [ ] **仓库**：HCOMM
- **依赖**：COV-001
- **工作/验收**：区分 intra/inter-node phase 和 rank 域；本任务不做时钟校准。

### COV-005 覆盖 NHR

- [ ] **仓库**：HCOMM
- **依赖**：COV-001
- **工作/验收**：输出每 hop 的 src/dst/protocol sequence；本任务不构图。
- **2026-08-18 进展**：设备结果确认 NHR 内部 payload SDMA 已完整命中；剩余每个
  FFTS graph 首尾 4 条 SDMA 来自公共 AllReduce executor 的 user/CCL buffer 搬运。
  已按 `allreduce_executor/copy_start` 补点，并以 `user_to_ccl_copy`、
  `ccl_to_user_copy` 区分方向。尚待设备回归，预期 operation scope 内 profiler-only
  SDMA 从 1,344 降为 0，因此暂不勾选完成。

### COV-006 覆盖 RDMA/RoCE

- [ ] **仓库**：HCOMM
- **依赖**：COV-001
- **工作/验收**：验证 Reduce、RoCE 和 ACK 的 DB task 映射，无 SDMA 误标。

### COV-007 覆盖 AIV

- [ ] **仓库**：HCOMM
- **依赖**：COV-001
- **工作/验收**：审计 AIV `Save()` 的语义捕获路径，只标注可关联 AIV kernel；父
  AI_CORE 不伪装为内部 context，不保留看似支持但永不输出的捕获接口。

### COV-008 审计 resource task-kind 覆盖

- [ ] **仓库**：HCCL 文档/测试
- **依赖**：COV-001、DEP-017
- **工作**：统计 profiler task kind、当前 resource whitelist、profiler-only 和 isolated
  节点；逐类评估 AI Core compute、新 transport primitive 是否消耗待分析资源。
- **验收**：新增 resource kind 必须有物理语义、fixture/device case 和收缩测试；未知
  kind 不自动进入 resource graph。

### COV-009 覆盖 910B/910C 单机 small-count

- [ ] **仓库**：HCOMM
- **依赖**：COV-001
- **工作**：按实际模板覆盖 910B Reduce-Bcast、Doubling/Direct、Local Reduce-Bcast，以及
  910C（`DEV_TYPE_910_93`）HD Optim；不使用 `AllReduceMeshSmallCountExecutor` 名称掩盖
  内部算法差异。
- **验收**：每类模板有 selector fixture 和对应目标设备 golden；phase/step/peer 合同完整，
  910B 与 910C 分别有设备测试 ID。

### COV-010 覆盖 910B 确定性与 Oneshot

- [ ] **仓库**：HCOMM
- **依赖**：COV-003、COV-009
- **工作**：覆盖 Local Reduce、Order Preserved、Mesh Direct Oneshot 和 Chunk Mesh；仅普通/
  atomic Mesh RS/AG 使用 `step=0`，不得把 Oneshot/Chunk 自动归入同一合同。
- **验收**：small/medium/huge count 的 selector 叶子均有 fixture；ordered/local/oneshot 合同
  分离，并至少各有一组 910B 设备 golden。

### COV-011 覆盖 910C 单机 Ring 变体

- [ ] **仓库**：HCOMM
- **依赖**：COV-002
- **工作**：覆盖 910C（`DEV_TYPE_910_93`）Single Ring、Fast Double Ring 和 Zero-copy
  Ring；复用公共 event 封装，但分别描述 ring 数、slice/rank order、stream 和 buffer path。
- **验收**：三类 selector 叶子分别有 fixture/device case；Double Ring 每个物理 ring 的
  phase/step/slice/peer 可区分，Zero-copy 有用户内存路径证据。

### COV-012 覆盖 single-rank 与单机 fallback

- [ ] **仓库**：HCOMM 文档/测试
- **依赖**：COV-001
- **工作**：为 `AllReduceSingleExecutor` 定义 local copy/no-op 语义；审计 910B/910C
  `AllReduceComm` 在 `serverNum=1` 时的可达条件和实际通信 plane，特别检查 Level0 NULL/common
  加显式 Level1=NHR 时的 `COMM_COMBINE/COMM_COMBINE_ORDER` NHR/NHR-Oneshot 路径。
- **验收**：single-rank input/output 同址与异址行为均明确；fallback 要么有选择器 fixture 和
  设备 golden，要么以不可达证明记录在覆盖矩阵中；单机 NHR 与多机 hierarchical NHR 使用
  不同覆盖声明。

## 8. M6：多节点与高级诊断

### MNT-000 定义 profile-run manifest

- [ ] **仓库**：跨仓设计文档/HCCL
- **工作**：定义 `profile_run_id`、node 输入清单、采集起止、DB/plog 所属关系和 schema；
  单次采集边界由 manifest 给出，不由每个 task 独立生成。
- **验收**：相同 `(group_name, op_name)` 跨两次采集不会合并；缺失/重复 node 或跨 run
  输入明确失败。

### MNT-001 定义跨节点 protocol sequence

- [ ] **仓库**：跨仓设计文档
- **依赖**：无；复用已归档的 operation/Notify identity 合同
- **工作/验收**：定义 op/src/dst/kind/sequence；重传、并发和多 channel 不歧义。

### MNT-002 HCOMM 输出 protocol identity

- [ ] **仓库**：HCOMM
- **依赖**：MNT-001
- **工作/验收**：tx/rx signal 只凭 identity 配对，不依赖时间或 Ring 公式；不恢复
  payload semantic 因果边。

### MNT-003 生成 wait-relation artifact

- [ ] **仓库**：HCCL
- **依赖**：MNT-002
- **工作/验收**：输出 waiter、producer、interval、evidence；每条可追溯到同步 identity。

### MNT-004 采集时钟锚点

- [ ] **仓库**：HCOMM/采集工具
- **工作/验收**：每节点采集至少两个 Host/device 锚点和误差字段。

### MNT-005 实现时钟校准 artifact

- [ ] **仓库**：HCCL
- **依赖**：MNT-000、MNT-004
- **工作/验收**：输出 offset/drift/error；缺锚点明确失败。

### MNT-006 构建多节点精确边

- [ ] **仓库**：HCCL
- **依赖**：MNT-000、MNT-002、MNT-005
- **工作/验收**：以 protocol identity 建边，时间只作一致性检查。

### MNT-007 实现 critical path

- [ ] **仓库**：HCCL
- **依赖**：DIA-002、MNT-003、MNT-006
- **工作/验收**：将单机 critical-path 分析扩展到 calibrated 多节点图；输出路径、
  累计时间、等待占比、最弱证据和校准误差；未校准边不得进入全局时间累计。

### MNT-008 实现 NHR 视图

- [ ] **仓库**：HCCL
- **依赖**：COV-005、MNT-006
- **工作/验收**：只筛选/布局共享 graph artifact，不复制 merge。

## 9. M7：诊断分析层

### DIA-001 定义单机 critical-path 计费合同

- [ ] **仓库**：HCCL 文档/测试
- **依赖**：DEP-017；等待指标合同见当前归档
- **工作**：
  - 定义 resource node duration 与 sync edge `weight_ns` 的累计方式；
  - 明确已收缩 Notify wait 不重复计费；
  - 定义 semantic edge 是否进入路径、如何报告路径最弱 evidence；
  - 定义 isolated、boundary、ambiguity 和 cycle 的处理。
- **验收**：用小型 DAG 手算 golden 覆盖并行分支、同步等待、零权边和不可比较时间。

### DIA-002 实现单机 critical-path artifact

- [ ] **仓库**：HCCL
- **依赖**：DIA-001
- **工作**：只消费 resource node/edge artifact，输出关键路径节点/边、累计 resource
  duration、同步等待、handoff 和最弱 evidence。
- **验收**：不重新构边；DAG 结果与手算 golden 一致；cycle、boundary 或 unknown timing
  按合同显式失败或降级，不静默忽略。

### DIA-003 输出 Top Wait 与同步归因

- [ ] **仓库**：HCCL
- **依赖**：DIA-001
- **工作**：按 operation/rank/phase/signal 汇总 `wait_span/remote_block/post_signal/
  handoff_gap`，并保存 record/wait/resource 反查 ID。
- **验收**：输出 top-N CSV/HTML；每个归因项可回查 resource edge 和 execution 控制链；
  observational 指标不标为硬件内部精确延迟。

### DIA-004 输出 rank/operation imbalance

- [ ] **仓库**：HCCL
- **依赖**：DIA-003
- **工作**：比较同 operation 各 rank 的资源 duration、同步等待和 handoff 分布，报告
  max/min、p50/p95 和离群 rank。
- **验收**：只比较相同 operation scope 与可比较时间域；缺 rank/operation 信息时单独
  报告 coverage，不补默认值。

### DIA-005 输出 graph coverage 报告

- [ ] **仓库**：HCCL
- **依赖**：COV-008
- **工作**：汇总 matched/profiler-only、resource/excluded、isolated、boundary、
  Notify ambiguity、已禁用旧边和未知 task kind。
- **验收**：coverage 变化可进入 golden；报告能区分“真实控制节点被排除”和“功能尚未
  覆盖”，避免把所有 profiler-only 节点视为噪声。

## 10. 端到端门禁

### E2E-001 HCOMM 构建

- [ ] **仓库**：HCOMM
- **依赖**：HYG-001、HYG-002
- **工作/验收**：`bash build.sh --pkg` 成功，无新增告警。

### E2E-002 Trace-off 回归

- [ ] **仓库**：跨仓测试
- **依赖**：E2E-001
- **工作/验收**：与 8.5.0 功能和算法选择一致，关闭时无 semantic 日志。

### E2E-004 默认 mesh golden

- [ ] **仓库**：跨仓测试
- **依赖**：COV-003、E2E-001
- **工作/验收**：无测试强制运行 910B 默认 mesh，并达到覆盖矩阵目标。

### E2E-005 生产/消费 schema 合同测试

- [ ] **仓库**：HCCL
- **工作/验收**：HCOMM 格式样例成为 parser fixture；字段类型/名称变化使测试失败。

### E2E-006 开销基准

- [ ] **仓库**：测试目录
- **依赖**：E2E-001
- **工作/验收**：测 baseline、trace off/on、小/大消息，报告置信区间和内存。

### E2E-007 诊断质量报告

- [ ] **仓库**：HCCL
- **依赖**：DEP-017
- **工作/验收**：固定 exact、kind mismatch、unmatched、profiler-only、duplicate 定义和门禁。

### E2E-009 Graph schema v5 与证据 golden

- [ ] **仓库**：HCCL、测试目录
- **依赖**：DEP-017
- **工作**：为 evidence 修正更新固定 artifact/gate golden，记录 edge ID/kind/count
  变化原因。
- **验收**：相同输入重复导出 hash 一致；golden 明确证明 derived evidence 不增强、
  operation 不串扰、禁用旧 payload semantic 因果边。

## 11. 推荐顺序

```text
HYG-001 + HYG-002 -> E2E-001 -> E2E-002

CTX-002 -> TST-005
TST-001 + TST-002 + TST-003 + TST-004

SEM-006

DEP-016 -> DEP-017
DEP-020 -> DEP-027
DEP-021 -> DEP-022
DEP-021 -> DEP-023
DEP-024
DEP-022 + DEP-024 -> DEP-025
DEP-023 + DEP-025 -> DEP-026

COV-001 -> COV-002..COV-007
COV-001 + DEP-017 -> COV-008
COV-001 -> COV-009
COV-003 + COV-009 -> COV-010
COV-002 -> COV-011
COV-001 -> COV-012
MNT-001 -> MNT-002
MNT-000 + MNT-004 -> MNT-005
MNT-000 + MNT-002 + MNT-005 -> MNT-006

DEP-017 -> DIA-001 -> DIA-002
DIA-001 -> DIA-003 -> DIA-004
COV-008 -> DIA-005
DIA-002 + MNT-003 + MNT-006 -> MNT-007

DEP-017 -> E2E-009
```
