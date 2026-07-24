# HCCL fine-grained trace diagnosis

诊断链只接受两个事实源：HCOMM `[HcclTaskSemantic]` plog 与 msprof consolidated
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
node/edge CSV 当前标记 `graph_schema_version=4`。execution graph 保留 Notify；
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
观测事实。多节点精确边仍需要共享 protocol token、统一时钟或单独的时钟校准 artifact。

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
