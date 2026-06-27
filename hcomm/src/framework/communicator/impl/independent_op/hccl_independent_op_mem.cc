/**
 * Copyright (c) 2025 Huawei Technologies Co., Ltd.
 * This program is free software, you can redistribute it and/or modify it under the terms and conditions of
 * CANN Open Software License Agreement Version 2.0 (the "License").
 * Please refer to the License for details. You may not use this file except in compliance with the License.
 * THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
 * INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
 * See LICENSE in the root of the software repository for the full text of the License.
 */

#include <atomic>
#include <unordered_map>
#include <mutex>
#include <memory>
#include <vector>
#include <string>
#include "hccl_api.h"
#include "hccl_mem.h"
#include "stream_pub.h"
#include "hccl_communicator.h"
#include "hccl_comm_pub.h"

HcclResult HcclCommRegMem(HcclComm comm, const char *memTag, const HcclMem *mem,
                          HcclRegMemAttr attr, void **memHandle)
{
    CHK_PRT_RET(comm == nullptr,  HCCL_ERROR("[HcclCommRegMem]comm is null"), HCCL_E_PARA);
    CHK_PRT_RET(memTag == nullptr, HCCL_ERROR("[HcclCommRegMem]memTag is null"), HCCL_E_PARA);
    CHK_PRT_RET(strlen(memTag) == 0 || strlen(memTag) > HCCL_RES_TAG_MAX_LEN,
        HCCL_ERROR("[HcclCommRegMem]memTag length is %u", strlen(memTag)), HCCL_E_PARA);
    CHK_PRT_RET(mem == nullptr,   HCCL_ERROR("[HcclCommRegMem]mem is null"), HCCL_E_PARA);
    CHK_PRT_RET(memHandle == nullptr, HCCL_ERROR("[HcclCommRegMem]memHandle is null"), HCCL_E_PARA);
    CHK_PRT_RET((mem->type != HCCL_MEM_TYPE_DEVICE) && (mem->type != HCCL_MEM_TYPE_HOST),
        HCCL_ERROR("[HcclCommRegMem]memoryType[%d] must be device or host", mem->type), HCCL_E_PARA);
    CHK_PRT_RET(mem->addr == nullptr, HCCL_ERROR("[HcclCommRegMem]addr is null"), HCCL_E_PARA);
    CHK_PRT_RET(mem->size == 0, HCCL_ERROR("[HcclCommRegMem]size[%lld] invalid",
        static_cast<long long>(mem->size)), HCCL_E_PARA);

    auto *hcclComm = static_cast<hccl::hcclComm *>(comm);
    std::string commId = hcclComm->GetIdentifier();
    HCCL_RUN_INFO("Entry-%s: comm[%s], memTag[%s], addr[%p], size[%lld], type[%d]",
                  __func__, commId.c_str(), memTag, mem->addr, static_cast<long long>(mem->size), mem->type);
    // 通信域实例：按算子绑定（幂等）
    auto& commMemMgr = hcclComm->GetIndependentOp().GetCommMemMgr();
    HcclResult ret = commMemMgr.CommRegMem(std::string(memTag), *mem, attr, memHandle);
    CHK_PRT_RET(ret != HCCL_SUCCESS,
        HCCL_ERROR("[HcclCommRegMem]Bind failed. memTag[%s], ret[%d]", memTag, ret), ret);
    HCCL_INFO("[HcclCommRegMem] success: raw handle[%p]", *memHandle);
    return HCCL_SUCCESS;
}

HcclResult HcclCommDeregMem(HcclComm comm, const char *memTag, const void* memHandle)
{
    CHK_PRT_RET(comm == nullptr, HCCL_ERROR("[HcclCommDeregMem]comm is null"), HCCL_E_PARA);
    CHK_PRT_RET(memHandle == nullptr, HCCL_ERROR("[HcclCommDeregMem]memHandle is null"), HCCL_E_PARA);
    CHK_PRT_RET(memTag == nullptr, HCCL_ERROR("[HcclCommDeregMem]memTag is null"), HCCL_E_PARA);
    CHK_PRT_RET(strlen(memTag) == 0, HCCL_ERROR("[HcclCommDeregMem]memTag length is 0"), HCCL_E_PARA);

    auto *hcclComm = static_cast<hccl::hcclComm *>(comm);
    std::string commId = hcclComm->GetIdentifier();
    HCCL_RUN_INFO("Entry-%s: comm[%s], handle[%p]", __func__, commId.c_str(), memHandle);

    // 解绑某算子下的该句柄
    auto& commMemMgr = hcclComm->GetIndependentOp().GetCommMemMgr();
    HcclResult ret = commMemMgr.CommUnregMem(std::string(memTag), memHandle);
    CHK_PRT_RET(ret == HCCL_E_NOT_FOUND,
        HCCL_WARNING("[HcclCommDeregMem]handle not bound in this domain. raw[%p]", memHandle), HCCL_SUCCESS);
    CHK_PRT_RET(ret != HCCL_SUCCESS,
        HCCL_ERROR("[HcclCommDeregMem] unBind failed. handle[%p], ret[%d]", memHandle, ret), ret);
    HCCL_INFO("[HcclCommDeregMem]success: raw handle[%p]", memHandle);
    return HCCL_SUCCESS;
}

HcclResult HcclGetHcclBuffer(HcclComm comm, void ** buffer, uint64_t *size)
{
    CHK_PRT_RET(buffer == nullptr, HCCL_ERROR("[HcclGetHcclBuffer]buffer is null"), HCCL_E_PARA);
    CHK_PRT_RET(comm == nullptr, HCCL_ERROR("[HcclGetHcclBuffer]comm is null"), HCCL_E_PARA);
    auto* hcclComm = static_cast<hccl::hcclComm*>(comm);
    std::string commId = hcclComm->GetIdentifier();
    HCCL_RUN_INFO("Entry-%s:comm[%s]", __func__, commId.c_str());
    auto& commMemMgr = hcclComm->GetIndependentOp().GetCommMemMgr();
    CommBuffer commBuffer;
    HcclResult ret = commMemMgr.GetHcclBuffer(&commBuffer);
    if (ret != HCCL_SUCCESS) {
        HCCL_ERROR("[HcclGetHcclBuffer] Failed to get local cclBuffer ret[%d]", ret);
        return ret;
    }
    *buffer = commBuffer.addr;
    *size = commBuffer.size;
    return HCCL_SUCCESS;
}