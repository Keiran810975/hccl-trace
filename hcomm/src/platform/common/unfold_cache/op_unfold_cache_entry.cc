/*
 * This program is free software, you can redistribute it and/or modify it.
 * Copyright (c) 2025 Huawei Technologies Co., Ltd.
 * This file is a part of the CANN Open Software.
 * Licensed under CANN Open Software License Agreement Version 2.0 (the "License").
 * Please refer to the License for details. You may not use this file except in compliance with the License.
 * THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
 * See LICENSE in the root of the software repository for the full text of the License.
 */

#include <cstdint>
#include <cstdlib>

#include "op_unfold_cache_entry.h"

#include "aicpu_hccl_sqcq.h"
#include "aicpu_hccl_sqcqv1.h"
#include "aicpu_hccl_sqcqv2.h"
#include "log.h"
#include "sal.h"

namespace hccl {

    // struct OpUnfoldMemRange

    OpUnfoldMemRange::OpUnfoldMemRange() : isValid(false), baseAddr(0), memSize(0) {
    }

    OpUnfoldMemRange::OpUnfoldMemRange(const uint64_t curBaseAddr, const uint64_t curMemSize) : isValid(true), baseAddr(curBaseAddr), memSize(curMemSize) {
        // 检查地址有效性
        CHK_PRT_CONT(curBaseAddr == 0, HCCL_ERROR("[OpUnfoldMemRange][OpUnfoldMemRange] curBaseAddr is 0"));
    }

    OpUnfoldMemRange::OpUnfoldMemRange(const OpUnfoldMemRange& other)
        : isValid(other.isValid), baseAddr(other.baseAddr), memSize(other.memSize) {
    }

    OpUnfoldMemRange::~OpUnfoldMemRange() {}

    const OpUnfoldMemRange& OpUnfoldMemRange::operator=(const OpUnfoldMemRange& other) {
        if (this != &other) {
            isValid = other.isValid;
            baseAddr = other.baseAddr;
            memSize = other.memSize;
        }
        return *this;
    }

    HcclResult OpUnfoldMemRange::InRange(const uint64_t addr, bool& isInRange) const {
        // 检查地址是否溢出
        CHK_PRT_RET(baseAddr + memSize < baseAddr, HCCL_ERROR("[OpUnfoldMemRange][InRange] baseAddr[0x%016llx] + memSize[%llu] overflows", baseAddr, memSize), HCCL_E_INTERNAL);

        if (isValid && addr >= baseAddr && addr < (baseAddr + memSize)) {
            isInRange = true;
        } else {
            isInRange = false;
        }

        return HCCL_SUCCESS;
    }

    // struct RefreshAddrInfo

    RefreshAddrInfo::RefreshAddrInfo() : rankId(INVALID_VALUE_RANKID), memType(RefreshAddrInfo::INVALID_MEMTYPE) {
    }

    RefreshAddrInfo::RefreshAddrInfo(const uint32_t curRankId, const uint8_t curMemType) : rankId(curRankId), memType(curMemType) {
        // 注意: rankId可以为INVALID_VALUE_RANKID, 表示访问本地rank
        CHK_PRT_CONT(memType == INVALID_MEMTYPE, HCCL_ERROR("[RefreshAddrInfo][RefreshAddrInfo] invalid memType"));
    }

    RefreshAddrInfo::RefreshAddrInfo(const RefreshAddrInfo& other)
        : rankId(other.rankId), memType(other.memType) {
    }

    RefreshAddrInfo::~RefreshAddrInfo() {}

    const RefreshAddrInfo& RefreshAddrInfo::operator=(const RefreshAddrInfo& other) {
        if (this != &other) {
            rankId = other.rankId;
            memType = other.memType;
        }
        return *this;
    }

    // class OpUnfoldCacheEntry

    OpUnfoldCacheEntry::OpUnfoldCacheEntry(const std::vector<OpUnfoldMemRange>& userInputMemRanges, const std::vector<OpUnfoldMemRange>& userOutputMemRanges)
        : userInputMemRanges_(userInputMemRanges), userOutputMemRanges_(userOutputMemRanges) {
        HCCL_INFO("[OpUnfoldCacheEntry][OpUnfoldCacheEntry] create a cache entry with %llu userInputMemRanges and %llu userOutputMemRanges",
            userInputMemRanges_.size(), userOutputMemRanges_.size());
    }

