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

if(BUILD_OPEN_PROJECT)
    message(STATUS "open TOP_DIR = ${TOP_DIR}")
    set(HCCL_BASE_DIR ${CMAKE_CURRENT_SOURCE_DIR}/../)
    set(HCCL_OPEN_CODE_BASE_DIR ${CMAKE_CURRENT_SOURCE_DIR}/../)
    set(HCCL_THIRD_PARTY_DIR ${CMAKE_CURRENT_SOURCE_DIR}/../../../../../../../../)
else()
    message(STATUS "close TOP_DIR = ${TOP_DIR}")
    set(HCCL_BASE_DIR ${TOP_DIR}/hcomm/src/)
    set(HCCL_OPEN_CODE_BASE_DIR ${TOP_DIR}/hcomm/src/)
    set(HCCL_THIRD_PARTY_DIR ${TOP_DIR})
    set(INSTALL_CCL_KERNEL_JSON_DIR ${INSTALL_LIBRARY_DIR})
endif()

message(STATUS "HCCL_OPEN_CODE_BASE_DIR = ${HCCL_OPEN_CODE_BASE_DIR}")
message(STATUS "HCCL_BASE_DIR = ${HCCL_BASE_DIR}")
add_library(hcomm  SHARED)

set(hccl_include_list
    ${HCCL_BASE_DIR}/../include/hccl
    ${HCCL_BASE_DIR}/algorithm/base/inc
    ${HCCL_BASE_DIR}/algorithm/pub_inc
    ${HCCL_BASE_DIR}/pub_inc
    ${HCCL_BASE_DIR}/pub_inc/hccl
    ${HCCL_BASE_DIR}/pub_inc/new
    ${HCCL_BASE_DIR}/algorithm/base/alg_aiv_template
    ${HCCL_BASE_DIR}/algorithm/base/alg_template
    ${HCCL_BASE_DIR}/algorithm/base/mc2_handler
    ${HCCL_BASE_DIR}/algorithm/base/alg_template/component
    ${HCCL_BASE_DIR}/algorithm/base/communicator
    ${HCCL_BASE_DIR}/algorithm/base/communicator/legacy
    ${HCCL_BASE_DIR}/algorithm/impl
    ${HCCL_BASE_DIR}/algorithm/impl/legacy
    ${HCCL_BASE_DIR}/algorithm/impl/inc
    ${HCCL_BASE_DIR}/algorithm/impl/task
    ${HCCL_BASE_DIR}/algorithm/impl/resource_manager
    ${HCCL_BASE_DIR}/algorithm/impl/coll_executor

    ${HCCL_BASE_DIR}/framework/cluster_maintenance/health/heartbeat/
    ${HCCL_BASE_DIR}/framework/cluster_maintenance/recovery/operator_retry/
    ${HCCL_BASE_DIR}/framework/cluster_maintenance/detect/detect_connect_anomalies/
    ${HCCL_BASE_DIR}/framework/common/src/
    ${HCCL_BASE_DIR}/framework/common/src/host
    ${HCCL_BASE_DIR}/framework/common/src/config
    ${HCCL_BASE_DIR}/framework/common/src/topo
    ${HCCL_BASE_DIR}/framework/common/src/task
    ${HCCL_BASE_DIR}/framework/common/src/exception
    ${HCCL_BASE_DIR}/framework/common/src/h2d_tlv
    ${HCCL_BASE_DIR}/framework/common/src/thread
    ${HCCL_BASE_DIR}/framework/common/src/h2d_dto
    ${HCCL_BASE_DIR}/framework/common/src/onesided_memory_management
    ${HCCL_BASE_DIR}/framework/common/src/mgr
    ${HCCL_BASE_DIR}/framework/communicator/impl/
    ${HCCL_BASE_DIR}/framework/communicator/impl/resource_manager
    ${HCCL_BASE_DIR}/framework/communicator/impl/one_sided_service
    ${HCCL_BASE_DIR}/framework/communicator/impl/zero_copy_memory_agent
    ${HCCL_BASE_DIR}/framework/communicator/impl/independent_op
    ${HCCL_BASE_DIR}/framework/communicator/impl/independent_op/rank_graph
    ${HCCL_BASE_DIR}/framework/communicator/impl/independent_op/resource/engine
    ${HCCL_BASE_DIR}/framework/communicator/impl/independent_op/channel
    ${HCCL_BASE_DIR}/framework/communicator/impl/independent_op/channel/device
    ${HCCL_BASE_DIR}/framework/hcom/
    ${HCCL_BASE_DIR}/framework/hcom/gradient_segment
    ${HCCL_BASE_DIR}/framework/inc/
    ${HCCL_BASE_DIR}/framework/
    ${HCCL_BASE_DIR}/framework/nslbdp/
    ${HCCL_BASE_DIR}/framework/op_base/src
    ${HCCL_BASE_DIR}/common/health/
    ${HCCL_BASE_DIR}/common/stream/
    ${HCCL_BASE_DIR}/common/launch_device/
)

target_include_directories(hcomm PRIVATE
    ${hccl_include_list}
)

if(BUILD_OPEN_PROJECT)
    target_compile_definitions(hcomm PRIVATE
        OPEN_BUILD_PROJECT
        LOG_CPP)

    target_include_directories(hcomm PRIVATE
        ${HCCL_BASE_DIR}/pub_inc
        ${HCCL_BASE_DIR}/pub_inc/new/
        ${HCCL_BASE_DIR}/inc
        ${HCCL_BASE_DIR}/../include
        ${HCCL_BASE_DIR}/../include/hccl
        ${HCCL_BASE_DIR}/../pkg_inc/
        ${HCCL_BASE_DIR}/../pkg_inc/hccl/
        ${HCCL_BASE_DIR}/platform/common
        ${CMAKE_BINARY_DIR}/hcomm_utils/${PRODUCT_SIDE}/include/legacy
        ${HCCL_BASE_DIR}/platform/legacy/inc
        ${HCCL_BASE_DIR}/platform/resource/dispatcher_ctx

        ${THIRD_PARTY_NLOHMANN_PATH}

        ${HCCL_BASE_DIR}/common/debug/profiling/inc
        ${HCCL_BASE_DIR}/common/debug/profiling/inc/host
        ${HCCL_BASE_DIR}/common/debug/config

        # runtime头文件
        ${ASCEND_CANN_PACKAGE_PATH}/include/

        # mmpa头文件
        ${ASCEND_CANN_PACKAGE_PATH}/include/mmpa/

        # acl头文件
        ${ASCEND_CANN_PACKAGE_PATH}/include/acl/

        # driver头文件
        ${ASCEND_CANN_PACKAGE_PATH}/include/driver/

        # highlevel_api
        ${ASCEND_CANN_PACKAGE_PATH}/include/ascendc/highlevel_api/
        ${ASCEND_CANN_PACKAGE_PATH}/include/ascendc/

        # 包间接口
        ${ASCEND_CANN_PACKAGE_PATH}/pkg_inc/
        ${ASCEND_CANN_PACKAGE_PATH}/pkg_inc/runtime/
        ${ASCEND_CANN_PACKAGE_PATH}/pkg_inc/profiling/
        ${ASCEND_CANN_PACKAGE_PATH}/pkg_inc/base/
        ${ASCEND_CANN_PACKAGE_PATH}/pkg_inc/dump/
        ${ASCEND_CANN_PACKAGE_PATH}/pkg_inc/trace/
        ${ASCEND_CANN_PACKAGE_PATH}/pkg_inc/asc/hccl/internal/

        ${THIRD_PARTY_NLOHMANN_PATH}
    )

    target_link_directories(hcomm PRIVATE
        ${ASCEND_CANN_PACKAGE_PATH}/lib64
    )
