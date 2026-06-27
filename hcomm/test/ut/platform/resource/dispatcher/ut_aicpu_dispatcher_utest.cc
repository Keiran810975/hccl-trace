/**
 * Copyright (c) 2025 Huawei Technologies Co., Ltd.
 * This program is free software, you can redistribute it and/or modify it under the terms and conditions of
 * CANN Open Software License Agreement Version 2.0 (the "License").
 * Please refer to the License for details. You may not use this file except in compliance with the License.
 * THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
 * INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
 * See LICENSE in the root of the software repository for the full text of the License.
 */

#include "gtest/gtest.h"
#include <mockcpp/mockcpp.hpp>

#ifndef private
#define private public
#define protected public
#include "dispatcher_aicpu.h"
#endif
#include "profiling_manager.h"
#include "dlprof_function.h"
#include "profiler_manager.h"
#include "externalinput.h"
#include "adapter_rts.h"
#include "rts_notify.h"
#include "queue_notify_manager.h"
#include "llt_hccl_stub_mc2.h"
#include "profiling_manager_device.h"
#include "hccl_thread.h"

#undef private
#undef protected
#include "hccl_dispatcher_ctx.h"
#include "dispatcher_ctx.h"
#include "sub_inc/mmpa_typedef_linux.h"

using namespace hccl;

extern HcclResult CommTaskPrepare(char *key, uint32_t keyLen);
extern HcclResult CommTaskLaunch(ThreadHandle *threads, uint32_t threadNum);

#ifdef __cplusplus
extern "C" {
#endif // __cplusplus

typedef enum tagRtClearStep {
    RT_STREAM_STOP = 0,
    RT_STREAM_CLEAR,
} rtClearStep_t;

rtError_t rtStreamClear(rtStream_t stm, rtClearStep_t step)
{
    return 0;
}

INT32 mmGetEnv(const CHAR *name, CHAR *value, UINT32 len)
{
    INT32 ret;
    UINT32 envLen = 0;
    if ((name == NULL) || (value == NULL) || (len == MMPA_ZERO)) {
        return EN_INVALID_PARAM;
    }
    const CHAR *envPtr = getenv(name);
    if (envPtr == NULL) {
        return EN_ERROR;
    }

    UINT32 lenOfRet = (UINT32)strlen(envPtr);
    if (lenOfRet < (UINT32)(MMPA_MEM_MAX_LEN - 1)) {
        envLen = lenOfRet + 1U;
    }

    if ((envLen != MMPA_ZERO) && (len < envLen)) {
        return EN_INVALID_PARAM;
    } else {
        ret = memcpy_s(value, len, envPtr, envLen); //lint !e613
        if (ret != EN_OK) {
            return EN_ERROR;
        }
    }
    return EN_OK;
}

#ifdef __cplusplus
}
#endif // __cplusplus

class DispatcherAiCpu_UT : public testing::Test {
protected:
    static void SetUpTestCase()
    {
        std::cout << "DispatcherAiCpu_UT SetUP" << std::endl;
    }
    static void TearDownTestCase()
    {
        std::cout << "DispatcherAiCpu_UT TearDown" << std::endl;
    }
    // Some expensive resource shared by all tests.
    virtual void SetUp()
    {
        dispatcherAiCpu->aicpuInfo_.devType = DevType::DEV_TYPE_910B;
        dispatcherAiCpu->aicpuInfo_.devId = 1;
        dispatcherAiCpu->aicpuInfo_.ssid = 1;
        dispatcherAiCpu->Init();

        streamInfo.actualStreamId = 1;
        streamInfo.sqId = 1;
        streamInfo.sqDepth = 100;
        streamInfo.sqBaseAddr = static_cast<void *>(sq_addr);
        streamInfo.logicCqId = 1;
        s32 portNum = 7;
        MOCKER(hrtGetHccsPortNum)
            .stubs()
            .with(any(), outBound(portNum))
            .will(returnValue(HCCL_SUCCESS));
        std::cout << "DispatcherAiCpu_UT Test SetUP" << std::endl;
    }
    virtual void TearDown()
    {
        GlobalMockObject::verify();
        std::cout << "DispatcherAiCpu_UT Test TearDown" << std::endl;
    }

    std::unique_ptr<DispatcherAiCpu> dispatcherAiCpu = std::unique_ptr<DispatcherAiCpu>(new (std::nothrow) DispatcherAiCpu(1));
    HcclComStreamInfo streamInfo;

