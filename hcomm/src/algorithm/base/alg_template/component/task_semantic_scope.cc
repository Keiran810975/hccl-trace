/**
 * Copyright (c) 2025 Huawei Technologies Co., Ltd.
 * This program is free software, you can redistribute it and/or modify it under the terms and conditions of
 * CANN Open Software License Agreement Version 2.0 (the "License").
 * Please refer to the License for details. You may not use this file except in compliance with the License.
 * THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
 * INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
 * See LICENSE in the root of the software repository for the full text of the License.
 */

#include "task_semantic_scope.h"

namespace hccl {
TaskSemanticTraceInfo MakeTaskSemanticTraceInfo(const char *phase, u32 step, u32 userRank, u32 rankSize,
    u32 slice, const char *event, const char *semantic, u32 peerRank, const char *algorithm, u32 commRank)
{
    TaskSemanticTraceInfo info{};
    info.algorithm = algorithm;
    info.event = event;
    info.phase = phase;
    info.semantic = semantic;
    info.step = step;
    info.slice = slice;
    info.userRank = userRank;
    info.commRank = (commRank == INVALID_VALUE_RANKID) ? userRank : commRank;
    info.rankSize = rankSize;
    info.peerRank = peerRank;
    return info;
}

TaskSemanticScope::TaskSemanticScope(const TaskSemanticTraceInfo &info)
{
    enabled_ = IsTaskSemanticTraceEnabled();
    if (!enabled_) {
        return;
    }
    hadPrevious_ = GetTaskSemanticTraceInfo(previousInfo_);
    SetTaskSemanticTraceInfo(info);
}

TaskSemanticScope::~TaskSemanticScope()
{
    if (!enabled_) {
        return;
    }
    if (hadPrevious_) {
        SetTaskSemanticTraceInfo(previousInfo_);
        return;
    }
    ClearTaskSemanticTraceInfo();
}

} // namespace hccl
