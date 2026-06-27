/**
 * Copyright (c) 2025 Huawei Technologies Co., Ltd.
 * This program is free software, you can redistribute it and/or modify it under the terms and conditions of
 * CANN Open Software License Agreement Version 2.0 (the "License").
 * Please refer to the License for details. You may not use this file except in compliance with the License.
 * THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
 * INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
 * See LICENSE in the root of the software repository for the full text of the License.
 */

#ifndef TRANSPORT_HETEROG_EVENT_TCP_PUB_H
#define TRANSPORT_HETEROG_EVENT_TCP_PUB_H
#include <unordered_map>
#include <unordered_set>
#include <atomic>
#include <condition_variable>
#include <functional>
#include <vector>
#include <queue>
#include <stack>
#include <vector>
#include <mutex>
#include <hccl/hccl_types.h>
#include "hccl/base.h"
#include "dispatcher_pub.h"
#include "adapter_verbs.h"
#include "adapter_hal.h"
#include "transport_heterog_pub.h"

namespace hccl {

using EventReportFlag = struct EventReportFlagDef {
    std::atomic_flag flag;
    std::atomic<int> counter;
    EventReportFlagDef() : flag(ATOMIC_FLAG_INIT), counter(0) {}
};

class TransportHeterogEventTcp : public TransportHeterog {
public:
struct TcpRankInfo {
    u32 localUserRank = 0;   // 本端user rank
    u32 remoteUserRank = 0;  // 对端user rank
};
public:
    explicit TransportHeterogEventTcp(const std::string &transTag, HcclIpAddress &selfIp, HcclIpAddress &peerIp,
        u32 peerPort, u32 selfPort, u32 devId, const TransportResourceInfo &transportResourceInfo);
    ~TransportHeterogEventTcp() override;
    HcclResult Init() override;
    HcclResult Init(u32 localUserRank, u32 remoteUserRank) override;
    HcclResult Deinit() override;
    HcclResult Isend(const TransData &sendData, const TransportEndPointParam &epParam,
        HcclRequestInfo *&request) override;
    HcclResult SendNoBlock(const TransData &sendData, const TransportEndPointParam &epParam,
        u64 &envoffset, u64 &dataTranoffset, bool &envCompleted, bool &tranCompleted);
    HcclResult Send(const TransData &sendData, const TransportEndPointParam &epParam) override;
    HcclResult Improbe(const TransportEndPointParam &epParam, s32 &matched, HcclMessageInfo *&msg,
        HcclStatus &status) override;
    HcclResult Imrecv(const TransData &recvData, HcclMessageInfo &msg, HcclRequestInfo *&request) override;
    HcclResult Test(HcclRequestInfo &request, s32 &flag, HcclStatus &compState) override;
    HcclResult ReportSendComp(HcclRequestInfo *request);
    HcclResult ReportEnvelpComp(HcclEnvelopeSummary envelopeSummary);
    HcclResult ReportRecvComp(HcclRequestInfo *request);

    HcclResult BlockSend(const TransData &sendData, const TransportEndPointParam &epParam,
        HcclRequestInfo *&request, s32 waitTimeOut) override;
    HcclResult BlockRecv(const TransData &recvData, bool matched,
        TransportHeterog *&transport, s32 waitTimeOut, s32 waitPayloadTimeOut = EPOLL_WAIT_PAYLOAD_TIMEOUT_MS) override;

protected:
    HcclResult EnterStateProcess(ConnState nextState) override;
    HcclResult LoopStateProcess() override;

private:
    static void EschedAckCallback(u32 devId, u32 eventId);
    static void EschedAckCallbackRecvRequest(unsigned int devId, unsigned int subeventId, u8 *msg,
        unsigned int msgLen);
    static void EschedAckCallbackRecvCompletion(unsigned int devId, unsigned int subeventId, u8 *msg,
        unsigned int msgLen);
    static void EschedAckCallbackSendCompletion(unsigned int devId, unsigned int subeventId, u8 *msg,
        unsigned int msgLen);

    static HcclReceivedEnvelope gRecvEnvelopes;
    static std::mutex gRecvEnvelopesMutex;

private:
    static constexpr s32 INVALID_EPOLL_EVENT_FD = -1;
    static constexpr s32 EPOLL_WAIT_PAYLOAD_TIMEOUT_MS = 300000;

    static constexpr s32 DEVID_TO_GROUP_ID_NUM = 1024;
    static constexpr s32 RESERVED_DEV_ID = -1;

    static int gDevidToGroupid[DEVID_TO_GROUP_ID_NUM];

    static u32 gEschedAckRef[DEVID_TO_GROUP_ID_NUM];
    static EventReportFlag gCompCounterEvent[DEVID_TO_GROUP_ID_NUM][HCCL_EVENT_CONGESTION_RELIEF_MSG];

    struct EpollEventInfo {
        s32 epollEventFd{ INVALID_EPOLL_EVENT_FD };
        std::mutex epollEventFdMtx{};
    };

    struct EventStatus {
        s32 event{};
        bool matched{};
    };

    HcclResult RegisterEschedAckCallback();
    HcclResult DeregisterEschedAckCallback();
    HcclResult InitRecvCallback();
    HcclResult GetNetworkResource();
    HcclRequestInfo *GetTaskCache();
    HcclResult QueryRequestStatus(HcclRequestInfo &request, s32 &flag, HcclStatus &compState);
    HcclResult Connect(u32 localUserRank, u32 remoteUserRank);
    HcclResult CreateEventHandle();
    HcclResult DestroyEventHandle();

    HcclResult AddEpollEvents();
    HcclResult DelEpollEvents();

    HcclResult WaitEvents(EpollEventInfo &epollEventInfo, std::vector<SocketEventInfo> &eventInfos,
        const EventStatus &eventStatus, FdHandle &fdHandle, s32 timeout);

    HcclResult NoBlockRecv(const FdHandle fdHandle, void *&recvBuffer, u64 byteSize, u64 &recvSize);

    bool initFlag_;
    unsigned int devId_;
    s32 deviceLogicId_;
    bool needRepoEvent_;
    std::mutex taskCacheQueueLock_;
    std::queue<HcclRequestInfo *> taskCacheQueue_;
    u32 groupId_ = 0;

    EpollEventInfo sendEpollEventInfo_{};
    // recv有waitAny的需求，故采用共享epoll的方式
    static EpollEventInfo gRecvEpollEventInfo;
    static std::unordered_map<s32, FdHandle> gFdToFdhandleMap;
    static std::unordered_map<FdHandle, TransportHeterog *> gFdhandleToTransportMap;
};
}
#endif