/**
 * Copyright (c) 2025 Huawei Technologies Co., Ltd.
 * This program is free software, you can redistribute it and/or modify it under the terms and conditions of
 * CANN Open Software License Agreement Version 2.0 (the "License").
 * Please refer to the License for details. You may not use this file except in compliance with the License.
 * THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
 * INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
 * See LICENSE in the root of the software repository for the full text of the License.
 */

#include "all_gather_mesh_atomic.h"
#include "alg_template_register.h"
#include "task_semantic_scope.h"

namespace hccl {
AllGatherMeshAtomic::AllGatherMeshAtomic(const HcclDispatcher dispatcher)
    : AllGatherMesh(dispatcher)
{}

AllGatherMeshAtomic::~AllGatherMeshAtomic() {}

HcclResult AllGatherMeshAtomic::RunAllGather(const std::vector<LINK> &links, const std::vector<Slice> &outputSlices,
    const std::vector<Slice> &inputSlices)
{
    for (u32 round = 1; round < interRankSize_; round++) {
        u32 dstRank = BackwardRank(interRank_, interRankSize_, round);
        Stream& subStream = (round == interRankSize_ - 1) ? stream_ : meshStreams_[round - 1];
        {
            TaskSemanticScope semanticScope(MakeTaskSemanticTraceInfo(
                "allgather", 0, userRank_, interRankSize_, dstRank, "tx_ack_start", "link_tx_ack",
                links[dstRank]->GetRemoteRank(), TaskSemanticAlgorithm(), interRank_));
            CHK_RET(links[dstRank]->TxAck(subStream));
        }
        {
            TaskSemanticScope semanticScope(MakeTaskSemanticTraceInfo(
                "allgather", 0, userRank_, interRankSize_, interRank_, "rx_ack_start", "link_rx_ack",
                links[dstRank]->GetRemoteRank(), TaskSemanticAlgorithm(), interRank_));
            CHK_RET(links[dstRank]->RxAck(subStream));
        }
    }

    for (u32 round = 1; round < interRankSize_; round++) {
        u32 dstRank = BackwardRank(interRank_, interRankSize_, round);
        Stream& subStream = (round == interRankSize_ - 1) ? stream_ : meshStreams_[round - 1];
        profilerInput_.streamID = subStream.id();
        profilerInput_.planeID = round - 1;
        profilerInput_.step = HCCL_EXEC_STEP_NOT_SET;

        if (round == interRankSize_ - 1) {
            for (u32 signalIndex = 0; signalIndex < interRankSize_ - 2; signalIndex++) { // rankSize-2: stream num
                    CHK_RET(LocalNotify::Wait(subStream, dispatcher_, (*meshSignal_)[signalIndex], profilerInput_.stage));
            }
            // 为子图增加一个从stream到主stream的附着点
            DeviceMem src = DeviceMem::create(inputMem_.ptr(), 0);
            DeviceMem dst = DeviceMem::create(outputMem_.ptr(), 0);
            CHK_RET(HcclD2DMemcpyAsync(dispatcher_, dst, src, stream_));
            for (u32 signalIndex = 0; signalIndex < interRankSize_ - 2; signalIndex++) { // rankSize-2: stream num
                CHK_RET(LocalNotify::Post(subStream, dispatcher_, (*meshSignalAux_)[signalIndex],
                    profilerInput_.stage));
            }
        } else {
            u32 signalIndex = round - 1;
            CHK_RET(LocalNotify::Post(subStream, dispatcher_, (*meshSignal_)[signalIndex],
                profilerInput_.stage));
            CHK_RET(LocalNotify::Wait(subStream, dispatcher_, (*meshSignalAux_)[signalIndex], profilerInput_.stage));
        }
        // 本rank要收数据
        void *srcMemPtr = nullptr;
        // 从对端的input内存拿数据，input==output也没有关系
        CHK_RET(links[dstRank]->GetRemoteMem(UserMemType::OUTPUT_MEM, &srcMemPtr));
        DeviceMem srcDevMem(static_cast<s8 *>(srcMemPtr) + baseOffset_ + inputSlices[dstRank].offset,
            inputSlices[dstRank].size);
        DeviceMem dstDevMem = outputMem_.range(outputSlices[dstRank].offset, outputSlices[dstRank].size);
        {
            TaskSemanticScope semanticScope(MakeTaskSemanticTraceInfo(
                "allgather", 0, userRank_, interRankSize_, dstRank, nullptr, nullptr,
                links[dstRank]->GetRemoteRank(), TaskSemanticAlgorithm(), interRank_));
            TaskSemanticEventScope eventScope("rx_payload_copy_start", "link_rx_payload_copy");
            CHK_RET(HcclD2DMemcpyAsync(dispatcher_, dstDevMem, srcDevMem, subStream,
                links[dstRank]->GetRemoteRank(), links[dstRank]->GetLinkType()));
        }
        {
            TaskSemanticScope semanticScope(MakeTaskSemanticTraceInfo(
                "allgather", 0, userRank_, interRankSize_, dstRank, nullptr, nullptr,
                links[dstRank]->GetRemoteRank(), TaskSemanticAlgorithm(), interRank_));
            TaskSemanticEventScope eventScope("tx_data_signal_start", "link_tx_data_signal");
            CHK_RET(links[dstRank]->TxDataSignal(subStream));
        }
        {
            TaskSemanticScope semanticScope(MakeTaskSemanticTraceInfo(
                "allgather", 0, userRank_, interRankSize_, interRank_, nullptr, nullptr,
                links[dstRank]->GetRemoteRank(), TaskSemanticAlgorithm(), interRank_));
            TaskSemanticEventScope eventScope("rx_data_signal_start", "link_rx_data_signal");
            CHK_RET(links[dstRank]->RxDataSignal(subStream));
        }
    }

    CHK_RET(AlgTemplateBase::ExecEmptyTask(inputMem_, outputMem_, stream_, dispatcher_));
    return HCCL_SUCCESS;
}
REGISTER_TEMPLATE(TemplateType::TEMPLATE_ALL_GATHER_MESH_ATOMIC, AllGatherMeshAtomic);
} // namespace hccl