    OpUnfoldCacheEntry::~OpUnfoldCacheEntry() {
        size_t sqeArrayCount = sqeArrays_.size();
        size_t totalSqeCount = 0;
        for (size_t arrayIdx = 0; arrayIdx < sqeArrayCount; ++arrayIdx) {
            totalSqeCount += srcRefreshAddrInfoArrays_[arrayIdx].size();

            // 如果存在当前这段连续的SQE数组，则指向内容必不为空
            // 因为SQE数量为0时, DispatcherAicpu::LaunchTask()会直接返回, 不会添加SQE到OpUnfoldCache中
            uint8_t *curSqeArray = sqeArrays_[arrayIdx];

            // 释放当前SQE数组
            if (UNLIKELY(curSqeArray == nullptr)) { // 不能使用CHK_PTR_NULL，因为会return HcclResult
                HCCL_ERROR("[OpUnfoldCacheEntry][~OpUnfoldCacheEntry] curSqeArray is nullptr");
            } else {
                free(curSqeArray);
                curSqeArray = nullptr;
            }

            // 同理释放其他空间

            // 释放当前SQE type数组
            uint8_t *curSqeTypeArray = sqeTypeArrays_[arrayIdx];
            if (UNLIKELY(curSqeTypeArray == nullptr)) {
                HCCL_ERROR("[OpUnfoldCacheEntry][~OpUnfoldCacheEntry] curSqeTypeArray is nullptr");
            } else {
                free(curSqeTypeArray);
                curSqeTypeArray = nullptr;
            }

            // 释放当前SQE DfxInfo数组
            AicpuDfxInfo *curSqeDfxInfoArray = sqeDfxInfoArrays_[arrayIdx];
            if (UNLIKELY(curSqeDfxInfoArray == nullptr)) {
                HCCL_ERROR("[OpUnfoldCacheEntry][~OpUnfoldCacheEntry] curSqeDfxInfoArray is nullptr");
            } else {
                free(curSqeDfxInfoArray);
                curSqeDfxInfoArray = nullptr;
            }
        }

        HCCL_INFO("[OpUnfoldCacheEntry][~OpUnfoldCacheEntry] release %u SQE arrays (%u SQEs in total) from the cache entry", sqeArrayCount, totalSqeCount);
    }

    HcclResult OpUnfoldCacheEntry::GetSqeArrayCount(size_t& sqeArrayCount) const {
        sqeArrayCount = sqeArrays_.size();
        CHK_PRT_RET(sqeArrayCount == 0, HCCL_ERROR("[OpUnfoldCacheEntry][OpUnfoldCacheEntry] sqeArrayCount is 0"), HCCL_E_INTERNAL);
        return HCCL_SUCCESS;
    }

    HcclResult OpUnfoldCacheEntry::AllocSqeArray(const size_t sqeCount, const int32_t streamId, size_t& arrayIdx) {
        // Allocate a new SQE array
        const size_t sqeBytes = sqeCount * HCCL_SQE_SIZE;
        uint8_t *newSqeArray = reinterpret_cast<uint8_t *>(malloc(sqeBytes));
        CHK_PTR_NULL(newSqeArray);
        sqeArrays_.emplace_back(newSqeArray);

        // Allocate a new SQE type array
        const size_t sqeTypeBytes = sqeCount * sizeof(uint8_t);
        uint8_t *newSqeTypeArray = reinterpret_cast<uint8_t *>(malloc(sqeTypeBytes));
        CHK_PTR_NULL(newSqeTypeArray);
        sqeTypeArrays_.emplace_back(newSqeTypeArray);

        // Allocate a new SQE DFX info array
        const size_t sqeDfxInfoBytes = sqeCount * sizeof(AicpuDfxInfo);
        AicpuDfxInfo *newSqeDfxInfoArray = reinterpret_cast<AicpuDfxInfo *>(malloc(sqeDfxInfoBytes));
        CHK_PTR_NULL(newSqeDfxInfoArray);
        sqeDfxInfoArrays_.emplace_back(newSqeDfxInfoArray);

        // Copy stream pointer
        CHK_PRT_RET(streamId < 0, HCCL_ERROR("[OpUnfoldCacheEntry][AllocSqeArray] streamId %d < 0", streamId), HCCL_E_INTERNAL);
        streamIds_.emplace_back(streamId);

        // 注意: streamSeqIdxes_在cache miss LaunchTask()结束后, HcclCommAicpu通过CalcStreamSeqIdxes更新

        // 初始化src/dst RefreshAddrInfo
        srcRefreshAddrInfoArrays_.emplace_back(sqeCount);
        dstRefreshAddrInfoArrays_.emplace_back(sqeCount);

        // Set index of allocated array
        arrayIdx = sqeArrays_.size() - 1;

        HCCL_INFO("[OpUnfoldCacheEntry][AllocSqeArray] allocate %uth sqe array with sqeCount of %u and streamId of %d", arrayIdx, sqeCount, streamId);

        return HCCL_SUCCESS;
    }

