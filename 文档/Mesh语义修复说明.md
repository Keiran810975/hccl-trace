# Mesh normal AllGather 语义修复

更新：2026-09-15。修复分支 `codex/fix-mesh-semantic` 基于已集成 standard Ring/NHR 的
master，合入原 `feat-mesh@d870111` 后修改。修复提交 `286ef99` 已获用户批准，随
`f30a90a` 快进合入 master；设备验证待执行，详见 [测试 prompt](../test/prompts/integrated-master-device-test.md)。

## 问题与改动

normal `AllGatherMesh::Rx()` 调用 P2P `RxAsync()`，该调用先提交 Notify wait，再按
linkAttribute 提交目的端 SDMA。原先包住整个 Rx 的 payload one-shot 被 wait 消费，
导致 wait 误标为 copy，真正的 copy 无语义。Tx 在目的端拉取模式下也可能把 signal
标成 payload。

在 `all_gather_mesh.cc` 内沿用 standard Ring 的处理方式：

- inline P2P：TxData → TxDataSignal，分别使用 payload / data-signal event scope；
  RxDataSignal → RxData，分别使用 data-signal / payload-copy event scope。
- 非 inline transport 保留 TxAsync/RxAsync 及对应 payload scope。
- RunAllGather 只提供 phase、step、rank、slice、peer 上下文；具体事件在 Tx/Rx 内设置。

保留 `step=0`、stream、buffer 地址、长度、baseOffset 和错误返回；仍由 transport 决定
哪一端提交 SDMA。没有修改公共 TLS、TaskData、TransportP2p、atomic/direct 实现或算法选择，
没有新增设备任务。

## 本次检查与验证边界

- 对照 TransportP2p 的单 slice TxAsync/RxAsync 与拆分 API，核对提交顺序、copy 条件和参数；
  各失败点仍通过 CHK_RET 返回，后续调用不会继续提交。
- 核对 atomic 覆盖自己的 RunAllGather，不经过本次修改的 private Tx/Rx。
- `git diff --check` 通过。修复只改变一个 C++ 文件，消费端 Python 没有变化。
- 本机无可用 CANN Toolkit/HCOMM 编译环境；未执行 C++ 构建或修复后的设备采集。
  用户此前确认 Mesh 已测试、留存 HTML 符合 Direct 路径；该结果不能替代本次 normal 修复验证。

## 下一次设备运行

在配套 Linux/CANN 下构建 HCOMM（`bash build.sh --pkg`），部署新库后只跑一个能够由
selector 确认进入 **normal Mesh AllGather + inline P2P** 的代表性 AllReduce 样例，启用
`HCCL_STEP_TRACE=1` 和 msprof，保存 plog、DB、源码提交与命令。当前 Ring 测试强制仍是
独立待办，不能只凭配置字符串判断已运行 Mesh normal。

复用现有 merge/validate 流程，检查算子结果及匹配率，并关注：

- `rx_data_signal_start` 对应 wait，`rx_payload_copy_start` 对应实际 SDMA；
- `tx_data_signal_start` 对应 record；只有实际提交发送 SDMA 时才有 tx payload；
- 原 copy 缺标与 wait 错标消失，没有增加通信任务或出现 duplicate/kind mismatch。

以实际 linkAttribute 决定哪端有 copy，不要求每一对 peer 同时出现 Tx/Rx 两份 SDMA。
不为本次局部修复重复验证全部 Mesh 变体。
