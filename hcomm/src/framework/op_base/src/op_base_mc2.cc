/**
 * Copyright (c) 2025 Huawei Technologies Co., Ltd.
 * This program is free software, you can redistribute it and/or modify it under the terms and conditions of
 * CANN Open Software License Agreement Version 2.0 (the "License").
 * Please refer to the License for details. You may not use this file except in compliance with the License.
 * THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
 * INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
 * See LICENSE in the root of the software repository for the full text of the License.
 */

#include "op_base.h"
#include <algorithm>
#include <future>
#include <map>
#include <string>
#include <hccl/hccl_types.h>
#include "aicpu_operator_pub.h"
#include "coll_alg_param.h"
#include "hccl/base.h"
#include "kernel_tiling/kernel_tiling.h"
#include "param_check_pub.h"
#include "hccl_tiling_msg.h"

using namespace std;
using namespace hccl;

namespace {
const u32 MC2_TILING_VERSION = 2U;
const u32 ENABLE_AICPU_COMM_ENGINE = 0U;
}
HcclResult HcclGetInitTilingList(const void *mc2Tiling, const void *p[], uint32_t &cnt)
{
    const u32 *versionPtr = static_cast<const u32 *>(mc2Tiling);
    const u32 version = *(versionPtr++);
    CHK_PRT_RET(version < MC2_TILING_VERSION, HCCL_ERROR("Invalid tiling version %u.", version), HCCL_E_PARA);

    cnt = *(versionPtr++);
    CHK_PRT_RET(cnt > MAX_HCOM_NUM, HCCL_ERROR("Invalid hcom tiling number %u.", cnt), HCCL_E_PARA);

    u64 serverCfgAddr = reinterpret_cast<u64>(versionPtr) + sizeof(Mc2ServerCfg);
    for (uint32_t i = 0U; i < cnt; ++i) {
        if (version == MC2_TILING_VERSION) {
            p[i] = reinterpret_cast<const void *>(serverCfgAddr + i * sizeof(Mc2HcommCfg));
        } else {
            p[i] = reinterpret_cast<const void *>(reinterpret_cast<const u8 *>(mc2Tiling) + versionPtr[i]);
        }
    }
    return HCCL_SUCCESS;
}

HcclResult HcclMc2ComResourceByTiling(HcclComm comm, void *mc2Tiling, rtStream_t &aicpuStream)
{
    const void *tilingList[MAX_HCOM_NUM];
    uint32_t tilingNum;
    CHK_RET(HcclGetInitTilingList(mc2Tiling, tilingList, tilingNum));

    hccl::hcclComm *hcclComm = static_cast<hccl::hcclComm *>(comm);
    string commIdentifier = hcclComm->GetIdentifier();
    bool isAicpuCommEngine = false;
    for (uint32_t i = 0U; i < tilingNum; ++i) {
        const HcclApi::Mc2CcTilingInner *tiling = static_cast<const HcclApi::Mc2CcTilingInner *>(tilingList[i]);
        if (tiling == nullptr || string(tiling->groupName) != commIdentifier) {
            continue;
        }

        OpParam opParam;
        opParam.tag = string(tiling->groupName) + to_string(tiling->opType) + string("_mc2");
        opParam.stream = Stream(aicpuStream);
        opParam.reduceType = static_cast<HcclReduceOp>(tiling->reduceType);
        opParam.syncMode = SyncMode::DEFAULT_TIMEWAITSYNCMODE;
        opParam.aicpuUnfoldMode = true;
        opParam.opType = static_cast<HcclCMDType>(tiling->opType);
        if (opParam.opType == HcclCMDType::HCCL_CMD_BATCH_WRITE) {
            opParam.BatchWriteDataDes.queueNum = LOCAL_STREAM_MAX_NUM;
            HCCL_INFO("Requiring %u queues for batch-write.", opParam.BatchWriteDataDes.queueNum);
        }
        HCCL_INFO("Comm resource will be created for group %s. isAicpuCommEngine[%d] commEngine[%u]", 
            commIdentifier.c_str(), isAicpuCommEngine, tiling->commEngine);
        CHK_RET(hcclComm->AllocComResourceByTiling(tiling->algConfig, reinterpret_cast<void *>(&opParam)));
        // commEngine为0代表使能AICPU引擎
        if (!isAicpuCommEngine && tiling->commEngine == ENABLE_AICPU_COMM_ENGINE) {
            isAicpuCommEngine = true;
        }
    }

    if (isAicpuCommEngine) {
        CHK_RET(hcclComm->SetAicpuCommEngine(isAicpuCommEngine));
    }

    return HCCL_SUCCESS;
}

