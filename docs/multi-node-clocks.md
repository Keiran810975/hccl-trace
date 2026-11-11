# 多机时钟证据

[多机训练](../README.md#4-多机每机采集一次汇集后分析) 不需要校时就能查看各节点本地耗时和已有跨机依赖。
需要比较跨机事件先后或耗时时，要在采集前准备前后时钟探针。
探针使用 CPU 单调时钟，不会修改系统时间，也不代表 RDMA 硬件传输完成时间。

以下沿用 README 的 `gpt2-two-node-01`、`node-a`、`node-b`。
两机 shell 都设置同一个 `RUN_ID` 和实际可达的 `MASTER_ADDR`。
参考端口 `29860` 必须空闲，仅限已授权节点可访问的内网，不暴露到公网。

## 1. 在采集前启动探针

在节点 A 的独立终端启动参考服务，等待打印 `Clock probe server ready`：

```bash
hccl-diag clock-probe serve --address "$MASTER_ADDR" --port 29860 \
  --capture-id "$RUN_ID" --node-id node-a --reference-node node-a --peers node-b \
  --timeout 7200 --output "clocks/$RUN_ID/node-a.json"
```

然后在节点 B 做一次 `before` 探针，成功后再启动两端采集：

```bash
hccl-diag clock-probe probe --address "$MASTER_ADDR" --port 29860 \
  --capture-id "$RUN_ID" --node-id node-b --reference-node node-a --phase before \
  --timeout 60 --output "clocks/$RUN_ID/node-b-before.json"
```

## 2. 在所有节点采集退出后取后置样本

两端训练和 msprof 完全退出后，在节点 B 执行：

```bash
hccl-diag clock-probe probe --address "$MASTER_ADDR" --port 29860 \
  --capture-id "$RUN_ID" --node-id node-b --reference-node node-a --phase after \
  --timeout 60 --output "clocks/$RUN_ID/node-b-after.json"
```

节点 A 服务收到节点 B 的后置探针才会正常退出并写参考文件。
更多节点时，`--peers` 传逗号分隔的全部非参考节点名，每台各做两次探针。

## 3. 把证据随采集汇集

将节点 A 的 `node-a.json` 放入本机采集根的 `nodes/node-a/`，
并在该采集根创建 `capture.json`：

```json
{
  "run_id": "gpt2-two-node-01",
  "nodes": [{"node_id": "node-a", "clock_probe_files": ["nodes/node-a/node-a.json"]}]
}
```

将节点 B 的两个探针文件放入 `nodes/node-b/`，在节点 B 的采集根创建：

```json
{
  "run_id": "gpt2-two-node-01",
  "nodes": [{
    "node_id": "node-b",
    "clock_probe_files": ["nodes/node-b/node-b-before.json", "nodes/node-b/node-b-after.json"]
  }]
}
```

如果已经有 `capture.json`，只在本节点条目补 `clock_probe_files`，保留已有元数据。
上面的路径相对于各采集根；`join` 会保留这些声明及对应文件。
把两个采集根传到分析机后：

```bash
hccl-diag join runs/gpt2-two-node-01-node-a runs/gpt2-two-node-01-node-b \
  -o runs/gpt2-two-node-01
hccl-diag analyze runs/gpt2-two-node-01 --require-clock-alignment \
  -o reports/gpt2-two-node-01 --keep-debug
```

检查 `root_causes.json` 中的 `quality.clock_alignment_available` 与误差。
默认容限为 1 ms，前后探针还必须覆盖实际 profiler 会话。
证据缺失或超限时，不将其解释为已校时。只需要本地结果时，可改用
`--allow-uncalibrated-clock`，保留校时失败原因和本地时间轴；不要同时使用两个参数。
