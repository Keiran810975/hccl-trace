/**
 * Copyright (c) 2025 Huawei Technologies Co., Ltd.
 * This program is free software, you can redistribute it and/or modify it under the terms and conditions of
 * CANN Open Software License Agreement Version 2.0 (the "License").
 * Please refer to the License for details. You may not use this file except in compliance with the License.
 * THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
 * INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
 * See LICENSE in the root of the software repository for the full text of the License.
 */

#ifndef AIV_COMMUNICATION_A3_CROSSNODE_H
#define AIV_COMMUNICATION_A3_CROSSNODE_H

#include "kernel_operator.h"
#include "aiv_all_gather_crossnode_91093.h"
#include "aiv_all_gather_crossnode_91093_graph.h"
#include "aiv_reduce_scatter_crossnode_91093.h"
#include "aiv_reduce_scatter_crossnode_91093_graph.h"
#include "aiv_reduce_scatter_91093_deter.h"
#include "aiv_all_reduce_crossnode_91093.h"
#include "aiv_all_reduce_91093_deter.h"
#include "aiv_sync_91093.h"

using namespace AscendC;

#define EXPORT_AIV_META_INFO(kernel_name) \
static const struct FunLevelKType kernel_name##_kernel_type_section __attribute__ \
((used, section (".ascend.meta." #kernel_name))) \
= {{F_TYPE_KTYPE, sizeof(unsigned int), K_TYPE_AIV}}

// aiv allreduce
#define AIV_ALL_REDUCE_KERNEL_BATCH_DEF_A3(type) \
extern "C" __global__ __aicore__ void aiv_all_reduce_cn_##type(KERNEL_ARGS_DEF_A3) { \
    if(deterministic != 0) { \
        return aiv_all_reduce_91093_deter<type>(KERNEL_ARGS_CALL_A3); \
    } else { \
        return aiv_all_reduce_crossnode_91093<type>(KERNEL_ARGS_CALL_A3); \
    } \
} \
EXPORT_AIV_META_INFO(aiv_all_reduce_cn_##type)

// aiv allgather
#define AIV_ALL_GATHER_KERNEL_BATCH_DEF_A3(type) \
extern "C" __global__ __aicore__ void aiv_all_gather_cn_##type(KERNEL_ARGS_DEF_A3) { \
    if (isOpBase) { \
        return aiv_all_gather_crossnode_91093<type>(KERNEL_ARGS_CALL_A3); \
    } \
    return aiv_all_gather_crossnode_91093_graph<type>(KERNEL_ARGS_CALL_A3); \
} \
EXPORT_AIV_META_INFO(aiv_all_gather_cn_##type)

// aiv reducescatter
#define AIV_REDUCE_SCATTER_KERNEL_BATCH_DEF_A3(type) \
extern "C" __global__ __aicore__ void aiv_reduce_scatter_cn_##type(KERNEL_ARGS_DEF_A3) { \
    if (deterministic == 1){ \
        return aiv_reduce_scatter_91093_deter<type>(KERNEL_ARGS_CALL_A3); \
    } \
    if (isOpBase) { \
        return aiv_reduce_scatter_crossnode_91093<type>(KERNEL_ARGS_CALL_A3); \
    } \
    return aiv_reduce_scatter_crossnode_91093_graph<type>(KERNEL_ARGS_CALL_A3); \
} \
EXPORT_AIV_META_INFO(aiv_reduce_scatter_cn_##type)

// aiv sync
extern "C" __global__ __aicore__ void hccl_aiv_sync_cn(KERNEL_ARGS_DEF_A3) {
    return aiv_sync_91093_inner(KERNEL_ARGS_CALL_A3); 
}
EXPORT_AIV_META_INFO(hccl_aiv_sync_cn);

// AIV支持的Atomic数据类型
#define AIV_ATOMIC_DATA_TYPE_DEF_A3(func) \
    func(float); \
    func(half); \
    func(int16_t); \
    func(int32_t); \
    func(int8_t); \
    func(bfloat16_t)

// AIV支持的DataCopy数据类型
#define AIV_COPY_DATA_TYPE_DEF_A3(func) \
    func(half); \
    func(int16_t); \
    func(uint16_t); \
    func(float); \
    func(int32_t); \
    func(uint32_t); \
    func(int8_t); \
    func(uint8_t); \
    func(bfloat16_t)

// 定义各算子各数据类型Kernel入口
AIV_ATOMIC_DATA_TYPE_DEF_A3(AIV_ALL_REDUCE_KERNEL_BATCH_DEF_A3);
AIV_ATOMIC_DATA_TYPE_DEF_A3(AIV_REDUCE_SCATTER_KERNEL_BATCH_DEF_A3);
AIV_COPY_DATA_TYPE_DEF_A3(AIV_ALL_GATHER_KERNEL_BATCH_DEF_A3);

#endif  /* AIV_COMMUNICATION_H */
