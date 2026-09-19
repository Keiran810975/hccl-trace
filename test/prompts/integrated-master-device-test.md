# 给 gpt-5.6-sol 的设备测试 prompt

2026-09-20 补充：Ring 强制补丁撤回已合入 master。fetch 并固定 `origin/master` 的完整 SHA，
确认包含 `174381950305f0d8bcd975ae8136f41ca0269ac8`。
本轮只需构建后跑一组无 selector 补丁的默认 AllReduce trace-on/off，沿用下文的采集、
匹配及结果交付要求；已有 Ring/NHR 和有补丁的 Mesh 模板结果不要求全部重跑。

你负责在已有 Linux/CANN/昇腾环境中验证 hccl-trace 当前 master，并把可复核结果返回给负责
集成的 Codex。请直接执行以下工作。目标是验证本轮集成，重点确认 Mesh normal 的语义修复；
先做小而完整的测试，不扩展到多机、异常注入、性能矩阵或新算法开发。RHD 已弃用，不测试。

## 1. 锁定代码、环境和加载产物

仓库：`https://gitee.com/tjucyx/hccl-trace.git`，目标分支 `master`。
读取根目录 AGENTS.md、hccl/AGENTS.md、hccl/tools/diagnosis/task.md、spec.md，以及
`文档/Mesh语义修复说明.md`。旧 arch/覆盖矩阵只作历史依据，当前源码和最新计划优先。

- fetch 后在干净的独立测试工作树固定 `origin/master` 的完整 SHA，保存 git status。
  必须包含集成基线 `f30a90a978a6324a880f8c39658b456cdb00388e`，以及 Mesh 修复
  `286ef995b9cbb5e61a2dfa669c70b5ac265c1048`。若远端还有更新，列出新增差异再测试。
- 根仓直接跟踪 hcomm/hccl 源码；本地存在子仓 Git 元数据时也记录 HEAD 和 diff，不能只凭
  子仓旧 HEAD 声称测试了当前实现。保留现场已有改动，独立测试，不 reset/clean 他人工作。
- 记录主机、设备型号/数量、rank↔device 映射、系统架构、driver/firmware、Toolkit、msprof、
  Python 版本，workload 程序/版本、dtype、count/字节数、rank 数、warmup/实测迭代数。
- 在 hcomm 内运行 `bash build.sh --pkg`，保存完整日志与退出码。按现场配套要求构建或安装
  HCCL；若复用已有 HCCL，写明版本与兼容依据。仅构建 hccl 不算验证 HCOMM。
- 记录部署路径、产物 SHA-256，并用运行进程的加载映射或等价动态加载证据确认实际使用
  的 HCOMM/HCCL 库路径。只设置 LD_LIBRARY_PATH 或只看到构建成功，不足以证明加载正确。

## 2. 最小测试范围与选路证据

优先使用现有稳定 AllReduce workload，单机 8 卡（条件不支持则说明实际规模及覆盖限制），
固定一种普通消息大小，少量重复 operation。每个 case 使用独立的新输出目录，不混入旧日志。

| case | 实际必须进入的路径 | 本次目的 |
|---|---|---|
| mesh-normal-inline | `AllGatherMesh::RunAllGather` 的 normal Tx/Rx，inline P2P；`algorithm=mesh` | 必测，验证修复 |
| standard-ring | `ReduceScatterRing` / `AllGatherRing`；`algorithm=ring` | 一次集成小回归 |
| nhr-normal | 普通 NHR RS/AG；`algorithm=nhr` | 一次集成小回归 |

从 executor/template 选择日志确认路径，再结合目标语义、transport 类型和实际 linkAttribute
核对。不能从 HCCL_ALGO、目录名或 executor 名中的 Mesh 推断：`mesh_atomic`、`mesh_direct`
都不经过本次 normal Tx/Rx 修复；concurrent-direct Ring 也不能替代 standard Ring。
普通 NHR 和 nhr_oneshot 分开记录，本轮不要求补齐 Oneshot。

master 中的 `1743819` 已撤回 `alg_configurator.cc` 和 `all_reduce_operator.cc` 的
Ring `[TEST PATCH]`；验证时固定 master 完整 SHA，先完成一组无 selector 补丁的默认
AllReduce trace-on/off，用实际选出的 Mesh Atomic/Direct 等路径验收默认行为，不要求进入 normal Mesh。
先尝试已有配置/真实选择条件；若无法进入目标路径，可在独立测试工作树做最小 selector
测试补丁，完整保存 diff、编译日志和加载库哈希，禁止顺便改插桩、公共 scope 或配对规则。
结果必须标注“有测试补丁的模板验证”，不能写成“原样 master 默认选路已通过”。若无法
安全到达 normal inline P2P，明确返回“未覆盖”及选择日志，不拿 Direct 成功替代。

## 3. 正确采集

- 每个 case 用同一次运行的所有 rank plog 和 consolidated `msprof_*.db`；保存原始 PROF
  目录、导出命令及原始日志。唯一生产 profiler 输入是 DB，不改用 JSON/task_time.csv。
- trace-on 设置 `HCCL_STEP_TRACE=1`、`HCCL_TASK_SEMANTIC_TRACE=1`，通过现场版本支持的
  msprof 命令采集。先确认 `msprof --help` 和既有成功命令，再写出实际完整命令。
