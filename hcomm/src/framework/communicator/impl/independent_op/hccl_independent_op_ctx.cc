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
#include "independent_op_context_manager.h"
#include "log.h"
#include "hccl_comm_pub.h"
#include "independent_op.h"
#include <string>

using namespace hccl;

HcclResult HcclEngineCtxCreate(HcclComm comm, const char *ctxTag, CommEngine engine, uint64_t size, void **ctx)
{
    CHK_PTR_NULL(comm);
    CHK_PTR_NULL(ctxTag);
    CHK_PTR_NULL(ctx);
    CHK_PRT_RET(strlen(ctxTag) > HCCL_RES_TAG_MAX_LEN,
        HCCL_ERROR("[%s] ctxTag length exceeds maximum length, ctxTag length[%zu], max length[%d]",
            __func__,  strlen(ctxTag), HCCL_RES_TAG_MAX_LEN), HCCL_E_PARA);
    CHK_PRT_RET(size == 0, HCCL_ERROR("[%s]Invalid CtxSize, CtxSize[%u]", __func__, size), HCCL_E_PARA);
    hccl::hcclComm *hcclComm = static_cast<hccl::hcclComm *>(comm);
    auto& contextMgr = hcclComm->GetIndependentOp().GetContextManager();
    HcclResult ret = contextMgr.CreateCommEngineCtx(std::string(ctxTag), engine, size, ctx);
    if (ret != HCCL_SUCCESS) {
        HCCL_ERROR("[%s] Failed to create CommEngineCtx with ctxTag[%s], engine[%d], ctx size[%llu], ret[%d]",
           __func__, ctxTag, engine, size, ret);
        return ret;
    }

    HCCL_RUN_INFO("[%s] success, ctxTag[%s], engine[%d], size[%llu], ctx[%p], group[%s]", __func__, ctxTag, engine,
        size, *ctx, hcclComm->GetIdentifier().c_str());
    return HCCL_SUCCESS;
}

HcclResult HcclEngineCtxGet(HcclComm comm, const char *ctxTag, CommEngine engine, void **ctx, uint64_t *size)
{
    CHK_PTR_NULL(comm);
    CHK_PTR_NULL(ctxTag);
    CHK_PTR_NULL(ctx);
    CHK_PTR_NULL(size);
    CHK_PRT_RET(strlen(ctxTag) > HCCL_RES_TAG_MAX_LEN,
        HCCL_ERROR("[%s] ctxTag length exceeds maximum length, ctxTag length[%zu], max length[%d]",
            __func__, strlen(ctxTag), HCCL_RES_TAG_MAX_LEN), HCCL_E_PARA);
    hccl::hcclComm *hcclComm = static_cast<hccl::hcclComm *>(comm);
    auto& contextMgr = hcclComm->GetIndependentOp().GetContextManager();
    HcclResult ret = contextMgr.GetCommEngineCtx(std::string(ctxTag), engine, ctx, size);
    if (ret != HCCL_SUCCESS) {
        HCCL_WARNING("[%s] Failed to get CommEngineCtx with ctxTag[%s], engine[%d], ret[%d]", __func__, ctxTag, engine,
            ret);
        return ret;
    }

    HCCL_RUN_INFO("[%s] success, ctxTag[%s], engine[%d], ctx[%p], size[%llu], group[%s]", __func__, ctxTag, engine,
        *ctx, *size, hcclComm->GetIdentifier().c_str());
    return HCCL_SUCCESS;
}

HcclResult HcclEngineCtxCopy(HcclComm comm, CommEngine engine, const char *ctxTag, const void *srcCtx,
    uint64_t size, uint64_t dstCtxOffset)
{
    CHK_PTR_NULL(comm);
    CHK_PTR_NULL(ctxTag);
    CHK_PTR_NULL(srcCtx);
    CHK_PRT_RET(strlen(ctxTag) > HCCL_RES_TAG_MAX_LEN,
        HCCL_ERROR("[%s] ctxTag length exceeds maximum length, ctxTag length[%zu], max length[%d]",
            __func__,  strlen(ctxTag), HCCL_RES_TAG_MAX_LEN), HCCL_E_PARA);
    CHK_PRT_RET(size == 0, HCCL_ERROR("[%s]Invalid size, size[%llu]", __func__, size), HCCL_E_PARA);
    hccl::hcclComm *hcclComm = static_cast<hccl::hcclComm *>(comm);
    auto& contextMgr = hcclComm->GetIndependentOp().GetContextManager();
    HcclResult ret = contextMgr.CopyCommEngineCtx(std::string(ctxTag), engine, srcCtx, size, dstCtxOffset);
    if (ret != HCCL_SUCCESS) {
        HCCL_WARNING("[%s] Failed to copy CommEngineCtx with ctxTag[%s], engine[%d], size[%llu], dstCtxOffset[%llu],"
            " ret[%d]", __func__, ctxTag, engine, size, dstCtxOffset, ret);
        return ret;
    }

    HCCL_RUN_INFO("[%s] success, ctxTag[%s], engine[%d], srcCtx[%p], size[%llu], dstCtxOffset[%llu], group[%s]", 
        __func__, ctxTag, engine, srcCtx, size, dstCtxOffset, hcclComm->GetIdentifier().c_str());
    return HCCL_SUCCESS;
}

HcclResult HcommEngineCtxDestroy(HcclComm comm, const HcclMem *engineCtx)
{
    CHK_PTR_NULL(comm);
    CHK_PTR_NULL(engineCtx);
    hccl::hcclComm *hcclComm = static_cast<hccl::hcclComm *>(comm);
    auto& contextMgr = hcclComm->GetIndependentOp().GetContextManager();
    HcclResult ret = contextMgr.DestroyCommEngineCtx(engineCtx);
    if (ret != HCCL_SUCCESS) {
        HCCL_ERROR("[%s] Failed to destroy CommEngineCtx, engineCtx[type:%d, addr:%p, size:%lu], ret[%d]",
           __func__, engineCtx->type, engineCtx->addr, engineCtx->size, ret);
        return ret;
    }

    HCCL_RUN_INFO("[%s] success, engineCtx[type:%d, addr:%p, size:%lu], group[%s]", 
        __func__, engineCtx->type, engineCtx->addr, engineCtx->size, hcclComm->GetIdentifier().c_str());
    return HCCL_SUCCESS;
}
