# -----------------------------------------------------------------------------------------------------------
# Copyright (c) 2025 Huawei Technologies Co., Ltd.
# This program is free software, you can redistribute it and/or modify it under the terms and conditions of
# CANN Open Software License Agreement Version 2.0 (the "License").
# Please refer to the License for details. You may not use this file except in compliance with the License.
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
# See LICENSE in the root of the software repository for the full text of the License.
# -----------------------------------------------------------------------------------------------------------
set(HCCL_PACKET_FLAG 1)

set(CMAKE_CXX_STANDARD 14)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

# set(CMAKE_CXX_FLAGS "${CMAKE_CXX_FLAGS} -D_GLIBCXX_USE_CXX11_ABI=0")

#组件间对外头文件目录
add_library(hccl_headers INTERFACE)
target_include_directories(hccl_headers INTERFACE
    $<BUILD_INTERFACE:${TOP_DIR}/hcomm/include>
    $<BUILD_INTERFACE:${TOP_DIR}/hcomm/include/hccl>
    $<INSTALL_INTERFACE:include>
    $<INSTALL_INTERFACE:include/hccl>
    $<INSTALL_INTERFACE:include/hccl/external>
    $<INSTALL_INTERFACE:include/hccl/external/hccl>
)

if(BUILD_OPEN_PROJECT)
    message(STATUS "open TOP_DIR = ${TOP_DIR}")
    set(HCCL_BASE_DIR ${CMAKE_CURRENT_SOURCE_DIR}/)
    set(HCCL_THIRD_PARTY_DIR ${HCCL_BASE_DIR}/../../../../../../../)
else()
    message(STATUS "close TOP_DIR = ${TOP_DIR}")
    set(HCCL_BASE_DIR ${TOP_DIR}/hcomm/src/)
    set(HCCL_THIRD_PARTY_DIR ${TOP_DIR})
endif()

add_library(hccd  SHARED)

