/**
 * Copyright (c) 2025 Huawei Technologies Co., Ltd.
 * This program is free software, you can redistribute it and/or modify it under the terms and conditions of
 * CANN Open Software License Agreement Version 2.0 (the "License").
 * Please refer to the License for details. You may not use this file except in compliance with the License.
 * THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
 * INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
 * See LICENSE in the root of the software repository for the full text of the License.
 */

#include "transport_heterog_event_tcp.h"

#include <sys/epoll.h>

#include "log.h"
#include "externalinput_pub.h"
#include "transport_ibverbs_pub.h"
#include "adapter_hal.h"
#include "adapter_hccp.h"
#include "dlhal_function.h"
#include "tcp_send_thread_pool.h"
#include "tcp_recv_task.h"
#include "network_manager_pub.h"
#include "device_capacity.h"

using namespace std;
namespace hccl {

// 因无法直接访问network的private路径下的ra_rs_comm.h中的socket_peer_info结构体
struct socket_peer_info {
    int phyId;
    int fd;
    void *socketHandle;
};

constexpr s32 PROTOCOL_TYPE = 1;
constexpr s32 LINK_NUM = 1;
constexpr s32 BUILD_TRANS_TAG = INT_MAX;
constexpr u64 BLOCK_SEND_US = 500;
constexpr s32 EPOLL_EVENTS_NUM = 8;

HcclReceivedEnvelope TransportHeterogEventTcp::gRecvEnvelopes;
std::mutex TransportHeterogEventTcp::gRecvEnvelopesMutex;

int TransportHeterogEventTcp::gDevidToGroupid[DEVID_TO_GROUP_ID_NUM]{};

u32 TransportHeterogEventTcp::gEschedAckRef[DEVID_TO_GROUP_ID_NUM]{};
EventReportFlag TransportHeterogEventTcp::gCompCounterEvent[DEVID_TO_GROUP_ID_NUM][HCCL_EVENT_CONGESTION_RELIEF_MSG]{};

TransportHeterogEventTcp::EpollEventInfo TransportHeterogEventTcp::gRecvEpollEventInfo{};

unordered_map<FdHandle, TransportHeterog *> TransportHeterogEventTcp::gFdhandleToTransportMap;

void TransportHeterogEventTcp::EschedAckCallbackRecvRequest(unsigned int devId, unsigned int subeventId, u8 *msg,
    unsigned int msgLen)
{
    (void)subeventId;
    (void)msg;
    (void)msgLen;
    TransportHeterogEventTcp::EschedAckCallback(devId, HCCL_EVENT_RECV_REQUEST_MSG);
}

void TransportHeterogEventTcp::EschedAckCallbackSendCompletion(unsigned int devId, unsigned int subeventId, u8 *msg,
    unsigned int msgLen)
{
    (void)subeventId;
    (void)msg;
    (void)msgLen;
    TransportHeterogEventTcp::EschedAckCallback(devId, HCCL_EVENT_SEND_COMPLETION_MSG);
}

void TransportHeterogEventTcp::EschedAckCallbackRecvCompletion(unsigned int devId, unsigned int subeventId, u8 *msg,
    unsigned int msgLen)
{
    (void)subeventId;
    (void)msg;
    (void)msgLen;
    TransportHeterogEventTcp::EschedAckCallback(devId, HCCL_EVENT_RECV_COMPLETION_MSG);
}


TransportHeterogEventTcp::TransportHeterogEventTcp(const std::string &transTag, HcclIpAddress &selfIp,
    HcclIpAddress &peerIp, u32 peerPort, u32 selfPort, u32 devId, const TransportResourceInfo &transportResourceInfo)
    : TransportHeterog(transTag, selfIp, peerIp, peerPort, selfPort, transportResourceInfo), initFlag_(false),
    devId_(devId), needRepoEvent_(true)
{}

TransportHeterogEventTcp::~TransportHeterogEventTcp()
{
    (void)Deinit();
}

void TransportHeterogEventTcp::EschedAckCallback(u32 devId, u32 eventId)
{
    HCCL_DEBUG("EventCallback start. devId:%u, eventId:%u", devId, eventId);
    HcclUs startut = TIME_NOW();

    if (eventId > HCCL_EVENT_RECV_COMPLETION_MSG || eventId < HCCL_EVENT_RECV_REQUEST_MSG) {
        HCCL_WARNING("gCompCounterEvent not find eventId[%u]", eventId);
        return;
    }

    if (gCompCounterEvent[devId][eventId].counter.load(std::memory_order_relaxed) > 0) {
        hrtHalSubmitEvent(devId, eventId, TransportHeterogEventTcp::gDevidToGroupid[devId]);
    } else {
        gCompCounterEvent[devId][eventId].flag.clear();
        if (gCompCounterEvent[devId][eventId].counter.load(std::memory_order_relaxed) > 0) {
            hrtHalSubmitEvent(devId, eventId, TransportHeterogEventTcp::gDevidToGroupid[devId]);
            gCompCounterEvent[devId][eventId].flag.test_and_set();
        }
    }

    HcclUs endut = TIME_NOW();
    HCCL_INFO("EschedAckCallback cost time: %lld us, event id: %u, devId:%u",
        DURATION_US(endut - startut), eventId, devId);
    return;
}

HcclResult TransportHeterogEventTcp::RegisterEschedAckCallback()
{
    HCCL_INFO("START RegisterEschedAckCallback DlHalFunctionInit");
    if (gEschedAckRef[devId_] == 0) {
        CHK_RET(DlHalFunction::GetInstance().DlHalFunctionInit());
        u32 grpId = static_cast<u32>(TransportHeterogEventTcp::gDevidToGroupid[devId_]);

        CHK_RET(hrtHalEschedRegisterAckFuncWithGrpid(grpId, HCCL_EVENT_RECV_REQUEST_MSG, EschedAckCallbackRecvRequest));
        CHK_RET(hrtHalEschedRegisterAckFuncWithGrpid(grpId,
            HCCL_EVENT_SEND_COMPLETION_MSG, EschedAckCallbackSendCompletion));
        CHK_RET(hrtHalEschedRegisterAckFuncWithGrpid(grpId,
            HCCL_EVENT_RECV_COMPLETION_MSG, EschedAckCallbackRecvCompletion));

        HCCL_DEBUG("grpId[%u] all Registered", grpId);

        gCompCounterEvent[devId_][HCCL_EVENT_RECV_REQUEST_MSG].counter = 0;
        gCompCounterEvent[devId_][HCCL_EVENT_SEND_COMPLETION_MSG].counter = 0;
        gCompCounterEvent[devId_][HCCL_EVENT_RECV_COMPLETION_MSG].counter = 0;

        gCompCounterEvent[devId_][HCCL_EVENT_RECV_REQUEST_MSG].flag.clear();
        gCompCounterEvent[devId_][HCCL_EVENT_SEND_COMPLETION_MSG].flag.clear();
        gCompCounterEvent[devId_][HCCL_EVENT_RECV_COMPLETION_MSG].flag.clear();
    }

    gEschedAckRef[devId_]++;
    return HCCL_SUCCESS;
}

HcclResult TransportHeterogEventTcp::DeregisterEschedAckCallback()
{
    if (gEschedAckRef[devId_] == 0) {
        HCCL_WARNING("TransportHeterogEventTcp:: EschedAckCallback has been deregistered.");
        return HCCL_SUCCESS;
    }
    gEschedAckRef[devId_]--;
    return HCCL_SUCCESS;
}

HcclResult TransportHeterogEventTcp::Init(u32 localUserRank, u32 remoteUserRank)
{
    if (Is310PDevice()) {
        CHK_RET(hrtGetDevice(&deviceLogicId_));
    } else {
        deviceLogicId_ = HOST_DEVICE_ID;
    }

    needRepoEvent_ = false;
    CHK_RET(TransportHeterog::SetDeviceIndex(deviceLogicId_));
    Init();
    Connect(localUserRank, remoteUserRank);  // 推动建链
    return HCCL_SUCCESS;
}

HcclResult TransportHeterogEventTcp::Connect(u32 localUserRank, u32 remoteUserRank)
{
    TcpRankInfo buffer{};
    if (localUserRank < remoteUserRank) {
        HcclRequestInfo* request = nullptr;
        s32 flag = HCCL_TEST_INCOMPLETED;
        HcclStatus compState = {0};
        buffer.localUserRank = localUserRank;
        buffer.remoteUserRank = remoteUserRank;
        TransData sendData(reinterpret_cast<u64>(&buffer), reinterpret_cast<u64>(nullptr), sizeof(TcpRankInfo),
            HCCL_DATA_TYPE_INT8);
        TransportEndPointInfo srcEp(0, localUserRank, BUILD_TRANS_TAG);
        TransportEndPointInfo dstEp(0, remoteUserRank, BUILD_TRANS_TAG);
        TransportEndPointParam epParam(srcEp, dstEp);
        CHK_RET(Isend(sendData, epParam, request));
        // Test推动异步建链
        while (flag != HCCL_TEST_COMPLETED) {
            CHK_RET(Test(*request, flag, compState));
            CHK_PRT_RET(compState.error > 0, HCCL_ERROR("Test failed, compState.error[%d].", compState.error),
                HCCL_E_INTERNAL);
            SaluSleep(ONE_HUNDRED_MICROSECOND_OF_USLEEP);
        }
    } else {
        HcclRequestInfo* request = nullptr;
        s32 improbeFlag = HCCL_IMPROBE_INCOMPLETED;
        s32 testFlag = HCCL_TEST_INCOMPLETED;
        HcclStatus status = {0};
        HcclStatus compState = {0};
        HcclMessageInfo *msg = nullptr;
        TransportEndPointInfo srcEp(0, remoteUserRank, BUILD_TRANS_TAG);
        TransportEndPointInfo dstEp(0, localUserRank, BUILD_TRANS_TAG);
        TransportEndPointParam epParam(srcEp, dstEp);
        // Improbe推动异步建链
        while (improbeFlag != HCCL_IMPROBE_COMPLETED) {
            CHK_RET(Improbe(epParam, improbeFlag, msg, status));
            CHK_PRT_RET(status.error > 0, HCCL_ERROR("Improbe failed, status.error[%d].", status.error),
                HCCL_E_INTERNAL);
            SaluSleep(ONE_HUNDRED_MICROSECOND_OF_USLEEP);
        }

        TransData recvData(reinterpret_cast<u64>(nullptr), reinterpret_cast<u64>(&buffer),
            sizeof(TcpRankInfo), HCCL_DATA_TYPE_INT8);
        CHK_RET(Imrecv(recvData, *msg, request));

        while (testFlag != HCCL_TEST_COMPLETED) {
            CHK_RET(Test(*request, testFlag, compState));
            CHK_PRT_RET(compState.error > 0, HCCL_ERROR("Test failed, compState.error[%d].", compState.error),
                HCCL_E_INTERNAL);
            SaluSleep(ONE_HUNDRED_MICROSECOND_OF_USLEEP);
        }

        HCCL_INFO("recv envelope localRank=[%u], remoteRank=[%u]",
            buffer.localUserRank, buffer.remoteUserRank);
    }
    return HCCL_SUCCESS;
}

HcclResult TransportHeterogEventTcp::Init()
{
    CHK_RET(CheckRecvMsgAndRequestBuffer());
    int groupId = 0;
    int devId = 0;
    s32 ret = hrtGetgrpId(groupId, devId);
    if (ret != HCCL_SUCCESS) {
        HCCL_ERROR("hrtGetgrpId failed");
        return HCCL_E_PARA;
    }
    if (devId == RESERVED_DEV_ID) {
        if (devId_ > DEVID_TO_GROUP_ID_NUM) {
            HCCL_WARNING("devId_[%d] is invalid. It should be in [0, %d)", devId_, DEVID_TO_GROUP_ID_NUM);
            devId_ = 0;
        }

        TransportHeterogEventTcp::gDevidToGroupid[devId_] = groupId;
        HCCL_DEBUG("hrtGetgrpId use default.");
    } else if (devId < 0 || devId > DEVID_TO_GROUP_ID_NUM || groupId < 0) {
        HCCL_ERROR("hrtGetgrpId devId[%d] > [%d], < 0 or groupId[%d] is error.", devId, DEVID_TO_GROUP_ID_NUM, groupId);
        return HCCL_E_PARA;
    } else {
        TransportHeterogEventTcp::gDevidToGroupid[devId] = groupId;
        HCCL_DEBUG("devId was changed from [%d] to [%d].", devId_, devId);
        devId_ = devId;
    }

    CHK_RET(GetNetworkResource());
    if (needRepoEvent_) {
        HCCL_DEBUG("TransportHeterogEventTcp:: EschedAckCallback need registered.");
        CHK_RET(RegisterEschedAckCallback());
    }

    CHK_RET(InitTransportConnect(PROTOCOL_TYPE, LINK_NUM));
    CHK_RET(ConnectAsync());
    initFlag_ = true;

    return HCCL_SUCCESS;
}

HcclResult TransportHeterogEventTcp::Deinit()
{
    if (initFlag_) {
        TcpRecvTask::GetRecvTaskInstance()->Deinit();
        CHK_RET(DeregisterEschedAckCallback());
        CHK_RET(SocketClose());
        initFlag_ = false;
    } else {
        HCCL_WARNING("TransportHeterogEventTcp has been Deinit.");
    }

    return HCCL_SUCCESS;
}

HcclResult TransportHeterogEventTcp::Isend(const TransData &sendData, const TransportEndPointParam &epParam,
    HcclRequestInfo *&request)
{
    CHK_RET(GenerateSendRequest(sendData, epParam, request));
    HCCL_DEBUG("Isend: peerRank[%u] tag[%d] buffer[%llu] count[%d] dataType[%s] request[%p]",
        epParam.dst.rank, epParam.dst.tag, sendData.srcBuf, sendData.count,
        GetDataTypeEnumStr(sendData.dataType).c_str(), request);

    // 如果建链未完成，或者积压的信封未发送完成，则Isend不进行信封发送。
    // Test接口中推动积压信封发送完成后，Isend接口才启动信封发送。
    std::unique_lock<std::mutex> lock(taskCacheQueueLock_);
    if (GetState() != ConnState::CONN_STATE_COMPLETE || !taskCacheQueue_.empty()) {
        taskCacheQueue_.push(request);
        return HCCL_SUCCESS;
    }
    lock.unlock();

    return TcpSendThreadPool::GetSendPoolInstance()->AddSendTask(request);
}

HcclResult TransportHeterogEventTcp::SendNoBlock(const TransData &sendData, const TransportEndPointParam &epParam,
    u64& envoffset, u64& dataTranoffset, bool &envCompleted, bool &tranCompleted)
{
    HcclResult ret;
    u64 envSentSize = 0;
    u64 dataSentSize = 0;
    TransData transData = sendData;
    TransportEndPointParam transportParam = epParam;
    HcclEnvelope envelope(1, transData, transportParam, 0, 0);
    u64 envelopeSize = sizeof(envelope);
    if (envelopeSize >= envoffset) {
        envelopeSize -= envoffset;
    } else {
        HCCL_ERROR("SendNoBlock envelopeSize[%llu] < envoffset[%llu]", envelopeSize, envoffset);
        return HCCL_E_INTERNAL;
    }
    if (envelopeSize > 0) {
        ret = hrtRaSocketNonBlockSendHeterog(initSM_.locInitInfo.socketInfo[0].fdHandle,
            (reinterpret_cast<u8 *>(&envelope) + envoffset), envelopeSize, &envSentSize);
        envoffset += envSentSize;
        if (ret == HCCL_E_NETWORK) {
            HCCL_ERROR("TransportHeterogEventTcp SendNoBlock fail error[%d]", ret);
            return HCCL_E_TCP_TRANSFER;
        } else if (ret == HCCL_E_AGAIN || envelopeSize > envSentSize) { // 当前task envelope未发送完
            envCompleted = false;
            return HCCL_SUCCESS;
        }
    }
    u64 payloadSize = envelope.transData.count * SIZE_TABLE[envelope.transData.dataType];
    if (payloadSize >= dataTranoffset) {
        payloadSize -= dataTranoffset;
    } else {
        HCCL_ERROR("TransportHeterogEventTcp SendNoBlock payloadSize[%llu] < dataTranoffset[%llu]",
            envelopeSize, envoffset);
        return HCCL_E_INTERNAL;
    }
    if (payloadSize > 0) {
        ret = hrtRaSocketNonBlockSendHeterog(initSM_.locInitInfo.socketInfo[0].fdHandle,
            (reinterpret_cast<u8 *>(envelope.transData.srcBuf) + dataTranoffset), payloadSize, &dataSentSize);
        dataTranoffset += dataSentSize;
        if (ret == HCCL_E_NETWORK) {
            HCCL_ERROR("TransportHeterogEventTcp SendNoBlock fail error[%d]", ret);
            return HCCL_E_TCP_TRANSFER;
        } else if (ret == HCCL_E_AGAIN || payloadSize > dataSentSize) {
            tranCompleted = false;
        }
    }
    return HCCL_SUCCESS;
}

HcclResult TransportHeterogEventTcp::Send(const TransData &sendData, const TransportEndPointParam &epParam)
{
    TransData transData = sendData;
    TransportEndPointParam transportParam = epParam;
    HcclEnvelope envelope(1, transData, transportParam, 0, 0);

    CHK_RET(hrtRaSocketBlockSend(initSM_.locInitInfo.socketInfo[0].fdHandle, &envelope,
        sizeof(envelope)));

    if (envelope.transData.count > 0) {
        u64 payloadSize = envelope.transData.count * SIZE_TABLE[envelope.transData.dataType];
        CHK_RET(hrtRaSocketBlockSend(initSM_.locInitInfo.socketInfo[0].fdHandle,
            reinterpret_cast<void *>(envelope.transData.srcBuf), payloadSize));
    }
    return HCCL_SUCCESS;
}

HcclResult TransportHeterogEventTcp::ReportSendComp(HcclRequestInfo *request)
{
    CHK_PTR_NULL(request);
    request->transportRequest.status = 0;

    if (!needRepoEvent_) {
        gCompCounterEvent[devId_][HCCL_EVENT_SEND_COMPLETION_MSG].counter.fetch_add(1, std::memory_order_relaxed);
        HCCL_INFO("TransportHeterogEventTcp Send Doesn't need SubmitEvent!!!");
        return HCCL_SUCCESS;
    }

    EventReportFlag &flag = gCompCounterEvent[devId_][HCCL_EVENT_SEND_COMPLETION_MSG];
    flag.counter++;
    if (!flag.flag.test_and_set()) {
        HcclResult ret = hrtHalSubmitEvent(devId_, HCCL_EVENT_SEND_COMPLETION_MSG,
            TransportHeterogEventTcp::gDevidToGroupid[devId_]);
        if (ret != HCCL_SUCCESS) {
            HCCL_ERROR("hrtHalSubmitEvent failed for devId[%u], ret:%d", devId_, ret);
        }
    }

    return HCCL_SUCCESS;
}

HcclResult TransportHeterogEventTcp::ReportEnvelpComp(HcclEnvelopeSummary envelopeSummary)
{
    std::unique_lock<std::mutex> Queuelock(gRecvEnvelopesMutex);
    gRecvEnvelopes[envelopeSummary.envelope.epParam.src].push(envelopeSummary);
    Queuelock.unlock();

    if (!needRepoEvent_) {
        gCompCounterEvent[devId_][HCCL_EVENT_RECV_REQUEST_MSG].counter.fetch_add(1, std::memory_order_relaxed);
        HCCL_INFO("TransportHeterogEventTcp Envelop Doesn't need SubmitEvent!!!");
        return HCCL_SUCCESS;
    }

    EventReportFlag &flag = gCompCounterEvent[devId_][HCCL_EVENT_RECV_REQUEST_MSG];
    flag.counter++;
    if (!flag.flag.test_and_set()) {
        HcclResult ret = hrtHalSubmitEvent(devId_, HCCL_EVENT_RECV_REQUEST_MSG,
            TransportHeterogEventTcp::gDevidToGroupid[devId_]);
        if (ret != HCCL_SUCCESS) {
            HCCL_ERROR("hrtHalSubmitEvent failed for devId[%u], ret:%d", devId_, ret);
        }
    }

    return HCCL_SUCCESS;
}

HcclResult TransportHeterogEventTcp::ReportRecvComp(HcclRequestInfo *request)
{
    CHK_PTR_NULL(request);
    request->transportRequest.status = 0;

    if (!needRepoEvent_) {
        gCompCounterEvent[devId_][HCCL_EVENT_RECV_COMPLETION_MSG].counter.fetch_add(1, std::memory_order_relaxed);
        HCCL_INFO("TransportHeterogEventTcp Recv Doesn't need SubmitEvent!!!");
        return HCCL_SUCCESS;
    }

    EventReportFlag &flag = gCompCounterEvent[devId_][HCCL_EVENT_RECV_COMPLETION_MSG];
    flag.counter++;
    if (!flag.flag.test_and_set()) {
        HcclResult ret = hrtHalSubmitEvent(devId_, HCCL_EVENT_RECV_COMPLETION_MSG,
            TransportHeterogEventTcp::gDevidToGroupid[devId_]);
        if (ret != HCCL_SUCCESS) {
            HCCL_ERROR("hrtHalSubmitEvent failed for devId[%u], ret:%d", devId_, ret);
        }
    }

    return HCCL_SUCCESS;
}

HcclResult TransportHeterogEventTcp::Improbe(const TransportEndPointParam &epParam, s32 &matched, HcclMessageInfo *&msg,
    HcclStatus &status)
{
    // 建链未完成时，返回未匹配到
    if (GetState() != ConnState::CONN_STATE_COMPLETE) {
        CHK_RET(ConnectAsync());
        return ProbeNothing(matched, msg, status);
    }

    // 检查能否匹配到
    std::unique_lock<std::mutex> Queuelock(gRecvEnvelopesMutex);
    std::queue<HcclEnvelopeSummary> &envelopInfos = gRecvEnvelopes[epParam.src];
    Queuelock.unlock();

    auto probeSomething = [&]() -> HcclResult {
        CHK_RET(GenerateRecvMessage(envelopInfos.front(), msg, status));

        Queuelock.lock();
        envelopInfos.pop();
        Queuelock.unlock();
        matched = HCCL_IMPROBE_COMPLETED;
        if (gCompCounterEvent[devId_][HCCL_EVENT_RECV_REQUEST_MSG].counter > 0) {
            gCompCounterEvent[devId_][HCCL_EVENT_RECV_REQUEST_MSG].counter--;
        }
        return HCCL_SUCCESS;
    };

    if (!envelopInfos.empty()) {
        return probeSomething();
    } else {
        return ProbeNothing(matched, msg, status);
    }
}

HcclResult TransportHeterogEventTcp::Imrecv(const TransData &recvData, HcclMessageInfo &msg, HcclRequestInfo *&request)
{
    CHK_RET(CheckRecvEnvelope(recvData, msg.envelope));
    CHK_RET(GenerateRecvRequest(recvData, msg, request));

    CHK_RET(TcpRecvTask::GetRecvTaskInstance()->SetRecvTask(initSM_.locInitInfo.socketInfo[0].fdHandle, request));
    CHK_RET(FreeRecvMessage(msg));
    return HCCL_SUCCESS;
}

HcclResult TransportHeterogEventTcp::Test(HcclRequestInfo &request, s32 &flag, HcclStatus &compState)
{
    HCCL_DEBUG("[TransportHeterogEventTcp][Test]requestType [%u]", request.transportRequest.requestType);
    flag = HCCL_TEST_INCOMPLETED;
    // 建链未完成时，继续推进建链流程；
    if (GetState() != ConnState::CONN_STATE_COMPLETE) {
        CHK_RET(ConnectAsync());
        return HCCL_SUCCESS;
    }

    return QueryRequestStatus(request, flag, compState);
}

HcclResult TransportHeterogEventTcp::InitRecvCallback()
{
    TcpRecvTask::GetRecvTaskInstance()->Init(initSM_.locInitInfo.socketInfo[0], this);
    (void)hrtEpollCtlAdd(initSM_.locInitInfo.socketInfo[0].fdHandle, RA_EPOLLONESHOT);
    return HCCL_SUCCESS;
}

HcclResult TransportHeterogEventTcp::EnterStateProcess(ConnState nextState)
{
    switch (nextState) {
        case ConnState::CONN_STATE_CONNECT_CHECK_SOCKET:
            initSM_.socketNum = initSM_.locInitInfo.socketConnInfo.size();
            break;
        case ConnState::CONN_STATE_GET_CHECK_SOCKET:
            initSM_.socketNum = initSM_.locInitInfo.socketInfo.size();
            initSM_.completeNum = 0;
            break;
        case ConnState::CONN_STATE_SEND_CF:
        case ConnState::CONN_STATE_RECV_CF:
            initSM_.size = HETEROG_MAX_FRAME_LEN;
            initSM_.completeSize = 0;
            break;
        case ConnState::CONN_STATE_CHECK_CF:
            CHK_RET(CheckConsistentFrame());
            CHK_RET(InitRecvCallback());
            CHK_RET(TryTransition(HCCL_SUCCESS, true, ConnState::CONN_STATE_COMPLETE));
            break;
        case ConnState::CONN_STATE_COMPLETE:
            {
                HCCL_INFO("link[%s]: connect complete", initSM_.locInitInfo.socketInfo[0].tag);
                std::unique_lock<std::mutex> lock(taskCacheQueueLock_);
                while (!taskCacheQueue_.empty()) {
                    CHK_RET(TcpSendThreadPool::GetSendPoolInstance()->AddSendTask(GetTaskCache()));
                }
                lock.unlock();
                break;
            }
        default:
            HCCL_INFO("link[%s]: state[%u] no need to do anything", initSM_.locInitInfo.socketInfo[0].tag, nextState);
    }

    return HCCL_SUCCESS;
}

HcclResult TransportHeterogEventTcp::LoopStateProcess()
{
    HcclResult testRet = HCCL_SUCCESS;
    bool completed = false;
    switch (GetState()) {
        case ConnState::CONN_STATE_CONNECT_CHECK_SOCKET:
            testRet = ConnectSocket(initSM_.locInitInfo.socketConnInfo.data(), initSM_.socketNum, completed);
            CHK_RET(TryTransition(testRet, completed, ConnState::CONN_STATE_GET_CHECK_SOCKET));
            break;
        case ConnState::CONN_STATE_GET_CHECK_SOCKET:
            testRet = GetSocket(initSM_.locInitInfo.role, initSM_.locInitInfo.socketInfo.data(), initSM_.socketNum,
                initSM_.completeNum, completed);
            CHK_RET(TryTransition(testRet, completed, ConnState::CONN_STATE_SEND_CF));
            break;
        case ConnState::CONN_STATE_SEND_CF:
            if (initSM_.locInitInfo.socketInfo.size() == 0) {
                HCCL_ERROR("[LoopStateProcess]initSM_.locInitInfo.socketInfo is invalid!");
                return HCCL_E_PARA;
            }
            testRet = SocketSend(initSM_.locInitInfo.socketInfo[0].fdHandle, initSM_.locInitInfo.checkFrame,
                initSM_.size, initSM_.completeSize, completed);
            CHK_RET(TryTransition(testRet, completed, ConnState::CONN_STATE_RECV_CF));
            break;
        case ConnState::CONN_STATE_RECV_CF:
            if (initSM_.locInitInfo.socketInfo.size() == 0) {
                HCCL_ERROR("[LoopStateProcess]initSM_.locInitInfo.socketInfo is invalid!");
                return HCCL_E_PARA;
            }
            testRet = SocketRecv(initSM_.locInitInfo.socketInfo[0].fdHandle, initSM_.remInitInfo.checkFrame,
                initSM_.size, initSM_.completeSize, completed);
            CHK_RET(TryTransition(testRet, completed, ConnState::CONN_STATE_CHECK_CF));
            break;
        default:
            HCCL_ERROR("Establish communication connection failed state[%u]", GetState());
            if (initSM_.locInitInfo.socketInfo.size() == 0) {
                HCCL_ERROR("[LoopStateProcess]initSM_.locInitInfo.socketInfo is invalid!");
                return HCCL_E_INTERNAL;
            }
            HCCL_ERROR("link tag[%s]", initSM_.locInitInfo.socketInfo[0].tag);
            return HCCL_E_INTERNAL;
    }
    return HCCL_SUCCESS;
}

HcclResult TransportHeterogEventTcp::QueryRequestStatus(HcclRequestInfo &request, s32 &flag, HcclStatus &compState)
{
    u32 eventType;
    if (request.transportRequest.requestType == HcclRequestType::HCCL_REQUEST_SEND) {
        eventType = HCCL_EVENT_SEND_COMPLETION_MSG;
    } else if (request.transportRequest.requestType == HcclRequestType::HCCL_REQUEST_RECV) {
        eventType = HCCL_EVENT_RECV_COMPLETION_MSG;
    } else {
        HCCL_ERROR("[QueryRequestStatus]requestType is invalid! requestType[%u]",
            request.transportRequest.requestType);
        return HCCL_E_PARA;
    }

    EventReportFlag &eFlag = gCompCounterEvent[devId_][eventType];

    if (eFlag.counter > 0) {
        if (request.transportRequest.status >= 0) {
            gCompCounterEvent[devId_][eventType].counter--;
            // 该request已完成
            flag = HCCL_TEST_COMPLETED;
            compState.tag = request.transportRequest.epParam.src.tag;
            compState.srcRank = request.transportRequest.epParam.src.rank;
            compState.error = request.transportRequest.status;
            CHK_RET(FreeRequest(request));
        }
    }

    return HCCL_SUCCESS;
}

HcclResult TransportHeterogEventTcp::GetNetworkResource()
{
    RaResourceInfo raResourceInfo;
    CHK_RET(NetworkManager::GetInstance(index_).GetRaResourceInfo(raResourceInfo));
    auto it = raResourceInfo.nicSocketMap.find(selfIp_);
    if (it == raResourceInfo.nicSocketMap.end()) {
        HCCL_ERROR("[TransportHeterogEventTcp][Init]nic socket handle did not found");
        return HCCL_E_PARA;
    }
    nicSocketHandle_ = it->second.nicSocketHandle;
    CHK_PTR_NULL(nicSocketHandle_);
    return HCCL_SUCCESS;
}

HcclRequestInfo *TransportHeterogEventTcp::GetTaskCache()
{
    auto tmp = taskCacheQueue_.front();
    taskCacheQueue_.pop();
    return tmp;
}


// matched为false的时候，fdHandle为出参；否则fdHandle为入参
HcclResult TransportHeterogEventTcp::WaitEvents(EpollEventInfo &epollEventInfo,
    vector<SocketEventInfo> &eventInfos, const EventStatus &eventStatus, FdHandle &fdHandle, s32 timeout)
{
    bool waitComleted = false;
    u32 eventsNum{ 0 };
    HcclResult ret{ HCCL_SUCCESS };

    // 可能存在一直有epoll事件，但是一直没有预期的fd的可能性
    while (!waitComleted) {
        {
            lock_guard<mutex> lock(epollEventInfo.epollEventFdMtx);
            ret = hrtRaWaitEventHandle(epollEventInfo.epollEventFd, eventInfos,
                timeout, eventInfos.size(), eventsNum);
        }

        if (eventsNum == 0 && ret == HCCL_SUCCESS) {
            // 等待超时，部分场景属于正常
            HCCL_WARNING("hrtRaWaitEventHandle is timeout[%d] ms, eventsNum[%u], ret[%d]", timeout, eventsNum, ret);
            return HCCL_E_AGAIN;
        } else if (UNLIKELY(ret != HCCL_SUCCESS)) {
            HCCL_ERROR("hrtRaWaitEventHandle failed, epollEventFd[%d], ret[%d]", epollEventInfo.epollEventFd, ret);
            return ret;
        }

        for (u32 i = 0; i < eventsNum; i++) {
            if ((eventInfos[i].event & static_cast<u32>(EPOLLRDHUP)) != 0) {
                HCCL_ERROR("Peer socket has been closed from event, eventInfos[%u] fdHandle[%p], eventInfos num[%u]",
                    i, eventInfos[i].fdHandle, eventsNum);
                return HCCL_E_TCP_CONNECT;
            }

            if (eventStatus.matched) {
                socket_peer_info *socketInfo = static_cast<socket_peer_info *>(fdHandle);
                CHK_PTR_NULL(socketInfo);
                if (eventInfos[i].fdHandle != socketInfo) {
                    continue;
                }
            }

            if ((eventInfos[i].event & static_cast<u32>(eventStatus.event)) != 0) {
                waitComleted = true;
                if (!eventStatus.matched) {
                    fdHandle = eventInfos[i].fdHandle;
                    CHK_PTR_NULL(fdHandle);
                }

                break;
            }
        }
    }

    return HCCL_SUCCESS;
}


HcclResult TransportHeterogEventTcp::BlockSend(const TransData &sendData, const TransportEndPointParam &epParam,
    HcclRequestInfo *&request, s32 waitTimeOut)
{
    CHK_RET(GenerateSendRequest(sendData, epParam, request));
    HCCL_DEBUG("Isend: peerRank[%u] tag[%d] buffer[%llu] count[%d] dataType[%s]", epParam.dst.rank,
        epParam.dst.tag, sendData.srcBuf, sendData.count, GetDataTypeEnumStr(sendData.dataType).c_str());

    std::vector<SocketEventInfo> eventInfos(EPOLL_EVENTS_NUM);

    EventStatus eventStatus;
    eventStatus.matched = true;
    eventStatus.event = EPOLLOUT;

    // 当前只考虑一个连接
    FdHandle fdHandle = initSM_.locInitInfo.socketInfo[0].fdHandle;

    bool envCompleted; // 信封数据是否完全发送成功
    bool tranCompleted; // 数据是否完全发送
    do {
        envCompleted = true; // 信封数据是否完全发送成功
        tranCompleted = true; // 数据是否完全发送
        TransportRequestInfo &transpReqInfo = request->transportRequest;
        CHK_RET(static_cast<TransportHeterogEventTcp*>(request->transportHandle)->SendNoBlock(transpReqInfo.transData,
            transpReqInfo.epParam, transpReqInfo.envoffset, transpReqInfo.tranoffset, envCompleted, tranCompleted));

        HcclResult ret = WaitEvents(sendEpollEventInfo_, eventInfos, eventStatus, fdHandle, waitTimeOut);
        CHK_PRT_RET(ret != HCCL_SUCCESS, HCCL_ERROR("WaitEvents Error, ret[%d]", ret), HCCL_E_INTERNAL);
    } while (!envCompleted || !tranCompleted);

    return HCCL_SUCCESS;
}

// matched为true，表示只处理当前tcp对象的tag；否则，哪个tag先到达就先收，并返回对应的transport。 后续优化提取manager类
HcclResult TransportHeterogEventTcp::BlockRecv(const TransData &recvData, bool matched,
    TransportHeterog *&transport, s32 waitTimeOut, s32 waitPayloadTimeOut)
{
    std::vector<SocketEventInfo> eventInfos(EPOLL_EVENTS_NUM);
    u64 recvSize = 0;
    bool envelopeRecved = false;
    HcclEnvelope envelope{};
    u64 byteSize = sizeof(HcclEnvelope);
    FdHandle fdHandle{};

    EventStatus eventStatus;
    eventStatus.matched = matched;
    eventStatus.event = EPOLLIN;

    if (eventStatus.matched) {
        // 当前只考虑一个连接
        fdHandle = initSM_.locInitInfo.socketInfo[0].fdHandle;
    }

    void *recvBuffer = reinterpret_cast<void *>(recvData.dstBuf);
    while (recvSize < byteSize) {
        // 内部会循环获取需要的fdHandle的事件，循环获取超时会返回。
        HcclResult ret = WaitEvents(gRecvEpollEventInfo, eventInfos, eventStatus, fdHandle, waitTimeOut);
        if (ret == HCCL_E_AGAIN) {
            if (envelopeRecved) {
                HCCL_ERROR("WaitEvents timeout, while envelopeRecved is true, TimeOut[%d] ms", waitTimeOut);
                return HCCL_E_TCP_TRANSFER;
            }

            return ret;
        } else if (UNLIKELY(ret != 0)) {
            HCCL_ERROR("WaitEvents error, ret[%d]", ret);
            return ret;
        }

        if (!envelopeRecved) {
            // 信封获取当前先一次性接收，后续优化考虑使用hrtRaSocketRecv方式
            CHK_RET(hrtRaSocketBlockRecv(fdHandle, &envelope, sizeof(envelope)));

            // matched为false，获取到fdHandle之后，都变成匹配接收的方式，即matched为true。
            if (!eventStatus.matched) {
                EXECEPTION_CATCH(transport = gFdhandleToTransportMap.at(fdHandle), return HCCL_E_TCP_TRANSFER);
                eventStatus.matched = true;
            }

            s32 count = envelope.transData.count;
            // 空信封
            if (count == 0) {
                HCCL_DEBUG("hrtRaSocketBlockRecv envelope count == 0");
                return HCCL_SUCCESS;
            } else if (UNLIKELY(count < 0)) {
                HCCL_ERROR("hrtRaSocketBlockRecv failed, count[%d] in envelope < 0", count);
                return HCCL_E_TCP_TRANSFER;
            }

            byteSize = static_cast<u64>(count) * SIZE_TABLE[envelope.transData.dataType];
            envelopeRecved = true;
            // 收到信封之后，调整接收报文的超时时间
            waitTimeOut = waitPayloadTimeOut;
        }

        CHK_RET(NoBlockRecv(fdHandle, recvBuffer, byteSize, recvSize));
    }

    return HCCL_SUCCESS;
}

HcclResult TransportHeterogEventTcp::NoBlockRecv(const FdHandle fdHandle, void *&recvBuffer, u64 byteSize,
    u64 &recvSize)
{
    u64 recvLen = 0;
    byteSize -= recvSize;
    s32 rtRet = hrtRaSocketRecv(fdHandle, recvBuffer, byteSize, &recvLen);
    if ((rtRet == 0) && (recvLen > 0)) {
        CHK_PRT_RET(recvLen > byteSize,
            HCCL_ERROR("hrtRaSocketRecv errNo[0x%016llx] socket receive recvLen[%llu] > size[%llu]",
            HCCL_ERROR_CODE(HCCL_E_TCP_TRANSFER), recvLen, byteSize), HCCL_E_TCP_TRANSFER);
        recvSize += recvLen;
        // 更新recvBuffer的位置
        recvBuffer = static_cast<s8 *>(recvBuffer) + recvLen;
    } else if ((rtRet == 0) && (recvLen == 0)) {
        HCCL_ERROR("hrtRaSocketRecv recv fail, recLen[%llu]", recvLen);
        return HCCL_E_TCP_TRANSFER;
    } else if ((rtRet == SOCK_EAGAIN) && (recvLen == 0)) {
        HCCL_DEBUG("hrtRaSocketRecv rtRet[%d] recv again", rtRet);
    } else {
        HCCL_ERROR("hrtRaSocketRecv rtRet[%d] recv[%llu] fail", rtRet, recvLen);
        return HCCL_E_TCP_TRANSFER;
    }

    return HCCL_SUCCESS;
}

HcclResult TransportHeterogEventTcp::CreateEventHandle()
{
    HcclResult ret;

    if (sendEpollEventInfo_.epollEventFd == INVALID_EPOLL_EVENT_FD) {
        ret = hrtRaCreateEventHandle(sendEpollEventInfo_.epollEventFd);
        if (ret != HCCL_SUCCESS) {
            HCCL_ERROR("hrtRaCreateEventHandle create sendEpollEventFd failed, ret[%d]", ret);
            return HCCL_E_TCP_TRANSFER;
        }
    }

    lock_guard<mutex> lock(gRecvEpollEventInfo.epollEventFdMtx);
    if (gRecvEpollEventInfo.epollEventFd == INVALID_EPOLL_EVENT_FD) {
        ret = hrtRaCreateEventHandle(gRecvEpollEventInfo.epollEventFd);
        if (ret != HCCL_SUCCESS) {
            HCCL_ERROR("hrtRaCreateEventHandle create recvEpollEventFd failed, ret[%d]", ret);
            return HCCL_E_TCP_TRANSFER;
        }
    }

    return HCCL_SUCCESS;
}

HcclResult TransportHeterogEventTcp::AddEpollEvents()
{
    for (int i = 0; i < LINK_NUM; i++) {
        CHK_RET(hrtRaCtlEventHandle(sendEpollEventInfo_.epollEventFd, initSM_.locInitInfo.socketInfo[i].fdHandle,
            EPOLL_CTL_ADD, HcclEpollEvent::HCCL_EPOLLOUT));

        lock_guard<mutex> lock(gRecvEpollEventInfo.epollEventFdMtx);
        CHK_RET(hrtRaCtlEventHandle(gRecvEpollEventInfo.epollEventFd, initSM_.locInitInfo.socketInfo[i].fdHandle,
            EPOLL_CTL_ADD, HcclEpollEvent::HCCL_EPOLLIN));
    }

    return HCCL_SUCCESS;
}

HcclResult TransportHeterogEventTcp::DestroyEventHandle()
{
    HcclResult ret;

    if (sendEpollEventInfo_.epollEventFd != INVALID_EPOLL_EVENT_FD) {
        ret = hrtRaDestroyEventHandle(sendEpollEventInfo_.epollEventFd);
        if (ret != HCCL_SUCCESS) {
            HCCL_ERROR("DestroyEventHandle destroy sendEpollEventFd failed, ret[%d]", ret);
            return HCCL_E_TCP_TRANSFER;
        }

        sendEpollEventInfo_.epollEventFd = INVALID_EPOLL_EVENT_FD;
    }

    lock_guard<mutex> lock(gRecvEpollEventInfo.epollEventFdMtx);
    if (gRecvEpollEventInfo.epollEventFd != INVALID_EPOLL_EVENT_FD) {
        ret = hrtRaDestroyEventHandle(gRecvEpollEventInfo.epollEventFd);
        if (ret != HCCL_SUCCESS) {
            HCCL_ERROR("DestroyEventHandle destroy recvEpollEventFd failed, ret[%d]", ret);
            return HCCL_E_TCP_TRANSFER;
        }

        gRecvEpollEventInfo.epollEventFd = INVALID_EPOLL_EVENT_FD;
    }

    return HCCL_SUCCESS;
}

HcclResult TransportHeterogEventTcp::DelEpollEvents()
{
    for (int i = 0; i < LINK_NUM; i++) {
        CHK_RET(hrtRaCtlEventHandle(sendEpollEventInfo_.epollEventFd, initSM_.locInitInfo.socketInfo[i].fdHandle,
            EPOLL_CTL_DEL, HcclEpollEvent::HCCL_EPOLLOUT));

        lock_guard<mutex> lock(gRecvEpollEventInfo.epollEventFdMtx);
        CHK_RET(hrtRaCtlEventHandle(gRecvEpollEventInfo.epollEventFd, initSM_.locInitInfo.socketInfo[i].fdHandle,
            EPOLL_CTL_DEL, HcclEpollEvent::HCCL_EPOLLIN));
    }

    return HCCL_SUCCESS;
}

}