    HcclResult OpUnfoldCacheEntry::MemcpySqeArray(const size_t arrayIdx, const size_t sqeStartIdx, const size_t sqeCount, const uint8_t *sqeArray, const uint8_t *sqeTypeArray, const AicpuDfxInfo *sqeDfxInfoArray) {
        // Copy sqeArray[0:sqeCount) -> sqeArrays_[arrayIdx][sqeStartIdx:sqeStartIdx+sqeCount)

        // 检验入参
        CHK_PRT_RET(arrayIdx >= sqeArrays_.size(), HCCL_ERROR("[OpUnfoldCacheEntry][MemcpySqeArray] arrayIdx %u is out of range [0, %u)", arrayIdx, sqeArrays_.size()), HCCL_E_INTERNAL);
        const size_t totalSqeCount = srcRefreshAddrInfoArrays_[arrayIdx].size();
        CHK_PRT_RET(sqeStartIdx + sqeCount - 1 >= totalSqeCount, HCCL_ERROR("[OpUnfoldCacheEntry][MemcpySqeArray] sqeStartIdx %u + sqeCount %u - 1 is out of range [0, %u)", sqeStartIdx, sqeCount, totalSqeCount), HCCL_E_INTERNAL);
        CHK_PTR_NULL(sqeArray);
        CHK_PTR_NULL(sqeTypeArray);
        CHK_PTR_NULL(sqeDfxInfoArray);

        HCCL_INFO("[OpUnfoldCacheEntry][MemcpySqeArray] memcpy %uth sqe array[%u:%u]", arrayIdx, sqeStartIdx, sqeStartIdx + sqeCount - 1);

        // Copy SQE content
        const size_t sqeBytes = sqeCount * HCCL_SQE_SIZE;
        uint8_t *dstSqeArray = sqeArrays_[arrayIdx];
        CHK_PTR_NULL(dstSqeArray);
        CHK_SAFETY_FUNC_RET(memcpy_s(dstSqeArray + sqeStartIdx * HCCL_SQE_SIZE, (totalSqeCount - sqeStartIdx) * HCCL_SQE_SIZE, sqeArray, sqeBytes));

        // Copy SQE type
        const size_t sqeTypeBytes = sqeCount * sizeof(uint8_t);
        uint8_t *dstSqeTypeArray = sqeTypeArrays_[arrayIdx];
        CHK_PTR_NULL(dstSqeTypeArray);
        CHK_SAFETY_FUNC_RET(memcpy_s(dstSqeTypeArray + sqeStartIdx, (totalSqeCount - sqeStartIdx) * sizeof(uint8_t), sqeTypeArray, sqeTypeBytes));

        // Copy SQE DFX info
        const size_t sqeDfxInfoBytes = sqeCount * sizeof(AicpuDfxInfo);
        AicpuDfxInfo *dstSqeDfxInfoArray = sqeDfxInfoArrays_[arrayIdx];
        CHK_PTR_NULL(dstSqeDfxInfoArray);
        CHK_SAFETY_FUNC_RET(memcpy_s(dstSqeDfxInfoArray + sqeStartIdx, (totalSqeCount - sqeStartIdx) * sizeof(AicpuDfxInfo), sqeDfxInfoArray, sqeDfxInfoBytes));

        // 遍历SQE, 根据type更新src/dst RefreshAddrInfo
        std::vector<RefreshAddrInfo>& srcRefreshAddrInfoArray = srcRefreshAddrInfoArrays_[arrayIdx];
        std::vector<RefreshAddrInfo>& dstRefreshAddrInfoArray = dstRefreshAddrInfoArrays_[arrayIdx];
        uint64_t sqeSrcAddr = 0;
        uint64_t sqeDstAddr = 0;
        const uint8_t *sqePtr = sqeArray;
        for (size_t tmpSqeIdx = 0; tmpSqeIdx < sqeCount; tmpSqeIdx++) {
            const size_t cacheSqeIdx = sqeStartIdx + tmpSqeIdx;

            // 获得当前SQE的信息
            // 注意: 不使用sqeDfxInfoArray[tmpSqeIdx].remoteRank来准备RefreshAddrInfo, 因为DfxInfo.remoteRank某些整网用例下存在维护异常
            const uint8_t sqeType = sqeTypeArray[tmpSqeIdx];

            // 根据SQE type更新RefreshAddrInfo
            switch(sqeType) {
                case SqeType::NOTIFY_SQE:
                case SqeType::EVENT_SQE: {
                    // No need to update src/dst RefreshAddrInfo due to no addr fields
                    break;
                }
                case SqeType::WRITE_VALUE_SQE:
                case SqeType::RDMA_DB_SEND_SQE: {
                    const rtStarsWriteValueSqe_t *writeValueSqePtr = reinterpret_cast<const rtStarsWriteValueSqe_t *>(sqePtr);
                    
                    CombineUint32ToUint64(sqeDstAddr, writeValueSqePtr->write_addr_high, writeValueSqePtr->write_addr_low);
                    CHK_RET(CheckAndPrepareRefreshAddrInfo(sqeDstAddr, dstRefreshAddrInfoArray[cacheSqeIdx]));

                    break;
                }
                case SqeType::MEMCPY_ASYNC_SQE: {
                    const rtStarsMemcpyAsyncSqe_t *memcpyAsyncSqePtr = reinterpret_cast<const rtStarsMemcpyAsyncSqe_t *>(sqePtr);

                    CombineUint32ToUint64(sqeSrcAddr, memcpyAsyncSqePtr->src_addr_high, memcpyAsyncSqePtr->src_addr_low);
                    CHK_RET(CheckAndPrepareRefreshAddrInfo(sqeSrcAddr, srcRefreshAddrInfoArray[cacheSqeIdx]));

                    CombineUint32ToUint64(sqeDstAddr, memcpyAsyncSqePtr->dst_addr_high, memcpyAsyncSqePtr->dst_addr_low);
                    CHK_RET(CheckAndPrepareRefreshAddrInfo(sqeDstAddr, dstRefreshAddrInfoArray[cacheSqeIdx]));

                    break;
                }
                case SqeType::CCORE_WAIT_START_SQE: {
                    HCCL_ERROR("[OpUnfoldCacheEntry][MemcpySqeArray] SqeType::CCORE_WAIT_START_SQE is not supported in A3");
                    return HCCL_E_NOT_SUPPORT;
                }
                case SqeType::CCORE_WRITE_VALUE_SQE: {
                    HCCL_ERROR("[OpUnfoldCacheEntry][MemcpySqeArray] SqeType::CCORE_WRITE_VALUE_SQE is not supported in A3");
                    return HCCL_E_NOT_SUPPORT;
                }
                case SqeType::NOTIFY_SQE_V2: {
                    HCCL_ERROR("[OpUnfoldCacheEntry][MemcpySqeArray] SqeType::NOTIFY_SQE_V2 is not supported in A3");
                    return HCCL_E_NOT_SUPPORT;
                }
                case SqeType::WRITE_VALUE_SQE_V2: {
                    HCCL_ERROR("[OpUnfoldCacheEntry][MemcpySqeArray] SqeType::WRITE_VALUE_SQE_V2 is not supported in A3");
                    return HCCL_E_NOT_SUPPORT;
                }
                case SqeType::EVENT_SQE_V2: {
                    HCCL_ERROR("[OpUnfoldCacheEntry][MemcpySqeArray] SqeType::EVENT_SQE_V2 is not supported in A3");
                    return HCCL_E_NOT_SUPPORT;
                }
                case SqeType::MEMCPY_ASYNC_SQE_V2: {
                    HCCL_ERROR("[OpUnfoldCacheEntry][MemcpySqeArray] SqeType::MEMCPY_ASYNC_SQE_V2 is not supported in A3");
                    return HCCL_E_NOT_SUPPORT;
                }
                case SqeType::FLIP_PLACEHOLDER_SQE: {
                    HCCL_ERROR("[OpUnfoldCacheEntry][MemcpySqeArray] placeholder should not be cached, sqeType[%u] tmpSqeIdx[%u] cacheSqeIdx[%u]", sqeType, tmpSqeIdx, cacheSqeIdx);
                    return HCCL_E_INTERNAL;
                }
                default: {
                    HCCL_WARNING("[OpUnfoldCacheEntry][MemcpySqeArray] sqeType %u is unsupported", sqeType);
                    return HCCL_E_NOT_SUPPORT;
                }
            }

            sqePtr += HCCL_SQE_SIZE;
        }

        return HCCL_SUCCESS;
    }

