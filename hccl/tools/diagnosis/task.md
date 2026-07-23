# HCCL Step Trace 任务清单

既有历史归档见 [`arch-988653fc0037.md`](arch-988653fc0037.md)。从 DEP-001 起，
已完成任务继续保留在本文件；只有用户明确要求时才归档。

## 1. 约定与里程碑

- 一个任务只解决一个可独立验证的问题。
- HCOMM 生产端与 HCCL 消费端分开提交。
- 未声明依赖的任务可并行。
- 状态：`[ ]` 未开始，`[-]` 进行中，`[x]` 已完成，`[!]` 阻塞。

| 里程碑 | 目标 | 完成条件 |
|---|---|---|
| M0 发布卫生 | 移除 Ring 测试强制 | HYG-001～002 |
| M1 单机可靠语义 | 不丢记录、序号稳定、基础设施可测试 | CTX/SEQ/TST |
| M2 实例与语义质量 | collective identity 稳定、phase/slice 唯一 | ID/SEM |
| M3 msprof DB 事实源 | 已完成 | 见归档 |
| M4 单机精确依赖图 | 精确 stream/sync relation 和资源图 | DEP |
| M5 覆盖扩展 | 逐算法、逐 transport 可审计覆盖 | COV |
| M6 多节点因果诊断 | protocol、clock、wait、critical path | MNT |

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

## 3. M1：Context、上报与序号

### CTX-001 固化语义捕获时机契约

- [ ] **仓库**：HCOMM
- **工作**：明确“TaskData 构造时捕获，Run 时只消费快照”。
- **验收**：scope 在 TaskData 构造后退出，Run 仍上报原快照。

### CTX-002 修复提前返回导致 one-shot 丢失

- [ ] **仓库/文件**：HCOMM `task_profiling.cc`
- **依赖**：CTX-001
- **工作**：为 addition-info、OP_BASE、非 capture 提前返回建立唯一且可验证的语义处理出口。
- **验收**：覆盖 subscribe、OP_BASE、capture 组合；被捕获语义不会静默丢失。

### CTX-003 约束字符串生命周期

- [ ] **仓库**：HCOMM
- **依赖**：CTX-001
- **工作**：限制 API 为静态字符串表，或由 TaskData 做有界拥有型拷贝。
- **验收**：延迟上报无悬空指针，内存上界和超长行为有测试。

### CTX-004 补齐 AIV 语义快照路径

- [ ] **仓库**：HCOMM
- **依赖**：CTX-001
- **工作**：让 AIV `Save()` 遵循统一捕获规则；若不支持则删除无效捕获路径并记录非目标。
- **验收**：不存在“API 看似支持但永不输出”的状态。

### CTX-005 处理空 task Save 路径

- [ ] **仓库**：HCOMM
- **依赖**：无
- **工作**：审计空参数 `Save()` 是否对应物理 execution，并明确其 semantic/probe 行为。
- **验收**：每个 Save 重载有明确分类，物理 execution 不会无说明丢失语义。

### SEQ-001 决定 `profiler_seq/semantic_seq` 去留

- [x] **仓库**：跨仓
- **完成**：确认两个本地序号均不参与 exact merge、FFts correlation、依赖边或质量门禁；
  `semantic_seq` 的去重用途由 direct merge key 和 FFts graph/context identity 替代。
- **验收**：生产语义 schema v4 和公共 CSV 均删除两个字段；v2/v3 输入中的旧字段忽略。

### SEQ-002 删除 per-device 序号表

- [x] **仓库**：HCOMM
- **依赖**：SEQ-001
- **完成/验收**：删除两套按 device 懒分配的 65,536 `atomic<u64>` 数组及分配热路径；
  `g_nextGraphInstanceId` 保留，它是 FFts graph identity，不属于已废弃 task sequence。

### SEQ-003 删除 fallback 序号

- [x] **仓库**：HCOMM
- **依赖**：SEQ-001
- **完成/验收**：随本地 task sequence 一并删除进程级 fallback，不再存在作用域静默退化。

### LOG-001 完善 probe 字段

- [ ] **仓库**：HCOMM
- **依赖**：无
- **工作**：若 probe 仅调试则删除无用参数；若可消费则输出完整身份和 schema。
- **验收**：函数签名与日志字段一致，无未使用参数。

## 4. M1：基础设施测试

### TST-001 开关单元测试

