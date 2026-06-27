/**
 * Copyright (c) 2025 Huawei Technologies Co., Ltd.
 * This program is free software, you can redistribute it and/or modify it under the terms and conditions of
 * CANN Open Software License Agreement Version 2.0 (the "License").
 * Please refer to the License for details. You may not use this file except in compliance with the License.
 * THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
 * INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
 * See LICENSE in the root of the software repository for the full text of the License.
 */

#include "hccl_thread.h"
#include "stream_pub.h"
#include "adapter_hal_pub.h"
#include "device_capacity.h"
#include "aicpu/aicpu_hccl_sqcq.h"

namespace hccl {
HcclThread::HcclThread(rtStream_t rtStream, u32 notifyNum, const NotifyLoadType notifyLoadType)
    : rtStream_(rtStream), notifyNum_(notifyNum), notifyLoadType_(notifyLoadType)
{
}

HcclThread::HcclThread(StreamType streamType, u32 notifyNum, const NotifyLoadType notifyLoadType)
    : streamType_(streamType), notifyNum_(notifyNum), notifyLoadType_(notifyLoadType)
{
}

HcclThread::HcclThread(const std::string& uniqueIdStr) : uniqueIdStr_(uniqueIdStr)
{
}

HcclThread::~HcclThread()
{
    DeInit();
}

HcclResult HcclThread::Init()
{
    CHK_RET(GetRunSideIsDevice(isDeviceSide_));
    if (!isDeviceSide_) {
        CHK_PRT_RET(!uniqueIdStr_.empty(), HCCL_ERROR("[HcclThread][Init]not support init with uniqueId on host"),
            HCCL_E_NOT_SUPPORT);
        s32 deviceLogicId;
        CHK_RET(hrtGetDevice(&deviceLogicId));
        CHK_RET(hrtGetDevicePhyIdByIndex(static_cast<u32>(deviceLogicId), devId_));
        if (rtStream_ == nullptr) {
            stream_.reset(new (std::nothrow) Stream(streamType_));
            CHK_SMART_PTR_NULL(stream_);
            rtStream_ = stream_->ptr();
        } else {
            stream_.reset(new (std::nothrow) Stream(rtStream_));
            CHK_SMART_PTR_NULL(stream_);
        }
        notifys_.reserve(notifyNum_);
        for (u32 idx = 0; idx < notifyNum_; idx++) {
            notifys_.emplace_back(nullptr);
            notifys_[idx].reset(new (std::nothrow) LocalNotify());
            CHK_SMART_PTR_NULL(notifys_[idx]);
            CHK_RET(notifys_[idx]->Init(notifyLoadType_));
            if (Is310PDevice()) {
                CHK_RET(notifys_[idx]->SetIpc());
            }
        }
        if (streamType_ == StreamType::STREAM_TYPE_DEVICE) {
            u64 size = sizeof(SqCqeContext);
            sqCqeContext_ = DeviceMem::alloc(size);
            CHK_PTR_NULL(sqCqeContext_.ptr());
            CHK_RET(hrtMemSet(sqCqeContext_.ptr(), size, size));
        }
    } else {
        CHK_PRT_RET(uniqueIdStr_.empty(), HCCL_ERROR("[HcclThread][Init]uniqueIdStr is empty"), HCCL_E_INTERNAL);
        std::istringstream iss(uniqueIdStr_);
        u32 hostPhyId = 0;
        iss.read(reinterpret_cast<char_t *>(&streamType_), sizeof(streamType_));
        iss.read(reinterpret_cast<char_t *>(&notifyLoadType_), sizeof(notifyLoadType_));
        CHK_PRT_RET((streamType_ != StreamType::STREAM_TYPE_DEVICE || notifyLoadType_ != NotifyLoadType::DEVICE_NOTIFY),
            HCCL_ERROR("[HcclThread][Init]streamType[%d] or notifyLoadType[%d] is not support on device", streamType_,
            notifyLoadType_), HCCL_E_NOT_SUPPORT);
        iss.read(reinterpret_cast<char_t *>(&hostPhyId), sizeof(hostPhyId));
        CHK_RET(hrtDrvGetLocalDevIDByHostDevID(hostPhyId, &devId_));
        iss.read(reinterpret_cast<char_t *>(&notifyNum_), sizeof(notifyNum_));
        HcclStreamParam streamParam;
        iss.read(reinterpret_cast<char_t *>(&streamParam), sizeof(streamParam));
        CHK_RET(InitStream(streamParam));
        notifys_.reserve(notifyNum_);
        for (u32 idx = 0; idx < notifyNum_; idx++) {
            notifys_.emplace_back(nullptr);
            HcclSignalInfo notifyInfo;
            iss.read(reinterpret_cast<char_t *>(&notifyInfo), sizeof(notifyInfo));
            notifys_[idx].reset(new (std::nothrow) LocalNotify());
            CHK_SMART_PTR_NULL(notifys_[idx]);
            CHK_RET(notifys_[idx]->Init(notifyInfo, NotifyLoadType::DEVICE_NOTIFY));
            HCCL_INFO("[HcclThread][Init]local notify init success, resId[%u], tsId:%d, devId[%u]",
                notifyInfo.resId, notifyInfo.tsId, notifyInfo.devId);
        }
    }
    return HCCL_SUCCESS;
}

HcclResult HcclThread::DeInit()
{
    streamType_ = StreamType::STREAM_TYPE_RESERVED;
    notifyNum_ = 0;
    stream_ = nullptr;
    notifys_.clear();
    uniqueIdStr_ = std::string();
    sqCqeContext_ = DeviceMem();
    return HCCL_SUCCESS;
}

std::string &HcclThread::GetUniqueId()
{
    if (!uniqueIdStr_.empty()) {
        return uniqueIdStr_;
    }

    // 序列化信息
    std::ostringstream oss;
    oss.write(reinterpret_cast<const char_t *>(&streamType_), sizeof(streamType_));
    oss.write(reinterpret_cast<const char_t *>(&notifyLoadType_), sizeof(notifyLoadType_));
    oss.write(reinterpret_cast<const char_t *>(&devId_), sizeof(devId_));
    oss.write(reinterpret_cast<const char_t *>(&notifyNum_), sizeof(notifyNum_));
    HcclStreamParam streamParam;
    streamParam.streamInfo.streamIds = stream_->id();
    streamParam.streamInfo.sqIds = stream_->sqId();
    streamParam.streamInfo.cqIds = stream_->cqId();
    streamParam.streamInfo.logicCqids = stream_->logicCqId();
    streamParam.sqCqContextAddr = reinterpret_cast<u64>(sqCqeContext_.ptr());
    streamParam.sqCqContextSize = sqCqeContext_.size();

    oss.write(reinterpret_cast<const char_t *>(&streamParam), sizeof(streamParam));
    HcclResult ret = HCCL_SUCCESS;
    for (u32 idx = 0; idx < notifyNum_; idx++) {
        HcclSignalInfo notifyInfo;
        ret = notifys_[idx]->GetNotifyData(notifyInfo);
        if (ret != HCCL_SUCCESS) {
            HCCL_ERROR("[HcclThread][GetUniqueId]GetNotifyData failed, ret[%d]", ret);
            uniqueIdStr_ = std::string();
            return uniqueIdStr_;
        }
        HCCL_INFO("[HcclThread][GetUniqueId]get local notify data success, resId[%u], tsId:%d, devId[%u]",
            notifyInfo.resId, notifyInfo.tsId, notifyInfo.devId);
        oss.write(reinterpret_cast<const char_t *>(&notifyInfo), sizeof(notifyInfo));
    }
    HCCL_DEBUG("[HcclThread][GetUniqueId] stream[%p], notifyNum[%u]", stream_->ptr(), notifyNum_);

    uniqueIdStr_ = oss.str();
    return uniqueIdStr_;
}

HcclResult HcclThread::InitStream(HcclStreamParam &streamParam)
{
#ifdef CCL_KERNEL_AICPU
    HcclStreamInfo &streamInfo = streamParam.streamInfo;

    static bool isCustom = false;
    static bool init = false;
    if (UNLIKELY(!init)) {
        u32 cpType = DEVDRV_PROCESS_CPTYPE_MAX;
        unsigned int hostpid = 0;
        CHK_RET(HrtHalDrvQueryProcessHostPid(getpid(), nullptr, nullptr, &hostpid, &cpType));
        isCustom = cpType == static_cast<u32>(DEVDRV_PROCESS_CP2) ? true : false;
        init = true;
    }
    HcclResult ret = hrtHalResourceIdRestore(devId_, 0, DRV_STREAM_ID, streamInfo.streamIds, 0);
    // custom进程需要恢复stream资源, custom进程调用失败直接报错，aicpu进程调用失败做兼容性处理
    if (ret == HCCL_E_NOT_SUPPORT) {
        CHK_PRT_RET(isCustom, HCCL_ERROR("%s hrtHalResourceIdRestore fail, drv not support, custom[%d], ret[%d]",
            __func__, isCustom, ret), HCCL_E_DRV);
    } else if (ret != HCCL_SUCCESS) {
        HCCL_ERROR("%s hrtHalResourceIdRestore fail, ret[%d]", __func__, ret);
        return HCCL_E_DRV;
    }

    HcclComStreamInfo comStreamInfo = {0};
    comStreamInfo.sqId = streamInfo.sqIds;
    comStreamInfo.actualStreamId = streamInfo.streamIds;
    comStreamInfo.logicCqId = streamInfo.logicCqids;
    u64 sqAddr = 0;
    u32 sqTail = 0;
    u32 sqHead = 0;
    CHK_RET(QuerySqBaseAddr(devId_, streamInfo.sqIds, sqAddr));
    comStreamInfo.sqBaseAddr = reinterpret_cast<void *>(sqAddr);
    if (comStreamInfo.sqBaseAddr == nullptr) {
        HCCL_ERROR("%s sqe base addr ptr is null.", __func__);
        return HCCL_E_PARA;
    }
    CHK_RET(QuerySqStatusByType(devId_, streamInfo.sqIds, DRV_SQCQ_PROP_SQ_DEPTH, comStreamInfo.sqDepth));
    CHK_RET(QuerySqStatusByType(devId_, streamInfo.sqIds, DRV_SQCQ_PROP_SQ_TAIL, sqTail));
    CHK_RET(QuerySqStatusByType(devId_, streamInfo.sqIds, DRV_SQCQ_PROP_SQ_HEAD, sqHead));
    HCCL_DEBUG("%s get stream data success, streamId[%d], sqId[%d], logicCqId[%u], sqDepth[%u], sqHead[%u], sqTail[%u]",
        __func__, comStreamInfo.actualStreamId, comStreamInfo.sqId, comStreamInfo.logicCqId, comStreamInfo.sqDepth,
        sqHead, sqTail);

    stream_.reset(new (std::nothrow) Stream(comStreamInfo));
    CHK_SMART_PTR_NULL(stream_);

    // 初始化stream的sqeContext
    SqCqeContext* sqCqeContext =
        reinterpret_cast<SqCqeContext*>(streamParam.sqCqContextAddr);
    u64 sqCqContextSize = streamParam.sqCqContextSize;
    if (sqCqeContext == nullptr || sqCqContextSize != sizeof(SqCqeContext)) {
        HCCL_ERROR("%s fail, sqCqeContext[%p] is null or size[%llu] is not equal to SqCqeContext size[%llu]",
            __func__, sqCqeContext, sqCqContextSize, sizeof(SqCqeContext));
        return HCCL_E_PARA;
    }
    sqCqeContext_ = DeviceMem::create(reinterpret_cast<void*>(sqCqeContext), sqCqContextSize);
    ret = stream_->InitSqAndCqeContext(sqHead, sqTail, sqCqeContext);
    CHK_PRT_RET(ret != HCCL_SUCCESS,
        HCCL_ERROR("%s InitSqAndCqeContext failed", __func__), ret);
    HCCL_INFO("%s success, streamId[%d]", __func__, stream_->id());
#endif
    return HCCL_SUCCESS;
}
}  // namespace hccl