else()
    target_include_directories(hcomm PRIVATE
        ${TOP_DIR}/hcomm/include/hccl/                      # ${ASCEND_CANN_PACKAGE_PATH}/include
        ${TOP_DIR}/hcomm/src/algorithm/pub_inc
        ${TOP_DIR}/abl/msprof/inc                           # experiment/msprof/
        ${TOP_DIR}/ace/npuruntime/inc                       # experiment/runtime/
        ${TOP_DIR}/inc/driver                               # experiment/ascend_hal/driver/
        ${TOP_DIR}/inc/                                     # experiment/ascend_hal/driver/
        ${TOP_DIR}/open_source/json/include
        ${TOP_DIR}/hcomm/
        ${HCCL_BASE_DIR}/common/debug/profiling/inc
        ${HCCL_BASE_DIR}/common/debug/profiling/inc/host
        ${CMAKE_CURRENT_SOURCE_DIR}/../common/debug/config
        ${TOP_DIR}/ace/npuruntime/inc/runtime
        ${TOP_DIR}/runtime/include/external

        ${TOP_DIR}/abl/msprof/inc/toolchain
        ${HCCL_BASE_DIR}/platform/common
        ${HCCL_BASE_DIR}/inc
        ${TOP_DIR}/inc/aicpu
        ${HCCL_BASE_DIR}/pkg_inc
        ${HCCL_BASE_DIR}/platform/legacy/inc
    )
endif()

set(CMAKE_CXX_STANDARD 14)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

target_compile_options(hcomm PRIVATE
    -Werror
    -Wfloat-equal
    -Wall
    -fno-common
    -fno-strict-aliasing
    -pipe
    -O3
    -std=c++14
    -fstack-protector-all
    $<$<CONFIG:Debug>:-g>
)

target_link_options(hcomm PRIVATE
    -Wl,-z,relro
    -Wl,-z,now
    -Wl,-z,noexecstack
    -s
)

target_compile_definitions(hcomm PRIVATE
    $<$<STREQUAL:${PRODUCT_SIDE},host>:_GLIBCXX_USE_CXX11_ABI=0>
)

if(BUILD_OPEN_PROJECT)
    target_link_libraries(hcomm
            -Wl,--no-as-needed
            c_sec
            unified_dlog
            acl_rt
            hccl_alg
            hccl_plf
            -Wl,--as-needed
            -lrt
            -ldl
            -lpthread
    )
else()
    target_link_libraries(hcomm
            $<BUILD_INTERFACE:kernel_tiling_headers>
            -Wl,--no-as-needed
            c_sec
            unified_dlog
            mmpa
            hccl_alg
            hccl_plf
            -Wl,--as-needed
            -lrt
            -ldl
            -lpthread
    )
endif()

install(TARGETS hcomm
    LIBRARY DESTINATION ${INSTALL_LIBRARY_DIR} OPTIONAL
)

message(STATUS "framework KERNEL_MODE=${KERNEL_MODE}")
message(STATUS "framework BUILD_OPEN_PROJECT=${BUILD_OPEN_PROJECT}")
message(STATUS "framework ASCEND_CANN_PACKAGE_PATH=${ASCEND_CANN_PACKAGE_PATH}")