#ifdef __cplusplus
extern "C" {
#endif
HcclResult HcclAllocComResourceByTiling(HcclComm comm, void* stream, void* Mc2Tiling, void** commContext)
{
    // 校验
    CHK_PTR_NULL(comm);
    CHK_PTR_NULL(stream);
    CHK_PTR_NULL(Mc2Tiling);
    CHK_PTR_NULL(commContext);

    HcclUs startut = TIME_NOW();
    uint64_t streamMode = 0; //streamMode未使用，固定传0
    // 兼容老版本
    uint32_t *pVersion = reinterpret_cast<uint32_t *>(Mc2Tiling);
    DevType devType;
    CHK_RET(hrtGetDeviceType(devType));
    HCCL_INFO("[%s]version ptr[%p] val[%u] devType[%u]", __func__, pVersion, *pVersion, devType);
    hccl::hcclComm* hcclComm = static_cast<hccl::hcclComm *>(comm);
    string commIdentifier = hcclComm->GetIdentifier();
    HCCL_INFO("[%s]commIdentifier[%s]", __func__, commIdentifier.c_str());
    string cclBufferName = hcclComm->GetCCLbufferName();
    bool isShareComm = cclBufferName.empty() ? false : true;
    if (isShareComm) {
        HCCL_RUN_WARNING("MC2 using share CCLbuffer[%s], potential conflict with coll communicator", cclBufferName.c_str());
    }

    if (*pVersion < MC2_TILING_VERSION || devType != DevType::DEV_TYPE_910_93) {
        return HcclCreateComResourceByComm(comm, streamMode, true, commContext, true, Mc2Tiling);
    }

    // 根据streamMode创建aicpuStream
    rtStream_t aicpuStream{};
    CHK_RET(hcclComm->Mc2AiCpuStreamAllocAndGet(streamMode, aicpuStream));

    char stackLogBuffer[LOG_TMPBUF_SIZE];

    u32 localRank = INVALID_VALUE_RANKID;
    CHK_RET(hcclComm->GetUserRank(localRank));

    /* 接口交互信息日志 */
    if (GetExternalInputHcclEnableEntryLog()) {
        s32 ret = snprintf_s(stackLogBuffer, LOG_TMPBUF_SIZE, LOG_TMPBUF_SIZE - 1U, "commIdentifier[%s], version[%u]",
                             commIdentifier.c_str(), *pVersion);
        CHK_PRT_CONT(ret == -1, HCCL_WARNING("Failed to build log info, commIdentifier[%s].", commIdentifier.c_str()));

        std::string logInfo = "MC2 create resource by tiling: localRank[" + std::to_string(localRank)
                              + "]" + std::string(stackLogBuffer);
        CHK_RET(hcclComm->SaveTraceInfo(logInfo));
    }

    CHK_RET(HcclMc2ComResourceByTiling(comm, Mc2Tiling, aicpuStream));

    // 获取 commContext
    hcclComm->GetCommResource(*commContext);

    if (GetExternalInputHcclEnableEntryLog()) {
        HcclUs endut = TIME_NOW();
        /* 关键状态记录 */
        std::string endInfo = "MC2 create resource take time ["
                              + std::to_string(DURATION_US(endut - startut).count()) + "]us, localRank["
                              + std::to_string(localRank) + "] " + std::string(stackLogBuffer);
        CHK_RET(hcclComm->SaveTraceInfo(endInfo));
    }

    return HCCL_SUCCESS;
}
#ifdef __cplusplus
}
#endif
