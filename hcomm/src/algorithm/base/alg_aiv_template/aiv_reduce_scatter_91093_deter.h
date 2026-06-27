/**
 * Copyright (c) 2025 Huawei Technologies Co., Ltd.
 * This program is free software, you can redistribute it and/or modify it under the terms and conditions of
 * CANN Open Software License Agreement Version 2.0 (the "License").
 * Please refer to the License for details. You may not use this file except in compliance with the License.
 * THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
 * INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
 * See LICENSE in the root of the software repository for the full text of the License.
 */

#include "aiv_communication_base.h"
#include "aiv_crossnode_91093_base.h"

using namespace AscendC;

class AivReduceScatter91093Deter : public AivCrossNode91093Base {
public:
    __aicore__ inline AivReduceScatter91093Deter() {}

    template<typename T>
    __aicore__ inline void InitDataCopyOffset(uint64_t perRankBufferCount, uint64_t len);

    __aicore__ inline int64_t GetDeterministicRankOffset(int64_t x);
    __aicore__ inline int64_t GetDeterministicRank(int64_t x);

    template<typename T>
    __aicore__ inline void Process(GM_ADDR buffIn0, GM_ADDR buffOut0, GM_ADDR commInfoAddr, GM_ADDR input,
        GM_ADDR output, int32_t tag, uint64_t bufferSize, uint64_t len);
};

template<typename T>
__aicore__ inline void AivReduceScatter91093Deter::InitDataCopyOffset(uint64_t perRankBufferCount, uint64_t len)
{
    // 以下根据不同情况，计算每个aiv核的数据搬运参数
    // 当rankSize大于总aiv核数时，使用1个aiv服务一个对端，需要多次通信
    if (rankSize_ > blockdim_) {
        CalcNumTargetsAndTargetRanksDeter();

        blockNumPerGroup = 1;
        blockIdxInGroup = 0;
        if (len <= perRankBufferCount) { // ccl够用，只需要搬一轮的情况
            countMid = 0;
            countTail = len;
        } else if (len % perRankBufferCount == 0) { // ccl不够用，要搬多轮的情况1: 能整除
            countMid = perRankBufferCount;
            countTail = perRankBufferCount;
        } else { // ccl不够用，要搬多轮的情况2: 不能整除
            countMid = perRankBufferCount;
            countTail = len % perRankBufferCount;
        }
        blockOffsetMid = 0;
        blockOffsetTail = 0;
        flagOffsetInGroup = 0;
        countPerCore = len;
        blockOffset = 0;
        groupMid_ = countMid;
        groupTail_ = countTail;
    // 当rankSize小于等于总aiv核数时，根据ranksize和数据量大小选择使用多个aiv服务一个对端（多核并行），只需一次通信
    } else {
        numTargets = 1;
        blockNumPerGroup = blockdim_ / rankSize_; // 多少个aiv服务一个rank
        targetRanks[0] = GetBlockIdx() / blockNumPerGroup;

        uint32_t padCount = UB_ALIGN_SIZE / sizeof(T);
        blockIdxInGroup = GetBlockIdx() % blockNumPerGroup;

        if (len <= perRankBufferCount) { // ccl够用，只需要搬一轮的情况
            countMid = 0;
            blockOffsetMid = 0;
            groupMid_ = 0;
            CalCountAndBlockOffset(len, blockNumPerGroup, blockIdxInGroup, padCount, countTail, blockOffsetTail);
            groupTail_ = len;
        } else if (len % perRankBufferCount == 0) { // ccl不够用，要搬多轮的情况1: 能整除
            CalCountAndBlockOffset(perRankBufferCount, blockNumPerGroup, blockIdxInGroup, padCount, countMid, blockOffsetMid);
            countTail = countMid;
            blockOffsetTail = blockOffsetMid;
            groupMid_ = perRankBufferCount;
            groupTail_ = groupMid_;
        } else { // ccl不够用，要搬多轮的情况2: 不能整除
            CalCountAndBlockOffset(perRankBufferCount, blockNumPerGroup, blockIdxInGroup, padCount, countMid, blockOffsetMid);
            uint64_t remainLen = len % perRankBufferCount;
            CalCountAndBlockOffset(remainLen, blockNumPerGroup, blockIdxInGroup, padCount, countTail, blockOffsetTail);
            groupMid_ = perRankBufferCount;
            groupTail_ = remainLen;
        }
        flagOffsetInGroup = blockIdxInGroup * FLAG_SIZE;
        CalCountAndBlockOffset(len, blockNumPerGroup, blockIdxInGroup, padCount, countPerCore, blockOffset);
    }
}

