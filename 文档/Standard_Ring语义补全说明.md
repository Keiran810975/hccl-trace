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

`single_ring_direct` 现有实现也使用 `copy_start`，但 semantic 统一写成较宽泛的
`hccl_local_copy`，并把这些 copy 放在 `reduce_scatter_direct/allgather_direct` 的算法
step 中。标准 Ring 的边界 copy 位于公共 executor，因而使用独立 executor phase 和
方向明确的 semantic，避免冒充 Ring step。

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

本地 Windows 环境缺少项目所需的 Bash/CMake/CANN 构建环境，当前只执行静态 diff
检查；最终结论以设备重新构建和 msprof 回归为准。
