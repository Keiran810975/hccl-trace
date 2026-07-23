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
| M3 覆盖扩展 | 逐算法、逐 transport 增加可审计覆盖 | COV 任务按目标平台完成 |
| M4 多节点因果诊断 | 形成 protocol、wait、clock 和 critical path artifact | MNT 任务完成 |

## 3. M0：发布卫生

### HYG-001 撤回默认拓扑强制

- [!] **仓库**：HCOMM
- **文件**：`src/algorithm/impl/alg_configurator.cc`
- **依赖**：HYG-003 或目标 Ring 功能验证完成
- **阻塞原因**：当前 910B module 的 `SetAlgoLevel0Module()` 会明确忽略显式
  `HCCL_ALGO level0:ring`。若现在恢复默认 `ALG_LEVEL0_NP_MESH`，实际设备 workload
  将无法稳定进入待验证的 single-ring 插桩路径。
- **临时决定**：保留 `[TEST PATCH]`，继续把全 HCCS 910B 默认拓扑强制为
  `ALG_LEVEL0_NP_SINGLE_RING`，仅用于完成当前 Ring 功能验证。
- **解阻条件**：Ring 功能验证完成，或出现无需修改 HCOMM 源码即可选择同一路径的受支持控制面。
- **产物**：单文件功能提交。
- **验收**：
  - 与 `../hcomm` 的该函数行为一致；
  - trace 开关不影响算法 level 0 默认选择；
  - 相关算法选择测试通过。

### HYG-002 撤回 operator 的 ring executor 强制

- [!] **仓库**：HCOMM
- **文件**：`src/algorithm/impl/operator/all_reduce_operator.cc`
- **依赖**：HYG-003 或目标 Ring 功能验证完成
- **阻塞原因**：8.5.0 的 910B 多卡选择树在 ring topology 下仍会落入
  `AllReduceComm`；只保留 topology 强制不足以进入
  `AllReduceRingFor91093Executor` 和 concurrent-direct RS/AG 模板。
- **临时决定**：保留多卡 `isRingTopo` 的 `[TEST PATCH]` executor 选择分支。
- **解阻条件**：与 HYG-001 相同；移除时必须同时恢复 topology 和 operator 两处默认行为。
- **产物**：单文件功能提交。
- **验收**：
  - 生产选择树恢复 8.5.0 规则；
  - trace 开关开/关得到相同 executor 选择。

### HYG-003 提供测试侧 ring 路径选择

- [!] **仓库**：测试目录；如确需 HCOMM 测试接口，单独评审
- **依赖**：无；若本任务找到可行选择方案，再解阻 HYG-001、HYG-002
- **调查结论**：
  - `HCCL_ALGO` 能解析 `level0:ring`；
  - 但 910B module 的 `SetAlgoLevel0Module()` 只接受 `default/NA/null`，对 ring
    打印 warning 后仍走默认 topology；
  - 即使构造出 ring topology，8.5.0 多卡 operator 也不会选择目标 executor；
  - 现有 910_93 ST fixture 或标卡 topology 不能证明真实 910B module workload
    会走同一路径。
- **阻塞原因**：目前没有发现“不修改 HCOMM 源码”且能在目标 910B module 上稳定选择
  `AllReduceRingFor91093Executor` 的方式。新增环境变量或扩展 `HCCL_ALGO` 支持本身都属于
  HCOMM 产品源码变更，不满足当前约束。
- **临时决定**：不向测试脚本加入会被生产端忽略的 `--force-ring`，继续使用
  HYG-001/HYG-002 的临时源码强制完成 Ring 功能验证。
- **解阻条件**：满足以下任一项：
  1. Ring 功能验证完成，可以直接撤回两处强制；
  2. HCOMM 正式支持 910B module 的显式 level-0 ring 配置；
  3. 设备测试框架提供可证明等价的 topology/executor 注入接口。
- **产物**：阻塞调查结论；解阻后再实现可复用的 ring direct workload 启动方式。
- **验收**：
  - 测试能稳定进入 RS/AG concurrent-direct；
  - 不设置测试参数时完全保持默认算法行为；
  - 测试日志能证明实际 executor/template。

### HYG-004 分离无功能格式改动

- [x] **仓库**：HCOMM
- **文件**：`src/common/debug/profiling/profiler_manager_impl.cc`
- **依赖**：无
- **工作**：已将该文件中的纯格式化改动恢复至 HCOMM 当前 HEAD，不纳入 trace 功能提交。
- **验收**：`git diff HEAD -- src/common/debug/profiling/profiler_manager_impl.cc` 无输出，trace 功能 diff 不再包含该无功能文件。

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

- [ ] **仓库**：HCOMM
- **依赖**：无
- **工作**：定义字段新增、重命名、默认值和兼容期规则；明确 schema v1 的冻结字段。
- **验收**：生产端和 `parse_plog.py` 共享一份字段兼容矩阵。

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
- **工作**：对 record/wait 分别验证 notify id、stage、remote rank、ctx id。
- **验收**：非 notify task 不被误当作同步事件；record/wait 字段与 TaskParaNotify 一致。

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
  - v1 fixture 仍可解析；
  - 新 fixture 保留实例 ID；
  - 单元测试覆盖缺失/非法值。

## 7. M2：FFts parent/subtask 精确关联

### COR-001 定位 graph finalize 映射钩子

