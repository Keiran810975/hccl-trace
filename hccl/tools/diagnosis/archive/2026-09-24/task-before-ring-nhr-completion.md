> 历史快照：Ring/NHR闭环完成前的活动计划；不作为当前待办。

# HCCL Step Trace 任务清单

更新：2026-09-24。目标是在当前 HCCL/HCOMM 8.5 基线上完成**多机依赖感知诊断与异常验证**。
当前实现、分支和验证结果见 [阶段归档](../../arch-94a1ab31c3ee.md)；实现合同见 [spec.md](../../spec.md)。
旧任务编号和拆分保存在 [原任务快照](../../archive/2026-09-15/task.md)，不再作为并行活动计划。
补查远端后的实现与审批状态见 [分支调查](../../branch-review-2026-09-15.md)；不得只凭旧本地主线安排重复开发。

## 1. 当前起点

- 已验证：8 卡 single-ring concurrent-direct AllReduce RS/AG 的真实采集；DB 精确合并、
  direct/local/FFts Notify、execution/resource 图与 HTML/SVG。
- 已有样例：28,502 条 semantic 全部 exact，44,008 个 execution；62 项 Python 单测通过。
  这是已有单机样例的结论，不代表当前生产端已重新构建采集或多机已支持。
- 已知边界：28 个 FFts single、8 个 local Notify resource boundary；保留解释，不补猜测边。
- 已集成：远端 master 的提前返回语义修复、覆盖矩阵，以及 standard Ring/NHR/Mesh 插桩和 Mesh normal Tx/Rx 修复。
  用户确认 NHR/Mesh/standard Ring 已测试；RHD 已弃用。上级目录留存
  NHR/Mesh/Ring resource HTML，已核对并记录其覆盖边界，未提供的测试版本信息保持未回填。
- 当前缺口：分支成果集成、Ring 测试强制、resource 证据增强、多机输入与关系、自动诊断、异常测试。

### 分支集成状态

| 对象 | 当前动作 |
|---|---|
| `origin/master@d0d2904` | 已同步，合并提交 `2f26033` |
| `feat-standard-ring@7dadcea` | 已合入，合并提交 `360d650` |
| `feat-NHR@29ab3cd` | 已合入，合并提交 `638e94c` |
| `feat-mesh@d870111` + 修复 `286ef99` | 已获批准，随 `f30a90a` 快进合入；待构建和针对性设备验证 |
| `feat-RHD@e3e368f` | 用户决定弃用；保留历史，不合入、不安排验证 |

本次已按批准顺序同步 master→standard Ring→NHR→修复后的 Mesh；文档冲突保留简洁计划和分支实施记录。
缺少原始 DB 不要求重跑完整矩阵，HTML 中未覆盖项继续保留。
语义配对的最终验证与 Git 无冲突是两个结论，不能互相替代。
设备测试按 [交接 prompt](../../../../../test/prompts/integrated-master-device-test.md) 执行并返回原始证据。

## 2. 实施约定

- 状态：`[ ]` 未开始，`[-]` 进行中，`[x]` 已完成，`[!]` 阻塞。
- 每项以一个可运行样例和明确结果收尾；完成后移入阶段归档。
- HCOMM 负责实际路径插桩，HCCL 负责关联和分析，`test/` 负责样例与运行记录。
- 先使用现有字段和 artifact；新字段必须有实际缺口、生产位置和消费位置。
- 单测只覆盖本项规则及失败模式；设备验收保留命令、环境、源码状态、原始输入和简短结果。
  已通过的无关检查不重复执行，不为所有未来算法预设完整矩阵。

## 3. 活动任务

### 当前优先目标：Ring/NHR 场景诊断闭环（2026-09-24）

分支 `codex/ring-nhr-diagnosis` 从现有工作区继承 AI_CPU 与耗时诊断改动。
固定目标为机器0/1各4 rank，物理8、10、12、14，32MiB FP32 AllReduce，
实际 `AllReduceRingFor91093Executor`、机内Single Ring、机间NHR。
用户要求持续自主推进；允许适度并发，但不干扰、终止或重置其他任务。

- [-] 查清并补齐128个控制Notify缺元数据及128个single：真实缺口是Host runtime
  order-launch未走HCCL TaskData、Device order-stream缺profiling和Host offset/Device resId不同身份域。
  只补诊断事实，不改传输/调度行为；新增事实必须带真实physical execution key和显式算子anchor。
