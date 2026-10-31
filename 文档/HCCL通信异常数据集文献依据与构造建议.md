# HCCL 通信异常数据集：文献依据与构造建议

## 1. 结论

当前项目最适合验证的不是笼统的“CPU、网络或硬件故障”，而是这些故障在 HCCL 内部造成的、
可由现有证据直接观测的通信异常。单机和多机使用同一套分类：

1. 指定 Rank、phase、step、task 的通信进度变慢；
2. 通信资源任务变慢：单机主要是 SDMA/Reduce，多机主要是 RDMA/RoCE；
3. 上游变慢导致 Notify Wait 延长；
4. 异常沿依赖边传播到后续 Rank、step、task，或者传播到其他节点；
5. plog、profiler 任务缺失或 task kind 错配等采集质量问题。

其中第 3、4 项是前两种根因注入产生的**诊断现象**，不应重复统计为独立的根因样例。
第 5 项是工具健壮性测试，不是论文中的运行时通信故障。

## 2. 单机版本

| 类别 | 异常含义 | 文献依据 | 数据集怎么构造 | 应诊断出的明确结果 | 当前成熟度与结论边界 |
|---|---|---|---|---|---|
| **A. 指定 Rank 的 HCCL 内部通信进度变慢（独立根因样例）** | 一个 Rank 已经进入 collective，但它在某个具体 phase、step 的 `Tx/Rx/Reduce/Copy` 任务上启动得更晚、推进得更慢或停顿一段时间。其他 Rank 本身可能完全正常，却必须等它，因此整个 AllReduce 变慢。这是“通信内部哪个细粒度任务先变慢”，不是笼统的“整个 Rank 很慢”。 | Mycroft 在 NCCL `sendProxyProgress` 中按概率注入 1 秒 sleep，观察到受影响通信组显著延迟；CCL-D 将网络波动、拥塞等造成的性能下降归为 `Communication-Slow`；Holmes 用异常通信算子的时长和 Rank 信息定位不规则执行。 | 在固定 AllReduce workload 中，只对一个已知 `rank/phase/step/event` 注入 10/50/100/200 ms 延迟，事件从 `Tx/Rx/Reduce/Copy` 中选择。保存无注入 baseline，并对每个强度重复多次。 | 1. 给出**第一个异常位置**：Rank、phase、step、event、物理 stream/task；2. 给出它相对 baseline 增加了多少时间，并区分“任务自身执行变长”还是“前驱到该任务的启动间隙变长”；3. 列出由它造成的下游 Wait。正确结果例如：`Rank 0 / allgather_direct / step 0 / tx_payload_start` 的入边间隙增加约 199.54 ms。 | **P0，已具备。** 910B demo 已完成此类验证。当前可以断言“该通信任务/进度首先异常”，不能只凭 HCCL trace 进一步断言它一定由网络拥塞、CPU 调度或硬件故障造成。 |
| **B. 本地通信资源任务变慢（独立根因样例）** | NPU 内真正搬运或处理通信数据的资源任务耗时异常，例如 SDMA copy 变慢、Reduce 运算变慢。它与 A 的区别是：A 可以是任务发起前停顿；B 重点要求 msprof 中实际 `sdma/reduce_inline/reduce_tbe` 任务本身或紧邻的资源执行区间出现异常。 | Mycroft 指出资源竞争会延迟 Reduce kernel，并以 background computation 作为代表性注入；GREYHOUND 的生产分析把 fail-slow 归因到资源竞争、设备降速和通信拥塞。 | 第一阶段在指定 `Copy/Reduce` 路径定点注入延迟，验证语义定位和传播。第二阶段运行竞争 SDMA、HBM 或 Reduce 资源的背景任务，验证真实资源耗时变化。分别覆盖 `sdma`、`reduce_inline`、`reduce_tbe`；多机后再覆盖 `rdma`。 | 1. 找到异常资源节点的 Rank、phase、step、task kind、stream/task id；2. 报告资源任务时长或相邻资源任务间隔相对 baseline 的变化；3. 给出该资源节点经 Record/Wait 影响了哪些下游资源任务；4. 对同类 Rank/step 排序，确认被注入节点是最早或最显著的异常点。 | **P0，已完成 910B 实测。** 在 NPU 0 上并发 4 个 D2D copy 负载后，工具精确定位到 Rank 0 的两个 `reduce_scatter_direct / step 0 / copy_start / sdma` 任务：61.25 us 分别增至 123.50 us 和 123.00 us，并找到 Rank 1、Rank 2 上增加约 53.08 us、50.68 us 的下游等待。该证据证明“SDMA 资源任务变慢并产生传播”；具体注入真值是 D2D copy 竞争，不能仅凭 HCCL trace 泛化为其他硬件根因。 |
| **C. Notify / 同步等待延长（派生诊断现象）** | consumer 已经执行到 Notify Wait，但 producer 尚未完成对应工作并发出 Record，所以 consumer 长时间卡在同步点。Wait 是“上游还没准备好”的表现，长 Wait 所在 Rank 通常是受害者，不一定是根因。 | Mycroft 的核心方法是追踪 collective 内部 control/data dependency；其 AllGather 示例显示慢 Rank 会令下一 Rank 等待数据。Holmes 也通过正常/异常通信算子的相互等待关系回溯上游。 | 不直接篡改 Wait 时长。复用 A/B 的 producer 延迟，选择 Record/Wait 两端完整、可唯一配对的 Notify channel，让长 Wait 自然产生；以 baseline 中同一 relation 的 Wait 作为对照。 | 1. 输出异常 Wait 的 Rank、phase、step、stream/task 和 `wait_span_ns`；2. 输出与它唯一对应的 Record、producer Rank、consumer Rank 和 relation id；3. 报告 Wait 相对 baseline 增长多少；4. 沿控制链指出 Wait 上游的资源任务和 Wait 完成后的下游资源任务；5. 标明配对证据是 `exact` 还是 `observed`。同节点时还可报告 `remote_block_ns`、`post_signal_ns`。 | **P0，已具备。** direct/local Notify 可 exact 配对，FFts 为 observed 证据。不能把“Wait 最长的 Rank”直接写成根因 Rank，必须继续回溯 producer。 |
| **D. 通信依赖链上的阻塞传播（派生诊断现象）** | 一个 Rank 的原始慢任务通过 Ring 的数据和同步依赖，使下一个 Rank 在后续 step 等待；后者又可能继续影响再下一个 Rank。最终多个 Rank 都变慢，但只有传播链起点是本次注入点，其余是被依赖阻塞的 Rank。 | Mycroft 展示了 Rank 0 传输慢导致 Rank 1、Rank 2 逐 step 级联变慢；Holmes 使用通信算子图回溯传播路径；CCL-D 强调异常传播后必须区分根因 Rank 与受影响 Rank。 | 复用 A/B 的单点注入，workload 至少使用 3 个 Rank。提前记录注入节点及根据 Ring 拓扑预期经过的 Rank/step；比较不同延迟强度和多次重复中的传播路径。 | 1. 输出按先后关系排列的完整路径，例如“Rank 0 异常资源任务 -> Rank 1 Notify Wait -> Rank 1 后续资源任务 -> Rank 2 Notify Wait”；2. 每条边给出 `stream_order` 或 `notify_sync` 类型及 `exact/observed/semantic` 证据等级；3. 标出**首发异常 Rank**和**受影响 Rank**；4. 报告每一级等待增量，检查延迟是否沿路径出现而不是在无关分支随机出现。 | **P0，单机已具备。** 910B 三 Rank demo 已得到 Rank 0 -> Rank 1 -> Rank 2 的传播证据；多机传播尚未完成，不能把单机结果外推成跨节点诊断已完成。 |

