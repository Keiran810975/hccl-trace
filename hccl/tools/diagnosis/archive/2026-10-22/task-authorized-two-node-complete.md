# nf 双机优先完整诊断验收

更新：2026-10-22。用户指定先用物理 Node0 + Node2 的自有容器，完成正常 workload、
语义打点、msprof DB、精确合并、跨机依赖、等待诊断和 HTML 输出。
四机验收保留为后续目标，本轮不扩展异常测试集。

## 已整合

`codex/ring-nhr-diagnosis@6312667` 的 AI_CPU 采集、控制事实补齐、同机/跨机 RDMA、
等待分析及 graph v6；保留 master 的默认选路修复和 nf 的既有本地改动。
接入 cr 的多节点本地关键路径和 CANN Python 包兼容性修复。154项诊断单测及2项结果门禁通过。
原计划及本地关键路径补充保存在 [本轮前快照](archive/2026-10-22/task-before-nf-four-node.md)。
真实单机HOST已通过数值、78/78 exact和108条同步关系；双机workload与完整语义分别记录。
原生Host/Device构建与C++回归通过；用户授权后Device已成功加载，详见[授权双机验收](nf-authorized-two-node-validation.md)。

## 下一步

- [x] 核对Node0/2空闲芯片，改用runtime 1/3（物理9/11）；不使用Node0已有占用的物理8/10。
- [x] 正常加载对照：自编译Device包checkcode校验失败，rtSetDevice=507033；官方包恢复并校验一致，官方包双机复核通过。未改验签。
- [x] nf Host+官方Device双机4 Rank、8MiB、1+3次AllReduce，数值误差0，1300个profiler任务；semantic=0，严格诊断失败。
- [x] 用户新增授权：允许为配套Device加载临时调整验签。使用正常宿主root SSH入口，不使用特权容器或命名空间绕过。
- [x] 自有Node0/NPU7单机AI_CPU加载成功：实际build[nf-aicpu-v2] enabled[1]，source=aicpu语义和数值正确；原验签False/5、官方包均恢复。
- [x] 双机仅选Node0/2空闲NPU7，原值快照+独立恢复定时器；结束后两机均恢复False/5和官方包。
- [x] 配套nf Host/Device双机AI_CPU正常小负载运行，4 Rank数值误差0。
- [x] 每节点256/256语义exact，共1300 profiler任务，重复/无效匹配0。
- [x] 4次operation有受控调用证据；144条跨机依赖、0未决通道，无环/缺端引用。
- [x] 完整入口导出496个paired Wait、诊断和三种HTML；源码/运行库哈希及原始数据留存。

## 后续未验收范围

- [ ] 扩大到既定训练型workload；本轮只验证正常8MiB小负载，不宣称大负载/异常闭环通过。
- [ ] Node1设备命名空间待管理员处理后，再开展四物理节点验收；不自行停止其他容器或重置设备。
- [ ] 无时钟校准时继续仅报告节点本地关键路径；不累计跨机全局关键路径。

本轮日志、恢复、复核及边界见 [Node0/2验证记录](nf-two-node-validation.md)。

## 边界

用户本轮明确授权临时调整验签。范围限Node0/2空闲NPU7；验签按整卡设置，测试后恢复两芯片原值并复核。
不调整其他设备、驱动、网络或共享库，不使用特权容器/命名空间绕过。Node1设备冲突留待管理员处理。
无跨机时钟校准和硬件完成证据时，只输出依赖拓扑、本地等待与节点本地关键路径。
正常样例没有异常基线时不宣称定位出异常根因。四机结果不得由离线 fixture 或旧双机结果替代。
