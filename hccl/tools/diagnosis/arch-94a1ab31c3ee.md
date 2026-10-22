# HCCL Trace 单机实现与后续开发交接归档

## 2026-09-24 新阶段入口

`codex/ring-nhr-diagnosis` 已完成固定2x4 Single Ring/NHR诊断闭环：1,792/1,792 exact，
1,504个Wait全部配对，288条跨机边，execution/resource完整门禁通过；
Ring rank3/RS step1与NHR rank7/RS step0的40ms CPU构图异常均4/4定位正确，
分别关联112/88项长等待。111项Python回归、Host/Device构建、C++stub和实际数据扰动检查通过。
最终正常off/on数值正确、无注入残留；验签恢复、远端临时产物清理完成。

实现合同、边界与测试证据见[Ring/NHR场景记录](ring-nhr-diagnosis.md)和
[测试报告](../../../test/out/ring-nhr-diagnosis/测试结果说明.md)。此前活动计划已归档到
[2026-09-24快照](archive/2026-09-24/task-before-ring-nhr-completion.md)。
本段补充最新入口，下文为旧阶段事实，不再作为本场景待办。

> 本归档记录旧本地 `94a1ab3`，不覆盖后来补查发现的远端增量。远端 master 已修复
> 提前返回窗口，另有 Ring/Mesh/NHR/RHD 分支；详见
> [分支调查](branch-review-2026-09-15.md)。以下旧状态保留作历史快照。

- **归档日期**：2026-09-15。
- **根仓基线**：`94a1ab31c3eee7ee7a51e2eb401167e24e5bbac6`，本次文档整理前的 HEAD。
- **范围**：当前实现、历史决策、单机验证证据及后续任务调整；不包含新功能实现。
- **活动计划**：[task.md](task.md)。本文件是阶段快照，不随未来实现更新统计。

## 1. 分支与源码状态

以下为整理开始时的本地状态；未 fetch，不代表远端实时状态。

| Git 仓库 | 当前分支 / HEAD | 工作树与其他分支 |
|---|---|---|
| 工作空间根目录 | `master / 94a1ab3` | 干净；本地 `origin/master` 同提交，`origin/8.5.0=8d6ed05` |
| `hccl/` | `dev-innerDia / 4600cb628104` | 有已跟踪修改、删除及未跟踪诊断文件；`8.5.0`、`init` 均为 `3f4e05e`，`8.5.0` 比本地 `origin/8.5.0` 前进 1 个提交 |
| `hcomm/` | `dev-innerDia / 7db54477d156` | 17 个已跟踪文件修改；`8.5.0=2981ffa7`，`master=2a854361` |

根仓以普通文件直接跟踪 HCCL/HCOMM 源码，不是只保存 submodule 指针。因此根仓后续提交
已经记录的实现，在子仓仍可显示为未提交。`4600cb6`、`7db54477` 不能单独代表当前代码；
本归档也不表示已为子仓补提交。所有既有源码改动和 Git 状态均保留。

本版本建立在配套 8.5 源码上；传统 AllReduce 的生产端位于 HCOMM，HCCL 承载 Python
诊断工具和新算子架构。`../cann-hccl/` 仍只作旧版参考。

## 2. 提交与记录索引

| 提交 / 记录 | 形成的能力或决策 |
|---|---|
| HCOMM `9e60ec27`、`7db54477`（2026-06-27） | 初始 TLS/RAII 语义设施、Sender/Reducer 与 direct RS/AG 插桩 |
| 根仓 `8d48380`（2026-07-02） | 在 TaskData 创建时捕获语义，避免上报时读取失效 scope |
| 根仓 `99d804f`（2026-07-23） | 消费端止错、FFts parent/context 精确关联 |
| 根仓 `988653f`（2026-07-23） | consolidated DB 替代 JSON，整数纳秒、42 列 merged 合同 |
| 根仓 `9f89b3a`、`935d3e2`（2026-07-24） | 稳定身份、operation scope、FFts 依赖；清理本地 task 序号与重复实例字段 |
| 根仓 `2a2737c`、`f5e21e7`、`1d7503c`（2026-07-24） | direct Notify ordinal、双层图、resource 收缩、等待指标与门禁 |
| 根仓 `1270e7d`（2026-07-25） | step 合同、local Notify exact、宽整数修复、删除 payload semantic 边 |
| 根仓 `94a1ab3`（2026-08-11） | 更正旧归档对 HEAD 与工作树的说明，无功能修改 |

