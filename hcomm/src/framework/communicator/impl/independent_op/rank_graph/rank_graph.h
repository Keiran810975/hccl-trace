/**
 * Copyright (c) 2025 Huawei Technologies Co., Ltd.
 * This program is free software, you can redistribute it and/or modify it under the terms and conditions of
 * CANN Open Software License Agreement Version 2.0 (the "License").
 * Please refer to the License for details. You may not use this file except in compliance with the License.
 * THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
 * INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
 * See LICENSE in the root of the software repository for the full text of the License.
 */

#ifndef RANK_GRAPH_H
#define RANK_GRAPH_H

#include "topoinfo_struct.h"
#include "hccl_api.h"
#include "hccl_common.h"
#include "hccl_impl_pub.h"
#include "hccl_rank_graph.h"
#include "hccl_rankgraph.h"
namespace hccl {
constexpr uint32_t HCCL_NETLAYER_0 = 0;
constexpr uint32_t HCCL_NETLAYER_1 = 1;
constexpr uint32_t HCCL_NETLAYER_2 = 2;

class RankGraph {
struct RankGraphInfo {
    RankInfo_t rankInfo;  // rank → server / supernode 等归属
    std::vector<EndpointDesc> endPoints; // 通信端点信息
};

enum class HcclNetLayerlevel {
    HCCL_NetLayer_L0 = 0,
    HCCL_NetLayer_L1,
    HCCL_NetLayer_L2,
    HCCL_NetLayer_MAX,
};

public:
    HcclResult Init(const RankTable_t& rankTable, const HcclTopoAttr &topoAttr);
    HcclResult Init(const HcclTopoAttr &topoAttr);
    HcclResult GetLinks(uint32_t netLayer, uint32_t srcRank, uint32_t dstRank, CommLink** linkList,
        uint32_t* listSize);
    HcclResult GetHeterogMode(HcclHeterogMode *mode) const;
    // 根据 rankId 获取 rank 信息
    const RankInfo_t* FindRank(uint32_t rankId) const;
    HcclResult GetRankGraphInfo(GraphType type, void **graph, uint32_t *len);
    HcclResult GetNetLayers(uint32_t **netLayers, uint32_t *netLayerNum);
    HcclResult GetInstTopoTypeByNetLayer(uint32_t netLayer, CommTopo *topoType);
    HcclResult GetInstSizeByNetLayer(uint32_t netLayer, uint32_t *rankNum);
    HcclResult GetInstRanksByNetLayer(uint32_t netLayer, uint32_t **rankList, uint32_t *rankNum);
    HcclResult GetInstSizeListByNetLayer(uint32_t netLayer, uint32_t **instSizeList, uint32_t *listSize);
    
private:
    HcclResult DevTypeToCommProtocol(DevType &type, CommProtocol &protocol);
    HcclResult BuildRankGraphInfo(const RankInfo_t &rankItem, const CommProtocol &protocol, RankGraphInfo &outInfo);
    CommProtocol GetCommProtocolFromRankInfo(const RankInfo_t &srcInfo, const RankInfo_t &dstInfo, uint32_t netLayer);
    HcclResult InitRankInfo();
    HcclResult InitServerRankInfo();
    HcclResult InitSuperPodRankInfo();
    HcclResult InitNetLayer();
    HcclResult InitGraphRankInfo();
    CommProtocol GetCommProtocolInSameServer(const RankInfo_t &srcInfo, const RankInfo_t &dstInfo);
    CommProtocol GetCommProtocolBetweenServers(const RankInfo_t &srcInfo, const RankInfo_t &dstInfo);
    bool NeedIgnoreEndPoints(CommProtocol srcProtocol, CommProtocol dstProtocol, CommProtocol linkProtocol);
    void PrintLinksInfo(CommLink &link);
 	bool IsRoceInSameServer(uint32_t netLayer, const RankInfo_t &srcInfo, const RankInfo_t &dstInfo);
    HcclResult InitHeterogMode();
    RankTable_t rankTable_;
    // 根据 rankId 获取 RankInfo_t 与 EndPoint信息
    std::unordered_map<uint32_t, RankGraphInfo> rankIndex_;
    // 根据 srcRank dstRank 获取CommLink信息
    std::map<std::tuple<uint32_t, uint32_t, uint32_t>, std::vector<CommLink>> rankPairInfo_;
    std::vector<uint32_t> netLayer_;
    std::unordered_map<uint32_t, std::vector<u32>> rankList_;      //level->rankList
    std::unordered_map<uint32_t, std::vector<u32>> rankSizeList_;  //level->rankSizeList
    std::vector<RankInfo_t> rankGraph_;
    std::vector<struct GraphRankInfo> graphRankInfo_;
    HcclTopoAttr topoAttr_;
    RankInfo rankData_;         // 当前rank的相关信息
    HcclHeterogMode heterogMode_{HcclHeterogMode::HCCL_HETEROG_MODE_INVALID};    // 组网异构&同构形态
    DevType devType_ = DevType::DEV_TYPE_NOSOC;

    // 通信域在当前superPod内, 按照serverIdx划分的所有rank信息
    std::map<u32, std::vector<RankInfo> > serverToRank_;
    // 通信域所有rank的信息, 按照superPodId -> RankInfo 的结构划分
    std::map<u32, std::vector<RankInfo> > superPodToRank_;
};
} // namespace hccl
#endif