/**
 * Copyright (c) 2026 Huawei Technologies Co., Ltd.
 * This program is free software under the CANN Open Software License Agreement Version 2.0.
 * See LICENSE in the root of the software repository for the full text of the License.
 */
#ifndef HCCL_RDMA_COMPLETION_OBSERVER_H
#define HCCL_RDMA_COMPLETION_OBSERVER_H

#include <chrono>
#include <cstdint>
#include <cstdlib>
#include <unistd.h>

namespace hccl {
// Observe only the application's existing post/poll calls. Never consume an
// additional CQE, change send flags, or turn a device doorbell into a completion.
inline bool RdmaCompletionTraceEnabled()
{
    static const bool enabled = []() {
        const char *value = std::getenv("HCCL_RDMA_COMPLETION_TRACE");
        return value != nullptr && value[0] == '1' && value[1] == '\0';
    }();
    return enabled;
}

inline uint64_t RdmaCompletionClockNs()
{
    return static_cast<uint64_t>(std::chrono::duration_cast<std::chrono::nanoseconds>(
        std::chrono::steady_clock::now().time_since_epoch()).count());
}

inline uint64_t RdmaCompletionProcessEpoch()
{
    static const uint64_t epoch = RdmaCompletionClockNs();
    return epoch;
}

struct RdmaCompletionContext {
    int64_t localRank{-1};
    int64_t peerRank{-1};
    uint64_t messageId{0};
    const char *role{"unknown"};
};

inline RdmaCompletionContext &CurrentRdmaCompletionContext()
{
    static thread_local RdmaCompletionContext context;
    return context;
}

class RdmaCompletionContextScope {
public:
    RdmaCompletionContextScope(int64_t localRank, int64_t peerRank, uint64_t messageId, const char *role)
        : previous_(CurrentRdmaCompletionContext())
    {
        if (RdmaCompletionTraceEnabled()) {
            CurrentRdmaCompletionContext() = {static_cast<int64_t>(localRank),
                static_cast<int64_t>(peerRank), messageId, role};
        }
    }
    ~RdmaCompletionContextScope() { CurrentRdmaCompletionContext() = previous_; }
    RdmaCompletionContextScope(const RdmaCompletionContextScope &) = delete;
    RdmaCompletionContextScope &operator=(const RdmaCompletionContextScope &) = delete;
private:
    RdmaCompletionContext previous_;
};

inline const char *RdmaCompletionOpcode(int opcode)
{
    switch (opcode) {
        case IBV_WR_SEND:
        case IBV_WR_SEND_WITH_IMM: return "send";
        case IBV_WR_RDMA_WRITE:
        case IBV_WR_RDMA_WRITE_WITH_IMM: return "write";
        case IBV_WR_RDMA_READ: return "read";
        default: return "other";
    }
}

inline void ObserveRdmaPost(struct ibv_qp *qp, const struct ibv_send_wr *first,
    const struct ibv_send_wr *bad, int result, uint64_t beginNs, uint64_t returnNs)
{
    if (!RdmaCompletionTraceEnabled() || qp == nullptr || beginNs == 0) {
        return;
    }
    constexpr unsigned int MAX_CHAIN = 1024;
    constexpr int MAX_SGE = 1024;
    bool badFound = false;
    unsigned int count = 0;
    auto *end = first;
    for (; end != nullptr && count < MAX_CHAIN; end = end->next, ++count) {
        badFound = badFound || end == bad;
    }
    if (end != nullptr) {
        HCCL_INFO("[HcclRdmaCompletion] schema_version[1] stage[gap] reason[wr_chain_limit]");
    }
    bool afterBad = false;
    const auto context = CurrentRdmaCompletionContext();
    count = 0;
    for (auto *wr = first; wr != nullptr && count < MAX_CHAIN; wr = wr->next, ++count) {
        afterBad = afterBad || wr == bad;
        const int accepted = result == 0 ? 1 : (badFound ? (afterBad ? 0 : 1) : -1);
        uint64_t bytes = 0;
        if (wr->num_sge < 0 || wr->num_sge > MAX_SGE || (wr->num_sge && wr->sg_list == nullptr)) {
            HCCL_INFO("[HcclRdmaCompletion] schema_version[1] stage[gap] reason[invalid_sge]");
            continue;
        }
        for (int index = 0; index < wr->num_sge; ++index) {
            bytes += wr->sg_list[index].length;
        }
        HCCL_INFO("[HcclRdmaCompletion] schema_version[1] stage[post] backend[ibverbs] "
            "clock[process_steady_ns] process_epoch[%llu] pid[%u] cq_id[%llu] qp_num[%u] wr_id[%llu] "
            "opcode[%s] raw_opcode[%d] bytes[%llu] accepted[%d] result[%d] start_ns[%llu] "
            "post_return_ns[%llu] local_rank[%lld] peer_rank[%lld] message_id[%llu] role[%s] send_flags[%u]",
            static_cast<unsigned long long>(RdmaCompletionProcessEpoch()), static_cast<unsigned int>(getpid()),
            static_cast<unsigned long long>(reinterpret_cast<uintptr_t>(qp->send_cq)), qp->qp_num,
            static_cast<unsigned long long>(wr->wr_id), RdmaCompletionOpcode(wr->opcode),
            static_cast<int>(wr->opcode), static_cast<unsigned long long>(bytes), accepted, result,
            static_cast<unsigned long long>(beginNs), static_cast<unsigned long long>(returnNs),
            static_cast<long long>(context.localRank), static_cast<long long>(context.peerRank),
            static_cast<unsigned long long>(context.messageId), context.role, static_cast<unsigned int>(wr->send_flags));
    }
}

inline void ObserveRdmaCompletions(struct ibv_cq *cq, const struct ibv_wc *wc, int count, uint64_t observedNs)
{
    if (!RdmaCompletionTraceEnabled() || cq == nullptr || wc == nullptr) {
        return;
    }
    for (int index = 0; index < count; ++index) {
        HCCL_INFO("[HcclRdmaCompletion] schema_version[1] stage[cqe] backend[ibverbs] "
            "clock[process_steady_ns] process_epoch[%llu] pid[%u] cq_id[%llu] qp_num[%u] wr_id[%llu] "
            "wc_opcode[%d] status[%u] observed_ns[%llu]",
            static_cast<unsigned long long>(RdmaCompletionProcessEpoch()), static_cast<unsigned int>(getpid()),
            static_cast<unsigned long long>(reinterpret_cast<uintptr_t>(cq)), wc[index].qp_num,
            static_cast<unsigned long long>(wc[index].wr_id), static_cast<int>(wc[index].opcode),
            static_cast<unsigned int>(wc[index].status), static_cast<unsigned long long>(observedNs));
    }
}
} // namespace hccl
#endif
