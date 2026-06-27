/**
 * Copyright (c) 2025 Huawei Technologies Co., Ltd.
 * This program is free software, you can redistribute it and/or modify it under the terms and conditions of
 * CANN Open Software License Agreement Version 2.0 (the "License").
 * Please refer to the License for details. You may not use this file except in compliance with the License.
 * THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
 * INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
 * See LICENSE in the root of the software repository for the full text of the License.
 */

#ifndef LLT_HCCL_STUB_MC2_H
#define LLT_HCCL_STUB_MC2_H

#include "gtest/gtest.h"

#ifndef private
#define private public
#define protected public
#endif
#include <cstring>
#include "common/aicpu_kfc_def.h"
#include "common/aicpu_sqe_context.h"
#include "framework/aicpu_kfc_rpc_server.h"
#include "framework/aicpu_kfc_rpc_serverv2.h"
#include "framework/aicpu_hccl_process.h"
#include "framework/aicpu_kfc_process.h"
#include "utils/hccl_aicpu_utils.h"
#include "aicpu_kfc/common/aicpu_kfc_utils.h"
#include "coll_alg_param.h"
#include "hccl_msg.h"
#include "hccl_tiling_msg.h"
#include "framework/aicpu_communicator.h"
#undef private
#undef protected

extern DevType g_stubDevType;

inline void ResetMC2Context()
{
    AicpuComContext *ctx = AicpuGetComContext();
    ctx->kfcStatusTransferD2H = nullptr;
    ctx->kfcControlTransferH2D = nullptr;
    std::vector<struct hccl::TransportDeviceNormalData> temp;
    ctx->ibversData.swap(temp);
    memset(ctx, 0, sizeof(AicpuComContext));
    AicpuSqeContext::InitSqeContext();
}

class StubHccCommRes {
public:
    StubHccCommRes()
    {
        workSpaceSize = 16 * 1024 * 1024;
        workSpace = (u64 *)malloc(workSpaceSize);
        winSize = 200 * 1024 * 1024;
        windows = (u64 *)malloc(winSize);
    }
    ~StubHccCommRes()
    {
        if (workSpace != nullptr) {
            free(workSpace);
        }
        if (windows != nullptr) {
            free(windows);
        }
    }
    HccCommResParamTask StubHccCommResParamTask()
    {
        HccCommResParamTask paramTask;
        std::memset(&paramTask, 0, sizeof(HccCommResParamTask));
        paramTask.mc2WorkSpace.workSpaceSize = workSpaceSize;
        paramTask.mc2WorkSpace.workSpace = (u64)workSpace;
        paramTask.rankId = 0;
        paramTask.rankNum = 8;
        paramTask.winSize = winSize;
        strcpy(paramTask.hcomId, "hcom\0");
        for (uint32_t i = 0; i < AC_MAX_RANK_NUM; i++) {
            paramTask.windowsIn[i] = (u64)windows * (i + 1);
            paramTask.windowsOut[i] = (u64)windows * (i + 1);
            paramTask.streamInfo[i].streamIds = 52 + i;
            paramTask.streamInfo[i].sqIds = 52 + i;
            paramTask.streamInfo[i].cqIds = 52 + i;
            paramTask.streamInfo[i].logicCqids = 52 + i;
        }
        uint64_t resId = 0;
        for (uint32_t i = 0; i < AC_MAX_RANK_NUM * 2; i++) {
            paramTask.signalInfo.noIpcNotifys[i].resId = ++resId;
            paramTask.signalInfo.noIpcNotifys[i].addr = 0x10 + i;
            paramTask.signalInfo.noIpcNotifys[i].devId = 0;
            paramTask.signalInfo.noIpcNotifys[i].tsId = 0;
            paramTask.signalInfo.noIpcNotifys[i].rankId = i % AC_MAX_RANK_NUM;
        }
        for (uint32_t i = 0; i < AC_MAX_RANK_NUM * 4; i++) {
            paramTask.signalInfo.ipcNotifys[i].resId = ++resId;
            paramTask.signalInfo.ipcNotifys[i].addr = 0x100 + i;
            paramTask.signalInfo.ipcNotifys[i].devId = 0;
            paramTask.signalInfo.ipcNotifys[i].tsId = 0;
            paramTask.signalInfo.ipcNotifys[i].rankId = i % AC_MAX_RANK_NUM;
        }
        for (uint32_t i = 0; i < AC_MAX_RANK_NUM; i++) {
            paramTask.signalInfo.noIpcEvents[i].resId = ++resId;
            paramTask.signalInfo.noIpcEvents[i].addr = 0x1000 + i;
            paramTask.signalInfo.noIpcEvents[i].devId = 0;
            paramTask.signalInfo.noIpcEvents[i].tsId = 0;
            paramTask.signalInfo.noIpcEvents[i].rankId = i;
        }
        paramTask.signalInfo.aicpuNotify.resId = ++resId;
        paramTask.signalInfo.aicpuNotify.addr = 0x10000;
        paramTask.signalInfo.aicpuNotify.devId = 0;
        paramTask.signalInfo.aicpuNotify.tsId = 0;
        paramTask.signalInfo.aicpuNotify.rankId = 0;
        paramTask.config.deterministic = 0;
        paramTask.config.notifyWaitTime = 1;
        paramTask.overFlowAddr = 0;
        return paramTask;
    }

private:
    u64 *workSpace;
    u64 workSpaceSize;
    u64 *windows;
    u64 winSize;
};

