#pragma once
#include <cstdlib>
#include <cstring>
#include <fstream>
#include <mutex>
using aclrtStream = void *;
constexpr int ACL_MEM_MALLOC_HUGE_FIRST = 0;
constexpr int ACL_MEMCPY_HOST_TO_DEVICE = 1;
constexpr int ACL_MEMCPY_DEVICE_TO_HOST = 2;
inline void StubCleanup()
{
    static std::mutex lock;
    std::lock_guard<std::mutex> held(lock);
    const char *path = std::getenv("HCCL_WORKER_STUB_LOG");
    if (path) std::ofstream(path, std::ios::app) << "cleanup\n";
}
inline int aclInit(const char *) { return 0; }
inline int aclFinalize() { StubCleanup(); return 0; }
inline int aclrtSetDevice(int) { return 0; }
inline int aclrtMalloc(void **out, size_t size, int) { *out = std::malloc(size); return *out ? 0 : 1; }
inline int aclrtFree(void *data) { StubCleanup(); std::free(data); return 0; }
inline int aclrtMemcpy(void *dst, size_t, const void *src, size_t size, int)
{ std::memcpy(dst, src, size); return 0; }
inline int aclrtCreateStream(aclrtStream *out) { *out = new int(1); return 0; }
inline int aclrtDestroyStream(aclrtStream stream) { StubCleanup(); delete static_cast<int *>(stream); return 0; }
inline int aclrtSynchronizeStream(aclrtStream) { return 0; }
