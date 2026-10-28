# 最近五轮参考与单机随机实验

本轮需求：910C单机4 Rank，1个正常组和4类异常各5个，每例独立重跑完整workload，共21次。
已实现分析、随机运行器、公开调用绑定和独立时间窗口验收。**2026-10-25完成21/21次正式实验**：
正常组1例，延迟/Copy/通信/计算各5例，均通过严格语义与构图门禁；每例语义142080/142080 exact，
四类根因定位均0/5，正常组有误报候选。采集/构图完成不代表诊断准确率通过。
图与逐例摘要在`artifacts/single-node-formal-20261025/`。Node0的NPU0..3出现外部VLLM任务，
整机空闲保护曾在第6例启动前停止；用户随后明确允许仅用空闲NPU4..7继续。
后续仍检查目标整卡进程及显存，记录共享主机干扰，未重跑已完成workload、未放宽诊断门禁。
正式尺寸混合预检及兼容方案见[修复与证据](gemm-compatibility-20261025.md)。
最终状态以该产物目录`records/suite-state.json`为准，不重复启动队列。
20例窗口评判已用保留的小型证据独立复核；21张图已逐例通过校验值和真实浏览器依赖选择检查。
自有负载已退出，目标卡空闲，Host/Device包哈希未变；正常组原始4份DB保留，异常大文件已清理。
下文旧失败记录保留为历史，不将任何预检算作正式结果。

## 当前源头策略v4（本地修复，待新设备采集）

判慢仍使用前5个正式iteration均值、1.5倍及3*MAD，无绝对增量下限；独立验收仍为
主源头与实际注入窗口在同一Rank上重叠。分析器不读取注入位置或窗口来选择候选。

1. **从慢Wait回溯，而非先挑最大慢任务。** 从真实Notify生产端沿已存在的observed/exact
   依赖反查，正常执行但晚开始的中间任务继续向上找。遇到可比的执行耗时增长，记录源头候选；
   自身增长与上游晚到同时存在时保留两条解释。gap仅是观察，不冒充有执行主体的根因。
2. **不在调用边界截断真实依赖。** 保留已有跨operation流顺序边，不增加推测边。
   局部HTML、保留图和“Show evidence chain”均保留完整源头到Wait路径及其真实端点。
3. **定位和影响分开。** 撤销v3的“整个调用必须变慢”和“移除单任务增量必须有正关键路径收益”
   两个定位否决条件。多个并列慢源头可能使单任务收益为零，不能因此否认定位证据。
   本地关键路径收益、调用跨度和slack仍独立输出；它们不是整个workload的实测收益。
4. **证据不足明确输出。** `wait_backtraces`保存真实路径、生产端时间检查和断点，`coverage`
   保存可比/不可比任务及原因。未配对、生产端时间不相容、缺GEMM语义、跨机无时钟校准等
   不再默认为健康，也不按最近时间、task偏移或邻居step补边。跨机只沿真实拓扑追踪。
5. **后台退出移出测量区。** 竞争窗口结束只发停止请求；worker完成当前在途操作后暂停，
   正式轮次结束才允许数值校验和资源销毁。保存真实活动窗口、暂停/授权时间及逐轮耗时，
   防止把后台退出开销混进后续正式轮次。后台活动结束时间仍以worker实测记录为准。

新增结构化输出：`source_policy_version=4`、`wait_backtraces`、`coverage`、`impact_status`、
`impact_scope`、`modeled_execution_gain_ns`，以及`rolling/wait_backtraces.csv`。
`diagnosis_status=unresolved_waits`明确表示有慢Wait但尚未定位，不等于没有异常。
主根因候选仍不是已证明的物理故障类型；未绑定的GEMM/Event依赖仍有覆盖缺口。

Python消费者和控制器无需重编HCOMM Device包；单进程通信worker的C++源码修改后必须
重新编译`single_process_comm_load`再部署，旧二进制不支持新的延迟收尾参数。
原21例HTML/结果/ZIP保持不变。本地合成回归及保留的真实正常预检回放不代表新异常准确率，
服务器未同步，未启动新的NPU实验。验证记录见
[v4修复验收](../../../artifacts/diagnosis-source-policy4-20261025/README.md)。

## 源头策略v2（历史：正式结果之后）

2026-10-25复核发现20个旧主候选均为任务前空隙。现已分离执行与gap组件；
gap只保留为`unattributed_gap`观察，不选主根因，执行候选必须经真实Notify生产端边指向受影响Wait。
上游gap/Wait不再自动遮蔽下游独立执行慢化；规则和覆盖缺口见
[失败复核与修正](source-attribution-review-20261025.md)。原21例结果仍属于旧策略，0/5不改写。
新版只完成本地回归及保留的真实正常预检回放，尚未重新采集正式异常；正常样本仍有候选，
不能宣称定位准确率或误报率已经达标。判慢与独立窗口评判标准未改。

