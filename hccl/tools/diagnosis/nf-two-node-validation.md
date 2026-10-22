# nf Node0 + Node2 诊断复核

本页是**用户授权调整验签之前**的失败对照。用户后续明确授权后，配套Device加载及
双机小负载完整链路已通过，见[最新授权验收](nf-authorized-two-node-validation.md)。

日期：2026-10-22。结论：**双机通信和 msprof 采集通过，完整语义诊断未通过**。
本轮只操作自有 `zjy-new`，没有改验签、驱动、网络、其他容器或其他人的任务。
用户确认没有可用的设备包签名服务或已签名的项目 Device 包。

## 本轮真实结果

| 配置 | 结果 |
|---|---|
| 物理节点 | Node0（192.169.0.173）+ Node2（192.169.0.125） |
| 设备 | 每机容器 runtime ID 1、3，对应物理 9、11；避开 Node0 已有明显显存占用的物理 8、10 |
| workload | 4 Rank，FP32 SUM AllReduce，每 Rank 8 MiB；1 次 warmup + 3 次 measured，无额外 barrier |
| nf Host + 官方 Device | 4 Rank 数值误差均为 0，结果门禁通过；每节点 650 个 profiler task，共 1300 个 |
| 语义覆盖 | 每节点 semantic=0；Host 控制任务每节点精确 enrich 48 个，不能代替算法 task 语义 |
| 严格诊断入口 | `status=failed`、`replay_gate_passed=false`、`analysis_completed=false`；未生成成功依赖图或等待诊断 |
| 本地回归 | Python 3.11：154 项诊断测试和 2 项 workload 结果门禁测试通过；不替代设备验收 |

原始目录 `current-input/node1` 是 torchrun 的第二节点，物理机器是 Node2，不是设备访问
异常的物理 Node1；manifest 已明确记录物理节点身份。4 次调用的跨机 operation 对齐来自
受控单通信域调用序列和全部 Rank 数值记录，不使用跨机时间接近或名称相同推断。

## 为什么停在设备包加载

本轮在 Node0 自有容器临时替换了正常加载入口中的 `aicpu_hcomm.tar.gz`，没有改加载
配置或安全设置。原包先备份，脚本退出时恢复并逐字节比较。第一次 150 秒外层超时未能
等到完整错误，第二次延长到 240 秒，保留了以下错误链：

```text
LoadPackageToDeviceByConfig:
  host and device checkcode compare failed package:aicpu_hcomm.tar.gz
OpenProcess: load package to device by config failed
TsdOpen failed
rtSetDevice: ErrCode=507033, desc=[device retain error]
```

失败发生在设备上下文初始化，还没有进入集合通信。两次测试进程均由超时边界退出，
最终自有容器均仅剩原有 `sleep infinity`。同一组芯片使用官方包的单机对照成功；恢复
官方包后的上述双机 trace+msprof 复核也成功。

自编译包是普通 gzip（首字节 `1f 8b`），官方包含附加头（首字节 `aa 55 aa 55`）。
仓库 [HCOMM 构建说明](../../../hcomm/docs/build.md:118) 说明自编译设备包不含签名头，
默认加载会做安全验签。本轮日志直接证明的是 **Device 包 checkcode 校验失败**，
尚不足以独立证明驱动具体在哪一个签名检查步骤拒绝，不能写成已实测明确的签名错误码。

官方 Device 没有本项目 AI_CPU sidecar。仅部署 nf Host 虽可通信并采集硬件任务，仍不能
补出真实 phase/step/event 和通知端点语义；不允许用任务序号、时间最近或猜测算法关系补配。

## 留存与后续条件

所有证据在 `test/out/nf-four-node-20261022/`：

- `device-load-evidence/`：两次加载日志、最短错误链、官方单机对照和恢复哈希。
- `device-load-evidence-complete.tar.gz`：完整归档；早期 `device-load-evidence.tar.gz` 因
  宿主用户无权读取容器日志而不完整，不作验收输入。
- `current-input/`：本轮真实双机 plog、msprof DB 和四个 Rank 数值结果。
- `two-node-current-manifest.json`：受控调用绑定及节点/Rank/设备映射。
- `current-replay/nf-two-node-current/`：精确合并统计及失败状态，不含伪造成功图。
- `try-device-package.sh`、`two-node-current.sh`：本轮加载/恢复及双机复核命令。

原官方包恢复 SHA256：`d51cca4ff0d8b5e5e138be7541eac6f9c7b83079834ae4f9a74150c9b6aa9625`。
本次自编译包 SHA256：`2b30fbe89be9eaa3c962f139aee162d356e97e1ce2b0788181d649d380f9974f`。

在用户“不调整验签”约束下，下一步需要管理员提供**现有策略能够接受的配套 Device 包
部署条件**，例如受信任签名流程或可合法加载开发包的独立测试环境。没有这个条件，
不能承诺靠继续改 Python、换节点或放宽合并门禁跑通 AI_CPU 的完整语义诊断。
HOST 跨机官方对照此前也超时，并非已验证的可用替代路径。
