# AGENTS.md — HCCL Trace 项目 Agent 指南

## 项目概述

`hccl-trace` 是一个多仓库工作空间，围绕**华为集合通信库 (HCCL)** 的**步骤级语义追踪与离线诊断**能力构建。核心目标：从 C++ 运行时插桩产生 `[HcclTaskSemantic]` 日志，到 Python 离线工具完成解析、合并、校验与可视化，形成端到端的通信问题诊断流水线。

### 仓库组成

| 目录 | 角色 | 语言 | 说明 |
|------|------|------|------|
| `hcomm/` | **主要编辑仓库** — 通信基础库 | C++ | 包含 profiler 插桩、算法层、平台层、HCCP 协议栈。语义 trace 的生产端在此。 |
| `hccl/` | **主要编辑仓库** — 算子库 + 诊断工具 | C++ / Python | HCCL 算子实现和 `tools/diagnosis/` 下的 Python 离线诊断工具链。 |
| `../cann-hccl/` | **只读参考** — 旧版原型 | C++ / Python | 旧版 step-trace 诊断与 SVG 可视化脚本。仅供查阅，**不要修改**。 |
| `test/` | 测试脚本与数据 | Bash / Python | 功能测试入口、开销测试 wrapper、测试 plog 与预期输出。 |
| `deploy/` | 部署产物 | 二进制 | 编译后的 `.so` 部署包，不参与编辑。 |
| `审查报告/` | 提交审查文档 | Markdown | 6 份 commit review 报告，记录设计决策与已知问题。 |

### 工作空间规则

- `hcomm/` 和 `hccl/` 是本工作空间的可编辑仓库。
- `../cann-hccl/` 是只读参考，除非用户明确要求，否则不要修改。
- 跨仓库任务时，明确说明每个变更属于哪个仓库。
- **不要在 `hcomm/` 下生成 `claude.md` 或 `AGENTS.md`**（已在 `.gitignore` 中忽略）。

---

## 架构总览

### HCOMM 三层架构（C++ 生产端）

```
┌─────────────────────────────────────────────────────────┐
│  framework/  — 通信框架层（控制面）                       │
│  编排通信生命周期：hcclComm → HcclCommunicator → HcclAlg │
│  管理 communicator、心跳、异常检测、算子重试、NSLBDP      │
├─────────────────────────────────────────────────────────┤
│  algorithm/  — 通信算法层（数据面核心）                    │
│  算法选择 (SelectAlg) → 资源计算 (CalcResRequest)         │
│  → 算子编排 (Orchestrate)                                │
│  包含 ring/mesh/hierarchical 等算法模板                   │
├─────────────────────────────────────────────────────────┤
│  platform/   — 通信平台层（硬件抽象）                      │
│  DispatcherPub 下发 Memcpy/Reduce/RDMA/Signal 等原语     │
│  HCCP 协议栈、RDMA、Transport、资源管理                   │
└─────────────────────────────────────────────────────────┘
```

### 语义 Trace 数据流

```
[生产端 C++]                              [消费端 Python]
                                            
TaskProfiling::Run()                      parse_plog.py ──→ semantic CSV
  └─ ReportTaskSemanticTrace()               │
       └─ plog [HcclTaskSemantic] ──────────→┤
                                              ├─→ merge_timeline.py ──→ merged CSV
msprof task_time.csv ────────────────────────→┘         │
                                                        ├─→ validate_trace.py (质量门禁)
                                                        ├─→ visualize_timeline.py (SVG)
                                                        └─→ visualize_dependency_graph.py (SVG)
```

### 关键 C++ 文件（trace 生产端）

| 文件 | 角色 |
|------|------|
| `hcomm/src/common/debug/profiling/inc/task_semantic_trace.h` | `TaskSemanticTraceInfo` 结构体 + 上报 API 声明 |
| `hcomm/src/common/debug/profiling/task_semantic_trace.cc` | plog `[HcclTaskSemantic]` 格式化输出 |
| `hcomm/src/common/debug/profiling/task_profiling.cc` | `TaskProfiling::Run()` — 从 `deviceLogicId_` 传入真实 `device_id` |
| `hcomm/src/algorithm/base/alg_template/component/task_semantic_scope.cc` | `TaskSemanticEventScope` — RAII 作用域，设置 `oneShot = true` |

