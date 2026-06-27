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
#include <cstdlib>
#include <cstring>

namespace hccl {
namespace {
constexpr u32 TASK_SEMANTIC_SCHEMA_VERSION = 1;
constexpr u32 TASK_SEMANTIC_PROBE_LOG_LIMIT = 32;
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

HcclResult ReportTaskSemanticTrace(u32 streamId, u32 taskId, TaskType taskType)
{
    if (!IsTaskSemanticTraceEnabled()) {
        return HCCL_SUCCESS;
    }
    if (!g_taskSemanticValid) {
        static std::atomic<u32> logCount(0);
        u32 curLogCount = logCount.fetch_add(1);
        if (curLogCount < TASK_SEMANTIC_PROBE_LOG_LIMIT) {
            HCCL_RUN_INFO("[HcclTaskSemanticProbe] report without context stream_id[%u] task_id[%u] "
                "task_type[%u] task_kind[%s]",
                streamId, taskId, static_cast<u32>(taskType), TaskTypeToName(taskType));
        }
        return HCCL_SUCCESS;
    }

    HCCL_RUN_INFO("[HcclTaskSemantic] schema_version[%u] op_id[%llu] op_type[%s] algorithm[%s] "
        "event[%s] phase[%s] step[%u] slice[%u] rank[%u] ranksize[%u] user_rank[%u] comm_rank[%u] "
        "rank_size[%u] peer_rank[%u] semantic[%s] stream_id[%u] task_id[%u] task_type[%u] task_kind[%s] source[%s]",
        TASK_SEMANTIC_SCHEMA_VERSION, g_taskSemanticInfo.opId, SafeStr(g_taskSemanticInfo.opType),
        SafeStr(g_taskSemanticInfo.algorithm), SafeStr(g_taskSemanticInfo.event), SafeStr(g_taskSemanticInfo.phase),
        g_taskSemanticInfo.step, g_taskSemanticInfo.slice, g_taskSemanticInfo.userRank, g_taskSemanticInfo.rankSize,
        g_taskSemanticInfo.userRank, g_taskSemanticInfo.commRank, g_taskSemanticInfo.rankSize,
        g_taskSemanticInfo.peerRank, SafeStr(g_taskSemanticInfo.semantic),
        streamId, taskId, static_cast<u32>(taskType), TaskTypeToName(taskType), SafeStr(g_taskSemanticInfo.source));
    return HCCL_SUCCESS;
}
} // namespace hccl
