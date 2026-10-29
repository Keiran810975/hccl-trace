# HCCL fine-grained trace diagnosis

## 用户诊断入口

安装后用 `hccl-diag analyze --capture DIR --mode rolling --output RESULTS`，或
`--mode baseline --baseline NORMAL`，一条命令执行完整离线诊断。默认最终仅保留
`execution.html`、`root_causes.json`、`propagation.html`；临时分析自动清理，原始输入只读。
通用 SDK、任意实际节点/Rank/设备配置、双模式规则及已知边界见
[诊断工具使用说明](../../../文档/诊断工具使用说明.md)。旧开发/实验入口继续兼容。

开发入口：[活动任务](task.md)、[实现规格](spec.md)、[阶段归档](arch-94a1ab31c3ee.md)。
双机配置、容器、运行和样例验收见[910C运行指南](../../../文档/910C双机实验运行与验收指南.md)。
`nf` 已整合 `codex/ring-nhr-diagnosis@6312667` 的 AI_CPU、控制事实、同机/跨机 RDMA
及等待诊断，保留 master 的默认选路修复和本地关键路径。历史设备结论只对应原场景，
本次四机验收进度见 [活动任务](task.md)。
代码与真实设备验证边界见 [nf四机验证记录](nf-four-node-validation.md)。
Node0+Node2正常小负载的配套AI_CPU语义、跨机依赖和等待诊断已通过，
详见[授权双机验收](nf-authorized-two-node-validation.md)；两机原验签及官方Device包均恢复。

## 完整多机回放

多机协议判慢、直接通信算子/小任务元数据及带误差说明的软件时钟对齐见
[多机通信诊断与校时](multinode-communication.md)。新采集可通过`run-node --diagnosis-capture
--clock-probe-port 29860`保存完整公开调用和前后探针，再用`bind_multinode_capture.py`生成映射。
`run_diagnosis --require-clock-alignment`拒绝缺少适用校时的采集；旧数据不会被事后平移成已校准。
软件对齐只用于展示，不等于PTP精度、逐WQE硬件计时或跨机全局关键路径。

```bash
python3 -m hccl.tools.diagnosis.run_diagnosis run.json -o replay
```

输入清单必须提供各节点原始 plog/DB、真实 rank/device 映射及有调用证据的 operation 绑定。
通过语义和图检查后才输出诊断 JSON/CSV、节点本地关键路径及 execution/waits/resource HTML。
正常样例没有异常基线时不硬报根因；跨节点无时钟校准时不累计全局路径。
已有正常参考可通过 `--baseline-dir` 传入，基线须是相同 workload 配置。
传入后自动生成 `comparison/index.html`、全量任务增量与源头候选 JSON/CSV、
以及源头局部的 Baseline/异常交互 HTML 和同尺度 SVG 对比图。
已有 artifact 也可直接运行 `compare_diagnosis`；规则、阈值与边界见
[Baseline自动对比说明](baseline-comparison.md)。

本轮单机21例实验改用 `--iteration-map public-call-map.json`：参考同次运行前5个正式iteration
同定位任务的均值，不设绝对增量下限，不传外部Baseline。输出在 `rolling/`，规则、调用绑定
要求和当前设备阻塞状态见[最近五轮诊断](rolling-diagnosis.md)。正常组用于对照/误报检查，
不作为其他20例的慢化检测参考；注入真值只供独立验收使用。
当前滚动归因使用v4：从慢Wait的真实生产端回溯，保留已有跨调用路径，源头定位与本地关键
路径影响分别输出。`rolling/report.json`及`wait_backtraces.csv`包含回溯断点与比较覆盖率；
未定位不等于没有异常。后台收尾移至测量结束之后；通信worker需重编，尚待新设备验收。

## 从候选开始的传播链

当前滚动诊断自动导出 `propagation/index.html`、`report.json`、`chains.csv`、`steps.csv`和
`chains.md`。按原候选顺序逐个展开其已报告的“源头任务→中间控制任务→Record→慢Wait”路径，
包含Node/Rank/stream/task、iter/Block/桶、当前耗时、前5轮均值、增量及每跳证据等级。
不是重新向前搜索所有下游，也不改变候选排名、诊断阈值或独立评判。
HTML默认展示主候选的耗时对比及一条带Rank的源头→Record→Wait流程，可切换候选、目标Rank
和等待分支。仅折叠普通同流中间任务，保留同步端点、变慢任务、跨调用位置和时间警告；
完整逐跳记录仍可展开。中文文字报告提供同样的精简路径，不再逐条重复全部普通控制任务。

已有通过门禁的v4诊断可只运行导出，不重跑负载或分析器：

