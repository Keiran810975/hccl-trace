# Single Ring / NHR 诊断闭环

分支：`codex/ring-nhr-diagnosis`，基于 `f7b0e89` 和继承的未提交 AI_CPU / 耗时诊断改动。
原工作区快照保存在 `test/out/ring-nhr-diagnosis/inherited-worktree.tar.gz`，不把子仓旧 HEAD
当作测试源码版本。测试源码逐文件 SHA256、覆盖包和运行库 SHA256 随采集保存。

## 范围

机器0/1各4 rank，物理设备8、10、12、14；32MiB FP32 SUM AllReduce，4次调用。
实际选中 `AllReduceRingFor91093Executor`，机内 `single_ring_direct`，机间 `nhr`。
本机 Ring RS/AG 各3步；两机 NHR 每阶段只有一个机间步。本轮不代表4节点 NHR、
双环、FFts/AIV、retry/replay 或其他算子的设备验证。

镜像、容器、解释器和库版本见本地测试报告。沿用官方默认算法选择，不设置 HOST
强制展开或修改 atomic-write/传输路径。异常仅存在于独立测试构建覆盖中。

## 控制链事实补齐

此前128个 incomplete 和128个 single 来自三个真实缺口：Host order-launch 的原生
ACL Notify 不经过 TaskData，Device order-stream 缺 DB operation 元数据，以及
Host offset 编码与 Device resId 的两个本地 Notify 身份域。

新增独立 `[HcclTaskControl]` v1 日志，不改 semantic v4 / merged 43列：

- `(node, physical device, physical stream, task)` 精确指向已有 DB 执行任务。
- `task_kind` 必须兼容；`notify_id` 为真实资源 ID；`db_notify_id` 显式证明 Host 别名。
- `anchor_stream_id/task_id` 指向同一物理设备的实际任务；从该任务取得 DB operation。
  Device order → Host kernel → main Post 可形成两级归属链。anchor **不是同步边**。
- 缺任务、重复任务/日志、类型/别名/算子冲突、循环 anchor 都明确失败，不做偏移或近邻补配。

消费端 `control_trace.py` 只替换内存中的 profiler 元数据，DB 始终只读。
每节点 `control_metadata.csv` 留存原 ID、规范 ID、原算子、anchor 和日志行号。
本地同步仍以完整 channel、唯一 stream、等数量及双方 stream ordinal 建边。
资源图所有收缩边取完整路径最弱证据；graph artifact 升为 **v6**，不能混用旧节点/边。

## CPU 构图时长与等待诊断

新增 `[HcclTaskBuildSpan]` v1，仅在 trace 开启且实际 AI_CPU kernel 身份可取得时计时。
`TaskSemanticScope` 使用 CPU `steady_clock` 记录构图阶段，仅上报 >=1ms 的 span。
日志携带真实 kernel key、global rank、algorithm/phase/step/slice、整数纳秒时长和
`timing_domain=aicpu_build_cpu`。这不是设备执行区间，也不是传输耗时；嵌套 span 可重叠，
不能相加为硬件时间。缓存命中可绕过构图，本轮异常验证显式设置 `HCCL_AICPU_CACHE_ENABLE=0`。

多机回放导出每节点 `build_spans.csv`，`analyze_waits.py` 只读这些文件及 execution artifact：

- 完整等待清单、按 operation/node/rank/algorithm/phase 汇总、本地 wait/payload 的 sum 与 union。
  union 只消除同一组区间重叠；跨 rank、phase 再相加仍不是算子墙钟耗时。
- 缺 producer 保留 `evidence_gap`；其余区分短等待、等待生产者、上游等待链、
  RDMA 完成未观测和存在上游慢候选。
- 对 SDMA / Inline reduce / 已绑定 AI_CPU kernel，比较**相同工作负载配置**的正常基线：
  相同 rank、算法、phase、step、event、类型、字节数，默认 >=5ms 且 >=基线中位数3倍。
  未绑定的初始化 kernel 不作为通信算子根因。RDMA 门铃绝不作为传输执行慢候选。
- >=5ms CPU 构图 span 是独立候选。回溯只在当前 operation 的实际边上进行，至多4096个节点。
  CPU 候选还要求路径含同 rank、算法、phase、step 的任务；kernel 包含子 SQE 的执行，
  因而使用显式标注的 `upstream_rank_operation_correlation`，不伪造 kernel.end → 子任务边。
- 输出 `diagnosis.json`、`diagnosis_waits.csv`、`diagnosis_candidates.csv`、`diagnosis_summaries.csv`。
  每项保留物理图 ID、候选与证据路径 edge ID；重新分析不会保留过期候选文件内容。

未校准节点时钟只用于各自本地时长，不能相减为网络延迟，也不累计全局 critical path。
较长 wait 是症状；具体候选与其关联不一律等同于确定硬件根因。

## 视图入口

```bash
python -m hccl.tools.diagnosis.multi_node_trace run.json --output-dir out
python -m hccl.tools.diagnosis.analyze_waits out/RUN --baseline-dir out/NORMAL_RUN
python -m hccl.tools.diagnosis.visualize_html out/RUN/dep_graph_nodes.csv \
  --edges-csv out/RUN/dep_graph_edges.csv --view waits \
  --operations-csv out/RUN/operation_timings.csv \
  --issues-csv out/RUN/dep_graph_notify_ambiguities.csv \
  --diagnosis out/RUN/diagnosis.json --output out/RUN/waits.html
```

`--initial-operation` 可指定实际 scope；execution / waits 使用完整 execution artifact，
resource 使用对应的 `dep_graph_resource_{nodes,edges}.csv`。三者均可传入同一诊断文件。
waits 校验等待 ID 与 execution 一致，不在前端重新构图。phase/operation 筛选可自动聚焦。
resource 默认隐藏纯控制边界，可用复选框恢复；边界不是缺失执行任务。
等待详情可显示候选及真实证据链。CPU span 以独立说明显示，不画成 Copy / Reduce 的设备块。

## 验证入口

```bash
python -m unittest discover -s hccl/tools/diagnosis -p 'test_*.py'
python test/test_aicpu_semantic.py --out-dir test/out/aicpu-unit
node test/check_diagnosis_html.js < waits.html
```

最后一项是 DOM/交互与真实 artifact 的烟测，不等同于浏览器截图验收。
真实设备样例、注入期望/实际定位、off/on、清理与恢复记录见
[测试报告](../../../test/out/ring-nhr-diagnosis/测试结果说明.md)。
