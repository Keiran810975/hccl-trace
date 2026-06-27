# -----------------------------------------------------------------------------------------------------------
# Copyright (c) 2025 Huawei Technologies Co., Ltd.
# This program is free software, you can redistribute it and/or modify it under the terms and conditions of
# CANN Open Software License Agreement Version 2.0 (the "License").
# Please refer to the License for details. You may not use this file except in compliance with the License.
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
# See LICENSE in the root of the software repository for the full text of the License.
# -----------------------------------------------------------------------------------------------------------
set_source_files_properties(
    aiv_communication.h PROPERTIES LANGUAGE CXX
)

if(CCACHE_PROGRAM)
    set(BISHENG_CCACHE ${CCACHE_PROGRAM})
endif()
if(BUILD_OPEN_PROJECT)
    set(CCE_DIR ${ASCEND_CANN_PACKAGE_PATH}/tools/ccec_compiler/bin)
    add_custom_target(hccl_aiv_op_ascend910B ALL
        DEPENDS ${CMAKE_CURRENT_BINARY_DIR}/hccl_aiv_op_ascend910B.o)
    add_custom_command(OUTPUT ${CMAKE_CURRENT_BINARY_DIR}/hccl_aiv_op_ascend910B.o
            COMMAND ${BISHENG_CCACHE} ${CCE_DIR}/ccec -c -x cce -O2 ${CMAKE_CURRENT_SOURCE_DIR}/aiv_communication.h -o ${CMAKE_CURRENT_BINARY_DIR}/hccl_aiv_op_ascend910B_tmp.o 
            -DASCNEDC_DUMP --cce-aicore-arch=dav-c220-vec
            --cce-aicore-input-parameter-size=28000 --cce-aicore-only -mllvm -cce-aicore-function-stack-size=0x8000 -mllvm -cce-aicore-dcci-insert-for-scalar=false
            -mllvm -cce-aicore-stack-size=0x8000
            -I${ASCEND_CANN_PACKAGE_PATH}/include/ascendc/basic_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/include/ascendc/basic_api/interface/
            -I${ASCEND_CANN_PACKAGE_PATH}/include/ascendc/include/adv_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/include/ascendc/highlevel_api
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/ascendc/include/basic_api/impl/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/asc/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/asc/impl/basic_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/asc/impl/simt_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/asc/impl/micro_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/include/basic_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/include/simt_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/include/micro_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/include/hccl/
            -I${CMAKE_CURRENT_SOURCE_DIR}/aiv_interface/
            -mllvm -cce-aicore-record-overflow=false -mllvm -cce-aicore-addr-transform -mllvm
            --cce-aicore-jump-expand=true -std=c++17 -fstack-protector-all -DONE_CORE_DUMP_SIZE=1024
            COMMAND ${CCE_DIR}/ld.lld -m aicorelinux -Ttext=0 ${CMAKE_CURRENT_BINARY_DIR}/hccl_aiv_op_ascend910B_tmp.o -static -o ${CMAKE_CURRENT_BINARY_DIR}/hccl_aiv_op_ascend910B.o
            WORKING_DIRECTORY ${CMAKE_CURRENT_BINARY_DIR}
    )
    add_custom_target(hccl_ag_superkernel_int8 ALL
        DEPENDS ${CMAKE_CURRENT_BINARY_DIR}/hccl_ag_superkernel_int8.o)
    add_custom_command(OUTPUT ${CMAKE_CURRENT_BINARY_DIR}/hccl_ag_superkernel_int8.o
            COMMAND ${BISHENG_CCACHE} ${CCE_DIR}/ccec -c -x cce -O2 ${CMAKE_CURRENT_SOURCE_DIR}/aiv_ag_superkernel.h -o ${CMAKE_CURRENT_BINARY_DIR}/hccl_ag_superkernel_int8.o --cce-aicore-arch=dav-c220-vec
            -DTILING_KEY_VAR=0UL -D__ASCENDC_ENABLE_SUPER_KERNEL__ -DASCENDC_DUMP=0 -DL2_CACHE_HINT -DCONST_TILING -DDETERMINISTIC_MODE=0 -DHCCL_DTYPE_INT8 -Dsk_allgather=sk_allgather_int8
            --cce-aicore-input-parameter-size=28000 --cce-aicore-only -mllvm -cce-aicore-function-stack-size=0x8000 -mllvm -cce-aicore-stack-size=0x8000
            -I${ASCEND_CANN_PACKAGE_PATH}/include/ascendc/basic_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/include/ascendc/basic_api/interface/
            -I${ASCEND_CANN_PACKAGE_PATH}/include/ascendc/include/adv_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/include/ascendc/highlevel_api
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/ascendc/include/basic_api/impl/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/asc/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/asc/impl/basic_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/asc/impl/simt_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/asc/impl/micro_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/include/basic_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/include/simt_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/include/micro_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/include/hccl/
            -I${CMAKE_CURRENT_SOURCE_DIR}/aiv_interface/
            -mllvm -cce-aicore-record-overflow=false -mllvm -cce-aicore-addr-transform -mllvm
            --cce-aicore-jump-expand=true -std=c++17 -fstack-protector-all
            WORKING_DIRECTORY ${CMAKE_CURRENT_BINARY_DIR}
    )

    add_custom_target(hccl_ag_superkernel_int16 ALL
        DEPENDS ${CMAKE_CURRENT_BINARY_DIR}/hccl_ag_superkernel_int16.o)
    add_custom_command(OUTPUT ${CMAKE_CURRENT_BINARY_DIR}/hccl_ag_superkernel_int16.o
            COMMAND ${BISHENG_CCACHE} ${CCE_DIR}/ccec -c -x cce -O2 ${CMAKE_CURRENT_SOURCE_DIR}/aiv_ag_superkernel.h -o ${CMAKE_CURRENT_BINARY_DIR}/hccl_ag_superkernel_int16.o --cce-aicore-arch=dav-c220-vec
            -DTILING_KEY_VAR=0UL -D__ASCENDC_ENABLE_SUPER_KERNEL__ -DASCENDC_DUMP=0 -DL2_CACHE_HINT -DCONST_TILING -DDETERMINISTIC_MODE=0 -DHCCL_DTYPE_INT16 -Dsk_allgather=sk_allgather_int16
            --cce-aicore-input-parameter-size=28000 --cce-aicore-only -mllvm -cce-aicore-function-stack-size=0x8000 -mllvm -cce-aicore-stack-size=0x8000
            -I${ASCEND_CANN_PACKAGE_PATH}/include/ascendc/basic_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/include/ascendc/basic_api/interface/
            -I${ASCEND_CANN_PACKAGE_PATH}/include/ascendc/include/adv_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/include/ascendc/highlevel_api
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/ascendc/include/basic_api/impl/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/asc/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/asc/impl/basic_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/asc/impl/simt_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/asc/impl/micro_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/include/basic_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/include/simt_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/include/micro_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/include/hccl/
            -I${CMAKE_CURRENT_SOURCE_DIR}/aiv_interface/
            -mllvm -cce-aicore-record-overflow=false -mllvm -cce-aicore-addr-transform -mllvm
            --cce-aicore-jump-expand=true -std=c++17 -fstack-protector-all
            WORKING_DIRECTORY ${CMAKE_CURRENT_BINARY_DIR}
            
    )

    add_custom_target(hccl_ag_superkernel_int32 ALL
        DEPENDS ${CMAKE_CURRENT_BINARY_DIR}/hccl_ag_superkernel_int32.o)
    add_custom_command(OUTPUT ${CMAKE_CURRENT_BINARY_DIR}/hccl_ag_superkernel_int32.o
            COMMAND ${BISHENG_CCACHE} ${CCE_DIR}/ccec -c -x cce -O2 ${CMAKE_CURRENT_SOURCE_DIR}/aiv_ag_superkernel.h -o ${CMAKE_CURRENT_BINARY_DIR}/hccl_ag_superkernel_int32.o --cce-aicore-arch=dav-c220-vec
            -DTILING_KEY_VAR=0UL -D__ASCENDC_ENABLE_SUPER_KERNEL__ -DASCENDC_DUMP=0 -DL2_CACHE_HINT -DCONST_TILING -DDETERMINISTIC_MODE=0 -DHCCL_DTYPE_INT32 -Dsk_allgather=sk_allgather_int32
            --cce-aicore-input-parameter-size=28000 --cce-aicore-only -mllvm -cce-aicore-function-stack-size=0x8000 -mllvm -cce-aicore-stack-size=0x8000
            -I${ASCEND_CANN_PACKAGE_PATH}/include/ascendc/basic_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/include/ascendc/basic_api/interface/
            -I${ASCEND_CANN_PACKAGE_PATH}/include/ascendc/include/adv_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/include/ascendc/highlevel_api
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/ascendc/include/basic_api/impl/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/asc/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/asc/impl/basic_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/asc/impl/simt_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/asc/impl/micro_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/include/basic_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/include/simt_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/include/micro_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/include/hccl/
            -I${CMAKE_CURRENT_SOURCE_DIR}/aiv_interface/
            -mllvm -cce-aicore-record-overflow=false -mllvm -cce-aicore-addr-transform -mllvm
            --cce-aicore-jump-expand=true -std=c++17 -fstack-protector-all
            WORKING_DIRECTORY ${CMAKE_CURRENT_BINARY_DIR}
            
    )

    add_custom_target(hccl_ag_superkernel_float16 ALL
        DEPENDS ${CMAKE_CURRENT_BINARY_DIR}/hccl_ag_superkernel_float16.o)
    add_custom_command(OUTPUT ${CMAKE_CURRENT_BINARY_DIR}/hccl_ag_superkernel_float16.o
            COMMAND ${BISHENG_CCACHE} ${CCE_DIR}/ccec -c -x cce -O2 ${CMAKE_CURRENT_SOURCE_DIR}/aiv_ag_superkernel.h -o ${CMAKE_CURRENT_BINARY_DIR}/hccl_ag_superkernel_float16.o --cce-aicore-arch=dav-c220-vec
            -DTILING_KEY_VAR=0UL -D__ASCENDC_ENABLE_SUPER_KERNEL__ -DASCENDC_DUMP=0 -DL2_CACHE_HINT -DCONST_TILING -DDETERMINISTIC_MODE=0 -DHCCL_DTYPE_FP16 -Dsk_allgather=sk_allgather_float16
            --cce-aicore-input-parameter-size=28000 --cce-aicore-only -mllvm -cce-aicore-function-stack-size=0x8000 -mllvm -cce-aicore-stack-size=0x8000
            -I${ASCEND_CANN_PACKAGE_PATH}/include/ascendc/basic_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/include/ascendc/basic_api/interface/
            -I${ASCEND_CANN_PACKAGE_PATH}/include/ascendc/include/adv_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/include/ascendc/highlevel_api
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/ascendc/include/basic_api/impl/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/asc/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/asc/impl/basic_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/asc/impl/simt_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/asc/impl/micro_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/include/basic_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/include/simt_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/include/micro_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/include/hccl/
            -I${CMAKE_CURRENT_SOURCE_DIR}/aiv_interface/
            -mllvm -cce-aicore-record-overflow=false -mllvm -cce-aicore-addr-transform -mllvm
            --cce-aicore-jump-expand=true -std=c++17 -fstack-protector-all
            WORKING_DIRECTORY ${CMAKE_CURRENT_BINARY_DIR}
            
    )

    add_custom_target(hccl_ag_superkernel_float32 ALL
        DEPENDS ${CMAKE_CURRENT_BINARY_DIR}/hccl_ag_superkernel_float32.o)
    add_custom_command(OUTPUT ${CMAKE_CURRENT_BINARY_DIR}/hccl_ag_superkernel_float32.o
            COMMAND ${BISHENG_CCACHE} ${CCE_DIR}/ccec -c -x cce -O2 ${CMAKE_CURRENT_SOURCE_DIR}/aiv_ag_superkernel.h -o ${CMAKE_CURRENT_BINARY_DIR}/hccl_ag_superkernel_float32.o --cce-aicore-arch=dav-c220-vec
            -DTILING_KEY_VAR=0UL -D__ASCENDC_ENABLE_SUPER_KERNEL__ -DASCENDC_DUMP=0 -DL2_CACHE_HINT -DCONST_TILING -DDETERMINISTIC_MODE=0 -DHCCL_DTYPE_FP32 -Dsk_allgather=sk_allgather_float32
            --cce-aicore-input-parameter-size=28000 --cce-aicore-only -mllvm -cce-aicore-function-stack-size=0x8000 -mllvm -cce-aicore-stack-size=0x8000
            -I${ASCEND_CANN_PACKAGE_PATH}/include/ascendc/basic_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/include/ascendc/basic_api/interface/
            -I${ASCEND_CANN_PACKAGE_PATH}/include/ascendc/include/adv_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/include/ascendc/highlevel_api
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/ascendc/include/basic_api/impl/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/asc/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/asc/impl/basic_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/asc/impl/simt_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/asc/impl/micro_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/include/basic_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/include/simt_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/include/micro_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/include/hccl/
            -I${CMAKE_CURRENT_SOURCE_DIR}/aiv_interface/
            -mllvm -cce-aicore-record-overflow=false -mllvm -cce-aicore-addr-transform -mllvm
            --cce-aicore-jump-expand=true -std=c++17 -fstack-protector-all
            WORKING_DIRECTORY ${CMAKE_CURRENT_BINARY_DIR}
            
    )

    add_custom_target(hccl_ag_superkernel_bfloat16 ALL
        DEPENDS ${CMAKE_CURRENT_BINARY_DIR}/hccl_ag_superkernel_bfloat16.o)
    add_custom_command(OUTPUT ${CMAKE_CURRENT_BINARY_DIR}/hccl_ag_superkernel_bfloat16.o
            COMMAND ${BISHENG_CCACHE} ${CCE_DIR}/ccec -c -x cce -O2 ${CMAKE_CURRENT_SOURCE_DIR}/aiv_ag_superkernel.h -o ${CMAKE_CURRENT_BINARY_DIR}/hccl_ag_superkernel_bfloat16.o --cce-aicore-arch=dav-c220-vec
            -DTILING_KEY_VAR=0UL -D__ASCENDC_ENABLE_SUPER_KERNEL__ -DASCENDC_DUMP=0 -DL2_CACHE_HINT -DCONST_TILING -DDETERMINISTIC_MODE=0 -DHCCL_DTYPE_BFP16 -Dsk_allgather=sk_allgather_bfloat16
            --cce-aicore-input-parameter-size=28000 --cce-aicore-only -mllvm -cce-aicore-function-stack-size=0x8000 -mllvm -cce-aicore-stack-size=0x8000
            -I${ASCEND_CANN_PACKAGE_PATH}/include/ascendc/basic_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/include/ascendc/basic_api/interface/
            -I${ASCEND_CANN_PACKAGE_PATH}/include/ascendc/include/adv_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/include/ascendc/highlevel_api
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/ascendc/include/basic_api/impl/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/asc/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/asc/impl/basic_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/asc/impl/simt_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/asc/impl/micro_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/include/basic_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/include/simt_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/include/micro_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/include/hccl/
            -I${CMAKE_CURRENT_SOURCE_DIR}/aiv_interface/
            -mllvm -cce-aicore-record-overflow=false -mllvm -cce-aicore-addr-transform -mllvm
            --cce-aicore-jump-expand=true -std=c++17 -fstack-protector-all
            WORKING_DIRECTORY ${CMAKE_CURRENT_BINARY_DIR}
            
    )

    add_custom_target(hccl_ag_superkernel_uint8 ALL
        DEPENDS ${CMAKE_CURRENT_BINARY_DIR}/hccl_ag_superkernel_uint8.o)
    add_custom_command(OUTPUT ${CMAKE_CURRENT_BINARY_DIR}/hccl_ag_superkernel_uint8.o
            COMMAND ${BISHENG_CCACHE} ${CCE_DIR}/ccec -c -x cce -O2 ${CMAKE_CURRENT_SOURCE_DIR}/aiv_ag_superkernel.h -o ${CMAKE_CURRENT_BINARY_DIR}/hccl_ag_superkernel_uint8.o --cce-aicore-arch=dav-c220-vec
            -DTILING_KEY_VAR=0UL -D__ASCENDC_ENABLE_SUPER_KERNEL__ -DASCENDC_DUMP=0 -DL2_CACHE_HINT -DCONST_TILING -DDETERMINISTIC_MODE=0 -DHCCL_DTYPE_UINT8 -Dsk_allgather=sk_allgather_uint8
            --cce-aicore-input-parameter-size=28000 --cce-aicore-only -mllvm -cce-aicore-function-stack-size=0x8000 -mllvm -cce-aicore-stack-size=0x8000
            -I${ASCEND_CANN_PACKAGE_PATH}/include/ascendc/basic_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/include/ascendc/basic_api/interface/
            -I${ASCEND_CANN_PACKAGE_PATH}/include/ascendc/include/adv_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/include/ascendc/highlevel_api
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/ascendc/include/basic_api/impl/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/asc/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/asc/impl/basic_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/asc/impl/simt_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/asc/impl/micro_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/include/basic_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/include/simt_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/include/micro_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/include/hccl/
            -I${CMAKE_CURRENT_SOURCE_DIR}/aiv_interface/
            -mllvm -cce-aicore-record-overflow=false -mllvm -cce-aicore-addr-transform -mllvm
            --cce-aicore-jump-expand=true -std=c++17 -fstack-protector-all
            WORKING_DIRECTORY ${CMAKE_CURRENT_BINARY_DIR}
            
    )
    
    add_custom_target(hccl_ag_superkernel_uint16 ALL
        DEPENDS ${CMAKE_CURRENT_BINARY_DIR}/hccl_ag_superkernel_uint16.o)
    add_custom_command(OUTPUT ${CMAKE_CURRENT_BINARY_DIR}/hccl_ag_superkernel_uint16.o
            COMMAND ${BISHENG_CCACHE} ${CCE_DIR}/ccec -c -x cce -O2 ${CMAKE_CURRENT_SOURCE_DIR}/aiv_ag_superkernel.h -o ${CMAKE_CURRENT_BINARY_DIR}/hccl_ag_superkernel_uint16.o --cce-aicore-arch=dav-c220-vec
            -DTILING_KEY_VAR=0UL -D__ASCENDC_ENABLE_SUPER_KERNEL__ -DASCENDC_DUMP=0 -DL2_CACHE_HINT -DCONST_TILING -DDETERMINISTIC_MODE=0 -DHCCL_DTYPE_UINT16 -Dsk_allgather=sk_allgather_uint16
            --cce-aicore-input-parameter-size=28000 --cce-aicore-only -mllvm -cce-aicore-function-stack-size=0x8000 -mllvm -cce-aicore-stack-size=0x8000
            -I${ASCEND_CANN_PACKAGE_PATH}/include/ascendc/basic_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/include/ascendc/basic_api/interface/
            -I${ASCEND_CANN_PACKAGE_PATH}/include/ascendc/include/adv_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/include/ascendc/highlevel_api
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/ascendc/include/basic_api/impl/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/asc/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/asc/impl/basic_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/asc/impl/simt_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/asc/impl/micro_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/include/basic_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/include/simt_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/include/micro_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/include/hccl/
            -I${CMAKE_CURRENT_SOURCE_DIR}/aiv_interface/
            -mllvm -cce-aicore-record-overflow=false -mllvm -cce-aicore-addr-transform -mllvm
            --cce-aicore-jump-expand=true -std=c++17 -fstack-protector-all
            WORKING_DIRECTORY ${CMAKE_CURRENT_BINARY_DIR}
            
    )

    add_custom_target(hccl_ag_superkernel_uint32 ALL
        DEPENDS ${CMAKE_CURRENT_BINARY_DIR}/hccl_ag_superkernel_uint32.o)
    add_custom_command(OUTPUT ${CMAKE_CURRENT_BINARY_DIR}/hccl_ag_superkernel_uint32.o
            COMMAND ${BISHENG_CCACHE} ${CCE_DIR}/ccec -c -x cce -O2 ${CMAKE_CURRENT_SOURCE_DIR}/aiv_ag_superkernel.h -o ${CMAKE_CURRENT_BINARY_DIR}/hccl_ag_superkernel_uint32.o --cce-aicore-arch=dav-c220-vec
            -DTILING_KEY_VAR=0UL -D__ASCENDC_ENABLE_SUPER_KERNEL__ -DASCENDC_DUMP=0 -DL2_CACHE_HINT -DCONST_TILING -DDETERMINISTIC_MODE=0 -DHCCL_DTYPE_UINT32 -Dsk_allgather=sk_allgather_uint32
            --cce-aicore-input-parameter-size=28000 --cce-aicore-only -mllvm -cce-aicore-function-stack-size=0x8000 -mllvm -cce-aicore-stack-size=0x8000
            -I${ASCEND_CANN_PACKAGE_PATH}/include/ascendc/basic_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/include/ascendc/basic_api/interface/
            -I${ASCEND_CANN_PACKAGE_PATH}/include/ascendc/include/adv_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/include/ascendc/highlevel_api
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/ascendc/include/basic_api/impl/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/asc/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/asc/impl/basic_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/asc/impl/simt_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/asc/impl/micro_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/include/basic_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/include/simt_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/include/micro_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/include/hccl/
            -I${CMAKE_CURRENT_SOURCE_DIR}/aiv_interface/
            -mllvm -cce-aicore-record-overflow=false -mllvm -cce-aicore-addr-transform -mllvm
            --cce-aicore-jump-expand=true -std=c++17 -fstack-protector-all
            WORKING_DIRECTORY ${CMAKE_CURRENT_BINARY_DIR}
            
    )


    add_custom_target(hccl_rs_superkernel_int8 ALL
        DEPENDS ${CMAKE_CURRENT_BINARY_DIR}/hccl_rs_superkernel_int8.o)
    add_custom_command(OUTPUT ${CMAKE_CURRENT_BINARY_DIR}/hccl_rs_superkernel_int8.o
            COMMAND ${BISHENG_CCACHE} ${CCE_DIR}/ccec -c -x cce -O2 ${CMAKE_CURRENT_SOURCE_DIR}/aiv_rs_superkernel.h -o ${CMAKE_CURRENT_BINARY_DIR}/hccl_rs_superkernel_int8.o --cce-aicore-arch=dav-c220-vec
            -DTILING_KEY_VAR=0UL -D__ASCENDC_ENABLE_SUPER_KERNEL__ -DASCENDC_DUMP=0 -DL2_CACHE_HINT -DCONST_TILING -DDETERMINISTIC_MODE=0 -DHCCL_DTYPE_INT8 -Dsk_reducescatter=sk_reducescatter_int8
            --cce-aicore-input-parameter-size=28000 --cce-aicore-only -mllvm -cce-aicore-function-stack-size=0x8000 -mllvm -cce-aicore-stack-size=0x8000
            -I${ASCEND_CANN_PACKAGE_PATH}/include/ascendc/basic_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/include/ascendc/basic_api/interface/
            -I${ASCEND_CANN_PACKAGE_PATH}/include/ascendc/include/adv_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/include/ascendc/highlevel_api
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/ascendc/include/basic_api/impl/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/asc/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/asc/impl/basic_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/asc/impl/simt_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/asc/impl/micro_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/include/basic_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/include/simt_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/include/micro_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/include/hccl/
            -I${CMAKE_CURRENT_SOURCE_DIR}/aiv_interface/
            -mllvm -cce-aicore-record-overflow=false -mllvm -cce-aicore-addr-transform -mllvm
            --cce-aicore-jump-expand=true -std=c++17 -fstack-protector-all
            WORKING_DIRECTORY ${CMAKE_CURRENT_BINARY_DIR}
            
    )

    add_custom_target(hccl_rs_superkernel_int16 ALL
        DEPENDS ${CMAKE_CURRENT_BINARY_DIR}/hccl_rs_superkernel_int16.o)
    add_custom_command(OUTPUT ${CMAKE_CURRENT_BINARY_DIR}/hccl_rs_superkernel_int16.o
            COMMAND ${BISHENG_CCACHE} ${CCE_DIR}/ccec -c -x cce -O2 ${CMAKE_CURRENT_SOURCE_DIR}/aiv_rs_superkernel.h -o ${CMAKE_CURRENT_BINARY_DIR}/hccl_rs_superkernel_int16.o --cce-aicore-arch=dav-c220-vec
            -DTILING_KEY_VAR=0UL -D__ASCENDC_ENABLE_SUPER_KERNEL__ -DASCENDC_DUMP=0 -DL2_CACHE_HINT -DCONST_TILING -DDETERMINISTIC_MODE=0 -DHCCL_DTYPE_INT16 -Dsk_reducescatter=sk_reducescatter_int16
            --cce-aicore-input-parameter-size=28000 --cce-aicore-only -mllvm -cce-aicore-function-stack-size=0x8000 -mllvm -cce-aicore-stack-size=0x8000
            -I${ASCEND_CANN_PACKAGE_PATH}/include/ascendc/basic_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/include/ascendc/basic_api/interface/
            -I${ASCEND_CANN_PACKAGE_PATH}/include/ascendc/include/adv_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/include/ascendc/highlevel_api
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/ascendc/include/basic_api/impl/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/asc/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/asc/impl/basic_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/asc/impl/simt_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/asc/impl/micro_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/include/basic_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/include/simt_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/include/micro_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/include/hccl/
            -I${CMAKE_CURRENT_SOURCE_DIR}/aiv_interface/
            -mllvm -cce-aicore-record-overflow=false -mllvm -cce-aicore-addr-transform -mllvm
            --cce-aicore-jump-expand=true -std=c++17 -fstack-protector-all
            WORKING_DIRECTORY ${CMAKE_CURRENT_BINARY_DIR}
            
    )

    add_custom_target(hccl_rs_superkernel_int32 ALL
        DEPENDS ${CMAKE_CURRENT_BINARY_DIR}/hccl_rs_superkernel_int32.o)
    add_custom_command(OUTPUT ${CMAKE_CURRENT_BINARY_DIR}/hccl_rs_superkernel_int32.o
            COMMAND ${BISHENG_CCACHE} ${CCE_DIR}/ccec -c -x cce -O2 ${CMAKE_CURRENT_SOURCE_DIR}/aiv_rs_superkernel.h -o ${CMAKE_CURRENT_BINARY_DIR}/hccl_rs_superkernel_int32.o --cce-aicore-arch=dav-c220-vec
            -DTILING_KEY_VAR=0UL -D__ASCENDC_ENABLE_SUPER_KERNEL__ -DASCENDC_DUMP=0 -DL2_CACHE_HINT -DCONST_TILING -DDETERMINISTIC_MODE=0 -DHCCL_DTYPE_INT32 -Dsk_reducescatter=sk_reducescatter_int32
            --cce-aicore-input-parameter-size=28000 --cce-aicore-only -mllvm -cce-aicore-function-stack-size=0x8000 -mllvm -cce-aicore-stack-size=0x8000
            -I${ASCEND_CANN_PACKAGE_PATH}/include/ascendc/basic_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/include/ascendc/basic_api/interface/
            -I${ASCEND_CANN_PACKAGE_PATH}/include/ascendc/include/adv_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/include/ascendc/highlevel_api
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/ascendc/include/basic_api/impl/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/asc/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/asc/impl/basic_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/asc/impl/simt_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/asc/impl/micro_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/include/basic_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/include/simt_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/include/micro_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/include/hccl/
            -I${CMAKE_CURRENT_SOURCE_DIR}/aiv_interface/
            -mllvm -cce-aicore-record-overflow=false -mllvm -cce-aicore-addr-transform -mllvm
            --cce-aicore-jump-expand=true -std=c++17 -fstack-protector-all
            WORKING_DIRECTORY ${CMAKE_CURRENT_BINARY_DIR}
            
    )

    add_custom_target(hccl_rs_superkernel_float16 ALL
        DEPENDS ${CMAKE_CURRENT_BINARY_DIR}/hccl_rs_superkernel_float16.o)
    add_custom_command(OUTPUT ${CMAKE_CURRENT_BINARY_DIR}/hccl_rs_superkernel_float16.o
            COMMAND ${BISHENG_CCACHE} ${CCE_DIR}/ccec -c -x cce -O2 ${CMAKE_CURRENT_SOURCE_DIR}/aiv_rs_superkernel.h -o ${CMAKE_CURRENT_BINARY_DIR}/hccl_rs_superkernel_float16.o --cce-aicore-arch=dav-c220-vec
            -DTILING_KEY_VAR=0UL -D__ASCENDC_ENABLE_SUPER_KERNEL__ -DASCENDC_DUMP=0 -DL2_CACHE_HINT -DCONST_TILING -DDETERMINISTIC_MODE=0 -DHCCL_DTYPE_FP16 -Dsk_reducescatter=sk_reducescatter_float16
            --cce-aicore-input-parameter-size=28000 --cce-aicore-only -mllvm -cce-aicore-function-stack-size=0x8000 -mllvm -cce-aicore-stack-size=0x8000
            -I${ASCEND_CANN_PACKAGE_PATH}/include/ascendc/basic_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/include/ascendc/basic_api/interface/
            -I${ASCEND_CANN_PACKAGE_PATH}/include/ascendc/include/adv_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/include/ascendc/highlevel_api
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/ascendc/include/basic_api/impl/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/asc/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/asc/impl/basic_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/asc/impl/simt_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/asc/impl/micro_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/include/basic_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/include/simt_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/include/micro_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/include/hccl/
            -I${CMAKE_CURRENT_SOURCE_DIR}/aiv_interface/
            -mllvm -cce-aicore-record-overflow=false -mllvm -cce-aicore-addr-transform -mllvm
            --cce-aicore-jump-expand=true -std=c++17 -fstack-protector-all
            WORKING_DIRECTORY ${CMAKE_CURRENT_BINARY_DIR}
            
    )

    add_custom_target(hccl_rs_superkernel_float32 ALL
        DEPENDS ${CMAKE_CURRENT_BINARY_DIR}/hccl_rs_superkernel_float32.o)
    add_custom_command(OUTPUT ${CMAKE_CURRENT_BINARY_DIR}/hccl_rs_superkernel_float32.o
            COMMAND ${BISHENG_CCACHE} ${CCE_DIR}/ccec -c -x cce -O2 ${CMAKE_CURRENT_SOURCE_DIR}/aiv_rs_superkernel.h -o ${CMAKE_CURRENT_BINARY_DIR}/hccl_rs_superkernel_float32.o --cce-aicore-arch=dav-c220-vec
            -DTILING_KEY_VAR=0UL -D__ASCENDC_ENABLE_SUPER_KERNEL__ -DASCENDC_DUMP=0 -DL2_CACHE_HINT -DCONST_TILING -DDETERMINISTIC_MODE=0 -DHCCL_DTYPE_FP32 -Dsk_reducescatter=sk_reducescatter_float32
            --cce-aicore-input-parameter-size=28000 --cce-aicore-only -mllvm -cce-aicore-function-stack-size=0x8000 -mllvm -cce-aicore-stack-size=0x8000
            -I${ASCEND_CANN_PACKAGE_PATH}/include/ascendc/basic_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/include/ascendc/basic_api/interface/
            -I${ASCEND_CANN_PACKAGE_PATH}/include/ascendc/include/adv_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/include/ascendc/highlevel_api
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/ascendc/include/basic_api/impl/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/asc/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/asc/impl/basic_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/asc/impl/simt_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/asc/impl/micro_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/include/basic_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/include/simt_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/include/micro_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/include/hccl/
            -I${CMAKE_CURRENT_SOURCE_DIR}/aiv_interface/
            -mllvm -cce-aicore-record-overflow=false -mllvm -cce-aicore-addr-transform -mllvm
            --cce-aicore-jump-expand=true -std=c++17 -fstack-protector-all
            WORKING_DIRECTORY ${CMAKE_CURRENT_BINARY_DIR}
            
    )


    add_custom_target(hccl_rs_superkernel_bfloat16 ALL
        DEPENDS ${CMAKE_CURRENT_BINARY_DIR}/hccl_rs_superkernel_bfloat16.o)
    add_custom_command(OUTPUT ${CMAKE_CURRENT_BINARY_DIR}/hccl_rs_superkernel_bfloat16.o
            COMMAND ${BISHENG_CCACHE} ${CCE_DIR}/ccec -c -x cce -O2 ${CMAKE_CURRENT_SOURCE_DIR}/aiv_rs_superkernel.h -o ${CMAKE_CURRENT_BINARY_DIR}/hccl_rs_superkernel_bfloat16.o --cce-aicore-arch=dav-c220-vec
            -DTILING_KEY_VAR=0UL -D__ASCENDC_ENABLE_SUPER_KERNEL__ -DASCENDC_DUMP=0 -DL2_CACHE_HINT -DCONST_TILING -DDETERMINISTIC_MODE=0 -DHCCL_DTYPE_BFP16 -Dsk_reducescatter=sk_reducescatter_bfloat16
            --cce-aicore-input-parameter-size=28000 --cce-aicore-only -mllvm -cce-aicore-function-stack-size=0x8000 -mllvm -cce-aicore-stack-size=0x8000
            -I${ASCEND_CANN_PACKAGE_PATH}/include/ascendc/basic_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/include/ascendc/basic_api/interface/
            -I${ASCEND_CANN_PACKAGE_PATH}/include/ascendc/include/adv_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/include/ascendc/highlevel_api
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/ascendc/include/basic_api/impl/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/asc/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/asc/impl/basic_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/asc/impl/simt_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/asc/impl/micro_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/include/basic_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/include/simt_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/include/micro_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/include/hccl/
            -I${CMAKE_CURRENT_SOURCE_DIR}/aiv_interface/
            -mllvm -cce-aicore-record-overflow=false -mllvm -cce-aicore-addr-transform -mllvm
            --cce-aicore-jump-expand=true -std=c++17 -fstack-protector-all
            WORKING_DIRECTORY ${CMAKE_CURRENT_BINARY_DIR}
            
    )

    add_custom_target(hccl_ar_superkernel_int8 ALL
        DEPENDS ${CMAKE_CURRENT_BINARY_DIR}/hccl_ar_superkernel_int8.o)
    add_custom_command(OUTPUT ${CMAKE_CURRENT_BINARY_DIR}/hccl_ar_superkernel_int8.o
            COMMAND ${BISHENG_CCACHE} ${CCE_DIR}/ccec -c -x cce -O2 ${CMAKE_CURRENT_SOURCE_DIR}/aiv_ar_superkernel.h -o ${CMAKE_CURRENT_BINARY_DIR}/hccl_ar_superkernel_int8.o --cce-aicore-arch=dav-c220-vec
            -DTILING_KEY_VAR=0UL -D__ASCENDC_ENABLE_SUPER_KERNEL__ -DASCENDC_DUMP=0 -DL2_CACHE_HINT -DCONST_TILING -DDETERMINISTIC_MODE=0 -DHCCL_DTYPE_INT8 -Dsk_allreduce=sk_allreduce_int8
            --cce-aicore-input-parameter-size=28000 --cce-aicore-only -mllvm -cce-aicore-function-stack-size=0x8000 -mllvm -cce-aicore-stack-size=0x8000
            -I${ASCEND_CANN_PACKAGE_PATH}/include/ascendc/basic_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/include/ascendc/basic_api/interface/
            -I${ASCEND_CANN_PACKAGE_PATH}/include/ascendc/include/adv_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/include/ascendc/highlevel_api
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/ascendc/include/basic_api/impl/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/asc/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/asc/impl/basic_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/asc/impl/simt_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/asc/impl/micro_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/include/basic_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/include/simt_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/include/micro_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/include/hccl/
            -I${CMAKE_CURRENT_SOURCE_DIR}/aiv_interface/
            -mllvm -cce-aicore-record-overflow=false -mllvm -cce-aicore-addr-transform -mllvm
            --cce-aicore-jump-expand=true -std=c++17 -fstack-protector-all
            WORKING_DIRECTORY ${CMAKE_CURRENT_BINARY_DIR}
            
    )

    add_custom_target(hccl_ar_superkernel_int16 ALL
        DEPENDS ${CMAKE_CURRENT_BINARY_DIR}/hccl_ar_superkernel_int16.o)
    add_custom_command(OUTPUT ${CMAKE_CURRENT_BINARY_DIR}/hccl_ar_superkernel_int16.o
            COMMAND ${BISHENG_CCACHE} ${CCE_DIR}/ccec -c -x cce -O2 ${CMAKE_CURRENT_SOURCE_DIR}/aiv_ar_superkernel.h -o ${CMAKE_CURRENT_BINARY_DIR}/hccl_ar_superkernel_int16.o --cce-aicore-arch=dav-c220-vec
            -DTILING_KEY_VAR=0UL -D__ASCENDC_ENABLE_SUPER_KERNEL__ -DASCENDC_DUMP=0 -DL2_CACHE_HINT -DCONST_TILING -DDETERMINISTIC_MODE=0 -DHCCL_DTYPE_INT16 -Dsk_allreduce=sk_allreduce_int16
            --cce-aicore-input-parameter-size=28000 --cce-aicore-only -mllvm -cce-aicore-function-stack-size=0x8000 -mllvm -cce-aicore-stack-size=0x8000
            -I${ASCEND_CANN_PACKAGE_PATH}/include/ascendc/basic_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/include/ascendc/basic_api/interface/
            -I${ASCEND_CANN_PACKAGE_PATH}/include/ascendc/include/adv_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/include/ascendc/highlevel_api
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/ascendc/include/basic_api/impl/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/asc/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/asc/impl/basic_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/asc/impl/simt_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/asc/impl/micro_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/include/basic_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/include/simt_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/include/micro_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/include/hccl/
            -I${CMAKE_CURRENT_SOURCE_DIR}/aiv_interface/
            -mllvm -cce-aicore-record-overflow=false -mllvm -cce-aicore-addr-transform -mllvm
            --cce-aicore-jump-expand=true -std=c++17 -fstack-protector-all
            WORKING_DIRECTORY ${CMAKE_CURRENT_BINARY_DIR}
            
    )

    add_custom_target(hccl_ar_superkernel_int32 ALL
        DEPENDS ${CMAKE_CURRENT_BINARY_DIR}/hccl_ar_superkernel_int32.o)
    add_custom_command(OUTPUT ${CMAKE_CURRENT_BINARY_DIR}/hccl_ar_superkernel_int32.o
            COMMAND ${BISHENG_CCACHE} ${CCE_DIR}/ccec -c -x cce -O2 ${CMAKE_CURRENT_SOURCE_DIR}/aiv_ar_superkernel.h -o ${CMAKE_CURRENT_BINARY_DIR}/hccl_ar_superkernel_int32.o --cce-aicore-arch=dav-c220-vec
            -DTILING_KEY_VAR=0UL -D__ASCENDC_ENABLE_SUPER_KERNEL__ -DASCENDC_DUMP=0 -DL2_CACHE_HINT -DCONST_TILING -DDETERMINISTIC_MODE=0 -DHCCL_DTYPE_INT32 -Dsk_allreduce=sk_allreduce_int32
            --cce-aicore-input-parameter-size=28000 --cce-aicore-only -mllvm -cce-aicore-function-stack-size=0x8000 -mllvm -cce-aicore-stack-size=0x8000
            -I${ASCEND_CANN_PACKAGE_PATH}/include/ascendc/basic_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/include/ascendc/basic_api/interface/
            -I${ASCEND_CANN_PACKAGE_PATH}/include/ascendc/include/adv_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/include/ascendc/highlevel_api
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/ascendc/include/basic_api/impl/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/asc/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/asc/impl/basic_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/asc/impl/simt_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/asc/impl/micro_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/include/basic_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/include/simt_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/include/micro_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/include/hccl/
            -I${CMAKE_CURRENT_SOURCE_DIR}/aiv_interface/
            -mllvm -cce-aicore-record-overflow=false -mllvm -cce-aicore-addr-transform -mllvm
            --cce-aicore-jump-expand=true -std=c++17 -fstack-protector-all
            WORKING_DIRECTORY ${CMAKE_CURRENT_BINARY_DIR}
            
    )

    add_custom_target(hccl_ar_superkernel_float16 ALL
        DEPENDS ${CMAKE_CURRENT_BINARY_DIR}/hccl_ar_superkernel_float16.o)
    add_custom_command(OUTPUT ${CMAKE_CURRENT_BINARY_DIR}/hccl_ar_superkernel_float16.o
            COMMAND ${BISHENG_CCACHE} ${CCE_DIR}/ccec -c -x cce -O2 ${CMAKE_CURRENT_SOURCE_DIR}/aiv_ar_superkernel.h -o ${CMAKE_CURRENT_BINARY_DIR}/hccl_ar_superkernel_float16.o --cce-aicore-arch=dav-c220-vec
            -DTILING_KEY_VAR=0UL -D__ASCENDC_ENABLE_SUPER_KERNEL__ -DASCENDC_DUMP=0 -DL2_CACHE_HINT -DCONST_TILING -DDETERMINISTIC_MODE=0 -DHCCL_DTYPE_FP16 -Dsk_allreduce=sk_allreduce_float16
            --cce-aicore-input-parameter-size=28000 --cce-aicore-only -mllvm -cce-aicore-function-stack-size=0x8000 -mllvm -cce-aicore-stack-size=0x8000
            -I${ASCEND_CANN_PACKAGE_PATH}/include/ascendc/basic_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/include/ascendc/basic_api/interface/
            -I${ASCEND_CANN_PACKAGE_PATH}/include/ascendc/include/adv_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/include/ascendc/highlevel_api
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/ascendc/include/basic_api/impl/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/asc/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/asc/impl/basic_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/asc/impl/simt_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/asc/impl/micro_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/include/basic_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/include/simt_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/include/micro_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/include/hccl/
            -I${CMAKE_CURRENT_SOURCE_DIR}/aiv_interface/
            -mllvm -cce-aicore-record-overflow=false -mllvm -cce-aicore-addr-transform -mllvm
            --cce-aicore-jump-expand=true -std=c++17 -fstack-protector-all
            WORKING_DIRECTORY ${CMAKE_CURRENT_BINARY_DIR}
            
    )

    add_custom_target(hccl_ar_superkernel_float32 ALL
        DEPENDS ${CMAKE_CURRENT_BINARY_DIR}/hccl_ar_superkernel_float32.o)
    add_custom_command(OUTPUT ${CMAKE_CURRENT_BINARY_DIR}/hccl_ar_superkernel_float32.o
            COMMAND ${BISHENG_CCACHE} ${CCE_DIR}/ccec -c -x cce -O2 ${CMAKE_CURRENT_SOURCE_DIR}/aiv_ar_superkernel.h -o ${CMAKE_CURRENT_BINARY_DIR}/hccl_ar_superkernel_float32.o --cce-aicore-arch=dav-c220-vec
            -DTILING_KEY_VAR=0UL -D__ASCENDC_ENABLE_SUPER_KERNEL__ -DASCENDC_DUMP=0 -DL2_CACHE_HINT -DCONST_TILING -DDETERMINISTIC_MODE=0 -DHCCL_DTYPE_FP32 -Dsk_allreduce=sk_allreduce_float32
            --cce-aicore-input-parameter-size=28000 --cce-aicore-only -mllvm -cce-aicore-function-stack-size=0x8000 -mllvm -cce-aicore-stack-size=0x8000
            -I${ASCEND_CANN_PACKAGE_PATH}/include/ascendc/basic_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/include/ascendc/basic_api/interface/
            -I${ASCEND_CANN_PACKAGE_PATH}/include/ascendc/include/adv_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/include/ascendc/highlevel_api
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/ascendc/include/basic_api/impl/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/asc/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/asc/impl/basic_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/asc/impl/simt_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/asc/impl/micro_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/include/basic_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/include/simt_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/include/micro_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/include/hccl/
            -I${CMAKE_CURRENT_SOURCE_DIR}/aiv_interface/
            -mllvm -cce-aicore-record-overflow=false -mllvm -cce-aicore-addr-transform -mllvm
            --cce-aicore-jump-expand=true -std=c++17 -fstack-protector-all
            WORKING_DIRECTORY ${CMAKE_CURRENT_BINARY_DIR}
            
    )

    add_custom_target(hccl_ar_superkernel_bfloat16 ALL
        DEPENDS ${CMAKE_CURRENT_BINARY_DIR}/hccl_ar_superkernel_bfloat16.o)
    add_custom_command(OUTPUT ${CMAKE_CURRENT_BINARY_DIR}/hccl_ar_superkernel_bfloat16.o
            COMMAND ${BISHENG_CCACHE} ${CCE_DIR}/ccec -c -x cce -O2 ${CMAKE_CURRENT_SOURCE_DIR}/aiv_ar_superkernel.h -o ${CMAKE_CURRENT_BINARY_DIR}/hccl_ar_superkernel_bfloat16.o --cce-aicore-arch=dav-c220-vec
            -DTILING_KEY_VAR=0UL -D__ASCENDC_ENABLE_SUPER_KERNEL__ -DASCENDC_DUMP=0 -DL2_CACHE_HINT -DCONST_TILING -DDETERMINISTIC_MODE=0 -DHCCL_DTYPE_BFP16 -Dsk_allreduce=sk_allreduce_bfloat16
            --cce-aicore-input-parameter-size=28000 --cce-aicore-only -mllvm -cce-aicore-function-stack-size=0x8000 -mllvm -cce-aicore-stack-size=0x8000
            -I${ASCEND_CANN_PACKAGE_PATH}/include/ascendc/basic_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/include/ascendc/basic_api/interface/
            -I${ASCEND_CANN_PACKAGE_PATH}/include/ascendc/include/adv_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/include/ascendc/highlevel_api
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/ascendc/include/basic_api/impl/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/asc/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/asc/impl/basic_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/asc/impl/simt_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/asc/impl/micro_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/include/basic_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/include/simt_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/include/micro_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/include/hccl/
            -I${CMAKE_CURRENT_SOURCE_DIR}/aiv_interface/
            -mllvm -cce-aicore-record-overflow=false -mllvm -cce-aicore-addr-transform -mllvm
            --cce-aicore-jump-expand=true -std=c++17 -fstack-protector-all
            WORKING_DIRECTORY ${CMAKE_CURRENT_BINARY_DIR}
            
    )

    add_custom_target(hccl_a2a_superkernel_int8 ALL
        DEPENDS ${CMAKE_CURRENT_BINARY_DIR}/hccl_a2a_superkernel_int8.o)
    add_custom_command(OUTPUT ${CMAKE_CURRENT_BINARY_DIR}/hccl_a2a_superkernel_int8.o
            COMMAND ${BISHENG_CCACHE} ${CCE_DIR}/ccec -c -x cce -O2 ${CMAKE_CURRENT_SOURCE_DIR}/aiv_a2a_superkernel.h -o ${CMAKE_CURRENT_BINARY_DIR}/hccl_a2a_superkernel_int8.o --cce-aicore-arch=dav-c220-vec
            -DTILING_KEY_VAR=0UL -D__ASCENDC_ENABLE_SUPER_KERNEL__ -DASCENDC_DUMP=0 -DL2_CACHE_HINT -DCONST_TILING -DDETERMINISTIC_MODE=0 -DHCCL_DTYPE_INT8 -Dsk_alltoall=sk_alltoall_int8
            --cce-aicore-input-parameter-size=28000 --cce-aicore-only -mllvm -cce-aicore-function-stack-size=0x8000 -mllvm -cce-aicore-stack-size=0x8000
            -I${ASCEND_CANN_PACKAGE_PATH}/include/ascendc/basic_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/include/ascendc/basic_api/interface/
            -I${ASCEND_CANN_PACKAGE_PATH}/include/ascendc/include/adv_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/include/ascendc/highlevel_api
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/ascendc/include/basic_api/impl/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/asc/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/asc/impl/basic_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/asc/impl/simt_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/asc/impl/micro_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/include/basic_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/include/simt_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/include/micro_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/include/hccl/
            -I${CMAKE_CURRENT_SOURCE_DIR}/aiv_interface/
            -mllvm -cce-aicore-record-overflow=false -mllvm -cce-aicore-addr-transform -mllvm
            --cce-aicore-jump-expand=true -std=c++17 -fstack-protector-all
            WORKING_DIRECTORY ${CMAKE_CURRENT_BINARY_DIR}
            
    )

    add_custom_target(hccl_a2a_superkernel_int16 ALL
        DEPENDS ${CMAKE_CURRENT_BINARY_DIR}/hccl_a2a_superkernel_int16.o)
    add_custom_command(OUTPUT ${CMAKE_CURRENT_BINARY_DIR}/hccl_a2a_superkernel_int16.o
            COMMAND ${BISHENG_CCACHE} ${CCE_DIR}/ccec -c -x cce -O2 ${CMAKE_CURRENT_SOURCE_DIR}/aiv_a2a_superkernel.h -o ${CMAKE_CURRENT_BINARY_DIR}/hccl_a2a_superkernel_int16.o --cce-aicore-arch=dav-c220-vec
            -DTILING_KEY_VAR=0UL -D__ASCENDC_ENABLE_SUPER_KERNEL__ -DASCENDC_DUMP=0 -DL2_CACHE_HINT -DCONST_TILING -DDETERMINISTIC_MODE=0 -DHCCL_DTYPE_INT16 -Dsk_alltoall=sk_alltoall_int16
            --cce-aicore-input-parameter-size=28000 --cce-aicore-only -mllvm -cce-aicore-function-stack-size=0x8000 -mllvm -cce-aicore-stack-size=0x8000
            -I${ASCEND_CANN_PACKAGE_PATH}/include/ascendc/basic_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/include/ascendc/basic_api/interface/
            -I${ASCEND_CANN_PACKAGE_PATH}/include/ascendc/include/adv_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/include/ascendc/highlevel_api
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/ascendc/include/basic_api/impl/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/asc/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/asc/impl/basic_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/asc/impl/simt_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/asc/impl/micro_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/include/basic_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/include/simt_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/include/micro_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/include/hccl/
            -I${CMAKE_CURRENT_SOURCE_DIR}/aiv_interface/
            -mllvm -cce-aicore-record-overflow=false -mllvm -cce-aicore-addr-transform -mllvm
            --cce-aicore-jump-expand=true -std=c++17 -fstack-protector-all
            WORKING_DIRECTORY ${CMAKE_CURRENT_BINARY_DIR}
            
    )

    add_custom_target(hccl_a2a_superkernel_int32 ALL
        DEPENDS ${CMAKE_CURRENT_BINARY_DIR}/hccl_a2a_superkernel_int32.o)
    add_custom_command(OUTPUT ${CMAKE_CURRENT_BINARY_DIR}/hccl_a2a_superkernel_int32.o
            COMMAND ${BISHENG_CCACHE} ${CCE_DIR}/ccec -c -x cce -O2 ${CMAKE_CURRENT_SOURCE_DIR}/aiv_a2a_superkernel.h -o ${CMAKE_CURRENT_BINARY_DIR}/hccl_a2a_superkernel_int32.o --cce-aicore-arch=dav-c220-vec
            -DTILING_KEY_VAR=0UL -D__ASCENDC_ENABLE_SUPER_KERNEL__ -DASCENDC_DUMP=0 -DL2_CACHE_HINT -DCONST_TILING -DDETERMINISTIC_MODE=0 -DHCCL_DTYPE_INT32 -Dsk_alltoall=sk_alltoall_int32
            --cce-aicore-input-parameter-size=28000 --cce-aicore-only -mllvm -cce-aicore-function-stack-size=0x8000 -mllvm -cce-aicore-stack-size=0x8000
            -I${ASCEND_CANN_PACKAGE_PATH}/include/ascendc/basic_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/include/ascendc/basic_api/interface/
            -I${ASCEND_CANN_PACKAGE_PATH}/include/ascendc/include/adv_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/include/ascendc/highlevel_api
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/ascendc/include/basic_api/impl/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/asc/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/asc/impl/basic_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/asc/impl/simt_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/asc/impl/micro_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/include/basic_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/include/simt_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/include/micro_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/include/hccl/
            -I${CMAKE_CURRENT_SOURCE_DIR}/aiv_interface/
            -mllvm -cce-aicore-record-overflow=false -mllvm -cce-aicore-addr-transform -mllvm
            --cce-aicore-jump-expand=true -std=c++17 -fstack-protector-all
            WORKING_DIRECTORY ${CMAKE_CURRENT_BINARY_DIR}
            
    )

    add_custom_target(hccl_a2a_superkernel_float16 ALL
        DEPENDS ${CMAKE_CURRENT_BINARY_DIR}/hccl_a2a_superkernel_float16.o)
    add_custom_command(OUTPUT ${CMAKE_CURRENT_BINARY_DIR}/hccl_a2a_superkernel_float16.o
            COMMAND ${BISHENG_CCACHE} ${CCE_DIR}/ccec -c -x cce -O2 ${CMAKE_CURRENT_SOURCE_DIR}/aiv_a2a_superkernel.h -o ${CMAKE_CURRENT_BINARY_DIR}/hccl_a2a_superkernel_float16.o --cce-aicore-arch=dav-c220-vec
            -DTILING_KEY_VAR=0UL -D__ASCENDC_ENABLE_SUPER_KERNEL__ -DASCENDC_DUMP=0 -DL2_CACHE_HINT -DCONST_TILING -DDETERMINISTIC_MODE=0 -DHCCL_DTYPE_FP16 -Dsk_alltoall=sk_alltoall_float16
            --cce-aicore-input-parameter-size=28000 --cce-aicore-only -mllvm -cce-aicore-function-stack-size=0x8000 -mllvm -cce-aicore-stack-size=0x8000
            -I${ASCEND_CANN_PACKAGE_PATH}/include/ascendc/basic_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/include/ascendc/basic_api/interface/
            -I${ASCEND_CANN_PACKAGE_PATH}/include/ascendc/include/adv_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/include/ascendc/highlevel_api
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/ascendc/include/basic_api/impl/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/asc/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/asc/impl/basic_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/asc/impl/simt_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/asc/impl/micro_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/include/basic_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/include/simt_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/include/micro_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/include/hccl/
            -I${CMAKE_CURRENT_SOURCE_DIR}/aiv_interface/
            -mllvm -cce-aicore-record-overflow=false -mllvm -cce-aicore-addr-transform -mllvm
            --cce-aicore-jump-expand=true -std=c++17 -fstack-protector-all
            WORKING_DIRECTORY ${CMAKE_CURRENT_BINARY_DIR}
            
    )

    add_custom_target(hccl_a2a_superkernel_float32 ALL
        DEPENDS ${CMAKE_CURRENT_BINARY_DIR}/hccl_a2a_superkernel_float32.o)
    add_custom_command(OUTPUT ${CMAKE_CURRENT_BINARY_DIR}/hccl_a2a_superkernel_float32.o
            COMMAND ${BISHENG_CCACHE} ${CCE_DIR}/ccec -c -x cce -O2 ${CMAKE_CURRENT_SOURCE_DIR}/aiv_a2a_superkernel.h -o ${CMAKE_CURRENT_BINARY_DIR}/hccl_a2a_superkernel_float32.o --cce-aicore-arch=dav-c220-vec
            -DTILING_KEY_VAR=0UL -D__ASCENDC_ENABLE_SUPER_KERNEL__ -DASCENDC_DUMP=0 -DL2_CACHE_HINT -DCONST_TILING -DDETERMINISTIC_MODE=0 -DHCCL_DTYPE_FP32 -Dsk_alltoall=sk_alltoall_float32
            --cce-aicore-input-parameter-size=28000 --cce-aicore-only -mllvm -cce-aicore-function-stack-size=0x8000 -mllvm -cce-aicore-stack-size=0x8000
            -I${ASCEND_CANN_PACKAGE_PATH}/include/ascendc/basic_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/include/ascendc/basic_api/interface/
            -I${ASCEND_CANN_PACKAGE_PATH}/include/ascendc/include/adv_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/include/ascendc/highlevel_api
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/ascendc/include/basic_api/impl/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/asc/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/asc/impl/basic_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/asc/impl/simt_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/asc/impl/micro_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/include/basic_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/include/simt_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/include/micro_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/include/hccl/
            -I${CMAKE_CURRENT_SOURCE_DIR}/aiv_interface/
            -mllvm -cce-aicore-record-overflow=false -mllvm -cce-aicore-addr-transform -mllvm
            --cce-aicore-jump-expand=true -std=c++17 -fstack-protector-all
            WORKING_DIRECTORY ${CMAKE_CURRENT_BINARY_DIR}
            
    )


    add_custom_target(hccl_a2a_superkernel_bfloat16 ALL
        DEPENDS ${CMAKE_CURRENT_BINARY_DIR}/hccl_a2a_superkernel_bfloat16.o)
    add_custom_command(OUTPUT ${CMAKE_CURRENT_BINARY_DIR}/hccl_a2a_superkernel_bfloat16.o
            COMMAND ${BISHENG_CCACHE} ${CCE_DIR}/ccec -c -x cce -O2 ${CMAKE_CURRENT_SOURCE_DIR}/aiv_a2a_superkernel.h -o ${CMAKE_CURRENT_BINARY_DIR}/hccl_a2a_superkernel_bfloat16.o --cce-aicore-arch=dav-c220-vec
            -DTILING_KEY_VAR=0UL -D__ASCENDC_ENABLE_SUPER_KERNEL__ -DASCENDC_DUMP=0 -DL2_CACHE_HINT -DCONST_TILING -DDETERMINISTIC_MODE=0 -DHCCL_DTYPE_BFP16 -Dsk_alltoall=sk_alltoall_bfloat16
            --cce-aicore-input-parameter-size=28000 --cce-aicore-only -mllvm -cce-aicore-function-stack-size=0x8000 -mllvm -cce-aicore-stack-size=0x8000
            -I${ASCEND_CANN_PACKAGE_PATH}/include/ascendc/basic_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/include/ascendc/basic_api/interface/
            -I${ASCEND_CANN_PACKAGE_PATH}/include/ascendc/include/adv_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/include/ascendc/highlevel_api
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/ascendc/include/basic_api/impl/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/asc/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/asc/impl/basic_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/asc/impl/simt_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/asc/impl/micro_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/include/basic_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/include/simt_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/include/micro_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/include/hccl/
            -I${CMAKE_CURRENT_SOURCE_DIR}/aiv_interface/
            -mllvm -cce-aicore-record-overflow=false -mllvm -cce-aicore-addr-transform -mllvm
            --cce-aicore-jump-expand=true -std=c++17 -fstack-protector-all
            WORKING_DIRECTORY ${CMAKE_CURRENT_BINARY_DIR}
            
    )

    add_custom_target(hccl_a2a_superkernel_uint8 ALL
        DEPENDS ${CMAKE_CURRENT_BINARY_DIR}/hccl_a2a_superkernel_uint8.o)
    add_custom_command(OUTPUT ${CMAKE_CURRENT_BINARY_DIR}/hccl_a2a_superkernel_uint8.o
            COMMAND ${BISHENG_CCACHE} ${CCE_DIR}/ccec -c -x cce -O2 ${CMAKE_CURRENT_SOURCE_DIR}/aiv_a2a_superkernel.h -o ${CMAKE_CURRENT_BINARY_DIR}/hccl_a2a_superkernel_uint8.o --cce-aicore-arch=dav-c220-vec
            -DTILING_KEY_VAR=0UL -D__ASCENDC_ENABLE_SUPER_KERNEL__ -DASCENDC_DUMP=0 -DL2_CACHE_HINT -DCONST_TILING -DDETERMINISTIC_MODE=0 -DHCCL_DTYPE_UINT8 -Dsk_alltoall=sk_alltoall_uint8
            --cce-aicore-input-parameter-size=28000 --cce-aicore-only -mllvm -cce-aicore-function-stack-size=0x8000 -mllvm -cce-aicore-stack-size=0x8000
            -I${ASCEND_CANN_PACKAGE_PATH}/include/ascendc/basic_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/include/ascendc/basic_api/interface/
            -I${ASCEND_CANN_PACKAGE_PATH}/include/ascendc/include/adv_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/include/ascendc/highlevel_api
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/ascendc/include/basic_api/impl/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/asc/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/asc/impl/basic_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/asc/impl/simt_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/asc/impl/micro_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/include/basic_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/include/simt_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/include/micro_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/include/hccl/
            -I${CMAKE_CURRENT_SOURCE_DIR}/aiv_interface/
            -mllvm -cce-aicore-record-overflow=false -mllvm -cce-aicore-addr-transform -mllvm
            --cce-aicore-jump-expand=true -std=c++17 -fstack-protector-all
            WORKING_DIRECTORY ${CMAKE_CURRENT_BINARY_DIR}
            
    )
    
    add_custom_target(hccl_a2a_superkernel_uint16 ALL
        DEPENDS ${CMAKE_CURRENT_BINARY_DIR}/hccl_a2a_superkernel_uint16.o)
    add_custom_command(OUTPUT ${CMAKE_CURRENT_BINARY_DIR}/hccl_a2a_superkernel_uint16.o
            COMMAND ${BISHENG_CCACHE} ${CCE_DIR}/ccec -c -x cce -O2 ${CMAKE_CURRENT_SOURCE_DIR}/aiv_a2a_superkernel.h -o ${CMAKE_CURRENT_BINARY_DIR}/hccl_a2a_superkernel_uint16.o --cce-aicore-arch=dav-c220-vec
            -DTILING_KEY_VAR=0UL -D__ASCENDC_ENABLE_SUPER_KERNEL__ -DASCENDC_DUMP=0 -DL2_CACHE_HINT -DCONST_TILING -DDETERMINISTIC_MODE=0 -DHCCL_DTYPE_UINT16 -Dsk_alltoall=sk_alltoall_uint16
            --cce-aicore-input-parameter-size=28000 --cce-aicore-only -mllvm -cce-aicore-function-stack-size=0x8000 -mllvm -cce-aicore-stack-size=0x8000
            -I${ASCEND_CANN_PACKAGE_PATH}/include/ascendc/basic_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/include/ascendc/basic_api/interface/
            -I${ASCEND_CANN_PACKAGE_PATH}/include/ascendc/include/adv_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/include/ascendc/highlevel_api
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/ascendc/include/basic_api/impl/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/asc/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/asc/impl/basic_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/asc/impl/simt_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/asc/impl/micro_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/include/basic_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/include/simt_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/include/micro_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/include/hccl/
            -I${CMAKE_CURRENT_SOURCE_DIR}/aiv_interface/
            -mllvm -cce-aicore-record-overflow=false -mllvm -cce-aicore-addr-transform -mllvm
            --cce-aicore-jump-expand=true -std=c++17 -fstack-protector-all
            WORKING_DIRECTORY ${CMAKE_CURRENT_BINARY_DIR}
            
    )

    add_custom_target(hccl_a2a_superkernel_uint32 ALL
        DEPENDS ${CMAKE_CURRENT_BINARY_DIR}/hccl_a2a_superkernel_uint32.o)
    add_custom_command(OUTPUT ${CMAKE_CURRENT_BINARY_DIR}/hccl_a2a_superkernel_uint32.o
            COMMAND ${BISHENG_CCACHE} ${CCE_DIR}/ccec -c -x cce -O2 ${CMAKE_CURRENT_SOURCE_DIR}/aiv_a2a_superkernel.h -o ${CMAKE_CURRENT_BINARY_DIR}/hccl_a2a_superkernel_uint32.o --cce-aicore-arch=dav-c220-vec
            -DTILING_KEY_VAR=0UL -D__ASCENDC_ENABLE_SUPER_KERNEL__ -DASCENDC_DUMP=0 -DL2_CACHE_HINT -DCONST_TILING -DDETERMINISTIC_MODE=0 -DHCCL_DTYPE_UINT32 -Dsk_alltoall=sk_alltoall_uint32
            --cce-aicore-input-parameter-size=28000 --cce-aicore-only -mllvm -cce-aicore-function-stack-size=0x8000 -mllvm -cce-aicore-stack-size=0x8000
            -I${ASCEND_CANN_PACKAGE_PATH}/include/ascendc/basic_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/include/ascendc/basic_api/interface/
            -I${ASCEND_CANN_PACKAGE_PATH}/include/ascendc/include/adv_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/include/ascendc/highlevel_api
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/ascendc/include/basic_api/impl/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/asc/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/asc/impl/basic_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/asc/impl/simt_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/asc/impl/micro_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/include/basic_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/include/simt_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/include/micro_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/include/hccl/
            -I${CMAKE_CURRENT_SOURCE_DIR}/aiv_interface/
            -mllvm -cce-aicore-record-overflow=false -mllvm -cce-aicore-addr-transform -mllvm
            --cce-aicore-jump-expand=true -std=c++17 -fstack-protector-all
            WORKING_DIRECTORY ${CMAKE_CURRENT_BINARY_DIR}
            
    )
    
    add_custom_target(hccl_sk_rs_deter ALL
        DEPENDS ${CMAKE_CURRENT_BINARY_DIR}/hccl_sk_rs_deter.o)
    add_custom_command(OUTPUT ${CMAKE_CURRENT_BINARY_DIR}/hccl_sk_rs_deter.o
            COMMAND ${BISHENG_CCACHE} ${CCE_DIR}/ccec -c -x cce -O2 ${CMAKE_CURRENT_SOURCE_DIR}/aiv_sk_rs_deter.h -o ${CMAKE_CURRENT_BINARY_DIR}/hccl_sk_rs_deter.o --cce-aicore-arch=dav-c220-vec
            -DTILING_KEY_VAR=0UL -D__ASCENDC_ENABLE_SUPER_KERNEL__ -DASCENDC_DUMP=0 -DL2_CACHE_HINT -DCONST_TILING -DDETERMINISTIC_MODE=0
            --cce-aicore-input-parameter-size=28000 --cce-aicore-only -mllvm -cce-aicore-function-stack-size=0x8000 -mllvm -cce-aicore-stack-size=0x8000
            -I${ASCEND_CANN_PACKAGE_PATH}/include/ascendc/basic_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/include/ascendc/basic_api/interface/
            -I${ASCEND_CANN_PACKAGE_PATH}/include/ascendc/include/adv_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/include/ascendc/highlevel_api
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/ascendc/include/basic_api/impl/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/asc/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/asc/impl/basic_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/asc/impl/simt_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/asc/impl/micro_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/include/basic_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/include/simt_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/include/micro_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/include/hccl/
            -I${CMAKE_CURRENT_SOURCE_DIR}/aiv_interface/
            -mllvm -cce-aicore-record-overflow=false -mllvm -cce-aicore-addr-transform -mllvm
            --cce-aicore-jump-expand=true -std=c++17 -fstack-protector-all
            WORKING_DIRECTORY ${CMAKE_CURRENT_BINARY_DIR}
            
    )
    
    add_custom_target(hccl_sk_ar_deter ALL
        DEPENDS ${CMAKE_CURRENT_BINARY_DIR}/hccl_sk_ar_deter.o)
    add_custom_command(OUTPUT ${CMAKE_CURRENT_BINARY_DIR}/hccl_sk_ar_deter.o
            COMMAND ${BISHENG_CCACHE} ${CCE_DIR}/ccec -c -x cce -O2 ${CMAKE_CURRENT_SOURCE_DIR}/aiv_sk_ar_deter.h -o ${CMAKE_CURRENT_BINARY_DIR}/hccl_sk_ar_deter.o --cce-aicore-arch=dav-c220-vec
            -DTILING_KEY_VAR=0UL -D__ASCENDC_ENABLE_SUPER_KERNEL__ -DASCENDC_DUMP=0 -DL2_CACHE_HINT -DCONST_TILING -DDETERMINISTIC_MODE=0
            --cce-aicore-input-parameter-size=28000 --cce-aicore-only -mllvm -cce-aicore-function-stack-size=0x8000 -mllvm -cce-aicore-stack-size=0x8000
            -I${ASCEND_CANN_PACKAGE_PATH}/include/ascendc/basic_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/include/ascendc/basic_api/interface/
            -I${ASCEND_CANN_PACKAGE_PATH}/include/ascendc/include/adv_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/include/ascendc/highlevel_api
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/ascendc/include/basic_api/impl/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/asc/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/asc/impl/basic_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/asc/impl/simt_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/asc/impl/micro_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/include/basic_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/include/simt_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/include/micro_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/include/hccl/
            -I${CMAKE_CURRENT_SOURCE_DIR}/aiv_interface/
            -mllvm -cce-aicore-record-overflow=false -mllvm -cce-aicore-addr-transform -mllvm
            --cce-aicore-jump-expand=true -std=c++17 -fstack-protector-all
            WORKING_DIRECTORY ${CMAKE_CURRENT_BINARY_DIR}
            
    )

    add_custom_target(hccl_sk_ar_crossnode ALL
        DEPENDS ${CMAKE_CURRENT_BINARY_DIR}/hccl_sk_ar_crossnode.o)
    add_custom_command(OUTPUT ${CMAKE_CURRENT_BINARY_DIR}/hccl_sk_ar_crossnode.o
            COMMAND ${BISHENG_CCACHE} ${CCE_DIR}/ccec -c -x cce -O2 ${CMAKE_CURRENT_SOURCE_DIR}/aiv_sk_ar_crossnode.h -o ${CMAKE_CURRENT_BINARY_DIR}/hccl_sk_ar_crossnode.o --cce-aicore-arch=dav-c220-vec
            -DTILING_KEY_VAR=0UL -D__ASCENDC_ENABLE_SUPER_KERNEL__ -DASCENDC_DUMP=0 -DL2_CACHE_HINT -DCONST_TILING -DDETERMINISTIC_MODE=0
            --cce-aicore-input-parameter-size=28000 --cce-aicore-only -mllvm -cce-aicore-function-stack-size=0x8000 -mllvm -cce-aicore-stack-size=0x8000
            -I${ASCEND_CANN_PACKAGE_PATH}/include/ascendc/basic_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/include/ascendc/basic_api/interface/
            -I${ASCEND_CANN_PACKAGE_PATH}/include/ascendc/include/adv_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/include/ascendc/highlevel_api
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/ascendc/include/basic_api/impl/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/asc/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/asc/impl/basic_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/asc/impl/simt_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/asc/impl/micro_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/include/basic_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/include/simt_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/include/micro_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/include/hccl/
            -I${CMAKE_CURRENT_SOURCE_DIR}/aiv_interface/
            -mllvm -cce-aicore-record-overflow=false -mllvm -cce-aicore-addr-transform -mllvm
            --cce-aicore-jump-expand=true -std=c++17 -fstack-protector-all
            WORKING_DIRECTORY ${CMAKE_CURRENT_BINARY_DIR}
    )
    
    add_custom_target(hccl_sk_rs_crossnode ALL
        DEPENDS ${CMAKE_CURRENT_BINARY_DIR}/hccl_sk_rs_crossnode.o)
    add_custom_command(OUTPUT ${CMAKE_CURRENT_BINARY_DIR}/hccl_sk_rs_crossnode.o
            COMMAND ${BISHENG_CCACHE} ${CCE_DIR}/ccec -c -x cce -O2 ${CMAKE_CURRENT_SOURCE_DIR}/aiv_sk_rs_crossnode.h -o ${CMAKE_CURRENT_BINARY_DIR}/hccl_sk_rs_crossnode.o --cce-aicore-arch=dav-c220-vec
            -DTILING_KEY_VAR=0UL -D__ASCENDC_ENABLE_SUPER_KERNEL__ -DASCENDC_DUMP=0 -DL2_CACHE_HINT -DCONST_TILING -DDETERMINISTIC_MODE=0
            --cce-aicore-input-parameter-size=28000 --cce-aicore-only -mllvm -cce-aicore-function-stack-size=0x8000 -mllvm -cce-aicore-stack-size=0x8000
            -I${ASCEND_CANN_PACKAGE_PATH}/include/ascendc/basic_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/include/ascendc/basic_api/interface/
            -I${ASCEND_CANN_PACKAGE_PATH}/include/ascendc/include/adv_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/include/ascendc/highlevel_api
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/ascendc/include/basic_api/impl/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/asc/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/asc/impl/basic_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/asc/impl/simt_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/asc/impl/micro_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/include/basic_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/include/simt_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/include/micro_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/include/hccl/
            -I${CMAKE_CURRENT_SOURCE_DIR}/aiv_interface/
            -mllvm -cce-aicore-record-overflow=false -mllvm -cce-aicore-addr-transform -mllvm
            --cce-aicore-jump-expand=true -std=c++17 -fstack-protector-all
            WORKING_DIRECTORY ${CMAKE_CURRENT_BINARY_DIR}
            
    )
    
    add_custom_target(hccl_sk_ag_crossnode ALL
        DEPENDS ${CMAKE_CURRENT_BINARY_DIR}/hccl_sk_ag_crossnode.o)
    add_custom_command(OUTPUT ${CMAKE_CURRENT_BINARY_DIR}/hccl_sk_ag_crossnode.o
            COMMAND ${BISHENG_CCACHE} ${CCE_DIR}/ccec -c -x cce -O2 ${CMAKE_CURRENT_SOURCE_DIR}/aiv_sk_ag_crossnode.h -o ${CMAKE_CURRENT_BINARY_DIR}/hccl_sk_ag_crossnode.o --cce-aicore-arch=dav-c220-vec
            -DTILING_KEY_VAR=0UL -D__ASCENDC_ENABLE_SUPER_KERNEL__ -DASCENDC_DUMP=0 -DL2_CACHE_HINT -DCONST_TILING -DDETERMINISTIC_MODE=0
            --cce-aicore-input-parameter-size=28000 --cce-aicore-only -mllvm -cce-aicore-function-stack-size=0x8000 -mllvm -cce-aicore-stack-size=0x8000
            -I${ASCEND_CANN_PACKAGE_PATH}/include/ascendc/basic_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/include/ascendc/basic_api/interface/
            -I${ASCEND_CANN_PACKAGE_PATH}/include/ascendc/include/adv_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/include/ascendc/highlevel_api
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/ascendc/include/basic_api/impl/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/asc/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/asc/impl/basic_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/asc/impl/simt_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/asc/impl/micro_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/include/basic_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/include/simt_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/include/micro_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/include/hccl/
            -I${CMAKE_CURRENT_SOURCE_DIR}/aiv_interface/
            -mllvm -cce-aicore-record-overflow=false -mllvm -cce-aicore-addr-transform -mllvm
            --cce-aicore-jump-expand=true -std=c++17 -fstack-protector-all
            WORKING_DIRECTORY ${CMAKE_CURRENT_BINARY_DIR}
            
    )
    
    add_custom_target(hccl_sk_a2a_crossnode ALL
        DEPENDS ${CMAKE_CURRENT_BINARY_DIR}/hccl_sk_a2a_crossnode.o)
    add_custom_command(OUTPUT ${CMAKE_CURRENT_BINARY_DIR}/hccl_sk_a2a_crossnode.o
            COMMAND ${BISHENG_CCACHE} ${CCE_DIR}/ccec -c -x cce -O2 ${CMAKE_CURRENT_SOURCE_DIR}/aiv_sk_a2a_crossnode.h -o ${CMAKE_CURRENT_BINARY_DIR}/hccl_sk_a2a_crossnode.o --cce-aicore-arch=dav-c220-vec
            -DTILING_KEY_VAR=0UL -D__ASCENDC_ENABLE_SUPER_KERNEL__ -DASCENDC_DUMP=0 -DL2_CACHE_HINT -DCONST_TILING -DDETERMINISTIC_MODE=0
            --cce-aicore-input-parameter-size=28000 --cce-aicore-only -mllvm -cce-aicore-function-stack-size=0x8000 -mllvm -cce-aicore-stack-size=0x8000
            -I${ASCEND_CANN_PACKAGE_PATH}/include/ascendc/basic_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/include/ascendc/basic_api/interface/
            -I${ASCEND_CANN_PACKAGE_PATH}/include/ascendc/include/adv_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/include/ascendc/highlevel_api
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/ascendc/include/basic_api/impl/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/asc/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/asc/impl/basic_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/asc/impl/simt_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/asc/impl/micro_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/include/basic_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/include/simt_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/include/micro_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/include/hccl/
            -I${CMAKE_CURRENT_SOURCE_DIR}/aiv_interface/
            -mllvm -cce-aicore-record-overflow=false -mllvm -cce-aicore-addr-transform -mllvm
            --cce-aicore-jump-expand=true -std=c++17 -fstack-protector-all
            WORKING_DIRECTORY ${CMAKE_CURRENT_BINARY_DIR}
            
    )
