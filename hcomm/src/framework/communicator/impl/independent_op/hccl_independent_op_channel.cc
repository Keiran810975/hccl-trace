/**
 * Copyright (c) 2025 Huawei Technologies Co., Ltd.
 * This program is free software, you can redistribute it and/or modify it under the terms and conditions of
 * CANN Open Software License Agreement Version 2.0 (the "License").
 * Please refer to the License for details. You may not use this file except in compliance with the License.
 * THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
 * INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
 * See LICENSE in the root of the software repository for the full text of the License.
 */

#include "hccl_api.h"
#include "channel_manager.h"
#include "log.h"
#include "hccl_comm_pub.h"
#include "independent_op.h"

using namespace hccl;

const uint32_t HCCL_CHANNEL_VERSION_ONE = 1;
static HcclResult HandleHcclResPackReq(const HcclChannelDesc &channelDesc, HcclChannelDesc &channelDescFinal)
{
    if (channelDesc.header.size < channelDescFinal.header.size) {
        // 需要前向兼容HcclChannelDesc，末尾部分字段不支持处理
    } else if (channelDesc.header.size > channelDescFinal.header.size) {
        // 需要后向向兼容HcclChannelDesc，末尾部分字段会被忽略
    }

    if (channelDesc.header.magicWord != channelDescFinal.header.magicWord) {
        HCCL_ERROR("[%s]channelDescFinal.header.magicWord[%u] not equal to channelDesc.header.magicWord[%u]",
            __func__, channelDescFinal.header.magicWord, channelDesc.header.magicWord);
        return HCCL_E_PARA;
    }

    uint32_t copySize = (channelDescFinal.header.size < channelDesc.header.size ?
        channelDescFinal.header.size : channelDesc.header.size) - sizeof(CommAbiHeader);
    CHK_SAFETY_FUNC_RET(memcpy_s((uint8_t *)&channelDescFinal + sizeof(CommAbiHeader), copySize,
        (uint8_t *)&channelDesc + sizeof(CommAbiHeader), copySize));

    if (channelDesc.header.version >= HCCL_CHANNEL_VERSION_ONE) {
        channelDescFinal.remoteRank = channelDesc.remoteRank;
        channelDescFinal.channelProtocol   = channelDesc.channelProtocol;
        channelDescFinal.localEndpoint  = channelDesc.localEndpoint;
        channelDescFinal.remoteEndpoint  = channelDesc.remoteEndpoint;
        channelDescFinal.notifyNum  = channelDesc.notifyNum;
        channelDescFinal.memHandles  = channelDesc.memHandles;
        channelDescFinal.memHandleNum  = channelDesc.memHandleNum;

        // 根据协议类型拷贝union中的相应成员
        switch (channelDesc.channelProtocol) {
            case COMM_PROTOCOL_HCCS:
            case COMM_PROTOCOL_PCIE:
            case COMM_PROTOCOL_SIO:
                break;
            case COMM_PROTOCOL_ROCE:
                channelDescFinal.roceAttr.queueNum = channelDesc.roceAttr.queueNum;
                channelDescFinal.roceAttr.retryCnt = channelDesc.roceAttr.retryCnt;
                channelDescFinal.roceAttr.retryInterval = channelDesc.roceAttr.retryInterval;
                channelDescFinal.roceAttr.tc = channelDesc.roceAttr.tc;
                channelDescFinal.roceAttr.sl = channelDesc.roceAttr.sl;
                break;
            default:
                HCCL_ERROR("[%s]Unsupported protocol[%d] found in HcclChannelDesc.", __func__, channelDesc.channelProtocol);
                return HCCL_E_PARA;
        }
    }

    if (channelDesc.header.version > HCCL_CHANNEL_VERSION) {
        // 传入的版本高于当前版本，警告不支持的配置项将被忽略
        HCCL_WARNING("The version of provided [%u] is higher than the current version[%u], "
            "unsupported configuration will be ignored.",
            channelDesc.header.version, HCCL_CHANNEL_VERSION);
    } else if (channelDesc.header.version < HCCL_CHANNEL_VERSION) {
        // 传入的版本低于当前版本，警告高版本支持的配置项将被忽略
        HCCL_WARNING("The version of provided [%u] is lower than the current version[%u], "
            "configurations supported by later versions will be ignored.",
            channelDesc.header.version, HCCL_CHANNEL_VERSION);
    }

    // 如果扩展到version=2后
    // 1) 在底层为新的结构体和版本（version为2）上，会正常执行下面的判断处理逻辑；
    // 2) 在底层为旧的结构体和版本（version为1）上，下面的逻辑没有，version的2 > 1的部分会被忽略掉；
    if (channelDesc.header.version >= 2) {
    }

    return HCCL_SUCCESS;
}