if(NOT BUILD_OPEN_PROJECT OR (BUILD_OPEN_PROJECT AND KERNEL_MODE))
    add_library(ccl_kernel  SHARED)

    set(CCL_KERNEL_SRC_LIST
        ${HCCL_BASE_DIR}/algorithm/impl/alg_env_config.cc
        ${HCCL_BASE_DIR}/algorithm/impl/coll_alg_utils.cc
        ${HCCL_BASE_DIR}/algorithm/impl/hccl_alg_device.cc
        ${HCCL_BASE_DIR}/algorithm/impl/hccl_aiv_device.cc
        ${HCCL_BASE_DIR}/algorithm/impl/topo_matcher.cc
        ${HCCL_BASE_DIR}/algorithm/impl/resource_manager/ccl_buffer_manager.cc
        ${HCCL_BASE_DIR}/algorithm/impl/resource_manager/stream_active_manager.cc
        ${HCCL_BASE_DIR}/algorithm/impl/resource_manager/workspace_mem.cc
        ${HCCL_BASE_DIR}/algorithm/impl/resource_manager/workspace_resource.cc
        ${HCCL_BASE_DIR}/algorithm/impl/resource_manager/workspace_resource_impl.cc
        ${HCCL_BASE_DIR}/algorithm/impl/resource_manager/op_base_stream_manager.cc
        ${HCCL_BASE_DIR}/algorithm/impl/resource_manager/offload_stream_manager.cc
        ${HCCL_BASE_DIR}/algorithm/impl/resource_manager/hccl_socket_manager.cc
        ${HCCL_BASE_DIR}/algorithm/impl/resource_manager/queue_notify_manager.cc
        ${HCCL_BASE_DIR}/algorithm/impl/resource_manager/share_ccl_buffer_manager.cc

        ${HCCL_BASE_DIR}/algorithm/base/communicator/legacy/comm_base.cc
        ${HCCL_BASE_DIR}/algorithm/base/communicator/legacy/comm_ring.cc
        ${HCCL_BASE_DIR}/algorithm/base/communicator/legacy/comm_p2p.cc
        ${HCCL_BASE_DIR}/algorithm/base/communicator/legacy/comm_mesh.cc
        ${HCCL_BASE_DIR}/algorithm/base/communicator/legacy/comm_halving_doubling.cc
        ${HCCL_BASE_DIR}/algorithm/base/communicator/legacy/comm_star.cc
        ${HCCL_BASE_DIR}/algorithm/base/communicator/calc_hd_transport_req.cc
        ${HCCL_BASE_DIR}/algorithm/base/communicator/calc_mesh_transport_req.cc
        ${HCCL_BASE_DIR}/algorithm/base/communicator/calc_partial_mesh_transport_req.cc
        ${HCCL_BASE_DIR}/algorithm/base/communicator/calc_ring_transport_req.cc
        ${HCCL_BASE_DIR}/algorithm/base/communicator/calc_transport_req_base.cc
        ${HCCL_BASE_DIR}/algorithm/base/communicator/calc_p2p_transport_req.cc
        ${HCCL_BASE_DIR}/algorithm/base/communicator/calc_hccs_plus_sio_transport_req.cc
        ${HCCL_BASE_DIR}/algorithm/base/communicator/calc_ahc_broke_transport_req.cc
        ${HCCL_BASE_DIR}/algorithm/base/communicator/calc_ahc_transport_req.cc
        ${HCCL_BASE_DIR}/algorithm/base/communicator/calc_ahc_transport_req_base.cc
        ${HCCL_BASE_DIR}/algorithm/base/communicator/calc_nb_transport_req.cc
        ${HCCL_BASE_DIR}/algorithm/base/communicator/calc_nhr_transport_req.cc
        ${HCCL_BASE_DIR}/algorithm/base/communicator/calc_nhr_v1_transport_req.cc

        ${HCCL_BASE_DIR}/algorithm/base/alg_template/alg_template_register.cc
        ${HCCL_BASE_DIR}/algorithm/base/alg_template/alg_template_base.cc
        ${HCCL_BASE_DIR}/algorithm/base/alg_template/nonuniform_hierarchical_ring_base.cc
        ${HCCL_BASE_DIR}/algorithm/base/alg_template/nonuniform_hierarchical_ring_v1_base.cc
        ${HCCL_BASE_DIR}/algorithm/base/alg_template/nonuniform_bruck_base.cc
        ${HCCL_BASE_DIR}/algorithm/base/alg_template/asymmetric_hierarchical_concatenate_base.cc
        ${HCCL_BASE_DIR}/algorithm/base/alg_template/asymmetric_hierarchical_concatenate_alg_template_base.cc
        ${HCCL_BASE_DIR}/algorithm/base/alg_template/asymmetric_hierarchical_concatenate_base.cc
        ${HCCL_BASE_DIR}/algorithm/base/alg_template/asymmetric_hierarchical_concatenate_nslb.cc
        ${HCCL_BASE_DIR}/algorithm/base/alg_template/recursive_halvingdoubling_base.cc

        ${HCCL_BASE_DIR}/algorithm/base/alg_template/component/reducer.cc
        ${HCCL_BASE_DIR}/algorithm/base/alg_template/component/sender.cc

        ${HCCL_BASE_DIR}/algorithm/base/alg_template/temp_all_gather/aligned_all_gather_double_ring.cc
        ${HCCL_BASE_DIR}/algorithm/base/alg_template/temp_all_gather/all_gather_ring_concurrent_direct.cc
        ${HCCL_BASE_DIR}/algorithm/base/alg_template/temp_all_gather/all_gather_halving_doubling.cc
        ${HCCL_BASE_DIR}/algorithm/base/alg_template/temp_all_gather/all_gather_mesh.cc
        ${HCCL_BASE_DIR}/algorithm/base/alg_template/temp_all_gather/all_gather_ring.cc
        ${HCCL_BASE_DIR}/algorithm/base/alg_template/temp_all_gather/all_gather_mesh_direct.cc
        ${HCCL_BASE_DIR}/algorithm/base/alg_template/temp_all_gather/all_gather_mesh_atomic.cc
        ${HCCL_BASE_DIR}/algorithm/base/alg_template/temp_all_gather/all_gather_mesh_mix.cc
        ${HCCL_BASE_DIR}/algorithm/base/alg_template/temp_all_gather/all_gather_recursive_hd.cc
        ${HCCL_BASE_DIR}/algorithm/base/alg_template/temp_all_gather/all_gather_nhr.cc
        ${HCCL_BASE_DIR}/algorithm/base/alg_template/temp_all_gather/all_gather_nhr_v1.cc
        ${HCCL_BASE_DIR}/algorithm/base/alg_template/temp_all_gather/all_gather_pipeline.cc
        ${HCCL_BASE_DIR}/algorithm/base/alg_template/temp_all_gather/all_gather_unified_march.cc
        ${HCCL_BASE_DIR}/algorithm/base/alg_template/temp_all_gather/all_gather_nb.cc
        ${HCCL_BASE_DIR}/algorithm/base/alg_template/temp_all_gather/all_gather_ahc.cc
        ${HCCL_BASE_DIR}/algorithm/base/alg_template/temp_all_gather/all_gather_ahc_broke.cc
        ${HCCL_BASE_DIR}/algorithm/base/alg_template/temp_all_gather/all_gather_hd_stage.cc
        ${HCCL_BASE_DIR}/algorithm/base/alg_template/temp_all_gather/all_gather_hccs_sio.cc

        ${HCCL_BASE_DIR}/algorithm/base/alg_template/temp_all_reduce/all_reduce_recursive_hd.cc
        ${HCCL_BASE_DIR}/algorithm/base/alg_template/temp_all_reduce/all_reduce_ring.cc
        ${HCCL_BASE_DIR}/algorithm/base/alg_template/temp_all_reduce/all_reduce_nhr_oneshot.cc
        ${HCCL_BASE_DIR}/algorithm/base/alg_template/temp_all_reduce/all_reduce_nhr.cc
        ${HCCL_BASE_DIR}/algorithm/base/alg_template/temp_all_reduce/all_reduce_nhr_v1.cc
        ${HCCL_BASE_DIR}/algorithm/base/alg_template/temp_all_reduce/all_reduce_ahc.cc
        ${HCCL_BASE_DIR}/algorithm/base/alg_template/temp_all_reduce/all_reduce_ahc_broke.cc
        ${HCCL_BASE_DIR}/algorithm/base/alg_template/temp_all_reduce/all_reduce_nb.cc
        ${HCCL_BASE_DIR}/algorithm/base/alg_template/temp_all_reduce/all_reduce_reduce_broadcast.cc
        ${HCCL_BASE_DIR}/algorithm/base/alg_template/temp_all_reduce/all_reduce_mesh_opbase.cc
        ${HCCL_BASE_DIR}/algorithm/base/alg_template/temp_all_reduce/all_reduce_mesh_oneshot.cc
        ${HCCL_BASE_DIR}/algorithm/base/alg_template/temp_all_reduce/all_reduce_doubling.cc
        ${HCCL_BASE_DIR}/algorithm/base/alg_template/temp_all_reduce/all_reduce_doubling_direct.cc
        ${HCCL_BASE_DIR}/algorithm/base/alg_template/temp_all_reduce/all_reduce_local_reduce_bcast.cc
        ${HCCL_BASE_DIR}/algorithm/base/alg_template/temp_all_reduce/all_reduce_local_reduce.cc
        ${HCCL_BASE_DIR}/algorithm/base/alg_template/temp_all_reduce/all_reduce_chunk_mesh.cc
        ${HCCL_BASE_DIR}/algorithm/base/alg_template/temp_all_reduce/all_reduce_opbase_pipeline.cc
        ${HCCL_BASE_DIR}/algorithm/base/alg_template/temp_all_reduce/all_reduce_hd_optim.cc
        ${HCCL_BASE_DIR}/algorithm/base/alg_template/temp_all_reduce/all_reduce_graph_pipeline.cc

        ${HCCL_BASE_DIR}/algorithm/base/alg_template/temp_alltoall/allltoall_pipeline_base.cc
        ${HCCL_BASE_DIR}/algorithm/base/alg_template/temp_alltoall/allltoall_pipeline_mesh_pairwise_ping_pong.cc
        ${HCCL_BASE_DIR}/algorithm/base/alg_template/temp_alltoall/allltoall_pipeline_mesh_pairwise_ccl_enough.cc

        ${HCCL_BASE_DIR}/algorithm/base/alg_template/temp_alltoallv/alltoallv_pairwise.cc
        ${HCCL_BASE_DIR}/algorithm/base/alg_template/temp_alltoallv/alltoallv_staged_base.cc
        ${HCCL_BASE_DIR}/algorithm/base/alg_template/temp_alltoallv/alltoallv_staged_pairwise.cc
        ${HCCL_BASE_DIR}/algorithm/base/alg_template/temp_alltoallv/alltoallv_staged_mesh.cc
        ${HCCL_BASE_DIR}/algorithm/base/alg_template/temp_alltoallv/alltoallv_staged_calculator.cc
        ${HCCL_BASE_DIR}/algorithm/base/alg_template/temp_alltoallv/alltoallv_for_310p.cc
        ${HCCL_BASE_DIR}/algorithm/base/alg_template/temp_alltoallv/alltoallv_direct_fullmesh.cc

        ${HCCL_BASE_DIR}/algorithm/base/alg_template/temp_broadcast/bcast_recursive_halvingdoubling.cc
        ${HCCL_BASE_DIR}/algorithm/base/alg_template/temp_broadcast/broadcast_ring.cc
        ${HCCL_BASE_DIR}/algorithm/base/alg_template/temp_broadcast/broadcast_star.cc
        ${HCCL_BASE_DIR}/algorithm/base/alg_template/temp_broadcast/broadcast_nhr_oneshot.cc
        ${HCCL_BASE_DIR}/algorithm/base/alg_template/temp_broadcast/broadcast_nhr.cc
        ${HCCL_BASE_DIR}/algorithm/base/alg_template/temp_broadcast/broadcast_nhr_v1.cc
        ${HCCL_BASE_DIR}/algorithm/base/alg_template/temp_broadcast/broadcast_nb.cc
        ${HCCL_BASE_DIR}/algorithm/base/alg_template/temp_broadcast/broadcast_nb_binary.cc
        ${HCCL_BASE_DIR}/algorithm/base/alg_template/temp_broadcast/broadcast_oneshot.cc

        ${HCCL_BASE_DIR}/algorithm/base/alg_template/temp_reduce/reduce_ring.cc
        ${HCCL_BASE_DIR}/algorithm/base/alg_template/temp_reduce/reduce_recursive_hd.cc
        ${HCCL_BASE_DIR}/algorithm/base/alg_template/temp_reduce/reduce_nhr_oneshot.cc

        ${HCCL_BASE_DIR}/algorithm/base/alg_template/temp_reduce_scatter/aligned_reduce_scatter_double_ring_with_serial_local_copy.cc
        ${HCCL_BASE_DIR}/algorithm/base/alg_template/temp_reduce_scatter/aligned_reduce_scatter_double_ring.cc
        ${HCCL_BASE_DIR}/algorithm/base/alg_template/temp_reduce_scatter/reduce_scatter_ring_concurrent_direct.cc
        ${HCCL_BASE_DIR}/algorithm/base/alg_template/temp_reduce_scatter/reduce_scatter_halving_doubling.cc
        ${HCCL_BASE_DIR}/algorithm/base/alg_template/temp_reduce_scatter/reduce_scatter_recursive_hd.cc
        ${HCCL_BASE_DIR}/algorithm/base/alg_template/temp_reduce_scatter/reduce_scatter_mesh.cc
        ${HCCL_BASE_DIR}/algorithm/base/alg_template/temp_reduce_scatter/reduce_scatter_ring.cc
        ${HCCL_BASE_DIR}/algorithm/base/alg_template/temp_reduce_scatter/reduce_scatter_mesh_atomic.cc
        ${HCCL_BASE_DIR}/algorithm/base/alg_template/temp_reduce_scatter/reduce_scatter_mesh_mix.cc
        ${HCCL_BASE_DIR}/algorithm/base/alg_template/temp_reduce_scatter/reduce_scatter_mesh_mix_single_stream.cc
        ${HCCL_BASE_DIR}/algorithm/base/alg_template/temp_reduce_scatter/reduce_scatter_mesh_atomic_opbase.cc
        ${HCCL_BASE_DIR}/algorithm/base/alg_template/temp_reduce_scatter/reduce_scatter_nhr.cc
        ${HCCL_BASE_DIR}/algorithm/base/alg_template/temp_reduce_scatter/reduce_scatter_nhr_v1.cc
        ${HCCL_BASE_DIR}/algorithm/base/alg_template/temp_reduce_scatter/reduce_scatter_nb.cc
        ${HCCL_BASE_DIR}/algorithm/base/alg_template/temp_reduce_scatter/reduce_scatter_ahc.cc
        ${HCCL_BASE_DIR}/algorithm/base/alg_template/temp_reduce_scatter/reduce_scatter_ahc_broke.cc
        ${HCCL_BASE_DIR}/algorithm/base/alg_template/temp_reduce_scatter/reduce_scatter_hd_stage.cc
        ${HCCL_BASE_DIR}/algorithm/base/alg_template/temp_reduce_scatter/reduce_scatter_local_reduce.cc
        ${HCCL_BASE_DIR}/algorithm/base/alg_template/temp_reduce_scatter/reduce_scatter_pipeline.cc
        ${HCCL_BASE_DIR}/algorithm/base/alg_template/temp_reduce_scatter/reduce_scatter_unified_march.cc
        ${HCCL_BASE_DIR}/algorithm/base/alg_template/temp_reduce_scatter/reduce_scatter_hccs_sio.cc

        ${HCCL_BASE_DIR}/algorithm/base/alg_template/temp_scatter/scatter_ring_concurrent_direct.cc
        ${HCCL_BASE_DIR}/algorithm/base/alg_template/temp_scatter/scatter_double_ring_direct.cc
        ${HCCL_BASE_DIR}/algorithm/base/alg_template/temp_scatter/scatter_mesh.cc
        ${HCCL_BASE_DIR}/algorithm/base/alg_template/temp_scatter/scatter_ring.cc
        ${HCCL_BASE_DIR}/algorithm/base/alg_template/temp_scatter/multi_root_scatter_ring.cc
        ${HCCL_BASE_DIR}/algorithm/base/alg_template/temp_scatter/scatter_nhr.cc
        ${HCCL_BASE_DIR}/algorithm/base/alg_template/temp_scatter/scatter_nb.cc
        ${HCCL_BASE_DIR}/algorithm/base/alg_template/temp_scatter/scatter_ring_direct.cc

        ${HCCL_BASE_DIR}/algorithm/base/alg_template/temp_send_recv/send_receive.cc

        ${HCCL_BASE_DIR}/algorithm/base/alg_template/temp_gather/gather_ring.cc
        ${HCCL_BASE_DIR}/algorithm/base/alg_template/temp_gather/gather_mesh.cc
        ${HCCL_BASE_DIR}/algorithm/base/alg_template/temp_gather/gather_star.cc

        ${HCCL_BASE_DIR}/algorithm/base/mc2_handler/mc2_handler.cc

        ${HCCL_BASE_DIR}/algorithm/impl/coll_executor/coll_executor_base.cc
        ${HCCL_BASE_DIR}/algorithm/impl/coll_executor/coll_native_executor_base.cc
        ${HCCL_BASE_DIR}/algorithm/impl/coll_executor/coll_comm_executor.cc

        ${HCCL_BASE_DIR}/algorithm/impl/coll_executor/coll_all_reduce/coll_all_reduce_executor.cc
        ${HCCL_BASE_DIR}/algorithm/impl/coll_executor/coll_all_reduce/coll_all_reduce_single_rank_executor.cc
        ${HCCL_BASE_DIR}/algorithm/impl/coll_executor/coll_all_reduce/coll_all_reduce_fast_double_ring_for_910_93_executor.cc
        ${HCCL_BASE_DIR}/algorithm/impl/coll_executor/coll_all_reduce/coll_aligned_all_reduce_double_ring_for_910_93_executor.cc
        ${HCCL_BASE_DIR}/algorithm/impl/coll_executor/coll_all_reduce/coll_all_reduce_ring_executor.cc
        ${HCCL_BASE_DIR}/algorithm/impl/coll_executor/coll_all_reduce/coll_all_reduce_comm_executor.cc
        ${HCCL_BASE_DIR}/algorithm/impl/coll_executor/coll_all_reduce/coll_all_reduce_ring_for_910_93_executor.cc
        ${HCCL_BASE_DIR}/algorithm/impl/coll_executor/coll_all_reduce/coll_all_reduce_mesh_executor.cc
        ${HCCL_BASE_DIR}/algorithm/impl/coll_executor/coll_all_reduce/coll_all_reduce_mesh_mid_count_executor.cc
        ${HCCL_BASE_DIR}/algorithm/impl/coll_executor/coll_all_reduce/coll_all_reduce_mesh_oneshot_executor.cc
        ${HCCL_BASE_DIR}/algorithm/impl/coll_executor/coll_all_reduce/coll_all_reduce_mesh_opbase_executor.cc
        ${HCCL_BASE_DIR}/algorithm/impl/coll_executor/coll_all_reduce/coll_all_reduce_mesh_opbase_pipeline_executor.cc
        ${HCCL_BASE_DIR}/algorithm/impl/coll_executor/coll_all_reduce/coll_all_reduce_mesh_graph_pipeline_executor.cc
        ${HCCL_BASE_DIR}/algorithm/impl/coll_executor/coll_all_reduce/coll_all_reduce_mesh_small_count_executor.cc
        ${HCCL_BASE_DIR}/algorithm/impl/coll_executor/coll_all_reduce/coll_all_reduce_reduce_plus_bcast_executor.cc
        ${HCCL_BASE_DIR}/algorithm/impl/coll_executor/coll_all_reduce/coll_all_reduce_mix_executor.cc
        ${HCCL_BASE_DIR}/algorithm/impl/coll_executor/coll_all_reduce/coll_all_reduce_ring_zerocopy_executor.cc
        ${HCCL_BASE_DIR}/algorithm/impl/coll_executor/coll_all_reduce/coll_all_reduce_order_preserved_executor.cc
        ${HCCL_BASE_DIR}/algorithm/impl/coll_executor/coll_all_reduce/310P/coll_all_reduce_for_310p_ring_executor.cc
        ${HCCL_BASE_DIR}/algorithm/impl/coll_executor/coll_all_reduce/310P/coll_all_reduce_for_310p_doubling_executor.cc
        ${HCCL_BASE_DIR}/algorithm/impl/coll_executor/coll_all_reduce/310P/coll_all_reduce_for_310p_doubling_direct_executor.cc

        ${HCCL_BASE_DIR}/algorithm/impl/coll_executor/coll_all_gather/coll_all_gather_executor.cc
        ${HCCL_BASE_DIR}/algorithm/impl/coll_executor/coll_all_gather/coll_all_gather_comm_executor.cc
        ${HCCL_BASE_DIR}/algorithm/impl/coll_executor/coll_all_gather/coll_all_gather_ring_executor.cc
        ${HCCL_BASE_DIR}/algorithm/impl/coll_executor/coll_all_gather/coll_all_gather_ring_for_910_93_executor.cc
        ${HCCL_BASE_DIR}/algorithm/impl/coll_executor/coll_all_gather/coll_aligned_all_gather_double_ring_for_910_93_executor.cc
        ${HCCL_BASE_DIR}/algorithm/impl/coll_executor/coll_all_gather/coll_all_gather_mesh_executor.cc
        ${HCCL_BASE_DIR}/algorithm/impl/coll_executor/coll_all_gather/coll_all_gather_mesh_opbase_executor.cc
        ${HCCL_BASE_DIR}/algorithm/impl/coll_executor/coll_all_gather/coll_all_gather_mesh_opbase_pipeline_executor.cc
        ${HCCL_BASE_DIR}/algorithm/impl/coll_executor/coll_all_gather/coll_all_gather_single_rank_executor.cc
        ${HCCL_BASE_DIR}/algorithm/impl/coll_executor/coll_all_gather/coll_all_gather_small_count_executor.cc
        ${HCCL_BASE_DIR}/algorithm/impl/coll_executor/coll_all_gather/coll_all_gather_semi_ring_executor.cc
        ${HCCL_BASE_DIR}/algorithm/impl/coll_executor/coll_all_gather/coll_all_gather_mix_executor.cc
        ${HCCL_BASE_DIR}/algorithm/impl/coll_executor/coll_all_gather/coll_all_gather_hccs_sio_executor.cc
        ${HCCL_BASE_DIR}/algorithm/impl/coll_executor/coll_all_gather/coll_all_gather_ring_zerocopy_executor.cc
        ${HCCL_BASE_DIR}/algorithm/impl/coll_executor/coll_all_gather/coll_all_gather_ring_zerocopy_exchange_executor.cc
        ${HCCL_BASE_DIR}/algorithm/impl/coll_executor/coll_all_gather/coll_all_gather_ring_zerocopy_pipeline_executor.cc

        ${HCCL_BASE_DIR}/algorithm/impl/coll_executor/coll_all_gather_v/coll_all_gather_v_executor.cc
        ${HCCL_BASE_DIR}/algorithm/impl/coll_executor/coll_all_gather_v/coll_all_gather_v_ring_for_910_93_executor.cc
        ${HCCL_BASE_DIR}/algorithm/impl/coll_executor/coll_all_gather_v/coll_aligned_all_gather_v_double_ring_for_910_93_executor.cc
        ${HCCL_BASE_DIR}/algorithm/impl/coll_executor/coll_all_gather_v/coll_all_gather_v_semi_ring_executor.cc

        ${HCCL_BASE_DIR}/algorithm/impl/coll_executor/coll_broadcast/coll_broadcast_executor.cc
        ${HCCL_BASE_DIR}/algorithm/impl/coll_executor/coll_broadcast/coll_broadcast_ring_for_910_93_executor.cc
        ${HCCL_BASE_DIR}/algorithm/impl/coll_executor/coll_broadcast/coll_broadcast_mesh_executor.cc
        ${HCCL_BASE_DIR}/algorithm/impl/coll_executor/coll_broadcast/coll_broadcast_ring_executor.cc
        ${HCCL_BASE_DIR}/algorithm/impl/coll_executor/coll_broadcast/coll_broadcast_comm_executor.cc
        ${HCCL_BASE_DIR}/algorithm/impl/coll_executor/coll_broadcast/coll_broadcast_smallcount_executor.cc
        ${HCCL_BASE_DIR}/algorithm/impl/coll_executor/coll_broadcast/coll_broadcast_mix_executor.cc
        ${HCCL_BASE_DIR}/algorithm/impl/coll_executor/coll_broadcast/coll_broadcast_ring_zerocopy_executor.cc

        ${HCCL_BASE_DIR}/algorithm/impl/coll_executor/coll_reduce/coll_reduce_executor.cc
        ${HCCL_BASE_DIR}/algorithm/impl/coll_executor/coll_reduce/coll_reduce_mesh_executor.cc
        ${HCCL_BASE_DIR}/algorithm/impl/coll_executor/coll_reduce/coll_reduce_ring_plus_hd_executor.cc
        ${HCCL_BASE_DIR}/algorithm/impl/coll_executor/coll_reduce/coll_reduce_ring_for_910_93_executor.cc
        ${HCCL_BASE_DIR}/algorithm/impl/coll_executor/coll_reduce/coll_reduce_comm_executor.cc
        ${HCCL_BASE_DIR}/algorithm/impl/coll_executor/coll_reduce/coll_reduce_single_rank_executor.cc

        ${HCCL_BASE_DIR}/algorithm/impl/coll_executor/coll_reduce_scatter/coll_reduce_scatter_comm_executor.cc
        ${HCCL_BASE_DIR}/algorithm/impl/coll_executor/coll_reduce_scatter/coll_reduce_scatter_deter_executor.cc
        ${HCCL_BASE_DIR}/algorithm/impl/coll_executor/coll_reduce_scatter/coll_reduce_scatter_fast_double_ring_for_910_93_executor.cc
        ${HCCL_BASE_DIR}/algorithm/impl/coll_executor/coll_reduce_scatter/coll_aligned_reduce_scatter_double_ring_for_910_93_executor.cc
        ${HCCL_BASE_DIR}/algorithm/impl/coll_executor/coll_reduce_scatter/coll_reduce_scatter_ring_for_910_93_executor.cc
        ${HCCL_BASE_DIR}/algorithm/impl/coll_executor/coll_reduce_scatter/coll_reduce_scatter_executor.cc
        ${HCCL_BASE_DIR}/algorithm/impl/coll_executor/coll_reduce_scatter/coll_reduce_scatter_mesh_dma_elimination.cc
        ${HCCL_BASE_DIR}/algorithm/impl/coll_executor/coll_reduce_scatter/coll_reduce_scatter_mesh_executor.cc
        ${HCCL_BASE_DIR}/algorithm/impl/coll_executor/coll_reduce_scatter/coll_reduce_scatter_mesh_opbase_pipeline_executor.cc
        ${HCCL_BASE_DIR}/algorithm/impl/coll_executor/coll_reduce_scatter/coll_reduce_scatter_ring_executor.cc
        ${HCCL_BASE_DIR}/algorithm/impl/coll_executor/coll_reduce_scatter/coll_reduce_scatter_single_rank_executor.cc
        ${HCCL_BASE_DIR}/algorithm/impl/coll_executor/coll_reduce_scatter/coll_reduce_scatter_semi_ring_executor.cc
        ${HCCL_BASE_DIR}/algorithm/impl/coll_executor/coll_reduce_scatter/coll_reduce_scatter_mix_executor.cc
        ${HCCL_BASE_DIR}/algorithm/impl/coll_executor/coll_reduce_scatter/coll_reduce_scatter_hccs_sio_executor.cc
        ${HCCL_BASE_DIR}/algorithm/impl/coll_executor/coll_reduce_scatter/coll_reduce_scatter_ring_zerocopy_executor.cc
        ${HCCL_BASE_DIR}/algorithm/impl/coll_executor/coll_reduce_scatter/coll_reduce_scatter_ring_zerocopy_exchange_executor.cc
        ${HCCL_BASE_DIR}/algorithm/impl/coll_executor/coll_reduce_scatter/coll_reduce_scatter_ring_zerocopy_exchange_pipeline_executor.cc
        ${HCCL_BASE_DIR}/algorithm/impl/coll_executor/coll_reduce_scatter/coll_reduce_scatter_order_preserved_executor.cc

        ${HCCL_BASE_DIR}/algorithm/impl/coll_executor/coll_reduce_scatter_v/coll_reduce_scatter_v_executor.cc
        ${HCCL_BASE_DIR}/algorithm/impl/coll_executor/coll_reduce_scatter_v/coll_reduce_scatter_v_aiv_big_count_executor.cc
        ${HCCL_BASE_DIR}/algorithm/impl/coll_executor/coll_reduce_scatter_v/coll_reduce_scatter_v_mesh_aiv_smallcount_executor.cc
        ${HCCL_BASE_DIR}/algorithm/impl/coll_executor/coll_reduce_scatter_v/coll_reduce_scatter_v_mesh_executor.cc
        ${HCCL_BASE_DIR}/algorithm/impl/coll_executor/coll_reduce_scatter_v/coll_reduce_scatter_v_mesh_opbase_executor.cc
        ${HCCL_BASE_DIR}/algorithm/impl/coll_executor/coll_reduce_scatter_v/coll_reduce_scatter_v_ring_for_910_93_executor.cc
        ${HCCL_BASE_DIR}/algorithm/impl/coll_executor/coll_reduce_scatter_v/coll_aligned_reduce_scatter_v_double_ring_for_910_93_executor.cc
        ${HCCL_BASE_DIR}/algorithm/impl/coll_executor/coll_reduce_scatter_v/coll_reduce_scatter_v_fast_double_ring_for_910_93_executor.cc
        ${HCCL_BASE_DIR}/algorithm/impl/coll_executor/coll_reduce_scatter_v/coll_reduce_scatter_v_semi_ring_executor.cc

        ${HCCL_BASE_DIR}/algorithm/impl/coll_executor/coll_scatter/coll_scatter_executor.cc
        ${HCCL_BASE_DIR}/algorithm/impl/coll_executor/coll_scatter/coll_scatter_ring_executor.cc
        ${HCCL_BASE_DIR}/algorithm/impl/coll_executor/coll_scatter/coll_scatter_ring_for_910_93_executor.cc
        ${HCCL_BASE_DIR}/algorithm/impl/coll_executor/coll_scatter/coll_scatter_comm_executor.cc
        ${HCCL_BASE_DIR}/algorithm/impl/coll_executor/coll_scatter/coll_scatter_mesh_executor.cc
        ${HCCL_BASE_DIR}/algorithm/impl/coll_executor/coll_scatter/coll_scatter_single_rank_executor.cc

        ${HCCL_BASE_DIR}/algorithm/impl/coll_executor/coll_send_receive/coll_batch_send_recv_executor.cc
        ${HCCL_BASE_DIR}/algorithm/impl/coll_executor/coll_send_receive/coll_batch_send_recv_retry_executor.cc
        ${HCCL_BASE_DIR}/algorithm/impl/coll_executor/coll_send_receive/coll_send_executor.cc
        ${HCCL_BASE_DIR}/algorithm/impl/coll_executor/coll_send_receive/coll_receive_executor.cc
        ${HCCL_BASE_DIR}/algorithm/impl/coll_executor/coll_send_receive/coll_batch_write_executor.cc
        ${HCCL_BASE_DIR}/algorithm/impl/coll_executor/coll_all_to_all/coll_all_to_all_executor.cc
        ${HCCL_BASE_DIR}/algorithm/impl/coll_executor/coll_all_to_all/coll_all_to_all_executor_aicpu.cc
        ${HCCL_BASE_DIR}/algorithm/impl/coll_executor/coll_all_to_all/coll_all_to_all_single_rank_executor.cc
        ${HCCL_BASE_DIR}/algorithm/impl/coll_executor/coll_all_to_all/coll_all_to_all_v_fullmesh_executor.cc
        ${HCCL_BASE_DIR}/algorithm/impl/coll_executor/coll_all_to_all/coll_all_to_all_v_direct_fullmesh_executor.cc
        ${HCCL_BASE_DIR}/algorithm/impl/coll_executor/coll_all_to_all/coll_all_to_all_v_2level_pipeline_excecutor.cc
        ${HCCL_BASE_DIR}/algorithm/impl/coll_executor/coll_all_to_all/310P/coll_all_to_all_v_for_310p_executor.cc

        ${HCCL_BASE_DIR}/algorithm/impl/coll_executor/registry/coll_alg_exec_registry.cc
        ${HCCL_BASE_DIR}/algorithm/impl/coll_executor/alg_profiling.cc

        ${HCCL_BASE_DIR}/algorithm/impl/task/threadManage.cc
        ${HCCL_BASE_DIR}/algorithm/impl/task/parallel_task_loader.cc
        ${HCCL_BASE_DIR}/algorithm/impl/task/task_loader.cc

        # common
        ${HCCL_BASE_DIR}/common/debug/profiling/task_profiling.cc
        ${HCCL_BASE_DIR}/common/debug/profiling/task_exception_handler.cc
        ${HCCL_BASE_DIR}/common/debug/profiling/task_exception_handler_device.cc
        ${HCCL_BASE_DIR}/common/debug/profiling/profiler_base.cc
        ${HCCL_BASE_DIR}/common/debug/profiling/plugin_runner.cc
        ${HCCL_BASE_DIR}/common/debug/profiling/plugin_runner_device.cc
        ${HCCL_BASE_DIR}/common/debug/profiling/command_handle.cc
        ${HCCL_BASE_DIR}/common/debug/profiling/profiling_manager.cc
        ${HCCL_BASE_DIR}/common/debug/profiling/task_overflow.cc
        ${HCCL_BASE_DIR}/common/debug/profiling/profiler_manager_impl.cc
        ${HCCL_BASE_DIR}/common/debug/profiling/profiler_manager.cc
        ${HCCL_BASE_DIR}/common/debug/profiling/profiling_manager_pub.cc
        ${HCCL_BASE_DIR}/common/debug/profiling/adapter_prof.cc
        ${HCCL_BASE_DIR}/common/debug/profiling/dlprof_function.cc
        ${HCCL_BASE_DIR}/common/debug/profiling/dlrt_function.cc
        ${HCCL_BASE_DIR}/common/debug/config/config_log.cc
        ${HCCL_BASE_DIR}/common/health/calc_crc.cc
        ${HCCL_BASE_DIR}/common/health/rank_consistentcy_checker.cc
        ${HCCL_BASE_DIR}/common/stream/stream_utils_aicpu.cc

        #framework
        ${HCCL_BASE_DIR}/framework/communicator/impl/independent_op/hccl_independent_rank_graph.cc
        ${HCCL_BASE_DIR}/framework/communicator/impl/one_sided_service/i_hccl_one_sided_service.cc
    )
    target_sources(ccl_kernel PRIVATE
        ${CCL_KERNEL_SRC_LIST}
    )

    target_compile_options(ccl_kernel PRIVATE
        -Werror
        -Wfloat-equal
        -Wall
        -fno-common
        -fstack-protector-strong
        -fno-strict-aliasing
        -pipe
        -O3
        -std=c++14
    )

    target_link_options(ccl_kernel PRIVATE
    -Wl,-z,relro
    -Wl,-z,now
    -Wl,-z,noexecstack
    $<$<CONFIG:Release>:-s>
    )

    target_compile_definitions(ccl_kernel PRIVATE
        HCCD
        CCL_KERNEL_AICPU
    )
    target_include_directories(ccl_kernel PRIVATE
        ${HCCL_BASE_DIR}/../include/hccl
        ${TOP_DIR}/abl/atrace/inc/utrace
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
        ${HCCL_BASE_DIR}/common/health
        ${HCCL_BASE_DIR}/common/debug/profiling/inc
        ${HCCL_BASE_DIR}/common/debug/profiling/inc/aicpu
        ${HCCL_BASE_DIR}/common/debug/config/
        ${HCCL_BASE_DIR}/common/debug/
        ${HCCL_BASE_DIR}/common/stream
        ${HCCL_BASE_DIR}/common/launch_device
        ${HCCL_BASE_DIR}/framework/inc
        ${HCCL_BASE_DIR}/framework/cluster_maintenance/health/heartbeat/
        ${HCCL_BASE_DIR}/framework/cluster_maintenance/detect/detect_connect_anomalies/
        ${HCCL_BASE_DIR}/framework/common/src
        ${HCCL_BASE_DIR}/framework/common/src/aicpu
        ${HCCL_BASE_DIR}/framework/common/src/config
        ${HCCL_BASE_DIR}/framework/common/src/task
        ${HCCL_BASE_DIR}/framework/common/src/topo
        ${HCCL_BASE_DIR}/framework/hcom
        ${HCCL_BASE_DIR}/framework/communicator/impl/
        ${HCCL_BASE_DIR}/framework/communicator/impl/one_sided_service/
        ${HCCL_BASE_DIR}/framework/communicator/impl/zero_copy_memory_agent
        ${HCCL_BASE_DIR}/framework/communicator/impl/resource_manager
        ${HCCL_BASE_DIR}/framework/op_base/src/
        ${HCCL_BASE_DIR}/framework/device/
        ${HCCL_BASE_DIR}/framework/device/aicpu_kfc
        ${HCCL_BASE_DIR}/framework/device/aicpu_kfc/inc
        ${HCCL_BASE_DIR}/framework/device/aicpu_kfc/dfx
        ${HCCL_BASE_DIR}/framework/device/common
        ${HCCL_BASE_DIR}/framework/device/inc
        ${HCCL_BASE_DIR}/framework/device/framework
        ${HCCL_BASE_DIR}/framework/cluster_maintenance/recovery/operator_retry
        ${HCCL_BASE_DIR}/framework/common/src/exception
        ${HCCL_BASE_DIR}/framework/communicator/impl/independent_op/
        ${HCCL_BASE_DIR}/framework/communicator/impl/independent_op/resource
        ${HCCL_BASE_DIR}/framework/communicator/impl/independent_op/thread
        ${HCCL_BASE_DIR}/framework/communicator/impl/independent_op/rank_graph
        ${HCCL_BASE_DIR}/framework/communicator/impl/independent_op/channel
        ${HCCL_BASE_DIR}/framework/communicator/impl/independent_op/channel/device

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
        ${HCCL_BASE_DIR}/../pkg_inc/
        ${HCCL_BASE_DIR}/../pkg_inc/hccl/

        ${HCCL_BASE_DIR}/platform/
        ${HCCL_BASE_DIR}/platform/inc/
        ${HCCL_BASE_DIR}/platform/inc/adapter
        ${HCCL_BASE_DIR}/platform/resource/transport/heterog/
        ${HCCL_BASE_DIR}/platform/resource/transport/host/
        ${HCCL_BASE_DIR}/platform/resource/transport/
        ${HCCL_BASE_DIR}/platform/resource/notify/
        ${HCCL_BASE_DIR}/platform/task
        ${HCCL_BASE_DIR}/platform/common
        ${HCCL_BASE_DIR}/platform/common/unique
        ${HCCL_BASE_DIR}/platform/common/unfold_cache
    )

    target_link_directories(ccl_kernel PRIVATE
        ${ASCEND_CANN_PACKAGE_PATH}/devlib/device/ # c_sec、mmpa、unified_dlog动态库搜索路径
    )

    add_subdirectory(device)
