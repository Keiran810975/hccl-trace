/**
 * Copyright (c) 2025 Huawei Technologies Co., Ltd.
 * This program is free software, you can redistribute it and/or modify it under the terms and conditions of
 * CANN Open Software License Agreement Version 2.0 (the "License").
 * Please refer to the License for details. You may not use this file except in compliance with the License.
 * THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
 * INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
 * See LICENSE in the root of the software repository for the full text of the License.
 */

#ifndef AIV_COMMUNICATION_H
#define AIV_COMMUNICATION_H

#include "aiv_communication_base.h"
#include "aiv_communication_a3_crossnode.h"

#include "aiv_all_reduce_910b_smalldata.h"
#include "aiv_all_reduce_910b_middata.h"
#include "aiv_all_reduce_910b_bigdata.h"
#include "aiv_all_reduce_910b_rdma_smalldata.h"
#include "aiv_all_reduce_910b_rdma_middata.h"

#include "aiv_all_reduce_910b_bigdata_graph.h"
#include "aiv_all_reduce_910b_smalldata_graph.h"
#include "aiv_all_reduce_910b_rdma_smalldata_graph.h"
#include "aiv_all_reduce_910b_rdma_middata_graph.h"
#include "aiv_all_reduce_91093.h"

#include "aiv_all_to_all_vc_910b_no_loop.h"
#include "aiv_all_to_all_vc_910b_graph.h"
#include "aiv_all_to_all_v_910b.h"
#include "aiv_all_to_all_v_910b_graph.h"
#include "aiv_all_to_all_rdma_910b.h"

#include "aiv_all_to_all_910b_smalldata.h"
#include "aiv_all_to_all_91093.h"
#include "aiv_all_to_all_91093_graph.h"
#include "aiv_all_to_all_v_91093.h"
#include "aiv_all_to_all_v_91093_graph.h"
#include "aiv_all_to_all_v_91093_single.h"
#include "aiv_all_to_all_91093_single.h"

#include "aiv_all_gather_910b_graph.h"
#include "aiv_all_gather_91093_smalldata.h"
#include "aiv_all_gather_910b_smalldata.h"
#include "aiv_all_gather_v_910b_smalldata.h"
#include "aiv_all_gather_910b_bigdata.h"

#include "aiv_all_gather_v_910b_bigdata.h"

#include "aiv_reduce_scatter_910b_graph.h"
#include "aiv_reduce_scatter_91093_smalldata.h"
#include "aiv_reduce_scatter_910b_smalldata.h"
#include "aiv_reduce_scatter_910b_bigdata.h"
#include "aiv_reduce_scatter_910b_middata.h"

#include "aiv_reduce_scatter_v_910b_smalldata.h"
#include "aiv_reduce_scatter_v_910b_middata.h"
#include "aiv_reduce_scatter_v_910b_bigdata.h"

#include "aiv_sync_910b.h"

#include "aiv_all_gather_910B_rdma.h"
#include "aiv_all_gather_910B_rdma_graph.h"
#include "aiv_reduce_scatter_910b_rdma.h"
#include "aiv_reduce_scatter_910b_rdma_graph.h"
#include "aiv_all_reduce_deter_910b_smalldata.h"
#include "aiv_all_reduce_deter_910b_middata.h"
#include "aiv_all_reduce_deter_910b_bigdata.h"
#include "aiv_reduce_scatter_deter_910b_smalldata.h"
#include "aiv_reduce_scatter_deter_910b_middata.h"
#include "aiv_reduce_scatter_deter_910b_bigdata.h"
#include "aiv_broadcast_910b_bigdata.h"
#include "aiv_broadcast_910b_smalldata.h"

using namespace AscendC;

