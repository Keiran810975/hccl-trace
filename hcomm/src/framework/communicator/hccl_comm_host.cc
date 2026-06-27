/**
 * Copyright (c) 2025 Huawei Technologies Co., Ltd.
 * This program is free software, you can redistribute it and/or modify it under the terms and conditions of
 * CANN Open Software License Agreement Version 2.0 (the "License").
 * Please refer to the License for details. You may not use this file except in compliance with the License.
 * THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
 * INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
 * See LICENSE in the root of the software repository for the full text of the License.
 */

#include <atomic>
#include <algorithm>
#include <arpa/inet.h>
#include <fstream>
#include <fcntl.h>
#include <unistd.h>
#include <hccl/hccl_types.h>
#include "device_capacity.h"
#include "hccl_communicator.h"
#include "hccl_comm_pub.h"
#include "task_abort_handler_pub.h"
#include "coll_alg_utils.h"
#include "env_config.h"
#include "i_hccl_one_sided_service.h"

namespace hccl
{
    HcclResult hcclComm::AllReduce(const std::string &tag, void *inputPtr, void *outputPtr, u64 count,
                                   HcclDataType dataType, HcclReduceOp op, HcclRtStream stream, SyncMode syncMode)
    {
        /* 增加输出日志关键字 */
        HCCL_DEBUG("HCCL_KEY_INFO: tag[%s], input_ptr[%p], output_ptr[%p], count[%llu], data_type[%s], op[%s]",
                   tag.c_str(), inputPtr, outputPtr, count, GetDataTypeEnumStr(dataType).c_str(),
                   GetReduceOpEnumStr(op).c_str());

        /* * 入参检查 */
        CHK_PTR_NULL(stream);
        CHK_PTR_NULL(inputPtr);
        CHK_PTR_NULL(outputPtr);

        CHK_PRT_RET(tag.empty(), HCCL_ERROR("[HcclComm][AllReduce]errNo[0x%016llx] AllReduce tag length is 0", HCCL_ERROR_CODE(HCCL_E_PARA)), HCCL_E_PARA);

        CHK_RET(communicator_->CheckCount(count));
        CHK_RET(communicator_->CheckDataType(dataType, true));
        CHK_RET(communicator_->CheckReduceDataType(dataType, op));
        CHK_RET(communicator_->CheckReductionOp(op));
        HcclResult ret = communicator_->AllReduce(tag, inputPtr, outputPtr, count, dataType, op, stream, syncMode);
        if (ret != HCCL_SUCCESS)
        {
            PrintSubmittedOpCnt(tag, ret);
            return ret;
        }

        return HCCL_SUCCESS;
    }

    HcclResult hcclComm::AllReduceOutPlace(const std::string &tag, void *inputPtr, void *outputPtr, u64 count,
                                           HcclDataType dataType, HcclReduceOp op, HcclRtStream stream, SyncMode syncMode)
    {
        /* 增加输出日志关键字 */
        HCCL_DEBUG("HCCL_KEY_INFO: tag[%s], input_ptr[%p], output_ptr[%p], count[%llu], data_type[%s], op[%s]", tag.c_str(),
                   inputPtr, outputPtr, count, GetDataTypeEnumStr(dataType).c_str(), GetReduceOpEnumStr(op).c_str());

        /* * 入参检查 */
        CHK_RET(communicator_->CheckDataType(dataType, true));
        CHK_RET(communicator_->CheckReduceDataType(dataType, op));
        HcclResult ret = communicator_->AllReduceOutPlace(tag, inputPtr, outputPtr, count, dataType, op, stream, syncMode);
        if (ret != HCCL_SUCCESS)
        {
            PrintSubmittedOpCnt(tag, ret);
            return ret;
        }

        return HCCL_SUCCESS;
    }

    HcclResult hcclComm::GetOneSidedService(IHcclOneSidedService **service)
    {
        CHK_RET(communicator_->GetOneSidedService(service));

        return HCCL_SUCCESS;
    }

    HcclResult hcclComm::InitOneSidedServiceNetDevCtx(u32 remoteRankId)
    {
        CHK_RET(communicator_->InitOneSidedServiceNetDevCtx(remoteRankId));
        return HCCL_SUCCESS;
    }

