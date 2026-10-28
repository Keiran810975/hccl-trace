// Copyright (c) 2026 Huawei Technologies Co., Ltd.
// Licensed under CANN Open Software License Agreement Version 2.0.
// One process, two device threads, one separate HCCL communication domain.
#include <acl/acl.h>
#include <hccl/hccl.h>
#include <hccl/hccl_types.h>
#include <atomic>
#include <chrono>
#include <condition_variable>
#include <cstdint>
#include <fstream>
#include <iostream>
#include <mutex>
#include <stdexcept>
#include <string>
#include <thread>
#include <vector>
#include <time.h>
#include <unistd.h>

namespace {
uint64_t Now(clockid_t clock)
{
    timespec t{};
    if (clock_gettime(clock, &t) != 0) throw std::runtime_error("clock_gettime failed");
    return static_cast<uint64_t>(t.tv_sec) * 1000000000ULL + t.tv_nsec;
}
bool Exists(const std::string &path) { return static_cast<bool>(std::ifstream(path)); }
void Touch(const std::string &path)
{
    std::ofstream file(path);
    if (!file) throw std::runtime_error("cannot signal controller");
}
void Check(int result, const char *call = "ACL/HCCL")
{
    if (result != 0) throw std::runtime_error(std::string(call) + " error " + std::to_string(result));
}

class Rendezvous {
    std::mutex mutex;
    std::condition_variable cv;
    int count = 0, generation = 0;
    bool aborted = false;
public:
    void Abort() { std::lock_guard<std::mutex> lock(mutex); aborted = true; cv.notify_all(); }
    void Wait()
    {
        std::unique_lock<std::mutex> lock(mutex);
        if (aborted) throw std::runtime_error("peer failed");
        int observed = generation;
        if (++count == 2) { count = 0; ++generation; cv.notify_all(); return; }
        if (!cv.wait_for(lock, std::chrono::seconds(180), [&] { return generation != observed || aborted; }) || aborted)
            throw std::runtime_error("local endpoint rendezvous failed");
    }
};
}

