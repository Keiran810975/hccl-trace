/*
 * This program is free software, you can redistribute it and/or modify it.
 * Copyright (c) 2025 Huawei Technologies Co., Ltd.
 * This file is a part of the CANN Open Software.
 * Licensed under CANN Open Software License Agreement Version 2.0 (the "License").
 * Please refer to the License for details. You may not use this file except in compliance with the License.
 * THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
 * See LICENSE in the root of the software repository for the full text of the License.
 */

#ifndef __OP_UNFOLD_CACHE_ENTRY_H__
#define __OP_UNFOLD_CACHE_ENTRY_H__

#include <cstdint>
#include <vector>

#include "stream_pub.h"

// 确认ptr应该为空
#define CHK_PTR_NOTNULL(ptr) \
    do { \
        if (UNLIKELY((ptr) != nullptr)) { \
            HCCL_ERROR("[%s] errNo[0x%016llx] ptr[%s] is 0x%016llx (should be null), return HCCL_E_INTERNAL", \
                __func__, HCCL_ERROR_CODE(HCCL_E_INTERNAL), #ptr, (ptr)); \
            return HCCL_E_INTERNAL; \
        } \
    } while (0)

// 确认ptrPtr不应该为空, 但*ptrPtr应该为空
#define CHK_PTRPTR_NULL(ptrPtr) \
    do { \
        CHK_PTR_NULL(ptrPtr); \
        CHK_PTR_NOTNULL(*(ptrPtr)); \
    } while (0)

namespace hccl {

// 记录算子展开的输入/输出的内存范围
// 注意: 内存的分配销毁由外部DeviceMem控制, 这里只是记录基地址和内存大小
struct OpUnfoldMemRange {
    explicit OpUnfoldMemRange();
    explicit OpUnfoldMemRange(const uint64_t curBaseAddr, const uint64_t curMemSize);
    explicit OpUnfoldMemRange(const OpUnfoldMemRange& other);
    ~OpUnfoldMemRange();

    const OpUnfoldMemRange& operator=(const OpUnfoldMemRange& other); // 拷贝赋值操作符

    HcclResult InRange(const uint64_t addr, bool& isInRange) const;

    bool isValid;
    uint64_t baseAddr;
    uint64_t memSize;
};

struct RefreshAddrInfo {
    explicit RefreshAddrInfo();
    explicit RefreshAddrInfo(const uint32_t curRankId, const uint8_t curMemType);
    explicit RefreshAddrInfo(const RefreshAddrInfo& other);
    ~RefreshAddrInfo();

    const RefreshAddrInfo& operator=(const RefreshAddrInfo& other); // 拷贝赋值操作符

    static constexpr uint8_t INVALID_MEMTYPE = 0;
    static constexpr uint8_t USER_INPUT_MEMTYPE = 1;
    static constexpr uint8_t USER_OUTPUT_MEMTYPE = 2;

    uint32_t rankId;
    uint8_t memType; // 0: invalid; 1: user input; 2: user output
};

// 算子展开的动态缓存条目 (每个OpUnfoldKey对应最多一个缓存条目)
class OpUnfoldCacheEntry {
public:
    OpUnfoldCacheEntry() = delete;
    explicit OpUnfoldCacheEntry(const std::vector<OpUnfoldMemRange>& userInputMemRanges, const std::vector<OpUnfoldMemRange>& userOutputMemRanges);
    ~OpUnfoldCacheEntry();

    HcclResult GetSqeArrayCount(size_t& sqeArrayCount) const;

    // 缓存不命中下的函数

    // 分成两次函数调用是为了即使算子第一次展开的SQE存在placeholder, 一次LaunchTask下发的SQE仍然能够缓存在连续内存中, 减少后续cache hit的开销
    HcclResult AllocSqeArray(const size_t sqeCount, const int32_t streamId, size_t& arrayIdx); // 分配成功会将arrayIdx设置为分配的SQE数组在sqeArrays_当中的索引
    HcclResult MemcpySqeArray(const size_t arrayIdx, const size_t sqeStartIdx, const size_t sqeCount, const uint8_t *sqeArray, const uint8_t *sqeTypeArray, const AicpuDfxInfo *sqeDfxInfoArray); // 将sqeArray memcpy到sqeArrays_[arrayIdx][sqeStartIdx:sqeStartIdx+sqeCount-1]

    // 根据streamId计算streamSeqIdx
    HcclResult CalcStreamSeqIdxes(Stream& mainStream, std::vector<Stream>& slaveStreams);

    // 缓存命中下的函数

    // 更新指定的一段连续SQE, 并将相关信息设置给对应指针, 用于后续下发task到RTSQ
    HcclResult UpdateAndGetSqeArray(const size_t arrayIdx, const std::vector<OpUnfoldMemRange>& curUserInputMemRanges, const std::vector<OpUnfoldMemRange>& curUserOutputMemRanges, Stream& mainStream, std::vector<Stream> &slaveStreams, const uint32_t opRingBufferIdx, size_t& sqeCount, uint8_t **sqeArrayPtr, uint8_t **sqeTypeArrayPtr, AicpuDfxInfo **sqeDfxInfoArrayPtr, Stream **streamPtrPtr, std::vector<size_t>& largestSqeIdxes, const bool profL1Enable, std::vector<uint64_t>& profTimestamps); // largestSqeIdxes指的是该段连续SQE中taskid达到最大值的SQE的索引, 即这些SQE后面需要增加placeholder

    // Cache hit更新并下发entry中所有的SQE后, 由于缓存的SQE的addr-related fields被in-place更新, 需要把userInputMemRanges_/userOutputMemRanges_为当前执行对应的memory ranges
    HcclResult SetInputOutputMemRanges(const std::vector<OpUnfoldMemRange>& curUserInputMemRanges, const std::vector<OpUnfoldMemRange>& curUserOutputMemRanges);

private:
    // 合并两个uint32_t成为一个uint64_t
    inline void CombineUint32ToUint64(uint64_t& addr, const uint32_t high, const uint32_t low) const {
        constexpr uint64_t uintBitWidth = 32;
        addr = (static_cast<uint64_t>(high) << uintBitWidth) | static_cast<uint64_t>(low);
        return;
    }

    // 拆分一个uint64_t成为两个uint32_t
    inline void SplitUint64ToUint32(const uint64_t addr, uint32_t& high, uint32_t& low) const {
        constexpr uint64_t uintBitWidth = 32;
        high = static_cast<uint32_t>(addr >> uintBitWidth);
        low = static_cast<uint32_t>(addr & 0xFFFFFFFFULL);
        return;
    }

    // 缓存不命中下的函数
    HcclResult CheckAndPrepareRefreshAddrInfo(const uint64_t sqeAddr, RefreshAddrInfo& refreshAddrInfo); // 根据range判断sqeAddr是否在某个rankid的input/output user memory范围内, 并相应更新RefreshAddrInfo为后续缓存命中刷新地址做准备

    // 缓存命中下的函数
    HcclResult RefreshSqeAddr(uint64_t &sqeAddr, const uint32_t rankId, const std::vector<OpUnfoldMemRange>& cachedMemRanges, const std::vector<OpUnfoldMemRange>& curMemRanges) const; // 根据range判断是否需要刷新, 根据delta进行刷新

    std::vector<uint8_t *> sqeArrays_; // 多段连续的SQE数组 (每段连续的SQE不超过HCCL_SQE_SIZE * HCCL_PER_LAUNCH_SQE_CNT bytes)
    std::vector<uint8_t *> sqeTypeArrays_; // 每段每个SQE的type
    std::vector<AicpuDfxInfo *>  sqeDfxInfoArrays_; // 每段每个SQE的DfxInfo
    std::vector<int32_t> streamIds_; // 每段SQE对应的actual stream ID
    std::vector<uint32_t> streamSeqIdxes_; // 每段SQE对应的sequential stream index (sequential是指将mainStream + slaveStreams顺序起来看, 0代表mainStream, 1代表slaveStreams[0])
    std::vector<std::vector<RefreshAddrInfo>> srcRefreshAddrInfoArrays_; // 每段每个SQE中dstAddr (if any)对应的刷新信息
    std::vector<std::vector<RefreshAddrInfo>> dstRefreshAddrInfoArrays_; // 每段每个SQE中dstAddr (if any)对应的刷新信息

    std::vector<OpUnfoldMemRange> userInputMemRanges_; // 当前通信域每个rank的user input memory range
    std::vector<OpUnfoldMemRange> userOutputMemRanges_; // 当前通信域每个rank的user output memory range
};

};

#endif // __OP_UNFOLD_CACHE_ENTRY_H__