- [ ] **仓库**：HCOMM
- **工作**：覆盖新旧环境变量、非 `"1"` 值和静态缓存。
- **验收**：测试互不依赖执行顺序。

### TST-002 RAII 嵌套恢复测试

- [ ] **仓库**：HCOMM
- **依赖**：CTX-001
- **工作/验收**：覆盖无父、单层、双层、事件 scope 和提前返回；退出后 TLS 完全恢复。

### TST-003 one-shot 捕获测试

- [ ] **仓库**：HCOMM
- **依赖**：CTX-001
- **工作/验收**：首个 TaskData 捕获成功、第二个失败，外层后续 event 可重新捕获。

### TST-004 capture stream 身份测试

- [ ] **仓库**：HCOMM
- **依赖**：CTX-001
- **工作/验收**：覆盖 `captureStreamID != streamID` 的 DMA/Reduce/Notify Save。

### TST-005 Notify 元数据测试

- [ ] **仓库**：HCOMM
- **依赖**：CTX-002
- **工作**：验证 record/wait 的 notify id、stage、通用 peer 和 FFts context 字段。
- **验收**：非 Notify task 不被误分类，不恢复已删除的重复字段。

### TST-006 并发序号测试

- [x] **仓库**：HCOMM
- **依赖**：SEQ-002、SEQ-003
- **完成/验收**：本地 task sequence 及共享表已删除，不再需要该并发测试；FFts
  `graph_instance_id` 的并发测试应在 graph correlation 专项任务中独立补充。

## 5. M2：算子实例身份

### ID-001～ID-005 撤销生产端实例 ID，采用 msprof operation identity

- [x] **仓库**：HCOMM、HCCL `tools/diagnosis`
- **决策**：不再生成、传播或序列化 `op_instance_id/retry_generation`。DB 主输入已经提供
  operation metadata，规范 collective invocation identity 为 `(group_name, op_name)`；
  `op_name` 作为 opaque 值使用，不解析后缀作为私有合同。
- **HCOMM 完成**：删除 communicator 计数器/锁/FNV/碰撞集合、`OpParam` 字段、
  operation TLS/RAII、worker 快照及 plog 字段；生产 schema 回到 v4。
- **HCCL 完成**：删除 semantic/merged schema 字段及 v5 parser/validator；operation scope
  摘要只由 `(group_name, op_name)` 生成，本地 `opId` 仅验证映射唯一性。
- **边界**：当前样例 `group_name=group_name_0`，并非完整 hash；同一次分析输入必须代表
  同一 profile run。多 profile run 汇总需要外层 `profile_run_id`，同名 graph replay/retry
  若被 msprof 复用仍需要独立 execution epoch 证据。
- **验证**：38 项 Python 单测通过；`test/out` 回放保持 28,502/28,502 exact、
  44,008 个 physical task、7 个 operation scope、42 列；依赖边仍为 53,777，
  Notify 为 4,676 observed、28 single、0 ambiguous/incomplete。

## 6. M2：现有语义质量

### SEM-001 调查 RS/AG 物理 task 重叠声明

- [ ] **仓库**：HCCL 分析任务
- **工作**：按 physical execution 列出多 phase 声明。
- **产物/验收**：冲突 CSV；每类冲突有调用栈或 graph 证据，不按最近时间猜测。

### SEM-002 修复 RS/AG phase 唯一归属

- [ ] **仓库**：HCOMM
- **依赖**：SEM-001
- **工作**：调整 scope；必要时使用明确 `phase_transition`，不复制 task。
- **验收**：golden trace phase 冲突为 0。

### SEM-003 定义 task/slice ordinal

- [ ] **仓库**：跨仓设计文档
- **工作**：区分算法 slice、vector element、primitive submission 和 physical context。
- **验收**：四种序号不再复用同一字段。

### SEM-004 修复 ReduceScatter 首元素标注

- [ ] **仓库**：HCOMM
- **依赖**：SEM-003
- **工作**：为 RS vector primitive 建立可关联 ordinal，删除首元素布尔标记。
- **验收**：每条 semantic 精确指向一个 execution，无 duplicate。

### SEM-005 修复 AllGather 首元素标注

- [ ] **仓库**：HCOMM
- **依赖**：SEM-003
- **工作**：为 AG init/sub/final copy 和 receive vector 使用明确 ordinal。
- **验收**：覆盖率和预期 task 数有 golden 断言。

### SEM-006 校准 step 编号

