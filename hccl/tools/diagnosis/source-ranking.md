# 候选排序与五组历史数据复核

2026-11-01，nf 离线消费者修改；source policy6 不变，source_ranking_version=2。
没有重新训练/采集，没有调整设备、慢化阈值、图门禁或命中标准。

## 原因

1. 原排序优先关联调用数、Rank数和Wait数，再看局部关键路径收益，容易把零散波动放在
   真正持续变慢的源头之前。依赖可达说明存在路径，不代表该源头解释了全部Wait增量。
2. 100ms调用前sleep主要表现为Host准备区间变长，不是设备任务自身执行100ms。
   112报告确实观察到Node3 Rank4第32轮Host准备106.500180ms，前5轮均值6.449314ms，
   增100.050866ms；但缺少被它延迟的慢Wait支持，仍为unresolved_host_preparation。
   不能把调用之后才执行的任务挪到sleep期间，或把外部线索算成内部根因来提高命中率。
3. 机间协议依赖已存在，但RDMA提交不等于硬件完成；缺失完成时间、归属或相容的
   Notify时间证据时，回溯必须保留边界。不能通过放宽配对/时间门禁补出根因。
4. 本批通信、计算和限速注入没有持续明显拉长整轮训练。该检查只作影响佐证，
   不作为局部任务判慢的新门槛，也不能据此断言没有局部影响或已证明物理原因。

## 排序修改

- 保留前5个正式iteration、同定位任务均值、1.5倍、3 MAD；不加绝对增量下限。
- 根因发现仍从慢Wait反查真实依赖；候选资格、成员集合和传播链不由排序层改变。
- 同Node/Rank/通信组的相邻候选iteration归为候选段；旧Block/bucket入口仍按其位置分组。
  分组是展示与排序单位，不声明整段只有一个物理故障，也不跨机累计延迟。
- 单任务排序预算=min(自身正执行增量, 关联慢Wait的最大正增量)。一个execution只计一次，
  不因多条传播路径或多个Wait重复放大。候选段按这些预算的去重和排序，段内再按任务预算排序。
- 这是启发式优先级，不是实测因果贡献、训练完成时间损失或统计置信度；局部关键路径
  收益仍保留为独立指标，零收益不删除已有证据支持的候选。
- 不再把几十微秒源头可达百毫秒Wait，直接解释成“它导致了全部百毫秒等待”。
  supported_wait_excess_beyond_source_growth_ns仅是两个增量的差，不是剩余延迟的数学下界。

## 输出

最终仍是execution.html、root_causes.json、propagation.html，不增加正式交付文件。

root_causes.json新增source_regions、recommended_candidate_ids和source_ranking_version；
候选新增source_region_id/rank/budget、ranking_execution_budget_ns、ranking_metric、
supported_wait_max_excess_ns和supported_wait_excess_beyond_source_growth_ns。
全部候选仍可见；推荐集合只是排名第一段，不是已证明的根因集合。
propagation.html展示候选段排名、去重排序预算及关联Wait增量，并保留原传播路径。

## 历史数据回放

旧原始DB及完整artifact已按此前要求清理。本次从原生传播HTML及结构化报告读取原候选、
完整慢Wait事实和已报告路径，只重新排序，不声称完成新的全图根因发现/回溯。
五组慢Wait覆盖分别9739/10729/10785/10415/11564，读取器逐组核对完整性和重复事实一致性。
分析器不读注入真值；排序完成后，独立评测才按原同Node/Rank正时间重叠标准核对。

| 实验 | 全部候选命中（不变） | 第一候选：原→新 | 推荐段命中 |
|---|---|---|---|
| 101 Copy竞争 | 35/56 | 否→是 | 35/35 |
| 102 通信竞争 | 2/19 | 否→否 | 0/2 |
| 103 计算竞争 | 1/50 | 否→否 | 0/1 |
| 111 网卡限速 | 0/52 | 否→否 | 0/4 |
| 112 调用前延迟 | 0/50 | 否→否 | 0/7 |

SDMA第一候选为Node3 Rank4第23轮，自身执行增量40.900us；首段覆盖22..24轮。
任一内部候选命中仍为3/5，第一候选从0/5到1/5。只能视为本批历史排序复核，
不是独立新实验的准确率，更不能声称其他四组已修复或35/35代表系统准确率100%。

CPU审计服务器目录：
`/home/commTeam/zjy/zjy-new-workspace/hccl-diagnose-node03-audit-20261101-001/ranking-v2/`。
每组`101-complete`等目录保留analysis-input.json、summary.json、reranked.json；
最终代码再回放保存在`101-final`等目录，final-verification.json记录排序代码哈希和命中核对。
evaluation-comparison.json是后置评测，iteration-impact.json是目标Rank整轮耗时复核。
原五组报告未覆盖。精简证据本地见
[复核结果](../../../test/out/node03-candidate-ranking-20261101/evaluation-comparison.json)。

## 验证

```bash
python3 -m unittest discover -s hccl/tools/diagnosis -t . -p 'test_*.py'
python3 -m unittest discover -s test -t . -p 'test_*.py'
python3 -m test.audit_retained_diagnosis --report /path/to/report --output /new/audit
```

脚本回归中校时探针需要本机回环端口。排序测试覆盖孤立高fanout、连续候选段、重复execution、
不跨Node/Rank/通信组、零关键路径收益、外部/未知不晋升、幂等排序及留存证据缺失拒绝。
本轮351项诊断回归、181项脚本回归通过。

## 剩余限制

通信竞争/计算竞争需要进一步核实是否真正覆盖了瓶颈、原比较位置是否具备完整任务语义；
限速需要可测的机间协议完成区间/硬件完成证据，而非把doorbell耗时当传输耗时。
Host延迟可以明确报告观察值，但没有真实慢Wait传播证据时仍不能归因为内部执行任务。
这些不是重排现有候选即可补出的事实；本轮不扩大采集权限、不自动重跑设备实验。