endif()

if(NOT BUILD_OPEN_PROJECT)
    target_include_directories(ccl_kernel PRIVATE
        ${HCCL_BASE_DIR}/../include/hccl
        ${HCCL_BASE_DIR}/pub_inc
        ${HCCL_BASE_DIR}/pub_inc/inner
        ${HCCL_BASE_DIR}/pub_inc/aicpu
        ${HCCL_BASE_DIR}/pub_inc/new

        ${HCCL_BASE_DIR}/hccl/hccl_comm/wrapper/notify/

        ${TOP_DIR}/inc
        ${TOP_DIR}/inc/driver
        ${TOP_DIR}/metadef/inc/external
        ${TOP_DIR}/metadef/pkg_inc
        ${TOP_DIR}/metadef/pkg_inc
        ${TOP_DIR}/open_source/json/include
        ${TOP_DIR}/inc/aicpu/
        ${TOP_DIR}/atc/opcompiler/ascendc_compiler/api
        ${TOP_DIR}/atc/opcompiler/ascendc_compiler/api/impl
        ${TOP_DIR}/atc/opcompiler/ascendc_compiler/api/include
        ${TOP_DIR}/abl/adump/inc/adump
        ${TOP_DIR}/abl/atrace/inc/utrace
        ${TOP_DIR}/runtime/include/external
        ${TOP_DIR}/runtime/include/external/acl
        ${TOP_DIR}/runtime/pkg_inc
        ${TOP_DIR}/runtime/pkg_inc/runtime
        ${TOP_DIR}/runtime/pkg_inc/profiling
        ${TOP_DIR}/runtime/pkg_inc/trace
        ${TOP_DIR}/runtime/pkg_inc/base
        ${TOP_DIR}/runtime/pkg_inc/aicpu
        ${TOP_DIR}/asc/asc-devkit/include/adv_api/hccl/internal
        ${HCCL_BASE_DIR}/platform/
        ${HCCL_BASE_DIR}/platform/inc/
        ${HCCL_BASE_DIR}/platform/inc/adapter
        ${HCCL_BASE_DIR}/platform/resource/transport/heterog/
        ${HCCL_BASE_DIR}/platform/resource/transport/host/
        ${HCCL_BASE_DIR}/platform/resource/transport/
        ${HCCL_BASE_DIR}/platform/resource/notify/
        ${HCCL_BASE_DIR}/platform/resource/dispatcher_ctx
        ${HCCL_BASE_DIR}/platform/task
        ${HCCL_BASE_DIR}/platform/common
        ${HCCL_BASE_DIR}/platform/common/unique
        ${HCCL_BASE_DIR}/platform/common/unfold_cache

        ${HCCL_BASE_DIR}/platform/hccp/inc
        ${HCCL_BASE_DIR}/platform/hccp/inc/network
	    ${HCCL_BASE_DIR}/../pkg_inc/
        ${HCCL_BASE_DIR}/../pkg_inc/hccl/
        ${HCCL_BASE_DIR}/framework
        ${HCCL_BASE_DIR}/framework/common
        ${HCCL_BASE_DIR}/framework/common/src
        ${HCCL_BASE_DIR}/framework/common/src/mgr
        ${HCCL_BASE_DIR}/framework/communicator
        ${HCCL_BASE_DIR}/framework/communicator/impl/independent_op/resource/engine
    )
    target_link_libraries(ccl_kernel PRIVATE
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
        ccl_kernel_plf
        mmpa
        -Wl,--as-needed
        -lrt
        -ldl
        -lpthread
        ofed_headers
    )

    install(TARGETS  ccl_kernel
        LIBRARY DESTINATION ${INSTALL_LIBRARY_DIR}  OPTIONAL
    )
