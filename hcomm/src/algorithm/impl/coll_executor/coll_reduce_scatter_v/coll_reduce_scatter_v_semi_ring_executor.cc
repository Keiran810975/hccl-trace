/**
 * Copyright (c) 2025 Huawei Technologies Co., Ltd.
 * This program is free software, you can redistribute it and/or modify it under the terms and conditions of
 * CANN Open Software License Agreement Version 2.0 (the "License").
 * Please refer to the License for details. You may not use this file except in compliance with the License.
 * THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
 * INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
 * See LICENSE in the root of the software repository for the full text of the License.
 */

#include "coll_reduce_scatter_v_semi_ring_executor.h"

namespace hccl {

CollReduceScatterVSemiRingExecutor::CollReduceScatterVSemiRingExecutor(const HcclDispatcher dispatcher,
    std::unique_ptr<TopoMatcher> &topoMatcher)
    : CollReduceScatterSemiRingExecutor(dispatcher, topoMatcher)
{
    isReduceScatterV_ = true;
}

u64 CollReduceScatterVSemiRingExecutor::CalcLoopMaxCount(const u32 unitSize)
{
    // 中转内存单次最多能够接受的output count，这里不除以RankSize，因为每次循环可能会减少需要参与通信的Rank
    return inCCLbufferSize_ / HCCL_MIN_SLICE_ALIGN * HCCL_MIN_SLICE_ALIGN / unitSize;
}

bool CollReduceScatterVSemiRingExecutor::IsHugeData(const u64 curSize, OpParam *param)
{
    const u64 TBE_REDUCE_MAX_COUNT = INT32_MAX;
    u64 curCount = curSize / SIZE_TABLE[param->VDataDes.dataType];
    return (curSize > SDMA_SEND_MAX_SIZE) || ((!isSupportSDMAReduce_) && (curCount > TBE_REDUCE_MAX_COUNT));
}

REGISTER_EXEC("ReduceScatterVSemiRingExecutor", ReduceScatterVDoubleRingMidCount, CollReduceScatterVSemiRingExecutor);
} // namespace hccl