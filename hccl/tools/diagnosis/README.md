# HCCL Trace诊断

单机和多机使用同样的用户命令，不再选择实验脚本或策略版本：

```bash
hccl-diag capture -o capture -- torchrun ... train.py
hccl-diag analyze capture
```

训练需先合法部署配套Host/Device并接入`hccl_trace.Trace`。采集在Linux/CANN节点运行；
离线诊断只依赖Python标准库。多机在各节点采集同一run_id，汇集`nodes/`后使用同一分析命令。
已有本机目录可用`hccl-diag join node0-capture node3-capture -o capture`汇集并校验SHA。
输出默认`capture-report/`，也可用`-o results`；`--keep-debug`保留完整中间证据。

## 支持路径

| 自动识别 | 保留的诊断路径 | 边界 |
|---|---|---|
|单节点|局部依赖簇Top1＋严格Host准备迟到证据|固定位置/部分预冻结位置有验证，不保证任意负载精度|
|多节点|P95全量任务群辅助的单簇排序＋同样严格的Host证据|SDMA已知开发数据改善，通信竞争/RoCE漏诊及正常误报尚未解决|

节点数来自真实采集身份，不从Rank数或目录名称猜。无校时时保留节点本地时长、拓扑及证据边界，
不制造跨节点时间或物理因果。默认使用当前轮之前连续五个正式轮均值，1.5倍/3MAD和原图准入不变。
一个胜出簇内候选平行，不标“主候选”。
未被所选簇解释的慢Wait仍公开为未归因观测，不将无候选解释为无异常。

## 三份报告

- `execution.html`：候选所在正式轮的原图切片；完整图可由debug或原始输入重放。
- `root_causes.json`：候选位置、实际/参考时长、慢化倍数、覆盖率及证据限制。
- `propagation.html`：候选到慢Wait的原依赖传播链。

用户报告已去除关键路径、模型收益等字段和展示；真实依赖边与传播证据不删除。
切片保留真实通信显示区间和完整质量计数；完整图是否留存以实际debug保留设置为准。
报告成功表示采集关联/构图/分析完成，不等于一定定位到物理故障。

## 开发与历史

正式入口是`cli.py`，推荐选择集中在`recommended_policy.py`；parser、binder、图模块都是共用基础设施，
不是多个用户版本。旧函数/隐藏参数仅为冻结脚本和回归兼容，不能当作推荐命令。
11个选择实验入口归档于`test/archive/diagnosis_20261108/`，旧报告和SHA清单不重写。

- [统一操作](../../../文档/统一采集与诊断.md)
- [从克隆到报告的完整教程](../../../文档/从零开始运行训练诊断.md)
- [当前活动任务](task.md)与[实现合同](spec.md)
- [整理前说明，仅供历史参考](archive/2026-11-08/README-before-consolidation.md)
