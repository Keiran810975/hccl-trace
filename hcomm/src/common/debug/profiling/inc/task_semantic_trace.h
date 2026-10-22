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
    const char *algorithm{nullptr};
    const char *event{nullptr};
    const char *phase{nullptr};
    const char *semantic{nullptr};
    const char *source{"host"};
    u64 submitTs{0};        // msprof host-cycle submit timestamp; candidate window/validation only
    u64 notifyId{0};
    s32 notifyStage{-1};
    u32 step{0};
    u32 slice{0};
    u32 userRank{0};
    u32 commRank{0};
    u32 rankSize{0};
    u32 peerRank{INVALID_VALUE_RANKID};
    bool oneShot{false};
};

bool IsTaskSemanticTraceEnabled();
// Local control evidence uses an existing physical task as its operation anchor.
// It never introduces an execution task or a process-local operation counter.
struct TaskControlAnchor {
    u32 deviceId{INVALID_UINT};
    u32 streamId{INVALID_UINT};
    u32 taskId{INVALID_UINT};
};
class TaskControlScope {
public:
    explicit TaskControlScope(const TaskControlAnchor &anchor);
    ~TaskControlScope();
    TaskControlScope(const TaskControlScope &) = delete;
    TaskControlScope &operator=(const TaskControlScope &) = delete;
private:
    TaskControlAnchor previous_;
};
bool GetTaskControlAnchor(TaskControlAnchor &anchor);
void ReportTaskControl(const TaskControlAnchor &anchor, u32 streamId, u32 taskId,
    const char *kind, u64 notifyId = INVALID_U64, u64 dbNotifyId = INVALID_U64);
class TaskBuildContext {
public:
    explicit TaskBuildContext(const TaskControlAnchor &anchor);
    ~TaskBuildContext();
    TaskBuildContext(const TaskBuildContext &) = delete;
    TaskBuildContext &operator=(const TaskBuildContext &) = delete;
private:
    TaskControlAnchor previous_;
};
bool GetTaskBuildAnchor(TaskControlAnchor &anchor);
u64 TaskBuildClockNs();
void ReportTaskBuildSpan(const TaskControlAnchor &anchor, const TaskSemanticTraceInfo &info, u64 durationNs);
// Device workers do not inherit the submitting Host process environment.
// Version 2 also carries the submitting process's profiler device namespace.
constexpr u32 TASK_SEMANTIC_DEVICE_MAGIC = 0x48545331; // HTS1
u32 ResolveTaskSemanticDeviceId(u32 logicalDeviceId);
class TaskSemanticDeviceScope {
public:
    explicit TaskSemanticDeviceScope(bool enabled, u32 userRank = INVALID_VALUE_RANKID,
        u32 physicalDeviceId = INVALID_UINT);
    ~TaskSemanticDeviceScope();
    TaskSemanticDeviceScope(const TaskSemanticDeviceScope &) = delete;
    TaskSemanticDeviceScope &operator=(const TaskSemanticDeviceScope &) = delete;
private:
    int previous_;
    u32 previousUserRank_;
    u32 previousPhysicalDeviceId_;
};
u32 GetTaskSemanticPhysicalDeviceId();
bool GetTaskSemanticTraceInfo(TaskSemanticTraceInfo &info);
bool CaptureTaskSemanticTraceInfo(TaskSemanticTraceInfo &info);
void SetTaskSemanticTraceInfo(const TaskSemanticTraceInfo &info);
void ClearTaskSemanticTraceInfo();
HcclResult ReportTaskSemanticTraceProbe(u32 deviceId, u32 streamId, u32 taskId, const char *taskKind);
HcclResult ReportTaskSemanticTrace(u32 deviceId, u32 streamId, u32 taskId, TaskType taskType);
// fftsCtxId is the zero-based graph context id (TaskPara.ctxId), which maps to
// msprof JSON Subtask Id only after the graph parent has been identified.
HcclResult ReportTaskSemanticTrace(u32 deviceId, u32 streamId, u32 taskId, TaskType taskType,
    const TaskSemanticTraceInfo *info, u32 fftsCtxId = INVALID_UINT);
// Complete the pending graph built on this thread with the physical parent
// identity observed immediately after LaunchGraph.
HcclResult ReportTaskSemanticGraphCorrelation(u32 deviceId, u32 parentStreamId, u32 parentTaskId);
} // namespace hccl

#endif // TASK_SEMANTIC_TRACE_H
