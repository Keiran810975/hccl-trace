# -----------------------------------------------------------------------------------------------------------
# Copyright (c) 2025 Huawei Technologies Co., Ltd.
# This program is free software, you can redistribute it and/or modify it under the terms and conditions of
# CANN Open Software License Agreement Version 2.0 (the "License").
# Please refer to the License for details. You may not use this file except in compliance with the License.
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
# See LICENSE in the root of the software repository for the full text of the License.
# -----------------------------------------------------------------------------------------------------------
set -e

CURRENT_DIR=$(dirname $(readlink -f ${BASH_SOURCE[0]}))
BUILD_DIR=${CURRENT_DIR}/build
BUILD_DEVICE_DIR="${CURRENT_DIR}/build_device"
BUILD_OUTPUT_DIR=${CURRENT_DIR}/build_out
USER_ID=$(id -u)
CPU_NUM=$(cat /proc/cpuinfo | grep "^processor" | wc -l)
JOB_NUM="-j${CPU_NUM}"
ASAN="false"
COV="false"
CUSTOM_OPTION="-DCMAKE_INSTALL_PREFIX=${BUILD_OUTPUT_DIR}"
FULL_MODE="false"  # 新增变量，用于控制是否全量构建
KERNEL="false"  # 新增变量，用于控制是否只编译 ccl_kernel.so
DO_NOT_CLEAN="false" # 是否清理
CANN_3RD_LIB_PATH="${CURRENT_DIR}/third_party"
CANN_UTILS_LIB_PATH="${CURRENT_DIR}/utils"
BUILD_AARCH="false"
CUSTOM_SIGN_SCRIPT="${CURRENT_DIR}/scripts/sign/community_sign_build.py"
ENABLE_SIGN="false"
VERSION_INFO="8.5.0"

if [ "${USER_ID}" != "0" ]; then
    DEFAULT_TOOLKIT_INSTALL_DIR="${HOME}/Ascend/ascend-toolkit/latest"
    DEFAULT_INSTALL_DIR="${HOME}/Ascend/latest"
else
    DEFAULT_TOOLKIT_INSTALL_DIR="/usr/local/Ascend/ascend-toolkit/latest"
    DEFAULT_INSTALL_DIR="/usr/local/Ascend/latest"
fi

function log() {
    local current_time=`date +"%Y-%m-%d %H:%M:%S"`
    echo "[$current_time] "$1
}

function set_env()
{
    source $ASCEND_CANN_PACKAGE_PATH/set_env.sh || echo "0"
}

function clean()
{
    if [ -n "${BUILD_DIR}" ];then
        rm -rf ${BUILD_DIR}
    fi

    if [ -z "${TEST}" ] && [ -z "${KERNEL}" ];then
        if [ -n "${BUILD_OUTPUT_DIR}" ];then
            rm -rf ${BUILD_OUTPUT_DIR}
        fi
    fi

    mkdir -p ${BUILD_DIR}
}

function cmake_config()
{
    local extra_option="$1"
    log "Info: cmake config ${CUSTOM_OPTION} ${extra_option} ."
    cmake ..  ${CUSTOM_OPTION} ${extra_option}
}

function build()
{
    log "Info: build target:$@ JOB_NUM:${JOB_NUM}"
    cmake --build . --target "$@" ${JOB_NUM} #--verbose
}

function build_package(){
    cmake_config
    log "Info: build_package"
    build package
}

function build_device(){
    cmake_config
    log "Info: build_device"
    TARGET_LIST="hccp_service.bin rs ccl_kernel_plf ccl_kernel_plf_a ccl_kernel"
    echo "TARGET_LIST=${TARGET_LIST}"
    PKG_TARGET_LIST="generate_device_hccp_package generate_device_aicpu_package"
    echo "PKG_TARGET_LIST=${PKG_TARGET_LIST}"
    SIGN_TARGET_LIST="sign_cann_hcomm_compat sign_aicpu_hcomm"
    echo "SIGN_TARGET_LIST=${SIGN_TARGET_LIST}"
    build ${TARGET_LIST} ${PKG_TARGET_LIST} ${SIGN_TARGET_LIST}
}