历史资料保留原位置，避免破坏已有链接：

- [arch-988653fc0037.md](arch-988653fc0037.md)：DB 迁移和 single-ring golden。
- [arch-4600cb628104.md](arch-4600cb628104.md)：双层图初版；其中 payload 边与旧边数已被后续实现替代。
- [整理前 task/spec 完整快照](archive/2026-09-15/README.md)：保留所有旧任务、实现叙述与当时的限制。
- [早期迁移方案](../../docs/help/step-trace-causal-diagnosis-migration-plan.md)、
  [版本差异调查](../../docs/help/repository-differences.md)：解释迁移起点，不能据此恢复已撤销的设计。
- [当前规格](spec.md)、[依赖定义](../../../文档/依赖关系的定义与构建.md)：后续实现的合同入口。

## 3. 当前实现基线

```text
HCOMM TaskData semantic + FFts graph correlation plog
                  + msprof consolidated DB
                             |
                         exact merge
                             |
                      execution graph
                             |
                      resource graph
                             |
                    CSV / HTML / SVG
```

- semantic 生产 v4，消费 v2/v3/v4；graph correlation v1，msprof DB schema `1.2.0`，
  merged 42 列、graph artifact v4。JSON/task_time.csv 及无版本日志已退出生产输入。
- direct 使用物理 task identity；FFts 使用 graph parent + context。DB 的 operation
  名称元组生成 scope，不再由生产端维护另一套 operation/retry 计数。
- execution 保留所有目标 physical task，包括 profiler-only 控制任务；resource 白名单为
  `sdma/rdma/reduce_inline/reduce_tbe`，派生边保留源 execution/control/relation ID。
- direct stream 顺序是 observed，FFts logical stream 声明序是 semantic；FFts Notify
  唯一 relation 是 observed，direct/local Notify 完整 channel ordinal 是 exact。
- 当前有本地 wait span 和同节点观测分解，尚无正式 Top Wait、根因报告或 critical path。

### 本次移出活动清单的完成项

| 旧任务 | 已完成内容 | 证据 |
|---|---|---|
| SEM-006 | 固化 RS/AG phase 内 step 因果桶，拒绝 main-round 事件落入 epilogue | 当前 28,502 行合同检查无违规 |
| DEP-020 | `dstRank=-1` 的 local Notify 独立配对，宽整数 Notify ID 不经过 float | 112 个 channel、5,376 条 exact 边；两个方向各 2,688 |
| DEP-027 | 删除传递冗余且 occurrence 不可靠的 payload semantic 因果边 | 原 2,142 条均有替代 Notify/stream 路径；当前两层图 payload 边为 0 |

上述功能已在根仓 `1270e7d` 中记录；本次只是归档，不是重新实现。更早的 DBI、COR、
DEP-001～015 等完成项继续保留在前两份归档中。

## 4. 单机验证证据

原始采集日期为 2026-07-23。输入位于工作空间 `test/out/plog/` 和
`test/out/function/msprof/`（8 个 consolidated DB）；已有输出位于 `test/out/function/`。
这些目录被 Git 忽略，本次不搬移或复制大体积数据。文档归档不能代替原始数据备份；
其他机器需要另行携带这些输入才能复现。