    static u8 sq_addr[HCCL_SQE_SIZE * HCCL_SQE_MAX_CNT];
};

u8 DispatcherAiCpu_UT::sq_addr[HCCL_SQE_SIZE * HCCL_SQE_MAX_CNT] = {0};
// 补充覆盖率
#if 0
TEST_F(DispatcherAiCpu_UT, ut_DispatcherAiCpuLaunchTaskEx)
{
    u32 streamNum = 7;
    Stream stream(streamInfo, true);
    std::vector<Stream> subStreams;
    subStreams.resize(streamNum);

    for (u32 i = 0; i < subStreams.size(); i++) {
        streamInfo.actualStreamId = i;
        streamInfo.sqId = i;
        subStreams[i] = Stream(streamInfo, false);
    }

    MOCKER_CPP(&DispatcherAiCpu::LaunchTask, HcclResult(DispatcherAiCpu::*)(hccl::Stream &, bool))
        .stubs()
        .with(any())
        .will(returnValue(HCCL_E_INTERNAL))
        .then(returnValue(HCCL_SUCCESS))
        .then(returnValue(HCCL_E_INTERNAL))
        .then(returnValue(HCCL_SUCCESS));
    auto ret1 = dispatcherAiCpu->LaunchTasksEx(stream, subStreams);
    EXPECT_EQ(ret1, HCCL_E_INTERNAL);

    auto ret2 = dispatcherAiCpu->LaunchTasksEx(stream, subStreams);
    EXPECT_EQ(ret2, HCCL_E_INTERNAL);

    auto ret = dispatcherAiCpu->LaunchTasksEx(stream, subStreams);
    EXPECT_EQ(ret, HCCL_SUCCESS);
    uint32_t sqHead = 0;
    uint32_t sqTail = 100;

    SqCqeContext sqeCqeCtx;
    sqeCqeCtx.sqContext.inited = false;
    stream.InitSqAndCqeContext(sqHead, sqTail, &sqeCqeCtx);
    // 测试初始化是否成功
    HcclSqeContext *sqeContext = stream.GetSqeContextPtr();
    auto &buff = sqeContext->buffer;
    HCCL_ERROR("buf sqHead[%u] sqTail[%u]", buff.sqHead, buff.sqTail);
    EXPECT_EQ(buff.sqHead, sqHead);
    EXPECT_EQ(buff.sqTail, sqTail);

    ret = dispatcherAiCpu->AddRetryPreamble(stream);
    EXPECT_EQ(ret, HCCL_SUCCESS);
}
#endif

TEST_F(DispatcherAiCpu_UT, ut_DispatcherAiCpuSignalRecord)
{
    HcclSignalInfo notifyInfo;
    std::unique_ptr<QueueNotifyManager> queueNotifyManager = nullptr;
    queueNotifyManager.reset(new (std::nothrow) QueueNotifyManager());
    EXPECT_NE(queueNotifyManager, nullptr);
    auto ret = queueNotifyManager->Init();
    EXPECT_EQ(ret, HCCL_SUCCESS);

    std::shared_ptr<LocalNotify> signalAux = nullptr;
    std::shared_ptr<LocalNotify> signalMain = nullptr;
    std::string tag = "aicpu_signal_test";
    std::vector<std::shared_ptr<LocalNotify>> notifys(2, nullptr);
    ret = queueNotifyManager->Alloc(tag, 2, notifys, NotifyLoadType::DEVICE_NOTIFY);
    EXPECT_EQ(ret, HCCL_SUCCESS);
    signalMain = notifys[0];
    signalAux = notifys[1];
    signalMain->GetNotifyData(notifyInfo);

    u32 notifyId = static_cast<u32>(notifyInfo.resId);

    HcclRtNotify signal;
    uint32_t sqHead = 0;
    uint32_t sqTail = 100;
    u32 userRank = 1;
    u64 offset = 0;
    s32 stage = 0;
    Stream stream(streamInfo, true);
    SqCqeContext sqeCqeCtx;
    sqeCqeCtx.sqContext.inited = false;
    stream.InitSqAndCqeContext(sqHead, sqTail, &sqeCqeCtx);

    u64 signalAddr = INVALID_U64;
    ret = dispatcherAiCpu->SignalRecord(signal, stream, userRank, offset, stage, true, signalAddr, notifyId);
    EXPECT_EQ(HCCL_SUCCESS, ret);

    ret = dispatcherAiCpu->SignalRecord(signal, stream, userRank, offset, stage, false, signalAddr, notifyId);
    EXPECT_EQ(HCCL_SUCCESS, ret);

    GlobalMockObject::verify();
}

