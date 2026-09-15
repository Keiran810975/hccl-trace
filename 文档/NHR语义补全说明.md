# NHR 语义补全说明

## 分支与目标

- 分支：`feat-NHR`
- 基线提交：`a00ddb6`
- 目标：补齐 NHR 测试中未标记的 SDMA，同时保持 NHR hop/step 语义不变。

## 定位结论

最新结果中 `semantic_total=10,416`，operation scope 内 profiler task 为 11,760。
缺失的 1,344 条任务全部是 SDMA，稳定表现为 336 个 FFTS graph 每图 4 条：两条位于
NHR 模板之前，两条位于模板之后。NHR 内部的 1,008 条 AllGather copy SDMA 和
1,008 条 ReduceScatter reduce SDMA均已正确匹配。

这四条任务来自 `CollAllReduceExecutor::RunLoopInner`：

- user input buffer 拷入 CCL input buffer；
- CCL output buffer 拷回 user output buffer。

一个 `HcclD2DMemcpyAsync` 在当前 FFTS 图中会展开为两条 SDMA，因此入口和出口两次
调用合计四条。修复使用非 one-shot 的 `TaskSemanticScope` 包住各次 memcpy，使展开后
的物理任务都获得语义。

## 命名

| 方向 | algorithm / phase | step | event | semantic |
|---|---|---:|---|---|
| user buffer -> CCL input buffer | `allreduce_executor` | 0 | `copy_start` | `user_to_ccl_copy` |
| CCL output buffer -> user buffer | `allreduce_executor` | 1 | `copy_start` | `ccl_to_user_copy` |

这些搬运不属于 NHR hop，因此不使用 `algorithm=nhr`，也不占用 NHR step。
`single_ring_direct` 采用的事件同样是 `copy_start`，但 semantic 使用通用名称
`hccl_local_copy`，并因 direct 算法直接操作 user memory 而归入相应算法 step。

## 设备测试方案

复用当前 8 卡 NHR AllReduce 测试，检查：

1. `nhr` 算法记录仍为 10,416 条，原有 phase/step/event 分布不变；
2. 新增 `allreduce_executor/copy_start` 1,344 条；
3. `user_to_ccl_copy` 与 `ccl_to_user_copy` 各 672 条；
4. operation scope 内 profiler-only SDMA 从 1,344 降为 0；
5. semantic duplicate、profiler duplicate、graph correlation duplicate 均为 0。

本地 Windows 环境缺少项目所需的 Bash/CMake/CANN 构建环境，当前只执行静态 diff
检查；最终结论以设备重新构建和 msprof 回归为准。