else()
    get_filename_component(CCE_DIR "${CMAKE_LINKER}" PATH)

    set(TILING_GEN_DIR ${CMAKE_BINARY_DIR}/asc/asc-devkit)

    add_custom_target(hccl_aiv_op_ascend910B
            COMMAND ${BISHENG_CCACHE} ${CCE_DIR}/ccec -c -x cce -O2 ${CMAKE_CURRENT_SOURCE_DIR}/aiv_communication.h -o ${CMAKE_CURRENT_BINARY_DIR}/hccl_aiv_op_ascend910B_tmp.o
            -DASCENDC_DUMP --cce-aicore-arch=dav-c220-vec
            --cce-aicore-input-parameter-size=28000 --cce-aicore-only -mllvm -cce-aicore-function-stack-size=0x8000 -mllvm -cce-aicore-dcci-insert-for-scalar=false
            -mllvm -cce-aicore-stack-size=0x8000
            -I${ASCEND_CANN_PACKAGE_PATH}/include/ascendc/basic_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/include/ascendc/basic_api/interface/
            -I${ASCEND_CANN_PACKAGE_PATH}/include/ascendc/include/adv_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/include/ascendc/highlevel_api
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/ascendc/include/basic_api/impl/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/asc/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/asc/impl/basic_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/asc/impl/simt_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/asc/impl/micro_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/include/basic_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/include/simt_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/include/micro_api/
            -I${TOP_DIR}/hcomm/include/hccl/
            -I${CMAKE_CURRENT_SOURCE_DIR}/aiv_interface/
            -I${TILING_GEN_DIR}
            -mllvm -cce-aicore-record-overflow=false -mllvm -cce-aicore-addr-transform -mllvm
            --cce-aicore-jump-expand=true -std=c++17 -fstack-protector-all -DONE_CORE_DUMP_SIZE=1024
            WORKING_DIRECTORY ${CMAKE_CURRENT_BINARY_DIR}
            DEPENDS kernel_tiling_headers
            COMMAND ${CCE_DIR}/ld.lld -m aicorelinux -Ttext=0 ${CMAKE_CURRENT_BINARY_DIR}/hccl_aiv_op_ascend910B_tmp.o -static -o ${CMAKE_CURRENT_BINARY_DIR}/hccl_aiv_op_ascend910B.o
            WORKING_DIRECTORY ${CMAKE_CURRENT_BINARY_DIR}
    )

        add_custom_target(hccl_ag_superkernel_int8
            COMMAND ${BISHENG_CCACHE} ${CCE_DIR}/ccec -c -x cce -O2 ${CMAKE_CURRENT_SOURCE_DIR}/aiv_ag_superkernel.h -o ${CMAKE_CURRENT_BINARY_DIR}/hccl_ag_superkernel_int8.o --cce-aicore-arch=dav-c220-vec
            -DTILING_KEY_VAR=0UL -D__ASCENDC_ENABLE_SUPER_KERNEL__ -DASCENDC_DUMP=0 -DL2_CACHE_HINT -DCONST_TILING -DDETERMINISTIC_MODE=0 -DHCCL_DTYPE_INT8 -Dsk_allgather=sk_allgather_int8
            --cce-aicore-input-parameter-size=28000 --cce-aicore-only -mllvm -cce-aicore-function-stack-size=0x8000 -mllvm -cce-aicore-stack-size=0x8000
            -I${ASCEND_CANN_PACKAGE_PATH}/include/ascendc/basic_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/include/ascendc/basic_api/interface/
            -I${ASCEND_CANN_PACKAGE_PATH}/include/ascendc/include/adv_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/include/ascendc/highlevel_api
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/ascendc/include/basic_api/impl/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/asc/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/asc/impl/basic_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/asc/impl/simt_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/asc/impl/micro_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/include/basic_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/include/simt_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/include/micro_api/
            -I${TOP_DIR}/hcomm/include/hccl/
            -I${CMAKE_CURRENT_SOURCE_DIR}/aiv_interface/
            -I${TILING_GEN_DIR}
            -mllvm -cce-aicore-record-overflow=false -mllvm -cce-aicore-addr-transform -mllvm
            --cce-aicore-jump-expand=true -std=c++17 -fstack-protector-all
            WORKING_DIRECTORY ${CMAKE_CURRENT_BINARY_DIR}
            DEPENDS kernel_tiling_headers
    )

    add_custom_target(hccl_ag_superkernel_int16
            COMMAND ${BISHENG_CCACHE} ${CCE_DIR}/ccec -c -x cce -O2 ${CMAKE_CURRENT_SOURCE_DIR}/aiv_ag_superkernel.h -o ${CMAKE_CURRENT_BINARY_DIR}/hccl_ag_superkernel_int16.o --cce-aicore-arch=dav-c220-vec
            -DTILING_KEY_VAR=0UL -D__ASCENDC_ENABLE_SUPER_KERNEL__ -DASCENDC_DUMP=0 -DL2_CACHE_HINT -DCONST_TILING -DDETERMINISTIC_MODE=0 -DHCCL_DTYPE_INT16 -Dsk_allgather=sk_allgather_int16
            --cce-aicore-input-parameter-size=28000 --cce-aicore-only -mllvm -cce-aicore-function-stack-size=0x8000 -mllvm -cce-aicore-stack-size=0x8000
            -I${ASCEND_CANN_PACKAGE_PATH}/include/ascendc/basic_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/include/ascendc/basic_api/interface/
            -I${ASCEND_CANN_PACKAGE_PATH}/include/ascendc/include/adv_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/include/ascendc/highlevel_api
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/ascendc/include/basic_api/impl/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/asc/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/asc/impl/basic_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/asc/impl/simt_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/asc/impl/micro_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/include/basic_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/include/simt_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/include/micro_api/
            -I${TOP_DIR}/hcomm/include/hccl/
            -I${CMAKE_CURRENT_SOURCE_DIR}/aiv_interface/
            -I${TILING_GEN_DIR}
            -mllvm -cce-aicore-record-overflow=false -mllvm -cce-aicore-addr-transform -mllvm
            --cce-aicore-jump-expand=true -std=c++17 -fstack-protector-all
            WORKING_DIRECTORY ${CMAKE_CURRENT_BINARY_DIR}
            DEPENDS kernel_tiling_headers
    )

    add_custom_target(hccl_ag_superkernel_int32
            COMMAND ${BISHENG_CCACHE} ${CCE_DIR}/ccec -c -x cce -O2 ${CMAKE_CURRENT_SOURCE_DIR}/aiv_ag_superkernel.h -o ${CMAKE_CURRENT_BINARY_DIR}/hccl_ag_superkernel_int32.o --cce-aicore-arch=dav-c220-vec
            -DTILING_KEY_VAR=0UL -D__ASCENDC_ENABLE_SUPER_KERNEL__ -DASCENDC_DUMP=0 -DL2_CACHE_HINT -DCONST_TILING -DDETERMINISTIC_MODE=0 -DHCCL_DTYPE_INT32 -Dsk_allgather=sk_allgather_int32
            --cce-aicore-input-parameter-size=28000 --cce-aicore-only -mllvm -cce-aicore-function-stack-size=0x8000 -mllvm -cce-aicore-stack-size=0x8000
            -I${ASCEND_CANN_PACKAGE_PATH}/include/ascendc/basic_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/include/ascendc/basic_api/interface/
            -I${ASCEND_CANN_PACKAGE_PATH}/include/ascendc/include/adv_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/include/ascendc/highlevel_api
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/ascendc/include/basic_api/impl/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/asc/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/asc/impl/basic_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/asc/impl/simt_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/asc/impl/micro_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/include/basic_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/include/simt_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/include/micro_api/
            -I${TOP_DIR}/hcomm/include/hccl/
            -I${CMAKE_CURRENT_SOURCE_DIR}/aiv_interface/
            -I${TILING_GEN_DIR}
            -mllvm -cce-aicore-record-overflow=false -mllvm -cce-aicore-addr-transform -mllvm
            --cce-aicore-jump-expand=true -std=c++17 -fstack-protector-all
            WORKING_DIRECTORY ${CMAKE_CURRENT_BINARY_DIR}
            DEPENDS kernel_tiling_headers
    )

    add_custom_target(hccl_ag_superkernel_float16
            COMMAND ${BISHENG_CCACHE} ${CCE_DIR}/ccec -c -x cce -O2 ${CMAKE_CURRENT_SOURCE_DIR}/aiv_ag_superkernel.h -o ${CMAKE_CURRENT_BINARY_DIR}/hccl_ag_superkernel_float16.o --cce-aicore-arch=dav-c220-vec
            -DTILING_KEY_VAR=0UL -D__ASCENDC_ENABLE_SUPER_KERNEL__ -DASCENDC_DUMP=0 -DL2_CACHE_HINT -DCONST_TILING -DDETERMINISTIC_MODE=0 -DHCCL_DTYPE_FP16 -Dsk_allgather=sk_allgather_float16
            --cce-aicore-input-parameter-size=28000 --cce-aicore-only -mllvm -cce-aicore-function-stack-size=0x8000 -mllvm -cce-aicore-stack-size=0x8000
            -I${ASCEND_CANN_PACKAGE_PATH}/include/ascendc/basic_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/include/ascendc/basic_api/interface/
            -I${ASCEND_CANN_PACKAGE_PATH}/include/ascendc/include/adv_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/include/ascendc/highlevel_api
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/ascendc/include/basic_api/impl/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/asc/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/asc/impl/basic_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/asc/impl/simt_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/asc/impl/micro_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/include/basic_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/include/simt_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/include/micro_api/
            -I${TOP_DIR}/hcomm/include/hccl/
            -I${CMAKE_CURRENT_SOURCE_DIR}/aiv_interface/
            -I${TILING_GEN_DIR}
            -mllvm -cce-aicore-record-overflow=false -mllvm -cce-aicore-addr-transform -mllvm
            --cce-aicore-jump-expand=true -std=c++17 -fstack-protector-all
            WORKING_DIRECTORY ${CMAKE_CURRENT_BINARY_DIR}
            DEPENDS kernel_tiling_headers
    )

    add_custom_target(hccl_ag_superkernel_float32
            COMMAND ${BISHENG_CCACHE} ${CCE_DIR}/ccec -c -x cce -O2 ${CMAKE_CURRENT_SOURCE_DIR}/aiv_ag_superkernel.h -o ${CMAKE_CURRENT_BINARY_DIR}/hccl_ag_superkernel_float32.o --cce-aicore-arch=dav-c220-vec
            -DTILING_KEY_VAR=0UL -D__ASCENDC_ENABLE_SUPER_KERNEL__ -DASCENDC_DUMP=0 -DL2_CACHE_HINT -DCONST_TILING -DDETERMINISTIC_MODE=0 -DHCCL_DTYPE_FP32 -Dsk_allgather=sk_allgather_float32
            --cce-aicore-input-parameter-size=28000 --cce-aicore-only -mllvm -cce-aicore-function-stack-size=0x8000 -mllvm -cce-aicore-stack-size=0x8000
            -I${ASCEND_CANN_PACKAGE_PATH}/include/ascendc/basic_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/include/ascendc/basic_api/interface/
            -I${ASCEND_CANN_PACKAGE_PATH}/include/ascendc/include/adv_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/include/ascendc/highlevel_api
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/ascendc/include/basic_api/impl/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/asc/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/asc/impl/basic_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/asc/impl/simt_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/asc/impl/micro_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/include/basic_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/include/simt_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/include/micro_api/
            -I${TOP_DIR}/hcomm/include/hccl/
            -I${CMAKE_CURRENT_SOURCE_DIR}/aiv_interface/
            -I${TILING_GEN_DIR}
            -mllvm -cce-aicore-record-overflow=false -mllvm -cce-aicore-addr-transform -mllvm
            --cce-aicore-jump-expand=true -std=c++17 -fstack-protector-all
            WORKING_DIRECTORY ${CMAKE_CURRENT_BINARY_DIR}
            DEPENDS kernel_tiling_headers
    )


    add_custom_target(hccl_ag_superkernel_bfloat16
            COMMAND ${BISHENG_CCACHE} ${CCE_DIR}/ccec -c -x cce -O2 ${CMAKE_CURRENT_SOURCE_DIR}/aiv_ag_superkernel.h -o ${CMAKE_CURRENT_BINARY_DIR}/hccl_ag_superkernel_bfloat16.o --cce-aicore-arch=dav-c220-vec
            -DTILING_KEY_VAR=0UL -D__ASCENDC_ENABLE_SUPER_KERNEL__ -DASCENDC_DUMP=0 -DL2_CACHE_HINT -DCONST_TILING -DDETERMINISTIC_MODE=0 -DHCCL_DTYPE_BFP16 -Dsk_allgather=sk_allgather_bfloat16
            --cce-aicore-input-parameter-size=28000 --cce-aicore-only -mllvm -cce-aicore-function-stack-size=0x8000 -mllvm -cce-aicore-stack-size=0x8000
            -I${ASCEND_CANN_PACKAGE_PATH}/include/ascendc/basic_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/include/ascendc/basic_api/interface/
            -I${ASCEND_CANN_PACKAGE_PATH}/include/ascendc/include/adv_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/include/ascendc/highlevel_api
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/ascendc/include/basic_api/impl/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/asc/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/asc/impl/basic_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/asc/impl/simt_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/asc/impl/micro_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/include/basic_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/include/simt_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/include/micro_api/
            -I${TOP_DIR}/hcomm/include/hccl/
            -I${CMAKE_CURRENT_SOURCE_DIR}/aiv_interface/
            -I${TILING_GEN_DIR}
            -mllvm -cce-aicore-record-overflow=false -mllvm -cce-aicore-addr-transform -mllvm
            --cce-aicore-jump-expand=true -std=c++17 -fstack-protector-all
            WORKING_DIRECTORY ${CMAKE_CURRENT_BINARY_DIR}
            DEPENDS kernel_tiling_headers
    )

    add_custom_target(hccl_ag_superkernel_uint8
            COMMAND ${BISHENG_CCACHE} ${CCE_DIR}/ccec -c -x cce -O2 ${CMAKE_CURRENT_SOURCE_DIR}/aiv_ag_superkernel.h -o ${CMAKE_CURRENT_BINARY_DIR}/hccl_ag_superkernel_uint8.o --cce-aicore-arch=dav-c220-vec
            -DTILING_KEY_VAR=0UL -D__ASCENDC_ENABLE_SUPER_KERNEL__ -DASCENDC_DUMP=0 -DL2_CACHE_HINT -DCONST_TILING -DDETERMINISTIC_MODE=0 -DHCCL_DTYPE_UINT8 -Dsk_allgather=sk_allgather_uint8
            --cce-aicore-input-parameter-size=28000 --cce-aicore-only -mllvm -cce-aicore-function-stack-size=0x8000 -mllvm -cce-aicore-stack-size=0x8000
            -I${ASCEND_CANN_PACKAGE_PATH}/include/ascendc/basic_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/include/ascendc/basic_api/interface/
            -I${ASCEND_CANN_PACKAGE_PATH}/include/ascendc/include/adv_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/include/ascendc/highlevel_api
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/ascendc/include/basic_api/impl/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/asc/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/asc/impl/basic_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/asc/impl/simt_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/asc/impl/micro_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/include/basic_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/include/simt_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/include/micro_api/
            -I${TOP_DIR}/hcomm/include/hccl/
            -I${CMAKE_CURRENT_SOURCE_DIR}/aiv_interface/
            -I${TILING_GEN_DIR}
            -mllvm -cce-aicore-record-overflow=false -mllvm -cce-aicore-addr-transform -mllvm
            --cce-aicore-jump-expand=true -std=c++17 -fstack-protector-all
            WORKING_DIRECTORY ${CMAKE_CURRENT_BINARY_DIR}
            DEPENDS kernel_tiling_headers
    )
    
    add_custom_target(hccl_ag_superkernel_uint16
            COMMAND ${BISHENG_CCACHE} ${CCE_DIR}/ccec -c -x cce -O2 ${CMAKE_CURRENT_SOURCE_DIR}/aiv_ag_superkernel.h -o ${CMAKE_CURRENT_BINARY_DIR}/hccl_ag_superkernel_uint16.o --cce-aicore-arch=dav-c220-vec
            -DTILING_KEY_VAR=0UL -D__ASCENDC_ENABLE_SUPER_KERNEL__ -DASCENDC_DUMP=0 -DL2_CACHE_HINT -DCONST_TILING -DDETERMINISTIC_MODE=0 -DHCCL_DTYPE_UINT16 -Dsk_allgather=sk_allgather_uint16
            --cce-aicore-input-parameter-size=28000 --cce-aicore-only -mllvm -cce-aicore-function-stack-size=0x8000 -mllvm -cce-aicore-stack-size=0x8000
            -I${ASCEND_CANN_PACKAGE_PATH}/include/ascendc/basic_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/include/ascendc/basic_api/interface/
            -I${ASCEND_CANN_PACKAGE_PATH}/include/ascendc/include/adv_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/include/ascendc/highlevel_api
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/ascendc/include/basic_api/impl/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/asc/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/asc/impl/basic_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/asc/impl/simt_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/asc/impl/micro_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/include/basic_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/include/simt_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/include/micro_api/
            -I${TOP_DIR}/hcomm/include/hccl/
            -I${CMAKE_CURRENT_SOURCE_DIR}/aiv_interface/
            -I${TILING_GEN_DIR}
            -mllvm -cce-aicore-record-overflow=false -mllvm -cce-aicore-addr-transform -mllvm
            --cce-aicore-jump-expand=true -std=c++17 -fstack-protector-all
            WORKING_DIRECTORY ${CMAKE_CURRENT_BINARY_DIR}
            DEPENDS kernel_tiling_headers
    )

    add_custom_target(hccl_ag_superkernel_uint32
            COMMAND ${BISHENG_CCACHE} ${CCE_DIR}/ccec -c -x cce -O2 ${CMAKE_CURRENT_SOURCE_DIR}/aiv_ag_superkernel.h -o ${CMAKE_CURRENT_BINARY_DIR}/hccl_ag_superkernel_uint32.o --cce-aicore-arch=dav-c220-vec
            -DTILING_KEY_VAR=0UL -D__ASCENDC_ENABLE_SUPER_KERNEL__ -DASCENDC_DUMP=0 -DL2_CACHE_HINT -DCONST_TILING -DDETERMINISTIC_MODE=0 -DHCCL_DTYPE_UINT32 -Dsk_allgather=sk_allgather_uint32
            --cce-aicore-input-parameter-size=28000 --cce-aicore-only -mllvm -cce-aicore-function-stack-size=0x8000 -mllvm -cce-aicore-stack-size=0x8000
            -I${ASCEND_CANN_PACKAGE_PATH}/include/ascendc/basic_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/include/ascendc/basic_api/interface/
            -I${ASCEND_CANN_PACKAGE_PATH}/include/ascendc/include/adv_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/include/ascendc/highlevel_api
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/ascendc/include/basic_api/impl/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/asc/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/asc/impl/basic_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/asc/impl/simt_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/asc/impl/micro_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/include/basic_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/include/simt_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/include/micro_api/
            -I${TOP_DIR}/hcomm/include/hccl/
            -I${CMAKE_CURRENT_SOURCE_DIR}/aiv_interface/
            -I${TILING_GEN_DIR}
            -mllvm -cce-aicore-record-overflow=false -mllvm -cce-aicore-addr-transform -mllvm
            --cce-aicore-jump-expand=true -std=c++17 -fstack-protector-all
            WORKING_DIRECTORY ${CMAKE_CURRENT_BINARY_DIR}
            DEPENDS kernel_tiling_headers
    )


    add_custom_target(hccl_rs_superkernel_int8
            COMMAND ${BISHENG_CCACHE} ${CCE_DIR}/ccec -c -x cce -O2 ${CMAKE_CURRENT_SOURCE_DIR}/aiv_rs_superkernel.h -o ${CMAKE_CURRENT_BINARY_DIR}/hccl_rs_superkernel_int8.o --cce-aicore-arch=dav-c220-vec
            -DTILING_KEY_VAR=0UL -D__ASCENDC_ENABLE_SUPER_KERNEL__ -DASCENDC_DUMP=0 -DL2_CACHE_HINT -DCONST_TILING -DDETERMINISTIC_MODE=0 -DHCCL_DTYPE_INT8 -Dsk_reducescatter=sk_reducescatter_int8
            --cce-aicore-input-parameter-size=28000 --cce-aicore-only -mllvm -cce-aicore-function-stack-size=0x8000 -mllvm -cce-aicore-stack-size=0x8000
            -I${ASCEND_CANN_PACKAGE_PATH}/include/ascendc/basic_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/include/ascendc/basic_api/interface/
            -I${ASCEND_CANN_PACKAGE_PATH}/include/ascendc/include/adv_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/include/ascendc/highlevel_api
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/ascendc/include/basic_api/impl/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/asc/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/asc/impl/basic_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/asc/impl/simt_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/asc/impl/micro_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/include/basic_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/include/simt_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/include/micro_api/
            -I${TOP_DIR}/hcomm/include/hccl/
            -I${CMAKE_CURRENT_SOURCE_DIR}/aiv_interface/
            -I${TILING_GEN_DIR}
            -mllvm -cce-aicore-record-overflow=false -mllvm -cce-aicore-addr-transform -mllvm
            --cce-aicore-jump-expand=true -std=c++17 -fstack-protector-all
            WORKING_DIRECTORY ${CMAKE_CURRENT_BINARY_DIR}
            DEPENDS kernel_tiling_headers
    )

    add_custom_target(hccl_rs_superkernel_int16
            COMMAND ${BISHENG_CCACHE} ${CCE_DIR}/ccec -c -x cce -O2 ${CMAKE_CURRENT_SOURCE_DIR}/aiv_rs_superkernel.h -o ${CMAKE_CURRENT_BINARY_DIR}/hccl_rs_superkernel_int16.o --cce-aicore-arch=dav-c220-vec
            -DTILING_KEY_VAR=0UL -D__ASCENDC_ENABLE_SUPER_KERNEL__ -DASCENDC_DUMP=0 -DL2_CACHE_HINT -DCONST_TILING -DDETERMINISTIC_MODE=0 -DHCCL_DTYPE_INT16 -Dsk_reducescatter=sk_reducescatter_int16
            --cce-aicore-input-parameter-size=28000 --cce-aicore-only -mllvm -cce-aicore-function-stack-size=0x8000 -mllvm -cce-aicore-stack-size=0x8000
            -I${ASCEND_CANN_PACKAGE_PATH}/include/ascendc/basic_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/include/ascendc/basic_api/interface/
            -I${ASCEND_CANN_PACKAGE_PATH}/include/ascendc/include/adv_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/include/ascendc/highlevel_api
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/ascendc/include/basic_api/impl/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/asc/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/asc/impl/basic_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/asc/impl/simt_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/asc/impl/micro_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/include/basic_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/include/simt_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/include/micro_api/
            -I${TOP_DIR}/hcomm/include/hccl/
            -I${CMAKE_CURRENT_SOURCE_DIR}/aiv_interface/
            -I${TILING_GEN_DIR}
            -mllvm -cce-aicore-record-overflow=false -mllvm -cce-aicore-addr-transform -mllvm
            --cce-aicore-jump-expand=true -std=c++17 -fstack-protector-all
            WORKING_DIRECTORY ${CMAKE_CURRENT_BINARY_DIR}
            DEPENDS kernel_tiling_headers
    )

    add_custom_target(hccl_rs_superkernel_int32
            COMMAND ${BISHENG_CCACHE} ${CCE_DIR}/ccec -c -x cce -O2 ${CMAKE_CURRENT_SOURCE_DIR}/aiv_rs_superkernel.h -o ${CMAKE_CURRENT_BINARY_DIR}/hccl_rs_superkernel_int32.o --cce-aicore-arch=dav-c220-vec
            -DTILING_KEY_VAR=0UL -D__ASCENDC_ENABLE_SUPER_KERNEL__ -DASCENDC_DUMP=0 -DL2_CACHE_HINT -DCONST_TILING -DDETERMINISTIC_MODE=0 -DHCCL_DTYPE_INT32 -Dsk_reducescatter=sk_reducescatter_int32
            --cce-aicore-input-parameter-size=28000 --cce-aicore-only -mllvm -cce-aicore-function-stack-size=0x8000 -mllvm -cce-aicore-stack-size=0x8000
            -I${ASCEND_CANN_PACKAGE_PATH}/include/ascendc/basic_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/include/ascendc/basic_api/interface/
            -I${ASCEND_CANN_PACKAGE_PATH}/include/ascendc/include/adv_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/include/ascendc/highlevel_api
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/ascendc/include/basic_api/impl/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/asc/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/asc/impl/basic_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/asc/impl/simt_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/asc/impl/micro_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/include/basic_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/include/simt_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/include/micro_api/
            -I${TOP_DIR}/hcomm/include/hccl/
            -I${CMAKE_CURRENT_SOURCE_DIR}/aiv_interface/
            -I${TILING_GEN_DIR}
            -mllvm -cce-aicore-record-overflow=false -mllvm -cce-aicore-addr-transform -mllvm
            --cce-aicore-jump-expand=true -std=c++17 -fstack-protector-all
            WORKING_DIRECTORY ${CMAKE_CURRENT_BINARY_DIR}
            DEPENDS kernel_tiling_headers
    )

    add_custom_target(hccl_rs_superkernel_float16
            COMMAND ${BISHENG_CCACHE} ${CCE_DIR}/ccec -c -x cce -O2 ${CMAKE_CURRENT_SOURCE_DIR}/aiv_rs_superkernel.h -o ${CMAKE_CURRENT_BINARY_DIR}/hccl_rs_superkernel_float16.o --cce-aicore-arch=dav-c220-vec
            -DTILING_KEY_VAR=0UL -D__ASCENDC_ENABLE_SUPER_KERNEL__ -DASCENDC_DUMP=0 -DL2_CACHE_HINT -DCONST_TILING -DDETERMINISTIC_MODE=0 -DHCCL_DTYPE_FP16 -Dsk_reducescatter=sk_reducescatter_float16
            --cce-aicore-input-parameter-size=28000 --cce-aicore-only -mllvm -cce-aicore-function-stack-size=0x8000 -mllvm -cce-aicore-stack-size=0x8000
            -I${ASCEND_CANN_PACKAGE_PATH}/include/ascendc/basic_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/include/ascendc/basic_api/interface/
            -I${ASCEND_CANN_PACKAGE_PATH}/include/ascendc/include/adv_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/include/ascendc/highlevel_api
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/ascendc/include/basic_api/impl/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/asc/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/asc/impl/basic_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/asc/impl/simt_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/asc/impl/micro_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/include/basic_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/include/simt_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/include/micro_api/
            -I${TOP_DIR}/hcomm/include/hccl/
            -I${CMAKE_CURRENT_SOURCE_DIR}/aiv_interface/
            -I${TILING_GEN_DIR}
            -mllvm -cce-aicore-record-overflow=false -mllvm -cce-aicore-addr-transform -mllvm
            --cce-aicore-jump-expand=true -std=c++17 -fstack-protector-all
            WORKING_DIRECTORY ${CMAKE_CURRENT_BINARY_DIR}
            DEPENDS kernel_tiling_headers
    )

    add_custom_target(hccl_rs_superkernel_float32
            COMMAND ${BISHENG_CCACHE} ${CCE_DIR}/ccec -c -x cce -O2 ${CMAKE_CURRENT_SOURCE_DIR}/aiv_rs_superkernel.h -o ${CMAKE_CURRENT_BINARY_DIR}/hccl_rs_superkernel_float32.o --cce-aicore-arch=dav-c220-vec
            -DTILING_KEY_VAR=0UL -D__ASCENDC_ENABLE_SUPER_KERNEL__ -DASCENDC_DUMP=0 -DL2_CACHE_HINT -DCONST_TILING -DDETERMINISTIC_MODE=0 -DHCCL_DTYPE_FP32 -Dsk_reducescatter=sk_reducescatter_float32
            --cce-aicore-input-parameter-size=28000 --cce-aicore-only -mllvm -cce-aicore-function-stack-size=0x8000 -mllvm -cce-aicore-stack-size=0x8000
            -I${ASCEND_CANN_PACKAGE_PATH}/include/ascendc/basic_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/include/ascendc/basic_api/interface/
            -I${ASCEND_CANN_PACKAGE_PATH}/include/ascendc/include/adv_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/include/ascendc/highlevel_api
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/ascendc/include/basic_api/impl/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/asc/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/asc/impl/basic_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/asc/impl/simt_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/asc/impl/micro_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/include/basic_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/include/simt_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/include/micro_api/
            -I${TOP_DIR}/hcomm/include/hccl/
            -I${CMAKE_CURRENT_SOURCE_DIR}/aiv_interface/
            -I${TILING_GEN_DIR}
            -mllvm -cce-aicore-record-overflow=false -mllvm -cce-aicore-addr-transform -mllvm
            --cce-aicore-jump-expand=true -std=c++17 -fstack-protector-all
            WORKING_DIRECTORY ${CMAKE_CURRENT_BINARY_DIR}
            DEPENDS kernel_tiling_headers
    )


    add_custom_target(hccl_rs_superkernel_bfloat16
            COMMAND ${BISHENG_CCACHE} ${CCE_DIR}/ccec -c -x cce -O2 ${CMAKE_CURRENT_SOURCE_DIR}/aiv_rs_superkernel.h -o ${CMAKE_CURRENT_BINARY_DIR}/hccl_rs_superkernel_bfloat16.o --cce-aicore-arch=dav-c220-vec
            -DTILING_KEY_VAR=0UL -D__ASCENDC_ENABLE_SUPER_KERNEL__ -DASCENDC_DUMP=0 -DL2_CACHE_HINT -DCONST_TILING -DDETERMINISTIC_MODE=0 -DHCCL_DTYPE_BFP16 -Dsk_reducescatter=sk_reducescatter_bfloat16
            --cce-aicore-input-parameter-size=28000 --cce-aicore-only -mllvm -cce-aicore-function-stack-size=0x8000 -mllvm -cce-aicore-stack-size=0x8000
            -I${ASCEND_CANN_PACKAGE_PATH}/include/ascendc/basic_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/include/ascendc/basic_api/interface/
            -I${ASCEND_CANN_PACKAGE_PATH}/include/ascendc/include/adv_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/include/ascendc/highlevel_api
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/ascendc/include/basic_api/impl/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/asc/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/asc/impl/basic_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/asc/impl/simt_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/asc/impl/micro_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/include/basic_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/include/simt_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/include/micro_api/
            -I${TOP_DIR}/hcomm/include/hccl/
            -I${CMAKE_CURRENT_SOURCE_DIR}/aiv_interface/
            -I${TILING_GEN_DIR}
            -mllvm -cce-aicore-record-overflow=false -mllvm -cce-aicore-addr-transform -mllvm
            --cce-aicore-jump-expand=true -std=c++17 -fstack-protector-all
            WORKING_DIRECTORY ${CMAKE_CURRENT_BINARY_DIR}
            DEPENDS kernel_tiling_headers
    )

    add_custom_target(hccl_ar_superkernel_int8
            COMMAND ${BISHENG_CCACHE} ${CCE_DIR}/ccec -c -x cce -O2 ${CMAKE_CURRENT_SOURCE_DIR}/aiv_ar_superkernel.h -o ${CMAKE_CURRENT_BINARY_DIR}/hccl_ar_superkernel_int8.o --cce-aicore-arch=dav-c220-vec
            -DTILING_KEY_VAR=0UL -D__ASCENDC_ENABLE_SUPER_KERNEL__ -DASCENDC_DUMP=0 -DL2_CACHE_HINT -DCONST_TILING -DDETERMINISTIC_MODE=0 -DHCCL_DTYPE_INT8 -Dsk_allreduce=sk_allreduce_int8
            --cce-aicore-input-parameter-size=28000 --cce-aicore-only -mllvm -cce-aicore-function-stack-size=0x8000 -mllvm -cce-aicore-stack-size=0x8000
            -I${ASCEND_CANN_PACKAGE_PATH}/include/ascendc/basic_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/include/ascendc/basic_api/interface/
            -I${ASCEND_CANN_PACKAGE_PATH}/include/ascendc/include/adv_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/include/ascendc/highlevel_api
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/ascendc/include/basic_api/impl/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/asc/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/asc/impl/basic_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/asc/impl/simt_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/asc/impl/micro_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/include/basic_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/include/simt_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/include/micro_api/
            -I${TOP_DIR}/hcomm/include/hccl/
            -I${CMAKE_CURRENT_SOURCE_DIR}/aiv_interface/
            -I${TILING_GEN_DIR}
            -mllvm -cce-aicore-record-overflow=false -mllvm -cce-aicore-addr-transform -mllvm
            --cce-aicore-jump-expand=true -std=c++17 -fstack-protector-all
            WORKING_DIRECTORY ${CMAKE_CURRENT_BINARY_DIR}
            DEPENDS kernel_tiling_headers
    )

    add_custom_target(hccl_ar_superkernel_int16
            COMMAND ${BISHENG_CCACHE} ${CCE_DIR}/ccec -c -x cce -O2 ${CMAKE_CURRENT_SOURCE_DIR}/aiv_ar_superkernel.h -o ${CMAKE_CURRENT_BINARY_DIR}/hccl_ar_superkernel_int16.o --cce-aicore-arch=dav-c220-vec
            -DTILING_KEY_VAR=0UL -D__ASCENDC_ENABLE_SUPER_KERNEL__ -DASCENDC_DUMP=0 -DL2_CACHE_HINT -DCONST_TILING -DDETERMINISTIC_MODE=0 -DHCCL_DTYPE_INT16 -Dsk_allreduce=sk_allreduce_int16
            --cce-aicore-input-parameter-size=28000 --cce-aicore-only -mllvm -cce-aicore-function-stack-size=0x8000 -mllvm -cce-aicore-stack-size=0x8000
            -I${ASCEND_CANN_PACKAGE_PATH}/include/ascendc/basic_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/include/ascendc/basic_api/interface/
            -I${ASCEND_CANN_PACKAGE_PATH}/include/ascendc/include/adv_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/include/ascendc/highlevel_api
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/ascendc/include/basic_api/impl/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/asc/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/asc/impl/basic_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/asc/impl/simt_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/asc/impl/micro_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/include/basic_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/include/simt_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/include/micro_api/
            -I${TOP_DIR}/hcomm/include/hccl/
            -I${CMAKE_CURRENT_SOURCE_DIR}/aiv_interface/
            -I${TILING_GEN_DIR}
            -mllvm -cce-aicore-record-overflow=false -mllvm -cce-aicore-addr-transform -mllvm
            --cce-aicore-jump-expand=true -std=c++17 -fstack-protector-all
            WORKING_DIRECTORY ${CMAKE_CURRENT_BINARY_DIR}
            DEPENDS kernel_tiling_headers
    )

    add_custom_target(hccl_ar_superkernel_int32
            COMMAND ${BISHENG_CCACHE} ${CCE_DIR}/ccec -c -x cce -O2 ${CMAKE_CURRENT_SOURCE_DIR}/aiv_ar_superkernel.h -o ${CMAKE_CURRENT_BINARY_DIR}/hccl_ar_superkernel_int32.o --cce-aicore-arch=dav-c220-vec
            -DTILING_KEY_VAR=0UL -D__ASCENDC_ENABLE_SUPER_KERNEL__ -DASCENDC_DUMP=0 -DL2_CACHE_HINT -DCONST_TILING -DDETERMINISTIC_MODE=0 -DHCCL_DTYPE_INT32 -Dsk_allreduce=sk_allreduce_int32
            --cce-aicore-input-parameter-size=28000 --cce-aicore-only -mllvm -cce-aicore-function-stack-size=0x8000 -mllvm -cce-aicore-stack-size=0x8000
            -I${ASCEND_CANN_PACKAGE_PATH}/include/ascendc/basic_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/include/ascendc/basic_api/interface/
            -I${ASCEND_CANN_PACKAGE_PATH}/include/ascendc/include/adv_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/include/ascendc/highlevel_api
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/ascendc/include/basic_api/impl/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/asc/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/asc/impl/basic_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/asc/impl/simt_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/asc/impl/micro_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/include/basic_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/include/simt_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/include/micro_api/
            -I${TOP_DIR}/hcomm/include/hccl/
            -I${CMAKE_CURRENT_SOURCE_DIR}/aiv_interface/
            -I${TILING_GEN_DIR}
            -mllvm -cce-aicore-record-overflow=false -mllvm -cce-aicore-addr-transform -mllvm
            --cce-aicore-jump-expand=true -std=c++17 -fstack-protector-all
            WORKING_DIRECTORY ${CMAKE_CURRENT_BINARY_DIR}
            DEPENDS kernel_tiling_headers
    )

    add_custom_target(hccl_ar_superkernel_float16
            COMMAND ${BISHENG_CCACHE} ${CCE_DIR}/ccec -c -x cce -O2 ${CMAKE_CURRENT_SOURCE_DIR}/aiv_ar_superkernel.h -o ${CMAKE_CURRENT_BINARY_DIR}/hccl_ar_superkernel_float16.o --cce-aicore-arch=dav-c220-vec
            -DTILING_KEY_VAR=0UL -D__ASCENDC_ENABLE_SUPER_KERNEL__ -DASCENDC_DUMP=0 -DL2_CACHE_HINT -DCONST_TILING -DDETERMINISTIC_MODE=0 -DHCCL_DTYPE_FP16 -Dsk_allreduce=sk_allreduce_float16
            --cce-aicore-input-parameter-size=28000 --cce-aicore-only -mllvm -cce-aicore-function-stack-size=0x8000 -mllvm -cce-aicore-stack-size=0x8000
            -I${ASCEND_CANN_PACKAGE_PATH}/include/ascendc/basic_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/include/ascendc/basic_api/interface/
            -I${ASCEND_CANN_PACKAGE_PATH}/include/ascendc/include/adv_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/include/ascendc/highlevel_api
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/ascendc/include/basic_api/impl/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/asc/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/asc/impl/basic_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/asc/impl/simt_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/asc/impl/micro_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/include/basic_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/include/simt_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/include/micro_api/
            -I${TOP_DIR}/hcomm/include/hccl/
            -I${CMAKE_CURRENT_SOURCE_DIR}/aiv_interface/
            -I${TILING_GEN_DIR}
            -mllvm -cce-aicore-record-overflow=false -mllvm -cce-aicore-addr-transform -mllvm
            --cce-aicore-jump-expand=true -std=c++17 -fstack-protector-all
            WORKING_DIRECTORY ${CMAKE_CURRENT_BINARY_DIR}
            DEPENDS kernel_tiling_headers
    )

    add_custom_target(hccl_ar_superkernel_float32
            COMMAND ${BISHENG_CCACHE} ${CCE_DIR}/ccec -c -x cce -O2 ${CMAKE_CURRENT_SOURCE_DIR}/aiv_ar_superkernel.h -o ${CMAKE_CURRENT_BINARY_DIR}/hccl_ar_superkernel_float32.o --cce-aicore-arch=dav-c220-vec
            -DTILING_KEY_VAR=0UL -D__ASCENDC_ENABLE_SUPER_KERNEL__ -DASCENDC_DUMP=0 -DL2_CACHE_HINT -DCONST_TILING -DDETERMINISTIC_MODE=0 -DHCCL_DTYPE_FP32 -Dsk_allreduce=sk_allreduce_float32
            --cce-aicore-input-parameter-size=28000 --cce-aicore-only -mllvm -cce-aicore-function-stack-size=0x8000 -mllvm -cce-aicore-stack-size=0x8000
            -I${ASCEND_CANN_PACKAGE_PATH}/include/ascendc/basic_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/include/ascendc/basic_api/interface/
            -I${ASCEND_CANN_PACKAGE_PATH}/include/ascendc/include/adv_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/include/ascendc/highlevel_api
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/ascendc/include/basic_api/impl/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/asc/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/asc/impl/basic_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/asc/impl/simt_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/asc/impl/micro_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/include/basic_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/include/simt_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/include/micro_api/
            -I${TOP_DIR}/hcomm/include/hccl/
            -I${CMAKE_CURRENT_SOURCE_DIR}/aiv_interface/
            -I${TILING_GEN_DIR}
            -mllvm -cce-aicore-record-overflow=false -mllvm -cce-aicore-addr-transform -mllvm
            --cce-aicore-jump-expand=true -std=c++17 -fstack-protector-all
            WORKING_DIRECTORY ${CMAKE_CURRENT_BINARY_DIR}
            DEPENDS kernel_tiling_headers
    )

    add_custom_target(hccl_ar_superkernel_bfloat16
            COMMAND ${BISHENG_CCACHE} ${CCE_DIR}/ccec -c -x cce -O2 ${CMAKE_CURRENT_SOURCE_DIR}/aiv_ar_superkernel.h -o ${CMAKE_CURRENT_BINARY_DIR}/hccl_ar_superkernel_bfloat16.o --cce-aicore-arch=dav-c220-vec
            -DTILING_KEY_VAR=0UL -D__ASCENDC_ENABLE_SUPER_KERNEL__ -DASCENDC_DUMP=0 -DL2_CACHE_HINT -DCONST_TILING -DDETERMINISTIC_MODE=0 -DHCCL_DTYPE_BFP16 -Dsk_allreduce=sk_allreduce_bfloat16
            --cce-aicore-input-parameter-size=28000 --cce-aicore-only -mllvm -cce-aicore-function-stack-size=0x8000 -mllvm -cce-aicore-stack-size=0x8000
            -I${ASCEND_CANN_PACKAGE_PATH}/include/ascendc/basic_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/include/ascendc/basic_api/interface/
            -I${ASCEND_CANN_PACKAGE_PATH}/include/ascendc/include/adv_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/include/ascendc/highlevel_api
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/ascendc/include/basic_api/impl/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/asc/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/asc/impl/basic_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/asc/impl/simt_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/asc/impl/micro_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/include/basic_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/include/simt_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/include/micro_api/
            -I${TOP_DIR}/hcomm/include/hccl/
            -I${CMAKE_CURRENT_SOURCE_DIR}/aiv_interface/
            -I${TILING_GEN_DIR}
            -mllvm -cce-aicore-record-overflow=false -mllvm -cce-aicore-addr-transform -mllvm
            --cce-aicore-jump-expand=true -std=c++17 -fstack-protector-all
            WORKING_DIRECTORY ${CMAKE_CURRENT_BINARY_DIR}
            DEPENDS kernel_tiling_headers
    )

        add_custom_target(hccl_a2a_superkernel_int8
            COMMAND ${BISHENG_CCACHE} ${CCE_DIR}/ccec -c -x cce -O2 ${CMAKE_CURRENT_SOURCE_DIR}/aiv_a2a_superkernel.h -o ${CMAKE_CURRENT_BINARY_DIR}/hccl_a2a_superkernel_int8.o --cce-aicore-arch=dav-c220-vec
            -DTILING_KEY_VAR=0UL -D__ASCENDC_ENABLE_SUPER_KERNEL__ -DASCENDC_DUMP=0 -DL2_CACHE_HINT -DCONST_TILING -DDETERMINISTIC_MODE=0 -DHCCL_DTYPE_INT8 -Dsk_alltoall=sk_alltoall_int8
            --cce-aicore-input-parameter-size=28000 --cce-aicore-only -mllvm -cce-aicore-function-stack-size=0x8000 -mllvm -cce-aicore-stack-size=0x8000
            -I${ASCEND_CANN_PACKAGE_PATH}/include/ascendc/basic_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/include/ascendc/basic_api/interface/
            -I${ASCEND_CANN_PACKAGE_PATH}/include/ascendc/include/adv_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/include/ascendc/highlevel_api
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/ascendc/include/basic_api/impl/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/asc/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/asc/impl/basic_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/asc/impl/simt_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/asc/impl/micro_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/include/basic_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/include/simt_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/include/micro_api/
            -I${TOP_DIR}/hcomm/include/hccl/
            -I${CMAKE_CURRENT_SOURCE_DIR}/aiv_interface/
            -I${TILING_GEN_DIR}
            -mllvm -cce-aicore-record-overflow=false -mllvm -cce-aicore-addr-transform -mllvm
            --cce-aicore-jump-expand=true -std=c++17 -fstack-protector-all
            WORKING_DIRECTORY ${CMAKE_CURRENT_BINARY_DIR}
            DEPENDS kernel_tiling_headers
    )

    add_custom_target(hccl_a2a_superkernel_int16
            COMMAND ${BISHENG_CCACHE} ${CCE_DIR}/ccec -c -x cce -O2 ${CMAKE_CURRENT_SOURCE_DIR}/aiv_a2a_superkernel.h -o ${CMAKE_CURRENT_BINARY_DIR}/hccl_a2a_superkernel_int16.o --cce-aicore-arch=dav-c220-vec
            -DTILING_KEY_VAR=0UL -D__ASCENDC_ENABLE_SUPER_KERNEL__ -DASCENDC_DUMP=0 -DL2_CACHE_HINT -DCONST_TILING -DDETERMINISTIC_MODE=0 -DHCCL_DTYPE_INT16 -Dsk_alltoall=sk_alltoall_int16
            --cce-aicore-input-parameter-size=28000 --cce-aicore-only -mllvm -cce-aicore-function-stack-size=0x8000 -mllvm -cce-aicore-stack-size=0x8000
            -I${ASCEND_CANN_PACKAGE_PATH}/include/ascendc/basic_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/include/ascendc/basic_api/interface/
            -I${ASCEND_CANN_PACKAGE_PATH}/include/ascendc/include/adv_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/include/ascendc/highlevel_api
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/ascendc/include/basic_api/impl/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/asc/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/asc/impl/basic_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/asc/impl/simt_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/asc/impl/micro_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/include/basic_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/include/simt_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/include/micro_api/
            -I${TOP_DIR}/hcomm/include/hccl/
            -I${CMAKE_CURRENT_SOURCE_DIR}/aiv_interface/
            -I${TILING_GEN_DIR}
            -mllvm -cce-aicore-record-overflow=false -mllvm -cce-aicore-addr-transform -mllvm
            --cce-aicore-jump-expand=true -std=c++17 -fstack-protector-all
            WORKING_DIRECTORY ${CMAKE_CURRENT_BINARY_DIR}
            DEPENDS kernel_tiling_headers
    )

    add_custom_target(hccl_a2a_superkernel_int32
            COMMAND ${BISHENG_CCACHE} ${CCE_DIR}/ccec -c -x cce -O2 ${CMAKE_CURRENT_SOURCE_DIR}/aiv_a2a_superkernel.h -o ${CMAKE_CURRENT_BINARY_DIR}/hccl_a2a_superkernel_int32.o --cce-aicore-arch=dav-c220-vec
            -DTILING_KEY_VAR=0UL -D__ASCENDC_ENABLE_SUPER_KERNEL__ -DASCENDC_DUMP=0 -DL2_CACHE_HINT -DCONST_TILING -DDETERMINISTIC_MODE=0 -DHCCL_DTYPE_INT32 -Dsk_alltoall=sk_alltoall_int32
            --cce-aicore-input-parameter-size=28000 --cce-aicore-only -mllvm -cce-aicore-function-stack-size=0x8000 -mllvm -cce-aicore-stack-size=0x8000
            -I${ASCEND_CANN_PACKAGE_PATH}/include/ascendc/basic_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/include/ascendc/basic_api/interface/
            -I${ASCEND_CANN_PACKAGE_PATH}/include/ascendc/include/adv_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/include/ascendc/highlevel_api
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/ascendc/include/basic_api/impl/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/asc/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/asc/impl/basic_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/asc/impl/simt_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/asc/impl/micro_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/include/basic_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/include/simt_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/include/micro_api/
            -I${TOP_DIR}/hcomm/include/hccl/
            -I${CMAKE_CURRENT_SOURCE_DIR}/aiv_interface/
            -I${TILING_GEN_DIR}
            -mllvm -cce-aicore-record-overflow=false -mllvm -cce-aicore-addr-transform -mllvm
            --cce-aicore-jump-expand=true -std=c++17 -fstack-protector-all
            WORKING_DIRECTORY ${CMAKE_CURRENT_BINARY_DIR}
            DEPENDS kernel_tiling_headers
    )

    add_custom_target(hccl_a2a_superkernel_float16
            COMMAND ${BISHENG_CCACHE} ${CCE_DIR}/ccec -c -x cce -O2 ${CMAKE_CURRENT_SOURCE_DIR}/aiv_a2a_superkernel.h -o ${CMAKE_CURRENT_BINARY_DIR}/hccl_a2a_superkernel_float16.o --cce-aicore-arch=dav-c220-vec
            -DTILING_KEY_VAR=0UL -D__ASCENDC_ENABLE_SUPER_KERNEL__ -DASCENDC_DUMP=0 -DL2_CACHE_HINT -DCONST_TILING -DDETERMINISTIC_MODE=0 -DHCCL_DTYPE_FP16 -Dsk_alltoall=sk_alltoall_float16
            --cce-aicore-input-parameter-size=28000 --cce-aicore-only -mllvm -cce-aicore-function-stack-size=0x8000 -mllvm -cce-aicore-stack-size=0x8000
            -I${ASCEND_CANN_PACKAGE_PATH}/include/ascendc/basic_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/include/ascendc/basic_api/interface/
            -I${ASCEND_CANN_PACKAGE_PATH}/include/ascendc/include/adv_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/include/ascendc/highlevel_api
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/ascendc/include/basic_api/impl/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/asc/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/asc/impl/basic_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/asc/impl/simt_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/asc/impl/micro_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/include/basic_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/include/simt_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/include/micro_api/
            -I${TOP_DIR}/hcomm/include/hccl/
            -I${CMAKE_CURRENT_SOURCE_DIR}/aiv_interface/
            -I${TILING_GEN_DIR}
            -mllvm -cce-aicore-record-overflow=false -mllvm -cce-aicore-addr-transform -mllvm
            --cce-aicore-jump-expand=true -std=c++17 -fstack-protector-all
            WORKING_DIRECTORY ${CMAKE_CURRENT_BINARY_DIR}
            DEPENDS kernel_tiling_headers
    )

    add_custom_target(hccl_a2a_superkernel_float32
            COMMAND ${BISHENG_CCACHE} ${CCE_DIR}/ccec -c -x cce -O2 ${CMAKE_CURRENT_SOURCE_DIR}/aiv_a2a_superkernel.h -o ${CMAKE_CURRENT_BINARY_DIR}/hccl_a2a_superkernel_float32.o --cce-aicore-arch=dav-c220-vec
            -DTILING_KEY_VAR=0UL -D__ASCENDC_ENABLE_SUPER_KERNEL__ -DASCENDC_DUMP=0 -DL2_CACHE_HINT -DCONST_TILING -DDETERMINISTIC_MODE=0 -DHCCL_DTYPE_FP32 -Dsk_alltoall=sk_alltoall_float32
            --cce-aicore-input-parameter-size=28000 --cce-aicore-only -mllvm -cce-aicore-function-stack-size=0x8000 -mllvm -cce-aicore-stack-size=0x8000
            -I${ASCEND_CANN_PACKAGE_PATH}/include/ascendc/basic_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/include/ascendc/basic_api/interface/
            -I${ASCEND_CANN_PACKAGE_PATH}/include/ascendc/include/adv_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/include/ascendc/highlevel_api
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/ascendc/include/basic_api/impl/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/asc/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/asc/impl/basic_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/asc/impl/simt_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/asc/impl/micro_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/include/basic_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/include/simt_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/include/micro_api/
            -I${TOP_DIR}/hcomm/include/hccl/
            -I${CMAKE_CURRENT_SOURCE_DIR}/aiv_interface/
            -I${TILING_GEN_DIR}
            -mllvm -cce-aicore-record-overflow=false -mllvm -cce-aicore-addr-transform -mllvm
            --cce-aicore-jump-expand=true -std=c++17 -fstack-protector-all
            WORKING_DIRECTORY ${CMAKE_CURRENT_BINARY_DIR}
            DEPENDS kernel_tiling_headers
    )


    add_custom_target(hccl_a2a_superkernel_bfloat16
            COMMAND ${BISHENG_CCACHE} ${CCE_DIR}/ccec -c -x cce -O2 ${CMAKE_CURRENT_SOURCE_DIR}/aiv_a2a_superkernel.h -o ${CMAKE_CURRENT_BINARY_DIR}/hccl_a2a_superkernel_bfloat16.o --cce-aicore-arch=dav-c220-vec
            -DTILING_KEY_VAR=0UL -D__ASCENDC_ENABLE_SUPER_KERNEL__ -DASCENDC_DUMP=0 -DL2_CACHE_HINT -DCONST_TILING -DDETERMINISTIC_MODE=0 -DHCCL_DTYPE_BFP16 -Dsk_alltoall=sk_alltoall_bfloat16
            --cce-aicore-input-parameter-size=28000 --cce-aicore-only -mllvm -cce-aicore-function-stack-size=0x8000 -mllvm -cce-aicore-stack-size=0x8000
            -I${ASCEND_CANN_PACKAGE_PATH}/include/ascendc/basic_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/include/ascendc/basic_api/interface/
            -I${ASCEND_CANN_PACKAGE_PATH}/include/ascendc/include/adv_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/include/ascendc/highlevel_api
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/ascendc/include/basic_api/impl/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/asc/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/asc/impl/basic_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/asc/impl/simt_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/asc/impl/micro_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/include/basic_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/include/simt_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/include/micro_api/
            -I${TOP_DIR}/hcomm/include/hccl/
            -I${CMAKE_CURRENT_SOURCE_DIR}/aiv_interface/
            -I${TILING_GEN_DIR}
            -mllvm -cce-aicore-record-overflow=false -mllvm -cce-aicore-addr-transform -mllvm
            --cce-aicore-jump-expand=true -std=c++17 -fstack-protector-all
            WORKING_DIRECTORY ${CMAKE_CURRENT_BINARY_DIR}
            DEPENDS kernel_tiling_headers
    )

    add_custom_target(hccl_a2a_superkernel_uint8
            COMMAND ${BISHENG_CCACHE} ${CCE_DIR}/ccec -c -x cce -O2 ${CMAKE_CURRENT_SOURCE_DIR}/aiv_a2a_superkernel.h -o ${CMAKE_CURRENT_BINARY_DIR}/hccl_a2a_superkernel_uint8.o --cce-aicore-arch=dav-c220-vec
            -DTILING_KEY_VAR=0UL -D__ASCENDC_ENABLE_SUPER_KERNEL__ -DASCENDC_DUMP=0 -DL2_CACHE_HINT -DCONST_TILING -DDETERMINISTIC_MODE=0 -DHCCL_DTYPE_UINT8 -Dsk_alltoall=sk_alltoall_uint8
            --cce-aicore-input-parameter-size=28000 --cce-aicore-only -mllvm -cce-aicore-function-stack-size=0x8000 -mllvm -cce-aicore-stack-size=0x8000
            -I${ASCEND_CANN_PACKAGE_PATH}/include/ascendc/basic_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/include/ascendc/basic_api/interface/
            -I${ASCEND_CANN_PACKAGE_PATH}/include/ascendc/include/adv_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/include/ascendc/highlevel_api
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/ascendc/include/basic_api/impl/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/asc/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/asc/impl/basic_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/asc/impl/simt_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/asc/impl/micro_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/include/basic_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/include/simt_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/include/micro_api/
            -I${TOP_DIR}/hcomm/include/hccl/
            -I${CMAKE_CURRENT_SOURCE_DIR}/aiv_interface/
            -I${TILING_GEN_DIR}
            -mllvm -cce-aicore-record-overflow=false -mllvm -cce-aicore-addr-transform -mllvm
            --cce-aicore-jump-expand=true -std=c++17 -fstack-protector-all
            WORKING_DIRECTORY ${CMAKE_CURRENT_BINARY_DIR}
            DEPENDS kernel_tiling_headers
    )
    
    add_custom_target(hccl_a2a_superkernel_uint16
            COMMAND ${BISHENG_CCACHE} ${CCE_DIR}/ccec -c -x cce -O2 ${CMAKE_CURRENT_SOURCE_DIR}/aiv_a2a_superkernel.h -o ${CMAKE_CURRENT_BINARY_DIR}/hccl_a2a_superkernel_uint16.o --cce-aicore-arch=dav-c220-vec
            -DTILING_KEY_VAR=0UL -D__ASCENDC_ENABLE_SUPER_KERNEL__ -DASCENDC_DUMP=0 -DL2_CACHE_HINT -DCONST_TILING -DDETERMINISTIC_MODE=0 -DHCCL_DTYPE_UINT16 -Dsk_alltoall=sk_alltoall_uint16
            --cce-aicore-input-parameter-size=28000 --cce-aicore-only -mllvm -cce-aicore-function-stack-size=0x8000 -mllvm -cce-aicore-stack-size=0x8000
            -I${ASCEND_CANN_PACKAGE_PATH}/include/ascendc/basic_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/include/ascendc/basic_api/interface/
            -I${ASCEND_CANN_PACKAGE_PATH}/include/ascendc/include/adv_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/include/ascendc/highlevel_api
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/ascendc/include/basic_api/impl/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/asc/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/asc/impl/basic_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/asc/impl/simt_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/asc/impl/micro_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/include/basic_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/include/simt_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/include/micro_api/
            -I${TOP_DIR}/hcomm/include/hccl/
            -I${CMAKE_CURRENT_SOURCE_DIR}/aiv_interface/
            -I${TILING_GEN_DIR}
            -mllvm -cce-aicore-record-overflow=false -mllvm -cce-aicore-addr-transform -mllvm
            --cce-aicore-jump-expand=true -std=c++17 -fstack-protector-all
            WORKING_DIRECTORY ${CMAKE_CURRENT_BINARY_DIR}
            DEPENDS kernel_tiling_headers
    )

    add_custom_target(hccl_a2a_superkernel_uint32
            COMMAND ${BISHENG_CCACHE} ${CCE_DIR}/ccec -c -x cce -O2 ${CMAKE_CURRENT_SOURCE_DIR}/aiv_a2a_superkernel.h -o ${CMAKE_CURRENT_BINARY_DIR}/hccl_a2a_superkernel_uint32.o --cce-aicore-arch=dav-c220-vec
            -DTILING_KEY_VAR=0UL -D__ASCENDC_ENABLE_SUPER_KERNEL__ -DASCENDC_DUMP=0 -DL2_CACHE_HINT -DCONST_TILING -DDETERMINISTIC_MODE=0 -DHCCL_DTYPE_UINT32 -Dsk_alltoall=sk_alltoall_uint32
            --cce-aicore-input-parameter-size=28000 --cce-aicore-only -mllvm -cce-aicore-function-stack-size=0x8000 -mllvm -cce-aicore-stack-size=0x8000
            -I${ASCEND_CANN_PACKAGE_PATH}/include/ascendc/basic_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/include/ascendc/basic_api/interface/
            -I${ASCEND_CANN_PACKAGE_PATH}/include/ascendc/include/adv_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/include/ascendc/highlevel_api
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/ascendc/include/basic_api/impl/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/asc/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/asc/impl/basic_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/asc/impl/simt_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/asc/impl/micro_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/include/basic_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/include/simt_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/include/micro_api/
            -I${TOP_DIR}/hcomm/include/hccl/
            -I${CMAKE_CURRENT_SOURCE_DIR}/aiv_interface/
            -I${TILING_GEN_DIR}
            -mllvm -cce-aicore-record-overflow=false -mllvm -cce-aicore-addr-transform -mllvm
            --cce-aicore-jump-expand=true -std=c++17 -fstack-protector-all
            WORKING_DIRECTORY ${CMAKE_CURRENT_BINARY_DIR}
            DEPENDS kernel_tiling_headers
   )
   
   add_custom_target(hccl_sk_rs_deter
            COMMAND ${BISHENG_CCACHE} ${CCE_DIR}/ccec -c -x cce -O2 ${CMAKE_CURRENT_SOURCE_DIR}/aiv_sk_rs_deter.h -o ${CMAKE_CURRENT_BINARY_DIR}/hccl_sk_rs_deter.o --cce-aicore-arch=dav-c220-vec
            -DTILING_KEY_VAR=0UL -D__ASCENDC_ENABLE_SUPER_KERNEL__ -DASCENDC_DUMP=0 -DL2_CACHE_HINT -DCONST_TILING -DDETERMINISTIC_MODE=0
            --cce-aicore-input-parameter-size=28000 --cce-aicore-only -mllvm -cce-aicore-function-stack-size=0x8000 -mllvm -cce-aicore-stack-size=0x8000
            -I${ASCEND_CANN_PACKAGE_PATH}/include/ascendc/basic_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/include/ascendc/basic_api/interface/
            -I${ASCEND_CANN_PACKAGE_PATH}/include/ascendc/include/adv_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/include/ascendc/highlevel_api
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/ascendc/include/basic_api/impl/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/asc/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/asc/impl/basic_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/asc/impl/simt_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/asc/impl/micro_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/include/basic_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/include/simt_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/include/micro_api/
            -I${TOP_DIR}/hcomm/include/hccl/
            -I${CMAKE_CURRENT_SOURCE_DIR}/aiv_interface/
            -I${TILING_GEN_DIR}
            -mllvm -cce-aicore-record-overflow=false -mllvm -cce-aicore-addr-transform -mllvm
            --cce-aicore-jump-expand=true -std=c++17 -fstack-protector-all
            WORKING_DIRECTORY ${CMAKE_CURRENT_BINARY_DIR}
            DEPENDS kernel_tiling_headers
   )
   
   add_custom_target(hccl_sk_ar_deter
            COMMAND ${BISHENG_CCACHE} ${CCE_DIR}/ccec -c -x cce -O2 ${CMAKE_CURRENT_SOURCE_DIR}/aiv_sk_ar_deter.h -o ${CMAKE_CURRENT_BINARY_DIR}/hccl_sk_ar_deter.o --cce-aicore-arch=dav-c220-vec
            -DTILING_KEY_VAR=0UL -D__ASCENDC_ENABLE_SUPER_KERNEL__ -DASCENDC_DUMP=0 -DL2_CACHE_HINT -DCONST_TILING -DDETERMINISTIC_MODE=0
            --cce-aicore-input-parameter-size=28000 --cce-aicore-only -mllvm -cce-aicore-function-stack-size=0x8000 -mllvm -cce-aicore-stack-size=0x8000
            -I${ASCEND_CANN_PACKAGE_PATH}/include/ascendc/basic_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/include/ascendc/basic_api/interface/
            -I${ASCEND_CANN_PACKAGE_PATH}/include/ascendc/include/adv_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/include/ascendc/highlevel_api
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/ascendc/include/basic_api/impl/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/asc/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/asc/impl/basic_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/asc/impl/simt_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/asc/impl/micro_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/include/basic_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/include/simt_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/include/micro_api/
            -I${TOP_DIR}/hcomm/include/hccl/
            -I${CMAKE_CURRENT_SOURCE_DIR}/aiv_interface/
            -I${TILING_GEN_DIR}
            -mllvm -cce-aicore-record-overflow=false -mllvm -cce-aicore-addr-transform -mllvm
            --cce-aicore-jump-expand=true -std=c++17 -fstack-protector-all
            WORKING_DIRECTORY ${CMAKE_CURRENT_BINARY_DIR}
            DEPENDS kernel_tiling_headers
   )

   add_custom_target(hccl_sk_ar_crossnode
            COMMAND ${BISHENG_CCACHE} ${CCE_DIR}/ccec -c -x cce -O2 ${CMAKE_CURRENT_SOURCE_DIR}/aiv_sk_ar_crossnode.h -o ${CMAKE_CURRENT_BINARY_DIR}/hccl_sk_ar_crossnode.o --cce-aicore-arch=dav-c220-vec
            -DTILING_KEY_VAR=0UL -D__ASCENDC_ENABLE_SUPER_KERNEL__ -DASCENDC_DUMP=0 -DL2_CACHE_HINT -DCONST_TILING -DDETERMINISTIC_MODE=0
            --cce-aicore-input-parameter-size=28000 --cce-aicore-only -mllvm -cce-aicore-function-stack-size=0x8000 -mllvm -cce-aicore-stack-size=0x8000
            -I${ASCEND_CANN_PACKAGE_PATH}/include/ascendc/basic_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/include/ascendc/basic_api/interface/
            -I${ASCEND_CANN_PACKAGE_PATH}/include/ascendc/include/adv_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/include/ascendc/highlevel_api
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/ascendc/include/basic_api/impl/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/asc/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/asc/impl/basic_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/asc/impl/simt_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/asc/impl/micro_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/include/basic_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/include/simt_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/include/micro_api/
            -I${TOP_DIR}/hcomm/include/hccl/
            -I${CMAKE_CURRENT_SOURCE_DIR}/aiv_interface/
            -I${TILING_GEN_DIR}
            -mllvm -cce-aicore-record-overflow=false -mllvm -cce-aicore-addr-transform -mllvm
            --cce-aicore-jump-expand=true -std=c++17 -fstack-protector-all
            WORKING_DIRECTORY ${CMAKE_CURRENT_BINARY_DIR}
            DEPENDS kernel_tiling_headers
   )
   
   add_custom_target(hccl_sk_rs_crossnode
            COMMAND ${BISHENG_CCACHE} ${CCE_DIR}/ccec -c -x cce -O2 ${CMAKE_CURRENT_SOURCE_DIR}/aiv_sk_rs_crossnode.h -o ${CMAKE_CURRENT_BINARY_DIR}/hccl_sk_rs_crossnode.o --cce-aicore-arch=dav-c220-vec
            -DTILING_KEY_VAR=0UL -D__ASCENDC_ENABLE_SUPER_KERNEL__ -DASCENDC_DUMP=0 -DL2_CACHE_HINT -DCONST_TILING -DDETERMINISTIC_MODE=0
            --cce-aicore-input-parameter-size=28000 --cce-aicore-only -mllvm -cce-aicore-function-stack-size=0x8000 -mllvm -cce-aicore-stack-size=0x8000
            -I${ASCEND_CANN_PACKAGE_PATH}/include/ascendc/basic_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/include/ascendc/basic_api/interface/
            -I${ASCEND_CANN_PACKAGE_PATH}/include/ascendc/include/adv_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/include/ascendc/highlevel_api
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/ascendc/include/basic_api/impl/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/asc/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/asc/impl/basic_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/asc/impl/simt_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/asc/impl/micro_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/include/basic_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/include/simt_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/include/micro_api/
            -I${TOP_DIR}/hcomm/include/hccl/
            -I${CMAKE_CURRENT_SOURCE_DIR}/aiv_interface/
            -I${TILING_GEN_DIR}
            -mllvm -cce-aicore-record-overflow=false -mllvm -cce-aicore-addr-transform -mllvm
            --cce-aicore-jump-expand=true -std=c++17 -fstack-protector-all
            WORKING_DIRECTORY ${CMAKE_CURRENT_BINARY_DIR}
            DEPENDS kernel_tiling_headers
   )
   
   add_custom_target(hccl_sk_ag_crossnode
            COMMAND ${BISHENG_CCACHE} ${CCE_DIR}/ccec -c -x cce -O2 ${CMAKE_CURRENT_SOURCE_DIR}/aiv_sk_ag_crossnode.h -o ${CMAKE_CURRENT_BINARY_DIR}/hccl_sk_ag_crossnode.o --cce-aicore-arch=dav-c220-vec
            -DTILING_KEY_VAR=0UL -D__ASCENDC_ENABLE_SUPER_KERNEL__ -DASCENDC_DUMP=0 -DL2_CACHE_HINT -DCONST_TILING -DDETERMINISTIC_MODE=0
            --cce-aicore-input-parameter-size=28000 --cce-aicore-only -mllvm -cce-aicore-function-stack-size=0x8000 -mllvm -cce-aicore-stack-size=0x8000
            -I${ASCEND_CANN_PACKAGE_PATH}/include/ascendc/basic_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/include/ascendc/basic_api/interface/
            -I${ASCEND_CANN_PACKAGE_PATH}/include/ascendc/include/adv_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/include/ascendc/highlevel_api
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/ascendc/include/basic_api/impl/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/asc/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/asc/impl/basic_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/asc/impl/simt_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/asc/impl/micro_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/include/basic_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/include/simt_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/include/micro_api/
            -I${TOP_DIR}/hcomm/include/hccl/
            -I${CMAKE_CURRENT_SOURCE_DIR}/aiv_interface/
            -I${TILING_GEN_DIR}
            -mllvm -cce-aicore-record-overflow=false -mllvm -cce-aicore-addr-transform -mllvm
            --cce-aicore-jump-expand=true -std=c++17 -fstack-protector-all
            WORKING_DIRECTORY ${CMAKE_CURRENT_BINARY_DIR}
            DEPENDS kernel_tiling_headers
   )
   
   add_custom_target(hccl_sk_a2a_crossnode
            COMMAND ${BISHENG_CCACHE} ${CCE_DIR}/ccec -c -x cce -O2 ${CMAKE_CURRENT_SOURCE_DIR}/aiv_sk_a2a_crossnode.h -o ${CMAKE_CURRENT_BINARY_DIR}/hccl_sk_a2a_crossnode.o --cce-aicore-arch=dav-c220-vec
            -DTILING_KEY_VAR=0UL -D__ASCENDC_ENABLE_SUPER_KERNEL__ -DASCENDC_DUMP=0 -DL2_CACHE_HINT -DCONST_TILING -DDETERMINISTIC_MODE=0
            --cce-aicore-input-parameter-size=28000 --cce-aicore-only -mllvm -cce-aicore-function-stack-size=0x8000 -mllvm -cce-aicore-stack-size=0x8000
            -I${ASCEND_CANN_PACKAGE_PATH}/include/ascendc/basic_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/include/ascendc/basic_api/interface/
            -I${ASCEND_CANN_PACKAGE_PATH}/include/ascendc/include/adv_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/include/ascendc/highlevel_api
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/ascendc/include/basic_api/impl/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/asc/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/asc/impl/basic_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/asc/impl/simt_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/asc/impl/micro_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/include/basic_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/include/simt_api/
            -I${ASCEND_CANN_PACKAGE_PATH}/${CMAKE_HOST_SYSTEM_PROCESSOR}-linux/include/micro_api/
            -I${TOP_DIR}/hcomm/include/hccl/
            -I${CMAKE_CURRENT_SOURCE_DIR}/aiv_interface/
            -I${TILING_GEN_DIR}
            -mllvm -cce-aicore-record-overflow=false -mllvm -cce-aicore-addr-transform -mllvm
            --cce-aicore-jump-expand=true -std=c++17 -fstack-protector-all
            WORKING_DIRECTORY ${CMAKE_CURRENT_BINARY_DIR}
            DEPENDS kernel_tiling_headers
   )

