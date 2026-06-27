# -----------------------------------------------------------------------------------------------------------
# Copyright (c) 2025 Huawei Technologies Co., Ltd.
# This program is free software, you can redistribute it and/or modify it under the terms and conditions of
# CANN Open Software License Agreement Version 2.0 (the "License").
# Please refer to the License for details. You may not use this file except in compliance with the License.
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
# See LICENSE in the root of the software repository for the full text of the License.
# -----------------------------------------------------------------------------------------------------------
#!/bin/bash

set -e
BASEPATH=$(cd "$(dirname $0)"; pwd)
OUTPUT_PATH="${BASEPATH}/output/third_party"

# print usage message
usage() {
  echo "Usage:"
  echo "  sh build_third_party.sh [-h | --help]"
  echo "              [--output_path=<PATH>]"
  echo ""
  echo "Options:"
  echo "    -h, --help     Print usage"
  echo "    --output_path=<PATH>"
  echo "                   Set the output path for third-party libraries, default ./output/third_party"
  echo ""
}

# parse and set options
checkopts() {
  while [[ $# -gt 0 ]]; do
    case "$1" in
      -h | --help)
        usage
        exit 0
        ;;
      --output_path=*)
        OUTPUT_PATH="$(realpath "${1#*=}")"
        shift
        ;;
      *)
        echo "Undefined option: $1"
        usage
        exit 1
        ;;
    esac
  done
}

mk_dir() {
  local create_dir="$1"
  mkdir -pv "${create_dir}"
  echo "created ${create_dir}"
}

download_and_compile() {
    echo "Downloading files to ${OUTPUT_PATH}..."

    mk_dir "${OUTPUT_PATH}/pkg"
    mk_dir "${OUTPUT_PATH}/json"
    mk_dir "${OUTPUT_PATH}/gtest_shared"
    mk_dir "${OUTPUT_PATH}/mpich_shared"
    cpu_cores=$(lscpu | grep 'CPU(s):' | awk '{print$2}')

    # Downloading json
    wget --no-check-certificate -O "${OUTPUT_PATH}/pkg/json_include.zip" https://gitcode.com/cann-src-third-party/json/releases/download/v3.11.3/include.zip
    if [ $? -ne 0 ]; then
      echo "Failed to download json files"
      exit 1;
    fi

    unzip "${OUTPUT_PATH}/pkg/json_include.zip" -d "${OUTPUT_PATH}/json"
    if [ $? -ne 0 ]; then
      echo "Failed to extract json files"
      exit 1;
    fi

    # Downloading gtest
    wget --no-check-certificate -O "${OUTPUT_PATH}/pkg/googletest-1.14.0.tar.gz" https://gitcode.com/cann-src-third-party/googletest/releases/download/v1.14.0/googletest-1.14.0.tar.gz
    if [ $? -ne 0 ]; then
      echo "Failed to download gtest files"
      exit 1;
    fi

    tar -zxvf "${OUTPUT_PATH}/pkg/googletest-1.14.0.tar.gz" -C "${OUTPUT_PATH}/gtest_shared"
    if [ $? -ne 0 ]; then
      echo "Failed to extract gtest files"
      exit 1;
    fi

    cd "${OUTPUT_PATH}/gtest_shared/googletest-1.14.0"
    cmake -DCMAKE_CXX_FLAGS="-D_GLIBCXX_USE_CXX11_ABI=0 -O2 -D_FORTIFY_SOURCE=2 -fPIC -fstack-protector-all -Wl,-z,relro,-z,now,-z,noexecstack" \
          -DCMAKE_C_FLAGS="-D_GLIBCXX_USE_CXX11_ABI=0 -O2 -D_FORTIFY_SOURCE=2 -fPIC -fstack-protector-all -Wl,-z,relro,-z,now,-z,noexecstack" \
          -DCMAKE_INSTALL_PREFIX=${OUTPUT_PATH}/gtest_shared \
          -DCMAKE_INSTALL_LIBDIR=lib64 \
          -DBUILD_TESTING=OFF \
          -DBUILD_SHARED_LIBS=ON
    if [ $? -ne 0 ]; then
      echo "Failed to configure googletest with cmake"
      exit 1;
    fi

    make && make install
    if [ $? -ne 0 ]; then
      echo "Failed to install googletest"
      exit 1;
    fi

    cd "${OUTPUT_PATH}/gtest_shared"
    ln -s lib64 lib

    echo "All operations completed successfully!"
}