## 源头策略v3（历史：下述硬筛选已由v4替换）

判慢和独立评判标准不变。新增两级筛选，不再把全采集最大的局部波动直接当主根因：

1. 对每个已绑定通信调用，按节点分别计算实际任务最早开始到最晚结束的跨度，并与前5轮
   同Block/桶、同任务结构的跨度均值比较，仍用1.5倍和3*MAD，不加绝对下限。
   局部task可以标慢，但调用跨度没有标慢时不输出主根因。
2. 执行源头除真实生产端到Wait路径外，还需对该调用的本地完成时间有正的模型影响。
   复用关键路径模型，仅移除该task相对前5轮均值的执行增量，保留其余执行、Notify完成join、
   残余Wait和未归因release/gap。没有正收益或无法重建时不冒充已定位。
   按异常调用增量、影响证据和task增量排序；这是节点本地调用分析，不是整个workload的全局关键路径。
3. 新采集在每个Rank、每个调用上记录相同的公共准备区间：前置计算提交前到AllReduce调用前。
   区间包括CPU准备、计算提交及可能的调用前延迟，不读取私有异常配置，不新增NPU任务或同步。
   `single_node_capture.bind`独立验证完整调用、DB和API绑定后导出`preparation-map.json`。
4. Host准备区间只有在其本身按前5轮标慢、调用跨度标慢，且有该调用真实exact Notify生产端
   在API之后执行、对端Wait在准备结束前已经开始时，才成为`host_preparation`源头候选。
   `source_activity_id`标识公共Host区间，`graph_id/anchor_graph_id`只是设备图上的定位锚点；
   `task_id/stream_id=null`，不伪造Host kernel或Host到设备的依赖边。物理原因仍为`unknown`。

新JSON增加`events`、`diagnosis_status`、`primary_eligible`、`modeled_execution_gain_ns`、
`selection_reason`等；`events.csv`保留逐调用判定。`diagnosis.json`/等待视图只展示通过v3筛选的
源头，未通过的局部慢化和gap仍保留在滚动报告中作为观察。独立评判函数完全未改。

```bash
python3 -m hccl.tools.diagnosis.run_diagnosis capture.json -o new-replay \
  --iteration-map iteration-map.json --preparation-map preparation-map.json
```

单机采集和离线移交入口会自动传入新生成的公共准备文件。旧采集没有该文件时仍可分析，
但不能从注入真值、空白或最近时间反推出Host准备活动。普通device GEMM的精确调用绑定和
物理资源竞争归因仍有缺口；短延迟如果被流水线吸收，也不应强行输出影响完成时间的根因。

本地回放两个保留的真实正常预检：正式尺寸混合组仍为3200个可比、726个标慢，
短通信组仍为296个可比、63个标慢；两者旧策略均有主候选，v3均为`no_slow_event`、无主候选。
这只是两个正常预检的误报排除证据，不是新异常命中率。原21例0/5和原图/ZIP不改写，
20例异常原始输入已清理，需在新代码下重新采集才能评估新准确率；本轮未部署服务器或启动NPU实验。

## 慢化判定

本轮正式分析选择 `run_diagnosis --iteration-map`，不传 `--baseline-dir`。
旧Baseline比较入口保留用于历史数据回放，不作为本轮检测参考。

- 同一次运行，取同一个Block、通信桶、Rank、算法phase/step/slice/event/类型/数据量，
  且通信任务结构一致的**前面连续5个正式iteration**。不混入预热、当前或未来轮次。
- 参考值为5个耗时的算术平均值，MAD仍为这5个样本相对其中位数的中位绝对偏差。
- 当前值严格大于参考均值、至少为均值1.5倍，且增量至少3倍MAD时标慢。
  **没有10us或其他绝对增量下限**。系数可配置，默认保留1.5和3。
- 执行时长与同operation内唯一observed流前驱后的空隙分别比较。
- 前5轮、缺一轮、语义位置重复、任务结构变化均保留不可比状态，不按出现序号补配。
  前5轮不可比较不是健康证明；持续故障进入历史后可能使滚动参考逐步升高。
- 只沿原始observed/exact依赖回查源头，分析器不读取注入配置或验收真值。

公开调用映射示例：

```json
{
  "schema_version": 1,
  "operations": [
    {
      "operation_scope": "op_FROM_CAPTURE_ARTIFACT",
      "stage": "measured",
      "iteration": 5,
      "block": 0,
      "bucket": 1,
      "evidence": "实际前台调用日志与DB通信域/操作的已核实绑定"
    }
  ]
}
```