- [ ] **仓库**：HCOMM、schema 文档
- **工作**：明确 init、主循环、final 编号；必要时增加 `stage_kind`。
- **验收**：任意 rank 的 step 无歧义，不因编号碰撞串边。

## 7. M4：单机精确依赖图

### DEP-001 定义双层图合同

- [x] **仓库**：HCCL 文档
- **完成**：定义 execution/resource graph、稳定 identity、证据等级、歧义、控制收缩和
  边权；execution 保留 Notify，resource 收缩边必须反查控制证据，时间最近不得产生 exact。
- **验证**：合同已写入 `spec.md` 8.6。

### DEP-002 建立稳定 operation/execution identity

- [x] **仓库**：HCCL
- **依赖**：DEP-001
- **完成**：使用 DB operation scope；node ID 不再依赖 CSV 行号或时间；重复 execution
  identity 为硬错误；本地 `opId` 只做 scope 映射验证，operation connection 仅作本地诊断，
  两者都不用于跨 device/rank 关联。
- **验证**：44,008 个 execution 全量反序后 ID 全部不变；operation scope
  unique 43,680、missing 328、ambiguous 0；诊断单元测试覆盖 operation scope 的跨
  device、跨 node、group 隔离和本地映射歧义。

### DEP-003 隔离 direct stream 顺序

- [x] **仓库**：HCCL
- **依赖**：DEP-001、DEP-002
- **完成**：direct builder 只接收 `subtask_id < 0`，按 node/device/physical stream 和
  DB 精确十进制时间分组；同起始时间作为无序 bucket，不靠 CSV 行号强排，重叠 pair 不建边。
- **验证**：27,544 个 direct execution、32 个 physical stream 组生成 27,512 条
  `direct_stream_order_observed`；FFts row 进入数为 0，时间精度/同时间测试通过。

### DEP-004 使用逻辑 stream 重建 FFts 顺序

- [x] **仓库**：HCCL
- **依赖**：DEP-001、DEP-002
- **完成**：只对 exact matched 且 operation/parent/context 完整的 FFts row，按
  node/device/pid/op/graph parent/semantic stream 分组，以唯一 context 声明序建边。
- **验证**：14,405 个 context、670 个逻辑流组生成 13,735 条
  `ffts_logical_stream_order`；跨逻辑 stream 边为 0。原 2,352 是旧分析估计；当前 DB
  全量审计实际删除 4,690 条双向跨逻辑流伪边，并隔离所有 profiler-only FFts context。

### DEP-005 定义 Notify relation identity

- [x] **仓库**：跨仓设计文档、HCCL 共享模型
- **依赖**：DEP-001
- **完成**：区分 Notify resource 与 relation occurrence；relation identity 固化为
  op、规范化 producer/consumer、signal、phase/step/slice、notify resource 和
  graph/protocol sequence，不包含时间、connection 或本地 opId。
- **验证**：相同 16 个 Notify resource 在 FFts 中展开为 4,704 个 relation candidate：
  4,676 个唯一 producer+consumer，14 个仅 producer、14 个仅 consumer；资源跨 graph
  复用时 stable relation ID 不同。direct 因缺共享 sequence 明确保持 incomplete。

### DEP-006 精确配对 FFts Notify

- [x] **仓库**：HCCL
- **依赖**：DEP-004、DEP-005
- **完成**：按完整 `NotifyRelationIdentity` 分组；仅恰好一个 producer 和一个
  consumer 时生成 `ffts_notify_sync_observed/observed`，边保存稳定 relation ID。
  单边、多端和缺字段分别输出 `single/ambiguous/incomplete` 到
  `*_notify_ambiguities.csv`，不读取时间做消歧。
- **验证**：当前 DB replay 生成 4,676 条唯一 observed relation、28 条 single
  （14 缺 producer、14 缺 consumer）、0 ambiguous、0 incomplete；单测覆盖
  唯一配对、单边、多端禁止排序 zip、graph instance 隔离资源复用。

### DEP-007 为 direct Notify 输出同步 token

- [!] **仓库**：HCOMM
- **依赖**：DEP-002、DEP-005
- **阻塞**：DB `(group_name, op_name)` 已隔离 collective invocation，但
  Notify/transport 仍未暴露跨 rank 共享的 `channel_id + protocol occurrence sequence`。
  `notify_id` 是复用资源，`task_id/connection_id` 是本地执行关联；operation scope
  单独仍不能区分同一 collective 内的多次 record/wait。
