# AI_CPU 诊断链路（ai-cpu-support）

更新：2026-09-24。基线 `f7b0e89c947ef5280e42b21408965c436b236bcc`，工作区未提交。
**真实双机4 rank及16 rank的off/on数值均通过。最新16 rank为4,800/4,800 semantic exact、
1,080条跨机同步边且0未决通道；完整图仍有256个本地控制Notify缺DB元数据，
并暴露同机RDMA通道未纳入构图的缺口。100%匹配率不代表任务语义全覆盖。**

2026-09-24扩大测试使用机器0/1 NPU4–7，各物理8–15；沿用物理设备ID修正版部署。
实际选择AllReduceComm、全16 rank NHR/RoCE，RS/AG均观察到step0–3。
816个同机direct single通道在独立DB审计中有1,224对数量相等、单stream且顺序唯一的
RDMA/Wait候选；生产跨机函数跳过同机两端，本地构图器不接收rdma生产端，尚未生成这些边。
另有256个device-local single；512条RDMA门铃任务虽有DB operation/Notify事实但无算法语义。
下一步复用现有RDMA完整通道规则支持同机跨设备路径，再处理控制元数据及局部语义缺口。
详细证据与资源图见[16 rank报告](../../../test/out/ai-cpu-support-20260924-16rank/测试结果说明.md)。
两机验签已恢复False/5，其他任务保留；采集下载校验后已清理远程临时产物。

## 实现

- Host 通过 HcclOpResParam 原有 rsv[0]/rsv[1] 传递 magic `0x48545331` 和 trace 开关。
  保留结构布局，未知值关闭；这是项目配套 Host/device 的诊断扩展。
- HcclCommAicpu 在正常及重试展开入口建立 TaskSemanticDeviceScope，传递开关与
  `topoInfo_.userRank`。算法保留子通信域 commRank/rankSize；设备快照使用真实全局 userRank。
  这是双机 NHR 数据暴露的 rank 域修正，不从 device 或 rank 序号猜测映射。
- 2026-09-24两机NPU7复测暴露设备身份差异：dispatcher局部号为0/1，DB为物理14/15。
  DeviceScope同时传入`topoInfo_.devicePhyId`，SQE sidecar在捕获时保存物理身份，
  上报和缓存重放均读取快照；没有物理身份时丢弃诊断项，不修改日志/DB或放宽匹配。
- DispatcherAiCpu 在 Notify、SDMA、inline reduction、RDMA SQE 成功构造后捕获 one-shot。
  独立 sidecar 保存 TaskSemanticTraceInfo，不修改 SQE 字节、AicpuDfxInfo/SqCqeContext ABI。
  更新硬件队尾成功后读取真实 SQE header 的 stream/task ID 上报；没有额外设备任务。
- 展开缓存复制、重放、释放同步维护 sidecar；重放使用本次刷新后的 header。
  分配失败丢弃诊断项并告警，不改变通信返回值；消费端仍执行严格门禁。
- AI_CPU profiler 的 WRITE_VALUE 原先没有填充 Notify ID，DB 中显示默认 0。
  ReportTaskInfo 现从已有 dfxInfo 快照补充，包括 RDMA 门铃；只改诊断上报。
- 设备 trace/scope 代码编入完整 ccl_kernel 与 ccl_kernel_plf（含静态目标），避免两份 TLS。
- 沿用 semantic v4，`source=aicpu`、`submit_ts=0`；设备时间仍来自 DB。
  仅启用 910B/910_93 V1 SQE，未开启 310P V2。

## 消费端补齐

1. 扫描 Host `plog*.log` 及 CANN 实际生成的 `device-*.log`，保留原始文件。
2. 支持 `SDMA_SQE`、`NOTIFY_*_SQE`；只对 `source=aicpu` 使用对应类型兼容。
   `WRITE_VALUE_SQE` 必须由同一执行的 COMMUNICATION_TASK_INFO.taskType 区分
   Inter_Rank_Record 与 RDMASend；没有该字段/子类型时不猜测。原始 event_name 保留。
3. AI_CPU 跨节点 Notify 使用接收端硬件 Notify ID、DB 两端 user rank、显式 node/device
   映射和共享 operation 绑定。与 Host rank+offset 编码隔离，不跨格式拼接。
   仍要求完整 channel、等数量、两端各自唯一 stream/ordinal；跨节点时间不相减。

## 已验证

环境：两机 A3/Ascend910，driver25.5.1，CANN/HCCL/HCOMM8.5.1 基线及 A3 ops，
Python3.11.14、torch2.9.0+cpu、torch-npu2.9.0。
容器 `cann-8.5.1-910b-cyx`，镜像 `quay.io/ascend/cann:8.5.1-910b-ubuntu22.04-py3.11`。
本轮使用隔离 Host 库与完整自编译设备包，不覆盖官方安装。