    HcclResult hcclComm::OneSidedServiceStartListen(NicType nicType, HcclNetDevCtx netDevCtx)
    {
        CHK_SMART_PTR_NULL(communicator_);
        CHK_RET(communicator_->OneSidedServiceStartListen(nicType, netDevCtx));
        return HCCL_SUCCESS;
    }

    HcclResult hcclComm::GetOneSidedServiceDevIpAndPort(NicType nicType, HcclIpAddress& ipAddress, u32& port)
    {
        CHK_SMART_PTR_NULL(communicator_);
        CHK_RET(communicator_->GetOneSidedServiceDevIpAndPort(nicType, ipAddress, port));
        return HCCL_SUCCESS;
    }

    HcclResult hcclComm::DeinitOneSidedService()
    {
        CHK_SMART_PTR_NULL(communicator_);
        CHK_RET(communicator_->DeinitOneSidedService());
        return HCCL_SUCCESS;
    }

    HcclResult hcclComm::RegistTaskAbortHandler() const
    {
        HCCL_RUN_INFO("RegistTaskAbortHandler begin, group[%s]", identifier_.c_str());
        CHK_RET(TaskAbortHandler::Init(communicator_.get()));
        return HCCL_SUCCESS;
    }

    HcclResult hcclComm::UnRegistTaskAbortHandler() const
    {
        HCCL_RUN_INFO("UnRegistTaskAbortHandler begin, group[%s]", identifier_.c_str());
        CHK_RET(TaskAbortHandler::DeInit(communicator_.get()));
        return HCCL_SUCCESS;
    }

    HcclResult hcclComm::RegisterCommUserMem(void* addr, u64 size, void **handle)
    {
        CHK_SMART_PTR_NULL(communicator_);
        CHK_RET(communicator_->RegisterCommUserMem(addr, size, handle));
        return HCCL_SUCCESS;
    }
 
    HcclResult hcclComm::DeregisterCommUserMem(void* handle)
    {
        CHK_SMART_PTR_NULL(communicator_);
        CHK_RET(communicator_->DeregisterCommUserMem(handle));
        return HCCL_SUCCESS;
    }
 
    HcclResult hcclComm::ExchangeCommUserMem(void* handle, std::vector<u32>& peerRanks)
    {
        CHK_SMART_PTR_NULL(communicator_);
        return communicator_->ExchangeCommUserMem(handle, peerRanks);
    }

    HcclResult hcclComm::SetIndependentOpConfig(const CommConfig &commConfig, const RankTable_t &rankTable)
    {
        CHK_SMART_PTR_NULL(communicator_);
        HcclTopoAttr topoAttr = communicator_->GetTopoAttr();
        aclrtBinHandle binHandle = communicator_->GetBinHandle();
        HDCommunicateParams kfcControlTransferH2DParams;
        HDCommunicateParams kfcStatusTransferD2HParams;
        std::function<bool()> getAicpuCommState = [this]() { return this->GetIndependentOp().GetAicpuCommState(); };
        CHK_RET(communicator_->GetHDCommunicate(kfcControlTransferH2DParams, kfcStatusTransferD2HParams));
        CHK_RET(communicator_->SetGetAicpuCommState(getAicpuCommState));
        CHK_RET(GetIndependentOp().SetIndependentOpConfig(commConfig, rankTable, topoAttr, binHandle,
            kfcControlTransferH2DParams, kfcStatusTransferD2HParams));
        return HCCL_SUCCESS;
    }

    HcclResult hcclComm::ReleaseChannel()
    {
        return independentOp_.GetChannelManager().ReleaseChannel();
    }

    HcclResult hcclComm::InitIndependentOp()
    {
        if (communicator_ != nullptr) {
            communicator_->SetReleaseChannel([this]() -> HcclResult { return this->ReleaseChannel(); });
        }
        ChannelManagerCallbacks channelCallbacks;
        channelCallbacks.indOpTransportAlloc = [this](const std::string &tag, OpCommTransport &opCommTransport, 
            bool isAicpuModeEn) -> HcclResult {
            return this->IndOpTransportAlloc(tag, opCommTransport, isAicpuModeEn);
        };
        channelCallbacks.getRankLists = [this]() -> std::vector<RankInfo> { return this->GetRankLists(); };
        return independentOp_.SetChannelCallbacks(channelCallbacks);
    }