### 关键 Python 文件（trace 消费端）

所有诊断工具位于 `hccl/tools/diagnosis/`，**仅使用 Python 标准库，不引入外部依赖**：

| 文件 | CLI 入口 | 职责 |
|------|----------|------|
| `schema.py` | — | 共享数据模型：`SemanticRecord`、`ProfilerTask`、`MERGED_FIELDS`、`merge_key` |
| `parse_plog.py` | `python -m tools.diagnosis.parse_plog` | 解析 plog 中的 `[HcclTaskSemantic]` 行 |
| `parse_msprof.py` | `python -m tools.diagnosis.parse_msprof` | 解析 msprof `task_time.csv` |
| `merge_timeline.py` | `python -m tools.diagnosis.merge_timeline` | 按 `(node_id, device_id, stream_id, task_id)` 合并语义与 profiler 数据 |
| `validate_trace.py` | `python -m tools.diagnosis.validate_trace` | 校验匹配合并率 ≥ 阈值，检测 duplicate key |
| `visualize_timeline.py` | `python -m tools.diagnosis.visualize_timeline` | 渲染 SVG 时间线（默认逻辑布局，支持 `--layout time`） |
| `visualize_dependency_graph.py` | `python -m tools.diagnosis.visualize_dependency_graph` | 渲染 SVG 依赖图（ack/signal/payload 边） |
| `visualize_html.py` | `python -m tools.diagnosis.visualize_html` | 渲染交互式 HTML canvas 页面 |
| `test_diagnosis.py` | `python -m unittest hccl.tools.diagnosis.test_diagnosis` | 单元测试 |

---

## 核心概念与数据模型

### 身份体系（容易混淆）

| 概念 | 含义 | 来源 |
|------|------|------|
| `device_id` | 芯片物理 ID | 生产端 `deviceLogicId_`，与 msprof `Device_id` 对齐 |
| `user_rank` | 用户在通信域中的 rank | `[HcclTaskSemantic]` 的 `user_rank[N]` |
| `comm_rank` | 通信算法内部的 rank 编号 | `[HcclTaskSemantic]` 的 `comm_rank[N]` |
| `peer_rank` | 对端 rank | `[HcclTaskSemantic]` 的 `peer_rank[N]` |
| `rank_size` | 通信域总 rank 数 | `[HcclTaskSemantic]` 的 `rank_size[N]` |
| profiler `Device_id` | msprof CSV 中的设备列 | `task_time.csv` 列 `Device_id` |

**关键规则**：不要从 rank 推断 `device_id`。`device_id` 必须由生产端显式注入，仅在处理历史遗留数据时使用 rank-as-device fallback。

### Merge Key

语义记录与 profiler 任务的匹配键：

```
(node_id, device_id, stream_id, task_id)
```

两端的 dataclass（`SemanticRecord`、`ProfilerTask`）均提供 `merge_key` property。

### 语义字段

`SEMANTIC_FIELDS`（20 列）：`schema_version`、`algorithm`、`phase`、`step`、`slice`、`user_rank`、`comm_rank`、`rank_size`、`peer_rank`、`event`、`semantic`、`stream_id`、`task_id`、`semantic_seq`、`profiler_seq`、`task_kind`、`source`、`device_id`、`device_ts`、`node_id`、`pid`

### 事件体系

常见事件及其在 AllReduce 中的含义：

| 事件 | 含义 |
|------|------|
| `tx_payload_start` | 发送数据载荷 |
| `rx_payload_reduce_start` | 接收并 Reduce |
| `rx_payload_copy_start` | 接收并拷贝 |
| `copy_start` | 本地拷贝 |
| `tx_ack_start` | 发送 ACK 信号 |
| `rx_ack_start` | 接收 ACK 信号 |
| `tx_data_signal_start` | 发送数据就绪信号 |
| `rx_data_signal_start` | 接收数据就绪信号 |
| `allreduce_start` | AllReduce 开始 |

### Phase 类型

`reduce_scatter_direct`、`reduce_scatter`、`allgather_direct`、`allgather`、`allreduce_executor`

### Task Kind

`sdma`、`rdma`、`reduce_inline`、`reduce_tbe`、`notify_record`、`notify_wait`

---

