/**
 * Copyright (c) 2025 Huawei Technologies Co., Ltd.
 * This program is free software, you can redistribute it and/or modify it under the terms and conditions of
 * CANN Open Software License Agreement Version 2.0 (the "License").
 * Please refer to the License for details. You may not use this file except in compliance with the License.
 * THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
 * INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
 * See LICENSE in the root of the software repository for the full text of the License.
 */

#include "hccl_api_data.h"
#include "dispatcher.h"
#include "new/hccl_primitive_local.h"
#include "new/hccl_primitive_remote.h"
#include "hccl_thread.h"
#include "launch_context.h"
#ifdef CCL_KERNEL_AICPU
#include "device/framework/aicpu_hccl_process.h"
#endif

using namespace hccl;
thread_local LaunchContext g_threadLaunchCtx;

void AddThread(ThreadHandle thread) {
    g_threadLaunchCtx.AddThread(thread);
}

int32_t HcommLocalCopyOnThread(ThreadHandle thread, void *dst, const void *src, uint64_t len)
{
    CHK_PTR_NULL(dst);
    CHK_PTR_NULL(src);
    HCCL_DEBUG("[HcommLocalCopyOnThread]dst[%p], src[%p], len[%llu].", dst, src, len);

    HcclBuf srcBuf{const_cast<void*>(src), len, nullptr};
    HcclBuf dstBuf{dst, len, nullptr};
    AddThread(thread);
    Stream *stream = GetStream(thread);
    CHK_PTR_NULL(stream);

    return HcclLocalCopy(stream, &dstBuf, &srcBuf);
}

int32_t HcommLocalReduceOnThread(ThreadHandle thread, void *dst, const void *src, uint64_t count,
    HcommDataType dataType, HcommReduceOp reduceOp)
{
    CHK_PTR_NULL(dst);
    CHK_PTR_NULL(src);
    HCCL_DEBUG("[HcommLocalReduceOnThread]dst[%p], src[%p], count[%llu], dataType[%d], reduceOp[%d].",
        dst, src, count, dataType, reduceOp);

    HcclBuf srcBuf{const_cast<void*>(src), count * SIZE_TABLE[dataType], nullptr};
    HcclBuf dstBuf{dst, count * SIZE_TABLE[dataType], nullptr};
    HcclReduceInfo reduceInfo{static_cast<HcclDataType>(dataType), static_cast<HcclReduceOp>(reduceOp)};
    AddThread(thread);
    Stream *stream = GetStream(thread);
    CHK_PTR_NULL(stream);

    return HcclLocalCopyReduce(stream, &dstBuf, &srcBuf, reduceInfo);
}

int32_t HcommThreadNotifyRecordOnThread(ThreadHandle thread, ThreadHandle dstThread, uint32_t dstNotifyIdx)
{
    HCCL_DEBUG("[HcommThreadNotifyRecordOnThread]thread[%llu], dstThread[%p], dstNotifyIdx[%u].", thread, dstThread, dstNotifyIdx);
    AddThread(thread);
    Stream *stream = GetStream(thread);
    CHK_PTR_NULL(stream);

    LocalNotify *notify = GetNotify(dstThread, dstNotifyIdx);
    CHK_PTR_NULL(notify);

    return HcclLocalNotifyRecord(stream, notify);
}

int32_t HcommThreadNotifyWaitOnThread(ThreadHandle thread, uint32_t notifyIdx, uint32_t timeout)
{
    HCCL_DEBUG("[HcommThreadNotifyWaitOnThread]thread[%llu], notifyIdx[%u], timeout[%u].", thread, notifyIdx, timeout);
    AddThread(thread);
    Stream *stream = GetStream(thread);
    CHK_PTR_NULL(stream);
    LocalNotify *notify = GetNotify(thread, notifyIdx);
    CHK_PTR_NULL(notify);

    return HcclLocalNotifyWait(stream, notify, timeout);
}


int32_t HcommAclrtNotifyRecordOnThread(ThreadHandle thread, uint64_t dstNotifyId)
{
    AddThread(thread);
    Stream *stream = GetStream(thread);
    CHK_PTR_NULL(stream);
    HCCL_DEBUG("[HcommAclrtNotifyRecordOnThread]thread[%p], dstNotifyId[%u].", thread, dstNotifyId);
    return HcclLocalBareNotifyRecord(stream, dstNotifyId);
}

int32_t HcommAclrtNotifyWaitOnThread(ThreadHandle thread, uint64_t notifyId, uint32_t timeOut)
{
    AddThread(thread);
    Stream *stream = GetStream(thread);
    CHK_PTR_NULL(stream);
    HCCL_DEBUG("[HcommAclrtNotifyWaitOnThread]thread[%p], notifyId[%llu], timeOut[%u].",
        thread, notifyId, timeOut);
    return HcclLocalBareNotifyWait(stream, notifyId, timeOut);
}