#需要编译的文件list
set(include_list
    ${HCCL_BASE_DIR}/pub_inc
    ${HCCL_BASE_DIR}/pub_inc/aicpu/
    ${HCCL_BASE_DIR}/pub_inc/inner
    ${HCCL_BASE_DIR}/pub_inc/new

    ${HCCL_BASE_DIR}/algorithm/base/inc
    ${HCCL_BASE_DIR}/algorithm/pub_inc
    ${HCCL_BASE_DIR}/algorithm/base/alg_aiv_template
    ${HCCL_BASE_DIR}/algorithm/base/alg_template
    ${HCCL_BASE_DIR}/algorithm/base/alg_template/component
    ${HCCL_BASE_DIR}/algorithm/base/mc2_handler
    ${HCCL_BASE_DIR}/algorithm/base/communicator
    ${HCCL_BASE_DIR}/algorithm/impl
    ${HCCL_BASE_DIR}/algorithm/impl/inc
    ${HCCL_BASE_DIR}/algorithm/impl/legacy
    ${HCCL_BASE_DIR}/algorithm/impl/legacy/operator
    ${HCCL_BASE_DIR}/algorithm/base/communicator/legacy
    ${HCCL_BASE_DIR}/algorithm/impl/resource_manager
    ${HCCL_BASE_DIR}/algorithm/impl/task
    ${HCCL_BASE_DIR}/algorithm/impl/operator
    ${HCCL_BASE_DIR}/algorithm/impl/operator/registry
    ${HCCL_BASE_DIR}/algorithm/impl/coll_executor
    ${HCCL_BASE_DIR}/algorithm/impl/coll_executor/registry
    ${HCCL_BASE_DIR}/algorithm/impl/coll_executor/coll_send_receive
    ${HCCL_BASE_DIR}/algorithm/impl/coll_executor/coll_all_reduce
    ${HCCL_BASE_DIR}/algorithm/impl/coll_executor/coll_all_reduce/310P
    ${HCCL_BASE_DIR}/algorithm/impl/coll_executor/coll_all_gather
    ${HCCL_BASE_DIR}/algorithm/impl/coll_executor/coll_all_gather/310P
    ${HCCL_BASE_DIR}/algorithm/impl/coll_executor/coll_all_gather_v
    ${HCCL_BASE_DIR}/algorithm/impl/coll_executor/coll_reduce_scatter
    ${HCCL_BASE_DIR}/algorithm/impl/coll_executor/coll_reduce_scatter/310P
    ${HCCL_BASE_DIR}/algorithm/impl/coll_executor/coll_reduce_scatter_v
    ${HCCL_BASE_DIR}/algorithm/impl/coll_executor/coll_reduce_scatter_v/310P
    ${HCCL_BASE_DIR}/algorithm/impl/coll_executor/coll_all_to_all
    ${HCCL_BASE_DIR}/algorithm/impl/coll_executor/coll_scatter
    ${HCCL_BASE_DIR}/algorithm/base/alg_template/temp_all_gather
    ${HCCL_BASE_DIR}/algorithm/base/alg_template/temp_all_reduce
    ${HCCL_BASE_DIR}/algorithm/base/alg_template/temp_alltoall
    ${HCCL_BASE_DIR}/algorithm/base/alg_template/temp_alltoallv
    ${HCCL_BASE_DIR}/algorithm/base/alg_template/temp_broadcast
    ${HCCL_BASE_DIR}/algorithm/base/alg_template/temp_reduce
    ${HCCL_BASE_DIR}/algorithm/base/alg_template/temp_reduce_scatter
    ${HCCL_BASE_DIR}/algorithm/base/alg_template/temp_scatter
    ${HCCL_BASE_DIR}/algorithm/base/alg_template
    ${HCCL_BASE_DIR}/algorithm/pub_inc

    ${HCCL_BASE_DIR}/common/health
    ${HCCL_BASE_DIR}/common/debug/profiling/inc
    ${HCCL_BASE_DIR}/common/debug/config/
    ${HCCL_BASE_DIR}/common/stream
    ${HCCL_BASE_DIR}/common/launch_device

    ${HCCL_BASE_DIR}/framework/inc
    ${HCCL_BASE_DIR}/framework/inc/hccd
    ${HCCL_BASE_DIR}/framework/cluster_maintenance/health/heartbeat/
    ${HCCL_BASE_DIR}/framework/cluster_maintenance/detect/detect_connect_anomalies/
    ${HCCL_BASE_DIR}/framework/cluster_maintenance/recovery/operator_retry
    ${HCCL_BASE_DIR}/framework/
    ${HCCL_BASE_DIR}/framework/common/src/
    ${HCCL_BASE_DIR}/framework/common/src/exception
    ${HCCL_BASE_DIR}/framework/common/src/config
    ${HCCL_BASE_DIR}/framework/common/src/task
    ${HCCL_BASE_DIR}/framework/common/src/topo
    ${HCCL_BASE_DIR}/framework/common/src/mgr
    ${HCCL_BASE_DIR}/framework/hcom
    ${HCCL_BASE_DIR}/framework/communicator/impl/
    ${HCCL_BASE_DIR}/framework/communicator/impl/one_sided_service/
    ${HCCL_BASE_DIR}/framework/communicator/impl/zero_copy_memory_agent
    ${HCCL_BASE_DIR}/framework/communicator/impl/resource_manager
    ${HCCL_BASE_DIR}/framework/communicator/impl/independent_op
    ${HCCL_BASE_DIR}/framework/communicator/impl/independent_op/rank_graph
    ${HCCL_BASE_DIR}/framework/communicator/impl/independent_op/resource/engine
    ${HCCL_BASE_DIR}/framework/communicator/impl/independent_op/channel
    ${HCCL_BASE_DIR}/framework/communicator/impl/independent_op/channel/device
    ${HCCL_BASE_DIR}/framework/op_base/src/

    ${HCCL_BASE_DIR}/platform/inc
    ${HCCL_BASE_DIR}/platform/inc/adapter
    ${HCCL_BASE_DIR}/platform/inc/adapter/hccd
    ${HCCL_BASE_DIR}/platform/resource/dispatcher_ctx
    ${HCCL_BASE_DIR}/platform/common/
    ${HCCL_BASE_DIR}/platform/common/unique
    ${HCCL_BASE_DIR}/platform/common/buffer_manager
    ${HCCL_BASE_DIR}/platform/common/unfold_cache
    ${HCCL_BASE_DIR}/platform/resource/transport
    ${HCCL_BASE_DIR}/platform/resource/transport/device
    ${HCCL_BASE_DIR}/platform/resource/transport/host
    ${HCCL_BASE_DIR}/platform/resource/transport/heterog
    ${HCCL_BASE_DIR}/platform/resource/transport/onesided
    ${HCCL_BASE_DIR}/platform/resource/transport/onesided/device
    ${HCCL_BASE_DIR}/platform/resource/notify
    ${HCCL_BASE_DIR}/platform/ping_mesh
    ${HCCL_BASE_DIR}/platform/resource/socket
    ${HCCL_BASE_DIR}/platform/task
    ${CMAKE_BINARY_DIR}/hcomm_utils/${PRODUCT_SIDE}/include/legacy
    ${HCCL_BASE_DIR}/platform/aiv_communication
    ${HCCL_BASE_DIR}/platform/typical
)

