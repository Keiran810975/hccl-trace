set(BASIC_PATH ${CMAKE_CURRENT_SOURCE_DIR}/../../)

set(TLV_DIR ${BASIC_PATH}/rdma_agent/adapter/tlv)
set(ra_adp_list
    ra_adp.c
    ra_adp_socket.c
    ${BASIC_PATH}/rdma_agent/adapter/async/ra_adp_pool.c
    ${BASIC_PATH}/rdma_agent/adapter/async/ra_adp_async.c
)

if((("${PRODUCT}" STREQUAL "ascend910B") OR ("${PRODUCT}" STREQUAL "ascend")) AND
   ("${PRODUCT_SIDE}" STREQUAL "device") AND
   (NOT ${USE_ALOG}))
list(APPEND ra_adp_list
    ${TLV_DIR}/ra_adp_tlv.c
)
endif()

#编译目标
add_library(ra_adp SHARED
    ${ra_adp_list}
    ${BASIC_PATH}/common/dl_hal_function.c
    ${BASIC_PATH}/common/ascend_hal_dl.c
)

#添加头文件搜索路径
if(BUILD_OPEN_PROJECT)
    target_compile_definitions(ra_adp PRIVATE OPEN_BUILD_PROJECT LOG_CPP)

    target_include_directories(ra_adp PRIVATE
        ${BASIC_PATH}/external_depends/inc/driver
        ${BASIC_PATH}/external_depends/inc/log
        ${BASIC_PATH}/external_depends/rdma-core/include
        ${BASIC_PATH}/inc/network
        ${BASIC_PATH}/inc/private/network
        ${BASIC_PATH}/rdma_agent/inc
        ${BASIC_PATH}/rdma_agent/hdc/
        ${BASIC_PATH}/rdma_agent/hdc/async/
        ${BASIC_PATH}/rdma_agent/comm
        ${BASIC_PATH}/rdma_agent/adapter
        ${BASIC_PATH}/rdma_agent/adapter/async/
        ${BASIC_PATH}/rdma_service
        ${BASIC_PATH}/common

        # runtime头文件
        ${ASCEND_CANN_PACKAGE_PATH}/include/

        # rdma头文件
        ${BASIC_PATH}/external_depends/host_lite
    )

    target_link_directories(ra_adp PRIVATE
        ${ASCEND_CANN_PACKAGE_PATH}/devlib/device/ # c_sec、mmpa、unified_dlog动态库搜索路径
    )
endif()

if((("${PRODUCT}" STREQUAL "ascend910B") OR ("${PRODUCT}" STREQUAL "ascend")) AND
   ("${PRODUCT_SIDE}" STREQUAL "device") AND
   (NOT ${USE_ALOG}))
target_include_directories(ra_adp PRIVATE
    ${TLV_DIR}
    ${BASIC_PATH}/rdma_service/tlv
)

target_compile_definitions(ra_adp PRIVATE
    CONFIG_TLV
)
endif()

#编译选项
target_compile_options(ra_adp PRIVATE
    -Werror -fvisibility=hidden -fsigned-char -fno-common -fno-strict-aliasing -std=gnu11
    -fstack-protector-strong
    $<$<CONFIG:Debug>:-g>
)

target_link_options(ra_adp PRIVATE
    -Wl,-Bsymbolic
    -rdynamic
    -Wl,--no-undefined
    -Wl,-z,now
    $<$<CONFIG:Release>:-s>
)

#链接动态库
if(BUILD_OPEN_PROJECT)
    target_link_libraries(ra_adp PRIVATE
        # $<BUILD_INTERFACE:intf_pub>
        # $<BUILD_INTERFACE:slog_headers>
        # $<BUILD_INTERFACE:network_headers>
        -Wl,--no-as-needed
        rs
        c_sec
        unified_dlog
        -Wl,--as-needed
        -lrt
        -ldl
        -pthread
        # ofed_headers
    )
endif()

install(TARGETS  ra_adp
    LIBRARY DESTINATION ${INSTALL_LIBRARY_DIR}  OPTIONAL
)