endif()

install(FILES ${CMAKE_CURRENT_BINARY_DIR}/hccl_aiv_op_ascend910B.o OPTIONAL
    DESTINATION ${INSTALL_LIBRARY_DIR}
)

install(FILES ${CMAKE_CURRENT_BINARY_DIR}/hccl_rs_superkernel_int8.o OPTIONAL
    DESTINATION ${INSTALL_LIBRARY_DIR}
)

install(FILES ${CMAKE_CURRENT_BINARY_DIR}/hccl_rs_superkernel_int16.o OPTIONAL
    DESTINATION ${INSTALL_LIBRARY_DIR}
)

install(FILES ${CMAKE_CURRENT_BINARY_DIR}/hccl_rs_superkernel_int32.o OPTIONAL
    DESTINATION ${INSTALL_LIBRARY_DIR}
)

install(FILES ${CMAKE_CURRENT_BINARY_DIR}/hccl_rs_superkernel_float16.o OPTIONAL
    DESTINATION ${INSTALL_LIBRARY_DIR}
)

install(FILES ${CMAKE_CURRENT_BINARY_DIR}/hccl_rs_superkernel_float32.o OPTIONAL
    DESTINATION ${INSTALL_LIBRARY_DIR}
)

install(FILES ${CMAKE_CURRENT_BINARY_DIR}/hccl_rs_superkernel_bfloat16.o OPTIONAL
    DESTINATION ${INSTALL_LIBRARY_DIR}
)

