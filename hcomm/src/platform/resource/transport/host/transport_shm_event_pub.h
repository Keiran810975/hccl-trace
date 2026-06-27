/**
 * Copyright (c) 2025 Huawei Technologies Co., Ltd.
 * This program is free software, you can redistribute it and/or modify it under the terms and conditions of
 * CANN Open Software License Agreement Version 2.0 (the "License").
 * Please refer to the License for details. You may not use this file except in compliance with the License.
 * THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
 * INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
 * See LICENSE in the root of the software repository for the full text of the License.
 */

#ifndef TRANSPORT_SHM_EVENT_PUB_H
#define TRANSPORT_SHM_EVENT_PUB_H

#include<mutex>

#include "transport_base_pub.h"
#include "transport_heterog_pub.h"
#include "memory_alloc_ring.h"
#include "hccl/base.h"
#include "adapter_hal.h"
#include "es_private.h"

namespace hccl {

struct TransportShmEventMember {
    u32 rank;
    u32 tag;
    s32 deviceLogicId;
    DeviceMem inputShmMem;
    DeviceMem outputShmMem;
    DeviceMem envelopeShmQue;
};

enum class NodeType {
    WORKER_NODE = 0,
    PS_NODE
};

constexpr u32 ENVELOPE_QUE_CAPACITY = 256;
constexpr u32 TIME_TEN_US = 10;

class TransportShmEvent : public TransportBase, public TransportHeterog {
public:
    struct ShmEnvelopeQue {
        struct QueInfo {
            u32 tail = 0;
            u32 head = 0;
            u32 size = 0;
        } queInfo;
        HcclEnvelopePcie que[ENVELOPE_QUE_CAPACITY];
        u32 hostLock = 0;
        u32 deviceLock = 0;
    };

    class ShmQueLock {
    public:
        explicit ShmQueLock(void *shmQue, s32 id) : shmQue_(shmQue), id_(id) {}
        virtual ~ShmQueLock()
        {
            Unlock();
        }

        HcclResult Lock()
        {
            CHK_PTR_NULL(shmQue_);
            if (id_ == HOST_DEVICE_ID) {
                u32 lockNum = 1;
                u32 hostLockOffset = MEMBER_OFFSET(ShmEnvelopeQue, hostLock);
                uintptr_t lockAddr = reinterpret_cast<uintptr_t>(shmQue_) + hostLockOffset;
                CHK_RET(hrtDrvMemCpy(reinterpret_cast<void *>(lockAddr), sizeof(u32), &lockNum, sizeof(u32)));

                u32 deviceLockOffset = MEMBER_OFFSET(ShmEnvelopeQue, deviceLock);
                lockAddr = reinterpret_cast<uintptr_t>(shmQue_) + deviceLockOffset;
                while (lockNum != 0) {
                    CHK_RET(hrtDrvMemCpy(&lockNum, sizeof(u32), reinterpret_cast<void *>(lockAddr), sizeof(u32)));
                    SaluSleep(TIME_TEN_US);
                }
            } else {
                ShmEnvelopeQue *quePtr = static_cast<ShmEnvelopeQue *>(shmQue_);
                while (quePtr->hostLock != 0) {
                    SaluSleep(TIME_TEN_US);
                }

                quePtr->deviceLock = 1;
            }
            return HCCL_SUCCESS;
        }

        HcclResult Unlock()
        {
            if (id_ == HOST_DEVICE_ID) {
                u32 lockNum = 0;
                uintptr_t lockAddr = reinterpret_cast<uintptr_t>(shmQue_) + MEMBER_OFFSET(ShmEnvelopeQue, hostLock);
                CHK_RET(hrtDrvMemCpy(reinterpret_cast<void *>(lockAddr), sizeof(u32), &lockNum, sizeof(u32)));
            } else {
                ShmEnvelopeQue *quePtr = static_cast<ShmEnvelopeQue *>(shmQue_);
                quePtr->deviceLock = 0;
            }
            return HCCL_SUCCESS;
        }
    private:
        void *shmQue_ = nullptr;
        s32 id_ = 0;
    };

public:
    explicit TransportShmEvent(const HcclDispatcher dispatcher,
                        const std::unique_ptr<NotifyPool> &notifyPool,
                        MachinePara &machinePara,
                        std::chrono::milliseconds timeout, HcclIpAddress &selfIp, HcclIpAddress &peerIp, u32 peerPort,
                        u32 selfPort, s32 deviceLogicId, u32 role,
                        const TransportResourceInfo &transportResourceInfo,
                        HcclRtContext rtCtx);
    ~TransportShmEvent() override;

    HcclResult Init() override;
    HcclResult Init(TransportShmEventMember transport);

    HcclResult GetTransportMember(TransportShmEventMember &transport);

