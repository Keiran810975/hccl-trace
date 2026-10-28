#pragma once
#include <algorithm>
#include <cstdint>
#include <acl/acl.h>
using HcclComm = void *;
constexpr int HCCL_DATA_TYPE_FP32 = 0;
constexpr int HCCL_REDUCE_SUM = 0;
inline int HcclCommInitAll(int count, int32_t *, HcclComm *comms)
{ for (int i = 0; i < count; ++i) comms[i] = reinterpret_cast<void *>(static_cast<uintptr_t>(i + 1)); return 0; }
inline int HcclAllReduce(void *, void *recv, size_t count, int, int, HcclComm, aclrtStream)
{ std::fill_n(static_cast<float *>(recv), count, 3.0f); return 0; }
inline int HcclCommDestroy(HcclComm) { StubCleanup(); return 0; }
