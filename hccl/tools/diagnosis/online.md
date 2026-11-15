# 在线集合通信诊断 V1

这是可选模式，不替换 `hccl-diag analyze` 或默认离线 Backtrace。现有训练 `Trace` 能提供
Host 调用前观测、通信器成员和计数，但不能直接取得设备真实完成时间。因此当前可以在线判
**缺席型 Hang（H1）**；已实现 Slow 的计算与报告接口，未接入实时 NPU 计时生产端。

## 启动

安装项目后，在能被各 Rank 到达的主机起一个收集器。先在本机回环测试：

```bash
hccl-diag-online --job-id train-001 --output ./online-train-001
```

在所有训练 Rank 的环境设置 `HCCL_TRACE_ONLINE_ADDR=127.0.0.1:7341`，
`HCCL_TRACE_RUN_ID=train-001`，保留原来的 `Trace`、设备 ID 和 `HCCL_TRACE_CALLS_DIR` 配置。
多机时用 `--listen <collector-private-ip>` 启动，让 Rank 设置该私有地址；服务端和所有 Rank
使用同一个通过秘密管理配置的 `HCCL_TRACE_ONLINE_TOKEN`。TCP 本身不加密，只在受信私网或
加密网络内使用，不对公网监听。未设置 `HCCL_TRACE_ONLINE_ADDR` 时不会启动探针。

`Trace.group()` 在各 Rank 使用相同名称和真实成员集。重建通信器时注册新的代次，不能在同一
代次重置计数。每个通信器需要完整且顺序一致的 `Trace.collective()` 覆盖，不能只标其中
几次。该观测点是调用包裹层，不宣称是 HCCL 内部函数入口；未打点的通信也不会被诊断。
训练调用不会等待网络或新加设备同步。队列过载会丢弃上报并显式记录缺口；该 Rank 的连续性
证据降级，需要启动新 job 才能恢复。并行提交的框架适配器可以直接使用
`OnlineProbe`，按真实提交次序登记并为异步完成保留返回的 `OperationToken`。

## 如何解读报告

- `NOT_ENTERED_HANG`：已有部分 Rank 进入，默认等待 30 秒另加 2 秒传输容忍；缺席 Rank
  有新鲜、连续的心跳，且计数确实停在上一次通信。用收集器单调时钟，无需跨机 Host 相减。
- `STALLED_UNKNOWN`：都已进入，健康遥测下仍未看到完成，不能区分设备停滞与计时未送达。
  断连、丢帧和通信签名不一致则报告 `INCOMPLETE_DATA`，不猜成 H1。没有通信开始时不报警。
- Slow 只对真实设备区间使用 `T_max > 3 × T_base`。正式第 0 轮用全部可比预热；之后用
  最近 20 个正常历史样本的中位数（可配）。异常不写回基线；无法匹配标记
  `INSUFFICIENT_BASELINE`。必要历史若因异步到达尚未完成，不能用未来样本填补。
- `COMPUTATION_SLOW` 和 `COMMUNICATION_SLOW` 是 `P` 启发式分类，不是物理根因。
  前者只把耗时最短的 Rank 列为疑似晚进入；后者在没有通信进度证据时不猜根因 Rank。
  证据不足、角色不明或 `P` 在中间区间时报告 `SLOW_UNCLASSIFIED`。

`telemetry.jsonl` 保存接收的帧，`events.jsonl` 保存按通信去重的报告。每条报告含 job、组、
代次、计数和语义位置，可与启用在线模式后 SDK 的 `online_op_counter`、
`online_communicator_generation` 对照；附 Rank 本地时间戳、时钟域、边界定义、误差和原始帧
引用。没有可靠公共时间轴时，全局时间为空。当前只提供离线回溯接口字段，不自动抓取依赖图。

## 设备计时适配和等价回放

适配器必须能证明某个 `OperationToken` 对应同一次设备通信的起点和终点（边界定义保持一致，
并包含定义范围内的协议等待）。它可在 `Trace.collective()` 内拿到 `Trace.online_token`，并用
`OnlineProbe.device_span()` 异步上报。还应提供节点内时钟域、角色、算法和误差估计。API 返回、
DDP Future 回调的 Host 时间和 `completion_boundary()` 的 Host 上界都不是设备结束时间。

有原始 SDK 调用观测和 consolidated DB 的归档，可在数据所在环境用同一套 Slow 判定做等价回放：

```bash
python3 -m hccl.tools.diagnosis.online_replay /path/to/capture --output ./online-replay.json
```

回放调用现有精确绑定器，使用 `COMMUNICATION_OP.startNs/endNs`，验证各 Rank 调用顺序；
它不读取注入标签，不从事后数据推断 H1，不把离线 profiler 区间声称为训练时实时可读。
输出包含基线、每次可比较通信的 `R`、告警，以及完整结果 SHA-256。评分应在封存之后单独完成。
