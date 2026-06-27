/**
 * Copyright (c) 2025 Huawei Technologies Co., Ltd.
 * This program is free software, you can redistribute it and/or modify it under the terms and conditions of
 * CANN Open Software License Agreement Version 2.0 (the "License").
 * Please refer to the License for details. You may not use this file except in compliance with the License.
 * THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
 * INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
 * See LICENSE in the root of the software repository for the full text of the License.
 */
#ifndef LAUNCH_CONTEXT_H
#define LAUNCH_CONTEXT_H

#include <unordered_map>
#include <unordered_set>
#include <vector>
#include <string>
#include <mutex>
#include "hccl_api_data.h"
#include "hccl_thread.h"

class LaunchContext {
public:
    LaunchContext() = default;

    HcclResult SetLaunchMode(const char* launchTag, HcommLaunchMode mode);
    void AddThread(ThreadHandle thread);

private:
    HcclResult HandleBatchMode();
    HcclResult HandleEagerMode();
    HcclResult HandleClear();

    std::string launchTag_; // 当前tag
    std::unordered_map<std::string, std::unordered_set<ThreadHandle>> launchModeMap_;
    std::mutex mtx_;
    HcommLaunchMode mode_ = HCOMM_LAUNCH_MODE_EAGER;
};

#endif