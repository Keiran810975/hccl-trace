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
project(hccl_alg)

set(CMAKE_VERBOSE_MAKEFILE ON)

add_library(hccl_alg SHARED)

if(BUILD_OPEN_PROJECT)
    set(HCCL_BASE_DIR ${CMAKE_CURRENT_SOURCE_DIR}/../)
    message(STATUS "AlG HCCL_BASE_DIR = ${HCCL_BASE_DIR}")
else()
    set(HCCL_BASE_DIR ${TOP_DIR}/hcomm/src/)
    message(STATUS "AlG HCCL_BASE_DIR = ${HCCL_BASE_DIR}")
endif()

target_include_directories(hccl_alg PRIVATE
    ${CMAKE_CURRENT_SOURCE_DIR}/base/inc
    ${HCCL_BASE_DIR}/pub_inc

    ${CMAKE_CURRENT_SOURCE_DIR}/base/alg_aiv_template
    ${CMAKE_CURRENT_SOURCE_DIR}/base/alg_template
    ${CMAKE_CURRENT_SOURCE_DIR}/base/alg_template/component/
    ${CMAKE_CURRENT_SOURCE_DIR}/base/alg_template/temp_all_gather
    ${CMAKE_CURRENT_SOURCE_DIR}/base/alg_template/temp_all_reduce
    ${CMAKE_CURRENT_SOURCE_DIR}/base/alg_template/temp_alltoall
    ${CMAKE_CURRENT_SOURCE_DIR}/base/alg_template/temp_alltoallv
    ${CMAKE_CURRENT_SOURCE_DIR}/base/alg_template/temp_broadcast
    ${CMAKE_CURRENT_SOURCE_DIR}/base/alg_template/temp_reduce
    ${CMAKE_CURRENT_SOURCE_DIR}/base/alg_template/temp_reduce_scatter
    ${CMAKE_CURRENT_SOURCE_DIR}/base/alg_template/temp_scatter
    ${CMAKE_CURRENT_SOURCE_DIR}/base/mc2_handler
    ${CMAKE_CURRENT_SOURCE_DIR}/base/communicator
    ${CMAKE_CURRENT_SOURCE_DIR}/base/communicator/legacy
    ${CMAKE_CURRENT_SOURCE_DIR}/impl
    ${CMAKE_CURRENT_SOURCE_DIR}/impl/inc
    ${CMAKE_CURRENT_SOURCE_DIR}/impl/legacy
    ${CMAKE_CURRENT_SOURCE_DIR}/impl/legacy/operator
    ${CMAKE_CURRENT_SOURCE_DIR}/impl/resource_manager
    ${CMAKE_CURRENT_SOURCE_DIR}/impl/task
    ${CMAKE_CURRENT_SOURCE_DIR}/impl/operator
    ${CMAKE_CURRENT_SOURCE_DIR}/impl/operator/registry
    ${CMAKE_CURRENT_SOURCE_DIR}/impl/coll_executor
    ${CMAKE_CURRENT_SOURCE_DIR}/impl/coll_executor/registry
    ${CMAKE_CURRENT_SOURCE_DIR}/impl/coll_executor/coll_send_receive
    ${CMAKE_CURRENT_SOURCE_DIR}/impl/coll_executor/coll_all_reduce
    ${CMAKE_CURRENT_SOURCE_DIR}/impl/coll_executor/coll_all_reduce/310P
    ${CMAKE_CURRENT_SOURCE_DIR}/impl/coll_executor/coll_all_to_all
    ${CMAKE_CURRENT_SOURCE_DIR}/impl/coll_executor/coll_all_gather
    ${CMAKE_CURRENT_SOURCE_DIR}/impl/coll_executor/coll_all_gather/310P
    ${CMAKE_CURRENT_SOURCE_DIR}/impl/coll_executor/coll_all_gather_v
    ${CMAKE_CURRENT_SOURCE_DIR}/impl/coll_executor/coll_all_gather_v/310P
    ${CMAKE_CURRENT_SOURCE_DIR}/impl/coll_executor/coll_reduce_scatter
    ${CMAKE_CURRENT_SOURCE_DIR}/impl/coll_executor/coll_reduce_scatter/310P
    ${CMAKE_CURRENT_SOURCE_DIR}/impl/coll_executor/coll_reduce_scatter_v
    ${CMAKE_CURRENT_SOURCE_DIR}/impl/coll_executor/coll_reduce_scatter_v/310P
    ${CMAKE_CURRENT_SOURCE_DIR}/impl/coll_executor/coll_scatter
    ${CMAKE_CURRENT_SOURCE_DIR}/impl/coll_executor/coll_broadcast
    ${CMAKE_CURRENT_SOURCE_DIR}/impl/coll_executor/coll_broadcast/310P
    ${CMAKE_CURRENT_SOURCE_DIR}/pub_inc
    ${CMAKE_CURRENT_SOURCE_DIR}/../common/health
    ${CMAKE_CURRENT_SOURCE_DIR}/../common/debug/profiling/inc
    ${CMAKE_CURRENT_SOURCE_DIR}/../common/debug/profiling/inc/host
    ${CMAKE_CURRENT_SOURCE_DIR}/../common/debug/config
    ${CMAKE_CURRENT_SOURCE_DIR}/../common/stream/
    ${CMAKE_CURRENT_SOURCE_DIR}/../common/launch_device
    ${HCCL_BASE_DIR}/framework/common/src/config
    ${HCCL_BASE_DIR}/framework/inc/
    ${CMAKE_CURRENT_SOURCE_DIR}/../framework/common/src/config
)

