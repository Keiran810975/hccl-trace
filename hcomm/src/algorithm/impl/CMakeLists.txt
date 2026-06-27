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
    ${CMAKE_CURRENT_SOURCE_DIR}/hccl_alg.cc
    ${CMAKE_CURRENT_SOURCE_DIR}/topo_matcher.cc
    ${CMAKE_CURRENT_SOURCE_DIR}/coll_alg_utils.cc
    ${CMAKE_CURRENT_SOURCE_DIR}/alg_configurator.cc
    ${CMAKE_CURRENT_SOURCE_DIR}/hccl_aiv.cc
    ${CMAKE_CURRENT_SOURCE_DIR}/alg_env_config.cc
    ${CMAKE_CURRENT_SOURCE_DIR}/hccl_aiv_host.cc
)

target_sources(hccl_alg PRIVATE
    ${src_list}
)

add_subdirectory(resource_manager)
add_subdirectory(task)
add_subdirectory(operator)
add_subdirectory(coll_executor)
add_subdirectory(legacy)