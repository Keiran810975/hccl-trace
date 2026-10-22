# 双机异常测试集与 Workload

更新：2026-10-22。入口 `test/two_node_suite.py`，复用已有四机执行器与异常控制逻辑。
本阶段只验证测试脚本和大负载短预检能正常运行，不统计诊断准确率、不执行正式异常矩阵。

## Workload

| 配置项 | 双机主配置 |
|---|---|
| 节点 | 910C Node0 + Node2；在torchrun中分别是node-rank 0/1 |
| Rank | 每机2个，共4个：Node0为Rank0/1，Node2为Rank2/3 |
| 本次短预检设备 | 每机自有zjy-new的runtime1/3，对应NPU4/5的chip1、物理9/11；每次运行前重新确认空闲 |
| 计算 | Transformer-CommMix合成负载，BF16 GEMM和GELU，tokens2048、hidden8192、FFN32768 |
| 每轮 | 8个Block，每Block依次计算并执行128、256、512MiB的FP32 SUM AllReduce |
| 正式重复 | 10轮warmup + 50轮measured |
| 数值门禁 | 末轮各桶SUM结果检查；最后barrier和通信域销毁成功后才保存成功记录 |
| 默认采集 | 配套nf Host/Device语义打点和msprof consolidated DB |

本次短预检使用官方Device包、nf Host库和`--no-profile`，不调整验签。
Node0的其他芯片有外部任务，不能将空闲chip1等同于整张NPU卡空闲，更不能修改整卡验签策略。
模板中的runtime6/7只是示例，不能直接当作当前可用设备。

这不是完整Transformer训练：没有attention、反向传播、梯度或优化器，通信桶也不是真实梯度。
每轮24次AllReduce，每Rank输入 **7168MiB = 7GiB**；50轮正式测量累计350GiB/Rank。
包含预热共1440次业务collective，不乘Rank数量计算collective次数。
输入字节数不是网卡实际收发字节数，不能直接算成RoCE流量或带宽。

每Rank BF16权重约14GiB，三个通信桶合计896MiB，另有激活、缓存、运行时和后台负载。
这些是形状估算，不是峰值显存实测；不能据此跳过设备占用检查。
启动阶段另有2次小型配置摘要AllReduce，以及预热后/异常窗口开始/窗口结束/测量后的
控制barrier。它们需与业务通信分开识别，不按DB operation总数盲目绑定轮次。

## 测试集

一场完整双机运行是一个样例，4个Rank不是4个独立故障样例。
默认目标是 **Rank2 / measured iteration25 / block3 / bucket1**（均为0基编号），
即物理Node2的第一颗测试芯片、第26个测量轮次、第4个Block、256MiB桶。

| 类型 | 三档注入 | 时间与边界 |
|---|---|---|
| 通信调用前延迟 `progress_delay` | 1/20/200ms | 指定桶前sleep一次；默认arrival，不冒充内部task变慢 |
| 网卡带宽受限 `nic_limit` | 75%/50%/25%配置上限 | 现场验证过的RoCE限速hook；整段生效，结束恢复原配置 |
| 数据搬运竞争 `copy_contention` | 1/2/4个后台进程 | 目标芯片持续D2D Copy，每进程两个256MiB缓冲区 |
| 计算竞争 `compute_contention` | 1/2/4个后台进程 | 目标芯片持续BF16 4096x4096 GEMM |
| 通信竞争 `communication_contention` | 1/2/4组后台双端通信 | Rank2与Rank0所在芯片，独立组持续256MiB FP32 AllReduce |

后三类默认覆盖iteration25–29，正常组使用相同控制窗口与barrier。
后台通信使用独立TCPStore端口，并对后台进程设置`HCCL_HOST_SOCKET_PORT_RANGE=auto`、
`HCCL_NPU_SOCKET_PORT_RANGE=auto`。只改变启动端口不足以避免HCCL内部默认16666监听端口冲突；
自动端口只作用于这些子进程，不修改系统网络或前台任务环境。
Copy可能同时竞争SDMA/HBM，不称纯SDMA竞争；背景通信同时占用本地资源，未经网络计数器
确认不称纯网络拥塞。并发数不保证线性对应变慢幅度。

保留已有`library_task`选择器接口，但AI_CPU内部延迟必须有真正支持且已验证的设备端注入。
当前nf运行库不能只靠Host环境变量就宣称支持；默认使用可执行的arrival延迟。

每个规模/位置/seed：1个正常对照 + 5类x3档 = **16个计划样例**。
main规模、位置10/25/40、3个seed是144例；再扩small/main/large是432例。
它们是计划数量，本次不会完整执行或计入已采集数据集。

| 档位 | 每Block三个桶 | 每Rank每轮输入 |
|---|---|---:|
| small | 32/64/128MiB | 1.75GiB |
| main | 128/256/512MiB | 7GiB |
| large | 256/512/1024MiB | 14GiB |

三档只改变通信桶，计算规模和Block数不变。

## 生成与运行

从工作空间根目录执行，只生成计划不占设备，已有目录拒绝覆盖：

