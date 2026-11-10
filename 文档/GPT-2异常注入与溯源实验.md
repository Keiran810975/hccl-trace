# GPT-2 异常注入与溯源实验

本文是 `nf` 的历史实验说明。下文注入、运行器和评测脚本不随 `main` 发布；
`main` 的可运行样例见 [gpt2_normal.py](../examples/gpt2_normal.py)。

## 入口与前提

从仓库根目录运行。采集需要已合法加载匹配的 Host/Device 通信包、已验证可用的 Linux/CANN
训练环境（包括 msprof、PyTorch、torch_npu 和 transformers），以及独占分配给这次实验的 NPU。
诊断和判定可在 CPU 上离线运行。安装命令是 `python3 -m pip install -e .`。
新入口不 SSH、不抢占任务、不换设备策略、不覆盖目录，也不重启既有实验。

| 阶段 | 脚本 |
| --- | --- |
| 生成冻结设置和分节点采集 | [run_backtrace_experiment.py](../test/run_backtrace_experiment.py) |
| GPT-2训练和注入触发 | [gpt2_train.py](../test/gpt2_train.py) |
| 单机/多机注入控制 | [gpt_three_anomaly_control.py](../test/gpt_three_anomaly_control.py) / [node03_gpt2_control.py](../test/node03_gpt2_control.py) |
| 单桶RoCE窗口及受保护运行 | [roce_single_collective.py](../test/roce_single_collective.py) / [run_roce_single_collective.py](../test/run_roce_single_collective.py) |
| 诊断 | `hccl-diag analyze`，入口 [cli.py](../hccl/tools/diagnosis/cli.py)，回溯 [wait_backtrace.py](../hccl/tools/diagnosis/wait_backtrace.py) |
| 严格的实验级判定 | [evaluate_backtrace_experiment.py](../test/evaluate_backtrace_experiment.py) |

## 冻结设置

GPT-2 Small 全模型 DDP：12 层、12 头、隐藏维度 768，每 Rank 4 条长度 1024 的序列，
BF16 autocast、FP32 参数与梯度 AllReduce、AdamW。10 预热 + 50 正式轮。
单机 Node0 四 Rank；双机 Node0 Rank 0–3，Node3 Rank 4–7，同一个八 Rank 训练通信组。
正式轮从 0 编号；异常试验使用编号 25，桶选择种子 20261102。实际桶从预热稳定桶中
确定，诊断不得读取注入位置。单机 workload seed 20261028，双机 20261103。
每个设置是一组独立实验，不混入历史批次的统计。

| `--kind` | 单机 | 双机 | 方法 |
| --- | --- | --- | --- |
| `normal` | 支持 | 支持 | 不注入，用于查看无干扰诊断输出 |
| `copy_contention` | Rank 0 | Rank 4 | 2 GiB ACL D2D，异步提交后触发，本轮设备同步后暂停；5 秒活动上限 |
| `communication_contention` | Rank 0、1 | Rank 0、4 | 独立通信组 1 GiB FP32 SUM AllReduce；同机单进程双设备，跨机各一进程；提交后触发，本轮同步后暂停 |
| `progress_delay` | Rank 0 | Rank 4 | 目标桶 API 调用前 Host 暂停 500 ms |
| `compute_contention` | Rank 0 | Rank 4 | 可选历史对照：8192 阶 grouped GEMM，提交后触发，本轮同步后暂停 |
| `bandwidth_limit` | 不提供 | Node0 Rank 0、物理端口 9 | 只放行一个目标桶；20 Gbps，结束后恢复原值，不使用五轮限速 |

## 非 RoCE：生成设置、采集

数据准备和设置生成不启动 NPU 训练。数据准备会下载文本和分词器；离线环境可用
`--data-assets` 指向含 `alice.txt` 及 GPT-2 分词器文件的本地目录。

```bash
python3 -m test.gpt2_train --prepare-data gpt-data
python3 -m test.run_backtrace_experiment plan --topology single \
  --kind copy_contention --run-id sdma-01 -o sdma-01.json
python3 -m test.run_backtrace_experiment run --case sdma-01.json \
  --data gpt-data --devices 1,3,5,7 --allocated-devices -o trial
```

`--devices` 是本机**容器内的运行时 ID**，按实际分配填写，不是物理卡号。更换异常用不同的
`--run-id` 和新输出目录。单机通信竞争还要编译独立工作进程并传入
`--communication-worker`；沿用当前容器 CANN 和配套通信库位置：

```bash
g++ -std=c++14 -O2 test/anomaly_injection/single_process_comm_load.cc \
  -I"$CANN_HOME/include" -L"$HCOMM_LIB" -L"$CANN_HOME/lib64" \
  -lascendcl -lhccl -pthread -o single-process-comm-load
```

