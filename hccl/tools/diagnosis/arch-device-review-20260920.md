# 2026-09-20 集成设备结果复核

被测主线：`10cda209dd869b6f780435305f5cad9819d2b0a4`。设备测试日期：2026-09-15。
输入由用户提供于 `E:/integrated-master-20260915`；原始报告为该目录的 `RESULTS.md`。
本次只读报告、小型汇总、必要 CSV 聚合、一个 DB 的三条目标 TASK 和对应 plog，未全量回放。
未修改测试目录、设备代码或合入 selector 测试补丁。

## 可接受的结论

| 用例 | 范围 | exact | 结论 |
|---|---|---:|---|
| standard-ring-valid | 原样 master，3 rank，物理设备 4/5/6 | 966/966 | 单机回归通过 |
| nhr-normal-valid | 原样 master，3 rank，普通 NHR | 966/966 | 单机回归通过，不含 Oneshot/多机 |
| mesh-normal-selector-patch-v2-8rank-trace-on | 8 rank，隔离 selector/template 补丁 | 8064/8064 | normal AllGather 模板验证通过 |
| 原样 master 的 Mesh 请求 | 3/8 rank 实际进入 concurrent-direct Ring | 非目标 | normal Mesh 默认选路未覆盖 |

设备为 910B3、CANN 8.5.1，fp32、每 rank 256 MiB、warmup 2 + 实测 5。HCOMM 原样及补丁
构建的最终退出文件均为 0；三个有效 trace-on 的 workload/replay 均退出 0，重复键和
invalid match 为 0。Mesh v2 是 **atomic ReduceScatter + normal AllGather**，不是全部 normal Mesh。

Mesh normal allgather 的五类 ack/signal/copy 事件各 784 条，全部 exact；record/wait/copy
分别匹配 notify_record/notify_wait/sdma。本次抽核 device 0、peer 7、graph instance 1：
`plog-140722_20260915131749742.log:1219/1220/1221` 对应 context 42/43/44，
DB `PROF_000001_20260915131756455_KMFAOCQALEBOEBLB/msprof_20260915131838.db`
的 TASK rowid 71/78/81，stream 45、task 1、connection 1781。三条身份与时间均吻合。

Mesh 图门禁通过，resource boundary 为 672；Ring/NHR boundary 为 0。
operation 内未标语义 SDMA 分别为 Ring 84、NHR 84、Mesh 336；各另有 3/3/8 条无 scope SDMA。
因此 **100% semantic exact 不等于全部物理任务已标语义**，这些余项继续保留。

## 对照与统计口径

Mesh trace-off 无语义；on/off 的物理 task-kind 数量相同。原始 DB 各有 11,976 条
（每设备 1,497）；解析器排除 AI_CORE 112 条后，merged/execution 各为 11,864 条
（每设备 1,483）。原报告把两种口径连写，应按此区分。

时间排序序列不同，现有数据只支持“路径和任务数量一致”，不证明严格顺序等价。
外部任务并行不足以单独解释所有差异；FFTS context 也不能仅按物理 stream 推断执行顺序。
不作性能结论，不因此判为 Mesh 功能失败。

首轮逻辑 device 0–2 与 DB 物理 device 4–6 不一致，exact 为 0；显式物理绑定重采后通过。
当前可接受结论依赖本次明确的设备绑定，不能外推为可见设备重映射已自动支持。

## 交接完整性

已核对以下 SHA-256 与报告一致，归档无需展开：

- `archives/raw-plog-db-prof.tar.gz`：`9022274d2c9455bc95d09764124a06395333172977f4f81225520dc8e989a7ce`
- `archives/derived-csv-and-logs.tar.gz`：`e59172028eec002a1ae921cea3737d4f75b0880ad1ec04898f6e0daa2207b263`
- `deploy-selector-mesh/lib64/libhccl_alg.so`：`28c43ad660bd074f1ea19f8a0073bc01378725d89fcf3e595893d0b2319b3005`
- `selector-test.patch`：`4bb8dc0d02c25304eddbe4ac1031119136e53e57e9ca4bc0aafccc30e003f24b`

加载映射指向隔离部署库；8 个 rank 留有 addition-info 订阅成功记录。补丁只涉及
alg_configurator、all_reduce_operator、coll_all_reduce_mesh_executor 的选路。

两个记录缺口需测试者补交现有材料，**无需重跑设备测试**：

1. `logs/source-state.log` 的 BUILD_SOURCE 三项 `ancestor_rc=128` 与报告“均成功”不一致，
   补最终构建源码的 HEAD/status/diff 和成功祖先检查输出。
2. 收到的 source 副本中 `all_gather_mesh.cc`、`transport_p2p.cc` 为 0 字节，无法用副本确认
   构建源码；补这两份文件或最终源码清单。task_semantic_scope.cc、task_profiling.cc 与主线一致。

这些是复现材料缺口；已复核的设备行为及原始数据仍成立，不宣称源码来源已完整独立核验。

## 后续

继续 NEXT-001：撤回生产 Ring 强制，按真实 selector 验证默认路径；不要合入本次强制
normal 模板的测试补丁。NEXT-002 修正公共 resource 证据传播，随后按原计划推进一个双机
样例及依赖诊断。已有通过样例保留作为回归输入，不重复全算法矩阵。
