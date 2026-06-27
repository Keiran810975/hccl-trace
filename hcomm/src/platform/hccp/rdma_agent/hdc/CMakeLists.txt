if(BUILD_OPEN_PROJECT)
    set(BASE_DIR ${CMAKE_CURRENT_SOURCE_DIR}/../comm)
    set(ASYNC_DIR ${CMAKE_CURRENT_SOURCE_DIR}/async)
else()
    set(BASE_DIR "${TOP_DIR}/hcomm/src/platform/hccp/rdma_agent/comm")
    set(ASYNC_DIR "${TOP_DIR}/hcomm/src/platform/hccp/rdma_agent/hdc/async")
endif()

set(ra_hdc_list ra_hdc.c
    ${BASE_DIR}/ra_comm.c
    ra_rdma_lite.c
    ra_hdc_lite.c
    ra_hdc_ping.c
    ra_hdc_socket.c
    ra_hdc_rdma.c
    ra_hdc_tlv.c
    ${ASYNC_DIR}/ra_hdc_async.c
    ${ASYNC_DIR}/ra_hdc_async_socket.c
    ${CMAKE_CURRENT_SOURCE_DIR}/../../common/dl_hal_function.c
    ${CMAKE_CURRENT_SOURCE_DIR}/../../common/ascend_hal_dl.c
)

add_library(ra_hdc SHARED ${ra_hdc_list})

if(BUILD_OPEN_PROJECT)
    target_compile_definitions(ra_hdc PRIVATE
        OPEN_BUILD_PROJECT
        LOG_CPP)

    target_include_directories(ra_hdc PRIVATE
        ${CMAKE_CURRENT_SOURCE_DIR}/../inc
        ${CMAKE_CURRENT_SOURCE_DIR}/../../inc/network
        ${CMAKE_CURRENT_SOURCE_DIR}/../../inc/private
        ${CMAKE_CURRENT_SOURCE_DIR}/../../rdma_service
        ${CMAKE_CURRENT_SOURCE_DIR}/../../inc/private/network
        ${BASE_DIR}/
        ${CMAKE_CURRENT_SOURCE_DIR}/
        ${ASYNC_DIR}/
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
        ${CMAKE_CURRENT_SOURCE_DIR}/../../external_depends/rdma-core/providers/hns
        ${CMAKE_CURRENT_SOURCE_DIR}/../../external_depends/host_lite
    )

    target_link_directories(ra_hdc PRIVATE
        ${ASCEND_CANN_PACKAGE_PATH}/lib64
    )
    if (DEVICE_MODE)
        target_link_directories(ra_hdc PRIVATE
            ${ASCEND_CANN_PACKAGE_PATH}/devlib/device/ # c_sec、mmpa、unified_dlog动态库搜索路径
        )
    endif()
else()
    target_include_directories(ra_hdc PRIVATE
        ${TOP_DIR}/inc/driver
        ${TOP_DIR}/hcomm/src/platform/hccp/inc/network
        ${TOP_DIR}/hcomm/src/platform/hccp/inc/private/network
        ${TOP_DIR}/hcomm/src/platform/hccp/rdma_agent/inc
        ${TOP_DIR}/hcomm/src/platform/hccp/rdma_service
        ${TOP_DIR}/hcomm/src/platform/hccp/rdma_agent/comm
        ${TOP_DIR}/hcomm/src/platform/hccp/rdma_agent/hdc
        ${TOP_DIR}/hcomm/src/platform/hccp/rdma_agent/hdc/async
        ${TOP_DIR}/hcomm/src/platform/hccp/common/
        ${TOP_DIR}/hcomm/src/platform/hccp/external_depends/host_lite
        ${TOP_DIR}/hcomm/src/platform/hccp/external_depends/rdma-core/providers/hns
    )
endif()

target_compile_options(ra_hdc PRIVATE
    -Werror -fno-common -fsigned-char -fno-strict-aliasing -std=gnu11 -Wextra
    -fstack-protector-strong
    $<$<CONFIG:Debug>:-g>
)

target_compile_definitions(ra_hdc PRIVATE

)

target_link_options(ra_hdc PRIVATE
    -Wl,-z,now
    $<$<CONFIG:Release>:-s>
)

if(BUILD_OPEN_PROJECT)
    target_link_libraries(ra_hdc PRIVATE
        -Wl,--no-as-needed
        c_sec
        $<$<STREQUAL:${PRODUCT_SIDE},host>:unified_dlog>
        -Wl,--as-needed
        -lrt
        -ldl
    )
else()
    target_link_libraries(ra_hdc PRIVATE
    $<BUILD_INTERFACE:intf_pub>
    $<BUILD_INTERFACE:slog_headers>
    -Wl,--no-as-needed
    c_sec
    slog
    -Wl,--as-needed
    -lrt
    -ldl
    ofed_headers
    )
endif()

target_compile_definitions(ra_hdc PRIVATE
    LOG_HOST
)

install(TARGETS  ra_hdc
    LIBRARY DESTINATION ${INSTALL_LIBRARY_DIR}  OPTIONAL
)

# install_package(
#     PACKAGE ra_hdc
#     TARGETS ra_hdc
# )