endif()
add_subdirectory(common)
add_subdirectory(communicator)
add_subdirectory(hcom)
add_subdirectory(op_base)
add_subdirectory(cluster_maintenance)
add_subdirectory(nslbdp)

if(NOT KERNEL_MODE)
    SET(HCCL_CMAKE_DIR ${HCCL_OPEN_CODE_BASE_DIR}/../cmake/)
    message(STATUS "HCCL_CMAKE_DIR = ${HCCL_CMAKE_DIR}")
    add_custom_command(OUTPUT ${CMAKE_CURRENT_BINARY_DIR}/ccl_kernel.json
        COMMAND ${HI_PYTHON} ${HCCL_CMAKE_DIR}/scripts/parser_ini.py ${CMAKE_CURRENT_SOURCE_DIR}/device/framework/ccl_kernel.ini ${CMAKE_CURRENT_BINARY_DIR}/ccl_kernel.json
        WORKING_DIRECTORY ${CMAKE_CURRENT_SOURCE_DIR}
    )
    add_custom_target(ccl_kernel_json DEPENDS ${CMAKE_CURRENT_BINARY_DIR}/ccl_kernel.json)
    install(FILES ${CMAKE_CURRENT_BINARY_DIR}/ccl_kernel.json
        DESTINATION ${INSTALL_CCL_KERNEL_JSON_DIR} OPTIONAL
    )

    add_custom_command(OUTPUT ${CMAKE_CURRENT_BINARY_DIR}/libaicpu_custom.json
        COMMAND ${HI_PYTHON} ${HCCL_BASE_DIR}/../cmake/scripts/parser_ini.py ${CMAKE_CURRENT_SOURCE_DIR}/device/framework/aicpu_custom.ini ${CMAKE_CURRENT_BINARY_DIR}/libaicpu_custom.json
        WORKING_DIRECTORY ${CMAKE_CURRENT_SOURCE_DIR}
    )
    add_custom_target(aicpu_custom_json DEPENDS ${CMAKE_CURRENT_BINARY_DIR}/libaicpu_custom.json)
    install(FILES ${CMAKE_CURRENT_BINARY_DIR}/libaicpu_custom.json
        DESTINATION ${INSTALL_CCL_KERNEL_JSON_DIR} OPTIONAL
    )

    add_dependencies(hcomm ccl_kernel_json aicpu_custom_json)