- HCOMM Host hcomm/hccl_alg/hccl_plf，设备 ccl_kernel/ccl_kernel_plf/ccl_kernel_plf_a 构建通过。
- C++ 真实诊断源码加最小 SDK/日志替身回归通过：one-shot、延迟上报、缓存身份刷新、
  全局/子域 rank 区分、物理设备号快照及缓存/嵌套恢复、缺物理身份不输出、线程/关闭隔离、宽 Notify、槽位复用。
- Python 85 项回归通过；`git diff --check` 通过。
- 9月22日rank修正版机器1单机两卡：off/on 各4次8 MiB FP32 SUM AllReduce，全部数值正确，
  退出0。off语义0条，on语义104条，104/104 exact，重复/冲突0；设备内核标识证明实际加载。
- rank修正前的双机各2卡：off/on各4次，全部4 rank数值正确，off语义0条，on每节点256条。
  实际路径为机内 single-ring direct、机间 NHR/TransportDeviceIbverbs RoCE，atomicWrite[1]。
  尚存NHR userRank域错误时，node0为220/256、node1为184/256，严格门禁明确失败。
  这份旧数据未被修改或重新标为通过。
- 仅用同一次双机的原始 DB 和受控调用绑定做独立核对：144条跨节点 RDMA Notify 边、0未决。
  这是DB关系核对，不替代 semantic 或完整图验收。
- 9月24日最终物理设备号修正版：机器0/1各NPU7（物理14、15），off/on各4次8MiB、4 rank数值正确。
  两机分别256/256 exact、重复/无效匹配0，全局rank为0/1及2/3。生产流程构建144条跨机同步边、0未决通道。
  实际serverNum=2、single-ring direct + NHR/RoCE、atomicWrite[1]；未修改通信功能或强制HOST/算法配置。
  首轮设备号0/1导致0%匹配的失败数据与修复后数据分别保留，不能混用。
  完整证据、回放命令与HTML：`test/out/ai-cpu-support-20260924/测试结果说明.md`。

## 剩余验收与边界

2026-09-23补充同机8卡、两组各4卡模拟：off/on各8 rank×4次AllReduce数值正确，
所选NPU0/2/3/4验签均恢复。HCCL实际识别serverNum=1，选择AllReduceFastDoubleRingFor91093Executor/P2P；
项目设备包已加载且enabled=1，但该fast double-ring模板未有语义标注，两个逻辑节点均0条semantic，
11,817条profiler task的merge门禁失败。本次不能验证最终双机rank修正或替代RoCE/NHR验收。
证据及清理记录：`test/out/ai-cpu-support-20260923/simulated/测试结果说明.md`。

1. 最终双机语义匹配与跨机同步配对已验收；完整图仍有64个本地控制Notify缺operation_scope/notify_id，另64个single。
   双机execution 1,284节点/1,680边，resource 304节点/728边，两层无环、无缺端引用，资源boundary=0。
   未放宽门禁；自动等待诊断与异常闭环尚未验收。
2. 单机全采集 execution/resource 图无环、无缺端引用，资源图64节点204边、0资源boundary。
   但完整图门禁仍因32个缺operation/Notify DB元数据的Host控制端点失败；另32个single保持可见。
   不用时间近邻或高低位截断补边，不放宽门禁。
3. 缓存重放和16-bit任务ID回绕仅有针对性小型回归；本轮没有明确硬件缓存命中/跨回绕验收。
4. 未新增 HOST/算法强制/禁用atomic配置，未改传输功能；基线已有Ring测试强制仍属于独立待办。
   短采集含msprof，不能用其运行时间宣称生产开销达标。

## 设备配置与清理

9月22日使用用户批准的两机NPU ID0（物理0、1），当日NPU4未实际使用。
9月23日同机模拟经用户确认后使用机器0 NPU0/2/3/4，配置已逐项恢复；原始证据在上述模拟报告目录。
9月24日经用户明确批准使用两机NPU7并临时调整验签，允许机器1原有任务并发；仅限本轮，其他任务未被终止。
四轮结束及最终清理后均核对False/5；机器1原有ek-worker PID1288916、1291994仍在。此次不作性能基线。
每次必须宿主机root视角检查占用，不能依赖容器/普通用户的空进程表。
原值 enable=False、mode=5；测试时临时True/0，finally恢复并复核。两机均已恢复。
机器0的nsenter进程仍被驱动视为容器，因此经宿主机临时systemd任务运行已授权的配置包装脚本；
设备负载始终在指定容器内。临时任务与管理容器自动回收，不新增常驻服务。

原始DB、plog、命令、结果、配置恢复、各版本源码清单和部署包均下载到
`test/out/ai-cpu-support-20260922/`；详见该目录 `测试结果说明.md`。
两机采集目录、传输归档、临时单测输出及过期收集脚本已删除。
9月24日新增证据在`test/out/ai-cpu-support-20260924/evidence-final/`；本轮测试、传输、单测临时目录和脚本已清理。
为后续诊断缺口调查保留隔离源码/构建、deploy/toolkit、必要通用脚本及日志，
准确目录已更新上级 `远程服务器新增文件.txt`；没有修改既有官方环境或他人任务。
