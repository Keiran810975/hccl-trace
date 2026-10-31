# 诊断分类与回溯边界

2026-10-31，按用户提供的《HCCL-Trace 诊断脚本修改方案》实现，source policy6。
此修改针对离线Python消费者，不改Host/AI_CPU打点、msprof解析或原始依赖图。

## 任务归属

`task_classifier.py`只接受已精确匹配且完整的HCCL语义，或唯一的DB通信调用归属，
作为`hccl_internal`证据。只有operation字符串、kernel名称或`kernel_mix_aic`类型不够。
当前artifact尚无经过核验的外部计算算子归属，因此不自动赋予`external_compute`；
相关任务保留`unknown`。Host preparation是独立公开观察区间，不是假造的设备任务。

## 回溯与分类

保持原有前5个正式轮次均值、1.5倍和3 MAD的比较，不新增绝对增量门槛。
从慢Notify Wait，沿真实observed/exact通知生产端和同流前驱反查。
所有经过的任务必须有相同正式Iteration身份；同轮可以跨CollOp。
跨轮记录`iteration_boundary`，身份缺失记录`missing_iteration_identity`，不猜测、不补边。
已有warmup、FFts不完整、未配对Notify和RDMA仅提交等边界继续保留。

- 通信内部源头候选：可信HCCL内部、执行慢化、完整真实路径到慢Wait。
- 外部异常线索：公开Host准备区间变长。保留实际调用/API及通知支持状态；没有下游支持也可展示，
  但不绘制虚构路径，不作为内部主候选，不声称已找出GEMM或物理故障。
- 未归因观测：孤立慢任务、gap、未知归属任务、回溯边界。不存在依赖边不等于存在外部计算根因。

类别分别排序并给出category_rank；内部主候选与首个外部线索ID分开。
`physical_cause`仍可为unknown，同流顺序或路径连通不等于量化了个体因果贡献。

## 公共结果schema v2

一条命令和最终三文件不变：execution.html、root_causes.json、propagation.html。

- `communication_source_candidates`：内部源头候选。
- `candidates`：上述数组的兼容别名，不再混入孤立任务或Host线索。
- `primary_candidate_id`：仅内部主候选，没有则null。
- `external_anomaly_clues`、`primary_external_clue_id`：独立外部线索和首个线索ID。
- `unresolved_observations`：未归因任务与等待边界。
- `category_counts`、`task_domain`、`diagnosis_category`：分类统计及归属。

v1历史报告仍可被最终文件验证器读取；分析旧输入后输出v2，旧结果不会原地改写。
评测代码若只读取candidates，现在只评估内部候选；不得与原v1混合候选的历史准确率直接比较。
传播HTML按类别展示，有真实依赖才展开路径。无支持Host线索和未归因观测同样可见。

## 回归与验证边界

```bash
python3 -m unittest discover -s hccl/tools/diagnosis -t .
python3 -m unittest discover -s test -t .
```

测试覆盖内部Copy阳性、孤立慢任务、未知mixed kernel、Host独立分类、跨机RDMA协议锚点、
同轮跨调用、跨轮与缺Iteration边界，以及原绑定/构图/统计回归。
第二条中的两项CPU校时测试需要允许本机回环监听；不需要NPU。
这是代码与离线验收，不是新设备异常注入或准确率验收，不预设准确率上升。

本轮验收：344项诊断回归、167项脚本回归通过；CLI生成恰好三份独立报告且输入哈希不变。
使用隔离无界面Chrome核对1440和390像素宽度下的分类、Host锚点及执行图加载，未发现脚本错误或页面溢出。
未重跑训练、采集或新的NPU实验，未修改服务器环境。
