set(stub_tsd_list
    stub_tsd.c
)
# 创建共享库
add_library(tsd_eventclient SHARED ${stub_tsd_list})

# 设置头文件搜索路径
target_include_directories(tsd_eventclient PRIVATE
    ${ASCEND_CANN_PACKAGE_PATH}/pkg_inc/aicpu/tsd
)