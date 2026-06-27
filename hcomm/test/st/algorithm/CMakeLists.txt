# -----------------------------------------------------------------------------------------------------------
# Copyright (c) 2025 Huawei Technologies Co., Ltd.
# This program is free software, you can redistribute it and/or modify it under the terms and conditions of
# CANN Open Software License Agreement Version 2.0 (the "License").
# Please refer to the License for details. You may not use this file except in compliance with the License.
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
# See LICENSE in the root of the software repository for the full text of the License.
# -----------------------------------------------------------------------------------------------------------
cmake_minimum_required(VERSION 3.16.0)

set(CMAKE_CXX_STANDARD 14)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

set(HCOMM_ALG_TC_ROOT    ${CMAKE_CURRENT_SOURCE_DIR}/testcase)
set(HCOMM_ALG_UTILS_ROOT ${CMAKE_CURRENT_SOURCE_DIR}/utils)

set(HCOMM_CODE_ROOT      ${CMAKE_CURRENT_SOURCE_DIR}/../../..)
set(HCOMM_CODE_COMMON    ${HCOMM_CODE_ROOT}/src/common)
set(HCOMM_CODE_PLATFORM  ${HCOMM_CODE_ROOT}/src/platform)
set(HCOMM_CODE_ALGORITHM ${HCOMM_CODE_ROOT}/src/algorithm)
set(HCOMM_CODE_FRAMEWORK ${HCOMM_CODE_ROOT}/src/framework)

set(THIRD_PARTY_PATH   ${HCOMM_CODE_ROOT}/output/third_party)
set(PROTO_SOURCE_DIR   ${THIRD_PARTY_PATH}/protobuf/lib64)
set(PROTOC_PROGRAM     ${THIRD_PARTY_PATH}/protobuf/bin/protoc)

# Include List
set(ASCEND_CANN_INCLUDE_LIST
    ${ASCEND_CANN_PACKAGE_PATH}/pkg_inc
    ${ASCEND_CANN_PACKAGE_PATH}/pkg_inc/base
    ${ASCEND_CANN_PACKAGE_PATH}/pkg_inc/hccl
    ${ASCEND_CANN_PACKAGE_PATH}/pkg_inc/trace
    ${ASCEND_CANN_PACKAGE_PATH}/pkg_inc/runtime
    ${ASCEND_CANN_PACKAGE_PATH}/pkg_inc/runtime/runtime
    ${ASCEND_CANN_PACKAGE_PATH}/pkg_inc/profiling
    ${ASCEND_CANN_PACKAGE_PATH}/include
    ${ASCEND_CANN_PACKAGE_PATH}/include/driver
    ${ASCEND_CANN_PACKAGE_PATH}/include/mmpa
    ${ASCEND_CANN_PACKAGE_PATH}/include/toolchain
    ${ASCEND_CANN_PACKAGE_PATH}/include/experiment/metadef
    ${ASCEND_CANN_PACKAGE_PATH}/asc/include
    ${ASCEND_CANN_PACKAGE_PATH}/asc/include/basic_api
    ${ASCEND_CANN_PACKAGE_PATH}/asc/impl/basic_api
)

set(UTILS_PUBLIC_INCLUDE_LIST
    ${HCOMM_ALG_UTILS_ROOT}/inc
    ${HCOMM_ALG_UTILS_ROOT}/pub_inc
    ${HCOMM_ALG_UTILS_ROOT}/pub_inc/inc
    ${HCOMM_ALG_UTILS_ROOT}/pub_inc/checker
    ${HCOMM_ALG_UTILS_ROOT}/pub_inc/adapter_v1/aiv
    ${HCOMM_ALG_UTILS_ROOT}/pub_inc/adapter_v1/notify
    ${HCOMM_ALG_UTILS_ROOT}/pub_inc/adapter_v1/stream
    ${HCOMM_ALG_UTILS_ROOT}/pub_inc/adapter_v1/transport
)

set(HCOMM_PUBLIC_INCLUDE_LIST
    ${HCOMM_CODE_ROOT}
    ${HCOMM_CODE_ROOT}/include
    ${HCOMM_CODE_ROOT}/include/hccl
    ${HCOMM_CODE_ROOT}/src/pub_inc
    ${HCOMM_CODE_ROOT}/src/pub_inc/new
    ${HCOMM_CODE_ROOT}/src/pub_inc/inner
)

set(HCOMM_PLATFORM_INCLUDE_LIST
    ${HCOMM_CODE_PLATFORM}/inc
    ${HCOMM_CODE_PLATFORM}/inc/adapter
    ${HCOMM_CODE_PLATFORM}/inc/adapter/host
    ${HCOMM_CODE_PLATFORM}/common
    ${HCOMM_CODE_PLATFORM}/hccp/external_depends/inc/log
)