- [ ] 最小等待分析：按operation/rank/phase汇总，Top Wait与上游证据路径、慢执行/上游等待/证据不足分类。
- [ ] 视图收尾：保持execution/resource/waits一致来源，突出payload、控制提交及操作区间，方便定位单次调用。
- [ ] 正常与受控异常真实双机验证，缺失/重复/时间平移离线回归，off/on数值及开销边界。
- [ ] 更新合同、说明及结果，下载校验、恢复验签并清理本轮远端产物。

此前样例证据：`test/out/ring-nhr-20260924/`。1,792/1,792 exact，288条跨机边，
机内RS/AG各3步，但完整图门禁尚未通过。以下广泛历史任务中与本场景无关的HOST身份、
FFts/AIV/双环覆盖暂缓；不能将它们列为本轮完成前提或声称本轮已覆盖。


### NEXT-001 收尾生产端单机问题

2026-09-24新增真实失败证据：HOST展开在可见物理8–15时，semantic设备号仍为逻辑0–7，
导致2,336条语义无法精确合并；改用物理0–7后同一部署8 rank Ring全部exact且图门禁通过。
需单独修正HOST设备身份采集，不在消费端按rank/偏移补配。证据见
[单机8卡说明](../../../../../test/out/single8-diagnosis-20260924/测试结果说明.md)。

- [ ] **位置**：HCOMM 算法选择、`task_profiling.cc`；`test/`。
- **工作**：撤回两处 Ring `[TEST PATCH]`；直接复用已集成的
  `ReportCapturedTaskSemantic()`，只补尚缺的捕获/提前返回回归，不重复修复。
  Ring 验证需要的路径选择留在明确的测试控制中，不改变生产默认算法。
- **完成**：HCOMM 自身构建通过；相关捕获/提前返回小测试通过；短设备运行确认 trace
  on/off 不改变算法选择，当前 schema 能关联真实 task。默认路径缺插桩时如实记录，
  只补下一步样例实际使用的路径。

### NEXT-002 修正派生边证据

- [ ] **位置**：HCCL `resource_dependency_graph.py`、模型/测试/规格。
- **工作**：resource 顺序与 Notify 收缩均取所有源边的最弱 confidence，消除 FFts/mixed
  order 被提升为 observed 的问题；同步调整 kind、必要的 graph schema 版本和读取端。
- **完成**：小图覆盖 direct、FFts、mixed 与 Notify 收缩；已存单机样例的纯证据修正不改变
  可达关系，边类型/ID 变化有说明。无需另建一套审计框架。

### NEXT-003 正常双机样例已完成

2026-09-24在机器0/1 NPU7（各物理14、15）完成最终候选off/on、4 rank各4次8MiB AllReduce。
数值全部正确，两机各256/256 semantic exact，重复和类型/Notify匹配冲突为0。
真实路径为single-ring direct + NHR/RoCE，显式operation绑定及物理设备映射有原始证据。
此前NHR全局rank问题及NPU7暴露的HAL局部设备号问题均已修正并实测。
完成记录见[AI_CPU支持记录](../../ai-cpu-support.md)，完整证据在`test/out/ai-cpu-support-20260924/`。
后续集中NEXT-004的完整图缺口，不再把正常双机语义采集列为待执行。

同日扩大至NPU4–7、16 rank：off/on数值通过，4,800/4,800 semantic exact、1,080条跨机边。
实际为AllReduceComm全rank NHR；RS/AG各4步。详见AI_CPU支持记录及16 rank本地报告。

### NEXT-004 打通多机依赖图

2026-09-24：4 rank生产分析已构建144条跨机边、16 rank为1,080条，均0未决跨机通道。
16 rank完整图因256个本地控制Notify缺operation/notify元数据失败，另有256个本地single。
2026-09-24消费端补齐同机RDMA构图：816个通道生成1,224条observed同步边，跨机1,080条不变，
两类RDMA通道均0未决；剩余256个本地控制incomplete和256个single仍保留。
后续调查控制元数据和512条无算法语义的RDMA门铃；不猜测补边或放宽门禁。
已完成的任务分类、同机RDMA和等待视图见[耗时与RDMA诊断记录](../../timing-rdma-diagnosis.md)。


- [-] **位置**：HCCL 输入组织、identity 与构图；仅缺事实时修改 HCOMM。
- **实现进度**：清单驱动的 run 隔离、显式 operation 绑定、Ibverbs RDMA Notify channel、
  双层 artifact 与节点本地时钟视图已实现，79 项离线单测通过。
  设计及限制见 [多机实现记录](../../multi-node-design.md)。重复 FFts occurrence 仍保留歧义；
  下一步用 NEXT-003 实际样例核实 rank 域、共享调用与 channel 字段，按失败证据收尾。
