# HCCL Step Trace 后续任务清单

## 1. 拆分原则

本清单基于 `spec.md` 的当前差异和风险。任务按以下原则拆分：

- 一个任务只解决一个可验证问题；
- HCOMM 生产端与 HCCL 消费端分开提交；
- schema 先定义、生产与消费分别实现，避免一次跨仓大提交；
- 算法覆盖按模板/transport 分任务，不以“覆盖全部算法”作为单个任务；
- 每项均给出依赖、产物和验收条件；
- 未明确写依赖的任务可并行实施。

状态约定：

- `[ ]` 未开始
- `[-]` 进行中
- `[x]` 完成
- `[!]` 阻塞

## 2. 里程碑

| 里程碑 | 目标 | 完成条件 |
|---|---|---|
| M0 发布卫生 | 移除生产路径中的测试强制行为 | HYG 全部完成 |
| M1 单机可靠语义 | 不丢记录、序号契约稳定、基础设施可测试 | CTX/SEQ/TST 基础项完成 |
| M2 FFts 精确关联 | composite subtask 不再依赖固定偏移 | ID/COR 全部完成 |
| M3 msprof DB 事实源 | DB 成为默认输入，JSON 生产入口退役 | DBI 全部完成 |
| M4 单机精确依赖图 | 区分 FFts 逻辑 stream，精确配对同步并提供资源图 | DEP 全部完成 |
| M5 覆盖扩展 | 逐算法、逐 transport 增加可审计覆盖 | COV 任务按目标平台完成 |
| M6 多节点因果诊断 | 形成 protocol、wait、clock 和 critical path artifact | MNT 任务完成 |

## 3. M0：发布卫生

### HYG-001 撤回默认拓扑强制

- [ ] **仓库**：HCOMM（已解阻）
- **文件**：`src/algorithm/impl/alg_configurator.cc`
- **依赖**：HYG-003 或目标 Ring 功能验证完成
- **历史阻塞原因**：当前 910B module 的 `SetAlgoLevel0Module()` 会明确忽略显式
  `HCCL_ALGO level0:ring`。若现在恢复默认 `ALG_LEVEL0_NP_MESH`，实际设备 workload
  将无法稳定进入待验证的 single-ring 插桩路径。
- **临时决定**：保留 `[TEST PATCH]`，继续把全 HCCS 910B 默认拓扑强制为
  `ALG_LEVEL0_NP_SINGLE_RING`，仅用于完成当前 Ring 功能验证。
- **解阻结论**：`test/out` 已完成目标 Ring 功能验证：28,502/28,502 exact，
  FFts 14,405/14,405 parent+ctx exact。完成一次 schema v3 短采集后即可撤回强制。
- **产物**：单文件功能提交。
- **验收**：
  - 与 `../hcomm` 的该函数行为一致；
  - trace 开关不影响算法 level 0 默认选择；
  - 相关算法选择测试通过。

### HYG-002 撤回 operator 的 ring executor 强制

- [ ] **仓库**：HCOMM（已解阻）
- **文件**：`src/algorithm/impl/operator/all_reduce_operator.cc`
- **依赖**：HYG-003 或目标 Ring 功能验证完成
- **历史阻塞原因**：8.5.0 的 910B 多卡选择树在 ring topology 下仍会落入
  `AllReduceComm`；只保留 topology 强制不足以进入
  `AllReduceRingFor91093Executor` 和 concurrent-direct RS/AG 模板。
- **临时决定**：保留多卡 `isRingTopo` 的 `[TEST PATCH]` executor 选择分支。
- **解阻结论**：与 HYG-001 相同；移除时必须同时恢复 topology 和 operator 两处默认行为。
- **产物**：单文件功能提交。
- **验收**：
  - 生产选择树恢复 8.5.0 规则；
  - trace 开关开/关得到相同 executor 选择。

### HYG-003 提供测试侧 ring 路径选择

- [x] **仓库**：测试目录；如确需 HCOMM 测试接口，单独评审
- **依赖**：无；若本任务找到可行选择方案，再解阻 HYG-001、HYG-002
- **调查结论**：
  - `HCCL_ALGO` 能解析 `level0:ring`；
  - 但 910B module 的 `SetAlgoLevel0Module()` 只接受 `default/NA/null`，对 ring
    打印 warning 后仍走默认 topology；
  - 即使构造出 ring topology，8.5.0 多卡 operator 也不会选择目标 executor；
  - 现有 910_93 ST fixture 或标卡 topology 不能证明真实 910B module workload
    会走同一路径。
- **结论**：没有发现“不修改 HCOMM 源码”且能在目标 910B module 上稳定选择
  `AllReduceRingFor91093Executor` 的方式。新增环境变量或扩展 `HCCL_ALGO` 支持本身都属于
  HCOMM 产品源码变更，不满足当前约束。
- **临时决定**：不向测试脚本加入会被生产端忽略的 `--force-ring`，继续使用
  HYG-001/HYG-002 的临时源码强制完成 Ring 功能验证。
- **关闭依据**：以下第 1 项已经满足：
  1. Ring 功能验证完成，可以直接撤回两处强制；
  2. HCOMM 正式支持 910B module 的显式 level-0 ring 配置；
  3. 设备测试框架提供可证明等价的 topology/executor 注入接口。
- **产物**：阻塞调查结论；解阻后再实现可复用的 ring direct workload 启动方式。
- **验收**：
  - 测试能稳定进入 RS/AG concurrent-direct；
  - 不设置测试参数时完全保持默认算法行为；
  - 测试日志能证明实际 executor/template。

## 4. M1：Context、上报与序号可靠性

### CTX-001 固化语义捕获时机契约

- [ ] **仓库**：HCOMM
- **依赖**：无
- **工作**：在头文件注释和测试中明确“TaskData 构造时捕获、Run 时只消费快照”。
- **产物**：API 契约注释和最小单元测试。
- **验收**：scope 在 TaskData 构造后退出，Run 仍能上报原快照。

### CTX-002 修复提前返回导致 one-shot 丢失

