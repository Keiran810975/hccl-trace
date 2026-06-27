if(BUILD_OPEN_PROJECT)
    set(CRYP_DIR ${CMAKE_CURRENT_SOURCE_DIR}/../crypt)
    set(TLV_DIR ${CMAKE_CURRENT_SOURCE_DIR}/tlv)
else()
    set(CRYP_DIR ${TOP_DIR}/hccl/src/platform/hccp/crypt)
    set(TLV_DIR ${TOP_DIR}/hcomm/src/platform/hccp/rdma_service/tlv)
endif()

set(rs_list
    rs.c
    rs_epoll.c
    rs_ping.c
    rs_ping_inner.c
    rs_ping_roce.c
    rs_socket.c
    rs_rdma.c
    rs_drv_rdma.c
    rs_drv_socket.c
    dl_ibverbs_function.c
    hccp_dl.c
    ${CMAKE_CURRENT_SOURCE_DIR}/../common/dl_hal_function.c
    ${CMAKE_CURRENT_SOURCE_DIR}/../common/ascend_hal_dl.c
    $<$<NOT:$<STREQUAL:${PRODUCT},ascend310p>>:${CMAKE_CURRENT_SOURCE_DIR}/../common/file_opt.c>
    $<$<NOT:$<STREQUAL:${PRODUCT},ascend310p>>:${CMAKE_CURRENT_SOURCE_DIR}/../common/network_comm.c>
)

if((("${PRODUCT}" STREQUAL "ascend910B") OR ("${PRODUCT}" STREQUAL "ascend")) AND
   ("${PRODUCT_SIDE}" STREQUAL "device") AND
   (NOT ${USE_ALOG}))
list(APPEND rs_list
    ${TLV_DIR}/dl_netco_function.c
    ${TLV_DIR}/rs_tlv.c
    ${TLV_DIR}/rs_adp_nslb.c
)
endif()

add_library(rs  SHARED ${rs_list})

if(BUILD_OPEN_PROJECT)
    target_compile_definitions(rs PRIVATE
        OPEN_BUILD_PROJECT
        LOG_CPP)

    target_include_directories(rs PRIVATE
        ${CMAKE_CURRENT_SOURCE_DIR}/
        ${CMAKE_CURRENT_SOURCE_DIR}/../inc
        ${CMAKE_CURRENT_SOURCE_DIR}/../inc/network
        ${CMAKE_CURRENT_SOURCE_DIR}/../inc/private/network
        ${CMAKE_CURRENT_SOURCE_DIR}/../common/
        ${CMAKE_CURRENT_SOURCE_DIR}/../crypt/inc

        ${ASCEND_CANN_PACKAGE_PATH}/pkg_inc/base/
        ${ASCEND_CANN_PACKAGE_PATH}/include/
        ${ASCEND_CANN_PACKAGE_PATH}/include/toolchain/
        ${ASCEND_CANN_PACKAGE_PATH}/include/driver/
        ${ASCEND_CANN_PACKAGE_PATH}/pkg_inc

        # runtime头文件
        ${ASCEND_CANN_PACKAGE_PATH}/include/

        # 第三方库依赖路径
        ${OPENSSL_INCLUDE_DIR}
        ${CMAKE_BINARY_DIR}/hcomm_utils/${PRODUCT_SIDE}/include/tls_adp
        ${CMAKE_BINARY_DIR}/hcomm_utils/${PRODUCT_SIDE}/include/kms

        # rdma头文件
        ${CMAKE_CURRENT_SOURCE_DIR}/../external_depends/rdma-core/include
        ${CMAKE_CURRENT_SOURCE_DIR}/../external_depends/host_lite
        ${CMAKE_CURRENT_SOURCE_DIR}/../external_depends/rdma-core/providers/hns
    )

    target_link_directories(rs PRIVATE
        ${ASCEND_CANN_PACKAGE_PATH}/devlib/device/ # c_sec、mmpa、unified_dlog动态库搜索路径
    )