if(BUILD_OPEN_PROJECT)
    target_compile_definitions(hccl_alg PRIVATE
        OPEN_BUILD_PROJECT
        LOG_CPP)

    target_include_directories(hccl_alg PRIVATE
        ${CMAKE_CURRENT_SOURCE_DIR}/../pub_inc
        ${CMAKE_CURRENT_SOURCE_DIR}/../../include
        ${CMAKE_CURRENT_SOURCE_DIR}/../../include/hccl
        ${CMAKE_CURRENT_SOURCE_DIR}/../../pub_inc
        ${CMAKE_CURRENT_SOURCE_DIR}/../../pkg_inc
        ${CMAKE_CURRENT_SOURCE_DIR}/../../pkg_inc/hccl

        # runtime头文件
        ${ASCEND_CANN_PACKAGE_PATH}/include/
        ${ASCEND_CANN_PACKAGE_PATH}/include/base/
        ${ASCEND_CANN_PACKAGE_PATH}/include/driver/
        ${ASCEND_CANN_PACKAGE_PATH}/include/dump/
        ${ASCEND_CANN_PACKAGE_PATH}/include/external/
        ${ASCEND_CANN_PACKAGE_PATH}/include/platform/

        # mmpa头文件
        ${ASCEND_CANN_PACKAGE_PATH}/include/mmpa/

        # acl头文件
        ${ASCEND_CANN_PACKAGE_PATH}/include/acl/

        # driver头文件
        ${ASCEND_CANN_PACKAGE_PATH}/include/driver/

        # 包间接口
        ${ASCEND_CANN_PACKAGE_PATH}/pkg_inc/
        ${ASCEND_CANN_PACKAGE_PATH}/pkg_inc/runtime/
        ${ASCEND_CANN_PACKAGE_PATH}/pkg_inc/profiling/
        ${ASCEND_CANN_PACKAGE_PATH}/pkg_inc/base/
        ${ASCEND_CANN_PACKAGE_PATH}/pkg_inc/dump/
        ${ASCEND_CANN_PACKAGE_PATH}/pkg_inc/trace/

        ${THIRD_PARTY_NLOHMANN_PATH}
    )

    target_link_directories(hccl_alg PRIVATE
        ${ASCEND_CANN_PACKAGE_PATH}/lib64
    )
else()
    target_include_directories(hccl_alg PRIVATE
        ${TOP_DIR}/abl/msprof/inc
        ${TOP_DIR}/abl/adump/inc/adump
        ${TOP_DIR}/ace/npuruntime/inc
        ${TOP_DIR}/metadef/pkg_inc
        ${TOP_DIR}/metadef/inc/external/
	${TOP_DIR}/metadef/pkg_inc
        ${TOP_DIR}/ace/npuruntime/inc/runtime
        ${TOP_DIR}/open_source/json/include
        ${TOP_DIR}/runtime/include/external
    )
endif()

target_compile_definitions(hccl_alg PRIVATE
    $<$<STREQUAL:${PRODUCT_SIDE},host>:_GLIBCXX_USE_CXX11_ABI=0>
)

target_compile_options(hccl_alg PRIVATE
    -Werror
    -fno-common
    -fno-strict-aliasing
    -pipe
    -O3
    -std=c++14
    -fstack-protector-all
    $<$<CONFIG:Debug>:-g>
)

target_link_options(hccl_alg PRIVATE
    -Wl,-z,relro
    -Wl,-z,now
    -Wl,-z,noexecstack
    -s
)

if(BUILD_OPEN_PROJECT)
    target_link_libraries(hccl_alg PRIVATE
        -Wl,--no-as-needed
        c_sec
        unified_dlog
        mmpa
        -Wl,--no-as-needed
        hccl_plf
    )
else()
    target_link_libraries(hccl_alg PRIVATE
        -Wl,--no-as-needed
        c_sec
        unified_dlog
        mmpa
        -Wl,--no-as-needed
        hccl_plf
        ofed_headers
    )
endif()

add_subdirectory(base)
add_subdirectory(impl)

install(TARGETS hccl_alg
    LIBRARY DESTINATION ${INSTALL_LIBRARY_DIR} OPTIONAL
)

if(NOT BUILD_OPEN_PROJECT)
    install_package(
        PACKAGE hccl
        TARGETS hccl_alg
    )
endif()
