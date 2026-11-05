# HCCL-Trace

基于真实通信任务、版本化语义日志和依赖关系的离线诊断工具。
在配套HCOMM/HCCL上采集自己的训练任务，再生成执行图、源头候选和传播证据。

**从克隆代码到诊断结果：[通用使用教程](文档/从零开始运行训练诊断.md)。**

```bash
git clone --branch nf --single-branch https://github.com/Keiran810975/hccl-trace.git
cd hccl-trace
python3 -m pip install -e .
# 以下命令要求已经完成配套库部署、训练接入和采集，并不是采集命令。
hccl-diag analyze --capture /path/to/capture --mode rolling \
  --output /path/to/new-results --keep-debug
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
| SDK、目录和CLI接口 | [接口说明](文档/诊断工具使用说明.md) |
| 最小真实设备示例 | [diagnosis_collectives.py](examples/diagnosis_collectives.py) |
| 多机校时与计时边界 | [多机通信诊断](hccl/tools/diagnosis/multinode-communication.md) |
| 实现合同、开发计划 | [spec.md](hccl/tools/diagnosis/spec.md)、[task.md](hccl/tools/diagnosis/task.md) |
| HCOMM/HCCL构建参考 | [HCOMM](hcomm/docs/build.md)、[HCCL](hccl/docs/build.md) |

诊断命令默认`--source-policy legacy`；`dual`和`dual-v2`是显式选择的实验策略，
后者用于当前多机局部源头排序。报告成功不等于定位成功，候选不等于已确认物理故障。
已有实验仍存在正常误报和独立样例漏诊，不能承诺任意模型、算法或动态通信都无需适配。
`test/run_*`中的现场实验编排通常绑定特定设备和授权，不是通用部署程序。

## CPU回归

```bash
python3 -m unittest discover -s hccl/tools/diagnosis -p 'test_*.py' -t .
python3 -m unittest discover -s test -p 'test_*.py' -t .
```

源码与测试在Git中；原始采集、机器环境记录、构建产物及本地实验报告不随仓库发布。
旧设备实验文档中的具体IP、卡号、哈希和路径是历史记录，不能作为新设备配置直接照搬。
