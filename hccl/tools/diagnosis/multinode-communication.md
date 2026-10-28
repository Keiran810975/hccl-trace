# 多机通信诊断与时间线对齐

2026-10-28，适用于本地 `nf` 工作树。此次修改主要在 Python 采集控制和离线消费端，
不新增 NPU 打点任务，不修改驱动或共享 HCCP 服务；仍需实际加载原有配套 nf Host/Device。
代码、本地回归与旧数据回放通过，不代表已部署服务器或完成新的多机异常准确率实验。

## 能力与计时口径

| 输出 | 事实来源 | 含义 |
|---|---|---|
| 每 Rank 通信算子区间 | DB `COMMUNICATION_OP.startNs/endNs` | 直接采集的一次 collective 执行区间，不是 iteration 减计算时间 |
| Copy/Reduce/Notify/RDMA 小任务 | DB `TASK` + `COMMUNICATION_TASK_INFO`，再与语义 exact 合并 | 物理 task 时间、真实身份、Rank、phase/step、传输类型和数据量 |
| 已报告带宽 | `COMMUNICATION_TASK_INFO.bandwidth`，单位 Byte/s | 原 profiler 元数据；不使用短 RDMA SQE 时长重算带宽 |
| 带宽推导时长 | `size / reported_bandwidth`，仅 RDMA payload 且带宽有效 | **估计值**，不是新增的硬件完成时间，也不是独立于 profiler 的另一份证据 |
| 跨机协议区间 | 接收端准备 ACK 至接收端数据 Wait 结束 | 只沿现有唯一依赖路径，含调度、同步、数据传输和通知释放 |

