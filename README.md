# HCCL-Trace

基于真实通信任务、版本化语义日志和依赖关系的离线诊断工具。
在配套HCOMM/HCCL上采集自己的训练任务，再生成执行图、源头候选和传播证据。

**从克隆代码到诊断结果：[通用使用教程](文档/从零开始运行训练诊断.md)。**

先了解功能、真实报告长相和已验证结果，见[采集、打点与诊断功能说明](文档/采集打点与诊断功能说明.md)。

```bash
git clone --branch nf --single-branch https://github.com/Keiran810975/hccl-trace.git
cd hccl-trace
python3 -m pip install -e .
# 配套Host/Device已部署、训练已接入Trace SDK后，在每个训练节点运行：
hccl-diag capture -o capture -- torchrun ... train.py
# 单机直接分析；多机先汇集各节点的capture/nodes目录，再使用同一命令：
hccl-diag analyze capture
```

也可从Gitee克隆同一`nf`分支：`https://gitee.com/tjucyx/hccl-trace.git`。
安装Python工具不会编译或部署通信库，不会自动启动训练或修改设备安全策略。

## 输入与输出

- 采集需要受支持的Ascend/CANN环境，以及同源码、相互配套的Host库和实际执行路径所需的Device包。
- 生产输入为版本化语义plog和consolidated `msprof_*.db`；不使用`task_time.csv`或Chrome-trace JSON补配。
- Rolling还需要公开调用/正式轮次观测；推荐接入`hccl_trace.Trace`。多机时间对齐需要采集期前后探针。
- 最终目录只有`execution.html`、`root_causes.json`、`propagation.html`，HTML可离线打开。
- 分析在CPU上运行，原始输入只读；`--keep-debug`保留可审计中间结果。

## 入口

| 内容 | 文档/代码 |
| --- | --- |
| 新用户完整流程 | [通用教程](文档/从零开始运行训练诊断.md) |
| 对外讲解原理与使用 | [讲解稿与注意事项](文档/诊断工具讲解稿.md) |
| 功能、报告样例与实验结果 | [易懂说明](文档/采集打点与诊断功能说明.md) |
| SDK、目录和CLI接口 | [接口说明](文档/诊断工具使用说明.md) |
| 当前单机/多机及Host迟到诊断逻辑 | [诊断逻辑](文档/当前诊断逻辑.md) |
| 最小真实设备示例 | [diagnosis_collectives.py](examples/diagnosis_collectives.py) |
| 多机校时与计时边界 | [多机通信诊断](hccl/tools/diagnosis/multinode-communication.md) |
| 实现合同、开发计划 | [spec.md](hccl/tools/diagnosis/spec.md)、[task.md](hccl/tools/diagnosis/task.md) |
| HCOMM/HCCL构建参考 | [HCOMM](hcomm/docs/build.md)、[HCCL](hccl/docs/build.md) |

用户不需要选择单机、多机或策略版本。根据真实节点身份，单机自动使用局部簇＋Host迟到，
多机自动使用当前P95任务群辅助的单簇排序。新报告不包含关键路径模型或收益，保留真实依赖传播链。
报告成功不等于定位成功，候选不等于已确认物理故障。
已有实验仍存在正常误报和独立样例漏诊，不能承诺任意模型、算法或动态通信都无需适配。
`test/run_*`中的现场实验编排通常绑定特定设备和授权，不是通用部署程序。
旧选择实验入口已移至`test/archive/diagnosis_20261108/`，只用于历史复核，不再让用户逐个选版本。
简明操作与目录分工见[统一入口](文档/统一采集与诊断.md)。

## CPU回归

```bash
python3 -m unittest discover -s hccl/tools/diagnosis -p 'test_*.py' -t .
python3 -m unittest discover -s test -p 'test_*.py' -t .
```

源码与测试在Git中；原始采集、机器环境记录、构建产物及本地实验报告不随仓库发布。
旧设备实验文档中的具体IP、卡号、哈希和路径是历史记录，不能作为新设备配置直接照搬。
