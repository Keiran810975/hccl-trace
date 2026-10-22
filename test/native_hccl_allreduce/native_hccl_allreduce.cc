#include <acl/acl.h>
#include <hccl/hccl.h>
#include <hccl/hccl_types.h>

#include <atomic>
#include <chrono>
#include <cstdint>
#include <cstdlib>
#include <cstring>
#include <iostream>
#include <string>
#include <thread>
#include <vector>

namespace {

struct Args {
    uint32_t rankSize = 8;
    uint32_t deviceOffset = 0;
    uint64_t count = 1048576;
    uint32_t warmup = 1;
    uint32_t iters = 2;
};

struct ThreadContext {
    HcclComm comm = nullptr;
    uint32_t rankSize = 0;
    uint32_t rank = 0;
    uint32_t device = 0;
    uint64_t count = 0;
    uint32_t warmup = 0;
    uint32_t iters = 0;
    std::atomic<int> *failed = nullptr;
};

void Usage(const char *argv0)
{
    std::cerr << "Usage: " << argv0
              << " [--rank-size N] [--device-offset N] [--count N] [--warmup N] [--iters N]\n";
}

bool ParseUint32(const char *text, uint32_t *out)
{
    char *end = nullptr;
    unsigned long value = std::strtoul(text, &end, 10);
    if (end == text || *end != '\0') {
        return false;
    }
    *out = static_cast<uint32_t>(value);
    return true;
}

bool ParseUint64(const char *text, uint64_t *out)
{
    char *end = nullptr;
    unsigned long long value = std::strtoull(text, &end, 10);
    if (end == text || *end != '\0') {
        return false;
    }
    *out = static_cast<uint64_t>(value);
    return true;
}

bool ParseArgs(int argc, char **argv, Args *args)
{
    for (int i = 1; i < argc; ++i) {
        auto needValue = [&](const char *name) -> const char * {
            if (i + 1 >= argc) {
                std::cerr << "missing value for " << name << "\n";
                return nullptr;
            }
            return argv[++i];
        };
        if (std::strcmp(argv[i], "--rank-size") == 0) {
            const char *value = needValue(argv[i]);
            if (value == nullptr || !ParseUint32(value, &args->rankSize)) {
                return false;
            }
        } else if (std::strcmp(argv[i], "--device-offset") == 0) {
            const char *value = needValue(argv[i]);
            if (value == nullptr || !ParseUint32(value, &args->deviceOffset)) {
                return false;
            }
        } else if (std::strcmp(argv[i], "--count") == 0) {
            const char *value = needValue(argv[i]);
            if (value == nullptr || !ParseUint64(value, &args->count)) {
                return false;
            }
        } else if (std::strcmp(argv[i], "--warmup") == 0) {
            const char *value = needValue(argv[i]);
            if (value == nullptr || !ParseUint32(value, &args->warmup)) {
                return false;
            }
        } else if (std::strcmp(argv[i], "--iters") == 0) {
            const char *value = needValue(argv[i]);
            if (value == nullptr || !ParseUint32(value, &args->iters)) {
                return false;
            }
        } else if (std::strcmp(argv[i], "-h") == 0 || std::strcmp(argv[i], "--help") == 0) {
            Usage(argv[0]);
            std::exit(0);
        } else {
            std::cerr << "unknown argument: " << argv[i] << "\n";
            return false;
        }
    }
    return args->rankSize > 0 && args->count > 0;
}

#define CHECK_ACL(expr)                                                                           \
    do {                                                                                          \
        aclError ret = (expr);                                                                    \
        if (ret != ACL_SUCCESS) {                                                                 \
            std::cerr << "ACL error at " << __FILE__ << ":" << __LINE__ << " ret=" << ret << "\n"; \
            return 1;                                                                             \
        }                                                                                         \
    } while (0)

#define CHECK_HCCL(expr)                                                                               \
    do {                                                                                               \
        HcclResult ret = (expr);                                                                       \
        if (ret != HCCL_SUCCESS) {                                                                     \
            std::cerr << "HCCL error at " << __FILE__ << ":" << __LINE__ << " ret=" << ret << "\n"; \
            return 1;                                                                                  \
        }                                                                                              \
    } while (0)

int RunRank(ThreadContext ctx)
{
    void *sendBuf = nullptr;
    void *recvBuf = nullptr;
    void *hostBuf = nullptr;
    aclrtStream stream = nullptr;
    const size_t bytes = static_cast<size_t>(ctx.count * sizeof(float));

    auto fail = [&]() {
        if (ctx.failed != nullptr) {
            ctx.failed->store(1);
        }
        return 1;
    };

    aclError aclRet = aclrtSetDevice(static_cast<int32_t>(ctx.device));
    if (aclRet != ACL_SUCCESS) {
        std::cerr << "rank " << ctx.rank << " aclrtSetDevice(" << ctx.device << ") failed ret=" << aclRet << "\n";
        return fail();
    }
    if (aclrtMalloc(&sendBuf, bytes, ACL_MEM_MALLOC_HUGE_ONLY) != ACL_SUCCESS ||
        aclrtMalloc(&recvBuf, bytes, ACL_MEM_MALLOC_HUGE_ONLY) != ACL_SUCCESS ||
        aclrtMallocHost(&hostBuf, bytes) != ACL_SUCCESS) {
        std::cerr << "rank " << ctx.rank << " buffer allocation failed\n";
        return fail();
    }

    float *host = static_cast<float *>(hostBuf);
    for (uint64_t i = 0; i < ctx.count; ++i) {
        host[i] = static_cast<float>(ctx.rank + 1);
    }
    if (aclrtMemcpy(sendBuf, bytes, hostBuf, bytes, ACL_MEMCPY_HOST_TO_DEVICE) != ACL_SUCCESS) {
        std::cerr << "rank " << ctx.rank << " host-to-device copy failed\n";
        return fail();
    }

    if (aclrtCreateStream(&stream) != ACL_SUCCESS) {
        std::cerr << "rank " << ctx.rank << " aclrtCreateStream failed\n";
        return fail();
    }

    for (uint32_t i = 0; i < ctx.warmup; ++i) {
        if (HcclAllReduce(sendBuf, recvBuf, ctx.count, HCCL_DATA_TYPE_FP32, HCCL_REDUCE_SUM, ctx.comm, stream) !=
            HCCL_SUCCESS) {
            std::cerr << "rank " << ctx.rank << " warmup allreduce failed\n";
            return fail();
        }
    }
    if (aclrtSynchronizeStream(stream) != ACL_SUCCESS) {
        std::cerr << "rank " << ctx.rank << " warmup sync failed\n";
        return fail();
    }

    auto begin = std::chrono::steady_clock::now();
    for (uint32_t i = 0; i < ctx.iters; ++i) {
        if (HcclAllReduce(sendBuf, recvBuf, ctx.count, HCCL_DATA_TYPE_FP32, HCCL_REDUCE_SUM, ctx.comm, stream) !=
            HCCL_SUCCESS) {
            std::cerr << "rank " << ctx.rank << " measured allreduce failed\n";
            return fail();
        }
    }
    if (aclrtSynchronizeStream(stream) != ACL_SUCCESS) {
        std::cerr << "rank " << ctx.rank << " measured sync failed\n";
        return fail();
    }
    auto end = std::chrono::steady_clock::now();

    if (aclrtMemcpy(hostBuf, bytes, recvBuf, bytes, ACL_MEMCPY_DEVICE_TO_HOST) != ACL_SUCCESS) {
        std::cerr << "rank " << ctx.rank << " device-to-host copy failed\n";
        return fail();
    }
    const float expected = static_cast<float>((ctx.rankSize * (ctx.rankSize + 1)) / 2);
    if (host[0] != expected) {
        std::cerr << "rank " << ctx.rank << " verify failed got=" << host[0] << " expected=" << expected << "\n";
        return fail();
    }

    if (ctx.rank == 0) {
        double ms = std::chrono::duration<double, std::milli>(end - begin).count() / ctx.iters;
        std::cout << "Native HCCL AllReduce rank_size=" << ctx.rankSize << " count=" << ctx.count
                  << " warmup=" << ctx.warmup << " iters=" << ctx.iters << " avg_ms=" << ms << "\n";
    }

    if (stream != nullptr) {
        aclrtDestroyStream(stream);
    }
    if (sendBuf != nullptr) {
        aclrtFree(sendBuf);
    }
    if (recvBuf != nullptr) {
        aclrtFree(recvBuf);
    }
    if (hostBuf != nullptr) {
        aclrtFreeHost(hostBuf);
    }
    aclrtResetDevice(static_cast<int32_t>(ctx.device));
    return 0;
}

}  // namespace

