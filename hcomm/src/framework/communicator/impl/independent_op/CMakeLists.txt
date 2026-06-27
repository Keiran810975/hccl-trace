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
    ${CMAKE_CURRENT_SOURCE_DIR}/hccl_independent_op_ctx.cc
    ${CMAKE_CURRENT_SOURCE_DIR}/independent_op_context_manager.cc
    ${CMAKE_CURRENT_SOURCE_DIR}/hccl_independent_op_mem.cc
    ${CMAKE_CURRENT_SOURCE_DIR}/independent_op.cc
    ${CMAKE_CURRENT_SOURCE_DIR}/hccl_independent_op_channel.cc
    ${CMAKE_CURRENT_SOURCE_DIR}/reg_mem_manager.cc
    ${CMAKE_CURRENT_SOURCE_DIR}/comm_mem_manager.cc
    ${CMAKE_CURRENT_SOURCE_DIR}/hccl_independent_rank_graph.cc
    ${CMAKE_CURRENT_SOURCE_DIR}/hccl_independent_op_engine.cc
)
 
target_sources(hcomm PRIVATE
    ${src_list}
)

add_subdirectory(channel)
add_subdirectory(data_api)
add_subdirectory(resource)
add_subdirectory(rank_graph)
add_subdirectory(device)
add_subdirectory(diag)
