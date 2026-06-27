/**
 * Copyright (c) 2025 Huawei Technologies Co., Ltd.
 * This program is free software, you can redistribute it and/or modify it under the terms and conditions of
 * CANN Open Software License Agreement Version 2.0 (the "License").
 * Please refer to the License for details. You may not use this file except in compliance with the License.
 * THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
 * INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
 * See LICENSE in the root of the software repository for the full text of the License.
 */

#include "channel_aicpu_interface.h"
#include "framework/aicpu_hccl_process.h"

extern "C" {
__attribute__((visibility("default"))) uint32_t RunAicpuIndOpThreadInit(void *args)
{
    if (args == nullptr) {
        HCCL_ERROR("args is null.");
        return HCCL_E_PARA;
    }
 
    struct InitTask {
        u64 context;
        bool isCustom;
    };
    InitTask *ctxArgs = reinterpret_cast<InitTask *>(args);
    ThreadMgrAicpuParam* param = reinterpret_cast<ThreadMgrAicpuParam*>(ctxArgs->context);
    return AicpuHcclProcess::AicpuIndOpThreadInit(param);
}

__attribute__((visibility("default"))) uint32_t RunAicpuIndOpNotify(void *args)
{
    if (args == nullptr) {
        HCCL_ERROR("args is null.");
        return HCCL_E_PARA;
    }
 
    struct InitTask {
        u64 context;
        bool isCustom;
    };
    InitTask *ctxArgs = reinterpret_cast<InitTask *>(args);
    NotifyMgrAicpuParam* param = reinterpret_cast<NotifyMgrAicpuParam*>(ctxArgs->context);
    return AicpuHcclProcess::AicpuIndOpNotifyInit(param);
}
}