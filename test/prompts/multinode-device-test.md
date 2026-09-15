# NEXT-003 / NEXT-004 双机设备测试交接

测试对象：`codex/multinode-diagnosis`。实现与边界见
[多机设计记录](../../hccl/tools/diagnosis/multi-node-design.md)。本方案尚未在设备执行。
目标是一条正常双机 AllReduce 路径；无需重跑所有 Ring/NHR/Mesh 变体。

## 1. 环境与采集

1. checkout 本开发分支，保存根仓提交、相关 diff、加载库路径及哈希。HCOMM 仍用已集成的
   8.5 实现；若需重建，在 HCOMM 自身执行 `bash build.sh --pkg`，保留构建日志。
   填写两节点 Toolkit、driver、msprof 版本及完整命令。
2. 固定一类消息大小，建议先 1 MiB FP32 AllReduce、1 次 warmup + 3 次正式调用，
   两节点使用同一 launcher/通信域，结果逐项校验。实际规模按现有稳定程序调整并记录。
   每个 rank 的数据可取 `rank+1`，SUM 结果应为 `rank_size*(rank_size+1)/2`。
3. trace-on 使用 `HCCL_STEP_TRACE=1`。按现场 `msprof --help` 与已有成功命令采集
   consolidated DB；FFts 要有 addition-info 订阅成功证据。不通过修改 callback 门控造数据。
   本仓尚有两处 Ring `[TEST PATCH]`，按已有设备交接核实实际选路，不能把配置意图写成实测路径。
4. 每节点分别保存本次全部 rank 的 plog 和原始 PROF/consolidated `msprof_*.db`。
   不混入 trace-off、上一次运行或重试运行；不要把两个节点目录直接拼给单节点 wrapper。
5. 保存实际 executor、机内/机间 template、transport、FFts/direct 模式的选择日志。
   本版跨机目标为 Ibverbs 的 rank+offset Notify 编码路径；其他 transport 的结果单独记录。
   已知 NHR 子通信域插桩可能仍用内部 rank 填 user_rank，遇到 mismatch 保留两端证据，
   不改 CSV 或放宽门禁。根据实际失败位置再补生产端。

## 2. 输入清单与首次回放

复制 [模板](../fixtures/multinode-run.example.json) 为采集目录的 `run.json`。
填写所有实际 user rank → node/device；同一个物理 device ID 可以在不同节点重复。
从 rank table/communicator 记录各层 comm rank 映射，不能把 comm rank 当 user rank。
路径相对 `run.json`。模板中的两个 rank 只是格式示例，不是完整 16 卡配置。

首次 `operations` 保持空列表，运行：

```bash
python -m unittest hccl.tools.diagnosis.test_diagnosis hccl.tools.diagnosis.test_multi_node_trace
python -m hccl.tools.diagnosis.multi_node_trace /capture/run.json -o /capture/inspect
```

首次没有 operation 绑定，预期入口返回 1，保留节点内图及 incomplete 原因。
检查 `inspect/<run>/merge_summary.csv`：每节点 exact >=95%，重复、invalid_matches、
ambiguous_semantic、duplicate_graph_correlation_keys 均为 0；每节点都要有 semantic。
merge 失败时不会生成图，应先查 raw plog/DB，不能忽略失败继续宣称图验收成功。

## 3. 核实共享 operation 与 Notify

从 `operations.csv` 找各端 `(group_name,op_name,local opId)`，对照共同 launcher 调用记录
与 communicator 成员，确认是同一轮 collective。相同名称、相同本地 opId 或本地计数相等
均不足以单独证明共享调用。连续 operation 各建立一条绑定；warmup 也独立分区。
例如，证据已核实后写入：

```json
{
  "operation_id": "allreduce-call-0",
  "evidence": "launcher.log 的共同调用 0；node0/node1 DB 查询记录与通信域成员见 op-map.txt",
  "members": [
    {"node_id": "node0", "group_name": "实际域名A", "op_name": "实际调用名A"},
    {"node_id": "node1", "group_name": "实际域名B", "op_name": "实际调用名B"}
  ]
}
```

