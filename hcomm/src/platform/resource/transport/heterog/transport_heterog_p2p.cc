/**
 * Copyright (c) 2025 Huawei Technologies Co., Ltd.
 * This program is free software, you can redistribute it and/or modify it under the terms and conditions of
 * CANN Open Software License Agreement Version 2.0 (the "License").
 * Please refer to the License for details. You may not use this file except in compliance with the License.
 * THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
 * INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
 * See LICENSE in the root of the software repository for the full text of the License.
 */

#include <securec.h>
#include <sys/socket.h>
#include <sys/types.h>
#include <arpa/inet.h>
#include <unistd.h>

#include "../heterog/transport_heterog_p2p_pub.h"
#include "mem_name_repository_pub.h"
#include "adapter_hal.h"
#include "dlhal_function.h"
#include "hccl_common.h"
#include "externalinput.h"

namespace hccl {
// link特性位图
constexpr u64 LINK_ATTRIBUTE_WRITE = 0x1;
constexpr u64 LINK_ATTRIBUTE_READ = 0x2;

static bool g_eschedEventInit = false;
TransportHeterogP2P::TransportHeterogP2P(DispatcherPub *dispatcher,
    const std::unique_ptr<NotifyPool> &notifyPool,
    MachinePara &machinePara,
    std::chrono::milliseconds timeout)
    : TransportBase(dispatcher, notifyPool, machinePara, timeout), remoteInputPtr_(nullptr),
      remoteOutputPtr_(nullptr), endType_(TRANSPORT_ENDPOINT_TYPE_NPU), connectState_(TRANSPORT_CONNECT_STATE_INIT),
      socketRecvSize_(0)
{
}

TransportHeterogP2P::~TransportHeterogP2P()
{
    DeInit();
}

HcclResult TransportHeterogP2P::DeInit()
{
    if (!isInit_) {
        return HCCL_SUCCESS;
    }

    bool devHasBeenSet = false;
    if (endType_ == TRANSPORT_ENDPOINT_TYPE_CPU) {
        void *ctx = nullptr;
        CHK_RET(hrtCtxGetCurrent(&ctx));
        if (ctx == nullptr) {
            CHK_RET(SetDeivceByPhyId());
            devHasBeenSet = true;
        }
    }
    HCCL_DEBUG("TransportHeterogP2P DeInit Enter!");
    MemNameRepository* memNameRepositoryInstance = MemNameRepository::GetInstance(machinePara_.deviceLogicId);
    for (auto &ipcName : openIpcNames_) {
        memNameRepositoryInstance->CloseIpcMem(reinterpret_cast<const u8 *>(ipcName.c_str()));
    }
    for (auto &ipcInfo : setIpcMemInfos_) {
        memNameRepositoryInstance->DestroyIpcMem(ipcInfo.ptr, ipcInfo.size);
    }

    if (g_eschedEventInit) {
        u32 remoteDevLogicId = machinePara_.remoteDeviceId;
        if (machinePara_.remoteDeviceId != HOST_DEVICE_ID) {
            CHK_RET(hrtGetDeviceIndexByPhyId(machinePara_.remoteDeviceId, remoteDevLogicId));
        }
        CHK_RET(hrtHalEschedDettachDevice(remoteDevLogicId));
        HCCL_INFO("TransportHeterogP2P detach device success");
        g_eschedEventInit = false;
    }

    if (remoteSendReadyNotify_ != nullptr) {
        remoteSendReadyNotify_->Close();
        remoteSendReadyNotify_ = nullptr;
    }
    if (remoteSendDoneNotify_ != nullptr) {
        remoteSendDoneNotify_->Close();
        remoteSendDoneNotify_ = nullptr;
    }

    if (socket_) {
        socket_->Close();
        socket_ = nullptr;
    }
    if (endType_ == TRANSPORT_ENDPOINT_TYPE_CPU && devHasBeenSet) {
        u32 remoteDevLogicId = 0;
        CHK_RET(hrtGetDeviceIndexByPhyId(machinePara_.remoteDeviceId, remoteDevLogicId));
        hrtResetDevice(remoteDevLogicId);
    }
    isInit_ = false;
    HCCL_DEBUG("TransportHeterogP2P DeInit Success!");
    return HCCL_SUCCESS;
}

void TransportHeterogP2P::Break()
{
    if (sendReadyNotify_ != nullptr) {
        sendReadyNotify_->Break();
    }

    if (sendDoneNotify_ != nullptr) {
        sendDoneNotify_->Break();
    }
}

HcclResult TransportHeterogP2P::Init(void)
{
    HcclResult ret = HCCL_SUCCESS;
    u32 status;
    auto startTime = std::chrono::steady_clock::now();
    auto timeout = std::chrono::seconds(GetExternalInputHcclLinkTimeOut());
    do {
        if ((std::chrono::steady_clock::now() - startTime) >= timeout) {
            HCCL_ERROR("[TransportHeterogP2P]transport connect timeout[%lld s], may be insufficient.", timeout);
            return HCCL_E_TIMEOUT;
        }
        CHK_RET(ConnectQuerry(status));
        if (status == HETEROG_P2P_SUCCESS) {
            isInit_ = true;
            ret = HCCL_SUCCESS;
        } else if (status == HETEROG_P2P_FAILED) {
            HCCL_ERROR("ConnectQuerry failed");
            ret = HCCL_E_INTERNAL;
        } else {
            SaluSleep(ONE_MILLISECOND_OF_USLEEP);
        }
    } while (status != HETEROG_P2P_SUCCESS);

    HCCL_USER_CRITICAL_LOG("create hccl transport:communicator[%s], local rank[%u], remote rank[%u], "\
        "transporttype[%s]", machinePara_.collectiveId.c_str(), machinePara_.localUserrank, 
        machinePara_.remoteUserrank, GetLinkTypeEnumStr(GetLinkType()).c_str());
        
    return ret;
}

HcclResult TransportHeterogP2P::ConnectAsync(u32& status)
{
    switch (connectState_) {
        case TRANSPORT_CONNECT_STATE_INIT:
            CHK_RET(ConnectInit());
            break;
        case TRANSPORT_CONNECT_STATE_SOCKET_CONNECT:
            CHK_RET(GetSocket());
            break;
        case TRANSPORT_CONNECT_STATE_EXCHANGE_PID:
            CHK_RET(RecvPid());
            break;
        case TRANSPORT_CONNECT_STATE_EXCHANGE_TRANSPORT_INFO:
            CHK_RET(RecvIpcInfo());
            break;
        default:
            break;
    }

    status = (connectState_ == TRANSPORT_CONNECT_STATE_DONE) ? 0 : 1;
    HCCL_DEBUG("ConnectAsync %u", status);
    return HCCL_SUCCESS;
}

HcclResult TransportHeterogP2P::ConnectQuerry(u32& status)
{
    if (connectState_ != TRANSPORT_CONNECT_STATE_DONE) {
        CHK_RET(ConnectAsync(status));
    } else {
        status = HETEROG_P2P_SUCCESS;
    }
    HCCL_DEBUG("ConnectQuerry %u", connectState_);
    return HCCL_SUCCESS;
}

HcclResult TransportHeterogP2P::SetDeivceByPhyId()
{
    u32 remoteDevLogicId = 0;
    CHK_RET(hrtGetDeviceIndexByPhyId(machinePara_.remoteDeviceId, remoteDevLogicId));
    CHK_RET(hrtSetDevice(remoteDevLogicId));
    return HCCL_SUCCESS;
}

HcclResult TransportHeterogP2P::ConnectInit()
{
    HCCL_INFO("machineType=[%d], serverId=[%s], localDeviceId=[%d] remoteDeviceId=[%d], "
        "localRank=[%u], localUserRank=[%u], remoteRank=[%u], remoteUserRank=[%u], "
        "deviceType=[%d], input_ptr=[%p], output_ptr=[%p], linkAttribute=[0x%x], linkMode=[%d]"
        "remoteAddr=[%s], localAddr=[%s], remotePort=[%u], localport=[%u], custom exchange data size [%llu].",
        machinePara_.machineType, machinePara_.serverId.c_str(), machinePara_.localDeviceId,
        machinePara_.remoteDeviceId, machinePara_.localUserrank, machinePara_.localWorldRank,
        machinePara_.remoteUserrank, machinePara_.remoteWorldRank, machinePara_.deviceType,
        machinePara_.inputMem.ptr(), machinePara_.outputMem.ptr(), machinePara_.linkAttribute, machinePara_.linkMode,
        machinePara_.remoteIpAddr.GetReadableAddress(), machinePara_.localIpAddr.GetReadableAddress(),
        machinePara_.remoteSocketPort, machinePara_.localSocketPort, machinePara_.exchangeInfo.size());

    /* make input memory shared interprocess and assigned a name */
    CHK_SMART_PTR_NULL(machinePara_.inputMem);
    CHK_SMART_PTR_NULL(machinePara_.outputMem);
    CHK_RET(CheckLinkMode());
    CHK_RET(CheckExchangeData());

    transportAttr_.linkType = hccl::LinkType::LINK_PCIE;
    endType_ = (machinePara_.localDeviceId == -1) ? TRANSPORT_ENDPOINT_TYPE_CPU : TRANSPORT_ENDPOINT_TYPE_NPU;
    machinePara_.linkAttribute = (endType_ == TRANSPORT_ENDPOINT_TYPE_CPU) ? 0x03 : 0x00;
    if (endType_ == TRANSPORT_ENDPOINT_TYPE_CPU) {
        CHK_RET(SetDeivceByPhyId());
        HCCL_INFO("TransportHeterogP2P set device success.");
        if (!g_eschedEventInit) {
            CHK_RET(DlHalFunction::GetInstance().DlHalFunctionInit());
            CHK_RET(hrtHalEschedAttachDevice(0));
            g_eschedEventInit = true;
        }
    }

    connectState_ = TRANSPORT_CONNECT_STATE_SOCKET_CONNECT;
    CHK_RET(ConnectSocket());

    return HCCL_SUCCESS;
}

HcclResult TransportHeterogP2P::ConnectSocket()
{
    HCCL_INFO("TransportHeterogP2P start socket connect.");
    u32 role = (machinePara_.machineType == MachineType::MACHINE_SERVER_TYPE) ? SERVER_ROLE_SOCKET : CLIENT_ROLE_SOCKET;
    u32 socketServerPort = (machinePara_.machineType == MachineType::MACHINE_SERVER_TYPE) ?
        machinePara_.localSocketPort : machinePara_.remoteSocketPort;

    std::string linkTag = machinePara_.tag + "_";
    if (machinePara_.remoteUserrank < machinePara_.localUserrank) {
        linkTag += std::to_string(machinePara_.remoteUserrank);
        linkTag += "_";
        linkTag += std::to_string(machinePara_.localUserrank);
    } else {
        linkTag += std::to_string(machinePara_.localUserrank);
        linkTag += "_";
        linkTag += std::to_string(machinePara_.remoteUserrank);
    }

    HcclIpAddress loopBackIp("127.0.0.1");
    socket_.reset(new (std::nothrow) Socket(linkTag, role, SocketType::SOCKET_NIC, NICDeployment::NIC_DEPLOYMENT_HOST,
        loopBackIp, machinePara_.localDeviceId, loopBackIp, machinePara_.remoteDeviceId,
        DeviceIdType::DEVICE_ID_TYPE_PHY_ID, socketServerPort));
    CHK_SMART_PTR_NULL(socket_);

    CHK_RET(socket_->PrepareConnect());
    u32 status;
    CHK_RET(socket_->ConnectAsync(status));

    if (status == HETEROG_P2P_SUCCESS) {
        HCCL_INFO("TransportHeterogP2P socket connect success.");
        connectState_ = TRANSPORT_CONNECT_STATE_EXCHANGE_PID;
        isInit_ = true;
        CHK_RET(ExchangePid());
    }
    return HCCL_SUCCESS;
}

HcclResult TransportHeterogP2P::GetSocket()
{
    u32 status;
    CHK_RET(socket_->ConnectQuerry(status));
    if (status == HETEROG_P2P_SUCCESS) {
        HCCL_INFO("TransportHeterogP2P socket connect success.");
        connectState_ = TRANSPORT_CONNECT_STATE_EXCHANGE_PID;
        isInit_ = true;
        CHK_RET(ExchangePid());
    }
    return HCCL_SUCCESS;
}

HcclResult TransportHeterogP2P::ExchangePid()
{
    s32 selfPid = 0;
    CHK_RET(SalGetBareTgid(&selfPid)); // 当前进程id
    CHK_RET(socket_->Send(&selfPid, sizeof(selfPid)));
    socketRecvSize_ = 0;
    CHK_RET(RecvPid());
    return HCCL_SUCCESS;
}

HcclResult TransportHeterogP2P::RecvPid()
{
    u64 recvSize = 0;
    CHK_RET(socket_->IRecv((reinterpret_cast<char *>(&recvPid_) + socketRecvSize_),
        (sizeof(recvPid_) - socketRecvSize_), recvSize));
    socketRecvSize_ += recvSize;
    if (socketRecvSize_ == sizeof(recvPid_)) {
        socketRecvSize_ = 0;
        connectState_ = TRANSPORT_CONNECT_STATE_EXCHANGE_TRANSPORT_INFO;
        CHK_RET(ExchangeTransportInfo());
    } else if (socketRecvSize_ > sizeof(recvPid_)) {
        return HCCL_E_INTERNAL;
    }
    return HCCL_SUCCESS;
}

HcclResult TransportHeterogP2P::ExchangeTransportInfo()
{
    CHK_RET(SendIpcInfo());
    CHK_RET(RecvIpcInfo());
    return HCCL_SUCCESS;
}

HcclResult TransportHeterogP2P::SendIpcInfo()
{
    ExchangeMsg sendMsg;
    s32 sRet = memset_s(&sendMsg, sizeof(sendMsg), 0, sizeof(sendMsg));
    CHK_PRT_RET(sRet != EOK, HCCL_ERROR("[Clear][CheckInfo]memory set fail. return[%d].",\
        sRet), HCCL_E_MEMORY);
    CHK_RET(CreateIpcSignal(sendReadyNotify_, sendMsg.sendReadyNotify));
    CHK_RET(CreateIpcSignal(sendDoneNotify_, sendMsg.sendDoneNotify));
    if (endType_ == TRANSPORT_ENDPOINT_TYPE_NPU) {
        CHK_RET(SetIpcMem(machinePara_.inputMem, sendMsg.ipcMem[0]));
        setIpcMemInfos_.push_back(sendMsg.ipcMem[0]);
        HCCL_INFO("set ipc mem input mem[%p] size[%llu] setIpcMemInfos size[%u]",
            machinePara_.inputMem.ptr(), machinePara_.inputMem.size(), setIpcMemInfos_.size());
        CHK_RET(SetIpcMem(machinePara_.outputMem, sendMsg.ipcMem[1]));
        setIpcMemInfos_.push_back(sendMsg.ipcMem[1]);
        HCCL_INFO("set ipc mem output mem[%p] size[%llu] setIpcMemInfos size[%u]",
            machinePara_.outputMem.ptr(), machinePara_.outputMem.size(), setIpcMemInfos_.size());
    }
    u64 dataLength = machinePara_.exchangeInfo.size();
    exchangeDataTotalSize_ += sizeof(sendMsg);
    exchangeDataTotalSize_ += dataLength;
    exchangeDataForSend_.resize(exchangeDataTotalSize_);
    exchangeDataForRecv_.resize(exchangeDataTotalSize_);
    u8* exchangeDataPtr = exchangeDataForSend_.data();
    CHK_SAFETY_FUNC_RET(memcpy_s(exchangeDataPtr, sizeof(sendMsg),
        &sendMsg, sizeof(sendMsg)));
    exchangeDataPtr += sizeof(sendMsg);

    if (dataLength != 0) {
        CHK_SAFETY_FUNC_RET(memcpy_s(exchangeDataPtr, dataLength,
            &machinePara_.exchangeInfo[0], dataLength));
    }

    CHK_RET(socket_->Send(exchangeDataForSend_.data(), exchangeDataTotalSize_));
    return HCCL_SUCCESS;
}

HcclResult TransportHeterogP2P::RecvIpcInfo()
{
    u64 recvSize = 0;
    CHK_RET(socket_->IRecv((exchangeDataForRecv_.data() + socketRecvSize_),
        (exchangeDataTotalSize_ - socketRecvSize_), recvSize));
    socketRecvSize_ += recvSize;
    if (socketRecvSize_ == exchangeDataTotalSize_) {
        socketRecvSize_ = 0;
        u8* exchangeDataPtr = exchangeDataForRecv_.data();
        CHK_SAFETY_FUNC_RET(memcpy_s(&remoteMsg_, sizeof(remoteMsg_),
            exchangeDataPtr, sizeof(remoteMsg_)));
        exchangeDataPtr += sizeof(remoteMsg_);

        std::vector<u8> sendReadyNotify(remoteMsg_.sendReadyNotify, remoteMsg_.sendReadyNotify + NOTIFY_INFO_LENGTH);
        CHK_RET(OpenRemoteNotify(sendReadyNotify, remoteSendReadyNotify_));

        std::vector<u8> sendDoneNotify(remoteMsg_.sendDoneNotify, remoteMsg_.sendDoneNotify + NOTIFY_INFO_LENGTH);
        CHK_RET(OpenRemoteNotify(sendDoneNotify, remoteSendDoneNotify_));

        if (endType_ == TRANSPORT_ENDPOINT_TYPE_CPU) {
            CHK_RET(WaitPeerMemConfig(&remoteInputPtr_, remoteMsg_.ipcMem[0].name.ipcName,
                remoteMsg_.ipcMem[0].size, remoteMsg_.ipcMem[0].offset));
            remoteInputMemSize_ = remoteMsg_.ipcMem[0].size;
            CHK_RET(WaitPeerMemConfig(&remoteOutputPtr_, remoteMsg_.ipcMem[1].name.ipcName,
                remoteMsg_.ipcMem[1].size, remoteMsg_.ipcMem[1].offset));
            remoteOutputMemSize_ = remoteMsg_.ipcMem[1].size;
        }

        u64 dataLength = machinePara_.exchangeInfo.size();
        if (dataLength != 0) {
            exchangeMsg_.resize(dataLength);
            CHK_SAFETY_FUNC_RET(memcpy_s(&exchangeMsg_[0], dataLength, exchangeDataPtr, dataLength));
        }

        connectState_ = TRANSPORT_CONNECT_STATE_DONE;
        CHK_RET(socket_->Close());
        socket_ = nullptr;
        HCCL_INFO("TransportHeterogP2P connect complete.");
    } else if (socketRecvSize_ > exchangeDataTotalSize_) {
        return HCCL_E_INTERNAL;
    }
    return HCCL_SUCCESS;
}

HcclResult TransportHeterogP2P::GetRemoteMem(UserMemType memType, void **remotePtr, u64 &remoteMemSize)
{
    switch (memType) {
        case UserMemType::INPUT_MEM: {
            *remotePtr = remoteInputPtr_;
            remoteMemSize = remoteInputMemSize_;
            break;
        }

        case UserMemType::OUTPUT_MEM: {
            *remotePtr = remoteOutputPtr_;
            remoteMemSize = remoteOutputMemSize_;
            break;
        }

        default: {
            HCCL_ERROR("[Get][RemoteMem]not support dst_mem_type=%d", memType);
            return HCCL_E_NOT_SUPPORT;
        }
    }

    return HCCL_SUCCESS;
}

HcclResult TransportHeterogP2P::SetIpcMem(DeviceMem &memory, HcclIpcMemInfo& ipcMemInfo)
{
    HcclResult ret;
    /* make memory shared interprocess and assigned a name */
    ret = MemNameRepository::GetInstance(machinePara_.deviceLogicId)->SetIpcMem(
        memory.ptr(), memory.size(), ipcMemInfo.name.ipcName, HCCL_IPC_MEM_NAME_LEN, ipcMemInfo.offset, recvPid_);
    CHK_PRT_RET(ret != HCCL_SUCCESS,
        HCCL_ERROR("[Send][IpcMemMesg]errNo[0x%016llx], In send ipc mesg, get para mem name failed. "
        "mem addr[%p] local rank[%u]", HCCL_ERROR_CODE(ret), memory.ptr(), machinePara_.localUserrank), ret);

    ipcMemInfo.size = memory.size();
    ipcMemInfo.ptr = memory.ptr();

    HCCL_DEBUG("localUserrank=%u, ptr=%p, remoteUserrank=%u, offset=%llu",
        machinePara_.localUserrank, memory.ptr(), machinePara_.remoteUserrank, ipcMemInfo.offset);
    return HCCL_SUCCESS;
}
HcclResult TransportHeterogP2P::CreateIpcSignal(std::shared_ptr<LocalIpcNotify> &localNotify, u8 *notifyInfo)
{
    RemoteRankInfo info(machinePara_.remoteDeviceId, machinePara_.remoteWorldRank, recvPid_);
    CHK_SMART_PTR_NULL(notifyPool_);
    CHK_RET(notifyPool_->Alloc(machinePara_.tag, info, localNotify));

    std::vector<u8> data(NOTIFY_INFO_LENGTH, 0);
    CHK_RET(localNotify->Serialize(data));
    CHK_SAFETY_FUNC_RET(memcpy_s((u8 *)notifyInfo, NOTIFY_INFO_LENGTH, &data[0], data.size()));

    return HCCL_SUCCESS;
}

HcclResult TransportHeterogP2P::WaitPeerMemConfig(void **memPtr, const u8 *memName, uint64_t size, u64 offset)
{
    CHK_PTR_NULL(memPtr);
    CHK_PTR_NULL(memName);

    bool firstOpened = false;
    // 支持进程间、进程内都可以通过name获取对端内存
    HcclResult ret = MemNameRepository::GetInstance(machinePara_.deviceLogicId)
                         ->OpenIpcMem(memPtr, size, memName, HCCL_IPC_MEM_NAME_LEN, offset, firstOpened);

    CHK_PRT_RET(ret != HCCL_SUCCESS,
        HCCL_ERROR("[Wait][WaitPeerMemConfig]errNo[0x%016llx]In link pcie, open mem failed. offset[%llu], size[%llu Byte]",
            HCCL_ERROR_CODE(ret), offset, size), ret);

    openIpcNames_.push_back(reinterpret_cast<const char *>(memName));
    return HCCL_SUCCESS;
}

HcclResult TransportHeterogP2P::TxDataSignal(Stream &stream)
{
    CHK_PRT_RET((connectState_ != TRANSPORT_CONNECT_STATE_DONE), HCCL_ERROR("transport is not ready"), HCCL_E_PARA);
    HcclResult ret = remoteSendReadyNotify_->Post(stream, dispatcher_);
    CHK_PRT_RET(ret != HCCL_SUCCESS,
        HCCL_ERROR("[TransportHeterogP2P][TxDataSignal]errNo[0x%016llx]In tx data signal, signal record failed.",
        HCCL_ERROR_CODE(ret)), ret);
    return HCCL_SUCCESS;
}

HcclResult TransportHeterogP2P::RxDataSignal(Stream &stream)
{
    CHK_PRT_RET((connectState_ != TRANSPORT_CONNECT_STATE_DONE), HCCL_ERROR("transport is not ready"), HCCL_E_PARA);
    HcclResult ret = sendReadyNotify_->Wait(stream, dispatcher_, INVALID_VALUE_STAGE,
        static_cast<u32>(dispatcher_->GetExecTimeOut()));
    CHK_PRT_RET(ret != HCCL_SUCCESS,
        HCCL_ERROR("[TransportHeterogP2P][RxDataSignal]errNo[0x%016llx]In rx data signal, signal wait failed.",
        HCCL_ERROR_CODE(ret)), ret);
    return HCCL_SUCCESS;
}

HcclResult TransportHeterogP2P::TxAck(Stream &stream)
{
    CHK_PRT_RET((connectState_ != TRANSPORT_CONNECT_STATE_DONE), HCCL_ERROR("transport is not ready"), HCCL_E_PARA);
    HcclResult ret = remoteSendDoneNotify_->Post(stream, dispatcher_);
    CHK_PRT_RET(ret != HCCL_SUCCESS,
        HCCL_ERROR("[TransportHeterogP2P][TxAck]errNo[0x%016llx]In tx ack signal, signal record failed.",
        HCCL_ERROR_CODE(ret)), ret);
    return HCCL_SUCCESS;
}

HcclResult TransportHeterogP2P::RxAck(Stream &stream)
{
    CHK_PRT_RET((connectState_ != TRANSPORT_CONNECT_STATE_DONE), HCCL_ERROR("transport is not ready"), HCCL_E_PARA);
    HcclResult ret = sendDoneNotify_->Wait(stream, dispatcher_, INVALID_VALUE_STAGE,
        static_cast<u32>(dispatcher_->GetExecTimeOut()));
    CHK_PRT_RET(ret != HCCL_SUCCESS,
        HCCL_ERROR("[TransportHeterogP2P][RxAck]errNo[0x%016llx]In rx ack signal, signal wait failed.",
        HCCL_ERROR_CODE(ret)), ret);
    return HCCL_SUCCESS;
}

HcclResult TransportHeterogP2P::TxAsync(UserMemType dstMemType, u64 dstOffset, const void *src, u64 len, Stream &stream)
{
    CHK_PRT_RET((connectState_ != TRANSPORT_CONNECT_STATE_DONE), HCCL_ERROR("transport is not ready"), HCCL_E_PARA);
    /* 源端发起数据传输 */
    if ((machinePara_.linkAttribute & LINK_ATTRIBUTE_WRITE) && len > 0) {  // 支持源端发起
        CHK_PTR_NULL(src);
        void *dstMemPtr = nullptr;
        u64 dstMemSize = 0;
        CHK_RET(GetRemoteMem(dstMemType, &dstMemPtr, dstMemSize));
        void *dstAddr = static_cast<s8 *>(dstMemPtr) + dstOffset;

        HCCL_INFO("TxAsync srcAddr=[%p], dstOffset=[%llu],dstAddr=[%p],dstSize=[%llu] len=[%llu]" \
            " remoteInput[%p] remoteOutput[%p]",
            src, dstOffset, dstMemPtr, dstMemSize - dstOffset, len, remoteInputPtr_, remoteOutputPtr_);
        CHK_RET(hrtDrvMemCpy(dstAddr, dstMemSize - dstOffset, src, len));
    }

    /* 发起send_ready_signal事件 */
    HcclResult ret = remoteSendReadyNotify_->Post(stream, dispatcher_);
    CHK_PRT_RET(ret != HCCL_SUCCESS,
        HCCL_ERROR("[TransportHeterogP2P][TxAsync]errNo[0x%016llx]In tx async, signal record failed.",
        HCCL_ERROR_CODE(ret)), ret);
    return HCCL_SUCCESS;
}

HcclResult TransportHeterogP2P::TxAsync(std::vector<TxMemoryInfo>& txMems, Stream &stream)
{
    CHK_PRT_RET((connectState_ != TRANSPORT_CONNECT_STATE_DONE), HCCL_ERROR("transport is not ready"), HCCL_E_PARA);

    /* 源端发起数据传输 */
    if (machinePara_.linkAttribute & LINK_ATTRIBUTE_WRITE) {  // 支持源端端发起
        for (auto& mem : txMems) {
            if (mem.len == 0) {
                continue;
            }
            CHK_PTR_NULL(mem.src);
            void *dstMemPtr = nullptr;
            u64 dstMemSize = 0;
            CHK_RET(GetRemoteMem(mem.dstMemType, &dstMemPtr, dstMemSize));

            DeviceMem dstDevMem = DeviceMem::create(static_cast<s8 *>(dstMemPtr) + mem.dstOffset,
                dstMemSize - mem.dstOffset);
            DeviceMem srcDevMem = DeviceMem::create(const_cast<void *>(mem.src), mem.len);
            /* 增加hccl 数据传输时数据地址和size记录 */
            HCCL_DEBUG("HCCL_KEY_INFO: srcAddr=[%p],srcSize=[%llu],dstAddr=[%p],dstSize=[%llu]", srcDevMem.ptr(),
                srcDevMem.size(), dstDevMem.ptr(), dstDevMem.size());
            CHK_RET(hrtDrvMemCpy(dstDevMem.ptr(), dstDevMem.size(), srcDevMem.ptr(), srcDevMem.size()));
        }
    }

    /* 发起send_ready_signal事件 */
    HcclResult ret = remoteSendReadyNotify_->Post(stream, dispatcher_);
    CHK_PRT_RET(ret != HCCL_SUCCESS,
        HCCL_ERROR("[TransportHeterogP2P][TxAsync]errNo[0x%016llx]In tx async, signal record failed.",
        HCCL_ERROR_CODE(ret)), ret);
    return HCCL_SUCCESS;
}

HcclResult TransportHeterogP2P::RxAsync(UserMemType srcMemType, u64 srcOffset, void *dst, u64 len, Stream &stream)
{
    CHK_PRT_RET((connectState_ != TRANSPORT_CONNECT_STATE_DONE), HCCL_ERROR("transport is not ready"), HCCL_E_PARA);
    /* 等待send_ready_signal事件 */
    HcclResult ret = sendReadyNotify_->Wait(stream, dispatcher_, INVALID_VALUE_STAGE, GetIncreSaveExecTimeOut());
    CHK_PRT_RET(ret == HCCL_E_AGAIN, HCCL_WARNING("[TransportHeterogP2P][RxAsync]group has been destroyed."), ret);
    CHK_PRT_RET(ret != HCCL_SUCCESS,
        HCCL_ERROR("[TransportHeterogP2P][RxAsync]errNo[0x%016llx]In rx async, signal wait failed.",
        HCCL_ERROR_CODE(ret)), ret);

    /* 目的端发起数据传输 */
    if ((machinePara_.linkAttribute & LINK_ATTRIBUTE_READ) && len > 0) {  // 支持目的端发起
        CHK_PTR_NULL(dst);
        void *srcMemPtr = nullptr;
        u64 srcMemSize = 0;
        CHK_RET(GetRemoteMem(srcMemType, &srcMemPtr, srcMemSize));
        void *srcAddr = static_cast<s8 *>(srcMemPtr) + srcOffset;
        CHK_RET(hrtDrvMemCpy(dst, len, srcAddr, len));
    }
    return HCCL_SUCCESS;
}

HcclResult TransportHeterogP2P::RxAsync(std::vector<RxMemoryInfo>& rxMems, Stream &stream)
{
    CHK_PRT_RET((connectState_ != TRANSPORT_CONNECT_STATE_DONE), HCCL_ERROR("transport is not ready"), HCCL_E_PARA);

    /* 等待send_ready_signal事件 */
    HcclResult ret = sendReadyNotify_->Wait(stream, dispatcher_, INVALID_VALUE_STAGE,
        static_cast<u32>(dispatcher_->GetExecTimeOut()));
    CHK_PRT_RET(ret != HCCL_SUCCESS,
        HCCL_ERROR("[TransportHeterogP2P][RxAsync]errNo[0x%016llx]In rx async, signal wait failed.",
        HCCL_ERROR_CODE(ret)), ret);

    /* 目的端发起数据传输 */
    if ((machinePara_.linkAttribute & LINK_ATTRIBUTE_READ) != 0) {  // 支持目的端发起
        for (auto& mem : rxMems) {
            if (mem.len == 0) {
                continue;
            }
            CHK_PTR_NULL(mem.dst);
            void *srcMemPtr = nullptr;
            u64 srcMemSize = 0;
            CHK_RET(GetRemoteMem(mem.srcMemType, &srcMemPtr, srcMemSize));

            DeviceMem srcDevMem = DeviceMem::create(static_cast<s8 *>(srcMemPtr) + mem.srcOffset, mem.len);
            DeviceMem dstDevMem = DeviceMem::create(static_cast<s8 *>(mem.dst), mem.len);
            CHK_RET(hrtDrvMemCpy(dstDevMem.ptr(), dstDevMem.size(), srcDevMem.ptr(), srcDevMem.size()));
        }
    }
    return HCCL_SUCCESS;
}

HcclResult TransportHeterogP2P::TxData(UserMemType dstMemType, u64 dstOffset, const void *src, u64 len, Stream &stream)
{
    CHK_PRT_RET((connectState_ != TRANSPORT_CONNECT_STATE_DONE), HCCL_ERROR("transport is not ready"), HCCL_E_PARA);
    /* 源端发起数据传输 */
    if ((machinePara_.linkAttribute & LINK_ATTRIBUTE_WRITE) && len > 0) {  // 支持源端发起
        CHK_PTR_NULL(src);
        void *dstMemPtr = nullptr;
        u64 dstMemSize = 0;
        CHK_RET(GetRemoteMem(dstMemType, &dstMemPtr, dstMemSize));
        void *dstAddr = static_cast<s8 *>(dstMemPtr) + dstOffset;

        HCCL_INFO("TxAsync srcAddr=[%p], dstOffset=[%llu],dstAddr=[%p],dstSize=[%llu] len=[%llu]" \
            " remoteInput[%p] remoteOutput[%p]",
            src, dstOffset, dstMemPtr, dstMemSize - dstOffset, len, remoteInputPtr_, remoteOutputPtr_);
        CHK_RET(hrtDrvMemCpy(dstAddr, dstMemSize - dstOffset, src, len));
    }
    return HCCL_SUCCESS;
}

HcclResult TransportHeterogP2P::RxData(UserMemType srcMemType, u64 srcOffset, void *dst, u64 len, Stream &stream)
{
    CHK_PRT_RET((connectState_ != TRANSPORT_CONNECT_STATE_DONE), HCCL_ERROR("transport is not ready"), HCCL_E_PARA);
    /* 目的端发起数据传输 */
    if ((machinePara_.linkAttribute & LINK_ATTRIBUTE_READ) && len > 0) {  // 支持目的端发起
        CHK_PTR_NULL(dst);
        void *srcMemPtr = nullptr;
        u64 srcMemSize = 0;
        CHK_RET(GetRemoteMem(srcMemType, &srcMemPtr, srcMemSize));
        void *srcAddr = static_cast<s8 *>(srcMemPtr) + srcOffset;
        CHK_RET(hrtDrvMemCpy(dst, len, srcAddr, len));
    }
    return HCCL_SUCCESS;
}

HcclResult TransportHeterogP2P::TxPrepare(Stream &stream)
{
    CHK_RET(TxAck(stream));
    return HCCL_SUCCESS;
}

HcclResult TransportHeterogP2P::RxPrepare(Stream &stream)
{
    CHK_RET(RxAck(stream));
    return HCCL_SUCCESS;
}

HcclResult TransportHeterogP2P::TxDone(Stream &stream)
{
    HcclResult ret = RxDataSignal(stream);
    CHK_PRT_RET(ret != HCCL_SUCCESS, HCCL_ERROR("[TransportP2p][TxDone]RxDataSignal failed"), ret);

    ret = RxWaitDone(stream);
    CHK_PRT_RET(ret != HCCL_SUCCESS, HCCL_ERROR("[TransportP2p][TxDone]RxWaitDone failed"), ret);
    ret = TxWaitDone(stream);
    CHK_PRT_RET(ret != HCCL_SUCCESS, HCCL_ERROR("[TransportP2p][TxDone]TxWaitDone failed"), ret);
    return HCCL_SUCCESS;
}

HcclResult TransportHeterogP2P::RxDone(Stream &stream)
{
    HcclResult ret = TxDataSignal(stream);
    CHK_PRT_RET(ret != HCCL_SUCCESS, HCCL_ERROR("[TransportP2p][RxDone]TxDataSignal failed"), ret);
    return HCCL_SUCCESS;
}
}  // namespace hccl