class StubSqeBuffer {
public:
    StubSqeBuffer()
    {
        buffer = new uint8_t[64 * 64 * 64];
        AicpuComContext *ctx = AicpuGetComContext();
        for (auto &info : ctx->streamInfo) {
            info.sqDepth = 4096;
            info.sqBaseAddr = buffer;
        }
    }
    ~StubSqeBuffer()
    {
        if (buffer != nullptr) {
            delete[] buffer;
            buffer = nullptr;
        }
    }

private:
    uint8_t *buffer = nullptr;
};


drvError_t StubhalGetDeviceInfo(uint32_t devId, int32_t moduleType, int32_t infoType, int64_t *value);
class MC2AicpuProcessStub: public AicpuKfcProcess {
public:
    HcclResult InitTimeOutConfig(HccCommResParamTask *commParam, AicpuComContext *ctx) {
        (void) commParam;
        return HCCL_SUCCESS;
    }
};
inline uint32_t RunAicpuKfcResInitStub(void *args)
{
    if (args == nullptr) {
        return HCCL_E_PTR;
    }
    KFCResInitTask *ctxArgs = reinterpret_cast<KFCResInitTask *>(args);
    MC2AicpuProcessStub mc2AicpuProcessStub;
    return mc2AicpuProcessStub.AicpuRpcResInit(reinterpret_cast<HccCommResParamTask *>(ctxArgs->context));
}

inline uint32_t RunAicpuKfcResInitV2Stub(void *args)
{
    if (args == nullptr) {
        HCCL_ERROR("args is null.");
        return HCCL_E_PARA;
    }
    KFCResInitTask *ctxArgs = reinterpret_cast<KFCResInitTask *>(args);
    AicpuHcclProcess mc2AicpuProcessStub;
    return AicpuHcclProcess::AicpuRpcResInitV2(reinterpret_cast<HcclOpResParam *>(ctxArgs->context), false);
}

// inline void MockGetSendRecvCnt()
// {
//     MOCKER(AicpuKfcUtils::GetSendCnt)
//         .stubs()
//         .will(returnValue(0));
//     MOCKER(AicpuKfcUtils::GetRecvCnt)
//         .stubs()
//         .will(returnValue(0));
// }
extern "C" {
__attribute__((default)) int32_t AdprofReportAdditionalInfo(uint32_t agingFlag, const void *data, uint32_t length);
__attribute__((default)) int32_t MsprofReportAdditionalInfo(uint32_t agingFlag, const VOID_PTR data, uint32_t length);
__attribute__((default)) int32_t AdprofCheckFeatureIsOn(uint64_t feature);
__attribute__((default)) uint64_t AdprofGetHashId(const char *hashInfo, size_t length);
__attribute__((default)) uint64_t MsprofStr2Id(const char *hashInfo, size_t length);
__attribute__((default)) uint32_t AicpuGetStreamId();
__attribute__((default)) uint64_t AicpuGetTaskId();
}
namespace aicpu {
extern __attribute__((default)) status_t GetTaskAndStreamId(uint64_t &taskId, uint32_t &streamId);
}

