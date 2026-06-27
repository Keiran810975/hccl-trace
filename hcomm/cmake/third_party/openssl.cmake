# -----------------------------------------------------------------------------------------------------------
# Copyright (c) 2025 Huawei Technologies Co., Ltd.
# This program is free software, you can redistribute it and/or modify it under the terms and conditions of
# CANN Open Software License Agreement Version 2.0 (the "License").
# Please refer to the License for details. You may not use this file except in compliance with the License.
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
# See LICENSE in the root of the software repository for the full text of the License.
# -----------------------------------------------------------------------------------------------------------
include(ExternalProject)
set(OPENSSL_SRC_DIR ${PROJECT_SOURCE_DIR}/third_party/openssl-${PRODUCT_SIDE})

if(CCACHE_PROGRAM)
    set(OPENSSL_CC "${CCACHE_PROGRAM} ${CMAKE_C_COMPILER}")
    set(OPENSSL_CXX "${CCACHE_PROGRAM} ${CMAKE_CXX_COMPILER}")
else()
    set(OPENSSL_CC "${CMAKE_C_COMPILER}")
    set(OPENSSL_CXX "${CMAKE_CXX_COMPILER}")
endif()

# ========== 基本路径配置 ==========
set(OPENSSL_DOWNLOAD_COMMAND "")
# 检查 CANN_3RD_LIB_PATH 是否存在且不为空
if(EXISTS ${CANN_3RD_LIB_PATH}/openssl)
    file(COPY ${CANN_3RD_LIB_PATH}/openssl/ DESTINATION ${OPENSSL_SRC_DIR})
    message(STATUS "Successfully copied ${CANN_3RD_LIB_PATH}/openssl to ${OPENSSL_SRC_DIR}.")
else()
    set(OPENSSL_TARBALL https://gitcode.com/cann-src-third-party/openssl/releases/download/openssl-3.0.9/openssl-openssl-3.0.9.tar.gz)   # 源码包
    set(OPENSSL_DOWNLOAD_COMMAND
        URL ${OPENSSL_TARBALL}
        DOWNLOAD_DIR ${CMAKE_BINARY_DIR}/downloads
        TLS_VERIFY OFF
    )
endif()
set(OPENSSL_INSTALL_DIR ${CMAKE_BINARY_DIR}/openssl-install) # 安装路径
set(OPENSSL_INCLUDE_DIR
    ${CMAKE_BINARY_DIR}/openssl-install/include
    ${OPENSSL_SRC_DIR}/include
)
message("---------------------------${OPENSSL_TARBALL}")
message("---------------------------${OPENSSL_SRC_DIR}")
# ========== 工具链配置（根据系统架构判断） ==========
if(CMAKE_SYSTEM_PROCESSOR STREQUAL "x86_64")
    set(OPENSSL_PLATFORM linux-x86_64)
    set(OPENSSL_INSTALL_LIBDIR ${OPENSSL_INSTALL_DIR}/lib)
elseif(CMAKE_SYSTEM_PROCESSOR STREQUAL "aarch64")
    set(OPENSSL_PLATFORM linux-aarch64)
elseif(CMAKE_SYSTEM_PROCESSOR STREQUAL "arm")
    set(OPENSSL_PLATFORM linux-armv4)
else()
    set(OPENSSL_PLATFORM linux-generic64)
endif()

# ========== 编译选项 ==========
set(OPENSSL_OPTION "-fstack-protector-all -D_FORTIFY_SOURCE=2 -O2 -Wl,-z,relro,-z,now,-z,noexecstack -Wl,--build-id=none -s")

if("${TOOLCHAIN_DIR}" STREQUAL "arm-tiny-hcc-toolchain.cmake")
    set(OPENSSL_OPTION "-mcpu=cortex-a55 -mfloat-abi=hard ${OPENSSL_OPTION}")
elseif("${TOOLCHAIN_DIR}" STREQUAL "arm-nano-hcc-toolchain.cmake")
    set(OPENSSL_OPTION "-mcpu=cortex-a9 -mfloat-abi=soft ${OPENSSL_OPTION}")
endif()

# ========== Perl 路径（OpenSSL 的 configure 依赖 Perl）==========
find_program(PERL_PATH perl REQUIRED)

# ========== 构建命令 ==========
set(OPENSSL_MAKE_CMD $(MAKE))
set(OPENSSL_INSTALL_CMD $(MAKE) install_dev)

message(STATUS "------------------------CMAKE_CXX_COMPILER=${CMAKE_CXX_COMPILER}")
message(STATUS "------------------------CMAKE_C_COMPILER=${CMAKE_C_COMPILER}")
message(STATUS "------------------------CMAKE_SYSTEM_PROCESSOR=${CMAKE_SYSTEM_PROCESSOR}")
message(STATUS "------------------------CC=$ENV{CC}")
message(STATUS "------------------------CXX=$ENV{CXX}")
set(OPENSSL_CONFIGURE_PUB_COMMAND
    ${PERL_PATH} <SOURCE_DIR>/Configure
    ${OPENSSL_PLATFORM}
    no-asm enable-shared threads enable-ssl3-method no-tests
    ${OPENSSL_OPTION}
    --prefix=${OPENSSL_INSTALL_DIR}
)

if (DEVICE_MODE)
    set(OPENSSL_CONFIGURE_COMMAND
        unset CROSS_COMPILE &&
        ${OPENSSL_CONFIGURE_PUB_COMMAND}
    )
    set(OPENSSL_INSTALL_PATH lib)
    set(COPY_BIN_COMMAND "")
else()
    set(OPENSSL_CONFIGURE_COMMAND
        unset CROSS_COMPILE &&
        export NO_OSSL_RENAME_VERSION=1 &&
        ${OPENSSL_CONFIGURE_PUB_COMMAND}
    )
    if(CMAKE_SYSTEM_PROCESSOR STREQUAL "x86_64")
        set(OPENSSL_INSTALL_PATH lib64)
    else()
        set(OPENSSL_INSTALL_PATH lib)
    endif()
endif()
# ========== ExternalProject_Add ==========
ExternalProject_Add(openssl_project
    ${OPENSSL_DOWNLOAD_COMMAND}
    # COMMAND tar -zxf ${OPENSSL_TARBALL} --strip-components 1 -C ${OPENSSL_SRC_DIR}
    SOURCE_DIR ${OPENSSL_SRC_DIR}                 # 解压后的源码目录
    CONFIGURE_COMMAND   ${OPENSSL_CONFIGURE_COMMAND} CC=${OPENSSL_CC} CXX={OPENSSL_CXX}
    BUILD_COMMAND ${OPENSSL_MAKE_CMD}
    INSTALL_COMMAND ${OPENSSL_INSTALL_CMD}
    BUILD_IN_SOURCE TRUE                          # OpenSSL 不支持分离构建目录
    ${COPY_BIN_COMMAND}
)

add_library(crypto_static STATIC IMPORTED GLOBAL)
add_library(ssl_static STATIC IMPORTED GLOBAL)
add_dependencies(crypto_static ssl_static openssl_project)

set_target_properties(crypto_static PROPERTIES
    IMPORTED_LOCATION "${CMAKE_BINARY_DIR}/openssl-install/${OPENSSL_INSTALL_PATH}/libcrypto.a"
)

set_target_properties(ssl_static PROPERTIES
    IMPORTED_LOCATION "${CMAKE_BINARY_DIR}/openssl-install/${OPENSSL_INSTALL_PATH}/libssl.a"
)