    HcclResult OpUnfoldCacheEntry::CalcStreamSeqIdxes(Stream& mainStream, std::vector<Stream>& slaveStreams) {
        const size_t streamIdCount = streamIds_.size();
        HCCL_INFO("[OpUnfoldCacheEntry][CalcStreamSeqIdxes] calculate stream sequential indexes for %u stream ids", streamIdCount);

        // 对每个stream id找到对应的sequential stream index
        streamSeqIdxes_.resize(streamIdCount);
        for (size_t i = 0; i < streamIdCount; ++i) {
            const int32_t curStreamId = streamIds_[i];

            if (curStreamId == mainStream.GetHcclStreamInfo().actualStreamId) { // 主流
                streamSeqIdxes_[i] = 0;
            } else { // 遍历从流
                bool isFound = false;
                for (size_t j = 0; j < slaveStreams.size(); ++j) {
                    if (curStreamId == slaveStreams[j].GetHcclStreamInfo().actualStreamId) { // 匹配某个从流
                        streamSeqIdxes_[i] = j + 1;
                        isFound = true;
                        break;
                    }
                }

                // No stream can match the stream id
                if (!isFound) {
                    HCCL_ERROR("[OpUnfoldCacheEntry][CalcStreamSeqIdxes] cannot find any stream to match streamId %u", curStreamId);
                    return HCCL_E_INTERNAL;
                }
            }
        }

        return HCCL_SUCCESS;
    }

