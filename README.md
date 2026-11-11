# HCCL-Trace

HCCL-Trace 用于排查 Ascend 训练中的集合通信慢化。它把 msprof 记录的设备任务、
HCOMM 的算法语义和训练侧标注的轮次、通信位置关联起来，沿实测依赖区分源头候选和等待传播。
单机、多机都用同一个命令分析；离线分析不占 NPU。

## 1. 克隆和准备环境

可编辑安装需要支持 PEP 660 的 pip（21.3 或更新版本）。在已有的训练环境或单独的分析环境中执行：

```bash
git clone --branch main --single-branch https://github.com/Keiran810975/hccl-trace.git
# 也可把上面的地址换成 https://gitee.com/tjucyx/hccl-trace.git
cd hccl-trace
git rev-parse HEAD
python3 -m pip install -e .
hccl-diag --help
```

- **采集端**：使用已经能正常训练的 Linux Ascend 环境和 Python 3.9+。加载实际 CANN 环境，
  确认 `msprof` 可用、设备已经分配、原训练能跑完，并预留采集空间。GPT-2 样例另外需要兼容的
  `torch`、`torch_npu` 和 `transformers`。
- **通信库**：必须实际加载和本次提交配套的 HCOMM Host 库；AI_CPU 路径还需要配套 Device 包。
  Python 安装不会部署这些库，也不会更改驱动或验签策略。新设备按[配套库部署指南](docs/deployment.md)准备。
- **分析端**：可以是另一台 CPU 机器。安装同一提交即可，运行分析不需要 CANN、PyTorch 或 NPU。
  当前读取 consolidated `msprof_*.db` schema `1.2.0`；工具有 CANN 8.5.1 设备验证记录，
  新软硬件组合应先跑下面的短采集，不能把安装成功当作兼容性已验证。

## 2. 先跑通单机样例

[GPT-2 Small 样例](examples/gpt2_normal.py)使用随机初始权重和合成 token，
会做前向、反向、梯度桶 AllReduce 和参数更新，不下载模型、不注入异常。
下面以单机 2 Rank 为例。将 `DEVICES` 换成已分配的实际 runtime 设备 ID，顺序与本地 Rank 对应。
若 profiler 里的 ID 不同，额外给样例传 `--profiler-devices`，不要用 Rank 代替设备 ID。

```bash
RUN_ID="gpt2-$(date -u +%Y%m%dT%H%M%SZ)"
DEVICES=1,3
hccl-diag capture -o "runs/$RUN_ID" --node node-a --run-id "$RUN_ID" -- \
  torchrun --standalone --nproc-per-node=2 --max-restarts=0 \
  examples/gpt2_normal.py --devices "$DEVICES" --warmup 2 --iterations 8

hccl-diag analyze "runs/$RUN_ID" -o "reports/$RUN_ID" --keep-debug
```

`capture` 运行 `--` 后面的原启动命令，自动打开 HCOMM 语义和低日志 msprof 采集，
不采集 AI Core 性能计数器，但仍采集任务时间线和通信关联所需的 Host API。不要再套一层 profiler。
采集结束后保留整个 `runs/$RUN_ID/`，尤其是每个 `nodes/<node>/` 下的 `msprof/`、`plog/` 和 `calls/`。
`collection.json` 和 `profiler.log` 用于排查采集失败。不要只拷走 DB 或删掉 PROF 目录里的会话元数据。

`analyze` 只读原始采集，输出必须是采集目录之外的一个新目录。省略 `-o` 时输出到采集目录旁边的
`<capture>-report/`。第一次建议加 `--keep-debug`，完整任务关联、依赖图和分析中间结果会留在并列的
`<report>.debug/`。不加这个选项不会删除原始采集。

## 3. 换成自己的训练

单机、多机都用显式通信打点。保留原来的分布式启动方式、Rank 分配、通信域和同步语义：

1. 每个 Rank 创建一个 `Trace`，传实际 profiler 设备 ID，并注册实际通信域的全局 Rank 列表。
2. 用 `trace.iteration(...)` 标记轮次，用 `trace.collective(...)` 包住实际通信 API。
   同一位置每轮用相同的 `call_site`，通信类型、元素数、数据类型按真实 API 填写。
3. 在原训练已有且能证实设备已完成的边界之后，调用 `trace.completion_boundary()`。
   它只记录时间，不执行同步；一个完成边界可以覆盖多个通信调用。

下面展示如何接入**已有的显式 FP32 AllReduce**；变量和完成点换成原训练中的对应内容。

```python
import torch.distributed as dist
from hccl_trace import Trace

with Trace.from_environment(device_id=profiler_device_id) as trace:
    trace.group("dp", dp_global_ranks)
    for stage, steps in (("warmup", warmup_steps), ("measured", measured_steps)):
        for step in range(steps):
            with trace.iteration(step, stage=stage):
                # Keep the original forward/backward and obtain the actual gradient tensor.
                with trace.collective(group="dp", call_site="gradient.bucket.0",
                                      operation_type="AllReduce", element_count=grad.numel(),
                                      dtype="float32", reduction="sum"):
                    dist.all_reduce(grad, group=dp_group)
                existing_verified_device_completion_boundary()  # Replace with the real boundary.
                trace.completion_boundary()
```

