# 短 Copy 固定采集与离线溯源修复

## 本轮结果

仅用 Node0+Node3 自有 `zjy-new` 的 NPU4..7，各4 Rank。负载为128MiB FP32 SUM
AllReduce，10轮预热+20轮正式，不是GPT训练。目标为正式第10轮（0基）、Node3 Rank4。
单个后台线程使用独立ACL流，仅执行一次D2D Copy；初始化提前，校验与销毁推迟至测量结束。

| 尝试 | 注入 | 实测设备Copy | 目标Rank通信区间 | 结果 |
| --- | --- | --- | --- | --- |
| 240 | 提交后64MiB Copy | 0.101640ms | 5.677340ms | 完全重叠，但早于主要搬运；无明显执行慢化，保留阴性结果 |
| 241 | 提交后后台等待2200μs，再512MiB Copy | 1.332140ms | 6.080160ms | 完全落在通信内；Rank4自身最多1.02684倍，Rank5 Reduce达到1.50271倍 |

241是依据240前5个正常轮次搬运时序做的一次有界位置校正，属于探索性调试，不是独立重复。
Copy设备区间来自真实msprof SDMA task，不能把Host调用包络当设备时长。
八Rank数值检查、语义精确合并、图门禁通过；10560个Wait全部paired、1440条跨机Notify边。
后台Copy没有伪造HCCL语义或资源依赖边。

## 修复的主要错误

旧回溯在遇到“自身耗时正常，且相对本次通信起点未晚到”的Record或其他正常中间任务时，
以`normal_reference_boundary`停止。不同轮次整体进入时间可以提前，掩盖局部执行增量；
正常Record不等于其前驱没有变慢，短Wait也可以沿本流继承延迟。

policy7不再以此作为停止依据。沿原有唯一stream order和Notify依赖继续回溯；
遇到真正已经提前就绪的信号、时间矛盾、缺边/多生产者、缺少轮次身份或跨轮，仍明确停止。
任务自身慢化仍由前5个正式轮次同定位均值、1.5倍和3MAD判断，不读注入真值。

241修复前内部候选0，修复后1，首选是Node3 Rank5 / stream90 / task1539：

| 环节 | 正常前5轮均值 | 当前 | 增量 |
| --- | --- | --- | --- |
| Rank5 `reduce_scatter_direct` step1 Reduce | 232.6676μs | 349.633μs | 116.9654μs |
| Rank4 step2 ACK Wait | 0.020μs | 110.660μs | 110.640μs |
| Rank6 step2 data-signal Wait | 0.020μs | 116.880μs | 116.860μs |

上述两条路径分别为2条和4条真实依赖边，都是连通的本机传播证据。另有一条20边的
跨机拓扑路径到Rank1长Wait，明确标记时间证据受限；不宣称逐笔RDMA完成时间或确定因果贡献。
并发Wait增量不能相加为整个负载损失。

**仍不能把本例报为原注入评测成功**：注入在Rank4，慢任务在Rank5，按原同Node/Rank正重叠
标准是0/1。Rank5慢任务整个区间与背景Copy重叠，但不证明物理资源竞争原因；
需要进一步验证远端内存/资源共享关系，不能为提高准确率把根因强行移到Rank4。

## 兼顾孤立任务与噪声

- 可独立配置`--source-slowdown-factor`与`--wait-slowdown-factor`，默认均1.5。
- `--completion-fallback`可保留没有长Notify Wait的执行源头，但须存在可信HCCL归属、
  自身执行慢化、同Node/Rank/调用完成区间也明显变长，以及到真实完成端点的依赖路径。
  输出`local_completion_supported_candidate`，不冒称有Wait传播；缺路径或被松弛吸收则仍未归因。
- `--calibrated-release-intervals`使用独立采集的各设备profiler→RAW偏移和元数据量化误差，
  不再直接比较不同设备原始epoch，也不把Record.stop当精确通知时刻。区间相容只是候选证据，
  不确定性明确输出；真正矛盾依然保留，绝不按时间最近补边。
- 回放使用私有复制而非硬链接，防止重写校时元数据污染保留的原证据。每次回放验证全部原artifact
  SHA256不变，记录分析器模块SHA256；输出目录必须全新。

在两份固定采集上回放：源头/Wait=1.5/1.5、1.5/1.1、1.2/1.1，内部候选均为240=0、241=1。
241降低Wait阈值后回溯数301→466，未新增内部源头；不据此修改默认阈值。
残余时间矛盾、无细粒度语义的控制任务以及RDMA完成未观测仍存在，不能宣称证据链已全部补齐。

## 产物与重放

本地根目录为`test/out/short-copy-20261101/`：

- `retained/240`、`retained/241`：两机完整压缩包、逐文件SHA256、解包事实和原三报告。
- `final-replays/241-strict/report/`：本轮推荐查看的execution.html、root_causes.json、propagation.html。
- `final-replays/*/replay-receipt.json`：原事实及消费者代码哈希、参数和覆盖度。
- `final-replays/241-strict/independent-audit.json`：独立的注入重叠及原同Rank规则评测。
- `experiment-plan/`：两次采集选择历史、阴性结果、门禁和离线消融记录。

```bash
python3 -m test.replay_fixed_trace \
  --root test/out/short-copy-20261101/retained/241/node0/facts \
  --output test/out/short-copy-20261101/replay-NEW --intervals
```

