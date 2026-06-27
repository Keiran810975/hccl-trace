set(checker_to_test_list)
add_library(hccl_alg_analyzer SHARED ${checker_to_test_list})

set(UTILS_INNER_INCLUDE_LIST
    ${HCOMM_ALG_UTILS_ROOT}/checker
    ${HCOMM_ALG_UTILS_ROOT}/checker/common/types
    ${HCOMM_ALG_UTILS_ROOT}/checker/rank_info_recorder
    ${HCOMM_ALG_UTILS_ROOT}/checker/mem_layout
    ${HCOMM_ALG_UTILS_ROOT}/checker/link_type_recorder
    ${HCOMM_ALG_UTILS_ROOT}/checker/task_collector
    ${HCOMM_ALG_UTILS_ROOT}/checker/semantics_check
    ${HCOMM_ALG_UTILS_ROOT}/checker/singletask_check
    ${HCOMM_ALG_UTILS_ROOT}/checker/mem_conflict_check
    ${HCOMM_ALG_UTILS_ROOT}/checker/ui/data_dumper
    ${HCOMM_ALG_UTILS_ROOT}/checker/param_trans
    ${HCOMM_ALG_UTILS_ROOT}/adapter_v1
    ${HCOMM_ALG_UTILS_ROOT}/adapter_v1/runtime
)

add_subdirectory(checker)
add_subdirectory(adapter_v1)

# 需要针对protobuf自动编译生成的文件设置GENERATED属性，否则会编译报错
set_property(SOURCE ${CMAKE_BINARY_DIR}/proto/alg_analyzer_proto/proto/analysis_result.pb.cc PROPERTY GENERATED 1)

#头文件搜索路径
target_include_directories(hccl_alg_analyzer PRIVATE
    ${UTILS_PUBLIC_INCLUDE_LIST}
    ${UTILS_INNER_INCLUDE_LIST}
)

target_compile_definitions(hccl_alg_analyzer PRIVATE
    -DOPEN_HCCL_TEST
    _GLIBCXX_USE_CXX11_ABI=0
)

target_compile_options(hccl_alg_analyzer PRIVATE
    -U_FORTIFY_SOURCE
    -Os
    -O2
    -pipe
)

target_link_libraries(hccl_alg_analyzer PRIVATE
    hccl_alg_adaption
    ${THIRD_PARTY_PATH}/gtest_shared/lib64/libgtest.so
    -lpthread
    ${PROTO_SOURCE_DIR}/libprotobuf.so
    ${ASCEND_CANN_PACKAGE_PATH}/lib64/libc_sec.so
    -lrt
    -ldl
)