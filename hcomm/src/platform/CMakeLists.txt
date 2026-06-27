# -----------------------------------------------------------------------------------------------------------
# Copyright (c) 2025 Huawei Technologies Co., Ltd.
# This program is free software, you can redistribute it and/or modify it under the terms and conditions of
# CANN Open Software License Agreement Version 2.0 (the "License").
# Please refer to the License for details. You may not use this file except in compliance with the License.
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
# See LICENSE in the root of the software repository for the full text of the License.
# -----------------------------------------------------------------------------------------------------------
set(CMAKE_VERBOSE_MAKEFILE on)

if(BUILD_OPEN_PROJECT)
    message(STATUS "open CMAKE_CURRENT_SOURCE_DIR = ${CMAKE_CURRENT_SOURCE_DIR}")
    set(HCCL_BASE_DIR ${CMAKE_CURRENT_SOURCE_DIR}/../)
    set(HCCL_INC_DIR ${CMAKE_CURRENT_SOURCE_DIR}/../../include/hccl)
    message(STATUS "open HCCL_INC_DIR = ${HCCL_INC_DIR}")
    set(HCCL_OPEN_CODE_BASE_DIR ${CMAKE_CURRENT_SOURCE_DIR}/../)
    set(HCCL_THIRD_PARTY_DIR ${CMAKE_CURRENT_SOURCE_DIR}/../../../../../../../../)
else()
    message(STATUS "close TOP_DIR = ${TOP_DIR}")
    set(HCCL_BASE_DIR ${TOP_DIR}/hcomm/src/)
    set(HCCL_OPEN_CODE_BASE_DIR ${TOP_DIR}/hcomm/src/)
    set(HCCL_THIRD_PARTY_DIR ${TOP_DIR})
endif()

add_library(hccl_plf  SHARED)

set(platform_include_list
    ${CMAKE_CURRENT_SOURCE_DIR}/../pub_inc
    ${CMAKE_CURRENT_SOURCE_DIR}/../pub_inc/aicpu/
    ${CMAKE_CURRENT_SOURCE_DIR}/../pub_inc/inner
    ${CMAKE_CURRENT_SOURCE_DIR}/../pub_inc/new

    ${CMAKE_CURRENT_SOURCE_DIR}/
    ${CMAKE_CURRENT_SOURCE_DIR}/inc
    ${CMAKE_CURRENT_SOURCE_DIR}/inc/adapter
    ${CMAKE_CURRENT_SOURCE_DIR}/inc/adapter/host
    ${CMAKE_CURRENT_SOURCE_DIR}/task
    ${CMAKE_CURRENT_SOURCE_DIR}/common/
    ${CMAKE_CURRENT_SOURCE_DIR}/common/buffer_manager
    ${CMAKE_CURRENT_SOURCE_DIR}/common/unfold_cache
    ${CMAKE_CURRENT_SOURCE_DIR}/common/p2p_mgmt
    ${CMAKE_CURRENT_SOURCE_DIR}/common/unique
    ${CMAKE_CURRENT_SOURCE_DIR}/common/misc/network_manager
    ${CMAKE_CURRENT_SOURCE_DIR}/common/misc/gradient_segment
    ${CMAKE_CURRENT_SOURCE_DIR}/resource/transport
    ${CMAKE_CURRENT_SOURCE_DIR}/resource/transport/device
    ${CMAKE_CURRENT_SOURCE_DIR}/resource/transport/host
    ${CMAKE_CURRENT_SOURCE_DIR}/resource/transport/heterog
    ${CMAKE_CURRENT_SOURCE_DIR}/resource/transport/onesided
    ${CMAKE_CURRENT_SOURCE_DIR}/resource/transport/onesided/device
    ${CMAKE_CURRENT_SOURCE_DIR}/resource/mem
    ${CMAKE_CURRENT_SOURCE_DIR}/resource/dispatcher_ctx
    ${CMAKE_CURRENT_SOURCE_DIR}/resource/notify
    ${CMAKE_CURRENT_SOURCE_DIR}/resource/socket
    ${CMAKE_CURRENT_SOURCE_DIR}/resource/stream
    ${CMAKE_CURRENT_SOURCE_DIR}/resource/rma_buffer
    ${CMAKE_CURRENT_SOURCE_DIR}/resource/
    ${CMAKE_CURRENT_SOURCE_DIR}/remote_access
    ${CMAKE_CURRENT_SOURCE_DIR}/task
    ${CMAKE_CURRENT_SOURCE_DIR}/tbe_vector_reduce
    ${CMAKE_CURRENT_SOURCE_DIR}/aiv_communication
)