function build_hccd(){
    cmake_config
    log "Info: build_hccd"
    TARGET_LIST="rs ra_peer ra_hdc ra hccd"
    echo "TARGET_LIST=${TARGET_LIST}"
    PKG_TARGET_LIST="generate_device_hccd_package"
    echo "PKG_TARGET_LIST=${PKG_TARGET_LIST}"
    SIGN_TARGET_LIST="sign_cann_hccd_compat"
    echo "SIGN_TARGET_LIST=${SIGN_TARGET_LIST}"
    build ${TARGET_LIST} ${PKG_TARGET_LIST} ${SIGN_TARGET_LIST}
}

function build_kernel() {
    cmake_config
    log "Info: build_kernel"
    build ccl_kernel_plf ccl_kernel_plf_a ccl_kernel aicpu_custom_json
}

# print usage message
function usage() {
  echo "Usage:"
  echo "  sh build.sh --pkg [-h | --help] [-j<N>]"
  echo "              [--cann_3rd_lib_path=<PATH>] [-p|--package-path <PATH>]"
  echo "              [--asan]"
  echo "              [--sign-script <PATH>] [--enable-sign] [--version <VERSION>]"
  echo ""
  echo "Options:"
  echo "    -h, --help     Print usage"
  echo "    --asan         Enable AddressSanitizer"
  echo "    -build-type=<TYPE>"
  echo "                   Specify build type (TYPE options: Release/Debug), Default: Release"
  echo "    -j<N>          Set the number of threads used for building, default is 8"
  echo "    --cann_3rd_lib_path=<PATH>"
  echo "                   Set ascend third_party package install path, default ./output/third_party"
  echo "    -p|--package-path <PATH>"
  echo "                   Set ascend package install path, default /usr/local/Ascend/cann"
  echo "    --sign-script <PATH>"
  echo "                   Set sign-script's path to <PATH>"
  echo "    --enable-sign"
  echo "                   Enable to sign"
  echo "    --version <VERSION>"
  echo "                   Set sign version to <VERSION>"
  echo ""
}

while [[ $# -gt 0 ]]; do
    case "$1" in
      -h | --help)
        usage
        exit 0
        ;;
    -j*)
        JOB_NUM="$1"
        shift
        ;;
    --build-type=*)
        OPTARG=$1
        BUILD_TYPE="${OPTARG#*=}"
        shift
        ;;
    --ccache)
        CCACHE_PROGRAM="$2"
        shift 2
        ;;
    -p|--package-path)
        ascend_package_path="$2"
        shift 2
        ;;
    --nlohmann_path)
        third_party_nlohmann_path="$2"
        shift 2
        ;;
    --pkg)
        # 跳过 --pkg，不做处理
        shift
        ;;
    --cann_3rd_lib_path=*)
        OPTARG=$1
        CANN_3RD_LIB_PATH="$(realpath ${OPTARG#*=})"
        shift
        ;;
    --aicpu)  # 新增选项，用于只编译 ccl_kernel.so
        KERNEL="true"
        shift
        ;;
    --full)
        FULL_MODE="true"
        shift
        ;;
    --build_aarch)
        BUILD_AARCH="true"
        shift
        ;;
    --asan)
        ASAN="true"
        shift
        ;;
    --cov)
        COV="true"
        shift
        ;;
    --noclean)
        DO_NOT_CLEAN="true"
        shift
        ;;
    --enable-sign)
        ENABLE_SIGN="true"
        shift
        ;;
    --sign-script)
        CUSTOM_SIGN_SCRIPT="$(realpath $2)"
        shift 2
        ;;
    --version)
        VERSION_INFO="$2"
        shift 2
        ;;
    *)
        log "Error: Undefined option: $1"
        usage
        exit 1
        ;;
    esac
done

if [ "${KERNEL}" == "true" ];then
    CUSTOM_OPTION="${CUSTOM_OPTION} -DKERNEL_MODE=ON -DDEVICE_MODE=ON -DPRODUCT=ascend -DPRODUCT_SIDE=device"
fi

if [ "${FULL_MODE}" == "true" ];then
    CUSTOM_OPTION="${CUSTOM_OPTION} -DFULL_MODE=ON"
fi

if [ "${BUILD_AARCH}" == "true" ];then
    CUSTOM_OPTION="${CUSTOM_OPTION} -DAARCH_MODE=ON"
fi

if [ "${ASAN}" == "true" ];then
    CUSTOM_OPTION="${CUSTOM_OPTION} -DENABLE_ASAN=true"
fi

