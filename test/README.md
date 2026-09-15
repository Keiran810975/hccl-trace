# HCCL step trace single-node test runbook

当前单机证据见 [阶段归档](../hccl/tools/diagnosis/arch-94a1ab31c3ee.md)。多机采集与异常
测试按 [task.md](../hccl/tools/diagnosis/task.md) 推进；本文不表示这些场景已验证。

本文档说明如何在单机昇腾环境验证当前 step trace 迁移，包括功能正确性和开销。脚本假设从 `hccl-trace` 仓库根目录执行；如需在设备机器上运行，可以整体同步本目录、`hccl/tools/diagnosis` 以及已编译安装的 HCCL/HCOMM 产物。

## 1. 测试目标

功能测试要证明：

- `HCCL_STEP_TRACE=1` 时，运行 single-ring AllReduce 能在 plog 中产生 `[HcclTaskSemantic]` 记录。
- 仅与 msprof consolidated DB 聚合，保留 FFts 展开的 SDMA、Write Value、Notify Wait 和 context id。
- `validate_trace` 的匹配率达到阈值，建议先用 `--min-match-rate 95`。
- 输出中覆盖 `reduce_scatter_direct`、`allgather_direct`，以及 `tx_payload_start`、`rx_payload_copy_start`、`rx_payload_reduce_start`、`copy_start` 等事件。宽泛的 `allreduce_executor` scope 已撤回，不作为验收条件。

开销测试要证明：

- 默认关闭 tracing 时行为正常，且不产生额外语义日志。
- 开启 `HCCL_STEP_TRACE=1` 后端到端耗时没有明显回退。
- 对比时使用同一条 AllReduce 命令、同一消息大小、同一 rank 数、同一 CANN/HCCL/HCOMM 产物。

## 2. 前置条件

在真实设备机器上准备：

- CANN Toolkit/driver 环境可用，`set_env.sh` 已 source。
- 当前 `hcomm` 改动已构建并被运行时加载。HCOMM 变更需要在 `hcomm` 仓库自身验证，不要只构建 `hccl`。
- 有一条稳定的单机 AllReduce 命令，最好是 8 卡 single-ring 路径。
- 能采集 HCCL plog 和 consolidated `msprof_*.db`。

建议先完成构建：

```bash
cd /path/to/hccl-trace/hcomm
bash build.sh --pkg

cd /path/to/hccl-trace/hccl
bash build.sh --pkg
```

如果现场只替换 HCOMM 动态库，请确认 `LD_LIBRARY_PATH` 或安装目录指向新产物。Windows 只适合脚本和离线工具校验，不能作为 HCOMM 构建结论。

## 3. 准备 AllReduce 命令

脚本不绑定具体测试程序，使用 `--` 后面的命令作为被测 workload。例如：

```bash
./some_all_reduce_test --rank-size 8 --count 268435456 --dtype fp32
```

如果你的测试程序需要 `msprof` 包裹，可以直接把完整命令放在 `--` 后面：

```bash
msprof --application="./some_all_reduce_test --rank-size 8 --count 268435456" --output=/tmp/msprof_step_trace
```

推荐固定以下变量：

- rank 数：先用 8 卡单机。
- 算法路径：优先让环境选择当前已插桩的 single-ring AllReduce 910/93 路径。
- 消息大小：功能测试可用中等大小；开销测试建议使用能稳定运行 1 秒以上的规模，减少进程启动噪声。
- 重复次数：开销测试至少 `--repeat 10`，正式结论建议 `--repeat 30`。

## 4. 功能测试流程

1. 清理旧输出目录和旧 profiler 输出。
2. 开启 `HCCL_STEP_TRACE=1` 运行 AllReduce。
3. 从 HCCL plog 中找到包含 `[HcclTaskSemantic]` 的文件。
4. 从每个 `PROF_*` 根目录找到 consolidated `msprof_*.db`。
5. 执行 merge 和 validate。

示例：

```bash
cd /path/to/hccl-trace

bash test/run_step_trace_function_test.sh \
  --out-dir test/out/function \
  --plog /path/to/hccl/plog.log \
  --msprof-db-dir /path/to/msprof \
  --node-id node0 \
  --min-match-rate 95 \
  -- \
  ./some_all_reduce_test --rank-size 8 --count 268435456
```

如果你已经提前跑完 workload，只想合并验证，也可以省略 `--` 后面的命令：

```bash
bash test/run_step_trace_function_test.sh \
  --plog /path/to/hccl/plog.log \
  --msprof-db-dir /path/to/msprof
```

功能通过的最低标准：

- 脚本退出码为 0。
- `semantic_total > 0`。
- `exact_match_rate_percent >= 95`；质量门禁只接受 exact，direct 使用物理 task 身份，FFts 使用 parent/context 身份；已删除 heuristic 匹配。
- `duplicate_semantic_rows == 0` 且 `duplicate_profiler_rows == 0`。
- `test/out/function/merged.csv` 中 `match_status` 主要为 `matched`。
- 默认生成逻辑 `timeline.svg`、物理依赖 `dependency.html` 和可筛选的 `timeline_time.html`。

若不通过，优先检查：

- plog 是否来自新 HCOMM/HCCL 产物。
- workload 是否真的走到 single-ring AllReduce 910/93 路径。
- `msprof_*.db` 是否和 plog 来自同一次运行。
- DB `META_DATA.SCHEMA_VERSION` 是否受支持，`TASK` 是否包含 stream/task/context/connection。
- 每个 consolidated DB 是否只包含一个 device，输入目录是否存在重复 device profile。

## 5. 开销测试流程

开销测试使用 Python wrapper 反复运行同一条命令。它会分别测：

- baseline：`HCCL_STEP_TRACE=0`，同时关闭兼容变量 `HCCL_TASK_SEMANTIC_TRACE=0`。
- trace：`HCCL_STEP_TRACE=1`。

示例：

```bash
cd /path/to/hccl-trace

python3 test/measure_step_trace_overhead.py \
  --repeat 20 \
  --warmup 3 \
  --output test/out/overhead/overhead.csv \
  --summary test/out/overhead/summary.txt \
  -- \
  ./some_all_reduce_test --rank-size 8 --count 268435456
```

输出解读：

- `baseline_mean_s`：关闭 trace 的平均 wall time。
- `trace_mean_s`：开启 trace 的平均 wall time。
- `overhead_percent`：`(trace_mean_s / baseline_mean_s - 1) * 100`。
- CSV 中保留每轮耗时和退出码，失败轮次会让脚本退出非 0。

建议判定：

- 先看 `return_code` 是否全为 0。
- 再比较 median，不要只看单次耗时。
- 如果 workload 本身太短，进程启动和 profiler 开销会淹没 tracing 开销；应增大消息量或循环次数。
- 开销测试不要同时开非常重的 profiler 采集，除非 baseline 和 trace 两组完全一致。

## 6. 推荐产物归档

每轮测试保留：

- 被测源码：根仓 `git rev-parse HEAD`、两个子仓 HEAD 及相关工作树差异；当前实现不能仅由子仓 HEAD 复现。
- 构建日志和运行命令。
- plog 原始文件。
- msprof 原始 consolidated `msprof_*.db`。
- `merged.csv`、`summary.csv`、`validate.log`、`dependency.html`、`timeline_time.html`。
- `overhead.csv`、`summary.txt`。

这样后续定位 unmatched task、duplicate key 或性能抖动时，可以直接回放离线工具。