int main(int argc, char **argv)
{
    Args args;
    if (!ParseArgs(argc, argv, &args)) {
        Usage(argv[0]);
        return 2;
    }

    CHECK_ACL(aclInit(nullptr));
    uint32_t deviceCount = 0;
    CHECK_ACL(aclrtGetDeviceCount(&deviceCount));
    if (args.deviceOffset + args.rankSize > deviceCount) {
        std::cerr << "requested rank-size/device-offset exceeds device count: rank_size=" << args.rankSize
                  << " device_offset=" << args.deviceOffset << " device_count=" << deviceCount << "\n";
        aclFinalize();
        return 2;
    }

    std::vector<int32_t> devices(args.rankSize);
    std::vector<HcclComm> comms(args.rankSize, nullptr);
    for (uint32_t rank = 0; rank < args.rankSize; ++rank) {
        devices[rank] = static_cast<int32_t>(args.deviceOffset + rank);
    }
    CHECK_HCCL(HcclCommInitAll(args.rankSize, devices.data(), comms.data()));

    std::atomic<int> failed(0);
    std::vector<std::thread> threads;
    std::vector<ThreadContext> contexts(args.rankSize);
    threads.reserve(args.rankSize);
    for (uint32_t rank = 0; rank < args.rankSize; ++rank) {
        contexts[rank].comm = comms[rank];
        contexts[rank].rankSize = args.rankSize;
        contexts[rank].rank = rank;
        contexts[rank].device = args.deviceOffset + rank;
        contexts[rank].count = args.count;
        contexts[rank].warmup = args.warmup;
        contexts[rank].iters = args.iters;
        contexts[rank].failed = &failed;
        threads.emplace_back(RunRank, contexts[rank]);
    }
    for (auto &thread : threads) {
        thread.join();
    }

    for (HcclComm comm : comms) {
        if (comm != nullptr) {
            HcclCommDestroy(comm);
        }
    }
    CHECK_ACL(aclFinalize());
    return failed.load() == 0 ? 0 : 1;
}
