# Standard Ring 语义补全说明

## 分支与目标

- 分支：`feat-standard-ring`
- 基线提交：`5b43135`
- 目标：修复 AllGather 的 notify/payload 语义错位，并补齐 AllReduce executor 的
  user/CCL buffer 边界搬运。

## 问题与实现

设备结果包含 336 个 FFTS graph。每个 graph 的 AllGather 有 7 条实际 SDMA 未标，
同时 `rx_payload_copy_start` 错误落在前置 `notify_wait` 上。根因是 one-shot event
scope 包住了复合 `TxVector/RxVector`，而 `TransportP2p::RxAsync` 会先提交 signal wait，
再提交 SDMA。

本分支将 `TaskSemanticEventScope` 移到 common profiling 层，并在
`TransportP2p` 的真实物理原语处设置事件：

| 物理原语 | event | semantic |
|---|---|---|
| send-ready record | `tx_data_signal_start` | `link_tx_data_signal` |
| send-ready wait | `rx_data_signal_start` | `link_rx_data_signal` |
| source-side DMA | `tx_payload_start` | `link_tx_payload` |
| destination-side DMA | `rx_payload_copy_start` | `link_rx_payload_copy` |

AllGather 仍在算法层提供 `phase/step/slice/peer` context，但不再在复合 transport
调用外层设置 one-shot event。

AllReduce executor 的边界搬运采用：

| 方向 | algorithm / phase | step | event | semantic |
|---|---|---:|---|---|
| user buffer -> CCL input buffer | `allreduce_executor` | 0 | `copy_start` | `user_to_ccl_copy` |
| CCL output buffer -> user buffer | `allreduce_executor` | 1 | `copy_start` | `ccl_to_user_copy` |

`single_ring_direct` 同样使用 `copy_start`。本次把其中真实跨越 user/CCL buffer 的
copy 统一为 `user_to_ccl_copy`、`ccl_to_user_copy`；user→user、CCL→CCL 和单 rank
本地 copy 继续使用 `hccl_local_copy`。这些 direct copy 仍属于
`reduce_scatter_direct/allgather_direct` 的当前算法 step；标准 Ring 的边界 copy 位于
公共 executor，因此使用独立 executor phase，避免冒充 Ring step。

## 设备测试方案

复用 8 卡 standard Ring AllReduce 命令和诊断流程。除原有 exact match、duplicate、
phase/step/peer 检查外，增加以下断言：

1. operation scope 内 SDMA 总数仍为 6,384，profiler-only SDMA 从 3,696 降为 0；
2. `allgather/rx_payload_copy_start/sdma` 为 2,352 条；
3. `allgather/rx_data_signal_start/notify_wait` 与
   `allgather/tx_data_signal_start/notify_record` 各为 2,352 条；
4. `allreduce_executor/copy_start` 为 1,344 条，其中两个方向各 672 条；
5. 允许剩余每 graph 4 条尚未建模的 phase-end notify，但不得再有 operation-scoped
   profiler-only SDMA。
6. 回归 `single_ring_direct`，确认边界 copy 的 semantic 已按方向拆分，原 phase/step、
   task 数和 exact match 率不变。

## 合并顺序兼容性

计划合并顺序为 `feat-standard-ring -> feat-NHR -> feat-mesh`。scope 调整具备以下性质：

- `TaskSemanticEventScope` 的类名、namespace、构造/析构签名和 one-shot 行为不变，只把
  声明从算法 component header 移到其原本已包含的 common profiling header，把实现从
  `task_semantic_scope.cc` 移到 `task_semantic_trace.cc`；不改变 ABI 符号；
- 两个实现文件都通过 CMake `target_sources` 编入同一个 `hccl_alg` target；
- `feat-NHR`、`feat-mesh` 均未修改 scope、common profiling 或 P2P transport 文件；
- NHR/mesh 继续包含 `task_semantic_scope.h`，该 header 仍包含
  `task_semantic_trace.h`，所以现有 `TaskSemanticEventScope` 调用无需修改；
- P2P transport 的 event scope 只有在线程上已有算法 `TaskSemanticTraceInfo` 时才激活，
  未插桩算法和关闭 trace 的执行路径不产生语义，也不改变通信原语。

`git merge-tree` 对 standard Ring/NHR、standard Ring/mesh、NHR/mesh 三组分支均未发现
内容冲突。NHR 与 standard Ring 对公共 executor 边界 copy 的修改相同，顺序合并时只
保留一份；各分支的 `task.md` 修改位于不同任务段。

本地 Windows 环境缺少项目所需的 Bash/CMake/CANN 构建环境，当前只执行静态 diff
检查；最终结论以设备重新构建和 msprof 回归为准。
