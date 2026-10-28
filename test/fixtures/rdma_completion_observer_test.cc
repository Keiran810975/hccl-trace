#include <cassert>
#include <cstdarg>
#include <cstdio>
#include <cstdint>
#include <string>

// Minimal ABI-shaped fixture, not a CANN/verbs hardware test.
enum { IBV_WR_RDMA_WRITE = 0, IBV_WR_RDMA_WRITE_WITH_IMM = 1, IBV_WR_SEND = 2,
       IBV_WR_SEND_WITH_IMM = 3, IBV_WR_RDMA_READ = 4 };
struct ibv_cq {};
struct ibv_qp { ibv_cq *send_cq; uint32_t qp_num; };
struct ibv_sge { uint64_t addr; uint32_t length; uint32_t lkey; };
struct ibv_send_wr {
    uint64_t wr_id;
    ibv_send_wr *next;
    ibv_sge *sg_list;
    int num_sge;
    int opcode;
    unsigned int send_flags;
};
struct ibv_wc { uint64_t wr_id; unsigned int status; int opcode; uint32_t qp_num; };

void TraceLog(const char *format, ...)
{
    va_list args;
    va_start(args, format);
    vprintf(format, args);
    va_end(args);
    putchar('\n');
}
#define HCCL_INFO(...) TraceLog(__VA_ARGS__)
#include "rdma_completion_observer.h"

int main()
{
    ibv_cq cq;
    ibv_qp qp{&cq, 7};
    ibv_sge sg{0, 2097152, 0};
    ibv_send_wr read{UINT64_MAX, nullptr, &sg, 1, IBV_WR_RDMA_READ, 2};
    const auto before = hccl::CurrentRdmaCompletionContext();
    {
        hccl::RdmaCompletionContextScope scope(3, 1, 42, "data_read_and_ack");
        hccl::ObserveRdmaPost(&qp, &read, nullptr, 0, 1000, 1100);
        if (hccl::RdmaCompletionTraceEnabled()) {
            assert(hccl::CurrentRdmaCompletionContext().localRank == 3);
        }
    }
    assert(hccl::CurrentRdmaCompletionContext().localRank == before.localRank);
    ibv_wc wc{UINT64_MAX, 0, 2, 7};
    hccl::ObserveRdmaCompletions(&cq, &wc, 1, 2000);
    assert(read.send_flags == 2 && read.next == nullptr && wc.status == 0);

    ibv_send_wr second{2, nullptr, &sg, 1, IBV_WR_SEND, 2};
    ibv_send_wr first{1, &second, &sg, 1, IBV_WR_RDMA_WRITE, 0};
    hccl::ObserveRdmaPost(&qp, &first, &second, 12, 3000, 3100);
    wc = {1, 5, 1, 7};
    hccl::ObserveRdmaCompletions(&cq, &wc, 1, 4000);
    assert(first.send_flags == 0 && first.next == &second && second.send_flags == 2);
    first.num_sge = -1;
    first.next = nullptr;
    hccl::ObserveRdmaPost(&qp, &first, nullptr, 0, 5000, 5100);
    return 0;
}