## 3. 多机版本

多机仍然诊断同样四类对象，只是身份中必须增加 `node_id`，资源任务的重点从本机
SDMA/Reduce 扩展到跨节点 RDMA/RoCE。多机验收不能依赖不同节点的绝对时间相减；若没有统一
时钟，只能使用每个节点本地的 task duration、Wait duration、顺序以及跨端共享 relation identity。

| 类别 | 异常含义 | 文献依据 | 数据集怎么构造 | 应诊断出的明确结果 | 当前成熟度与结论边界 |
|---|---|---|---|---|---|
| **A. 指定节点/Rank 的 HCCL 内部通信进度变慢（独立根因样例）** | 与单机 A 相同：某个 Rank 已进入 collective，但在具体 phase、step 的 `Tx/Rx/Reduce/Copy` 上首先变慢。区别只是该 Rank 位于某一台指定机器，延迟会影响远端 peer。 | Mycroft 的 NCCL proxy delay；CCL-D 的 `Communication-Slow`；Holmes 的异常通信算子定位。 | 在固定双机或多机 AllReduce 中，只对一个已知 `node/rank/phase/step/event` 注入 10/50/100/200 ms 延迟。其余节点不注入；保存每个节点的 baseline 与重复实验。 | 1. 定位首发异常的 node、Rank、phase、step、event、物理 stream/task；2. 在该节点本地计算任务时长或启动间隙相对 baseline 的增量；3. 找到远端 peer 的对应等待；4. 区分首发异常 Rank 和其他节点上的受影响 Rank。 | **P1。** 每节点语义合并和物理任务解析可复用，但当前跨节点 exact relation identity 尚未闭环。没有时钟校准时不得直接用两台机器的绝对时间戳相减。 |
| **B. 跨节点 RDMA/RoCE 通信资源变慢（独立根因样例）** | 某个 Rank 的跨节点发送或接收任务变慢，例如端口限速、共享链路背景流量或拥塞使 RDMA 数据完成得更晚。其他 Rank 的 NPU 可以是正常的，但会等待这条慢链路上的数据。 | Mycroft 的 NIC bandwidth limit 和 background traffic；GREYHOUND 的生产案例表明共享链路和网络拥塞会限制通信带宽；CCL-D 将其归为 `Communication-Slow`。 | 在独占或可控网络环境中，对指定节点/NIC/Rank 做带宽限制，或使用 perftest 等工具制造背景 RoCE 流量。记录注入端口、目标 Rank、限制带宽、流量强度和网络侧 ground truth。 | 1. 定位首先异常的 node、Rank、phase、step 和 `rdma` 任务；2. 报告该 Rank 本地 RDMA task duration、任务间隔或推进速度相对 baseline 的变化；3. 指出对应远端 peer 及其下游 Wait；4. 用限速配置、吞吐或 CNP 等外部指标确认“网络拥塞/限速”根因。 | **P1。** 当前工具能保留 `rdma` 任务并生成资源节点，但仅凭 HCCL/msprof 只能证明“RDMA 路径变慢”，不能独立证明是交换机拥塞、NIC 故障还是背景流量。 |
| **C. 跨节点 Notify / 同步等待延长（派生诊断现象）** | 与单机 C 相同：consumer 已到达 Wait，而另一台机器上的 producer 尚未完成发送或同步，因此本地 Wait 变长。长 Wait 所在节点通常是受害者，真正异常可能在远端 producer。 | Mycroft 的 Coll-level control/data dependency 和跨节点等待；Holmes 根据通信算子及 peer 关系回溯上游。 | 不直接修改 Wait。复用多机 A/B 的上游延迟或 RDMA 限速，让远端 Wait 自然增长。选择能够用跨端共享 relation identity 唯一对应 producer/consumer 的 channel。 | 1. 输出 consumer 的 node、Rank、phase、step、Wait task 和本地 `wait_span_ns`；2. 输出远端 producer 的 node、Rank 和对应 Record/资源任务；3. 报告 Wait 相对本节点 baseline 的增长；4. 标明跨节点时序为 `cross_node_uncalibrated`，不输出未经校准的 `remote_block_ns/post_signal_ns`。 | **P1。** 本地 Wait duration 可以计算，但跨节点 producer/consumer 的唯一配对仍需补共享身份；不能按“时间最近”猜边。 |
| **D. 跨节点通信依赖链上的阻塞传播（派生诊断现象）** | 与单机 D 相同：一个 Rank 的原始慢任务逐步阻塞其他 Rank；区别是传播路径会跨越机器边界，例如节点 A 的 Rank 0 使节点 B 的 Rank 1 等待，节点 B 又影响节点 C。 | Mycroft 展示异常通过通信和计算依赖传播到其他机器和通信组；Holmes 使用通信算子图追踪影响；CCL-D 区分根因 Rank 和传播后的受影响 Rank。 | 复用多机 A/B 的单点注入，至少使用两台机器，并让 Ring 邻接关系跨节点。提前记录预期拓扑路径，比较多次重复和多个延迟强度下的传播结果。 | 1. 输出包含 node、Rank、phase、step 的有序传播路径；2. 每条跨节点边给出 relation id 和证据等级；3. 标记首发异常节点/Rank与后续受影响节点/Rank；4. 分别报告各节点本地 Wait 增量，不能把未校准的跨节点时间差累计成全局关键路径。 | **P1。** 图模型可以表示多个 node，但现有 DB 字段是否足以唯一配对跨端关系仍需真实多机数据验证；当前不能声称多机传播已经验收。 |

