# HCOMM

## 🔥Latest News

- [2025/11/30] HCOMM项目开源。

## 🚀 概述

HCOMM（Huawei Communication）是HCCL的通信基础库，提供通信域以及通信资源的管理能力。

HCOMM提供了标准化通信编程接口，具备以下关键特性：

- 支持昇腾设备上的多种通信引擎，充分发挥硬件能力。
- 支持多种通信协议，包括PCIe、HCCS、RDMA等。
- 通信平台与通信算子开发解耦，支持通信算子的独立开发、构建与部署。

<img src="./docs/figures/architecture.png" alt="hccl-architecture" style="width: 65%;  height:65%;" />

HCOMM通信基础库采用分层解耦的设计思路，将通信能力划分为控制面和数据面两部分。

- 控制面：提供拓扑信息查询与通信资源管理能力。
- 数据面：提供本地操作、算子间同步、通信操作等数据搬运和计算功能。

## 🔍 目录结构说明

本项目关键目录如下所示：

```
├── src                     # HCCL源码目录
│   ├── algorithm           # 通信算法源码目录
│   ├── framework           # 通信框架源码目录
│   └── platform            # 通信平台源码目录
├── build.sh                # 源码编译脚本
├── python                  # Python 包
├── inc                     # 集合通信对外头文件
├── docs                    # 资料文档目录
└── test                    # 测试代码目录
```

## ⚡️ 快速开始

若您希望快速构建并体验本项目，请访问如下简易指南。

- [源码构建](./docs/build.md)：了解如何编译、安装本项目，并进行基础测试验证。
- [样例执行](./examples/README.md)：参照详细的示例代码与操作步骤指引，快速体验。

## 📖 学习教程

HCCL提供了用户指南、技术文章、培训视频，详细可参见 [HCCL 参考资料](./docs/README.md)。

## 📝 相关信息

- [贡献指南](CONTRIBUTING.md)
- [安全声明](SECURITY.md)
- [许可证](LICENSE)