if [ "${COV}" == "true" ];then
    CUSTOM_OPTION="${CUSTOM_OPTION} -DENABLE_GCOV=true"
fi

if [ -n "${ascend_package_path}" ];then
    ASCEND_CANN_PACKAGE_PATH=${ascend_package_path}
elif [ -n "${ASCEND_HOME_PATH}" ];then
    ASCEND_CANN_PACKAGE_PATH=${ASCEND_HOME_PATH}
elif [ -n "${ASCEND_OPP_PATH}" ];then
    ASCEND_CANN_PACKAGE_PATH=$(dirname ${ASCEND_OPP_PATH})
elif [ -d "${DEFAULT_TOOLKIT_INSTALL_DIR}" ];then
    ASCEND_CANN_PACKAGE_PATH=${DEFAULT_TOOLKIT_INSTALL_DIR}
elif [ -d "${DEFAULT_INSTALL_DIR}" ];then
    ASCEND_CANN_PACKAGE_PATH=${DEFAULT_INSTALL_DIR}
else
    log "Error: Please set the toolkit package installation directory through parameter -p|--package-path."
    exit 1
fi

if [ -n "${third_party_nlohmann_path}" ];then
    CUSTOM_OPTION="${CUSTOM_OPTION} -DTHIRD_PARTY_NLOHMANN_PATH=${third_party_nlohmann_path}"
fi

CUSTOM_OPTION="${CUSTOM_OPTION} -DCUSTOM_ASCEND_CANN_PACKAGE_PATH=${ASCEND_CANN_PACKAGE_PATH}"
# CUSTOM_OPTION="${CUSTOM_OPTION} -DCANN_3RD_LIB_PATH=${cann_3rd_lib_path}"
CUSTOM_OPTION="$CUSTOM_OPTION -DCANN_3RD_LIB_PATH=${CANN_3RD_LIB_PATH} -DCANN_UTILS_LIB_PATH=${CANN_UTILS_LIB_PATH}"

CUSTOM_OPTION="$CUSTOM_OPTION -DCMAKE_BUILD_TYPE=${BUILD_TYPE}"

set_env

if [ "${DO_NOT_CLEAN}" = "false" ]; then
    clean
else
    mkdir -p "${BUILD_DIR}"
fi

cd ${BUILD_DIR}

if [ "${KERNEL}" == "true" ]; then
    build_kernel
elif [ "${FULL_MODE}" == "true" ]; then
    cd ..
    mkdir -p ${BUILD_DEVICE_DIR}
    cd ${BUILD_DEVICE_DIR}
    CURRENT_CUSTOM_OPTION="${CUSTOM_OPTION}"
    CUSTOM_OPTION="${CURRENT_CUSTOM_OPTION} -DFULL_MODE=ON -DDEVICE_MODE=ON -DKERNEL_MODE=ON -DPRODUCT=ascend910B -DPRODUCT_SIDE=device -DUSE_ALOG=0 -DCUSTOM_SIGN_SCRIPT=${CUSTOM_SIGN_SCRIPT} -DENABLE_SIGN=${ENABLE_SIGN} -DVERSION_INFO=${VERSION_INFO}"
    build_device
    BUILD_HCCD_DIR="${CURRENT_DIR}/build_hccd"
    mkdir -p ${BUILD_HCCD_DIR}
    cd ${BUILD_HCCD_DIR}
    CUSTOM_OPTION="${CURRENT_CUSTOM_OPTION} -DDEVICE_MODE=ON -DPRODUCT=ascend -DPRODUCT_SIDE=device -DUSE_ALOG=1 -DCUSTOM_SIGN_SCRIPT=${CUSTOM_SIGN_SCRIPT} -DENABLE_SIGN=${ENABLE_SIGN} -DVERSION_INFO=${VERSION_INFO}"
    build_hccd
    cd .. & cd ${BUILD_DIR}
    CUSTOM_OPTION="${CURRENT_CUSTOM_OPTION} -DDEVICE_MODE=OFF -DPRODUCT=ascend -DPRODUCT_SIDE=host -DUSE_ALOG=1"
    build_package
    rm -rf ${BUILD_DEVICE_DIR} ${BUILD_HCCD_DIR}
else
    CUSTOM_OPTION="${CUSTOM_OPTION} -DDEVICE_MODE=OFF -DPRODUCT=ascend -DPRODUCT_SIDE=host -DUSE_ALOG=1"
    build_package
fi
