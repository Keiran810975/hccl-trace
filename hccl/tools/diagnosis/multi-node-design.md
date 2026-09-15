# NEXT-003 / NEXT-004 多机输入与依赖实现记录

更新：2026-09-15。开发分支 `codex/multinode-diagnosis`，起点为根仓
`10cda209dd869b6f780435305f5cad9819d2b0a4`。使用独立 worktree，原 master 和
HCCL/HCOMM 子仓的 checkout、已有差异均保留。

## 1. 范围与结论

已实现同一次采集的节点清单回放、显式 operation 绑定、跨节点 RDMA Notify 关系、
execution/resource artifact 和未校准时钟下的视图。复用已有 parser、merge、构图及门禁，
Python 仅用标准库。没有新增生产端协议、schema 字段或设备任务。

**设备验收尚未完成**：用户确认当前无测试环境，由用户后续进行双机采集。因此 NEXT-003
的正常样例与 NEXT-004 的真实跨节点证据闭环仍待验收。合成 fixture 只验证离线规则，
不代表当前算法/transport 已通过双机设备验证。

## 2. 已核实的生产事实

| 源码位置（HCOMM） | 已有事实及消费方式 |
|---|---|
| `src/platform/resource/transport/host/transport_ibverbs.cc`：`TxAck`、`TxDataSignal`、`RdmaSendAsync` | Notify WQE 使用交换得到的接收端 notify offset；发送任务是 RDMA，接收端 `RxAck/RxDataSignal` 是 Wait |
| `src/platform/task/dispatcher.cc`：`RdmaSend`；`dispatcher_graph.cc`：`RdmaSend/GetNotifyDfxInfo` | SEND_NOTIFY 与 Wait 均使用 `(receiver_user_rank << 32) | offset_low32`；普通 RDMA payload 低 32 位是 `UINT32_MAX` |
| `src/pub_inc/dispatcher_task_types.h`：`TaskParaDMA` | 从 Notify 标识高 32 位取 remote user rank；这不是从 rank 推断 device |
| `src/common/debug/profiling/task_profiling.cc`：`GetRdmaTaskData/GetNotifyTaskData` | 已向 msprof 上报 Notify 标识与 remote rank，DB parser 已读取对应字段 |

本次只把已有 RDMA DB `notifyId/srcRank/dstRank` 保留到 merged 的 canonical
`notify_id/user_rank/peer_rank`。这三个值以前只保留在 Notify record/wait 行。
DB 物理身份仍负责 exact merge，semantic 的 phase/step/comm_rank 原样保留。

这些事实限定当前支持的 **rank + offset 编码的 Ibverbs 路径**，不是全部 RoCE 实现的承诺。
其他 transport、RDMA read、特殊 atomic/multi-QP 路径须以设备实际记录确认编码与完成语义。
payload 不因 event 名叫 `tx_payload_start` 就被当成远端 Notify。

## 3. 输入与身份

入口：`python -m hccl.tools.diagnosis.multi_node_trace RUN.json -o OUTPUT`。
模板见 [run.example.json](../../../test/fixtures/multinode-run.example.json)。

- 一份清单只代表一次 run；`nodes` 指定每节点 plog/DB 目录，路径相对清单文件。
  运行记录、Toolkit/driver/msprof 版本、命令与源码状态放在 `capture`，随清单保存。
- `ranks` 显式给出 user rank → node/device。可在每项的 `comm_ranks` 中记录各子通信域的
  comm rank；该记录用于人工核对，工具不把内部 comm rank 自动转成 user rank。
  不一致保留为 merge/依赖问题，不能覆盖 raw semantic 来掩盖生产端插桩错误。
  联合输出中，缺 user rank 的 profiler-only 任务可从这份显式 device 映射补充；
  节点原始 merged 与已有 semantic/DB rank 不覆盖。
- 各节点先独立 merge，保存 `<run>/<node>/merged.csv`。每节点 exact 匹配率 >=95%，
  重复 semantic/profiler/graph correlation、无效匹配、歧义认领均阻止联合构图。
- 联合 merged 使用 `node_id=<run_id>/<node_id>`。run/node 名仅允许字母、数字、点、
  下划线和连字符，因而 namespace 可唯一拆分。物理 graph ID 自然包含 run，
  不增加另一套 execution identity。原始节点名和输入路径保存在 `inputs.json`。
- 未绑定的 operation 使用 `(run,node,local_scope)` 隔离；绝不因 DB 字符串相同就跨节点
  合组。`operations.csv` 输出每节点 DB 名称及本地 opId，供采集者回查。
- `operations` 为采集者确认的共享调用映射：每项有 `operation_id`、`evidence` 和各节点
  `group_name/op_name`。`operation_id` 是这次清单内的调用标签，不能直接填各进程计数。
  采集者必须用共同 launcher 调用记录、通信域成员和各端 DB 引用证明对应，再填写映射。
  工具检查一对一绑定，**不声称能自动验证 evidence 文本的真实性**。
  缺乏这种证据时留空 `operations`，得到独立图与 incomplete 记录。
- 联合 operation scope 为 `(run,operation_id)` 的摘要；两端 group/op 名可以不同。
  本地 DB missing/ambiguous scope 不会因清单存在就被升级为 unique。