- [ ] **仓库**：HCOMM
- **文件**：`task_profiling.cc`
- **依赖**：CTX-001
- **工作**：重排 `TaskProfiling::Run()`，保证被 TaskData 捕获的语义不会因
  addition-info/OP_BASE 提前返回而静默丢失。先定义该模式是否仍应输出 plog，再实现唯一出口。
- **验收**：
  - 覆盖 `is_subscribe` 真/假、OP_BASE、capture 真/假四类组合；
  - one-shot 被捕获时要么明确上报，要么在返回前可恢复且有测试证明；
  - `profiler_seq` 与选择的契约一致。

### CTX-003 约束字符串生命周期

- [ ] **仓库**：HCOMM
- **依赖**：CTX-001
- **工作**：选择并实施一种方案：
  1. API 只接受静态枚举/字符串表；或
  2. TaskData 对字符串做有界拥有型拷贝。
- **验收**：
  - TaskData 延迟上报时不存在悬空 `const char *`；
  - 最大内存增量有明确上界；
  - 字符串过长行为有测试。

### CTX-004 补齐 AIV 的语义快照路径

- [ ] **仓库**：HCOMM
- **依赖**：CTX-001
- **工作**：让 AIV 专用 `Save()` 与其他 TaskData 路径遵循同一捕获/上报规则；
  若 AIV 明确不支持语义，则删除无效的 AIV TaskData 捕获并记录非目标。
- **验收**：
  - 支持方案：AIV 有 context 时输出完整语义，无 context 时仅推进序号；
  - 不支持方案：API 和文档不存在“看似支持但永不调用”的路径。

### CTX-005 处理空 task Save 路径

- [ ] **仓库**：HCOMM
- **依赖**：SEQ-001
- **工作**：审计两个直接返回成功的空参数 `Save()` 重载，判断它们是否对应 msprof
  物理 execution；若对应，则推进统一 submission 序号并输出受控 probe。
- **验收**：
  - 每个 Save 重载在序号契约表中有明确分类；
  - golden workload 中 `profiler_seq` 不因空 task 无说明地跳位。

### SEQ-001 定义 `profiler_seq`/`semantic_seq` 契约

- [ ] **仓库**：HCOMM 文档/API
- **依赖**：无
- **工作**：定义序号的作用域、起点、包含的 task 类型、是否跨 graph、越界行为和进程重用行为。
- **产物**：头文件契约表。
- **验收**：
  - 能回答 AIV、空 task、提前返回、capture task 是否计数；
  - 消费端不再根据实现细节猜测含义。

### SEQ-002 降低 per-device 序号表内存

- [ ] **仓库**：HCOMM
- **依赖**：SEQ-001
- **工作**：以实际 stream id 范围为依据，在稀疏 map、分段数组或受控上限中选择实现，
  替换每 device 每套固定 65536 原子的分配方式。
- **验收**：
  - 8/16/64 device 的理论和实测内存有报告；
  - 并发递增保持无重复；
  - 热路径性能不劣于约定阈值。

### SEQ-003 明确并测试 fallback 序号

- [ ] **仓库**：HCOMM
- **依赖**：SEQ-001
- **工作**：为 device/stream 越界和分配失败定义可检测行为，避免无标记地退化为全局序号。
- **验收**：
  - 日志或状态字段能识别 fallback；
  - fallback 不会被消费端误认为正常 per-stream 序号；
  - 有边界单元测试。

### LOG-001 完善 probe 字段

- [ ] **仓库**：HCOMM
- **依赖**：SEQ-001
- **工作**：决定 probe 是否是可消费数据。若仅调试，移除无用 `taskId` 参数；若用于序号审计，
  输出 device/stream/task/type/profiler_seq 和明确 schema。
- **验收**：函数签名与实际日志字段一致，无未使用参数。

### LOG-002 为 schema version 建立演进规则

- [x] **仓库**：HCOMM/HCCL
- **依赖**：无
- **工作**：semantic 当前生产版本升级为 v3；消费端接受 v2/v3，拒绝 v1、无版本和旧
  token 格式。Graph correlation version 1 是独立 schema。
- **验收**：生产端和 `parse_plog.py` 版本一致，v1 rejection 与 v2/v3 parsing 有单元测试。

## 5. M1：基础设施测试

### TST-001 开关单元测试

- [ ] **仓库**：HCOMM
- **依赖**：无
- **工作**：覆盖新旧环境变量、非 `"1"` 值和函数静态缓存行为。
- **验收**：每种输入有独立断言，测试不依赖执行顺序。

### TST-002 RAII 嵌套恢复测试

- [ ] **仓库**：HCOMM
- **依赖**：CTX-001
- **工作**：测试无父 scope、单层 scope、两层完整 scope、事件 scope 和异常/提前返回析构。
- **验收**：每次退出后 TLS 与进入前完全一致。

### TST-003 one-shot 捕获测试

- [ ] **仓库**：HCOMM
- **依赖**：CTX-001
- **工作**：验证 event scope 只允许首个 TaskData 捕获，父 context 能在析构后恢复。
- **验收**：首个 capture 成功、第二个失败、外层后续 event 可再次成功。

### TST-004 capture stream 身份测试

- [ ] **仓库**：HCOMM
- **依赖**：CTX-001
- **工作**：覆盖 `captureStreamID != streamID` 的 DMA/Reduce/Notify Save 重载。
- **验收**：profiler 原字段保持预期，语义日志使用真实物理 stream。

### TST-005 notify 元数据测试

- [ ] **仓库**：HCOMM
- **依赖**：CTX-002
- **工作**：对 record/wait 分别验证保留的 notify id、stage；remote rank 使用通用
  `peer_rank`，context 使用通用 `ffts_ctx_id`。
- **验收**：非 notify task 不被误当作同步事件；不再输出重复 notify 专用字段。

### TST-006 并发序号测试

- [ ] **仓库**：HCOMM
- **依赖**：SEQ-002、SEQ-003
- **工作**：多线程、多 device、多 stream 并发推进两套序号。
- **验收**：每个约定作用域内从 0 连续或满足契约、无重复、无数据竞争。

