/**
 * Copyright (c) 2025 Huawei Technologies Co., Ltd.
 * This program is free software, you can redistribute it and/or modify it under the terms and conditions of
 * CANN Open Software License Agreement Version 2.0 (the "License").
 * Please refer to the License for details. You may not use this file except in compliance with the License.
 * THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
 * INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
 * See LICENSE in the root of the software repository for the full text of the License.
 */

#include "transport_shm_event.h"
#include <arpa/inet.h>
#include <securec.h>
#include <fcntl.h>

#include "externalinput_pub.h"
#include "network/hccp.h"
#include "network/hccp_common.h"
#include "network_manager_pub.h"
#include "dlhal_function.h"

using namespace hccl;

constexpr s32 REG_VALID = 1;
constexpr s32 LINK_NUM = 1;
constexpr u64 NAME_LEN = 65;
constexpr u32 MSG_BUFF_SIZE = 2048;
constexpr u32 CALC_SHMENVELOPE_SIZE = 2;
bool TransportShmEvent::eschedEventInit_ = false;

using NotifyMsg = struct NotifyMsgDef {
    u8 remoteIsendDoneNotify[NOTIFY_INFO_LENGTH];
    u8 remoteImrecvDoneNotify[NOTIFY_INFO_LENGTH];
};

TransportShmEvent::TransportShmEvent(const HcclDispatcher dispatcher,
    const std::unique_ptr<NotifyPool> &notifyPool,
    MachinePara &machinePara, std::chrono::milliseconds timeout,
    HcclIpAddress &selfIp, HcclIpAddress &peerIp, u32 peerPort, u32 selfPort, s32 deviceLogicId, u32 role,
    const TransportResourceInfo &transportResourceInfo, HcclRtContext rtCtx)
    : TransportBase(reinterpret_cast<DispatcherPub*>(const_cast<HcclDispatcher>(dispatcher)),
        notifyPool, machinePara, timeout),
    TransportHeterog(machinePara.tag, selfIp, peerIp, peerPort, selfPort, transportResourceInfo),
      selfIp_(selfIp), peerIp_(peerIp), peerPort_(peerPort), selfPort_(selfPort), tag_(machinePara.tag),
      deviceLogicId_(deviceLogicId), role_(role), isInited_(false), rtCtx_(rtCtx)
{
}

TransportShmEvent::~TransportShmEvent()
{
    if (deviceLogicId_ != HOST_DEVICE_ID) {
        MemNameRepository::GetInstance(deviceLogicId_)->DestroyIpcMem(inputShmMem_.ptr(), inputShmMem_.size());
        MemNameRepository::GetInstance(deviceLogicId_)->DestroyIpcMem(outputShmMem_.ptr(), outputShmMem_.size());
        MemNameRepository::GetInstance(deviceLogicId_)->DestroyIpcMem(envelopeShmQue_.ptr(), envelopeShmQue_.size());
    } else {
        MemNameRepository::GetInstance(deviceLogicId_)->CloseIpcMem(remoteInputMemName_.ipcName);
        MemNameRepository::GetInstance(deviceLogicId_)->CloseIpcMem(remoteOutputMemName_.ipcName);
        MemNameRepository::GetInstance(deviceLogicId_)->CloseIpcMem(remoteEnvelopeItemMemName_.ipcName);
    }

    if (isendDoneNotify_ != nullptr) {
        isendDoneNotify_->Close();
        isendDoneNotify_ = nullptr;
    }

    if (imrecvDoneNotify_ != nullptr) {
        imrecvDoneNotify_->Close();
        imrecvDoneNotify_ = nullptr;
    }

    if (remoteIsendDoneNotify_ != nullptr) {
        remoteIsendDoneNotify_->Destroy();
        remoteIsendDoneNotify_ = nullptr;
    }

    if (remoteImrecvDoneNotify_ != nullptr) {
        remoteImrecvDoneNotify_->Destroy();
        remoteImrecvDoneNotify_ = nullptr;
    }

    static_cast<void>(Deinit());
}

HcclResult TransportShmEvent::InitMem()
{
    if (deviceLogicId_ != HOST_DEVICE_ID) {
        if (inputShmMem_.ptr() == nullptr) {
            inputShmMem_ = machinePara_.inputMem;
            CHK_PTR_NULL(inputShmMem_.ptr());
        }
        if (outputShmMem_.ptr() == nullptr) {
            outputShmMem_ = machinePara_.outputMem;
            CHK_PTR_NULL(outputShmMem_.ptr());
        }
        if (envelopeShmQue_.ptr() == nullptr) {
            CHK_RET(DeviceMem::alloc(envelopeShmQue_, CALC_SHMENVELOPE_SIZE * sizeof(ShmEnvelopeQue)));
            std::unique_ptr<ShmEnvelopeQue> tempQue(new (std::nothrow) ShmEnvelopeQue());
            CHK_SMART_PTR_NULL(tempQue);
            CHK_RET(hrtDrvMemCpy(envelopeShmQue_.ptr(), envelopeShmQue_.size(), tempQue.get(), sizeof(ShmEnvelopeQue)));
            CHK_RET(hrtDrvMemCpy(static_cast<u8 *>(envelopeShmQue_.ptr()) + sizeof(ShmEnvelopeQue),
                envelopeShmQue_.size() - sizeof(ShmEnvelopeQue), tempQue.get(), sizeof(ShmEnvelopeQue)));
            localEnvelopeShmQue_ = static_cast<u8 *>(envelopeShmQue_.ptr()) + sizeof(ShmEnvelopeQue);
        }
    }
    CHK_RET(ExchangeIpcMesg());
    return HCCL_SUCCESS;
}