| 指标 | 已保存结果 |
|---|---:|
| semantic / exact | 28,502 / 28,502（100%） |
| direct / FFts exact | 14,097 / 14,405 |
| graph correlation | 335 |
| physical execution / profiler-only | 44,008 / 15,506 |
| operation scope | 7；328 个 physical task 缺 scope，仍保留为节点 |
| execution node / edge | 44,008 / 56,675 |
| direct / local Notify exact | 5,376 / 5,376 |
| FFts Notify observed / single | 4,676 / 28 |
| resource 真实任务 / boundary / edge | 11,432 / 8 / 25,479 |
| resource order / Notify sync | 10,051 / 15,428 |
| execution / resource isolated | 2,059 / 695 |
| duplicate、missing endpoint、自环、cycle residual | 均为 0 |
| Notify ambiguous/incomplete/conflict、收缩歧义 | 均为 0 |

28 个 FFts single 与 rank 7 缺 graph instance 16 的 semantic/correlation 有关，具体生产或
日志丢失原因仍未定责。8 个 boundary 是各 device 最早 slave→main local Notify 缺少上游
资源任务，属于显式覆盖边界。semantic 100% exact 只说明**已记录的语义均能匹配**，
不证明所有 physical task 或完整 graph 都有语义。

### 2026-09-15 本次实际复核

从工作空间根目录执行：

```bash
python -m unittest hccl.tools.diagnosis.test_diagnosis
python -m hccl.tools.diagnosis.validate_trace test/out/function/merged.csv --min-match-rate 95
python -m hccl.tools.diagnosis.validate_dependency_graph test/out/function/dep_graph --max-boundary-nodes 8
```

Python 3.12.7：62 项单测通过；已有 merged 的 exact rate 为 100%、step 违规为 0；
已有图 artifact 门禁通过。这里检查了保存的 CSV/summary，**没有重新执行 DB merge、
构图、HCOMM 构建或设备 workload**。图门禁通过也不表示已修复下面的证据传播问题。

## 5. 未解决问题与支持边界

1. **生产端收尾**：两处 `[TEST PATCH]` 仍强制 910B Ring；TaskData 消费 one-shot 后，
   `Run()` 的 addition-info/OP_BASE/非 capture 分支仍可能提前返回而不输出语义。
2. **派生证据**：FFts/mixed resource order 硬编码 observed，可能强于源 semantic；
   Notify 收缩也应按完整源路径核定最弱 confidence。现有 gate 未验证这一不变量。
3. **FFts 完整性**：profiler-only graph membership、direct↔FFts 边界和内部硬件 DAG
   尚不完整；context 声明序不能替代硬件 arc，28 个 single 仍需新采集定位。
4. **覆盖**：设备证据限于上述单机样例；标准 Ring、默认 mesh、hierarchical、NHR、
   RDMA/RoCE、AIV 等不能仅凭公共 helper 已插桩就宣称完成。vector 路径只标首任务，
   AIV 专用 Save 仍只有 probe。
5. **多机**：已有 node 字段和未校准 timing 状态，但没有多节点输入组织、实测跨节点
   共享身份、校准 artifact 或多机验收；同名 operation 不能未经核实直接跨采集关联。
6. **诊断**：尚无正式 Top Wait/关键路径与异常定位闭环；已有小型失败 fixture 不等于
   慢 rank、机间链路异常的设备测试。

## 6. 后续计划的收敛

| 原任务组 | 新计划位置 |
|---|---|
| HYG、CTX、TST、相关 E2E | NEXT-001：围绕生产端收尾做针对性回归 |
| DEP-016/017、E2E-009 | NEXT-002：修正源路径证据，不新建独立框架 |
| COV、MNT-000/001/002/006 | NEXT-003/004：一个双机样例先证实字段，再补必要实现 |
| DIA 等分析项 | NEXT-005：先 Top Wait 与证据回查，critical path 后置 |
| 原计划缺少的异常闭环 | NEXT-006：正常对照、慢 rank、机间延迟与数据缺失样例 |
| DEP-021～026、校准、更多算法 | 按实际诊断阻塞逐项启用，旧细节保留在快照 |

拓扑配对与跨节点时间分析分开推进：有共享事实即可建立关系；需要跨时钟差值时再校准。
协议 token、drift、完整 FFts DAG 和全算法覆盖不预先绑定成一个大工程。
