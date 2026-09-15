# 算法分支调查与集成记录

## 最新决定与执行状态

用户已批准同步远端 master、合入 standard Ring/NHR，并要求修复 Mesh、弃用 RHD。
本地根仓 master 已依次完成合并：`2f26033`（远端 master）、`360d650`（standard Ring）、
`638e94c`（NHR）。本轮整理文档先保存为 `c7ae7c7`；合并中的 task/spec 冲突保留精简计划，
结合远端事实更新，算法实施记录仍在分支说明及下文。

Mesh 已在 `codex/fix-mesh-semantic@286ef99` 修复；该分支基于已集成主线，通过 `7d89a0c`
合入原 Mesh。normal Tx/Rx 沿用 Ring 的 signal/data 分开标注，仅改一个 C++ 文件，公共
scope、transport、atomic/direct 和 Python 消费端未变。对照 transport 完成提交顺序与参数
检查，`git diff --check` 通过；本机没有 CANN 构建环境，未声称 C++ 构建或设备验证通过。
工作树在 `test/out/mesh-fix/`，其中 `文档/Mesh语义修复说明.md` 记录针对性设备验收步骤；
用户随后批准 Mesh 合入及推送，master 已快进到 `f30a90a`，包含原 Mesh 和修复 `286ef99`。
设备测试尚未执行，交接见 [测试 prompt](../../../test/prompts/integrated-master-device-test.md)。

RHD 弃用，保留历史引用，不安排测试或集成。以下为合并前调查快照，其中待批清单以本节
最新决定为准。

更新：2026-09-15。目标分支是 **hccl-trace 根仓的 master**，不是 HCOMM 上游的 master。
本次已读取远端 heads 并 fetch 根仓远端跟踪引用；没有切换分支、合并、提交或推送。

用户最终确认 **feat-NHR、feat-mesh、feat-standard-ring 已经过测试**，并更正
**feat-RHD 尚未测试**。原始输入暂缺，上级目录有留存 HTML。已将最新确认及 HTML
检查纳入结论，不继续把已测试分支旧文档中的“待测”当作最新事实。

## 1. 调查范围与更正

上一轮本地 `master@94a1ab3` 比实际远端落后 7 个提交，漏掉四个算法功能分支。
因此此前“尚未实现”的判断只适用于旧本地源码，不能代表整个项目。

| 引用 | 本次核实的提交 | 相对远端 master 的独有提交 |
|---|---|---:|
| 本地 `master` | `94a1ab31c3eee7ee7a51e2eb401167e24e5bbac6` | 落后 7 |
| `origin/master` | `d0d290400f1b355a8e4df3d5a24970d1d5c6bfd4` | 基准 |
| `origin/feat-standard-ring` | `7dadcea647e9a43fa59c676a459a9fe774450189` | 9；包含当前远端 master |
| `origin/feat-NHR` | `29ab3cd72f901f55d9483d4565b7ae1883e37922` | 5；缺主线后续 4 个提交 |
| `origin/feat-mesh` | `d87011154d784625a3a8403f0d79d602ed96cdf5` | 4；缺主线后续 5 个提交 |
| `origin/feat-RHD` | `e3e368f473449c3fcd52c8e8bae37c8af7f90491` | 1；包含当前远端 master |

HCCL 子仓的 origin 也指向同一个 `tjucyx/hccl-trace` 远端，不能把其远端分支当作独立的
HCCL-only 分支直接合入子仓。HCOMM origin 为 `cann/hcomm` 上游；本次读取其远端 heads，
8.5.0 仍为 `2981ffa7`，其 9.x/master 是版本演进，不属于本次诊断功能合入范围。
三个仓均只有当前 checkout 对应的本地 worktree。

## 2. 实现与已有验证

### 远端 master：应先同步的主线增量

`9eedf27` 已抽取 `ReportCapturedTaskSemantic()`，在 OP_BASE 未订阅 addition-info、
非 capture 的提前返回路径兑现已捕获语义；正常路径保持共用 submit timestamp。
这已是主线实现，后续工作应是同步与必要回归，不能重复开发。