## 6. M2：算子实例身份

### ID-001 定义 `op_instance_id`

- [ ] **仓库**：跨仓设计文档
- **依赖**：LOG-002
- **工作**：定义进程/节点内唯一性、生命周期、重试行为、wrap 行为和跨 rank 关联方式。
- **验收**：给出 AllReduce 正常、并发、重试三个序列示例。

### ID-002 在 AllReduce 入口生成实例 ID

- [ ] **仓库**：HCOMM
- **依赖**：ID-001
- **工作**：在稳定的 collective invocation 边界生成 ID，不与算法选择或 trace 开关耦合。
- **验收**：同一 invocation 的 RS/AG 共用 ID，不同 invocation 不重复。

### ID-003 将实例 ID 贯穿语义 scope

- [ ] **仓库**：HCOMM
- **依赖**：ID-002
- **工作**：把 ID 写入 `TaskSemanticTraceInfo`，验证主/从 stream 和嵌套 scope 不丢失。
- **验收**：同一 invocation 的所有已标注 task 输出相同 ID。

### ID-004 序列化 `op_instance_id`

- [ ] **仓库**：HCOMM
- **依赖**：ID-003、LOG-002
- **工作**：升级日志 schema 并输出实例 ID；清理或正式定义现有未使用的 `opId/opType`。
- **验收**：新旧日志格式均有明确解析策略。

### ID-005 消费端解析实例 ID

- [ ] **仓库**：HCCL `tools/diagnosis`
- **依赖**：ID-004
- **工作**：扩展 `schema.py`、`parse_plog.py` 和相关 CSV 字段。
- **验收**：
  - v1 fixture 明确拒绝；
  - v2 golden 与 v3 fixture 均可解析；
  - 新 fixture 保留实例 ID；
  - 单元测试覆盖缺失/非法值。

## 7. M2：FFts parent/subtask 精确关联

### COR-001 定位 graph finalize 映射钩子

- [x] **仓库**：HCOMM 调查
- **依赖**：SEQ-001、ID-001
- **工作**：只做只读调用链调查，找出 semantic submission 到
  `(parent_task_id, context_id, physical_stream_id, connection_id)` 的最小稳定挂点。
- **产物**：已定位 `DispatcherGraph::GraphAdd*Task -> TaskPara.ctxId` 与
  graph launch `PluginRunner -> TaskProfiling::Save(stream, task)` 两个稳定挂点。
- **验收**：不靠固定 ordinal 即可描述至少一个真实 direct-ring graph。

### COR-002 定义 correlation artifact schema

- [x] **仓库**：跨仓设计文档
- **依赖**：COR-001、ID-001
- **工作**：已在 `spec.md` 定义最小字段：
  `pid, graph_instance_id, ffts_ctx_id, parent_task_id, parent_stream_id`。
- **验收**：普通 task、composite task、无语义 task 均有明确表示方法。

### COR-003 HCOMM 输出 correlation

- [x] **仓库**：HCOMM
- **依赖**：COR-002、ID-004
- **工作**：已输出 semantic schema v3 字段和 version 1
  `[HcclTaskGraphCorrelation]` 日志；设备侧验收归入 E2E-003。
- **验收**：
  - 一个 semantic 最多映射一个物理 execution；
  - artifact 无重复主键；
  - 关闭 trace 时无额外持久化开销。

### COR-004 HCCL 解析 correlation

- [x] **仓库**：HCCL `tools/diagnosis`
- **依赖**：COR-002
- **工作**：已新增 `GraphCorrelation` dataclass 和独立 plog correlation parser。
- **验收**：标准库实现；合法、缺字段、重复键 fixture 全覆盖。

### COR-005 增加 exact composite merge

- [x] **仓库**：HCCL `tools/diagnosis`
- **依赖**：COR-003、COR-004、ID-005
- **工作**：已按 parent correlation + `ffts_ctx_id` 精确认领 profiler context，输出独立
  `match_method` 和 `exact` confidence。
- **验收**：同一 profiler execution 不被两个 semantic 认领；kind mismatch 单独计数。

### COR-006 删除 direct-ring 固定偏移

- [x] **仓库**：HCCL `tools/diagnosis`
- **依赖**：COR-005
- **工作**：固定偏移、ordinal、`profiler_seq` composite heuristic 及对应 CLI 已全部删除。
- **验收**：direct 只允许 task-id exact，FFts 只允许 parent+ctx exact。

## 8. M2：现有语义质量

### SEM-001 调查 RS/AG 物理 task 重叠声明

- [ ] **仓库**：HCCL 分析任务
- **依赖**：COR-005
- **工作**：以 correlation 后的 physical execution 为键，列出被多个 phase 声明的任务。
- **产物**：冲突 CSV 和归属规则建议。
- **验收**：每类冲突有真实调用栈或 graph 证据，不用时间最近原则猜测。

### SEM-002 修复 RS/AG phase 唯一归属

- [ ] **仓库**：HCOMM
- **依赖**：SEM-001
- **工作**：调整 scope 边界，使同一物理 task 只属于一个 phase；必要时引入明确
  `phase_transition`，不复制 task。
- **验收**：新 golden trace 中 phase 冲突为 0。

### SEM-003 定义 task/slice ordinal

- [ ] **仓库**：跨仓设计文档
- **依赖**：COR-002
- **工作**：区分算法 slice、vector element、primitive submission 和物理 subtask ordinal。
- **验收**：四种序号不能再复用同一字段表达。

### SEM-004 替换 ReduceScatter 的 `traceXxx` 首元素布尔量

- [ ] **仓库**：HCOMM
- **依赖**：SEM-003
- **工作**：对 RS vector 中每个需要诊断的 primitive 建立可关联 ordinal，
  删除首元素专用布尔标记。
- **验收**：每个输出 semantic 都能精确指向一个 physical execution，且无 duplicate。

### SEM-005 替换 AllGather 的首元素布尔量