    IndependentOp& hcclComm::GetIndependentOp() {
        return independentOp_;
    }
    HcclResult hcclComm::PrepareChannelMem(const std::string &tag, TransportIOMem &transMem)
    {
        // 获取本地cclbuffer
        CommBuffer commBuffer;
        CHK_RET(GetIndependentOp().GetCommMemMgr().GetHcclBuffer(&commBuffer));
        DeviceMem cclbuffer =  DeviceMem::create(commBuffer.addr, commBuffer.size);
        CHK_PTR_NULL(cclbuffer.ptr());

        // 获取通信域内存
        IndOpMem indOpMem{};
        std::vector<HcclMem> localMemVec{};
        CHK_RET(GetIndependentOp().GetCommMemMgr().CommGetLocalRegMemByTag(tag, localMemVec));
        for (const HcclMem& mem : localMemVec) {
            if (mem.type == HCCL_MEM_TYPE_HOST) {
                indOpMem.userHostMem.push_back(HostMem::create(mem.addr, mem.size));
                CHK_PTR_NULL(indOpMem.userHostMem.back().ptr());
            } else if (mem.type == HCCL_MEM_TYPE_DEVICE) {
                indOpMem.userDeviceMem.push_back(DeviceMem::create(mem.addr, mem.size));
                CHK_PTR_NULL(indOpMem.userDeviceMem.back().ptr());
            }
        }
        transMem.indOpMem = indOpMem;
        transMem.cclInputMem = cclbuffer;
        transMem.cclOutputMem = cclbuffer;
        return HCCL_SUCCESS;
    }
    HcclResult hcclComm::IndOpTransportAlloc(const std::string &tag, OpCommTransport &opCommTransport, bool isAicpuModeEn)
    {
        CHK_SMART_PTR_NULL(communicator_);
        TransportIOMem transMem;
        CHK_RET(PrepareChannelMem(tag, transMem));
        std::string commId = GetIdentifier();
        return communicator_->IndOpTransportAlloc(tag, opCommTransport, transMem, isAicpuModeEn);
    }
    HcclResult hcclComm::CommGetNetLayers(uint32_t **netLayers, uint32_t *netLayerNum)
    {
        return communicator_->CommGetNetLayers(netLayers, netLayerNum);
    }
    
    HcclResult hcclComm::CommGetInstSizeByNetLayer(uint32_t netLayer, uint32_t *rankNum)
    {
        return communicator_->CommGetInstSizeByNetLayer(netLayer, rankNum);
    }
    
    HcclResult hcclComm::CommGetInstTopoTypeByNetLayer(uint32_t netLayer, u32 *topoType)
    {
        return communicator_->CommGetInstTopoTypeByNetLayer(netLayer, topoType);
    }
    HcclResult hcclComm::GetNetLayers(uint32_t **netLayers, uint32_t *netLayerNum)
    {
        return communicator_->GetNetLayers(netLayers, netLayerNum);
    }
    
    HcclResult hcclComm::GetInstSizeByNetLayer(uint32_t netLayer, uint32_t *rankNum)
    {
        return communicator_->GetInstSizeByNetLayer(netLayer, rankNum);
    }
    
    HcclResult hcclComm::GetInstTopoTypeByNetLayer(uint32_t netLayer, CommTopo *topoType)
    {
        return communicator_->GetInstTopoTypeByNetLayer(netLayer, topoType);
    }

    HcclResult hcclComm::GetInstRanksByNetLayer(uint32_t netLayer, uint32_t **rankList, uint32_t *rankNum)
    {
        return communicator_->GetInstRanksByNetLayer(netLayer, rankList, rankNum);
    }
    
    HcclResult hcclComm::GetInstSizeListByNetLayer(uint32_t netLayer, uint32_t **instSizeList, uint32_t *listSize)
    {
        return communicator_->GetInstSizeListByNetLayer(netLayer, instSizeList, listSize);
    }

    HcclResult hcclComm::GetRankGraph(GraphType type, void **graph, uint32_t *len)
    {
        return communicator_->GetRankGraph(type, graph, len);
    }

    HcclResult hcclComm::GetLinks(uint32_t netLayer, uint32_t srcRank, uint32_t dstRank,
        CommLink **linkList, uint32_t *listSize)
    {
        return communicator_->GetLinks(netLayer, srcRank, dstRank, linkList, listSize);
    }

    HcclResult hcclComm::GetHeterogMode(HcclHeterogMode *mode)
    {
        return communicator_->GetHeterogMode(mode);
    }
} // namespace hccl
