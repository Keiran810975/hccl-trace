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
option(BUILD_OPEN_PROJECT "Build open hcomm project." ON)
message(STATUS "DEVICE_MODE=${DEVICE_MODE}")
message(STATUS "BUILD_OPEN_PROJECT=${BUILD_OPEN_PROJECT}")
message(STATUS "AARCH_MODE=${AARCH_MODE}")

find_program(CCACHE_PROGRAM ccache)
if(CCACHE_PROGRAM)
    set(CMAKE_C_COMPILER_LAUNCHER ${CCACHE_PROGRAM})
    set(CMAKE_CXX_COMPILER_LAUNCHER ${CCACHE_PROGRAM})
endif()

if((BUILD_OPEN_PROJECT AND DEVICE_MODE) OR AARCH_MODE)
    # need to switch
    set(CMAKE_SYSTEM_NAME Linux)
    set(CMAKE_SYSTEM_PROCESSOR aarch64)
    #Change the path to the absolute path of the cross compilation tool after the toolkit package is decompressed
    # set cross compile toolchain dir
    set(TOOLCHAIN_DIR ${CUSTOM_ASCEND_CANN_PACKAGE_PATH}/toolkit/toolchain/hcc/)
    message(STATUS "TOOLCHAIN_DIR: ${TOOLCHAIN_DIR}")
    if (NOT "x${TOOLCHAIN_DIR}" STREQUAL "x")
        if (NOT IS_DIRECTORY ${TOOLCHAIN_DIR})
            message(FATAL_ERROR "specify cross compile toolchain directory(${TOOLCHAIN_DIR}) is not exist")
        endif()
    endif()
    # endif()
    set(CMAKE_CXX_COMPILER ${TOOLCHAIN_DIR}/bin/aarch64-target-linux-gnu-g++)
    set(CMAKE_C_COMPILER   ${TOOLCHAIN_DIR}/bin/aarch64-target-linux-gnu-gcc)
endif()

# 获取host架构
execute_process(
    COMMAND uname -m
    OUTPUT_VARIABLE SYSTEM_ARCH
    OUTPUT_STRIP_TRAILING_WHITESPACE
)
message(STATUS "当前系统架构: ${SYSTEM_ARCH}")
project(hcomm)

set(CMAKE_CXX_COMPILE_OBJECT
    "<CMAKE_CXX_COMPILER> <DEFINES> -D__FILE__='\"$(notdir $(abspath <SOURCE>))\"' -Wno-builtin-macro-redefined <INCLUDES> <FLAGS> -o <OBJECT> -c <SOURCE>"
)
set(CMAKE_C_COMPILE_OBJECT
    "<CMAKE_C_COMPILER> <DEFINES> -D__FILE__='\"$(notdir $(abspath <SOURCE>))\"' -Wno-builtin-macro-redefined <INCLUDES> <FLAGS> -o <OBJECT> -c <SOURCE>"
)

# 获取 CPU 核心数
if(${CMAKE_SYSTEM_NAME} STREQUAL "Linux")
    execute_process(
        COMMAND nproc
        OUTPUT_VARIABLE CPU_CORES
        OUTPUT_STRIP_TRAILING_WHITESPACE
    )
elseif(${CMAKE_SYSTEM_NAME} STREQUAL "Windows")
    execute_process(
        COMMAND wmic cpu get NumberOfCores /value
        OUTPUT_VARIABLE CPU_CORES
        OUTPUT_STRIP_TRAILING_WHITESPACE
    )
    # 解析输出
    string(REGEX REPLACE "NumberOfCores=([0-9]+)" "\\1" CPU_CORES "${CPU_CORES}")
else()
    # 默认设置为 1
    set(CPU_CORES 1)
endif()

math(EXPR JOBS "${CPU_CORES} * 2")
message(STATUS "Detected JOBS: ${JOBS}")
set(CMAKE_JOB_POOL_COMPILE "${JOBS}")
set(CMAKE_JOB_POOL_LINK "${JOBS}")

if(ENABLE_TEST)
    include(cmake/config.cmake)
    include(cmake/function.cmake)
    include(cmake/intf_pub_gccnative.cmake)
    include(cmake/utils.cmake)
    add_subdirectory(test)
    return()
endif()

