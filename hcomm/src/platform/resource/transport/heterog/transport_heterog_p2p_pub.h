/**
 * Copyright (c) 2025 Huawei Technologies Co., Ltd.
 * This program is free software, you can redistribute it and/or modify it under the terms and conditions of
 * CANN Open Software License Agreement Version 2.0 (the "License").
 * Please refer to the License for details. You may not use this file except in compliance with the License.
 * THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
 * INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
 * See LICENSE in the root of the software repository for the full text of the License.
 */

#ifndef TRANSPORT_HETEROG_P2P_PUB_H
#define TRANSPORT_HETEROG_P2P_PUB_H

#include <sstream>

#include "transport_base_pub.h"
#include "socket.h"
#include "stream_pub.h"
#include "private_types.h"

namespace hccl {
using HcclIpcMemInfo = struct HcclIpcMemInfoDef {
    SecIpcName_t name;
    u64 size;
    u64 offset;
    void *ptr = nullptr;
    HcclIpcMemInfoDef() {};
};

using ExchangeMsg = struct ExchangeMsgDef {
    u32 type;
    u8 sendReadyNotify[NOTIFY_INFO_LENGTH];
    u8 sendDoneNotify[NOTIFY_INFO_LENGTH];
    HcclIpcMemInfo ipcMem[2];
    ExchangeMsgDef() {};
};

enum TransportEndPointType {
    TRANSPORT_ENDPOINT_TYPE_CPU,
    TRANSPORT_ENDPOINT_TYPE_NPU
};

enum TransportState {
    TRANSPORT_CONNECT_STATE_INIT,
    TRANSPORT_CONNECT_STATE_SOCKET_CONNECT,
    TRANSPORT_CONNECT_STATE_EXCHANGE_PID,
    TRANSPORT_CONNECT_STATE_EXCHANGE_TRANSPORT_INFO,
    TRANSPORT_CONNECT_STATE_DONE
};

class TransportHeterogP2P : public TransportBase {
public:
    explicit TransportHeterogP2P(DispatcherPub *dispatcher,
                      const std::unique_ptr<NotifyPool> &notifyPool,
                      MachinePara &machinePara,
                      std::chrono::milliseconds timeout);
    ~TransportHeterogP2P() override;

    HcclResult Init() override;
    HcclResult DeInit() override;

    HcclResult TxDataSignal(Stream &stream) override;
    HcclResult RxDataSignal(Stream &stream) override;

    HcclResult TxAck(Stream &stream) override;
    HcclResult RxAck(Stream &stream) override;

    HcclResult TxAsync(UserMemType dstMemType, u64 dstOffset, const void *src, u64 len,
                                  Stream &stream) override;
    HcclResult TxAsync(std::vector<TxMemoryInfo>& txMems, Stream &stream) override;

    HcclResult RxAsync(UserMemType srcMemType, u64 srcOffset, void *dst, u64 len,
                                  Stream &stream) override;
    HcclResult RxAsync(std::vector<RxMemoryInfo>& rxMems, Stream &stream) override;

    HcclResult GetRemoteMem(UserMemType memType, void **remotePtr, u64 &remoteMemSize);

    HcclResult ConnectAsync(u32& status) override;
    HcclResult ConnectQuerry(u32& status) override;

    HcclResult TxPrepare(Stream &stream) override;
    HcclResult RxPrepare(Stream &stream) override;

    HcclResult TxData(UserMemType dstMemType, u64 dstOffset, const void *src, u64 len,
                                  Stream &stream) override;
    HcclResult RxData(UserMemType srcMemType, u64 srcOffset, void *dst, u64 len,
                                  Stream &stream) override;

    HcclResult TxDone(Stream &stream) override;
    HcclResult RxDone(Stream &stream) override;

    void Break() override;
protected:
private:
    HcclResult ConnectInit();
    HcclResult ConnectSocket();
    HcclResult GetSocket();
    HcclResult ExchangePid();
    HcclResult RecvPid();
    HcclResult ExchangeTransportInfo();
    HcclResult SendIpcInfo();
    HcclResult RecvIpcInfo();
    HcclResult SetIpcMem(DeviceMem &memory, HcclIpcMemInfo& ipcMemInfo);
    HcclResult CreateIpcSignal(std::shared_ptr<LocalIpcNotify> &localNotify, u8 *notifyInfo);
    HcclResult WaitPeerMemConfig(void **memPtr, const u8 *memName, uint64_t size, u64 offset);
    HcclResult SetDeivceByPhyId();

    void *remoteInputPtr_;
    u64 remoteInputMemSize_ = 0;
    void *remoteOutputPtr_;
    u64 remoteOutputMemSize_ = 0;

    std::unique_ptr<Socket> socket_;
    ExchangeMsg remoteMsg_;

    std::shared_ptr<LocalIpcNotify> sendReadyNotify_ = nullptr;
    std::shared_ptr<LocalIpcNotify> sendDoneNotify_ = nullptr;

    std::shared_ptr<RemoteNotify> remoteSendReadyNotify_ = nullptr;
    std::shared_ptr<RemoteNotify> remoteSendDoneNotify_ = nullptr;

    TransportEndPointType endType_;
    TransportState connectState_;
    u64 socketRecvSize_;
    std::vector<HcclIpcMemInfo> setIpcMemInfos_;
    std::vector<std::string> openIpcNames_;
    bool isInit_ = false;
};
}  // namespace hccl

#endif /* TRANSPORT_P2P_PUB_H */