install(FILES ${CMAKE_CURRENT_BINARY_DIR}/hccl_ag_superkernel_int8.o OPTIONAL
    DESTINATION ${INSTALL_LIBRARY_DIR}
)

install(FILES ${CMAKE_CURRENT_BINARY_DIR}/hccl_ag_superkernel_int16.o OPTIONAL
    DESTINATION ${INSTALL_LIBRARY_DIR}
)

install(FILES ${CMAKE_CURRENT_BINARY_DIR}/hccl_ag_superkernel_int32.o OPTIONAL
    DESTINATION ${INSTALL_LIBRARY_DIR}
)

install(FILES ${CMAKE_CURRENT_BINARY_DIR}/hccl_ag_superkernel_float16.o OPTIONAL
    DESTINATION ${INSTALL_LIBRARY_DIR}
)

install(FILES ${CMAKE_CURRENT_BINARY_DIR}/hccl_ag_superkernel_float32.o OPTIONAL
    DESTINATION ${INSTALL_LIBRARY_DIR}
)

install(FILES ${CMAKE_CURRENT_BINARY_DIR}/hccl_ag_superkernel_bfloat16.o OPTIONAL
    DESTINATION ${INSTALL_LIBRARY_DIR}
)

install(FILES ${CMAKE_CURRENT_BINARY_DIR}/hccl_ag_superkernel_uint8.o OPTIONAL
    DESTINATION ${INSTALL_LIBRARY_DIR}
)