HcclResult TransportShmEvent::ExchangeIpcMesg()
{
    HcclResult ret;

    if (deviceLogicId_ != HOST_DEVICE_ID) {
        /* 发送IPC input中转内存 */
        ret = SendIpcMemMesg(inputShmMem_.ptr(), inputShmMem_.size());
        CHK_PRT_RET(ret != HCCL_SUCCESS,
            HCCL_ERROR("[ExchangeI][pcMesg]In exchange ipc mesg, send ipc mem output mesg fail. ret[%d], "\
                "ptr[%p], size[%llu]", ret, inputShmMem_.ptr(), inputShmMem_.size()), ret);
        /* 发送IPC output中转内存 */
        ret = SendIpcMemMesg(outputShmMem_.ptr(), outputShmMem_.size());
        CHK_PRT_RET(ret != HCCL_SUCCESS,
            HCCL_ERROR("[ExchangeI][pcMesg]In exchange ipc mesg, send ipc mem output mesg fail. ret[%d], "\
                "ptr[%p], size[%llu]", ret, outputShmMem_.ptr(), outputShmMem_.size()), ret);
        /* 发送IPC 信封元素内存 */
        ret = SendIpcMemMesg(envelopeShmQue_.ptr(), envelopeShmQue_.size());
        CHK_PRT_RET(ret != HCCL_SUCCESS,
            HCCL_ERROR("[ExchangeI][pcMesg]In exchange ipc mesg, send ipc mem output mesg fail. ret[%d], "\
                "ptr[%p], size[%llu]", ret, envelopeShmQue_.ptr(), envelopeShmQue_.size()), ret);
    } else {
        u64 size = 0;
        /* 接收IPC input中转内存 */
        void *remoteMemPtr = nullptr;
        ret = RecvIpcMemMesg(&remoteMemPtr, remoteInputMemName_.ipcName, remoteInputOffsetValue_, size);
        CHK_PRT_RET(ret != HCCL_SUCCESS,
            HCCL_ERROR("[Exchange][IpcMesg]In exchange ipc mesg, recive ipc input mem mesg fail. ret[%d], "\
            "ptr[%p], mem name[%s], offset[%llu]", ret, remoteMemPtr, remoteInputMemName_.ipcName,
            remoteOutputOffsetValue_), ret);
        HCCL_DEBUG("remote inpue ptr size[%llu]", size);
        inputShmMem_ = DeviceMem::create(remoteMemPtr, size);
        /* 接收IPC output中转内存 */
        ret = RecvIpcMemMesg(&remoteMemPtr, remoteOutputMemName_.ipcName, remoteOutputOffsetValue_, size);
        CHK_PRT_RET(ret != HCCL_SUCCESS,
            HCCL_ERROR("[Exchange][IpcMesg]In exchange ipc mesg, recive ipc output mem mesg fail. ret[%d], "\
            "ptr[%p], mem name[%s], offset[%llu]", ret, remoteMemPtr, remoteOutputMemName_.ipcName,
            remoteOutputOffsetValue_), ret);
        HCCL_DEBUG("remote inpue ptr size[%llu]", size);
        outputShmMem_ = DeviceMem::create(remoteMemPtr, size);
        /* 接收IPC 信封元素内存 */
        ret = RecvIpcMemMesg(&remoteMemPtr, remoteEnvelopeItemMemName_.ipcName,
            remoteEnvelopeItemOffsetValue_, size);
        CHK_PRT_RET(ret != HCCL_SUCCESS,
            HCCL_ERROR("[Exchange][IpcMesg]In exchange ipc mesg, recive ipc envelope mem mesg fail. ret[%d], "\
            "ptr[%p], mem name[%s], offset[%llu]", ret, remoteMemPtr, remoteEnvelopeItemMemName_.ipcName,
            remoteOutputOffsetValue_), ret);
        envelopeShmQue_ = DeviceMem::create(remoteMemPtr, size);
    }

    return HCCL_SUCCESS;
}

HcclResult TransportShmEvent::SocketSend(std::string &message)
{
    u32 msgLen = message.length() + 1;
    /* 检查入参，包括消息长度是否符合要求，目的rank是否合法 */
    if (msgLen > MSG_BUFF_SIZE) {
        HCCL_ERROR("[ExchangerNetwork][Send]errNo[0x%016llx] deviceLogicId_[%d] message "\
            "length[%u] is illegal", HCCL_ERROR_CODE(HCCL_E_PARA), deviceLogicId_, msgLen);
        return HCCL_E_INTERNAL;
    }

    /* 使用socket发送，非阻塞。能确保写入发送缓冲区 */
    u8 buff[MSG_BUFF_SIZE] = {0};

    s32 sRet = strncpy_s(reinterpret_cast<char *>(buff), msgLen, message.c_str(), message.size());
    CHK_PRT_RET(sRet != EOK, HCCL_ERROR("[ExchangerNetwork][Send]errNo[0x%016llx]str copy failed, return[%d]. ",\
        HCCL_ERROR_CODE(HCCL_E_INTERNAL), sRet), HCCL_E_INTERNAL);
    CHK_RET(hrtRaSocketBlockSend(fdHandle_, buff, MSG_BUFF_SIZE));
    return HCCL_SUCCESS;
}

HcclResult TransportShmEvent::SocketRecv(std::string &message)
{
    /* 检查入参，包括消息长度是否符合要求，目的rank是否合法，清理出参message */
    message.clear();
    u8 buff[MSG_BUFF_SIZE] = {0};
    CHK_RET(hrtRaSocketBlockRecv(fdHandle_, buff, MSG_BUFF_SIZE));

    HCCL_DEBUG("socket deviceLogicId_[%d], msg_len[%u].", deviceLogicId_, MSG_BUFF_SIZE);

    /* 接收信息处理 */
    message.assign(reinterpret_cast<char *>(buff));

    return HCCL_SUCCESS;
}

HcclResult TransportShmEvent::ExchangePidMesg()
{
    if (deviceLogicId_ != HOST_DEVICE_ID) {
        /* 接收PS pid */
        CHK_RET(hrtRaSocketBlockRecv(fdHandle_, &recvPid_, sizeof(recvPid_)));
        HCCL_INFO("[ExchangePidMesg]recv ps pid[%d].", recvPid_);
    } else {
        /* PS发送pid给Worker */
        s32 psPid = 0;
        hrtDrvDeviceGetBareTgid(psPid);

        CHK_RET(hrtRaSocketBlockSend(fdHandle_, &psPid, sizeof(psPid)));
        HCCL_INFO("[ExchangePidMesg]send ps pid[%d].", psPid);
    }
    return HCCL_SUCCESS;
}

