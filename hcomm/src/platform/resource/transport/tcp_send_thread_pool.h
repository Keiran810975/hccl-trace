/**
 * Copyright (c) 2025 Huawei Technologies Co., Ltd.
 * This program is free software, you can redistribute it and/or modify it under the terms and conditions of
 * CANN Open Software License Agreement Version 2.0 (the "License").
 * Please refer to the License for details. You may not use this file except in compliance with the License.
 * THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
 * INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
 * See LICENSE in the root of the software repository for the full text of the License.
 */

#ifndef TCP_SEND_THREAD_POOL_H
#define TCP_SEND_THREAD_POOL_H

#include <atomic>
#include <mutex>
#include <condition_variable>
#include <memory>
#include <string>
#include <algorithm>
#include <sched.h>
#include <thread>
#include <sstream>

#include "hccl/base.h"
#include "transport_heterog_def.h"
#include "dlhal_function.h"
#include "ascend_hal.h"

namespace hccl {
constexpr s64 SEND_UPPER_LIMIT = 1024 * 1024;   // 负载均衡，一次发送的数据上限标准
constexpr u32 INVALID_TAG = 0xFFFFFFFF;
constexpr u32 RUN_TASK_THREAD_SLEEP = 500;
constexpr u32 MAX_THREAD_SERIAL = 16;

class TcpSendThreadPool {
public:
using TagTaskQueue = std::unordered_map<u32, std::queue<HcclRequestInfo *>>; // <tag, Task>
struct TaskQueueInfo {
    std::pair<TagTaskQueue, TagTaskQueue> taskQueues;
    TagTaskQueue *threadTaskQueuePtr;
};

    static TcpSendThreadPool* GetSendPoolInstance()
    {
        static TcpSendThreadPool instance;
        return &instance;
    }

    HcclResult Init(u32 devId);
    HcclResult Deinit();
    HcclResult AddSendTask(HcclRequestInfo *request);

private:
    explicit TcpSendThreadPool();
    ~TcpSendThreadPool();
    HcclResult RunTask(u32 serialNum);
    HcclResult SendWork(std::queue<HcclRequestInfo *>& requestArray, bool &sendComplete);
    HcclResult LoadBalancing(TagTaskQueue *&sendWorkQueue);
    bool ThreadTaskQueueAddTask(u32 &threadSerial, TagTaskQueue* &sendWorkQueue);
    u32 DataUnitSize(HcclDataType dataType) const
    {
        if (dataType >= HCCL_DATA_TYPE_RESERVED) {
            HCCL_ERROR("[TcpSendThreadPool][dataUnitSize]data type[%s] out of range[%d, %d]",
                GetDataTypeEnumStr(dataType).c_str(), HCCL_DATA_TYPE_INT8, HCCL_DATA_TYPE_RESERVED - 1);
            return 0;
        }

        return SIZE_TABLE[dataType];
    }
    HcclResult SetAffinity(u32 devId, u32 cpuId);
    HcclResult WriteTidToDataCpuTasks();
    HcclResult BindDataCpu(unsigned int devId);
    u32 GetThreadNum();
    static std::array<std::mutex, MAX_THREAD_SERIAL> threadMutexs_; // thread task mutex
    std::vector<TaskQueueInfo> TaskQueueManager_; //  <threadSerial, <tag, task>的指针>
    std::vector<std::unique_ptr<std::thread>> threads_;
    std::condition_variable cond_;
    void* hcclImpl_;
    u32 threadNum_;
    bool isRunning_;
    u32 initCount_;
    u32 devId_;
};
}

#endif /** __SEND_THREAD_POOL_H__ */