TEST_F(DispatcherAiCpu_UT, ut_DispatcherAiCpuSignalWait)
{
    HcclSignalInfo notifyInfo;
    std::unique_ptr<QueueNotifyManager> queueNotifyManager = nullptr;
    queueNotifyManager.reset(new (std::nothrow) QueueNotifyManager());
    EXPECT_NE(queueNotifyManager, nullptr);
    auto ret = queueNotifyManager->Init();
    EXPECT_EQ(ret, HCCL_SUCCESS);

    std::shared_ptr<LocalNotify> signalAux = nullptr;
    std::shared_ptr<LocalNotify> signalMain = nullptr;
    std::string tag = "aicpu_signal_test";
    std::vector<std::shared_ptr<LocalNotify>> notifys(2, nullptr);
    ret = queueNotifyManager->Alloc(tag, 2, notifys, NotifyLoadType::DEVICE_NOTIFY);
    EXPECT_EQ(ret, HCCL_SUCCESS);
    signalMain = notifys[0];
    signalAux = notifys[1];

    signalMain->GetNotifyData(notifyInfo);

    u32 notifyId = static_cast<u32>(notifyInfo.resId);
    HcclRtNotify signal;
    uint32_t sqHead = 0;
    uint32_t sqTail = 100;
    u32 userRank = 0;
    u32 remoteRank = 1;
    u64 offset = 0;
    s32 stage = 0;
    Stream stream(streamInfo, true);
    SqCqeContext sqeCqeCtx;
    sqeCqeCtx.sqContext.inited = false;
    stream.InitSqAndCqeContext(sqHead, sqTail, &sqeCqeCtx);

    ret = dispatcherAiCpu->SignalWait(signal, stream, userRank, remoteRank, stage, true, notifyId);
    EXPECT_EQ(HCCL_SUCCESS, ret);

    ret = dispatcherAiCpu->SignalWait(signal, stream, userRank, remoteRank, stage, false, notifyId);
    EXPECT_EQ(HCCL_SUCCESS, ret);

    GlobalMockObject::verify();
}

TEST_F(DispatcherAiCpu_UT, ut_DispatcherAiCpuMemcpy)
{
    uint32_t sqHead = 0;
    uint32_t sqTail = 100;
    u64 *ptr = new u64(1);
    DeviceMem dst(ptr, 0x80, false);
    DeviceMem src(ptr, 0x80, false);
    Stream stream(streamInfo, true);
    SqCqeContext sqeCqeCtx;
    sqeCqeCtx.sqContext.inited = false;
    stream.InitSqAndCqeContext(sqHead, sqTail, &sqeCqeCtx);
    auto ret = dispatcherAiCpu->MemcpyAsync(dst, src, stream);
    EXPECT_EQ(HCCL_SUCCESS, ret);
    delete ptr;

    GlobalMockObject::verify();
}

TEST_F(DispatcherAiCpu_UT, ut_DispatcherAiCpuInlineReduceAsync)
{
    uint32_t sqHead = 0;
    uint32_t sqTail = 100;
    DeviceMem dst = DeviceMem::alloc(80);
    DeviceMem src = DeviceMem::alloc(80);
    Stream stream(streamInfo, true);
    SqCqeContext sqeCqeCtx;
    sqeCqeCtx.sqContext.inited = false;
    stream.InitSqAndCqeContext(sqHead, sqTail, &sqeCqeCtx);

    u64 dataCount = 20;
    auto ret = dispatcherAiCpu->InlineReduceAsync(src.ptr(), dataCount, HcclDataType::HCCL_DATA_TYPE_FP32,
        HcclReduceOp::HCCL_REDUCE_SUM, stream, dst.ptr());
    EXPECT_EQ(HCCL_SUCCESS, ret);
    GlobalMockObject::verify();
}

TEST_F(DispatcherAiCpu_UT, ut_DispatcherAiCpuReduceAsync)
{
    uint32_t sqHead = 0;
    uint32_t sqTail = 100;
    DeviceMem dst = DeviceMem::alloc(0x19000000);
    DeviceMem src = DeviceMem::alloc(0x19000000);

    Stream stream(streamInfo, true);
    SqCqeContext sqeCqeCtx;
    sqeCqeCtx.sqContext.inited = false;
    stream.InitSqAndCqeContext(sqHead, sqTail, &sqeCqeCtx);

    u64 dataCount = 0x6400000;

    auto ret = dispatcherAiCpu->ReduceAsync(src.ptr(), dst.ptr(), dataCount, HcclDataType::HCCL_DATA_TYPE_INT8,
        HcclReduceOp::HCCL_REDUCE_SUM, stream, HcclReduceType::HCCL_INLINE_REDUCE);

    EXPECT_EQ(HCCL_SUCCESS, ret);
    GlobalMockObject::verify();
}

