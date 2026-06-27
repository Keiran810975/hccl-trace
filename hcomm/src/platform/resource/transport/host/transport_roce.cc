/**
 * Copyright (c) 2025 Huawei Technologies Co., Ltd.
 * This program is free software, you can redistribute it and/or modify it under the terms and conditions of
 * CANN Open Software License Agreement Version 2.0 (the "License").
 * Please refer to the License for details. You may not use this file except in compliance with the License.
 * THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
 * INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
 * See LICENSE in the root of the software repository for the full text of the License.
 */

#include "transport_roce.h"
#include <arpa/inet.h>
#include <securec.h>
#include <fcntl.h>

#include "externalinput_pub.h"
#include "network/hccp.h"
#include "network/hccp_common.h"
#include "adapter_verbs.h"
#include "adapter_rts.h"
#include "dlibv_function.h"
#include "network_manager_pub.h"
#include "device_capacity.h"

using namespace hccl;

constexpr s32 REG_VALID = 1;
constexpr s32 HCCL_DEFAULT_INITIAL_VALUE = -1;

constexpr u32 RECV_WQE_BATCH_NUM = 64;
constexpr u32 RECV_WQE_NUM_THRESHOLD = 32;
constexpr u32 RECV_WQE_BATCH_SUPPLEMENT = 16;
constexpr u32 LOOP_SLEEP_TIME_US = 10;

TransportRoce::TransportRoce(const HcclDispatcher dispatcher,
    const std::unique_ptr<NotifyPool> &notifyPool,
    MachinePara &machinePara,
    std::chrono::milliseconds timeout, HcclIpAddress &selfIp, HcclIpAddress &peerIp, u32 peerPort, u32 selfPort,
    const TransportResourceInfo &transportResourceInfo, u32 proxyDevLogicId,
    bool isRootRank, bool isESPs)
    : TransportBase(reinterpret_cast<DispatcherPub*>(const_cast<HcclDispatcher>(dispatcher)),
        notifyPool, machinePara, timeout),
      TransportHeterogRoce(machinePara_.tag, selfIp, peerIp, peerPort, selfPort, transportResourceInfo),
      deviceLogicId_(HCCL_DEFAULT_INITIAL_VALUE), isInited_(false), proxyDevLogicId_(proxyDevLogicId),
      isRootRank_(isRootRank), isESPs_(isESPs)
{
    recvWithReduceParam_ = ReduceParam();
    recvWqeBatchNum_ = RECV_WQE_BATCH_NUM;
    recvWqeBatchThreshold_ = RECV_WQE_NUM_THRESHOLD;
    recvWqeBatchSupplement_ = RECV_WQE_BATCH_SUPPLEMENT;
}

TransportRoce::~TransportRoce()
{
}

HcclResult TransportRoce::RegUserMem(MemType memType)
{
    void *memPtr = nullptr;
    u64 memSize;
    switch (memType) {
        case USER_INPUT_MEM: {
            memPtr = machinePara_.inputMem.ptr();
            memSize = machinePara_.inputMem.size();
            break;
        }

        case USER_OUTPUT_MEM: {
            memPtr = machinePara_.outputMem.ptr();
            memSize = machinePara_.outputMem.size();
            break;
        }

        default: {
            HCCL_ERROR("[Reg][UserMem]not support dst_mem_type=%d", memType);
            return HCCL_E_NOT_SUPPORT;
        }
    }

    u32 lkey = 0;
    CHK_RET(mrManager_->GetKey(memPtr, memSize, lkey));

    memMsg_[memType].mrRegFlag = REG_VALID;
    memMsg_[memType].addr = memPtr;
    memMsg_[memType].len = memSize;
    memMsg_[memType].memType = memType;
    // 发送成功字节数与发送字节数不等，发送失败
    CHK_RET(hrtRaSocketBlockSend(socketFdHandles_[0], &memMsg_[memType], sizeof(MemMsg)));

    HCCL_DEBUG("memType=%d mem_ptr=%p mem_size=%llu Byte", memType, memPtr, memSize);

    return HCCL_SUCCESS;
}

HcclResult TransportRoce::GetRemoteAddr(MemType memType)
{
    MemMsg mrMsg;
    s32 sRet = memset_s(&mrMsg, sizeof(MemMsg), 0, sizeof(MemMsg));
    CHK_PRT_RET(sRet != EOK, HCCL_ERROR("[Get][RemoteAddr]errNo[0x%016llx]get remote addr, memory set 0 failed. \
        params: dest[%p], destMaxSize[%zu], count[%zu]", HCCL_ERROR_CODE(HCCL_E_MEMORY), \
        &mrMsg, sizeof(MemMsg), sizeof(MemMsg)), HCCL_E_MEMORY);

    CHK_RET(hrtRaSocketBlockRecv(socketFdHandles_[0], &mrMsg, sizeof(MemMsg)));
    CHK_PRT_RET((memType != mrMsg.memType), HCCL_ERROR("[Get][RemoteAddr]In lbv exp get remote addr, "\
        "receive type error. memType[%d] msg type[%d]", memType, mrMsg.memType), HCCL_E_INTERNAL);
    sRet = memcpy_s(&remoteMemMsg_[mrMsg.memType], sizeof(MemMsg), &mrMsg, sizeof(MemMsg));
    CHK_PRT_RET(sRet != EOK, HCCL_ERROR("[Get][RemoteAddr]errNo[0x%016llx] In lbv exp get remote addr, "\
        "memcpy failed. errorno[%d], params:dest[%p],destMaxSize[%zu],src[%p],count[%zu]",
        HCCL_ERROR_CODE(HCCL_E_MEMORY), sRet, static_cast<MemMsg *>(&remoteMemMsg_[mrMsg.memType]),
        sizeof(MemMsg), &mrMsg, sizeof(MemMsg)), HCCL_E_MEMORY);
    HCCL_INFO("recv success: memType=%d, addr=%p len=%llu", mrMsg.memType, mrMsg.addr, mrMsg.len);

    return HCCL_SUCCESS;
}

