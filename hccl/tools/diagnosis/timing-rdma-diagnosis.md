# 耗时分类、同机 RDMA 与等待视图

2026-09-24，分支 `codex/diagnosis-timing-rdma`，从 `ai-cpu-support` 的
`f7b0e89c947ef5280e42b21408965c436b236bcc` 建立，并保留此前未提交的 AI_CPU 实现。
本轮仅修改 HCCL Python 消费端、回归测试和文档，没有新增 HCOMM/通信功能修改。

## 实现合同

1. `SDMA_SQE` 结合同一 execution 的 `COMMUNICATION_TASK_INFO.taskType`
   区分 `Memcpy` 与 `Reduce_Inline`；原始硬件名仍保留。
   `size` 导出为 `profiler_size_bytes`，未知为 -1，merged 共 43 列。
   HTML 显示 Copy / Inline reduce / RDMA submit 及字节数。4 字节本身不能证明
   是控制计数器，因此缺少算法语义的 reduce 保留用途未知，不冒充业务数据归约。
2. 同机跨设备 RDMA 复用跨机完整通道规则：显式 operation 绑定、rank/node/device
   映射、接收端 Notify 资源、每端单一物理 stream、等数量与唯一局部执行顺序。
   必须存在真正的 RDMA Notify producer；payload sentinel 不参与，普通 SDMA Notify
   仍由原构图处理。新 execution kind 为 `same_node_rdma_notify_sync_observed`。
   resource 收缩保留最弱证据；门铃完成不等于数据到达，不计算 remote/post 分解，
   使用 `same_node_rdma_completion_unmeasured`，只保留本地 `wait_span_ns`。
3. 回放另存 `operation_timings.csv`，保留 DB `COMMUNICATION_OP` 整数纳秒区间。
   无时间列时不推算；重复身份和非法区间拒绝。operation 是独立显示泳道，
   不改变 execution/resource 任务和依赖。`--view waits` 消费 execution artifact，
   导出全部 Wait（包括未配对项），按本地时长排序，沿实际边跳转上游/对端。

graph artifact 升级为 **v5**。稳定 ID 包含版本，新旧节点/边必须成套使用；
旧采集从原始输入回放生成 v5。semantic 仍为 v4。跨节点时间不相减；
仅在单节点内先做精确十进制时间差，再转换为 HTML 显示坐标。

## 验证

本轮使用已下载的真实 DB/plog 离线回放，没有新建远程测试或改动设备验签配置。
94 项单测通过，覆盖类型兼容、精确时间、operation 显示、同机通道失败模式、
时移/乱序、最弱证据与未配对 Wait。浏览器验证等待排序、同机/跨机跳转、
operation 详情/筛选、4 字节 Inline reduce 和窄窗口显示。

| 指标 | 两机 4 rank | 两机 16 rank |
|---|---:|---:|
| semantic exact | 512/512 | 4,800/4,800 |
| execution 任务 | 1,284 | 6,480 |
| 跨机同步边 | 144 | 1,080 |
| 新增同机 RDMA 同步边 | 0 | 1,224 |
| RDMA 未决通道（同机/跨机） | 0/0 | 0/0 |
| operation 区间 | 16 | 64 |
| 本地控制 incomplete / single | 64/64 | 256/256 |

16 rank 原 7,432 条边全部保留，新加 1,224 条同机 RDMA 边；仅 128 条旧 SDMA
记录改为 Inline reduce，所有原有时间、identity 和匹配字段不变。Copy 为 192 条。
等待视图 2,560 项，其中 2,304 paired、256 unresolved；最长 Wait 23.051518 ms，
最长已配对 Wait 15.935940 ms。它们是等待时间，不能直接解释为网络传输时间。

**完整图门禁仍失败**：4 rank 的 64 个、16 rank 的 256 个本地控制 Notify 缺元数据。
没有放宽门禁。两组图无环、无重复 ID、无缺失边端点。512 条无算法语义的 RDMA
门铃、控制 Notify 元数据、自动根因分类和异常注入验证留待后续；未修复既有
FFTS/mixed resource 顺序证据增强问题。

完整日志、HTML、CSV及复现命令见
[本地测试结果说明](../../../test/out/diagnosis-timing-rdma-20260924/测试结果说明.md)。
输出为本机测试产物，不作为受版本控制的原始采集交付。

## 后续单机8卡新采集

2026-09-24按用户要求，在机器0物理0–7新采集HOST Ring，4次64 MiB AllReduce，
2,336/2,336 exact，960条Notify同步边，语义及图门禁均通过。
HTML显示384个Copy、224个Inline reduce（每个8 MiB）、960个Wait和32个operation。
HOST中DB以MEMCPY_ASYNC表达的归约，只有精确匹配的reduce_inline语义才改变显示分类；
DB硬件类型和artifact保持不变。新增对应回归，95项单测通过。
首轮物理8–15暴露HOST逻辑/物理设备号不一致，作为未修复问题单独保留。
新采集的环境、范围、失败证据与清理见
[单机8卡结果](../../../test/out/single8-diagnosis-20260924/测试结果说明.md)。