## 重要规则与边界条件

### Schema 与匹配

1. **`PROFILER_TRACE_EX` 行必须跳过** — `parse_msprof.py` 在 `kernel_type == "PROFILER_TRACE_EX"` 时 `continue`。这些是 profiler 自身的 marker，不是真实 task。
2. **`AI_CORE` kernel type** — 不匹配任何语义记录，但被明确排除在 `unmatched_profiler` 噪声之外（`IGNORED_UNMATCHED_PROFILER_KERNEL_TYPES`）。
3. **plog 时间戳不可用于 task duration** — `device_ts` 仅在 probe 记录中有值，完整记录中为 0。duration 应从 profiler `task_start`/`task_stop` 获取。
4. **Duplicate key 是硬错误** — `validate_trace.py` 在 `duplicate_semantic_rows > 0` 或 `duplicate_profiler_rows > 0` 时返回失败。
5. **`oneShot` 机制** — 生产端 `TaskSemanticEventScope` 在析构时设置 `oneShot = true`，`ReportTaskSemanticTrace` 在输出完整记录后立即将 `g_taskSemanticValid` 置为 false，防止同一 scope 覆盖多个 task 导致 duplicate merge key。

### plog 解析

- 支持三种格式：`field=value` 键值对（新版标准）、旧版空格分隔 token、跨行 legacy 格式。
- 自动从 `HCCL(pid,process):` 前缀提取 PID。
- CSV 写入统一使用 `utf-8` 编码，读取时兼容 `utf-8-sig`（BOM 头）。

### msprof 解析

- `first_present()` 在多可能列名中按优先级查找，兼容不同版本的 msprof CSV 列名差异。
- `default_node_id` 参数补充历史数据缺失的 node_id 字段。

---

## 构建与测试

### 构建

```bash
# 构建 HCOMM（通信基础库，包含 trace 生产端）
cd hcomm && bash build.sh --pkg

# 构建 HCCL（算子库 + 诊断工具）
cd hccl && bash build.sh --pkg
```

HCOMM 变更需要在 `hcomm` 仓库自身验证，不要只构建 `hccl`。构建产物通过 `LD_LIBRARY_PATH` 或安装目录指向新动态库。

### 功能测试

```bash
# 完整流程：运行 workload + merge + validate + visualize
bash test/run_step_trace_function_test.sh \
  --plog <plog> \
  --task-time <task_time.csv> \
  --node-id node0 \
  --min-match-rate 95 \
  -- \
  <your_allreduce_test_command>

# 仅 merge/validate（不运行 workload）
bash test/run_step_trace_function_test.sh \
  --plog <plog> \
  --task-time <task_time.csv>
```

功能通过标准：
- 脚本退出码 0
- `semantic_total > 0`
- `match_rate_percent >= 95`
- `duplicate_semantic_rows == 0` 且 `duplicate_profiler_rows == 0`
- `timeline.svg` 使用逻辑 phase/step/event 列展示（默认）

### 开销测试

```bash
python3 test/measure_step_trace_overhead.py \
  --repeat 20 --warmup 3 \
  --output test/out/overhead/overhead.csv \
  -- \
  <your_allreduce_test_command>
```

输出对比 baseline（`HCCL_STEP_TRACE=0`）和 trace（`HCCL_STEP_TRACE=1`）的 wall time。

### Python 单元测试

```bash
# 编译检查
python3 -m py_compile hccl/tools/diagnosis/*.py

# 运行单元测试
python3 -m unittest hccl.tools.diagnosis.test_diagnosis
```

---

## 可视化约定

### 时间线 (Timeline)

- **默认布局：逻辑列** — phase/step/event 分组列，而非真实时间缩放。这保证了密集 task 的可读性。
- 使用 `--layout time` 可切换到 raw msprof 时间轴。
- 每个 rank/stream 为一个 lane，事件按 `EVENT_COLOR` 配色。

### 依赖图 (Dependency Graph)

- 不要仅连接 payload 节点。对 single-ring AllReduce，有价值的一阶边包括：
  - **同 rank 程序序**：RxAck → Signal → Payload
  - **`right_neighbor_ack_dep`**：RxAck wait 依赖右邻居的上一 payload
  - **`upstream_data_signal_dep`**：data-signal wait 依赖上游生产者的上一 payload
  - **Payload 级简化边**：同 rank 上一步、上游上一 payload、reduce_scatter 到 allgather 的 phase bridge
