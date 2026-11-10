# 单次集合通信RoCE限速试验

## 状态与范围

2026-11-08用户确认尝试“只在某个有RDMA任务的通信范围内限速”，取代后续试验使用五轮限速的做法。
新增显式实验profile `roce-single-collective-v1`，与旧五轮批次、源快照、结果分母完全分开。
本轮只有CPU控制/故障测试，不是已完成NPU采集、RDMA慢化或根因定位验收。

只读资源凭证：`test/out/roce-single-collective-20261108/readiness.json`。
Node0整机空闲，Node3目标NPU4--7被外部VLLM占用；两机registry absent。
旧剩余六例监督3238321/start ticks503369603仍在`waiting_resources`，cmdline身份匹配。
没有停止外部进程、暂停旧监督、部署新服务器快照、加载包、修改端口或启动训练。
新入口拒绝与存活的旧监督竞争，不能在旧队列等待时偷偷插入第二个设备实验。

## 冻结实验

- 唯一新attempt名：`hccl-diagnose-node03-20261108-1101`，只用Node0/Node3原自有非特权容器及NPU4--7。
- 原GPT-2 Small DDP八Rank、每机四Rank、10预热+50正式，参数/梯度与原数据不改。
- 正式第25轮、桶种子20261102；运行时用实际参数桶signature在八个Rank核对同一通信。
- 仅Node0 Rank0实际出方向端口9，200Gbps降到20Gbps；相邻端口8保持原值。
- 不新增后台竞争、不修改HCOMM生产端、检测门槛、Notify依赖或默认诊断策略。
  新采集仍用已验证低日志Device包；诊断用不分簇的依赖溯源，保留原图、全部控制事实与独立结果。
- 只跑一次，不自动重试、改桶、改强度或补跑。没有实际RDMA或明显慢化时如实判无效。

## 控制顺序

1. 八Rank在目标桶提交前先等待此前提交的所有通信Future，再分别执行设备同步；
   不以一次同步或API返回代替尚未提交完成的异步工作。排空后通过CPU TCPStore会合，
   严格检查八个不同Rank、相同轮次、桶signature及元素数。此控制不新增HCCL barrier。
2. Rank0将完整会合记录交给原生端口保护器。保护器核对自有进程、原端口值、独立恢复演练后，
   设置20Gbps，读回确认并验证相邻端口未改变。
3. 只有确认之后，CPU控制通道才放行这一桶的原AllReduce。所有Rank在其后等待Future，
   再执行设备同步，分别记录本地提交和设备完成时间。
4. 等齐八Rank设备完成，恢复原端口值并读回，撤销网络保护timer，再通过CPU通道放行后续通信。
   不能用Python API返回或第一个Rank完成作为恢复/放行条件。

**精度边界：** 端口物理限速开始早于目标通信提交、结束晚于设备完成；原生设置无法微秒级切换。
但这段期间所有参与Rank都在控制边界内，按公开提交日志验证只放行一次目标collective，
因而目标是限制“受影响的通信集合”，不是声称限速精确包住某条RDMA硬件task。
后台未知进程或其他工作负载不能与本试验共用目标整卡。

## 控制等待与诊断隔离

`gpt-output/public/roce-controls-rank-N.jsonl`单独记录进入、放行、完成、离开控制阶段。
目标通信的公开准备起点在入门控制结束后重置，后续桶准备起点在出门控制结束后重置。
原来的准备阶段、控制等待及设备完成见证仍可从独立日志核对，不能将设置/恢复等待当成Host迟到。

这个实验故意序列化并暂停一个通信边界，不再是自然训练时间线。
整轮耗时含人为CPU控制等待，不用于训练开销、正常Host迟到或正常抖动误报的验收。
目标HCCL任务、协议区间与此前五轮自身历史的比较仍读取原事实，不读取注入标签选根因。

## 恢复与故障

复用原端口snapshot、原生set/readback、相邻芯片保护和独立恢复器；保留准备阶段3600秒回滚，
另在真正设置前启动120秒活动窗口独立回滚。CPU会合/确认轮询最长90秒，
设备Future另受原HCCL与外层捕获超时约束，不能把CPU轮询超时冒称设备完成上限。
读回失败、未知进程、不同桶、参与Rank缺失、Future失败、超时、流量未增长都拒绝成功放行。
异常立即向等待者报告失败，finally恢复原端口；无法验证恢复时不发布restored确认，
无论失败是否已恢复，都不放行正常后续通信。
外层仍复核两机策略/官方包/registry/全部Device和网络timer，失败不能无界重试。

只有隔离根、显式`single_collective_user_confirmed`、两节点NPU4--7、强制恢复、
`node3_target_process_stop_user_confirmed=false`及匹配低日志构建凭证被接受。
不复用旧800/900/1000实验根，不修改其活动快照。

## 采集后的独立验收

诊断先封存execution.html/root_causes.json/propagation.html，再做：

- 八Rank公开记录与控制会合/完成记录逐项一致；每个本地控制区间内只提交一个目标通信。
- 限速确认在Rank0该调用提交前，恢复在其设备完成后，后续提交在本地出门控制结束之后。
- TASK派生比较表中确实有该调用的RDMA提交任务，与实际目标窗口正重叠。
- 原协议CSV中，同调用/轮次/发送端具有恰好前五轮参考，至少两个不同协议区间被原1.5倍/3MAD标慢。
- 原生RoCE字节/包counter增长，八Rank训练数值及语义/图/校时门禁通过。
- 所有结果保留，包括无效和定位漏诊。协议区间不是RDMA硬件wire time，不证明物理网卡因果。

控制与公开日志会合通过，不代表DB里一定存在RDMA；DB中存在RDMA，也不代表慢化效果门禁通过。
当前没有设备数据，以上条件均未作实际验收。

## 入口与验证

代码：`test/roce_single_collective.py`；受保护单次入口：`test/run_roce_single_collective.py`。
现有GPT/保护采集入口只在显式新profile下接入，旧五轮路径与默认诊断入口不变。
须先部署独立、逐文件SHA冻结的源码、既有匹配Host/Device和新授权文件，且旧监督退出、
两机资源通过原35GiB/整卡/租约门禁，才可在Node0受保护根运行入口；本次未执行部署或启动。

CPU测试：

```bash
python3 -m unittest test.test_roce_single_collective \
  test.test_node03_network_control test.test_node03_roce_window test.test_multinode19 \
  test.test_node03_device_guard test.test_multinode20 test.test_gpt_three_anomalies test.test_single_sdma10
python3 -m unittest discover -s hccl/tools/diagnosis -t .
```

源码修改前备份：`test/out/roce-single-collective-20261108/backup/before-single-collective.tar.gz`，
SHA256 `501b184274637b2cee9ae21b1bd1410ead59c1816aac81fb655ea7f286dba2b9`。
这份备份保留此前未提交的实际文件，不回滚或覆盖用户改动。