// aiv allreduce
#define AIV_ALL_REDUCE_KERNEL_BATCH_DEF(type) \
extern "C" __global__ __aicore__ void aiv_all_reduce_##type(KERNEL_ARGS_DEF) { \
    if (devType == DEV_TYPE_910B && deterministic == 1) { \
        if (len * sizeof(type) < AIV_ALL_REDUCE_DETER_SMALL_SIZE) { \
            return aiv_all_reduce_deter_910b_smalldata<type>(KERNEL_ARGS_CALL); \
        } else if (len * sizeof(type) <= AIV_ALL_REDUCE_DETER_MID_SIZE) { \
            return aiv_all_reduce_deter_910b_middata<type>(KERNEL_ARGS_CALL); \
        } else { \
            return aiv_all_reduce_deter_910b_bigdata<type>(KERNEL_ARGS_CALL); \
        } \
    }\
    if (isOpBase) { \
        if (aivRdmaStep >= 0) { \
            if (!useAivRdmaSmall) { \
                return aiv_all_reduce_910b_rdma_middata<type>(KERNEL_ARGS_CALL); \
            } else { \
                return aiv_all_reduce_910b_rdma_smalldata<type>(KERNEL_ARGS_CALL); \
            } \
        } else if (len * sizeof(type) >= AIV_ALL_REDUCE_BIG_SIZE) { \
            return aiv_all_reduce_910b_bigdata<type>(KERNEL_ARGS_CALL); \
        } else if (len * sizeof(type) > AIV_ALL_REDUCE_SMALL_SIZE) { \
            return aiv_all_reduce_910b_middata<type>(KERNEL_ARGS_CALL); \
        } else { \
            return aiv_all_reduce_910b_smalldata<type>(KERNEL_ARGS_CALL); \
        } \
    } else { \
        if (devType == DEV_TYPE_910_93) { \
            return aiv_all_reduce_91093<type>(KERNEL_ARGS_CALL); \
        } else if (aivRdmaStep >= 0) { \
            if (!useAivRdmaSmall) { \
                return aiv_all_reduce_910b_rdma_middata_graph<type>(KERNEL_ARGS_CALL); \
            } else { \
                return aiv_all_reduce_910b_rdma_smalldata_graph<type>(KERNEL_ARGS_CALL); \
            } \
        } else if (len * sizeof(type) > UB_MAX_DATA_SIZE) { \
            return aiv_all_reduce_910b_bigdata_graph<type>(KERNEL_ARGS_CALL); \
        } else { \
            return aiv_all_reduce_910b_smalldata_graph<type>(KERNEL_ARGS_CALL); \
        } \
    } \
} \
EXPORT_AIV_META_INFO(aiv_all_reduce_##type)

// aiv alltoallvc
#define AIV_ALL_TO_ALL_VC_KERNEL_BATCH_DEF(type) \
extern "C" __global__ __aicore__ void aiv_all_to_all_vc_##type(EXTERN_KERNEL_ARGS_DEF) { \
    if (isOpBase) { \
        if (extraArgs.maxCount * sizeof(type) > bufferSize) { \
            return aiv_all_to_all_vc_910b<type>(EXTERN_KERNEL_ARGS_CALL); \
        } else { \
            return aiv_all_to_all_vc_910b_no_loop<type>(EXTERN_KERNEL_ARGS_CALL); \
        } \
    } else { \
        if (devType == DEV_TYPE_910_93) { \
            return aiv_all_to_all_vc_91093_single_graph<type>(KERNEL_ARGS_CALL, &extraArgs); \
        } else { \
            return aiv_all_to_all_vc_910b_graph<type>(EXTERN_KERNEL_ARGS_CALL); \
        } \
    } \
} \
EXPORT_AIV_META_INFO(aiv_all_to_all_vc_##type)

// aiv alltoallv
#define AIV_ALL_TO_ALL_V_KERNEL_BATCH_DEF(type) \
extern "C" __global__ __aicore__ void aiv_all_to_all_v_##type(EXTERN_KERNEL_ARGS_DEF) { \
    if (isOpBase) { \
        if (devType == DEV_TYPE_910B) { \
            return aiv_all_to_all_v_910b<type>(EXTERN_KERNEL_ARGS_CALL); \
        } else { \
            return aiv_all_to_all_v_91093_single<type>(KERNEL_ARGS_CALL, &extraArgs); \
        } \
    } else { \
        return aiv_all_to_all_v_910b_graph<type>(EXTERN_KERNEL_ARGS_CALL); \
    } \
} \
EXPORT_AIV_META_INFO(aiv_all_to_all_v_##type)

// aiv alltoallv a3
#define AIV_ALL_TO_ALL_V_KERNEL_BATCH_DEF_V2(type) \
extern "C" __global__ __aicore__ void aiv_all_to_all_v_sp_##type(EXTERN_KERNEL_ARGS_DEF_V2) { \
    if (isOpBase) { \
        return aiv_all_to_all_v_91093<type>(KERNEL_ARGS_CALL, &extraArgs); \
    } else { \
        return aiv_all_to_all_v_91093_graph<type>(KERNEL_ARGS_CALL, &extraArgs); \
    } \
} \
EXPORT_AIV_META_INFO(aiv_all_to_all_v_sp_##type)

// aiv alltoall
#define AIV_ALL_TO_ALL_KERNEL_BATCH_DEF(type) \
extern "C" __global__ __aicore__ void aiv_all_to_all_##type(KERNEL_ARGS_DEF) { \
    if (devType == DEV_TYPE_910_93 && serverNum > 1) { \
        if (isOpBase) { \
            return aiv_all_to_all_91093<type>(KERNEL_ARGS_CALL); \
        } else { \
            return aiv_all_to_all_91093_graph<type>(KERNEL_ARGS_CALL); \
        } \
    } else if (aivRdmaStep >= 0) { \
        return aiv_all_to_all_rdma_910b<type>(KERNEL_ARGS_CALL); \
    } else if (isOpBase) { \
        if (len * sizeof(type) < AIV_ALL_TO_ALL_BIG_SIZE) { \
            return aiv_all_to_all_910b_smalldata<type>(KERNEL_ARGS_CALL); \
        } \
    } else { \
        if (devType == DEV_TYPE_910_93) { \
            return aiv_all_to_all_91093_single<type>(KERNEL_ARGS_CALL); \
        } \
    } \
} \
EXPORT_AIV_META_INFO(aiv_all_to_all_##type)

// aiv allgather
#define AIV_ALL_GATHER_KERNEL_BATCH_DEF(type) \
extern "C" __global__ __aicore__ void aiv_all_gather_##type(KERNEL_ARGS_DEF) { \
    if (isOpBase) { \
        if (aivRdmaStep >= 0) { \
            return aiv_all_gather_910b_rdma<type>(KERNEL_ARGS_CALL); \
        } else if (len * sizeof(type) > AIV_ALL_GATHER_SMALL_SIZE) { \
            return aiv_all_gather_910b_bigdata<type>(KERNEL_ARGS_CALL); \
        } else { \
            return aiv_all_gather_910b_smalldata<type>(KERNEL_ARGS_CALL); \
        } \
    } else { \
        if (aivRdmaStep >= 0) { \
            return aiv_all_gather_910b_rdma_graph<type>(KERNEL_ARGS_CALL); \
        } else if (devType == DEV_TYPE_910B) { \
            return aiv_all_gather_910b_bigdata_graph<type>(KERNEL_ARGS_CALL); \
        } else { \
            return aiv_all_gather_91093_smalldata<type>(KERNEL_ARGS_CALL); \
        } \
    } \
} \
EXPORT_AIV_META_INFO(aiv_all_gather_##type)

// aiv allgatherv
#define AIV_ALL_GATHER_V_KERNEL_BATCH_DEF(type) \
extern "C" __global__ __aicore__ void aiv_all_gather_v_##type(EXTERN_KERNEL_ARGS_DEF) { \
    if (isOpBase) { \
        if (sizeof(type) * extraArgs.maxCount > AIV_ALL_GATHER_SMALL_SIZE) { \
            return aiv_all_gather_v_910b_bigdata<type>(EXTERN_KERNEL_ARGS_CALL); \
        } else { \
            return aiv_all_gather_v_910b_smalldata<type>(EXTERN_KERNEL_ARGS_CALL); \
        } \
    } \
} \
EXPORT_AIV_META_INFO(aiv_all_gather_v_##type)

// aiv reducescatter
#define AIV_REDUCE_SCATTER_KERNEL_BATCH_DEF(type) \
extern "C" __global__ __aicore__ void aiv_reduce_scatter_##type(KERNEL_ARGS_DEF) { \
    if (devType == DEV_TYPE_910B && deterministic == 1) { \
        if (rankSize * len * sizeof(type) < AIV_REDUCE_SCATTER_DETER_SMALL_SIZE) { \
            return aiv_reduce_scatter_deter_910b_smalldata<type>(KERNEL_ARGS_CALL); \
        } else if (rankSize * len * sizeof(type) <= AIV_REDUCE_SCATTER_DETER_MID_SIZE) { \
            return aiv_reduce_scatter_deter_910b_middata<type>(KERNEL_ARGS_CALL); \
        } else { \
            return aiv_reduce_scatter_deter_910b_bigdata<type>(KERNEL_ARGS_CALL); \
        } \
    }\
    if (isOpBase) { \
        if (aivRdmaStep >= 0) { \
            return aiv_reduce_scatter_910b_rdma<type>(KERNEL_ARGS_CALL); \
        } else if (len * sizeof(type) > (devType == DEV_TYPE_910B ? AIV_REDUCE_SCATTER_MID_SIZE : AIV_REDUCE_SCATTER_SMALL_SIZE)) { \
            return aiv_reduce_scatter_910b_bigdata<type>(KERNEL_ARGS_CALL); \
        } else if (len * sizeof(type) > UB_MAX_DATA_SIZE) { \
            return aiv_reduce_scatter_910b_middata<type>(KERNEL_ARGS_CALL); \
        } else { \
            return aiv_reduce_scatter_910b_smalldata<type>(KERNEL_ARGS_CALL); \
        } \
    } else { \
        if (aivRdmaStep >= 0) { \
            return aiv_reduce_scatter_910b_rdma_graph<type>(KERNEL_ARGS_CALL); \
        } else if (devType == DEV_TYPE_910B) { \
            return aiv_reduce_scatter_910b_bigdata_graph<type>(KERNEL_ARGS_CALL); \
        } else { \
            return aiv_reduce_scatter_91093_smalldata<type>(KERNEL_ARGS_CALL); \
        } \
    } \
} \
EXPORT_AIV_META_INFO(aiv_reduce_scatter_##type)

//AIV ReduceScatterV
#define AIV_REDUCE_SCATTER_V_KERNEL_BATCH_DEF(type) \
extern "C" __global__ __aicore__ void aiv_reduce_scatter_v_##type(EXTERN_KERNEL_ARGS_DEF) { \
    if (extraArgs.maxCount * sizeof(type) > AIV_REDUCE_SCATTER_MID_SIZE) { \
        return aiv_reduce_scatter_v_910b_bigdata<type>(EXTERN_KERNEL_ARGS_CALL); \
    } else if (extraArgs.maxCount * sizeof(type) > UB_MAX_DATA_SIZE) { \
        return aiv_reduce_scatter_v_910b_middata<type>(EXTERN_KERNEL_ARGS_CALL); \
    } else  { \
        return aiv_reduce_scatter_v_910b_smalldata<type>(EXTERN_KERNEL_ARGS_CALL); \
    } \
} \
EXPORT_AIV_META_INFO(aiv_reduce_scatter_v_##type)

//aiv broadcast
#define AIV_BROADCAST_KERNEL_BATCH_DEF(type) \
extern "C" __global__ __aicore__ void aiv_broadcast_##type(KERNEL_ARGS_DEF) \
{ \
    if (len * sizeof(type) <= UB_MAX_DATA_SIZE) { \
        return aiv_broadcast_910b_smalldata<type>(KERNEL_ARGS_CALL); \
    } else { \
        return aiv_broadcast_910b_bigdata<type>(KERNEL_ARGS_CALL); \
    } \
} \
EXPORT_AIV_META_INFO(aiv_broadcast_##type)

// aiv sync
extern "C" __global__ __aicore__ void hccl_aiv_sync(KERNEL_ARGS_DEF) {
    return aiv_sync_910b_inner(KERNEL_ARGS_CALL); 
}
EXPORT_AIV_META_INFO(hccl_aiv_sync);

// 910B支持的Atomic数据类型
#define AIV_ATOMIC_DATA_TYPE_DEF(func) \
    func(float); \
    func(half); \
    func(int16_t); \
    func(int32_t); \
    func(int8_t); \
    func(bfloat16_t)

// 910B支持的DataCopy数据类型
#define AIV_COPY_DATA_TYPE_DEF(func) \
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
AIV_ATOMIC_DATA_TYPE_DEF(AIV_ALL_REDUCE_KERNEL_BATCH_DEF);
AIV_COPY_DATA_TYPE_DEF(AIV_ALL_TO_ALL_VC_KERNEL_BATCH_DEF);
AIV_COPY_DATA_TYPE_DEF(AIV_ALL_TO_ALL_V_KERNEL_BATCH_DEF);
AIV_COPY_DATA_TYPE_DEF(AIV_ALL_TO_ALL_V_KERNEL_BATCH_DEF_V2);
AIV_COPY_DATA_TYPE_DEF(AIV_ALL_TO_ALL_KERNEL_BATCH_DEF);
AIV_ATOMIC_DATA_TYPE_DEF(AIV_REDUCE_SCATTER_KERNEL_BATCH_DEF);
AIV_ATOMIC_DATA_TYPE_DEF(AIV_REDUCE_SCATTER_V_KERNEL_BATCH_DEF);
AIV_COPY_DATA_TYPE_DEF(AIV_ALL_GATHER_KERNEL_BATCH_DEF);
AIV_COPY_DATA_TYPE_DEF(AIV_ALL_GATHER_V_KERNEL_BATCH_DEF);
AIV_COPY_DATA_TYPE_DEF(AIV_BROADCAST_KERNEL_BATCH_DEF);

#endif  /* AIV_COMMUNICATION_H */
