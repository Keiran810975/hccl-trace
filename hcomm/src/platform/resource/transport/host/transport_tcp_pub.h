/**
 * Copyright (c) 2025 Huawei Technologies Co., Ltd.
 * This program is free software, you can redistribute it and/or modify it under the terms and conditions of
 * CANN Open Software License Agreement Version 2.0 (the "License").
 * Please refer to the License for details. You may not use this file except in compliance with the License.
 * THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
 * INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
 * See LICENSE in the root of the software repository for the full text of the License.
 */

#ifndef LINK_HOST_TCP_PUB_H
#define LINK_HOST_TCP_PUB_H

#include "transport_net_pub.h"
#include "workflow_pub.h"

namespace hccl {
class TransportTcp : public TransportNet {
public:
    explicit TransportTcp(DispatcherPub *dispatcher,
                        const std::unique_ptr<NotifyPool> &notifyPool,
                        MachinePara &machinePara,
                        std::chrono::milliseconds timeout, NICDeployment nicDeploy =
                        NICDeployment::NIC_DEPLOYMENT_RESERVED);
    ~TransportTcp() override;

    HcclResult Init() override;

    HcclResult DeInit() override;

    HcclResult TxAsync(UserMemType dstMemType, u64 dstOffset, const void *src, u64 len,
                                  Stream &stream) override;
    HcclResult TxAsync(std::vector<TxMemoryInfo>& txMems, Stream &stream) override;

    HcclResult RxAsync(UserMemType srcMemType, u64 srcOffset, void *dst, u64 len,
                                  Stream &stream) override;
    HcclResult RxAsync(std::vector<RxMemoryInfo>& rxMems, Stream &stream) override;

    HcclResult TxAck(Stream &stream) override;
    HcclResult RxAck(Stream &stream) override;

    HcclResult TxPrepare(Stream &stream) override;
    HcclResult RxPrepare(Stream &stream) override;

    HcclResult TxData(UserMemType dstMemType, u64 dstOffset, const void *src, u64 len,
                                Stream &stream) override;
    HcclResult RxData(UserMemType srcMemType, u64 srcOffset, void *dst, u64 len,
                                Stream &stream) override;

    HcclResult TxDone(Stream &stream) override;
    HcclResult RxDone(Stream &stream) override;

    HcclResult TxDataSignal(Stream &stream) override;
    HcclResult RxDataSignal(Stream &stream) override;

    HcclResult TxWaitDone(Stream &stream) override;

private:
    HcclResult GetNicHandle(u32 curPortId);

    // host侧发送接收缓冲区内存
    HostMem hostSendBuffer_;
    HostMem hostRecvBuffer_;

    // dev侧发送接收缓冲区内存
    DeviceMem deviceSendBuffer_;
    DeviceMem deviceRecvBuffer_;

    // 区分当前网卡部署位置
    NICDeployment nicDeploy_;
};
}  // namespace hccl

#endif /* LINK_HOST_TCP_PUB_H */
