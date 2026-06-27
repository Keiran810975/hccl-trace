
if(BUILD_OPEN_PROJECT)
    set(BASE_DIR ${CMAKE_CURRENT_SOURCE_DIR}/../comm)
else()
    set(BASE_DIR "${TOP_DIR}/hcomm/src/platform/hccp/rdma_agent/comm")
endif()

set(ra_peer_list
    ra_peer.c
    ra_peer_socket.c
    ${BASE_DIR}/ra_comm.c
    ${CMAKE_CURRENT_SOURCE_DIR}/../../common/dl_hal_function.c
    ${CMAKE_CURRENT_SOURCE_DIR}/../../common/ascend_hal_dl.c
    )


#编译目标
add_library(ra_peer SHARED ${ra_peer_list})

if(BUILD_OPEN_PROJECT)
    target_compile_definitions(ra_peer PRIVATE
        OPEN_BUILD_PROJECT
        LOG_CPP)

    target_include_directories(ra_peer PRIVATE
        ${BASE_DIR}/
        ${CMAKE_CURRENT_SOURCE_DIR}/
        ${CMAKE_CURRENT_SOURCE_DIR}/../inc
        ${CMAKE_CURRENT_SOURCE_DIR}/../../rdma_service
        ${CMAKE_CURRENT_SOURCE_DIR}/../../inc/network
        ${CMAKE_CURRENT_SOURCE_DIR}/../../inc/private/network
        ${CMAKE_CURRENT_SOURCE_DIR}/../../common/

        ${ASCEND_CANN_PACKAGE_PATH}/pkg_inc/base/
        ${ASCEND_CANN_PACKAGE_PATH}/include/
        ${ASCEND_CANN_PACKAGE_PATH}/include/toolchain/
        ${ASCEND_CANN_PACKAGE_PATH}/include/driver/
        ${ASCEND_CANN_PACKAGE_PATH}/pkg_inc

        # rdma头文件
        ${CMAKE_CURRENT_SOURCE_DIR}/../../external_depends/rdma-core/include
        ${CMAKE_CURRENT_SOURCE_DIR}/../../external_depends/host_lite
    )

    target_link_directories(ra_peer PRIVATE
        ${ASCEND_CANN_PACKAGE_PATH}/lib64
    )
    if (DEVICE_MODE)
        target_link_directories(ra_peer PRIVATE
            ${ASCEND_CANN_PACKAGE_PATH}/devlib/device/ # c_sec、mmpa、unified_dlog动态库搜索路径
        )
    endif()
else()
    #添加头文件搜索路径
    target_include_directories(ra_peer PRIVATE
        ${TOP_DIR}/hcomm/src/platform/hccp/inc/network
        ${TOP_DIR}/hcomm/src/platform/hccp/inc/private/network
        ${TOP_DIR}/hcomm/src/platform/hccp/rdma_agent/inc
        ${TOP_DIR}/hcomm/src/platform/hccp/rdma_service
        ${TOP_DIR}/inc/driver
        ${TOP_DIR}/hcomm/src/platform/hccp/rdma_agent/comm
        ${TOP_DIR}/hcomm/src/platform/hccp/common
        ${TOP_DIR}/hcomm/src/platform/hccp/external_depends/host_lite
    )
endif()


target_compile_options(ra_peer PRIVATE
    -Werror -std=gnu11 -fno-common -Wfloat-equal -Wextra
    -fstack-protector-strong
    $<$<CONFIG:Debug>:-g>
)

target_link_options(ra_peer PRIVATE
    -Wl,-z,now
    $<$<CONFIG:Release>:-s>
)

if(BUILD_OPEN_PROJECT)
    target_link_libraries(ra_peer PRIVATE
        -Wl,--no-as-needed
        rs
        c_sec
        $<$<STREQUAL:${PRODUCT_SIDE},host>:unified_dlog>
        -Wl,--as-needed
        -ldl
    )
else()
#链接动态库
    target_link_libraries(ra_peer PRIVATE
        $<BUILD_INTERFACE:intf_pub>
        $<BUILD_INTERFACE:slog_headers>
        -Wl,--no-as-needed
        rs
        c_sec
        slog
        -Wl,--as-needed
        -ldl
        ofed_headers
    )
endif()

target_compile_definitions(ra_peer PRIVATE
    LOG_HOST
)

install(TARGETS  ra_peer
    LIBRARY DESTINATION ${INSTALL_LIBRARY_DIR}  OPTIONAL
)

# install_package(
#     PACKAGE ra_peer
#     TARGETS ra_peer
# )