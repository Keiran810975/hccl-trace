LOCAL_PATH := $(call my-dir)

include $(CLEAR_VARS)

LOCAL_MODULE := libra

LOCAL_LDFLAGS += -ldl -lrt


# LOCAL_PATH用于build核心加上LOCAL_SRC_FILES组合成源文件, 如果需要编译
# 源代码文件. 则需要PATH_BRIDGE引过去, PATH_BRIDGE和LOCAL_PATH组合成build
# 核心需要的源代码路径
PATH_BRIDGE		:=

LOCAL_SRC_FILES :=

LOCAL_SRC_FILES += $(PATH_BRIDGE)ra_host.c


LOCAL_C_INCLUDES:= 

#第三方头文件搜索路径
LOCAL_C_INCLUDES+=$(TOPDIR)inc/network $(TOPDIR)hccl/src/platform/hccp/rdma_agent/inc \
			$(TOPDIR)inc/toolchain $(TOPDIR)inc/driver \
			$(TOPDIR)hccl/src/platform/hccp/rdma_agent/hdc \
			$(TOPDIR)drivers/network/include \
			$(TOPDIR)libc_sec/include \
			$(TOPDIR)hccl/src/platform/hccp/rdma_agent/comm \
                        $(TOPDIR)hccl/src/platform/hccp/rdma_agent/peer
#第三方库搜索路径
LOCAL_LD_DIRS :=  

LOCAL_CFLAGS += -Werror -std=c11
## add more LOCAL_SRC_FILES and LOCAL_C_INCLUDES

LOCAL_SHARED_LIBRARIES := libc_sec libslog libra_hdc stub/libascend_hal

include $(BUILD_HOST_SHARED_LIBRARY)