HcclResult TransportShmEvent::ExchangeSignalMesg()
{
    CHK_RET(hrtRaSocketBlockSend(fdHandle_, &deviceLogicId_, sizeof(s32)));
    CHK_RET(hrtRaSocketBlockRecv(fdHandle_, &remoteDeviceId_, sizeof(s32)));
    if (deviceLogicId_ == HOST_DEVICE_ID) {
        // ps
        // EVENT start
        NotifyMsg notifyMsg;
        CHK_RET(CreateIpcSignal(remoteIsendDoneNotify_, notifyMsg.remoteIsendDoneNotify));
        CHK_RET(CreateIpcSignal(remoteImrecvDoneNotify_, notifyMsg.remoteImrecvDoneNotify));
        CHK_RET(hrtRaSocketBlockSend(fdHandle_, &notifyMsg, sizeof(notifyMsg)));
        // EVENT end

        // Notify start
        CHK_RET(hrtRaSocketBlockRecv(fdHandle_, &notifyMsg, sizeof(notifyMsg)));
        std::vector<u8> isendDoneNotify(notifyMsg.remoteIsendDoneNotify,
            notifyMsg.remoteIsendDoneNotify + NOTIFY_INFO_LENGTH);
        CHK_RET(OpenRemoteNotify(isendDoneNotify, isendDoneNotify_));

        std::vector<u8> imrecvDoneNotify(notifyMsg.remoteImrecvDoneNotify,
            notifyMsg.remoteImrecvDoneNotify + NOTIFY_INFO_LENGTH);
        CHK_RET(OpenRemoteNotify(imrecvDoneNotify, imrecvDoneNotify_));
        // Notify end
    } else {
        // worker
        // EVENT start
        NotifyMsg notifyMsg;
        CHK_RET(hrtRaSocketBlockRecv(fdHandle_, &notifyMsg, sizeof(notifyMsg)));
        std::vector<u8> isendDoneNotify(notifyMsg.remoteIsendDoneNotify,
            notifyMsg.remoteIsendDoneNotify + NOTIFY_INFO_LENGTH);
        CHK_RET(OpenRemoteNotify(isendDoneNotify, isendDoneNotify_));

        std::vector<u8> imrecvDoneNotify(notifyMsg.remoteIsendDoneNotify,
            notifyMsg.remoteIsendDoneNotify + NOTIFY_INFO_LENGTH);
        CHK_RET(OpenRemoteNotify(imrecvDoneNotify, imrecvDoneNotify_));
        // EVENT end

        // Notify start
        CHK_RET(CreateIpcSignal(remoteIsendDoneNotify_, notifyMsg.remoteIsendDoneNotify));
        CHK_RET(CreateIpcSignal(remoteImrecvDoneNotify_, notifyMsg.remoteImrecvDoneNotify));
        CHK_RET(hrtRaSocketBlockSend(fdHandle_, &notifyMsg, sizeof(notifyMsg)));
        // Notify end
    }

    return HCCL_SUCCESS;
}

HcclResult TransportShmEvent::GetRemoteIsendDoneSignal(std::shared_ptr<LocalIpcNotify> &notify)
{
    notify = remoteIsendDoneNotify_;
    CHK_SMART_PTR_NULL(notify);
    return HCCL_SUCCESS;
}

HcclResult TransportShmEvent::GetRemoteImrecvDoneSignal(std::shared_ptr<LocalIpcNotify> &notify)
{
    notify = remoteImrecvDoneNotify_;
    CHK_SMART_PTR_NULL(notify);
    return HCCL_SUCCESS;
}

HcclResult TransportShmEvent::GetIsendDoneSignal(std::shared_ptr<RemoteNotify> &notify)
{
    notify = isendDoneNotify_;
    CHK_SMART_PTR_NULL(notify);
    return HCCL_SUCCESS;
}

HcclResult TransportShmEvent::CreateIpcSignal(std::shared_ptr<LocalIpcNotify> &localNotify, u8 *notifyInfo)
{
    EXECEPTION_CATCH((localNotify = std::make_shared<LocalIpcNotify>()), return HCCL_E_PTR);
    CHK_SMART_PTR_NULL(localNotify);

    CHK_RET(localNotify->Init(deviceLogicId_, remoteDeviceId_));
    CHK_RET(localNotify->SetIpc());
    s64 recvId = 0xFFFFFFFF00000000 | (static_cast<s64>(recvPid_) & 0xFFFFFFFF);
    CHK_RET(localNotify->Grant(recvId));

    std::vector<u8> data(NOTIFY_INFO_LENGTH, 0);
    CHK_RET(localNotify->Serialize(data));
    CHK_SAFETY_FUNC_RET(memcpy_s((u8 *)notifyInfo, NOTIFY_INFO_LENGTH, &data[0], data.size()));
    return HCCL_SUCCESS;
}

