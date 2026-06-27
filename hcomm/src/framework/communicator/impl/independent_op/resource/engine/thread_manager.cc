/**
 * Copyright (c) 2025 Huawei Technologies Co., Ltd.
 * This program is free software, you can redistribute it and/or modify it under the terms and conditions of
 * CANN Open Software License Agreement Version 2.0 (the "License").
 * Please refer to the License for details. You may not use this file except in compliance with the License.
 * THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
 * INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
 * See LICENSE in the root of the software repository for the full text of the License.
 */

#include "thread_manager.h"
#include <cstring>
#include "aicpu_launch_manager.h"
#include "aicpu_operator_pub.h"
#include "independent_op.h"

namespace hccl {

HcclResult ThreadMgr::CommEngineToNotifyLoadType(CommEngine engine, NotifyLoadType &type)
{
    switch (engine) {
        case COMM_ENGINE_CPU:
        case COMM_ENGINE_CPU_TS:
            type =  NotifyLoadType::HOST_NOTIFY;
            break;
        case COMM_ENGINE_AICPU:
        case COMM_ENGINE_AICPU_TS:
            type =  NotifyLoadType::DEVICE_NOTIFY;
            break;
        default:
            HCCL_ERROR("[ThreadMgr] Unknown comm engine type: %d", engine);
            return HCCL_E_PARA;
    }
    return HCCL_SUCCESS;
}

HcclResult ThreadMgr::CommEngineToStreamType(CommEngine engine, StreamType &type)
{
    switch (engine) {
        case COMM_ENGINE_CPU:
        case COMM_ENGINE_CPU_TS:
            type = StreamType::STREAM_TYPE_ONLINE; // 单算子使用online，图模式使用offine
            break;
        case COMM_ENGINE_AICPU:
        case COMM_ENGINE_AICPU_TS:
            type = StreamType::STREAM_TYPE_DEVICE;
            break;
        // 暂不支持AIV、CCU
        case COMM_ENGINE_AIV:
        case COMM_ENGINE_CCU:
        default:
            HCCL_ERROR("[ThreadMgr] Unknown comm engine type: %d", engine);
            return HCCL_E_PARA;
    }
    return HCCL_SUCCESS;
}

ThreadMgr::ThreadMgr(uint32_t threadNum, uint32_t notifyNumPerThread, std::string commId, 
    aclrtBinHandle binHandle, const ManagerCallbacks& callbacks) : threadNum_(threadNum), notifyNumPerThread_(notifyNumPerThread), 
    commId_(commId), binHandle_(binHandle), callbacks_(callbacks){}

HcclResult ThreadMgr::HcclThreadAcquire(CommEngine engine, uint32_t threadNum,
    uint32_t notifyNumPerThread, ThreadHandle *threads)
{
    CHK_PTR_NULL(threads);
    std::lock_guard<std::mutex> lock(threadMutex_);

    HCCL_INFO("[ThreadMgr][%s] Hcom[%s] HcclThreadAcquire begin, max: engine[%d] threadNum[%u],"
        "notifyPerThread[%u], need: threadNum[%u], notifyPerThread[%u]",
        __func__, commId_.c_str(), engine, threadNum_, notifyNumPerThread_, threadNum, notifyNumPerThread);

    if (threadNum == 0) {
        HCCL_ERROR("[ThreadMgr][HcclThreadAcquire] threadNum is 0");
        return HCCL_E_PARA;
    }
    // 如果没设定最大值，设置一下
    uint64_t maxNotifyTotal = 0;
    if (threadNum_ == HCCL_COMM_THREADNUM_CONFIG_NOT_SET &&
        notifyNumPerThread_ == HCCL_COMM_NOTIFY_NUM_PER_THREAD_CONFIG_NOT_SET) {
        maxNotifyTotal = LOCAL_NOTIFY_MAX_NUM;
        threadNum_ = LOCAL_STREAM_MAX_NUM;
        notifyNumPerThread_ = LOCAL_NOTIFY_MAX_NUM;
    } else {
        maxNotifyTotal = static_cast<uint64_t>(threadNum_) * static_cast<uint64_t>(notifyNumPerThread_);
        maxNotifyTotal = maxNotifyTotal > LOCAL_NOTIFY_MAX_NUM ? LOCAL_NOTIFY_MAX_NUM : maxNotifyTotal;
    }
    uint32_t remainQuota = (threadNum_ > threads_.size()) ? (threadNum_ - threads_.size()) : 0;
    if (remainQuota == 0 || threadNum > remainQuota) {
        HCCL_ERROR("[ThreadMgr][%s] Threads quota exhausted: remainQuota[%u], need[%u].",
            __func__, remainQuota, threadNum);
        return HCCL_E_UNAVAIL;
    }

    const uint64_t used = usedNotifyNum_;
    uint64_t remainNotifyQuota = (maxNotifyTotal > used) ? (maxNotifyTotal - used) : 0;
    uint64_t needNotifyTotal = static_cast<uint64_t>(threadNum) * static_cast<uint64_t>(notifyNumPerThread);
    if (remainNotifyQuota < needNotifyTotal  || notifyNumPerThread > notifyNumPerThread_ ||
        maxNotifyTotal > LOCAL_NOTIFY_MAX_NUM) {
        HCCL_ERROR("[ThreadMgr][%s] Notify quota exhausted: remainQuota[%llu], total[%llu], used[%llu], need[%llu], " 
            "setPreNum[%u], allocPreNum[%u]", __func__, remainNotifyQuota, maxNotifyTotal, used, needNotifyTotal,
            notifyNumPerThread_, notifyNumPerThread);
        return HCCL_E_UNAVAIL;
    }

    HCCL_INFO("[ThreadMgr][%s] Hcom[%s] HcclThreadAcquire quota: engine[%d] threadNum[%llu], "
        "remainNotifyQuota[%u]", __func__, commId_.c_str(), engine, remainQuota, remainNotifyQuota);

    NotifyLoadType notifyLoadType;
    StreamType streamType;
    CHK_RET(CommEngineToNotifyLoadType(engine, notifyLoadType));
    CHK_RET(CommEngineToStreamType(engine, streamType));
    std::vector<std::shared_ptr<HcclThread>> newThreads;
    newThreads.reserve(threadNum);
    HcclResult ret = HCCL_E_INTERNAL;

    for (uint32_t i = 0; i < threadNum; ++i) {
        std::shared_ptr<HcclThread> handle;
        HCCL_INFO("[ThreadMgr][%s] Hcom[%s] HcclThread notifyLoadType[%u], streamType[%u]",
            __func__, commId_.c_str(), static_cast<int32_t>(notifyLoadType), static_cast<int32_t>(streamType));
        EXECEPTION_CATCH(handle = std::make_shared<HcclThread>(streamType, notifyNumPerThread, notifyLoadType),
            return HCCL_E_PTR);
        ret = handle->Init();
        if (ret != HCCL_SUCCESS) {
            HCCL_ERROR("[ThreadMgr][HcclThreadAcquire] Failed to init thread index %u", i);
            return ret;
        }
        usedNotifyNum_ += notifyNumPerThread;
        newThreads.emplace_back(std::move(handle));
    }

    // thread资源 AICPU侧展开
    std::unique_ptr<ThreadHandle[]> hostHandle;
    if (engine == COMM_ENGINE_AICPU || engine == COMM_ENGINE_AICPU_TS) {
        if (!callbacks_.getAicpuCommState()) {
            HcclResult ret = callbacks_.kernelLaunchAicpuCommInit();
            CHK_PRT_RET(ret != HCCL_SUCCESS, 
                HCCL_ERROR("[%s] kernelLaunchAicpuCommInit failed, return [%d].", __func__, ret), ret);
            callbacks_.setAicpuCommState(true);
        }
        EXECEPTION_CATCH(hostHandle = std::make_unique<ThreadHandle[]>(newThreads.size()),
            return HCCL_E_PTR);
        ret = AicpuLaunchMgr::ThreadKernelLaunch(newThreads, commId_, hostHandle, binHandle_);
        CHK_PRT_RET(ret != HCCL_SUCCESS,
            HCCL_ERROR("[ThreadMgr][HcclThreadAcquire] AiCpuKernelLaunch failed, return [%d].", ret), ret);
        for (size_t i = 0; i < newThreads.size(); ++i) {
            threads[i] = hostHandle[i];
            HCCL_INFO("[ThreadMgr][%s] aicpu threadArray[%u] = [%lu]", __func__, i, threads[i]);
        }
    } else {
        for (size_t i = 0; i < newThreads.size(); ++i) {
            threads[i] = reinterpret_cast<ThreadHandle>(newThreads[i].get());
            HCCL_INFO("[ThreadMgr][%s] host threadArray[%u] = [%lu]", __func__, i, threads[i]);
        }
    }
    threads_.insert(threads_.end(),
                    std::make_move_iterator(newThreads.begin()),
                    std::make_move_iterator(newThreads.end()));

    HCCL_INFO("[ThreadMgr][HcclThreadAcquire] Hcom[%s] HcclThreadAcquire done: engine[%d] threadNum[%u],"
        "notifyPerThread[%u]%s", commId_.c_str(), engine, threadNum, notifyNumPerThread,
        (engine == COMM_ENGINE_AICPU || engine == COMM_ENGINE_AICPU_TS) ? " (AICPU token ready)" : "");
    return HCCL_SUCCESS;
}

HcclResult ThreadMgr::HcclGetNotifyNumInThread(ThreadHandle thread, uint32_t *notifyNum)
{
    CHK_PTR_NULL(notifyNum);
    HcclThread* hcclThread = reinterpret_cast<HcclThread*>(thread);
    CHK_PTR_NULL(hcclThread);
    *notifyNum = hcclThread->GetNotifyNum();
    HCCL_INFO("[ThreadMgr] Hcom[%s] thread[%s] HcclGetNotifyNumInThread done: notifyPerThread[%u]",
        commId_.c_str(), hcclThread->GetUniqueId().c_str(), *notifyNum);
    return HCCL_SUCCESS;
}

HcclResult ThreadMgr::HcclThreadAcquireWithStream(CommEngine engine,
    rtStream_t stream, uint32_t notifyNum, ThreadHandle *thread)
{
    CHK_PTR_NULL(thread);
    NotifyLoadType notifyLoadType;
    CHK_RET(CommEngineToNotifyLoadType(engine, notifyLoadType));
    std::unique_ptr<HcclThread> handle;
    EXECEPTION_CATCH(handle = std::make_unique<HcclThread>(stream, notifyNum, notifyLoadType), return HCCL_E_PTR);
    CHK_RET(handle->Init());

    // 返回第一个句柄
    *thread = reinterpret_cast<ThreadHandle>(handle.get());
    std::lock_guard<std::mutex> lock(mainThreadMutex_);
    mainThread_.emplace(stream, std::move(handle));

    HCCL_INFO("[ThreadMgr] Hcom[%s] HcclThreadAcquireWithStream done: engine[%d] stream[%p],"
        "notifyNum[%u]", commId_.c_str(), engine, stream, notifyNum);
    return HCCL_SUCCESS;
}
}