- [ ] **仓库**：HCOMM
- **依赖**：SEM-003
- **工作**：对 AG init/sub/final copy 和 receive vector 使用明确 ordinal。
- **验收**：逐 vector element 覆盖率和预期 task 数有 golden 断言。

### SEM-006 校准 step 编号

- [ ] **仓库**：HCOMM + schema 文档
- **依赖**：无
- **工作**：明确 init、主循环、final 的逻辑编号，决定是否增加 `stage_kind`
  而不是把 init 和主循环都编码为 step 0。
- **验收**：任意 rank 下 step 展示无歧义，peer 配对不因编号碰撞串边。

### SEM-007 调查 Notify record/wait 命名空间

- [x] **仓库**：HCCL `tools/diagnosis`
- **依赖**：TST-005
- **调查结论**：
  - HCOMM 的 `notify_id=(user_rank << 32) | offset_low32` 是可用的物理 Notify 资源身份；
  - record 与对应 wait 位于不同 device，现有 `(node, device, notify_id)` 分组错误地拆开两端，
    因而 `notify_sync_observed=0`；
  - 去掉 `device_id` 后，同一 Notify 资源仍跨 step、graph launch 和 collective invocation
    复用，不能只按 `notify_id` 或时间最近建立 exact 边；
  - `connection_id` 是本地 profiler 关联范围，不是同步 pair identity。
- **后续实现**：移入 DEP-005～DEP-010；禁止继续扩展 connection/time 最近匹配。
- **验收证据**：当前 18,779 条 Notify semantic 已完成按 device、notify、op/graph instance
  和逻辑协议坐标的分组审计。

## 9. M3：msprof DB 主输入迁移

### DBI-001 固化 msprof DB 输入合同

- [x] **仓库**：HCCL `tools/diagnosis` 文档
- **依赖**：无
- **工作**：
  - 选择每个 `PROF_*` 根目录下的 consolidated `msprof_*.db` 作为主输入；
  - 固化 `META_DATA.SCHEMA_VERSION`、必需表/列、整数纳秒时间单位和只读打开规则；
  - 定义采集未结束、DB 损坏、未知 schema、缺表和多 DB 冲突的错误行为。
- **产物**：`spec.md` DB schema 支持矩阵及输入合同。
- **验收**：
  - 当前 schema `1.2.0` 有明确适配条目；
  - 使用 SQLite URI `mode=ro`，工具不会修改 profiler DB；
  - 未支持版本明确失败，不静默降级或猜列。

### DBI-002 建立最小 SQLite fixture 工厂

- [x] **仓库**：HCCL `tools/diagnosis`
- **依赖**：DBI-001
- **工作**：仅用标准库 `sqlite3` 创建临时 DB，分别覆盖 direct、FFts、Notify、
  communication op、compute task、未知版本和缺表场景。
- **产物**：可复用测试 helper 和按表隔离的 fixture。
- **验收**：
  - 单元测试不依赖真实 msprof 安装或固定本机路径；
  - 每个错误场景有独立断言；
  - fixture 关闭后不残留临时文件。

### DBI-003 实现基础物理 TASK 解析

- [x] **仓库**：HCCL `tools/diagnosis`
- **依赖**：DBI-001、DBI-002
- **工作**：新增 `parse_msprof_db.py`，从 `TASK + STRING_IDS` 读取 device、stream、
  task、context、connection、model、event type、`startNs/endNs`；将 `UINT32_MAX`
  context 规范化为空 subtask。
- **产物**：返回共享 `ProfilerTask`/等价内部模型的 DB parser。
- **验收**：
  - 时间从读取到计算全程使用整数纳秒，不经过 `float`；
  - direct 与 FFts context fixture 均能唯一解析；
  - task kind 规范化结果与现有 HCCL merge 契约一致。

### DBI-004 关联通信与 collective 元数据

- [x] **仓库**：HCCL `tools/diagnosis`
- **依赖**：DBI-003
- **工作**：通过 `globalTaskId` 关联 `COMMUNICATION_TASK_INFO`，再通过 `opId`
  关联 `COMMUNICATION_OP` 和 `STRING_IDS`，取得 `notifyId/srcRank/dstRank/op_name/group_name`。
  原始字符串保存在规范化 operation/task-metadata 映射中，不复制到每条 merged CSV。
- **验收**：
  - join 前后物理 TASK 行数不因一对多关系膨胀；
  - 每个 enrichment 字段有来源表和缺失策略；
  - `opId`、`connection_id` 明确只作 profile 内 join，不当作跨 rank identity。

### DBI-005 补齐 compute task 展示名称

- [x] **仓库**：HCCL `tools/diagnosis`
- **依赖**：DBI-003
- **工作**：对 `STARS_COMMON` 等通用 TASK 类型，通过
  `COMPUTE_TASK_INFO.globalTaskId -> STRING_IDS` 补充真实 compute name；保持
  `AI_CORE` unmatched-noise 策略独立于显示名称。
- **验收**：
  - 当前样本每卡一条 `aclnnInplaceNormal_DSARandomNormal_DSARandomNormal`
    能从 DB 完整恢复；
  - 通用 task type 与具体 event name 不混为同一字段；
  - HCCL task kind 不受 compute-name enrichment 影响。

### DBI-006 实现 PROF 目录发现与输入边界校验

- [x] **仓库**：HCCL `tools/diagnosis`
- **依赖**：DBI-003
- **工作**：从输入目录递归发现每个 `PROF_*` 的 consolidated DB，在输入边界填充
  `node_id`，使用 DB 内 device/rank map 校验每个 profile 的 device 身份和重复采集。
- **验收**：
  - 单文件、单 PROF、多 PROF 和多节点目录分别有测试；
  - 同一 profile 多个候选主 DB、重复 device 或无法识别 device 时明确失败；
  - 不从 user rank 推断 device id。

### DBI-007 将 DB parser 接入 merge 并中性化命名