DB带宽单位见[官方DB字段说明](https://www.hiascend.com/document/detail/en/mindstudio/830/TITools/Profiling/atlasprofiling_16_1144.html)。
`RDMASend` 的短时间条仍表示提交，不能称为纯数据传输时间。
单条 WQE 硬件起止时间、完整 AI_CPU CQ 完成绑定、网络拥塞的物理原因判定仍未实现，见
[完成事件边界](rdma-completion.md)。后台设备任务及普通计算/Event DAG的完整覆盖也不由本次修改补齐。

## 诊断规则

输入必须先通过原有语义、执行图与跨机通道门禁，不更改任何原始依赖边。
`run_diagnosis --iteration-map`在已有任务级分析之外增加：

1. **协议片段比较**：同 Rank 方向、算法/phase/step/slice、大小及路径结构，取前面连续5个
   正式 iteration 的同调用位置。重复位置、缺历史或缺路径均保留不可比较，不按最近时间配对。
2. **直接通信算子比较**：各节点/设备的实际 `COMMUNICATION_OP` 区间，与前5轮同调用位置比较。
3. **带宽估计比较**：只在现有任务结构比较已经独立提供5个唯一历史 task 时，比较对应的
   `size/bandwidth` 估计；字段名明确为 `bandwidth_proxy_slow`，不冒充真实执行时长增长。

三者沿用默认1.5倍及3*MAD，无绝对增量下限。前5轮不能比较不表示健康；持续故障污染
滚动参考、跨机采集不完整等限制仍保留。

协议变慢后，若已有等待回溯报告给出了指向该数据Wait的源头候选，报告为
`upstream_source_candidates`；否则保留 `cross_node_path_candidate`，物理原因仍为unknown。
它表示跨机片段异常，**不表示已证明网卡/交换机是根因**。不根据注入真值选择根因。

## 时间线怎样对齐

新采集在工作负载前、后各进行一批独立的CPU TCP双向探测，使用`CLOCK_MONOTONIC_RAW`，
不修改服务器系统时钟，不消耗完成队列，不插入通信库设备任务。

一次探测保存本地发送L1、参考节点接收R2、参考节点发送R3、本地接收L4。
仅由消息因果可得本地到参考时钟偏移范围 `[R3-L4, R2-L1]`。每批选择最小往返延迟样本，
使用前后锚点拟合近似仿射映射，不假定两方向网络延迟相等来宣称精确时钟。

每个设备的`host/start_info`、`host/end_info`须与本DB的`SESSION_TIME_INFO`严格对应，
再将该设备profiler时间转换到本机raw时钟。探测必须覆盖实际采集窗口，并覆盖所有节点/设备；
不同capture ID、缺一侧探测、超过1000ppm的速率差、估计误差超过容限均拒绝。
默认误差容限1ms，可在manifest显式设置整数`clock_alignment_max_error_ns`。

HTML统一轴使用参考节点raw时间，以可见采集任务的最早映射时间为0。**0不是某个iteration的开始。**
页头标明`Estimated aligned time`及估计误差。原始DB、图节点/边、原始时间和本地task耗时均不修改。
变换只用于展示；现有诊断仍使用本地时长和真实跨机拓扑，不据此计算纯传输时间或全局关键路径。

这是**软件网络探测估计对齐，不是硬件PTP精度保证**。误差估计包括探测延迟范围、profiler元数据
漂移和量化，不覆盖所有未建模的时钟非线性及Host/Device同步误差。微秒级因果结论不能超出其精度。
旧采集没有当时的探针，不能事后用现在的探针套用，也不能靠首task/首AllReduce平移伪装校准。

## 双机运行

先按[910C运行指南](../../../文档/910C双机实验运行与验收指南.md)准备两机相同源码/配置、
配套库、空闲设备和合法Device加载；本入口不会调整验签或操作他人任务。
沿用原`run-node`命令，两机增加以下选项，时钟端口须相同、空闲，且与前后台端口不冲突：

```bash
python3 test/two_node_suite.py run-node \
  --case /path/to/case.json --cluster /path/to/cluster.json \
  --node-rank 0 --output /path/to/runs --attempt capture-001 \
  --execute --timeout 1800 --diagnosis-capture --clock-probe-port 29860
```

第二台使用`--node-rank 1`。不要带`--no-profile`来验收完整诊断。
`--diagnosis-capture`记录独立的公开调用/准备/每轮设备同步边界，另记录实际执行的两次
配置检查AllReduce；关闭额外barrier，不把配置调用或后台组当业务调用。
时钟探测默认等待超时180秒，可用`--clock-probe-timeout`配置；与workload超时分别有界。
前后台注入开关仍按原入口显式授权，本次不自动启动测试集。

将两节点完整目录收集到同一`ATTEMPT/node0`与`ATTEMPT/node1`，这里是launcher序号；
实际物理节点名来自cluster，例如node0/node2。然后：

```bash
python3 test/bind_multinode_capture.py /path/to/ATTEMPT \
  --cluster /path/to/cluster.json --run-id my-run -o /path/to/new-bound

python3 -m hccl.tools.diagnosis.run_diagnosis /path/to/new-bound/manifest.json \
  -o /path/to/new-replay \
  --iteration-map /path/to/new-bound/iteration-map.json \
  --preparation-map /path/to/new-bound/preparation-map.json \
  --require-clock-alignment
```

绑定器只适用于本项目runner的完整公开序列，不是任意DDP训练插件。它要求所有Rank的配置/
业务日志一致、设备明确，校验DB命名调用计数、dtype/大小、通信域及完整CANN_API包络；
不使用task偏移或最近时间。输出中只隔离选中的前台DB及clock元数据，同盘优先硬链接，
不改原文件，不把后台DB编号补成业务调用。失败或重复输出目录拒绝复用。
自定义训练任务仍需独立提供符合合同的manifest、iteration/preparation映射及校时证据。

## 输出和查看

- `execution.html` / `waits.html`：原生任务与依赖；新增接收端`cross-node protocols`展示轨道。
  点击协议区间显示前5轮统计、诊断状态及真实任务按钮；该区间不是新hardware task、不增边。
- 原任务详情增加传输类型、RDMA角色、原带宽及带宽推导估计，保留原始task执行耗时。
  profiler端点编号须与exact语义的user/peer Rank一致，才能标记机内/跨机；否则保留未知，
  不把通信域内编号、全局Rank和设备编号混用。
- `cross_node/index.html` / `report.json` / `segments.csv`：片段判慢、覆盖、候选和原边ID。
- `cross_node/communication_ops.csv`：直接通信算子区间及滚动比较。
- `cross_node/communication_tasks.csv`：精确绑定的通信小任务、语义、带宽及代理比较。
- `clock_alignment.json`：每个device的映射、估计误差、原始证据文件哈希及适用窗口。
- `pipeline_result.json`：明确区分原图门禁、是否有校时、协议判慢、带宽代理和硬件计时缺口。

缺校时且指定`--require-clock-alignment`时，仍保留已生成图/报告，但状态为incomplete、返回非零。
`--require-complete-rdma`仍用于更严格的逐笔完成证据验收，当前AI_CPU不满足；不要与软件校时混淆。

## 验证范围

- 本地诊断278项、运行控制115项回归通过；浏览器6个页面/尺寸组合通过，未修改原有图门禁。
- 回归覆盖独立时钟、旧数据不伪对齐、探针过期/混用/不完整、缺历史、真实依赖回查、
  直接DB元数据、带宽代理、完整公开控制/业务绑定，以及实际本机TCP回环协议。
- 旧Node0+Node2 8MiB小数据重新回放通过：16个直接通信算子、1088条通信小任务元数据、
  32条协议区间、496 paired Wait，1300个原节点/1756条边与原始图完全一致。
  旧数据只有4次调用、没有校时探针，因此不宣称已对齐或已有新异常准确率。
- 校时回归fixture与真实数据在1500/720/390宽度通过浏览器、canvas像素及依赖跳转检查。
  fixture只验证机制，不是新NPU实验。服务器部署及新双机带校时采集尚待实际验收。
- 在Node0与Node1自有容器做了CPU双机探针验证，前后各16次，所选样本网络误差估计约
  0.08ms，临时服务正常退出。没有设置系统时钟或使用NPU，不证明Node1设备访问问题已解决，
  也没有将新探针套用到旧采集。证据见`artifacts/multinode-clock-probe-20261028/`。

最新回放证据位于`test/out/cross-node-diagnosis-20261028-final/`，
其中`synthetic-clock-fixture/`仅为回归数据。
