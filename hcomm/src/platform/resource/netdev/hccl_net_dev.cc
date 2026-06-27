/**
 * Copyright (c) 2025 Huawei Technologies Co., Ltd.
 * This program is free software, you can redistribute it and/or modify it under the terms and conditions of
 * CANN Open Software License Agreement Version 2.0 (the "License").
 * Please refer to the License for details. You may not use this file except in compliance with the License.
 * THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
 * INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
 * See LICENSE in the root of the software repository for the full text of the License.
 */
#include "log.h"
#include "hccl_net_dev_v1.h"
#include "adapter_rts_common.h"
#include "hccl_net_dev.h"

using namespace std;

HcclResult HcclNetDevOpen(const HcclNetDevInfos *info, HcclNetDev *netDev)
{
    CHK_PTR_NULL(netDev);
    CHK_PTR_NULL(info);

    return HcclNetDevOpenV1(info, netDev);
}

HcclResult HcclNetDevClose(HcclNetDev netDev)
{
    // 先销毁设备
    CHK_PTR_NULL(netDev);

    return HcclNetDevCloseV1(netDev);
}

HcclResult HcclNetDevGetAddr(HcclNetDev netDev, HcclAddress *addr)
{
    CHK_PTR_NULL(netDev);
    CHK_PTR_NULL(addr);

    return HcclNetDevGetAddrV1(netDev, addr);
}

HcclResult HcclNetDevGetBusAddr(HcclDeviceId dstDevId, HcclAddress *busAddr)
{
    CHK_PTR_NULL(busAddr);

    return HcclNetDevGetBusAddrV1(dstDevId, busAddr);
}

HcclResult HcclNetDevGetNicAddr(int32_t devicePhyId, HcclAddress **addr, uint32_t *addrNum)
{
    CHK_PTR_NULL(addrNum);
    CHK_PTR_NULL(addr);

    return HcclNetDevGetNicAddrV1(devicePhyId, addr, addrNum);
}