TEST_F(DispatcherAiCpu_UT, ut_DispatcherAiCpuTbeReduce_RdmaSend)
{
    uint32_t sqHead = 0;
    uint32_t sqTail = 100;
    u32 dbIndex = 0;
    u64 dbInfo = 0;
    u32 userRank;
    Stream stream(streamInfo, true);
    SqCqeContext sqeCqeCtx;
    sqeCqeCtx.sqContext.inited = false;
    stream.InitSqAndCqeContext(sqHead, sqTail, &sqeCqeCtx);

    RdmaTaskInfo taskInfo;
    taskInfo.remoteRank = userRank;

    auto ret = dispatcherAiCpu->RdmaSend(dbIndex, dbInfo, stream, taskInfo);
    EXPECT_EQ(HCCL_SUCCESS, ret);

    DeviceMem dst = DeviceMem::alloc(0x19000000);
    DeviceMem src1 = DeviceMem::alloc(0x19000000);
    DeviceMem src2 = DeviceMem::alloc(0x19100000);

    u64 dataCount = 0x6400000;

    auto ret2 = dispatcherAiCpu->TbeReduceAsync(src1.ptr(), src2.ptr(), dataCount, HcclDataType::HCCL_DATA_TYPE_INT8,
        HcclReduceOp::HCCL_REDUCE_SUM, stream, dst.ptr());
    EXPECT_EQ(HCCL_E_NOT_SUPPORT, ret2);

    GlobalMockObject::verify();
}

TEST_F(DispatcherAiCpu_UT, ut_DispatcherProfilingRdmaSend)
{
    uint32_t sqHead = 0;
    uint32_t sqTail = 5;
    u32 dbIndex = 0;
    u64 dbInfo = 0;
    u32 userRank;

    Stream stream(streamInfo, true);
    SqCqeContext sqeCqeCtx;
    sqeCqeCtx.sqContext.inited = false;
    stream.InitSqAndCqeContext(sqHead, sqTail, &sqeCqeCtx);

    RdmaTaskInfo taskInfo;
    taskInfo.remoteRank = userRank;

    auto ret = dispatcherAiCpu->RdmaSend(dbIndex, dbInfo, stream, taskInfo);
    EXPECT_EQ(HCCL_SUCCESS, ret);

    dispatcherAiCpu->aicpuInfo_.devType = DevType::DEV_TYPE_910_93;
    ret = dispatcherAiCpu->RdmaSend(dbIndex, dbInfo, stream, taskInfo);
    EXPECT_EQ(HCCL_SUCCESS, ret);

    ret = dfx::ProfilingManager::ReportTaskInfo(stream.id(), stream.GetSqeContextPtr());
    GlobalMockObject::verify();
}

int32_t AdprofReportBatchAdditionalInfo(uint32_t agingFlag, ConstVoidPtr data, uint32_t length)
{
    return 0;
}

int32_t MsprofReportBatchAdditionalInfo(uint32_t agingFlag, const VOID_PTR data, uint32_t length)
{
    return 0;
}

TEST_F(DispatcherAiCpu_UT, ut_AdprofReportBatchAdditionalInfo)
{
    uint32_t sqHead = 0;
    uint32_t sqTail = 5;
    u32 dbIndex = 0;
    u64 dbInfo = 0;
    u32 userRank;

    Stream stream(streamInfo, true);
    SqCqeContext sqeCqeCtx;
    stream.InitSqAndCqeContext(sqHead, sqTail, &sqeCqeCtx);

    RdmaTaskInfo taskInfo;
    taskInfo.remoteRank = userRank;

    auto ret = dispatcherAiCpu->RdmaSend(dbIndex, dbInfo, stream, taskInfo);
    EXPECT_EQ(HCCL_SUCCESS, ret);

    dispatcherAiCpu->aicpuInfo_.devType = DevType::DEV_TYPE_910_93;
    ret = dispatcherAiCpu->RdmaSend(dbIndex, dbInfo, stream, taskInfo);
    EXPECT_EQ(HCCL_SUCCESS, ret);

    ret = dfx::ProfilingManager::ReportTaskInfo(stream.id(), stream.GetSqeContextPtr());
    GlobalMockObject::verify();
}

