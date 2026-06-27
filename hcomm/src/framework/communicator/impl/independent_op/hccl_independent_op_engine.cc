/**
 * Copyright (c) 2025 Huawei Technologies Co., Ltd.
 * This program is free software, you can redistribute it and/or modify it under the terms and conditions of
 * CANN Open Software License Agreement Version 2.0 (the "License").
 * Please refer to the License for details. You may not use this file except in compliance with the License.
 * THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
 * INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
 * See LICENSE in the root of the software repository for the full text of the License.
 */

#include <atomic>
#include <unordered_map>
#include <mutex>
#include <memory>
#include <vector>
#include <string>
#include "hccl_api.h"
#include "hccl_mem.h"
#include "stream_pub.h"
#include "hccl_communicator.h"
#include "hccl_comm_pub.h"
#include "hccl_independent_common.h"

HcclResult HcclGetNotifyNumInThread(HcclComm comm, ThreadHandle thread,
    CommEngine engine, uint32_t *notifyNum)
{
    CHK_PRT_RET(comm == nullptr,  HCCL_ERROR("[%s] comm is null", __func__), HCCL_E_PTR);
    CHK_PRT_RET(!IsValidCommEngine(engine), 
        HCCL_ERROR("[%s] commEngine[%d] is invalid", __func__, static_cast<int32_t>(engine)), HCCL_E_PARA);
    CHK_PRT_RET(notifyNum == nullptr,  HCCL_ERROR("[%s] notifyNum is null", __func__), HCCL_E_PTR);

    auto* hcclComm = static_cast<hccl::hcclComm*>(comm);
    std::string commId = hcclComm->GetIdentifier();
    HCCL_RUN_INFO("Entry-%s:comm[%s] engine[%u]", __func__, commId.c_str(), engine);
    auto& engineResMgr = hcclComm->GetIndependentOp().GetCommEngineResMgr();
    HcclResult ret = engineResMgr.HcclGetNotifyNumInThread(thread, engine, notifyNum);
    if (ret != HCCL_SUCCESS) {
        HCCL_ERROR("[HcclGetNotifyNumInThread] Failed to get notifyNum for engine[%d] ret[%d]", engine, ret);
        return ret;
    }
    HCCL_INFO("[HcclGetNotifyNumInThread] threads for engine[%d], notifyNum[%u]", engine, *notifyNum);
    return HCCL_SUCCESS;
}

HcclResult HcclThreadAcquire(HcclComm comm, CommEngine engine, uint32_t threadNum,
    uint32_t notifyNumPerThread, ThreadHandle *threads)
{
    CHK_PRT_RET(comm == nullptr,  HCCL_ERROR("[%s] comm is null", __func__), HCCL_E_PTR);
    CHK_PRT_RET(threads == nullptr,  HCCL_ERROR("[%s] threads is null", __func__), HCCL_E_PTR);
    CHK_PRT_RET(!IsValidCommEngine(engine), 
        HCCL_ERROR("[%s] commEngine[%d] is invalid", __func__, static_cast<int32_t>(engine)), HCCL_E_PARA);

    auto* hcclComm = static_cast<hccl::hcclComm*>(comm);
    std::string commId = hcclComm->GetIdentifier();
    HCCL_RUN_INFO("Entry-%s:comm[%s] engine[%u] reqThreadNum[%u] notifyNumPerThread[%u]",
        __func__, commId.c_str(), engine, threadNum, notifyNumPerThread);

    auto& engineResMgr = hcclComm->GetIndependentOp().GetCommEngineResMgr();
    HcclResult ret = engineResMgr.HcclThreadAcquire(engine, threadNum, notifyNumPerThread, threads);
    if (ret != HCCL_SUCCESS) {
        HCCL_ERROR("[%s] Failed to create threads for engine[%d], threadNum[%u], notifyNumPerThread[%u]",
            __func__, engine, threadNum, notifyNumPerThread);
        return ret;
    }

    HCCL_INFO("[%s] Allocated %u threads for engine[%d], notifyPerThread[%u]", __func__,
              threadNum, engine, notifyNumPerThread);
    return HCCL_SUCCESS;
}

HcclResult HcclThreadAcquireWithStream(HcclComm comm, CommEngine engine,
    aclrtStream stream, uint32_t notifyNum, ThreadHandle *thread)
{
    CHK_PTR_NULL(comm);
    CHK_PTR_NULL(stream);
    CHK_PTR_NULL(thread);

    auto* hcclComm = static_cast<hccl::hcclComm*>(comm);
    std::string commId = hcclComm->GetIdentifier();
    HCCL_RUN_INFO("Entry-%s:comm[%s] engine[%u] notifyNum[%u] stream[%p]",
        __func__, commId.c_str(), engine, notifyNum, stream);
    auto& engineResMgr = hcclComm->GetIndependentOp().GetCommEngineResMgr();
    HcclResult ret = engineResMgr.HcclThreadAcquireWithStream(engine, stream, notifyNum, thread);
    if (ret != HCCL_SUCCESS) {
        HCCL_ERROR("[HcclThreadAcquireWithStream] Failed to create thread for engine[%d]", engine);
        return ret;
    }

    HCCL_INFO("[HcclThreadAcquireWithStream] Allocated thread for engine[%d], stream[%p], notifyNum[%u]",
              engine, stream, notifyNum);
    return HCCL_SUCCESS;
}

