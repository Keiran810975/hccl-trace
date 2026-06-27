# -----------------------------------------------------------------------------------------------------------
# Copyright (c) 2025 Huawei Technologies Co., Ltd.
# This program is free software, you can redistribute it and/or modify it under the terms and conditions of
# CANN Open Software License Agreement Version 2.0 (the "License").
# Please refer to the License for details. You may not use this file except in compliance with the License.
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
# See LICENSE in the root of the software repository for the full text of the License.
# -----------------------------------------------------------------------------------------------------------
set(HCCL_CODE_ROOT ${CMAKE_CURRENT_SOURCE_DIR}/../../..)
set(HCCL_LLT_ROOT ${CMAKE_CURRENT_SOURCE_DIR}/..)

set(hccl_llt_stub
    ${HCCL_LLT_ROOT}/stub/llt_hccl_stub.cc
    ${HCCL_LLT_ROOT}/stub/llt_hccl_stub_profiling_plugin.cc
    ${HCCL_LLT_ROOT}/stub/llt_hccl_stub_gdr.cc
    ${HCCL_LLT_ROOT}/stub/llt_hccl_stub_sal.cc
    ${HCCL_LLT_ROOT}/stub/llt_hccl_stub_fe.cc
    # ${HCCL_LLT_ROOT}/stub/llt_hccl_stub_error_manager.cc
    ${HCCL_LLT_ROOT}/stub/llt_hccl_stub_mc2.cc
    # ${HCCL_LLT_ROOT}/stub/llt_hccl_stub_GenRankTable.cc
    ${HCCL_LLT_ROOT}/stub/llt_hccl_stub_gert.cc
    ${HCCL_LLT_ROOT}/stub/llt_hccl_stub_platform.cc
    ${HCCL_LLT_ROOT}/stub/llt_stub_sec.c
    ${HCCL_LLT_ROOT}/stub/llt_mmpa_stub.c
    ${HCCL_LLT_ROOT}/stub/llt_stub_mm.c
    ${HCCL_LLT_ROOT}/stub/llt_hccl_stub_error_msg.cc
)

file(GLOB_RECURSE ALGORITHM_SOURCES "${HCCL_CODE_ROOT}/src/algorithm/*.cc")
file(GLOB_RECURSE COMMON_SOURCES "${HCCL_CODE_ROOT}/src/common/*.cc")
file(GLOB_RECURSE FRAMEWORK_HOST_SOURCES "${HCCL_CODE_ROOT}/src/framework/*.cc")
file(GLOB_RECURSE FRAMEWORK_DEVICE_SOURCES "${HCCL_CODE_ROOT}/src/framework/*.cc")
file(GLOB_RECURSE HCCD_SOURCES "${HCCL_CODE_ROOT}/src/hccd/*.cc")
file(GLOB_RECURSE PLATFORM_SOURCES "${HCCL_CODE_ROOT}/src/platform/*.cc")

set(EXCLUDE_FREAMEWORK_DEVICE_REGEX
    "${HCCL_CODE_ROOT}/src/framework/communicator/impl/hccl_communicator_attrs_device.cc"
    "${HCCL_CODE_ROOT}/src/framework/communicator/impl/hccl_communicator_device.cc"
    "${HCCL_CODE_ROOT}/src/framework/common/src/config/env_config_aicpu.cc"
    "${HCCL_CODE_ROOT}/src/framework/communicator/hccl_comm_device.cc"
    "${HCCL_CODE_ROOT}/src/framework/device/framework/zero_copy_address_mgr.cc"
    "${HCCL_CODE_ROOT}/src/framework/common/src/launch_aicpu.cc"
    "${HCCL_CODE_ROOT}/src/framework/op_base/src/op_base_device.cc"
    "${HCCL_CODE_ROOT}/src/framework/communicator/impl/independent_op/diag/aicpu/hcomm_diag_adapt_aicpu.cc"
    )
list(REMOVE_ITEM FRAMEWORK_HOST_SOURCES ${EXCLUDE_FREAMEWORK_DEVICE_REGEX})

set(EXCLUDE_ALGORITHM_DEVICE_REGEX 
    "${HCCL_CODE_ROOT}/src/algorithm/impl/hccl_alg_device.cc"
    "${HCCL_CODE_ROOT}/src/algorithm/impl/hccl_aiv_device.cc"
    "${HCCL_CODE_ROOT}/src/algorithm/impl/coll_executor/coll_all_to_all/coll_all_to_all_executor_aicpu.cc"
    )
list(REMOVE_ITEM ALGORITHM_SOURCES ${EXCLUDE_ALGORITHM_DEVICE_REGEX})

