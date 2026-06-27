/**
 * Copyright (c) 2025 Huawei Technologies Co., Ltd.
 * This program is free software, you can redistribute it and/or modify it under the terms and conditions of
 * CANN Open Software License Agreement Version 2.0 (the "License").
 * Please refer to the License for details. You may not use this file except in compliance with the License.
 * THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
 * INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
 * See LICENSE in the root of the software repository for the full text of the License.
 */

#include "transport_tcp.h"
#include <arpa/inet.h>
#include <securec.h>

#include "externalinput_pub.h"
#include "network/hccp.h"
#include "network/hccp_common.h"
#include "network_manager_pub.h"

namespace hccl {
TransportTcp::TransportTcp(DispatcherPub *dispatcher,
    const std::unique_ptr<NotifyPool> &notifyPool,
    MachinePara &machinePara, std::chrono::milliseconds timeout, NICDeployment nicDeploy)
    : TransportNet(dispatcher, notifyPool, machinePara, timeout), nicDeploy_(nicDeploy)
{
}

TransportTcp::~TransportTcp()
{
    HCCL_DEBUG("~TransportTcp Enter!");

    (void)DeInit();

    HCCL_DEBUG("~TransportTcp Success!");
}

// 申请内存做缓冲区，取socket链接
HcclResult TransportTcp::Init()
{
    CHK_PRT_RET(nicDeploy_ == NICDeployment::NIC_DEPLOYMENT_RESERVED,
        HCCL_ERROR("[TransportTcp][Init]transport tcp nicDeploy invalid"), HCCL_E_PARA);

    /* 获取socket */
    // 上层初始化时保证 machinePara_.sockets 非空
    if (machinePara_.sockets.size() == 0) {
        HCCL_ERROR("machinePara sockets is empty.");
        return HCCL_E_INTERNAL;
    }
    defaultSocket_ = machinePara_.sockets[0];
    CHK_PTR_NULL(defaultSocket_);
    CHK_RET(CheckExchangeData());

    /* 自定义信息交换校验 */
    // 发送自定义信息信息
    CHK_RET(this->SendExchangeData());
    HCCL_DEBUG("Send exchange data success");

    // 接收自定义信息并进行校验
    CHK_RET(this->RecvAndCheckExchangeData());
    HCCL_DEBUG("Recv and check exchange data success");

    /* 申请socket收发缓冲区 */
    if (nicDeploy_ == NICDeployment::NIC_DEPLOYMENT_HOST) {
        hostSendBuffer_ = HostMem::alloc(TCP_BUFFER_SIZE);
        CHK_PRT_RET(!hostSendBuffer_, HCCL_ERROR("[TransportTcp][Init]malloc send buffer failed."), HCCL_E_MEMORY);
        hostRecvBuffer_ = HostMem::alloc(TCP_BUFFER_SIZE);
        CHK_PRT_RET(!hostRecvBuffer_, HCCL_ERROR("[TransportTcp][Init]malloc recv buffer failed."), HCCL_E_MEMORY);
    } else {
        CHK_RET(DeviceMem::alloc(deviceSendBuffer_, TCP_BUFFER_SIZE));
        CHK_RET(DeviceMem::alloc(deviceRecvBuffer_, TCP_BUFFER_SIZE));
    }

    HCCL_INFO(
        "Init succ,machineType=[%d], serverId=[%s], localDeviceId=[%d], remoteDeviceId=[%d], \
        localRank=[%u], localUserRank=[%u], remoteRank=[%u], remoteUserRank=[%u], \
        deviceType=[%d], inputMem=%p, outputMem=%p, custom exchange data size [%llu]",
        machinePara_.machineType, machinePara_.serverId.c_str(), machinePara_.localDeviceId,
        machinePara_.remoteDeviceId, machinePara_.localUserrank, machinePara_.localWorldRank,
        machinePara_.remoteUserrank, machinePara_.remoteWorldRank, machinePara_.deviceType,
        machinePara_.inputMem.ptr(), machinePara_.outputMem.ptr(), machinePara_.exchangeInfo.size());

    HCCL_USER_CRITICAL_LOG("create hccl transport:communicator[%s], local rank[%u], remote rank[%u], "\
        "transporttype[%s]", machinePara_.collectiveId.c_str(), machinePara_.localUserrank, 
        machinePara_.remoteUserrank, GetLinkTypeEnumStr(GetLinkType()).c_str());
        
    return HCCL_SUCCESS;
}

// 释放内存，socket链接赋无效值
HcclResult TransportTcp::DeInit()
{
    dispatcher_->WaitHostNicTcpSendThreadComplete();
    defaultSocket_ = nullptr;
    return HCCL_SUCCESS;
}

// tcp不关心
HcclResult TransportTcp::TxDataSignal(Stream &stream)
{
    return HCCL_SUCCESS;
}

// tcp不关心
HcclResult TransportTcp::RxDataSignal(Stream &stream)
{
    return HCCL_SUCCESS;
}

// 发送数据，使用得到的socket去发数据，实际去下callback task
HcclResult TransportTcp::TxAsync(UserMemType dstMemType, u64 dstOffset, const void *src, u64 len, Stream &stream)
{
    CHK_SMART_PTR_NULL(stream);
    static_cast<void>(dstMemType);
    static_cast<void>(dstOffset);
    if (!(len > 0)) {
        HCCL_WARNING("[TransportTcp][TxAsync]len[%llu] should be greater than 0.", len);
        return HCCL_SUCCESS;
    }
    CHK_PTR_NULL(src);

    const void* sendBufferPtr = nicDeploy_ == NICDeployment::NIC_DEPLOYMENT_HOST ? hostSendBuffer_.ptr() :
        deviceSendBuffer_.ptr();
    u64 sendBufferSize = nicDeploy_ == NICDeployment::NIC_DEPLOYMENT_HOST ? hostSendBuffer_.size() :
        deviceSendBuffer_.size();
    HcclResult ret = HCCL_SUCCESS;
    ret = dispatcher_->HostNicTcpSend(defaultSocket_->GetFdHandle(),
        sendBufferPtr, sendBufferSize, src, len, stream, nicDeploy_);
    CHK_PRT_RET(ret != HCCL_SUCCESS,
        HCCL_ERROR("[TransportTcp][TxAsync]errNo[0x%016llx]" \
            "tcp send failed. src[%p], len[%llu]", HCCL_ERROR_CODE(ret), src, len), ret);

    return HCCL_SUCCESS;
}

HcclResult TransportTcp::TxAsync(std::vector<TxMemoryInfo>& txMems, Stream &stream)
{
    CHK_SMART_PTR_NULL(stream);
    for (auto& mem : txMems) {
        if (mem.len == 0) {
            continue;
        }
        CHK_PTR_NULL(mem.src);
        CHK_RET(TxAsync(mem.dstMemType, mem.dstOffset, mem.src, mem.len, stream));
    }
    return HCCL_SUCCESS;
}

// 接收数据，使用得到的socket去接收数据，实际去下callback task
HcclResult TransportTcp::RxAsync(UserMemType srcMemType, u64 srcOffset, void *dst, u64 len, Stream &stream)
{
    CHK_SMART_PTR_NULL(stream);
    if (!(len > 0)) {
        HCCL_WARNING("[TransportTcp][RxAsync]len[%llu] should be greater than 0.", len);
        return HCCL_SUCCESS;
    }
    CHK_PTR_NULL(dst);

    const void* recvBufferPtr = nicDeploy_ == NICDeployment::NIC_DEPLOYMENT_HOST ? hostRecvBuffer_.ptr() :
        deviceRecvBuffer_.ptr();
    u64 recvBufferSize = nicDeploy_ == NICDeployment::NIC_DEPLOYMENT_HOST ? hostRecvBuffer_.size() :
        deviceRecvBuffer_.size();
    HcclResult ret = HCCL_SUCCESS;
    ret = dispatcher_->HostNicTcpRecv(defaultSocket_->GetFdHandle(),
        recvBufferPtr, recvBufferSize, dst, len, stream, nicDeploy_);
    CHK_PRT_RET(ret != HCCL_SUCCESS,
        HCCL_ERROR("[TransportTcp][RxAsync]errNo[0x%016llx]" \
            "tcp recv failed. dst[%p], len[%llu]", HCCL_ERROR_CODE(ret), dst, len), ret);

    return HCCL_SUCCESS;
}

HcclResult TransportTcp::TxData(UserMemType dstMemType, u64 dstOffset, const void *src, u64 len, Stream &stream)
{
    CHK_RET(TxAsync(dstMemType, dstOffset, src, len, stream));
    return HCCL_SUCCESS;
}

HcclResult TransportTcp::RxData(UserMemType srcMemType, u64 srcOffset, void *dst, u64 len, Stream &stream)
{
    CHK_RET(RxAsync(srcMemType, srcOffset, dst, len, stream));
    return HCCL_SUCCESS;
}

HcclResult TransportTcp::RxAsync(std::vector<RxMemoryInfo>& rxMems, Stream &stream)
{
    CHK_SMART_PTR_NULL(stream);
    for (auto& mem : rxMems) {
        if (mem.len == 0) {
            continue;
        }
        CHK_PTR_NULL(mem.dst);
        CHK_RET(RxAsync(mem.srcMemType, mem.srcOffset, mem.dst, mem.len, stream));
    }
    return HCCL_SUCCESS;
}

// tcp不关心
HcclResult TransportTcp::TxAck(Stream &stream)
{
    return HCCL_SUCCESS;
}

// tcp不关心
HcclResult TransportTcp::RxAck(Stream &stream)
{
    return HCCL_SUCCESS;
}

// tcp不关心
HcclResult TransportTcp::TxPrepare(Stream &stream)
{
    return HCCL_SUCCESS;
}

// tcp不关心
HcclResult TransportTcp::RxPrepare(Stream &stream)
{
    return HCCL_SUCCESS;
}

// tcp不关心
HcclResult TransportTcp::TxDone(Stream &stream)
{
    return HCCL_SUCCESS;
}

// tcp不关心
HcclResult TransportTcp::RxDone(Stream &stream)
{
    return HCCL_SUCCESS;
}

HcclResult TransportTcp::TxWaitDone(Stream &stream)
{
    HcclResult ret = dispatcher_->HostNicTcpWaitSendCompletion(stream);
    CHK_PRT_RET(ret != HCCL_SUCCESS, HCCL_ERROR("[TransportTcp][TxWaitDone]errNo[0x%016llx]" \
        "TxWaitDone callback task failed", HCCL_ERROR_CODE(ret)), ret);
    return HCCL_SUCCESS;
}
}  // namespace hccl
