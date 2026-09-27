/**
 * Copyright (c) 2025 Huawei Technologies Co., Ltd.
 * This program is free software, you can redistribute it and/or modify it under the terms and conditions of
 * CANN Open Software License Agreement Version 2.0 (the "License").
 * Please refer to the License for details. You may not use this file except in compliance with the License.
 * THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
 * INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
 * See LICENSE in the root of the software repository for the full text of the License.
 */

#ifndef TASK_SEMANTIC_AICPU_H
#define TASK_SEMANTIC_AICPU_H
#include "task_semantic_trace.h"
#include <cstddef>
namespace hccl {
// Sidecar records are process-local; never alter SQE bytes or H2D resource layout.
void CaptureAicpuTaskSemantic(const uint8_t *sqe, TaskType kind, u64 notifyId, s32 stage);
void CopyAicpuTaskSemantic(const uint8_t *dst, const uint8_t *src, size_t count);
void EraseAicpuTaskSemantic(const uint8_t *sqes, size_t count);
void ReportAicpuTaskSemantic(const uint8_t *sqes, size_t count, bool consume);
}
#endif