constexpr uint32_t CHANNEL_NUM_MAX = 1024 * 1024;  // channel的默认限制最大为1024 * 1024
HcclResult HcclChannelAcquire(HcclComm comm, CommEngine engine, const HcclChannelDesc *channelDescList,
    uint32_t listNum, ChannelHandle *channelList)
{
    // 入参校验
    CHK_PTR_NULL(comm);
    CHK_PTR_NULL(channelDescList);
    CHK_PTR_NULL(channelList);
    CHK_PRT_RET((listNum == 0 || listNum > CHANNEL_NUM_MAX), HCCL_ERROR("[%s]Invalid listNum, listNum[%u], max channel num[%u]",
        __func__, listNum, CHANNEL_NUM_MAX), HCCL_E_PARA);

    HcclResult ret = HCCL_SUCCESS;
    hccl::hcclComm *hcclComm = static_cast<hccl::hcclComm *>(comm);
    std::vector<HcclChannelDesc> channelDescFinals;
    for (uint32_t idx = 0; idx < listNum; idx++) {
        HcclChannelDesc channelDescFinal;
        HcclChannelDescInit(&channelDescFinal, 1);
        ret = HandleHcclResPackReq(channelDescList[idx], channelDescFinal);
        if (ret != HCCL_SUCCESS) {
            HCCL_ERROR("[%s] Failed check channelDesc, channelDesc idx[%u], group[%s], engine[%d], "
                "channelNum[%llu], ret[%d]", __func__, idx, hcclComm->GetIdentifier().c_str(),
                engine, listNum, ret);
            return ret;
        }
        channelDescFinals.push_back(channelDescFinal);
    }
    auto& channelMgr = hcclComm->GetIndependentOp().GetChannelManager();
    ret = channelMgr.ChannelCommCreate(hcclComm->GetIdentifier(), engine,
        channelDescFinals.data(), listNum, channelList);
    if (ret != HCCL_SUCCESS) {
        HCCL_ERROR("[%s] Failed to acquire channel, group[%s], engine[%d], channelNum[%llu], ret[%d]",
           __func__, hcclComm->GetIdentifier().c_str(), engine, listNum, ret);
        return ret;
    }

    HCCL_RUN_INFO("[%s] acquire channel success, group[%s], engine[%d], channelNum[%llu], ret[%d]", 
        __func__, hcclComm->GetIdentifier().c_str(), engine, listNum, ret);
    return HCCL_SUCCESS;
}

HcclResult HcclChannelGetNotifyNum(HcclComm comm, ChannelHandle channel, uint32_t *notifyNum)
{
    CHK_PTR_NULL(notifyNum);
    hccl::hcclComm *hcclComm = static_cast<hccl::hcclComm *>(comm);
    auto& channelMgr = hcclComm->GetIndependentOp().GetChannelManager();
    HcclResult ret = channelMgr.ChannelCommGetNotifyNum(channel, notifyNum);
    if (ret != HCCL_SUCCESS) {
        HCCL_ERROR("[%s] Failed to get channel notifyNum, group[%s], channel[%llu], ret[%d]",
           __func__, hcclComm->GetIdentifier().c_str(), channel, ret);
        return ret;
    }

    HCCL_RUN_INFO("[%s] get channel notifyNum success, group[%s], channel[%llu], notifyNum[%lu], ret[%d]", 
        __func__, hcclComm->GetIdentifier().c_str(), channel, *notifyNum, ret);
    return HCCL_SUCCESS;
}

