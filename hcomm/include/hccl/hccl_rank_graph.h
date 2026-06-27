/**
 * Copyright (c) 2025 Huawei Technologies Co., Ltd.
 * This program is free software, you can redistribute it and/or modify it under the terms and conditions of
 * CANN Open Software License Agreement Version 2.0 (the "License").
 * Please refer to the License for details. You may not use this file except in compliance with the License.
 * THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
 * INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
 * See LICENSE in the root of the software repository for the full text of the License.
 */

#ifndef HCCL_RANK_GRAPH_H
#define HCCL_RANK_GRAPH_H

#include <arpa/inet.h>
#include "securec.h"
#include "hccl_res.h"
#ifdef __cplusplus
extern "C" {
#endif  // __cplusplus

/**
 * @brief 通信拓扑枚举
 */
typedef enum {
    COMM_TOPO_RESERVED = -1,  ///< 保留拓扑
    COMM_TOPO_CLOS = 0,       ///< CLOS互联拓扑
    COMM_TOPO_1DMESH = 1,     ///< 1DMesh互联拓扑
    COMM_TOPO_910_93 = 2,     ///< 910_93互联拓扑(带SIO)
    COMM_TOPO_310P = 3,       ///< 310P互联拓扑
} CommTopo;

/**
 * @brief 异构组网模式枚举
 * @note 描述通信域中芯片类型的混合情况，可用于优化通信算法选择
 */
typedef enum {
    HCCL_HETEROG_MODE_INVALID = -1,    ///< 无效/未初始化
    HCCL_HETEROG_MODE_HOMOGENEOUS = 0, ///< 同构组网：单一芯片类型
    HCCL_HETEROG_MODE_MIX_A2_A3,       ///< 异构组网：A2和A3芯片混合
} HcclHeterogMode;

const uint32_t COMM_LINK_MAGIC_WORD = 0x0f0e0f0f;
const uint32_t COMM_LINK_VERSION = 1;    // CommLink末尾非固定区扩展时，COMM_LINK_VERSION + 1

/**
 * @brief 通信Link信息
 * @note 支持扩展Link的属性等。由于主要用于出参，外部要根据不同的版本进行兼容处理。
 */
typedef struct {
    CommAbiHeader header;
    EndpointDesc srcEndpointDesc;
    EndpointDesc dstEndpointDesc;
    union {
        uint8_t raws[128];
        struct {
            CommProtocol linkProtocol;
        };
    } linkAttr;
} CommLink;

/**
 * @brief 初始化CommLink结构体
 * 
 * @param[inout] commLink 通信link信息列表
 * @param[in] linkNum link数量
 * @return HcclResult 执行结果状态码
 */
inline HcclResult CommLinkInit(CommLink *commLink, uint32_t linkNum)
{
    for (uint32_t idx = 0; idx < linkNum; idx++) {
        if (commLink != nullptr) {
            // 先用0xFF填充整个结构体
            (void)memset_s(commLink, sizeof(CommLink), 0xFF, sizeof(CommLink));
            
            // 初始化ABI头信息
            commLink->header.version     = COMM_LINK_VERSION;
            commLink->header.magicWord   = COMM_LINK_MAGIC_WORD;
            commLink->header.size        = sizeof(CommLink);
            commLink->header.reserved    = 0;

            // 初始化源端点和目的端点的关键字段
             if (UNLIKELY(EndpointDescInit(&commLink->srcEndpointDesc, 1) != HCCL_SUCCESS) ||
                UNLIKELY(EndpointDescInit(&commLink->dstEndpointDesc, 1) != HCCL_SUCCESS)) {
                return HCCL_E_INTERNAL;
            }

            // 初始化链路属性（显式设置保留值）
            commLink->linkAttr.linkProtocol = COMM_PROTOCOL_RESERVED;
            commLink++;  // 移动到下一个描述符
        } else {
            return HCCL_E_PTR;
        }
    }
    return HCCL_SUCCESS;
}

/**
 * @brief 获取通信域中自己的rankId
 * @param[in] comm 通信域句柄
 * @param[out] rank 自己的rankId
 * @return HcclResult 执行结果状态码
 */
extern HcclResult HcclGetRankId(HcclComm comm, uint32_t *rank);

/**
 * @brief 给定通信域，返回该通信域的rank数量
 * @param[in] comm 通信域
 * @param[out] rankSize 该通信域包含的rank数量
 * @return HcclResult 执行结果状态码
 * @code {.c}
 * // 例如4个server(8卡)的通信域
 * uint32_t rankSize;
 * HcclGetRankSize(comm, &rankSize);
 * // rankSize = 32
 * @endcode
 */
extern HcclResult HcclGetRankSize(HcclComm comm, uint32_t *rankSize);

/**
 * @brief 给定通信域，查询本rank在该通信域中的网络层次，返回分层信息
 * @param[in] comm 通信域
 * @param[out] netLayers 通信域中包含的通信网络层次，返回一个list，包含layer编号
 * @param[out] netLayerNum 网络层次列表数量
 * @return HcclResult 执行结果状态码
 * @note 使用参考：
 * @code {.c}
 * uint32_t *netLayers;
 * uint32_t layerNum;
 * HcclRankGraphGetLayers(comm, &netLayers, &layerNum);
 * // 以server内，server间两级拓扑为例
 * // netLayers = [0,1], layerNum = 2
 * @endcode
 * @warning 重要约束：
 * 1、返回的netLayers内存由库内管理，调用者严禁释放
 * 2、应及时复制返回的netLayers数据，同一通信域重复调用可能使前次结果失效
 */
extern HcclResult HcclRankGraphGetLayers(HcclComm comm, uint32_t **netLayers, uint32_t *netLayerNum);

/**
 * @brief 给定通信域和netLayer，返回本Rank所在的netInstance中的所有ranks
 * @param[in] comm 通信域
 * @param[in] netLayer 通信网络层次
 * @param[out] ranks 该层netLayer中包含的rankId列表
 * @param[out] rankNum rankId列表数量
 * @return HcclResult 执行结果状态码
 * @note 使用参考：
 * @code {.c}
 * 以4server为例，共32个rank，分为两级，8（server内）*4（server数量）
 * Rank0
 * HcclComm commTp = CreateComm([0,1,2,3,…,31]);
 * vector<uint32_t> ranks;
 * uint32_t rankNum;
 * 如果本卡为rank0
 * HcclRankGraphGetRanksByLayer( commTp, netLayer=0, &ranks, &rankNum )
 * // ranks = [0,1,2,…,7],  rankNum=8
 * HcclRankGraphGetRanksByLayer( commTp, netLayer=1, &ranks, &rankNum )
 * // ranks = [0,1,2,…,31],  rankNum=32
 * 
 * 如果本卡为rank9
 * HcclRankGraphGetRanksByLayer( commTp, netLayer=0, &ranks, &rankNum )
 * // ranks = [8,9,10,…,15],  rankNum=8
 * HcclRankGraphGetRanksByLayer( commTp, netLayer=1, &ranks, &rankNum )
 * // ranks = [0,1,2,…,31],  rankNum=32
 * @endcode
 * 说明：该接口只反映组网/拓扑情况，不反映算法情况，所以这里的netLayer1查询的是level1可连通的范围，
 * 查询结果List里是32张卡，而不是4张卡。\n
 * 例如算法选择单级全连接算法，就只使用netLayer1的链路
* @warning 重要约束：
 * 1、返回的ranks内存由库内管理，调用者严禁释放
 * 2、应及时复制返回的ranks数据，同一通信域重复调用可能使前次结果失效
 */
extern HcclResult HcclRankGraphGetRanksByLayer(HcclComm comm, uint32_t netLayer, uint32_t **ranks, uint32_t *rankNum);

/**
 * @brief 给定通信域和netLayer，返回rank数量
 * @param[in] comm 通信域句柄
 * @param[in] netLayer 通信网络层次
 * @param[out] rankNum 该netLayer的rank数量
 * @return HcclResult 执行结果状态码
 * @note 以4server为例，共32个rank，分为两级，8（server内）*4（server数量）\n使用参考：
 * @code {.c}
 * HcclComm commTp = CreateComm([0,1,2,3,…,31]);
 * uint32 rankNum;
 * HcclRankGraphGetRankSizeByLayer(commTp, level=0, &rankNum)
 * // rankNum=8
 * HcclRankGraphGetRankSizeByLayer(commTp, level=1, &rankNum )
 * // rankNum=32
 * @endcode
 * 主要用于不需要返回list的场景，只返回size即可；对于超大规模的集群，
 * 返回list会消耗较多的时间和内存
 */
extern HcclResult HcclRankGraphGetRankSizeByLayer(HcclComm comm, uint32_t netLayer, uint32_t *rankNum);

/**
 * @brief 给定通信域和netLayer，查询本rank在该netLayer的硬件连接拓扑
 * @param[in] comm 通信域
 * @param[in] netLayer 通信网络层次
 * @param[out] topoType topo类型，包括1DMesh/clos等
 * @return HcclResult 执行结果状态码
 * @note 以4server为例，共32个rank，分为两级，8（server内，为1DMesh）*4（server数量）
 * 32个Rank在netLayer1为RDMA全互联（clos网络）
 * @code {.c}
 * commTp = CreateComm([0,1,2,..,31]);
 * uint32_t topoType;
 * HcclRankGraphGetTopoTypeByLayer(commTp, netLayer=0, &topoType); // topoType=1 (1DMesh)
 * HcclRankGraphGetTopoTypeByLayer(commTp, netLayer=1, &topoType); // topoType=2 (clos)
 * @endcode
 */
extern HcclResult HcclRankGraphGetTopoTypeByLayer(HcclComm comm, uint32_t netLayer, CommTopo *topoType);

/**
 * @brief 给定通信域和netLayer，查询rankTable在该层分为多少group，以及每个group的size
 * @param[in] comm 通信域
 * @param[in] netLayer 通信网络层次
 * @param[out] instSizeList 所有inst的size组成一个列表
 * @param[out] listSize 列表大小
 * @return HcclResult 执行结果状态码
 * @note 以8（server内）*4（server间）的拓扑为例。使用参考：
 * @code {.cc}
 * commA = CreateComm([0,1,2,…,31]);
 * uint32_t *sizeList;
 * uint32_t listSize;
 * HcclRankGraphGetInstSizeListByLayer(commA, netLayer=0, &sizeList, &listSize);
 * // sizeList=[8,8,8,8], listSize=4
 * HcclRankGraphGetInstSizeListByLayer(commA, netLayer=1, &sizeList, &listSize);
 * // sizeList = [32], listSize=1
 * @endcode
 * @warning 重要约束：
 * 1、返回的instSizeList内存由库内管理，调用者严禁释放
 * 2、应及时复制返回的instSizeList数据，同一通信域重复调用可能使前次结果失效
 */
extern HcclResult HcclRankGraphGetInstSizeListByLayer(HcclComm comm, uint32_t netLayer, uint32_t **instSizeList,
    uint32_t *listSize);

/**
 * @brief 查询制定层次，源和目的之间的link信息
 * @param[in] comm 通信域
 * @param[in] netLayer 通信网络层次
 * @param[in] srcRank 源rank ID
 * @param[in] dstRank 目的rank ID
 * @param[out] links 通信链路列表
 * @param[out] linkNum 链路数量
 * @return HcclResult 执行结果状态码
 * @warning 重要约束：
 * 1、返回的links内存由库内管理，调用者严禁释放
 * 2、应及时复制返回的links数据，同一通信域重复调用可能使前次结果失效
 */
extern HcclResult HcclRankGraphGetLinks(HcclComm comm, uint32_t netLayer, uint32_t srcRank, uint32_t dstRank,
    CommLink **links, uint32_t *linkNum);

/**
 * @brief 获取通信域的异构组网模式
 * @param[in] comm 通信域句柄
 * @param[out] mode 返回的异构模式
 * @return HcclResult 执行结果状态码
 * @note 该接口用于查询当前通信域的组网模式：
 *       - HCCL_HETEROG_MODE_HOMOGENEOUS：同构组网，所有rank使用相同芯片
 *       - HCCL_HETEROG_MODE_MIX_*：异构组网，存在多种芯片混合
 * @code {.c}
 * // 使用示例：检查是否为异构组网
 * HcclHeterogMode mode;
 * HcclResult ret = HcclGetHeterogMode(comm, &mode);
 * if (ret == HCCL_SUCCESS) {
 *     switch (mode) {
 *         case HCCL_HETEROG_MODE_HOMOGENEOUS:
 *             printf("同构组网\n");
 *             break;
 *         case HCCL_HETEROG_MODE_MIX_A2_A3:
 *             printf("A2/A3异构组网\n");
 *             break;
 *         default:
 *             printf("未知组网模式\n");
 *             break;
 *     }
 * }
 * @endcode
 */
extern HcclResult HcclGetHeterogMode(HcclComm comm, HcclHeterogMode *mode);
#ifdef __cplusplus
}
#endif  // __cplusplus
#endif
