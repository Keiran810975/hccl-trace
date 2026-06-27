/**
 * Copyright (c) 2025 Huawei Technologies Co., Ltd.
 * This program is free software, you can redistribute it and/or modify it under the terms and conditions of
 * CANN Open Software License Agreement Version 2.0 (the "License").
 * Please refer to the License for details. You may not use this file except in compliance with the License.
 * THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
 * INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
 * See LICENSE in the root of the software repository for the full text of the License.
 */

#include "socket.h"
#include "externalinput_pub.h"
#include "network_manager_pub.h"
#include "hccl_socket.h"
#include "adapter_hccp.h"
namespace hccl {

Socket::Socket() : tag_(""), role_(SERVER_ROLE_SOCKET), type_(SocketType::SOCKET_VNIC),
    nicDeploy_(NICDeployment::NIC_DEPLOYMENT_DEVICE), locDevPhyId_(0),
    remDevPhyId_(0), deviceIdType_(DeviceIdType::DEVICE_ID_TYPE_PHY_ID) {}

Socket::Socket(const std::string &tag, u32 role, SocketType type, NICDeployment nicDeploy, HcclIpAddress &locNicIp,
    u32 locDevPhyId, HcclIpAddress &remNicIp, u32 remDevPhyId, DeviceIdType deviceIdType, u32 serverPort)
    : tag_(tag),
      role_(role),
      type_(type),
      nicDeploy_(nicDeploy),
      locNicIp_(locNicIp),
      locDevPhyId_(locDevPhyId),
      remNicIp_(remNicIp),
      remDevPhyId_(remDevPhyId),
      deviceIdType_(deviceIdType),
      serverPort_(serverPort)
{}

Socket::~Socket() {}

HcclResult Socket::PrepareConnect()
{
    CHK_RET(GetSocketHandle());
    CHK_RET(AddSocketWhiteList());
    CHK_RET(ConnectToServer());
    return HCCL_SUCCESS;
}

HcclResult Socket::Connect()
{
    CHK_RET(GetConnection());
    return HCCL_SUCCESS;
}

HcclResult Socket::ConnectAsync(u32& status)
{
    if (fdHandle_) {
        status = static_cast<u32>(SocketStatus::HCCL_CONNECT_SUCCESS);
        return HCCL_SUCCESS;
    }
    SocketInfoT socketInfo = {nullptr};

    socketInfo.socketHandle = socketHandle_;
    socketInfo.fdHandle = nullptr;
    HcclInAddr ipAddr;
    if (role_ == SERVER_ROLE_SOCKET) {
        ipAddr = locNicIp_.GetBinaryAddress();
    } else {
        ipAddr = GetRemAddr().GetBinaryAddress();
    }
    socketInfo.remoteIp.addr = ipAddr.addr;
    socketInfo.remoteIp.addr6 = ipAddr.addr6;
    socketInfo.status = CONNECT_FAIL;
    s32 sRet = memcpy_s(socketInfo.tag, sizeof(socketInfo.tag) - 1, tag_.c_str(), tag_.size());
    CHK_PRT_RET(sRet != EOK, HCCL_ERROR("memcpy_s failed, errorno[%d].", sRet), HCCL_E_MEMORY);

    u32 tmpNum = 0;
    HcclResult ret = hrtRaNonBlockGetSockets(role_, &socketInfo, 1, &tmpNum);
    if (ret == HCCL_SUCCESS && tmpNum == 1 && socketInfo.status == CONNECT_OK && socketInfo.fdHandle != nullptr) {
        status = static_cast<u32>(SocketStatus::HCCL_CONNECT_SUCCESS);
        fdHandle_ = socketInfo.fdHandle;
        HcclInAddr tempAddr;
        tempAddr.addr = socketInfo.remoteIp.addr;
        tempAddr.addr6 = socketInfo.remoteIp.addr6;
        HcclIpAddress remoteIP(locNicIp_.GetFamily(), tempAddr);
        HCCL_RUN_INFO("[Socket][GetConnection] get socket success with remote[%s], tag[%s]",
            remoteIP.GetReadableAddress(), socketInfo.tag);
    } else if (ret == HCCL_E_AGAIN || ret == HCCL_SUCCESS) {
        status = static_cast<u32>(SocketStatus::HCCL_CONNECT_WAIT);
    } else {
        HCCL_ERROR("non block get socket failed. ret: %u", ret);
        status = static_cast<u32>(SocketStatus::HCCL_CONNECT_FAILED);
        return ret;
    }

    return HCCL_SUCCESS;
}

HcclResult Socket::ConnectQuerry(u32& status)
{
    return ConnectAsync(status);
}

HcclResult Socket::Close()
{
    if (fdHandle_ == nullptr) {
        return HCCL_SUCCESS;
    }
    HCCL_RUN_INFO("[Socket][Close] tag[%s]", tag_.c_str());
    CHK_RET(DelSocketWhiteList());
    SocketCloseInfoT closeInfo = {0};
    closeInfo.socketHandle = socketHandle_;
    closeInfo.fdHandle = fdHandle_;
    if (hrtRaSocketBatchClose(&closeInfo, 1) != HCCL_SUCCESS) {
        HCCL_ERROR("ra socket batch close failed");
    }
    fdHandle_ = nullptr;
    return HCCL_SUCCESS;
}

HcclResult Socket::GetConnection()
{
    SocketInfoT socketInfo = {nullptr};

    socketInfo.socketHandle = socketHandle_;
    socketInfo.fdHandle = nullptr;
    HcclInAddr ipAddr;
    if (role_ == SERVER_ROLE_SOCKET) {
        ipAddr = locNicIp_.GetBinaryAddress();
    } else {
        ipAddr = GetRemAddr().GetBinaryAddress();
    }
    socketInfo.remoteIp.addr = ipAddr.addr;
    socketInfo.remoteIp.addr6 = ipAddr.addr6;
    socketInfo.status = CONNECT_FAIL;
    s32 sRet = memcpy_s(socketInfo.tag, sizeof(socketInfo.tag) - 1, tag_.c_str(), tag_.size());
    CHK_PRT_RET(sRet != EOK, HCCL_ERROR("memcpy_s failed, errorno[%d].", sRet), HCCL_E_MEMORY);
    CHK_RET(hrtRaBlockGetSockets(role_, &socketInfo, 1));
    CHK_PRT_RET((socketInfo.status != CONNECT_OK) || (socketInfo.fdHandle == nullptr),
        HCCL_ERROR("[Socket][GetConnection] get socket failed. status[%d]",
            socketInfo.status), HCCL_E_TCP_TRANSFER);
    fdHandle_ = socketInfo.fdHandle;
    HCCL_RUN_INFO("[Socket][GetConnection] get socket success with remote[%s], tag[%s]",
        GetRemAddr().GetReadableAddress(), socketInfo.tag);

    return HCCL_SUCCESS;
}

HcclResult Socket::ConnectToServer()
{
    if (role_ != CLIENT_ROLE_SOCKET) {
        return HCCL_SUCCESS;
    }

    SocketConnectInfoT connInfo = {nullptr};
    connInfo.remoteIp.addr = GetRemAddr().GetBinaryAddress().addr;
    connInfo.remoteIp.addr6 = GetRemAddr().GetBinaryAddress().addr6;
    connInfo.socketHandle = socketHandle_;
    connInfo.port = GetRemPort();
    s32 sRet = memcpy_s(connInfo.tag, sizeof(connInfo.tag) - 1, tag_.c_str(), tag_.size());
    CHK_PRT_RET(sRet != EOK, HCCL_ERROR("memcpy_s failed, errorno[%d].", sRet), HCCL_E_MEMORY);
    HCCL_RUN_INFO("[Socket][ConnectToServer] link tag[%s] remote ip[%s] remote port[%u]", connInfo.tag,
        GetRemAddr().GetReadableAddress(), connInfo.port);
    CHK_RET(hrtRaSocketBatchConnect(&connInfo, 1));
    return HCCL_SUCCESS;
}

HcclResult Socket::AddSocketWhiteList()
{
    if (role_ != SERVER_ROLE_SOCKET) {
        return HCCL_SUCCESS;
    }

    SocketWlistInfoT wlistInfo = {0};
    wlistInfo.connLimit = NIC_SOCKET_CONN_LIMIT;
    s32 sRet = memcpy_s(wlistInfo.tag, sizeof(wlistInfo.tag) - 1, tag_.c_str(), tag_.size());
    CHK_PRT_RET(sRet != EOK, HCCL_ERROR("memcpy_s failed, errorno[%d].", sRet), HCCL_E_MEMORY);
    wlistInfo.remoteIp.addr = GetRemAddr().GetBinaryAddress().addr;
    wlistInfo.remoteIp.addr6 = GetRemAddr().GetBinaryAddress().addr6;
    HCCL_RUN_INFO("[Socket][AddSocketWhiteList] tag[%s]", wlistInfo.tag);
    CHK_RET(hrtRaSocketWhiteListAdd(socketHandle_, &wlistInfo, 1));
    return HCCL_SUCCESS;
}

HcclResult Socket::DelSocketWhiteList()
{
    if (role_ != SERVER_ROLE_SOCKET) {
        return HCCL_SUCCESS;
    }

    SocketWlistInfoT wlistInfo = {0};
    wlistInfo.connLimit = NIC_SOCKET_CONN_LIMIT;
    s32 sRet = memcpy_s(wlistInfo.tag, sizeof(wlistInfo.tag) - 1, tag_.c_str(), tag_.size());
    CHK_PRT_RET(sRet != EOK, HCCL_ERROR("memcpy_s failed, errorno[%d].", sRet), HCCL_E_MEMORY);
    wlistInfo.remoteIp.addr = GetRemAddr().GetBinaryAddress().addr;
    wlistInfo.remoteIp.addr6 = GetRemAddr().GetBinaryAddress().addr6;
    HCCL_INFO("[Socket][DelSocketWhiteList] tag[%s]", wlistInfo.tag);
    CHK_RET(hrtRaSocketWhiteListDel(socketHandle_, &wlistInfo, 1));
    return HCCL_SUCCESS;
}

HcclResult Socket::Send(void *data, u64 size) const
{
    HcclResult ret = hrtRaSocketBlockSend(fdHandle_, data, size);
    HCCL_DEBUG("[Send]BlockSend, send size [%u Byte], ret[%u]", size, ret);
    return ret;
}

HcclResult Socket::ISend(void *data, u64 size, u64& compSize)
{
    HcclResult ret = hrtRaSocketNonBlockSendHeart(fdHandle_, data, size, &compSize);

    HCCL_DEBUG("[ISend]NonBlockSend, except size [%u Byte], actual size [%u Byte], ret[%u]", size, compSize, ret);
    if (ret == HCCL_E_AGAIN) {
        return HCCL_SUCCESS;
    }
    return ret;
}

HcclResult Socket::IRecv(void *data, u64 size, u64& compSize)
{
    HcclResult ret = hrtRaSocketNonBlockRecvHeart(fdHandle_, data, size, &compSize);

    HCCL_DEBUG("[IRecv]NonBlockRecv, except size [%u Byte], actual size [%u Byte], ret[%u]", size, compSize, ret);
    if (ret == HCCL_E_AGAIN) {
        return HCCL_SUCCESS;
    }
    return ret;
}

HcclResult Socket::GetSocketHandle()
{
    RaResourceInfo raResourceInfo;
    s32 deviceLogicId = MAX_DEV_NUM;
    u32 devicePhyId = INVALID_UINT;
    if (static_cast<s32>(locDevPhyId_) != HOST_DEVICE_ID) {
        CHK_RET(hrtGetDevice(&deviceLogicId));
    } else {
        deviceLogicId = 0;
    }
    CHK_RET(NetworkManager::GetInstance(deviceLogicId).GetRaResourceInfo(raResourceInfo));
    if (type_ == SocketType::SOCKET_VNIC) {
        CHK_RET(hrtGetDevicePhyIdByIndex(static_cast<u32>(deviceLogicId), devicePhyId));
        locNicIp_ = HcclIpAddress(devicePhyId);
        socketHandle_ = raResourceInfo.vnicSocketHandle;
        remNicIp_ = HcclIpAddress(remDevPhyId_);
        // 获取本端vic ip
        CHK_RET(hrtRaGetSingleSocketVnicIpInfo(devicePhyId, deviceIdType_, locDevPhyId_, locNicIp_));
        // 获取远端vic ip
        CHK_RET(hrtRaGetSingleSocketVnicIpInfo(devicePhyId, deviceIdType_, remDevPhyId_, remNicIp_));
    } else {
        auto& tmpSocketMap = (nicDeploy_ == NICDeployment::NIC_DEPLOYMENT_HOST) ?
        raResourceInfo.hostNetSocketMap : raResourceInfo.nicSocketMap;
        auto itSocket = tmpSocketMap.find(locNicIp_);
        if (itSocket == tmpSocketMap.end()) {
            HCCL_ERROR("nic socket handle did not found");
            return HCCL_E_PARA;
        }
        socketHandle_ = itSocket->second.nicSocketHandle;
    }
    CHK_PTR_NULL(socketHandle_);
    return HCCL_SUCCESS;
}

HcclIpAddress Socket::GetRemAddr()
{
    return remNicIp_;
}

u32 Socket::GetRemPort() const
{
    u32 port = 0;
    if (serverPort_ == 0) {
        port = HETEROG_CCL_PORT;
    } else {
        port = serverPort_;
    }
    return port;
}

}