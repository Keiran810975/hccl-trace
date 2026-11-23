# HCCL-Trace

HCCL-Trace 排查 Ascend 训练中的集合通信异常。运行 `hccl-diag online` 后：

1. **训练中分类告警**：识别 H1（Rank 未进入通信）、S1（有调用前延迟证据的慢通信）
   和 S2（其余已测得的慢通信），报告轮次、通信位置和有证据支持的可疑 Rank。
2. **自动追查慢通信**：设备 Task 数据就绪后，后台对 S1 回溯入口 Wait 和可核验的上游，
   对 S2 列出通信内各 Rank 的慢 Task/Wait、所属算法 Step 和下游传播，生成该轮依赖图与传播报告。

**只有第一步不需要等 msprof 封存。** 普通 `capture` 在采集结束后自动接上第二步；
要在训练仍在跑时看到 Task 或依赖图，需要另外提供相应的已封存输入，见[在线追查模式](#6-在线追查模式)。
也可用 `hccl-diag analyze` 手动分析已有采集；单机、多机用同一命令，CPU 即可运行。

## 1. 克隆和准备环境

```bash
git clone --branch submit --single-branch https://github.com/Keiran810975/hccl-trace.git
cd hccl-trace
python3 -m pip install -e .
hccl-diag --help
```

需要 Python 3.9+，可编辑安装需要 pip 21.3+。训练节点使用能正常运行原任务的 Linux + Ascend 环境，
装好匹配的驱动、固件、CANN 和训练框架。样例使用兼容的 `torch`、`torch_npu` 和 `transformers`，
随机初始化 GPT-2 Small，用合成 token 训练，不下载权重、不注入异常。CPU 分析机只需安装同一提交；
离线读取 consolidated `msprof_*.db` schema `1.2.0`，保留 DB 旁的 PROF 会话元数据。

在训练节点加载现场实际 Toolkit，确认工具和已分配设备可用：

```bash
export CANN_ROOT=/usr/local/Ascend/ascend-toolkit/latest
source "$CANN_ROOT/set_env.sh"
command -v msprof
npu-smi info
python3 -c 'import torch, torch_npu; print(torch.__version__, torch_npu.__version__)'
```

**必须实际加载与本提交配套的语义采集库。** 优先使用管理员交付、已核验的 HCOMM Host 库组和
当前芯片需要的 Device 包。仅安装 Python 不会部署这些库；用官方未打点的库运行不能替代这一环。

- Host：在有匹配 CANN 开发头、编译器、CMake、ccache 和构建依赖的 Linux 上可执行
  `(cd hcomm && bash build.sh --pkg -p "$CANN_ROOT")`。把配套的
  `libhcomm.so`、`libhccl_alg.so`、`libhccl_plf.so` 部署到私有运行目录，与现场 HCCL 前端保持 ABI 兼容。
  `export LD_LIBRARY_PATH="$HOME/hccl-trace-runtime/lib64:${LD_LIBRARY_PATH:-}"` 后，
  在自己的短跑进程中通过加载日志或 `/proc/<pid>/maps` 确认实际路径。
- AI_CPU：Host 库不能替代设备内部语义。请由管理员按目标芯片和 SDK 构建、签名并部署同一提交的
  `aicpu_hcomm.tar.gz`。用 `sha256sum` 核对包，不覆盖共享 CANN，不更改全局验签或驱动配置；
  无权部署时停止。若现场批准临时变更，先做独立回滚，采集结束或中断后核对恢复。
- 映射：样例 `--devices` 按本地 Rank 顺序填写 **runtime 设备 ID**。如果 msprof 记录的 ID 不同，
  另传 `--profiler-devices` 指明对应的 **profiler device ID**。以实际 msprof 设备元数据核对，
  不能用全局 Rank、逻辑序号或物理卡号猜。

RHD（Recursive Halving-Doubling）AllReduce 走配套 HCOMM 模板时，任务可以记录为
`algorithm=rhd`，分别标出 ReduceScatter、AllGather 的递归 Step，以及非 2 次幂 Rank 的
折叠和回传阶段。采集指令不变，实际选路仍由 HCCL 决定。复合传输调用的标签只表示所属阶段，
不代表逐笔 RDMA 硬件传输时长。

## 2. 配置报告目录

根目录的 [config.yaml](config.yaml) 可直接编辑：

```yaml
online_output_dir: reports/online
online_report_output_dir: reports/online-details
offline_output_dir: reports/offline
```

| 配置项 | 默认放置位置 | 内容 |
| --- | --- | --- |
| `online_output_dir` | `reports/online/RUN_ID/` | `events.jsonl` 在线告警；同目录保留 `measurements.jsonl`、`telemetry.jsonl`、`run_health.jsonl` |
| `online_report_output_dir` | `reports/online-details/RUN_ID/` | `diagnostics.jsonl` 记录追查进度；详细报告放在 `iterations/iter-N/`，快报模式的文件见第 6 节 |
| `offline_output_dir` | `reports/offline/RUN_ID/` | 手动运行 `hccl-diag analyze` 的报告 |

在线产物写在**收集器所在的机器**，各训练节点不分别生成告警文件。三个配置目录不能相同或互相包含。
配置加载顺序为 `--config`、`HCCL_TRACE_CONFIG`、当前目录的 `config.yaml`；配置里的相对路径以
配置文件所在目录为准，缺省项用上表默认值。重复运行请用新的 `RUN_ID`，工具不会覆盖已有报告。
`online -o`、`online --report-output` 和 `analyze -o` 分别覆盖各自的最终目录，不再追加 `RUN_ID`。
原始采集目录由 `capture -o` 指定，在线 worker 从 `--capture` 读取；两者都不由输出配置决定。

## 3. 启动：先跑通 GPT-2 样例

以下以单机 2 Rank 为例。要在线观察时，**先**在终端 A 启动收集器，等它打印监听地址：

```bash
hccl-diag online gpt2-001 --config ./config.yaml --expected-ranks 2
```

终端 B 在同一仓库目录启动训练，把 `DEVICES` 改成实配 ID：

```bash
RUN_ID=gpt2-001
DEVICES=1,3
export HCCL_TRACE_ONLINE_ADDR=127.0.0.1:7341
export HCCL_TRACE_ONLINE_TIMING=npu_event

hccl-diag capture --run-id "$RUN_ID" -o "runs/$RUN_ID" -- \
  torchrun --standalone --nproc-per-node=2 --max-restarts=0 \
  examples/gpt2_normal.py --devices "$DEVICES"
```

只做离线时，跳过收集器并清掉上述两个在线变量。只要 H1 而不做慢化，可将计时模式改为 `host`。
启用 `npu_event` 后，样例默认做 3 个不进入基线的启动步、10 轮预热、20 轮正式训练；
调整 `--warmup` 时须同步调整收集器的 `--warmup-iterations`。如果需要在运行结束时核查预期覆盖，
在收集器上加 `--expected-ranks` 和 `--expected-collectives`；后者是全组逻辑通信次数（预热加正式，
不乘 Rank 数，不含启动步）。打开另一个终端可随时看 `tail -F reports/online/gpt2-001/events.jsonl`。
如需自动追查，训练结束后继续保留收集器，等 msprof 封存和后台报告发布后再用 Ctrl+C 停止。

`capture` 自动打开语义打点和低日志 msprof 采集；不要再套一层 profiler。它会保留设备任务时间线
和通信绑定需要的 Host API，不采集 AI Core 性能计数器。保存整个 `runs/$RUN_ID`，尤其是
`nodes/<node>/` 下的 `plog/`、`msprof/` 和 `calls/`。不要只复制 DB。
采集目录使用上面的默认路径时，在线收集器会自动寻找已完成的采集来补发慢化报告。
没有开启在线时，或想独立离线重看时，在采集结束后用 CPU 执行：

```bash
hccl-diag analyze "runs/$RUN_ID"
```

工具按采集声明的运行 ID 查找在线告警；在线报告在别处时用 `--online /path/to/online/RUN_ID`。
没有在线日志时走默认 Backtrace。若有在线日志但希望独立分析，不按在线慢告警选通信，加
`--without-online`。有单独的匹配正常采集时，也可用 `--baseline /path/to/normal-capture`
做离线对照（不能同用 `--online`）。中间文件只在临时目录使用，结束后清理，不删除原始输入。
分析大型采集前确保临时盘有余量，必要时把 `TMPDIR` 指向有空间的目录。

## 4. 换成自己的训练：只给真实的轮次、通信和完成点打点

保留原 launcher、通信域和同步方案。每个 Rank 建一个 `Trace`，注册真实通信域的全局 Rank 列表；
轮次从 0 开始，明确区分 `warmup` 和 `measured`。用同一个 `call_site` 表示不同轮次的同一位置，
按真实 API 填 type、元素数、dtype、规约类型。
下面是从样例抽出的显式 AllReduce 写法，`flat` 是你的实际 FP32 梯度桶，`prepare_bucket`
代表原有的梯度打包；其他训练代码照旧：

```python
import torch.distributed as dist
import torch_npu
from hccl_trace import Trace
from hccl_trace.npu_event import NpuEventTiming

# 在原代码初始化分布式通信和设备之后建立 Trace。
timing = NpuEventTiming.from_environment(
    torch_npu.npu, torch_npu_version=getattr(torch_npu, "__version__", None)
)
with Trace.from_environment(device_id=profiler_device_id, timing_adapter=timing) as trace:
    trace.group("dp", range(dist.get_world_size()))  # 对应这里使用的默认进程组。
    for stage, steps in (("warmup", 10), ("measured", 20)):
        for step in range(steps):
            with trace.iteration(step, stage=stage):
                # 原有前向、反向得到梯度。
                prep = trace.mark_preparation()  # 可选：实际准备开始，供 S1 比较。
                flat = prepare_bucket()
                trace.call_collective(
                    lambda: dist.all_reduce(flat, op=dist.ReduceOp.SUM, async_op=True),
                    wait_for_work=True, group="dp", call_site="gradient.bucket.0",
                    operation_type="AllReduce", element_count=flat.numel(),
                    dtype="float32", reduction="sum",
                    preparation_start_raw_ns=prep, preparation_definition="pack_to_submit",
                )
                # 保留原有后续训练逻辑。在原有且已确认设备全部完成的边界之后打点：
                torch_npu.npu.synchronize()  # 这里只示意原训练已有的同步，不要求新增。
                trace.completion_boundary()
```

- 在线 ENTER 必须包住**实际通信提交函数**，不能把前向、打包或延迟放进 `lambda`。Host 准备标记是可选的；
  缺这个起点时不能凭 API 进入时间独立证实准备延迟。已明确的本地轮起点不需要再给每个任务打点。
- `wait_for_work=True` 只用于本来就在该位置调用 `Work.wait()` 的路径。Python API 返回或单独的
  `Work.wait()` 不保证设备完成；不要把它们当成 `completion_boundary()`，也不要给每桶强加设备同步。
  样例的在线 Event 是消费流区间，内部可能包含排队与依赖；未独立验证前不能当作原生 HCCL 执行区间。
- PyTorch DDP/FSDP 只包 `backward()` 不能自动得到各桶身份。应在真实通信 Hook/框架适配层打点，
  保留现有 future、规约和同步行为；不支持把异步 DDP Hook 直接替换成上面的同步示例来保证在线计时。
  纯离线也可用 `with trace.collective(...):` 包住显式 API。推荐先照着
  [GPT-2 样例](examples/gpt2_normal.py) 验证后再扩到自定义训练。

要自动生成整轮报告，`completion_boundary()` 必须放在对应的 `trace.iteration(...)` 内；
工具用各 Rank 的已结束轮次边界检查通信是否完成并裁出设备图，不会额外插入同步。

## 5. 多机采集

每台机器采集自己的 Rank；两边使用同一提交和 `RUN_ID`，节点名不同。两机各 2 Rank 时：
A 用 `NODE_ID=node-a`、`NODE_RANK=0`，B 用 `NODE_ID=node-b`、`NODE_RANK=1`。
`MASTER_ADDR` 填 A 的可达私网地址，`DEVICES` 填本机设备 ID。

```bash
hccl-diag capture --node "$NODE_ID" --run-id "$RUN_ID" -o "runs/$RUN_ID-$NODE_ID" -- \
  torchrun --nnodes=2 --nproc-per-node=2 --node-rank="$NODE_RANK" \
  --master-addr="$MASTER_ADDR" --master-port=29500 --max-restarts=0 \
  examples/gpt2_normal.py --devices "$DEVICES"
```

多机仍只启动**一个**在线收集器，例如 `hccl-diag online "$RUN_ID" --listen "$COLLECTOR_IP" --expected-ranks 4`。
要同时检测 Slow，各训练节点统一设置 `HCCL_TRACE_ONLINE_ADDR=$COLLECTOR_IP:7341` 和
`HCCL_TRACE_ONLINE_TIMING=npu_event`，并使用样例里的计时适配器。收集器和各训练节点均需事先设置
同一个 `HCCL_TRACE_ONLINE_TOKEN`；不要把 Token 写进配置或日志。连接不加密，不暴露到公网。

训练退出后，将两份完整采集转移到**收集器可访问**的分析目录，用 `join` 汇集。
若需要自动报告，汇集目录应与收集器启动时传入的 `--capture` 一致；默认是 `runs/RUN_ID`。
每个 profiler device 必须有对应的完整 Rank 观测；
SDK 记录了 `WORLD_SIZE` 时还会核对全组 Rank。 `join` 不修改输入，逐文件校验完成后才发布目的目录：

```bash
hccl-diag join "runs/$RUN_ID-node-a" "runs/$RUN_ID-node-b" -o "runs/$RUN_ID"
# 此时在线收集器会自动处理已告警的轮；无需再跑 analyze。
# 如需另出一份离线报告，才运行：hccl-diag analyze "runs/$RUN_ID"
```

无可信校时时不跨节点比较绝对时间。确需跨钟顺序时，采集前用
`hccl-diag clock-probe serve` 启动私网参考端，其他节点分别在采集前后执行
`hccl-diag clock-probe probe --phase before/after`（每次填写一个 phase），用各子命令
`--help` 查看地址、节点名和采集 ID 参数。把探针文件放进各自采集目录，在其
`capture.json` 的对应 `nodes` 条目中用 `clock_probe_files` 声明相对路径；`join` 会保留。
参考端的 `serve --timeout` 需要覆盖训练、profiler 结束和采后探针。分析时加
`--require-clock-alignment` 可要求校时通过；没有跨机校时证据时，Timeline 各节点分别以本地起点显示，
同机设备缺少有效校时时也各用自己的起点，
不能把相同横坐标当成同时发生。Notify 配对由端点身份和通道顺序决定，校时只用于核验时间关系。
跨设备比较需考虑两端误差；缺少可靠时钟或精确生产者时，保留能验证的依赖，不猜测实际阻塞时长。
RDMA 提交任务不是网卡传输完成事件。

按次取数试用：知道目标调用在 msprof 中的精确通信组、调用名和 profiler device ID 后，可以运行：

```bash
hccl-diag slice-collop /path/to/PROF_XXX --phase s2-internal \
  --device-id 1 --group-name "$DB_GROUP_NAME" --op-name "$DB_OP_NAME" > s2-internal.json
```

对原始 `PROF_*` 目录，命令默认等 30 秒，然后复制原始文件、导出副本中的 DB，再只返回目标调用。
S1 用 `s1-upstream`，另取设备开工前 1 秒；S2 首次分析后可再运行 `s2-downstream`，
默认再等 30 秒，另取该设备上通信完成后 30 秒内重叠的 Task。等待和窗口长度可分别覆盖。
输入已封存的 `msprof_*.db` 则默认立即提取，不重新导出。多 Rank 按各自的 profiler device ID 取数。
原始文件复制上限为 192 MiB；复制期间检测到源变化时拒绝导出。本命令不修改原始采集。

这是手动取数入口，不自动订阅 Slow 告警，不做语义关联或溯源，也不把导出成功认作数据齐全。
没有目标或没有 Task 时以 JSON 状态区分；`coverage_verified` 为 false 代表覆盖未认证。

## 6. 在线追查模式

| 启动方式（均从 `hccl-diag online RUN_ID` 开始） | 设备数据来源 | 分型之后生成什么 |
| --- | --- | --- |
| 默认，或加 `--capture PATH` | 采集结束后封存的 DB、语义日志和 SDK 日志；多机先 `join` | S1/S2 整轮依赖图及传播报告三件套 |
| 加 `--iteration-snapshots PATH` | 外部生产端提供的全 Rank 封存轮次快照 | 同上；快照齐全时可在训练结束前发布 |
| 加 `--slow-tasks-only` | 同上两种封存输入，可配合 `--iteration-snapshots` | 只输出 S2 的 `iterations/iter-N/slow_tasks.json`，不构图 |
| 加 `--task-batches PATH` | 外部生产端提供的、已精确关联的 Rank Task 批次 | 只输出 S2 的增量首报 `slow_tasks.jsonl`，不构图 |
| 加 `--no-detailed-reports` | 不读设备 Task | 仅告警和测量日志 |

以上模式不改变 H1/S1/S2 分类。**默认详细报告也包含慢 Task/Step，不必加快报开关。**
但快报是详细报告的替代模式：当前一次收集器运行不会自动「先发增量首报、再补依赖图」。
手动 `slice-collop` 里的 30 秒等待不是在线 worker 的定时导出策略。

**默认详细追查**

H1 只写告警，不尝试给未完成的通信构图。只有正式轮的 Slow 才排队，同一轮的多个慢桶共用一份图和报告。
所有 Rank 的轮次边界、已完成的设备 Task 和该轮各通信的在线状态都到齐后，独立 CPU 进程再处理，
不持有收集器的接收锁，训练也无需等待报告。优先用 SDK 记录的 `WORLD_SIZE` 核对整轮覆盖，
旧日志没有这个字段时，在收集器上指定 `--expected-ranks`。

- `online_report_output_dir/RUN_ID/diagnostics.jsonl` 记录进度。
  `waiting_for_sealed_trace` 表示还没有可读的封存输入；`waiting_for_all_ranks` 表示 Rank 覆盖不全；
  `waiting_for_final_online_results` 表示该轮通信状态未齐。看到 `published` 再按该行的 `report` 路径打开产物；
  `failed` 或 `unfinished_on_shutdown` 不会撤回已写出的分类告警。
- 在同一详细报告目录下生成 `iterations/iter-N/execution.html`、`root_causes.json`、`propagation.html`。
  在 JSON 的 `online_followup.alerts` 按告警看明细：S1 看准备区间、可能晚开工的 Rank 和 Wait 上游；
  S2 看 `slow_tasks_by_rank`（同位置历史均值的至少两倍）及 `downstream_propagation`。
  证据齐全时还可展示接收端跨机协议区间；它不等于逐笔 RDMA 硬件传输时间。
  图按每个 Rank 的本地轮次起止裁出该轮所有**已采到**的设备 Task 和证据支持的边，
  包括正常桶；必要的上游端点可以超出目标轮。只保留最近至多 10 个连续正式轮作为分析历史，
  没有可比历史或校时证据时不猜测。后台满时记录 `skipped_queue_full`，保留原告警。
- 默认输入是 `runs/RUN_ID`。自定义目录（包括多机合并后的目录）在启动收集器时传
  `--capture /path/to/assembled-capture`。标准 `hccl-diag capture` 的 msprof 汇总 DB 只在采集封存后
  用于这条路径，因此可以自动出报告，但这并不意味着训练过程中已有实时设备 Task 流。
  采集封存或多机 `join` 后，可用 `tail -F reports/online-details/RUN_ID/diagnostics.jsonl` 等到发布。
- 如果部署环境已有兼容且验证过的训练中分段导出器，可启动
  `hccl-diag online RUN_ID --iteration-snapshots /path/to/spool`。生产者须先准备与普通采集同结构的
  `/path/to/spool/iter-N/`，含全 Rank 的已封存 DB、语义日志、完整 SDK 日志及目标轮结束标记，
  并保留所需历史。SDK 日志必须有该快照的完整序列和 `capture_end`，原在线通信 token 不能改。
  完成后将下面的 `online-ready.json` 原子放入该目录，再保持快照不可变：

  ```json
  {"schema_version": 1, "run_id": "gpt2-001", "iteration": 5, "complete": true}
  ```

  此模式在训练仍在继续时即可处理已封存的轮。本仓没有为所有 CANN 版本实现训练中的设备 Task 导出器，
  不读取仍在更新的 DB，也不把 Host 提交或 Rank 总耗时当作设备 Task 完成。默认启用的标准采集回退仍然可用。
- Ctrl+C 停止收集器后，后台排空预算由 `--report-drain-seconds` 控制（默认 120 秒）。
  多机传输、汇集或大型诊断耗时较长时，先等 `published` 再停收集器，不要只依赖排空时间。

**只看 S2 慢 Task/step**：启动时加 `--slow-tasks-only`，例如：

```bash
hccl-diag online gpt2-001 --expected-ranks 8 --slow-tasks-only --report-drain-seconds 240
```

Hang/Slow 告警不变；后台只对 S2 涉及的通信出快报，不构建依赖边、不生成 HTML 或传播报告。
在 `online_report_output_dir/RUN_ID/diagnostics.jsonl` 看到 `published` 后，打开对应
`iterations/iter-N/slow_tasks.json`。`alerts[].tasks_by_rank` 分列 Task 和 Wait，包含
phase/step、stream/task ID、本地设备时间、实际耗时、历史参考及慢化百分比。
同 Rank、同位置唯一匹配，至少需要 3 个有效历史样本，增量达到 100% 才列入。
没有精确 step、依赖关系才能关联的未标注任务，以及历史不足的任务只计入覆盖，不猜测慢化和物理根因。
快报是纯耗时观测，不执行基于前序间隙、Copy 重叠或依赖关系的完整分析，内容可能与详细报告不同。

该模式仍需要已封存的设备 Task 数据。训练期间要看结果，应同时提供上述
`--iteration-snapshots`，每份快照须带目标轮和可比较的历史。普通 msprof 采集则等最终 DB
封存（多机需要汇集），不会从在线 CollOp 总时长推算内部 Task。

**增量首报（需要预关联数据输入）**：

```bash
hccl-diag online gpt2-001 --expected-ranks 8 --task-batches /path/to/task-batches
tail -f reports/online-details/gpt2-001/slow_tasks.jsonl
```

与 `--capture`、`--iteration-snapshots` 是不同输入模式，不混用。S2 告警出现后，每个 Rank 的
目标调用一旦就绪便独立发布；按绝对增量最多展示 3 条慢 Task 和 3 条慢 Wait，不等其他 Rank，
也不生成图。5 秒仍缺输入时会报告待补 Rank，最多再等待到告警被处理后 60 秒或 worker 关闭。
`observed_latency_ms` 从 worker 读到告警算起，不是设备执行到告警的总时延。

输入由可信的采集/关联端写到 `iter-N/rank-R.json`，临时文件写完后原子替换。
外层字段为 `schema_version: 1`、`run_id`、`iteration`、`rank`、`node_id`、`device_id`、
`source: "exact_device_task_association"`、`complete: true` 和 `operations` 数组。
每次可追加该 Rank 新完成的调用，保留已发布的调用不变；`complete` 只说明文件中每个调用的
设备 Task 已完成且归属明确，不要求整轮齐全。单文件上限 2 MiB，只需提供希望覆盖的通信。
每个调用写 `communicator_id`、`communicator_generation`、`op_counter`、`bucket_id`、
`occurrence`、`op_type`、`tensor_bytes`、`dtype`、`reduction`、`host_entry_ts` 及 `tasks`。
Task 必须提供唯一的 `execution_id`，`stream_id`、`task_id`、同一设备时钟域的整数
`start_ns`/`stop_ns`，以及 `algorithm`、`phase`、`step`、`slice`、`event`、
`semantic`、`task_kind`、`peer_rank`、`size_bytes`。仅写有明确语义位置的真实设备 Task。
缺失的 slice、peer 或大小写 `-1`，不填猜测值。

首报核对当前告警的调用身份和 Rank 提交记录，从前 10 个正式轮中找同 Rank、同通信布局的历史，
最多取 5 个有效样本（至少 3 个）。不使用注入真值，不将找不到历史解释为正常。
仓库目前没有把普通 `msprof` 采集自动转换成运行中批次的生产端；未提供批次时不会静默降级成
以 Host 提交计时，也不会从最终 DB 临时全量提取。5 秒是首报目标，不是对上游导出延迟的保证。

## 7. 看报告

**在线**：从 `online_output_dir/RUN_ID/events.jsonl` 看一行一条告警，例如
`tail -f reports/online/gpt2-001/events.jsonl`。先看 `event_type`、`iteration`、`bucket_id`，
再看 `suspected_ranks`、`metrics.R`、`metrics.P` 和 `reason`。

| 含义 | 在线事件 |
| --- | --- |
| H1：有 Rank 在时限内未进入，而且心跳/计数能证实 | `NOT_ENTERED_HANG` |
| S1：慢化并且有该 Rank 的独立 Host 准备延迟证据 | `COMPUTATION_SLOW` |
| S2：通信慢化，尚不能凭在线耗时判定物理原因 | `COMMUNICATION_SLOW` |
| 全部 Rank 已进入，但超时且没有完成证据，不能定位原因 | `STALLED_UNKNOWN` |
| 遥测或设备计时不完整，不能确认类别 | `INCOMPLETE_DATA` |
| 参考不完整或不稳定，不能计算慢化 | `INSUFFICIENT_BASELINE` |

`R=(Tmax-Tbase)/Tbase`，严格 `R>1` 才报慢，即耗时增量超过100%（总耗时超过历史基线两倍）；
刚好增长100%不报慢。`P=(Tmax-Tmin)/(Tmax-Tbase)`。
T 是各 Rank 的观测耗时，不是跨机绝对时间。用样例的 NPU Event 计时，须在现有同步点读回、
收齐全 Rank 数据并建立同位置基线后才能判断 S1/S2。`P>0.6` 本身不构成 S1：还需要唯一最短耗时的
Rank 同时有独立的 Host 准备延迟证据，已知的同钟进入顺序也不能与之矛盾。过慢化门槛但未证实 S1
时归为 S2；S2 标签不证明是 RoCE、SDMA 或其他某一种物理原因。
`measurements.jsonl` 包括正常、异常和证据不足的通信；`telemetry.jsonl` 保存原始帧；
`run_health.jsonl` 用于看是否丢帧、预热是否齐全以及计时覆盖。健康门禁不代表诊断准确率。

**离线**：`hccl-diag analyze` 默认把以下三个文件写到 `offline_output_dir/RUN_ID/`。
滚动分析的默认图只展示选出的轮次；使用独立 `--baseline` 时默认导出完整图。
需要整份采集的全部已解析任务和依赖，或只需要机器可读结果时，可分别运行：

```bash
hccl-diag analyze "runs/$RUN_ID" --report full -o "reports/offline/${RUN_ID}-full"
hccl-diag analyze "runs/$RUN_ID" --report json -o "reports/offline/${RUN_ID}-json"
```

`full` 保留三件套，但 `execution.html` 不裁轮次，长训练的文件可能很大。
`json` 只保存 `root_causes.json`（含传播链及节点），不渲染 HTML。两种选项都不改变诊断门槛，
完整图也不会补造未采到的任务或依赖。

| 文件 | 阅读方法 |
| --- | --- |
| `execution.html` | 在浏览器查看各节点、Rank、Stream 的任务和依赖；可从报告跳到标记任务。 |
| `root_causes.json` | 机器可读的传播报告；先看 `quality`、`coverage`，再看候选、传播链和 `online_followup`。 |
| `propagation.html` | 同一诊断的可读报告。S1 查准备区间和入口 Wait 的可信上游；S2 按 Rank 看慢化至少 +100% 的 Task/Wait 及后续传播。证据不足和未过线分别显示。 |

基于在线告警的详细分析只绑定可以唯一核验的通信实例；不凭桶顺序或时间接近补配。H1 的缺席判断留在
在线告警里，不把一条未完成通信当成已采齐的 Task 图。单一候选不能证明物理故障，计时或依赖缺失也
不代表没有异常。分析报错时优先核查实际库、设备映射、语义 plog 和每个 Rank 的调用日志。