```bash
python3 -m hccl.tools.diagnosis.source_propagation /path/to/passed-diagnosis \
  -o /path/to/new-propagation
```

输入为已有执行图、`diagnosis_candidates.csv`及`rolling/task_comparison.csv`，不读取注入真值。
JSON用真实图节点/边ID保留每条完整路径；CSV分别提供分支摘要和有序逐步记录，HTML可展开阅读。
缺边、断链及时间不相容明确保留；跨机无时钟校准不计算全局时差。Host准备候选使用每个分支
实际Record作为设备锚点，不补造Host→设备边。`path_complete`只表示已报告路径能完整展开，
不等于已证明物理因果或某个Wait增量全由该候选造成，也不保证穷尽所有下游异常。
精简保存模式保留传播JSON/CSV/文字证据，仍只保留原来的一张依赖HTML，不新增第二张HTML。

## 跨机协议完成区间

多节点诊断额外生成`rdma_timing/index.html`、`report.json`及`transfers.csv`，
沿真实准备ACK→发送端Payload→数据通知依赖，用接收端自身时钟计算协议完成区间。
与RDMA提交耗时分开，不冒充纯网络/硬件传输耗时；缺失或歧义时保留未解析。
已有数据可独立导出，规则、命令和边界见[跨机计时说明](rdma-timing.md)。

新增原生 verbs CQ 完成事件观察器，默认关闭；多节点回放同时导出
`rdma_completion/index.html`、JSON/CSV，明确区分完成观测、失败/缺失及未绑定 task。
**当前910C AI_CPU路径尚缺实际成功完成事件，不能称完整传输计时已实现。**
使用`--require-complete-rdma`进行严格验收时，此缺口会返回非零而不是假通过。
生产端开关、支持路径与验证范围见[RDMA完成证据](rdma-completion.md)。

诊断链只接受 HCOMM 版本化 plog 与 msprof consolidated
`msprof_*.db`。Chrome-trace `msprof_*.json` 和 `task_time.csv` 已不再作为生产输入。

## 数据流

```text
plog semantic ─┐
               ├─ merge_timeline.py ── merged.csv
msprof DB ─────┘                         ├─ validate_trace.py
                                        ├─ visualize_dependency_graph.py
                                        │    ├─ execution node/edge/ambiguity CSV
                                        │    └─ resource node/edge/ambiguity CSV
                                        ├─ validate_dependency_graph.py
                                        └─ visualize_html.py → HTML/SVG
```

DB 解析从 `TASK` 保留物理 stream/task/context、`connection_id` 和整数纳秒起止时间，
并通过 `COMMUNICATION_TASK_INFO`、`COMMUNICATION_OP`、`COMPUTE_TASK_INFO` 补充通信
operation 与具体计算事件名称。合并结果同时保留未标注的 `profiler_only` 执行单元。
原始 operation 名称和本地 ID 不进入公共 schema；merge 仅输出紧凑
`profiler_op_scope` 及其 `unique/missing/ambiguous` 状态。

当前支持的 msprof DB schema 为 `1.2.0`。解析器以 SQLite `mode=ro` 打开数据库；未知
schema、缺表、重复 device 或一对多 communication metadata 会明确失败。

## 聚合

```bash
python -m tools.diagnosis.merge_timeline \
  --plog-dir /path/to/plog \
  --msprof-db-dir /path/to/msprof \
  --node-id node0 \
  -o merged.csv \
  --summary summary.csv
```

匹配分为：

- `task_id / exact`：普通任务的 device/physical-stream/task id 与 task kind 唯一一致。
- `ffts_parent_ctx / exact`：schema v2～v4 plog 先用 graph correlation 定位 FFts parent，
  再用 `ffts_ctx_id == TASK.contextId` 定位物理子任务。
- `correlation_kind_mismatch`：身份候选与物理 kind 冲突，属于硬错误，
  不得按 matched 使用。
- `unmatched_semantic`：无法唯一认领物理执行单元；不得用时间最近原则强行匹配。
- `profiler_only`：DB 中存在但没有语义声明的执行单元。

`submit_ts` 是 msprof host-cycle 提交时间，只能缩小候选窗口和做一致性检查，不能替代
task/subtask correlation id。设备执行起止时间始终来自 DB `TASK.startNs/endNs`，内部先
保留整数纳秒，到 CSV 边界才精确表示为十进制微秒。

