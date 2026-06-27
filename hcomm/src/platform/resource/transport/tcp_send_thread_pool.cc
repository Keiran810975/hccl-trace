/**
 * Copyright (c) 2025 Huawei Technologies Co., Ltd.
 * This program is free software, you can redistribute it and/or modify it under the terms and conditions of
 * CANN Open Software License Agreement Version 2.0 (the "License").
 * Please refer to the License for details. You may not use this file except in compliance with the License.
 * THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
 * INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
 * See LICENSE in the root of the software repository for the full text of the License.
 */

#include <array>
#include <mutex>

#include "transport_heterog_event_tcp.h"
#include "log.h"
#include "adapter_hal.h"
#include "tcp_send_thread_pool.h"

using namespace std;
namespace hccl {
constexpr int BIND_MIN_DCPU_NUM = 1;
constexpr int HOST_WORKER_THREAD_NUM = 2;
constexpr int DEV_WORKER_THREAD_NUM = 1;
constexpr uint32_t HOST = 1;

array<mutex, MAX_THREAD_SERIAL> TcpSendThreadPool::threadMutexs_;

HcclResult TcpSendThreadPool::SetAffinity(u32 devId, u32 cpuId)
{
    s32 ret = 0;
    cpu_set_t mask;
    cpu_set_t get;

    // 设置线程CPU亲和力
    CPU_ZERO(&mask);
    CPU_SET(cpuId, &mask);
    ret = pthread_setaffinity_np(pthread_self(), sizeof(mask), &mask);
    CHK_PRT_RET(ret != 0, HCCL_ERROR("[SetAffinity]could not set CPU affinity, ret[%d], strerror[%s]",
        ret, strerror(errno)), HCCL_E_SYSCALL);

    // 获取线程cpu亲和力
    CPU_ZERO(&get);
    ret = pthread_getaffinity_np(pthread_self(), sizeof(get), &get);
    CHK_PRT_RET(ret != 0, HCCL_ERROR("[SetAffinity]could not get CPU affinity, ret[%d], strerror[%s]",
        ret, strerror(errno)), HCCL_E_SYSCALL);

    if (CPU_ISSET(cpuId, &get)) {
        HCCL_INFO("[SetAffinity]dev is %d thread %llu is running in processor %d", devId, pthread_self(), cpuId);
    } else {
        HCCL_WARNING("[SetAffinity]dev is %d thread %llu is not running in processor %d", devId, pthread_self(), cpuId);
    }

    return HCCL_SUCCESS;
}

HcclResult TcpSendThreadPool::BindDataCpu(unsigned int devId)
{
    HCCL_INFO("START BindDataCpu");
    s32 cpuId;
    int64_t cCpuNum = 0;
    int64_t dCpuNum = 0;
    int64_t aCpuNum = 0;
    int64_t cpuNum = 0;
    uint32_t info = 0;
    uint32_t numDev = 0;

    // 当前位于host侧时不做绑核直接返回
    CHK_RET(hrtDrvGetPlatformInfo(&info));
    if (info == HOST) {
        HCCL_WARNING("host not need bind cpu, info: %u", info);
        return HCCL_SUCCESS;
    }

    // 获取当前os的device数量
    CHK_RET(hrtDrvGetDevNum(&numDev));
    if (numDev == 0) {
        HCCL_WARNING("no device need bind cpu, device num %u", numDev);
        return HCCL_SUCCESS;
    }

    // 获取data cpu数量
    CHK_RET(hrtHalGetDeviceInfo(devId, MODULE_TYPE_DCPU, INFO_TYPE_CORE_NUM, &dCpuNum));

    // dCpuNum < 1，无需绑核直接返回
    if (dCpuNum < BIND_MIN_DCPU_NUM) {
        HCCL_WARNING("data Cpu num %d, device not need bind cpu", dCpuNum);
        return HCCL_SUCCESS;
    }

    // 获取ctrl cpu的num
    CHK_RET(hrtHalGetDeviceInfo(devId, MODULE_TYPE_CCPU, INFO_TYPE_CORE_NUM, &cCpuNum));

    // 获取ai cpu的num
    CHK_RET(hrtHalGetDeviceInfo(devId, MODULE_TYPE_AICPU, INFO_TYPE_CORE_NUM, &aCpuNum));

    // 计算单个device上的核数
    cpuNum = cCpuNum + dCpuNum + aCpuNum;
    HCCL_INFO("halGetDeviceInf devId = %u, devNum = %u ccpu = %lld dcpu = %lld acpu = %lld cpu_num = %lld",
        devId, numDev, cCpuNum, dCpuNum, aCpuNum, cpuNum);

    cpuId = (devId % numDev) * cpuNum + cCpuNum;

    // 进行绑核
    CHK_RET(hrtHalBindCgroup(BIND_DATACPU_CGROUP));

    CHK_RET(SetAffinity(devId, cpuId));

    HCCL_INFO("devId[%u] bind data cpu[%u] success.", devId, cpuId);
    return HCCL_SUCCESS;
}

u32 TcpSendThreadPool::GetThreadNum()
{
    u32 threadNum;
    uint32_t info = 0;

    // 区分头节点还是加速节点
    CHK_RET(hrtDrvGetPlatformInfo(&info));
    if (info != 0) {
        threadNum = DEV_WORKER_THREAD_NUM; // 暂启用一条线程
        HCCL_INFO("hrtDrvGetPlatformInfo get info %u, Head node\n", info);
    } else {
        threadNum = DEV_WORKER_THREAD_NUM;
    }

    return threadNum;
}

TcpSendThreadPool::TcpSendThreadPool()
    : threadNum_(0), isRunning_(false), initCount_(0), devId_(0)
{
}

TcpSendThreadPool::~TcpSendThreadPool()
{
    if (initCount_ != 0) {
        HCCL_WARNING("TcpSendThreadPool initCount_ %d not zore", initCount_);
        initCount_ = 0;
    }
    (void)Deinit();
}

HcclResult TcpSendThreadPool::Init(u32 devId)
{
    if (initCount_ == 0 && !isRunning_) {
        devId_ = devId;
        isRunning_ = true;
        threadNum_ = GetThreadNum();
        threads_.resize(threadNum_);
        TaskQueueManager_.resize(threadNum_);
        for (u32 i = 0; i < threadNum_; i++) {
            TagTaskQueue mainThreadTaskQueue;
            TagTaskQueue swapThreadTaskQueue;
            {
                lock_guard<mutex> threadLock(threadMutexs_[i]);
                TaskQueueManager_[i].taskQueues = make_pair(mainThreadTaskQueue, swapThreadTaskQueue);
                TaskQueueManager_[i].threadTaskQueuePtr = &TaskQueueManager_[i].taskQueues.first;
            }
            EXECEPTION_CATCH((threads_[i] = make_unique<thread>(&TcpSendThreadPool::RunTask, this, i)),
                return HCCL_E_PTR);
        }
    }
    initCount_++;
    HCCL_DEBUG("[TcpSendThreadPool][Init]call Init threadNum_[%u] initCount_[%u]", threadNum_, initCount_);

    return HCCL_SUCCESS;
}

HcclResult TcpSendThreadPool::Deinit()
{
    if (initCount_ == 0) {
        isRunning_ = false;
        cond_.notify_all();

        for (auto &ptr : threads_) {
            if (ptr != nullptr && ptr->joinable()) {
                ptr->join();
                ptr = nullptr;
            }
        }
        threads_.clear();
        TaskQueueManager_.clear();
    } else if (initCount_ > 0) {
        initCount_--;
    } else {
        HCCL_WARNING("[TcpSendThreadPool][Deinit] initCount_[%d] ERROR", initCount_);
    }

    return HCCL_SUCCESS;
}

HcclResult TcpSendThreadPool::AddSendTask(HcclRequestInfo *request)
{
    CHK_PTR_NULL(request);
    HCCL_DEBUG("AddSendTask request[%p] tag[%d]", request, request->transportRequest.epParam.dst.tag);
    s32 tag = request->transportRequest.epParam.dst.tag;
    {
        lock_guard<mutex> threadLock(threadMutexs_[tag % threadNum_]);
        TagTaskQueue *ptr = TaskQueueManager_[tag % threadNum_].threadTaskQueuePtr;
        CHK_PTR_NULL(ptr);
        auto &&iter = ptr->emplace(tag, queue<HcclRequestInfo *>());
        iter.first->second.push(request);
    }

    cond_.notify_all();

    return HCCL_SUCCESS;
}

HcclResult TcpSendThreadPool::RunTask(u32 serialNum)
{
    if (BindDataCpu(devId_) != HCCL_SUCCESS) {
        HCCL_WARNING("send thread bind cpu failed!!!");
    }

    HCCL_DEBUG("threadSerial[%u]", serialNum);
    TagTaskQueue *sendWorkQueue = nullptr;

    while (isRunning_) {
        unique_lock<mutex> threadLock(threadMutexs_[serialNum]);
        while (isRunning_ && ThreadTaskQueueAddTask(serialNum, sendWorkQueue)) {
            cond_.wait(threadLock);
        }
        threadLock.unlock();
        if (isRunning_) {
            CHK_RET(LoadBalancing(sendWorkQueue));
        }
    }

    return HCCL_SUCCESS;
}

HcclResult TcpSendThreadPool::SendWork(queue<HcclRequestInfo *>& requestArray, bool &sendComplete)
{
    bool envCompleted = true;  // 信封数据是否完全发送成功
    bool tranCompleted = true;  // 数据是否完全发送
    while (!requestArray.empty()) {
        HcclRequestInfo *request = requestArray.front();
        CHK_RET(static_cast<TransportHeterogEventTcp*>(request->transportHandle)->SendNoBlock(
            request->transportRequest.transData, request->transportRequest.epParam,
            request->transportRequest.envoffset, request->transportRequest.tranoffset,
            envCompleted, tranCompleted));
        if (envCompleted && tranCompleted) { // 发完出队
            CHK_RET(static_cast<TransportHeterogEventTcp*>(request->transportHandle)->ReportSendComp(request));
            requestArray.pop(); // 删除
        } else {
            sendComplete = false;
            break;
        }
    }

    return HCCL_SUCCESS;
}

bool TcpSendThreadPool::ThreadTaskQueueAddTask(u32 &threadSerial, TagTaskQueue* &sendWorkQueue)
{
    bool threadTaskQueueEmpty = true;
    for (auto &iter : *(TaskQueueManager_[threadSerial].threadTaskQueuePtr)) {
        if (!iter.second.empty()) {
            sendWorkQueue = TaskQueueManager_[threadSerial].threadTaskQueuePtr;
            TaskQueueManager_[threadSerial].threadTaskQueuePtr =
                &TaskQueueManager_[threadSerial].taskQueues.first ==
                TaskQueueManager_[threadSerial].threadTaskQueuePtr ?
                &TaskQueueManager_[threadSerial].taskQueues.second : &TaskQueueManager_[threadSerial].taskQueues.first;
            threadTaskQueueEmpty = false;
            break;
        }
    }

    return threadTaskQueueEmpty;
}

HcclResult TcpSendThreadPool::LoadBalancing(TagTaskQueue *&sendWorkQueue)
{
    while (true) {
        if (sendWorkQueue == nullptr) {
            break;
        }
        bool allSendTaskFinish = true;
        for (auto &&iter : *sendWorkQueue) {
            if (iter.second.empty()) {
                continue;
            }
            CHK_RET(SendWork(iter.second, allSendTaskFinish));
        }
        if (allSendTaskFinish) {
            break;
        } else {
            SaluSleep(RUN_TASK_THREAD_SLEEP);
        }
    }

    return HCCL_SUCCESS;
}
}