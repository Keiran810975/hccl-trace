# nf 四机诊断适配与设备验证

日期：2026-10-22。状态：**代码整合及部分设备验证完成，四机完整诊断尚未验收**。
不把旧双机数据、四节点离线fixture、编译通过或msprof退出0视为四机运行成功。

最新进展：用户授权后，Node0+Node2正常小负载的配套Device、512/512语义、144条跨机边、
496个paired Wait及HTML已通过，原验签和官方包恢复；见[授权双机验收](nf-authorized-two-node-validation.md)。
这不改变本页“四机尚未验收”的结论。

后续用户指定先跑Node0+Node2，正常Device包加载尝试、恢复及最新双机复核见
[双机验证记录](nf-two-node-validation.md)。以下“未安装/加载”为该次四机整合阶段记录；
后续已在自有Node0容器临时安装测试，但未成功加载，已恢复官方包。

## 代码

- nf基线 `fb4fbc8`；整合 `codex/ring-nhr-diagnosis@6312667`，包含AI_CPU sidecar、
  精确控制anchor、同机/跨机RDMA Notify、等待分析及graph v6。保留master选路修复。
- 保留nf本地关键路径，接入cr的分节点分析。无时钟校准时只输出本地路径和跨节点依赖，
  不累计全局关键路径，不把采集窗口完成等同于整个训练完成。
- 新增 `run_diagnosis.py`：严格回放成功后导出等待清单、候选、关键路径、
  execution/waits/resource三种HTML。失败不伪造诊断结果。
- 修复Host分层算法打点的全局userRank；commRank保持子通信域身份。
- 真实DB暴露Host门铃类型 `RDMA_DB_SEND`，新增精确类型兼容；门铃时长仍不是网络完成时长。
- 统一Host semantic/control/FFts设备身份。Host/device扩展v2在既有reserved word中
  传递明确的profiler设备ID，兼容旧v1物理设备ID；不改H2D结构布局、不修改DB。
- 启动器支持显式HOST/AI_CPU/DEFAULT，直接使用容器设备ID，避免可见设备二次重编号。
  每个worker数值检查及正常销毁通信域后写结果，启动器检查全部本地Rank，
  不再把msprof退出0当成workload成功。重复输出目录拒绝复用，避免继承过期成功记录。

## 已验证

| 检查 | 结果及边界 |
|---|---|
| Python诊断回归 | 154项通过，包括四独立节点时钟的完整入口、异常状态落盘与失败门禁；这是fixture，不是四机设备数据 |
| workload结果门禁 | 2项通过，缺worker或非有限误差拒绝通过 |
| HCOMM原生构建 | 自有Node0容器内Host及Device目标通过；Device只编译，未安装/加载 |
| C++真实源码回归 | one-shot、缓存身份、全局Rank、设备列表及Host/AI_CPU/FFts身份边界通过 |
| nf单机HOST | 910C、自有容器、2 Rank、32MiB FP32、1 warmup+2 measured；数值正确，78/78 semantic exact |
| 单机依赖与等待 | 316节点、414边，48条跨设备Notify+60条本地Notify；无环、无缺端点、0未决Notify关系；108个等待可回查生产者 |
| 单机视图 | 原生HTML生成及交互烟测通过；本地关键路径标记partial_evidence，不冒充完整应用关键路径 |
| 官方DEFAULT对照 | Node0/2，2 Rank，各8MiB，1+3次AllReduce，数值误差0 |
| nf Host+官方Device | Node0/2，4 Rank，各8MiB，1+3次，数值误差0、DB共1300任务，但semantic为0；完整诊断不通过 |
| 设备身份v2复验 | 同配置4 Rank再次数值通过；每节点48个Host控制任务精确enrich，原先物理8/DB0错配消失；仍因Device语义0条而严格失败 |
| 官方HOST对照 | 关闭项目trace、使用官方库，跨机Notify仍超时；单次fast-post配置也未解决；不能归因于项目打点独有问题 |

## 当前障碍

1. **Node1设备命名空间冲突。** 新的非特权 `zjy-new` 中，`npu-smi` 返回-8020，
   驱动报 `Conflict open udevid`。用户授权后仅重建此新容器，去掉host PID共享、
   缩小到物理9/11/13/15、补齐Ascend运行时显式分配后仍失败。
   不能通过停止旧容器、重置设备或调整共享策略自行处理，需要管理员确认资源分配。
2. **AI_CPU完整采集尚需合法Device部署。** 官方签名Device包没有项目sidecar，
   只替换Host库仍是0条设备语义。后续标准加载自编译包实测checkcode校验失败，
   设备上下文创建报507033，未进入通信，官方包已恢复。用户不允许调整验签，且确认无
   可用签名服务/已签名项目包；需要管理员提供符合现有策略的配套设备包部署条件。
3. **HOST不是已验证可用的跨机替代路径。** 官方库对照也超时，根因仍需进一步调查。
   当前只证明HOST本地诊断可用，不能用它宣称四机诊断已完成。

## 证据与继续入口

原始输入、构建日志、运行库哈希、容器记录和回放保存在工作空间
`test/out/nf-four-node-20261022/`。服务器独立目录为自有容器中的
`/workspace/nf-20261022/`。未改其他人的容器、驱动、验签、网络或任务。

已通过的真实单机视图：`one-node-replay/waits.html`、`dependency_execution.html`、
`dependency.html`；失败双机原始输入为 `default-input/` 和最初HOST的 `node0/`、`node1/`。
最终v2复验在 `v2-input/`、`default-v2-manifest.json`、`v2-replay/`；
`pipeline_result.json` 为failed，保留每节点semantic=0/control_tasks_enriched=48的原始统计。
真实实验的raw目录名node1代表本次torchrun的第二节点，物理机器是Node2（192.169.0.125），
不是当前设备访问失败的物理Node1（192.169.0.85）；manifest已显式区分。

后续先解决以上设备分配和合法Device部署，再进行四机正常小负载验收，之后扩大到训练型
workload。本轮不开展异常测试集，也不放宽语义或构图检查来生成成功截图。