- [x] **仓库**：HCCL `tools/diagnosis`
- **依赖**：DBI-004、DBI-005、DBI-006
- **工作**：
  - 增加 `--msprof-db/--msprof-db-dir` 或统一 `--msprof-dir` 入口；
  - merge 只消费共享物理 task 模型，不直接依赖 SQLite row；
  - 将 `json_task_id`、`json_ffts_parent_ctx`、`json_ffts_ctx_kind_mismatches`
    改为 source-neutral 名称。
- **验收**：
  - merge/validate/visualize 不需要知道 profiler 输入格式；
  - DB exact match 不输出 `json_*` 方法名；
  - CLI 对同时指定 DB/JSON、无输入和重复输入给出确定错误。

### DBI-008 建立 DB/JSON 等价性门禁

- [x] **仓库**：HCCL `tools/diagnosis`
- **依赖**：DBI-007
- **工作**：对 `test/out` 同时解析 DB 与旧 JSON，比较物理 task identity、task kind、
  context、connection、时间和最终 semantic merge。
- **验收**：
  - 两端均得到 44,008 个目标物理 task；
  - 28,502/28,502 semantic exact，FFts 14,405/14,405 parent+ctx exact；
  - compute name 经 DB enrichment 后一致；
  - 时间差只能来自旧 JSON 浮点舍入，DB 整数纳秒作为新基准；
  - 输出可审计 parity report。
- **结果**：当前 `test/out` 两条路径均为 44,008 execution，物理 identity 集合一致；
  DB 重放为 28,502/28,502 exact、14,405 FFts parent+ctx exact、duplicate/invalid 为 0。
  DB 纳秒时间使 connection/time heuristic Notify 边由旧输出 3,016 变为 5,094，
  证明该推断不具备输入精度稳定性；其删除仍由 DEP-008 独立完成。

### DBI-009 建立 DB 离线开销门禁

- [x] **仓库**：测试目录
- **依赖**：DBI-007
- **工作**：固定记录相同采集的输入体积、解析 wall time、峰值内存和 task/s，
  分别测基础 TASK 查询与带 communication/compute enrichment 的完整查询。
- **当前参考**：8 卡样本 JSON 88.67 MiB、4.32 s、53.56 MiB；consolidated DB
  16.40 MiB、0.67 s、24.86 MiB。
- **验收**：
  - 基准脚本可重复运行并输出 CSV；
  - DB 路径不得比当前 JSON 路径更慢或占用更多峰值内存；
  - 报告区分设备采集开销、JSON 导出开销和离线解析开销。
- **结果**：新增 `test/measure_msprof_db_parse.py`；完整 dataclass/enrichment 路径在
  tracemalloc 门禁下中位 1.284 s、峰值中位 31.68 MB，仍显著低于旧 JSON 路径。

### DBI-010 切换默认脚本和文档到 DB

- [x] **仓库**：HCCL `tools/diagnosis`、测试目录
- **依赖**：DBI-008、DBI-009
- **工作**：更新 README、`spec.md`、功能测试 wrapper 和命令示例，使 DB 成为默认
  profiler 输入；JSON 参数进入显式 deprecated 状态。
- **验收**：
  - 新用户只需提供 `PROF_*` 或其父目录；
  - 完整 merge/validate/visualize 流程不生成也不读取 Chrome-trace JSON；
  - 文档不再把 JSON 描述为唯一事实源。

### DBI-011 删除 JSON 生产入口

- [x] **仓库**：HCCL `tools/diagnosis`、测试目录
- **依赖**：DBI-010
- **工作**：DB golden 和环境合同确认后已删除 `parse_msprof_json.py`、JSON CLI、
  JSON flow 扫描及过时 JSON-only 审查文档；测试改用临时 SQLite fixture。
- **验收**：
  - 仓库生产 CLI 不接受 `msprof_*.json`；
  - 所有测试只凭 plog + DB 通过；
  - 不再维护 DB/JSON 双实现分支。

## 10. M4：单机精确依赖图

### DEP-001 定义双层依赖图合同

- [ ] **仓库**：HCCL `tools/diagnosis` 文档
- **依赖**：无
- **工作**：定义保真 execution graph 与折叠 resource graph；固化 node/edge identity、
  `observed/semantic/inferred` 证据、歧义表示、控制节点收缩和边权语义。
- **产物**：`spec.md` 图模型、字段表和 direct/FFts/Notify 示例。
- **验收**：
  - execution graph 保留 Notify 物理节点；
  - resource graph 只折叠控制节点，不丢失其 ID、时间和证据；
  - “时间最近”不能单独产生 exact/observed 因果边。

### DEP-002 建立稳定 operation 与 execution identity

- [ ] **仓库**：HCCL `tools/diagnosis`
- **依赖**：DEP-001、DBI-004、DBI-007、COR-005
- **工作**：使用 DB operation 映射为 task 补充 collective scope；execution node ID
  由稳定身份键生成，不再使用 CSV 行号 `p{index}`。验证 `group_name/op_name`
  跨 rank 一致性，歧义时不提升置信度。
- **验收**：
  - 重排 merged CSV 不改变 node ID；
  - 同一物理 execution 只有一个 node；
  - `opId/connection_id` 的跨 rank 数值差异不改变 operation 归属。

### DEP-003 隔离 direct 物理 stream 顺序

- [ ] **仓库**：HCCL `tools/diagnosis`
- **依赖**：DEP-001、DEP-002
- **工作**：只对非 FFts execution 按 `(node, device, physical_stream)` 和明确执行序
  生成 direct stream-order edge，不与 FFts parent 内部 ctx 共用构造器。
- **验收**：
  - direct edge 不跨 device、stream 或 operation 误连；
  - 重复时间戳有稳定 tie-break 和歧义检查；
  - 单元测试证明 FFts row 不进入 direct builder。

### DEP-004 使用逻辑 stream 重建 FFts 顺序

- [ ] **仓库**：HCCL `tools/diagnosis`
- **依赖**：DEP-001、DEP-002
- **工作**：按 `(node, device, op_instance, graph_instance, semantic_stream_id)` 分组，
  以 `ffts_ctx_id`/graph 声明序生成同逻辑 stream 边；禁止按 FFts parent 的物理 stream
  串接不同逻辑 stream。