HcclResult TransportShmEvent::SendIpcMemMesg(void *ptr, u64 size)
{
    HcclResult ret;
    /* make memory shared interprocess and assigned a name */
    u64 offset;
    SecIpcName_t memName;
    ret = MemNameRepository::GetInstance(deviceLogicId_)->SetIpcMem(ptr, size, memName.ipcName, NAME_LEN,
        offset, recvPid_);
    CHK_PRT_RET(ret != HCCL_SUCCESS,
        HCCL_ERROR("[Send][IpcMemMesg]errNo[0x%016llx], In send ipc mesg, get para mem name failed. "\
        "mem addr[%p] local rank[%u]", HCCL_ERROR_CODE(ret), ptr, machinePara_.localUserrank), ret);

    /* send memName to remote rank */
    CHK_RET(hrtRaSocketBlockSend(fdHandle_, &memName.ipcName, NAME_LEN));

    std::string memOffset = std::to_string(offset);
    HCCL_INFO("localUserrank=%u, ptr=%p, remoteUserrank=%u, mem_offset=%s.",
        machinePara_.localUserrank, ptr, machinePara_.remoteUserrank, memOffset.c_str());

    /* send memsize to remote rank */
    CHK_RET(hrtRaSocketBlockSend(fdHandle_, &size, sizeof(u64)));

    /* send memOffset to remote rank */
    CHK_RET(SocketSend(memOffset));

    HCCL_DEBUG("localUserrank=%u, ptr=%p, remoteUserrank=%u, offset=%s, memName[%s].",
        machinePara_.localUserrank, ptr, machinePara_.remoteUserrank, memOffset.c_str(), memName.ipcName);
    return HCCL_SUCCESS;
}

HcclResult TransportShmEvent::RecvIpcMemMesg(void **memPtr, u8 *memName, u64 &offset, u64 &size)
{
    HcclResult ret;
    /* 获取对端内存名字 */
    CHK_RET(hrtRaSocketBlockRecv(fdHandle_, memName, NAME_LEN));
    /* 获取对端内存的大小 */
    CHK_RET(hrtRaSocketBlockRecv(fdHandle_, &size, sizeof(u64)));

    /* 获取对端内存的偏移值 */
    std::string remoteOffsetName;
    CHK_RET(SocketRecv(remoteOffsetName));

    CHK_RET(SalStrToULonglong(remoteOffsetName, HCCL_BASE_DECIMAL, offset));

    /* 根据名字，获取对端IPC 内存 */
    ret = WaitPeerMemConfig(memPtr, const_cast<u8 *>(memName), size, offset);
    CHK_PRT_RET(ret != HCCL_SUCCESS,
        HCCL_ERROR("[Recv][IpcMemMesg]errNo[0x%016llx]In recv ipc mem mesg, wait peer mem config "\
        "failed. local rank[%u]", HCCL_ERROR_CODE(ret), machinePara_.localUserrank), ret);

    HCCL_DEBUG("localUserrank[%u] receive from remoteUserrank[%u], memName[%s]",
        machinePara_.localUserrank, machinePara_.remoteUserrank, memName);

    return HCCL_SUCCESS;
}

HcclResult TransportShmEvent::WaitPeerMemConfig(void **memPtr, const u8 *memName, uint64_t size, u64 offset)
{
    CHK_PTR_NULL(memPtr);
    CHK_PTR_NULL(memName);

    bool firstOpened = false;
    // 支持进程间、进程内都可以通过name获取对端内存
    HcclResult ret = MemNameRepository::GetInstance(deviceLogicId_)->OpenIpcMem(memPtr, size, memName, 65,
        offset, firstOpened);
    CHK_PRT_RET(ret != HCCL_SUCCESS,
        HCCL_ERROR("[Wait][WaitPeerMemConfig]errNo[0x%016llx]In link pcie, open mem failed. offset[%llu], size[%llu Byte]",
            HCCL_ERROR_CODE(ret), offset, size), ret);
    return HCCL_SUCCESS;
}

void TransportShmEvent::GetScratchMem(std::vector<DeviceMem> &scratchMemInfos)
{
    u32 size = 2;
    scratchMemInfos.resize(size);
    scratchMemInfos[0] = inputShmMem_;
    scratchMemInfos[1] = outputShmMem_;
}

HcclResult TransportShmEvent::PrepareConnect()
{
    if (selfIp_ == peerIp_) {
        role_ = (selfPort_ < peerPort_) ? SERVER_ROLE_SOCKET : CLIENT_ROLE_SOCKET;
    } else {
        role_ = (selfIp_ < peerIp_) ? SERVER_ROLE_SOCKET : CLIENT_ROLE_SOCKET;
    }

    linkTag_ = tag_;
    if (role_ == CLIENT_ROLE_SOCKET) {
        linkTag_ += std::string(peerIp_.GetReadableIP()) + std::to_string(peerPort_) +
            std::string(selfIp_.GetReadableIP()) + std::to_string(selfPort_);
    } else {
        linkTag_ += std::string(selfIp_.GetReadableIP()) + std::to_string(selfPort_) +
            std::string(peerIp_.GetReadableIP()) + std::to_string(peerPort_);
    }
    HCCL_INFO("link tag[%s]", linkTag_.c_str());

    CHK_RET(InitSocketWhiteList());
    CHK_RET(AddSocketWhiteList());
    CHK_RET(ConnectToServer());

    return HCCL_SUCCESS;
}

HcclResult TransportShmEvent::GetConnection()
{
    SocketInfoT socketInfo = {nullptr};

    socketInfo.socketHandle = socketHandle_;
    socketInfo.fdHandle = nullptr;
    socketInfo.remoteIp.addr = peerIp_.GetBinaryAddress().addr;
    socketInfo.remoteIp.addr6 = peerIp_.GetBinaryAddress().addr6;

    socketInfo.status = CONNECT_FAIL;
    s32 sRet = memcpy_s(socketInfo.tag, sizeof(socketInfo.tag) - 1, linkTag_.c_str(), linkTag_.size());
    CHK_PRT_RET(sRet != EOK, HCCL_ERROR("memcpy_s failed, errorno[%d]", sRet), HCCL_E_MEMORY);
    CHK_RET(hrtRaBlockGetSockets(role_, &socketInfo, 1));
    CHK_PRT_RET((socketInfo.status != CONNECT_OK) || (socketInfo.fdHandle == nullptr),
        HCCL_ERROR("[Socket][GetConnection] get socket failed. status[%d]",
            socketInfo.status), HCCL_E_TCP_TRANSFER);
    fdHandle_ = socketInfo.fdHandle;
    HCCL_INFO("[Socket][GetConnection] get socket success with remote[%s], tag[%s]",
        peerIp_.GetReadableAddress(), socketInfo.tag);

    return HCCL_SUCCESS;
}