- [x] **仓库**：HCOMM 调查
- **依赖**：SEQ-001、ID-001
- **工作**：只做只读调用链调查，找出 semantic submission 到
  `(parent_task_id, subtask_id, physical_stream_id, connection_id)` 的最小稳定挂点。
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
- **工作**：已输出 semantic schema v2 字段和 version 1
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
- **工作**：已按 parent correlation + `ffts_ctx_id` 精确认领 JSON subtask，输出独立
  `match_method` 和 `exact` confidence。
- **验收**：同一 JSON execution 不被两个 semantic 认领；kind mismatch 单独计数。

### COR-006 删除 direct-ring 固定偏移

- [x] **仓库**：HCCL `tools/diagnosis`
- **依赖**：COR-005
- **工作**：固定偏移分支默认关闭，仅在显式
  `--allow-legacy-composite-heuristic` 时用于旧数据调查。
- **验收**：新采集无需固定偏移；旧数据若继续支持，必须显式 opt-in 并标记 heuristic。

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

### SEM-007 notify observed edge golden 测试

- [ ] **仓库**：HCCL `tools/diagnosis`
- **依赖**：TST-005
- **工作**：用含真实 notify id 的新 plog/JSON fixture 验证 record -> wait。
- **验收**：相同 device/id、跨 stream 的唯一 record/wait 生成 observed 边；
  数量不等或候选不唯一时拒绝强配。

## 9. M3：覆盖矩阵与独立扩展

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
- **验收**：RDMA task kind 与 JSON hardware event 兼容，无 SDMA 语义误标。

### COV-007 覆盖 AIV

- [ ] **仓库**：HCOMM
- **依赖**：CTX-004、COV-001、ID-003
- **工作**：为已确认可关联的 AIV kernel 建立 phase/event；不能关联的保持 profiler-only。
- **验收**：不把父 AI_CORE 伪装成已精确匹配的内部 subtask。

## 10. M4：多节点与高级诊断

### MNT-001 定义跨节点 protocol sequence

- [ ] **仓库**：跨仓设计文档
- **依赖**：ID-001
- **工作**：定义 `(op_instance_id, src_rank, dst_rank, protocol_kind, protocol_seq)`。
- **验收**：重传、双向并发和多 channel 不产生歧义。

### MNT-002 HCOMM 输出 protocol identity

- [ ] **仓库**：HCOMM
- **依赖**：MNT-001、ID-004
- **工作**：在 tx/rx signal/payload 语义中写入 protocol kind/sequence。
- **验收**：两端可只凭 identity 配对，不依赖时间最近或 ring 邻居公式。

### MNT-003 消费端生成 wait-relation artifact

- [ ] **仓库**：HCCL `tools/diagnosis`
- **依赖**：MNT-002、COR-005
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
- **依赖**：MNT-002、MNT-005
- **工作**：使用 protocol identity 建边，时间仅用于一致性检查。
- **验收**：跨节点边 evidence 为 observed/semantic，不使用“最近任务”作为唯一依据。

### MNT-007 实现 critical path

- [ ] **仓库**：HCCL `tools/diagnosis`
- **依赖**：MNT-003、MNT-006
- **工作**：在有向无环执行/等待图上计算 critical path；环单独报告。
- **验收**：输出路径、累计时间、等待占比和每条边证据。

### MNT-008 实现 NHR 依赖视图

- [ ] **仓库**：HCCL `tools/diagnosis`
- **依赖**：COV-005、MNT-006
- **工作**：消费通用 node/edge artifact 渲染 NHR，不复制一套 merge 逻辑。
- **验收**：NHR 视图只负责筛选/布局，身份和边来自共享模型。

## 11. 端到端质量门禁

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

- [ ] **仓库**：跨仓测试
- **依赖**：HYG-003、E2E-001
- **工作**：固定 rank size、数据量、transport，保存 plog、msprof JSON、summary。
- **验收**：
  - `semantic_total > 0`；
  - `ffts_semantic_total > 0`、`graph_correlation_total > 0`；
  - duplicate semantic/profiler execution/graph correlation key 均为 0；
  - `ffts_semantic_missing_correlation == 0`、
    `json_ffts_ctx_kind_mismatches == 0`；
  - `json_ffts_parent_ctx_matches > 0`，exact match 达到约定值；
  - heuristic 与 exact 分开报告，heuristic 不计入质量门禁。

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
- **工作**：固定输出 exact rate、heuristic count、kind mismatch、unmatched semantic、
  profiler-only 和 duplicate execution key。
- **验收**：总 match rate 不能掩盖 heuristic；95% 门禁的分子分母有明确定义。

## 12. 推荐执行顺序

第一批先关闭发布阻断和基础语义丢失：

```text
HYG-001 + HYG-002
  -> HYG-003
CTX-001 + SEQ-001
  -> CTX-002
  -> TST-001..TST-005
  -> E2E-001..E2E-003
```

第二批建立精确身份，替换启发式：

```text
LOG-002
  -> ID-001..ID-005
COR-001
  -> COR-002
  -> COR-003 + COR-004
  -> COR-005
  -> COR-006
```

第三批修复语义质量并扩覆盖：

```text
SEM-001 -> SEM-002
SEM-003 -> SEM-004 + SEM-005
COV-001 -> COV-002..COV-007
```

多节点工作在 identity 稳定后进行：

```text
MNT-001 -> MNT-002
MNT-004 -> MNT-005
MNT-002 + MNT-005 -> MNT-006
MNT-003 + MNT-006 -> MNT-007
```
