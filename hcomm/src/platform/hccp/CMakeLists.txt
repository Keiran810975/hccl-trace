# -----------------------------------------------------------------------------------------------------------
# Copyright (c) 2025 Huawei Technologies Co., Ltd.
# This program is free software, you can redistribute it and/or modify it under the terms and conditions of
# CANN Open Software License Agreement Version 2.0 (the "License").
# Please refer to the License for details. You may not use this file except in compliance with the License.
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
# See LICENSE in the root of the software repository for the full text of the License.
# -----------------------------------------------------------------------------------------------------------
if(BUILD_OPEN_PROJECT)
    if (DEVICE_MODE)
        add_subdirectory(stub_tsd)
    endif()
endif()
add_subdirectory(rdma_agent)
add_subdirectory(rdma_service)

if (NOT DEVICE_MODE)
    return()
endif()

add_executable(hccp_service.bin  hccp_service/main.c hccp_service/param.c
    ${CMAKE_CURRENT_SOURCE_DIR}/common/ascend_hal_dl.c
    ${CMAKE_CURRENT_SOURCE_DIR}/common/dl_hal_function.c
)

if(BUILD_OPEN_PROJECT)
    target_compile_definitions(hccp_service.bin PRIVATE OPEN_BUILD_PROJECT LOG_CPP)

    target_include_directories(hccp_service.bin PRIVATE
        ${CMAKE_CURRENT_SOURCE_DIR}/
        ${CMAKE_CURRENT_SOURCE_DIR}/hccp_service
        ${CMAKE_CURRENT_SOURCE_DIR}/external_depends/inc/driver
        ${CMAKE_CURRENT_SOURCE_DIR}/external_depends/inc/log
        ${CMAKE_CURRENT_SOURCE_DIR}/external_depends/rdma-core/include
        ${CMAKE_CURRENT_SOURCE_DIR}/external_depends/host_lite
        ${CMAKE_CURRENT_SOURCE_DIR}/external_depends/rdma-core/providers/hns
        ${CMAKE_CURRENT_SOURCE_DIR}/inc/network
        ${CMAKE_CURRENT_SOURCE_DIR}/inc/private/network
        ${CMAKE_CURRENT_SOURCE_DIR}/rdma_service
        ${CMAKE_CURRENT_SOURCE_DIR}/rdma_agent/adapter
        ${CMAKE_CURRENT_SOURCE_DIR}/rdma_agent/adapter/async
        ${CMAKE_CURRENT_SOURCE_DIR}/rdma_agent/hdc
        ${CMAKE_CURRENT_SOURCE_DIR}/rdma_agent/inc
        ${CMAKE_CURRENT_SOURCE_DIR}/common
        ${ASCEND_CANN_PACKAGE_PATH}/include/
        ${ASCEND_CANN_PACKAGE_PATH}/pkg_inc/aicpu/tsd
    )

    target_link_directories(hccp_service.bin PRIVATE
        ${ASCEND_CANN_PACKAGE_PATH}/devlib/device/ # c_sec、mmpa、unified_dlog动态库搜索路径
    )
endif()

target_compile_options(hccp_service.bin PRIVATE
    -Werror -Wall -fPIC -fPIE -rdynamic -fvisibility=hidden -fno-common -fsigned-char -fno-strict-aliasing -std=gnu11
    -fstack-protector-strong
    $<$<CONFIG:Debug>:-g>
)

target_link_options(hccp_service.bin PRIVATE
    -Wl,-Bsymbolic -Wl,--no-undefined -rdynamic
    -Wl,-z,now
    -pie
    $<$<CONFIG:Release>:-s>
)

target_compile_definitions(hccp_service.bin PRIVATE
    google=ascend_private
    $<$<AND:$<STREQUAL:${PRODUCT},ascend910>,$<STREQUAL:${PRODUCT_SIDE},device>>:CONFIG_CGROUP>
    $<$<AND:$<STREQUAL:${PRODUCT},ascend310p>,$<STREQUAL:${PRODUCT_SIDE},device>>:CONFIG_CGROUP>
)

if(BUILD_OPEN_PROJECT)
    target_link_libraries(hccp_service.bin PRIVATE
        # $<BUILD_INTERFACE:intf_pub>
        # $<BUILD_INTERFACE:slog_headers>
        # $<BUILD_INTERFACE:network_headers>
        c_sec
        unified_dlog
        ra_adp
        rs
        mmpa
        tsd_eventclient
        # ascend_protobuf
        # crypto_static
        -ldl
        # ofed_headers
    )
endif()

install(TARGETS  hccp_service.bin
    RUNTIME DESTINATION ${INSTALL_RUNTIME_DIR}  OPTIONAL
)

add_dependencies(hccp_service.bin rs)
if(DEVICE_MODE)
    set(HCCP_TAR_DIR ${HCCL_BASE_DIR}/../build_device/tar_pkg/)
    set(GENERATE_HASH_SCRIPT ${HCCL_BASE_DIR}/../scripts/sign/generate_hash.sh)
    add_custom_command(
        TARGET hccp_service.bin
        POST_BUILD
        COMMAND ${CMAKE_COMMAND} -E make_directory ${HCCP_TAR_DIR}
        COMMAND ${CMAKE_COMMAND} -E copy $<TARGET_FILE:rs> ${HCCP_TAR_DIR}
        COMMAND ${CMAKE_COMMAND} -E copy $<TARGET_FILE:ra_adp> ${HCCP_TAR_DIR}
        COMMAND ${CMAKE_COMMAND} -E copy $<TARGET_FILE:hccp_service.bin> ${HCCP_TAR_DIR}
        COMMAND ${CMAKE_COMMAND} -E copy ${CMAKE_BINARY_DIR}/hcomm_utils/${PRODUCT_SIDE}/lib/lib* ${HCCP_TAR_DIR}
        COMMAND chmod 750 ${HCCP_TAR_DIR}/lib*
        COMMAND chmod 750 ${HCCP_TAR_DIR}/hccp_service.bin
        COMMENT "Copying rs ra_adp hccp_service.bin ascend_kms tls_adp to ${HCCP_TAR_DIR}"
    )
endif()