- **调查证据**：当前 direct 9,399 个 endpoint 去掉 sequence 后只形成 784 个候选组，
  每组聚合 11～12 个端点。给 Tx/Rx 各自增加本地计数器只能在理想调用顺序下对齐；
  非对称 retry 会使后续整体错位，多 channel 会从相同初值碰撞，回绕会复用旧 token。
- **解除条件**：由 transport 协议层输出
  `(channel_id, signal_kind, protocol_seq_or_epoch_seq)`，离线侧与
  `(group_name, op_name)` operation scope 组合，
  使用饱和/epoch 机制禁止静默 wrap。完成后必须重新构建 HCOMM，并采集含正常、并发、
  retry 和多 channel 的设备数据，验收每个 token 恰好一个 producer/consumer。

### DEP-008 删除 connection/time 默认推断

- [x] **仓库**：HCCL
- **依赖**：DEP-005
- **完成**：从默认 builder、edge vocabulary 和 HTML 图例删除
  `notify_sync_inferred`；不提供隐式 research fallback。
- **验收**：DB replay 的 inferred 从 5,094 降为 0，总边数从 58,871 降为 53,777；
  旧 JSON 3,016 条和 DB 5,094 条 connection/time 结果都不再进入因果图，单测验证
  即使 connection 和时间形成唯一最近候选也不构边。

### DEP-009 消费显式同步 token

- [ ] **仓库**：HCCL
- **依赖**：DEP-005、DEP-007
- **工作**：按 token 构建 exact relation，并校验 notify/rank/phase。
- **验收**：重复、单边、冲突 token 使质量门禁失败。

### DEP-010 合并 Notify 与 peer semantic 证据

- [ ] **仓库**：HCCL
- **依赖**：DEP-005、DEP-006、DEP-009
- **工作**：ACK/data-signal 合为一条同步边及多份 evidence；payload 边保持独立。
- **验收**：无重复控制边；身份冲突进入 validation。

### DEP-011 产出 execution graph artifact

- [ ] **仓库**：HCCL
- **依赖**：DEP-003、DEP-004、DEP-006、DEP-008、DEP-009、DEP-010
- **工作**：输出稳定 nodes/edges，保留资源 task、Notify、stream、payload 和证据。
- **验收**：endpoint 完整、edge identity 唯一，环/孤立/缺失分别统计。

### DEP-012 折叠 resource graph

- [ ] **仓库**：HCCL
- **依赖**：DEP-011
- **工作**：按可达关系收缩 `resource -> record -> wait -> resource`；缺端使用 boundary。
- **验收**：resource edge 可反查原始 Notify，分支和控制链不丢关系。

### DEP-013 计算同步边时间指标

- [ ] **仓库**：HCCL
- **依赖**：DEP-012
- **工作**：输出 `wait_span_ns/remote_block_ns/post_signal_ns/handoff_gap_ns`。
- **验收**：边界时间有测试；未校准的跨节点边不计算可比较权重。

### DEP-014 支持 execution/resource 双视图

- [ ] **仓库**：HCCL
- **依赖**：DEP-011、DEP-012、DEP-013
- **工作**：SVG/HTML 只消费共享 artifact，不在布局层推断依赖。
- **验收**：两种视图共享稳定 ID；resource 视图展示边指标和 evidence。

### DEP-015 建立依赖图门禁

- [ ] **仓库**：HCCL
- **依赖**：DEP-014
- **工作**：统计 stream、sync、payload、ambiguity、环、boundary 和伪边删除。
- **验收**：FFts 伪顺序和默认 time-inferred 均为 0；golden 变化需说明。

## 8. M5：覆盖矩阵

### COV-001 建立覆盖矩阵

- [ ] **仓库**：HCCL 文档/测试
- **工作**：按 device、algorithm、phase、transport、primitive、task kind 标记支持状态。
- **验收**：每个 supported 单元有 fixture 或设备测试 ID。

### COV-002 覆盖非 concurrent-direct ring

- [ ] **仓库**：HCOMM
- **依赖**：COV-001
- **工作/验收**：只覆盖标准 ring RS/AG；golden phase/step/peer 完整且无算法强制。

### COV-003 覆盖 mesh

- [ ] **仓库**：HCOMM
- **依赖**：COV-001
- **工作/验收**：覆盖 910B 默认 mesh，撤回 Ring 强制后仍输出可用语义。

### COV-004 覆盖 hierarchical