set(EXCLUDE_COMMON_DEVICE_REGEX 
    "${HCCL_CODE_ROOT}/src/common/debug/profiling/plugin_runner_device.cc"
    "${HCCL_CODE_ROOT}/src/common/stream/stream_utils_aicpu.cc"
    "${HCCL_CODE_ROOT}/src/common/debug/profiling/task_exception_handler_device.cc"
    )
list(REMOVE_ITEM COMMON_SOURCES ${EXCLUDE_COMMON_DEVICE_REGEX})

set(EXCLUDE_PLATFORM_DEVICE_REGEX
    "${HCCL_CODE_ROOT}/src/platform/resource/mem/mem_mapping_manager_device.cc"
    )
list(REMOVE_ITEM PLATFORM_SOURCES ${EXCLUDE_PLATFORM_DEVICE_REGEX})

list(FILTER PLATFORM_SOURCES EXCLUDE REGEX ".*src/platform/legacy/.*")
list(FILTER PLATFORM_SOURCES EXCLUDE REGEX ".*src/platform/typical/.*")
list(FILTER FRAMEWORK_HOST_SOURCES EXCLUDE REGEX ".*src/framework/next/.*")

set(hccl_list
    ${hccl_llt_stub}
    ${HCCD_SOURCES}
    ${COMMON_SOURCES}
    ${FRAMEWORK_HOST_SOURCES}
    ${ALGORITHM_SOURCES}
    ${PLATFORM_SOURCES}
)

add_library(hccl_llt SHARED  ${hccl_list})

target_compile_definitions(hccl_llt PRIVATE
    OPEN_BUILD_PROJECT
)

