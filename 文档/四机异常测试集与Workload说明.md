# 四机异常测试集与 Workload 说明

更新：2026-10-22。本文对应 `test/four_node_suite.py`。当前交付是测试代码、配置模板和
离线验证，不是已经采集完成的数据集，也不是四机诊断通过的结论。未自动切换分支、编译
HCOMM、部署运行库、连接服务器或修改网卡。

## 1. 测什么

用同一套较大的计算通信负载，分别制造进度延迟、网卡限速、数据搬运竞争、计算竞争和
背景通信竞争，检查诊断工具能否找到慢任务、等待对象及下游传播关系。

一个样例是一场完整的四机运行。16 个 Rank 的记录共同属于该样例，不能把 16 个 Rank
或一条故障引出的多个 Wait 统计成多个独立异常。

## 2. 主负载配置

| 项目 | 主配置 |
|---|---|
| 机器 | 4 台 910C 环境机器 |
| Rank | 每台 4 个，共 16 个；Node 0/1/2/3 分别为 Rank 0-3/4-7/8-11/12-15 |
| 设备 | 每个前台 Rank 使用不同物理 NPU 的一个芯片；实际映射必须先核实 |
| 类型 | Transformer-CommMix：仿训练节奏的合成计算通信，不是完整模型训练 |
| 计算 | BF16 矩阵乘和 GELU；Tokens=2048，Hidden=8192，FFN=32768 |
| 每个 iteration | 8 个 Block，每个 Block 有 3 次 FP32 SUM AllReduce |
| 三个桶 | 128、256、512 MiB |
| 重复 | 10 轮预热 + 50 轮正式测量 |
| 正确性 | 每次通信前填入可计算的 Rank/iteration/Block/桶编号，检查末轮 SUM 结果 |
| 采集 | semantic plog + consolidated `msprof_*.db`；不走 profiler JSON 合并链 |

一个 Block 的顺序如下，重复 8 次完成一轮：

```text
QKV 风格矩阵计算 + GELU -> AllReduce 128 MiB
输出投影风格计算 + GELU -> AllReduce 256 MiB
两次 FFN 矩阵计算 + GELU -> AllReduce 512 MiB
```

没有完整 attention、反向传播、梯度计算或优化器更新。通信桶是合成数据，不是实际梯度。
AllReduce 采用同步调用，正式循环每轮还会等待本地 NPU 完成，便于取得独立的轮次时长。

业务通信规模：

- 每轮 8 x 3 = **24 次 AllReduce**。
- 每 Rank 每轮输入 8 x (128+256+512) = **7168 MiB = 7 GiB**。
- 每 Rank 正式测量累计输入 **350 GiB**。
- 包含预热共 **1440 次业务 AllReduce**，不是 1440 x 16 个独立 collective。
- 这是输入量，不是网络发送字节数，不能据此直接报告 RoCE 吞吐。

按当前权重形状计算，每 Rank 的 BF16 权重约 14 GiB，三个通信桶合计 0.875 GiB；激活、
临时张量、算子 workspace、运行时和后台负载另计。应先测峰值显存，不把此估算当作实测。

为防四台误跑不同样例，启动阶段额外使用 **2 次小型 AllReduce** 核对配置摘要。预热后、
异常窗口开始、窗口结束、测量结束各有一个控制 barrier，正常组和异常组相同。这些控制
通信不是业务的 1440 次 AllReduce，回放时要分开识别，不能按 DB operation 总数硬对齐。
配置摘要只是防误配校验，不证明运行库、限速或异常确实生效。

## 3. 五类异常和默认位置

所有编号从 0 开始：默认目标为 `Rank 8 / iteration 25 / block 3 / bucket 1`，即
**Node 2、第 26 个测量轮次、第 4 个 Block、256 MiB 桶**。iteration 是 workload 外层轮次，
不是通信算法内部的 step。

| 样例类型 | 三档注入 | 时间范围 | 实现及边界 |
|---|---|---|---|
| `progress_delay` | 1、20、200 ms | 指定桶，一次 | 默认 `arrival`：AllReduce 调用前暂停；可另选配套库的 `library_task` 模式，见下文 |
| `nic_limit` | 75%、50%、25% 配置上限 | 启动前设置，覆盖预热和测量，退出恢复 | 仅调用现场提供的 RoCE 限速接口，不提供可能绕过 RDMA 的通用 Linux 限速替代品 |
| `copy_contention` | 1、2、4 个进程 | iteration 25-29 | 目标芯片持续 D2D Copy，每进程使用两个 256 MiB FP32 缓冲区 |
| `compute_contention` | 1、2、4 个进程 | iteration 25-29 | 目标芯片持续 BF16 4096 x 4096 矩阵乘，输出复用，避免无界排队 |
| `communication_contention` | 1、2、4 组双端通信 | iteration 25-29 | Rank 8 和 Rank 0 所在芯片上建立独立通信组，持续执行 256 MiB FP32 AllReduce |