# 指定hccd所需包含文件搜索路径
if(BUILD_OPEN_PROJECT)
    target_compile_definitions(hccd PRIVATE
        OPEN_BUILD_PROJECT)

    target_include_directories(hccd PRIVATE
        ${HCCL_BASE_DIR}/../include
        ${HCCL_BASE_DIR}/../include/hccl
        ${HCCL_BASE_DIR}/../pkg_inc
        ${HCCL_BASE_DIR}/../pkg_inc/hccl
        ${HCCL_BASE_DIR}/platform/hccp/inc
        ${HCCL_BASE_DIR}/platform/hccp/inc/network
        ${HCCL_BASE_DIR}/platform/hccp/external_depends/rdma-core/include # 解决头文件依赖问题<infiniband/verbs.h>

        # runtime头文件
        ${ASCEND_CANN_PACKAGE_PATH}/include/

        # mmpa头文件
        ${ASCEND_CANN_PACKAGE_PATH}/include/mmpa/

        # driver头文件
        ${ASCEND_CANN_PACKAGE_PATH}/include/driver/

        # 包间接口
        ${ASCEND_CANN_PACKAGE_PATH}/pkg_inc/
        ${ASCEND_CANN_PACKAGE_PATH}/pkg_inc/aicpu/
        ${ASCEND_CANN_PACKAGE_PATH}/pkg_inc/aicpu/common/
        ${ASCEND_CANN_PACKAGE_PATH}/pkg_inc/runtime/
        ${ASCEND_CANN_PACKAGE_PATH}/pkg_inc/profiling/
        ${ASCEND_CANN_PACKAGE_PATH}/pkg_inc/base/
        ${ASCEND_CANN_PACKAGE_PATH}/pkg_inc/dump/
        ${ASCEND_CANN_PACKAGE_PATH}/pkg_inc/trace/

        # 临时依赖，后续删除
        ${HCCL_BASE_DIR}/../externel_depends/tsch/
        ${HCCL_BASE_DIR}/platform/hccp/external_depends/rdma-core/include

        ${THIRD_PARTY_NLOHMANN_PATH}
    )

    target_link_directories(hccd PRIVATE
        ${ASCEND_CANN_PACKAGE_PATH}/devlib/device/ # c_sec、mmpa、unified_dlog动态库搜索路径
    )
else()
    target_include_directories(hccd PRIVATE
        ${TOP_DIR}/inc
        ${TOP_DIR}/inc/driver
        ${TOP_DIR}/runtime/include/external
        ${TOP_DIR}/inc/aicpu/
        ${TOP_DIR}/abl/msprof/inc
        ${TOP_DIR}/ace/npuruntime/inc
        ${TOP_DIR}/ace/npuruntime/inc/runtime

        ${TOP_DIR}/open_source/json/include
        ${TOP_DIR}/hcomm/
        ${TOP_DIR}/hcomm/include/hccl/                      # ${ASCEND_CANN_PACKAGE_PATH}/include
        ${TOP_DIR}/hcomm/pkg_inc
        ${TOP_DIR}/hcomm/src/platform/hccp/inc
        ${TOP_DIR}/hcomm/src/platform/hccp/inc/network
    )
endif()


target_include_directories(hccd PRIVATE
    ${include_list}
    ${HCCL_BASE_DIR}/hccl/hccl_comm/comm/inc/inc_all_reduce_deter
    ${HCCL_BASE_DIR}/hccl/hccl_comm/wrapper/notify/
    ${HCCL_BASE_DIR}/algorithm/pub_inc
    ${HCCL_BASE_DIR}/algorithm/impl
    ${HCCL_BASE_DIR}/common/debug/profiling/inc
    ${HCCL_BASE_DIR}/common/debug/profiling/inc/host
    ${HCCL_BASE_DIR}/common/debug/config
    ${HCCL_BASE_DIR}/framework/common/src/aicpu
)