    HcclResult OpUnfoldCacheEntry::UpdateAndGetSqeArray(const size_t arrayIdx, const std::vector<OpUnfoldMemRange>& curUserInputMemRanges, const std::vector<OpUnfoldMemRange>& curUserOutputMemRanges, Stream& mainStream, std::vector<Stream> &slaveStreams, const uint32_t opRingBufferIdx, size_t& sqeCount, uint8_t **sqeArrayPtr, uint8_t **sqeTypeArrayPtr, AicpuDfxInfo **sqeDfxInfoArrayPtr, Stream **streamPtrPtr, std::vector<size_t>& largestSqeIdxes, const bool profL1Enable, std::vector<uint64_t>& profTimestamps) {
        HCCL_INFO("[OpUnfoldCacheEntry][UpdateAndGetSqeArray] update and get SQEs from %uth SQE array", arrayIdx);

        // 检验入参
        CHK_PRT_RET(arrayIdx >= sqeArrays_.size(), HCCL_ERROR("[OpUnfoldCacheEntry][MemcpySqeArray] arrayIdx %u is out of range [0, %u)", arrayIdx, sqeArrays_.size()), HCCL_E_INTERNAL);
        CHK_PRT_RET(arrayIdx >= streamSeqIdxes_.size(), HCCL_ERROR("[OpUnfoldCacheEntry][MemcpySqeArray] arrayIdx %u is out of range [0, %u)", arrayIdx, streamSeqIdxes_.size()), HCCL_E_INTERNAL);
        // 检查指针, arrayPtr不应该是null, 但*arrayPtr应该是null
        CHK_PTRPTR_NULL(sqeArrayPtr);
        CHK_PTRPTR_NULL(sqeTypeArrayPtr);
        CHK_PTRPTR_NULL(sqeDfxInfoArrayPtr);
        CHK_PTRPTR_NULL(streamPtrPtr);

        // 设置入参
        sqeCount = srcRefreshAddrInfoArrays_[arrayIdx].size();
        *sqeArrayPtr = sqeArrays_[arrayIdx];
        *sqeTypeArrayPtr = sqeTypeArrays_[arrayIdx];
        *sqeDfxInfoArrayPtr = sqeDfxInfoArrays_[arrayIdx];
        largestSqeIdxes.clear();
        if (profL1Enable) {
            profTimestamps.clear();
            profTimestamps.reserve(sqeCount); // 需要额外flip placeholder是小概率事件, 所以只reserve cached SQE个数 (即非flip placeholder类SQE)
        }

        // 设置入参的stream pointer
        const uint32_t streamSeqIdx = streamSeqIdxes_[arrayIdx];
        if (streamSeqIdx == 0) {
            *streamPtrPtr = &mainStream;
        } else {
            CHK_PRT_RET(streamSeqIdx > slaveStreams.size(), HCCL_ERROR("[OpUnfoldCacheEntry][UpdateAndGetSqeArray] invalid streamSeqIdx %u > slaveStreams.size() %u", streamSeqIdx, slaveStreams.size()), HCCL_E_MEMORY);
            *streamPtrPtr = &(slaveStreams[streamSeqIdx - 1]); // 0 < streamSeqIdx <= slaveStreams.size())
        }

        // 从stream中获取SQE刷新需要的当前task id
        HcclSqeContext *sqeContext = (*streamPtrPtr)->GetSqeContextPtr();
        CHK_PTR_NULL(sqeContext);
        SqeRingBuffer *sqeContextBuffer = &(sqeContext->buffer);
        CHK_PTR_NULL(sqeContextBuffer);
        uint16_t& curTaskId = sqeContextBuffer->tailSqeTaskId;
        HCCL_INFO("[OpUnfoldCacheEntry][UpdateAndGetSqeArray] get curTaskId[%u] from stream with streamId %u for %u cached SQEs",
            curTaskId, (*streamPtrPtr)->GetHcclStreamInfo().actualStreamId, sqeCount);

        // 执行SQE刷新
        // 注意: curUserInputMemRanges/curUserOutputMemRanges为当前算子执行时各rank输入输出的user memory range, userInputMemRanges_/userOutputMemRanges_为算子缓存时各rank输入输出的user memory range
        const std::vector<RefreshAddrInfo>& srcRefreshAddrInfoArray = srcRefreshAddrInfoArrays_[arrayIdx];
        const std::vector<RefreshAddrInfo>& dstRefreshAddrInfoArray = dstRefreshAddrInfoArrays_[arrayIdx];
        uint64_t sqeSrcAddr = 0;
        uint64_t sqeDstAddr = 0;
        uint8_t *sqePtr = (*sqeArrayPtr);
        for (size_t sqeIdx = 0 ; sqeIdx < sqeCount; ++sqeIdx){
            // 获取当前SQE的信息
            uint8_t sqeType = (*sqeTypeArrayPtr)[sqeIdx];
            const RefreshAddrInfo& srcRefreshAddrInfo = srcRefreshAddrInfoArray[sqeIdx];
            const RefreshAddrInfo& dstRefreshAddrInfo = dstRefreshAddrInfoArray[sqeIdx];
            HCCL_DEBUG("[OpUnfoldCacheEntry][UpdateAndGetSqeArray] update %uth cached SQE: sqeType[%u] srcRefreshAddrInfo[rankid[%u], memType[%u]] dstRefreshAddrInfoArray[rankid[%u], memType[%u]] curTaskId[%u]",
                sqeIdx, sqeType, srcRefreshAddrInfo.rankId, srcRefreshAddrInfo.memType, dstRefreshAddrInfo.rankId, dstRefreshAddrInfo.memType, curTaskId);

            // 根据SQE type进行对应刷新 (task id始终要刷新; addr相关字段有条件刷新)
            switch(sqeType) {
                case SqeType::NOTIFY_SQE: {
                    rtStarsNotifySqeV1_t *notifySqePtr = reinterpret_cast<rtStarsNotifySqeV1_t *>(sqePtr);
                    notifySqePtr->header.taskId = curTaskId;
                    break;
                }
                case SqeType::WRITE_VALUE_SQE:
                case SqeType::RDMA_DB_SEND_SQE: {
                    rtStarsWriteValueSqe_t *writeValueSqePtr = reinterpret_cast<rtStarsWriteValueSqe_t *>(sqePtr);
                    writeValueSqePtr->header.taskId = curTaskId;

                    if (dstRefreshAddrInfo.memType != RefreshAddrInfo::INVALID_MEMTYPE) { // 需要刷新地址
                        CombineUint32ToUint64(sqeDstAddr, writeValueSqePtr->write_addr_high, writeValueSqePtr->write_addr_low);
                        if (dstRefreshAddrInfo.memType == RefreshAddrInfo::USER_OUTPUT_MEMTYPE) { // user output
                            CHK_RET(RefreshSqeAddr(sqeDstAddr, dstRefreshAddrInfo.rankId, userOutputMemRanges_, curUserOutputMemRanges));
                        } else { // user input
                            CHK_RET(RefreshSqeAddr(sqeDstAddr, dstRefreshAddrInfo.rankId, userInputMemRanges_, curUserInputMemRanges));
                        }

                        // Bit-field member不能直接传引用
                        uint32_t tmp_high_addr = 0;
                        SplitUint64ToUint32(sqeDstAddr, tmp_high_addr, writeValueSqePtr->write_addr_low);
                        writeValueSqePtr->write_addr_high = tmp_high_addr;
                    }
                    break;
                }
                case SqeType::EVENT_SQE: {
                    rtStarsEventSqe_t *eventSqePtr = reinterpret_cast<rtStarsEventSqe_t *>(sqePtr);
                    eventSqePtr->header.taskId = curTaskId;
                    break;
                }
                case SqeType::MEMCPY_ASYNC_SQE: {
                    rtStarsMemcpyAsyncSqe_t *memcpyAsyncSqePtr = reinterpret_cast<rtStarsMemcpyAsyncSqe_t *>(sqePtr);
                    memcpyAsyncSqePtr->header.taskId = curTaskId;

                    if (srcRefreshAddrInfo.memType != RefreshAddrInfo::INVALID_MEMTYPE) { // 需要刷新src addr
                        CombineUint32ToUint64(sqeSrcAddr, memcpyAsyncSqePtr->src_addr_high, memcpyAsyncSqePtr->src_addr_low);
                        if (srcRefreshAddrInfo.memType == RefreshAddrInfo::USER_OUTPUT_MEMTYPE) { // user output
                            CHK_RET(RefreshSqeAddr(sqeSrcAddr, srcRefreshAddrInfo.rankId, userOutputMemRanges_, curUserOutputMemRanges));
                        } else { // user input
                            CHK_RET(RefreshSqeAddr(sqeSrcAddr, srcRefreshAddrInfo.rankId, userInputMemRanges_, curUserInputMemRanges));
                        }
                        SplitUint64ToUint32(sqeSrcAddr, memcpyAsyncSqePtr->src_addr_high, memcpyAsyncSqePtr->src_addr_low);
                    }

                    if (dstRefreshAddrInfo.memType != RefreshAddrInfo::INVALID_MEMTYPE) { // 需要刷新地址
                        CombineUint32ToUint64(sqeDstAddr, memcpyAsyncSqePtr->dst_addr_high, memcpyAsyncSqePtr->dst_addr_low);
                        if (dstRefreshAddrInfo.memType == RefreshAddrInfo::USER_OUTPUT_MEMTYPE) { // user output
                            CHK_RET(RefreshSqeAddr(sqeDstAddr, dstRefreshAddrInfo.rankId, userOutputMemRanges_, curUserOutputMemRanges));
                        } else { // user input
                            CHK_RET(RefreshSqeAddr(sqeDstAddr, dstRefreshAddrInfo.rankId, userInputMemRanges_, curUserInputMemRanges));
                        }
                        SplitUint64ToUint32(sqeDstAddr, memcpyAsyncSqePtr->dst_addr_high, memcpyAsyncSqePtr->dst_addr_low);
                    }

                    break;
                }
                case SqeType::CCORE_WAIT_START_SQE: {
                    HCCL_ERROR("[OpUnfoldCacheEntry][UpdateAndGetSqeArray] SqeType::CCORE_WAIT_START_SQE is not supported in A3");
                    return HCCL_E_NOT_SUPPORT;
                }
                case SqeType::CCORE_WRITE_VALUE_SQE: {
                    HCCL_ERROR("[OpUnfoldCacheEntry][UpdateAndGetSqeArray] SqeType::CCORE_WRITE_VALUE_SQE is not supported in A3");
                    return HCCL_E_NOT_SUPPORT;
                }
                case SqeType::NOTIFY_SQE_V2: {
                    HCCL_ERROR("[OpUnfoldCacheEntry][UpdateAndGetSqeArray] SqeType::NOTIFY_SQE_V2 is not supported in A3");
                    return HCCL_E_NOT_SUPPORT;
                }
                case SqeType::WRITE_VALUE_SQE_V2: {
                    HCCL_ERROR("[OpUnfoldCacheEntry][UpdateAndGetSqeArray] SqeType::WRITE_VALUE_SQE_V2 is not supported in A3");
                    return HCCL_E_NOT_SUPPORT;
                }
                case SqeType::EVENT_SQE_V2: {
                    HCCL_ERROR("[OpUnfoldCacheEntry][UpdateAndGetSqeArray] SqeType::EVENT_SQE_V2 is not supported in A3");
                    return HCCL_E_NOT_SUPPORT;
                }
                case SqeType::MEMCPY_ASYNC_SQE_V2: {
                    HCCL_ERROR("[OpUnfoldCacheEntry][UpdateAndGetSqeArray] SqeType::MEMCPY_ASYNC_SQE_V2 is not supported in A3");
                    return HCCL_E_NOT_SUPPORT;
                }
                case SqeType::FLIP_PLACEHOLDER_SQE: {
                    HCCL_ERROR("[OpUnfoldCacheEntry][UpdateAndGetSqeArray] placeholder should not be cached, sqeType[%u] sqeIdx[%u]", sqeType, sqeIdx);
                    return HCCL_E_INTERNAL;
                }
                default: {
                    HCCL_WARNING("[OpUnfoldCacheEntry][UpdateAndGetSqeArray] sqeType %u is unsupported", sqeType);
                    return HCCL_E_NOT_SUPPORT;
                }
            }

            // 记录SQE刷新时间用于profiling
            if (profL1Enable) {
                const uint64_t curTime = ProfGetCurCpuTimestamp();
                profTimestamps.push_back(curTime);
            }

            // 刷新stream.curTaskId
            if (curTaskId < UINT16_MAX) { // 未出现uint16 overflow
                curTaskId += 1;
            } else { // 触发flip
                curTaskId = 1; // 为placeholder SQE预留task id = 0
                largestSqeIdxes.push_back(sqeIdx); // 记录sqeIdx, LaunchNewTask中需要在该位置后添加placeholder SQE

                // Flip placeholder SQE在外侧dispatcher aicpu中生成, 这里记录当前时间作为flip placeholder SQE的生成时间
                if (profL1Enable) {
                    const uint64_t curTime = ProfGetCurCpuTimestamp();
                    profTimestamps.push_back(curTime);
                }
            }

            sqePtr += HCCL_SQE_SIZE;
        }

        // 更新每个SQE的DfxInfo中的opRingBufferIdx
        HCCL_INFO("[OpUnfoldCacheEntry][UpdateAndGetSqeArray] update opRingBufferIndx in DfxInfoArray as %u", opRingBufferIdx);
        for (size_t sqeIdx = 0; sqeIdx < sqeCount; ++sqeIdx) {
            (*sqeDfxInfoArrayPtr)[sqeIdx].opRingBufferIdx = opRingBufferIdx;
        }

        HCCL_INFO("[OpUnfoldCacheEntry][UpdateAndGetSqeArray] update and get %uth SQE array with %u SQEs, streamId[%u] and %u largestSqeIdxes", arrayIdx, sqeCount, (*streamPtrPtr)->GetHcclStreamInfo().actualStreamId, largestSqeIdxes.size());

        return HCCL_SUCCESS;
    }

