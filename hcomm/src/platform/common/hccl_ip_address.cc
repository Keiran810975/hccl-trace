/**
 * Copyright (c) 2025 Huawei Technologies Co., Ltd.
 * This program is free software, you can redistribute it and/or modify it under the terms and conditions of
 * CANN Open Software License Agreement Version 2.0 (the "License").
 * Please refer to the License for details. You may not use this file except in compliance with the License.
 * THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
 * INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
 * See LICENSE in the root of the software repository for the full text of the License.
 */
#include <algorithm>
#include "log.h"
#include "hccl_ip_address.h"

namespace hccl {

HcclResult HcclIpAddress::SetBianryAddress(s32 family, const union HcclInAddr &address)
{
    char buf[IP_ADDRESS_BUFFER_LEN] = {0};
    if (inet_ntop(family, &address, buf, sizeof(buf)) == nullptr) {
        if (family == AF_INET) {
            HCCL_ERROR("ip addr[0x%08x] is invalid IPv4 address.", address.addr.s_addr);
        } else {
            HCCL_ERROR("ip addr[%08x %08x %08x %08x] is invalid IPv6 address.",
                address.addr6.s6_addr32[0],  // 打印ipv6地址中的 word 0
                address.addr6.s6_addr32[1],  // 打印ipv6地址中的 word 1
                address.addr6.s6_addr32[2],  // 打印ipv6地址中的 word 2
                address.addr6.s6_addr32[3]); // 打印ipv6地址中的 word 3
        }
        return HCCL_E_PARA;
    } else {
        this->family = family;
        this->binaryAddr = address;
        this->readableIP = buf;
        this->readableAddr = this->readableIP;
        return HCCL_SUCCESS;
    }
}

HcclResult HcclIpAddress::SetReadableAddress(const std::string &address)
{
    CHK_PRT_RET(address.empty(), HCCL_ERROR("ip addr is null."), HCCL_E_PARA);

    std::size_t found = address.find("%");
    if ((found == 0) || (found == (address.length() - 1))) {
        HCCL_ERROR("addr[%s] is invalid.", address.c_str());
        return HCCL_E_PARA;
    }
    std::string ipStr = address.substr(0, found);
    int cnt = std::count(ipStr.begin(), ipStr.end(), ':');
    if (cnt >= 2) { // ipv6地址中至少有2个":"
        if (inet_pton(AF_INET6, ipStr.c_str(), &binaryAddr.addr6) <= 0) {
            HCCL_ERROR("ip addr[%s] is invalid IPv6 address.", ipStr.c_str());
            binaryAddr.addr6.s6_addr32[0] = 0; // 清空ipv6地址中的 word 0
            binaryAddr.addr6.s6_addr32[1] = 0; // 清空ipv6地址中的 word 1
            binaryAddr.addr6.s6_addr32[2] = 0; // 清空ipv6地址中的 word 2
            binaryAddr.addr6.s6_addr32[3] = 0; // 清空ipv6地址中的 word 3
            clear();
            return HCCL_E_PARA;
        }
        this->family = AF_INET6;
    } else {
        if (inet_pton(AF_INET, ipStr.c_str(), &binaryAddr.addr) <= 0) {
            HCCL_ERROR("ip addr[%s] is invalid IPv4 address.", ipStr.c_str());
            clear();
            return HCCL_E_PARA;
        }
        this->family = AF_INET;
    }
    if (found != std::string::npos) {
        this->ifname = address.substr(found + 1);
    }
    this->readableIP = ipStr;
    this->readableAddr = address;
    return HCCL_SUCCESS;
}

HcclResult HcclIpAddress::SetIfName(const std::string &name)
{
    CHK_PRT_RET(name.empty(), HCCL_ERROR("if name is null."), HCCL_E_PARA);

    std::size_t found = readableAddr.find("%");
    if (found == std::string::npos) {
        ifname = name;
        readableAddr.append("%");
        readableAddr.append(ifname);
    } else {
        HCCL_ERROR("addr[%s] ifname has existed.", readableAddr.c_str());
        return HCCL_E_PARA;
    }
    return HCCL_SUCCESS;
}
}
