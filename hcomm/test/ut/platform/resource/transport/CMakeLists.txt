# -----------------------------------------------------------------------------------------------------------
# Copyright (c) 2025 Huawei Technologies Co., Ltd.
# This program is free software, you can redistribute it and/or modify it under the terms and conditions of
# CANN Open Software License Agreement Version 2.0 (the "License").
# Please refer to the License for details. You may not use this file except in compliance with the License.
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
# See LICENSE in the root of the software repository for the full text of the License.
# -----------------------------------------------------------------------------------------------------------
set(hccl_utest_platform_transport_list
    main.cc
    ut_aicpu_transport_device_p2p_utest.cc
)
add_executable(hccl_utest_platform_transport  ${hccl_utest_platform_transport_list})

target_include_directories(hccl_utest_platform_transport  PRIVATE
    ${UT_COMMON_INCLUDE_LIST}
)

target_compile_definitions(hccl_utest_platform_transport    PRIVATE
    HALF_T=float
    google=ascend_private
    CCL_KERNEL
    -DCCL_LLT
)

target_compile_options(hccl_utest_platform_transport   PRIVATE 
    -U_FORTIFY_SOURCE
    -O0 -g --coverage -fprofile-arcs -ftest-coverage -fno-access-control
    $<$<COMPILE_LANGUAGE:CXX>:-std=c++14>
)


target_link_libraries(hccl_utest_platform_transport  PRIVATE
    $<BUILD_INTERFACE:intf_pub>
    -lpthread
    hccl_llt
    -Wl,--whole-archive
    -Wl,--no-whole-archi
    -lgcov
    -lrt
    -lpthread
)

add_dependencies(hccl_utest_platform_transport hccl_llt)

run_llt_test(
    TARGET  hccl_utest_platform_transport
    TASK_NUM 1
)