HcclResult CommChannelDestroy(HcclComm comm, ChannelHandle *channelList, uint32_t channelNum)
{
    CHK_PTR_NULL(comm);
    CHK_PTR_NULL(channelList);
    CHK_PRT_RET(channelNum == 0, HCCL_ERROR("[%s]Invalid channelNum, channelNum[%u]",
        __func__, channelNum), HCCL_E_PARA);
    hccl::hcclComm *hcclComm = static_cast<hccl::hcclComm *>(comm);
    auto& channelMgr = hcclComm->GetIndependentOp().GetChannelManager();
    HcclResult ret = channelMgr.ChannelCommDestroy(channelList, channelNum);
    if (ret != HCCL_SUCCESS) {
        HCCL_ERROR("[%s] Failed to destroy channel, group[%s], channelList[%p], channelNum[%lu], ret[%d]",
           __func__, hcclComm->GetIdentifier().c_str(), channelList, channelNum, ret);
        return ret;
    }

    HCCL_RUN_INFO("[%s] destroy channel success, group[%s], channelList[%p], channelNum[%lu], ret[%d]", 
        __func__, hcclComm->GetIdentifier().c_str(), channelList, channelNum, ret);
    return HCCL_SUCCESS;
}

HcclResult HcclChannelGetHcclBuffer(HcclComm comm, ChannelHandle channel, void **buffer, uint64_t *size)
{
    CHK_PTR_NULL(comm);
    CHK_PTR_NULL(buffer);
    CHK_PTR_NULL(size);
    hccl::hcclComm *hcclComm = static_cast<hccl::hcclComm *>(comm);
    auto& channelMgr = hcclComm->GetIndependentOp().GetChannelManager();
    CommBuffer commBuffer;
    HcclResult ret = channelMgr.ChannelCommGetHcclBuffer(channel, &commBuffer);
    if (ret != HCCL_SUCCESS) {
        HCCL_ERROR("[%s] Failed to get channel hccl buffer, group[%s], channel[%llu], ret[%d]",
           __func__, hcclComm->GetIdentifier().c_str(), channel, ret);
        return ret;
    }
    *buffer = commBuffer.addr;
    *size = commBuffer.size;

    HCCL_RUN_INFO("[%s] get channel hccl buffer success, group[%s], channel[%llu], " 
        "buffer[type:%d, addr:%p, size:%llu], ret[%d]", __func__, hcclComm->GetIdentifier().c_str(), 
        channel, commBuffer.type, commBuffer.addr, commBuffer.size, ret);
    return HCCL_SUCCESS;
}

HcclResult HcclChannelGetRemoteMem(HcclComm comm, ChannelHandle channel, HcclMem **remoteMem, char **memTag, uint32_t *memNum)
{
    // memTag 目前未使用
    CHK_PTR_NULL(comm);
    CHK_PTR_NULL(remoteMem);
    CHK_PTR_NULL(memNum);
    hccl::hcclComm *hcclComm = static_cast<hccl::hcclComm *>(comm);
    auto& channelMgr = hcclComm->GetIndependentOp().GetChannelManager();
    HcclResult ret = channelMgr.ChannelCommGetRemoteMem(channel, remoteMem, memNum);
    if (ret != HCCL_SUCCESS) {
        HCCL_ERROR("[%s] Failed to get channel remote mem, group[%s], channel[%p], ret[%d]",
           __func__, hcclComm->GetIdentifier().c_str(), channel, ret);
        return ret;
    }

    HCCL_RUN_INFO("[%s] get channel remote mem success, group[%s], channel[%p], memNum[%lu], ret[%d]", 
        __func__, hcclComm->GetIdentifier().c_str(), channel, *memNum, ret);
    return HCCL_SUCCESS;
}