# 调用前准备迟到：离线选择补充

## 本轮冻结规则（回放前记录）

不改采集、任务身份、边、1.5倍/3MAD检测、前5个正式轮次或已有内部Top1簇排序。
内部执行簇与Host准备迟到是两个不同机制的提案，不能因为Host不属于设备任务就丢掉后者。

1. 内部提案沿用已有局部Top1簇全部执行候选，传播仍非必要。
2. Host提案必须有公开准备区间及绑定API、同定位前5轮、原分析已验证的唯一Notify生产端、
   慢peer Wait及超出校时误差的真实重叠。没有支持的Host慢区间仍是未归因线索。
3. 两类提案统一使用`(当前耗时-前5均值)/max(前5均值,3MAD)`比较相对历史异常程度。
   内部提案按物理stream/task kind分组先平均，再等权平均，避免重复切片放大权重。
   此第二阶段不沿用内部簇的1.5增量封顶，不加传播数奖励；同分保留内部提案，再按稳定ID。
   仅一个最高分提案进入最终候选。此规则不是经过校准的故障概率或绝对报警器。
4. Host区间保留独立activity身份，stream/task为null；device anchor不是Host任务。
   公开准备到API的关联不伪造成execution边。Notify边才是原图依赖。
5. 新采集保留支持端点/边/时间及慢化比较。旧三例已按用户要求清理原DB/全图，只能回放
   原封存报告的选择层；旧支持结论标为`sealed_prior_analysis`，不能冒充重新构图或逐跳复核。
6. 分析器不接收注入类型、Rank、轮次、窗口或评测文件。生成并封存后由独立评测读取真值。

本例延迟位置和旧结果已经公开，因此这次属于已知样例离线修复，不是盲测准确率验收。
保持原报告不变，同时对两组资源竞争及纯净组做退化检查。没有准备/提交公开观测时不能
从长Wait直接猜测调用前延迟；没有慢Wait支持不宣称其造成下游阻塞。

## 作用范围

本轮只接入`test/diagnose_gpt_local_clusters.py`的新双机制选择模式及封存报告回放入口，
不悄悄切换`hccl-diag analyze`既有分类合同。新公共支持事实来自`source_events.py`，
但默认发布入口仍把Host列为外部线索。

新GPT回放入口默认`--source-policy dual`；显式`--source-policy execution-only`保持旧选择。
两类源头数量分开计数：Host候选是准备区间，不是一个被虚构出来的HCCL执行task。

## 本次已知样例回放

原输入均只读；新产物独立保存于`test/out/host-delay-selection-20261103-003/`。

| 已有实验 | 新首选 | 独立同Node/预声明Rank正重叠评测 | 说明 |
|---|---|---|---|
| 500ms调用前延迟 | Rank0，第25正式轮，bucket9，Host准备区间 | Host区间1/1 | 原内部Top1第31轮0/3，现降为非首选执行提案 |
| 1024MiB通信竞争 | 原Rank1第25轮执行簇不变 | 执行task3/3 | 按运行前声明的Rank0/1两端评测；仅主Rank0仍0/3 |
| 8192阶计算竞争 | 原Rank0第25轮执行簇不变 | 执行task3/3 | 原传播路径保持不变 |
| 纯净GPT对照 | 无新增Host候选；原执行Top1不变 | 不适用 | 仍有3个资源候选，不能宣称误报已解决 |

延迟候选公开观测509.406370ms，前5轮均值8.832740ms、MAD0.158340ms，增量500.573630ms。
无量纲相对异常分56.6725；旧内部Top1提案用相同公式为2.7121，因此选择准备迟到。
全部65个Host观测中其余64个没有足够慢peer Wait支持，仍不准入。
原封存分析保留2个Wait支持ID与Notify边ID，但当前缺失这些端点原始事实；回放明确继承旧支持
结论，不伪造端点、流号、任务号、等待时长或完整execution.html。

分析先写入`report.json`、`report.html`和含SHA256的`sealed.json`，随后独立评测写`evaluation.json`。
报告保留全部机制提案、原内部排序与被拒绝Host理由。调用前延迟1个Host区间与另外6个
设备task不是同一统计单位，不合并报告“7/7任务级准确率”。这是选择层的探索验证，不是重采集
或独立盲测；不能由此推断任意单/多机准备延迟都可定位。

## 复现命令

从根目录运行，输出目录必须不存在：

```bash
python3 test/replay_source_selection.py \
  --report artifacts/gpt-three-anomalies-20261102-100/gpt2-three-anomalies-20261102-101/top1/report.json \
  --output test/out/host-delay-new-replay

python3 test/evaluate_source_selection.py \
  --report test/out/host-delay-new-replay/report.json \
  --original-evaluation artifacts/gpt-three-anomalies-20261102-100/gpt2-three-anomalies-20261102-101/evaluation.json

python3 -m unittest hccl.tools.diagnosis.test_source_selection test.test_source_selection
```

第一条命令不读取第二条命令的输入，也不接受注入位置参数。旧支持继承只在该封存回放入口
显式开启；新采集分析必须有新增的完整支持端点事实，不可用旧摘要降级绕过。

验证：419项诊断单测通过；234项脚本测试中232项在受限环境通过，另2项本机回环端口
测试在允许监听后复跑通过。新策略包含完整公开fixture的严格回放→Host证据→选择→封存→
独立评测接线测试，以及缺边、错时、缺校时、旧摘要显式继承、不同Rank不命中等反例。
原三例全部留存SHA、原候选和原评测也再次核验不变。没有重新训练或同步服务器。