HcclResult TransportRoce::InitMem()
{
    // 注册本端输出内存，并发送至对端
    CHK_RET(RegUserMem(USER_OUTPUT_MEM));

    // 注册本端输入内存，并发送至对端
    CHK_RET(RegUserMem(USER_INPUT_MEM));

    // 获取对端输出内存
    CHK_RET(GetRemoteAddr(USER_OUTPUT_MEM));

    // 获取对端输入内存
    CHK_RET(GetRemoteAddr(USER_INPUT_MEM));

    return HCCL_SUCCESS;
}

HcclResult TransportRoce::CreateCqAndQp()
{
    if (isESMode_) {
        return TransportHeterogRoce::CreateCqAndQp();
    }

    HCCL_INFO("TransportRoce CreateCompChannel");
    // 创建Comp Channel
    void *tagSendChannel = nullptr;
    void *tagRecvChannel = nullptr;
    void *dataSendCompChannel = nullptr;
    void *dataRecvCompChannel = nullptr;
    CHK_RET(hrtRaCreateCompChannel(nicRdmaHandle_, &tagSendChannel));
    CHK_RET(hrtRaCreateCompChannel(nicRdmaHandle_, &tagRecvChannel));
    CHK_RET(hrtRaCreateCompChannel(nicRdmaHandle_, &dataSendCompChannel));
    CHK_RET(hrtRaCreateCompChannel(nicRdmaHandle_, &dataRecvCompChannel));

    // 创建CQ和QP
    HCCL_INFO("TransportRoce CreateCqAndQp");
    CHK_RET(CreateQpWithCq(nicRdmaHandle_, -1, -1, tagSendChannel, tagRecvChannel, tagQpInfo_));
    CHK_RET(CreateQpWithCq(nicRdmaHandle_, -1, -1, dataSendCompChannel, dataRecvCompChannel, dataQpInfo_));

    return HCCL_SUCCESS;
}

HcclResult TransportRoce::DestroyCqAndQp()
{
    if (isESMode_) {
        return TransportHeterogRoce::DestroyCqAndQp();
    }

    HCCL_INFO("TransportRoce DestroyCqAndQp");
    CHK_RET(DestroyQpWithCq(tagQpInfo_));
    CHK_RET(DestroyQpWithCq(dataQpInfo_));

    HCCL_INFO("TransportRoce DestroyCompChannel");
    CHK_RET(hrtRaDestroyCompChannel(nicRdmaHandle_, reinterpret_cast<void *>(tagQpInfo_.sendChannel)));
    CHK_RET(hrtRaDestroyCompChannel(nicRdmaHandle_, reinterpret_cast<void *>(tagQpInfo_.recvChannel)));
    CHK_RET(hrtRaDestroyCompChannel(nicRdmaHandle_, reinterpret_cast<void *>(dataQpInfo_.sendChannel)));
    CHK_RET(hrtRaDestroyCompChannel(nicRdmaHandle_, reinterpret_cast<void *>(dataQpInfo_.recvChannel)));

    tagQpInfo_ = QpInfo();
    dataQpInfo_ = QpInfo();

    return HCCL_SUCCESS;
}

// GetNicHandle函数TCP、ibv都在使用
HcclResult TransportRoce::GetNicHandle()
{
    RaResourceInfo raResourceInfo;
    CHK_RET(NetworkManager::GetInstance(machinePara_.deviceLogicId).GetRaResourceInfo(raResourceInfo));
    std::map<HcclIpAddress, IpSocket> &tmpSocketMap = machinePara_.nicDeploy == NICDeployment::NIC_DEPLOYMENT_DEVICE ?
        raResourceInfo.nicSocketMap : raResourceInfo.hostNetSocketMap;

    HcclIpAddress localIpAddr = machinePara_.localIpAddr;

    // 获取 nicSocketHandle
    auto itSocket = tmpSocketMap.find(localIpAddr);
    if (itSocket == tmpSocketMap.end()) {
        HCCL_ERROR("[Get][NicHandle]In get nic handle, can not find socket handle, handle size[%u], "\
            "local ip[%s]", tmpSocketMap.size(), localIpAddr.GetReadableAddress());
        return HCCL_E_PARA;
    }
    nicSocketHandle_ = itSocket->second.nicSocketHandle;
    CHK_PTR_NULL(nicSocketHandle_);

    nicRdmaHandle_ = itSocket->second.nicRdmaHandle;
    CHK_PTR_NULL(nicRdmaHandle_);

    return HCCL_SUCCESS;
}

HcclResult TransportRoce::GetSocketInfo()
{
    CHK_RET(GetSocketInfos(socketsInfo_));
    for (u32 nicIdx = 0; nicIdx < socketsInfo_.size(); nicIdx++) {
        if (nicSocketHandle_ == socketsInfo_[nicIdx][0].socketHandle) {
            for (u32 fdHandleIdx = 0; fdHandleIdx < socketsInfo_[nicIdx].size(); fdHandleIdx++) {
                socketFdHandles_.push_back(socketsInfo_[nicIdx][fdHandleIdx].fdHandle);
            }
            break;
        }
    }
    CHK_PRT_RET(socketFdHandles_.size() == 0,
        HCCL_ERROR("[Get][SocketInfo]transport roce init failed, get socket fd handle fail."), HCCL_E_INTERNAL);

    return HCCL_SUCCESS;
}

