/*
 * This program is free software, you can redistribute it and/or modify it.
 * Copyright (c) 2025 Huawei Technologies Co., Ltd.
 * This file is a part of the CANN Open Software.
 * Licensed under CANN Open Software License Agreement Version 2.0 (the "License").
 * Please refer to the License for details. You may not use this file except in compliance with the License.
 * THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
 * See LICENSE in the root of the software repository for the full text of the License.
 */

#include <sstream>

#include "op_unfold_key.h"

#include "log.h"

namespace hccl {
    OpUnfoldKey::OpUnfoldKey()
        : opType(HcclCMDType::HCCL_CMD_INVALID), dataType(HcclDataType::HCCL_DATA_TYPE_RESERVED), reduceType(HcclReduceOp::HCCL_REDUCE_RESERVED), isZeroCopy(false), inputSize(0), isInplacePreSync(false), workflowMode(HcclWorkflowMode::HCCL_WORKFLOW_MODE_RESERVED) {
    }

    OpUnfoldKey::OpUnfoldKey(const OpUnfoldKey& other)
        : opType(other.opType), dataType(other.dataType), reduceType(other.reduceType), isZeroCopy(other.isZeroCopy), inputSize(other.inputSize), isInplacePreSync(other.isInplacePreSync), workflowMode(other.workflowMode) {
        CHK_PRT_CONT(opType == HcclCMDType::HCCL_CMD_INVALID, HCCL_ERROR("[OpUnfoldKey][OpUnfoldKey] opType is invalid"));
        CHK_PRT_CONT(dataType == HcclDataType::HCCL_DATA_TYPE_RESERVED, HCCL_ERROR("[OpUnfoldKey][OpUnfoldKey] dataType is reserved"));
        CHK_PRT_CONT(workflowMode == HcclWorkflowMode::HCCL_WORKFLOW_MODE_RESERVED, HCCL_ERROR("[[OpUnfoldKey][OpUnfoldKey]] workflowMode is reserved"));

        // 注意: 当算子不涉及reduce操作时, reduceType为HcclReduceOp::HCCL_REDUCE_RESERVED
    }

    HcclResult OpUnfoldKey::Init(const HcclCMDType curOpType, const HcclDataType curDataType, const HcclReduceOp curReduceType, const bool curIsZeroCopy, const uint64_t curInputSize, const bool curIsInplacePreSync, const HcclWorkflowMode curWorkflowMode) {
        CHK_PRT_RET(curOpType == HcclCMDType::HCCL_CMD_INVALID, HCCL_ERROR("[OpUnfoldKey][Init] opType is invalid"), HCCL_E_INTERNAL);
        CHK_PRT_RET(curDataType == HcclDataType::HCCL_DATA_TYPE_RESERVED, HCCL_ERROR("[OpUnfoldKey][Init] dataType is reserved"), HCCL_E_INTERNAL);
        CHK_PRT_RET(curWorkflowMode == HcclWorkflowMode::HCCL_WORKFLOW_MODE_RESERVED, HCCL_ERROR("[[OpUnfoldKey][Init]] workflowMode is reserved"), HCCL_E_INTERNAL);

        // 注意: 当算子不涉及reduce操作时, reduceType为HcclReduceOp::HCCL_REDUCE_RESERVED
        
        opType = curOpType;
        dataType = curDataType;
        reduceType = curReduceType;
        isZeroCopy = curIsZeroCopy;
        inputSize = curInputSize;
        isInplacePreSync = curIsInplacePreSync;
        workflowMode = curWorkflowMode;

        return HCCL_SUCCESS;
    }

    std::string OpUnfoldKey::getKeyString() const {
        std::ostringstream oss;
        oss << "opType" << static_cast<uint32_t>(opType)
            << "-dataType" << static_cast<uint32_t>(dataType)
            << "-reduceType" << static_cast<uint32_t>(reduceType)
            << "-isZeroCopy" << isZeroCopy
            << "-inputSize" << inputSize
            << "-isInplacePreSync" << isInplacePreSync
            << "-workflowMode" << static_cast<uint32_t>(workflowMode);
        return oss.str();
    }

    bool OpUnfoldKey::operator==(const OpUnfoldKey& other) const {
        return opType == other.opType &&
            dataType == other.dataType &&
            reduceType == other.reduceType &&
            isZeroCopy == other.isZeroCopy &&
            inputSize == other.inputSize &&
            isInplacePreSync == other.isInplacePreSync &&
            workflowMode == other.workflowMode;
    }

    const OpUnfoldKey& OpUnfoldKey::operator=(const OpUnfoldKey& other) {
        if (this != &other) {
            this->opType = other.opType;
            this->dataType = other.dataType;
            this->reduceType = other.reduceType;
            this->isZeroCopy = other.isZeroCopy;
            this->inputSize = other.inputSize;
            this->isInplacePreSync = other.isInplacePreSync;
            this->workflowMode = other.workflowMode;
        }
        return *this;
    }

}; // namespace hccl