#头文件搜索路径
target_include_directories(hccl_llt  PRIVATE
    ${HCCL_LLT_ROOT}/stub

    ${HCCL_CODE_ROOT}/src/framework/common/src
    ${HCCL_CODE_ROOT}/include/
    ${HCCL_CODE_ROOT}/include/hccl/
    ${HCCL_CODE_ROOT}/pkg_inc
    ${HCCL_CODE_ROOT}/pkg_inc/hccl
    ${HCCL_CODE_ROOT}/externel_depends/tsch
    ${HCCL_CODE_ROOT}/src/pub_inc/
    ${HCCL_CODE_ROOT}/src/pub_inc/inner
    ${HCCL_CODE_ROOT}/src/pub_inc/aicpu
    ${HCCL_CODE_ROOT}/src/pub_inc/new
    ${HCCL_CODE_ROOT}/src/platform/hccp/inc
    ${HCCL_CODE_ROOT}/src/platform/hccp/inc/network
    ${HCCL_CODE_ROOT}/src/platform/hccp/external_depends/rdma-core/include
    ${HCCL_CODE_ROOT}/src/pkg_inc
    ${HCCL_CODE_ROOT}/external_depends

    # hccl/hccl目录下头文件
    ${HCCL_CODE_ROOT}/src/inc
    ${HCCL_CODE_ROOT}/src/algorithm/pub_inc
    ${HCCL_CODE_ROOT}/src/algorithm/impl
    ${HCCL_CODE_ROOT}/src/framework/
    ${HCCL_CODE_ROOT}/src/framework/inc/
    ${HCCL_CODE_ROOT}/src/framework/inc/host/
    ${HCCL_CODE_ROOT}/src/framework/cluster_maintenance/health/heartbeat/
    ${HCCL_CODE_ROOT}/src/framework/cluster_maintenance/detect/detect_connect_anomalies/
    ${HCCL_CODE_ROOT}/src/framework/cluster_maintenance/recovery/operator_retry
    ${HCCL_CODE_ROOT}/src/framework/common/src/host
    ${HCCL_CODE_ROOT}/src/framework/common/src/config
    ${HCCL_CODE_ROOT}/src/framework/common/src/task
    ${HCCL_CODE_ROOT}/src/framework/common/src/topo
    ${HCCL_CODE_ROOT}/src/framework/common/src/exception
    ${HCCL_CODE_ROOT}/src/framework/common/src/thread
    ${HCCL_CODE_ROOT}/src/framework/common/src/onesided_memory_management
    ${HCCL_CODE_ROOT}/src/framework/communicator/impl
    ${HCCL_CODE_ROOT}/src/framework/communicator/impl/one_sided_service
    ${HCCL_CODE_ROOT}/src/framework/communicator/impl/resource_manager
    ${HCCL_CODE_ROOT}/src/framework/communicator/impl/independent_op
    ${HCCL_CODE_ROOT}/src/framework/communicator/impl/independent_op/channel/
    ${HCCL_CODE_ROOT}/src/framework/communicator/impl/independent_op/channel/device
    ${HCCL_CODE_ROOT}/src/framework/communicator/impl/independent_op/rank_graph
    ${HCCL_CODE_ROOT}/src/framework/communicator/impl/independent_op/resource/engine
    ${HCCL_CODE_ROOT}/src/framework/hcom/
    ${HCCL_CODE_ROOT}/src/framework/hcom/gradient_segment
    ${HCCL_CODE_ROOT}/src/framework/op_base/src/
    ${HCCL_CODE_ROOT}/src/framework/nslbdp/

    ${HCCL_CODE_ROOT}/src/platform/
    ${HCCL_CODE_ROOT}/src/platform/common/
    ${HCCL_CODE_ROOT}/src/platform/common/unique
    ${HCCL_CODE_ROOT}/src/platform/common/unfold_cache
    ${HCCL_CODE_ROOT}/src/platform/common/buffer_manager
    ${HCCL_CODE_ROOT}/src/platform/inc
    ${HCCL_CODE_ROOT}/src/platform/inc/adapter
    ${HCCL_CODE_ROOT}/src/platform/inc/adapter/host
    ${HCCL_CODE_ROOT}/src/platform/inc/common/
    ${HCCL_CODE_ROOT}/src/platform/resource/transport/
    ${HCCL_CODE_ROOT}/src/platform/resource/transport/host/
    ${HCCL_CODE_ROOT}/src/platform/resource/transport/device/
    ${HCCL_CODE_ROOT}/src/platform/resource/transport/heterog/
    ${HCCL_CODE_ROOT}/src/platform/resource/transport/onesided/
    ${HCCL_CODE_ROOT}/src/platform/resource/transport/onesided/device
    ${HCCL_CODE_ROOT}/src/platform/resource/notify/
    ${HCCL_CODE_ROOT}/src/platform/resource/rma_buffer
    ${HCCL_CODE_ROOT}/src/platform/resource/socket
    ${HCCL_CODE_ROOT}/src/platform/resource/mem
    ${HCCL_CODE_ROOT}/src/platform/task/
    ${HCCL_CODE_ROOT}/src/platform/aiv_communication/
    ${HCCL_CODE_ROOT}/src/hccd

    ${HCCL_CODE_ROOT}/src/platform/resource/dispatcher_ctx

    # hccl/common 目录下头文件
    ${HCCL_CODE_ROOT}/src/common/health/
    ${HCCL_CODE_ROOT}/src/common/debug/profiling
    ${HCCL_CODE_ROOT}/src/common/debug/profiling/inc
    ${HCCL_CODE_ROOT}/src/common/debug/config
    ${HCCL_CODE_ROOT}/src/common/debug/profiling/inc/host
    ${HCCL_CODE_ROOT}/src/common/stream/
    ${HCCL_CODE_ROOT}/src/common/launch_device/

    # hccl/algorithm 目录下头文件
    ${HCCL_CODE_ROOT}/src/algorithm/base
    ${HCCL_CODE_ROOT}/src/algorithm/base/inc
    ${HCCL_CODE_ROOT}/src/algorithm/base/alg_aiv_template
    ${HCCL_CODE_ROOT}/src/algorithm/base/alg_template
    ${HCCL_CODE_ROOT}/src/algorithm/base/alg_template/inc_all_reduce_deter
    ${HCCL_CODE_ROOT}/src/algorithm/base/communicator
    ${HCCL_CODE_ROOT}/src/algorithm/base/communicator/legacy
    ${HCCL_CODE_ROOT}/src/algorithm/base/mc2_handler
    ${HCCL_CODE_ROOT}/src/algorithm/impl
    ${HCCL_CODE_ROOT}/src/algorithm/impl/inc
    ${HCCL_CODE_ROOT}/src/algorithm/impl/legacy
    ${HCCL_CODE_ROOT}/src/algorithm/impl/legacy/operator
    ${HCCL_CODE_ROOT}/src/algorithm/impl/resource_manager
    ${HCCL_CODE_ROOT}/src/algorithm/impl/task
    ${HCCL_CODE_ROOT}/src/algorithm/impl/operator
    ${HCCL_CODE_ROOT}/src/algorithm/impl/operator/registry
    ${HCCL_CODE_ROOT}/src/algorithm/impl/coll_executor
    ${HCCL_CODE_ROOT}/src/algorithm/impl/coll_executor/registry
    ${HCCL_CODE_ROOT}/src/algorithm/impl/coll_executor/coll_all_gather
    ${HCCL_CODE_ROOT}/src/algorithm/impl/coll_executor/coll_all_gather/310P
    ${HCCL_CODE_ROOT}/src/algorithm/impl/coll_executor/coll_all_gather_v
    ${HCCL_CODE_ROOT}/src/algorithm/impl/coll_executor/coll_all_gather_v/310P
    ${HCCL_CODE_ROOT}/src/algorithm/impl/coll_executor/coll_all_reduce
    ${HCCL_CODE_ROOT}/src/algorithm/impl/coll_executor/coll_all_reduce/310P
    ${HCCL_CODE_ROOT}/src/algorithm/impl/coll_executor/coll_send_receive
    ${HCCL_CODE_ROOT}/src/algorithm/impl/coll_executor/coll_reduce_scatter
    ${HCCL_CODE_ROOT}/src/algorithm/impl/coll_executor/coll_reduce_scatter/310P
    ${HCCL_CODE_ROOT}/src/algorithm/impl/coll_executor/coll_reduce_scatter_v
    ${HCCL_CODE_ROOT}/src/algorithm/impl/coll_executor/coll_reduce_scatter_v/310P
    ${HCCL_CODE_ROOT}/src/algorithm/impl/coll_executor/coll_all_to_all
    ${HCCL_CODE_ROOT}/src/algorithm/impl/coll_executor/coll_scatter

    ${HCCL_CODE_ROOT}/src/algorithm/base/alg_template/temp_all_gather
    ${HCCL_CODE_ROOT}/src/algorithm/base/alg_template/temp_all_reduce
    ${HCCL_CODE_ROOT}/src/algorithm/base/alg_template/temp_alltoall
    ${HCCL_CODE_ROOT}/src/algorithm/base/alg_template/temp_alltoallv
    ${HCCL_CODE_ROOT}/src/algorithm/base/alg_template/temp_broadcast
    ${HCCL_CODE_ROOT}/src/algorithm/base/alg_template/temp_reduce
    ${HCCL_CODE_ROOT}/src/algorithm/base/alg_template/temp_reduce_scatter
    ${HCCL_CODE_ROOT}/src/algorithm/base/alg_template/temp_scatter
    ${HCCL_CODE_ROOT}/src/algorithm/base/alg_template/component
    ${HCCL_CODE_ROOT}/src/algorithm/base/alg_template
    ${HCCL_CODE_ROOT}/src/algorithm/base/pub_inc

    # hccl/operator目录下头文件
    ${HCCL_CODE_ROOT}/operator

    # /hccl/framework/device/目录下头文件
    ${HCCL_CODE_ROOT}/src/framework/device/
    ${HCCL_CODE_ROOT}/src/framework/device/common
    ${HCCL_CODE_ROOT}/src/framework/device/inc
    ${HCCL_CODE_ROOT}/src/framework/device/aicpu_kfc
    ${HCCL_CODE_ROOT}/src/framework/device/aicpu_kfc/inc
    ${HCCL_CODE_ROOT}/src/framework/device/aicpu_kfc/common

    # proto.h头文件
    ${CMAKE_BINARY_DIR}/proto/hccl_llt

    ${CMAKE_BINARY_DIR}/hcomm_utils/${PRODUCT_SIDE}/include/legacy

    ${HCCL_CODE_ROOT}/test/ut/depends/pkg_inc/
    ${HCCL_CODE_ROOT}/test/ut/depends/pkg_inc/aicpu/
    ${HCCL_CODE_ROOT}/test/ut/depends/pkg_inc/aicpu/common/
    ${HCCL_CODE_ROOT}/test/ut/depends/pkg_inc/runtime/
    ${HCCL_CODE_ROOT}/test/ut/depends/pkg_inc/profiling/
    ${HCCL_CODE_ROOT}/test/ut/depends/pkg_inc/base/
    ${HCCL_CODE_ROOT}/test/ut/depends/include/base/context_builder
    ${HCCL_CODE_ROOT}/test/ut/depends/pkg_inc/dump/
    ${HCCL_CODE_ROOT}/test/ut/depends/pkg_inc/trace/
    ${HCCL_CODE_ROOT}/test/ut/depends/pkg_inc/asc/include/adv_api/hccl/internal

    ${HCCL_CODE_ROOT}/test/ut/depends/include/
    ${HCCL_CODE_ROOT}/test/ut/depends/runtime/include/
    ${HCCL_CODE_ROOT}/test/ut/depends/include/mmpa/
    ${HCCL_CODE_ROOT}/test/ut/depends/include/driver/
    ${HCCL_CODE_ROOT}/test/ut/depends/include/acl/
    ${HCCL_CODE_ROOT}/test/ut/depends/include/ascendc/highlevel_api/

    ${THIRD_PARTY_NLOHMANN_PATH}
    ${ASCEND_3RD_LIB_PATH}/json/include/
    ${ASCEND_3RD_LIB_PATH}/gtest_shared/include/
)

target_compile_definitions(hccl_llt    PRIVATE
    HALF_T=float
    google=ascend_private
    CCL_KERNEL
    -DCCL_LLT
)

target_compile_options(hccl_llt   PRIVATE
    -O0 -U_FORTIFY_SOURCE -g
)

target_link_libraries(hccl_llt  PRIVATE
    $<BUILD_INTERFACE:intf_pub>
    -lrt
    -ldl
)
