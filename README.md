# HCCL-Trace

从真实通信任务和 HCOMM 语义日志还原依赖，离线诊断慢执行与等待传播。
`main` 只保留当前诊断工具和一个无注入训练样例；旧实验、旧策略和结果口径留在 `nf`。

## 快速开始

在本分支工作树内安装。分析只需 Python 3.9+；设备采集另需匹配的 Linux/CANN、配套 Host/Device 库和训练框架。

```bash
python3 -m pip install -e .
# 1,3 仅示意；改成两张已分配设备的实际 runtime ID。
hccl-diag capture -o gpt2-capture -- \
  torchrun --standalone --nproc-per-node=2 --max-restarts=0 \
  examples/gpt2_normal.py --devices 1,3 --warmup 2 --iterations 8
hccl-diag analyze gpt2-capture -o gpt2-report
```

样例用 GPT-2 Small、随机初始权重与固定种子的合成 token，显式同步梯度桶，不下载模型、不注入异常。
需要已匹配的 `torch`、`torch_npu` 和 `transformers`。分析时不需要这些训练依赖。
使用自己的训练任务时，接入 `hccl_trace.Trace` 并替换 `--` 后面的启动命令。安装 Python 工具不会改驱动、包或设备安全策略。

## 诊断

- 单机和多机用同一条 `analyze` 命令。多机可用 `hccl-diag join` 汇集，`hccl-diag clock-probe` 采集软件校时证据。
- 默认按任务取最近至多五条未标慢的可比正式样本，沿已有 Wait 依赖回溯；不分簇、不选 Top1。
- 可用 `--baseline` 与独立正常采集比较。缺身份或校时不猜边、不伪造跨机时差。
- 结果只有 `execution.html`、`root_causes.json`、`propagation.html`；`--keep-debug` 可保留完整中间证据。候选不是已证实的物理故障。

详见[完整教程](文档/从零开始运行训练诊断.md)、[统一命令](文档/统一采集与诊断.md)
和[诊断实现](hccl/tools/diagnosis/README.md)。

## CPU 回归

```bash
python3 -m unittest discover -s hccl/tools/diagnosis -p 'test_*.py' -t .
```
