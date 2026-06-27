
set(ra_list
    async/ra_comm.c
    async/ra_socket.c
    ra_host.c
    ra_common.c
    ra_ping.c
    ra_rdma.c
    ra_init.c
    ra_socket.c
    ra_tlv.c
    ${CMAKE_CURRENT_SOURCE_DIR}/../../common/dl_hal_function.c
    ${CMAKE_CURRENT_SOURCE_DIR}/../../common/ascend_hal_dl.c
)

add_library(ra  SHARED ${ra_list})

if(BUILD_OPEN_PROJECT)
    target_compile_definitions(ra PRIVATE
        OPEN_BUILD_PROJECT
        LOG_CPP)

    target_include_directories(ra PRIVATE
        ${CMAKE_CURRENT_SOURCE_DIR}/../inc
        ${CMAKE_CURRENT_SOURCE_DIR}/../hdc
        ${CMAKE_CURRENT_SOURCE_DIR}/../hdc/async
        ${CMAKE_CURRENT_SOURCE_DIR}/../../inc/network
        ${CMAKE_CURRENT_SOURCE_DIR}/../../inc/private/network
        ${CMAKE_CURRENT_SOURCE_DIR}/../comm
        ${CMAKE_CURRENT_SOURCE_DIR}/../peer
        ${CMAKE_CURRENT_SOURCE_DIR}/
        ${CMAKE_CURRENT_SOURCE_DIR}/../../common/

        ${ASCEND_CANN_PACKAGE_PATH}/pkg_inc/base/
        ${ASCEND_CANN_PACKAGE_PATH}/include/
        ${ASCEND_CANN_PACKAGE_PATH}/include/toolchain/
        ${ASCEND_CANN_PACKAGE_PATH}/include/driver/
        ${ASCEND_CANN_PACKAGE_PATH}/pkg_inc

        # runtime头文件
        ${ASCEND_CANN_PACKAGE_PATH}/include/

        # rdma头文件
        ${CMAKE_CURRENT_SOURCE_DIR}/../../external_depends/rdma-core/include
        ${CMAKE_CURRENT_SOURCE_DIR}/../../external_depends/host_lite
    )

    target_link_directories(ra PRIVATE
        ${ASCEND_CANN_PACKAGE_PATH}/lib64
    )
    if (DEVICE_MODE)
        target_link_directories(ra PRIVATE
            ${ASCEND_CANN_PACKAGE_PATH}/devlib/device/ # c_sec、mmpa、unified_dlog动态库搜索路径
        )
    endif()
else()
    target_include_directories(ra PRIVATE
        ${TOP_DIR}/hccl/src/platform/hccp/inc/network
        ${TOP_DIR}/hccl/src/platform/hccp/inc/private/network
        ${TOP_DIR}/hccl/src/platform/hccp/rdma_agent/inc
        ${TOP_DIR}/inc/driver
        ${TOP_DIR}/hccl/src/platform/hccp/rdma_agent/hdc
        ${TOP_DIR}/hccl/src/platform/hccp/rdma_agent/hdc/async
        ${TOP_DIR}/hccl/src/platform/hccp/rdma_agent/comm
        ${TOP_DIR}/hccl/src/platform/hccp/rdma_agent/peer
        ${TOP_DIR}/hccl/src/platform/hccp/rdma_agent/client
        ${TOP_DIR}/hccl/src/platform/hccp/common
        ${TOP_DIR}/hccl/src/platform/hccp/external_depends/host_lite
    )
endif()

target_compile_options(ra PRIVATE
    -Werror -fvisibility=hidden -fno-strict-aliasing -fsigned-char -fno-common -std=gnu11 -Wextra
    -fstack-protector-strong
    $<$<CONFIG:Debug>:-g>
)

target_compile_definitions(ra PRIVATE
)

target_link_options(ra PRIVATE
    -Wl,-z,now
    $<$<CONFIG:Release>:-s>
)

if(BUILD_OPEN_PROJECT)
    target_link_libraries(ra PRIVATE
        -Wl,--no-as-needed
        c_sec
        $<$<STREQUAL:${PRODUCT_SIDE},host>:unified_dlog>
        ra_hdc
        ra_peer
        -Wl,--as-needed
        -ldl -lrt
    )
else()
    target_link_libraries(ra PRIVATE
        $<BUILD_INTERFACE:intf_pub>
        $<BUILD_INTERFACE:slog_headers>
        -Wl,--no-as-needed
        c_sec
        slog
        ra_hdc
        ra_peer
        -Wl,--as-needed
        -ldl -lrt
        ofed_headers
    )
endif()

target_compile_definitions(ra PRIVATE
    LOG_HOST
)

install(TARGETS  ra
    LIBRARY DESTINATION ${INSTALL_LIBRARY_DIR}  OPTIONAL
)

# install_package(
#     PACKAGE ra
#     TARGETS ra
# )