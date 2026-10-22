/**
 * Copyright (c) 2025 Huawei Technologies Co., Ltd.
 * This program is free software, you can redistribute it and/or modify it under the terms and conditions of
 * CANN Open Software License Agreement Version 2.0 (the "License").
 * Please refer to the License for details. You may not use this file except in compliance with the License.
 * THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
 * INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
 * See LICENSE in the root of the software repository for the full text of the License.
 */

#include "task_semantic_trace.h"

#include <atomic>
#include <algorithm>
#include <cerrno>
#include <chrono>
#include <cstdlib>
#include <cstring>
#include <new>
#include <vector>

namespace hccl {
namespace {
constexpr u32 TASK_SEMANTIC_SCHEMA_VERSION = 4;
constexpr u32 TASK_GRAPH_CORRELATION_SCHEMA_VERSION = 1;
thread_local bool g_taskSemanticValid = false;
thread_local int g_deviceTraceEnabled = -1;
thread_local u32 g_deviceUserRank = INVALID_VALUE_RANKID;
thread_local u32 g_physicalDeviceId = INVALID_UINT;
thread_local TaskSemanticTraceInfo g_taskSemanticInfo{};
thread_local TaskControlAnchor g_controlAnchor{};
thread_local TaskControlAnchor g_buildAnchor{};
// DispatcherGraph adds contexts and launches the graph synchronously on the
// same thread. Keep one pending build per thread until the launch callback
// supplies its physical parent stream/task.
struct PendingFftsGraph {
    bool valid{false};
    u32 deviceId{INVALID_UINT};
    u32 anchorTaskId{INVALID_UINT};
    u64 graphInstanceId{0};
};
thread_local PendingFftsGraph g_pendingFftsGraph{};
std::atomic<u64> g_nextGraphInstanceId{1};

const char *TaskTypeToName(TaskType taskType)
{
    switch (taskType) {
        case TaskType::TASK_SDMA:
            return "sdma";
        case TaskType::TASK_RDMA:
            return "rdma";
        case TaskType::TASK_REDUCE_INLINE:
            return "reduce_inline";
        case TaskType::TASK_REDUCE_TBE:
            return "reduce_tbe";
        case TaskType::TASK_NOTIFY_RECORD:
            return "notify_record";
        case TaskType::TASK_NOTIFY_WAIT:
            return "notify_wait";
        case TaskType::TASK_HOST:
            return "host";
        case TaskType::TASK_GRAPH_LAUNCH:
            return "graph_launch";
        case TaskType::TASK_BATCH_REPORT:
            return "batch_report";
        case TaskType::TASK_FLIP:
            return "flip";
        default:
            return "unknown";
    }
}

const char *SafeStr(const char *value)
{
    return value == nullptr ? "" : value;
}

bool HasReportableSemantic(const TaskSemanticTraceInfo &info)
{
    return info.event != nullptr && info.event[0] != '\0' &&
        info.semantic != nullptr && info.semantic[0] != '\0';
}

u64 ObserveFftsGraphTask(u32 deviceId, u32 anchorTaskId)
{
    if (!g_pendingFftsGraph.valid) {
        g_pendingFftsGraph.valid = true;
        g_pendingFftsGraph.deviceId = deviceId;
        g_pendingFftsGraph.anchorTaskId = anchorTaskId;
        g_pendingFftsGraph.graphInstanceId =
            g_nextGraphInstanceId.fetch_add(1, std::memory_order_relaxed);
    } else if (g_pendingFftsGraph.deviceId != deviceId ||
        g_pendingFftsGraph.anchorTaskId != anchorTaskId) {
        HCCL_WARNING("[HcclTaskGraphCorrelation] replace pending graph without launch "
            "old_device_id[%u] old_anchor_task_id[%u] new_device_id[%u] new_anchor_task_id[%u]",
            g_pendingFftsGraph.deviceId, g_pendingFftsGraph.anchorTaskId, deviceId, anchorTaskId);
        g_pendingFftsGraph.deviceId = deviceId;
        g_pendingFftsGraph.anchorTaskId = anchorTaskId;
        g_pendingFftsGraph.graphInstanceId =
            g_nextGraphInstanceId.fetch_add(1, std::memory_order_relaxed);
    }
    return g_pendingFftsGraph.graphInstanceId;
}

} // namespace

TaskControlScope::TaskControlScope(const TaskControlAnchor &anchor) : previous_(g_controlAnchor)
{
    g_controlAnchor = IsTaskSemanticTraceEnabled() ? anchor : TaskControlAnchor{};
}

TaskControlScope::~TaskControlScope()
{
    g_controlAnchor = previous_;
}

bool GetTaskControlAnchor(TaskControlAnchor &anchor)
{
    anchor = g_controlAnchor;
    return IsTaskSemanticTraceEnabled() && anchor.deviceId != INVALID_UINT &&
        anchor.streamId != INVALID_UINT && anchor.taskId != INVALID_UINT;
}

void ReportTaskControl(const TaskControlAnchor &anchor, u32 streamId, u32 taskId,
    const char *kind, u64 notifyId, u64 dbNotifyId)
{
    if (!IsTaskSemanticTraceEnabled() || anchor.deviceId == INVALID_UINT ||
        anchor.streamId == INVALID_UINT || anchor.taskId == INVALID_UINT) {
        return;
    }
    HCCL_RUN_INFO("[HcclTaskControl] schema_version[1] device_id[%u] stream_id[%u] task_id[%u] "
        "task_kind[%s] notify_id[%llu] db_notify_id[%llu] anchor_stream_id[%u] anchor_task_id[%u]",
        anchor.deviceId, streamId, taskId, kind, notifyId, dbNotifyId, anchor.streamId, anchor.taskId);
}

TaskBuildContext::TaskBuildContext(const TaskControlAnchor &anchor) : previous_(g_buildAnchor)
{
    g_buildAnchor = IsTaskSemanticTraceEnabled() ? anchor : TaskControlAnchor{};
}

TaskBuildContext::~TaskBuildContext()
{
    g_buildAnchor = previous_;
}

bool GetTaskBuildAnchor(TaskControlAnchor &anchor)
{
    anchor = g_buildAnchor;
    return IsTaskSemanticTraceEnabled() && anchor.deviceId != INVALID_UINT &&
        anchor.streamId != INVALID_UINT && anchor.taskId != INVALID_UINT;
}

u64 TaskBuildClockNs()
{
    return static_cast<u64>(std::chrono::duration_cast<std::chrono::nanoseconds>(
        std::chrono::steady_clock::now().time_since_epoch()).count());
}

void ReportTaskBuildSpan(const TaskControlAnchor &anchor, const TaskSemanticTraceInfo &info, u64 durationNs)
{
    // Sparse CPU-side construction observation, not a device execution interval.
    // Scope nesting may overlap; consumers must never sum these as device time.
    constexpr u64 MIN_BUILD_SPAN_NS = 1000000;
    if (!IsTaskSemanticTraceEnabled() || durationNs < MIN_BUILD_SPAN_NS || anchor.deviceId == INVALID_UINT) {
        return;
    }
    HCCL_RUN_INFO("[HcclTaskBuildSpan] schema_version[1] device_id[%u] kernel_stream_id[%u] "
        "kernel_task_id[%u] user_rank[%u] algorithm[%s] phase[%s] step[%u] slice[%u] "
        "duration_ns[%llu] threshold_ns[%llu] timing_domain[aicpu_build_cpu]",
        anchor.deviceId, anchor.streamId, anchor.taskId, info.userRank, SafeStr(info.algorithm),
        SafeStr(info.phase), info.step, info.slice, durationNs, MIN_BUILD_SPAN_NS);
}

bool IsTaskSemanticTraceEnabled()
{
    if (g_deviceTraceEnabled >= 0) {
        return g_deviceTraceEnabled != 0;
    }
#ifdef CCL_KERNEL
    return false;
#else
    static const bool enabled = []() -> bool {
        const char *stepTraceEnv = std::getenv("HCCL_STEP_TRACE");
        if (stepTraceEnv != nullptr && std::strcmp(stepTraceEnv, "1") == 0) {
            return true;
        }
        const char *legacyEnv = std::getenv("HCCL_TASK_SEMANTIC_TRACE");
        return legacyEnv != nullptr && std::strcmp(legacyEnv, "1") == 0;
    }();
    return enabled;
#endif
}

u32 ResolveTaskSemanticDeviceId(u32 logicalDeviceId)
{
    const char *cursor = std::getenv("ASCEND_RT_VISIBLE_DEVICES");
    if (cursor == nullptr || *cursor == '\0') {
        return logicalDeviceId;
    }
    try {
        std::vector<u32> devices;
        while (*cursor != '\0') {
            if (*cursor < '0' || *cursor > '9') { return INVALID_UINT; }
            char *end = nullptr;
            errno = 0;
            const auto value = std::strtoull(cursor, &end, 10);
            if (errno != 0 || value >= INVALID_UINT || (*end != '\0' && *end != ',')) {
                return INVALID_UINT;
            }
            const u32 device = static_cast<u32>(value);
            if (std::find(devices.begin(), devices.end(), device) != devices.end()) { return INVALID_UINT; }
            devices.push_back(device);
            if (*end == '\0') { break; }
            cursor = end + 1;
            if (*cursor == '\0') { return INVALID_UINT; }
        }
        return logicalDeviceId < devices.size() ? devices[logicalDeviceId] : INVALID_UINT;
    } catch (const std::bad_alloc &) {
        return INVALID_UINT;
    }
}

TaskSemanticDeviceScope::TaskSemanticDeviceScope(bool enabled, u32 userRank, u32 physicalDeviceId)
    : previous_(g_deviceTraceEnabled), previousUserRank_(g_deviceUserRank),
      previousPhysicalDeviceId_(g_physicalDeviceId)
{
    g_deviceTraceEnabled = enabled ? 1 : 0;
    g_deviceUserRank = userRank;
    g_physicalDeviceId = physicalDeviceId;
}

TaskSemanticDeviceScope::~TaskSemanticDeviceScope()
{
    g_deviceTraceEnabled = previous_;
    g_deviceUserRank = previousUserRank_;
    g_physicalDeviceId = previousPhysicalDeviceId_;
}

u32 GetTaskSemanticPhysicalDeviceId()
{
    return g_physicalDeviceId;
}

bool GetTaskSemanticTraceInfo(TaskSemanticTraceInfo &info)
{
    if (!IsTaskSemanticTraceEnabled() || !g_taskSemanticValid) {
        return false;
    }
    info = g_taskSemanticInfo;
    // Hierarchical templates may use a subcommunicator rank. Keep commRank
    // unchanged and obtain the global user rank from the device communicator.
    if (g_deviceUserRank != INVALID_VALUE_RANKID) {
        info.userRank = g_deviceUserRank;
    }
    return true;
}

bool CaptureTaskSemanticTraceInfo(TaskSemanticTraceInfo &info)
{
    if (!GetTaskSemanticTraceInfo(info) || !HasReportableSemantic(info)) {
        return false;
    }
    if (info.oneShot) {
        g_taskSemanticValid = false;
    }
    return true;
}

void SetTaskSemanticTraceInfo(const TaskSemanticTraceInfo &info)
{
    if (!IsTaskSemanticTraceEnabled()) {
        return;
    }
    g_taskSemanticInfo = info;
    g_taskSemanticValid = true;
    HCCL_DEBUG("[HcclTaskSemanticProbe] set event[%s] phase[%s] step[%u] slice[%u] "
        "peer_rank[%u] semantic[%s]",
        SafeStr(info.event), SafeStr(info.phase), info.step, info.slice,
        info.peerRank, SafeStr(info.semantic));
}

void ClearTaskSemanticTraceInfo()
{
    if (!IsTaskSemanticTraceEnabled()) {
        return;
    }
    g_taskSemanticValid = false;
    HCCL_DEBUG("[HcclTaskSemanticProbe] clear");
}

HcclResult ReportTaskSemanticTraceProbe(u32 deviceId, u32 streamId, u32 taskId, const char *taskKind)
{
    if (!IsTaskSemanticTraceEnabled()) {
        return HCCL_SUCCESS;
    }
    HCCL_DEBUG("[HcclTaskSemanticProbe] report without context device_id[%u] stream_id[%u] "
        "hccl_task_id[%u] task_kind[%s]",
        deviceId, streamId, taskId, SafeStr(taskKind));
    return HCCL_SUCCESS;
}

HcclResult ReportTaskSemanticTrace(u32 deviceId, u32 streamId, u32 taskId, TaskType taskType)
{
    TaskSemanticTraceInfo info{};
    const TaskSemanticTraceInfo *infoPtr = CaptureTaskSemanticTraceInfo(info) ? &info : nullptr;
    return ReportTaskSemanticTrace(deviceId, streamId, taskId, taskType, infoPtr, INVALID_UINT);
}

HcclResult ReportTaskSemanticTrace(u32 deviceId, u32 streamId, u32 taskId, TaskType taskType,
    const TaskSemanticTraceInfo *info, u32 fftsCtxId)
{
    if (!IsTaskSemanticTraceEnabled()) {
        return HCCL_SUCCESS;
    }
    if (info == nullptr || info->source == nullptr || std::strcmp(info->source, "aicpu") != 0) {
        deviceId = ResolveTaskSemanticDeviceId(deviceId);
        if (deviceId == INVALID_UINT) { return HCCL_SUCCESS; }
    }
    const bool isFfts = fftsCtxId != INVALID_UINT;
    const u64 graphInstanceId = isFfts ? ObserveFftsGraphTask(deviceId, taskId) : 0;
    if (info == nullptr) {
        HCCL_DEBUG("[HcclTaskSemanticProbe] report without context device_id[%u] stream_id[%u] "
            "hccl_task_id[%u] task_type[%u] task_kind[%s] "
            "ffts_ctx_id[%u] graph_instance_id[%llu]",
            deviceId, streamId, taskId, static_cast<u32>(taskType), TaskTypeToName(taskType),
            fftsCtxId, graphInstanceId);
        return HCCL_SUCCESS;
    }

    HCCL_RUN_INFO("[HcclTaskSemantic] schema_version[%u] "
        "algorithm[%s] event[%s] phase[%s] step[%u] slice[%u] "
        "user_rank[%u] comm_rank[%u] rank_size[%u] peer_rank[%u] semantic[%s] "
        "device_id[%u] stream_id[%u] hccl_task_id[%u] "
        "task_type[%u] task_kind[%s] "
        "ffts_ctx_id[%u] graph_instance_id[%llu] "
        "submit_ts[%llu] notify_id[%llu] notify_stage[%d] source[%s]",
        TASK_SEMANTIC_SCHEMA_VERSION,
        SafeStr(info->algorithm), SafeStr(info->event), SafeStr(info->phase),
        info->step, info->slice,
        info->userRank, info->commRank, info->rankSize,
        info->peerRank, SafeStr(info->semantic), deviceId,
        streamId, taskId, static_cast<u32>(taskType), TaskTypeToName(taskType),
        fftsCtxId, graphInstanceId, info->submitTs, info->notifyId, info->notifyStage,
        SafeStr(info->source));
    return HCCL_SUCCESS;
}

HcclResult ReportTaskSemanticGraphCorrelation(u32 deviceId, u32 parentStreamId, u32 parentTaskId)
{
    if (!IsTaskSemanticTraceEnabled()) {
        return HCCL_SUCCESS;
    }
    deviceId = ResolveTaskSemanticDeviceId(deviceId);
    if (deviceId == INVALID_UINT) { return HCCL_SUCCESS; }
    if (!g_pendingFftsGraph.valid) {
        HCCL_DEBUG("[HcclTaskGraphCorrelation] launch without pending semantic graph "
            "device_id[%u] parent_stream_id[%u] parent_task_id[%u]",
            deviceId, parentStreamId, parentTaskId);
        return HCCL_SUCCESS;
    }
    if (g_pendingFftsGraph.deviceId != deviceId) {
        HCCL_WARNING("[HcclTaskGraphCorrelation] launch device mismatch "
            "pending_device_id[%u] launch_device_id[%u] graph_instance_id[%llu]",
            g_pendingFftsGraph.deviceId, deviceId, g_pendingFftsGraph.graphInstanceId);
        g_pendingFftsGraph = PendingFftsGraph{};
        return HCCL_SUCCESS;
    }
    HCCL_RUN_INFO("[HcclTaskGraphCorrelation] schema_version[%u] graph_instance_id[%llu] "
        "device_id[%u] anchor_task_id[%u] parent_stream_id[%u] parent_task_id[%u]",
        TASK_GRAPH_CORRELATION_SCHEMA_VERSION, g_pendingFftsGraph.graphInstanceId,
        deviceId, g_pendingFftsGraph.anchorTaskId, parentStreamId, parentTaskId);
    g_pendingFftsGraph = PendingFftsGraph{};
    return HCCL_SUCCESS;
}

} // namespace hccl