struct HcclMsgV1ForTest {
    HcclCMDType commType;      // ͨ��ԭ�����ͣ�AllReduce/AllGather.../Finalize/InterHcclGroupSync
    HcclReduceOp opType;        // reduce�������ͣ�sum/prod/max/min
    uint64_t sendBuffer;        // Դ����buffer��ַ��
    uint64_t recvBuffer;        // Ŀ������buffer��ַ
    uint64_t dataCnt;           // ������������ݸ���
    uint64_t strideCount;       // ���������ݽ��һ���������ģ��зֶ��ֺ�ᵼ����Ҫ����stride������AllGather��stride��ÿ�����ϵ�����������
    uint64_t ccOpTilingData;    // ��Ϣ��tiling��Ϣ
    uint32_t valid;             // �����Ϣ��Ч��
    HcclDataType hcclDataType;  // �����������������
    uint8_t repeatCnt;          // ����Ϣ��Ҫ�ظ��Ĵ�����Ĭ����1
    HcclHandle selfHandleID;    // ͨ����Ϣ��Ӧ��handleIdֵ
    uint8_t seqNum;             // ��Ϣ���
    uint8_t version;            // ��Ϣ�İ汾��Ϣ��version=1ʹ��hcclMsgV1
    uint32_t xorCheck;          // xor checksum
};

struct HcclMsgForTest {
    HcclCMDType commType;          // ͨ��ԭ�����ͣ�AllReduce/AllGather.../Finalize/InterHcclGroupSync
    HcclReduceOp opType;            // reduce�������ͣ�sum/prod/max/min
    uint64_t sendBuffer;            // Դ����buffer��ַ��
    uint64_t recvBuffer;            // Ŀ������buffer��ַ
    uint64_t dataCnt;               // ������������ݸ���
    uint64_t strideCount;           // ���������ݽ��һ���������ģ��зֶ��ֺ�ᵼ����Ҫ����stride������AllGather��stride��ÿ�����ϵ�����������
    HcclDataType hcclDataType;      // �����������������
    uint32_t p2pSrcDestRankId;      // ��Ե�ͨ��send/recv�Զ˵�rankId��send�е�destRank, recv�е�srcRank

    uint32_t valid;                 // �����Ϣ��Ч��
    uint8_t repeatCnt;              // ����Ϣ��Ҫ�ظ��Ĵ�����Ĭ����1
    uint8_t everyTurnRsp;           // ÿ�ֶ���Ҫ�ȴ�ִ�н���������Ӧ����ִ����һ��
    uint8_t everyTurnWait;          // ÿ�ֶ���Ҫ�ȴ�work��Ϣ��ִ��
    HcclHandle commDepGroupID;      // ����Ϣִ����Ҫ�ȴ���ͨ������id��Ĭ����-1����ʾ����Ҫ�ȴ�����������notify������ͨ������id
    HcclHandle commDepHandleID;     // ����Ϣִ����Ҫ�ȴ���ͨ�����ִΣ�Ĭ����-1����ʾ����Ҫ�ȴ�����������notify�����ĵ�ַ
    HcclHandle selfHandleID;        // ͨ����Ϣ��Ӧ��handleIdֵ
    uint8_t seqNum;                 // ��Ϣ���
    uint8_t version;                // ��Ϣ�İ汾��Ϣ��version=0ʹ��hcclMsg
    uint32_t xorCheck;              // xor checksum
};

struct HcclMsgAreaForTest {
    HcclMsgForTest sendMsgList[HcclApi::HCCL_MSG_CNT];  // ������Ϣ����
    HcclMsgForTest recvMsgList[HcclApi::HCCL_MSG_CNT];  // ������Ϣ���У�Ϊ�˱������˺Ϳͻ���ͬʱд
    uint8_t reserved0[8 * HcclApi::BYTE_PER_KB];    // for abi compatibility
    HcclApi::TurnCnt commitTurnCnt[HcclApi::HCCL_MSG_CNT];
    HcclApi::TurnCnt finishedTurnCnt[HcclApi::HCCL_MSG_CNT];
    uint8_t reserved1[HcclApi::BYTE_PER_MB];
    HcclApi::HcclMsgExt paramExtMsgList[HcclApi::HCCL_MSG_CNT];
    HcclApi::ControlHcclMsg controlMsg;
};

