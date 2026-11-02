# 显著范围筛选与分级传播阈值：固定 GPT 离线试验

## 范围与结论

按用户提出的“50%预选 → 显著范围 → 上游解释/剔除 → 20%下游传播”实现可选离线策略。
只回放 `artifacts/gpt2-semantic-20261102-001` 中同一份正常/强Copy采集，未启动训练、
未访问NPU、未改生产端、原始时间/语义/依赖和旧报告不变。**本次未达到定位精度目标，
不能替换当前默认诊断策略。** 不删除失败对照，也不把选中一个范围等同于准确定位。

## 固定规则

入口为 `test/replay_significant_regions.py`，实现为 `significant_regions.py`。
输入只有原始rolling比较事实和execution edges，不接受注入位置或外部baseline。

1. 保留每个定位任务前5个正式iteration的均值/MAD；自身执行增长须达到50%并超过3MAD，
   不恢复绝对增量门槛。资源执行为可信HCCL归属的Copy、Inline Reduce及已有支持的计算任务；
   AI_CPU父任务不重复计数，Notify Record比值不被当作独立payload执行源头。
2. 一个范围固定为“同Node/Rank的一次、公开绑定的collective调用”。第一种评分只对预选
   慢执行任务计算 `sum(当前-前5均值)/sum(前5均值)`，即参考耗时加权增幅。
   达最大分数90%或增幅达到150%的范围入选。150%**增加**对应2.5倍总耗时，
   不是1.5倍。90%是本次明确固定的“相近”定义，不是验证过的最优参数。
3. 在入选调用中检查慢Wait的实际唯一Notify producer，再沿真实依赖找慢执行任务。
   可解释的Wait剔出根因候选；证据不足的Wait保留为`unexplained_wait_candidate`，
   明确不是已证实源头。Copy/Reduce自身执行增长不能仅凭“它前面有另一个慢任务”就被解释掉；
   依赖能解释晚到，不自动解释任务内部为何执行更久。
4. 从执行候选沿真实出边搜索，同一正式iteration内允许分支和跨调用；20%+3MAD识别下游Wait。
   只有实际Record→Wait路径可解释等待增长，仅沿Wait自身流的order到达不能解释Wait变长。
   正常/更短Wait、另一独立执行增长、时间矛盾、未校准跨节点、轮次或4096遍历预算均显式停止。
   保留每个源头/慢Wait对的一条完整见证路径，不指数枚举所有等价组合路径。
5. 未解释Wait候选单独列证据不足原因，不虚构从它出发的确定传播链。真实依赖＋慢Wait是观测
   传播证据，不代表已测得源头的因果贡献；并发Wait不能累加成workload损失。

第一轮发现评分仅看预选任务，仍会被个别高倍率任务主导。因此在不读取注入坐标给分析器的
前提下增加第二个明确标识的**探索性对照**：`--score-population all_comparable_work`，
对范围内全部可比较资源执行计算同一加权增幅。阈值、根因规则和事实不变。
两版均封存后独立评测，第二版属于看到第一版问题后的改法，不是独立泛化验收。

## 结果

以同Node/Rank且任务区间与实际注入活动包络有严格正重叠评测；不使用配置触发桶或整个
iteration替代实际区间，不把Host Copy+同步活动包络冒称纯SDMA硬件时长。

| 方法 | 入选范围 | 执行候选命中/总数 | 未解释Wait候选命中/总数 | 合并候选命中/总数 | 传播路径 |
|---|---:|---:|---:|---:|---:|
| 原默认Wait驱动 | 未使用此筛选 | 0/306 | 不纳入原默认源头列表 | 0/306 | 710 |
| 仅预选慢执行评分 | 62 | 3/183（1.64%） | 0/343 | 3/526（0.57%） | 44 |
| 全部可比较执行评分 | 3 | 0/25 | 0/23 | 0/48 | 7 |

前者916个预选执行任务分布在379个调用范围；第二门槛仍留下62个范围，并非一个。
两版第一候选均未命中。纯净组也会入选：前者43个范围、127执行候选＋254未解释Wait，
后者2个范围、23执行候选＋19未解释Wait；**不能把“候选变少”说成准确率已提高。**

高倍率范围不只发生在注入处。例如Rank2第46轮一个Inline Reduce从前5均值0.540us变为
28.939us，53.59倍、历史MAD=0，满足现有倍率/MAD条件。这是非注入处真实记录的局部
异常波动，不能仅因不命中就说它时间不真实，也不能确定其物理原因。

注入Rank0第25轮内三个资源执行的预选加权增幅约196.10%，所以第一版会保留；但是
该调用全部16个可比资源执行的总参考耗时619.540us，总增量101.287us，整体仅增长16.35%。
第二版把该局部异常稀释，反而选中了第16/19/35轮三个整体增幅约117.82%至125.31%的范围。
这些比例是并行任务耗时统计，不是调用墙钟增加量。

## 新找到的局部路径

第一版保留了原先漏掉的三项自身执行增长：Rank0 Inline Reduce `stream90/task27609`，
以及Copy `stream90/task27611`、`stream50/task10691`。实际边不变。

```text
Rank0 stream90 Inline Reduce task27609
  2.9958us → 14.300us（+377.33%）
      ↓ 原生stream order
Rank0 stream90 Record task27610: local_main_record_sub_begin
      ↓ 原生exact local Notify
Rank0 stream50 Wait task10690: local_sub_wait_main_begin
  7.4599948ms → 9.559109ms（+28.14%）
```

这条两边路径在20%门槛下可显示，而50%下不会显示。不能把Wait的2.099ms增量全部归给
Reduce的11.3042us执行增量。两项Copy后的主要汇合Wait本次更短，降到20%也不会产生
“增长传播”证据；仍保留Copy候选，但不为它们伪造变长Wait或跨设备时钟。

## 复现与产物

从工作区根目录运行，使用新的输出目录，不覆盖旧结果：

```bash
python3 test/replay_significant_regions.py \
  --rolling-report artifacts/gpt2-semantic-20261102-001/analysis-input/reports/strong-copy.debug/analysis/strong-copy/rolling/report.json \
  --edges artifacts/gpt2-semantic-20261102-001/analysis-input/reports/strong-copy.debug/analysis/strong-copy/dep_graph_edges.csv \
  --out test/out/significant-regions-new/strong-copy
```

第二版额外指定 `--score-population all_comparable_work`。阈值位于
`RegionOptions`，本次没有事后修改阈值挑命中率。评测是另一条、在`sealed.json`之后执行的
`test/evaluate_significant_regions.py`，分析器不接收评测真值。

本次路径：`test/out/significant-regions-20261102-001/`：

- `strong-copy/report.html`：第一版全部候选与44条逐跳传播路径。
- `strong-copy-all-work/report.html`：第二版全部候选与7条路径。
- `normal/`、`normal-all-work/`：相同策略的正常组对照。
- 各目录`report.json`、`input-manifest.json`、`sealed.json`；异常组另有独立评测JSON。
- `audit-summary.json`：四次封存结果、评测及旧报告不变哈希。
- `method-v1.zip`、`method-all-work.zip`：两次方法源快照。

验证：15项新专项、391项诊断全回归通过。不是生产默认切换，也没有服务器部署或新采集。
后续应在不读取注入坐标的前提下设计更局部的范围，并用正常组估计范围级显著性/误报；
不能为了保留本次三项任务，事后手选Rank/iteration、时间宽度或阈值。
