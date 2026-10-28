# 跨机协议完成区间

2026-10-28：用户确认先测协议级完成区间，不要求将其称为精确硬件RDMA传输耗时。
本功能只消费通过门禁的执行图，不新增设备任务、不修改原依赖边、不重编Host/Device。
随后用户提出完整传输计时与依赖的要求；新增[完成事件采集](rdma-completion.md)作为独立证据，
但当前910C AI_CPU路径尚未完整支持，不能将本文协议区间改称完整传输时间。

## 测量口径

设A发送数据、B接收数据，沿现有图提取：

```text
B: 发出准备ACK
       -> A: 等待ACK
       -> A: RDMA Payload提交
       -> A: 数据通知提交（可能与Payload合并为一个doorbell）
       -> B: 数据Notify Wait结束
```

协议区间 = B的数据Wait结束时刻 - B的准备ACK提交开始时刻。
两个时间端点必须是同一Node、device、Rank，因此不需要跨节点时钟相减。
它包含准备同步、发送端调度/等待、数据传输、通知及接收端Wait释放开销。
它**不是**纯网络耗时、单个WQE的硬件完成耗时、带宽或全局关键路径损失。

同时保留A本地的`submission_duration_ns`。`network_transfer_duration_ns`保持null，
不从Wait时长、节点时间戳差或“size/带宽”假算精确完成时间。

## 证据规则

- Payload必须有已匹配的`link_tx_payload`语义、唯一operation和明确peer。
- 只沿真实、唯一、时间相容的direct物理stream顺序寻找准备ACK和通知；不按最近时间、
  相邻task编号、相邻step或猜测邻居配对。
- 两次跨节点通知均使用已有`cross_node_notify_sync_observed`边，方向相反，端点Rank一致。
- 准备端是`link_tx_ack`；完成端是对应接收端的data-signal或payload Copy/Reduce Wait。
- 同步端点不唯一、另一个Payload插入、跨operation、FFTS或遍历截断均保留未解析。
- 合并doorbell的Payload/Notify使用其自身已有同步边，不跳到后一个通知。
- 输出路径仅引用原始节点/边ID，不生成新的payload因果边；不保证覆盖所有未标注RDMA流量。

这是按HCCL已有协议观测到的完成区间，不是底层CQ硬件完成时间。
源码中`TransportDeviceIbverbs::TxSendDataAndNotifyWithSingleQP`把数据和其后通知一起编排，
接收端`RxAsync`等待数据通知；通常路径的`TxWaitDone`并非硬件完成轮询。
官方也明确RDMASend的任务时长只是WQE下发耗时，见
[通信任务行为说明](https://www.hiascend.com/document/detail/zh/CANNCommunityEdition/910beta3/API/hcclug/docs/zh/user_guide/perf_analysis/profiling_op_behavior.md)。

## 使用

多节点`run_diagnosis`通过门禁后自动产生：

- `rdma_timing/index.html`：提交时间、协议区间和可展开的真实依赖路径。
- `rdma_timing/report.json`：完整事实、路径、未解析原因及测量边界。
- `rdma_timing/transfers.csv`：每个已标注Payload一行，精确整数纳秒。

已有通过诊断门禁的数据可独立回放，输出目录必须不存在：

```bash
python3 -m hccl.tools.diagnosis.rdma_timing /path/to/passed-diagnosis \
  -o /path/to/new-rdma-timing
```

pipeline结果区分`rdma_protocol_interval_count`与始终为false的
`rdma_hardware_transfer_duration_available`；没有有效协议区间不等于通信正常。

## 留存数据验证

使用2026-10-22已验收的Node0+Node2双机8MiB、4 Rank小实验离线回放，176个RDMA类别任务中，
32个已标注Payload均取得协议区间。第一行发送Rank1、接收Rank3，提交0.320us，协议区间117.018us。
这不是新采集、异常准确率验收或大负载性能结论。原图、原始DB和旧诊断结果保持不变。
