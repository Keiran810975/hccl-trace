# AGENTS.md — HCCL Trace 项目 Agent 指南

## 1. 目标与当前阶段

在配套 HCCL/HCOMM 8.5 基线上实现**依赖关系感知的离线诊断**：把真实通信任务与
phase/step/rank 语义关联，沿依赖解释等待与慢任务，并用异常样例验证定位结果。

本地旧主线已完成 **8 卡 single-ring concurrent-direct AllReduce RS/AG** 的数据验证、
精确合并、execution/resource 两层图和交互视图。远端另有 standard Ring、Mesh、NHR、
RHD 实现，Ring/NHR 已有设备问题定位记录；后续必须结合各分支及最终提交的验证状态，
不能把旧本地覆盖当作项目全部进展。多机依赖、自动等待诊断和异常闭环仍待推进。
用户已确认 NHR/Mesh/standard Ring 经过测试，并更正 RHD 尚未测试。上级目录留有
NHR/Mesh/Ring HTML；可复核内容和
未留存的版本信息分别记录，不因原始 DB 暂缺就撤销已有测试结论或要求重跑全矩阵。

优先阅读：

1. [task.md](hccl/tools/diagnosis/task.md)：唯一活动计划与完成条件。
2. [spec.md](hccl/tools/diagnosis/spec.md)：实现合同及已知限制。
3. [阶段归档](hccl/tools/diagnosis/arch-94a1ab31c3ee.md)：分支、提交、验证证据和历史入口。
4. [诊断 README](hccl/tools/diagnosis/README.md)、[依赖关系说明](文档/依赖关系的定义与构建.md)：工具用法与构图规则。
5. [分支调查与待批合入清单](hccl/tools/diagnosis/branch-review-2026-09-15.md)：远端实现、验证边界及合并建议。

`arch-*.md`、`archive/` 和早期迁移方案是历史材料，其中的任务、边类型、统计和设计建议
不自动成为当前要求。完成记录归档，活动计划只保留下一步。

## 2. 工作空间与 Git

| 目录 | 职责 |
|---|---|
| `hcomm/` | 传统集合通信算法、平台与 trace 生产端；主要 C++ 修改位置 |
| `hccl/` | 新算子架构与 `tools/diagnosis/` Python 消费端 |
| `test/` | 采集、回放、开销脚本；`test/out/` 保存本地原始数据与生成物 |
| `文档/` | 当前依赖关系说明 |
| `../cann-hccl/` | 旧版原型，只读参考，除非用户明确要求不得修改 |

根目录、`hccl/`、`hcomm/` **各有独立 Git 元数据**，且根仓库直接跟踪两目录源码。
2026-09-15 核对时，根仓为 `master@94a1ab3`、工作树干净；子仓均为 `dev-innerDia`，
HCCL HEAD 为 `4600cb6`、HCOMM HEAD 为 `7db54477`，后续实现相对子仓 HEAD 为未提交修改。
这是整理开始时的本地记录。随后 fetch 确认远端 `master@d0d2904` 领先 7 个提交，另有
`feat-standard-ring`、`feat-mesh`、`feat-NHR`、`feat-RHD`；源码尚未合并。

- 修改前检查三个仓的分支、状态和相关 diff，保留已有改动；根仓干净不代表子仓干净。
- 调查进展时同时检查远端 heads/跟踪引用及相关分支记录，不仅检查当前 checkout。
  区分“当前主线已集成”“分支已实现”“指定提交已验证”；先列合入对象，用户批准后再合并。
- 提交/交付说明区分 HCOMM 生产端、HCCL 消费端和工作空间文档；不要把子仓 HEAD
  当作全部当前实现。设备复现记录工作区提交及必要的子仓差异。
- 不自动切分支、重置、清理或提交已有工作。不得在 `hcomm/` 下生成 `AGENTS.md` 或 `claude.md`。
- `deploy/`、构建产物和原始采集数据不作为源码编辑对象。

## 3. 当前数据流与入口

```text
HCOMM scope -> TaskData 语义快照 -> semantic plog + graph correlation
                                                       |
msprof consolidated DB --------------------------------+-> merged.csv
                                                           -> execution graph
                                                           -> resource graph
                                                           -> CSV / HTML / SVG
```

| 位置 | 职责 |
|---|---|
| `hcomm/src/common/debug/profiling/` | 语义开关、捕获、上报及 FFts graph correlation |
| `hcomm/src/algorithm/base/alg_template/component/` | RAII scope、Sender/Reducer 事件 |
| `hcomm/src/algorithm/base/alg_template/temp_reduce_scatter/`、`temp_all_gather/` | 当前 concurrent-direct RS/AG 插桩 |
| `hccl/tools/diagnosis/schema.py`、`parse_plog.py`、`parse_msprof_db.py` | 数据模型及事实源解析 |
| `hccl/tools/diagnosis/merge_timeline.py`、`validate_trace.py` | 精确关联、语义质量检查 |
| `hccl/tools/diagnosis/dependency_model.py`、`visualize_dependency_graph.py` | 稳定身份、execution graph 与双层 artifact 导出 |
| `hccl/tools/diagnosis/resource_dependency_graph.py` | 控制链收缩、等待指标 |
| `hccl/tools/diagnosis/validate_dependency_graph.py`、`visualize_html.py` | 图门禁、artifact 驱动视图 |

## 4. 必须保持的合同

### 输入与身份

