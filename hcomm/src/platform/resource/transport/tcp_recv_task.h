/**
 * Copyright (c) 2025 Huawei Technologies Co., Ltd.
 * This program is free software, you can redistribute it and/or modify it under the terms and conditions of
 * CANN Open Software License Agreement Version 2.0 (the "License").
 * Please refer to the License for details. You may not use this file except in compliance with the License.
 * THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
 * INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
 * See LICENSE in the root of the software repository for the full text of the License.
 */

#ifndef TCP_RECV_TASK_H
#define TCP_RECV_TASK_H

#include <mutex>
#include <condition_variable>
#include <memory>
#include <string>
#include <algorithm>
#include <thread>
#include <sstream>
#include <atomic>

#include "hccl/base.h"
#include "hccp_common.h"
#include "transport_heterog_def.h"

#define MAX_EVENTS 1024

namespace hccl {
using EnvelopStatusFlag = struct EnvelopStatusFlagDef {
    bool flag;
    EnvelopStatusFlagDef() : flag(false) {};
};

using RecvRecord = struct RecvRecordDef {
    void *buffer;
    u64 size;
    RecvRecordDef() : buffer(nullptr), size(0) {};
};

class TcpRecvTask {
public:
    static TcpRecvTask* GetRecvTaskInstance()
    {
        static TcpRecvTask instance;
        return &instance;
    }

    static void RecvDataCb(const FdHandle fdHandle);
    HcclResult Init(const SocketInfoT socketInfo, void *transportPtr);
    HcclResult Deinit();
    HcclResult SetRecvTask(const FdHandle fdHandle, HcclRequestInfo *request);

private:
    explicit TcpRecvTask();
    ~TcpRecvTask();
    HcclResult RecvData(const FdHandle fdHandle);

    static std::atomic<bool> g_initFlag_;
    std::map<const FdHandle, void *> fdTransportMap_; // 记录fd对应transport的映射
    std::map<const FdHandle, EnvelopStatusFlag> envelopMap_; // 记录某个socket当前是否收到信封
    std::map<const FdHandle, std::pair<HcclRequestInfo *, RecvRecord>> recvTaskMap_; // 记录某个socket当前的recvEntry
    s32 initCount_;
    std::mutex recvMutex_;
    std::mutex transportMapMutex_;
};
}

#endif /** _RECV_TASK_H__ */