download_mockcpp() {
  MOCKCPP_PKG_URL="https://gitcode.com/cann-src-third-party/mockcpp/releases/download/v2.7-h2/mockcpp-2.7.zip"
  MOCKCPP_PATCH_URL="https://gitcode.com/cann-src-third-party/mockcpp/releases/download/v2.7-h2/mockcpp-2.7_py3.patch"

  # 下载
  wget --no-check-certificate -O "${OUTPUT_PATH}/pkg/mockcpp-2.7.zip" ${MOCKCPP_PKG_URL}
  wget --no-check-certificate -O "${OUTPUT_PATH}/pkg/mockcpp-2.7.patch" ${MOCKCPP_PATCH_URL}

  # 解压
  unzip "${OUTPUT_PATH}/pkg/mockcpp-2.7.zip" -d "${OUTPUT_PATH}/mockcpp_shared"

  # 补丁
  cd ${OUTPUT_PATH}/mockcpp_shared/mockcpp-2.7
  patch -p1 < ${OUTPUT_PATH}/pkg/mockcpp-2.7.patch
}

build_mockcpp() {
  apt-get install libboost-dev -y

  cd "${OUTPUT_PATH}/mockcpp_shared/mockcpp-2.7/"

  cmake -DCMAKE_CXX_FLAGS="-D_GLIBCXX_USE_CXX11_ABI=0 -O2 -D_FORTIFY_SOURCE=2 -fPIC -fstack-protector-all -Wl,-z,relro,-z,now,-z,noexecstack" \
        -DCMAKE_C_FLAGS="-D_GLIBCXX_USE_CXX11_ABI=0 -O2 -D_FORTIFY_SOURCE=2 -fPIC -fstack-protector-all -Wl,-z,relro,-z,now,-z,noexecstack" \
        -DBUILD_32_BIT_TARGET_BY_64_BIT_COMPILER=OFF \
        -DCMAKE_INSTALL_PREFIX=${OUTPUT_PATH}/mockcpp_shared \
        -DCMAKE_INSTALL_LIBDIR=lib64 \
        -DBUILD_TESTING=OFF \
        -DBUILD_SHARED_LIBS=ON

  make && make install

  cd "${OUTPUT_PATH}/mockcpp_shared"
  ln -s lib64 lib
}

download_and_compile_protobuf() {
  mk_dir "${OUTPUT_PATH}/protobuf"
  mk_dir "${OUTPUT_PATH}/abseil-cpp"

  # 下载
  PROTOBUF_URL="https://gitcode.com/cann-src-third-party/protobuf/releases/download/v25.1/protobuf-25.1.zip"
  wget --no-check-certificate -O "${OUTPUT_PATH}/pkg/protobuf-25.1.zip" ${PROTOBUF_URL}

  # 下载abseil子模块
  ABSEIL_URL="https://gitcode.com/cann-src-third-party/abseil-cpp/releases/download/20250127.0/abseil-cpp-20250127.0.zip"
  wget --no-check-certificate -O "${OUTPUT_PATH}/pkg/abseil-cpp-20250127.0.zip" ${ABSEIL_URL}

  # 解压
  unzip "${OUTPUT_PATH}/pkg/protobuf-25.1.zip" -d "${OUTPUT_PATH}/protobuf"
  unzip "${OUTPUT_PATH}/pkg/abseil-cpp-20250127.0.zip" -d "${OUTPUT_PATH}/protobuf/protobuf-25.1/third_party"

  # 下载abseil子模块
  cd "${OUTPUT_PATH}/protobuf/protobuf-25.1/third_party"
  mv abseil-cpp-20250127.0/* abseil-cpp

  # 编译
  mk_dir "${OUTPUT_PATH}/protobuf/protobuf-25.1"
  cd "${OUTPUT_PATH}/protobuf/protobuf-25.1"

  cmake -G "Unix Makefiles" -DCMAKE_CXX_FLAGS="-D_GLIBCXX_USE_CXX11_ABI=0" \
        -DCMAKE_BUILD_TYPE=Release \
        -DCMAKE_INSTALL_PREFIX=${OUTPUT_PATH}/protobuf \
        -DCMAKE_INSTALL_LIBDIR=lib64 \
        -DBUILD_SHARED_LIBS=ON \
        -Dprotobuf_WITH_ZLIB=OFF \
        -Dprotobuf_BUILD_TESTS=OFF
  
  make -j8 && make install
  ln -s lib64 lib
}

main() {
  checkopts "$@"

  echo "---------------- script start ----------------"
  whoami
  id
  echo $USER

  download_and_compile
  if [[ "$?" -ne 0 ]]; then
    echo "script failed.";
    exit 1;
  fi
  echo "---------------- download_and_compile pass ----------------"
  # 下载、编译 mockcpp
  download_mockcpp
  echo "---------------- download_mockcpp pass ----------------"
  build_mockcpp
  echo "---------------- build_mockcpp pass ----------------"

  # 下载、编译 protobuf
  download_and_compile_protobuf

  echo "---------------- script finished ----------------"
}

main "$@"
