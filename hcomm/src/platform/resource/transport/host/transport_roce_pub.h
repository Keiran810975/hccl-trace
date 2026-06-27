/**
 * Copyright (c) 2025 Huawei Technologies Co., Ltd.
 * This program is free software, you can redistribute it and/or modify it under the terms and conditions of
 * CANN Open Software License Agreement Version 2.0 (the "License").
 * Please refer to the License for details. You may not use this file except in compliance with the License.
 * THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
 * INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
 * See LICENSE in the root of the software repository for the full text of the License.
 */

#ifndef TRANSPORT_ROCE_PUB_H
#define TRANSPORT_ROCE_PUB_H

#include <functional>
#include <deque>
#include <atomic>
#include "transport_base_pub.h"
#include "workflow_pub.h"
#include "transport_heterog_roce_pub.h"

// callback实现send、recv
void TaskExecCallback(void *fnData);
namespace hccl {
constexpr s32 DEFAULT_INITIAL_VALUE = -1;
enum class OperationType {
    OP_SEND = 0,
    OP_RECV = 1,
    OP_RECV_WITH_REDUCE = 2,
    OP_WAIT_DONE = 3,
    OP_INVAILD = 4
};

using ReduceParam = struct ReduceParamDef {
    // reduce相关参数
    void *src = nullptr;
    void *dst = nullptr;
    u64 dataCount = 0;
    HcclDataType datatype;
    HcclReduceOp reduceOp;
    HcclRtStream stream = nullptr;
    HcclReduceType reduceType;
    ReduceParamDef() {}
    ReduceParamDef(void *src, void *dst, u64 dataCount, HcclDataType datatype,
        HcclReduceOp reduceOp, HcclRtStream stream, HcclReduceType reduceType)
        : src(src),
          dst(dst),
          dataCount(dataCount),
          datatype(datatype),
          reduceOp(reduceOp),
          stream(stream),
          reduceType(reduceType)
    {}
};

using SendRecvParam = struct SendRecvParamDef {
    // send、recv相关参数
    void *ptr = nullptr;
    u64 len = 0;
    s32 streamId = 0;
    void *transportRocePtr = nullptr;
    s32 queIndex = 0;   // 当前任务队列下标
    HcclRequestInfo* sendRequest = nullptr; // send task要test的request

    SendRecvParamDef() {}
    // Tx/RxWaitDone 构造函数
    SendRecvParamDef(s32 streamId, void *transportRocePtr, s32 queIndex)
        : streamId(streamId), transportRocePtr(transportRocePtr), queIndex(queIndex)
    {}
    // Tx/RxAsync 构造函数
    SendRecvParamDef(void *ptr, u64 len, s32 streamId, void *transportRocePtr)
        : ptr(ptr), len(len), streamId(streamId), transportRocePtr(transportRocePtr)
    {}
};

using RoceRankInfo = struct RankInfoDef {
    u32 localUserrank;   // 本端user rank
    u32 remoteUserrank;  // 对端user rank
    RankInfoDef() : localUserrank(INVALID_VALUE_RANKID), remoteUserrank(INVALID_VALUE_RANKID) {}
    RankInfoDef(u32 localUserrank, u32 remoteUserrank)
        : localUserrank(localUserrank), remoteUserrank(remoteUserrank) {}
};

class TransportRoce : public TransportBase, public TransportHeterogRoce {
public:
    explicit TransportRoce(const HcclDispatcher dispatcher,
        const std::unique_ptr<NotifyPool> &notifyPool,
        MachinePara &machinePara, std::chrono::milliseconds timeout,
        HcclIpAddress &selfIp, HcclIpAddress &peerIp, u32 peerPort, u32 selfPort,
        const TransportResourceInfo &transportResourceInfo, u32 proxyDevLogicId = DEFAULT_INITIAL_VALUE,
        bool isRootRank = false, bool isESPs = false);
    ~TransportRoce() override;

    HcclResult Init() override;

    HcclResult DeInit() override;

    HcclResult Deinit() override;

    HcclResult TxAsync(UserMemType dstMemType, u64 dstOffset, const void *src, u64 len,
                                Stream &stream) override;
    HcclResult TxAsync(std::vector<TxMemoryInfo>& txMems, Stream &stream) override;