HcclResult TransportRoce::Connect()
{
    if (isESMode_) {
        return TransportHeterog::WaitBuildLinkComplete();
    }

    RoceRankInfo buffer{};
    // rankID小的作为发送，大的作为接受
    if (machinePara_.localUserrank < machinePara_.remoteUserrank) {
        HcclRequestInfo* request = nullptr;
        s32 flag = HCCL_TEST_INCOMPLETED;
        HcclStatus compState = {0};
        buffer.localUserrank = machinePara_.localUserrank;
        buffer.remoteUserrank = machinePara_.remoteUserrank;
        TransData sendData(reinterpret_cast<u64>(&buffer), reinterpret_cast<u64>(nullptr), sizeof(RoceRankInfo),
            HCCL_DATA_TYPE_INT8);
        TransportEndPointInfo srcEp(0, machinePara_.localUserrank, 0);
        TransportEndPointInfo dstEp(0, machinePara_.remoteUserrank, 0);
        TransportEndPointParam epParam(srcEp, dstEp);
        CHK_RET(Isend(sendData, epParam, request));
        // Test推动异步建链
        while (flag != HCCL_TEST_COMPLETED) {
            CHK_RET(IsProcessStop());
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
        TransportEndPointInfo srcEp(0, machinePara_.remoteUserrank, 0);
        TransportEndPointInfo dstEp(0, machinePara_.localUserrank, 0);
        TransportEndPointParam epParam(srcEp, dstEp);
        // Improbe推动异步建链
        while (improbeFlag != HCCL_IMPROBE_COMPLETED) {
            CHK_RET(IsProcessStop());
            CHK_RET(Improbe(epParam, improbeFlag, msg, status));
            CHK_PRT_RET(status.error > 0, HCCL_ERROR("Improbe failed, status.error[%d].", status.error),
                HCCL_E_INTERNAL);
            SaluSleep(ONE_HUNDRED_MICROSECOND_OF_USLEEP);
        }

        TransData recvData(reinterpret_cast<u64>(nullptr), reinterpret_cast<u64>(&buffer),
            sizeof(RoceRankInfo), HCCL_DATA_TYPE_INT8);
        CHK_RET(Imrecv(recvData, *msg, request));
        // 此处已经完成建链，可以使用 WaitCompletion
        CHK_RET(Test(*request, testFlag, compState));
        CHK_PRT_RET(compState.error > 0, HCCL_ERROR("Test failed, status.error[%d].", compState.error),
            HCCL_E_INTERNAL);
        while (testFlag != HCCL_TEST_COMPLETED) {
            CHK_RET(IsProcessStop());
            if (!isESMode_) {
                CHK_RET(WaitCompletion(dataQpInfo_.sendCq, dataQpInfo_.sendChannel));
            }
            CHK_RET(Test(*request, testFlag, compState));
            CHK_PRT_RET(compState.error > 0, HCCL_ERROR("Test failed, compState.error[%d].", compState.error),
                HCCL_E_INTERNAL);
        }

        HCCL_INFO("recv envelope localRank=[%u], remoteRank=[%u]",
            buffer.localUserrank,
            buffer.remoteUserrank);
    }
    return HCCL_SUCCESS;
}

HcclResult TransportRoce::SendAndRecvExchangeData()
{
    u64 dataLength = machinePara_.exchangeInfo.size();
    if (dataLength == 0) {
        HCCL_DEBUG("[SendAndRecv][ExchangeData]exchangeInfo size is 0.");
        return HCCL_SUCCESS;
    }
    HCCL_DEBUG("[SendAndRecv][ExchangeData]exchangeInfo size[%llu].", dataLength);
    HcclResult ret = hrtRaSocketBlockSend(socketFdHandles_[0], machinePara_.exchangeInfo.data(), dataLength);
    CHK_PRT_RET(ret != HCCL_SUCCESS,
        HCCL_ERROR("[SendAndRecv][ExchangeData]failed to send custom exchange data size [%llu].",
        dataLength), ret);

    exchangeMsg_.resize(dataLength);

    ret = hrtRaSocketBlockRecv(socketFdHandles_[0], exchangeMsg_.data(), dataLength);
    CHK_PRT_RET(ret != HCCL_SUCCESS,
        HCCL_ERROR("[SendAndRecv][ExchangeData]failed to recv custom exchange data size [%llu].",
        dataLength), ret);

    return HCCL_SUCCESS;
}

HcclResult TransportRoce::Init()
{
    HCCL_INFO(
        "machineType=[%d], serverId=[%s], localDeviceId=[%d], remoteDeviceId=[%d]," \
        "localRank=[%u], localUserRank=[%u], remoteRank=[%u], remoteUserRank=[%u]," \
        "deviceType=[%d], inputMem=%p, outputMem=%p, custom exchange data size [%llu].",
        machinePara_.machineType, machinePara_.serverId.c_str(), machinePara_.localDeviceId,
        machinePara_.remoteDeviceId, machinePara_.localUserrank, machinePara_.localWorldRank,
        machinePara_.remoteUserrank, machinePara_.remoteWorldRank,
        machinePara_.deviceType, machinePara_.inputMem.ptr(),
        machinePara_.outputMem.ptr(), machinePara_.exchangeInfo.size());

    transportAttr_.linkType = hccl::LinkType::LINK_STANDARD_ROCE;
    isProcessStop_ = false;

    CHK_SMART_PTR_NULL(machinePara_.inputMem);
    CHK_SMART_PTR_NULL(machinePara_.outputMem);
    CHK_RET(CheckExchangeData());
    if (isESMode_) {
        if (!isESPs_) {
            CHK_RET(DeviceMem::alloc(sendEnvelopeMem_, sizeof(HcclEnvelope)));
            CHK_RET(MrManager::GetInstance().RegGlobalMr(sendEnvelopeMem_.ptr(), sendEnvelopeMem_.size()));
        }

        if (isHdcMode_) {
            CHK_RET(MrManager::GetInstance().RegGlobalMr(machinePara_.inputMem.ptr(), machinePara_.inputMem.size()));
            CHK_RET(MrManager::GetInstance().RegGlobalMr(machinePara_.outputMem.ptr(), machinePara_.outputMem.size()));
        }
    } else {
        CHK_RET(DlIbvFunction::GetInstance().DlIbvFunctionInit());
    }

    if (Is310PDevice()) {
        CHK_RET(hrtGetDevice(&deviceLogicId_));
        CHK_PTR_NULL(dispatcher_);
        CHK_SMART_PTR_NULL(notifyPool_);
    } else {
        deviceLogicId_ = HOST_DEVICE_ID;
    }

    // ES模式 通用服务器ps侧不在此获取Nichandle校验
    if (!(IsGeneralServer() && isESMode_ && deviceLogicId_ == HOST_DEVICE_ID)) {
        CHK_RET(GetNicHandle());
    }

    // save流程通用服务器侧HcclImplBase::Init(HcclCommParams &params, const RankTable_t &rankTable)中deviceLogicId_为 0
    // 此处deviceLogicId_为-1 index默认为0  此处不可使用deviceLogicId_设置index
    if (IsGeneralServer() && GetRemoteIsHdc()) {
        HCCL_INFO("no need set Device");
    } else if (isESMode_ && isHdcMode_) {
        HCCL_INFO("set Device proxyDevLogicId_");
        CHK_RET(TransportHeterog::SetDeviceIndex(proxyDevLogicId_));
    } else {
        HCCL_INFO("set Device deviceLogicId_");
        CHK_RET(TransportHeterog::SetDeviceIndex(deviceLogicId_));
    }

    CHK_RET(TransportHeterogRoce::Init()); // 创建channel、cq、qp，准备WQE，CRC校验

    CHK_RET(Connect()); // 推动建链

    CHK_RET(GetSocketInfo());
    CHK_RET(SendAndRecvExchangeData());

    CHK_RET(InitMem()); // 初始化内存信息

    isInited_ = true;

    struct QpAttr attr{};
    hrtRaGetQpAttr(tagQpInfo_.qpHandle, &attr);
    HCCL_USER_CRITICAL_LOG("create hccl transport:communicator[%s], local rank[%u] ip[%s], remote rank[%u] ip[%s], "\
        "transporttype[%s], rdma qpn[%u], rdma qp sport[%u].", machinePara_.collectiveId.c_str(), machinePara_.localUserrank, 
        machinePara_.localIpAddr.GetReadableAddress(), machinePara_.remoteUserrank, machinePara_.remoteIpAddr.GetReadableAddress(),
        GetLinkTypeEnumStr(GetLinkType()).c_str(), attr.qpn, attr.udpSport);
        
    return HCCL_SUCCESS;
}

HcclResult TransportRoce::DeInit()
{
    if (!isInited_) {
        return HCCL_SUCCESS;
    }
    if (!isESPs_) {
        // 解注册信封内存
        CHK_RET(MrManager::GetInstance().DeRegGlobalMr(sendEnvelopeMem_.ptr()));
    }

    if (isHdcMode_) {
        CHK_RET(MrManager::GetInstance().DeRegGlobalMr(machinePara_.inputMem.ptr()));
        CHK_RET(MrManager::GetInstance().DeRegGlobalMr(machinePara_.outputMem.ptr()));
    }

    // 解注册本端输出内存
    CHK_RET(mrManager_->ReleaseKey(memMsg_[USER_OUTPUT_MEM].addr, memMsg_[USER_OUTPUT_MEM].len));

    // 解注册本端输入内存
    if (memMsg_[USER_INPUT_MEM].addr != memMsg_[USER_OUTPUT_MEM].addr) {
        CHK_RET(mrManager_->ReleaseKey(memMsg_[USER_INPUT_MEM].addr, memMsg_[USER_INPUT_MEM].len));
    }

    // 销毁channel、cq、qp
    CHK_RET(TransportHeterogRoce::Deinit());
    isInited_ = false;
    return HCCL_SUCCESS;
}

HcclResult TransportRoce::Deinit()
{
    return DeInit();
}

HcclResult TransportRoce::TxDataSignal(Stream &stream)
{
    return HCCL_SUCCESS;
}

HcclResult TransportRoce::RxDataSignal(Stream &stream)
{
    return HCCL_SUCCESS;
}

HcclResult TransportRoce::WaitDone(HcclRequestInfo *request)
{
    s32 flag = HCCL_TEST_INCOMPLETED;
    while (flag != HCCL_TEST_COMPLETED) {
        if (request == nullptr) {
            break;
        }

        CHK_RET(IsProcessStop());
        HcclStatus compState;
        CHK_RET(Test(*request, flag, compState));
        if (flag == HCCL_TEST_COMPLETED) {
            request = nullptr;
            break;
        } else {
            flag = HCCL_TEST_INCOMPLETED;
        }
        SaluSleep(LOOP_SLEEP_TIME_US);
    }
    return HCCL_SUCCESS;
}

HcclResult TransportRoce::TxAsync(UserMemType dstMemType, u64 dstOffset, const void *src,
                                  u64 len, Stream &stream)
{
    if (dataQpInfo_.qpMode == NORMAL_QP_MODE && !IsGeneralServer()) {
        s32 streamId = 0;
        CHK_RET(hrtGetStreamId(stream.ptr(), streamId));
        if (len > 0) {
            SendRecvParam sendParam(const_cast<void *>(src), len, streamId, this);
            sendParam.queIndex = taskOrchestration_[streamId].size();
            taskOrchestration_[streamId].push_back(std::make_pair(OperationType::OP_SEND, sendParam));
            CHK_RET(hrtCallbackLaunch(TaskExecCallback, &taskOrchestration_[streamId].back().second,
                stream.ptr(), true));
        }
        return HCCL_SUCCESS;
    }

    if (!isESPs_) {
        std::shared_ptr<LocalIpcNotify> remoteImrecvDoneSignal;
        CHK_RET(GetRemoteImrecvDoneSignal(remoteImrecvDoneSignal));
        CHK_RET(LocalIpcNotify::Wait(stream, dispatcher_, remoteImrecvDoneSignal, INVALID_VALUE_STAGE,
            NOTIFY_INVALID_WAIT_TIME, machinePara_.localUserrank, machinePara_.remoteUserrank));

        s32 streamId = 0;
        CHK_RET(hrtGetStreamId(stream.ptr(), streamId));
        if (len > 0) {
            SendRecvParam recvParam(const_cast<void *>(src), len, streamId, this);
            taskOrchestration_[streamId].push_back(std::make_pair(OperationType::OP_RECV, recvParam));
        }
        return HCCL_SUCCESS;
    }

    HCCL_INFO("TransportRoce TxAsync rdma_write start!");
    // rdma_write向对端写数据，不产生cq
    HcclEnvelopeSummary envelope;
    HcclRequestInfo *request = nullptr;
    if (GetSavedEnvelope(envelope)) {
        TransData sendData(reinterpret_cast<u64>(src), reinterpret_cast<u64>(nullptr), len, HCCL_DATA_TYPE_INT8);
        CHK_RET(Iwrite(sendData, envelope.envelope, request));
    }

    CHK_RET(WaitDone(request));
    return HCCL_SUCCESS;
}

// 分级alltoallv才会用的，暂时不考虑实现
HcclResult TransportRoce::TxAsync(std::vector<TxMemoryInfo>& txMems, Stream &stream)
{
    return HCCL_SUCCESS;
}

HcclResult TransportRoce::IsProcessStop()
{
    if (isProcessStop_) {
        return HCCL_E_AGAIN;
    }

    return HCCL_SUCCESS;
}

void TransportRoce::Break()
{
    HCCL_INFO("The process would be stopped!");
    isProcessStop_ = true;
}

// wr_list:RDMA_READ+RDMA_SEND(ACK)
HcclResult TransportRoce::RxAsync(UserMemType srcMemType, u64 srcOffset, void *dst, u64 len, Stream &stream)
{
    if (dataQpInfo_.qpMode == NORMAL_QP_MODE && !IsGeneralServer()) {
        s32 streamId = 0;
        CHK_RET(hrtGetStreamId(stream.ptr(), streamId));
        if (len > 0) {
            SendRecvParam recvParam(dst, len, streamId, this);
            taskOrchestration_[streamId].push_back(std::make_pair(OperationType::OP_RECV, recvParam));
        }
        return HCCL_SUCCESS;
    }

    if (!isESPs_) {
        std::shared_ptr<LocalIpcNotify> remoteIsendDoneSignal;
        GetRemoteIsendDoneSignal(remoteIsendDoneSignal);
        CHK_RET(LocalIpcNotify::Wait(stream, dispatcher_, remoteIsendDoneSignal, INVALID_VALUE_STAGE,
            NOTIFY_INVALID_WAIT_TIME, machinePara_.localUserrank, machinePara_.remoteUserrank));

        s32 streamId = 0;
        CHK_RET(hrtGetStreamId(stream.ptr(), streamId));
        if (len > 0) {
            SendRecvParam recvParam(dst, len, streamId, this);
            taskOrchestration_[streamId].push_back(std::make_pair(OperationType::OP_RECV, recvParam));
        }
        return HCCL_SUCCESS;
    }

    HcclEnvelopeSummary envelope;
    HcclRequestInfo *request = nullptr;
    if (GetSavedEnvelope(envelope)) {
        TransData recvData(reinterpret_cast<u64>(nullptr), reinterpret_cast<u64>(dst), len, HCCL_DATA_TYPE_INT8);
        HcclMessageInfo* tmpMsg;
        HcclStatus status;
        GenerateRecvMessage(envelope, tmpMsg, status);
        CHK_RET(Imrecv(recvData, *tmpMsg, request));
        HCCL_INFO("request->transportRequest.requestType[%d]", request->transportRequest.requestType);
    }

    // notify通知对端
    HcclRequestInfo *requestNotify = nullptr;
    CHK_RET(RecordNotifyWithReq(stream, RdmaNotifyOp::RECV_NOTIFY, requestNotify));

    CHK_RET(WaitDone(request));
    return HCCL_SUCCESS;
}

// 分级alltoallv才会用的，暂时不考虑实现
HcclResult TransportRoce::RxAsync(std::vector<RxMemoryInfo>& rxMems, Stream &stream)
{
    return HCCL_SUCCESS;
}

HcclResult TransportRoce::TxAck(Stream &stream)
{
    return HCCL_SUCCESS;
}

HcclResult TransportRoce::RxAck(Stream &stream)
{
    return HCCL_SUCCESS;
}

HcclResult TransportRoce::TxPrepare(Stream &stream)
{
    return HCCL_SUCCESS;
}

HcclResult TransportRoce::RxPrepare(Stream &stream)
{
    return HCCL_SUCCESS;
}


HcclResult TransportRoce::TxData(UserMemType dstMemType, u64 dstOffset, const void *src, u64 len, Stream &stream)
{
    CHK_RET(TxAsync(dstMemType, dstOffset, src, len, stream));
    return HCCL_SUCCESS;
}

HcclResult TransportRoce::RxData(UserMemType srcMemType, u64 srcOffset, void *dst, u64 len, Stream &stream)
{
    CHK_RET(RxAsync(srcMemType, srcOffset, dst, len, stream));
    return HCCL_SUCCESS;
}

HcclResult TransportRoce::TxDone(Stream &stream)
{
    return HCCL_SUCCESS;
}

HcclResult TransportRoce::RxDone(Stream &stream)
{
    return HCCL_SUCCESS;
}

// callback实现send、recv
void TaskExecCallback(void *fnData)
{
    SendRecvParam *params = static_cast<SendRecvParam *>(fnData);
    HcclResult ret = HCCL_SUCCESS;
    TransportRoce *tmpDispatcherPtr = static_cast<TransportRoce *>(params->transportRocePtr);
    ret = tmpDispatcherPtr->TaskExec(params->streamId, params->queIndex);
    if (ret != HCCL_SUCCESS) {
        HCCL_ERROR("[TaskExecCallback] TaskExec failed");
    }
}

// 下发callback任务
HcclResult TransportRoce::TxWaitDone(Stream &stream)
{
    // 判断当前stream中最后一个task是否是WaitDone类型的，若是，则不下callback；反之，下发callback
    s32 streamId = 0;
    CHK_RET(hrtGetStreamId(stream.ptr(), streamId));
    if (taskOrchestration_[streamId].size() != 0 &&
        taskOrchestration_[streamId].back().first != OperationType::OP_WAIT_DONE) {
        s32 queIndex = taskOrchestration_[streamId].size();
        SendRecvParam tempParam(streamId, this, queIndex);
        taskOrchestration_[streamId].push_back(std::make_pair(OperationType::OP_WAIT_DONE, tempParam));

        // 下发callback任务
        HCCL_INFO("param[%p] streamId[%d] queIndex[%d]", &taskOrchestration_[streamId].back().second,
            taskOrchestration_[streamId].back().second.streamId, taskOrchestration_[streamId].back().second.queIndex);
        CHK_RET(hrtCallbackLaunch(TaskExecCallback, &taskOrchestration_[streamId].back().second, stream.ptr(), true));
        if (recvWithReduceParam_.stream != nullptr) {
            CHK_RET(dispatcher_->ReduceAsync(recvWithReduceParam_.src, recvWithReduceParam_.dst,
                recvWithReduceParam_.dataCount, recvWithReduceParam_.datatype,
                recvWithReduceParam_.reduceOp, stream, recvWithReduceParam_.reduceType));
            recvWithReduceParam_ = ReduceParam();
        }
    }
    return HCCL_SUCCESS;
}

// 下发callback任务
HcclResult TransportRoce::RxWaitDone(Stream &stream)
{
    // 判断当前stream中最后一个task是否是WaitDone类型的，若是，则不下callback；反之，下发callback
    s32 streamId = 0;
    CHK_RET(hrtGetStreamId(stream.ptr(), streamId));
    if (taskOrchestration_[streamId].size() != 0 &&
        taskOrchestration_[streamId].back().first != OperationType::OP_WAIT_DONE) {
        s32 queIndex = taskOrchestration_[streamId].size();
        SendRecvParam tempParam(streamId, this, queIndex);
        taskOrchestration_[streamId].push_back(std::make_pair(OperationType::OP_WAIT_DONE, tempParam));

        // 下发callback任务
        CHK_RET(hrtCallbackLaunch(TaskExecCallback, &taskOrchestration_[streamId].back().second,
            stream.ptr(), true));
        if (recvWithReduceParam_.stream != nullptr) {
            CHK_RET(dispatcher_->ReduceAsync(recvWithReduceParam_.src, recvWithReduceParam_.dst,
                recvWithReduceParam_.dataCount, recvWithReduceParam_.datatype,
                recvWithReduceParam_.reduceOp, stream, recvWithReduceParam_.reduceType));
            recvWithReduceParam_ = ReduceParam();
        }
    }
    return HCCL_SUCCESS;
}

HcclResult TransportRoce::GetRemoteMem(UserMemType memType, void **remotePtr)
{
    switch (memType) {
        case UserMemType::INPUT_MEM:
        case UserMemType::OUTPUT_MEM:
            *remotePtr = remoteMemMsg_[static_cast<u32>(memType)].addr;
            break;

        default:
            HCCL_ERROR("[Get][RemoteMem]not support dst_mem_type=%d", memType);
            return HCCL_E_NOT_SUPPORT;
    }
    return HCCL_SUCCESS;
}

HcclResult TransportRoce::GetRemoteMemSize(UserMemType memType, u64 &size)
{
    switch (memType) {
        case UserMemType::INPUT_MEM:
        case UserMemType::OUTPUT_MEM:
            size = remoteMemMsg_[static_cast<u32>(memType)].len;
            break;

        default:
            HCCL_ERROR("[Get][RemoteMem]not support dst_mem_type=%d", memType);
            return HCCL_E_NOT_SUPPORT;
    }
    return HCCL_SUCCESS;
}

HcclResult TransportRoce::TxWithReduce(UserMemType dstMemType, u64 dstOffset, const void *src, u64 len,
    const HcclDataType datatype, HcclReduceOp redOp, Stream &stream)
{
    CHK_RET(TxAsync(dstMemType, dstOffset, src, len, stream));
    return HCCL_SUCCESS;
}

HcclResult TransportRoce::RxWithReduce(UserMemType recvSrcMemType, u64 recvSrcOffset, void *recvDst, u64 recvLen,
    void *reduceSrc, void *reduceDst, u64 reduceDataCount, HcclDataType reduceDatatype,
    HcclReduceOp reduceOp, Stream &stream, u64 reduceAttr)
{
    s32 streamId = 0;
    CHK_RET(hrtGetStreamId(stream.ptr(), streamId));

    if (recvLen > 0) {
        HcclReduceType reduceType = HcclReduceType::HCCL_TBE_REDUCE;
        if ((INLINE_REDUCE_BITMASK & reduceAttr) != 0) {
            reduceType = HcclReduceType::HCCL_INLINE_REDUCE;
        }
        SendRecvParam recvParam(recvDst, recvLen, streamId, this);
        taskOrchestration_[streamId].push_back(std::make_pair(OperationType::OP_RECV_WITH_REDUCE, recvParam));
        recvWithReduceParam_ = ReduceParam(reduceSrc, reduceDst, reduceDataCount, reduceDatatype, reduceOp,
            stream.ptr(), reduceType);
    }
    return HCCL_SUCCESS;
}

bool TransportRoce::IsSupportTransportWithReduce()
{
    return true;
}

// callback实现
// 参数列表：streamId
// TransportRoce配合参数：stream任务队列
// 队列中加判断决定调用send、recv、sendrecv
// 调用完成后及时更新stream队列状态
HcclResult TransportRoce::TaskExec(s32 streamId, s32 queIndex)
{
    if (taskOrchestration_[streamId].size() == 0 ||queIndex >= static_cast<s32>(taskOrchestration_[streamId].size())) {
        HCCL_WARNING("cur TaskExec para is invalid, streamId[%d], queIndex[%d]", streamId, queIndex);
        return HCCL_SUCCESS;
    }

    // 若入参queIndex对应send任务，下发Isend任务
    if (taskOrchestration_[streamId][queIndex].first == OperationType::OP_SEND) {
        // 异步send
        CHK_RET(SendAsync(taskOrchestration_[streamId][queIndex].second));
        return HCCL_SUCCESS;
    }

    // 判断当前callback执行哪个任务，解析任务队列
    bool haveSend = false;
    bool haveRecv = false;
    SendRecvParam sendParam;
    SendRecvParam recvParam;
    queIndex--;
    while (queIndex >= 0) {
        if (taskOrchestration_[streamId][queIndex].first == OperationType::OP_WAIT_DONE) {
            HCCL_INFO("[TaskExec] OperationType[%u]", static_cast<u32>(taskOrchestration_[streamId][queIndex].first));
            break;
        }
        if (taskOrchestration_[streamId][queIndex].first == OperationType::OP_SEND) {
            haveSend = true;
            sendParam = taskOrchestration_[streamId][queIndex].second;
        } else if (taskOrchestration_[streamId][queIndex].first == OperationType::OP_RECV ||
            taskOrchestration_[streamId][queIndex].first == OperationType::OP_RECV_WITH_REDUCE) {
            haveRecv = true;
            recvParam = taskOrchestration_[streamId][queIndex].second;
        }
        queIndex--;
    }

    if (haveSend && haveRecv) {
        // wait 异步send done + 同步recv
        CHK_RET(WaitSendAsyncCompleteAndRecv(sendParam, recvParam));
    } else if (haveSend) {
        // wait 异步send done
        CHK_RET(WaitSendAsyncComplete(sendParam));
    } else if (haveRecv) {
        // 同步recv
        CHK_RET(Recv(recvParam));
    }
    return HCCL_SUCCESS;
}

HcclResult TransportRoce::WaitCompletion(struct ibv_cq* notifyCq, struct ibv_comp_channel *channel)
{
    void *cqContext = nullptr;
    struct ibv_cq *evCq;
    CHK_RET(hrtIbvReqNotifyCq(notifyCq, 0));

    CHK_RET(hrtIbvGetCqEvent(channel, &evCq, &cqContext));
    hrtIbvAckCqEvent(evCq, 1);
    return HCCL_SUCCESS;
}

// Isend语义实现：RDMA send
HcclResult TransportRoce::SendAsync(SendRecvParam &sendParam)
{
    CHK_PTR_NULL(sendParam.ptr);
    HcclRequestInfo* request = nullptr;

    // 组装信封
    TransData sendData(
        reinterpret_cast<u64>(sendParam.ptr), reinterpret_cast<u64>(nullptr), sendParam.len, HCCL_DATA_TYPE_INT8);
    TransportEndPointInfo srcEp(0, machinePara_.localUserrank, 0);
    TransportEndPointInfo dstEp(0, machinePara_.remoteUserrank, 0);
    TransportEndPointParam epParam(srcEp, dstEp);
    CHK_RET(Isend(sendData, epParam, request));

    sendParam.sendRequest = request;
    return HCCL_SUCCESS;
}

// Send语义实现 ：RDMA send -> wait tag sq cqe、data rq cqe
HcclResult TransportRoce::Send(const SendRecvParam &sendParam)
{
    CHK_PTR_NULL(sendParam.ptr);
    s32 flag = HCCL_TEST_INCOMPLETED;
    HcclStatus compState = {0};
    HcclRequestInfo* request = nullptr;
    TransData sendData(
        reinterpret_cast<u64>(sendParam.ptr), reinterpret_cast<u64>(nullptr), sendParam.len, HCCL_DATA_TYPE_INT8);
    TransportEndPointInfo srcEp(0, machinePara_.localUserrank, 0);
    TransportEndPointInfo dstEp(0, machinePara_.remoteUserrank, 0);
    TransportEndPointParam epParam(srcEp, dstEp);
    CHK_RET(Isend(sendData, epParam, request));

    CHK_RET(Test(*request, flag, compState));
    CHK_PRT_RET(compState.error > 0, HCCL_ERROR("Test failed, status.error[%d].", compState.error),
        HCCL_E_INTERNAL);
    while (flag != HCCL_TEST_COMPLETED) {
        CHK_RET(IsProcessStop());
        if (!isESMode_) {
            CHK_RET(WaitCompletion(dataQpInfo_.recvCq, dataQpInfo_.recvChannel));
        }
        CHK_RET(Test(*request, flag, compState));
        CHK_PRT_RET(compState.error > 0, HCCL_ERROR("Test failed, compState.error[%d].", compState.error),
            HCCL_E_INTERNAL);
    }
    return HCCL_SUCCESS;
}

// WaitSendComplete语义实现 ：wait rcqe
HcclResult TransportRoce::WaitSendAsyncComplete(const SendRecvParam &sendParam)
{
    CHK_PTR_NULL(sendParam.ptr);
    s32 flag = HCCL_TEST_INCOMPLETED;
    HcclStatus compState = {0};
    HcclRequestInfo* request = sendParam.sendRequest;

    CHK_RET(Test(*request, flag, compState));
    CHK_PRT_RET(compState.error > 0, HCCL_ERROR("Test failed, status.error[%d].", compState.error),
        HCCL_E_INTERNAL);
    while (flag != HCCL_TEST_COMPLETED) {
        CHK_RET(IsProcessStop());
        if (!isESMode_) {
            CHK_RET(WaitCompletion(dataQpInfo_.recvCq, dataQpInfo_.recvChannel));
        }
        CHK_RET(Test(*request, flag, compState));
        CHK_PRT_RET(compState.error > 0, HCCL_ERROR("Test failed, compState.error[%d].", compState.error),
            HCCL_E_INTERNAL);
    }
    return HCCL_SUCCESS;
}

// Recv语义实现 ：wait cqe -> （RDMA read + RDMA send）
HcclResult TransportRoce::Recv(const SendRecvParam &recvParam)
{
    CHK_PTR_NULL(recvParam.ptr);
    s32 improbeFlag = HCCL_IMPROBE_INCOMPLETED;
    s32 TestFlag = HCCL_TEST_INCOMPLETED;
    HcclStatus status = {0};
    HcclStatus compState = {0};
    HcclMessageInfo *msg = nullptr;
    TransportEndPointInfo srcEp(0, machinePara_.localUserrank, 0);
    TransportEndPointInfo dstEp(0, machinePara_.remoteUserrank, 0);
    TransportEndPointParam epParam(srcEp, dstEp);

    CHK_RET(Improbe(epParam, improbeFlag, msg, status));
    CHK_PRT_RET(status.error > 0, HCCL_ERROR("Improbe failed, status.error[%d].", status.error),
        HCCL_E_INTERNAL);
    while (improbeFlag != HCCL_IMPROBE_COMPLETED) {
        CHK_RET(IsProcessStop());
        if (!isESMode_) {
            CHK_RET(WaitCompletion(tagQpInfo_.recvCq, tagQpInfo_.recvChannel));
        }
        CHK_RET(Improbe(epParam, improbeFlag, msg, status));
        CHK_PRT_RET(status.error > 0, HCCL_ERROR("Improbe failed, status.error[%d].", status.error),
            HCCL_E_INTERNAL);
    }

    HcclRequestInfo* request = nullptr;
    TransData recvData(reinterpret_cast<u64>(nullptr), reinterpret_cast<u64>(recvParam.ptr),
        status.count, HCCL_DATA_TYPE_INT8);

    CHK_RET(Imrecv(recvData, *msg, request));
    CHK_RET(Test(*request, TestFlag, compState));
    CHK_PRT_RET(compState.error > 0, HCCL_ERROR("Test failed, compState.error[%d].", compState.error),
        HCCL_E_INTERNAL);
    while (TestFlag != HCCL_TEST_COMPLETED) {
        CHK_RET(IsProcessStop());
        if (!isESMode_) {
            CHK_RET(WaitCompletion(dataQpInfo_.sendCq, dataQpInfo_.sendChannel));
        }
        CHK_RET(Test(*request, TestFlag, compState));
        CHK_PRT_RET(compState.error > 0, HCCL_ERROR("Test failed, compState.error[%d].", compState.error),
            HCCL_E_INTERNAL);
    }
    return HCCL_SUCCESS;
}

// SendRecv语义实现 ：wait rcqe -> (RDMA read + RDMA send) -> wait scqe
HcclResult TransportRoce::WaitSendAsyncCompleteAndRecv(const SendRecvParam &sendParam, const SendRecvParam &recvParam)
{
    CHK_PTR_NULL(sendParam.ptr);
    CHK_PTR_NULL(recvParam.ptr);
    s32 improbeFlag = HCCL_IMPROBE_INCOMPLETED;
    s32 TestFlag = HCCL_TEST_INCOMPLETED;
    HcclStatus compState = {0};
    HcclStatus status = {0};
    HcclRequestInfo* sendRequest = sendParam.sendRequest;
    TransportEndPointInfo srcEp(0, machinePara_.localUserrank, 0);
    TransportEndPointInfo dstEp(0, machinePara_.remoteUserrank, 0);
    TransportEndPointParam epParam(srcEp, dstEp);
    HcclMessageInfo *msg = nullptr;

    CHK_RET(Improbe(epParam, improbeFlag, msg, status));
    CHK_PRT_RET(status.error > 0, HCCL_ERROR("Improbe failed, status.error[%d].", status.error),
        HCCL_E_INTERNAL);
    while (improbeFlag != HCCL_IMPROBE_COMPLETED) {
        CHK_RET(IsProcessStop());
        if (isESMode_) {
            CHK_RET(WaitCompletion(tagQpInfo_.recvCq, tagQpInfo_.recvChannel));
        };
        CHK_RET(Improbe(epParam, improbeFlag, msg, status));
        CHK_PRT_RET(status.error > 0, HCCL_ERROR("Improbe failed, status.error[%d].", status.error),
            HCCL_E_INTERNAL);
    }

    HcclRequestInfo* recvRequest = nullptr;
    TransData recvData(reinterpret_cast<u64>(nullptr), reinterpret_cast<u64>(recvParam.ptr),
        recvParam.len, HCCL_DATA_TYPE_INT8);
    CHK_RET(Imrecv(recvData, *msg, recvRequest));

    CHK_RET(Test(*sendRequest, TestFlag, compState));
    CHK_PRT_RET(compState.error > 0, HCCL_ERROR("Test failed, compState.error[%d].", compState.error),
        HCCL_E_INTERNAL);
    while (TestFlag != HCCL_TEST_COMPLETED) {
        CHK_RET(IsProcessStop());
        if (!isESMode_) {
            CHK_RET(WaitCompletion(dataQpInfo_.recvCq, dataQpInfo_.recvChannel));
        }
        CHK_RET(Test(*sendRequest, TestFlag, compState));
        CHK_PRT_RET(compState.error > 0, HCCL_ERROR("Test failed, compState.error[%d].", compState.error),
            HCCL_E_INTERNAL);
    }

    // 重置TestFlag，保证Improbe不影响Test
    TestFlag = HCCL_TEST_INCOMPLETED;
    compState = {0};
    CHK_RET(Test(*recvRequest, TestFlag, compState));
    CHK_PRT_RET(compState.error > 0, HCCL_ERROR("Test failed, compState.error[%d].", compState.error),
        HCCL_E_INTERNAL);
    while (TestFlag != HCCL_TEST_COMPLETED) {
        CHK_RET(IsProcessStop());
        if (!isESMode_) {
            CHK_RET(WaitCompletion(dataQpInfo_.sendCq, dataQpInfo_.sendChannel));
        }
        CHK_RET(Test(*recvRequest, TestFlag, compState));
        CHK_PRT_RET(compState.error > 0, HCCL_ERROR("Test failed, compState.error[%d].", compState.error),
            HCCL_E_INTERNAL);
    }

    return HCCL_SUCCESS;
}

HcclResult TransportRoce::TxEnv(const void *ptr, const u64 len, Stream &stream)
{
    HcclRequestInfo *request = nullptr;
    TransData sendData(reinterpret_cast<u64>(ptr), reinterpret_cast<u64>(ptr), len, HCCL_DATA_TYPE_INT8);
    TransportEndPointInfo srcEp(0, machinePara_.localUserrank, 0);
    TransportEndPointInfo dstEp(0, machinePara_.remoteUserrank, 0);
    TransportEndPointParam epParam(srcEp, dstEp);
    CHK_RET(GenerateSendRequest(sendData, epParam, request));

    u32 lkey = 0;
    CHK_RET(RegMr(reinterpret_cast<void *>(sendData.srcBuf),
        static_cast<u64>(sendData.count * SIZE_TABLE[sendData.dataType]), lkey, true));
    HCCL_DEBUG("TxEnv addr[%llu] count[%d] datatype[%s]", sendData.srcBuf, sendData.count,
        GetDataTypeEnumStr(sendData.dataType).c_str());

    HcclEnvelope envelope(request->transportRequest.protocol, request->transportRequest.transData,
        request->transportRequest.epParam, lkey, request->transportRequest.msn);

    HcclEnvelope *envPtr = reinterpret_cast<HcclEnvelope *>(sendEnvelopeMem_.ptr());
    CHK_RET(hrtMemSyncCopy(envPtr, sizeof(HcclEnvelope), &(envelope), sizeof(HcclEnvelope),
        HcclRtMemcpyKind::HCCL_RT_MEMCPY_KIND_HOST_TO_DEVICE));
    return SendEnvelope(*envPtr, stream.ptr());
}

HcclResult TransportRoce::RxEnv(Stream &stream)
{
    struct ibv_wc wc[HCCL_POLL_CQ_DEPTH];
    s32 tagCqNum = 0;
    while (tagCqNum == 0) {
        CHK_RET(IsProcessStop());
        CHK_RET(PollCq(tagQpInfo_, false, tagCqNum, wc));
        if (tagCqNum == 0) {
            SaluSleep(TWO_HUNDRED_MICROSECOND_OF_USLEEP);
        }
    }

    CHK_RET(ParseTagRqes(wc, tagCqNum));
    return HCCL_SUCCESS;
}