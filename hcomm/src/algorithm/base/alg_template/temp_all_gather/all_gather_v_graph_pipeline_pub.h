/*
* Copyright (c) Huawei Technologies Co., Ltd. 2025-2025. All Rights Reserved.
* This file is a part of the CANN Open Software.
* Licensed under CANN Open Software License Agreement Version 2.0 (the "License").
* Please refer to the License for details. You may not use this file except in compliance with the License.
* THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
* INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
* See LICENSE in the root of the software repository for the full text of the License.
*/

#ifndef ALL_GATHER_V_GRAPH_PIPELINE_PUB_H
#define ALL_GATHER_V_GRAPH_PIPELINE_PUB_H

#include <vector>
#include <memory>
#include <hccl/hccl_types.h>
#include "hccl/base.h"
#include "externalinput_pub.h"
#include "mem_device_pub.h"
#include "stream_pub.h"
#include "all_gather_v_pipeline_pub.h"

namespace hccl {
class AllGatherVGraphPipeline : public AllGatherVPipeline {
public:
    explicit AllGatherVGraphPipeline(const HcclDispatcher dispatcher);
    ~AllGatherVGraphPipeline() override = default;
    HcclResult RunAsync() override;
private:
    HcclResult ExecInterServer(u32 step);
    HcclResult ExecIntraServer(u32 step);
};
}  // namespace hccl

#endif /* ALL_GATHER_PIPELINE_PUB_H */