    HcclResult Deinit() override;
    HcclResult EnterStateProcess(ConnState nextState) override;
    HcclResult LoopStateProcess() override;
    HcclResult Isend(const TransData &sendData, const TransportEndPointParam &epParam,
        HcclRequestInfo *&request) override;
    HcclResult Send(const TransData &sendData, const TransportEndPointParam &epParam) override;
    HcclResult Improbe(const TransportEndPointParam &epParam, s32 &matched, HcclMessageInfo *&msg,
        HcclStatus &status) override;
    HcclResult Imrecv(const TransData &recvData, HcclMessageInfo &msg, HcclRequestInfo *&request) override;
    HcclResult Test(HcclRequestInfo &request, s32 &flag, HcclStatus &compState) override;
    HcclResult Improbe(const TransportEndPointParam &epParam, s32 &matched, HcclMessageInfo *&msg,
        HcclStatus &status, bool &flag) override;
    HcclResult Imrecv(const TransData &recvData, HcclMessageInfo &msg, HcclRequestInfo *&request,
        bool flag, bool needRecordFlag) override;

    void GetScratchMem(std::vector<DeviceMem> &scratchMemInfos);

    HcclResult GetRemoteIsendDoneSignal(std::shared_ptr<LocalIpcNotify> &notify);
    HcclResult GetRemoteImrecvDoneSignal(std::shared_ptr<LocalIpcNotify> &notify);
    HcclResult GetIsendDoneSignal(std::shared_ptr<RemoteNotify> &notify);
    void GetLinkTag(std::string &tag) override;

    NodeType nodeType_;
private:
    HcclResult InitSharedQue();
    HcclResult InitSharedMem();
    HcclResult ExchangeIpcMesg();
    HcclResult SocketSend(std::string &message);
    HcclResult SocketRecv(std::string &message);
    HcclResult SendIpcMemMesg(void *ptr, u64 size);
    HcclResult RecvIpcMemMesg(void **memPtr, u8 *memName, u64 &offset, u64 &size);
    HcclResult WaitPeerMemConfig(void **memPtr, const u8 *memName, uint64_t size, u64 offset);

    HcclResult InitMem();

    HcclResult PrepareConnect();
    HcclResult GetConnection();
    HcclResult ConnectToServer();
    HcclResult InitSocketWhiteList();
    HcclResult AddSocketWhiteList();
    HcclResult DelSocketWhiteList();
    HcclResult Close();

    HcclResult PushEnvelope(HcclEnvelopePcie &envelope);
    HcclResult FrontEnvelope(HcclEnvelopePcie &envelope);
    HcclResult PopEnvelope();
    HcclResult EnvelopeQueSize(u32 &size);
    HcclResult RemoteEnvelopeQueSize(u32 &size);
    HcclResult GetMemInfo(uintptr_t memPtr, MemType &memType, u64 &offset);
    HcclResult ExchangePidMesg();
    HcclResult ExchangeSignalMesg();
    HcclResult CreateIpcSignal(std::shared_ptr<LocalIpcNotify> &localNotify, u8 *notifyInfo);
    HcclResult ShmMemcpy(void *dst, uint64_t destMax, const void *src, uint64_t count);
    HcclResult SetCtxCurrent();
    HcclResult CheckShmMemRange(MemType memType, u64 offset, u64 count, u32 dataType);

    std::array<MemMsg, static_cast<u32>(MemType::MEM_TYPE_RESERVED)> memMsg_;
    std::array<MemMsg, static_cast<u32>(MemType::MEM_TYPE_RESERVED)> remoteMemMsg_;
    HcclIpAddress selfIp_;
    HcclIpAddress peerIp_;
    u32 peerPort_;
    u32 selfPort_;
    const std::string tag_;
    std::string linkTag_;
    s32 deviceLogicId_;

    struct SocketWlistInfoT wlistInfo_;
    FdHandle fdHandle_ = nullptr;
    FdHandle socketHandle_ = nullptr;
    u32 role_ = 0;

    bool isInited_;

    // 这两块是dev mem，worker侧申请，ps侧通过ipc共享内存
    DeviceMem inputShmMem_;
    DeviceMem outputShmMem_;
    DeviceMem envelopeShmQue_;

    void *localEnvelopeShmQue_ = nullptr;

    u64 remoteOutputOffsetValue_;
    u64 remoteInputOffsetValue_;
    u64 remoteEnvelopeItemOffsetValue_;

    u32 tempRemoteQueSize_ = 0;
    s32 remoteDeviceId_ = 0;
private:
    SecIpcName_t remoteOutputMemName_;
    SecIpcName_t remoteInputMemName_;
    SecIpcName_t remoteEnvelopeItemMemName_;

    std::shared_ptr<RemoteNotify> isendDoneNotify_ = nullptr;
    std::shared_ptr<RemoteNotify> imrecvDoneNotify_ = nullptr;
    std::shared_ptr<LocalIpcNotify> remoteIsendDoneNotify_ = nullptr;
    std::shared_ptr<LocalIpcNotify> remoteImrecvDoneNotify_ = nullptr;
    std::mutex queMutex_;
    static bool eschedEventInit_;
    HcclRtContext rtCtx_{nullptr};
};
}  // namespace hccl

#endif /* TRANSPORT_SHM_EVENT_PUB_H */