- 更深层的 wait interval、NHR、多节点时钟对齐因果边属于未来规划。

---

## 工作约定

### Python 代码规范

- **仅使用标准库** — 诊断工具不引入任何第三方 pip 依赖。如需新依赖，需显式说明理由。
- 所有 `.py` 文件包含 `from __future__ import annotations`。
- 使用 `if __package__ in (None, ""): sys.path.insert(...)` 模式支持既可作为模块运行也可作为脚本运行。
- 数据模型使用 `@dataclass(frozen=True)` 保证不可变性。
- CSV 写入使用 `csv.DictWriter`，读取使用 `csv.DictReader`。

### C++ 代码规范

- Trace 相关代码集中在 `hcomm/src/common/debug/profiling/` 和 `hcomm/src/algorithm/base/alg_template/component/`。
- 使用 `CHK_RET` 宏进行错误检查和返回。
- 环境变量 `HCCL_STEP_TRACE=1` 控制 trace 开关。
- `device_id` 从 `deviceLogicId_` 成员获取，与 msprof `Device_id` 对齐。

### 跨仓库协作

- HCCL 和 HCOMM 有各自的构建系统和版本号。
- 一个完整的 trace 功能可能需要同时修改两个仓库（例如：HCOMM 加插桩 + HCCL 加解析）。
- 提交时说明每个仓库的变更。

---

## 已知问题与未来方向

当前 `hccl-trace` 工具链相比旧版 `cann-hccl/tools` 尚未实现：

- **Wait interval CSV 产出** — 无 `hccl_wait_relation_graph.py` 等价物
- **NHR 依赖图** — 无 `hccl_nhr_dependency_graph.py` 等价物
- **多节点时钟对齐** — 无 `hccl_clock_alignment_check.py` / `hccl_calibrate_intranode_offsets.py` 等价物
- **流顺序重排** — 无 `hccl_flow_order_table.py` 等价物

这些属于未来增量，需要先在消费端产出对应的中间 CSV artifact。

---

## Windows / PowerShell 注意事项

此工作空间经常从 Windows PowerShell 访问。

- 优先使用 `rg`（ripgrep）进行搜索。
- `apply_patch` 可能因 Windows 沙箱 helper 错误间歇性失败；失败时使用小型 PowerShell 文本替换或 UTF-8 no-BOM 写入。
- 避免在包含 `$`、反引号或嵌套引号的字符串中使用复杂内联 PowerShell 引用。对多行内容使用单引号 here-string。
- 写入文本时使用 UTF-8 without BOM：
  ```powershell
  $utf8NoBom = New-Object System.Text.UTF8Encoding($false)
  [System.IO.File]::WriteAllText((Resolve-Path $path), $text, $utf8NoBom)
  ```
- 本地 Python 启动器可能指向 WindowsApps 占位符。如果 `python`、`python3`、`py -3` 都无法启动，报告测试无法在本地运行，而非声称 Python 验证通过。
- `git diff --check` 在此机器上可能只报告 LF/CRLF 警告——这些是换行符警告，不是空格错误。

---

## 常用命令速查

```bash
# 运行完整诊断流水线
PYTHONPATH=hccl python3 -m tools.diagnosis.merge_timeline \
  --plog <plog> --task-time <task_time.csv> \
  -o merged.csv --summary summary.csv --node-id node0

# 校验合并结果
PYTHONPATH=hccl python3 -m tools.diagnosis.validate_trace merged.csv --min-match-rate 95

# 渲染时间线（逻辑布局）
PYTHONPATH=hccl python3 -m tools.diagnosis.visualize_timeline merged.csv -o timeline.svg

# 渲染依赖图
PYTHONPATH=hccl python3 -m tools.diagnosis.visualize_dependency_graph merged.csv -o dependency.svg

# 渲染交互式 HTML
PYTHONPATH=hccl python3 -m tools.diagnosis.visualize_html merged.csv -o report.html

# 编译检查所有诊断工具
python3 -m py_compile hccl/tools/diagnosis/*.py

# 运行单元测试
python3 -m unittest hccl.tools.diagnosis.test_diagnosis -v
```