semantic schema v1、无版本日志和旧空格 token 格式已不再支持。当前生产端输出 v4；
消费端接受 v2/v3/v4，以便复查已经通过设备验证的旧 golden 数据。v3 删除
`execution_mode`、`notify_remote_rank`、`notify_ctx_id`；msprof 侧删除与 `event_name`
重复的 `kernel_type`。v4 删除不参与 exact identity 或依赖构造的
`semantic_seq/profiler_seq`；旧输入中的这两个字段会被忽略。collective invocation
身份不由生产端重复生成，而是在 semantic 与物理 TASK exact 合并后，使用 msprof DB 的
`(group_name, op_name)` 建立；名称不完整或本地映射不唯一时标记为 missing/ambiguous，
不得参与 exact operation 分区。

## 依赖图

```bash
python -m tools.diagnosis.visualize_dependency_graph merged.csv \
  -o dep_graph

python -m tools.diagnosis.visualize_html dep_graph_nodes.csv \
  --edges-csv dep_graph_edges.csv \
  --view execution \
  --output dependency_execution.html

python -m tools.diagnosis.visualize_html dep_graph_resource_nodes.csv \
  --edges-csv dep_graph_resource_edges.csv \
  --view resource \
  --output dependency.html \
  --svg-output dependency_resource.svg

python -m tools.diagnosis.validate_dependency_graph dep_graph \
  --summary-output dep_graph_gate_summary.csv
```

execution node 使用
`(node, device, physical stream, task, subtask, connection)` 的稳定摘要作为
`graph_id`，CSV 重排和时间精度变化不会改变 ID；重复 physical identity 是硬错误。
node/edge CSV 当前标记 `graph_schema_version=6`。execution graph 保留 Notify；
resource graph 只保留 `sdma/rdma/reduce_inline/reduce_tbe` 资源任务，并把唯一可达的
`resource -> record -> wait -> resource` 控制链收缩为资源边。资源节点继续复用 execution
`graph_id`；缺少一侧资源任务时生成稳定 boundary，多候选时只写 ambiguity，不做笛卡尔积。

edge ID 由 `(graph_schema_version, kind, src, dst, relation_id)` 生成稳定摘要，nodes/edges
按稳定 ID 输出；CSV 行序不表示同步 occurrence。每次导出同时生成
`dependency_summary.csv`，统计重复 ID、缺失端点、自环、root/leaf、孤立节点、
cycle residual、edge kind 和 Notify ambiguity。重复 ID、缺失端点或自环会阻止导出。

resource edge 保存 `source_execution_edge_ids/control_graph_ids/record_graph_id/wait_graph_id`，
可反查完整控制证据。Notify 同步边还输出：

- `wait_span_ns`：wait 节点本地持续时间，也是当前同步边 `weight_ns`；
- `remote_block_ns/post_signal_ns`：同节点时，以 record 完成时刻切分 wait span 的观测值；
- `handoff_gap_ns`：wait 完成到下游资源任务开始的非负间隔；
- `timing_status`：跨节点未校准时为 `cross_node_uncalibrated`，此时不输出
  `remote_block_ns/post_signal_ns`，避免比较不同节点时钟。

依赖图 HTML/SVG 只读取已导出的 node/edge artifact，不在布局代码中重新推断依赖。
`validate_dependency_graph.py` 对 execution/resource 的重复 ID、缺失端点、自环、环、
Notify/收缩歧义及禁用伪边做门禁，并显式统计 stream/sync/boundary。
`ffts_physical_stream_order`、默认 `time_inferred`、旧 `notify_sync_inferred` 和已删除的
payload semantic edge 必须为 0。
可用 `--golden-summary` 固定期望统计；任何未更新的统计变化都会使门禁失败。

依赖边包含证据等级：

- `direct_stream_order_observed`：只对 `subtask_id < 0` 的 direct execution，在相同
  node/device/physical stream 内按 DB 精确时间建立顺序，`observed`。同起始时间不互相排序。
- `ffts_logical_stream_order`：只对 exact FFts context，按 operation、graph parent 和
  semantic logical stream 分组，再按 context 声明序连接，`semantic`；不使用设备时间排序。
- `ffts_notify_sync_observed`：完整 FFts relation identity 下恰好一个 producer 与一个
  consumer，`observed`；边保存稳定 relation ID。单边、多端或缺字段写入
  `dependency_notify_ambiguities.csv`，不生成因果边。
- `direct_notify_sync_exact`：按 DB operation scope、Notify resource、规范 rank 方向分
  channel，再按两侧各自 local physical stream 的 ordinal 配对，`exact`；不比较跨设备时间。
- `local_notify_sync_exact`：对 DB `dstRank=-1` 的 device-local Notify，按
  `(node, operation scope, device, notify)` 分 channel，再按 Record/Wait 各自 physical
  stream 内 ordinal 配对，`exact`；不比较两个 stream 的时间。

