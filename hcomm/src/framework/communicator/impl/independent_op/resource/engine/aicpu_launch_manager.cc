/**
 * Copyright (c) 2025 Huawei Technologies Co., Ltd.
 * This program is free software, you can redistribute it and/or modify it under the terms and conditions of
 * CANN Open Software License Agreement Version 2.0 (the "License").
 * Please refer to the License for details. You may not use this file except in compliance with the License.
 * THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
 * INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
 * See LICENSE in the root of the software repository for the full text of the License.
 */

#include "aicpu_launch_manager.h"
#include "adapter_rts_common.h"
#include "mem_device_pub.h"
#include "notify_manager.h"
#include "launch_aicpu.h"
#include "comm_configer.h"
#include <iomanip>

namespace hccl {
template <typename OpParam, typename ApiParam>
HcclResult AicpuLaunchMgr::KernelLaunch(OpParam &opParam, ApiParam &apiParam, rtStream_t aicpuInitStream)
{
    return HCCL_SUCCESS;
}

HcclResult AicpuLaunchMgr::KernelLaunchAicpuCustom(uint64_t context, std::string kernelName, rtStream_t aicpuInitStream,
    aclrtBinHandle binCustomHandle)
{
    struct InitTask {
        u64 context; // A矩阵地址，通信在前时为sendbuffer
        bool isCustom;
    };
    InitTask customInitTask = {0};

    // Step 1. 填充 customInitTask 中的 commContext
    customInitTask.context = context;
    customInitTask.isCustom = false;

    // Step 2. 启动 
    CHK_RET(AicpuAclKernelLaunch(aicpuInitStream, reinterpret_cast<void *>(&customInitTask),
            sizeof(customInitTask), binCustomHandle, kernelName, true, NOTIFY_DEFAULT_WAIT_TIME));
    return HCCL_SUCCESS;
}

HcclResult AicpuLaunchMgr::AiCpuStreamAllocAndGet(rtStream_t &aiCpuStream)
{
    if (opStream_.ptr() != nullptr) {
        HCCL_INFO("%s already alloc, stream id:%u", __func__, opStream_.id());
        aiCpuStream = opStream_.ptr();
        return HCCL_SUCCESS;
    }

    constexpr u32 aicpuStreamMode = 1; // 单独申请的kernel流，使能遇错即停，避免出错后流卡住不退
    opStream_ = Stream(StreamType::STREAM_TYPE_ONLINE);
    CHK_RET(hrtStreamSetMode(opStream_.ptr(), aicpuStreamMode));
    aiCpuStream = opStream_.ptr();
    HCCL_RUN_INFO("[AicpuLaunchMgr][%s] alloc success, stream id:%u, aicpuStreamMode:%u",
                    __func__, opStream_.id(), aicpuStreamMode);
    return HCCL_SUCCESS;
}

HcclResult AicpuLaunchMgr::ThreadKernelLaunch(std::vector<std::shared_ptr<HcclThread>> &newThreads,
    const std::string commId, std::unique_ptr<ThreadHandle[]> &hostHandle, aclrtBinHandle binCustomHandle)
{
    CHK_PRT_RET(newThreads.size() > LOCAL_STREAM_MAX_NUM,
        HCCL_ERROR("[AicpuLaunchMgr][%s] streamNum[%zu] > LOCAL_STREAM_MAX_NUM[%u]", __func__,
        newThreads.size(), LOCAL_STREAM_MAX_NUM), HCCL_E_PARA);

    // Step 1. 创建局部 stream
    Stream localStream(StreamType::STREAM_TYPE_ONLINE);
    constexpr u32 aicpuStreamMode = 1;
    CHK_RET(hrtStreamSetMode(localStream.ptr(), aicpuStreamMode));

    // Step 2. 填写 opParam
    ThreadMgrAicpuParam opParam{};
    (void)memset_s(&opParam, sizeof(opParam), 0, sizeof(opParam));
    opParam.threadNum = newThreads.size();
    errno_t sRet = strncpy_s(opParam.hcomId, HCOMID_MAX_SIZE, commId.c_str(), commId.length());
    CHK_PRT_RET(sRet != EOK, HCCL_ERROR("[AicpuLaunchMgr][%s] call strncpy_s failed, return [%d].", __func__, sRet),
        HCCL_E_MEMORY);
    opParam.hcomId[HCOMID_MAX_SIZE - 1] = '\0';
    for (u32 i = 0; i < opParam.threadNum; ++i) {
        const std::string &uid = newThreads[i]->GetUniqueId();
        size_t copyLen = std::min(uid.size(), static_cast<size_t>(THREAD_UNIQUE_ID_MAX_SIZE));
        sRet = memcpy_s(opParam.threadParam[i], THREAD_UNIQUE_ID_MAX_SIZE, uid.c_str(), copyLen);
        CHK_PRT_RET(sRet != EOK,
            HCCL_ERROR("[AicpuLaunchMgr][%s] call memcpy_s failed, return [%d].", __func__, sRet),
            HCCL_E_MEMORY);
        opParam.threadParam[i][THREAD_UNIQUE_ID_MAX_SIZE - 1] = '\0';
        // 打印每个字节
        if (UNLIKELY(HcclCheckLogLevel(HCCL_LOG_INFO))) {
            std::ostringstream oss;
            oss << "threadParam[" << i << "] raw bytes: ";
            for (u32 j = 0; j < THREAD_UNIQUE_ID_MAX_SIZE; ++j) {
                oss << std::hex << std::setw(2) << std::setfill('0')
                    << static_cast<unsigned int>(static_cast<unsigned char>(opParam.threadParam[i][j])) << " ";
            }
            HCCL_INFO("[AicpuLaunchMgr][%s] %s", __func__, oss.str().c_str());
        }
    }

    size_t handleLen = sizeof(ThreadHandle) * newThreads.size();
    DeviceMem deviceHandle = DeviceMem::alloc(handleLen);
    CHK_SMART_PTR_NULL(deviceHandle);
    opParam.deviceHandle = deviceHandle.ptr();

    // Step 3. 调用 KernelLaunch，传入本地流
    DeviceMem addr = DeviceMem::alloc(sizeof(opParam));
    CHK_RET(hrtMemSyncCopy(addr.ptr(), sizeof(opParam), &opParam, sizeof(opParam),
        HcclRtMemcpyKind::HCCL_RT_MEMCPY_KIND_HOST_TO_DEVICE));
    uint64_t context = reinterpret_cast<uint64_t>(addr.ptr());
    HcclResult ret = KernelLaunchAicpuCustom(context, "RunAicpuIndOpThreadInit", localStream.ptr(), binCustomHandle);
    CHK_PRT_RET(ret != HCCL_SUCCESS,
        HCCL_ERROR("[AicpuLaunchMgr][%s] KernelLaunch failed, return [%d].", __func__, ret), ret);

    // Step 4. 等待流完成，localStream生命周期随函数结束自动销毁
    CHK_RET(hcclStreamSynchronize(localStream.ptr(), CommConfiger::GetInstance().GetCommConfigExecTimeOut(commId)));

    // Step 5. 返回device侧句柄
    CHK_RET(hrtMemSyncCopy(hostHandle.get(), handleLen, opParam.deviceHandle, handleLen,
        HcclRtMemcpyKind::HCCL_RT_MEMCPY_KIND_DEVICE_TO_HOST));

    return HCCL_SUCCESS;
}

// 准备 opParam
HcclResult AicpuLaunchMgr::PrepareAicpuNotifyParam(NotifyMgrAicpuParam &opParam,
    const std::string &commId, size_t notifyNum, bool freeFlag, void *deviceHandle)
{
    (void)memset_s(&opParam, sizeof(opParam), 0, sizeof(opParam));

    opParam.notifyNum = notifyNum;
    opParam.freeFlag = freeFlag;
    opParam.deviceHandle = deviceHandle;

    errno_t sRet = strncpy_s(opParam.hcomId, HCOMID_MAX_SIZE, commId.c_str(), commId.length());
    CHK_PRT_RET(sRet != EOK,
        HCCL_ERROR("[AicpuLaunchMgr][PrepareAicpuNotifyParam] strncpy_s failed, ret[%d]", sRet),
        HCCL_E_MEMORY);
    opParam.hcomId[HCOMID_MAX_SIZE - 1] = '\0';
    return HCCL_SUCCESS;
}

HcclResult AicpuLaunchMgr::LaunchNotifyKernel(NotifyMgrAicpuParam &opParam, aclrtBinHandle binCustomHandle)
{
    Stream localStream(StreamType::STREAM_TYPE_ONLINE);
    constexpr u32 aicpuStreamMode = 1;
    CHK_RET(hrtStreamSetMode(localStream.ptr(), aicpuStreamMode));

    DeviceMem addr = DeviceMem::alloc(sizeof(opParam));
    CHK_RET(hrtMemSyncCopy(addr.ptr(), sizeof(opParam), &opParam, sizeof(opParam),
        HcclRtMemcpyKind::HCCL_RT_MEMCPY_KIND_HOST_TO_DEVICE));
    uint64_t context = reinterpret_cast<uint64_t>(addr.ptr());
    HcclResult ret = KernelLaunchAicpuCustom(context, "RunAicpuIndOpNotify", localStream.ptr(), binCustomHandle);
    CHK_PRT_RET(ret != HCCL_SUCCESS,
        HCCL_ERROR("[AicpuLaunchMgr][LaunchNotifyKernel] KernelLaunch failed, ret[%d]", ret), ret);
    CHK_RET(hcclStreamSynchronize(localStream.ptr(), CommConfiger::GetInstance().GetCommConfigExecTimeOut(opParam.hcomId)));
    return HCCL_SUCCESS;
}

HcclResult AicpuLaunchMgr::NotifyKernelLaunchAlloc(std::vector<std::unique_ptr<LocalNotify>> &newNotifys,
    const std::string &commId, std::unique_ptr<NotifyHandle[]> &hostHandle, aclrtBinHandle binCustomHandle)
{
    size_t handleLen = sizeof(NotifyHandle) * newNotifys.size();
    DeviceMem deviceHandle = DeviceMem::alloc(handleLen);
    CHK_SMART_PTR_NULL(deviceHandle);

    NotifyMgrAicpuParam opParam;
    CHK_RET(PrepareAicpuNotifyParam(opParam, commId, newNotifys.size(), false, deviceHandle.ptr()));
    std::string uid = NotifyManager::GetBinNotifys(newNotifys, NotifyLoadType::DEVICE_NOTIFY);
    if (UNLIKELY(uid.empty())) {
        HCCL_ERROR("[AicpuLaunchMgr][%s] uid is empty.", __func__, HCCL_E_MEMORY);
        return HCCL_E_MEMORY;
    }
    size_t copyLen = std::min(uid.size(), static_cast<size_t>(NOTIFY_UNIQUE_ID_MAX_SIZE));
    errno_t sRet = memcpy_s(opParam.notifyParam, NOTIFY_UNIQUE_ID_MAX_SIZE, uid.c_str(), copyLen);
    CHK_PRT_RET(sRet != EOK, HCCL_ERROR("[AicpuLaunchMgr][%s] call memcpy_s failed, return [%d].", __func__, sRet),
        HCCL_E_MEMORY);
    // 打印每个字节
    if (UNLIKELY(HcclCheckLogLevel(HCCL_LOG_INFO))) {
        std::ostringstream oss;
        oss << "notifyParam" << " raw bytes: ";
        for (u32 i = 0; i < NOTIFY_UNIQUE_ID_MAX_SIZE; ++i) {
            oss << std::hex << std::setw(2) << std::setfill('0')
                << static_cast<unsigned int>(static_cast<unsigned char>(opParam.notifyParam[i])) << " ";
        }
        HCCL_INFO("[AicpuLaunchMgr][%s] %s", __func__, oss.str().c_str());
    }

    CHK_RET(LaunchNotifyKernel(opParam, binCustomHandle));

    CHK_RET(hrtMemSyncCopy(hostHandle.get(), handleLen, opParam.deviceHandle,
        handleLen, HcclRtMemcpyKind::HCCL_RT_MEMCPY_KIND_DEVICE_TO_HOST));
    HCCL_RUN_INFO("[AicpuLaunchMgr][%s] notify alloc success, commid[%s], notifyNum[%u]",
        __func__, commId.c_str(), newNotifys.size());
    return HCCL_SUCCESS;
}

HcclResult AicpuLaunchMgr::NotifyKernelLaunchFree(std::vector<NotifyHandle> &aicpuNotifys, uint32_t notifyNum,
    const std::string &commId, aclrtBinHandle binCustomHandle)
{
    size_t handleLen = sizeof(NotifyHandle) * notifyNum;
    DeviceMem deviceHandle = DeviceMem::alloc(handleLen);
    CHK_SMART_PTR_NULL(deviceHandle);

    CHK_RET(hrtMemSyncCopy(deviceHandle.ptr(), handleLen, aicpuNotifys.data(),
        handleLen, HcclRtMemcpyKind::HCCL_RT_MEMCPY_KIND_HOST_TO_DEVICE));

    NotifyMgrAicpuParam opParam;
    CHK_RET(PrepareAicpuNotifyParam(opParam, commId, notifyNum, true, deviceHandle.ptr()));

    CHK_RET(LaunchNotifyKernel(opParam, binCustomHandle));
    HCCL_RUN_INFO("[AicpuLaunchMgr][%s] notify free kernalLaunch success, commid[%s], notifyNum[%u]",
        __func__, commId.c_str(), aicpuNotifys.size());
    return HCCL_SUCCESS;
}
}