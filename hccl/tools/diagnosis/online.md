# 在线集合通信诊断

可选功能，默认关闭，不替换 `hccl-diag analyze`。这一版的验收范围是样例的显式 FP32 SUM
AllReduce：H1 报缺席 Rank；S1 需要独立的本地准备延迟证据；S2 只报告通信实例。它不做
物理故障定位，也不为异步 DDP hook 或所有 HCCL 算法自动插入探针。

## 启动和报告

```bash
hccl-diag-online --job-id train-001 --output ./online-train-001 \
  --expected-ranks "$WORLD_SIZE" --expected-collectives "$TOTAL_COLLOPS" --warmup-iterations 10
```

`TOTAL_COLLOPS` 是各 Rank 共同执行的操作数（含预热），不是乘 Rank 数之后的记录数。
样例按实际梯度桶数乘 `(warmup + iterations)`；不计单独的启动步。输入不会自动从已经收到的
数据推断，以免缺失消息被当作正常。
本机使用 `HCCL_TRACE_ONLINE_ADDR=127.0.0.1:7341`；多机时收集器 `--listen` 绑定受信私网地址，
各 Rank 指向该地址，并用同一 `HCCL_TRACE_ONLINE_TOKEN`。TCP 本身不加密。各 Rank 的
`HCCL_TRACE_RUN_ID` / `hccl-diag capture` 的 run ID 必须与 `--job-id` 一致。

- 默认 `HCCL_TRACE_ONLINE_TIMING=host`，能判 H1；缺少设备计时只计为覆盖问题。
- 样例设置 `HCCL_TRACE_ONLINE_TIMING=npu_event`，启用 `torch_npu.npu.Event(enable_timing=True)`。
  两枚 Event 记录在同一消费流：第一枚在 `Trace.call_collective()` 进入提交前，第二枚在原有
  `Work.wait()` 之后；读取发生在训练原有 `npu.synchronize()` 之后，且必须通过两个 `query()`。
  `wait()` 不计入 SDK 的 Host 提交区间。设置此模式但适配器不可用、Event 未就绪或结果非法时，
  启动或首次读回会失败，不静默退回 Host 时间。Event 模式默认在注册在线探针前做 3 个真实
  训练启动步（`--online-startup-iterations` 可显式指定），一起预热通信器、算子和 Event 读回。
  启动步会更新模型，不占用在线计数或基线；之后仍保留全部指定预热。每步复用原同步点，
  新增的是这些启动步和每次通信的两枚设备 Event，不是给正式通信增加同步。
- 所有准备和延迟必须发生在 `Trace.call_collective(submit, ...)` 之前；`submit` 只做实际
  `dist.all_reduce`。在线模式拒绝用任意 `with trace.collective()` 块作为 ENTER。这个边界是
  Python 显式调用的入口，不是 HCOMM 的原生函数入口。

`telemetry.jsonl` 保存原始帧；`events.jsonl` 保存诊断和证据不足事件；`measurements.jsonl` 包括
正常轮、预热、异常和缺失覆盖，保留 `R`、可定义时的 `P`、历史及 Rank 本地数据。
`run_health.jsonl` 在预期 Rank 结束时（或收集器退出时）给出一次 `RUN_HEALTH`：确认 Rank、
丢失序列、声明的丢弃数、计时覆盖、完整预热及预期通信数，同时记录 Host 写盘耗时与收集器
锁等待。`acceptance_ready` 只是数据门禁，不代表异常检测已通过。正常退出要求收集器对最终
序号和计数回 ACK；缺 ACK、重连、丢帧或应用异常使结果不能通过完整性验收。不重传，也不支持
收集器热恢复；重启需使用新的 job 和输出目录。序列缺口和发送端丢弃数是两种观测，不能相加。
H1 后能由已知更早计数阻塞解释的通信会有界保留。恢复后记为 `COMPLETED_AFTER_BLOCK`，照常计入
完成覆盖但不更新基线；恢复期限内始终缺数据、心跳/遥测不可靠、或结束仍未完成，不算恢复成功。

## 在真机上核验边界

Event 模式首次运行**不设置验证配置**。`elapsed_time()` 给出持续时间，收集器保留
`start_ns/end_ns=null`，不会编造绝对时间。它测的是 `consumer_stream_collective_v1`；
能包括排队、跨流依赖与提交间隙，不能未经实测宣称等价于 HCCL 的 `COMMUNICATION_OP`。
保留同一运行的 msprof 和在线记录，再做精确绑定对照：

```bash
python3 -m hccl.tools.diagnosis.online_timing_audit /path/to/capture ./online-train-001 \
  --output ./timing-comparison.json
```

对照输出逐 Rank 的两种计时、差值、比例和 profiler 观测到的 `algType`，不会自动认证边界或
猜算法。需在固定的软硬件栈、拓扑与 AllReduce 配置上独立核验 `Work.wait()` 的依赖、从流
完成边界和正常/S1/S2 下两种计时的行为，才能标记为已认证计时。报告慢化不依赖这项认证。
如果其他同形状桶导致全量绑定失败，可以在命令上加 `--bucket gradient.bucket.0` 只审计该桶。
目标桶仍要覆盖全部 Rank，而且每条 SDK 调用与原生记录必须双向唯一。其他桶照样参与歧义检查，
不会因不在输出中就被忽略，也不会按顺序猜配。
完成后往所有 Rank 提供同一 `HCCL_TRACE_ONLINE_TIMING_PROFILE` JSON 文件，并用
`HCCL_TRACE_ONLINE_STACK_ID` 锁定这次人工核验的环境标识。配置字段：

