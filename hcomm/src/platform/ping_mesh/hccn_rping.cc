/**
 * Copyright (c) 2025 Huawei Technologies Co., Ltd.
 * This program is free software, you can redistribute it and/or modify it under the terms and conditions of
 * CANN Open Software License Agreement Version 2.0 (the "License").
 * Please refer to the License for details. You may not use this file except in compliance with the License.
 * THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
 * INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
 * See LICENSE in the root of the software repository for the full text of the License.
 */

#include "network/hccp_ping.h"
#include "ping_mesh.h"
#include "hccl_ip_address.h"
#include "dlra_function.h"
#include "adapter_rts_common.h"
#include "hccn_rping.h"

#ifdef __cplusplus
extern "C" {
#endif // __cplusplus

#define HCCN_RPING_MIN_TIMEOUT 1
#define HCCN_RPING_MAX_TIMEOUT 3600000
#define HCCN_RPING_DEFAULT_TIMEOUT 120000

using namespace hccl;
constexpr u32 BUFFER_SIZE_UNIT = 4096;
constexpr u32 NPU_NUM_MAX = 32768;
constexpr u32 NPU_NUM_MIN = 128;
constexpr u32 NPU_NUM_MAX_BITWIDTH = 128;
constexpr u32 LINK_TYPE_MODE_ROCE = 3;
constexpr u32 RPING_RESULT_STATE_VALID = 2;
constexpr u32 TARGET_NUM_MAX = 16;

HccnResult HccnRpingInit(uint32_t devLogicId, HccnRpingInitAttr *initAttr, HccnRpingCtx *rpingCtx)
{
    // 校验入参
    CHK_PRT_RET(initAttr == nullptr, HCCL_ERROR("[HccnRpingInit]initAttr is null."), HCCN_E_PARA);
    CHK_PRT_RET(initAttr->mode >= HCCN_RPING_MODE_RESERVED,
        HCCL_ERROR("[HccnRpingInit]LinkMode[%d] not support.", initAttr->mode), HCCN_E_PARA);
    CHK_PRT_RET(rpingCtx == nullptr, HCCL_ERROR("[HccnRpingInit]rpingCtx is null."), HCCN_E_PARA);
    // 初始化ra接口
    CHK_PRT_RET(DlRaFunction::GetInstance().DlRaFunctionInit() != HCCL_SUCCESS,
        HCCL_ERROR("[HccnRpingInit]dlrafunction failed."), HCCN_E_FAIL);
    HCCL_DEBUG("[HccnRpingInit]devLogicId:%u, mode:%d port:%u npuNum:%u bufferSize:%u sl:%u tc:%u ip:%s", devLogicId,
        initAttr->mode, initAttr->port, initAttr->npuNum, initAttr->bufferSize, initAttr->sl, initAttr->tc,
        std::string(initAttr->ipAddr).c_str());
    // 获取device id
    s32 currDevLogicId = 0;
    HcclResult ret = hrtGetDeviceRefresh(&currDevLogicId);
    CHK_PRT_RET(ret != HCCL_SUCCESS, HCCL_ERROR("[HccnRpingInit]cannot get device logic id, ret[%d].", ret), HCCN_E_FAIL);

    // 判断devLogicId与pingmesh所记录的是否一致
    if (devLogicId != static_cast<u32>(currDevLogicId)) {
        HCCL_ERROR("[HccnRpingInit]Input device logicId[%d] don't match current logicId[%d].",
            devLogicId, currDevLogicId);
        return HCCN_E_FAIL;
    }
    // 构造一个pingmesh实例, 用于存放初始化的pingmesh信息
    PingMesh *rping = new (std::nothrow) PingMesh();
    CHK_PRT_RET(rping == nullptr, HCCL_ERROR("[HccnRpingInit]rping alloc failed."), HCCN_E_MEM);
    // 利用用户输入的ip地址构造HcclIpAddress类
    HcclIpAddress ipAddr = HcclIpAddress(std::string(initAttr->ipAddr));
    // npuNum必须为2的整次幂
    u32 npuNum = (initAttr->npuNum > NPU_NUM_MIN) ? initAttr->npuNum : NPU_NUM_MIN;
    npuNum = (npuNum > NPU_NUM_MAX) ? (NPU_NUM_MAX - 1) : (npuNum - 1);
    for (u32 i = 0; i < NPU_NUM_MAX_BITWIDTH; i++) {
        npuNum |= (npuNum >> 1);
    }
    npuNum++;
    npuNum = npuNum < NPU_NUM_MIN ? NPU_NUM_MIN : npuNum;
    // bufferSize必须为4k的倍数
    u32 bufferSize = 0;
    if (initAttr->bufferSize > 0) {
        bufferSize = ((initAttr->bufferSize - 1) / BUFFER_SIZE_UNIT + 1) * BUFFER_SIZE_UNIT;
    }

    // 初始化pingmesh实例
    ret = rping->HccnRpingInit(devLogicId, LINK_TYPE_MODE_ROCE, ipAddr, initAttr->port, npuNum, bufferSize,
        initAttr->sl, initAttr->tc);
    if (ret != HCCL_SUCCESS) {
        HCCL_ERROR("[HccnRpingInit]Pingmesh init failed, ret:%d, devLogicId:%u, port:%u npuNum:%u bufferSize:%u sl:%u"
        " tc:%u ip:%s", ret, devLogicId, initAttr->port, npuNum, bufferSize, initAttr->sl, initAttr->tc,
        ipAddr.GetReadableIP());
        delete rping; // 初始化失败释放内存
        return HCCN_E_FAIL;
    }

    HCCL_RUN_INFO("[HccnRpingInit]Pingmesh init success, devLogicId:%u, mode:%d port:%u npuNum:%u bufferSize:%u sl:%u"
        " tc:%u ip:%s", devLogicId, initAttr->mode, initAttr->port, npuNum, bufferSize, initAttr->sl, initAttr->tc,
        ipAddr.GetReadableIP());
    // 记录pingmesh指针
    *rpingCtx = rping;
    return HCCN_SUCCESS;
}

HccnResult HccnRpingDeinit(HccnRpingCtx rpingCtx)
{
    // 初始化ra接口
    CHK_PRT_RET(DlRaFunction::GetInstance().DlRaFunctionInit() != HCCL_SUCCESS,
        HCCL_ERROR("[HccnRpingDeinit]dlrafunction failed."), HCCN_E_FAIL);
    // 校验指针，并将其转换为pingmesh指针
    CHK_PRT_RET(rpingCtx == nullptr, HCCL_ERROR("[HccnRpingDeinit]rpingCtx is null."), HCCN_E_PARA);
    PingMesh *rping = static_cast<PingMesh*>(rpingCtx);
    // 获取device id
    s32 devLogicId = 0;
    HcclResult ret = hrtGetDeviceRefresh(&devLogicId);
    CHK_PRT_RET(ret != HCCL_SUCCESS, HCCL_ERROR("[HccnRpingDeinit]cannot get device logic id, ret[%d].", ret), HCCN_E_FAIL);

    // 判断devLogicId与pingmesh所记录的是否一致
    if (devLogicId != rping->GetDeviceLogicId()) {
        HCCL_ERROR("[HccnRpingDeinit]curr devId[%d] don't match record logicId[%d].",
            devLogicId, rping->GetDeviceLogicId());
        return HCCN_E_PARA;
    }

    ret = rping->HccnRpingDeinit(static_cast<u32>(devLogicId));
    delete rping; // 先释放资源
    if (ret != HCCL_SUCCESS) {
        HCCL_ERROR("[HccnRpingDeinit]Device[%d] deinit fail, ret[%d]", devLogicId, ret);
        return HCCN_E_FAIL;
    }

    HCCL_RUN_INFO("[HccnRpingDeinit]Device[%d] deinit success", devLogicId);
    return HCCN_SUCCESS;
}

HccnResult HccnRpingAddTarget(HccnRpingCtx rpingCtx, uint32_t targetNum, HccnRpingTargetInfo *target)
{
    HccnRpingAddTargetConfig config;
    config.connectTimeout = HCCN_RPING_DEFAULT_TIMEOUT;
    return HccnRpingAddTargetV2(rpingCtx, targetNum, target, &config);
}

HccnResult HccnRpingAddTargetV2(HccnRpingCtx rpingCtx, uint32_t targetNum, HccnRpingTargetInfo *target, HccnRpingAddTargetConfig *config)
{
    // 校验入参
    CHK_PRT_RET(config == nullptr, HCCL_ERROR("[HccnRpingAddTargetV2]config is null."), HCCN_E_PARA);
    //超时设置判断 小于1ms,大于1h
    if (config->connectTimeout < HCCN_RPING_MIN_TIMEOUT || config->connectTimeout > HCCN_RPING_MAX_TIMEOUT) {
        HCCL_ERROR("[HCCN][HccnRpingAddTargetV2] timeout [%u ms], need to be in the range 1 to 3600000", config->connectTimeout);
        return HCCN_E_PARA;
    }
    // 校验入参
    CHK_PRT_RET(target == nullptr, HCCL_ERROR("[HccnRpingAddTarget]target is null."), HCCN_E_PARA);
    CHK_PRT_RET(targetNum > TARGET_NUM_MAX,
        HCCL_ERROR("[HccnRpingAddTarget]targetNum[%u] is more than %u!", targetNum, TARGET_NUM_MAX), HCCN_E_PARA);
    // 校验指针，并将其转换为pingmesh指针
    CHK_PRT_RET(rpingCtx == nullptr, HCCL_ERROR("[HccnRpingAddTarget]rpingCtx is null."), HCCN_E_PARA);
    HCCL_DEBUG("[HccnRpingAddTarget]targetNum:%u connectTimeout:%u", targetNum, config->connectTimeout);
    PingMesh *rping = static_cast<PingMesh*>(rpingCtx);
    // 获取device id
    s32 devLogicId = 0;
    HcclResult ret = hrtGetDeviceRefresh(&devLogicId);
    CHK_PRT_RET(ret != HCCL_SUCCESS, HCCL_ERROR("[HccnRpingAddTarget]cannot get device logic id, ret[%d].", ret), HCCN_E_FAIL);

    // 判断devLogicId与pingmesh所记录的是否一致
    if (devLogicId != rping->GetDeviceLogicId()) {
        HCCL_ERROR("[HccnRpingAddTarget]curr devId[%d] don't match record logicId[%d].",
            devLogicId, rping->GetDeviceLogicId());
        return HCCN_E_PARA;
    }
    HCCL_DEBUG("[HccnRpingAddTarget] device id is %d", devLogicId);

    // 将入参转换为内部接口可以使用的类型
    RpingInput *input = new (std::nothrow) RpingInput[targetNum];
    CHK_PRT_RET(input == nullptr, HCCL_ERROR("[HccnRpingAddTarget]memory alloc failed."), HCCN_E_MEM);
    for (uint32_t i = 0; i < targetNum; i++) {
        input[i].sip = HcclIpAddress(std::string(target[i].srcIp));
        input[i].dip = HcclIpAddress(std::string(target[i].dstIp));
        input[i].srcPort = target[i].srcPort;
        input[i].sl = target[i].sl;
        input[i].tc = target[i].tc;
        input[i].port = target[i].port;
        input[i].len = target[i].payloadLen;
        s32 sRet = memcpy_s(input[i].payload, input[i].len, target[i].payload, target[i].payloadLen);
        if (sRet != EOK) {
            HCCL_ERROR("[HccnRpingAddTarget]memcpy payload fail. errorno[%d] params:dstMaxSize[%u] dstPtr[%p] "
                         "srclen[%d] srcPayload[%p]",
                sRet, input[i].len, input[i].payload, target[0].payloadLen, target[0].payload);
            return HCCN_E_MEM;
        }
    }
    ret = rping->HccnRpingAddTarget(static_cast<u32>(devLogicId), targetNum, input, config);
    if (ret != HCCL_SUCCESS) {
        HCCL_ERROR("[HccnRpingAddTarget]Device[%d] add targetNum %u fail, ret[%d]", devLogicId, targetNum, ret);
        delete[] input;
        return HCCN_E_FAIL;
    }

    delete[] input;
    HCCL_RUN_INFO("[HccnRpingAddTarget]Device[%d] add targetNum %u success", devLogicId, targetNum);
    return HCCN_SUCCESS;
}
 
HccnResult HccnRpingRemoveTarget(HccnRpingCtx rpingCtx, uint32_t targetNum, HccnRpingTargetInfo *target)
{
    // 校验入参
    CHK_PRT_RET(target == nullptr, HCCL_ERROR("[HccnRpingRemoveTarget]target is null."), HCCN_E_PARA);
    CHK_PRT_RET(targetNum > TARGET_NUM_MAX,
        HCCL_ERROR("[HccnRpingRemoveTarget]targetNum[%u] is more than %u!", targetNum, TARGET_NUM_MAX), HCCN_E_PARA);
    // 校验指针，并将其转换为pingmesh指针
    CHK_PRT_RET(rpingCtx == nullptr, HCCL_ERROR("[HccnRpingRemoveTarget]rpingCtx is null."), HCCN_E_PARA);
    HCCL_DEBUG("[HccnRpingRemoveTarget]targetNum:%u", targetNum);
    PingMesh *rping = static_cast<PingMesh*>(rpingCtx);
    // 获取device id
    s32 devLogicId = 0;
    HcclResult ret = hrtGetDeviceRefresh(&devLogicId);
    CHK_PRT_RET(ret != HCCL_SUCCESS, HCCL_ERROR("[HccnRpingRemoveTarget]cannot get device logic id, ret[%d].", ret), HCCN_E_FAIL);

    // 判断devLogicId与pingmesh所记录的是否一致
    if (devLogicId != rping->GetDeviceLogicId()) {
        HCCL_ERROR("[HccnRpingRemoveTarget]curr devId[%d] don't match record logicId[%d].",
            devLogicId, rping->GetDeviceLogicId());
        return HCCN_E_PARA;
    }
    HCCL_DEBUG("[HccnRpingRemoveTarget] device id is %d", devLogicId);

    // 将入参转换为内部接口可以使用的类型
    RpingInput *input = new (std::nothrow) RpingInput[targetNum];
    CHK_PRT_RET(input == nullptr, HCCL_ERROR("[HccnRpingRemoveTarget]memory alloc failed."), HCCN_E_FAIL);
    for (uint32_t i = 0; i < targetNum; i++) {
        input[i].sip = HcclIpAddress(std::string(target[i].srcIp));
        input[i].dip = HcclIpAddress(std::string(target[i].dstIp));
        input[i].sl = target[i].sl;
        input[i].tc = target[i].tc;
    }

    ret = rping->HccnRpingRemoveTarget(static_cast<u32>(devLogicId), targetNum, input);
    if (ret != HCCL_SUCCESS) {
        HCCL_ERROR("[HccnRpingRemoveTarget]Device[%d] remove targetNum %u fail, ret[%d]", devLogicId, targetNum, ret);
        delete[] input;
        return HCCN_E_FAIL;
    }

    delete[] input;
    HCCL_RUN_INFO("[HccnRpingRemoveTarget]Device[%d] remove targetNum %u success", devLogicId, targetNum);
    return HCCN_SUCCESS;
}

inline void ConvertTargetState(uint32_t targetNum, int *state, HccnRpingAddTargetState *targetState)
{
    for (uint32_t i = 0; i < targetNum; i++) {
        switch(static_cast<RpingLinkState>(state[i])) {
            case RpingLinkState::CONNECTED :
                targetState[i] = HCCN_RPING_ADDTARGET_STATE_DONE;
                break;
            case RpingLinkState::CONNECTING :
                targetState[i] = HCCN_RPING_ADDTARGET_STATE_DOING;
                break;
            case RpingLinkState::DISCONNECTED :
                targetState[i] = HCCN_RPING_ADDTARGET_STATE_FAIL;
                break;
            case RpingLinkState::TIMEOUT :
                targetState[i] = HCCN_RPING_ADDTARGET_STATE_TIMEOUT;
                break;
            default:
                targetState[i] = HCCN_RPING_ADDTARGET_STATE_RESERVED;
                break;
        }
    }
}
 
HccnResult HccnRpingGetTarget(HccnRpingCtx rpingCtx, uint32_t targetNum, HccnRpingTargetInfo *target,
                              HccnRpingAddTargetState *targetState)
{
    // 校验入参
    CHK_PRT_RET(target == nullptr, HCCL_ERROR("[HccnRpingGetTarget]target is null."), HCCN_E_PARA);
    CHK_PRT_RET(targetState == nullptr, HCCL_ERROR("[HccnRpingGetTarget]targetState is null."), HCCN_E_PARA);
    CHK_PRT_RET(targetNum > TARGET_NUM_MAX,
        HCCL_ERROR("[HccnRpingGetTarget]targetNum[%u] is more than %u!", targetNum, TARGET_NUM_MAX), HCCN_E_PARA);
    // 校验指针，并将其转换为pingmesh指针
    CHK_PRT_RET(rpingCtx == nullptr, HCCL_ERROR("[HccnRpingGetTarget]rpingCtx is null."), HCCN_E_PARA);
    HCCL_DEBUG("[HccnRpingGetTarget]targetNum:%u", targetNum);
    PingMesh *rping = static_cast<PingMesh*>(rpingCtx);
    // 获取device id
    s32 devLogicId = 0;
    HcclResult ret = hrtGetDeviceRefresh(&devLogicId);
    CHK_PRT_RET(ret != HCCL_SUCCESS, HCCL_ERROR("[HccnRpingGetTarget]cannot get device logic id, ret[%d].", ret), HCCN_E_FAIL);

    // 判断devLogicId与pingmesh所记录的是否一致
    if (devLogicId != rping->GetDeviceLogicId()) {
        HCCL_ERROR("[HccnRpingGetTarget]curr devId[%d] don't match record logicId[%d].",
            devLogicId, rping->GetDeviceLogicId());
        return HCCN_E_PARA;
    }
    HCCL_DEBUG("[HccnRpingGetTarget] device id is %d", devLogicId);

    // 将入参转换为内部接口可以使用的类型
    RpingInput *input = new (std::nothrow) RpingInput[targetNum];
    CHK_PRT_RET(input == nullptr, HCCL_ERROR("[HccnRpingGetTarget]memory alloc failed."), HCCN_E_MEM);
    for (uint32_t i = 0; i < targetNum; i++) {
        input[i].sip = HcclIpAddress(std::string(target[i].srcIp));
        input[i].dip = HcclIpAddress(std::string(target[i].dstIp));
    }

    int *state = new (std::nothrow) int[targetNum];
    CHK_PRT_RET(state == nullptr, HCCL_ERROR("[HccnRpingGetTarget]memory alloc failed."), HCCN_E_MEM);
    ret = rping->HccnRpingGetTarget(static_cast<u32>(devLogicId), targetNum, input, state);
    if (ret != HCCL_SUCCESS) {
        HCCL_ERROR("[HccnRpingGetTarget]Device[%d] get targetNum %u fail, ret[%d]", devLogicId, targetNum, ret);
        delete[] input;
        delete[] state;
        return HCCN_E_FAIL;
    }

    ConvertTargetState(targetNum, state, targetState);
    delete[] input;
    delete[] state;
    HCCL_RUN_INFO("[HccnRpingGetTarget]Device[%d] get targetNum %u success", devLogicId, targetNum);
    return HCCN_SUCCESS;
}

HccnResult HccnRpingBatchPingStart(HccnRpingCtx rpingCtx, uint32_t pktNum, uint32_t interval, uint32_t timeout)
{
    // 校验指针，并将其转换为pingmesh指针
    CHK_PRT_RET(rpingCtx == nullptr, HCCL_ERROR("[HccnRpingBatchPingStart]rpingCtx is null.", rpingCtx), HCCN_E_PARA);
    HCCL_DEBUG("[HccnRpingBatchPingStart]pktNum:%u, interval:%u, timeout:%u", pktNum, interval, timeout);
    PingMesh *rping = static_cast<PingMesh*>(rpingCtx);
    // 获取device id
    s32 devLogicId = 0;
    HcclResult ret = hrtGetDeviceRefresh(&devLogicId);
    CHK_PRT_RET(ret != HCCL_SUCCESS, HCCL_ERROR("[HccnRpingBatchPingStart]cannot get device logic id, ret[%d].", ret), HCCN_E_PARA);

    // 判断devLogicId与pingmesh所记录的是否一致
    if (devLogicId != rping->GetDeviceLogicId()) {
        HCCL_ERROR("[HccnRpingBatchPingStart]curr devId[%d] don't match record logicId[%d].",
            devLogicId, rping->GetDeviceLogicId());
        return HCCN_E_PARA;
    }

    ret = rping->HccnRpingBatchPingStart(static_cast<u32>(devLogicId), pktNum, interval, timeout);
    CHK_PRT_RET(ret != HCCL_SUCCESS,
        HCCL_ERROR("[HccnRpingBatchPingStart]task start failed, devLogicId[%d], ret[%d], pktNum:%u, interval:%u, timeout:%u.",
        devLogicId, ret, pktNum, interval, timeout), HCCN_E_FAIL);

    HCCL_RUN_INFO("[HccnRpingBatchPingStart]task start success, devLogicId:%d, pktNum:%u, interval:%u, timeout:%u",
        devLogicId, pktNum, interval, timeout);
    return HCCN_SUCCESS;
}

HccnResult HccnRpingBatchPingStop(HccnRpingCtx rpingCtx)
{
    // 校验指针，并将其转换为pingmesh指针
    CHK_PRT_RET(rpingCtx == nullptr, HCCL_ERROR("[HccnRpingBatchPingStop]rpingCtx is null.", rpingCtx), HCCN_E_PARA);
    PingMesh *rping = static_cast<PingMesh*>(rpingCtx);
    // 获取device id
    s32 devLogicId = 0;
    HcclResult ret = hrtGetDeviceRefresh(&devLogicId);
    CHK_PRT_RET(ret != HCCL_SUCCESS, HCCL_ERROR("[HccnRpingBatchPingStop]cannot get device logic id, ret[%d].", ret), HCCN_E_PARA);

    // 判断devLogicId与pingmesh所记录的是否一致
    if (devLogicId != rping->GetDeviceLogicId()) {
        HCCL_ERROR("[HccnRpingBatchPingStop]curr devId[%d] don't match record logicId[%d].",
            devLogicId, rping->GetDeviceLogicId());
        return HCCN_E_PARA;
    }

    ret = rping->HccnRpingBatchPingStop(static_cast<u32>(devLogicId));
    CHK_PRT_RET(ret != HCCL_SUCCESS,
        HCCL_ERROR("[HccnRpingBatchPingStop]task stop failed, devLogicId[%d] ret[%d].", devLogicId, ret), HCCN_E_FAIL);

    HCCL_RUN_INFO("[HccnRpingBatchPingStop]task stop success, devLogicId[%d]", devLogicId);
    return HCCN_SUCCESS;
}

inline void ConvertResultState(uint32_t state, HccnRpingResultState &resultState)
{
    if (state == RPING_RESULT_STATE_VALID) {
        resultState = HCCN_RPING_RESULT_STATE_VALID;
    } else {
        resultState = HCCN_RPING_RESULT_STATE_INVALID;
    }
}

HccnResult HccnRpingGetResult(HccnRpingCtx rpingCtx, uint32_t targetNum, HccnRpingTargetInfo *target,
                              HccnRpingResultInfo *result)
{
    // 校验入参
    CHK_PRT_RET(target == nullptr, HCCL_ERROR("[HccnRpingGetResult]target is null."), HCCN_E_PARA);
    CHK_PRT_RET(result == nullptr, HCCL_ERROR("[HccnRpingGetResult]result is null."), HCCN_E_PARA);
    CHK_PRT_RET(targetNum > TARGET_NUM_MAX,
        HCCL_ERROR("[HccnRpingGetResult]targetNum[%u] is more than %u!", targetNum, TARGET_NUM_MAX), HCCN_E_PARA);
    // 校验指针，并将其转换为pingmesh指针
    CHK_PRT_RET(rpingCtx == nullptr, HCCL_ERROR("[HccnRpingGetResult]rpingCtx is null."), HCCN_E_PARA);
    HCCL_DEBUG("[HccnRpingGetResult]targetNum:%u", targetNum);
    PingMesh *rping = static_cast<PingMesh*>(rpingCtx);
    // 获取device id
    s32 devLogicId = 0;
    HcclResult ret = hrtGetDeviceRefresh(&devLogicId);
    CHK_PRT_RET(ret != HCCL_SUCCESS, HCCL_ERROR("[HccnRpingGetResult]cannot get device logic id, ret[%d].", ret), HCCN_E_FAIL);

    // 判断devLogicId与pingmesh所记录的是否一致
    if (devLogicId != rping->GetDeviceLogicId()) {
        HCCL_ERROR("[HccnRpingGetResult]curr devId[%d] not match record[%d].", devLogicId, rping->GetDeviceLogicId());
        return HCCN_E_PARA;
    }

    // 将入参转换为内部接口可以使用的类型
    RpingInput *input = new (std::nothrow) RpingInput[targetNum];
    CHK_PRT_RET(input == nullptr, HCCL_ERROR("[HccnRpingGetResult]memory alloc failed."), HCCN_E_MEM);
    RpingOutput *output = new (std::nothrow) RpingOutput[targetNum];
    if (output == nullptr) {
        delete[] input;
        HCCL_ERROR("[HccnRpingGetResult]memory alloc failed.");
        return HCCN_E_MEM;
    }
    for (uint32_t i = 0; i < targetNum; i++) {
        input[i].sip = HcclIpAddress(std::string(target[i].srcIp));
        input[i].dip = HcclIpAddress(std::string(target[i].dstIp));
    }

    ret = rping->HccnRpingGetResult(static_cast<u32>(devLogicId), targetNum, input, output);
    if (ret == HCCL_E_AGAIN) {
        delete[] input;
        delete[] output;
        return HCCN_E_AGAIN;
    }
    if (ret != HCCL_SUCCESS) {
        HCCL_ERROR("[HccnRpingGetResult]Device[%d] get result fail, targetNum[%u] ret[%d]", devLogicId, targetNum, ret);
        delete[] input;
        delete[] output;
        return HCCN_E_FAIL;
    }

    for (uint32_t i = 0; i < targetNum; i++) {
        ConvertResultState(output[i].state, result[i].state);
        if (output[i].state != PingResultState::PING_RESULT_STATE_VALID) {
            HCCL_INFO("[HccnRpingGetResult]Target[%d]'s state is not valid, state[%d].", i, output[i].state);
            continue;
        }
        result[i].txPkt = output[i].txPkt;
        result[i].rxPkt = output[i].rxPkt;
        result[i].minRTT = output[i].minRTT;
        result[i].maxRTT = output[i].maxRTT;
        result[i].avgRTT = output[i].avgRTT;
    }

    delete[] input;
    delete[] output;
    HCCL_RUN_INFO("[HccnRpingGetResult]Device[%d] get result success, targetNum[%u]", devLogicId, targetNum);
    return HCCN_SUCCESS;
}

HccnResult HccnRpingGetPayload(HccnRpingCtx rpingCtx, void **payload, uint32_t *payloadLen)
{
    // 校验入参
    CHK_PRT_RET(payload == nullptr, HCCL_ERROR("[HccnRpingGetPayload]payload is null."), HCCN_E_PARA);
    CHK_PRT_RET(payloadLen == nullptr, HCCL_ERROR("[HccnRpingGetPayload]payloadLen is null."), HCCN_E_PARA);
    // 校验指针，并将其转换为pingmesh指针
    CHK_PRT_RET(rpingCtx == nullptr, HCCL_ERROR("[HccnRpingGetPayload]rpingCtx is null."), HCCN_E_PARA);
    PingMesh *rping = static_cast<PingMesh*>(rpingCtx);
    // 获取device id
    s32 devLogicId = 0;
    HcclResult ret = hrtGetDeviceRefresh(&devLogicId);
    CHK_PRT_RET(ret != HCCL_SUCCESS, HCCL_ERROR("[HccnRpingGetPayload]cannot get device logic id, ret[%d].", ret), HCCN_E_FAIL);

    // 判断devLogicId与pingmesh所记录的是否一致
    if (devLogicId != rping->GetDeviceLogicId()) {
        HCCL_ERROR("[HccnRpingGetResult]curr devId[%d] not match record[%d].", devLogicId, rping->GetDeviceLogicId());
        return HCCN_E_PARA;
    }

    ret = rping->HccnRpingGetPayload(static_cast<u32>(devLogicId), payload, payloadLen);
    CHK_PRT_RET(ret != HCCL_SUCCESS, HCCL_ERROR("[HccnRpingGetPayload]Device[%d] get payload fail, ret[%d]", devLogicId, ret),
        HCCN_E_FAIL);

    HCCL_RUN_INFO("[HccnRpingGetPayload]Device[%d] get payload success, payloadLen[%u]", devLogicId, *payloadLen);
    return HCCN_SUCCESS;
}

#ifdef __cplusplus
}
#endif // __cplusplus