install(FILES ${CMAKE_CURRENT_BINARY_DIR}/hccl_ag_superkernel_uint16.o OPTIONAL
    DESTINATION ${INSTALL_LIBRARY_DIR}
)

install(FILES ${CMAKE_CURRENT_BINARY_DIR}/hccl_ag_superkernel_uint32.o OPTIONAL
    DESTINATION ${INSTALL_LIBRARY_DIR}
)

install(FILES ${CMAKE_CURRENT_BINARY_DIR}/hccl_a2a_superkernel_int8.o OPTIONAL
    DESTINATION ${INSTALL_LIBRARY_DIR}
)

install(FILES ${CMAKE_CURRENT_BINARY_DIR}/hccl_a2a_superkernel_int16.o OPTIONAL
    DESTINATION ${INSTALL_LIBRARY_DIR}
)

install(FILES ${CMAKE_CURRENT_BINARY_DIR}/hccl_a2a_superkernel_int32.o OPTIONAL
    DESTINATION ${INSTALL_LIBRARY_DIR}
)

install(FILES ${CMAKE_CURRENT_BINARY_DIR}/hccl_a2a_superkernel_float16.o OPTIONAL
    DESTINATION ${INSTALL_LIBRARY_DIR}
)

install(FILES ${CMAKE_CURRENT_BINARY_DIR}/hccl_a2a_superkernel_float32.o OPTIONAL
    DESTINATION ${INSTALL_LIBRARY_DIR}
)