merged 仍为 42 列，semantic v4、DB schema 1.2.0 和 artifact v4 保持。
新边 kind 是 additive 扩展；单机 identity 和既有 kind 不变。
`merged.csv` 是联合物理输入；**联合依赖应使用入口输出的 artifact**。单独运行旧
`visualize_dependency_graph merged.csv` 没有清单证据，只能重建节点内依赖。

## 4. 跨节点配对

1. 从 DB RDMA/Wait 行识别候选。排除 payload sentinel 和 device-local Wait。
2. 通过显式 rank 表确认双方节点、发送/接收方向及本端物理 device；检查 Notify 标识
   中的接收 rank 与方向一致。未知映射、缺共享 operation 或 Notify 字段记 incomplete。
3. channel = `(shared_operation_scope,producer_user_rank,consumer_user_rank,notify_id)`。
   完整 rank、operation 和 Notify 存储身份同时约束，不使用时间邻近、connection 相同或
   phase/step 相同来补端点。一个方向存在缺失/冲突元数据时，该方向其他 channel 也不部分强配。
4. direct 重复 occurrence 要求两端分别只有一条物理 stream、数量相等、本地顺序唯一，
   然后按各端本地 ordinal 配对。不比较两节点时间。缺端为 single，多 stream、数量
   不等或顺序不唯一为 ambiguous，整个 channel 不输出部分配对。
5. 含 FFts 的 channel 只支持两端各一个 occurrence：凭共享调用与 Notify channel
   唯一性配对。出现重复 FFts occurrence 时保留 ambiguous，不能使用本地 graph_instance、
   context 编号或时间最近跨机补配。实际样例若被此阻塞，再调查最小共享 occurrence 事实。

execution 新边 `cross_node_notify_sync_observed` 保留两端 graph ID、relation ID、ordinal
和 operation evidence。它表示观测到的发送任务与接收 Wait 关系，不把 RDMA doorbell task
的结束解释为远端数据完成时刻，也不提升成硬件级 exact。

缺端/歧义复用 `dep_graph_notify_ambiguities.csv`，有两端候选 graph ID 和具体原因。
远端 Wait 从节点内 Notify 配对排除，但其本地 stream/FFts 顺序照常保留。

## 5. 资源图与视图

复用既有收缩：RDMA send 本身就是上游 resource，Wait 后唯一可达 resource 是下游；
缺下游生成 boundary，多候选保留 ambiguity。`record_graph_id` 在这种边中指 RDMA send，
字段名称沿用通用同步 artifact；`wait_graph_id` 指真实 Notify Wait。

- 新 resource kind：`resource_cross_node_notify_sync_observed`；若接收端收缩路径含
  semantic order，使用 `resource_cross_node_notify_sync_semantic`。confidence 取所有源边最弱值。
- `wait_span_ns` 和 `handoff_gap_ns` 只使用接收节点本地时间；`remote_block_ns`、
  `post_signal_ns` 留空，`timing_status=cross_node_uncalibrated`。
- HTML/SVG 只消费 artifact。多节点分别以各节点最早 task 为展示起点；页面显示
  `Node-local elapsed time; clocks uncalibrated`，水平距离不能解释成机间延迟。
  lane 显示 node，task 详情区分 user rank/device。原始本地时间仍保留。

NEXT-002 的旧单机 FFts/mixed order 证据增强问题仍独立待修；本次只确保新跨机收缩边
不继承该错误，未扩大为全套派生边整改。

## 6. 输出与退出码

每次写新的 `OUTPUT/<run_id>`，不覆盖已有运行结果；相同原始 run 重放时换 OUTPUT。
本地 merge 失败仍保存 merged、merge_summary、operation inventory 和 inputs，停止构图。
构图成功后运行现有 graph gate，并输出 `run_summary.csv`：至少一条跨节点边、远端未决
channel 为 0、graph gate 通过时入口返回 0，否则返回 1，保留可审阅 artifact。
返回 0 也不等于算子正确性、采集完整性、所有 transport 或设备验收已经完成。
boundary 数由实际样例逐项解释；不套用旧样例阈值 8。

## 7. 验证记录

- Windows / Python 3.12.7：原有 62 项 + 新增 17 项，共 79 项单测通过。
- 新增 fixture 覆盖双节点 consolidated DB/plog 完整回放、不同 rank/device、相同物理
  task ID、多 run、不同本地 operation 名、缺共享绑定、缺端、重复计数、多 stream、
  顺序歧义、缺 Notify、payload sentinel、FFts 单 occurrence 与重复拒配、资源证据降级。
- 节点时间平移后，跨节点边 ID、本地等待指标和视图横向位置保持不变。
- Python 脚本 `--help` 入口通过；无 CANN/HCOMM 构建、无真实双机采集结果。
- 已有单机原始 plog/8 个 DB 回放通过：28,502 / 28,502 exact，重复与 invalid_matches 为 0；
  44,008 个 execution、56,675 条 execution 边、25,479 条 resource 边；28 个 single、
  8 个 boundary 与归档一致。validate_trace 与 graph gate 通过。
  输出保存在本分支 worktree 的 `test/out/single-replay*`，不作为新设备采集证据。

设备验收操作、预期与回传清单见 [双机设备测试方案](../../../test/prompts/multinode-device-test.md)。