set(HCOMM_COMMON_INCLUDE_LIST
    ${HCOMM_CODE_COMMON}/stream
    ${HCOMM_CODE_COMMON}/health
    ${HCOMM_CODE_COMMON}/launch_device
    ${HCOMM_CODE_COMMON}/debug/profiling
    ${HCOMM_CODE_COMMON}/debug/profiling/inc
    ${HCOMM_CODE_COMMON}/debug/profiling/inc/host
    ${HCOMM_CODE_COMMON}/debug/config
    ${HCOMM_CODE_COMMON}/debug/launch_device
)

set(HCOMM_ALGORITHM_INCLUDE_LIST
    ${HCOMM_CODE_ALGORITHM}/pub_inc
    ${HCOMM_CODE_ALGORITHM}/base
    ${HCOMM_CODE_ALGORITHM}/base/inc
    ${HCOMM_CODE_ALGORITHM}/base/communicator
    ${HCOMM_CODE_ALGORITHM}/base/communicator/legacy
    ${HCOMM_CODE_ALGORITHM}/base/alg_template
    ${HCOMM_CODE_ALGORITHM}/base/alg_template/component
    ${HCOMM_CODE_ALGORITHM}/base/alg_template/temp_all_gather
    ${HCOMM_CODE_ALGORITHM}/base/alg_template/temp_all_reduce
    ${HCOMM_CODE_ALGORITHM}/base/alg_template/temp_alltoall
    ${HCOMM_CODE_ALGORITHM}/base/alg_template/temp_alltoallv
    ${HCOMM_CODE_ALGORITHM}/base/alg_template/temp_reduce_scatter
    ${HCOMM_CODE_ALGORITHM}/base/alg_template/temp_reduce
    ${HCOMM_CODE_ALGORITHM}/base/alg_template/temp_scatter
    ${HCOMM_CODE_ALGORITHM}/base/alg_template/temp_broadcast
    ${HCOMM_CODE_ALGORITHM}/utils/inc
    ${HCOMM_CODE_ALGORITHM}/impl
    ${HCOMM_CODE_ALGORITHM}/impl/inc
    ${HCOMM_CODE_ALGORITHM}/impl/task
    ${HCOMM_CODE_ALGORITHM}/impl/legacy
    ${HCOMM_CODE_ALGORITHM}/impl/operator
    ${HCOMM_CODE_ALGORITHM}/impl/operator/registry
    ${HCOMM_CODE_ALGORITHM}/impl/coll_executor
    ${HCOMM_CODE_ALGORITHM}/impl/coll_executor/registry
    ${HCOMM_CODE_ALGORITHM}/impl/coll_executor/coll_all_gather
    ${HCOMM_CODE_ALGORITHM}/impl/coll_executor/coll_all_gather_v
    ${HCOMM_CODE_ALGORITHM}/impl/coll_executor/coll_all_reduce
    ${HCOMM_CODE_ALGORITHM}/impl/coll_executor/coll_all_to_all
    ${HCOMM_CODE_ALGORITHM}/impl/coll_executor/coll_broadcast
    ${HCOMM_CODE_ALGORITHM}/impl/coll_executor/coll_reduce
    ${HCOMM_CODE_ALGORITHM}/impl/coll_executor/coll_reduce_scatter
    ${HCOMM_CODE_ALGORITHM}/impl/coll_executor/coll_reduce_scatter_v
    ${HCOMM_CODE_ALGORITHM}/impl/coll_executor/coll_scatter
    ${HCOMM_CODE_ALGORITHM}/impl/coll_executor/coll_send_receive
    ${HCOMM_CODE_ALGORITHM}/impl/resource_manager
)

set(HCOMM_FRAMEWORK_INCLUDE_LIST
    ${HCOMM_CODE_FRAMEWORK}
    ${HCOMM_CODE_FRAMEWORK}/inc
    ${HCOMM_CODE_FRAMEWORK}/inc/host
    ${HCOMM_CODE_FRAMEWORK}/common/src
    ${HCOMM_CODE_FRAMEWORK}/common/src/mgr
    ${HCOMM_CODE_FRAMEWORK}/common/src/task
    ${HCOMM_CODE_FRAMEWORK}/common/src/topo
    ${HCOMM_CODE_FRAMEWORK}/common/src/config
    ${HCOMM_CODE_FRAMEWORK}/communicator/impl
    ${HCOMM_CODE_FRAMEWORK}/communicator/impl/resource_manager
    ${HCOMM_CODE_FRAMEWORK}/communicator/impl/independent_op
    ${HCOMM_CODE_FRAMEWORK}/communicator/impl/independent_op/channel
    ${HCOMM_CODE_FRAMEWORK}/communicator/impl/independent_op/rank_graph
    ${HCOMM_CODE_FRAMEWORK}/communicator/impl/independent_op/resource/engine
)

add_subdirectory(testcase)
add_subdirectory(utils)