install(FILES ${CMAKE_CURRENT_BINARY_DIR}/hccl_a2a_superkernel_bfloat16.o OPTIONAL
    DESTINATION ${INSTALL_LIBRARY_DIR}
)

install(FILES ${CMAKE_CURRENT_BINARY_DIR}/hccl_a2a_superkernel_uint8.o OPTIONAL
    DESTINATION ${INSTALL_LIBRARY_DIR}
)

install(FILES ${CMAKE_CURRENT_BINARY_DIR}/hccl_a2a_superkernel_uint16.o OPTIONAL
    DESTINATION ${INSTALL_LIBRARY_DIR}
)

install(FILES ${CMAKE_CURRENT_BINARY_DIR}/hccl_a2a_superkernel_uint32.o OPTIONAL
    DESTINATION ${INSTALL_LIBRARY_DIR}
)

install(FILES ${CMAKE_CURRENT_BINARY_DIR}/hccl_ar_superkernel_int8.o OPTIONAL
    DESTINATION ${INSTALL_LIBRARY_DIR}
)

install(FILES ${CMAKE_CURRENT_BINARY_DIR}/hccl_ar_superkernel_int16.o OPTIONAL
    DESTINATION ${INSTALL_LIBRARY_DIR}
)

install(FILES ${CMAKE_CURRENT_BINARY_DIR}/hccl_ar_superkernel_int32.o OPTIONAL
    DESTINATION ${INSTALL_LIBRARY_DIR}
)

