# 自动 Baseline 对比与源头报告

此功能位于 nf 消费端，只读取已导出的 execution artifact，不修改原始 DB、语义日志、
任务身份或依赖边，也不读取异常注入真值。服务器不必重新部署 Host/Device 库。

## 运行

完整诊断入口传入正常组目录后，会自动增加 `comparison/` 报告：

```bash
python3 -m hccl.tools.diagnosis.run_diagnosis anomaly-run.json -o replay \
  --baseline-dir replay/NORMAL_RUN_ID
```

已有 artifact 可直接分析，不重新采集：

```bash
python3 -m hccl.tools.diagnosis.compare_diagnosis /absolute/anomaly-artifact \
  --baseline-dir /absolute/baseline-artifact -o /absolute/new-comparison
```

目录必须为新目录，重跑换新目录，不覆盖旧结果。输入至少包含
`dep_graph_nodes.csv`、`dep_graph_edges.csv`；存在 `pipeline_result.json` 时必须为 passed。
仅有图文件时只验证图，不声称重新通过了原始采集门禁。

## 输出

| 文件 | 内容 |
|---|---|
| `index.html` | 自动报告入口，变慢清单、源头候选及局部对比链接 |
| `report.json` | 全量任务对比、源头候选、真实证据路径和限制 |
| `task_comparison.csv` | 每个任务的参考覆盖、耗时、增量、倍数及本地空隙变化 |
| `slow_tasks.csv` | 超过阈值的任务或本地空隙，未把两者混为设备执行时长 |
| `root_causes.csv`、`summary.md` | 源头候选、未决上游、受影响 Wait 和图链接 |
| `focus-NNN.html` | Baseline/异常局部对比页，统一时间窗口与比例尺 |
| `focus-NNN-baseline/anomaly.html` | 复用项目原生交互渲染器的局部图，默认选中候选并显示相关边 |
| `focus-NNN-baseline/anomaly.svg` | 同一任务模型导出的静态图，带时间轴、真实依赖箭头和候选高亮 |

默认只为前5个候选生成图片，全量候选和慢任务仍在 JSON/CSV。交互页的重新缩放不联动，
初始比例尺及静态对比图一致。跨节点分别以该 operation 的节点本地起点为原点，
不能从图上比较跨机绝对先后。红色虚线框表示任务前的观测空隙，不是新建的设备任务。

## 对比与溯源规则

1. 验证两次采集的 Rank/节点分组一致。按整次 operation 的任务语义结构寻找参考组，
   再按 Rank、peer、算法、phase、step、slice、事件、类型和字节数建立统计参考。
   不使用跨次采集的 task ID、Notify ID、时间最近或“第n个任务”认定任务身份。
2. 默认变慢门槛：增量至少10微秒、至少参考组的3倍MAD，且达到参考中位数的1.5倍。
   任务耗时与同物理stream、同operation、唯一observed前驱之后的空隙分别比较。
   不将采集边界、跨operation间隔或跨节点时间差当作空隙。
3. 在同一次 operation 内沿 observed/exact 的真实 stream/Notify 边回查。
   最上游的慢 Copy/Reduce 可成为源头候选；下游已有慢等待的慢任务保留在清单中，
   不直接升级为独立根因。增长的本地空隙是额外观测时间，即使之前也有小幅波动仍保留。
4. 有真实路径通向增长的 Wait 时标记 `dependency_supported_candidate`；
   无受影响等待的慢执行标记 `isolated_slow_task`；只有等待而未建立上游慢执行证据时
   标记 `unresolved_upstream`，同时保留已配对生产者；遍历受限标记证据不完整。
5. RDMA doorbell 耗时、AI_CPU kernel 整体包络仍可列为时长异常，但不直接当作
   payload 执行根因。任务前空隙不能自动解释成 CPU sleep、网络拥塞或驱动问题。

默认参考会混合结构相同的多次通信，因此是统计对比，不是训练轮次的精确配对。
变化的算法/任务结构会显式显示无可比参考；冷启动和正常抖动也可能形成候选，
不能把候选数量或 pipeline passed 当作异常识别准确率。

如有经过核实的调用对应关系，可传入以下 JSON：

```json
{
  "schema_version": 1,
  "operation_pairs": [
    {
      "current_scope": "ANOMALY_OPERATION_SCOPE",
      "baseline_scope": "BASELINE_OPERATION_SCOPE",
      "evidence": "依据真实调用与DB核实的对应关系"
    }
  ]
}
```

独立入口加 `--operation-map map.json`，完整入口加 `--baseline-operation-map map.json`。
显式映射也只约束统计参考来自哪个 operation，不虚构单个任务的一对一身份。

独立入口阈值参数为 `--min-increase-us`、`--slowdown-factor`、`--context-us`、
`--max-figures`；完整入口对应加 `--comparison-` 前缀。

没有跨机时钟校准或应用完成证据时，不输出全局首个慢任务、全局关键路径收益或
“某任务导致整个workload增加了多少时间”的确定结论。该功能不绕过原诊断门禁，
也不修改既有关键路径的证据边界。

## 本地验证

单测覆盖慢执行/等待传播、独立空隙、时钟偏移、不同比较规模、MAD、缺失语义参考、
显式operation映射、遍历边界、RDMA/AI_CPU限制、输出转义及统一比例尺。
已有910B稳定组与定点延迟组的artifact回放，首个候选落到 Rank0 / allgather_direct /
step0 / tx_payload_start 前的约200.136ms观测空隙；这只是旧数据回放，
不宣称新做了双机采集或已完成测试集准确率验收。
