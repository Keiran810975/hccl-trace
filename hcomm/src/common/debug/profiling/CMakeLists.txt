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
    ${CMAKE_CURRENT_SOURCE_DIR}/task_profiling.cc
    ${CMAKE_CURRENT_SOURCE_DIR}/task_semantic_trace.cc
    ${CMAKE_CURRENT_SOURCE_DIR}/task_exception_handler.cc
    ${CMAKE_CURRENT_SOURCE_DIR}/task_exception_handler_host.cc
    ${CMAKE_CURRENT_SOURCE_DIR}/profiler_base.cc
    ${CMAKE_CURRENT_SOURCE_DIR}/plugin_runner.cc
    ${CMAKE_CURRENT_SOURCE_DIR}/plugin_runner_host.cc
    ${CMAKE_CURRENT_SOURCE_DIR}/command_handle.cc
    ${CMAKE_CURRENT_SOURCE_DIR}/profiling_manager.cc
    ${CMAKE_CURRENT_SOURCE_DIR}/task_overflow.cc
    ${CMAKE_CURRENT_SOURCE_DIR}/profiler_manager_impl.cc
    ${CMAKE_CURRENT_SOURCE_DIR}/profiler_manager.cc
    ${CMAKE_CURRENT_SOURCE_DIR}/profiling_manager_pub.cc
    ${CMAKE_CURRENT_SOURCE_DIR}/adapter_prof.cc
    ${CMAKE_CURRENT_SOURCE_DIR}/dlprof_function.cc
    ${CMAKE_CURRENT_SOURCE_DIR}/dlrt_function.cc
)
 
target_sources(hccl_alg PRIVATE
    ${src_list}
)