- FFTS 路径检查 addition-info 订阅成功证据，例如 `MsprofCtrlCallback called, type: 0`、
  `StartAddtionInfoSubscribe:[0]`、`DrvFftsProfileStart`。其中 `[0]` 是成功码。日志级别
  不足时补充可等价证明订阅成功的证据；未确认订阅，不能把 0 语义直接归因于算法。
- Mesh normal 另跑一次同命令、同 msprof 配置的 trace-off 对照，两个 trace 变量均设为 0，
  保存独立目录。检查算子数值正确、实际路径一致、无新增 semantic/correlation 日志；
  对比相同有效 operation 的物理 copy/notify 数和顺序，避免把 warmup/不同 operation 数
  算作新增任务。不做正式性能基准。不要用功能 wrapper 执行 trace-off，它会强制开启 trace。

## 4. 回放与针对性验收

在仓库根目录回放 trace-on 原始输入。把以下占位符替换为本次真实路径；保留命令和退出码：

```bash
bash test/run_step_trace_function_test.sh \
  --out-dir <case-dir>/diagnosis \
  --plog-dir <this-run-plog-dir> \
  --msprof-db-dir <this-run-prof-dir> \
  --node-id node0 --min-match-rate 95
```

脚本遇到失败会提前退出。保留失败日志和已生成产物；需要时单独执行后续 validate/渲染，
但不能把分步成功覆盖原失败。不要放宽阈值、删除难匹配行或使用时间最近/偏移补配。

通用验收：算子数值正确、目标算法/phase 非空、semantic exact 匹配率至少 95%、重复键为 0，
目标 kind mismatch 为 0。保存 merge/validate 与 execution/resource 图门禁全部指标。
另按 `profiler_op_scope + algorithm + phase + event + task_kind + profiler_task_kind + match_status`
统计 CSV，分别给出目标语义覆盖和 operation 内未标语义 SDMA；总体匹配率不能代替覆盖率。
无 operation scope 的行单列；未标语义不能被可靠分到算法时保留为 scope 级统计，不猜算法。

Mesh normal 必须在真实任务层确认（不限于 resource HTML）：

- `rx_data_signal_start/link_rx_data_signal` 对应 Notify wait。
- `rx_payload_copy_start/link_rx_payload_copy` 对应实际 SDMA，不能落到 wait。
- `tx_data_signal_start/link_tx_data_signal` 对应 Notify record；只有 transport 实际提交
  发送 copy 时才出现 tx payload，不能把 record 当 payload。
- `algorithm=mesh` 的 step 为 0，phase/rank/peer/slice 和实际目标一致；FFTS 用 parent/context
  关联真实 DB task。至少各选一条 wait、copy、record 返回 plog→merged→DB 的完整证据链。
- 按实际 linkAttribute 解释由发送端 push 还是接收端 pull；不要求同一传输同时有 Tx/Rx
  两份 SDMA。无 copy 的方向缺 payload 是正常行为，真实 copy 无语义才需要追查。

Ring/NHR 检查实际 RS/AG step/peer 及 executor 的 `user_to_ccl_copy`/`ccl_to_user_copy`。
不要套用旧报告 336 graph、1,344 copy 等计数；以本次规模、有效 operation 和路径推导。
普通 NHR 单机通过不代表多机 rank 域或跨节点依赖已验收。

图的 boundary 数按本样例解释，不套用旧 direct 样例阈值 8。已知 resource FFts/mixed
confidence 传播问题单独列为公共分析层待办，不冒充 Mesh 新失败，也不修改门禁掩盖问题。

## 5. 返回结果（必须可回放）

创建 `test/out/<run-id>/RESULTS.md`，将报告全文返回给集成 Codex，并给出归档下载位置或
双方可访问路径。仅报测试机器的本地绝对路径不算完成交接；若暂时不能传输，明确列为待交付。
不只返回截图或 HTML。原始 plog/DB/PROF 和派生 CSV 可压缩，附文件清单、大小和 SHA-256；
大文件不提交 Git。保留数据直到结果复核完成。报告按以下格式：

```text
源码：根仓完整 SHA；子仓 HEAD/status（如存在）；额外测试 diff 的路径/哈希
环境：设备/拓扑/rank映射；Toolkit/driver/firmware/msprof；Python；workload版本
构建部署：命令、日志、退出码；实际加载库绝对路径与 SHA-256；加载证据

case | 实际executor/template/transport | 补丁情况 | 数值结果 | semantic总数/exact率 |
       duplicate/kind mismatch | operation内未标SDMA | 图门禁/boundary | 结论
结论分别标为：通过 / 失败 / 环境无效 / 路径未覆盖；不要把未覆盖算通过。

Mesh定向证据：wait/copy/record各一例，含plog文件行号、merged行号、DB文件/TASK行定位；
node/device/rank/peer、scope、物理stream/task/subtask、graph/context、事件及task kind。
trace-off对照：变量、命令、路径、数值、语义条数、归一化任务数/顺序比较。
局限与失败：第一处失败、相关日志、已验证事实、推测分开；最小复现命令。
产物：RESULTS.md、命令/环境/构建/选路/加载日志、原始plog/DB/PROF、merged/summary、
validate日志、dep_graph* CSV、dependency HTML、统计CSV、清单及压缩包位置/SHA-256。
建议：当前可接受的覆盖、尚未覆盖的路径、需要集成端处理的具体问题。
```

发现问题先保留失败样例、完成不受影响的 case。无需反复跑全矩阵，也不要擅自修复产品代码、
更改全局安装环境或推送提交。最终报告应让我能准确复现，并区分代码缺陷、加载错误、订阅失败
和没有进入目标模板。
