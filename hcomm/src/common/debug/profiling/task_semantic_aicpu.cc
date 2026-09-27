/**
 * Copyright (c) 2025 Huawei Technologies Co., Ltd.
 * This program is free software, you can redistribute it and/or modify it under the terms and conditions of
 * CANN Open Software License Agreement Version 2.0 (the "License").
 * Please refer to the License for details. You may not use this file except in compliance with the License.
 * THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
 * INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
 * See LICENSE in the root of the software repository for the full text of the License.
 */

#include "task_semantic_aicpu.h"
#include "aicpu/aicpu_hccl_sqcqv1.h"
#include <atomic>
#include <map>
#include <mutex>
#include <new>

namespace hccl {
namespace {
constexpr size_t SQE_BYTES = 64;
struct SemanticSnapshot {
    TaskSemanticTraceInfo info;
    TaskType kind;
    u32 physicalDeviceId;
};
std::mutex g_semanticMutex;
std::map<const uint8_t *, SemanticSnapshot> g_semanticSqes;
std::atomic<bool> g_hasSemanticSqes{false};
}

void EraseAicpuTaskSemantic(const uint8_t *sqes, size_t count)
{
    if (!g_hasSemanticSqes.load(std::memory_order_relaxed)) {
        return;
    }
    std::lock_guard<std::mutex> lock(g_semanticMutex);
    for (size_t i = 0; i < count; ++i) {
        g_semanticSqes.erase(sqes + i * SQE_BYTES);
    }
    g_hasSemanticSqes.store(!g_semanticSqes.empty(), std::memory_order_relaxed);
}

void CaptureAicpuTaskSemantic(const uint8_t *sqe, TaskType kind, u64 notifyId, s32 stage)
{
    if (!IsTaskSemanticTraceEnabled()) {
        return;
    }
    TaskSemanticTraceInfo info{};
    if (!GetTaskSemanticTraceInfo(info) || info.event == nullptr || info.event[0] == '\0' ||
        info.semantic == nullptr || info.semantic[0] == '\0') {
        return;
    }
    // HAL's device-local ID can differ from the Host physical ID in msprof.
    // Capture the communicator's explicit physical identity with the SQE;
    // neither delayed reporting nor cache replay may consult a new TLS scope.
    const u32 physicalDeviceId = GetTaskSemanticPhysicalDeviceId();
    if (physicalDeviceId == INVALID_UINT) {
        return;
    }
    info.source = "aicpu";
    info.submitTs = 0; // Device construction time is not a Host-cycle timestamp.
    info.notifyId = notifyId;
    info.notifyStage = stage;
    try {
        std::lock_guard<std::mutex> lock(g_semanticMutex);
        g_semanticSqes[sqe] = SemanticSnapshot{info, kind, physicalDeviceId};
        g_hasSemanticSqes.store(true, std::memory_order_relaxed);
        TaskSemanticTraceInfo consumed{};
        (void)CaptureTaskSemanticTraceInfo(consumed);
    } catch (const std::bad_alloc &) {
        HCCL_WARNING("[HcclTaskSemanticDevice] diagnostic allocation failed; record dropped");
    }
}

void CopyAicpuTaskSemantic(const uint8_t *dst, const uint8_t *src, size_t count)
{
    if (!g_hasSemanticSqes.load(std::memory_order_relaxed)) {
        return;
    }
    try {
        std::lock_guard<std::mutex> lock(g_semanticMutex);
        for (size_t i = 0; i < count; ++i) {
            const auto it = g_semanticSqes.find(src + i * SQE_BYTES);
            if (it == g_semanticSqes.end()) {
                g_semanticSqes.erase(dst + i * SQE_BYTES);
            } else {
                g_semanticSqes[dst + i * SQE_BYTES] = it->second;
            }
        }
        g_hasSemanticSqes.store(!g_semanticSqes.empty(), std::memory_order_relaxed);
    } catch (const std::bad_alloc &) {
        EraseAicpuTaskSemantic(dst, count);
        HCCL_WARNING("[HcclTaskSemanticDevice] cache diagnostic allocation failed; records dropped");
    }
}

void ReportAicpuTaskSemantic(const uint8_t *sqes, size_t count, bool consume)
{
    if (!g_hasSemanticSqes.load(std::memory_order_relaxed)) {
        return;
    }
    std::lock_guard<std::mutex> lock(g_semanticMutex);
    for (size_t i = 0; i < count; ++i) {
        const auto *sqe = sqes + i * SQE_BYTES;
        const auto it = g_semanticSqes.find(sqe);
        if (it == g_semanticSqes.end()) {
            continue;
        }
        // 910B/910_93 V1 only. Read the submitted (possibly cache-refreshed)
        // identity, never infer it from a local buffer index or previous call.
        const auto *header = reinterpret_cast<const rtStarsSqeHeader_t *>(sqe);
        (void)ReportTaskSemanticTrace(it->second.physicalDeviceId, header->rtStreamId, header->taskId,
            it->second.kind, &it->second.info);
        if (consume) {
            g_semanticSqes.erase(it);
        }
    }
    g_hasSemanticSqes.store(!g_semanticSqes.empty(), std::memory_order_relaxed);
}
} // namespace hccl