install(FILES ${CMAKE_CURRENT_BINARY_DIR}/hccl_ar_superkernel_float16.o OPTIONAL
    DESTINATION ${INSTALL_LIBRARY_DIR}
)

install(FILES ${CMAKE_CURRENT_BINARY_DIR}/hccl_ar_superkernel_float32.o OPTIONAL
    DESTINATION ${INSTALL_LIBRARY_DIR}
)

install(FILES ${CMAKE_CURRENT_BINARY_DIR}/hccl_ar_superkernel_bfloat16.o OPTIONAL
    DESTINATION ${INSTALL_LIBRARY_DIR}
)

install(FILES ${CMAKE_CURRENT_BINARY_DIR}/hccl_sk_rs_deter.o OPTIONAL
    DESTINATION ${INSTALL_LIBRARY_DIR}
)

install(FILES ${CMAKE_CURRENT_BINARY_DIR}/hccl_sk_ar_deter.o OPTIONAL
    DESTINATION ${INSTALL_LIBRARY_DIR}
)

install(FILES ${CMAKE_CURRENT_BINARY_DIR}/hccl_sk_ar_crossnode.o OPTIONAL
    DESTINATION ${INSTALL_LIBRARY_DIR}
)

install(FILES ${CMAKE_CURRENT_BINARY_DIR}/hccl_sk_rs_crossnode.o OPTIONAL
    DESTINATION ${INSTALL_LIBRARY_DIR}
)

install(FILES ${CMAKE_CURRENT_BINARY_DIR}/hccl_sk_ag_crossnode.o OPTIONAL
    DESTINATION ${INSTALL_LIBRARY_DIR}
)

install(FILES ${CMAKE_CURRENT_BINARY_DIR}/hccl_sk_a2a_crossnode.o OPTIONAL
    DESTINATION ${INSTALL_LIBRARY_DIR}
)