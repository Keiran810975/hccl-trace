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

本分支不修改公共 `TaskSemanticEventScope` 或 `TransportP2p`。只在
`AllGatherRing::TxVector/RxVector` 内对单机 inline P2P 复合调用进行等价拆分，并在
各次调用外设置 one-shot event：

| 物理原语 | event | semantic |
|---|---|---|
| send-ready record | `tx_data_signal_start` | `link_tx_data_signal` |
| send-ready wait | `rx_data_signal_start` | `link_rx_data_signal` |
| source-side DMA | `tx_payload_start` | `link_tx_payload` |
| destination-side DMA | `rx_payload_copy_start` | `link_rx_payload_copy` |

AllGather 在算法层提供 `phase/step/slice/peer` context。HCCS/PCIe/SIO/HCCS-SW 的
inline 路径使用 `TxData + TxDataSignal` 和 `RxDataSignal + RxData`，使 signal 与 SDMA
分别消费自己的 event；非 inline/RDMA 路径继续使用原来的 `TxAsync/RxAsync`，留待
`COV-006` 结合多机结果细化。

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

计划合并顺序为 `feat-standard-ring -> feat-NHR -> feat-mesh`。本次收敛后：

- `task_semantic_scope.h/.cc` 与当前 `master` 完全一致，不再移动声明或实现；
- common profiling 的 `task_semantic_trace.h/.cc` 与当前 `master` 完全一致；
- `TransportP2p` 与当前 `master` 完全一致，不会让后续 NHR/mesh 自动获得额外事件；
- standard Ring 的物理事件拆分仅位于 `AllGatherRing::TxVector/RxVector`；
- NHR 与 standard Ring 对公共 executor 边界 copy 的修改相同，顺序合并只保留一份。

因此，Ring 合并不会改变 NHR/mesh 的 scope 生命周期、one-shot 行为或 transport 提交
序列。分支间仍可能因 `task.md` 同一区域的进展记录产生文档冲突，应在合并时保留三方
进展；这不属于 C++ 功能冲突。

本地 Windows 环境缺少项目所需的 Bash/CMake/CANN 构建环境，当前只执行静态 diff
检查；最终结论以设备重新构建和 msprof 回归为准。
