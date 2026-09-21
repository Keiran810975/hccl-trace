# Direct inline reduction 类型兼容修复

2026-09-21，基线 `codex/multinode-diagnosis@03899b0fad54666eb75c4782a1768f6397b246c5`。

## 原因与修改

机器 1 A3 `Ascend910_9362`，CANN 8.5.1、Python 3.11.14、torch 2.9.0+cpu、
torch-npu 2.9.0。四 rank AllReduce，每 rank 8 MiB FP32，1 次预热、3 次测量，
`HCCL_ALGO='level0:null;level1:ring'`、`HCCL_OP_EXPANSION_MODE=HOST`；实际 executor
为 `AllReduceComm`，核心语义为 `ring`。各 rank 全元素结果正确。

528 条语义中，48 条 `reduce_scatter / rx_payload_reduce_start / reduce_inline`
被旧规则排除。逐条读取原始 DB（schema 1.2.0）确认，同 node/device/stream/task
均有且只有一条 TASK，`contextId=4294967295`（direct）、类型为 `MEMCPY_ASYNC`。
例如 node1/device0/stream45/task7、12、17。HCOMM `dispatcher.cc` 的 inline reduce
先调用 `hrtReduceAsync`（转发 `aclrtReduceAsync`），再以 `TASK_REDUCE_INLINE`
记录任务；该路径使用 SDMA reduction，两个层面的类型名不同并不表示执行异常。

只在 `merge_timeline.py` 的 direct `reduce_inline` 兼容项添加 `MEMCPY_ASYNC`。
保留已有 `REDUCE_INLINE`；仍先查精确物理身份。不把任意 SDMA 任务推断为 reduction，
不修改 parser、DB、生产端或 schema。合并行同时保留 semantic `reduce_inline` 与
profiler `sdma / MEMCPY_ASYNC`。FFts 的 parent/context 规则不变。

## 验证

- 新增 DB→parser→merge 回归在旧代码上失败，修复后通过。
- 负例覆盖 node/device/stream/task 不同、FFts context、错误任务类型，以及缺少
  graph correlation 的 FFts 语义；原 `REDUCE_INLINE` 路径保持。
- 本地 Python 3.12 和机器 1 容器 Python 3.11 均通过 81 项单测。
- 原采集路径：`/project/hccl-multinode-env/single-node-20260921-125055`。
- 修复后回放：`/project/hccl-multinode-env/direct-inline-fix-replay`。
- exact：480/528（90.91%）→ 528/528（100%）；未匹配语义 48→0，重复与 invalid
  均为 0。剩余 208 条 profiler-only 是无语义注解的 DB 任务，不属于未匹配语义。
- 对比修复前后 merged CSV，已有 480 条匹配行逐字段完全相同，新增匹配恰为上述 48 条。
- execution 736 节点/948 边，resource 176 节点/396 边；224 条 exact Notify 边；
  无环、缺端或 ambiguity，boundary 0。图门禁、95% trace 门禁和 HTML/SVG 全流程通过。
- 4 个原始 DB 的回放前后 SHA256 一致。仅离线回放，没有重新启动 NPU 工作负载或重编 C++。

远端副本是基线 HEAD 加本地补丁（未提交），补丁及哈希、完整命令/日志保存在回放目录。
本地结果位于 `test/out/remote-env-20260921/evidence/direct-inline-fix-replay/`；原始
失败结果未覆盖。本结论限于本次 A3 HOST Ring 样例，不表示双机或所有 transport 已验收。
