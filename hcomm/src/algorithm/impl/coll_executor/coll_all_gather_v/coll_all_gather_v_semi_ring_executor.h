/**
 * Copyright (c) 2025 Huawei Technologies Co., Ltd.
 * This program is free software, you can redistribute it and/or modify it under the terms and conditions of
 * CANN Open Software License Agreement Version 2.0 (the "License").
 * Please refer to the License for details. You may not use this file except in compliance with the License.
 * THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
 * INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
 * See LICENSE in the root of the software repository for the full text of the License.
 */

#ifndef COLL_ALL_GATHER_V_DOUBLE_RING_MID_COUNT_EXECUTOR_H
#define COLL_ALL_GATHER_V_DOUBLE_RING_MID_COUNT_EXECUTOR_H
#include "coll_all_gather_semi_ring_executor.h"
namespace hccl {
class CollAllGatherVSemiRingExecutor : public CollAllGatherSemiRingExecutor {
public:
    CollAllGatherVSemiRingExecutor(const HcclDispatcher dispatcher, std::unique_ptr<TopoMatcher> &topoMatcher);
    ~CollAllGatherVSemiRingExecutor() override = default;

private:
    bool IsSmallData(const u64 size) override;

    u64 CalcDstMemOffset(const OpParam &param, u32 perDataSize, u64 inputMemSize) const override;
    HcomCollOpInfo GetHcomCollOpInfo(const OpParam &param, const ExecMem &execMem) const override;
    HcclResult PrepareSlicesL0(std::vector<std::vector<Slice>> &multRingsSlice, const OpParam &param,
        const SubCommInfo &level2CommInfo, const SubCommInfo &level1CommInfo, const SubCommInfo &level0CommInfo,
        u32 perDataSize, u64 inputMemSize) override; // semi-ring only has L0
    HcclResult PrepareUserMemSlices(std::vector<std::vector<Slice>> &userMemSlices,
        const std::vector<std::vector<Slice>> &multRingsSlice, const OpParam &param, const SubCommInfo &level2CommInfo,
        const SubCommInfo &level1CommInfo, const SubCommInfo &level0CommInfo, u32 perDataSize,
        u64 inputMemSize) override;
};

} // namespace hccl

#endif