分析器不接受注入窗口；`test.audit_short_trace`仅在诊断报告生成后独立读取真值评估。
服务器240/241两机原始数据均保留，存在`retain-all-evidence.json`禁止清理。
服务器Node0根为`/home/commTeam/zjy/zjy-new-workspace/hccl-diagnose-node03-20261101-241`，
Node3根为`/home/zjy-new/workspace/hccl-diagnose-node03-20261101-241`；240同样替换后缀。

## 恢复与验证

241采集和诊断通过，但Node0自连管理IP的SSH重置导致自动恢复调用失败。
保留原`authorized-state.json`错误记录，随后经已验证相同主机密钥的本机loopback SSH入口
执行原Guard恢复并再次实读：NPU4..7原False/5、官方包哈希一致、registry不存在、timer inactive、
holder released。另存`recovery-verification.json`，未伪改原失败状态。Node3正常恢复。
240也已恢复。未停止外部任务，未改其他卡或宿主共享安装。

本轮358项诊断回归及42项采集/保护专项通过；没有以固定样例调参结果宣称一般准确率提升。

## 后续离线核实

继续调查未启动任何NPU负载、未连接服务器改环境，原240/241数据和此前报告不覆盖。
最新报告为`test/out/short-copy-20261101/investigation/241/report/`。

### 执行位置不等于通信对端或物理故障位置

原始DB按device3/stream90/task1539/startNs和TaskIndex精确核对，只有一条
`Reduce_Inline`记录，size=33554432（32MiB）、transportType=0（DB枚举SDMA），
srcRank=5、dstRank=4；语义为`link_rx_payload_reduce`、peer_rank=4，执行Rank为5。
这些rank字段不能未经解释就当成网络字节的发送/接收方向。
当前concurrent-direct模板对应的inline-reduce路径使用`GetRemoteMem(INPUT_MEM)`和对端link，
所以对端资源影响本地执行存在实现依据；但DB未提供本次读写地址或资源争用计数器，
仍不能证明后台Copy导致了它，也不能把Rank4提升为已证实的故障位置。

公共JSON及HTML已增加`communication_context`，同时展示执行Rank和由同次operation唯一参与者
确认的语义对端。`peer_is_proven_fault_location=false`；原同Rank注入评测仍0/1。
同时公开本地调用是否满足整体慢化条件、局部关键路径模型收益和
`workload_completion_impact_proven=false`。本例的局部任务及Wait变慢，但本节点调用整体
未达到1.5倍条件，局部模型收益为0；不再让读者把候选误解为整个负载已经受损。

### 慢Wait并非都缺边

本例301个慢Wait全部有唯一通知配对，回溯未发现缺失/歧义前驱；其中3个关联到内部源头，
165个的某条上游路径遇到时间矛盾。这些统计并非互斥分类。
133条不同的矛盾配对，其Record开始晚于Wait结束的超预算量中位数32.504μs，
90分位67.998μs、最大70.139μs；不应靠扩大到几十微秒的容忍量强行消除。
同设备配对未发现这类开始/结束矛盾。允许每设备任意常量偏移的约束可行性检查不能排除
跨设备时钟偏差解释，但**没有由Notify依赖反推/应用校时模型**，必须另有独立设备校时证据。

新增`arrival_observation`：只沿现有唯一Notify配对及同定位前5轮记录，使用已校准同节点RAW
时域记录等待方/通知方的相对到达变化。跨机、历史不完整、FFTS、时间矛盾不做这种解释。
“等待方提前而通知方未观察到晚到”只是时序观测，不能生成源头候选或证明物理原因。
240有2条、241有1条符合完整检查的此类观测；不能把未通过检查的其余Wait都归入该原因。
coverage现在区分配对数量、真正缺边数量、时间矛盾及已关联源头数量。

### 纯净GPT负控结果不支持直接宣称精度提高

从已逐文件校验留存的201纯净GPT采集中，在读取候选结果前固定选择正式第10、45轮，
各自带此前5轮历史、每轮13个公开调用。仅复用原图节点/边和绑定，不重建依赖。
窗口分别66768个节点、93560条边；1328条出入窗口边界边明确省略。
历史行只供参考，结果不是全50轮重放或总体准确率估计。

| 目标正式轮次（0基） | 存档policy6候选 | policy7原阈值候选 | policy7启用校准区间 |
| --- | --- | --- | --- |
| 10 | 7 | 17 | 17 |
| 45 | 0 | 2 | 2 |

各版同窗口的任务比较结果SHA256完全相同，差别来自回溯而不是改阈值、任务时间或参考样本。
旧消费者取自已验证归档；当前消费者先冻结独立源快照再运行，保存逐模块SHA256。
多数新增任务有5～130μs的自身执行增量及相近的Wait增量，不能解释成纯粹的纳秒舍入噪声，
也不能仅因为未注入就判定物理环境绝无异常。但在“纯净组不应报警”的用途下，这清楚暴露了
候选范围扩大风险，**本次修复提高可追溯性，不等于提高特异性**。
19个任务候选均未满足节点上整次调用1.5倍慢化条件；也不代表这些局部变化没有意义。
保持原1.5倍/3MAD和全部候选，不针对该负控选择阈值或删候选。

证据目录：`normal-audit-01/`、`normal-policy-comparison-02/`，位于本地短Copy根目录下。
后者`summary.json`记录对照，`consumer-snapshot.json`记录当前消费端快照；
`test.audit_normal_windows`和`test.compare_normal_policies`为可复用有界CPU审计入口。
后续需要独立设备时间校准证据，以及更干净/重复的正常负载对照，才能评价故障报警精度。
最新361项诊断回归和新增原DB身份只读审计测试通过。
