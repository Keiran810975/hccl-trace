# 配套通信库的构建与部署

本页用于把 [HCCL-Trace](../README.md) 接到新的 Linux Ascend 环境。
如果管理员已经提供了与当前提交匹配的 Host 库和 Device 包，可以跳过构建，直接检查实际加载。

## 1. 检查现有环境

```bash
export REPO="$(pwd)"  # From the hccl-trace checkout.
export CANN_ROOT=/usr/local/Ascend/ascend-toolkit/latest
source "$CANN_ROOT/set_env.sh"  # Use the actual CANN installation path.
npu-smi info
command -v msprof
python3 -c 'import torch, torch_npu; print(torch.__version__, torch_npu.__version__)'
```

- 确认驱动、固件、CANN、OPS 与训练框架匹配，先不带 profiler 跑通原任务。
- 核对每个本地 Rank 对应的 runtime ID 和 profiler 设备 ID。多芯片物理卡的芯片编号不能当作卡号，
  `LOCAL_RANK` 也不是物理设备 ID。只使用已授权设备，检查目标卡没有外部任务且 HBM 状态正常。
- 确认容器已有合法设备映射，多机网络及启动端口可用。用短采集估算原始数据和完整图的空间。

## 2. 准备 Host 库

传统集合通信及本工具的语义生产端在 `hcomm/`，`hccl/` 提供通信 API/算子前端和离线工具。
仅安装 Python 或只编译 HCCL 前端都不会替换 HCOMM 语义生产端。
自行构建前按 [HCOMM 构建说明](../hcomm/docs/build.md) 准备匹配的 CANN 开发头、工具链及第三方依赖：

```bash
cd "$REPO/hcomm"
bash build.sh --pkg -p "$CANN_ROOT"
cd "$REPO"
```

使用本次 Host 构建或由管理员交付的同版本库组，包括 `libhcomm.so`、`libhccl_alg.so`、
`libhccl_plf.so`，并与现场 `libhccl.so` 和其他 CANN 运行依赖保持 ABI 兼容。
如果现场也要构建匹配的新前端，见 [HCCL 构建说明](../hccl/docs/build.md)。
不要从不同机器或构建随意拼接库。

把配套 Host 库放进专用目录；下面的命令在运行训练的同一环境执行：

```bash
DEPLOY="$HOME/hccl-trace-runtime/lib64"  # Directory containing the verified host libraries.
export LD_LIBRARY_PATH="$DEPLOY:${LD_LIBRARY_PATH:-}"
ldd "$DEPLOY/libhcomm.so"
sha256sum "$DEPLOY/libhcomm.so" "$DEPLOY/libhccl_alg.so" "$DEPLOY/libhccl_plf.so"
```

短跑时通过自己训练进程的加载日志或 `/proc/<pid>/maps` 核对真实加载路径。
设置了 `LD_LIBRARY_PATH` 不代表已加载目标库，不要覆盖共享 CANN。

## 3. AI_CPU 路径还需要 Device 包

Host 库不能替代 AI_CPU 内部任务的打点。实际训练走 AI_CPU 时，请让管理员按芯片和 CANN SDK
构建或提供同一提交的 `aicpu_hcomm.tar.gz`，并按现场授权签名和加载到私有运行环境。
包名相同不代表内容匹配，旧 Device 包可能有语义日志，却缺低日志采集所需的绑定信息。

若自行构建，下面是仅生成 Device 归档的入口。先按上节准备依赖，
`DEVICE_PRODUCT` 由管理员核对目标芯片和 SDK 后设置，不照搬其他机器的产品值。

```bash
: "${DEVICE_PRODUCT:?Set the verified Device PRODUCT for this SDK}"
cmake -S "$REPO/hcomm" -B "$REPO/hcomm/build_device" \
  -DCUSTOM_ASCEND_CANN_PACKAGE_PATH="$CANN_ROOT" \
  -DCANN_3RD_LIB_PATH="$REPO/hcomm/third_party" \
  -DCANN_UTILS_LIB_PATH="$REPO/hcomm/utils" \
  -DDEVICE_MODE=ON -DKERNEL_MODE=ON -DPRODUCT_SIDE=device \
  -DPRODUCT="$DEVICE_PRODUCT" -DUSE_ALOG=0 -DCMAKE_BUILD_TYPE=Release
cmake --build "$REPO/hcomm/build_device" --target generate_device_aicpu_package -j 8
sha256sum "$REPO/hcomm/build_device/aicpu_hcomm.tar.gz"
```

这一步只生成归档，不负责签名或安装。真实包路径、部署与恢复由管理员确认。
没有合法加载权限就停止，不修改共享包或全局安全策略，也不为了采集强制更换算法或执行引擎。
若现场获准临时改动，必须在采集前保存原值和原包，设置独立回滚；不论采集成功、失败或中断，
都先恢复并核验，再继续离线分析。

部署完成后，按 [README](../README.md#2-先跑通单机样例) 做短采集，确认
`msprof` DB、HCOMM 语义 plog 和每 Rank 的 `calls` 均存在，再看分析报告是否通过关联与构图。