HcclResult CommTaskPrepare(char *key, uint32_t keyLen) // host ffts+使用
{
    std::string keyStr = "temp_key";
    if (key != nullptr && keyLen != 0) {
        keyStr = std::string(key, keyLen);
        HCCL_DEBUG("[CommTaskPrepare]key[%s], keyLen[%u]", key, keyLen);
    } else {
        HCCL_DEBUG("[CommTaskPrepare]disable cache, key[%p], keyLen[%u]", key, keyLen);
    }

    return HcclTaskPrepare(const_cast<char_t*>(keyStr.c_str()), keyStr.length());
}

HcclResult CommTaskLaunch(ThreadHandle *threads, uint32_t threadNum) // host ffts+或aicpu stars使用"
{
    CHK_PTR_NULL(threads);
    CHK_PRT_RET(threadNum < 1, HCCL_ERROR("[CommTaskLaunch]threadNum is less than 1"), HCCL_E_PARA);

    std::vector<hccl::Stream> streams;
    for (uint32_t i = 0; i < threadNum; i++) {
        hccl::Stream *stream = GetStream(threads[i]);
        CHK_PTR_NULL(stream);
        streams.push_back(*stream);
    }

    return HcclTaskLaunch(streams.data(), threadNum);
}

int32_t HcommWriteOnThread(ThreadHandle thread, ChannelHandle channel, void *dst, const void *src, uint64_t len)
{
    CHK_PTR_NULL(dst);
    CHK_PTR_NULL(src);
    AddThread(thread);
    HCCL_DEBUG("[HcommWriteOnThread]dst[%p], src[%p], len[%llu].", dst, src, len);

    HcclBuf locBuf{const_cast<void*>(src), len, nullptr};
    HcclBuf rmtBuf{dst, len, nullptr};

    Stream *stream = GetStream(thread);
    CHK_PTR_NULL(stream);

    return HcclRemoteWrite(stream, reinterpret_cast<void*>(channel), &rmtBuf, &locBuf);
}

int32_t HcommWriteReduceOnThread(ThreadHandle thread, ChannelHandle channel, void *dst, const void *src,
    uint64_t count, HcommDataType dataType, HcommReduceOp reduceOp)
{
    CHK_PTR_NULL(dst);
    CHK_PTR_NULL(src);
    AddThread(thread);
    HCCL_DEBUG("[HcommWriteReduceOnThread]dst[%p], src[%p], count[%llu], dataType[%d], reduceOp[%d].",
        dst, src, count, dataType, reduceOp);

    HcclBuf locBuf{const_cast<void*>(src), count * SIZE_TABLE[dataType], nullptr};
    HcclBuf rmtBuf{dst, count * SIZE_TABLE[dataType], nullptr};
    HcclReduceInfo reduceInfo{static_cast<HcclDataType>(dataType), static_cast<HcclReduceOp>(reduceOp)};

    Stream *stream = GetStream(thread);
    CHK_PTR_NULL(stream);

    return HcclRemoteWriteReduce(stream, reinterpret_cast<void*>(channel), &rmtBuf, &locBuf, reduceInfo);
}

HcclResult CommWriteReduceWithNotify(ThreadHandle thread, ChannelHandle channel, void *dst, const void *src,
    uint64_t count, HcclDataType dataType, HcclReduceOp reduceOp, uint32_t remoteNotifyIdx)
{
    CHK_PTR_NULL(src);
    CHK_PTR_NULL(dst);
    AddThread(thread);
    HcclBuf locBuf{const_cast<void*>(src), count * SIZE_TABLE[dataType], nullptr};
    HcclBuf rmtBuf{dst, count * SIZE_TABLE[dataType], nullptr};
    HcclReduceInfo reduceInfo{dataType, reduceOp};

    Stream *stream = GetStream(thread);
    CHK_PTR_NULL(stream);

    return HcclRemoteWriteReduceWithNotify(stream, reinterpret_cast<void*>(channel), &rmtBuf, &locBuf, reduceInfo,
        remoteNotifyIdx);
}
int32_t HcommWriteWithNotifyOnThread(ThreadHandle thread, ChannelHandle channel, void *dst, const void *src,
    uint64_t len, uint32_t remoteNotifyIdx)
{
    CHK_PTR_NULL(src);
    CHK_PTR_NULL(dst);
    AddThread(thread);
    HcclBuf locBuf{const_cast<void*>(src), len, nullptr};
    HcclBuf rmtBuf{dst, len, nullptr};

    Stream *stream = GetStream(thread);
    CHK_PTR_NULL(stream);

    return HcclRemoteWriteWithNotify(stream, reinterpret_cast<void*>(channel), &rmtBuf, &locBuf, remoteNotifyIdx);
}

