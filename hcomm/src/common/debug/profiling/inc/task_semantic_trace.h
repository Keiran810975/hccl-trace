/**
 * Copyright (c) 2025 Huawei Technologies Co., Ltd.
 * This program is free software, you can redistribute it and/or modify it under the terms and conditions of
 * CANN Open Software License Agreement Version 2.0 (the "License").
 * Please refer to the License for details. You may not use this file except in compliance with the License.
 * THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
 * INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
 * See LICENSE in the root of the software repository for the full text of the License.
 */

#ifndef TASK_SEMANTIC_TRACE_H
#define TASK_SEMANTIC_TRACE_H

#include "hccl_common.h"
#include "profiler_base_pub.h"

namespace hccl {
struct TaskSemanticTraceInfo {
    const char *opType{nullptr};
    const char *algorithm{nullptr};
    const char *event{nullptr};
    const char *phase{nullptr};
    const char *semantic{nullptr};
    const char *source{"host"};
    u64 opId{0};
    u32 step{0};
    u32 slice{0};
    u32 userRank{0};
    u32 commRank{0};
    u32 rankSize{0};
    u32 peerRank{INVALID_VALUE_RANKID};
    bool oneShot{false};
};

bool IsTaskSemanticTraceEnabled();
bool GetTaskSemanticTraceInfo(TaskSemanticTraceInfo &info);
bool CaptureTaskSemanticTraceInfo(TaskSemanticTraceInfo &info);
void SetTaskSemanticTraceInfo(const TaskSemanticTraceInfo &info);
void ClearTaskSemanticTraceInfo();
HcclResult ReportTaskSemanticTrace(u32 deviceId, u32 streamId, u32 taskId, TaskType taskType);
HcclResult ReportTaskSemanticTrace(u32 deviceId, u32 streamId, u32 taskId, TaskType taskType,
    const TaskSemanticTraceInfo *info);
} // namespace hccl

#endif // TASK_SEMANTIC_TRACE_H
