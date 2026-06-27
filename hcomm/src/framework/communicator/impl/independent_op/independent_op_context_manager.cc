/**
 * Copyright (c) 2025 Huawei Technologies Co., Ltd.
 * This program is free software, you can redistribute it and/or modify it under the terms and conditions of
 * CANN Open Software License Agreement Version 2.0 (the "License").
 * Please refer to the License for details. You may not use this file except in compliance with the License.
 * THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
 * INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
 * See LICENSE in the root of the software repository for the full text of the License.
 */
 
#include "independent_op_context_manager.h"
#include "hccl_comm_pub.h"
#include "log.h"
#include "adapter_rts_common.h"

namespace hccl {
ContextManager::ContextManager()
{
}

ContextManager::~ContextManager()
{
}

HcclResult ContextManager::CreateCommEngineCtx(const std::string &tag, CommEngine engine, uint64_t size, void **ctx)
{
    std::lock_guard<std::mutex> lock(mutex_); 
    // 阻止重复创建
    if (contextMap_.find(tag) != contextMap_.end()) {
        auto engineCtxMap = contextMap_[tag];
        CHK_PRT_RET(engineCtxMap.find(engine) != engineCtxMap.end(),
            HCCL_ERROR("[%s] already exist a context with same key, tag[%s], engine[%d]",
            __func__, tag.c_str(), engine), HCCL_E_PARA);
    }

    void* ctxData = nullptr;
    // 区分设备类型
    HcclMemType type;
    if (engine == COMM_ENGINE_CPU || engine == COMM_ENGINE_CPU_TS) {
        type = HCCL_MEM_TYPE_HOST;
        ctxData = malloc(size);
        CHK_PTR_NULL(ctxData);
        CHK_SAFETY_FUNC_RET(memset_s(ctxData, size, 0, size));
    } else if (engine == COMM_ENGINE_AICPU || engine == COMM_ENGINE_AICPU_TS) {
        type = HCCL_MEM_TYPE_DEVICE;
        CHK_RET(hrtMalloc(&ctxData, size));
    } else {
        HCCL_ERROR("[%s] not support engine type[%d]", __func__, engine);
        return HCCL_E_PARA;
    }

    contextMap_[tag][engine] = {type, ctxData, size};
    tagMap_[contextMap_[tag][engine]] = tag;
    engineMap_[contextMap_[tag][engine]] = engine;
    *ctx = contextMap_[tag][engine].addr;
    HCCL_INFO("[%s]create context success, tag[%s], engine[%d]", __func__, tag.c_str(), engine);

    return HCCL_SUCCESS;
}

HcclResult ContextManager::GetCommEngineCtx(const std::string &tag, CommEngine engine, void **ctx, uint64_t *size)
{
    std::lock_guard<std::mutex> lock(mutex_); 
    // Ctx未创建返回
    if (contextMap_.find(tag) == contextMap_.end()) {
        HCCL_INFO("[%s] not exist a context with tag[%s]", __func__, tag.c_str());
        return HCCL_E_PARA;
    } else {
        auto engineCtxMap = contextMap_[tag];
        if (engineCtxMap.find(engine) == engineCtxMap.end()) {
            HCCL_INFO("[%s] not exist a context with tag[%s], engine[%d]", __func__, tag.c_str(), engine);
            return HCCL_E_PARA;
        }
    }

    *ctx = contextMap_[tag][engine].addr;
    *size = contextMap_[tag][engine].size;
    HCCL_INFO("[%s]get context success, tag[%s], engine[%d]", __func__, tag.c_str(), engine);    
    return HCCL_SUCCESS;
}

HcclResult ContextManager::CopyCommEngineCtx(const std::string &tag, CommEngine engine, const void *srcCtx,
    uint64_t size, uint64_t dstCtxOffset)
{
    void *dstCtx;
    uint64_t dstSize = 0;
    if (engine == COMM_ENGINE_AICPU_TS || engine == COMM_ENGINE_AICPU) {
        CHK_RET(GetCommEngineCtx(tag, engine, &dstCtx, &dstSize));
        // 从Host内存拷贝到Device Context内存上
        CHK_RET(hrtMemSyncCopy(reinterpret_cast<uint8_t*>(dstCtx) + dstCtxOffset, size, srcCtx, size,
            HcclRtMemcpyKind::HCCL_RT_MEMCPY_KIND_HOST_TO_DEVICE));
    } else if (engine == COMM_ENGINE_CPU || engine == COMM_ENGINE_CPU_TS) {
        CHK_RET(GetCommEngineCtx(tag, engine, &dstCtx, &dstSize));
        (void)memcpy_s(reinterpret_cast<uint8_t*>(dstCtx) + dstCtxOffset, size, srcCtx, size);
    } else {
        HCCL_ERROR("[%s]copy engine ctx failed, Unsupported engine[%d], tag[%s]", __func__, engine, tag.c_str());
        return HCCL_E_PARA;
    }
    HCCL_INFO("[%s]copy engine ctx success, tag[%s], engine[%d]", __func__, tag.c_str(), engine);
    return HCCL_SUCCESS;
}

HcclResult ContextManager::DestroyCommEngineCtx(const HcclMem *engineCtx)
{
    CHK_PTR_NULL(engineCtx);
    std::lock_guard<std::mutex> lock(mutex_); 
    // Ctx不存在返回错误
    if (tagMap_.find(*engineCtx) == tagMap_.end()) {
        HCCL_ERROR("[%s]The provided engineCtx does not exist. engineCtx type[%d], addr[%p], size:[%lu]", 
                __func__, engineCtx->type, engineCtx->addr, engineCtx->size);
        return HCCL_E_PARA;
    }

    // Ctx存在进行销毁
    contextMap_[tagMap_[*engineCtx]].erase(engineMap_[*engineCtx]);
    if (contextMap_[tagMap_[*engineCtx]].empty()) {
        contextMap_.erase(tagMap_[*engineCtx]);
    }
    tagMap_.erase(*engineCtx);
    engineMap_.erase(*engineCtx);

    if (engineCtx->type == HCCL_MEM_TYPE_HOST) {
        free(engineCtx->addr);
    } else if (engineCtx->type == HCCL_MEM_TYPE_DEVICE) {
        CHK_RET(hrtFree(engineCtx->addr));
    }

    HCCL_INFO("[%s]destroy context success", __func__);   
    return HCCL_SUCCESS;
}

}