int32_t HcommReadOnThread(
    ThreadHandle thread, ChannelHandle channel, void *dst, const void *src, uint64_t len)
{
    CHK_PTR_NULL(dst);
    CHK_PTR_NULL(src);
    AddThread(thread);
    HCCL_DEBUG("[HcommReadOnThread]dst[%p], src[%p], len[%llu].", dst, src, len);

    HcclBuf locBuf{dst, len, nullptr};
    HcclBuf rmtBuf{const_cast<void*>(src), len, nullptr};

    Stream *stream = GetStream(thread);
    CHK_PTR_NULL(stream);

    return HcclRemoteRead(stream, reinterpret_cast<void*>(channel), &locBuf, &rmtBuf);
}

HcclResult HcommNotifyWaitOnThread(ThreadHandle thread, ChannelHandle channel, void *dst, const void *src, uint64_t count,
    HcclDataType dataType, HcclReduceOp reduceOp)
{
    CHK_PTR_NULL(dst);
    CHK_PTR_NULL(src);
    AddThread(thread);
    HCCL_DEBUG("[HcommNotifyWaitOnThread]dst[%p], src[%p], count[%llu], dataType[%d], reduceOp[%d].",
        dst, src, count, dataType, reduceOp);
    HcclBuf locBuf{dst, count * SIZE_TABLE[dataType], nullptr};
    HcclBuf rmtBuf{const_cast<void*>(src), count * SIZE_TABLE[dataType], nullptr};
    HcclReduceInfo reduceInfo{dataType, reduceOp};

    Stream *stream = GetStream(thread);
    CHK_PTR_NULL(stream);

    return HcclRemoteReadReduce(stream, reinterpret_cast<void*>(channel), &locBuf, &rmtBuf, reduceInfo);
}

int32_t HcommChannelNotifyRecordOnThread(ThreadHandle thread, ChannelHandle channel, const uint32_t remoteNotifyIdx)
{
    HCCL_DEBUG("[HcommChannelNotifyRecordOnThread]thread[%llu], channel[%llu], remoteNotifyIdx[%u].",
        thread, channel, remoteNotifyIdx);
    AddThread(thread);

    Stream *stream = GetStream(thread);
    CHK_PTR_NULL(stream);

    return HcclRemoteNotifyRecord(stream, reinterpret_cast<void*>(channel), remoteNotifyIdx);
}

int32_t HcommChannelNotifyWaitOnThread(ThreadHandle thread, ChannelHandle channel, uint32_t localNotifyIdx, uint32_t timeout)
{
    HCCL_DEBUG("[HcommChannelNotifyWaitOnThread]thread[%llu], channel[%llu], localNotifyIdx[%u], timeout[%u].",
        thread, channel, localNotifyIdx, timeout);
    AddThread(thread);
    Stream *stream = GetStream(thread);
    CHK_PTR_NULL(stream);

    return HcclRemoteNotifyWait(stream, reinterpret_cast<void*>(channel), localNotifyIdx, timeout);
}

HcclResult CommFence(ThreadHandle thread, ChannelHandle channel) // 控制前后的任务保序
{
    HCCL_DEBUG("[CommFence]thread[%llu], channel[%llu].", thread, channel);
    Stream *stream = GetStream(thread);
    CHK_PTR_NULL(stream);
    return HcclRemoteFence(stream, reinterpret_cast<void*>(channel), false);
}

int32_t HcommSetLaunchMode(const char *launchTag, HcommLaunchMode mode)
{
    HCCL_DEBUG("HcommSetLaunchMode launchTag[%s]", launchTag);
    return g_threadLaunchCtx.SetLaunchMode(launchTag, mode);
}

int32_t HcommBatchModeStart(const char *batchTag)
{
    return HcommSetLaunchMode(batchTag, HCOMM_LAUNCH_MODE_BATCH);
}

int32_t HcommBatchModeEnd(const char *batchTag)
{
    return HcommSetLaunchMode(batchTag, HCOMM_LAUNCH_MODE_EAGER);
}

int32_t HcommAcquireComm(const char* commId)
{
    CHK_PTR_NULL(commId);
#ifdef CCL_KERNEL_AICPU
    HcclCommAicpu *hcclComm = AicpuHcclProcess::AicpuGetCommbyGroup(commId);
    CHK_PRT_RET(!hcclComm, HCCL_ERROR("%s hcclComm is null, commId[%s]", __func__, commId), HCCL_E_PTR);
#else
    HCCL_INFO("%s not support, commId[%s], do nothing", __func__, commId);
#endif
    return HCCL_SUCCESS;
}

int32_t HcommReleaseComm(const char* commId)
{
    CHK_PTR_NULL(commId);
#ifdef CCL_KERNEL_AICPU
    AicpuHcclProcess::AicpuReleaseCommbyGroup(commId);
    HCCL_INFO("%s success, commId[%s]", __func__, commId);
#else
    HCCL_INFO("%s not support, commId[%s], do nothing", __func__, commId);
#endif
    return HCCL_SUCCESS;
}