TEST_F(DispatcherAiCpu_UT, ut_DispatcherAiCpuGetPrivateMember)
{
    // TEST V2
    dispatcherAiCpu->aicpuInfo_.devType = DevType::DEV_TYPE_310P1;
    auto ret = dispatcherAiCpu->Init();

    EXPECT_EQ(HCCL_SUCCESS, ret);

    u32 notifyId = 32768;
    HcclRtNotify signal;
    uint32_t sqHead = 0;
    uint32_t sqTail = 100;
    u32 userRank = 0;
    u32 remoteRank = 1;
    u64 offset = 0;
    s32 stage = 0;
    Stream stream(streamInfo, true);
    SqCqeContext sqeCqeCtx;
    sqeCqeCtx.sqContext.inited = false;
    stream.InitSqAndCqeContext(sqHead, sqTail, &sqeCqeCtx);

    ret = dispatcherAiCpu->SignalWait(signal, stream, userRank, remoteRank, stage, false, notifyId);
    EXPECT_EQ(HCCL_SUCCESS, ret);
}

TEST_F(DispatcherAiCpu_UT, ut_DispatcherAiCpuLaunchTask)
{
    uint32_t sqHead = 0;
    uint32_t sqTail = 50;
    Stream stream(streamInfo, true);
    SqCqeContext sqeCqeCtx;
    sqeCqeCtx.sqContext.inited = false;
    stream.InitSqAndCqeContext(sqHead, sqTail, &sqeCqeCtx);

    MOCKER(QuerySqStatusByType)
        .stubs()
        .will(returnValue(HCCL_SUCCESS));
    dispatcherAiCpu->dfxTimeOutConfig_.sqFullWaitTimeOut = 2;
    auto ret = dispatcherAiCpu->LaunchTask(stream, true);
    EXPECT_EQ(ret, HCCL_SUCCESS);
}


TEST_F(DispatcherAiCpu_UT, ut_aicpu_prof_taskInfoReport)
{
    uint32_t sqHead = 0;
    uint32_t sqTail = 100;
    Stream stream(streamInfo, true);
    SqCqeContext sqeCqeCtx;
    sqeCqeCtx.sqContext.inited = false;
    stream.InitSqAndCqeContext(sqHead, sqTail, &sqeCqeCtx);

    MOCKER(QuerySqStatusByType)
        .stubs()
        .will(returnValue(HCCL_SUCCESS));

    dispatcherAiCpu->dfxTimeOutConfig_.sqFullWaitTimeOut = 2;
    auto ret = dispatcherAiCpu->LaunchTask(stream, true);
    EXPECT_EQ(ret, HCCL_SUCCESS);

    stream.sqeContext_->buffer.sqeCnt = 10;
    stream.sqeContext_->buffer.tailSqeIdx = 10;

    ret = dispatcherAiCpu->LaunchTask(stream, true);

    stream.sqeContext_->buffer.sqTail = 50;
    ret = dispatcherAiCpu->LaunchTask(stream, true);
    EXPECT_EQ(ret, HCCL_SUCCESS);
}

TEST_F(DispatcherAiCpu_UT, ut_launchTask_rtsqfull)
{
    uint32_t sqHead = 0;
    uint32_t sqTail = 100;
    Stream stream(streamInfo, true);
    SqCqeContext sqeCqeCtx;
    sqeCqeCtx.sqContext.inited = false;
    stream.InitSqAndCqeContext(sqHead, sqTail, &sqeCqeCtx);

    MOCKER(QuerySqStatusByType)
        .stubs()
        .will(returnValue(HCCL_SUCCESS));

    stream.sqeContext_->buffer.sqeCnt = 10;
    stream.sqeContext_->buffer.tailSqeIdx = 10;

    Stream stream1(streamInfo, true);
    SqCqeContext sqeCqeCtx1;
    sqeCqeCtx1.sqContext.inited = false;
    stream1.InitSqAndCqeContext(sqHead, sqTail, &sqeCqeCtx1);
    dispatcherAiCpu->SaveStreamInfo(stream1);

    dispatcherAiCpu->dfxTimeOutConfig_.sqFullWaitTimeOut = 2;
    auto ret = dispatcherAiCpu->LaunchTask(stream, true);
    EXPECT_EQ(ret, HCCL_E_AGAIN);
}