- **验收**：
  - 当前 335 个 FFts parent 中两个逻辑 stream 被分别处理；
  - 13,735 组逻辑 stream 相邻关系无时间重叠；
  - 现有 2,352 条跨逻辑 stream 的重叠伪顺序边不再生成；
  - 缺 graph/ctx 身份时输出 incomplete，不退回物理 parent adjacency。

### DEP-005 定义 Notify 同步 relation identity

- [ ] **仓库**：跨仓设计文档
- **依赖**：DEP-001、DBI-004
- **工作**：定义角色规范化后的 relation：
  `(comm/op instance, producer_rank, consumer_rank, notify_id, phase, step, slice,
  signal_kind, graph/protocol sequence)`；endpoint device 属于节点，不进入共享 pair identity。
- **产物**：`sync_relation_id`、record/wait role、证据集合和 ambiguity schema。
- **验收**：
  - 同一 relation 的 record/wait 得到相同规范化键；
  - Notify 资源复用不会跨 invocation/graph/协议串边；
  - relation key 不依赖全局时钟或最近时间。

### DEP-006 精确配对 FFts Notify

- [ ] **仓库**：HCCL `tools/diagnosis`
- **依赖**：DEP-004、DEP-005
- **工作**：利用 operation、graph instance、规范化 rank/协议坐标和 notify id，
  仅对唯一 record/wait 组生成 observed relation；缺边和多对多组输出 ambiguity artifact。
- **验收**：
  - 当前 ring FFts RS 候选中 4,676 组一对一关系生成 observed 边；
  - 28 个单边缺失组被明确报告；
  - 不通过排序 zip 或时间最近补齐缺失关系。

### DEP-007 为未决 direct Notify 输出同步 token

- [ ] **仓库**：HCOMM
- **依赖**：DEP-005、ID-004
- **工作**：在无法由现有 operation/graph 坐标唯一配对的 direct/复用场景，为一次逻辑
  同步生成稳定 `dependency_token` 或 `protocol_seq`，并让 producer record 与 consumer wait
  输出同一身份。
- **验收**：
  - 同一 token 在约定 scope 内恰有一个 producer 和一个 consumer；
  - retry、多 channel、双向并发和 wrap 行为有契约；
  - 关闭 trace 时不改变 Notify 执行语义；
  - 需要 HCOMM 构建和设备侧新采集验收。

### DEP-008 默认移除 connection/time Notify 推断

- [ ] **仓库**：HCCL `tools/diagnosis`
- **依赖**：DEP-005
- **工作**：从默认依赖图删除按 `connection_id` 和最近时间选择 record 的逻辑；
  如保留研究模式，必须显式 opt-in，边标记 `heuristic` 且不得进入关键路径或 exact 门禁。
- **验收**：
  - 默认输出中 `notify_sync_inferred(connection/time)=0`；
  - ambiguity 不会被静默转换为边；
  - JSON 舍入输入的 3,016 条和 DB 纳秒输入的 5,094 条推断边均从默认图消失，
    差异报告说明时间精度不应改变 causal identity。

### DEP-009 消费显式同步 token

- [ ] **仓库**：HCCL `tools/diagnosis`
- **依赖**：DEP-005、DEP-007
- **工作**：解析生产端 sync identity，构建 direct 和跨 graph 的 exact record/wait relation，
  并验证 notify/rank/phase 等辅助字段。
- **验收**：
  - 配对只依赖 identity，不依赖执行时间；
  - 重复 token、单边 token 和字段冲突分别使质量门禁失败；
  - 与 DEP-006 使用同一 relation artifact，不另建 direct 专用模型。

### DEP-010 合并 Notify 与 peer semantic 证据

- [ ] **仓库**：HCCL `tools/diagnosis`
- **依赖**：DEP-005、DEP-006、DEP-009
- **工作**：将 `tx/rx_ack`、`tx/rx_data_signal` 与相同同步 relation 合并为一条边及多份
  evidence；`tx_payload -> rx_payload_copy/reduce` 保持独立数据边。
- **验收**：
  - 同一 ACK/data-signal 不同时出现 Notify 边和 peer-signal 重复边；
  - Notify 与 semantic identity 冲突进入 validation report；
  - payload 边不会被控制边折叠或去重。

### DEP-011 产出保真 execution graph artifact

- [ ] **仓库**：HCCL `tools/diagnosis`
- **依赖**：DEP-003、DEP-004、DEP-006、DEP-008、DEP-009、DEP-010
- **工作**：输出稳定的 execution nodes/edges CSV，保留所有资源 task、Notify record/wait、
  stream order、payload 和同步证据。
- **验收**：
  - 每条边的两个 endpoint 都存在且可追溯到 profiler execution；
  - 无重复 edge identity；
  - 环、孤立控制节点、缺失 endpoint 分别统计；
  - artifact 不依赖可视化布局。

### DEP-012 将控制节点折叠为 resource graph

- [ ] **仓库**：HCCL `tools/diagnosis`
- **依赖**：DEP-011
- **工作**：沿 execution graph 可达关系，把
  `resource -> record -> wait -> resource` 收缩为资源同步边；不得按时间最近选择端点。
  无资源前驱/后继时使用显式 boundary source/sink。
- **验收**：
  - Notify 节点不出现在 resource node 表，但完整保存在 edge provenance；
  - 分支、控制链和一侧缺失 fixture 不丢关系；
  - 从 resource edge 可反查原始 record/wait execution。

### DEP-013 定义并计算同步边时间指标

- [ ] **仓库**：HCCL `tools/diagnosis`
- **依赖**：DEP-012
- **工作**：基于整数纳秒分别输出 `wait_span_ns`、`remote_block_ns`、
  `post_signal_ns`、`handoff_gap_ns`；不再用一个含义不明的 `weight` 代替所有指标。
- **验收**：
  - signal 早于 wait、晚于 wait、跨越 wait 和缺时间分别有测试；
  - 关键路径选择的默认权重有明确定义；
  - 未完成时钟校准的跨节点 relation 不计算可比较边权。