- 唯一生产 profiler 输入是 consolidated `msprof_*.db`，当前支持 DB schema `1.2.0`，
  SQLite 只读打开。JSON、`task_time.csv` 和旧 marker 路径已退出生产链。
- semantic 生产 schema 为 v4，消费兼容 v2/v3/v4；拒绝 v1、无版本和旧 token 格式。
  graph correlation 独立使用 v1；merged CSV 当前 42 列，graph artifact 当前 v4。
- `device_id` 来自生产端 `deviceLogicId_` / DB 物理设备字段，绝不从 rank 推断。
  `user_rank`、`comm_rank`、`peer_rank`、node/device 分别处理。
- direct 按 `(node_id, device_id, stream_id, task_id)` 和兼容 task kind 精确匹配。
  FFts 先用 `(node, device, pid, graph_instance_id)` 找 parent，再用 parent stream/task
  与 `ffts_ctx_id` 匹配 DB context。禁止 task-id 偏移、本地序号或时间最近补配。
- execution identity 为 `(node, device, physical stream, task, subtask, connection)`。
  operation 使用同一次采集内 DB `(group_name, op_name)` 生成的 scope；本地 `opId`、
  进程内 graph 序号不能冒充跨节点/跨采集的全局身份。
- DB 时间内部保持整数纳秒；CSV 使用精确十进制微秒，Notify 宽整数 ID 不经 `float`。
  `submit_ts` 是 Host-cycle 提交时间，不能计算设备 task duration。

### 生产与依赖

- `TaskSemanticEventScope` 设置 one-shot；首个成功构造的 `TaskData` 捕获并消费 TLS，
  `Run()` 读取任务快照，scope 析构恢复父上下文。不要恢复上报时读取当前 TLS 的旧行为。
- trace 默认关闭，`HCCL_STEP_TRACE=1` 开启，兼容 `HCCL_TASK_SEMANTIC_TRACE=1`；
  不新增用于打点的设备任务，不恢复 `aclprofMarkEx`。
- direct stream 顺序为 `observed`；FFts 同 logical stream 的 context 声明序为
  `semantic`，不能当作完整硬件 DAG。
- direct 跨 rank 和 device-local Notify 在完整 channel 内按两端各自本地 stream
  ordinal 配对为 `exact`；须单 stream、等数量、顺序唯一。FFts 完整 relation 的唯一
  配对为 `observed`。仅 `notify_id` 相同不足以建同步边。
- 不恢复 connection/time、邻居/上一 step 或已删除的 payload semantic 因果边。
  缺证据保留 single、ambiguity 或 boundary；不伪造端点。
- resource graph 从 execution artifact 派生，视图不重新构边。派生边应取路径最弱证据；
  **当前 FFts/mixed resource order 错标 observed 仍待修复**，不能沿用为新功能合同。
- `wait_span_ns` 是本地 wait duration；remote/post 分解是观测值，不是硬件内部精确延迟。
  无校准时可报告跨节点拓扑与本地时长，不做跨节点绝对时间相减或全局关键路径累计。

## 5. 开发方式与验证

- 一个改动解决一个具体问题，复用现有 parser、CSV 和图模型；分析层只消费 artifact。
  先跑通一个实际多机路径，再按样例扩展算法与 transport。
- 仅在真实数据证明现有字段不足时增加 schema、协议字段或抽象；不预建通用框架、
  重复 operation 状态、全量覆盖矩阵或多套相同统计。
- Python 仅用标准库，保留 `from __future__ import annotations`、模块/脚本双入口和
  现有 frozen dataclass 风格。CSV 用 DictReader/DictWriter，写 UTF-8、读兼容 BOM。
- C++ 延续 C++14、版权头、`CHK_RET` 和现有 CMake 目标组织。HCOMM 修改在自身构建验证，
  不以 HCCL 构建代替；注意 host/device 多目标。
- 测试围绕改动及真实失败模式：小 fixture 验证规则，代表性设备样例验证路径。纯文档修改
  检查事实、链接与 diff 即可；不要求每次重复跑全算法、构建、性能矩阵。
- 旧本地仍有两处 Ring `[TEST PATCH]` 和 `Run()` 提前返回窗口；远端 master 已通过
  `ReportCapturedTaskSemantic()` 修复后者，待同步与针对性回归，禁止重复开发。FFTS
  callback 的正式采集仍需 msprof addition-info 订阅，不能混淆两种门控。

从工作空间根目录运行：

```bash
python -m unittest hccl.tools.diagnosis.test_diagnosis

# 对已有数据回放；新采集的命令接在 -- 后
bash test/run_step_trace_function_test.sh \
  --plog-dir test/out/plog --msprof-db-dir test/out/function/msprof \
  --out-dir test/out/replay --node-id node0 --min-match-rate 95

python -m hccl.tools.diagnosis.validate_trace test/out/function/merged.csv --min-match-rate 95
python -m hccl.tools.diagnosis.validate_dependency_graph test/out/function/dep_graph --max-boundary-nodes 8
```

最后一行的 8 是当前样例已解释的 boundary 数，不是所有数据集的通用阈值。
功能测试入口见 [test/README.md](test/README.md)。Linux/CANN 下进入相应目录运行
`bash build.sh --pkg`；Windows 离线检查不能算设备构建或新采集验收。

Windows 优先用 `rg`；写文本用 UTF-8 无 BOM。`apply_patch` 失败可用小型 PowerShell
替换。Python 启动失败应如实报告；Git LF/CRLF 提示与实际空白错误分开处理。
