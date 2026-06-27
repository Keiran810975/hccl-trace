/**
 * Copyright (c) 2025 Huawei Technologies Co., Ltd.
 * This program is free software, you can redistribute it and/or modify it under the terms and conditions of
 * CANN Open Software License Agreement Version 2.0 (the "License").
 * Please refer to the License for details. You may not use this file except in compliance with the License.
 * THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
 * INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
 * See LICENSE in the root of the software repository for the full text of the License.
 */
#ifndef AICPU_LAUNCH_MANAGER_H
#define AICPU_LAUNCH_MANAGER_H

#include "hccl_common.h"
#include "stream_pub.h"
#include "aicpu_operator_pub.h"
#include "hccl_thread.h"
#include "hccl_api.h"
#include "local_notify.h"
#include "aicpu_init_param.h"

constexpr uint32_t THREAD_UNIQUE_ID_MAX_SIZE = 1024;
constexpr uint32_t NOTIFY_UNIQUE_ID_MAX_SIZE = THREAD_UNIQUE_ID_MAX_SIZE * LOCAL_NOTIFY_MAX_NUM;
constexpr uint32_t NOTIFY_DEVCIE_ID_MAX_SIZE = 21  * LOCAL_NOTIFY_MAX_NUM;
constexpr uint32_t NAME_SIZE = 64;
struct ThreadMgrAicpuParam {
    u32 threadNum;
    char hcomId[HCOMID_MAX_SIZE];
    char threadParam[LOCAL_STREAM_MAX_NUM][THREAD_UNIQUE_ID_MAX_SIZE]; // 含序列化后thread信息，约40KB
    void* deviceHandle;
    u32 rsv1;
};

struct NotifyMgrAicpuParam {
    u32 notifyNum;
    char hcomId[HCOMID_MAX_SIZE];
    char notifyParam[NOTIFY_UNIQUE_ID_MAX_SIZE]; // 含序列化后notify信息
    void* deviceHandle;
    bool freeFlag;
    u32 rsv1;
};

namespace hccl {

struct ApiParamDef {
    uint64_t commContext{};
    char kernelName[NAME_SIZE] = {};
    char soName[NAME_SIZE] = {};
    char opName[NAME_SIZE] = {};

    ApiParamDef(const char *kName, const char *sName, const char *oName)
    {
        strncpy_s(kernelName, NAME_SIZE, kName, NAME_SIZE - 1);
        strncpy_s(soName, NAME_SIZE, sName, NAME_SIZE - 1);
        strncpy_s(opName, NAME_SIZE, oName, NAME_SIZE - 1);
    }
};

class AicpuLaunchMgr {
public:
    AicpuLaunchMgr() = default;
    ~AicpuLaunchMgr() = default;
    template <typename OpParam, typename ApiParam>
    static HcclResult KernelLaunch(OpParam &opParam, ApiParam &apiParam, rtStream_t aicpuInitStream);
    static HcclResult ThreadKernelLaunch(std::vector<std::shared_ptr<HcclThread>> &newThreads,
        const std::string commId, std::unique_ptr<ThreadHandle[]> &hostHandle, aclrtBinHandle binCustomHandle);
    static HcclResult NotifyKernelLaunchAlloc(std::vector<std::unique_ptr<LocalNotify>> &newNotifys,
        const std::string &commId, std::unique_ptr<NotifyHandle[]> &hostHandle, aclrtBinHandle binCustomHandle);
    static HcclResult NotifyKernelLaunchFree(std::vector<NotifyHandle> &aicpuNotifys, uint32_t notifyNum,
        const std::string &commId, aclrtBinHandle binCustomHandle);
    static HcclResult KernelLaunchAicpuCustom(uint64_t context, std::string kernelName, rtStream_t aicpuInitStream,
        aclrtBinHandle binCustomHandle);
private:
    HcclResult AiCpuStreamAllocAndGet(rtStream_t &aiCpuStream);
    static HcclResult PrepareAicpuNotifyParam(NotifyMgrAicpuParam &opParam, const std::string &commId,
        size_t notifyNum, bool freeFlag, void *deviceHandle);
    static HcclResult LaunchNotifyKernel(NotifyMgrAicpuParam &opParam, aclrtBinHandle binCustomHandle);
    Stream opStream_;
};
}
#endif