### DEP-014 支持 execution/resource 双视图

- [ ] **仓库**：HCCL `tools/diagnosis`
- **依赖**：DEP-011、DEP-012、DEP-013
- **工作**：让 SVG/HTML 只消费共享 graph artifact，并提供 `execution` 与 `resource`
  视图选择；布局代码不得重新推断依赖。
- **验收**：
  - execution 视图可查看 Notify 物理 task；
  - resource 视图默认隐藏控制节点并展示同步边指标和 evidence；
  - 两种视图共享稳定 node/relation ID。

### DEP-015 建立依赖图正确性门禁

- [ ] **仓库**：HCCL `tools/diagnosis`
- **依赖**：DBI-008、DEP-014
- **工作**：固定输出 direct/FFts stream edge、Notify exact/ambiguous、peer evidence fusion、
  payload、环、boundary 和伪边删除统计。
- **验收**：
  - 当前样本不再出现 FFts 跨逻辑 stream 的 2,352 条重叠伪顺序边；
  - 默认 connection/time inferred 边为 0；
  - exact/observed 边必须有可枚举 identity/evidence；
  - golden 统计变化需要显式更新理由。

## 11. M5：覆盖矩阵与独立扩展

### COV-001 建立覆盖矩阵

- [ ] **仓库**：HCCL 文档/测试
- **依赖**：无
- **工作**：按 device、algorithm、phase、transport、primitive、task kind 列出
  supported/partial/unsupported。
- **验收**：每个 supported 单元都有 fixture 或设备测试 ID。

### COV-002 覆盖非 concurrent-direct ring

- [ ] **仓库**：HCOMM
- **依赖**：COV-001、ID-003
- **工作**：只覆盖标准 ring RS/AG 模板，不同时修改 mesh/NHR。
- **验收**：标准 ring golden 中 phase/step/peer 完整且无测试强制算法。

### COV-003 覆盖 mesh

- [ ] **仓库**：HCOMM
- **依赖**：COV-001、ID-003
- **工作**：为 910B 默认 mesh 路径增加独立 scope。
- **验收**：恢复默认算法选择后仍能产生可用语义。

### COV-004 覆盖 hierarchical

- [ ] **仓库**：HCOMM
- **依赖**：COV-001、ID-003
- **工作**：分别标注 intra-node 与 inter-node phase，不同时实现时钟校准。
- **验收**：层级和 peer 域可区分，不能把 server rank 当 user rank。

### COV-005 覆盖 NHR

- [ ] **仓库**：HCOMM
- **依赖**：COV-001、ID-003
- **工作**：只增加 NHR producer 语义和 protocol identity，不在本任务构图。
- **验收**：每个 NHR hop 有显式 src/dst/protocol sequence。

### COV-006 覆盖 RDMA/RoCE 特有分支

- [ ] **仓库**：HCOMM
- **依赖**：COV-001、ID-003
- **工作**：验证 `Tx/RxWithReduce`、standard RoCE 和 data-received ACK 的实际 task 映射。
- **验收**：RDMA task kind 与 DB physical TASK/communication metadata 兼容，无 SDMA 语义误标。

### COV-007 覆盖 AIV

- [ ] **仓库**：HCOMM
- **依赖**：CTX-004、COV-001、ID-003
- **工作**：为已确认可关联的 AIV kernel 建立 phase/event；不能关联的保持 profiler-only。
- **验收**：不把父 AI_CORE 伪装成已精确匹配的内部 subtask。

## 12. M6：多节点与高级诊断

### MNT-001 定义跨节点 protocol sequence

- [ ] **仓库**：跨仓设计文档
- **依赖**：ID-001、DEP-005
- **工作**：定义 `(op_instance_id, src_rank, dst_rank, protocol_kind, protocol_seq)`。
- **验收**：重传、双向并发和多 channel 不产生歧义。

### MNT-002 HCOMM 输出 protocol identity

- [ ] **仓库**：HCOMM
- **依赖**：MNT-001、ID-004
- **工作**：在 tx/rx signal/payload 语义中写入 protocol kind/sequence。
- **验收**：两端可只凭 identity 配对，不依赖时间最近或 ring 邻居公式。

### MNT-003 消费端生成 wait-relation artifact

- [ ] **仓库**：HCCL `tools/diagnosis`
- **依赖**：DEP-001、DEP-005、MNT-002、COR-005
- **工作**：输出独立 wait interval CSV，包含 waiter、producer、start/stop、evidence。
- **验收**：每条关系可追溯到 notify 或 protocol identity。

### MNT-004 采集时钟锚点

- [ ] **仓库**：HCOMM/采集工具
- **依赖**：无
- **工作**：定义并采集 Host 与 device、节点间可比的时钟锚点及误差。
- **验收**：每个节点输出至少两个锚点和测量误差字段。

### MNT-005 实现时钟校准 artifact

- [ ] **仓库**：HCCL `tools/diagnosis`
- **依赖**：MNT-004
- **工作**：只生成 offset/drift/error CSV，不在本任务修改依赖图。
- **验收**：校准前后误差有统计；缺锚点时明确失败而非默认为 0。

### MNT-006 构建多节点精确依赖边

- [ ] **仓库**：HCCL `tools/diagnosis`
- **依赖**：DEP-001、MNT-002、MNT-005
- **工作**：使用 protocol identity 建边，时间仅用于一致性检查。
- **验收**：跨节点边 evidence 为 observed/semantic，不使用“最近任务”作为唯一依据。

### MNT-007 实现 critical path

- [ ] **仓库**：HCCL `tools/diagnosis`
- **依赖**：DEP-012、DEP-013、MNT-003、MNT-006
- **工作**：在有向无环执行/等待图上计算 critical path；环单独报告。
- **验收**：输出路径、累计时间、等待占比和每条边证据。

### MNT-008 实现 NHR 依赖视图

- [ ] **仓库**：HCCL `tools/diagnosis`
- **依赖**：COV-005、DEP-014、MNT-006
- **工作**：消费通用 node/edge artifact 渲染 NHR，不复制一套 merge 逻辑。
- **验收**：NHR 视图只负责筛选/布局，身份和边来自共享模型。