HcclResult TransportShmEvent::ConnectToServer()
{
    if (role_ != CLIENT_ROLE_SOCKET) {
        return HCCL_SUCCESS;
    }

    SocketConnectInfoT connInfo = {nullptr};
    connInfo.remoteIp.addr = peerIp_.GetBinaryAddress().addr;
    connInfo.remoteIp.addr6 = peerIp_.GetBinaryAddress().addr6;
    connInfo.socketHandle = socketHandle_;
    connInfo.port = peerPort_;
    s32 sRet = memcpy_s(connInfo.tag, sizeof(connInfo.tag) - 1, linkTag_.c_str(), linkTag_.size());
    CHK_PRT_RET(sRet != EOK, HCCL_ERROR("memcpy_s failed, errorno[%d]", sRet), HCCL_E_MEMORY);
    HCCL_INFO("[Socket][ConnectToServer] tag[%s]", connInfo.tag);
    CHK_RET(hrtRaSocketBatchConnect(&connInfo, 1));
    return HCCL_SUCCESS;
}

HcclResult TransportShmEvent::InitSocketWhiteList()
{
    s32 sRet = memset_s(&wlistInfo_, sizeof(wlistInfo_), 0, sizeof(wlistInfo_));
    CHK_PRT_RET(sRet != EOK, HCCL_ERROR("memset failed, errorno[%d]", sRet), HCCL_E_MEMORY);

    wlistInfo_.connLimit = NIC_SOCKET_CONN_LIMIT;

    sRet = memcpy_s(wlistInfo_.tag, sizeof(wlistInfo_.tag) - 1, linkTag_.c_str(), linkTag_.size());
    CHK_PRT_RET(sRet != EOK, HCCL_ERROR("memcpy_s failed, errorno[%d]", sRet), HCCL_E_MEMORY);

    wlistInfo_.remoteIp.addr = peerIp_.GetBinaryAddress().addr;
    wlistInfo_.remoteIp.addr6 = peerIp_.GetBinaryAddress().addr6;
    HCCL_INFO("[Socket][InitSocketWhiteList] tag[%s]", wlistInfo_.tag);

    return HCCL_SUCCESS;
}

HcclResult TransportShmEvent::AddSocketWhiteList()
{
    if (role_ != SERVER_ROLE_SOCKET) {
        return HCCL_SUCCESS;
    }

    CHK_RET(hrtRaSocketWhiteListAdd(socketHandle_, &wlistInfo_, 1));
    return HCCL_SUCCESS;
}

HcclResult TransportShmEvent::DelSocketWhiteList()
{
    if (role_ != SERVER_ROLE_SOCKET) {
        return HCCL_SUCCESS;
    }
    CHK_RET(hrtRaSocketWhiteListDel(socketHandle_, &wlistInfo_, 1));
    return HCCL_SUCCESS;
}

HcclResult TransportShmEvent::Close()
{
    if (fdHandle_ == nullptr) {
        return HCCL_SUCCESS;
    }
    HCCL_INFO("[Socket][Close] linkTag[%s]", linkTag_.c_str());
    CHK_RET(DelSocketWhiteList());
    SocketCloseInfoT closeInfo = {0};
    closeInfo.socketHandle = socketHandle_;
    closeInfo.fdHandle = fdHandle_;
    if (hrtRaSocketBatchClose(&closeInfo, 1) != HCCL_SUCCESS) {
        HCCL_ERROR("ra socket batch close failed");
    }
    return HCCL_SUCCESS;
}

HcclResult TransportShmEvent::SetCtxCurrent()
{
    HcclRtContext ctx = nullptr;
    CHK_RET(hrtCtxGetCurrent(&ctx));

    if (ctx != rtCtx_) {
        HCCL_INFO("hrt set ctx [%p]", rtCtx_);
        CHK_RET(hrtCtxSetCurrent(rtCtx_));  // set rt ctx
    }
    return HCCL_SUCCESS;
}

HcclResult TransportShmEvent::Init()
{
    HCCL_INFO(
        "machineType=[%d], serverId=[%s], localDeviceId=[%d], remoteDeviceId=[%d], \
        localRank=[%u], localUserRank=[%u], remoteRank=[%u], remoteUserRank=[%u], \
        deviceType=[%d], inputMem=%p, outputMem=%p",
        machinePara_.machineType, machinePara_.serverId.c_str(), machinePara_.localDeviceId,
        machinePara_.remoteDeviceId, machinePara_.localUserrank, machinePara_.localWorldRank,
        machinePara_.remoteUserrank, machinePara_.remoteWorldRank,
        machinePara_.deviceType, machinePara_.inputMem.ptr(),
        machinePara_.outputMem.ptr());

    RaResourceInfo raResourceInfo;
    CHK_RET(NetworkManager::GetInstance(machinePara_.deviceLogicId).GetRaResourceInfo(raResourceInfo));
    socketHandle_ = raResourceInfo.hostNetSocketMap[selfIp_].nicSocketHandle;
    CHK_PTR_NULL(socketHandle_);

    CHK_SMART_PTR_NULL(machinePara_.inputMem);
    CHK_SMART_PTR_NULL(machinePara_.outputMem);
    CHK_RET(DlHalFunction::GetInstance().DlHalFunctionInit());

    CHK_PTR_NULL(rtCtx_);
    CHK_RET(SetCtxCurrent());  // set rt ctx

    if (deviceLogicId_ == HOST_DEVICE_ID) {
        nodeType_ = NodeType::PS_NODE;
    } else {
        nodeType_ = NodeType::WORKER_NODE;
    }

    CHK_RET(CheckRecvMsgAndRequestBuffer());

    CHK_RET(PrepareConnect());
    CHK_RET(GetConnection());

    // ps、worker初始化EVENT并互相交换EVENT info
    // ps侧在transport init时订阅EVENT
    // 之后device侧注册transport时实际订阅EVENT
    if (!eschedEventInit_ && deviceLogicId_ == HOST_DEVICE_ID) {
        CHK_RET(hrtHalEschedAttachDevice(0));

        eschedEventInit_ = true;
    }

    // ps发送pid给worker用于设置ipc pic白名单
    CHK_RET(ExchangePidMesg());
    CHK_RET(ExchangeSignalMesg());

    CHK_RET(InitMem()); // 初始化内存信息，初始化信封队列的dev mem（ipc），初始化2块中转内存

    isInited_ = true;
    HCCL_INFO("[TransportShmEvent] init success! serverId[%s] localRank[%u], localIp[%s], remoteRank[%u], "
        "remoteIp[%u], linkTag[%s]", machinePara_.serverId.c_str(), machinePara_.localUserrank,
        selfIp_.GetReadableAddress(), machinePara_.remoteUserrank, peerIp_.GetReadableAddress(), linkTag_.c_str());
    return HCCL_SUCCESS;
}