#hccd 编译选项
target_compile_options(hccd PRIVATE
    -Werror
    -Wall
    -fno-common
    -fstack-protector-strong
    -fno-strict-aliasing
    -pipe
    -O3
    -std=c++14
    $<$<CONFIG:Debug>:-g>
)

#hccd 编译宏
target_compile_definitions(hccd PRIVATE
    HCCD
)

target_link_options(hccd PRIVATE
    -Wl,-z,relro
    -Wl,-z,now
    -Wl,-z,noexecstack
    $<$<CONFIG:Release>:-s>
)

if(BUILD_OPEN_PROJECT)
    target_link_libraries(hccd
        -Wl,--no-as-needed
        c_sec
        mmpa
        -Wl,--as-needed
        -lrt
        -ldl
        -lpthread
    )
else()
    target_link_libraries(hccd
        $<BUILD_INTERFACE:intf_pub_cxx14>
        $<BUILD_INTERFACE:hccl_headers>
        -Wl,--no-as-needed
        c_sec
        slog
        mmpa
        -Wl,--as-needed
        -lrt
        -ldl
        -lpthread
        ofed_headers
    )
endif()

message(STATUS "ccl_kernel_plf KERNEL_MODE=${KERNEL_MODE}")
message(STATUS "ccl_kernel_plf BUILD_OPEN_PROJECT=${BUILD_OPEN_PROJECT}")
message(STATUS "ccl_kernel_plf ASCEND_CANN_PACKAGE_PATH=${ASCEND_CANN_PACKAGE_PATH}")

# 创建 ccl_kernel_plf共享库
add_library(ccl_kernel_plf  SHARED)
# 创建 ccl_kernel_plf_a静态库
add_library(ccl_kernel_plf_a  STATIC)