保存此映射的查询结果与日志；工具只消费显式绑定，不自动证明 evidence 文本。
按 `dep_graph_notify_ambiguities.csv` 的 endpoint ID 回查 TASK 与
COMMUNICATION_TASK_INFO：

- 发送端 `RDMASEND`、接收端 `NOTIFY_WAIT`，双方 src/dst user rank 互为对应方向。
- 同一 channel 的 Notify 宽整数相同，高 32 位是接收 rank，低 32 位是 notify offset。
  RDMA payload 的低 32 位 `0xFFFFFFFF` 不计作 signal。
- 目标 direct channel 两侧分别单 stream、等数量且本地顺序唯一。
  FFts 两端各一个 occurrence 可接通；重复 FFts channel 当前应报告 ambiguous。
  如果实际正常样例均是这种重复 FFts 路径，应回传原始证据继续开发，不能按 graph 序号补配。

## 4. 正式回放与查看

填写完成后对同一 run 换输出根目录重放（保留同一个 run_id）：

```bash
python -m hccl.tools.diagnosis.multi_node_trace /capture/run.json -o /capture/replay
python -m hccl.tools.diagnosis.validate_dependency_graph /capture/replay/<run>/dep_graph
python -m hccl.tools.diagnosis.visualize_html /capture/replay/<run>/dep_graph_resource_nodes.csv \
  --edges-csv /capture/replay/<run>/dep_graph_resource_edges.csv --view resource \
  --output /capture/replay/<run>/resource.html --svg-output /capture/replay/<run>/resource.svg
```

正常验收：

- 算子结果正确；目标语义逐节点 exact >=95%，未覆盖项有解释。
- `run_summary.csv`：跨节点边 >0、远端 unresolved channel 为 0、两个 gate 通过；
  execution/resource 重复 ID、缺端点、自环、环残余为 0，所有 boundary 有解释。
- 每个正式 operation 至少抽查一条目标机间关系：send/wait graph ID → 联合 merged →
  各节点 merged → raw DB/plog。核对实际 phase/step/peer，确保不同 operation 不串组。
- `record_graph_id` 在跨节点边中指 RDMA send；`wait_graph_id` 指接收 Wait。
  `wait_span_ns` 等于接收端 `endNs-startNs`；未校准时 remote/post 分解必须为空。
- HTML 的 lane 包含 node，device 与 user rank 分开。不同节点各自本地起点对齐只是展示，
  不计算或解读机间绝对延迟。使用入口产生的 artifact，不能用旧构图 CLI 重建联合关系。

## 5. 离线失败模式

先使用新增 17 项 fixture 单测验证以下预期。若在实际采集副本上复核，保留原件及修改说明：

| 改动 | 预期 |
|---|---|
| 相同 DB/plog 但换 run_id | execution/relation/operation ID 隔离，不与原 run 串组 |
| 删除一个 channel 的 send 或 wait | single/数量不等；该 channel 不部分强配，入口返回 1 |
| 复制一条 semantic 或 DB physical TASK | 节点 merge/DB parser 阻止构图 |
| 额外候选或双方各多一条 stream | ambiguous，不做笛卡尔积 |
| 去掉 operation 绑定，或只保留另一轮绑定 | incomplete/single，无跨轮拼接 |
| 一个节点整体平移 task 时间 | 拓扑身份、本地 duration/wait、视图局部位置不变；remote/post 仍为空 |
| 重复 FFts occurrence | ambiguous，不使用 graph_instance 跨节点配对 |

不要为测试直接改原始采集 DB。设备副本平移需同时修改同一节点所有 startNs/endNs；
小 fixture 已自动覆盖这个时钟独立性质。NEXT-005 Top Wait 与 NEXT-006 真实延迟注入不在本轮。

## 6. 回传

返回 run.json、共同 launcher 与算法/transport 日志、操作对应证据、构建/版本/库信息、
算子正确性结果、两节点原始 plog/DB、全部回放 artifact 和退出码。
指出实际经过的层级与未覆盖项。Windows 单测或生成 HTML 均不能替代此双机设备验收。
