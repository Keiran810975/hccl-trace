# HCCL fine-grained trace diagnosis

诊断链只接受两个事实源：HCOMM `[HcclTaskSemantic]` plog 与 msprof
`msprof_*.json`。`task_time.csv` 会把 FFts 图压缩为一个 `AI_CORE` 父任务，已不再支持。

## 数据流

```text
plog semantic ─┐
               ├─ merge_timeline.py ── merged.csv
msprof JSON ───┘                         ├─ validate_trace.py
                                        ├─ visualize_dependency_graph.py → edge/node CSV
                                        └─ visualize_html.py → interactive HTML
```

JSON 解析保留物理 stream/task/subtask、`connection_id`、HostToDevice flow id、硬件事件名
和执行起止时间。合并结果同时保留未标注的 `profiler_only` 执行单元。

## 聚合

```bash
python -m tools.diagnosis.merge_timeline \
  --plog-dir /path/to/plog \
  --msprof-json-dir /path/to/msprof \
  --node-id node0 \
  -o merged.csv \
  --summary summary.csv
```

匹配分为：

- `json_task_id / exact`：普通任务的 device/physical-stream/task id 与 task kind 唯一一致。
- `json_ffts_parent_ctx / exact`：schema v2/v3 plog 先用 graph correlation 定位 FFts parent，
  再用 `ffts_ctx_id == Subtask Id` 定位物理子任务。
- `correlation_kind_mismatch`：身份候选与物理 kind 冲突，属于硬错误，
  不得按 matched 使用。
- `unmatched_semantic`：无法唯一认领物理执行单元；不得用时间最近原则强行匹配。
- `profiler_only`：JSON 中存在但没有语义声明的执行单元。

`submit_ts` 是 msprof host-cycle 提交时间，只能缩小候选窗口和做一致性检查，不能替代
task/subtask correlation id。设备执行起止时间始终来自 JSON。

semantic schema v1、无版本日志和旧空格 token 格式已不再支持。当前生产端输出 v3；
消费端接受 v2/v3，以便复查已经通过设备验证的 v2 golden 数据。v3 删除
`execution_mode`、`notify_remote_rank`、`notify_ctx_id`；msprof 侧删除与 `event_name`
重复的 `kernel_type`。

## 依赖图

```bash
python -m tools.diagnosis.visualize_dependency_graph merged.csv \
  -o dependency

python -m tools.diagnosis.visualize_html merged.csv \
  --view dependency \
  --output dependency.html
```

依赖边包含证据等级：

- `stream_order_observed`：JSON 中同一物理 stream 的相邻执行顺序，`observed`。
- `notify_sync_observed`：重新采集后 plog 中 record/wait 具有相同 `notify_id`，`observed`。
- `notify_sync_inferred`：旧样本无 notify id，按同 device/connection、跨 stream、事件类型
  和唯一时间候选推断，`inferred`。
- `peer_signal_semantic` / `peer_payload_semantic`：显式 peer rank、phase、step、slice 相同，
  再按 occurrence 顺序配对，`semantic`。

旧实现中的“右邻居上一 payload”“上一 step”等算法规则不再作为默认边；它们不是 JSON
观测事实。多节点精确边仍需要 collective instance id、统一时钟或单独的时钟校准 artifact。

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
```

质量门禁只接受 exact。质量结论必须同时报告 exact rate、kind mismatch、
unmatched semantic 和 duplicate execution key。
