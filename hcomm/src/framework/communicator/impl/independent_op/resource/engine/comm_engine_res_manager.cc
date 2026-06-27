/**
 * Copyright (c) 2025 Huawei Technologies Co., Ltd.
 * This program is free software, you can redistribute it and/or modify it under the terms and conditions of
 * CANN Open Software License Agreement Version 2.0 (the "License").
 * Please refer to the License for details. You may not use this file except in compliance with the License.
 * THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
 * INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
 * See LICENSE in the root of the software repository for the full text of the License.
 */

#include "comm_engine_res_manager.h"

namespace hccl {
CommEngineResMgr::CommEngineResMgr(){};

HcclResult CommEngineResMgr::Init(uint32_t threadNum, uint32_t notifyNumPerThread,
    const std::string& commId, const aclrtBinHandle binHandle, const ManagerCallbacks& callbacks)
{
    std::lock_guard<std::mutex> lock(mtx_);
    HCCL_INFO("[CommEngineResMgr][%s] Hcom[%s] threadNum[%u], notifyPerThread[%u]", 
        __func__, commId.c_str(), threadNum, notifyNumPerThread);
    if (!threadMgr_) {
        EXECEPTION_CATCH(threadMgr_ = std::make_unique<ThreadMgr>(threadNum, notifyNumPerThread, commId, binHandle, callbacks),
            return HCCL_E_PTR);
    }
    if (!notifyMgr_) {
        EXECEPTION_CATCH(notifyMgr_ = std::make_unique<NotifyManager>(commId, binHandle, callbacks),
            return HCCL_E_PTR);
    }
    return HCCL_SUCCESS;
}

HcclResult CommEngineResMgr::HcclThreadAcquire(CommEngine engine, uint32_t threadNum,
    uint32_t notifyNumPerThread, ThreadHandle *threads)
{
    CHK_SMART_PTR_NULL(threadMgr_);
    uint32_t setThreadNum = threadMgr_->GetThreadNum();
    uint32_t setNotifyNumPerThread = threadMgr_->GetNotifyNumPerThread();
    CHK_PRT_RET(threadNum > setThreadNum,  HCCL_ERROR("[%s] Alloced thread num[%u] more than num[%u] in config", 
        __func__, threadNum, setThreadNum), HCCL_E_PARA);
    CHK_PRT_RET(notifyNumPerThread > setNotifyNumPerThread,  HCCL_ERROR("[%s] Alloced preNotify num[%u] more than "
        "num[%u] in config", __func__, notifyNumPerThread, setNotifyNumPerThread), HCCL_E_PARA);
    return threadMgr_->HcclThreadAcquire(engine, threadNum, notifyNumPerThread, threads);
}

HcclResult CommEngineResMgr::HcclThreadAcquireWithStream(CommEngine engine,
        rtStream_t stream, uint32_t notifyNum, ThreadHandle *thread)
{
    CHK_SMART_PTR_NULL(threadMgr_);
    return threadMgr_->HcclThreadAcquireWithStream(engine, stream, notifyNum, thread);
}

HcclResult CommEngineResMgr::HcclGetNotifyNumInThread(ThreadHandle thread, CommEngine engine, uint32_t *notifyNum)
{
    CHK_SMART_PTR_NULL(threadMgr_);
    return threadMgr_->HcclGetNotifyNumInThread(thread, notifyNum);
}

HcclResult CommEngineResMgr::HcclAllocNotify(CommEngine commEngine, NotifyType notifyType, uint32_t notifyNum,
    NotifyHandle **notifyHandleList)
{
    CHK_SMART_PTR_NULL(threadMgr_);
    return notifyMgr_->HcclAllocNotify(commEngine, notifyType, notifyNum, notifyHandleList);
}

HcclResult CommEngineResMgr::HcommFreeNotify(uint32_t notifyNum, NotifyHandle *notifyHandleList)
{
    CHK_SMART_PTR_NULL(threadMgr_);
    return notifyMgr_->HcommFreeNotify(notifyNum, notifyHandleList);
}
}