constexpr uint32_t MAX_QUE_NUM = 48U;
constexpr uint32_t PADDING_SIZE = 0xF7000;
struct HcclMsgAreaForMultiQueForTest {
    HcclMsgForTest sendMsgList[MAX_QUE_NUM][HcclApi::HCCL_MSG_CNT];
    HcclApi::TurnCnt commitTurnCnt[MAX_QUE_NUM][HcclApi::HCCL_MSG_CNT];
    HcclApi::TurnCnt finishedTurnCnt[MAX_QUE_NUM][HcclApi::HCCL_MSG_CNT];
    uint8_t pad[PADDING_SIZE];
    HcclApi::ControlHcclMsg controlMsg;
};

inline uint32_t GenXorStub(HcclMsgForTest *msg) {
    if (msg == nullptr) {
        return UINT32_MAX;
    }
    DataBlock* block = reinterpret_cast<DataBlock *>(msg);
    uint32_t xorVal = 0;
    for (int i = 0; i < 15; i++) {
        xorVal ^= block->data[i];
    }
    return xorVal;
}

extern void InitMultiThreadSharedCtx(int32_t cpuId);
extern void GetCommonHcclMsg(HcclApi::HcclMsg *hcclMsg, CommonHcclMsg *commonHcclMsg, u64 tilingBase);
extern void PrepareOpParam(hccl::OpParam *opParam, CommonHcclMsg *hcclMsg, AicpuKfcRpcServerV2 &rpc, hccl::HcclCommAicpu *commAicpu);
extern bool CheckNsCommand(hccl::HcclCommAicpu *comm);
extern int32_t GetComGroupIdx(const std::string &hcomId);
extern AicpuKfcRpcServerV2 *GetCommRpcServer(uint32_t idx);
extern HcclResult InitIbversData(HccCommResParamTask *commParam, AicpuComContext *ctx);
extern HcclResult AddTaskForHcclMsgV2(hccl::HcclCommAicpu *comm, AicpuKfcRpcServerV2 *rpc, CommonHcclMsg *hcclMsg, const HcclOpResParam *commParam);
extern HcclResult BarrierProcess(u32 groupIdx, u32 queueId, BarrierStatus &status);
extern HcclResult CheckRestartError(hccl::HcclCommAicpu *comm);
extern HcclResult HcclOpExecFsmStoppedProcess(AicpuComContext *ctx, HcclOpExecFSM &state, KfcError &errorCode, u32 retryCnt, AivAicpuOpParam &opParams, u32 beginSqePos, u32 endSqePos);
extern HcclResult HcclOpExecFsmStoppingProcess(AicpuComContext *ctx, HcclOpExecFSM &state, KfcError &errorCode, u32 retryCnt);
extern HcclResult MC2OpExecFsmStoppedProcess(hccl::HcclCommAicpu &comm, HcclOpExecFSM &state, KfcError &errorCode, u8 restartCnt);
extern HcclResult MC2OpExecFsmStoppingProcess(hccl::HcclCommAicpu &comm, HcclOpExecFSM &state, KfcError &errorCode);
extern HcclResult MC2OpExecFsmWaitRetryProcess(hccl::HcclCommAicpu &comm, HcclOpExecFSM &state, KfcError &errorCode, uint8_t restartCnt, bool linkChanged);
extern HcclResult OrchestrateSdmaSqe(const hccl::OpParam &param, hccl::HcclCommAicpu &comm);
extern HcclResult ParseCcOpTilingData(CommonHcclMsg *commonHcclMsg, int32_t groupIdx);
extern HcclResult PrepareHcommInstance(u32 idx, HcclOpResParam *commParam, const HcclApi::Mc2InitTilingInner *tiling);
extern HcclResult RestartProcessConsulation(RestartParam &restartParam, bool &finalizeAllEnd, bool *finalizeMask, u32 groupNum);
extern HcclResult RpcServerPreCheck(AicpuKfcRpcServerV2 *rpc, hccl::HcclCommAicpu *comm, bool &finalizeFlag);
extern HcclResult RunRpcServerInnerProcessV2(uint32_t groupNum);
extern HcclResult RunRpcServerLoopProcess(u32 groupIdx, bool &finalizeFlag);
extern HcclResult UpdateOpExecStatus(AicpuComContext *ctx, HcclOpExecFSM &fsmState, KfcStatus state, KfcError &errorCode, uint32_t retryCnt);

#endif // __MC2_AICPU_STUB_HPP__
