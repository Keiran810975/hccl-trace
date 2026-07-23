# HCCL fine-grained trace diagnosis

诊断链只接受两个事实源：HCOMM `[HcclTaskSemantic]` plog 与 msprof consolidated
`msprof_*.db`。Chrome-trace `msprof_*.json` 和 `task_time.csv` 已不再作为生产输入。

## 数据流

```text
plog semantic ─┐
               ├─ merge_timeline.py ── merged.csv
msprof DB ─────┘                         ├─ validate_trace.py
                                        ├─ visualize_dependency_graph.py → node/edge/ambiguity CSV
                                        └─ visualize_html.py → interactive HTML
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
  -o dependency

python -m tools.diagnosis.visualize_html merged.csv \
  --view dependency \
  --output dependency.html
```

execution node 使用
`(node, device, physical stream, task, subtask, connection)` 的稳定摘要作为
`graph_id`，CSV 重排和时间精度变化不会改变 ID；重复 physical identity 是硬错误。
node/edge CSV 当前标记 `graph_schema_version=1`。execution graph 保留 Notify，
resource graph 的控制收缩合同见 `spec.md`，尚由后续 DEP-012 实现。

依赖边包含证据等级：

- `direct_stream_order_observed`：只对 `subtask_id < 0` 的 direct execution，在相同
  node/device/physical stream 内按 DB 精确时间建立顺序，`observed`。同起始时间不互相排序。
- `ffts_logical_stream_order`：只对 exact FFts context，按 operation、graph parent 和
  semantic logical stream 分组，再按 context 声明序连接，`semantic`；不使用设备时间排序。
- `ffts_notify_sync_observed`：完整 FFts relation identity 下恰好一个 producer 与一个
  consumer，`observed`；边保存稳定 relation ID。单边、多端或缺字段写入
  `dependency_notify_ambiguities.csv`，不生成因果边。
- `peer_signal_semantic` / `peer_payload_semantic`：显式 peer rank、phase、step、slice 相同，
  再按 occurrence 顺序配对，`semantic`。

Notify 资源身份是 `(node_id, notify_id)`，它会跨 step、graph 和 operation 复用，不能直接
代表一次同步。规范 relation identity 还包含 operation scope、producer/consumer、signal、
phase/step/slice 和 graph/protocol sequence；不包含时间或 `connection_id`。当前 FFts 已有
graph sequence 可生成 relation candidate，direct 必须等待生产端共享 token。

当前 DB golden replay 的 FFts Notify 结果为 4,676 条 observed edge、28 条 single
ambiguity、0 条 multi-endpoint ambiguity、0 条 incomplete。direct 的共享 token 被
transport 侧缺失的 channel/protocol occurrence sequence 阻塞；实例 ID 已完成，但本地
task/stream 计数仍不能替代跨 rank protocol sequence。

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
unmatched semantic 和 duplicate execution key。
