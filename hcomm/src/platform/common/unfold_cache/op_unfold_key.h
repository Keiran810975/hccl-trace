/*
 * This program is free software, you can redistribute it and/or modify it.
 * Copyright (c) 2025 Huawei Technologies Co., Ltd.
 * This file is a part of the CANN Open Software.
 * Licensed under CANN Open Software License Agreement Version 2.0 (the "License").
 * Please refer to the License for details. You may not use this file except in compliance with the License.
 * THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
 * See LICENSE in the root of the software repository for the full text of the License.
 */

#ifndef __OP_UNFOLD_KEY_H__
#define __OP_UNFOLD_KEY_H__

#include <cstdint>
#include <functional>
#include <string>

#include "hccl_types.h"
#include "workflow_pub.h"

namespace hccl {

// 作为展开算子的标识符
// 注意: 由于给定通信域下, 相同数据量相同算子的算法选择是固定的, 不需要在标识符中维护algType或algName
// 注意: 图模式或单算子模式是全局固定的, 不需要在标识符中维护
struct OpUnfoldKey{
    explicit OpUnfoldKey();
    explicit OpUnfoldKey(const OpUnfoldKey& other); // 拷贝构造函数 (make_pair需要)

    HcclResult Init(const HcclCMDType curOpType, const HcclDataType curDataType, const HcclReduceOp curReduceType, const bool curIsZeroCopy, const uint64_t curInputSize, const bool curIsInplacePreSync, const HcclWorkflowMode curWorkflowMode);

    // 用于debug
    std::string getKeyString() const;

    bool operator==(const OpUnfoldKey& other) const; // 重载operator==用于std::unordered_map中相等比较
    const OpUnfoldKey& operator=(const OpUnfoldKey& other); // 拷贝赋值操作符

    HcclCMDType opType;
    HcclDataType dataType;
    HcclReduceOp reduceType;
    bool isZeroCopy;

    // inputSize和outputSize是由totalCount(由rankSize+count决定)+dataType决定的, 给定通信域rankSize是固定的
    // 因为已经维护dataType, 所以inputSize/outputSize/totalCount中只需要维护任意一个即可
    uint64_t inputSize;

    // ReduceScatter和AllReduce在开启重执行、in-place update、userMem < HcclBuffSize的时候，会触发前同步 (与正常算子展开逻辑不同)
    bool isInplacePreSync;

    // 是否为图模式 (可能存在同一个通信域下的同一个算子, 既执行图模式又执行单算子模式下的算法)
    HcclWorkflowMode workflowMode; // 0: 图模式; 1: 单算子模式
};

}; // namespace hccl

namespace std {

// 全特化std::hash<OpUnfoldKey>, 用于std::unordered_map中计算哈希值
template<>
struct hash<hccl::OpUnfoldKey> {
    size_t operator()(const hccl::OpUnfoldKey& key) const {
        // 使用std::hash计算key中每个字段的哈希值
        std::hash<bool> hashBool;
        std::hash<uint8_t> hashUint8;
        std::hash<uint64_t> hashUint64;

        // 假设opType/dataType/reduceType <= 255
        const size_t opTypeHashValue = hashUint8(static_cast<uint8_t>(key.opType));
        const size_t dataTypeHashValue = hashUint8(static_cast<uint8_t>(key.dataType));
        const size_t reduceTypeHashValue = hashUint8(static_cast<uint8_t>(key.reduceType));

        const size_t isZeroCopyHashValue = hashBool(key.isZeroCopy);
        const size_t inputSizeHashValue = hashUint64(key.inputSize);
        const size_t isInplacePreSyncHashValue = hashBool(key.isInplacePreSync);

        // 假设workflowMode <= 255
        const size_t workflowModeHashValue = hashUint8(static_cast<uint8_t>(key.workflowMode));

        // 简单的哈希混合
        size_t hashValue = opTypeHashValue;
        hashValue ^= dataTypeHashValue;
        hashValue ^= reduceTypeHashValue;
        hashValue ^= isZeroCopyHashValue;
        hashValue ^= inputSizeHashValue;
        hashValue ^= isInplacePreSyncHashValue;
        hashValue ^= workflowModeHashValue;

        return hashValue;
    }
};

} // namespace std

#endif // __OP_UNFOLD_KEY_H__