## 13. 端到端质量门禁

### E2E-001 HCOMM 构建

- [ ] **仓库**：HCOMM
- **依赖**：HYG-001、HYG-002
- **命令**：`bash build.sh --pkg`
- **验收**：全量构建成功；新增源文件由目标 CMake 正确链接；无 unused parameter 等新增告警。

### E2E-002 开关关闭回归

- [ ] **仓库**：跨仓测试
- **依赖**：E2E-001
- **工作**：用相同 workload 对比 8.5.0 与当前代码的功能结果和算法选择。
- **验收**：`HCCL_STEP_TRACE=0` 时无 `[HcclTaskSemantic]`，collective 结果一致。

### E2E-003 single-ring direct golden trace

- [x] **仓库**：跨仓测试
- **依赖**：HYG-003、E2E-001
- **工作**：固定 rank size、数据量、transport，保存 plog、msprof profiler 数据、summary。
- **结果**：`test/out` 共 28,502 条 semantic，100% exact；其中 14,405 条 FFts
  全部 parent+ctx exact；335 条 graph correlation；duplicate/invalid 为 0。
- **验收**：
  - `semantic_total > 0`；
  - `ffts_semantic_total > 0`、`graph_correlation_total > 0`；
  - duplicate semantic/profiler execution/graph correlation key 均为 0；
  - `ffts_semantic_missing_correlation == 0`、
    `ffts_ctx_kind_mismatches == 0`；
  - `ffts_parent_ctx_matches > 0`，exact match 达到约定值；
  - 不存在 heuristic 匹配入口。

### E2E-004 默认 mesh golden trace

- [ ] **仓库**：跨仓测试
- **依赖**：COV-003、E2E-001
- **工作**：不使用测试强制参数运行 910B 默认路径。
- **验收**：算法选择仍为默认 mesh，且 mesh 语义覆盖达到矩阵目标。

### E2E-005 生产/消费 schema 合同测试

- [ ] **仓库**：HCCL `tools/diagnosis`
- **依赖**：LOG-002
- **工作**：把 HCOMM 日志格式样例作为 parser fixture，按版本校验所有字段。
- **验收**：字段漏写、改名、类型变化会使测试失败。

### E2E-006 开销基准

- [ ] **仓库**：测试目录
- **依赖**：E2E-001、SEQ-002
- **工作**：分别测 baseline、trace off、trace on；覆盖小消息和大消息。
- **验收**：报告 wall time、吞吐、日志量、内存增量和置信区间；阈值由发布要求确定。

### E2E-007 诊断质量报告

- [ ] **仓库**：HCCL `tools/diagnosis`
- **依赖**：E2E-003；完成 M2 后重跑
- **工作**：固定输出 exact rate、kind mismatch、unmatched semantic、
  profiler-only 和 duplicate execution key。
- **验收**：95% 门禁只接受 exact，分子分母有明确定义。

### E2E-008 DB 输入与依赖图 golden replay

- [ ] **仓库**：HCCL `tools/diagnosis`、测试目录
- **依赖**：DBI-010、DEP-015
- **工作**：只使用 `test/out` 的 plog 和 consolidated DB 重放 merge、validate、
  execution/resource graph 与可视化，不读取 `msprof_*.json`。
- **验收**：
  - 44,008 个目标 profiler task，28,502/28,502 semantic exact；
  - FFts 14,405/14,405 parent+ctx exact，duplicate/invalid 为 0；
  - FFts 跨逻辑 stream 伪顺序边和默认 connection/time Notify 边均为 0；
  - execution/resource artifact、SVG 和 HTML 均可生成；
  - 单独保存 DB 解析耗时、峰值内存和依赖边分类统计。

## 14. 推荐执行顺序

第一批先关闭发布阻断和基础语义丢失：

```text
schema v3 Ring 短采集
  -> HYG-001 + HYG-002
  -> E2E-004 默认 mesh 回归
CTX-001 + SEQ-001
  -> CTX-002
  -> TST-001..TST-005
  -> E2E-001/E2E-002
```

DB 主输入迁移可直接使用现有 `test/out`，不依赖新的 HCOMM 设备采集：

```text
DBI-001 -> DBI-002 -> DBI-003
DBI-003 -> DBI-004 + DBI-005 + DBI-006
DBI-004 + DBI-005 + DBI-006 -> DBI-007
DBI-007 -> DBI-008 + DBI-009
DBI-008 + DBI-009 -> DBI-010 -> DBI-011
```

单机依赖图先完成纯消费端止错和 FFts 精确关系，再接生产端 token：

```text
DEP-001
  -> DEP-002
  -> DEP-003 + DEP-004
DEP-001 + DBI-004 -> DEP-005
DEP-004 + DEP-005 -> DEP-006
DEP-005 -> DEP-008

ID-001..ID-005
DEP-005 + ID-004 -> DEP-007 -> DEP-009
DEP-006 + DEP-009 -> DEP-010

DEP-003 + DEP-004 + DEP-006 + DEP-008 + DEP-009 + DEP-010
  -> DEP-011 -> DEP-012 -> DEP-013 -> DEP-014 -> DEP-015
DBI-010 + DEP-015 -> E2E-008
```

其中 DEP-001～DEP-006、DEP-008 和 DBI 全部可以用现有数据在本地完成；DEP-007/DEP-009
需要 HCOMM 改动、新构建和设备侧采集。

随后修复语义质量并扩覆盖：

```text
SEM-001 -> SEM-002
SEM-003 -> SEM-004 + SEM-005
COV-001 -> COV-002..COV-007
```

多节点工作复用单机 relation/resource graph，不再复制依赖构造逻辑：

```text
DEP-005 + ID-001 -> MNT-001 -> MNT-002
MNT-004 -> MNT-005
MNT-002 + MNT-005 -> MNT-006
DEP-012 + DEP-013 + MNT-003 + MNT-006 -> MNT-007
```