HcclResult TransportShmEvent::Init(TransportShmEventMember transport)  // aicpu-sd进程中执行
{
    CHK_RET(CheckRecvMsgAndRequestBuffer());

    deviceLogicId_ = transport.deviceLogicId;
    inputShmMem_ = transport.inputShmMem;
    outputShmMem_ = transport.outputShmMem;
    envelopeShmQue_ = transport.envelopeShmQue;
    localEnvelopeShmQue_ = static_cast<u8 *>(envelopeShmQue_.ptr()) + sizeof(ShmEnvelopeQue);

    return HCCL_SUCCESS;
}

HcclResult TransportShmEvent::Deinit()
{
    if (!isInited_) {
        return HCCL_SUCCESS;
    }

    CHK_RET(Close());

    isInited_ = false;
    return HCCL_SUCCESS;
}

HcclResult TransportShmEvent::CheckShmMemRange(MemType memType, u64 offset, u64 count, u32 dataType)
{
    if (dataType >= HCCL_DATA_TYPE_RESERVED) {
        HCCL_ERROR("dataType >= HCCL_DATA_TYPE_RESERVED", dataType);
        return HCCL_E_NOT_SUPPORT;
    }

    u64 shmMemSize = memType == MemType::USER_INPUT_MEM ? inputShmMem_.size() : outputShmMem_.size();
    u64 length = count * SIZE_TABLE[dataType];
    if ((offset + length) > shmMemSize) {
        HCCL_ERROR("(offset[%llu] + length[%llu]) > shmMemSize[%llu Byte]", offset, length, shmMemSize);
        return HCCL_E_MEMORY;
    }

    return HCCL_SUCCESS;
}

HcclResult TransportShmEvent::Isend(const TransData &sendData, const TransportEndPointParam &epParam,
    HcclRequestInfo *&request)
{
    CHK_RET(GenerateSendRequest(sendData, epParam, request));

    MemType memType;
    u64 offset = 0;
    CHK_RET(GetMemInfo(sendData.srcBuf, memType, offset));
    CHK_RET(CheckShmMemRange(memType, offset, sendData.count, sendData.dataType));
    HcclEnvelopePcie envelope(memType, offset, sendData.count, sendData.dataType, false, sendData.tableId,
        sendData.globalStep);
    if (sendData.count == 0) {
        envelope.updateEndFlag = true;
    }

    CHK_RET(PushEnvelope(envelope));
    HCCL_DEBUG("print envelope memType[%d] offset[%llu] count[%llu] dataType[%s] updateEndFlag[%d]",
        envelope.memType, envelope.offset, envelope.count, GetDataTypeEnumStr(envelope.dataType).c_str(),
        envelope.updateEndFlag);
    if (deviceLogicId_ == HOST_DEVICE_ID) {
        Stream tmpStream(nullptr);
        CHK_RET(isendDoneNotify_->Post(tmpStream, dispatcher_));
    }

    return HCCL_SUCCESS;
}

HcclResult TransportShmEvent::GetMemInfo(uintptr_t memPtr, MemType &memType, u64 &offset)
{
    HCCL_DEBUG("GetMemInfo inputShmMem_ ptr[%p] uintptr[%llx] size[%llu Byte]",
        inputShmMem_.ptr(), reinterpret_cast<uintptr_t>(inputShmMem_.ptr()), inputShmMem_.size());
    HCCL_DEBUG("GetMemInfo outputShmMem_ ptr[%p] uintptr[%llx] size[%llu Byte]",
        outputShmMem_.ptr(), reinterpret_cast<uintptr_t>(inputShmMem_.ptr()), outputShmMem_.size());
    HCCL_DEBUG("GetMemInfo envelopeShmQue_ ptr[%p] uintptr[%llx] size[%llu Byte]",
        envelopeShmQue_.ptr(), reinterpret_cast<uintptr_t>(inputShmMem_.ptr()), envelopeShmQue_.size());
    HCCL_DEBUG("GetMemInfo input param memPtr[%llx]", memPtr);

    uintptr_t shmPtr = reinterpret_cast<uintptr_t>(inputShmMem_.ptr());
    if (memPtr >= shmPtr) {
        offset = memPtr - shmPtr;
        if (offset < inputShmMem_.size()) {
            memType = MemType::USER_INPUT_MEM;
            return HCCL_SUCCESS;
        }
    }

    shmPtr = reinterpret_cast<uintptr_t>(outputShmMem_.ptr());
    if (memPtr >= shmPtr) {
        offset = memPtr - shmPtr;
        if (offset < outputShmMem_.size()) {
            memType = MemType::USER_OUTPUT_MEM;
            return HCCL_SUCCESS;
        }
    }

    HCCL_ERROR("[Get][MemInfo] get mem info failed, memory ptr(0x%llx).", memPtr);
    return HCCL_E_PARA;
}

HcclResult TransportShmEvent::Send(const TransData &sendData, const TransportEndPointParam &epParam)
{
    Stream tmpStream(nullptr);
    CHK_RET(isendDoneNotify_->Post(tmpStream, dispatcher_));
    return HCCL_SUCCESS;
}

