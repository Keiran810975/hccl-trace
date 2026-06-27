/*
 * This program is free software, you can redistribute it and/or modify it.
 * Copyright (c) 2025 Huawei Technologies Co., Ltd.
 * This file is a part of the CANN Open Software.
 * Licensed under CANN Open Software License Agreement Version 2.0 (the "License").
 * Please refer to the License for details. You may not use this file except in compliance with the License.
 * THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED, INCLUDING
 * BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
 * See LICENSE in the root of the software repository for the full text of the License.
 */

/*!
 * \file hccl_common.h
 * \brief
 */
#ifndef LIB_HCCL_HCCL_COMMON_H
#define LIB_HCCL_HCCL_COMMON_H

namespace AscendC {
constexpr uint32_t HCCL_GROUP_ID_0 = 0;  // communication group id, 0 for only one communication group
using HcclHandle = int8_t;

enum class HcclCMDType {  // use enum class to differentiate from enum AicpuComType
    HCCL_CMD_INVALID = 0,
    HCCL_CMD_BROADCAST = 1,
    HCCL_CMD_ALLREDUCE,
    HCCL_CMD_REDUCE,
    HCCL_CMD_SEND,
    HCCL_CMD_RECEIVE,
    HCCL_CMD_ALLGATHER,
    HCCL_CMD_REDUCE_SCATTER,
    HCCL_CMD_ALLTOALLV,
    HCCL_CMD_ALLTOALLVC,
    HCCL_CMD_ALLTOALL,
    HCCL_CMD_GATHER,
    HCCL_CMD_SCATTER,
    HCCL_CMD_BATCH_SEND_RECV,
    HCCL_CMD_BATCH_PUT,
    HCCL_CMD_BATCH_GET,
    HCCL_CMD_ALLGATHER_V,
    HCCL_CMD_REDUCE_SCATTER_V,
    HCCL_CMD_BATCH_WRITE,
    HCCL_CMD_HALF_ALLTOALLV = 20,
    HCCL_CMD_ALL
};

enum HcclReduceOp {
    HCCL_REDUCE_SUM = 0,  // sum
    HCCL_REDUCE_PROD = 1, // prod
    HCCL_REDUCE_MAX = 2,  // max
    HCCL_REDUCE_MIN = 3,  // min
    HCCL_REDUCE_RESERVED  // reserved
};

enum class MC2_BUFFER_LOCATION {
    MC2_BUFFER_TYPE_DEFAULT = 0,
    MC2_BUFFER_TYPE_OUTPUT,
    MC2_BUFFER_TYPE_WINDOW_IN,
    MC2_BUFFER_TYPE_WINDOW_OUT,
    MC2_BUFFER_TYPE_WORKSPACE,
    MC2_BUFFER_TYPE_INPUT,
    MC2_BUFFER_TYPE_COMMOUT,
    MC2_BUFFER_TYPE_END
};

enum HcclServerType {
    HCCL_SERVER_TYPE_AICPU = 0,
    HCCL_SERVER_TYPE_CCU,
    HCCL_SERVER_TYPE_END
};

enum class CoreType: uint8_t {
    DEFAULT,
    ON_AIV,
    ON_AIC
};

struct HcclServerConfig {
    CoreType type;
    int64_t blockId;
};

enum HcclDataType {
    HCCL_DATA_TYPE_INT8 = 0,   // int8
    HCCL_DATA_TYPE_INT16 = 1,  // int16
    HCCL_DATA_TYPE_INT32 = 2,  // int32
    HCCL_DATA_TYPE_FP16 = 3,   // fp16
    HCCL_DATA_TYPE_FP32 = 4,   // fp32
    HCCL_DATA_TYPE_INT64 = 5,  // int64
    HCCL_DATA_TYPE_UINT64 = 6, // uint64
    HCCL_DATA_TYPE_UINT8 = 7,  // uint8
    HCCL_DATA_TYPE_UINT16 = 8, // uint16
    HCCL_DATA_TYPE_UINT32 = 9, // uint32
    HCCL_DATA_TYPE_FP64 = 10,  // fp64
    HCCL_DATA_TYPE_BFP16 = 11, // bfp16
    HCCL_DATA_TYPE_INT128 = 12, // int128
    HCCL_DATA_TYPE_HIF8 = 14, // hif8
    HCCL_DATA_TYPE_FP8E4M3 = 15, // fp8e4m3
    HCCL_DATA_TYPE_FP8E5M2 = 16, // fp8e5m2
    HCCL_DATA_TYPE_FP8E8M0 = 17, // fp8e8m0
    HCCL_DATA_TYPE_RESERVED    // reserved
};

enum class ScopeType: uint8_t {
    ALL,
    QUEUE,
    BLOCK,

    INVALID_TYPE
};
}  // namespace AscendC

#endif  // LIB_HCCL_HCCL_COMMON_H