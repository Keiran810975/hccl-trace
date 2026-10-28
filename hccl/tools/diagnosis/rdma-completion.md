# RDMA 完成事件采集与验收边界

2026-10-28，本轮在 `nf` 增加原生 verbs 完成事件观察器、严格离线解析和覆盖报告。
**尚未完成当前 910C AI_CPU AllReduce 的完整 RDMA 传输计时与物理 task 绑定。**
不能把新增代码、本地测试或旧数据回放称为这一目标已经设备验收通过。

## 三种时间不能混用

| 字段 | 端点 | 能说明什么 |
|---|---|---|
| `submission_duration_ns` | msprof RDMA SQE 开始到结束 | 提交 WQE/doorbell 的时间，不是传完数据 |
| `protocol_duration_ns` | 接收端准备 ACK 到本端数据 Notify Wait 结束 | 含调度、同步及数据到达的协议区间，见 [协议计时](rdma-timing.md) |
| `operation_elapsed_observed_ns` | 同一进程 post_send 入口到成功 CQE 被现有轮询观察到 | 本地操作完成观测区间，含提交、排队及轮询延迟，不是硬件纯传输时间 |

`network_transfer_duration_ns` 继续为 null。不跨 Node 相减时间，不将 CQE 的本地完成
解释为对端应用已经消费数据，不将控制信封 Send 解释为用户 payload Send。

## 生产端改动

- `hcomm/src/platform/common/adapter/adapter_verbs.cc`：只观察原有
  `hrtIbvPostSend` / `hrtIbvPollCq` 调用；后者返回什么 CQE 就记录什么。
- `rdma_completion_observer.h`：输出 `[HcclRdmaCompletion] schema_version[1]`，保留
  opcode、字节数、原始宽整数 WR ID、QP number、进程及 CQ 对象身份、post 返回值和 CQ 状态。
- `transport_heterog_roce.cc`：在确知协议角色的原生调用处附加 Rank、message ID 和
  `control_envelope` / `data_read_and_ack` / `data_write` 角色。Iwrite 此处无确定 Rank，保留 -1，
  不使用未赋值的 `localRank_` / `remoteRank_` 默认 0 猜测。Read 链中的 Ack 仍按实际 opcode 单列。
- `HCCL_RDMA_COMPLETION_TRACE=1` 才开启，默认关闭，并需启用采集 INFO plog。
  同时保留原 `HCCL_STEP_TRACE=1` 和 msprof 采集，新增日志不代替两者。
- 不改变 send_flags、不强制 signaled、不增加 CQ poll、不抢走设备或运行时拥有的 CQE，
  不新增设备任务。打开日志会产生观察开销，尚未测量，不宣称零开销。

## 精确配对与输出

同一次采集按 `(node, pid, process_epoch, cq_id, qp_num, wr_id)` 配对。
`cq_id` 是本进程 CQ 对象身份，不冒充全局硬件 CQ 编号。WR ID/message ID 不冒充跨机全局身份。
重复 WR ID 只在记录数量完整、每次生命周期严格不重叠时按本地顺序配对；否则全部保留歧义。
错误 CQE、失败提交、未知提交结果、缺失 CQE、opcode 不一致均不输出成功耗时。
日志截断另列覆盖缺口，不能由局部成功记录判定整体采集完整。

`multi_node_trace` 将各节点 plog 解析为 `node*/rdma_completion_events.csv`。
后续分析只消费这个 artifact。多节点 `run_diagnosis` 自动导出：

- `rdma_completion/index.html`：完成观测及缺口，链接到原生任务依赖图及协议路径。
- `rdma_completion/report.json`：完成记录、错误、未配对 CQE 和日志缺口。
- `rdma_completion/operations.csv`：每条提交一行，所有时间、宽整数身份保持整数精度。

WR 与 msprof 的 physical task 尚无直接外键，所以 `graph_id` 保持 null，
`rdma_completion_graph_binding_available` 与 `rdma_full_transfer_and_dependency_available` 保持 false。
不按“时间最近”“相同消息长度”“相同数量”将两类事件绑定，也不据此补依赖边。
现有真实 Notify 跨机依赖仍原样保留；它不是新 WR 完成事件已绑定的证明。

严格完整计时验收入口：

```bash
python3 -m hccl.tools.diagnosis.run_diagnosis manifest.json -o new-output \
  --require-complete-rdma
```

此选项不降低语义/图门禁。即使原链路通过，只要完整计时和 task 绑定未具备，返回非零，
`pipeline_result.json` 标为 `incomplete`，保留已成功生成的图和缺口报告。

## 当前 910C 为什么仍未完成

实际 AI_CPU 路径经 `TransportDeviceIbverbs::TxSendWrlistExt` 构造 WQE，
再由 `DispatcherAiCpu::RdmaSend` 下发 doorbell；它不调用上面的普通 post/poll 包装器。
`TransportDeviceIbverbs::TxWaitDone` 本身没有成功 CQ 完成轮询；现有 SQE profiler 也没有
单条数据 WQE 从开始到成功完成的硬件时间戳。部分普通 Write 未请求 CQE，也不能硬造耗时。

要完成该路径，仍需在**实际拥有完成队列的运行时/HCCP 层**获得成功完成证据，并将真实
QP/WQE 身份贯穿到对应 SQE/task；若要求纯硬件传输时间，还需配套硬件时间戳支持。
这是生产端可观测性的缺口，不是离线关键路径算法可以弥补的。不能另外开线程消费别人的 CQ，
不能把 SQ head 推进当网络传输完成，也不在本轮擅自替换服务器共享 HCCP 服务或驱动。

## 本轮验证

- 本地 C++14 编译并执行观察器 fixture，测试默认关闭、宽整数、部分提交失败、CQ 错误、
  上下文恢复及 WR flags 不变；这是 stub 测试，不是设备或网络传输测试。
- Node0 自有 `zjy-new` 中用实际 Linux verbs 头文件通过观察器的 C++14 语法检查；
  未部署新库，未使用 NPU，未替换运行时/服务。不等于整个 HCOMM Host/Device 构建通过。
- Python 诊断 266 项及 test 目录 108 项测试通过。
- 完成证据HTML在1500/720/390三种宽度通过浏览器检查，无页面错误或失效依赖图链接。
- 2026-10-22 双机 8MiB 小数据重新完整回放：512/512 语义 exact、144 条跨机 Notify 边、
  496 paired Wait、32 条协议区间。由于旧采集没有新 CQ 事件，严格完整计时验收正确返回
  `incomplete`，完成观测数 0。原有图的节点/边身份未改变。

回放目录：`test/out/rdma-completion-replay-20261028/nf-authorized-2n4r/`。