else()
    #头文件搜索路径
    target_include_directories(rs PRIVATE
        ${TOP_DIR}/hcomm/src/platform/hccp/inc/network
        ${TOP_DIR}/hcomm/src/platform/hccp/inc/private/network
        ${TOP_DIR}/inc/driver
        ${TOP_DIR}/hcomm/src/platform/hccp/common
        ${TOP_DIR}/hcomm/src/platform/hccp/crypt/inc
        ${TOP_DIR}/hcomm/src/platform/hccp/rdma_service/
        ${TOP_DIR}/hcomm/src/platform/hccp/external_depends/rdma-core/providers/hns
    )
endif()


if((("${PRODUCT}" STREQUAL "ascend910B") OR ("${PRODUCT}" STREQUAL "ascend")) AND
   ("${PRODUCT_SIDE}" STREQUAL "device") AND (NOT ${USE_ALOG}))
    target_include_directories(rs PRIVATE
        ${TLV_DIR}
    )

    target_compile_definitions(rs PRIVATE
        CUSTOM_INTERFACE google=ascend_private
        CONFIG_TLV
    )
endif()

target_compile_options(rs PRIVATE
    -Werror -fvisibility=hidden -fno-strict-aliasing -fsigned-char -fno-common -Wfloat-equal
    -Wextra -Wno-unused-parameter -std=gnu11
    -fstack-protector-strong
    $<$<CONFIG:Debug>:-g>
)

target_link_options(rs PRIVATE
    -Wl,-Bsymbolic -Wl,--exclude-libs,ALL
    -Wl,-z,now
    $<$<CONFIG:Release>:-s>
    # -rdynamic -Wl,--no-undefined
)

if(NOT (PRODUCT IN_LIST ASCEND910_95_PRODUCT_LIST) AND
   NOT (PRODUCT IN_LIST ASCEND910_96_PRODUCT_LIST) AND
   NOT (PRODUCT IN_LIST ASCEND910_55_PRODUCT_LIST) AND
   NOT (PRODUCT STREQUAL "ascend310p"))
target_compile_definitions(rs PRIVATE
    CONFIG_SSL
)
endif()

target_compile_definitions(rs PRIVATE
    $<$<AND:$<STREQUAL:${PRODUCT},ascend310p>,$<STREQUAL:${PRODUCT_SIDE},device>>:NOT_INIT_IBVERBS>
)

if(("${USE_ALOG}" STREQUAL "1"))
target_compile_definitions(rs PRIVATE
    LOG_HOST
)
endif()

if(BUILD_OPEN_PROJECT)
    target_link_libraries(rs PRIVATE
        -Wl,--no-as-needed
        c_sec
        $<$<STREQUAL:${PRODUCT_SIDE},host>:unified_dlog>
        $<$<NOT:$<STREQUAL:${PRODUCT},ascend310p>>:tls_adp>
        -Wl,--as-needed
        -Wl,--whole-archive
        -Wl,--no-whole-archive
        -lrt
        -ldl
    )
else()
#链接动态库
    target_link_libraries(rs PRIVATE
        $<BUILD_INTERFACE:intf_pub>
        $<BUILD_INTERFACE:mmpa_headers>
        $<BUILD_INTERFACE:slog_headers>
        -Wl,--no-as-needed
        c_sec
        slog
        mmpa
        -Wl,--as-needed

        -Wl,--whole-archive
        $<$<STREQUAL:${PRODUCT_SIDE},device>:ascend_protobuf_static>
        crypto_static
        -Wl,--no-whole-archive
        kmc
        sdp
        -lrt
        -ldl
        ofed_headers
    )
endif()

install(TARGETS  rs
    LIBRARY DESTINATION ${INSTALL_LIBRARY_DIR}  OPTIONAL
)

add_dependencies(rs crypto_static)