__aicore__ inline int64_t AivReduceScatter91093Deter::GetDeterministicRankOffset(int64_t x)
{
    int64_t tmp = 1;
    while(!(x & 1)) {
        x >>= 1;
        tmp <<= 1;
    }
    return tmp;
}

__aicore__ inline int64_t AivReduceScatter91093Deter::GetDeterministicRank(int64_t x)
{
    int64_t tmp = 1;
    while(DOUBLE*tmp <x){
        tmp <<=1;
    }
    return tmp;
}

template<typename T>
__aicore__ inline void AivReduceScatter91093Deter::Process(GM_ADDR buffIn0, GM_ADDR buffOut0, GM_ADDR commInfoAddr,
    GM_ADDR input, GM_ADDR output, int32_t tag, uint64_t avgBufferCount, uint64_t len)
{
    TQue<AscendC::TPosition::VECIN, 1> syncQue;
    GlobalTensor<int32_t> syncGlobal;
    GlobalTensor<int32_t> syncGlobalSecond;
    uint32_t syncBufferSize = blockdim_ * 32;
    LocalTensor<int32_t> workLocal;

    pipe.InitBuffer(syncQue, 1, syncBufferSize);
    syncGlobal.SetGlobalBuffer(reinterpret_cast<__gm__ int32_t*>(buffOut0 + SYNCALL_BUFF_START), syncBufferSize);
    syncGlobalSecond.SetGlobalBuffer(reinterpret_cast<__gm__ int32_t*>(buffOut0 + SYNCALL_BUFF_START + syncBufferSize), syncBufferSize);

    __gm__ T *inputGM = (__gm__ T *)input;
    __gm__ T *outputGM = (__gm__ T *)output;
    __gm__ T *cclGMSelf = (__gm__ T *)buffIn0;

    GlobalTensor<uint64_t> bufferArgsGT;
    __gm__ uint64_t *buffersGmAddr = (__gm__ uint64_t *)(commInfoAddr);
    bufferArgsGT.SetGlobalBuffer(buffersGmAddr, FLAG_SIZE * rankSize_ / sizeof(uint64_t));
    GM_ADDR buffersIn[MAX_TARGET_NUM] = {};
    GM_ADDR buffersOut[MAX_TARGET_NUM] = {};

    for (uint32_t i = 0; i < numTargets; i++) {
        uint32_t targetRank = targetRanks[i];
        DataCopy(bufferArgsTensor[i * 4], bufferArgsGT[2 * targetRank], 4); // buffersIn buffersOut
    }
    SyncFunc<HardEvent::MTE2_S>();
    for (uint32_t i = 0; i < numTargets; i++) {
        uint32_t curIdx = i * 4;
        buffersIn[i] = (GM_ADDR)(bufferArgsTensor.GetValue(curIdx));
        buffersOut[i] = (GM_ADDR)(bufferArgsTensor.GetValue(curIdx + 1));
    }
    PipeBarrier<PIPE_ALL>();

    if (clearEnable_ == 1) {
        workLocal = syncQue.AllocTensor<int32_t>();
        Barrier(buffersOut, 1);
        SyncAll(syncGlobal, workLocal, blockdim_);
        ClearGM();
        Barrier(buffersOut, 2);
        SyncAll(syncGlobalSecond, workLocal, blockdim_);
	    syncQue.FreeTensor(workLocal);
        PipeBarrier<PIPE_ALL>();
    }
    
    int32_t curTag = (tag << TAG_MOVE_LEFT_BITS);
    bool pingpong = false;
    uint64_t halfBufferCount = avgBufferCount*rankSize_;
    uint64_t curOffset = 0;
    uint64_t curCount; // 每个Aiv搬运的数量
    uint64_t curBlockOffset; 
    uint64_t curGroupCount; // 每组AIV搬运的数量

    uint32_t bufferLoopNum = (len + avgBufferCount - 1) / avgBufferCount;
    for (uint32_t loop = 0; loop < bufferLoopNum; loop++) {
	
        if (loop == bufferLoopNum - 1) { // 最后一轮ccl填充
            curCount = countTail;
            curBlockOffset = blockOffsetTail;
            curGroupCount = groupTail_;
        } else {
            curCount = countMid;
            curBlockOffset = blockOffsetMid;
            curGroupCount = groupMid_;
        }

        workLocal = syncQue.AllocTensor<int32_t>();
        // step1 本端 input -> 本端 ccl 
        for (uint32_t i = 0; i < numTargets; i++) {
            uint64_t localSendOffset = len * targetRanks[i];
            uint64_t localRecvOffset = avgBufferCount * targetRanks[i];
            CpGM2GM(cclGMSelf + localRecvOffset + curBlockOffset, inputGM + localSendOffset + curOffset + curBlockOffset, curCount);

            PipeBarrier<PIPE_ALL>();
        }
       
        PipeBarrier<PIPE_ALL>();
        BatchRecordWait(curTag, buffersOut, AivNotifyType::ACK);
        PipeBarrier<PIPE_ALL>();

        // step2 对端 ccl -> 本端 ccl 
        for (uint32_t i = 0; i < numTargets; i++) {
            __gm__ T *cclGMOther = (__gm__ T *)(buffersIn[i]);
            uint64_t remoteSendOffset = avgBufferCount * rank_;
            uint64_t localRecvOffset = avgBufferCount * targetRanks[i];
            CpGM2GM(cclGMSelf + halfBufferCount + localRecvOffset + curBlockOffset, cclGMOther + remoteSendOffset + curBlockOffset, curCount);
            PipeBarrier<PIPE_ALL>();
        }

        PipeBarrier<PIPE_ALL>();
        BatchRecordWait(curTag, buffersOut, AivNotifyType::DataSignal);

        // step3 本端ccl local reduce
        // step3.1 每个核先处理自己targets, 串行加
	
        for (int32_t i = numTargets-1; i >= 1; --i) {
            uint64_t preDataOffset = avgBufferCount * targetRanks[0];
            uint64_t curDataOffset = avgBufferCount * targetRanks[i];
            CpGM2GM(cclGMSelf + halfBufferCount + preDataOffset, 
                    cclGMSelf + halfBufferCount + curDataOffset, curCount, true, reduceOp_);
            PipeBarrier<PIPE_ALL>();
        }
	
        // 卡内每个核同步一次
        PipeBarrier<PIPE_ALL>();
        SyncAll(syncGlobal, workLocal, blockdim_);
        PipeBarrier<PIPE_ALL>();
        
        // step3.2 归约为numReduce份数据的reduce
        uint32_t numReduce = rankSize_ < usedBlockNum_ ? rankSize_ : usedBlockNum_;
        if (GetBlockIdx() < numReduce && GetBlockIdx() != 0){
            int x = GetBlockIdx();
            int64_t multiple = GetDeterministicRankOffset(x);
            int64_t target = x - multiple;
    
            if (x & 1) {
                CpGM2GM<T>(cclGMSelf + halfBufferCount + avgBufferCount * target, cclGMSelf + halfBufferCount + avgBufferCount * x, 
                            curGroupCount, true, reduceOp_);
                PipeBarrier<PIPE_ALL>();

                SetSyncRecord(curTag, flagAddrSelf_, 1, x, pingpong);
            } else {
                int64_t multipleTemp = multiple / DOUBLE;
                WaitSyncFlag(curTag, flagAddrSelf_, 1, x - multipleTemp, pingpong); 

                while (x + multipleTemp >= numReduce) {
                    multipleTemp /= DOUBLE;
                }
                if (multipleTemp >= 1) {
                    WaitSyncFlag(curTag, flagAddrSelf_, 1, x + multipleTemp, pingpong);
                }

                CpGM2GM<T>(cclGMSelf + halfBufferCount + avgBufferCount * target, cclGMSelf + halfBufferCount + avgBufferCount * x, 
                            curGroupCount, true, reduceOp_);
                PipeBarrier<PIPE_ALL>();

                SetSyncRecord(curTag, flagAddrSelf_, 1, x, pingpong);
            }
        }

        // step4 本端ccl -> 本端 output
        bool case1 = rankSize_ > blockdim_ && GetBlockIdx() == blockdim_ - 1; // 单核
        bool case2 = rankSize_ <= blockdim_ && targetRanks[0] == rank_; // 单核
        if (case1 || case2){
            int64_t waitBlock = GetDeterministicRank(numReduce);
            WaitSyncFlag(curTag, flagAddrSelf_, 1, waitBlock, pingpong);
            CpGM2GM(outputGM + curOffset + curBlockOffset, cclGMSelf + halfBufferCount + curBlockOffset, curCount);
        }

        // 尾同步 
        if(bufferLoopNum > 1){
            PipeBarrier<PIPE_ALL>();
            SyncAll(syncGlobalSecond, workLocal, blockdim_);
            PipeBarrier<PIPE_ALL>();
        }

        syncQue.FreeTensor(workLocal);
        curTag += 1;
        curOffset += avgBufferCount;   
    }
}