# 指定ccl_kernel_plf所需包含文件搜索路径
if(BUILD_OPEN_PROJECT)
    target_compile_definitions(ccl_kernel_plf PRIVATE
        OPEN_BUILD_PROJECT)

    target_compile_definitions(ccl_kernel_plf_a PRIVATE
        OPEN_BUILD_PROJECT)

    target_include_directories(ccl_kernel_plf PRIVATE
        ${HCCL_BASE_DIR}/../include
        ${HCCL_BASE_DIR}/../include/hccl
        ${HCCL_BASE_DIR}/../pkg_inc
        ${HCCL_BASE_DIR}/../pkg_inc/hccl
        ${HCCL_BASE_DIR}/pub_inc
        ${HCCL_BASE_DIR}/platform/hccp/inc
        ${HCCL_BASE_DIR}/platform/hccp/inc/network
        ${HCCL_BASE_DIR}/platform/hccp/external_depends/rdma-core/include # 解决头文件依赖问题<infiniband/verbs.h>

        # runtime头文件
        ${ASCEND_CANN_PACKAGE_PATH}/include/

        # mmpa头文件
        ${ASCEND_CANN_PACKAGE_PATH}/include/mmpa/

        # 包间接口
        ${ASCEND_CANN_PACKAGE_PATH}/pkg_inc/
        ${ASCEND_CANN_PACKAGE_PATH}/pkg_inc/aicpu/
        ${ASCEND_CANN_PACKAGE_PATH}/pkg_inc/aicpu/common/
        ${ASCEND_CANN_PACKAGE_PATH}/pkg_inc/runtime/
        ${ASCEND_CANN_PACKAGE_PATH}/pkg_inc/profiling/
        ${ASCEND_CANN_PACKAGE_PATH}/pkg_inc/base/
        ${ASCEND_CANN_PACKAGE_PATH}/pkg_inc/dump/
        ${ASCEND_CANN_PACKAGE_PATH}/pkg_inc/trace/

        # driver头文件
        ${ASCEND_CANN_PACKAGE_PATH}/include/driver

        # 临时依赖头文件，待删除
        ${HCCL_BASE_DIR}/../externel_depends/tsch/
        ${HCCL_BASE_DIR}/platform/hccp/external_depends/rdma-core/include

        ${THIRD_PARTY_NLOHMANN_PATH}
    )

    target_include_directories(ccl_kernel_plf_a PRIVATE
        ${HCCL_BASE_DIR}/../include
        ${HCCL_BASE_DIR}/../include/hccl
        ${HCCL_BASE_DIR}/../pkg_inc
        ${HCCL_BASE_DIR}/../pkg_inc/hccl
        ${HCCL_BASE_DIR}/pub_inc
        ${HCCL_BASE_DIR}/platform/hccp/inc
        ${HCCL_BASE_DIR}/platform/hccp/inc/network
        ${HCCL_BASE_DIR}/platform/hccp/external_depends/rdma-core/include # 解决头文件依赖问题<infiniband/verbs.h>

        # runtime头文件
        ${ASCEND_CANN_PACKAGE_PATH}/include/

        # mmpa头文件
        ${ASCEND_CANN_PACKAGE_PATH}/include/mmpa/

        # driver头文件
        ${ASCEND_CANN_PACKAGE_PATH}/include/driver

        # 包间接口
        ${ASCEND_CANN_PACKAGE_PATH}/pkg_inc/
        ${ASCEND_CANN_PACKAGE_PATH}/pkg_inc/aicpu/
        ${ASCEND_CANN_PACKAGE_PATH}/pkg_inc/aicpu/common/
        ${ASCEND_CANN_PACKAGE_PATH}/pkg_inc/runtime/
        ${ASCEND_CANN_PACKAGE_PATH}/pkg_inc/profiling/
        ${ASCEND_CANN_PACKAGE_PATH}/pkg_inc/base/
        ${ASCEND_CANN_PACKAGE_PATH}/pkg_inc/dump/
        ${ASCEND_CANN_PACKAGE_PATH}/pkg_inc/trace/

        # 临时依赖头文件，待删除
        ${HCCL_BASE_DIR}/../externel_depends/tsch/
        ${HCCL_BASE_DIR}/platform/hccp/external_depends/rdma-core/include

        ${THIRD_PARTY_NLOHMANN_PATH}
    )

    target_link_directories(ccl_kernel_plf PRIVATE
        ${ASCEND_CANN_PACKAGE_PATH}/devlib/device/ # c_sec、mmpa、unified_dlog动态库搜索路径
    )

    target_link_directories(ccl_kernel_plf_a PRIVATE
        ${ASCEND_CANN_PACKAGE_PATH}/devlib/device/ # c_sec、mmpa、unified_dlog动态库搜索路径
    )