- `schema_version: 1`、`timing_definition: "consumer_stream_collective_v1"`、`stack_id`、
  `torch_npu_version`、`boundary_evidence`（独立验收报告标识）。`stack_id` 应覆盖明确核对过的
  CANN/HCCL/设备/拓扑配置，它不是运行时自动硬件认证。
- `communicator_id`、`participants`（有序全局 Rank 列表）；`buckets` 以 `call_site` 为键，
  每项含 `tensor_bytes`、`dtype`、`reduction`、核验后的 `algorithm`，以及以 Rank 字符串为键的
  `rank_roles`。没有经核验的角色不得写成同类。各 Rank 的配置 SHA 必须一致。
- 只核验了目标桶时，显式设置 `allow_unprofiled_buckets: true`。其他桶仍采集并报告慢化；
  已核验桶的输入形状变化仍报错。`verified_timing_by_site` 可核对该桶覆盖，全局完整验收仍要求
  所有预期通信都有认证计时。仅看到相同 `algType` 不能证明 Rank 角色或计时边界已核验。

公式仍为 `R=(Tmax-base)/base`（严格 `R>2` 才慢），`P=(Tmax-Tmin)/(Tmax-base)`。
每个可比位置必须收齐全量预热，乱序到达先缓存。如果预热中的最大值超过其中位数三倍，
整条基线不可用，不删某条来凑结果。正式第 0 轮用全部预热，之后只用较早的正常历史，
最多最近 20 个。S1 要求 `P>0.6`（允许 `P>1`，不截断）且唯一耗时最短 Rank 的本地准备增量独立超过历史阈值
（1 ms、历史中位数的 50%、3 MAD 取最大）；准备区间可能包含前序等待，不证明计算核变慢。
S1 的独立准备证据不再因 Rank 角色不同而被跳过；同钟的入口次序与怀疑 Rank 矛盾时仍不定位。
没有支持 S1 的证据时，以 `COMMUNICATION_SLOW` 报告该通信，不推断故障 Rank。相同已知角色且
`P<0.4` 是相近耗时证据；不同已知角色可以用 `g_r=(T_r-base_r)/base_r`，各 Rank 均 `g_r>2`
且 `P_relative=(max(g)-min(g))/max(g)<0.4` 时是共同慢化证据。无法确认机制时标记
`classification_evidence=slowdown_only`，计时认证状态另记在 `timing_boundary_verified`；不等于证明 RoCE 或其他物理故障。

## 从在线告警追到离线 Task

同次运行需要同时保存 `hccl-diag capture` 的 HCOMM 语义、msprof DB、SDK 调用记录和在线收集器的
`events.jsonl`。在线耗时日志本身不能还原设备依赖。离线命令：

```bash
hccl-diag analyze ./capture --online ./online-train-001 -o ./report
```

也可将 `online/` 放在采集目录里，或和名为 `capture/` 的目录并排，原 `analyze` 命令会自动发现。
离线仍用同次采集的历史作比较，通过 job、通信域代次、操作序号和完整 Rank 调用做精确关联；
无法唯一绑定的告警保留为证据不足，不用桶顺序或邻近时间代替。`root_causes.json` 的 `online_followup`
及 `propagation.html` 的「在线告警离线追查」列出每个 CollOp 的慢 Task、慢 Wait 和关联候选。
S1 额外显示有证据的 Host 准备区间与晚开工；通信慢化保留从慢 Task 到下游慢 Wait 的已有路径，
允许路径到达另一个 CollOp。缺少真实生产者或跨钟顺序不可判时只报边界，不断言物理根因。
不提供在线产物时，默认离线 Backtrace 的行为不变。

## 验收矩阵

| 项 | 固定测试及通过条件 |
| --- | --- |
| T0/T1 | 两机全 Rank，10 预热 + 50 正式。拿到完整计时与算法对照，无无故 H1/S1/S2。 |
| T2 | 目标 Rank 在指定正式轮/桶调用前延迟 40 s，心跳继续；报告正确通信和缺席 Rank。 |
| T3 | 同样位置用 0.1 s 调用前延迟。独立记录确实晚进入，再核查 `R/P` 与 S1 Rank；不达阈值算未检出。 |
| T4 | 在专用实验环境独立施加并核验 RoCE 异常；先核查目标 CollOp 是否真正超过 3 倍，再看 S2，不按注入结果改阈值。 |
| T5/T6 | 人为丢失或重连：完整性失败，不当成确定异常。正式耗时早于最后预热到达：先不分类，补齐后重判。 |
| T7 | 同栈、同桶、同轮数对照关闭/Host-only/Event 三档；先固定开销预算，比较正式 step 时间和 AllReduce 时长，另核对写盘与锁等待。 |

T2/T3 可给样例传 `--acceptance-host-delay 4,12,0,40 --acceptance-evidence /path/to/new-evidence.json`，
T3 将 `40` 换成 `0.1`。索引从 0 开始，文件由目标 Rank 在调用前记录实际 Host 延迟，
不发送到检测端。T4 的注入在检测链之外，不自动修改网卡。先封存诊断与健康报告，再读取真值。

给旧采集做仅 Slow 的离线等价回放可用
`python3 -m hccl.tools.diagnosis.online_replay /path/to/capture --output ./online-replay.json`。
回放不读注入标签，也不把离线计时当成实时可用。新 Event 路径需通过上面的真机验收后才能宣称支持。

参考：[昇腾 WorkHCCL 等待实现](https://gitee.com/ascend/pytorch/blob/4c0820c212ba419ce4926ca85560a7233e9c2f85/torch_npu/csrc/distributed/ProcessGroupHCCL.cpp)、
[MindStudio 的 Profiler DB 字段说明](https://www.hiascend.com/document/detail/en/mindstudio/830/TITools/Profiling/atlasprofiling_16_1144.html)。