template<typename T>
__aicore__ inline void aiv_reduce_scatter_91093_deter(KERNEL_ARGS_DEF_A3)
{
    AivReduceScatter91093Deter op;
  
    // 每张卡的CCLBuffer大小为bufferSize, 平均分给ranksize*2块，每块的大小为avgBufferCount
    uint64_t avgBufferCount = (uint64_t)bufferSize / 2 / rankSize / sizeof(T);

    op.InitDeter<T>(buffOut0, rank, rankSize, reduceOp, tag, false);
    op.InitDataCopyOffset<T>(avgBufferCount, len);
    op.InitOpCounter(headCountMem, tailCountMem, addOneMem, SIZE_OF_INT32, isEnableCounter);
    op.HeadCounter();
    op.Process<T>(buffIn0, buffOut0, buffOut1, input, output, tag, avgBufferCount, len);
    op.TailCounter();
}

__aicore__ inline void sk_reduce_scatter_deter(SUPERKERNEL_ARGS_DEF)
{
    AivReduceScatter91093Deter op;
    
   op.InitSuperKernel(hiddenInput, false);
    // 每张卡的CCLBuffer大小为bufferSize, 平均分给ranksize*2块，每块的大小为avgBufferCount
    uint64_t avgBufferCount = op.len_;
   
    if (op.dataType_ == HcclDataType::HCCL_DATA_TYPE_INT8) {
        op.InitDataCopyOffset<int8_t>(avgBufferCount, op.len_);
        op.Process<int8_t>(op.dataAddrSelf_, op.flagAddrSelf_, op.commAddr_, input, output, op.tag_, avgBufferCount, op.len_);
    } else if (op.dataType_ == HcclDataType::HCCL_DATA_TYPE_INT16) {
        op.InitDataCopyOffset<int16_t>(avgBufferCount, op.len_);
        op.Process<int16_t>(op.dataAddrSelf_, op.flagAddrSelf_, op.commAddr_, input, output, op.tag_, avgBufferCount, op.len_);
    } else if (op.dataType_ ==HCCL_DATA_TYPE_INT32) {
        op.InitDataCopyOffset<int32_t>(avgBufferCount, op.len_);
        op.Process<int32_t>(op.dataAddrSelf_, op.flagAddrSelf_, op.commAddr_, input, output, op.tag_, avgBufferCount, op.len_);
    } else if (op.dataType_ == HCCL_DATA_TYPE_FP16) {
        op.InitDataCopyOffset<half>(avgBufferCount, op.len_);
        op.Process<half>(op.dataAddrSelf_, op.flagAddrSelf_, op.commAddr_, input, output, op.tag_, avgBufferCount, op.len_);
    } else if (op.dataType_ == HCCL_DATA_TYPE_FP32) {
        op.InitDataCopyOffset<float>(avgBufferCount, op.len_);
        op.Process<float>(op.dataAddrSelf_, op.flagAddrSelf_, op.commAddr_, input, output, op.tag_, avgBufferCount, op.len_);
    } else {
        op.InitDataCopyOffset<bfloat16_t>(avgBufferCount, op.len_);
        op.Process<bfloat16_t>(op.dataAddrSelf_, op.flagAddrSelf_, op.commAddr_, input, output, op.tag_, avgBufferCount, op.len_);
    }
}
