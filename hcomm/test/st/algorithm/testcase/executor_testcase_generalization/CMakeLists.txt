# -----------------------------------------------------------------------------------------------------------
# Copyright (c) 2025 Huawei Technologies Co., Ltd.
# This program is free software, you can redistribute it and/or modify it under the terms and conditions of
# CANN Open Software License Agreement Version 2.0 (the "License").
# Please refer to the License for details. You may not use this file except in compliance with the License.
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
# See LICENSE in the root of the software repository for the full text of the License.
# -----------------------------------------------------------------------------------------------------------
add_executable(executor_hccl_test ${src_to_test_list})

#头文件搜索路径
target_include_directories(executor_hccl_test PRIVATE
    ${HCOMM_ALG_TC_ROOT}/testcase

    ${UTILS_PUBLIC_INCLUDE_LIST}
    ${HCOMM_PUBLIC_INCLUDE_LIST}
    ${HCOMM_PLATFORM_INCLUDE_LIST}
    ${HCOMM_ALGORITHM_INCLUDE_LIST}
    ${HCOMM_COMMON_INCLUDE_LIST}
    ${HCOMM_FRAMEWORK_INCLUDE_LIST}

    ${THIRD_PARTY_PATH}/json/include
    ${THIRD_PARTY_PATH}/gtest_shared/include
    ${THIRD_PARTY_PATH}/mockcpp_shared/include

    ${ASCEND_CANN_INCLUDE_LIST}
)

target_compile_definitions(executor_hccl_test PRIVATE
    _GLIBCXX_USE_CXX11_ABI=0
    -DOPEN_HCCL_TEST
)

target_compile_options(executor_hccl_test PRIVATE
    -U_FORTIFY_SOURCE
    -Os
    -O0 -g
    $<$<STREQUAL:${ENABLE_ASAN},true>:-fsanitize=address -fsanitize-recover=address,all -fno-omit-frame-pointer>
)

target_link_libraries(executor_hccl_test PRIVATE
    hccl_alg_analyzer
    hccl_alg_adaption
    hccl_alg_test
    $<$<STREQUAL:${ENABLE_ASAN},true>:-fsanitize=address>
    ${THIRD_PARTY_PATH}/mockcpp_shared/lib/libmockcpp.a
    ${THIRD_PARTY_PATH}/gtest_shared/lib64/libgtest.so
    -lpthread
    ${PROTO_SOURCE_DIR}/libprotobuf.so
    ${ASCEND_CANN_PACKAGE_PATH}/lib64/libc_sec.so
    -lrt
    -ldl
)

add_subdirectory(RunAlltoAllVTwoLevelPipeline)
add_subdirectory(BroadCastRingFor91093Executor)
add_subdirectory(AllGatherMeshOpbasePipelineExecutor)
add_subdirectory(AllGatherMeshExecutor)
add_subdirectory(ScatterMeshExecutor)
add_subdirectory(BroadCastMeshExecutor)
add_subdirectory(AllGatherMeshGraphPipelineExecutor)
add_subdirectory(HcclAlgoEnv)

target_sources(executor_hccl_test
    PUBLIC
    main.cc
    ../testcase/testcase_utils.cc
)