    HcclResult OpUnfoldCacheEntry::SetInputOutputMemRanges(const std::vector<OpUnfoldMemRange>& curUserInputMemRanges, const std::vector<OpUnfoldMemRange>& curUserOutputMemRanges) {
        CHK_PRT_RET(userInputMemRanges_.size() != curUserInputMemRanges.size(), HCCL_ERROR("[OpUnfoldCacheEntry][SetInputOutputMemRanges] original rankSize %u != new rankSize %u", userInputMemRanges_.size(), curUserInputMemRanges.size()), HCCL_E_INTERNAL);

        userInputMemRanges_ = curUserInputMemRanges;
        userOutputMemRanges_ = curUserOutputMemRanges;

        return HCCL_SUCCESS;
    }

    HcclResult OpUnfoldCacheEntry::CheckAndPrepareRefreshAddrInfo(const uint64_t sqeAddr, RefreshAddrInfo& refreshAddrInfo) {
        // 遍历per-rank user input memory range
        for (size_t rankId = 0; rankId < userInputMemRanges_.size(); ++rankId) {
            bool isInRange = false;
            CHK_RET(userInputMemRanges_[rankId].InRange(sqeAddr, isInRange));
            if (isInRange) {
                refreshAddrInfo.rankId = rankId;
                refreshAddrInfo.memType = RefreshAddrInfo::USER_INPUT_MEMTYPE;
                return HCCL_SUCCESS; // 确实是某rank下的user input mem, 则无需继续搜索output mem
            }
        }

        // 遍历per-rank user input memory range
        for (size_t rankId = 0; rankId < userOutputMemRanges_.size(); ++rankId) {
            bool isInRange = false;
            CHK_RET(userOutputMemRanges_[rankId].InRange(sqeAddr, isInRange));
            if (isInRange) {
                refreshAddrInfo.rankId = rankId;
                refreshAddrInfo.memType = RefreshAddrInfo::USER_OUTPUT_MEMTYPE;
                return HCCL_SUCCESS;
            }
        }

        return HCCL_SUCCESS;
    }