双机先用 `plan --topology multi` 生成同一份设置，复制到两机。两边用相同数据、设置、
Node0 可达地址和端口；现有 HCCL 网卡选路配置保持不变。Node0 用 `--node-rank 0`，
Node3 用 `--node-rank 1`，各自在本机执行；训练前的 CPU 探针校验设置和 token 数据一致：

```bash
python3 -m test.run_backtrace_experiment run --case multi-01.json \
  --data gpt-data --devices 1,3,5,7 --allocated-devices \
  --node-rank "$NODE_RANK" --master-addr "$NODE0_ADDR" -o "trial-$NODE_RANK"
```

默认 TCP 端口 29773（torchrun）、29774（CPU 协调）、29776（校时）、29775（双机后台通信），
另保留已有 HCCL 通信端口配置。按现场准备足够磁盘空间。输出 `capture/` 是诊断输入；
`workload/` 内有训练数值、实际注入日志和时间，**只给判定脚本**。

## RoCE：只限一个梯度桶

```bash
python3 -m test.run_backtrace_experiment plan --topology multi \
  --kind bandwidth_limit -o roce-case.json
```

在原受保护的 Node0/Node3 环境，部署到新且未使用的专用根
`hccl-diagnose-node03-20261108-1101`，将生成设置放在 `input/case.json`。
该入口绑定现场设备，不是通用管理员命令。两机需要相同的 `src/` 源快照及
`source-snapshot.json`（文件相对路径到 SHA256），配套的 `deploy/`、`input/aicpu_hcomm.tar.gz`、
`build-receipt.json`，及现场确认的 `authorization.json`、`deployment.json`。
需要预先留存无后台干扰且数值通过的前台端口证据 `input/network-baseline.json`。
配置要求见[单桶RoCE保护流程](../hccl/tools/diagnosis/roce-single-collective-20261108.md)及
[设备保护器](../test/node03_device_guard.py)；不能用自己编造的授权或构建凭证代替。

仅在该专用根完成部署和现场授权后，从 Node0 执行：

```bash
python3 "$ROCE_ROOT/src/test/run_roce_single_collective.py" --root "$ROCE_ROOT"
```

所有 Rank 排空前序通信、对齐同一桶；读回限速后只放行该桶；设备完成后读回恢复，再放行后续桶。
不把异步提交返回当完成。窗口物理上早于提交、晚于完成，不能用于测自然训练开销；
CPU 等待单独记录，不能当作 Host 迟到异常。单桶流程当前只有 CPU 专项验证，未完成真实双机慢化验收。

## 诊断：不分簇

单机直接用 `trial/capture`。双机汇集两个完整采集目录后，用相同分析入口：

```bash
hccl-diag join trial-0/capture trial-1/capture -o combined
hccl-diag analyze combined -o result --keep-debug --require-clock-alignment
# 单机:
hccl-diag analyze trial/capture -o result --keep-debug
```

设备任务以同位置、同结构最近至多 5 条未标慢的正式样本为参考，不足 5 条按实际数量取均值；
Host 准备仍用连续前 5 轮。源头 1.5 倍、Wait 1.2 倍，均结合 3 MAD。从慢 Wait 沿
已验证的 Notify 配对和实测流顺序回溯。被上游解释的 Wait、只晚开始的中间任务留在
传播路径中，不作为根因；自身执行确实变长且有回溯支撑的任务可以保留。缺边、缺校时或
无法解释的慢任务列为未归因。不分候选簇、不排序选 Top1，不读实际注入时间。
根因 JSON、执行图、传播图仍分别输出。受保护的 RoCE 入口会自动生成同口径的诊断并封存三份报告。

## 判定：全部候选都必须有实际时间重叠

```bash
python3 -m test.evaluate_backtrace_experiment --report result/root_causes.json \
  --run-dir trial -o verdict.json
```

双机改用 `--run-dir trial-0 --run-dir trial-1`，并传
`--alignment result.debug/analysis/<run-id>/clock_alignment.json` 以核验跨机重叠。
RoCE 改用 `--truth "$ROCE_ROOT/evaluation.json"` 和 `--report "$ROCE_ROOT/report/root_causes.json"`，
需要跨机时用同次报告的 `report.debug` 中的校时文件。旧报告也可传已有独立评测文件：
只读其中的实际窗口，忽略其中旧版的命中字段。旧文件若仅保存整体包络，不自动推断单次活动区间。

按用户要求只判时间，不要求 Rank 一致；跨机仅在校时误差不足以改变相交结论时命中。
设备根因候选和已发布的 Host 异常线索都算候选，传播节点不算。每个候选至少与一个实际窗口
有正重叠才返回 `true`；只碰端点、任一不重叠、无法对时、零候选或没有实际窗口均为
`false`。本入口采集的 ACL Copy 按实际完成的逐次 API/同步包络判定，不把 Copy 间隙算成活动。
退出码 0 为真、1 为假、2 为输入/证据无效（也输出 `result:false`）。
时间重叠是本实验的判定指标，不等同于命中物理故障，也不证明注入有效或没有误报。