HcclResult TransportShmEvent::Improbe(const TransportEndPointParam &epParam, s32 &matched,
    HcclMessageInfo *&msg, HcclStatus &status)
{
    bool flag = true;
    return Improbe(epParam, matched, msg, status, flag);
}

HcclResult TransportShmEvent::Improbe(const TransportEndPointParam &epParam, s32 &matched, HcclMessageInfo *&msg,
    HcclStatus &status, bool &flag)
{
    HcclEnvelopeSummary envelopInfo{};
    if (deviceLogicId_ == HOST_DEVICE_ID) {
        // Improbe外部有循环保证, 所以不需要设置内部等待延时
        u32 timeOut = 0;
        if (flag) {
            Stream tmpStream(nullptr);
            HcclResult ret = remoteIsendDoneNotify_->Wait(tmpStream, dispatcher_, INVALID_VALUE_STAGE, timeOut);
            if (ret == HCCL_E_AGAIN) {
                return ProbeNothing(matched, msg, status);
            } else if (ret == HCCL_SUCCESS) {
                flag = false;
            } else {
                HCCL_ERROR("[TransportShmEvent][Improbe] wait notify error [%d].", ret);
                return ret;
            }
        }

        CHK_RET(FrontEnvelope(envelopInfo.pcieEnvelope));
        CHK_RET(PopEnvelope());
    } else {
        CHK_RET(FrontEnvelope(envelopInfo.pcieEnvelope));
        CHK_RET(PopEnvelope());
    }

    CHK_RET(GenerateRecvMessage(envelopInfo, msg, status));
    status.count = envelopInfo.pcieEnvelope.count;
    status.error = 0;
    matched = HCCL_IMPROBE_COMPLETED;
    HCCL_DEBUG("Improbe: memType[%u] offset[%llu] count[%llu] datatype[%s]",
        envelopInfo.pcieEnvelope.memType, envelopInfo.pcieEnvelope.offset, envelopInfo.pcieEnvelope.count,
        GetDataTypeEnumStr(envelopInfo.pcieEnvelope.dataType).c_str());
    return HCCL_SUCCESS;
}

HcclResult TransportShmEvent::Imrecv(const TransData &recvData, HcclMessageInfo &msg, HcclRequestInfo *&request)
{
    return Imrecv(recvData, msg, request, true, true);
}

HcclResult TransportShmEvent::Imrecv(const TransData &recvData, HcclMessageInfo &msg, HcclRequestInfo *&request,
    bool flag, bool needRecordFlag)
{
    CHK_RET(GenerateRecvRequest(recvData, msg, request));

    HcclEnvelopePcie &envelope = msg.envelope.pcieEnvelope;
    if (envelope.count != 0) {
        void *localMem = reinterpret_cast<void *>(recvData.dstBuf);
        u64 maxLength = recvData.count * SIZE_TABLE[recvData.dataType];
        u64 length = envelope.count * SIZE_TABLE[envelope.dataType];
        void *remoteBaseMem = envelope.memType == MemType::USER_INPUT_MEM ? inputShmMem_.ptr() : outputShmMem_.ptr();

        CHK_RET(CheckShmMemRange(envelope.memType, envelope.offset, envelope.count, envelope.dataType));
        void *remoteMem = reinterpret_cast<void *>(reinterpret_cast<uintptr_t>(remoteBaseMem) + envelope.offset);

        if (localMem != remoteMem) {
            if (ShmMemcpy(localMem, maxLength, remoteMem, length) != HCCL_SUCCESS) {
                HCCL_ERROR("[TransportShmEvent][Imrecv] shm mem cpy failed, local mem %p max length %llu remote mem %p"\
                    " length %llu", localMem, maxLength, remoteMem, length);
                return HCCL_E_MEMORY;
            }
        }
    }
    if (deviceLogicId_ == HOST_DEVICE_ID) {
        if (flag) {
            Stream tmpStream(nullptr);
            CHK_RET(imrecvDoneNotify_->Post(tmpStream, dispatcher_));
        } else {
            if (envelope.count == 0 && needRecordFlag) {
                Stream tmpStream(nullptr);
                CHK_RET(imrecvDoneNotify_->Post(tmpStream, dispatcher_));
            }
        }
    }
    CHK_RET(FreeRecvMessage(msg));
    return HCCL_SUCCESS;
}

HcclResult TransportShmEvent::Test(HcclRequestInfo &request, s32 &flag, HcclStatus &compState)
{
    flag = HCCL_TEST_COMPLETED;
    HCCL_INFO("QueryRequestStatus: flag [%d]", flag);
    compState.error = 0;
    CHK_RET(FreeRequest(request));
    return HCCL_SUCCESS;
}

HcclResult TransportShmEvent::EnterStateProcess(ConnState nextState)
{
    return HCCL_SUCCESS;
}

HcclResult TransportShmEvent::LoopStateProcess()
{
    return HCCL_SUCCESS;
}

HcclResult TransportShmEvent::PushEnvelope(HcclEnvelopePcie &envelope)
{
    std::unique_lock<std::mutex> lock(queMutex_);
    if (deviceLogicId_ == HOST_DEVICE_ID) {
        ShmEnvelopeQue tempQue;
        void *remoteQue = static_cast<u8 *>(envelopeShmQue_.ptr()) + sizeof(ShmEnvelopeQue);
        CHK_RET(hrtDrvMemCpy(&tempQue.queInfo, sizeof(ShmEnvelopeQue), remoteQue, sizeof(tempQue.queInfo)));

        CHK_PRT_RET((tempQue.queInfo.size >= ENVELOPE_QUE_CAPACITY),
            HCCL_WARNING("shm que is full"), HCCL_E_AGAIN);

        u32 tempHead = tempQue.queInfo.head;
        u8 *dstAddr = static_cast<u8 *>(remoteQue) + MEMBER_OFFSET(ShmEnvelopeQue, que) +
            (tempHead * sizeof(HcclEnvelopePcie));
        CHK_RET(hrtDrvMemCpy(dstAddr, ENVELOPE_QUE_CAPACITY * sizeof(HcclEnvelopePcie) - tempHead *
            sizeof(HcclEnvelopePcie), &envelope, sizeof(HcclEnvelopePcie)));
        tempQue.queInfo.head = (tempQue.queInfo.head + 1) % ENVELOPE_QUE_CAPACITY;
        tempQue.queInfo.size++;

        CHK_RET(hrtDrvMemCpy(remoteQue, sizeof(ShmEnvelopeQue), &tempQue.queInfo, sizeof(tempQue.queInfo)));
    } else {
        ShmEnvelopeQue *quePtr = static_cast<ShmEnvelopeQue *>(envelopeShmQue_.ptr());
        quePtr->que[quePtr->queInfo.head] = envelope;
        quePtr->queInfo.head = (quePtr->queInfo.head + 1) % ENVELOPE_QUE_CAPACITY;
        quePtr->queInfo.size++;
    }
    return HCCL_SUCCESS;
}