else()
    target_include_directories(ccl_kernel_plf PRIVATE
        ${TOP_DIR}/inc
        ${TOP_DIR}/inc/aicpu/tsd
        ${TOP_DIR}/inc/driver
        ${TOP_DIR}/runtime/include/external
        ${TOP_DIR}/runtime/include/external/acl
        ${TOP_DIR}/runtime/include/driver
        ${TOP_DIR}/runtime/pkg_inc
        ${TOP_DIR}/runtime/pkg_inc/runtime
        ${TOP_DIR}/runtime/pkg_inc/profiling
        ${TOP_DIR}/runtime/pkg_inc/trace
        ${TOP_DIR}/runtime/pkg_inc/base
        ${TOP_DIR}/runtime/pkg_inc/aicpu
        ${TOP_DIR}/runtime/src/runtime/platform/inc
        ${TOP_DIR}/inc/external
        ${TOP_DIR}/inc/aicpu/
        ${TOP_DIR}/inc/aicpu/aicpu_schedule/aicpu_sharder
        ${TOP_DIR}/abl/atrace/inc/utrace
        ${TOP_DIR}/abl/msprof/inc
        ${TOP_DIR}/abl/adump/inc/adump
        ${TOP_DIR}/inc/aicpu/common
        ${TOP_DIR}/ace/csruntime/inc/tsch
        ${TOP_DIR}/metadef
        ${TOP_DIR}/metadef/inc
        ${TOP_DIR}/metadef/pkg_inc
        ${TOP_DIR}/metadef/inc/common
        ${TOP_DIR}/metadef/inc/external
    
        ${TOP_DIR}/open_source/json/include
        ${TOP_DIR}/hcomm/pkg_inc
        ${TOP_DIR}/hcomm/pkg_inc/hccl
        ${TOP_DIR}/hcomm/src/
        ${TOP_DIR}/hcomm/src/include/hccl/                          # ${ASCEND_CANN_PACKAGE_PATH}/include
        ${TOP_DIR}/hcomm/src/platform
        ${TOP_DIR}/hcomm/src/platform/legacy/inc/
        ${TOP_DIR}/hcomm/src/platform/hccp/inc
        ${TOP_DIR}/hcomm/src/platform/hccp/inc/network
    )

    target_include_directories(ccl_kernel_plf_a PRIVATE
        ${TOP_DIR}/inc
        ${TOP_DIR}/inc/aicpu/tsd
        ${TOP_DIR}/inc/driver
        ${TOP_DIR}/runtime/include/external
        ${TOP_DIR}/runtime/include/external/acl
        ${TOP_DIR}/runtime/include/driver
        ${TOP_DIR}/runtime/pkg_inc
        ${TOP_DIR}/runtime/pkg_inc/runtime
        ${TOP_DIR}/runtime/pkg_inc/profiling
        ${TOP_DIR}/runtime/pkg_inc/trace
        ${TOP_DIR}/runtime/pkg_inc/base
        ${TOP_DIR}/runtime/pkg_inc/aicpu
        ${TOP_DIR}/runtime/src/runtime/platform/inc
        ${TOP_DIR}/inc/external
        ${TOP_DIR}/inc/aicpu/
        ${TOP_DIR}/inc/aicpu/aicpu_schedule/aicpu_sharder
        ${TOP_DIR}/abl/qos/qosmng
        ${TOP_DIR}/abl/atrace/inc/utrace
        ${TOP_DIR}/abl/msprof/inc
        ${TOP_DIR}/inc/aicpu/common
        ${TOP_DIR}/ace/csruntime/inc/tsch
        ${TOP_DIR}/metadef
        ${TOP_DIR}/metadef/inc
        ${TOP_DIR}/metadef/pkg_inc
        ${TOP_DIR}/metadef/inc/common
        ${TOP_DIR}/metadef/inc/external

        ${TOP_DIR}/open_source/json/include
        ${TOP_DIR}/hcomm/pkg_inc
        ${TOP_DIR}/hcomm/pkg_inc/hccl
        ${TOP_DIR}/hcomm/src/
        ${TOP_DIR}/hcomm/src/include/hccl/                           # ${ASCEND_CANN_PACKAGE_PATH}/include
        ${TOP_DIR}/hcomm/src/platform
        ${TOP_DIR}/hcomm/src/platform/legacy/inc/
        ${TOP_DIR}/hcomm/src/platform/hccp/inc
        ${TOP_DIR}/hcomm/src/platform/hccp/inc/network
    )
endif()

add_dependencies(ccl_kernel_plf json)

target_compile_definitions(ccl_kernel_plf PRIVATE
    $<$<STREQUAL:${PRODUCT_SIDE},host>:_GLIBCXX_USE_CXX11_ABI=0>
)

target_compile_definitions(ccl_kernel_plf_a PRIVATE
    $<$<STREQUAL:${PRODUCT_SIDE},host>:_GLIBCXX_USE_CXX11_ABI=0>
)

# 设置ccl_kernel_plf 包含文件列表
set(ccl_kernel_plf_include_list
    ${include_list}
    ${HCCL_BASE_DIR}/hccl/hccl_comm/wrapper/notify/
    ${HCCL_BASE_DIR}/common/debug/profiling/inc/aicpu
    ${HCCL_BASE_DIR}/framework/common/src/aicpu
)

# 指定ccl_kernel_plf所需头文件搜索路径
target_include_directories(ccl_kernel_plf PRIVATE
    ${ccl_kernel_plf_include_list}
)
# 指定ccl_kernel_plf_a所需头文件搜索路径
target_include_directories(ccl_kernel_plf_a PRIVATE
    ${ccl_kernel_plf_include_list}
)

# 给ccl_kernel_plf添加编译选项
target_compile_options(ccl_kernel_plf PRIVATE
    -Werror
    -Wall
    -fno-common
    -fno-strict-aliasing
    -pipe
    -O3
    -std=c++14
    -D_FORTIFY_SOURCE=2 -O2
    -fstack-protector-all
)