endif()

if(BUILD_OPEN_PROJECT AND KERNEL_MODE)
    target_include_directories(ccl_kernel PRIVATE
        ${HCCL_BASE_DIR}/platform/hccp/external_depends/rdma-core/include # 解决头文件依赖问题<infiniband/verbs.h>
        ${HCCL_BASE_DIR}/platform/
        ${HCCL_BASE_DIR}/platform/inc/
        ${HCCL_BASE_DIR}/platform/inc/adapter
        ${HCCL_BASE_DIR}/platform/resource/transport/heterog/
        ${HCCL_BASE_DIR}/platform/resource/transport/host/
        ${HCCL_BASE_DIR}/platform/resource/transport/
        ${HCCL_BASE_DIR}/platform/resource/notify/
        ${HCCL_BASE_DIR}/platform/resource/dispatcher_ctx
        ${HCCL_BASE_DIR}/platform/task
        ${HCCL_BASE_DIR}/platform/common
        ${HCCL_BASE_DIR}/platform/common/unique
        ${hccl_include_list}
        ${HCCL_BASE_DIR}/../include
        ${HCCL_BASE_DIR}/../include/hccl
        ${HCCL_BASE_DIR}/../pkg_inc/
        ${HCCL_BASE_DIR}/../pkg_inc/hccl/
        ${HCCL_BASE_DIR}/pub_inc
        ${HCCL_BASE_DIR}/pub_inc/aicpu

        ${HCCL_BASE_DIR}/framework/device/
        ${HCCL_BASE_DIR}/framework/device/common
        ${HCCL_BASE_DIR}/framework/device/inc
        ${HCCL_BASE_DIR}/framework/device/framework

        # runtime头文件
        ${ASCEND_CANN_PACKAGE_PATH}/include/

        # mmpa头文件
        ${ASCEND_CANN_PACKAGE_PATH}/include/acl/
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

        # ascendc
        ${ASCEND_CANN_PACKAGE_PATH}/include/ascendc/highlevel_api/
        ${ASCEND_CANN_PACKAGE_PATH}/pkg_inc/asc/hccl/internal/
        ${ASCEND_CANN_PACKAGE_PATH}/include/ascendc/

        ${HCCL_BASE_DIR}/../externel_depends/tsch/
        ${HCCL_BASE_DIR}/platform/hccp/external_depends/rdma-core/include
        ${THIRD_PARTY_NLOHMANN_PATH}
        )
    if(BUILD_OPEN_PROJECT)
        set(CMAKE_CXX_FLAGS "")
        target_compile_definitions(ccl_kernel PRIVATE
            OPEN_BUILD_PROJECT
            -D_GLIBCXX_USE_CXX11_ABI=1) # 链接ascendalog需要LOG_CPP，链接slog不需要
        # set(CMAKE_SHARED_LINKER_FLAGS "${CMAKE_SHARED_LINKER_FLAGS} -Wl,--allow-multiple-definition")
        message(STATUS "framework CMAKE_HOST_SYSTEM_PROCESSOR=${CMAKE_HOST_SYSTEM_PROCESSOR}")
        if(CMAKE_HOST_SYSTEM_PROCESSOR MATCHES "x86_64")
            message(STATUS "Host is x86_64")
            set(ASCEND_CANN_PACKAGE_ENV_PATH ${ASCEND_CANN_PACKAGE_PATH}/x86_64-linux)
        elseif(CMAKE_HOST_SYSTEM_PROCESSOR MATCHES "aarch64")
            message(STATUS "Host is ARM64")
            set(ASCEND_CANN_PACKAGE_ENV_PATH ${ASCEND_CANN_PACKAGE_PATH}/aarch64-linux)
        endif()
        message(STATUS "framework ASCEND_CANN_PACKAGE_ENV_PATH=${ASCEND_CANN_PACKAGE_ENV_PATH}")
        set(CCL_KERNEL_PLF_PATH
            -Wl,--whole-archive
            ${HCCL_BASE_DIR}/../build/src/libccl_kernel_plf.a
            -Wl,--no-whole-archive
            -Wl,-Bsymbolic
        )
        if(FULL_MODE)
            set(CCL_KERNEL_PLF_PATH ccl_kernel_plf)
        endif()
        target_link_libraries(ccl_kernel PRIVATE
            -Wl,--no-as-needed
            ascend_hal
            c_sec
            mmpa
            ${CCL_KERNEL_PLF_PATH}
            -Wl,--as-needed
            -lrt
            -ldl
            -lpthread
        )

        add_custom_command(OUTPUT ${CMAKE_CURRENT_BINARY_DIR}/libaicpu_custom.json
            COMMAND ${HI_PYTHON} ${HCCL_BASE_DIR}/../cmake/scripts/parser_ini.py ${CMAKE_CURRENT_SOURCE_DIR}/device/framework/aicpu_custom.ini ${CMAKE_CURRENT_BINARY_DIR}/libaicpu_custom.json
            WORKING_DIRECTORY ${CMAKE_CURRENT_SOURCE_DIR}
        )
        add_custom_target(aicpu_custom_json DEPENDS ${CMAKE_CURRENT_BINARY_DIR}/libaicpu_custom.json)
        install(FILES ${CMAKE_CURRENT_BINARY_DIR}/libaicpu_custom.json
            DESTINATION ${CMAKE_CURRENT_BINARY_DIR} OPTIONAL
        )

        target_link_directories(ccl_kernel PRIVATE
            ${ASCEND_CANN_PACKAGE_PATH}/devlib/device/ # c_sec、mmpa、unified_dlog动态库搜索路径
        )
    endif()