映射必须由实际采集绑定证明。只按DB总序号、时间最近或注入选择器生成的映射不合格。
没有映射时拒绝猜测iteration。`test/single_node_capture.py`核对完整四Rank公开调用序列，
DB实际AllReduce操作计数、FP32数据量及通信域，并校验CANN_API在公开提交之后、该轮设备
同步完成之前。HCCL可能在Python返回后异步提交，因此不用Python返回时刻作结束边界。
只有完整、唯一绑定才生成映射；不读取注入配置。后台DB与前台DB分开保存，原DB不修改。

```bash
python3 -m hccl.tools.diagnosis.run_diagnosis capture.json -o replay \
  --iteration-map public-call-map.json
```

输出 `rolling/report.json`、任务与源头CSV、`index.html`，以及候选和它前5轮的真实局部HTML/SVG。
JSON明确写 `reference_mean_ns`，不把平均值称为中位数。每张历史图都是一次真实记录，
不会合成不存在的“平均任务图”。`diagnosis.json`和等待HTML同步附带滚动源头候选。

## 固定的21个计划样例

2026-10-26机制复核：旧Copy worker的`Tensor.copy_`实际记录为AI Core TensorMove，
不能仅凭D2D方向将其称作SDMA竞争。为保持旧21例可复现，默认后端未悄悄替换；
新增`injection.copy_backend="acl_memcpy_async"`显式使用ACL D2D异步拷贝，一个进程、
两个缓冲区，仍支持测量结束后收尾。Node0单例独立预检记录MEMCPY_ASYNC，正式358次活动Copy
通过；全局采集仅保留后台API、缺后台设备TASK，不能假称已覆盖后台设备时间线。
本次只做人工已知窗口核查，未运行诊断，不更新准确率；见
[单组影响与传播证据](../../../artifacts/copy512-propagation-20261026/README.md)。

```bash
python3 test/single_node_random_suite.py --output test/out/single-node-910c-random-20261024
```

- 4个Rank、4 Block、tokens2048/hidden4096/FFN16384、64/128/256MiB FP32 SUM AllReduce，10预热+50测量。
- 一个正常组；调用前延迟、Copy竞争、机内通信竞争、计算竞争各5个。
- workload seed固定，注入seed单独保存。位置在第6个及以后的正式轮次内随机选择。
- 延迟1..200ms、0.1ms精度，对数尺度抽样，一次调用；不是设备kernel内延迟。
- Copy一个进程，每次64..512MiB，16MiB步长。
- 计算一个进程，BF16方阵维度2048..6144，256步长。
- 通信一个进程管理两端设备，消息32..256MiB，16MiB步长。旧“两端各一个进程”
  不满足本轮限制。新增C++ worker复用`HcclCommInitAll`和`HcclAllReduce`，用两个线程操作
  两设备；已完成独立运行预检，但尚未验证与正式四Rank混合负载同时竞争。
- 竞争窗口固定36次业务调用，即3轮长度，可在Block/桶边界开始，结束不超出50轮。
- 参数与真值置于 `private/`，生成状态明确为 `planned_not_executed`，脚本不会启动设备或修改验签。

## 独立验收

`test.single_node_random_suite.evaluate_temporal_localization`只在诊断输出后读取独立真值。
2026-10-25更新：主指标为**分析器事先选定的主源头候选的执行区间，或其定位到的任务前空隙，
与同一个Rank上的实际注入窗口重叠**。时间命中和Rank命中必须落在同一条窗口记录上。
不看真值重新挑候选，不把长Wait边界当作已定位源头。

`diagnosis_success = rank_time_hit`，不再允许只命中时间、Rank不符仍计成功。
同时输出`temporal_hit`和`target_rank_hit`用于解释失败原因。
延迟/Copy/计算的窗口仅属于目标Rank；后台通信涉及两个实际端点，因此各保存一条窗口，
分别使用该端点已核验的profiler时钟转换。未参与的其他Rank不能仅凭同一时间命中成功。
窗口采用半开区间，只有端点相接不算重叠；零时长事件按时间点是否落入窗口判断。

这种Rank与时间重叠的成功不证明物理故障类别或因果机制正确，也不会自动区分传播误定位与
无关错判。没有支持完整的主源头输出`not_localized`；时间不符或Rank不符分别输出原因。
实际窗口必须已在相同节点的profiler纳秒时间域中核实；不能把host monotonic直接与设备时间相减，
也不能仅凭一个clock标记声称完成校准。验收函数的字段检查不验证物理时钟校准本身。
无实际注入证据或不可比时间域返回 `not_evaluable`，不计算为成功。

每例在`evaluation.json`及`result.json/temporal_evaluation`保存完整判定，队列`results.csv`
同时保存规则名、时间命中、Rank命中、联合命中及失败分类。正常组仍单独记录误报，不作异常命中统计。
既有原始诊断不自动改写。可在不重跑workload的情况下，用已捕获的窗口独立复核：