    HcclResult OpUnfoldCacheEntry::RefreshSqeAddr(uint64_t &sqeAddr, const uint32_t rankId, const std::vector<OpUnfoldMemRange>& cachedMemRanges, const std::vector<OpUnfoldMemRange>& curMemRanges) const {
        CHK_PRT_RET(rankId == INVALID_VALUE_RANKID, HCCL_ERROR("[OpUnfoldCacheEntry][RefreshSqeAddr] invalid rankId"), HCCL_E_INTERNAL);
        CHK_PRT_RET(rankId >= cachedMemRanges.size(), HCCL_ERROR("[OpUnfoldCacheEntry][RefreshSqeAddr] rankId %u exceeds rankSize %u", rankId, cachedMemRanges.size()), HCCL_E_INTERNAL);

        // 获取缓存的和当前的memory ranges
        const OpUnfoldMemRange& cachedMemRange = cachedMemRanges[rankId];
        const OpUnfoldMemRange& curMemRange = curMemRanges[rankId];
        HCCL_DEBUG("[OpUnfoldCacheEntry][RefreshSqeAddr] cachedMemRange: isValid[%u] baseAddr[0x%016llx] memSize[%llu]; curMemRange: isValid[%u] baseAddr[0x%016llx] memSize[%llu]",
            cachedMemRange.isValid, cachedMemRange.baseAddr, cachedMemRange.memSize, curMemRange.isValid, curMemRange.baseAddr, curMemRange.memSize);

        // 对应rank下一定有user memory, 且对应SQE的addr字段一定在user memory range内, 才需要调用本函数刷新addr
        bool isInRange = false;
        CHK_RET(cachedMemRange.InRange(sqeAddr, isInRange));
        CHK_PRT_RET(!isInRange,
            HCCL_ERROR("[OpUnfoldCacheEntry][RefreshSqeAddr] sqeAddr[0x%016llx] not in the range of cachedMemRange[0x%016llx, 0x%016llx)",
                sqeAddr, cachedMemRange.baseAddr, cachedMemRange.baseAddr + cachedMemRange.memSize),
            HCCL_E_INTERNAL);

        // 刷新SQE addr
        const uint64_t offset = sqeAddr - cachedMemRange.baseAddr; // 计算缓存的sqe addr相对于缓存的base addr的offset
        sqeAddr = curMemRange.baseAddr + offset; // 用当前的base addr更新sqe addr

        return HCCL_SUCCESS;
    }

}; // namespace hccl