后台进程在预热前完成初始化及一次试运行，然后等待 start 文件。到达目标轮次时启动，
完成第一批设备操作后写 active；前台等待全部节点的同窗口 barrier 后才开始计时。
窗口结束时请求 stop 并等待退出，再执行同配置 barrier。后台通信两端通过独立 CPU
TCPStore 协商停止，避免一端退出、另一端继续 collective。每组使用独立端口和通信域。
该 Host 协调接口使用 PyTorch 的 [TCPStore/PrefixStore](https://docs.pytorch.org/docs/stable/distributed.html)，
设备上的具体 PyTorch/torch_npu 版本仍需短样例验证。

注意：

1. 控制轮次精确，实际资源重叠仍需 profiler 证据。进程数不保证线性对应异常严重程度。
2. D2D Copy 可能同时竞争 SDMA、HBM 等资源；在确认执行引擎前不宣称是纯 SDMA 竞争。
3. 后台通信目前复用前台目标芯片，以便共享该端的数据路径；同时也会竞争本地资源。
   未确认实际网口/交换机瓶颈和网络计数器前，只称“通信竞争”，不能宣称是纯网络拥塞。
4. 网卡限速的百分比是配置请求，不保证实测有效带宽恰好下降到该百分比。正常配置本身、
   队列和链路利用率均会影响结果。

### 3.1 内部 task 延迟与 arrival 延迟不是一回事

默认的 `arrival` 可直接使用，不需要改通信库，但只模拟某 Rank 晚调用 collective。
它不能证明通信库内部某个 phase/step/event 的 task 本身变慢，更不是复现了真实软件 bug。

需要内部注入时，生成样例加 `--internal-selector selector.json`，例如结构为：

```json
{
  "phase": "填写实际已验证的 phase",
  "step": 0,
  "event": "填写实际已验证的 event",
  "skip_matches": 0,
  "evidence": "本消息规模和目标轮次的选点/命中验证记录路径"
}
```

此时运行器传递现有 `HCCL_DIAG_INJECT_*` 环境变量，限定一次命中；不会自动应用补丁。
必须加载真正支持该协议的测试库，并在集群配置填写 `internal_delay_runtime_evidence`。
`skip_matches` 必须依据实际路径验证，不能把 operation 序号直接当匹配次数，也不能把同一
选择器盲目用于不同 size/注入轮次。生成器因此限制内部选择器一次只对应一种 size/position。
正常组必须加载同一版本注入库，但运行器会清除残留的注入环境变量。

历史 `hcomm_rank_step_delay.patch` 是 Host scope 的测试补丁。**不能假设 Host 的 getenv
开关在 AI-CPU 内核也能生效**；AI-CPU 需要设备端已验证的配套实现。仅设置环境变量或
填写 evidence 字符串不算注入成功。台账检查符合 `[HcclDiagInject] type[task_launch_delay]`
协议且 Rank/phase/step/event/延迟均匹配的命中日志，并区分缺失、单次命中和多次命中。
即使单次命中，也标记 `native_hit_observed_task_identity_and_effect_unverified`，仍需核对
对应物理 task 和 DB 时间后才能验收。其他 AI-CPU 注入日志格式需先适配，不能当成已支持。

## 4. 测试集怎么构建

保持 workload、seed、采集方式和运行库一致，每次只改变一种异常。每种规模、注入位置、
seed 对应一个正常对照，五类异常各三档，共 1+5x3=**16 个样例**。

| 层次 | 构建方式 | 正常 | 异常 | 合计 |
|---|---|---:|---:|---:|
| 首批核心集 | main、位置 25、1 个 seed | 1 | 15 | 16 |
| 时间和重复扩展 | main、位置 10/25/40、3 个 seed | 9 | 135 | 144 |
| 数据量扩展 | small/main/large、三个位置、三个 seed | 27 | 405 | 432 |

这些是计划数，不是现有采集数量。多个 seed 是独立运行的重复条件，不等同于硬件噪声已经
被随机化；后续正式统计应平衡运行顺序，并报告中位数/分位数及失败比例。

| 数据档 | 每 Block 的三个桶 | 每 Rank 每轮输入 |
|---|---|---:|
| small | 32、64、128 MiB | 1.75 GiB |
| main | 128、256、512 MiB | 7 GiB |
| large | 256、512、1024 MiB | 14 GiB |

三档只改变通信大小，Block 数、计算规模和预热/测量轮数不变，避免同时改变多个因素。
限速是整段施加，扩展表中其“位置”只改变配平的控制窗口，不代表限速在该轮才生效。
如需评估限速发生时刻，应另写经过验证的动态限速控制，不能把这里的重复条件解释成动态注入。

先生成独立的短预检计划：仍保持主配置的计算规模和通信桶，但只预热 1 轮、测量 2 轮，
异常窗口在 iteration 0，持续 1 轮。ID 带 `smoke-` 前缀，`purpose=preflight`，不计入正式集。

```bash
python3 test/four_node_suite.py generate --smoke \
  --output test/out/four-node-smoke-20261022
```

从工作空间根目录生成首批正式计划，不占用设备：

```bash
python3 test/four_node_suite.py generate \
  --output test/out/four-node-core-20261022
```

生成时间/重复扩展集或完整数据量扩展集：

```bash
python3 test/four_node_suite.py generate \
  --output test/out/four-node-time-repeat \
  --positions 10,25,40 --seeds 20261022,20261023,20261024

python3 test/four_node_suite.py generate \
  --output test/out/four-node-expanded \
  --sizes small,main,large --positions 10,25,40 \
  --seeds 20261022,20261023,20261024
```

已有目录不覆盖。`suite.json` 保存配对关系，`cases/*.json` 保存各样例配置。
重跑需要新 `--attempt`，不得覆盖前一次失败记录。同一 core 配置的内部延迟版本与 arrival
版本应放在不同 suite/运行根目录，避免把两种故障混为同一 ID。

## 5. 集群配置与执行

配置模板：[four_node_cluster.example.json](../test/configs/four_node_cluster.example.json)。
模板不能直接执行；`preflight_confirmed=false`，只允许查看计划。四台需要同一份完整配置，
其中每个 node 对象可以填写不同的运行库路径。配置检查不预先保证环境真的可用。

开跑前必须核实：

- 四台间实际的 Host/RoCE IP、路由与端口互通；不能拿公网跳板地址直接冒充 RoCE 地址。
- `devices` 是传给运行时的实际设备 ID。示例 `[0,2,4,6]` 只是待核实候选，不由 Rank 推断。
- 四台加载同一测试版本 HCCL/HCOMM 及 AI-CPU 产物，`runtime_lib_dir` 指向正确目录。
- `runtime_files` 明确列出实际加载的库/内核文件，运行器保存 SHA256。未填写会拒绝运行。
- 预留前台资源、目标芯片上后台负载的空间和 profiler 输出磁盘；目录不能含空白字符。
- 最近一次检查 Node 0/1 为驱动 25.5.1，Node 2/3 为 26.0.rc1；需先确认 CANN/HCCL 兼容，
  不自动升级或降级共享机器驱动。资源空闲快照也不是资源预约。
- `background_addr` 填目标 Node 2 可达的 Host 地址，用于背景组初始化；它不强制选择 RoCE 路径。
- 背景通信需要 `shared_path_evidence` 说明已核实的共享数据通路，仍需运行后网络指标验证。

完成检查后才设置 `preflight_confirmed=true`。先查看某节点的启动计划：

```bash
python3 test/four_node_suite.py run-node \
  --case test/out/four-node-core-20261022/cases/main-i25-s20261022-normal.json \
  --cluster test/configs/four_node_cluster.example.json \
  --node-rank 0 --output test/out/four-node-runs
```

运行时，在四台的 CANN/PyTorch/torch_npu 环境中分别执行同一条命令，`--node-rank` 取
0/1/2/3，使用相同 case、完整 cluster 配置和 attempt。增加 `--execute` 才会实际启动。
脚本不 SSH、不分发密钥、不远程清理进程，也不自动把 `nf` 当作支持 AI-CPU 的部署分支。
四节点的代码和配置必须先同步；不要同时执行多个样例，共用端口会冲突。

- Copy、计算、通信竞争额外要求 `--allow-background`。
- 网卡限速额外要求 `--allow-network-change`，并提供下节的现场接口。
- 默认 `msprof --hccl=on --task-time=on --type=db`；`--no-profile` 仅用于功能/资源预检，
  不能算完整诊断样例。torchrun 重试关闭，默认整次超时 1800 秒。
- 先用 `generate --smoke` 的独立预检样例估算输出体积和显存，再跑 50 轮。不能把预检计入正式矩阵，
  也不能把短窗口诊断宣称为完整 workload 的关键路径。

### 5.1 网卡限速接口

不硬编码未经现场验证的 `hccn_tool` 参数。配置 `nic_limit` 为：

```json
{
  "node_rank": 2,
  "port_evidence": "目标 Rank 所用物理 RoCE 端口和映射验证记录",
  "query": ["/absolute/site-roce-limit", "query-json"],
  "apply": ["/absolute/site-roce-limit", "apply-percent", "{percent}"],
  "verify": ["/absolute/site-roce-limit", "verify-json"],
  "restore": ["/absolute/site-roce-limit", "restore-json", "{snapshot}"]
}
```

这是接口格式，不是已经存在的设备命令。所有 hook 使用 argv 数组，不经 shell。
`query` 的标准输出必须为可恢复原状态的 JSON；`verify` 输出包含
`{"configured_percent": 50}` 这样的 JSON。`restore` 必须使用原配置快照，而不是简单设回
“100%”。执行失败、超时、Ctrl-C/SIGTERM 时都会尝试恢复；恢复失败单独标记
`restore_failed`，需要人工检查。SIGKILL、断电或主机失联无法保证自动恢复。
配置成功只表明 cap 已设置，实际带宽下降还需测量，不能依赖 hook 退出码证明。

## 6. 输出、诊断输入与结果判定

```text
four-node-runs/<case-id>/<attempt>/node0..node3/
  environment.json          # npu-smi、源码状态/哈希、运行库哈希
  execution.json            # 执行、超时、采集缺失、恢复失败等状态
  ascend_log/               # HCOMM 原始日志；诊断只读取正式 semantic/correlation 事实
  msprof/                   # consolidated DB
  private/
    case.json, cluster.json # 配置与注入真值
    command.json, capture.log
    nic-*.json              # 原网卡配置及操作记录（仅限速目标节点）
    events/rank*/           # Host 控制事件、逐轮时长、后台进程及结果
```

Host `collective_submit` 是“准备调用通信”，不是设备 task 的实际启动时间，也不能凭
Host 轮次日志猜测 DB 物理 task 身份。窗口/轮次记录用于测试控制；诊断关系仍来自项目原有
的 DB 精确关联和依赖 artifact。无校准时，不跨节点相减时间或累加全局关键路径。

`avg_step_ms` 不含窗口启停和 barrier；`measured_region_ns_including_window_control`
包含测量段内的窗口控制及退出等待，但不含测量前初始化和末尾 barrier。两种时间分开报告，
不把控制开销混称成通信 task 耗时。

只有四个节点均完成、每节点四个 Rank 数值正确且采集存在 DB，才标为执行完成；这不等于
注入有影响，更不等于诊断正确。后台 worker 的 `operations>0` 只证明执行过。
完整验收还需要检查目标 semantic、exact 匹配质量、图门禁、实际重叠/降速、等待链及数值。

四节点输出汇集到同一根目录后生成运行台账：

```bash
python3 test/four_node_suite.py summarize \
  --suite test/out/four-node-core-20261022/suite.json \
  --runs test/out/four-node-runs \
  --output test/out/four-node-ledger.csv
```

台账保留未运行、部分节点、失败、超时和所有重试，不挑选成功样例。它不是准确率计算器，
也不自动将“Copy 跑起来”解释成“SDMA 确实产生竞争”。限速样例保留配置成功但效果未验证，
内部延迟样例保留待核对命中与物理身份的状态。

**盲测时只给诊断程序正式 DB 和所需 semantic/correlation 记录，不给 private、原始命中
日志、带故障答案的 case ID 或注入参数。** 先独立产出根因候选和依赖链，再由评测器读取真值
核对位置。现有需要传入已知 Rank/phase/step/event 的对比脚本不能直接充当盲测准确率评测器。

## 7. 本地验证和实现范围

```bash
python3 -B -m unittest test.test_four_node_suite
```

本地标准库测试覆盖样例配对/数量、输入量、边界校验、执行授权、启动参数、网卡恢复、
超时清理、控制窗口和双端停止协议。不需要在开发机安装 PyTorch/torch_npu。
真实负载和 worker 仍依赖设备上的 PyTorch/torch_npu/CANN。

实现不改变 HCOMM 生产端、诊断 schema 或现有构边规则。四机是否走已插桩算法、AI-CPU
是否能采到完整语义、网络接口是否可用，必须由设备预检和真实回放回答，不能由离线单测代替。