```bash
python3 test/two_node_suite.py generate --output test/out/two-node-core
python3 test/two_node_suite.py generate --smoke --output test/out/two-node-smoke
python3 test/two_node_suite.py generate --sizes small,main,large \
  --positions 10,25,40 --seeds 20261022,20261023,20261024 \
  --output test/out/two-node-expanded
```

短预检保持8个Block、完整计算形状和main通信桶，仅缩成1轮预热+2轮测量，72次业务AllReduce。
ID前缀`smoke-2n4r-`、purpose为`preflight`，与正式样例分开，不计入测试集。

集群模板：`test/configs/two_node_cluster.example.json`，默认`preflight_confirmed=false`。
必须填写实际地址、已核实的runtime设备、配套Host/Device路径及runtime_files哈希输入。
`node_rank=1`明确对应物理Node2，不能误用物理Node1。
前台与后台均直接使用实际runtime设备ID，不设置ASCEND_RT_VISIBLE_DEVICES二次重编号。

两机先同步相同源码、case和完整cluster配置，准备CANN/PyTorch环境，然后分别执行：

```bash
python3 test/two_node_suite.py run-node \
  --case test/out/two-node-smoke/cases/smoke-2n4r-main-i0-s20261022-normal.json \
  --cluster /absolute/two-node-cluster.json --node-rank 0 \
  --output /absolute/two-node-runs --attempt smoke-001
```

另一机只把`--node-rank`改为1，case/cluster/attempt一致；默认只是打印计划，加`--execute`
才会运行。Copy/计算/通信背景进程还需`--allow-background`。
网卡限速另需`--allow-network-change`和真实query/apply/verify/restore接口，格式复用
[四机说明](四机异常测试集与Workload说明.md#51-网卡限速接口)，目标node_rank在双机配置中是1。
没有接口就拒绝执行，不用普通Linux限速命令假装已限制RoCE。

`--no-profile`只用于启动与资源预检，不采集正式DB；默认不加它才是语义+msprof采集。
脚本不自动SSH、不设置验签、不安装库、不修改网卡；Device开发包的授权加载与恢复
仍由现场独立保护流程负责，不能在公共runner里隐式修改服务器安全策略。

运行输出为`<output>/<case-id>/<attempt>/node0..node1/`，保留environment.json、execution.json、
原始日志、可选DB、private配置/事件/每Rank正确性结果。新attempt才能重跑，不覆盖失败记录。
后台worker必须真的执行并正常停止才能通过功能检查，但执行成功不证明竞争效果或诊断正确。

```bash
python3 test/two_node_suite.py summarize --suite test/out/two-node-smoke/suite.json \
  --runs /absolute/two-node-runs --output test/out/two-node-smoke-ledger.csv
```

台账只有执行状态与注入控制证据，不输出诊断准确率。

## 本次真实双机短预检

2026-10-22，在Node0和Node2的自有`zjy-new`中验证，采用上述完整main形状、
1轮预热+2轮测量。每个样例72次业务AllReduce，未运行50轮正式配置。

| 样例 | 实际预检 | 状态 |
|---|---|---|
| 正常对照 | 无异常 | 4 Rank完成，数值检查通过 |
| 通信调用前延迟 | Rank2指定桶前20ms，一次 | 延迟事件留存，4 Rank完成 |
| D2D Copy竞争 | Rank2芯片1个后台进程 | 后台974次Copy后正常停止，4 Rank完成 |
| 计算竞争 | Rank2芯片1个后台进程 | 后台358次GEMM后正常停止，4 Rank完成 |
| 通信竞争 | Rank2与Rank0芯片1组后台通信 | 两端各30次AllReduce后正常停止，4 Rank完成 |
| 网卡带宽受限 | 未设置真实限速hook | 未执行；仅离线验证权限门禁和恢复逻辑 |

通信竞争首次因HCCL内部默认16666监听端口冲突失败；补充上述后台动态端口配置后，
新attempt重跑通过。失败记录未覆盖，台账同时保留失败与成功attempt。
后台操作次数只证明负载执行过，不代表竞争强度或网络拥塞量级。

本次全程使用nf Host库、官方Device包、`--no-profile`，没有修改验签、网卡或他人容器。
成功样例共20份Rank结果，`max_error=0`；两机容器最终均仅有`sleep infinity`，
官方Device包SHA256复核一致且未改变：
`d51cca4ff0d8b5e5e138be7541eac6f9c7b83079834ae4f9a74150c9b6aa9625`。

本地证据在`test/out/two-node-suite-20261022/`：
`cluster-smoke.json`为实际配置，`plan-core/`与`plan-smoke/`为计划，
`evidence/runs/`保留两机执行与私有控制记录，`smoke-ledger.csv`为台账，
`smoke-summary.json`为功能核对结果，`source-final.tar.gz`保留本次测试代码。
服务器两机容器路径均为`/workspace/nf-20261022/two-node-suite/`。

共享执行器及双机测试38项通过，连同诊断和结果门禁回归共194项通过。
这些结果仅验收大workload启动、通信、软件注入和退出清理；
未采集本轮msprof DB，也未验收大workload上的语义覆盖、依赖诊断或异常定位准确率。