if(BUILD_OPEN_PROJECT)
    target_compile_definitions(hccl_plf PRIVATE
        OPEN_BUILD_PROJECT
        LOG_CPP)

    target_include_directories(hccl_plf PRIVATE
        ${HCCL_BASE_DIR}/../include
        ${HCCL_BASE_DIR}/../include/hccl/
        ${HCCL_BASE_DIR}/../pkg_inc
        ${HCCL_BASE_DIR}/../pkg_inc/hccl
        ${HCCL_BASE_DIR}/pub_inc
        ${CMAKE_CURRENT_SOURCE_DIR}/hccp/inc/
        ${CMAKE_CURRENT_SOURCE_DIR}/hccp/inc/network
        ${CMAKE_BINARY_DIR}/hcomm_utils/${PRODUCT_SIDE}/include/legacy/

        # runtime头文件
        ${ASCEND_CANN_PACKAGE_PATH}/include/
        ${ASCEND_CANN_PACKAGE_PATH}/include/base/
        ${ASCEND_CANN_PACKAGE_PATH}/include/driver/
        ${ASCEND_CANN_PACKAGE_PATH}/include/dump/
        ${ASCEND_CANN_PACKAGE_PATH}/include/external/
        ${ASCEND_CANN_PACKAGE_PATH}/include/platform/

        # driver头文件
        ${ASCEND_CANN_PACKAGE_PATH}/include/driver/

        # mmpa头文件
        ${ASCEND_CANN_PACKAGE_PATH}/include/mmpa/

        # driver头文件
        ${ASCEND_CANN_PACKAGE_PATH}/include/driver/

        # 包间接口
        ${ASCEND_CANN_PACKAGE_PATH}/pkg_inc/
        ${ASCEND_CANN_PACKAGE_PATH}/pkg_inc/runtime/
        ${ASCEND_CANN_PACKAGE_PATH}/pkg_inc/aicpu/
        ${ASCEND_CANN_PACKAGE_PATH}/pkg_inc/profiling/
        ${ASCEND_CANN_PACKAGE_PATH}/pkg_inc/base/
        ${ASCEND_CANN_PACKAGE_PATH}/pkg_inc/dump/
        ${ASCEND_CANN_PACKAGE_PATH}/pkg_inc/trace/

        ${THIRD_PARTY_NLOHMANN_PATH}
        ${HCCL_BASE_DIR}/platform/hccp/external_depends/rdma-core/include
    )

    target_link_directories(hccl_plf PRIVATE
        ${ASCEND_CANN_PACKAGE_PATH}/lib64
    )
else()
    target_include_directories(hccl_plf PRIVATE
        ${TOP_DIR}/abl/atrace/inc/utrace
        ${TOP_DIR}/abl/msprof/inc/
        ${TOP_DIR}/inc
        ${TOP_DIR}/inc/aicpu/
        ${TOP_DIR}/inc/driver/
        ${TOP_DIR}/metadef/pkg_inc/
        ${TOP_DIR}/metadef/inc/external/
        ${TOP_DIR}/metadef/pkg_inc
        ${TOP_DIR}/runtime/include/external

        ${TOP_DIR}/open_source/json/include

        ${TOP_DIR}/hcomm/src/platform/hccp/inc
        ${TOP_DIR}/hcomm/src/platform/hccp/inc/network

        ${CMAKE_CURRENT_SOURCE_DIR}/legacy/inc
    )
endif()


target_compile_definitions(hccl_plf  PRIVATE
    $<$<STREQUAL:${PRODUCT_SIDE},device>:ASCEND_310P_DEVICE>
    USE_AICORE_REDUCESUM
    USE_AICORE_GATHERV2
    USE_AICORE_GATHERV2_INFER
    $<$<STREQUAL:${PRODUCT_SIDE},host>:_GLIBCXX_USE_CXX11_ABI=0>
)

set(CMAKE_CXX_STANDARD 14)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

target_compile_options(hccl_plf PRIVATE
    -Werror
    -Wall
    -fno-common
    -fno-strict-aliasing
    -pipe
    -O3
    -std=c++14
    -fstack-protector-all
    $<$<CONFIG:Debug>:-g>
)

target_link_options(hccl_plf PRIVATE
    -Wl,-z,relro
    -Wl,-z,now
    -Wl,-z,noexecstack
    -Wl,--build-id=none
    $<$<CONFIG:Release>:-s>
)

#头文件搜索路径
target_include_directories(hccl_plf PRIVATE
    ${platform_include_list}
)

if(BUILD_OPEN_PROJECT)
    target_link_libraries(hccl_plf
    PRIVATE
        -Wl,--no-as-needed
        c_sec
        unified_dlog
        mmpa
        runtime
        acl_rt
        error_manager
        hccl_legacy
        -Wl,--as-needed
        -lrt
        -ldl
        -lpthread
    PUBLIC
        hccl_headers
    )
else()
    target_link_libraries(hccl_plf
    PRIVATE
        $<BUILD_INTERFACE:intf_pub_cxx14>
        $<BUILD_INTERFACE:hccl_headers>
        -Wl,--no-as-needed
        c_sec
        unified_dlog
        mmpa
        runtime
        ascendcl
        error_manager
        hccl_legacy
        -Wl,--as-needed
        -lrt
        -ldl
        -lpthread
        ofed_headers
    PUBLIC
        hccl_headers
    )
endif()

add_subdirectory(comm_primitive)
add_subdirectory(common)
add_subdirectory(debug)
add_subdirectory(remote_access)
add_subdirectory(resource)
add_subdirectory(task)
add_subdirectory(ping_mesh)
add_subdirectory(hccp)

add_dependencies(hccl_plf json)

install(TARGETS  hccl_plf
    LIBRARY DESTINATION ${INSTALL_LIBRARY_DIR}  OPTIONAL
)