endif()

if(DEVICE_MODE AND KERNEL_MODE)
    set(CCL_KERNEL_TAR_DIR ${HCCL_BASE_DIR}/../build_device/ccl_kernel_tar_pkg/aicpu_kernels_device)
    add_custom_command(
        TARGET ccl_kernel
        POST_BUILD
        COMMAND ${CMAKE_COMMAND} -E make_directory ${CCL_KERNEL_TAR_DIR}
        COMMAND ${CMAKE_COMMAND} -E copy $<TARGET_FILE:ccl_kernel> ${CCL_KERNEL_TAR_DIR}
        COMMAND ${CMAKE_COMMAND} -E copy $<TARGET_FILE:ccl_kernel_plf> ${CCL_KERNEL_TAR_DIR}
        COMMAND chmod 750 ${CCL_KERNEL_TAR_DIR}/lib*
        COMMENT "Copying libccl_kernel_plf.so libccl_kernel.so to ${CCL_KERNEL_TAR_DIR}"
    )

    set(AICPU_CUSTOM_DIR ${HCCL_BASE_DIR}/../build_device/aicpu_custom/)
    add_custom_command(
        TARGET ccl_kernel
        POST_BUILD
        COMMAND ${CMAKE_COMMAND} -E make_directory ${AICPU_CUSTOM_DIR}
        COMMAND ${CMAKE_COMMAND} -E copy $<TARGET_FILE:ccl_kernel> ${AICPU_CUSTOM_DIR}/libaicpu_custom.so
        COMMAND chmod 750 ${AICPU_CUSTOM_DIR}/lib*
        COMMENT "Copying libccl_kernel.so to ${AICPU_CUSTOM_DIR}/libaicpu_custom.so"
    )
endif()