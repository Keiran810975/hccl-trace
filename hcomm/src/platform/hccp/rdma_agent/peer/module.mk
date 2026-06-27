LOCAL_PATH 		:= 	$(call my-dir)

include $(CLEAR_VARS)

LOCAL_MODULE 	:= 	libra_peer

LOCAL_LDFLAGS	+= -lrs


# LOCAL_PATH用于build核心加上LOCAL_SRC_FILES组合成源文件, 如果需要编译
# 源代码文件. 则需要PATH_BRIDGE引过去, PATH_BRIDGE和LOCAL_PATH组合成build
# 核心需要的源代码路径
PATH_BRIDGE		:=

LOCAL_SRC_FILES :=

LOCAL_SRC_FILES += $(PATH_BRIDGE)ra_peer.c $(PATH_BRIDGE)/../comm/ra_comm.c


LOCAL_C_INCLUDES:= 

#第三方头文件搜索路径
LOCAL_C_INCLUDES+= 	$(TOPDIR)inc/network \
			$(TOPDIR)inc/toolchain \
		   	$(TOPDIR)libc_sec/include \
			$(TOPDIR)hccl/src/platform/hccp/rdma_agent/inc \
			$(TOPDIR)hccl/src/platform/hccp/rdma_service \
			$(TOPDIR)inc/driver \
			$(TOPDIR)drivers/network/include \
			$(TOPDIR)hccl/src/platform/hccp/rdma_agent/comm
#第三方库搜索路径
LOCAL_LD_DIRS :=  

LOCAL_CFLAGS += -Werror
LOCAL_CFLAGS += -DNETWORK_HOST

## add more LOCAL_SRC_FILES and LOCAL_C_INCLUDES

LOCAL_SHARED_LIBRARIES := librs libc_sec libslog libascend_hal

include $(BUILD_HOST_SHARED_LIBRARY)
