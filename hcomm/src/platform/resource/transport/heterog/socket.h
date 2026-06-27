/**
 * Copyright (c) 2025 Huawei Technologies Co., Ltd.
 * This program is free software, you can redistribute it and/or modify it under the terms and conditions of
 * CANN Open Software License Agreement Version 2.0 (the "License").
 * Please refer to the License for details. You may not use this file except in compliance with the License.
 * THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
 * INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
 * See LICENSE in the root of the software repository for the full text of the License.
 */

#ifndef HCCL_SOCKET_H
#define HCCL_SOCKET_H

#include "hccl/hccl_types.h"
#include "log.h"
#include "network/hccp_common.h"
#include "adapter_pub.h"

namespace hccl {

enum class SocketType {
    SOCKET_VNIC,
    SOCKET_NIC,
};

enum class SocketStatus {
    HCCL_CONNECT_SUCCESS = 0,
    HCCL_CONNECT_WAIT = 1,
    HCCL_CONNECT_FAILED = 2,
    HCCL_CONNECT_RESERVED
};

class Socket {
public:
    Socket();
    Socket(const std::string &tag, u32 role, SocketType type, NICDeployment nicDeploy, HcclIpAddress &locNicIp,
        u32 locDevPhyId, HcclIpAddress &remNicIp, u32 remDevPhyId, DeviceIdType deviceIdType, u32 serverPort = 0);
    ~Socket();
    HcclResult PrepareConnect();
    HcclResult Connect();
    HcclResult ConnectAsync(u32& status);
    HcclResult ConnectQuerry(u32& status);
    HcclResult Close();
    HcclResult Send(void *data, u64 size) const;
    HcclResult ISend(void *data, u64 size, u64& compSize);
    HcclResult IRecv(void *data, u64 size, u64& compSize);

private:
    HcclResult GetConnection();
    HcclResult ConnectToServer();
    HcclResult AddSocketWhiteList();
    HcclResult DelSocketWhiteList();
    HcclResult GetSocketHandle();
    HcclIpAddress GetRemAddr();
    u32 GetRemPort() const;

    std::string tag_;
    u32 role_;
    SocketType type_;
    NICDeployment nicDeploy_;
    HcclIpAddress locNicIp_;
    u32 locDevPhyId_;
    HcclIpAddress remNicIp_;
    u32 remDevPhyId_;
    DeviceIdType deviceIdType_;
    FdHandle fdHandle_ = nullptr;
    SocketHandle socketHandle_ = nullptr;
    u32 serverPort_;
};

} // namespace hccl
#endif // HCCL_SOCKET_H