    HcclResult RxAsync(UserMemType srcMemType, u64 srcOffset, void *dst, u64 len,
                                Stream &stream) override;
    HcclResult RxAsync(std::vector<RxMemoryInfo>& rxMems, Stream &stream) override;

    HcclResult TxAck(Stream &stream) override;
    HcclResult RxAck(Stream &stream) override;

    HcclResult TxDataSignal(Stream &stream) override;
    HcclResult RxDataSignal(Stream &stream) override;

    HcclResult TxWaitDone(Stream &stream) override;
    HcclResult RxWaitDone(Stream &stream) override;

    HcclResult TxPrepare(Stream &stream) override;
    HcclResult RxPrepare(Stream &stream) override;

    HcclResult TxData(UserMemType dstMemType, u64 dstOffset, const void *src, u64 len,
                                Stream &stream) override;
    HcclResult RxData(UserMemType srcMemType, u64 srcOffset, void *dst, u64 len,
                                Stream &stream) override;
    HcclResult TxDone(Stream &stream) override;
    HcclResult RxDone(Stream &stream) override;

    HcclResult TxWithReduce(UserMemType dstMemType, u64 dstOffset, const void *src, u64 len,
        const HcclDataType datatype, HcclReduceOp redOp, Stream &stream) override;
    HcclResult RxWithReduce(UserMemType recvSrcMemType, u64 recvSrcOffset, void *recvDst, u64 recvLen,
        void *reduceSrc, void *reduceDst, u64 reduceDataCount, HcclDataType reduceDatatype,
        HcclReduceOp reduceOp, Stream &stream, const u64 reduceAttr) override;
    bool IsSupportTransportWithReduce() override;

    HcclResult GetRemoteMem(UserMemType memType, void **remotePtr) override;
    HcclResult GetRemoteMemSize(UserMemType memType, u64 &size) override;

    HcclResult TxEnv(const void *ptr, const u64 len, Stream &stream) override;
    HcclResult RxEnv(Stream &stream) override;
    HcclResult WaitDone(HcclRequestInfo *request);
    HcclResult IsProcessStop();
    void Break() override;

public:
    HcclResult TaskExec(s32 streamId, s32 queIndex);

protected:
    HcclResult CreateCqAndQp() override;
    HcclResult DestroyCqAndQp() override;
private:
    // 异步send
    HcclResult SendAsync(SendRecvParam &sendParam);
    // wait 异步send done
    HcclResult WaitSendAsyncComplete(const SendRecvParam &sendParam);

    // wait 异步send done + 同步recv
    HcclResult WaitSendAsyncCompleteAndRecv(const SendRecvParam &sendParam, const SendRecvParam &recvParam);

    // 同步send
    HcclResult Send(const SendRecvParam &sendParam);
    // 同步recv
    HcclResult Recv(const SendRecvParam &recvParam);

    HcclResult RegUserMem(MemType memType);
    HcclResult GetRemoteAddr(MemType memType);
    HcclResult InitMem();
    HcclResult GetNicHandle();
    HcclResult Connect();
    HcclResult GetSocketInfo();
    HcclResult SendAndRecvExchangeData();

    HcclResult WaitCompletion(struct ibv_cq* notifyCq, struct ibv_comp_channel *channel);

    std::map<s32, std::deque<std::pair<OperationType, SendRecvParam>>> taskOrchestration_; // key:streamId
    ReduceParam recvWithReduceParam_;
    std::array<MemMsg, static_cast<u32>(MemType::MEM_TYPE_RESERVED)> memMsg_;
    std::array<MemMsg, static_cast<u32>(MemType::MEM_TYPE_RESERVED)> remoteMemMsg_;
    HcclMessageInfo *receEnvelope_;
    std::queue<HcclEnvelopeSummary> receivedEnvelopes_;
    s32 deviceLogicId_;
    bool isInited_;
    SendRecvParam gatherSendRecvParam_;
    DeviceMem sendEnvelopeMem_;
    u32 proxyDevLogicId_;
    bool isRootRank_;
    bool isESPs_;
    std::atomic<bool> isProcessStop_ = {false};

    RdmaHandle nicRdmaHandle_{nullptr};
    std::vector<std::vector<HcclSocketInfo>> socketsInfo_;
    std::vector<SocketHandle> socketFdHandles_;
};
}  // namespace hccl

#endif /* __LINK_HOST_ROCE_PUB_H__ */