## 4. 文献原文对应关系

- [Mycroft](https://arxiv.org/html/2509.03018v1) 的实验包含 NIC shutdown、NIC bandwidth limit、
  PCIe downgrading、GPU power limit、background computation、background traffic 和 NCCL proxy
  delay；与本项目最直接对应的是 proxy delay、background computation、bandwidth limit 和依赖传播。
- [CCL-D](https://arxiv.org/html/2605.04478v1) 将异常分为
  Not-Entered-Hang、Inconsistent-Hang、Hardware-Fault、Computation-Slow、Communication-Slow
  和 Mixed-Slow，并使用细粒度通信状态定位受影响 Rank。
- [GREYHOUND](https://www.usenix.org/system/files/atc25-wu-tianyuan.pdf) 的生产测量表明，
  通信 fail-slow 主要由网络拥塞引起，并观察到共享链路导致通信带宽被限制。
- [Holmes](https://www.usenix.org/system/files/nsdi25-yao.pdf) 从通信算子日志检测异常算子，
  再用通信算子图区分网络通信异常和上游计算延迟造成的等待。

## 5. 单机与多机通用的工具健壮性数据集

下面三项应单独命名为 `trace_quality`，不能与真实通信异常混在同一个准确率分母中。

| 质量异常 | 含义 | 构造方法 | 应诊断出的明确结果 |
|---|---|---|---|
| semantic plog 缺失 | msprof 中物理任务仍存在，但描述其 Rank/phase/step/event 的 HCCL 语义记录丢了。工具不能再说明这个物理任务在算法中的含义。 | 从完整样例删除指定 Rank/phase/step 的若干 `[HcclTaskSemantic]` 行。 | `profiler_only` 数量相对 baseline 增加，semantic 总数和覆盖率下降；这些节点可保留为物理任务，但不能被伪造语义或强行加入精确依赖关系。 |
| msprof task 缺失 | plog 声称某个语义任务已产生，但 profiler 数据中找不到对应的物理 task，可能是采集不完整或关联数据丢失。 | 从 consolidated DB 的副本删除已知物理 task。 | `unmatched_semantic` 增加、exact 匹配率下降；低于门槛时门禁必须失败，并指出缺失语义对应的 Rank/phase/step/event。 |
| task kind 错配 | plog 与 profiler 指向同一个身份候选，但一侧认为它是 SDMA，另一侧却是 Notify Wait 等不兼容类型。若继续匹配会把错误任务连进依赖图。 | 在 DB 副本中把一个 SDMA/Notify 等 task kind 改成不兼容类型。 | 输出 `correlation_kind_mismatch` 或 FFts context kind mismatch、`invalid_matches` 增加；该记录不得算作 matched，也不得据此生成因果边，门禁应失败。 |

这组测试证明工具面对坏输入时“不乱匹配、不伪造依赖”，但不能证明运行时 HCCL 故障诊断能力。

## 6. 暂不纳入当前核心验收的异常

| 异常 | 文献依据 | 暂缓原因 | 后续条件 |
|---|---|---|---|
| **NIC/链路掉线导致 hang** | Mycroft 的 NIC shutdown；CCL-D 的 Hardware-Fault | 当前工具是离线诊断，采集可能因 hang 不完整；缺失端点也可能来自 trace 丢失，不能直接等价为 NIC 故障。 | 独占测试环境、超时与恢复脚本、跨节点采集完整性标记、NIC 状态 ground truth。 |
| **Rank 未进入 collective** | CCL-D 的 Not-Entered-Hang | 当前 artifact 能看到缺任务或 boundary，但不能可靠区分“未进入”与“日志/Profiler 丢失”。 | 增加每 Rank collective invocation 完整性清单。 |
| **不同 Rank 调用不一致** | CCL-D 的 Inconsistent-Hang | 当前 operation scope 可隔离调用，但尚无跨 Rank 的 op type/count/size 一致性诊断。 | 增加 communicator 内 operation 类型、序号、数据量的一致性检查。 |
| **CPU 抢占、数据加载慢、GPU 降频** | CCL-D 的 Computation-Slow；GREYHOUND 的 CPU contention/GPU thermal throttling | 它们会表现为 Rank 晚进入通信，但项目没有 CPU、数据加载或温度/频率指标，无法从 HCCL trace 唯一归因。 | 与系统指标或训练框架 trace 联合后再纳入根因分类；当前最多标为 `late_entry/communication_progress_delay`。 |

## 7. 建议的样例组织

单机以固定的 3 Rank 或 8 Rank AllReduce 为 baseline；多机以固定的节点数和每节点 Rank 数
为 baseline。两者都固定算法、数据类型、消息大小、warmup 和迭代数。每个样例保存：

- `case_id`、单机/多机类型、算法、节点数、Rank 数、消息大小和迭代号；
- 注入的 `node/rank/phase/step/event`、延迟强度、开始和结束时间；
- 预期首个异常任务、预期下游等待节点和传播 Rank；
- 原始 plog、consolidated msprof DB、`merged.csv`、execution/resource graph；
- 是否准确定位 Rank、phase、step、task，等待增量和传播路径是否符合预期。

建议把数据集拆成三组：

1. `single_node/runtime_root_cause`：单机 A、B 两类独立根因注入；
2. `multi_node/runtime_root_cause`：多机 A、B 两类独立根因注入；
3. `derived_diagnosis`：从同一次采集评估 C、D 两类等待与传播结果；
4. `trace_quality`：plog 缺失、msprof 缺失、kind mismatch，单机和多机分别统计。

这样可以避免把同一次延迟注入重复计算成三次根因诊断成功，也符合当前项目“离线证据与依赖解释”
的实际能力边界。