- **依赖**：NEXT-003。
- **工作**：消费同一次采集的节点清单，隔离不同 run，显式映射 rank/node/device，复用现有
  merge 和双层图。先核实 DB operation/Notify/channel 事实是否足以唯一配对；不足时再补
  最小的跨端共享协议序号或 token，不用进程内计数、同名字符串或时间邻近冒充共享身份。
- **完成**：双机正常样例的目标跨节点关系可回查两端记录，operation 不串组；缺端和
  多候选有原因且不部分强配；单机回归保持。此阶段允许时钟未校准，只输出依赖拓扑和
  各端本地 duration，不把时间校准作为建拓扑的前置条件。

### NEXT-005 最小等待诊断

2026-09-24已交付全部Wait的CSV、按本地时长排序的HTML、operation区间和上游/对端跳转；
未配对Wait也保留。自动按operation/rank/phase汇总、根因分类和异常定位尚未完成。

- [-] **位置**：HCCL 分析脚本，复用 resource/execution artifact。
- **依赖**：NEXT-002；单机可先做，双机接入依赖 NEXT-004。
- **工作**：输出 Top Wait，按 operation/rank/phase 汇总等待与资源耗时，沿现有关系列出
  直接上游任务和对端，保留 relation/record/wait/resource ID。先交付 CSV，复用现有 HTML
  查看证据；不重复 merge、构边或另建图模型。
- **完成**：能从一项长等待回查到具体 task/step/peer；区分自身执行慢、等待上游与证据不足。
  多机未校准时只用本地时长排序，不输出跨时钟差值；不把相关长等待直接宣称为确定根因。

### NEXT-006 构造异常样例并验证定位

- [ ] **位置**：`test/`，必要时 HCOMM 独立测试开关；HCCL 回归 fixture。
- **依赖**：离线样例可提前准备；设备诊断验收依赖 NEXT-004、NEXT-005。
- **工作/预期**：

  | 样例 | 预期结果 |
  |---|---|
  | 正常对照 | 无注入目标，保留正常等待分布 |
  | 指定 rank 的指定阶段延迟 | 诊断指向目标 rank/阶段及其下游等待链 |
  | 指定机间通信阶段延迟或受控降速 | 目标跨节点关系出现预期长等待，可回查两端 |
  | 离线缺失一个 endpoint、重复记录或身份冲突 | 保留缺失/歧义或明确失败，不伪造精确边 |
  | 离线平移一个节点的时间 | 同步 identity 不变，未校准时不产生全局延迟结论 |

- **完成**：每例保存注入位置/参数/固定种子（如使用随机）、正常对照、预期定位与实际输出。
  先用小型合成数据验证规则，再用双机真实延迟样例验证采集到诊断的闭环；采集前确认注入
  位于可观测路径，不能把任意 host sleep 当作设备传输变慢。合成证据与设备结论分别记录。
  测试开关默认关闭、可撤销；超时设上限，不把异常注入留在默认运行路径。

## 4. 顺序与暂缓项

```text
NEXT-001 -> NEXT-003 -> NEXT-004 -> NEXT-006（双机设备闭环）
NEXT-002 -> NEXT-005 ------------> NEXT-006（定位验证）
```

优先完成以上闭环；以下事项保留方向，不作为所有任务的前置工程：

- **时钟校准**：确需跨节点绝对等待分解/全局路径时，先核实已有时间基；缺失再补最小
  offset/误差数据。只有长采集证明 drift 不可忽略时才增加 drift 模型。
- **FFts 完整 DAG 与 direct 边界**：当前 graph 缺失和声明序局限继续显式保留；目标异常
  定位被其阻塞时再获取真实 arc/barrier，禁止按 context 编号或时间补完整硬件依赖。
- **critical path**：Top Wait 与异常定位有效后再做，先用手算小图固定计费，避免重复计算 wait。
- **更多算法与资源类型**：优先使用已集成 standard Ring/NHR 和修复后的 Mesh；double ring、
  AIV、replay/retry、新 Scatter 按实际样例扩展，不把“接口存在”记为已支持。NHR 视图复用共享图。
- **开销**：修改热路径后在代表性 workload 比较 trace off/on；不因文档或离线展示变更重跑设备性能矩阵。

旧 HYG/CTX/TST/DEP/COV/MNT/DIA/E2E 拆分及未完成细节已完整保留在原任务快照中。
本次只整理文档，不把上述待办标为实现完成。
