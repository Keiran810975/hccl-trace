/**
 * Copyright (c) 2025 Huawei Technologies Co., Ltd.
 * This program is free software, you can redistribute it and/or modify it under the terms and conditions of
 * CANN Open Software License Agreement Version 2.0 (the "License").
 * Please refer to the License for details. You may not use this file except in compliance with the License.
 * THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
 * INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
 * See LICENSE in the root of the software repository for the full text of the License.
 */

#ifndef HCCL_MEM_DEFS_H
#define HCCL_MEM_DEFS_H

#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif // __cplusplus

/* 网络设备句柄 */
typedef void *HcclNetDev;
using HcclNetDevCtx = void *;

/**
 * @struct HcclBuf
 * @brief 内存缓冲区描述结构体
 * @var addr   - 虚拟地址指针
 * @var len    - 内存长度（单位字节）
 * @var handle - 内存管理句柄
 */
typedef struct {
    void *addr;
    uint64_t len;
    void *handle;
} HcclBuf;

/**
 * @enum HcclMemType
 * @brief 内存类型枚举定义
 */
typedef enum {
    HCCL_MEM_TYPE_DEVICE, ///< 设备侧内存（如NPU等）
    HCCL_MEM_TYPE_HOST,   ///< 主机侧内存
    HCCL_MEM_TYPE_NUM     ///< 内存类型数量
} HcclMemType;

/**
 * @struct HcclMem
 * @brief 内存段元数据描述结构体
 * @var type  - 内存物理位置类型，参见HcclMemType
 * @var addr  - 内存虚拟地址
 * @var size  - 内存区域字节数
 */
typedef struct {
    HcclMemType type;
    void *addr;
    uint64_t size;
} HcclMem;

#ifdef __cplusplus
}
#endif // __cplusplus
#endif