# 给ccl_kernel_plf_a添加编译选项
target_compile_options(ccl_kernel_plf_a PRIVATE
    -Werror
    -Wall
    -fno-common
    -fno-strict-aliasing
    -pipe
    -O3
    -std=c++14
    -ftrapv
    -D_FORTIFY_SOURCE=2 -O2
    -fPIC
    -fstack-protector-all
)
# 为ccl_kernel_plf添加编译定义
target_compile_definitions(ccl_kernel_plf PRIVATE
    HCCD
    CCL_KERNEL
    CCL_KERNEL_AICPU
    USE_AICORE_REDUCESUM
    USE_AICORE_GATHERV2
    USE_AICORE_GATHERV2_INFER
)
# 为ccl_kernel_plf_a添加编译定义
target_compile_definitions(ccl_kernel_plf_a PRIVATE
    HCCD
    CCL_KERNEL
    CCL_KERNEL_AICPU
    USE_AICORE_REDUCESUM
    USE_AICORE_GATHERV2
    USE_AICORE_GATHERV2_INFER
)
# 向ccl_kernel_plf添加链接器选项
target_link_options(ccl_kernel_plf PRIVATE
    -Wl,-z,relro,-z,now,-z,noexecstack
    -Wl,-Bsymbolic
    -Wl,--exclude-libs,ALL
    $<$<CONFIG:Release>:-s>
)
# 向ccl_kernel_plf_a添加链接器选项
target_link_options(ccl_kernel_plf_a PRIVATE
    -Wl,-z,relro,-z,now,-z,noexecstack
    -Wl,-Bsymbolic
    -Wl,--exclude-libs,ALL
)

# 将库文件链接到目标ccl_kernel_plf  ccl_kernel_plf_a
if(BUILD_OPEN_PROJECT)
    target_link_libraries(ccl_kernel_plf
        -Wl,--no-as-needed
        c_sec
        aicpu_sharder
        mmpa
        -Wl,--as-needed
        -lrt
        -ldl
        -lpthread
    )

    target_link_libraries(ccl_kernel_plf_a
        -Wl,--no-as-needed
        c_sec
        aicpu_sharder
        mmpa
        -Wl,--as-needed
        -lrt
        -ldl
        -lpthread
    )
else()
    target_link_libraries(ccl_kernel_plf
        $<BUILD_INTERFACE:intf_pub_cxx14>
        $<BUILD_INTERFACE:mmpa_headers>
        $<BUILD_INTERFACE:msprof_headers>
        $<BUILD_INTERFACE:slog_headers>
        $<BUILD_INTERFACE:hccl_headers>
        $<BUILD_INTERFACE:runtime_headers>
        $<BUILD_INTERFACE:atrace_headers>
        $<BUILD_INTERFACE:kernel_tiling_headers>
        -Wl,--no-as-needed
        c_sec
        aicpu_sharder
        mmpa
        -Wl,--as-needed
        -lrt
        -ldl
        -lpthread
        ofed_headers
    )

    target_link_libraries(ccl_kernel_plf_a PRIVATE
        $<BUILD_INTERFACE:intf_pub_cxx14>
        $<BUILD_INTERFACE:mmpa_headers>
        $<BUILD_INTERFACE:msprof_headers>
        $<BUILD_INTERFACE:slog_headers>
        $<BUILD_INTERFACE:hccl_headers>
        $<BUILD_INTERFACE:runtime_headers>
        $<BUILD_INTERFACE:atrace_headers>
        $<BUILD_INTERFACE:kernel_tiling_headers>
        -Wl,--no-as-needed
        c_sec
        aicpu_sharder
        mmpa
        -Wl,--as-needed
        -lrt
        -ldl
        -lpthread
        ofed_headers
    )
endif()

