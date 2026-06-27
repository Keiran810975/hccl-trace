/**
 * Copyright (c) 2025 Huawei Technologies Co., Ltd.
 * This program is free software, you can redistribute it and/or modify it under the terms and conditions of
 * CANN Open Software License Agreement Version 2.0 (the "License").
 * Please refer to the License for details. You may not use this file except in compliance with the License.
 * THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
 * INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
 * See LICENSE in the root of the software repository for the full text of the License.
 */

#include "tcp_recv_task.h"
#include "transport_heterog_event_tcp_pub.h"

namespace hccl {

std::atomic<bool> TcpRecvTask::g_initFlag_ = {false};

TcpRecvTask::TcpRecvTask() : initCount_(0)
{
}

TcpRecvTask::~TcpRecvTask()
{
    (void)Deinit();
}

void TcpRecvTask::RecvDataCb(const FdHandle fdHandle)
{
    if (!g_initFlag_) {
        HCCL_ERROR("[RecvData][Cb]TcpRecvTask obj has been destroyed");
        return;
    }
    if (fdHandle == nullptr) {
        HCCL_ERROR("[RecvTask][RecvDataCb]fdHandle is nullptr!!!!");
    } else {
        GetRecvTaskInstance()->RecvData(fdHandle);
    }
    return;
}

// 将callback指针传给hccp
HcclResult TcpRecvTask::Init(const SocketInfoT socketInfo, void *transportPtr)
{
    std::unique_lock<std::mutex> lock(transportMapMutex_);
    if (fdTransportMap_.count(socketInfo.fdHandle) == 0) {
        fdTransportMap_[socketInfo.fdHandle] = transportPtr;
    }
    lock.unlock();
    if (initCount_ == 0) {
        CHK_RET(hrtSetRecvDataCallback(socketInfo.socketHandle, reinterpret_cast<void *>(RecvDataCb)));
    }
    initCount_++;
    g_initFlag_ = true;
    HCCL_INFO("[RecvTask][Init]call Init count[%d]", initCount_);
    return HCCL_SUCCESS;
}

HcclResult TcpRecvTask::Deinit()
{
    g_initFlag_ = false;
    if (initCount_ == 0) {
        std::unique_lock<std::mutex> lock(transportMapMutex_);
        fdTransportMap_.clear();
        lock.unlock();
    } else if (initCount_ > 0) {
        initCount_--;
    } else {
        HCCL_WARNING("[RecvTask][Init] initCount_[%d] ERROR", initCount_);
    }

    return HCCL_SUCCESS;
}

HcclResult TcpRecvTask::SetRecvTask(const FdHandle fdHandle, HcclRequestInfo *request)
{
    CHK_PTR_NULL(fdHandle);
    CHK_PTR_NULL(request);
    if (request->transportRequest.transData.count > 0) {
        RecvRecord recvRecord;
        recvRecord.buffer = reinterpret_cast<void *>(request->transportRequest.transData.dstBuf);
        recvRecord.size = request->transportRequest.transData.count *
            SIZE_TABLE[request->transportRequest.transData.dataType];

        HCCL_DEBUG("SetRecvTask fdHandle[%p]", fdHandle);
        std::unique_lock<std::mutex> lock(recvMutex_);
        recvTaskMap_[fdHandle] = std::make_pair(request, recvRecord);
        lock.unlock();
        CHK_RET(hrtEpollCtlMod(fdHandle, RA_EPOLLIN));
    } else {
        // 接收的信封中count为0，则不需要接收数据，继续接收信封即可。因此需要将epoll修改为oneshot模式，并提交recv complete事件
        CHK_RET(hrtEpollCtlMod(fdHandle, RA_EPOLLONESHOT));
        std::unique_lock<std::mutex> lock(transportMapMutex_);
        FdHandle transport = fdTransportMap_[fdHandle];
        lock.unlock();
        CHK_RET(reinterpret_cast<TransportHeterogEventTcp *>(transport)->ReportRecvComp(request));
    }
    HCCL_DEBUG("[RecvTask][SetRecvTask] recv buffer[%p]",
        reinterpret_cast<void *>(request->transportRequest.transData.srcBuf));
    return HCCL_SUCCESS;
}

HcclResult TcpRecvTask::RecvData(const FdHandle fdHandle)
{
    CHK_PTR_NULL(fdHandle);
    if (!envelopMap_[fdHandle].flag) {
        HcclEnvelopeSummary envelopeSummary;
        CHK_RET(hrtRaSocketBlockRecv(fdHandle, &(envelopeSummary.envelope), sizeof(HcclEnvelope)));
        HCCL_DEBUG("envelop rank[%u] tag[%d] count[%d] size[%u]",
            envelopeSummary.envelope.epParam.src.rank, envelopeSummary.envelope.epParam.src.tag,
            envelopeSummary.envelope.transData.count, sizeof(envelopeSummary.envelope));

        envelopeSummary.status = 0;
        std::unique_lock<std::mutex> lock(transportMapMutex_);
        FdHandle transport = fdTransportMap_[fdHandle];
        lock.unlock();
        CHK_PTR_NULL(transport);
        CHK_RET(reinterpret_cast<TransportHeterogEventTcp *>(transport)->ReportEnvelpComp(envelopeSummary));
        if (envelopeSummary.envelope.transData.count == 0) {
            envelopMap_[fdHandle].flag = false; // 接收的信封中count为0，则不需要接收数据，继续接收信封即可
        } else {
            envelopMap_[fdHandle].flag = true;
        }
    } else {
        std::unique_lock<std::mutex> recvLock(recvMutex_);
        RecvRecord recvData = recvTaskMap_[fdHandle].second;
        recvLock.unlock();
        u64 recvSize = 0;
        s32 rtRet = hrtRaSocketRecv(fdHandle, recvData.buffer, recvData.size, &recvSize);
        if ((rtRet == 0) && (recvSize > 0)) {
            CHK_PRT_RET(recvSize > recvData.size,
                HCCL_ERROR("[RecvTask][RecvBody]errNo[0x%016llx] socket receive rtSize[%llu Byte] bigger size[%zu]",
                HCCL_ERROR_CODE(HCCL_E_TCP_TRANSFER), recvSize, recvData.size), HCCL_E_TCP_TRANSFER);
            recvData.size -= recvSize;
            recvData.buffer = reinterpret_cast<void *>(reinterpret_cast<uintptr_t>(recvData.buffer) + recvSize);
        } else if ((rtRet == 0) && (recvSize == 0)) {
            HCCL_ERROR("[RecvTask][RecvBody]recv fail, bufLen[%llu Byte], recLen[%llu Byte]", recvData.size, recvSize);
            return HCCL_E_TCP_TRANSFER;
        } else if ((rtRet == SOCK_EAGAIN) && (recvSize == 0)) {
            HCCL_DEBUG("[TcpRecvTask][RecvBody] rtRet[%d] recv again", rtRet);
            return HCCL_SUCCESS;
        } else {
            HCCL_ERROR("[TcpRecvTask][RecvBody] rtRet[%d] recv[%llu] fail", rtRet, recvSize);
            return HCCL_E_TCP_TRANSFER;
        }

        if (recvData.size == 0) {
            std::unique_lock<std::mutex> lock(recvMutex_);
            HcclRequestInfo *request = recvTaskMap_[fdHandle].first;
            recvTaskMap_.erase(fdHandle);
            lock.unlock();
            envelopMap_[fdHandle].flag = false;
            CHK_RET(hrtEpollCtlMod(fdHandle, RA_EPOLLONESHOT));
            std::unique_lock<std::mutex> transportLock(transportMapMutex_);
            FdHandle transport = fdTransportMap_[fdHandle];
            transportLock.unlock();
            HCCL_DEBUG("fdHandle[%p] recv OK!", fdHandle);
            CHK_RET(reinterpret_cast<TransportHeterogEventTcp *>(transport)->ReportRecvComp(request));
        } else {
            std::unique_lock<std::mutex> lock(recvMutex_);
            recvTaskMap_[fdHandle].second = recvData;
            lock.unlock();
        }
    }
    return HCCL_SUCCESS;
}

}
