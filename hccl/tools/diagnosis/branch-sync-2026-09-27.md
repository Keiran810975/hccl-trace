# 2026-09-27 分支提交与同步记录

用户要求同步各分支。检查时 `master`、`8.5.0` 和四个 `feat-*` 算法分支与远端同名提交一致；
`codex/multinode-diagnosis` 的 `f7b0e89` 领先远端1个提交。后续三个开发分支仍指向
`f7b0e89`，实际阶段成果通过未提交工作区一路继承，尚未形成独立提交。

按已保存快照恢复为连续历史，保留当前文件及历史验证证据：

| 分支 | 提交 / 内容 | 依据 |
|---|---|---|
| `codex/multinode-diagnosis` | `f7b0e89`：direct inline reduce兼容修复 | 原有本地提交 |
| `ai-cpu-support` | `0920910`：AI_CPU捕获、缓存语义、物理身份与多机匹配 | 耗时诊断开始时的 `inherited.patch`；AI_CPU最终源码归档与进入Ring/NHR前的未跟踪文件快照 |
| `codex/diagnosis-timing-rdma` | `b75ebee`：Copy/Reduce/RDMA耗时、同机RDMA及Wait视图 | Ring/NHR开始前的 `inherited-worktree.tar.gz` |
| `codex/ring-nhr-diagnosis` | 本记录所在提交：控制链、CPU阶段、等待分析与异常闭环 | 当前工作区；与9月24日最终47文件清单全部SHA256一致，另更新同步说明 |

前两阶段使用独立临时index恢复，不切换或覆盖当前工作文件。Python回归分别85、95项通过；
当前Ring/NHR阶段111项通过。此次是提交整理与同步，没有重新声称完成新的设备采集；
设备结论继续绑定各阶段归档的源码清单与原始证据。

原始DB、HTML、部署包、临时索引和测试输出留在被忽略的 `test/out/`，不作为源码推送。
当前hccl/hcomm目录都解析到根仓Git元数据，因此没有额外子仓远端需要推送。
四个旧算法临时worktree显示大量文件缺失，其分支提交与远端一致；保留这些目录状态，
不把临时checkout的缺失提交为源码删除。远端独有 `codex/remove-ring-forcing` 保持原状。

本次不合并不同功能分支到master、不强推、不删除远端分支。实际推送与最终远端SHA核验记录
保存在本地 `test/out/branch-sync-20260927/`。