# 将子目录添加到构建过程
add_subdirectory(framework)
add_subdirectory(hccd)
add_subdirectory(algorithm)
add_subdirectory(platform)
add_subdirectory(common)
# 自动找到项目内所有头文件
FILE(GLOB_RECURSE sources_list LIST_DIRECTORIES TRUE ${TOP_DIR}/hccl/*)
foreach (dir ${sources_list})
    IF ((IS_DIRECTORY ${dir} ) AND (${dir} MATCHES "hccl/orion"))
        target_include_directories(hccd PRIVATE ${dir})
    endif ()
endforeach ()

set(FRAMEWORK_SRC PRIVATE
    ${HCCL_BASE_DIR}/framework/common/src/config.cc
    ${HCCL_BASE_DIR}/framework/common/src/json_utils.cc
    ${HCCL_BASE_DIR}/framework/common/src/param_check.cc
    ${HCCL_BASE_DIR}/framework/common/src/topo/topoinfo_ranktableParser.cc
    ${HCCL_BASE_DIR}/framework/common/src/topo/topoinfo_ranktableConcise.cc
    ${HCCL_BASE_DIR}/framework/common/src/topo/topoinfo_ranktableHeterog.cc
    ${HCCL_BASE_DIR}/framework/common/src/topo/topoinfo_ranktableStandard.cc
    ${HCCL_BASE_DIR}/framework/common/src/topo/topoinfo_roletableParser.cc
)

set(algorithm_open_cc PRIVATE
    ${HCCL_BASE_DIR}/algorithm/impl/resource_manager/workspace_resource.cc
    ${HCCL_BASE_DIR}/algorithm/impl/resource_manager/workspace_resource_impl.cc
    ${HCCL_BASE_DIR}/algorithm/impl/resource_manager/workspace_mem.cc
    ${HCCL_BASE_DIR}/algorithm/impl/resource_manager/offload_stream_manager.cc
    ${HCCL_BASE_DIR}/algorithm/impl/resource_manager/ccl_buffer_manager.cc
    ${HCCL_BASE_DIR}/algorithm/impl/resource_manager/share_ccl_buffer_manager.cc
    ${HCCL_BASE_DIR}/algorithm/impl/resource_manager/workspace_mem.cc
)

set(common_cc PRIVATE
    ${HCCL_BASE_DIR}/common/health/rank_consistentcy_checker.cc
    ${HCCL_BASE_DIR}/common/health/calc_crc.cc
    ${HCCL_BASE_DIR}/common/debug/config/config_log.cc
)

# 动态地向已经定义的hccd添加源文件
target_sources(hccd PRIVATE
    ${algorithm_open_cc}
    ${FRAMEWORK_SRC}
    ${common_cc}
)
# 指定hccd构建完成后安装到指定的目标位置
install(TARGETS  hccd
    LIBRARY DESTINATION ${INSTALL_LIBRARY_DIR}  OPTIONAL
)

# 指定ccl_kernel_plf构建完成后安装到指定的目标位置
install(TARGETS  ccl_kernel_plf
    LIBRARY DESTINATION ${INSTALL_LIBRARY_DIR}  OPTIONAL
)
# 设置ccl_kernel_plf_a输出文件的名字
set_target_properties(ccl_kernel_plf_a
    PROPERTIES
    OUTPUT_NAME ccl_kernel_plf
)
# 指定ccl_kernel_plf_a构建完成后安装到指定的目标位置
install(TARGETS  ccl_kernel_plf_a
    ARCHIVE DESTINATION ${INSTALL_LIBRARY_DIR}  OPTIONAL
)

if(DEVICE_MODE)
    set(HCCD_TAR_DIR ${HCCL_BASE_DIR}/../build_hccd/hccd_tar_pkg/lib64)
    add_custom_command(
        TARGET hccd
        POST_BUILD
        COMMAND ${CMAKE_COMMAND} -E make_directory ${HCCD_TAR_DIR}
        COMMAND ${CMAKE_COMMAND} -E copy $<TARGET_FILE:rs> ${HCCD_TAR_DIR}
        COMMAND ${CMAKE_COMMAND} -E copy $<TARGET_FILE:ra_peer> ${HCCD_TAR_DIR}
        COMMAND ${CMAKE_COMMAND} -E copy $<TARGET_FILE:ra_hdc> ${HCCD_TAR_DIR}
        COMMAND ${CMAKE_COMMAND} -E copy $<TARGET_FILE:ra> ${HCCD_TAR_DIR}
        COMMAND ${CMAKE_COMMAND} -E copy $<TARGET_FILE:hccd> ${HCCD_TAR_DIR}
        COMMAND ${CMAKE_COMMAND} -E copy ${CMAKE_BINARY_DIR}/hcomm_utils/${PRODUCT_SIDE}/lib/lib* ${HCCD_TAR_DIR}
        COMMAND chmod 750 ${HCCD_TAR_DIR}/lib*
        COMMENT "Copying libhccd.so to ${HCCD_TAR_DIR}"
    )
endif()