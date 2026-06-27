/**
 * Copyright (c) 2025 Huawei Technologies Co., Ltd.
 * This program is free software, you can redistribute it and/or modify it under the terms and conditions of
 * CANN Open Software License Agreement Version 2.0 (the "License").
 * Please refer to the License for details. You may not use this file except in compliance with the License.
 * THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
 * INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
 * See LICENSE in the root of the software repository for the full text of the License.
 */

#include <mutex>
#include <iterator>
#include <functional>
#include <map>
#include "framework/aicpu_hccl_process.h"
#include "common/aicpu_hccl_common.h"
#include "stream_pub.h"
#include "utils/hccl_aicpu_utils.h"
#include "framework/aicpu_communicator.h"
#include "sal_pub.h"
#include "log_control.h"
#include "cann_error_reporter.h"
#include "executor_tracer.h"
#include "dfx/aicpu_executor_tracer.h"
#include "framework/aicpu_one_side_service.h"

namespace dfx_tracer {
void ExecutorTracer::BackGroundDfx(void *info)
{
    HCCL_RUN_INFO("Start to back ground.");
    // 外部保证info有效
    auto ctx = static_cast<AicpuComContext *>(info);
    hccl::HcclCommAicpu::ResetErrMsgReport(); // 业务重新拉起的场景，重置ErrMesg上报标记位
    while (true) {
        // 停止背景线程
        if (ctx->dfxExtendInfo.commandToBackGroud == CommandToBackGroud::kStop) {
            HCCL_INFO("Back ground thread returned..");
            break;
        }
        HandleDestroyComm(ctx);
        HandleBackGround(ctx);
        bool isNotStop = false;
        StopBackGround(ctx, isNotStop);
        if (!isNotStop) {
            HCCL_RUN_INFO("stop backGround Thread");
            break;
        }
        HandleReportStatusInComm();
        StopLaunchCommandHandle(ctx);
        KfcCommandHandle(ctx);
        HandleSwitchNic(ctx);
        HandleCqeStatus(ctx);
        HandleResumeChangeLink(ctx);
        hccl::HcclOneSideServiceAicpu::HandleErrCqe();
        usleep(TEN_MILLISECOND_OF_USLEEP);
    }
    (void)dfx::CannErrorReporter::GetInstance().Clear();
}

void ExecutorTracer::HandleDestroyComm(AicpuComContext *const ctx)
{
    ReadWriteLockBase &commAicpuMapMutex = AicpuHcclProcess::AicpuGetCommMutex();
    ReadWriteLock rwlock(commAicpuMapMutex);
    rwlock.readLock();
    std::vector<std::pair<std::string, hccl::HcclCommAicpu *>> aicpuCommInfo;
    std::vector<std::string> destroyGroupName;
    (void)AicpuHcclProcess::AicpuGetCommAll(aicpuCommInfo);
    KfcCommand cmd = KfcCommand::kNone;
    for (auto &commInfo : aicpuCommInfo) {
        hccl::HcclCommAicpu *hcclAicpu = commInfo.second;
        if (hcclAicpu->GetCommInfoStatus() || hcclAicpu->GetIsInitIndOp()) {
            (void) hcclAicpu->GetKfcCommand(cmd);
            if (cmd == KfcCommand::kDestroyComm) {
                auto groupName = hcclAicpu->GetGroupName();
                HCCL_RUN_INFO("[ExecutorTracer][%s]Recv kDestroyComm cmd, group name[%s]", __func__, groupName.c_str());
                hcclAicpu->FlushUtraceInfo();
                KfcExecStatus responseStatus;
                responseStatus.execStatus.kfcStatus = KfcStatus::kDestroyComm;
                // 需要在销毁通信域前返回 kfc status到host，销毁通信域会释放TransferD2H
                s32 ret = hcclAicpu->ResponseBackGroundStatus(responseStatus);
                CHK_PRT_CONT(ret, HCCL_ERROR("[ExecutorTracer][%s]ResponseBackGroundStatus failed, group[%s], ret[%d]",
                    __func__, groupName.c_str(), ret));
                AicpuExecutorTracer::StopKfcThread(ctx, aicpuCommInfo);
                destroyGroupName.push_back(groupName);
                cmd = KfcCommand::kNone;
            }
        }
    }
    rwlock.readUnlock();

    for (auto &groupName : destroyGroupName) {
        rwlock.writeLock();
        AicpuHcclProcess::AicpuDestoryCommbyGroup(groupName);
        rwlock.writeUnlock();
    }
}

void ExecutorTracer::HandleBackGround(AicpuComContext *const ctx)
{
    AicpuExecutorTracer::HandleBackGround(ctx);
}

// stop 背景线程
void ExecutorTracer::StopBackGround(AicpuComContext *const ctx, bool &isNotStop)
{
    if (ctx->commOpenStatus) {
        isNotStop = true;
    } else {
        ReadWriteLockBase &commAicpuMapMutex = AicpuHcclProcess::AicpuGetCommMutex();
        ReadWriteLock rwlock(commAicpuMapMutex);
        rwlock.readLock();
        std::vector<std::pair<std::string, hccl::HcclCommAicpu *>> aicpuCommInfo;
        (void)AicpuHcclProcess::AicpuGetCommAll(aicpuCommInfo);
        for (auto &commInfo : aicpuCommInfo) {
            hccl::HcclCommAicpu *hcclAicpu = commInfo.second;
            if (hcclAicpu->GetCommInfoStatus() || hcclAicpu->GetIsInitIndOp()) {
                isNotStop = true;
            }
        }
        rwlock.readUnlock();
    }

    if (!hccl::HcclOneSideServiceAicpu::isAllDestroy()) {
        isNotStop = true;
    }
}

void ExecutorTracer::StopBackGroundDfx(void *info)
{
    // 外部保证info有效
    auto ctx = static_cast<AicpuComContext *>(info);
    ctx->dfxExtendInfo.commandToBackGroud = CommandToBackGroud::kStop;
    HCCL_INFO("Stop back ground thread..");
}

// handle StopLaunch Command
void ExecutorTracer::StopLaunchCommandHandle(AicpuComContext *const ctx)
{
    AicpuExecutorTracer::StopLaunchCommandHandle(ctx);
    ReadWriteLockBase &commAicpuMapMutex = AicpuHcclProcess::AicpuGetCommMutex();
    ReadWriteLock rwlock(commAicpuMapMutex);
    rwlock.readLock();
    std::vector<std::pair<std::string, hccl::HcclCommAicpu *>> aicpuCommInfo;
    (void)AicpuHcclProcess::AicpuGetCommAll(aicpuCommInfo);
    KfcCommand cmd = KfcCommand::kNone;
    for (auto &commInfo : aicpuCommInfo) {
        hccl::HcclCommAicpu *hcclAicpu = commInfo.second;
        cmd = KfcCommand::kNone;
        if (hcclAicpu->GetCommInfoStatus()) {
            if (!hcclAicpu->GetNsStopLaunchStatus()) {
                (void)hcclAicpu->BackGroundGetCmd(cmd);
                if (cmd == KfcCommand::NsStopLaunch) {
                    if (!hcclAicpu->BackGroundGetOpStatus()) {
                        (void)hcclAicpu->BackGroundSetStatus(KfcStatus::kStoplaunch);
                        hcclAicpu->SetCommRecoveryFlag(true);
                        hcclAicpu->SetNsStopLaunchStatus(true);
                        HCCL_DEBUG("[NsRecovery][backGround]send in aicpu environment");
                    }
                }
            }
        }
    }
    rwlock.readUnlock();
}

// handle StopExec and Clean Command
void ExecutorTracer::KfcCommandHandle(AicpuComContext *const ctx)
{
    AicpuExecutorTracer::KfcCommandHandle(ctx);
    ReadWriteLockBase &commAicpuMapMutex = AicpuHcclProcess::AicpuGetCommMutex();
    ReadWriteLock rwlock(commAicpuMapMutex);
    rwlock.readLock();
    std::vector<std::pair<std::string, hccl::HcclCommAicpu *>> aicpuCommInfo;
    (void)AicpuHcclProcess::AicpuGetCommAll(aicpuCommInfo);
    for (auto &commItem : aicpuCommInfo) {
        hccl::HcclCommAicpu *commInfo = commItem.second;
        if (commInfo->GetCommInfoStatus()) {
            if (commInfo->GetCommRecoveryFlag()) {
                HandleAICPUCommand(commInfo);
            }
        }
    }
    rwlock.readUnlock();
}

// handle switch nic command
void ExecutorTracer::HandleSwitchNic(AicpuComContext *const ctx)
{
    ReadWriteLockBase &commAicpuMapMutex = AicpuHcclProcess::AicpuGetCommMutex();
    ReadWriteLock rwlock(commAicpuMapMutex);
    rwlock.readLock();
    std::vector<std::pair<std::string, hccl::HcclCommAicpu *>> aicpuCommInfo;
    (void)AicpuHcclProcess::AicpuGetCommAll(aicpuCommInfo);
    for (auto &commItem : aicpuCommInfo) {
        hccl::HcclCommAicpu *hcclAicpu = commItem.second;
        if (hcclAicpu->GetCommInfoStatus()) {
            KfcCommand kfcCmd = KfcCommand::kNone;
            (void) hcclAicpu->BackGroundGetCmd(kfcCmd);
            if (kfcCmd == KfcCommand::kSwitchNic) {
                auto groupName = hcclAicpu->GetGroupName();
                HCCL_RUN_INFO("[ExecutorTracer][%s]group name[%s], aicpu start switch nic",
                    __func__, groupName.c_str());
                HcclResult ret = hcclAicpu->SwitchNic();

                KfcExecStatus switchResp;
                if (ret == HCCL_SUCCESS) {
                    switchResp.execStatus.kfcStatus = KfcStatus::kSwitchSuccess;
                    (void) hcclAicpu->ResponseBackGroundStatus(switchResp);
                } else {
                    switchResp.execStatus.kfcStatus = KfcStatus::kSwitchFail;
                    (void) hcclAicpu->ResponseBackGroundStatus(switchResp);
                }
                HCCL_INFO("[ExecutorTracer][%s]group name[%s], aicpu finish switch nic, ret[%u]",
                    __func__, groupName.c_str(), ret);
            }
        }
    }
    rwlock.readUnlock();
}

void ExecutorTracer::HandleResumeChangeLink(AicpuComContext *const ctx) 
{
    ReadWriteLockBase &commAicpuMapMutex = AicpuHcclProcess::AicpuGetCommMutex();
    ReadWriteLock rwlock(commAicpuMapMutex);
    rwlock.readLock();
    std::vector<std::pair<std::string, hccl::HcclCommAicpu *>> aicpuCommInfo;
    (void)AicpuHcclProcess::AicpuGetCommAll(aicpuCommInfo);
    for (auto &commItem : aicpuCommInfo) {
        hccl::HcclCommAicpu *hcclAicpu = commItem.second;
        if (hcclAicpu == nullptr) {
            HCCL_ERROR("[ExecutorTracer][%s]hcclAicpu is nullptr", __func__);
        }
        if (hcclAicpu != nullptr && hcclAicpu->GetCommInfoStatus()) {
            KfcCommand kfcCmd = KfcCommand::kNone;
            (void) hcclAicpu->BackGroundGetCmd(kfcCmd);
            if (kfcCmd == KfcCommand::NsChangeLink) {
                auto groupName = hcclAicpu->GetGroupName();
                HCCL_INFO("[ExecutorTracer][resume][%s]group name[%s], resume aicpu, start change link",
                    __func__, groupName.c_str());
                HcclResult ret = hcclAicpu->ResumeChangeLink();
                KfcExecStatus resumeResp;
                if (ret == HCCL_SUCCESS) {
                    resumeResp.execStatus.kfcStatus = KfcStatus::kResumeChanged;
                    HCCL_INFO("[ExecutorTracer][resume][%s]group name[%s], resume aicpu, change link, kResumeChanged",__func__, groupName.c_str());
                } else {
                    resumeResp.execStatus.kfcStatus = KfcStatus::kResumeError;
                    HCCL_INFO("[ExecutorTracer][resume][%s]group name[%s], resume aicpu, change link, kResumeError",__func__, groupName.c_str());
                }
                (void) hcclAicpu->ResponseBackGroundStatus(resumeResp);
                HCCL_INFO("[ExecutorTracer][%s]group name[%s], resume process, finish change link, ret[%u]",
                    __func__, groupName.c_str(), ret);
            }
        }
    }
    rwlock.readUnlock();
}

void ExecutorTracer::HandleCqeStatusInComm()
{
    ReadWriteLockBase &commAicpuMapMutex = AicpuHcclProcess::AicpuGetCommMutex();
    ReadWriteLock rwlock(commAicpuMapMutex);
    rwlock.readLock();
    std::vector<std::pair<std::string, hccl::HcclCommAicpu *>> aicpuCommInfo;
    (void)AicpuHcclProcess::AicpuGetCommAll(aicpuCommInfo);

    for (auto &commInfo : aicpuCommInfo) {
        std::vector<hccl::Stream> streams;
        hccl::HcclCommAicpu *hcclAicpu = commInfo.second;

        // 通信域走自定义算子流程初始化，需要轮询thread状态
        if (hcclAicpu->GetIsInitIndOp()) {
            hcclAicpu->HandleIndOpCqe();
        }

        if (!hcclAicpu->GetCommInfoStatus()) { // 已结束, 不再轮询
            continue;
        }
        DfxExtendInfo* dfxInfo = hcclAicpu->GetDfxExtendInfo();
        if ((dfxInfo->cqeStatus != dfx::CqeStatus::kDefault) && (dfxInfo->cqeStatus != dfx::CqeStatus::kCqeException)) {
            continue;
        }

        (void)hcclAicpu->GetStreamAll(streams);
        for (hccl::Stream &stream : streams) {
            hcclAicpu->HandleCqeException(stream, false);
        }
    }
    rwlock.readUnlock();
}

void ExecutorTracer::HandleReportStatusInComm()
{
    ReadWriteLockBase &commAicpuMapMutex = AicpuHcclProcess::AicpuGetCommMutex();
    ReadWriteLock rwlock(commAicpuMapMutex);
    rwlock.readLock();
    std::vector<std::pair<std::string, hccl::HcclCommAicpu *>> aicpuCommInfo;
    (void)AicpuHcclProcess::AicpuGetCommAll(aicpuCommInfo);

    for (auto &commInfo : aicpuCommInfo) {
        hccl::HcclCommAicpu *hcclAicpu = commInfo.second;

        if (!hcclAicpu || !hcclAicpu->GetCommInfoStatus()) { // 已结束, 不再轮询
            continue;
        }

        u32 deviceId = hcclAicpu->GetDevId();

        std::queue<dfx::ReportStatus> reportStatusQueue;
        (void)hcclAicpu->GetReportStatusQueue(reportStatusQueue);

        while (!reportStatusQueue.empty()) {
            dfx::ReportStatus reportStatus = reportStatusQueue.front();
            HCCL_INFO("Reporting opRetry status[%u] to dp frame, deviceId[%u], report queue size[%u].",
                reportStatus, deviceId, reportStatusQueue.size());
            HcclResult ret = dfx::CannErrorReporter::GetInstance().UpdateSensorNode(deviceId, reportStatus);
            if (ret != HCCL_SUCCESS) {
                HCCL_WARNING("Fail to report reportStatus[%u] to dp frame, status droped, deviceId[%u].",
                    reportStatus, deviceId);
            }
            reportStatusQueue.pop();
        }
    }
    rwlock.readUnlock();
}

void ExecutorTracer::HandleCqeStatus(AicpuComContext *const ctx)
{
    HandleCqeStatusInComm();
    AicpuExecutorTracer::HandleCqeStatus(ctx);
}

void ExecutorTracer::SetCqeQueryInput(const uint32_t devId, const HcclComStreamInfo &streamInfo,
    CqeQueryInput &cqeQueryInput)
{
    cqeQueryInput.devId = devId;
    cqeQueryInput.streamId = streamInfo.actualStreamId;
    cqeQueryInput.sqId = streamInfo.sqId;
    cqeQueryInput.cqId = streamInfo.logicCqId;
    cqeQueryInput.type = static_cast<uint32_t>(DRV_LOGIC_TYPE);
}

void ExecutorTracer::HandleAICPUCommand(hccl::HcclCommAicpu *const commInfo){
    using CommandCall = std::function<void(hccl::HcclCommAicpu *const commInfo)>;
    static std::map<KfcCommand, CommandCall> commandAicpuHandles = {
        {KfcCommand::NsStopExec, AICPUcommandHandles::NsCommStop},
        {KfcCommand::NsClear, AICPUcommandHandles::NsCommClean}};
    KfcCommand cmd = KfcCommand::kNone;
    (void) commInfo->BackGroundGetCmd(cmd);
    auto iter = commandAicpuHandles.find(cmd);
    if (iter == commandAicpuHandles.cend()) {
        return;
    }
    HCCL_DEBUG("Start to run aicpu command %ld", cmd);
    iter->second(commInfo);
}

void AICPUcommandHandles::NsCommStop(hccl::HcclCommAicpu *const commInfo)
{
    bool streamStatus = commInfo->GetCommInfoStreamStatus();
    if (streamStatus) {
        std::string groupName = commInfo->GetGroupName();
        commInfo->SetCommInfoStreamStatus(false);
        HCCL_RUN_INFO("[NsRecovery][NsCommStop] groupName[%s]", groupName.c_str());
        commInfo->NsCommStop();
    }
}

void AICPUcommandHandles::NsCommClean(hccl::HcclCommAicpu *const commInfo){
    bool streamStatus = commInfo->GetCommInfoStreamStatus();
    if (!streamStatus) {
        std::string groupName = commInfo->GetGroupName();
        commInfo->SetCommInfoStreamStatus(true);
        HCCL_RUN_INFO("[NsRecovery][NsCommClean] groupName[%s]", groupName.c_str());
        commInfo->NsCommClean();
        commInfo->SetCommRecoveryFlag(false);
    }
}
}  // namespace dfx_tracer
