# nf 授权开发模式双机完整诊断验收

日期：2026-10-22。结论：**Node0 + Node2 的正常小负载已完成语义打点、精确合并、跨机依赖、等待分析和原生 HTML 输出**。
这不是四机验收，也不替代训练型大负载、异常注入和根因准确率评估。

## 授权与环境恢复

用户本轮明确授权临时调整设备验签。使用普通宿主 root SSH 入口，未使用特权容器、
命名空间绕过或修改驱动。只选 Node0/2 当前均空闲的 NPU7 整卡，每卡物理芯片14/15，
在自有非特权 `zjy-new` 中的 runtime ID 为6/7。命令按整卡设置，两个芯片分别核对。

- 原值：每节点两个芯片均 `enable=False, mode=5`。
- 测试窗口：仅NPU7临时 `enable=True, mode=0`；这是用户授权的开发包加载模式，不是给包补上受信任签名。
- 保护：设置前保存快照，独立8分钟 systemd 恢复定时器；正常/异常退出均恢复原值并核验，恢复成功才取消定时器。
- 设备包仅在自有容器内临时替换，未覆盖宿主共享CANN；先备份，退出时恢复并逐字节比较。
- 已核验两机均恢复 `False/5`，官方设备包恢复，自有容器均只剩原有 `sleep infinity`。
- 初次命令因交互确认缺失返回200，没有应用变更；后续在用户已授权范围内提供确认并成功执行。失败尝试单独留存。

## 实验配置与结果

| 项目 | 实测 |
|---|---|
| 软件 | nf基线 `fb4fbc8` + 既有未提交集成；配套自编译Host和Device；CANN8.5.1，Python3.11.14/torch2.9/torch-npu2.9 |
| 硬件 | Node0（192.169.0.173）+ Node2（192.169.0.125），每节点2 Rank，总4 Rank |
| workload | 每Rank 8MiB FP32 SUM AllReduce，1次warmup + 3次measured，无额外barrier，无异常注入 |
| Device加载证据 | 两端实际日志 `build[nf-aicpu-v2] enabled[1]`，源记录 `source[aicpu]`，runtime6/7与物理14/15显式区分 |
| 数值 | 四Rank均 `status=passed`、`max_error=0`，期望值10；每节点结果门禁通过 |
| profiler | 每节点650 task，共1300 task |
| 语义 | 每节点256/256 exact，共512/512；重复语义、重复profiler身份及invalid match均0 |
| Host控制事实 | 每节点56个control task精确enrich |
| execution graph | 1300节点、1756边；跨机Notify 144条observed、同机跨设备128条exact、本地Notify 224条exact |
| 图检查 | 无环、无重复ID、无缺端引用；跨机及同机RDMA未决通道均0，严格replay/graph门禁均通过 |
| 等待分析 | 496个Wait，全部paired，正常样例无根因候选；未提供异常baseline，不宣称定位出故障 |
| HTML | 统一入口生成execution/waits/resource；另由现有CLI生成聚焦最后一次AllReduce的focused_waits，交互烟测通过 |
| 回归 | 154项诊断单测、2项workload结果门禁单测均再次通过 |

100%是**已采到的512条语义与DB的匹配率**，不是1300个硬件task全部有算法语义。
每节点另有394个profiler-only task，保留在图中而不虚构phase/step。

## 一个真实跨机“在等谁”的例子

最后一次AllReduce（总第4次，测量第3次），同一allgather / step0：

```text
Node2 / Rank2 / device6 / stream90 / task199
tx_data_signal_start，Notify资源1228
                  |
                  | cross_node_notify_sync_observed
                  v
Node0 / Rank0 / device6 / stream90 / task200
rx_data_signal_start / NOTIFY_WAIT，Notify资源1228
本地Wait时长：28.199 us
```

这条边来自原始DB通知资源、Rank方向、受控operation绑定和完整通道顺序配对，
不是手绘关系，也不是跨机时间最近匹配。证据ID `e_02658ef5ea1c976e6fae343d`，
源执行 `x_0378905cfd12e0d2ae997731`，目标执行 `x_8faad4fdd7630e4670878520`。

`focused_waits.html` 默认聚焦 `op_ede2b9305f34dc40c737e515`；等待列表可定位上述Rank0/task200，
任务详情可沿生产者关系回查Rank2/task199。所有图由项目现有artifact驱动渲染器生成。
浏览器自动预览因本地file协议策略被拒绝，本轮没有截图级视觉验收，也没有用其他入口绕过。

## 证据位置与边界

工作空间 `test/out/nf-four-node-20261022/`：

- `authorized-evidence/`：原始DB、Host/Device日志、四Rank数值结果、原配置与恢复记录。
- `authorized-node0-evidence.tar.gz`、`authorized-node2-evidence.tar.gz`：完整采集归档。
- `authorized-manifest.json`：物理Node0/Node2、runtime6/7、全局Rank0–3及4次受控调用的绑定。
- `authorized-replay/nf-authorized-2n4r/`：合并、execution/resource图、diagnosis、关键路径报告和HTML。
- `authorized_device_guard.py`、`authorized_two_node.sh`：限定NPU7的宿主测试/恢复及双机调度脚本。

原始文件夹中的node1是本次torchrun的第二节点，实际为物理Node2；不与故障物理Node1混淆。
跨机时钟未校准，边表示依赖拓扑，Wait时长来自接收节点本地；RDMA门铃不是网络完成时间。
资源图有96个显式控制boundary（不是未匹配通知），本地关键路径仍为partial_evidence，
没有全局关键路径，不能解释成整个训练workload的精确完成时间或性能测量结论。

Host `libhcomm.so` SHA256：`498c951114cff9a2d6cd5e02958a6bf1bc3a90cd661ac93d4b0ba4243430a64e`。
自编译Device包SHA256：`2b30fbe89be9eaa3c962f139aee162d356e97e1ce2b0788181d649d380f9974f`。
Device二进制、其他Host库和源代码快照哈希保留在同目录 `delivery.json`。

旧未授权阶段的checkcode加载失败、官方Device语义为0的结果仍保留，见
[此前失败对照](nf-two-node-validation.md)，不覆盖为成功数据。