另有覆盖矩阵、算法分支报告与 msprof 采集说明。曾临时放宽 FFTS callback 门控的补丁已在
算法分支 revert；正式语义验收仍需 msprof。TaskData 已进入 `Run()` 后的快照兑现，与
FFTS callback 是否由 msprof 订阅触发，是不同问题。

### Standard Ring：用户确认已测试，HTML 支持单机语义结果

- 实现 standard Ring RS/AG；设备结果定位到 AG payload 语义误落 notify_wait、每 graph
  7 条 SDMA 未标。后续 `18c804d`、`87d4375` 在 Ring `TxVector/RxVector` 内拆开 signal/data
  调用，避免修改公共 scope 或 TransportP2p。
- 增加公共 executor 的 user↔CCL copy，并统一 direct Ring 对应 copy 的 semantic 标签。
- 分支说明记录 336 个 graph、operation 内 6,384 条 SDMA，以及修复前 3,696 条未标 SDMA；
  修复后的“未标 SDMA=0”、新增 1,344 条 executor copy 等写在**测试方案**中，不能当作
  已执行的最终结果。
- `7dadcea` 记录了 Ring→NHR→Mesh 顺序合并演练；这是兼容性证据，不是设备回归。
- 当前分支 task 仍标 `[-]`，用户已补充确认该分支经过测试；采用这一最新状态。
  原始采集目录、构建提交和最终 golden 未留存或未回填，HTML 计数见下一节。
  建议集成已有算法插桩，保留覆盖余项，不把测试方案的目标数当作实测数。

### NHR：用户确认已测试，HTML 支持普通 NHR 单机结果

- 实现普通 NHR RS/AG、Oneshot Reduce/Broadcast 的 SDMA/RDMA 分支和 hop 语义。
- 分支说明记录已有 `semantic_total=10,416`，operation 内 11,760 个 task；1,344 个未标
  SDMA 来自 executor 边界 copy，NHR 内部 AG copy 与 RS reduce 各 1,008 条已正确匹配。
- 最后代码提交 `29ab3cd` 补 executor copy；“新增 1,344、两个方向各 672、未标 SDMA=0”
  在分支文档中属于方案。用户已确认测试，留存 HTML 的实际计数见下一节；没有 commit
  元数据，不能把文档目标数直接写成最终实测数。
- 普通 NHR、Oneshot、不同 transport 的验证范围分别记录；单机 combine-plane 数据不能
  证明多机子通信域 rank 身份已正确。模板目前以内部 rank 填入部分 user_rank。

### Mesh：用户确认已测试，HTML 与 Direct 路径一致，normal 另有问题

- `d870111` 包含 normal/atomic RS/AG 和 Mesh Direct 插桩、rank 编译修正及 callback revert。
- 远端记录了静态合同、62 项 Python 单测及无 msprof 的正确计算结果；后者不能证明语义
  完整。用户补充的 HTML 已有 exact 资源语义，不能再停留在“0 语义、尚未测试”的旧结论；
  同时不能由某个变体通过推导全部 Mesh 通过。
- 本次源码审阅发现：normal `AllGatherMesh::RunAllGather` 第 122 行在整个 `Rx()` 外建立
  `rx_payload_copy_start` one-shot，而 `Rx()` 第 57 行调用 P2P `RxAsync`；后者第 1222 行
  先提交 `SignalWait`，再提交目的端 SDMA。首个 Wait 会消费 payload scope，SDMA 因而可能
  无语义。这是 Standard Ring 分支已经专门修正的同类问题。
- 该结论针对 normal P2P 路径，不否认 atomic/direct 可能已有通过的样例。当前不建议把
  整个 Mesh 分支作为“完整验证”直接合入。