HcclResult TransportShmEvent::FrontEnvelope(HcclEnvelopePcie &envelope)
{
    std::unique_lock<std::mutex> lock(queMutex_);
    if (deviceLogicId_ == HOST_DEVICE_ID) {
        ShmEnvelopeQue::QueInfo queInfo;
        CHK_RET(hrtDrvMemCpy(&queInfo, sizeof(queInfo), envelopeShmQue_.ptr(), sizeof(ShmEnvelopeQue::QueInfo)));
        if (queInfo.size == 0) {
            HCCL_ERROR("[TransportShmEvent][FrontEnvelope] que size is zero head[%u] tail[%u]",
                queInfo.head, queInfo.tail);
            return HCCL_E_INTERNAL;
        }

        u8 *queBeginAddr = static_cast<u8 *>(envelopeShmQue_.ptr()) + MEMBER_OFFSET(ShmEnvelopeQue, que);
        CHK_RET(hrtDrvMemCpy(&envelope, sizeof(HcclEnvelopePcie),
            queBeginAddr + queInfo.tail * sizeof(HcclEnvelopePcie), sizeof(HcclEnvelopePcie)));
    } else {
        ShmEnvelopeQue *quePtr = static_cast<ShmEnvelopeQue *>(localEnvelopeShmQue_);
        envelope = quePtr->que[quePtr->queInfo.tail];
    }
    return HCCL_SUCCESS;
}

HcclResult TransportShmEvent::PopEnvelope()
{
    std::unique_lock<std::mutex> lock(queMutex_);
    if (deviceLogicId_ == HOST_DEVICE_ID) {
        ShmEnvelopeQue::QueInfo queInfo;
        CHK_RET(hrtDrvMemCpy(&queInfo, sizeof(queInfo), envelopeShmQue_.ptr(), sizeof(ShmEnvelopeQue::QueInfo)));

        queInfo.tail = (queInfo.tail + 1) % ENVELOPE_QUE_CAPACITY;
        queInfo.size--;
        CHK_RET(hrtDrvMemCpy(envelopeShmQue_.ptr(), sizeof(ShmEnvelopeQue), &queInfo, sizeof(queInfo)));
    } else {
        ShmEnvelopeQue *quePtr = static_cast<ShmEnvelopeQue *>(localEnvelopeShmQue_);
        quePtr->queInfo.tail = (quePtr->queInfo.tail + 1) % ENVELOPE_QUE_CAPACITY;
        quePtr->queInfo.size--;
    }
    return HCCL_SUCCESS;
}

HcclResult TransportShmEvent::EnvelopeQueSize(u32 &size)
{
    std::unique_lock<std::mutex> lock(queMutex_);
    if (deviceLogicId_ == HOST_DEVICE_ID) {
        ShmEnvelopeQue::QueInfo queInfo;
        CHK_RET(hrtDrvMemCpy(&queInfo, sizeof(queInfo), envelopeShmQue_.ptr(), sizeof(ShmEnvelopeQue::QueInfo)));
        size = queInfo.size;
    } else {
        ShmEnvelopeQue *quePtr = static_cast<ShmEnvelopeQue *>(localEnvelopeShmQue_);
        size = quePtr->queInfo.size;
    }
    return HCCL_SUCCESS;
}

HcclResult TransportShmEvent::RemoteEnvelopeQueSize(u32 &size)
{
    std::unique_lock<std::mutex> lock(queMutex_);
    if (deviceLogicId_ == HOST_DEVICE_ID) {
        ShmEnvelopeQue::QueInfo queInfo;
        CHK_RET(hrtDrvMemCpy(&queInfo, sizeof(queInfo),
            static_cast<u8 *>(envelopeShmQue_.ptr()) + sizeof(ShmEnvelopeQue), sizeof(ShmEnvelopeQue::QueInfo)));
        size = queInfo.size;
    } else {
        ShmEnvelopeQue *quePtr = static_cast<ShmEnvelopeQue *>(envelopeShmQue_.ptr());
        size = quePtr->queInfo.size;
    }
    return HCCL_SUCCESS;
}

HcclResult TransportShmEvent::GetTransportMember(TransportShmEventMember &transport)
{
    transport.deviceLogicId = deviceLogicId_;
    transport.inputShmMem = inputShmMem_;
    transport.outputShmMem = outputShmMem_;
    transport.envelopeShmQue = envelopeShmQue_;

    return HCCL_SUCCESS;
}

HcclResult TransportShmEvent::ShmMemcpy(void *dst, uint64_t destMax, const void *src, uint64_t count)
{
    if (deviceLogicId_ == HOST_DEVICE_ID) {
        TIME_PRINT(CHK_RET(hrtDrvMemCpy(dst, destMax, src, count)));
    } else {
        CHK_SAFETY_FUNC_RET(memmove_s(dst, destMax, src, count));
    }
    return HCCL_SUCCESS;
}

void TransportShmEvent::GetLinkTag(std::string &tag)
{
    tag = linkTag_;
    return;
}