```bash
python3 test/evaluate_single_node_diagnosis.py \
  --report ATTEMPT/diagnosis/RUN_ID/rolling/report.json \
  --actual-windows ATTEMPT/private/actual-windows.json \
  --output ATTEMPT/evaluation-rank-time.json
```

输出文件必须尚不存在。旧通信竞争窗口如果仅记录控制端Rank，不能据此给另一端点补成功结论，
需先从原始后台日志和各Rank已验证的时钟信息重建两个端点窗口。

## 运行入口

- `test/run_single_node_case.py`：每例新目录、msprof采集、四Rank数值检查、调用绑定、
  严格构图、滚动诊断、独立时间窗验收；不传旧`--baseline-dir`。
- `test/anomaly_injection/single_node_control.py`：私有随机窗口控制，公开调用日志不含异常选择器。
- `test/run_single_node_suite.py`：宿主机显式运行的21例串行队列，需完整混合负载预检通过。
  使用锁拒绝重复启动，每例前检查宿主整机进程与16芯片基础显存；忙碌或失败立即停止，不自动重试。
  限定自己的非特权`zjy-new`和已核对的映射；不修改验签、设备包、驱动或共享策略。
- `test/run_single_node_offload.py`及`analyze_single_node_capture.py`：同一份真实DB/语义日志
  校验哈希后迁回本地，执行相同绑定、严格回放、滚动诊断和独立验收；不读取真值挑选根因。
  正常组原始采集保留。异常仅在HTML哈希、结构及真实浏览器检查通过并回传回执后清理大文件。
  移交完成5例既有产物。后续捕获使用用户明确授权的`--allow-other-cards-busy`；
  仍需NPU4..7整卡无外部进程和基础显存。默认不传此选项仍要求整机空闲。
- `--preflight --communication-reference-probe`仅验证纯通信的五轮参考数据通路，输出purpose
  为`communication_reference_preflight`，不能作为正式混合负载预检放行队列。

服务器源码在Node0的`/workspace/single-910c-random-20261024/src`（自有容器中）；
宿主目录`/home/commTeam/zjy/zjy-new-workspace/single-910c-random-20261024`。
21例配置在该目录`plan/private/cases/`；正常组仅作对照/误报检查，不作为异常组的比较参考。

## 本轮设备状态与障碍

2026-10-24北京时间23:00..23:06只读检查，Node0/1/2/3全16芯片均有外部NPU进程。
Node0 HBM约58.8..59.2GB，数据盘使用99%，约121GB剩余；Node1约59.8..60.2GB，
Node2约60.7..61.9GB，Node3约60.5..60.8GB。
Node0于23:18释放，后续实际使用NPU4..7的物理芯片9/11/13/15，对应容器runtime1/3/5/7。
未修改任何设备策略或包；运行在HOST模式，不扩大旧验签授权。

已通过的真实预检：每Rank8MiB FP32 AllReduce，1预热+2测量，444/444语义exact，
图无环无歧义，408/408 Wait配对；原生execution/waits/resource HTML已生成。
单进程双设备通信修订版先设置当前设备再初始化通信域，独立执行3027次，数值误差0。

2026-10-25通信参考预检也已通过：1预热+7测量、每轮1/2/4MiB三个AllReduce，公开调用
计数/数据量/四Rank一致性与设备同步边界验证通过，严格语义/构图后生成滚动HTML/JSON。
296个任务具备唯一位置及连续五轮历史，其中63个标慢，正常组产生源头候选（false_alarm=true）。
这是无注入短通信预检中的抖动/误报风险，不能当作正式混合负载准确率，也不能隐藏或调阈值后
重新宣称原规则通过。后续正式延迟4例均已完成窗口评判，但均未命中。

完整混合负载的短预检在首次BF16 GEMM处失败：CANN报561103/561108，查找MatMulV2
配置（`mat_mul_v2.json`/`mat_mul_v_2.json`）失败。正式矩阵尺寸、mm、bmm也未通过；
JIT路径报500001、GE算子管理器初始化失败。没有改用FP16、缩小正式矩阵或跳过计算来冒充成功。
后续受控对比已发现旧8192尺寸走MatMulV3可以成功，新4096尺寸触发缺配置的MatMulV2。
使用显式`--gemm-backend grouped`已保留原尺寸和BF16精度通过完整混合预检；
18944/18944语义exact、17408/17408 Wait配对。该兼容方案不等于原matmul环境已完全修复。
此前验签授权仅Node0/2 NPU7；四张物理卡的Device加载调整不得自动扩大范围。
本轮不建立自动空闲监控；完成进度见本文开头，不将部分结果报告为21例完整准确率。