代码依据：[Mesh scope](https://gitee.com/tjucyx/hccl-trace/blob/d87011154d784625a3a8403f0d79d602ed96cdf5/hcomm/src/algorithm/base/alg_template/temp_all_gather/all_gather_mesh.cc#L122)、
[P2P RxAsync](https://gitee.com/tjucyx/hccl-trace/blob/d0d290400f1b355a8e4df3d5a24970d1d5c6bfd4/hcomm/src/platform/resource/transport/host/transport_p2p.cc#L1219)。

### RHD：已实现，用户明确更正为未测试

- `e3e368f` 覆盖经典 recursive halving-doubling 的 RS/AG、非 2 次幂折叠与回填。
- 分支说明只记到静态合同、Python 检查；用户已撤回此前测试确认，明确 RHD 未测试。
  `../` 下未发现 RHD HTML，不能将 `graph-ring.html` 的 Ring round 数据替代为 RHD 证据。
- 移出本轮建议合入名单。后续复用现有插桩，针对实际 Level1/Level2 路径及 rank 映射
  做设备采集验证，再评估合入；不重复开发或预设完整测试矩阵。

## 3. 用户提供的 HTML 证据

从 HTML 的 `const model={...}` 用 JSON 解码读取节点/边，没有执行页面脚本。三份均为
resource 视图，16 个 lane、8 个 device、7 个非空 operation scope，均在 `node0`。
模型不含 algorithm、构建提交和完整 merge/gate summary，因此不能复算全部 semantic
匹配率，也不能据文件名独立确定算法。下表数值只针对 HTML 内可见 resource 节点。

| 留存文件 | 节点 / 边 | 带 exact 标记的资源节点 | operation 内未标语义 SDMA | boundary |
|---|---:|---:|---:|---:|
| [graph-NHR.html](../../../../graph-NHR.html) | 3,704 / 6,720 | 3,024 | 672 | 0 |
| [graph-mesh.html](../../../../graph-mesh.html) | 1,800 / 2,016 | 896 | 112 | 784 |
| [graph-ring.html](../../../../graph-ring.html) | 6,396 / 14,605 | 5,658 | 726 | 4 |

每份另有 8 个无 operation scope 的 SDMA。三份可见图的 duplicate node ID、missing
endpoint、self-loop、cycle residual 均为 0；这项检查不等同于原始 execution 图门禁。

- **NHR**：RS reduce 1,008、AG payload copy 1,008，phase step 均为 0/1/2；executor copy
  共 672，user→CCL 与 CCL→user 各 336。普通 NHR 的核心资源语义已有证据；仍有 672 个
  operation 内未标 SDMA，尚不能确认最终补全目标 1,344 条 executor copy 全部兑现。
- **Mesh**：RS `tx_payload_start/link_tx_payload_reduce` 392、AG copy 392、本地 copy 112，
  step 均为 0。这与 Mesh Direct 的源码合同一致（推断，不是 HTML 内的 algorithm 标签）。
  784 个 boundary 是留存图实际覆盖边界，不能套用旧 single-ring 样例的阈值 8；该 HTML
  不能验证 normal Mesh 的 `RxAsync` 路径，也不说明这些边界均已解释。
- **Ring**：RS/AG step 为 0..6，AG payload copy 2,349、RS reduce 2,312、executor copy
  666，说明存在补全后的语义产物；与分支测试方案的理想计数不完全一致，缺原始输入时不
  猜测为代码失败、日志丢失或某个具体 commit。它不是 8-rank RHD 的 3-round 证据。
- 图中仍有 `resource_ffts_order_observed`；已知证据传播问题是公共分析层待办，不对各
  算法分支重复提出同一修复，也不把它解释为新增算法通信失败。

原文件位于用户指定的上级目录，未修改、搬移或重复复制。SHA-256：

```text
graph-NHR.html  1148458c700c5bc2a9593e02e66fa46db76f0fc0fd8baed76ecda2438441afad
graph-mesh.html 7f700ca53f1f53d1784eb2c79f52781ce64027c7d1af313248034a5b6022e00f
graph-ring.html db0d56c47f3cd285f58128d58e5124cb50ece1abeeaf94c43f3315d6bfedaaae
```

## 4. 合并兼容性检查

本次使用 `git merge-tree --write-tree`，对象写入隔离的
`test/out/branch-review-20260915/objects`，没有更新分支、索引或源码工作树。

| 检查组合 | 结果 |
|---|---|
| 远端 master → Ring | 无冲突，可快进 |
| 远端 master + NHR | 仅 `hccl/tools/diagnosis/task.md` 内容冲突；C++ 自动合并 |
| 远端 master + Mesh | 无冲突 |
| 远端 master → RHD | 无冲突，可快进 |
| Ring + NHR | 仅 task.md 冲突；公共 executor 文件内容完全一致 |
| Ring + Mesh | 无冲突 |
| NHR + RHD | 仅 task.md 冲突；C++ 自动合并 |

本次只做分支两两合并检查，不代表全分支组合已经构建验证。
结合既有顺序演练及用户补充验证，当前优先审批
`同步 master -> standard Ring -> NHR`；Mesh normal 问题单独处理，RHD 待设备验证。

所有候选的 Python 消费端与旧本地主线完全相同，上一轮 62 项单测可作为消费端回归证据，
不能验证新增 C++ 插桩。分支 diff 检查只报告公共覆盖矩阵第 3、4 行 Markdown 硬换行空格，
无新增 C++ 空白错误；不把这两处文档空格当作功能阻断。

## 5. 待批准清单

| 对象 | 当前建议 | 批准前需明确的内容 |
|---|---|---|
| `origin/master@d0d2904` 同步到本地 master | 建议先同步 | 保留本轮未提交文档，整合远端进展；不重复实现 CTX-002 |
| `feat-NHR@29ab3cd` | 建议合入算法插桩；用户确认已测试，HTML 支持普通 NHR 核心语义 | 保留 executor copy 覆盖余项；不扩大为 Oneshot/全部 transport/多机依赖验收 |
| `feat-standard-ring@7dadcea` | 建议合入算法插桩；用户确认已测试，已有 HTML | 保留构建提交未回填和覆盖余项；不以不完整计数宣称全覆盖 |
| `feat-mesh@d870111` | 暂缓整体合入 | 处理 normal Rx one-shot 错位，区分 normal/atomic/direct 的验证范围 |
| `feat-RHD@e3e368f` | 暂缓；已实现但未经设备测试 | 针对实际 Level1/Level2 路径及 rank 映射验证后再评估 |

“建议合入”指将已有算法插桩集成到研究开发主线，不等于声明所有资源语义、变体和多机
诊断均已完成。用户确认的已测试状态予以保留；HTML 未提供的构建/提交字段如实留空，
缺失原始 DB 本身不作为强制重跑所有测试的理由。Mesh 暂缓来自具体代码问题。

实际合入等待用户逐项批准；提交若前进，只复核新增差异。不得因 merge-tree 无冲突直接
合并，也不自动推送。批准后的文档整合沿用简洁活动计划，并保留算法分支进展和限制。

## 6. 远端记录入口

- [主线实施报告](https://gitee.com/tjucyx/hccl-trace/blob/d0d290400f1b355a8e4df3d5a24970d1d5c6bfd4/文档/语义追踪算法覆盖实施报告.md)
- [主线覆盖矩阵](https://gitee.com/tjucyx/hccl-trace/blob/d0d290400f1b355a8e4df3d5a24970d1d5c6bfd4/文档/语义追踪覆盖矩阵.md)
- [Standard Ring 补全说明](https://gitee.com/tjucyx/hccl-trace/blob/7dadcea647e9a43fa59c676a459a9fe774450189/文档/Standard_Ring语义补全说明.md)
- [NHR 补全说明](https://gitee.com/tjucyx/hccl-trace/blob/29ab3cd72f901f55d9483d4565b7ae1883e37922/文档/NHR语义补全说明.md)
- [RHD 实施与测试说明](https://gitee.com/tjucyx/hccl-trace/blob/e3e368f473449c3fcd52c8e8bae37c8af7f90491/文档/RHD语义追踪实施与测试说明.md)

以上内容通过 Git 对象读取，不依赖网页展示。活动计划见 [task.md](task.md)，旧本地基线见
[阶段归档](arch-94a1ab31c3ee.md)。
