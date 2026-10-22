/**
 * Copyright (c) 2025 Huawei Technologies Co., Ltd.
 * This program is free software, you can redistribute it and/or modify it under the terms and conditions of
 * CANN Open Software License Agreement Version 2.0 (the "License").
 * Please refer to the License for details. You may not use this file except in compliance with the License.
 * THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
 * INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
 * See LICENSE in the root of the software repository for the full text of the License.
 */

#ifndef TASK_SEMANTIC_SCOPE_H
#define TASK_SEMANTIC_SCOPE_H

#include "task_semantic_trace.h"

namespace hccl {
TaskSemanticTraceInfo MakeTaskSemanticTraceInfo(const char *phase, u32 step, u32 userRank, u32 rankSize,
    u32 slice, const char *event = nullptr, const char *semantic = nullptr,
    u32 peerRank = INVALID_VALUE_RANKID, const char *algorithm = "single_ring_direct",
    u32 commRank = INVALID_VALUE_RANKID);

class TaskSemanticScope {
public:
    explicit TaskSemanticScope(const TaskSemanticTraceInfo &info);
    ~TaskSemanticScope();

    TaskSemanticScope(const TaskSemanticScope &) = delete;
    TaskSemanticScope &operator=(const TaskSemanticScope &) = delete;

private:
    TaskSemanticTraceInfo previousInfo_{};
    bool hadPrevious_{false};
    bool enabled_{false};
    TaskControlAnchor buildAnchor_{};
    TaskSemanticTraceInfo buildInfo_{};
    u64 buildStartNs_{0};
};

class TaskSemanticEventScope {
public:
    TaskSemanticEventScope(const char *event, const char *semantic);
    ~TaskSemanticEventScope();

    TaskSemanticEventScope(const TaskSemanticEventScope &) = delete;
    TaskSemanticEventScope &operator=(const TaskSemanticEventScope &) = delete;

private:
    TaskSemanticTraceInfo previousInfo_{};
    bool active_{false};
};
} // namespace hccl

#endif // TASK_SEMANTIC_SCOPE_H