if(BUILD_OPEN_PROJECT)
    include(cmake/third_party/openssl.cmake)
    include(cmake/third_party/json.cmake)
    include(cmake/utils.cmake)
    include(cmake/config.cmake)
    include(cmake/package.cmake)
    pack_built_in()
    add_subdirectory(src)
    add_subdirectory(python)

    set(HCCL_HEAD
        include/hccl/hccl_comm.h
        include/hccl/hccl_types.h
        src/pub_inc/hccn_rping.h
        include/hccl/hccl_rank_graph.h
        include/hccl/hccl_res.h
        include/hccl/hcomm_primitives.h
    )

    set(HCCL_JSON
        cmake/scripts/ccl_kernel.json
    )

    if(DEVICE_MODE)
        include(cmake/func.cmake)
        set(HCCP_TAR_DIR ${CMAKE_CURRENT_SOURCE_DIR}/build_device/tar_pkg/)
        set(CCL_KERNEL_TAR_DIR ${CMAKE_CURRENT_SOURCE_DIR}/build_device/ccl_kernel_tar_pkg/)
        set(HCCD_TAR_DIR ${CMAKE_CURRENT_SOURCE_DIR}/build_hccd/hccd_tar_pkg/)

        message(STATUS "Detected CUSTOM_SIGN_SCRIPT: ${CUSTOM_SIGN_SCRIPT}")
        message(STATUS "Detected ENABLE_SIGN: ${ENABLE_SIGN}")
        pack_targets_and_files(
            OUTPUT_TARGET "generate_device_hccp_package"
            OUTPUT "cann-hcomm-compat.tar.gz"
            TARGETS hccp_service.bin
            FILES  ${HCCP_TAR_DIR}/librs.so ${HCCP_TAR_DIR}/libra_adp.so ${HCCP_TAR_DIR}/libtls_adp.so ${HCCP_TAR_DIR}/libascend_kms.so
            MANIFEST "hccp_compat_bin_hash.cfg"
        )
        add_dependencies(generate_device_hccp_package hccp_service.bin)

        sign_file(
            INPUT "cann-hcomm-compat.tar.gz"
            CONFIG "${CMAKE_CURRENT_SOURCE_DIR}/scripts/sign/hcomm_check_cfg.xml"
            RESULT_VAR "cann-hcomm-compat_sign_file"
            DEPENDS generate_device_hccp_package
        )
        add_dependencies(sign_cann_hcomm_compat generate_device_hccp_package)

        add_custom_target(generate_device_hccd_package
            COMMAND cd ${HCCD_TAR_DIR} && ls && tar czf ../cann-hccd-compat.tar.gz lib64
            DEPENDS hccd
            COMMENT "Creating cann-hccd-compat.tar.gz"
        )
        add_dependencies(generate_device_hccd_package hccd)

        sign_file(
            INPUT "cann-hccd-compat.tar.gz"
            CONFIG "${CMAKE_CURRENT_SOURCE_DIR}/scripts/sign/hcomm_check_cfg.xml"
            RESULT_VAR "cann-hccd-compat_sign_file"
            DEPENDS generate_device_hccd_package
        )
        add_dependencies(sign_cann_hccd_compat generate_device_hccd_package)

        if(KERNEL_MODE)
            add_custom_target(generate_device_aicpu_package
                COMMAND cd ${CCL_KERNEL_TAR_DIR} && ls && tar czf ../aicpu_hcomm.tar.gz aicpu_kernels_device
                DEPENDS ccl_kernel
                COMMENT "Creating aicpu_hcomm.tar.gz"
            )
            add_dependencies(generate_device_aicpu_package ccl_kernel)
            sign_file(
                INPUT "aicpu_hcomm.tar.gz"
                CONFIG "${CMAKE_CURRENT_SOURCE_DIR}/scripts/sign/hcomm_check_cfg.xml"
                RESULT_VAR "aicpu_hcomm_sign_file"
                DEPENDS generate_device_aicpu_package
            )
            add_dependencies(sign_aicpu_hcomm generate_device_aicpu_package)
        endif()
    endif()

    if (NOT DEVICE_MODE)
        message(STATUS "Detected INSTALL_LIBRARY_DIR: ${INSTALL_LIBRARY_DIR}")

        set(BUILD_DEVICE_DIR ${CMAKE_CURRENT_SOURCE_DIR}/build_device/)
        set(BUILD_HCCD_DIR ${CMAKE_CURRENT_SOURCE_DIR}/build_hccd/)
        add_custom_target(install_tar DEPENDS
            ${BUILD_DEVICE_DIR}/signatures/cann-hcomm-compat.tar.gz
            ${BUILD_DEVICE_DIR}/signatures/aicpu_hcomm.tar.gz
            ${BUILD_HCCD_DIR}/signatures/cann-hccd-compat.tar.gz
            ${BUILD_DEVICE_DIR}/aicpu_custom/libaicpu_custom.so
        )
        install(FILES ${BUILD_DEVICE_DIR}/signatures/cann-hcomm-compat.tar.gz
            DESTINATION ${INSTALL_DEVICE_TAR_DIR} OPTIONAL
        )
        install(FILES ${BUILD_DEVICE_DIR}/signatures/aicpu_hcomm.tar.gz
            DESTINATION ${INSTALL_DEVICE_TAR_DIR} OPTIONAL
        )
        install(FILES ${BUILD_HCCD_DIR}/signatures/cann-hccd-compat.tar.gz
            DESTINATION ${INSTALL_DEVICE_TAR_DIR} OPTIONAL
        )
        install(FILES ${BUILD_DEVICE_DIR}/aicpu_custom/libaicpu_custom.so
            DESTINATION ${INSTALL_CCL_KERNEL_JSON_DIR} OPTIONAL
        )
        add_dependencies(install_tar hcomm)
    endif()

    install(FILES
        ${HCCL_HEAD}
        ${HCCL_JSON}
        DESTINATION ${INSTALL_INCLUDE_DIR}/hccl/ OPTIONAL
    )

    set(HCCL_PKG_HEAD
        pkg_inc/hccl/base.h
        pkg_inc/hccl/hccl_ex.h
        pkg_inc/hccl/hccl_one_sided_services.h
        pkg_inc/hccl/hcom.h
        pkg_inc/hccl/hcomm_diag.h
        pkg_inc/hccl/dtype_common.h
        pkg_inc/hccl/workflow.h
        pkg_inc/hccl/hccl_inner.h
        pkg_inc/hccl/hccl_ctrl_plane.h
    )
    install(FILES
        ${HCCL_PKG_HEAD}
        DESTINATION ${INSTALL_PKG_INCLUDE_DIR}/hccl/ OPTIONAL
    )
endif()