Notify 资源会跨 step、graph 和 operation 复用，不能单独代表一次同步。FFts relation 使用
graph instance；direct relation 使用
`(node, operation scope, notify, producer, consumer, db_notify_ordinal)`。两者都不包含跨设备
时间或 `connection_id`。local relation 使用
`(node, operation scope, device, notify, db_local_notify_ordinal)`；64 位 Notify ID 按整数
文本精确解析，不经过 `float`。

当前 DB golden replay 的 FFts Notify 结果为 4,676 条 observed edge、28 条 single
ambiguity、0 条 multi-endpoint ambiguity、0 条 incomplete。direct 结果为 5,376 条 exact：
语义 both 4,695、partial 9、none 672、conflict 0。ACK/data-signal 不再生成
`peer_signal_semantic` 时间排序边。local 结果为 5,376 条 exact，主→从和从→主各 2,688
条，ambiguity/incomplete 为 0。

`peer_payload_semantic/resource_payload_semantic` 已从默认因果图正式删除。当前样例原有
2,142 条 payload semantic edge 全部可由“一条 `direct_notify_sync_exact` + 三条
`direct_stream_order_observed`”的最短路径到达，未增加任何可达关系；其 occurrence 又只按
语义坐标和出现顺序配对。门禁拒绝旧 edge kind，`tx/rx_payload_*` 事件仍保留为节点语义。

DEP-008 已删除默认 connection/time Notify 推断。旧 JSON 的 3,016 条和 DB 的 5,094 条
最近时间边均不再进入因果图；如果未来恢复研究模式，必须使用独立显式入口并标为
`heuristic`，不能混入默认 artifact。

旧实现中的“右邻居上一 payload”“上一 step”等算法规则不再作为默认边；它们不是 profiler
观测事实。多节点关系需先确认跨端共享身份，现有 DB 字段不足时再增加 protocol token。
拓扑配对不依赖跨节点时间比较；跨时钟差值和全局路径累计才需要统一时间基或校准 artifact。

## 关键路径分析（nf 分支）

新增离线入口，读取 execution artifact，不读取 resource `weight_ns` 来累加全量 Wait：

```bash
python3 -m hccl.tools.diagnosis.critical_path dep_graph_nodes.csv \
  --edges-csv dep_graph_edges.csv -o critical_path
```

输出关键任务、slack、带原始边 ID 的代表路径，以及逐项缩短耗时后的模型完成时间变化。
默认终点是全部输入任务完成，包含采集初始化/收尾；分析业务 workload 时应按
`--operation-scope` 或 `--completion-task` 明确范围。仅支持同节点时间域，多机未校准时
拒绝全局累计。FFts/未配对 Wait/时间冲突保留为 partial evidence，不宣称确定根因。
计费公式、并行分支示例、CLI 和限制见 [关键路径说明](critical-path.md)。

## 交互可视化

```bash
python -m tools.diagnosis.visualize_html merged.csv \
  --view timeline --layout time -o timeline.html
```

Dependency HTML 使用类似 Perfetto 的固定高度物理 stream 轨道，水平时间缩放不会再压缩
纵向轨道。默认不绘制全局依赖边；单击任务后只高亮该任务、直接前驱、直接后继和对应
依赖边，右侧详情面板可沿依赖继续跳转，双击任务会聚焦到该任务。它支持 device、rank、
stream、event、edge kind 和文本筛选，并提供时间标尺与全局 overview。

Dependency HTML 不做密度聚合。零时长任务始终显示为菱形 marker；非零任务在当前缩放
下真实持续时间不足 2 个屏幕像素时也显示为 marker，放大后自动恢复为真实宽度矩形。
同一点击位置存在多个任务时，右侧详情面板列出候选任务供进一步选择。

Timeline HTML 继续支持 device、rank、stream、event、时间范围和文本筛选。鼠标悬停显示
task/subtask、语义、硬件事件、匹配方式与置信度。

## 验证

```bash
python -m py_compile hccl/tools/diagnosis/*.py
python -m unittest hccl.tools.diagnosis.test_diagnosis -v
python -m tools.diagnosis.validate_trace merged.csv --min-match-rate 95

python test/measure_msprof_db_parse.py \
  --msprof-db-dir /path/to/msprof \
  --output db_parse_overhead.csv
```

质量门禁只接受 exact。质量结论必须同时报告 exact rate、kind mismatch、
unmatched semantic 和 duplicate execution key。对当前 single-ring direct RS/AG，
门禁还校验 phase 内的 step 因果桶合同：`0 <= step < rank_size`，且
ACK/payload/data-signal 等 main-round event 不得进入 `step=rank_size-1` 的
final/epilogue 桶。未知 phase 不套用 Ring 规则；错误会输出可定位的 CSV 行和 task
坐标，不自动猜测修正。
