# -----------------------------------------------------------------------------------------------------------
# Copyright (c) 2025 Huawei Technologies Co., Ltd.
# This program is free software, you can redistribute it and/or modify it under the terms and conditions of
# CANN Open Software License Agreement Version 2.0 (the "License").
# Please refer to the License for details. You may not use this file except in compliance with the License.
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
# See LICENSE in the root of the software repository for the full text of the License.
# -----------------------------------------------------------------------------------------------------------
set(src_list
    dispatcher_common.cc
    dispatcher_virtural.cc
    dispatcher.cc
    task_logic_info.cc
)

set(src_list_extend
    dispatcher_aicpu.cc
)

target_sources(hccl_plf PRIVATE
    dispatcher_graph.cc
    ${src_list}
)

target_sources(hccd PRIVATE
    dispatcher.cc
)

target_sources(ccl_kernel_plf PRIVATE
    ${src_list}
    ${src_list_extend}
)

target_sources(ccl_kernel_plf_a  PRIVATE
    ${src_list}
    ${src_list_extend}
)

add_subdirectory(rtsq_interact)