示例里的完成边界函数是占位符，不由 SDK 提供。最后一行必须放到**实际完成点**，不要照搬到通信 API 返回之后：Python 返回或只建立流依赖的
`Work.wait()` 不一定代表设备完成。DDP/FSDP 等框架需要在真实通信 Hook 或适配层打点，
只包训练 step 或 `backward()` 不会自动识别内部梯度桶。也不要为了打点给每个桶强加一次同步。
在 profiler 时钟证据完整时，`trace.iteration` 已自动记录轮起点；报告里的
`iteration_start_observations` 比较任务相对轮起点的开始时间，不需要额外打点，也不将晚开工视为根因。
若要诊断 Host 调用前准备变长，在准备实际开始时读取 `CLOCK_MONOTONIC_RAW`，将纳秒值通过
`preparation_start_raw_ns` 传给该次 `trace.collective`；仅记录 API 的前后时刻不能补出准备起点。

接入后，在上节命令里把 `--` 之后换回自己的启动命令。先短跑，确认各 Rank 数值和采集都正常，再扩大规模。
日常分析默认和本次运行的过去正式轮比较。需要独立正常对照时，另外采集同形状、通信域、软件和算法配置的运行：

```bash
hccl-diag analyze runs/suspect --baseline runs/normal -o reports/against-normal
```

独立对照需要显式通信打点，主要比较设备执行，不替代默认的 Host 准备区间诊断。

## 4. 多机：每机采集一次，汇集后分析

每个训练节点使用相同提交、相同的 `RUN_ID`，分别指定不同的 `NODE_ID` 和本节点启动参数。
下例假定原训练已能在两台机器上各跑 2 Rank。节点 A 用 `NODE_ID=node-a`、`NODE_RANK=0`，
节点 B 用 `NODE_ID=node-b`、`NODE_RANK=1`。两边的 `MASTER_ADDR`、端口及 `RUN_ID` 相同，
`DEVICES` 按本机实际映射设置。

```bash
RUN_ID=gpt2-two-node-01
NODE_ID=node-a
NODE_RANK=0
MASTER_ADDR=node-a.internal   # Replace with the reachable training address.
DEVICES=1,3                  # Replace with local runtime IDs.

hccl-diag capture -o "runs/$RUN_ID-$NODE_ID" --node "$NODE_ID" --run-id "$RUN_ID" -- \
  torchrun --nnodes=2 --nproc-per-node=2 --node-rank="$NODE_RANK" \
  --master-addr="$MASTER_ADDR" --master-port=29500 --max-restarts=0 \
  examples/gpt2_normal.py --devices "$DEVICES" --warmup 2 --iterations 8
```

两边退出后，把两个完整采集目录传到分析机的 `runs/`。以下命令在分析机执行；
`join` 复制并逐文件校验 SHA-256，不会删除输入。

```bash
hccl-diag join runs/gpt2-two-node-01-node-a runs/gpt2-two-node-01-node-b \
  -o runs/gpt2-two-node-01
hccl-diag analyze runs/gpt2-two-node-01 -o reports/gpt2-two-node-01 --keep-debug
```

没有校时证据时，只解读各节点本地时长和可验证的跨节点依赖，不直接比较两机绝对时间。
如果需要跨机时序，**采集前**先按[多机校时指南](docs/multi-node-clocks.md)安排前后探针，
分析时再加 `--require-clock-alignment`。

## 5. 怎么看结果

| 文件 | 看什么 |
| --- | --- |
| `execution.html` | 看设备任务和真实依赖。默认滚动报告展示相关正式轮的原图切片，不是全程。 |
| `root_causes.json` | 先看 `quality` 和 `coverage`，再看 `communication_source_candidates`、`external_anomaly_clues` 和 `unresolved_observations`。候选包含 Rank、轮次、通信位置、实际与参考耗时。 |
| `propagation.html` | 看候选通过哪些依赖到达慢 Wait，以及哪里缺少继续回溯的证据。 |

两个 HTML 可离线用浏览器打开。默认诊断取最近最多五个未标慢的可比正式样本，沿已建立的依赖回查；
候选并列，不选 Top1。对特定单机双流 Copy，才会在样本不足时用第 6–10 个预热轮补重叠预算，
不改变普通任务的正式轮参考。详见[诊断规则](hccl/tools/diagnosis/README.md)。

采集成功不等于训练数值正确，分析成功也不等于定位了物理故障。没有候选时先检查样本和关联覆盖率，
不要直接判定没有异常。若分析失败，按报错分别检查输入/绑定（退出码 2）、语义关联（3）、
构图/诊断（4）和报告发布（5）。优先修复设备映射、实际加载的库或训练打点，不降低门禁来绕过缺失证据。

## 项目结构

| 路径 | 用途 |
| --- | --- |
| [`hccl_trace/`](hccl_trace/) | 训练侧 SDK，记录轮次、实际通信调用和完成边界。 |
| [`hccl/tools/diagnosis/`](hccl/tools/diagnosis/) | `hccl-diag` 的采集、解析、构图、诊断和报告模块。 |
| [`examples/gpt2_normal.py`](examples/gpt2_normal.py) | 唯一随本工具发布的训练样例，无异常注入。 |
| [`hcomm/`](hcomm/) 和 [`hccl/`](hccl/) | 配套通信库源代码、构建打包及其原生回归入口，不是诊断实验脚本。 |

历史异常注入、研究实验和旧文档不随 `main` 的用户版发布。