int main(int argc, char **argv)
{
    if (argc != 5 && argc != 6) { std::cerr << "device-a device-b buffer-mib control-directory [--defer-finalize]\n"; return 2; }
    const bool deferFinalize = argc == 6 && std::string(argv[5]) == "--defer-finalize";
    if (argc == 6 && !deferFinalize) return 2;
    int32_t devices[2] = {std::stoi(argv[1]), std::stoi(argv[2])};
    uint64_t mib = std::stoull(argv[3]);
    if (devices[0] < 0 || devices[1] < 0 || devices[0] == devices[1] || mib < 32 || mib > 256) return 2;
    std::string directory(argv[4]);
    HcclComm comms[2] = {nullptr, nullptr};
    Rendezvous gate;
    std::atomic<bool> failed(false), running(false);
    uint64_t operations = 0, started = 0, finished = 0, finalizeAuthorized = 0;
    try {
        Check(aclInit(nullptr));
        Check(aclrtSetDevice(devices[0]), "aclrtSetDevice before communication initialization");
        Check(HcclCommInitAll(2, devices, comms), "HcclCommInitAll");
        auto endpoint = [&](int rank) {
            void *send = nullptr, *recv = nullptr;
            aclrtStream stream = nullptr;
            const size_t bytes = mib * 1024 * 1024;
            std::vector<float> host(bytes / sizeof(float), static_cast<float>(rank + 1));
            try {
                Check(aclrtSetDevice(devices[rank]));
                Check(aclrtMalloc(&send, bytes, ACL_MEM_MALLOC_HUGE_FIRST));
                Check(aclrtMalloc(&recv, bytes, ACL_MEM_MALLOC_HUGE_FIRST));
                Check(aclrtMemcpy(send, bytes, host.data(), bytes, ACL_MEMCPY_HOST_TO_DEVICE));
                Check(aclrtCreateStream(&stream));
                auto operation = [&] {
                    Check(HcclAllReduce(send, recv, host.size(), HCCL_DATA_TYPE_FP32, HCCL_REDUCE_SUM, comms[rank], stream));
                    Check(aclrtSynchronizeStream(stream));
                };
                operation();
                gate.Wait();
                const uint64_t deadline = Now(CLOCK_MONOTONIC_RAW) + 1800ULL * 1000000000ULL;
                if (rank == 0) {
                    Touch(directory + "/ready");
                    while (!Exists(directory + "/start") && !Exists(directory + "/stop")) {
                        if (Now(CLOCK_MONOTONIC_RAW) > deadline) throw std::runtime_error("start timeout");
                        std::this_thread::sleep_for(std::chrono::milliseconds(5));
                    }
                    started = Now(CLOCK_MONOTONIC_RAW);
                }
                gate.Wait();
                while (true) {
                    if (rank == 0) running = !Exists(directory + "/stop") && Now(CLOCK_MONOTONIC_RAW) < deadline;
                    gate.Wait();
                    if (!running) break;
                    operation();
                    gate.Wait();
                    if (rank == 0) { ++operations; if (operations == 1) Touch(directory + "/active"); }
                    gate.Wait();
                }
                gate.Wait();
                if (rank == 0) {
                    finished = Now(CLOCK_MONOTONIC_RAW);
                    if (deferFinalize) {
                        std::ofstream window(directory + "/activity-window.json");
                        window << "{\"started_raw_ns\":" << started << ",\"finished_raw_ns\":" << finished
                               << ",\"operations\":" << operations << ",\"validation_status\":\"pending\"}\n";
                        window.close();
                        if (!window) throw std::runtime_error("cannot persist activity window");
                        Touch(directory + "/paused");
                    }
                }
                gate.Wait();
                if (deferFinalize) {
                    while (!Exists(directory + "/finalize")) {
                        if (Now(CLOCK_MONOTONIC_RAW) > deadline) throw std::runtime_error("finalize timeout");
                        std::this_thread::sleep_for(std::chrono::milliseconds(10));
                    }
                }
                if (rank == 0) finalizeAuthorized = Now(CLOCK_MONOTONIC_RAW);
                gate.Wait();
                Check(aclrtMemcpy(host.data(), bytes, recv, bytes, ACL_MEMCPY_DEVICE_TO_HOST));
                for (float value : host) if (value != 3.0f) throw std::runtime_error("background numerical mismatch");
                if (rank == 0) {
                    if (!operations || !Exists(directory + "/stop")) throw std::runtime_error("missing explicit active window/stop");
                }
            } catch (const std::exception &error) {
                failed = true; gate.Abort(); std::cerr << "endpoint " << rank << ": " << error.what() << '\n';
            }
            if (stream) aclrtDestroyStream(stream);
            if (send) aclrtFree(send);
            if (recv) aclrtFree(recv);
        };
        std::thread first(endpoint, 0), second(endpoint, 1);
        first.join(); second.join();
        for (HcclComm comm : comms) if (comm) Check(HcclCommDestroy(comm));
        Check(aclFinalize());
        if (failed) return 1;
        std::ofstream output(directory + "/result.json");
        output << "{\"kind\":\"communication\",\"pid\":" << getpid()
               << ",\"process_count\":1,\"endpoint_threads\":2,\"operations\":" << operations
               << ",\"started_raw_ns\":" << started << ",\"finished_raw_ns\":" << finished
               << ",\"finalize_deferred\":" << (deferFinalize ? "true" : "false")
               << ",\"finalize_authorized_raw_ns\":" << finalizeAuthorized
               << ",\"max_error\":0,\"status\":\"completed_not_proof_of_contention\"}\n";
        return output ? 0 : 1;
    } catch (const std::exception &error) { std::cerr << error.what() << '\n'; return 1; }
}