- [ ] **仓库**：HCOMM
- **依赖**：COV-001
- **工作/验收**：区分 intra/inter-node phase 和 rank 域；本任务不做时钟校准。

### COV-005 覆盖 NHR

- [ ] **仓库**：HCOMM
- **依赖**：COV-001
- **工作/验收**：输出每 hop 的 src/dst/protocol sequence；本任务不构图。

### COV-006 覆盖 RDMA/RoCE

- [ ] **仓库**：HCOMM
- **依赖**：COV-001
- **工作/验收**：验证 Reduce、RoCE 和 ACK 的 DB task 映射，无 SDMA 误标。

### COV-007 覆盖 AIV

- [ ] **仓库**：HCOMM
- **依赖**：CTX-004、COV-001
- **工作/验收**：只标注可关联 AIV kernel；父 AI_CORE 不伪装为内部 context。

## 9. M6：多节点与高级诊断

### MNT-001 定义跨节点 protocol sequence

- [ ] **仓库**：跨仓设计文档
- **依赖**：DEP-002、DEP-005
- **工作/验收**：定义 op/src/dst/kind/sequence；重传、并发和多 channel 不歧义。

### MNT-002 HCOMM 输出 protocol identity

- [ ] **仓库**：HCOMM
- **依赖**：MNT-001
- **工作/验收**：tx/rx signal/payload 只凭 identity 配对，不依赖时间或 Ring 公式。

### MNT-003 生成 wait-relation artifact

- [ ] **仓库**：HCCL
- **依赖**：DEP-001、DEP-005、MNT-002
- **工作/验收**：输出 waiter、producer、interval、evidence；每条可追溯到同步 identity。

### MNT-004 采集时钟锚点

- [ ] **仓库**：HCOMM/采集工具
- **工作/验收**：每节点采集至少两个 Host/device 锚点和误差字段。

### MNT-005 实现时钟校准 artifact

- [ ] **仓库**：HCCL
- **依赖**：MNT-004
- **工作/验收**：输出 offset/drift/error；缺锚点明确失败。

### MNT-006 构建多节点精确边

- [ ] **仓库**：HCCL
- **依赖**：DEP-001、MNT-002、MNT-005
- **工作/验收**：以 protocol identity 建边，时间只作一致性检查。

### MNT-007 实现 critical path

- [ ] **仓库**：HCCL
- **依赖**：DEP-012、DEP-013、MNT-003、MNT-006
- **工作/验收**：输出路径、累计时间、等待占比和证据；环单独报告。

### MNT-008 实现 NHR 视图

- [ ] **仓库**：HCCL
- **依赖**：COV-005、DEP-014、MNT-006
- **工作/验收**：只筛选/布局共享 graph artifact，不复制 merge。

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
- **依赖**：E2E-001、SEQ-002
- **工作/验收**：测 baseline、trace off/on、小/大消息，报告置信区间和内存。

### E2E-007 诊断质量报告

- [ ] **仓库**：HCCL
- **依赖**：DEP-002、DEP-015
- **工作/验收**：固定 exact、kind mismatch、unmatched、profiler-only、duplicate 定义和门禁。

### E2E-008 DB 输入与依赖图 golden replay

- [ ] **仓库**：HCCL、测试目录
- **依赖**：DEP-015
- **工作**：只用 plog + DB 重放 merge、validate、execution/resource graph 和可视化。
- **验收**：44,008 profiler task、28,502 exact、14,405 FFts exact；伪顺序和默认
  time-inferred 为 0。

## 11. 推荐顺序

```text
HYG-001 + HYG-002 -> E2E-001 -> E2E-002

SEQ-001 -> SEQ-002 + SEQ-003（已完成：删除本地 task sequence）
CTX-001 -> CTX-002..CTX-005 -> TST-001..TST-005

SEM-001 -> SEM-002
SEM-003 -> SEM-004 + SEM-005

DEP-001 -> DEP-002 -> DEP-003 + DEP-004
DEP-001 -> DEP-005 -> DEP-006 + DEP-008（已完成）
DEP-002 + DEP-005 -> DEP-007 -> DEP-009
DEP-006 + DEP-009 -> DEP-010
DEP-003..DEP-010 -> DEP-011 -> DEP-012 -> DEP-013 -> DEP-014 -> DEP-015

COV-001 -> COV-002..COV-007
DEP-002 + DEP-005 -> MNT-001 -> MNT-002
MNT-004 -> MNT-005
MNT-002 + MNT-005 -> MNT-006
```
