# HCCL Trace诊断

单机和多机使用同样的用户命令，不再选择实验脚本或策略版本：

```bash
hccl-diag capture -o capture -- torchrun ... train.py
hccl-diag analyze capture
```

训练需先合法部署配套Host/Device并接入`hccl_trace.Trace`。采集在Linux/CANN节点运行；
离线诊断只依赖Python标准库。多机在各节点采集同一run_id，汇集`nodes/`后使用同一分析命令。
已有本机目录可用`hccl-diag join node0-capture node3-capture -o capture`汇集并校验SHA。
跨机软件校时使用`hccl-diag clock-probe`。唯一训练样例是[无注入 GPT-2](../../../examples/gpt2_normal.py)。
输出默认`capture-report/`，也可用`-o results`；`--keep-debug`保留完整中间证据。

## 支持路径

通信位置由显式 SDK 调用和真实 API 证据唯一绑定，不按通信形状猜桶。
SDK 轮起点经本机 profiler 时钟转换，晚开工作为独立观测写入 `iteration_start_observations`，
不进入依赖溯源根因。这个观测复用轮次打点，不需要额外记录 Host 准备起点。

单机和多机均使用慢Wait依赖回溯，不做候选分簇、P95排序或Top1选择。
从慢Wait沿配对Notify和实测流顺序回查；仅晚开始的任务不是根因，有独立执行增量的任务仍可成为候选。
无法用现有证据解释的慢Wait、孤立慢任务和无传播支撑的Host准备变长均保留为未归因观测。
设备任务取最近至多五个同定位、未标慢的正式样本均值。判慢的执行耗时或任务间隙不再作为该任务的参考；
不足五个用实际数量，无先例只作为起始样本。源头1.5倍、Wait 1.2倍，均结合3MAD。
Host 准备区间保留连续前五轮口径。未标慢不等于已验证正常，样本少时结果需结合实际参考轮次看。
节点数来自真实采集身份；跨机回溯需要校时，缺证据时不制造跨节点时序或物理因果。
有校时且存在唯一的跨机准备/数据 Notify 配对时，另行比较“发送端提交数据结束到接收端数据通知结束”的区间。
要求同一方向、通信位置和消息大小有五个此前未标慢的参考；接收 Wait 和提交后区间都显著变长，且发送端收到准备信号后没有明显晚提交，才输出 `cross_node_path_candidates`。
该候选与设备任务、Host 区间并列，不是 RDMA 硬件传输时间，也不能判定网卡故障或限速。
没有跨机校时的采集和单机采集不会输出这类候选；区间证据不足时仍保留原慢 Wait 分析。

## 双终点回溯

安装后对有前后时钟探针、正式轮标记和 SDK 调用观测的采集目录运行：

```bash
hccl-diag-endpoints runs/my-job -o reports/my-job.endpoints.json
# 未安装命令时，从仓库根目录用同样参数运行：
python3 -m hccl.tools.diagnosis.endpoint_replay runs/my-job -o reports/my-job.endpoints.json
```

该命令只读原始采集，在临时目录重建并校验执行图，不修改 `hccl-diag analyze` 的默认行为。
输出中的 `results` 分别给出晚开工和完成尾段的回溯；可能同样晚完成的 Rank 不强行去重成一个。
先看 `trusted_source_events`（通过统计、依赖、顺序、阻塞和上游检查的源头），再看
`supported_stage_events`（已验证局部阻塞但上游仍未确定）。普通慢任务、传播 Wait 和
证据缺口不算源头命中。没有共享 Event 身份或跨机时间顺序不可确认时保留未确定；
协议区间不是 RDMA 硬件传输耗时。结果附诊断 SHA-256，不读注入标签。

## 异常阶段事件

```bash
hccl-diag-endpoints runs/my-job --stage-report -o reports/my-job.stages.json
```

`diagnosis.stage_report.events` 不要求确定最上游根因。候选使用同位置前五轮样本，
同时检查中位数、MAD 和历史最大值；只有强异常，或有连续异常和下游证据的阶段进入报告。
起止取自实测阶段，不按注入窗口改写。事件的起止包住所有所属阶段；
有多个阶段时应使用各阶段区间的并集做重叠评估，不能把中间空档算进去。
跨机时间附校时不确定性；Host 活动窗口的时间关联不是硬件竞争或 RDMA 完成证明。

## 常规回溯中的对端读取

对已验证的单节点 single-ring direct 远端读取，还会对照同次通信的其他接收方和两端本地输入 Copy。
符合方向性慢化但接收方本地对照也异常或不全时保留原候选；其他符合条件的任务单列为疑似对端影响。

默认滚动诊断也识别已验证的单节点四 Rank AI CPU single-ring direct 双流输入 Copy。
只处理同芯片、同一次通信、等尺寸且语义精确的重叠配对。重叠样本不进入单条参考；
两条各至少有三个非重叠参考。此前合格正式样本不够时，才从第 6–10 个预热轮补同位置、
同结构的样本，只用于重叠预算，不改变普通判慢的参考。只有两条都判慢、同芯片没有第三条
可见搬运或计算重叠，且两条合计完成包络不超过各自历史耗时上界之和的 1.2 倍时，
才不把这次单条变长当作根因。
原始耗时、慢化标记、依赖和晚开工证据保留；其他情形不据此排除。
配对、参考和判定保存在 `root_causes.json` 的 `input_copy_overlap_observations`，不证明物理瓶颈。
独立 `--baseline` 对比和多节点回溯不应用此规则。

## 三份报告

- `execution.html`：候选所在正式轮的原图切片；完整图可由debug或原始输入重放。
- `root_causes.json`：候选位置、实际/参考时长、慢化倍数、覆盖率及证据限制。
- `propagation.html`：候选到慢 Wait 的原依赖传播链，展示任务英文名、起止时间和耗时增量。
  未归因观测和疑似对端读取证据只在 JSON 中保留。

用户报告已去除关键路径、模型收益等字段和展示；真实依赖边与传播证据不删除。
切片保留真实通信显示区间和完整质量计数；完整图是否留存以实际debug保留设置为准。
报告成功表示采集关联/构图/分析完成，不等于一定定位到物理故障。

## 命令与模块

用户只需要使用 `hccl-diag`：`capture` 采集，`join` 汇集多节点数据，
`clock-probe` 采集跨机校时证据，`analyze` 生成诊断报告。`hccl-diag --help` 可查看命令。
同目录的其他 Python 文件是这些命令调用的内部模块，负责数据解析、语义关联、构图、依赖回溯和报告导出，
不需要单独运行。开发测试、独立旧命令和历史实验不随用户版发布。

- [从克隆到报告](../../../README.md)
- [配套库部署](../../../docs/deployment.md)
- [多机时钟证据](../../../docs/multi-node-clocks.md)