TEST_F(DispatcherAiCpu_UT, ut_DispatcherAiCpu_StreamSync)
{
    uint32_t sqHead = 0;
    uint32_t sqTail = 100;
    Stream stream(streamInfo, true);
    SqCqeContext sqeCqeCtx;
    sqeCqeCtx.sqContext.inited = false;
    stream.InitSqAndCqeContext(sqHead, sqTail, &sqeCqeCtx);

    stream.sqeContext_->buffer.sqeCnt = 10;
    stream.sqeContext_->buffer.tailSqeIdx = 10;

    dispatcherAiCpu->dfxTimeOutConfig_.sqeTimeOutTimeOut = 0;
    auto ret = dispatcherAiCpu->StreamSync(stream);
    EXPECT_EQ(ret, HCCL_E_TIMEOUT);

    dispatcherAiCpu->dfxTimeOutConfig_.sqeTimeOutTimeOut = 1000000000U;
    Stream stream1(streamInfo, true);
    SqCqeContext sqeCqeCtx1;
    sqeCqeCtx1.sqContext.inited = false;
    stream1.InitSqAndCqeContext(0, 0, &sqeCqeCtx1);

    stream1.sqeContext_->buffer.sqeCnt = 0;
    stream1.sqeContext_->buffer.tailSqeIdx = 0;

    ret = dispatcherAiCpu->StreamSync(stream1);
    EXPECT_EQ(ret, HCCL_SUCCESS);
}

TEST_F(DispatcherAiCpu_UT, ut_GetStreamSqeBufferAddr_2048)
{
    // sqe cnt != 0 && tailSqeIdx == 2048
    uint32_t sqHead = 0;
    uint32_t sqTail = 3;
    u64 *ptr = new u64(1);
    DeviceMem dst(ptr, 0x80, false);
    DeviceMem src(ptr, 0x80, false);
    Stream stream(streamInfo, true);
    SqCqeContext sqeCqeCtx;
    sqeCqeCtx.sqContext.inited = false;
    stream.InitSqAndCqeContext(sqHead, sqTail, &sqeCqeCtx);

    stream.sqeContext_->buffer.sqeCnt = 3;
    stream.sqeContext_->buffer.tailSqeIdx = 2048;

    auto ret = dispatcherAiCpu->MemcpyAsync(dst, src, stream);
    EXPECT_EQ(HCCL_SUCCESS, ret);
    delete ptr;

    GlobalMockObject::verify();
}

TEST_F(DispatcherAiCpu_UT, ut_aicpu_fine_granularity)
{
    uint32_t sqHead = 0;
    uint32_t sqTail = 3;
    u64 addr = 0x12345678;
    u64 value = 1;
    u64 valueaddr = (u64)&value;
    Stream stream(streamInfo, true);
    SqCqeContext sqeCqeCtx;
    sqeCqeCtx.sqContext.inited = false;
    stream.InitSqAndCqeContext(sqHead, sqTail, &sqeCqeCtx);
    stream.sqeContext_->buffer.sqeCnt = 3;
    stream.sqeContext_->buffer.tailSqeIdx = 1024;
    
    auto ret = dispatcherAiCpu->WriteValue(stream, addr, valueaddr);
    EXPECT_EQ(HCCL_SUCCESS, ret);
    bool reset = false;

    ret = dispatcherAiCpu->WaitValue(stream, addr, valueaddr, reset);
    EXPECT_EQ(HCCL_SUCCESS, ret);
}

TEST_F(DispatcherAiCpu_UT, ut_DispatcherAiCpu_SignalRecord)
{
    uint32_t sqHead = 0;
    uint32_t sqTail = 100;
    u32 *dstPtr = new u32(0);
    u32 *srcPtr = new u32(0);
    DeviceMem dst(dstPtr, 4, false);
    DeviceMem src(srcPtr, 4, false);
    Stream stream(streamInfo, true);
    SqCqeContext sqeCqeCtx;
    sqeCqeCtx.sqContext.inited = false;
    stream.InitSqAndCqeContext(sqHead, sqTail, &sqeCqeCtx);
    auto ret = dispatcherAiCpu->SignalRecord(dst, src, stream, 0, LinkType::LINK_HCCS_SW, 0);
    EXPECT_EQ(ret, HCCL_SUCCESS);
    delete dstPtr;
    delete srcPtr;

    GlobalMockObject::verify();
}