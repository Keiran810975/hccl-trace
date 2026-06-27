# ----------------------------------------------------------------------------
# This program is free software, you can redistribute it and/or modify it.
# Copyright (c) 2025 Huawei Technologies Co., Ltd.
# This file is a part of the CANN Open Software.
# Licensed under CANN Open Software License Agreement Version 2.0 (the "License").
# Please refer to the License for details. You may not use this file except in compliance with the License.
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
# See LICENSE in the root of the software repository for the full text of the License.
# ----------------------------------------------------------------------------
set(HCOMM_UTILS_PATH ${CMAKE_CURRENT_BINARY_DIR})
set(INSTALL_LIBRARY_DIR hcomm/lib64)
set(CANN_UTILS_VERSION "8.5.0-beta.1")

if(hcomm_utils_FOUND AND NOT FORCE_REBUILD_CANN_3RD)
    message(STATUS "hcomm_utils found in ${HCOMM_UTILS_PATH}")
else()
    message(STATUS "hcomm_utils INSTALL_LIBRARY_DIR ${INSTALL_LIBRARY_DIR} ${HCOMM_UTILS_PATH}")  
    message(STATUS "hcomm_utils CANN_UTILS_LIB_PATH ${CANN_UTILS_LIB_PATH}   process ${CMAKE_HOST_SYSTEM_PROCESSOR}")
    file(GLOB HCOMM_UTILS_PKG
        LIST_DIRECTORIES True
        ${CANN_UTILS_LIB_PATH}/cann-hcomm-utils_*_linux-${CMAKE_HOST_SYSTEM_PROCESSOR}.tar.gz
    )

    if(NOT EXISTS ${HCOMM_UTILS_PKG})
        set(HCOMM_UTILS_FILE "cann-hcomm-utils_${CANN_UTILS_VERSION}_linux-${CMAKE_HOST_SYSTEM_PROCESSOR}.tar.gz")
        set(SIMULATOR_DIR ${CMAKE_CURRENT_BINARY_DIR}/download/${HCOMM_UTILS_FILE})
        execute_process(COMMAND rm -rf ${SIMULATOR_DIR})

        set(HCOMM_UTILS_URL "https://ascend.devcloud.huaweicloud.com/artifactory/cann-run/dependency/${CANN_UTILS_VERSION}/${CMAKE_HOST_SYSTEM_PROCESSOR}/basic/${HCOMM_UTILS_FILE}")
        message(STATUS "hcomm_utils pkg not found in ${HCOMM_UTILS_PKG}, downloading utils pkg from ${HCOMM_UTILS_URL}")
        file(DOWNLOAD
            ${HCOMM_UTILS_URL}
            ${SIMULATOR_DIR}
            SHOW_PROGRESS
        )
        set(HCOMM_UTILS_PKG ${SIMULATOR_DIR})
    endif()

    execute_process(
        COMMAND mkdir -p ${HCOMM_UTILS_PATH}
        COMMAND chmod 755 -R ${HCOMM_UTILS_PATH}
        COMMAND tar -xf ${HCOMM_UTILS_PKG} --overwrite --strip-components=1 -C ${HCOMM_UTILS_PATH}
    )

    add_library(ascend_kms SHARED IMPORTED)

    set_target_properties(ascend_kms PROPERTIES
        INTERFACE_INCLUDE_DIRECTORIES "${HCOMM_UTILS_PATH}/hcomm_utils/${PRODUCT_SIDE}/include"
        IMPORTED_LOCATION "${HCOMM_UTILS_PATH}/hcomm_utils/${PRODUCT_SIDE}/lib/libascend_kms.so"
    )
    install(FILES  ${HCOMM_UTILS_PATH}/hcomm_utils/${PRODUCT_SIDE}/lib/libascend_kms.so
        DESTINATION ${INSTALL_LIBRARY_DIR}  OPTIONAL
    )

    add_library(tls_adp SHARED IMPORTED)

    set_target_properties(tls_adp PROPERTIES
        INTERFACE_INCLUDE_DIRECTORIES "${HCOMM_UTILS_PATH}/hcomm_utils/${PRODUCT_SIDE}/include"
        IMPORTED_LOCATION "${HCOMM_UTILS_PATH}/hcomm_utils/${PRODUCT_SIDE}/lib/libtls_adp.so"
    )

    install(FILES  ${HCOMM_UTILS_PATH}/hcomm_utils/${PRODUCT_SIDE}/lib/libtls_adp.so
        DESTINATION ${INSTALL_LIBRARY_DIR}  OPTIONAL
    )

    add_library(hccl_legacy SHARED IMPORTED)

    set_target_properties(hccl_legacy PROPERTIES
        INTERFACE_INCLUDE_DIRECTORIES "${HCOMM_UTILS_PATH}/hcomm_utils/${PRODUCT_SIDE}/include"
        IMPORTED_LOCATION "${HCOMM_UTILS_PATH}/hcomm_utils/host/lib/libhccl_legacy.so"
    )
    install(FILES  ${HCOMM_UTILS_PATH}/hcomm_utils/host/lib/libhccl_legacy.so
        DESTINATION ${INSTALL_LIBRARY_DIR}  OPTIONAL
    )
    
    install(FILES  ${HCOMM_UTILS_PATH}/hcomm_utils/host/lib/MemSet_dynamic_AtomicAddrClean_1_ascend310p3.o
        DESTINATION ${INSTALL_LIBRARY_DIR}  OPTIONAL
    )

    install(FILES  ${HCOMM_UTILS_PATH}/hcomm_utils/host/lib/MemSet_dynamic_AtomicAddrClean_1_ascend910.o
        DESTINATION ${INSTALL_LIBRARY_DIR}  OPTIONAL
    )

    install(FILES  ${HCOMM_UTILS_PATH}/hcomm_utils/host/lib/MemSet_dynamic_AtomicAddrClean_1_ascend910b.o
        DESTINATION ${INSTALL_LIBRARY_DIR}  OPTIONAL
    )

    install(FILES  ${HCOMM_UTILS_PATH}/hcomm_utils/host/lib/dynamic_add_float16_v51.o
        DESTINATION ${INSTALL_LIBRARY_DIR}  OPTIONAL
    )

    install(FILES  ${HCOMM_UTILS_PATH}/hcomm_utils/host/lib/dynamic_add_float16_v80.o
        DESTINATION ${INSTALL_LIBRARY_DIR}  OPTIONAL
    )

    install(FILES  ${HCOMM_UTILS_PATH}/hcomm_utils/host/lib/dynamic_add_float32_v51.o
        DESTINATION ${INSTALL_LIBRARY_DIR}  OPTIONAL
    )

    install(FILES  ${HCOMM_UTILS_PATH}/hcomm_utils/host/lib/dynamic_add_int32_v51.o
        DESTINATION ${INSTALL_LIBRARY_DIR}  OPTIONAL
    )

    install(FILES  ${HCOMM_UTILS_PATH}/hcomm_utils/host/lib/dynamic_add_int32_v80.o
        DESTINATION ${INSTALL_LIBRARY_DIR}  OPTIONAL
    )

    install(FILES  ${HCOMM_UTILS_PATH}/hcomm_utils/host/lib/dynamic_add_int64_v80.o
        DESTINATION ${INSTALL_LIBRARY_DIR}  OPTIONAL
    )

    install(FILES  ${HCOMM_UTILS_PATH}/hcomm_utils/host/lib/dynamic_add_int64_v81.o
        DESTINATION ${INSTALL_LIBRARY_DIR}  OPTIONAL
    )

    install(FILES  ${HCOMM_UTILS_PATH}/hcomm_utils/host/lib/dynamic_add_int8_v51.o
        DESTINATION ${INSTALL_LIBRARY_DIR}  OPTIONAL
    )

    install(FILES  ${HCOMM_UTILS_PATH}/hcomm_utils/host/lib/dynamic_add_int8_v80.o
        DESTINATION ${INSTALL_LIBRARY_DIR}  OPTIONAL
    )

    install(FILES  ${HCOMM_UTILS_PATH}/hcomm_utils/host/lib/dynamic_maximum_float16_v51.o
        DESTINATION ${INSTALL_LIBRARY_DIR}  OPTIONAL
    )

    install(FILES  ${HCOMM_UTILS_PATH}/hcomm_utils/host/lib/dynamic_maximum_float16_v80.o
        DESTINATION ${INSTALL_LIBRARY_DIR}  OPTIONAL
    )

    install(FILES  ${HCOMM_UTILS_PATH}/hcomm_utils/host/lib/dynamic_maximum_float32_v51.o
        DESTINATION ${INSTALL_LIBRARY_DIR}  OPTIONAL
    )

    install(FILES  ${HCOMM_UTILS_PATH}/hcomm_utils/host/lib/dynamic_maximum_float32_v80.o
        DESTINATION ${INSTALL_LIBRARY_DIR}  OPTIONAL
    )

    install(FILES  ${HCOMM_UTILS_PATH}/hcomm_utils/host/lib/dynamic_maximum_int32_v51.o
        DESTINATION ${INSTALL_LIBRARY_DIR}  OPTIONAL
    )

    install(FILES  ${HCOMM_UTILS_PATH}/hcomm_utils/host/lib/dynamic_maximum_int32_v80.o
        DESTINATION ${INSTALL_LIBRARY_DIR}  OPTIONAL
    )

    install(FILES  ${HCOMM_UTILS_PATH}/hcomm_utils/host/lib/dynamic_maximum_int64_v80.o
        DESTINATION ${INSTALL_LIBRARY_DIR}  OPTIONAL
    )

    install(FILES  ${HCOMM_UTILS_PATH}/hcomm_utils/host/lib/dynamic_maximum_int64_v81.o
        DESTINATION ${INSTALL_LIBRARY_DIR}  OPTIONAL
    )

    install(FILES  ${HCOMM_UTILS_PATH}/hcomm_utils/host/lib/dynamic_maximum_int8_v51.o
        DESTINATION ${INSTALL_LIBRARY_DIR}  OPTIONAL
    )

    install(FILES  ${HCOMM_UTILS_PATH}/hcomm_utils/host/lib/dynamic_maximum_int8_v80.o
        DESTINATION ${INSTALL_LIBRARY_DIR}  OPTIONAL
    )

    install(FILES  ${HCOMM_UTILS_PATH}/hcomm_utils/host/lib/dynamic_minimum_float16_v51.o
        DESTINATION ${INSTALL_LIBRARY_DIR}  OPTIONAL
    )

    install(FILES  ${HCOMM_UTILS_PATH}/hcomm_utils/host/lib/dynamic_minimum_float16_v80.o
        DESTINATION ${INSTALL_LIBRARY_DIR}  OPTIONAL
    )

    install(FILES  ${HCOMM_UTILS_PATH}/hcomm_utils/host/lib/dynamic_minimum_float32_v51.o
        DESTINATION ${INSTALL_LIBRARY_DIR}  OPTIONAL
    )

    install(FILES  ${HCOMM_UTILS_PATH}/hcomm_utils/host/lib/dynamic_minimum_float32_v80.o
        DESTINATION ${INSTALL_LIBRARY_DIR}  OPTIONAL
    )

    install(FILES  ${HCOMM_UTILS_PATH}/hcomm_utils/host/lib/dynamic_minimum_int32_v51.o
        DESTINATION ${INSTALL_LIBRARY_DIR}  OPTIONAL
    )

    install(FILES  ${HCOMM_UTILS_PATH}/hcomm_utils/host/lib/dynamic_minimum_int32_v80.o
        DESTINATION ${INSTALL_LIBRARY_DIR}  OPTIONAL
    )

    install(FILES  ${HCOMM_UTILS_PATH}/hcomm_utils/host/lib/dynamic_minimum_int64_v80.o
        DESTINATION ${INSTALL_LIBRARY_DIR}  OPTIONAL
    )

    install(FILES  ${HCOMM_UTILS_PATH}/hcomm_utils/host/lib/dynamic_minimum_int64_v81.o
        DESTINATION ${INSTALL_LIBRARY_DIR}  OPTIONAL
    )

    install(FILES  ${HCOMM_UTILS_PATH}/hcomm_utils/host/lib/dynamic_minimum_int8_v51.o
        DESTINATION ${INSTALL_LIBRARY_DIR}  OPTIONAL
    )

    install(FILES  ${HCOMM_UTILS_PATH}/hcomm_utils/host/lib/dynamic_minimum_int8_v80.o
        DESTINATION ${INSTALL_LIBRARY_DIR}  OPTIONAL
    )

    install(FILES  ${HCOMM_UTILS_PATH}/hcomm_utils/host/lib/dynamic_mul_float16_v51.o
        DESTINATION ${INSTALL_LIBRARY_DIR}  OPTIONAL
    )

    install(FILES  ${HCOMM_UTILS_PATH}/hcomm_utils/host/lib/dynamic_mul_float16_v80.o
        DESTINATION ${INSTALL_LIBRARY_DIR}  OPTIONAL
    )

    install(FILES  ${HCOMM_UTILS_PATH}/hcomm_utils/host/lib/dynamic_mul_float16_v81_910B1.o
        DESTINATION ${INSTALL_LIBRARY_DIR}  OPTIONAL
    )

    install(FILES  ${HCOMM_UTILS_PATH}/hcomm_utils/host/lib/dynamic_mul_float16_v81_910B2.o
        DESTINATION ${INSTALL_LIBRARY_DIR}  OPTIONAL
    )

    install(FILES  ${HCOMM_UTILS_PATH}/hcomm_utils/host/lib/dynamic_mul_float16_v81_910B3.o
        DESTINATION ${INSTALL_LIBRARY_DIR}  OPTIONAL
    )

    install(FILES  ${HCOMM_UTILS_PATH}/hcomm_utils/host/lib/dynamic_mul_float16_v81_910B4.o
        DESTINATION ${INSTALL_LIBRARY_DIR}  OPTIONAL
    )

    install(FILES  ${HCOMM_UTILS_PATH}/hcomm_utils/host/lib/dynamic_mul_float32_v51.o
        DESTINATION ${INSTALL_LIBRARY_DIR}  OPTIONAL
    )

    install(FILES  ${HCOMM_UTILS_PATH}/hcomm_utils/host/lib/dynamic_mul_float32_v80.o
        DESTINATION ${INSTALL_LIBRARY_DIR}  OPTIONAL
    )

    install(FILES  ${HCOMM_UTILS_PATH}/hcomm_utils/host/lib/dynamic_mul_float32_v81_910B1.o
        DESTINATION ${INSTALL_LIBRARY_DIR}  OPTIONAL
    )

    install(FILES  ${HCOMM_UTILS_PATH}/hcomm_utils/host/lib/dynamic_mul_float32_v81_910B2.o
        DESTINATION ${INSTALL_LIBRARY_DIR}  OPTIONAL
    )

    install(FILES  ${HCOMM_UTILS_PATH}/hcomm_utils/host/lib/dynamic_mul_float32_v81_910B3.o
        DESTINATION ${INSTALL_LIBRARY_DIR}  OPTIONAL
    )

    install(FILES  ${HCOMM_UTILS_PATH}/hcomm_utils/host/lib/dynamic_mul_float32_v81_910B4.o
        DESTINATION ${INSTALL_LIBRARY_DIR}  OPTIONAL
    )

    install(FILES  ${HCOMM_UTILS_PATH}/hcomm_utils/host/lib/dynamic_mul_int32_v51.o
        DESTINATION ${INSTALL_LIBRARY_DIR}  OPTIONAL
    )

    install(FILES  ${HCOMM_UTILS_PATH}/hcomm_utils/host/lib/dynamic_mul_int32_v80.o
        DESTINATION ${INSTALL_LIBRARY_DIR}  OPTIONAL
    )

    install(FILES  ${HCOMM_UTILS_PATH}/hcomm_utils/host/lib/dynamic_mul_int32_v81_910B1.o
        DESTINATION ${INSTALL_LIBRARY_DIR}  OPTIONAL
    )

    install(FILES  ${HCOMM_UTILS_PATH}/hcomm_utils/host/lib/dynamic_mul_int32_v81_910B2.o
        DESTINATION ${INSTALL_LIBRARY_DIR}  OPTIONAL
    )

    install(FILES  ${HCOMM_UTILS_PATH}/hcomm_utils/host/lib/dynamic_mul_int32_v81_910B3.o
        DESTINATION ${INSTALL_LIBRARY_DIR}  OPTIONAL
    )

    install(FILES  ${HCOMM_UTILS_PATH}/hcomm_utils/host/lib/dynamic_mul_int32_v81_910B4.o
        DESTINATION ${INSTALL_LIBRARY_DIR}  OPTIONAL
    )

    install(FILES  ${HCOMM_UTILS_PATH}/hcomm_utils/host/lib/dynamic_mul_int64_v80.o
        DESTINATION ${INSTALL_LIBRARY_DIR}  OPTIONAL
    )

    install(FILES  ${HCOMM_UTILS_PATH}/hcomm_utils/host/lib/dynamic_mul_int64_v81.o
        DESTINATION ${INSTALL_LIBRARY_DIR}  OPTIONAL
    )

    install(FILES  ${HCOMM_UTILS_PATH}/hcomm_utils/host/lib/dynamic_mul_int8_v51.o
        DESTINATION ${INSTALL_LIBRARY_DIR}  OPTIONAL
    )

    install(FILES  ${HCOMM_UTILS_PATH}/hcomm_utils/host/lib/dynamic_mul_int8_v80.o
        DESTINATION ${INSTALL_LIBRARY_DIR}  OPTIONAL
    )

    install(FILES  ${HCOMM_UTILS_PATH}/hcomm_utils/host/lib/dynamic_mul_int8_v81_910B1.o
        DESTINATION ${INSTALL_LIBRARY_DIR}  OPTIONAL
    )

    install(FILES  ${HCOMM_UTILS_PATH}/hcomm_utils/host/lib/dynamic_mul_int8_v81_910B2.o
        DESTINATION ${INSTALL_LIBRARY_DIR}  OPTIONAL
    )

    install(FILES  ${HCOMM_UTILS_PATH}/hcomm_utils/host/lib/dynamic_mul_int8_v81_910B3.o
        DESTINATION ${INSTALL_LIBRARY_DIR}  OPTIONAL
    )

    install(FILES  ${HCOMM_UTILS_PATH}/hcomm_utils/host/lib/dynamic_mul_int8_v81_910B4.o
        DESTINATION ${INSTALL_LIBRARY_DIR}  OPTIONAL
    )
    set(hcomm_utils_FOUND ON)
endif()
