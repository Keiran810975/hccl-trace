/**
 * Copyright (c) 2025 Huawei Technologies Co., Ltd.
 * This program is free software, you can redistribute it and/or modify it under the terms and conditions of
 * CANN Open Software License Agreement Version 2.0 (the "License").
 * Please refer to the License for details. You may not use this file except in compliance with the License.
 * THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
 * INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
 * See LICENSE in the root of the software repository for the full text of the License.
 */

#ifndef THREAD_MANAGER_H
#define THREAD_MANAGER_H
#include <string>
#include <unordered_map>
#include <memory>
#include <mutex>
#include "hccl_api.h"
#include "hccl_thread.h"
#include "log.h"
#include "manager_common.h"

namespace hccl {

class ThreadMgr {
public:
    ThreadMgr(uint32_t threadNum, uint32_t notifyNumPerThread, std::string commId, aclrtBinHandle binHandle, const ManagerCallbacks& callbacks);
    ~ThreadMgr() = default;
    HcclResult HcclThreadAcquire(CommEngine engine, uint32_t threadNum,
        uint32_t notifyNumPerThread, ThreadHandle *threads);
    HcclResult HcclThreadAcquireWithStream(CommEngine engine,
        rtStream_t stream, uint32_t notifyNum, ThreadHandle *thread);
    HcclResult HcclGetNotifyNumInThread(ThreadHandle thread, uint32_t *notifyNum);

    u32 GetThreadNum() const { return threadNum_; }
    u32 GetNotifyNumPerThread() const { return notifyNumPerThread_; }

private:
    HcclResult CommEngineToNotifyLoadType(CommEngine engine, NotifyLoadType &type);
    HcclResult CommEngineToStreamType(CommEngine engine, StreamType &type);

    u32 threadNum_ = 0;
    u32 notifyNumPerThread_ = 0;
    std::string commId_;
    aclrtBinHandle binHandle_;

    u64 usedNotifyNum_ = 0;
    std::mutex threadMutex_;
    std::vector<std::shared_ptr<HcclThread>> threads_;

    std::mutex mainThreadMutex_;
    std::map<rtStream_t, std::unique_ptr<HcclThread>> mainThread_;

    ManagerCallbacks callbacks_;
};
}
#endif