HcclResult HcclAllocNotify(HcclComm comm, CommEngine commEngine, NotifyType notifyType, uint32_t notifyNum,
    NotifyHandle **notifyHandleList)
{
    CHK_PRT_RET(comm == nullptr, HCCL_ERROR("[%s] comm is null", __func__), HCCL_E_PARA);
    CHK_PRT_RET(!IsValidCommEngine(commEngine), 
        HCCL_ERROR("[%s] commEngine[%u] is invalid", __func__, commEngine), HCCL_E_PARA);
    CHK_PRT_RET(!IsValidNotify(notifyType), 
        HCCL_ERROR("[%s] notifyType[%u] is invalid", __func__, notifyType), HCCL_E_PARA);
    CHK_PRT_RET(notifyNum > NOTIFY_MAX_NUM || notifyNum == 0, 
        HCCL_ERROR("[%s] notifyNum[%u] is invalid", __func__, notifyNum), HCCL_E_PARA);
    CHK_PRT_RET(notifyHandleList == nullptr, HCCL_ERROR("[%s] notifyHandleList is null", __func__), HCCL_E_PARA);
    CHK_PRT_RET(*notifyHandleList != nullptr, HCCL_ERROR("[%s] notifyHandleList is not null", __func__), HCCL_E_PARA);

    if (commEngine == CommEngine::COMM_ENGINE_CPU || commEngine == CommEngine::COMM_ENGINE_CPU_TS) {
        if (notifyType != NotifyType:: NOTIFY_TYPE_RTS_NOTIFY) {
            HCCL_ERROR("[%s] commEngine[%u] and notifyType[%u] are mismatch",  __func__, commEngine, notifyType);
            return HCCL_E_PARA;
        }
    } else {
        if (notifyType != NotifyType:: NOTIFY_TYPE_DEVICE_MEM) {
            HCCL_ERROR("[%s] commEngine[%u] and notifyType[%u] are mismatch",  __func__, commEngine, notifyType);
            return HCCL_E_PARA;
        }
    }
 
    auto* hcclComm = static_cast<hccl::hcclComm*>(comm);
    std::string commId = hcclComm->GetIdentifier();
    HCCL_RUN_INFO("Entry-%s:comm[%s] commEngine[%u] notifyType[%u] notifyNum[%p]",
        __func__, commId.c_str(), commEngine, notifyType, notifyNum);
    auto& engineResMgr = hcclComm->GetIndependentOp().GetCommEngineResMgr();
    HcclResult ret = engineResMgr.HcclAllocNotify(commEngine, notifyType, notifyNum, notifyHandleList);
    if (ret != HCCL_SUCCESS) {
        HCCL_ERROR("[%s] Failed to create notify for commEngine[%d]",  __func__, commEngine);
        return ret;
    }
 
    HCCL_RUN_INFO("[%s] Allocated notify for commEngine[%d], notifyType[%p], notifyNum[%u]", __func__,
        commEngine, notifyType, notifyNum);
    return HCCL_SUCCESS;
}
 
HcclResult HcommFreeNotify(HcclComm comm, uint32_t notifyNum, NotifyHandle *notifyHandleList)
{
    CHK_PRT_RET(comm == nullptr, HCCL_ERROR("[%s] comm is null", __func__), HCCL_E_PARA);
    CHK_PRT_RET(notifyHandleList == nullptr, HCCL_ERROR("[%s] notifyHandleList is null", __func__), HCCL_E_PARA);
    CHK_PRT_RET(notifyNum > NOTIFY_MAX_NUM || notifyNum == 0, 
        HCCL_ERROR("[%s] notifyNum[%u] is invalid", __func__, notifyNum), HCCL_E_PARA);
    auto* hcclComm = static_cast<hccl::hcclComm*>(comm);
    std::string commId = hcclComm->GetIdentifier();
    HCCL_RUN_INFO("Entry-%s:comm[%s] notifyNum[%u]", __func__, commId.c_str(), notifyNum);
    auto& engineResMgr = hcclComm->GetIndependentOp().GetCommEngineResMgr();
    HcclResult ret = engineResMgr.HcommFreeNotify(notifyNum, notifyHandleList);
    if (ret != HCCL_SUCCESS) {
        HCCL_ERROR("[%s] Failed to free notify",  __func__);
        return ret;
    }
 
    HCCL_RUN_INFO("[%s] Free notify for notifyNum[%u]", __func__, notifyNum);
    return HCCL_SUCCESS;
}