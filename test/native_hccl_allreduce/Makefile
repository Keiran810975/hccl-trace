ASCEND_HOME_PATH ?= /usr/local/Ascend/ascend-toolkit/latest
DEPLOY_LIB_DIR ?= ../../deploy/lib64

CXX ?= g++
CXXFLAGS ?= -std=c++14 -O2 -Wall -Wextra -fstack-protector-strong
INCS := -I$(ASCEND_HOME_PATH)/include
LIB_DIRS := -L$(DEPLOY_LIB_DIR) -L$(ASCEND_HOME_PATH)/lib64 -L$(ASCEND_HOME_PATH)/aarch64-linux/lib64
LIBS := -lhccl -lascendcl -lpthread

TARGET := native_hccl_allreduce
SOURCES := native_hccl_allreduce.cc

.PHONY: all clean

all: $(TARGET)

$(TARGET): $(SOURCES)
	$(CXX) $(CXXFLAGS) $(SOURCES) $(INCS) $(LIB_DIRS) $(LIBS) -o $@

clean:
	rm -f $(TARGET)
