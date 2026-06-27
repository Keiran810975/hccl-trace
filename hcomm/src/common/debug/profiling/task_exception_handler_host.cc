/**
 * Copyright (c) 2025 Huawei Technologies Co., Ltd.
 * This program is free software, you can redistribute it and/or modify it under the terms and conditions of
 * CANN Open Software License Agreement Version 2.0 (the "License").
 * Please refer to the License for details. You may not use this file except in compliance with the License.
 * THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
 * INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
 * See LICENSE in the root of the software repository for the full text of the License.
 */

#include <sstream>
#include <iostream>
#include <cstdint>
#include <iomanip>
#include <array>
#include "adapter_rts_common.h"
#include "externalinput_pub.h"
#include "config_log.h"
#include "sal_pub.h"
#include "../../../algorithm/pub_inc/common.h"
#include "task_exception_handler.h"
#include "adump_api.h"

using namespace hccl;

void TaskExceptionHandler::DumpAivPrintWorkSpace(const std::shared_ptr<std::deque<TaskInfo>> &taskQue)
{
    constexpr u64 MEM_SIZE_1M = 1024 * 1024;
    bool isAivOpsExc = UNLIKELY(GetDebugConfig() & HCCL_AIV_OPS_EXC);
    bool enableSync = false;

    // 配置AIV_OPS_EXC时，打印printf、assert内容；当前算子和前一个算子共2M；tag为奇数存放在AIV outBuffer后1M，否则后2M
    // 未配置AIV_OPS_EXC时，只打印assert内容，存放在AIV outBuffer后1M
    u64 dumpSize = MEM_SIZE_1M;
    u32 dumpAivCount = isAivOpsExc ? 2 : 1;
    char printBuffer[2 * dumpSize];
    setvbuf(stdout, printBuffer, _IOFBF, sizeof(printBuffer));
    for (auto it = taskQue->end()-1;it >= taskQue->begin(); --it) {
        if (!it->isAlgInfo) {
            continue;
        }
        if (dumpAivCount <= 0) {
            break;
        }
        auto taskInfo = *it;
        auto aivParam = taskInfo.taskPara.Aiv;
        auto tag = aivParam.tag;
        u64 offset = isAivOpsExc ? (tag & 1 ? 3 * MEM_SIZE_1M : 4 * MEM_SIZE_1M) : 3 * MEM_SIZE_1M;
        void *workSpaceAddr = reinterpret_cast<void*>(reinterpret_cast<uintptr_t>(aivParam.flagMem) + offset);
        Adx::AdumpPrintWorkSpace(workSpaceAddr, dumpSize, nullptr, taskInfo.tag.c_str(), enableSync);
        HCCL_INFO("[TaskExceptionHandler][%s]AdumpPrintWorkSpace success. workSpaceAddr[%p], dumpSize[%llu], "
            "aiv tag[%u], op tag[%s]", __func__, workSpaceAddr, dumpSize, tag, taskInfo.tag.c_str());
        dumpAivCount--;
    }
    fflush(stdout);
    // 异常信息非空字符串，通过ERROR日志打印
    if (std::string(printBuffer).find_first_not_of(" \t\n\r\f\v") != std::string::npos) {
        HCCL_ERROR("[TaskExceptionHandler][%s]AdumpPrintAivInfo: %s", __func__, printBuffer);
    }
}