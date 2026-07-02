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

#include <array>
#include <atomic>
#include <cstdlib>
#include <cstring>
#include <new>

namespace hccl {
namespace {
constexpr u32 TASK_SEMANTIC_SCHEMA_VERSION = 1;
constexpr u32 TASK_SEMANTIC_PROBE_LOG_LIMIT = 32;
constexpr u32 TASK_SEMANTIC_MAX_DEVICE_NUM = 64;
constexpr u32 TASK_SEMANTIC_MAX_STREAM_NUM = 65536;
using TaskSemanticStreamSeqArray = std::array<std::atomic<u64>, TASK_SEMANTIC_MAX_STREAM_NUM>;
thread_local bool g_taskSemanticValid = false;
thread_local TaskSemanticTraceInfo g_taskSemanticInfo{};

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

u64 NextTaskSemanticSeq(u32 deviceId, u32 streamId)
{
    static std::array<std::atomic<TaskSemanticStreamSeqArray *>, TASK_SEMANTIC_MAX_DEVICE_NUM> seqByDevice{};
    static std::atomic<u64> fallbackSeq{0};
    if (deviceId >= TASK_SEMANTIC_MAX_DEVICE_NUM || streamId >= TASK_SEMANTIC_MAX_STREAM_NUM) {
        return fallbackSeq.fetch_add(1, std::memory_order_relaxed);
    }

    TaskSemanticStreamSeqArray *streamSeqs = seqByDevice[deviceId].load(std::memory_order_acquire);
    if (streamSeqs == nullptr) {
        TaskSemanticStreamSeqArray *created = new (std::nothrow) TaskSemanticStreamSeqArray();
        if (created == nullptr) {
            return fallbackSeq.fetch_add(1, std::memory_order_relaxed);
        }
        for (auto &seq : *created) {
            seq.store(0, std::memory_order_relaxed);
        }
        TaskSemanticStreamSeqArray *expected = nullptr;
        if (seqByDevice[deviceId].compare_exchange_strong(expected, created, std::memory_order_release,
            std::memory_order_acquire)) {
            streamSeqs = created;
        } else {
            delete created;
            streamSeqs = expected;
        }
    }
    return (*streamSeqs)[streamId].fetch_add(1, std::memory_order_relaxed);
}
} // namespace

bool IsTaskSemanticTraceEnabled()
{
    static const bool enabled = []() -> bool {
        const char *stepTraceEnv = std::getenv("HCCL_STEP_TRACE");
        if (stepTraceEnv != nullptr && std::strcmp(stepTraceEnv, "1") == 0) {
            return true;
        }
        const char *legacyEnv = std::getenv("HCCL_TASK_SEMANTIC_TRACE");
        return legacyEnv != nullptr && std::strcmp(legacyEnv, "1") == 0;
    }();
    return enabled;
}

bool GetTaskSemanticTraceInfo(TaskSemanticTraceInfo &info)
{
    if (!IsTaskSemanticTraceEnabled() || !g_taskSemanticValid) {
        return false;
    }
    info = g_taskSemanticInfo;
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
    static std::atomic<u32> logCount(0);
    u32 curLogCount = logCount.fetch_add(1);
    if (curLogCount < TASK_SEMANTIC_PROBE_LOG_LIMIT) {
        HCCL_RUN_INFO("[HcclTaskSemanticProbe] set event[%s] phase[%s] step[%u] user_rank[%u] "
            "comm_rank[%u] rank_size[%u] slice[%u] peer_rank[%u] semantic[%s]",
            SafeStr(info.event), SafeStr(info.phase), info.step, info.userRank, info.commRank,
            info.rankSize, info.slice, info.peerRank, SafeStr(info.semantic));
    }
}

void ClearTaskSemanticTraceInfo()
{
    if (!IsTaskSemanticTraceEnabled()) {
        return;
    }
    g_taskSemanticValid = false;
    static std::atomic<u32> logCount(0);
    u32 curLogCount = logCount.fetch_add(1);
    if (curLogCount < TASK_SEMANTIC_PROBE_LOG_LIMIT) {
        HCCL_RUN_INFO("[HcclTaskSemanticProbe] clear");
    }
}

HcclResult ReportTaskSemanticTrace(u32 deviceId, u32 streamId, u32 taskId, TaskType taskType)
{
    TaskSemanticTraceInfo info{};
    const TaskSemanticTraceInfo *infoPtr = CaptureTaskSemanticTraceInfo(info) ? &info : nullptr;
    return ReportTaskSemanticTrace(deviceId, streamId, taskId, taskType, infoPtr);
}

HcclResult ReportTaskSemanticTrace(u32 deviceId, u32 streamId, u32 taskId, TaskType taskType,
    const TaskSemanticTraceInfo *info)
{
    if (!IsTaskSemanticTraceEnabled()) {
        return HCCL_SUCCESS;
    }
    if (info == nullptr) {
        static std::atomic<u32> logCount(0);
        u32 curLogCount = logCount.fetch_add(1);
        if (curLogCount < TASK_SEMANTIC_PROBE_LOG_LIMIT) {
            HCCL_RUN_INFO("[HcclTaskSemanticProbe] report without context device_id[%u] stream_id[%u] task_id[%u] "
                "task_type[%u] task_kind[%s]",
                deviceId, streamId, taskId, static_cast<u32>(taskType), TaskTypeToName(taskType));
        }
        return HCCL_SUCCESS;
    }

    u64 semanticSeq = NextTaskSemanticSeq(deviceId, streamId);
    HCCL_RUN_INFO("[HcclTaskSemantic] schema_version[%u] op_id[%llu] op_type[%s] algorithm[%s] "
        "event[%s] phase[%s] step[%u] slice[%u] rank[%u] ranksize[%u] user_rank[%u] comm_rank[%u] "
        "rank_size[%u] peer_rank[%u] semantic[%s] device_id[%u] stream_id[%u] task_id[%u] "
        "semantic_seq[%llu] task_type[%u] task_kind[%s] source[%s]",
        TASK_SEMANTIC_SCHEMA_VERSION, info->opId, SafeStr(info->opType),
        SafeStr(info->algorithm), SafeStr(info->event), SafeStr(info->phase),
        info->step, info->slice, info->userRank, info->rankSize,
        info->userRank, info->commRank, info->rankSize,
        info->peerRank, SafeStr(info->semantic), deviceId,
        streamId, taskId, semanticSeq, static_cast<u32>(taskType), TaskTypeToName(taskType),
        SafeStr(info->source));
    return HCCL_SUCCESS;
}

} // namespace hccl
