/**
 * Copyright (c) 2025 Huawei Technologies Co., Ltd.
 * This program is free software, you can redistribute it and/or modify it under the terms and conditions of
 * CANN Open Software License Agreement Version 2.0 (the "License").
 * Please refer to the License for details. You may not use this file except in compliance with the License.
 * THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
 * INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
 * See LICENSE in the root of the software repository for the full text of the License.
 */

#ifndef HCCL_API_H
#define HCCL_API_H

#include "hccl_types.h"
#include <stdint.h>
#include <securec.h>
#include <arpa/inet.h>
#include <hccl/base.h>
#include "acl/acl_rt.h"
#include "hccl_res.h"
#include "hccl_comm.h"
#include "hccl_rank_graph.h"
#include "hccl_mem_defs.h"
#ifdef __cplusplus
extern "C" {
#endif  // __cplusplus

/**
 * @brief 通信的rank图类型
 */
typedef enum {
    RANK_GRAPH_RESERVED = -1,   ///< 保留的rank图类型
    RANK_GRAPH_910_93 = 0,      ///< 910_93 rank图类型
} GraphType;

/**
 * @brief 获取通信域中的rank图
 * @param comm 通信域句柄
 * @param rankGraph 通信域中的rank图
 * @return HcclResult 执行结果状态码
 * @note 外部使用rankGraph，但不能释放rankGraph内存
 * @warning
 */
extern HcclResult HcclGetRankGraph(HcclComm comm, GraphType type, void **graph, uint32_t *len);

/**
 * @brief 获取通道通知数量
 * @param[in] channel 通道句柄
 * @param[out] notifyNum 通知槽数量
 * @return HcclResult 执行结果状态码
 */
extern HcclResult HcclChannelGetNotifyNum(HcclComm comm, ChannelHandle channel, uint32_t *notifyNum);

/**
 * @defgroup 运行时接口
 * @{
 */

 /**
 * @defgroup 运行时接口-类型定义
 * @{
 */

/**
 * @brief 根节点信息
 * @note 根节点信息包含网络地址、标识等信息，对外透明。
 */
typedef struct {
    char internal[HCCL_ROOT_INFO_BYTES];
} HcclRootInfoV2;

/**
 * @brief 通信域初始化配置
 * @warning
 */
typedef struct {
    char reserved[HCCL_COMM_CONFIG_INFO_BYTES];
    uint32_t hcclBufferSize;    ///< ccl buf大小
    uint32_t hcclDeterministic;
    char hcclCommName[COMM_NAME_MAX_LENGTH];
    char hcclUdi[UDI_MAX_LENGTH];
    uint32_t hcclOpExpansionMode;   ///< 0:默认值  1:host  2:aicpu  3:aiv
    uint32_t hcclRdmaTrafficClass;
    uint32_t hcclRdmaServiceLevel;
    uint32_t hcclWorldRankID;
    uint64_t hcclJobID;
    int32_t commEngine;             ///< 通信引擎（0: HOST CPU；1: HOST CPU TS；...)（参考CommEngine，从hcclOpExpansionMode变更）
    uint32_t threadNum;             ///< thread数量（新增）
    uint32_t notifyNumPerThread;    ///< 每个thread的notify数量（新增）
} HcclCommConfigV2;

/**
 * @brief 内存注册属性
 * @warning
 */
typedef union {
    struct {
    uint64_t requireShare : 1; ///< 是否允许注册的内存共享给其它rank
    uint64_t rsvd : 63;        ///< 保留字段
    };
    uint64_t value;
} HcclRegMemAttr;

/**
 * @brief 缓存段元数据描述结构体
 */
typedef struct {
    HcclMemType type; ///< 缓存物理位置类型，参见HcclMemType
    void *addr;       ///< 缓存地址
    uint64_t size;    ///< 缓存区域字节数
} CommBuffer;

typedef enum {
    NOTIFY_TYPE_RESERVED = -1,
    NOTIFY_TYPE_RTS_NOTIFY = 0,
    NOTIFY_TYPE_RTS_EVENT = 1,
    NOTIFY_TYPE_DEVICE_MEM = 2,
} NotifyType;

typedef uint64_t NotifyHandle;

/**
 * @brief 基于通信域申请Notify
 * 
 * @param hcclComm 
 * @param commEngine 
 * @param notifyType 
 * @param notifyHandleList
 * @return HcclResult 
 * @warning  需要考虑是否带tag 2、需要确认安全校验等方案
 */
extern HcclResult HcclAllocNotify(HcclComm comm, CommEngine commEngine,
    NotifyType notifyType, uint32_t notifyNum, NotifyHandle **notifyHandleList);

/**
 * @brief 获取线程通知数量
 * @param[in] comm 通信域句柄
 * @param[in] thread 线程句柄
 * @param[in] engine 通信引擎类型
 * @param[out] notifyNum 通知数量
 * @return HcclResult 执行结果状态码
 * @note 1.基于thread获取notify数量\n 2.后续数据面用notify idx操作
 */
extern HcclResult HcclGetNotifyNumInThread(HcclComm comm, ThreadHandle thread, CommEngine engine, uint32_t *notifyNum);
// extern HcclResult HcclThreadGetNotifyNum(HcclComm comm, CommEngine engine, ThreadHandle thread, uint32_t *notifyNum);

/** @} */  // 运行时接口-类型定义
/**
 * @defgroup 通信域管理接口（已对外开放）
 * @{
 */

/** @} */  // 通信域管理接口（已对外开放）
/**
 * @defgroup 通信内存接口
 * @{
 */

//  * @param[in] opTag 算子标签（建议包含算子名和标识，最大字符长度为HCCL_RES_TAG_MAX_LEN）。\n
//  *                  opTag为'\0'，表示注册的内存只绑定通信域，不绑定算子。
/**
 * @name 通信内存注册
 * @{
 */
/**
 * @brief 向通信域注册内存
 * @param[in] comm 通信域句柄
 * @param[in] memTag 内存字符串标识，以"\0"结尾，最大字符长度为HCCL_RES_TAG_MAX_LEN
 * @param[in] mem 内存信息
 * @param[in] regAttr 内存注册属性
 * @param[out] memHandle 注册内存句柄
 * @return HcclResult 执行结果状态码
 * @note 通信域内以memTag作为key存储该内存，并注册内存。 \n该接口既支持算子内，也支持算子外注册内存。
 * @warning
 */
extern HcclResult HcclCommRegMem(HcclComm comm, const char *memTag, const HcclMem *mem,
    HcclRegMemAttr regAttr, void **memHandle);

/**
 * @brief 从通信域解注册内存
 * @param[in] comm 通信域句柄
 * @param[in] memTag 内存字符串标识，以"\0"结尾，最大字符长度为HCCL_RES_TAG_MAX_LEN
 * @param[in] memHandle 注册内存句柄
 * @return HcclResult 执行结果状态码
 * @warning
 */
extern HcclResult HcclUnregMem(HcclComm comm, const char *memTag, const void* memHandle);

/** @} */  // 编程接口-类型定义

/** @} */  // 追加通信注册内存的交换
/**
 * @defgroup 通信引擎资源管理接口
 * @{
 */

/**
 * @brief 获取通信线程资源
 *
 * @param[in] comm 通信域句柄
 * @param[in] notifyNum 通知数量
 * @param[in] notifyHandleList 需要释放的通知句柄列表
 * @return HcclResult 执行结果状态码
 * @warning
 */
extern HcclResult HcommFreeNotify(HcclComm comm, uint32_t notifyNum, NotifyHandle *notifyHandleList);

/** @} */  // 通信引擎资源管理接口

/**
 * @brief 销毁通信通道
 * @param[in] comm 通信域句柄
 * @param[in] channel 通道句柄数组
 * @param[in] channelNum 通道句柄数量
 * @return HcclResult 执行结果状态码
 */
extern HcclResult CommChannelDestroy(HcclComm comm, ChannelHandle channel, uint32_t channelNum);

/** @} */  // 通信通道管理接口
/** @} */  // 控制面编程接口

/**
 * @defgroup 非对外关键接口
 * @{
 */

 /**
 * @defgroup 通信引擎上下文管理接口（编程控制面可选接口）
 * @{
 */

/**
 * @brief 销毁算子资源上下文
 * @param[in] comm 通信域句柄
 * @param[in] engineCtx 通信引擎上下文\n
 *                      -size: ctx内存大小；\n
 *                      -addr: ctx内存地址；\n
 *                      -type: ctx内存类型，分host和device。
 * @return HcclResult 执行结果状态码
 * @warning 考虑统一成通信引擎资源上下文
 */
extern HcclResult HcommEngineCtxDestroy(HcclComm comm, const HcclMem *engineCtx);

/** @} */  // 通信引擎上下文管理接口（编程控制面可选接口）
 /**
 * @defgroup 其他数据面接口
 * @{
 */

/**
 * @name 本地计数通知（主要应用在AIV）
 * @{
 */

/**
 * @brief 本地记录通知+1
 * @param[in] thread 线程句柄
 * @param[in] dstThread 目标线程句柄
 * @param[in] dstNotifyIdx 目标通知索引
 * @return HcclResult 执行结果状态码
 * @note 配合CommLocalCntNotifyWait使用；当前主要应用于AIV；通知一次，自动加1。
 * @warning
 */
extern HcclResult CommLocalCntNotifyRecord(ThreadHandle thread, ThreadHandle dstThread, uint32_t dstNotifyIdx);

/**
 * @brief 本地等待通知指定值
 * @param[in] thread 线程句柄
 * @param[in] notifyIdx 通知索引
 * @param[in] waitValue 等待值
 * @param[in] timeout 超时时间(毫秒)
 * @return HcclResult 执行结果状态码
 * @note 配合CommLocalCntNotifyRecord使用；当前主要应用于AIV
 * @warning
 */
extern HcclResult CommLocalCntNotifyWait(ThreadHandle thread, uint32_t notifyIdx, uint64_t waitValue, uint32_t timeout);

/** @} */  // 本地计数通知（主要应用在AIV）
/**
 * @name 计数通知（主要应用在AIV）
 * @{
 */

/**
 * @brief 记录通知事件+1
 * @param[in] thread 线程句柄
 * @param[in] channel 通道句柄
 * @param[in] remoteNotifyIdx 远端通知索引
 * @return HcclResult 执行结果状态码
 * @warning
 */
extern HcclResult CommCntNotifyRecord(ThreadHandle thread, ChannelHandle channel, uint32_t remoteNotifyIdx);

/**
 * @brief 等待通知值
 * @param[in] thread 线程句柄
 * @param[in] channel 通道句柄
 * @param[in] localNotifyIdx 本地通知索引
 * @param[in] waitValue 等待值
 * @param[in] timeout 超时时间(毫秒)
 * @return HcclResult 执行结果状态码
 */
extern HcclResult CommCntNotifyWait(ThreadHandle thread, ChannelHandle channel, uint32_t localNotifyIdx,
    uint64_t waitValue, uint32_t timeout);

/** @} */  // 通知（主要应用在AIV）
/**
 * @name 本地fork-join
 * @{
 */

/**
 * @brief 采用多个thread执行job
 *
 * @tparam job 待完成的工作
 * @tparam commEngine 通信引擎
 * @param[in] thread 执行线程
 * @param[in] threadNum 需要执行的线程数量
 * @return HcclResult 执行结果状态码
 * @warning
 */
HcclResult CommThreadFork(ThreadHandle thread, uint32_t threadNum, ...);

/**
 * @brief 阻塞等待所有job完成
 *
 * @tparam commEngine 通信引擎
 * @param[in] thread 执行线程
 * @return HcclResult 执行结果状态码
 */
HcclResult CommThreadJoin(ThreadHandle thread);

/** @} */  // 本地fork-join
/** @} */  // 其他数据面接口
/**
 * @defgroup 通信通道操作接口（双边语义）
 * @{
 */

/**
 * @brief 发送数据(双边通信)
 * @param[in] thread 线程句柄
 * @param[in] channel 通道句柄
 * @param[in] src 源内存地址
 * @param[in] len 数据长度(字节)
 * @param[out] sentLen 发送的数据长度(字节)
 * @return HcclResult 执行结果状态码
 */
extern HcclResult CommChannelSend(ThreadHandle thread, ChannelHandle channel, const void *src, uint64_t len, uint64_t *sentLen);

/**
 * @brief 接收数据(双边通信)
 * @param[in] thread 线程句柄
 * @param[in] channel 通道句柄
 * @param[out] dst 目标内存地址
 * @param[in] len 数据长度(字节)
 * @param[out] recvLen 接收的数据长度(字节)
 * @return HcclResult 执行结果状态码
 */
extern HcclResult CommChannelRecv(ThreadHandle thread, ChannelHandle channel, void *dst, uint64_t len, uint64_t *recvLen);

/** @} */  // 通信通道操作接口（双边语义）
/**
 * @defgroup 全局rankGraph接口（通信域内部接口）
 * @{
 */

/**
 * @brief HCCL的RankGraph句柄
 */
typedef void *HcclRankGraph;

/**
 * @brief 给定rankTable和topo文件，初始化rankGraph
 * @param[in] rankTable rank表文件
 * @param[in] topoFile 拓扑文件
 * @param[out] graph rank图句柄
 * @return HcclResult 执行结果状态码
 * @warning
 */
extern HcclResult HcclRankGraphInit(const char *rankTable, const char *topoFile, HcclRankGraph* graph);

/**
 * @brief 去初始化RankGraph
 * @param[in] graph rank图句柄
 * @return HcclResult 执行结果状态码
 */
extern HcclResult HcclRankGraphDeInit(HcclRankGraph graph);

/**
 * @brief 查询本rank包含的通信层次
 * @param[in] graph rank图句柄
 * @param[out] levels 通信层次
 * @return HcclResult 执行结果状态码
 */
extern HcclResult HcclRankGraphGetLevels(HcclRankGraph graph, uint32_t *levels);

/**
 * @brief 给定level，返回该通信层次包含的rank数量
 * @param[in] graph rank图句柄
 * @param[in] level 通信层次
 * @param[out] rankSize 通信rank列表大小
 * @return HcclResult 执行结果状态码
 */
extern HcclResult HcclRankGraphGetRankSize(HcclRankGraph graph, uint32_t level, uint32_t *rankSize);

/**
 * @brief 给定level，返回topo类型
 * @param[in] graph rank图句柄
 * @param[in] level 通信层次
 * @param[out] topoType topo类型
 * @return HcclResult 执行结果状态码
 */
extern HcclResult HcclRankGraphGetTopoType(HcclRankGraph graph, uint32_t level, uint32_t *topoType);

/**
 * @brief 给定level，返回该通信层次包含的rank列表
 * @param[in] graph rank图句柄
 * @param[in] level 通信层次
 * @param[out] rankList 通信rank列表
 * @param[out] rankSize 通信rank列表大小
 * @return HcclResult 执行结果状态码
 * @warning
 */
extern HcclResult HcclRankGraphGetRankList(HcclRankGraph graph, uint32_t level, uint32_t **rankList, uint32_t *rankSize);

/**
 * @brief 给定算法类型和level，返回该通信层次包含的rank列表
 * @param[in] graph rank图句柄
 * @param[in] algType 算法类型
 * @param[in] level 通信层次
 * @param[out] rankList 通信rank列表
 * @param[out] rankSize 通信rank列表大小
 * @return HcclResult 执行结果状态码
 * @warning
 */
extern HcclResult HcclRankGraphGetRankListByAlg(HcclRankGraph graph, uint32_t level, char *algType, uint32_t **rankList,
    uint32_t *rankSize);
/** @} */  // 全局rankGraph接口（通信域内部接口）

#ifdef __cplusplus
}
#endif  // __cplusplus

#endif  // HCCL_API_H

#ifdef NEW_API
#ifdef __cplusplus
extern "C" {
#endif  // __cplusplus
/**
 * @defgroup 对用户开放API
 * @{
 */

/**
 * @defgroup 集合通信
 * @{
 */

 /**
 * @defgroup 集合通信-类型定义
 * @{
 */

/**
 * @enum HcclMemType
 * @brief 内存类型枚举定义
 */
typedef enum {
    HCCL_MEM_TYPE_DEVICE, ///< 设备侧内存（如NPU等）
    HCCL_MEM_TYPE_HOST,   ///< 主机侧内存
    HCCL_MEM_TYPE_NUM     ///< 内存类型数量
} HcclMemType;

/**
 * @brief 内存段元数据描述结构体
 */
typedef struct {
    HcclMemType type; ///< 内存物理位置类型，参见HcclMemType
    void *addr;       ///< 内存地址
    uint64_t size;    ///< 内存区域字节数
} HcclMem;

/// 根节点信息长度
const uint32_t HCCL_ROOT_INFO_BYTES = 4108;

/**
 * @brief 根节点信息
 * @note 根节点信息包含网络地址、标识等信息，对外透明。
 */
typedef struct {
    char internal[HCCL_ROOT_INFO_BYTES];
} HcclRootInfo;

/**
 * @brief 通信域初始化配置
 * @warning  1、新增threadNum和notifyNumPerThread，面向AIV场景预计需要增加cntNotify\n
 * 2、这里的threadNum可能被误解成为运行的线程。3、hcclOpExpansionMode需要修改. 4、cntNotifyNumPerThread改为notifyType？
 * uint32_t cntNotifyNumPerThread; ///< 每个thread的count notify数量（新增）
 */
typedef struct {
    char reserved[HCCL_COMM_CONFIG_INFO_BYTES];
    uint32_t hcclBufferSize;    ///< ccl buf大小
    uint32_t hcclDeterministic;
    char hcclCommName[COMM_NAME_MAX_LENGTH];
    char hcclUdi[UDI_MAX_LENGTH];
    uint32_t hcclOpExpansionMode;   ///< 0:默认值  1:host  2:aicpu  3:aiv
    uint32_t hcclRdmaTrafficClass;
    uint32_t hcclRdmaServiceLevel;
    uint32_t hcclWorldRankID;
    uint64_t hcclJobID;
    int32_t commEngine;             ///< 通信引擎（0: HOST CPU；1: HOST CPU TS；...)（参考CommEngine，从hcclOpExpansionMode变更）
    uint32_t threadNum;             ///< thread数量（新增）
    uint32_t notifyNumPerThread;    ///< 每个thread的notify数量（新增）
} HcclCommConfig;

/** @} */  // 集合通信-类型定义

/**
 * @defgroup 通信域管理（已对外开放）
 * @{
 */
/**
 * @brief Initialize HCCL with config params.
 *
 * @param clusterInfo A string identifying the cluster info file path, include file name.
 * @param rank A integer identifying the identify for the rank.
 * @param config A pointer identifying config params about the current comm.
 * @param comm A pointer identifying the initialized communication resource.
 * @return HcclResult
 * @see HcclCommDestroy()
 */
extern HcclResult HcclCommInitClusterInfoConfig(const char *clusterInfo, uint32_t rank,
    HcclCommConfig *config, HcclComm *comm);

/**
 * @brief Initialize HCCL sub communication based on global communication with config params.
 *
 * @param comm A pointer identifying the global communication resource.
 * @param rankNum A integer identifying the rank size of the sub communication.
 * @param rankIds An array identifying the identifies for the ranks in the sub communication.
 * @param subCommId A integer identifying the identify of sub communication in global communication.
 * @param subCommRankId A array identifying the identify for the rank in the sub communication.
 * @param config A pointer identifying config params about the current comm.
 * @param comm A pointer identifying the initialized communication resource.
 * @return HcclResult
 * @see HcclCommDestroy()
 */
extern HcclResult HcclCreateSubCommConfig(HcclComm *comm, uint32_t rankNum, uint32_t *rankIds,
    uint64_t subCommId, uint32_t subCommRankId, HcclCommConfig *config, HcclComm *subComm);

/**
 * @brief 销毁通信域
 * @param[in] comm 通信域句柄
 * @return HcclResult 执行结果状态码
 */
extern HcclResult HcclCommDestroy(HcclComm comm);


/**
 * @brief 初始化通信域（含Thread/本地notify（通信域+thread粒度）/CCL buf等资源配置）
 * @param[in] nRanks 通信域中的rank总数
 * @param[in] rootInfo 根节点信息
 * @param[in] rank 当前进程的rank ID
 * @param[in] config 通信域配置参数
 * @param[out] comm 创建的通信域句柄
 * @return HcclResult 执行结果状态码
 * @note 创建通信域时按需填入需要的thread数量、每个thread的notify数量、需要的CCL Buffer大小。资源申请建议采用lazy方式。\n
 * 对外接口：https://www.hiascend.com/document/detail/zh/CANNCommunityEdition/82RC1/API/hcclapiref/hcclcpp_07_0001.html
 */
extern HcclResult HcclCommInitRootInfoConfig(
    uint32_t nRanks, const HcclRootInfo *rootInfo, uint32_t rank, const HcclCommConfig *config, HcclComm *comm);


/** @} */  // 通信域管理（已对外开放）

/**
 * @defgroup 集合通信算子（已对外开放）
 * @{
 */

/** @} */  // 集合通信算子（已对外开放）



/**
 * @defgroup 集合通信算子控制面编程
 * @{
 */

/**
 * @defgroup 算子编程-类型定义
 * @{
 */

// \cond
/**
 * @brief 通信的rank图
 */
// typedef struct {
// } CommRankGraph;
// \endcond

/**
 * @brief 通信拓扑枚举
 */
typedef enum {
    COMM_TOPO_RESERVED = -1,  ///< 保留拓扑
    COMM_TOPO_1DMESH = 1,     ///< 1DMesh互联拓扑
    COMM_TOPO_CLOS = 2,       ///< CLOS互联拓扑
    COMM_TOPO_910_93 = 3,     ///< 910_93互联拓扑(带SIO)
    COMM_TOPO_310P = 4,       ///< 310P互联拓扑
} CommTopo;

/**
 * @brief 通信协议类型枚举
 * @warning
 */
typedef enum {
    COMM_PROTOCOL_RESERVED = -1,  ///< 保留协议类型
    COMM_PROTOCOL_HCCS = 0,        ///< HCCS协议
    COMM_PROTOCOL_TCP = 1,        ///< 标准TCP协议
    COMM_PROTOCOL_ROCE = 2,       ///< RDMA over Converged Ethernet
    COMM_PROTOCOL_UB_CTP = 3,    ///< 华为统一总线UB_CTP
    COMM_PROTOCOL_UB_TP = 4,     ///< 华为统一总线UB_TP
    COMM_PROTOCOL_PCIE = 5,      ///< PCIE协议
    COMM_PROTOCOL_SIO = 6,        ///< SIO协议
} CommProtocol;

// CommProtocol protocol;  ///< 通信协议
// CommAddr localCommAddr;   ///< 本端通信地址，从rank graph中查询
// CommAddr remoteCommAddr;  ///< 远端通信地址，从rank graph中查询
// char *bandWidth;          ///< 带宽

/**
 * @brief EndPoint位置类型枚举
 * @warning  优化
 */
typedef enum {
    END_POINT_LOCATION_RESERVED = -1,  ///< 保留的EndPoint位置
    END_POINT_LOCATION_HOST = 0,  ///< EndPoint在Host上
    END_POINT_LOCATION_DEVICE = 1,  ///< EndPoint在Device上
} EndPointLocation;

/**
 * @brief EndPoint位置类型结构体
 * @warning  devId是否用int32_t
 */
typedef struct {
    int64_t devId;  ///< device标识
    EndPointLocation location; ///< EndPoint的位置
} EndPointLoc;
/**
 * @brief 通信连接通道的端侧
 * @warning  1、删除了uint32_t rankId;rank标识  的内容后，需要在Channel创建里加；2、优化Location
 */
typedef struct {
    CommProtocol protocol;  ///< 通信协议
    CommAddr commAddr;      ///< 通信地址
    // EndPointLoc loc; ///< EndPoint的位置信息
} EndPoint;

/**
 * @brief 通道描述参数
 * @warning  创建channel的参数需要分析； HccsAttr的定义需要分析（HCCS & UB MEM），或者改名？
 * 可能还要增加CntNotify，其他协议对应的Attr？
 */
typedef struct {
    EndPoint localEndPoint;  ///< 本地端侧描述
    EndPoint remoteEndPoint; ///< 远端端侧描述
    uint32_t notifyNum;  ///< channel上使用的通知消息数量
    union {
        HccsAttr hccsAttr;
        RoCEAttr roceAttr;
        UbAttr ubAttr;
    };
} ChannelDesc;

/**
 * @brief 通道句柄类型（不透明结构）
 * @warning  是否要将ChannelHandle和ThreadHandle改名为xxxId，可以是地址或Id。
 * typedef uint64_t ChannelHandle;
 */

/**
 * @brief 通信引擎类型枚举
 */
typedef enum {
    COMM_ENGINE_RESERVED = -1,    ///< 保留的通信引擎
    COMM_ENGINE_CPU = 0,      ///< HOST CPU引擎
    COMM_ENGINE_CPU_TS = 1,   ///< HOST CPU TS引擎
    COMM_ENGINE_AICPU = 2,        ///< AICPU引擎
    COMM_ENGINE_AICPU_TS = 3,     ///< AICPU TS引擎
    COMM_ENGINE_AIV = 4,          ///< AIV引擎
    COMM_ENGINE_CCU = 5,          ///< CCU引擎
} CommEngine;

/// 通信标识最大长度（字节）
const uint32_t COMM_TAG_LEN_MAX = 255;

/**
 * @brief 线程句柄类型（不透明结构）
 * typedef uint64_t ThreadHandle;
 */


 /**
 * @brief 910A3的RankGraph定义
 * @warning  完善内容
 */
typedef struct {
} RankGraph910A3;

 /**
 * @brief RankGraph类别
 * @warning  考虑A2等变更为version等
 */
typedef enum {
    RANK_GRAPH_TYPE_RESERVED = -1, ///< 保留的rank图类型
    RANK_GRAPH_TYPE_910A2 = 0,     ///< 910A2的rank图类型
    RANK_GRAPH_TYPE_910A3 = 1,     ///< 910A3的rank图类型
} RankGraphType;

/**
 * @brief 通信的rank图类型
 */
typedef enum {
    RANK_GRAPH_RESERVED = -1,   ///< 保留的rank图类型
    RANK_GRAPH_910_93 = 0,      ///< 910_93 rank图类型
} GraphType;

/**
 * #define __aicore__ 
 * #define __ubuf__
 * #define __gm__
*/

/** @} */  // 算子编程-类型定义

/**
 * @defgroup RankGraph查询
 * @{
 */

/**
 * @brief 获取通信域中自己的rankId（非world rank）（已对外开放，运行时和编程共用API）
 * @param[in] comm 通信域句柄
 * @param[out] rank 自己的rankId
 * @return HcclResult 执行结果状态码
 * @note 给定通信域，查询自己的rank号（本通信域内）
 * @warning extern HcclResult HcclGetMyRank(HcclComm comm, uint32_t *rankId)
 */



// \cond
/**
 * @brief 给定通信域和level，返回该通信层次包含的rank列表
 * @param[in] comm 通信域
 * @param[in] level 层级
 * @param[out] rankList rank列表
 * @param[out] rankSize rank列表大小
 * @return HcclResult 执行结果状态码
 * @note 以2个Pod组网为例，R0为64，R1的范围为128。\n
 *      GetRankList(level=0, rankList, rankSize)得到：rankSize=64, rankList=[0,1,2,…63]。\n
 *      GetRankList(level=1, rankList, rankSize)得到：rankSize=128, rankList=[0,1,2,…127]。
 */
extern HcclResult HcclGetRankList(HcclComm comm, uint32_t level, uint32_t **rankList, uint32_t *rankSize);

/**
 * @brief 给定通信域和level，返回topo类型
 * @param[in] comm 通信域
 * @param[in] level 层级
 * @param[out] topoType topo类型，包括clos/1DMesh/2DMesh等
 * @return HcclResult 执行结果状态码
 * @note 以本rank视角，返回该rank所在层次的topo类型
 * @warning  1、需要将topoType转换成枚举，字符串等？。 2、该接口非必须对外
 */
extern HcclResult HcclGetTopoType(HcclComm comm, uint32_t level, uint32_t *topoType);
// \endcond

// \cond
/**
 * @brief 给定通信域、level及算法类型，返回该通信层次包含的rank列表
 * @param[in] comm 通信域
 * @param[in] level 层级
 * @param[in] algType 算法类型
 * @param[out] rankList 通信域的rank列表
 * @param[out] rankSize 通信域的rank数量
 * @return HcclResult 执行结果状态码
 * @warning  1、需要将topoType转换成枚举。 2、该接口非必须对外
 * @warning  该接口可以先不提供
 */
// extern HcclResult HcclGetRankListByAlg(HcclComm comm, uint32_t level, char *algType,
//     uint32_t **rankList, uint32_t *rankSize);
// \endcond

// \cond
/**
 * @brief 查询通信域中给定level的rankSize
 * @param[in] comm 通信域
 * @param[in] level 层级
 * @param[out] rankSize 该通信域包含的rank数量
 * @return HcclResult 执行结果状态码
 * @warning  该接口和HcclGetRankSize基本一样，需要确认
 */
extern HcclResult HcclGetLevelSize(HcclComm comm, uint32_t level, uint32_t *rankSize);

// \endcond
/** @} */  // RankGraph查询

/**
 * @defgroup 通信内存管理
 * @{
 */

//  * @param[in] opTag 算子标签（建议包含算子名和标识，最大字符长度为COMM_TAG_LEN_MAX）。\n
//  *                  opTag为'\0'，表示注册的内存只绑定通信域，不绑定算子。
/**
 * @name 通信内存注册
 * @{
 */
/**
 * @brief 向通信域注册内存
 * @param[in] comm 通信域句柄
 * @param[in] memTag 内存字符串标识，以"\0"结尾，最大字符长度为COMM_TAG_LEN_MAX
 * @param[in] mem 内存信息
 * @param[out] memHandle 注册内存句柄
 * @return HcclResult 执行结果状态码
 * @note 通信域内以memTag作为key存储该内存，并注册内存。 \n该接口既支持算子内，也支持算子外注册内存。
 * @warning  3、建议将void*起一个别名\n
 * 4、如果都算到算子外部的接口，需要有opTag获取的接口或规则；或者默认全都注册到通信域。外部只支持单边交换的方式。 双边交换的方式，不支持每个算子的追加交换。
 */
extern HcclResult HcclRegMem(HcclComm comm, const char *memTag, const HcclMem *mem, void **memHandle);

/**
 * @brief 从通信域解注册内存
 * @param[in] comm 通信域句柄
 * @param[in] memTag 内存字符串标识，以"\0"结尾，最大字符长度为COMM_TAG_LEN_MAX
 * @param[in] memHandle 注册内存句柄
 * @return HcclResult 执行结果状态码
 * @warning  1、memTag可能不用，只要memHandle即可？2、名称都换成Comm开头的？
 */
extern HcclResult HcclUnregMem(HcclComm comm, const char *memTag, const void* memHandle);

/** @} */  // 通信内存注册

/** @} */  // 通信内存获取

/**
 * @name 通信内存交换
 * @{
 */
// \cond
/**
 * @brief 交换注册后的通信内存
 * @param[in] comm 通信域句柄
 * @param[in] channel 通信通道句柄
 * @param[in] memHandleList 已注册内存的句柄列表 
 * @param[in] listNum 列表数量 
 * @param[out] remoteMem 远端内存
 * @param[out] memTag 远端内存字符标识指针数组，每个成员以"\0"结尾（外部不能释放该内存）
 * @param[out] memNum 远端内存数量 
 * @param[in] timeout 超时时间（ms） 
 * @return HcclResult 执行结果状态码
 * @warning  1、是否要改为基于RankId的？          1、是不是就用channel最好？ 2、所有函数的const检查  4、参数超长\n
 * 5、需要针对运行时接口，增加基于RankId地址信息交换，以及获取对端内存信息的接口，如果需要交换的话！——2025年8月22日
 */
// extern HcclResult HcclChannelExchangeMem(HcclComm comm, ChannelHandle channel, const void **memHandleList,
//     uint32_t listNum, HcclMem **remoteMem, char **memTag, uint32_t *memNum, uint32_t timeout);
// \endcond

/**
 * @brief 交换注册内存
 * 
 * @param comm 
 * @param srcEndPoint 
 * @param dstEndPoint 
 * @param memHandleList 
 * @param listNum 
 * @param remoteMem 
 * @param memTag 
 * @param memNum 
 * @param timeout 
 * @return HcclResult 
 */
extern HcclResult HcclExchangeMem(HcclComm comm, const EndPoint *srcEndPoint, const EndPoint *dstEndPoint,
    const void **memHandleList, uint32_t listNum, HcclMem **remoteMem, char **memTag, uint32_t *memNum, uint32_t timeout);

// * @param[in] opTag 算子标签（建议包含算子名和标识，最大字符长度为COMM_TAG_LEN_MAX）
// \cond
/**
 * @brief 基于算子tag创建通信通道
 * @param[in] comm 通信域句柄
 * @param[in] channelTag 通信通道标签（最大字符长度为COMM_TAG_LEN_MAX）
 * @param[in] engine 通信引擎类型
 * @param[in] channelDescList 通道描述列表
 * @param[in] listNum 列表数量
 * @param[out] channelList 创建的通道句柄列表
 * @return HcclResult 执行结果状态码
 * @note 1.描述需建链的信息（如协议、远端EID等），支持批量完成与多个远端的建链\n
 * 2.CreateChannel时将交换内存信息（包含：已绑定到通信域的内存、已注册到算子TAG上的内存）\n
 * 3.注册后，通信域内以remoteRank+opName+customTag作为key存储该channel；如opName和customTag为空，则通信域内已remoteRank为key存储\n
 * 4.资源描述相同时，key相同情况下已有资源，则复用该资源返回，不重新创建；如需重复创建资源，可使用不同的tag\n
 * 5.注册后，通信域内以remoteRank+opName+customTag作为key存储该channel；如opName和customTag为空，则通信域内已remoteRank为key存储\n
 * 6.资源描述相同时，key相同情况下已有资源，则复用该资源返回，不重新创建（ps：host展开场景下 ，jetty不能复用）
 * @warning  note中的内容需要审核   1、参数精简；2、是否需要超时时间？另一个channel创建接口页数 3、增加内存等的参数描述 4、一个channelTag下是否可以多个channel？？？
 */
// extern HcclResult HcclChannelCreateWithMemExch(HcclComm comm, const char *channelTag, CommEngine engine,
//     const ChannelDesc *channelDescList, uint32_t listNum, const void **memHandleList, uint32_t memListNum,
//     uint32_t timeout, ChannelHandle *channelList);
// \endcond
/** @} */  // 通信内存交换

/** @} */  // 通信内存管理

/**
 * @defgroup 通信引擎资源管理
 * @{
 */
// -------------------------- ctx接口优化--------------
// \cond
/**
 * @brief 获取通信线程
 * @param[in] comm 通信域句柄
 * @param[in] engine 通信引擎类型
 * @param[in] reqThreadNum 请求的线程数量
 * @param[in] reqNotifyNumPerThread 每线程请求的通知数量
 * @param[out] thread 返回的线程句柄
 * @param[out] threadNum 实际分配的线程数
 * @param[out] notifyNumPerThread 每线程实际通知数
 * @return HcclResult 执行结果状态码
 * @note 1.创建通信域传入初始创建的thread数量\n 2、获取时按需获取，如资源不够则返回当前最大的thread数量
 * @warning  1、notifyNumPerThread没意义吧？满足不了notify数量诉求，返回仅有的。2、如果Thread数量不够，应该要添加申请Thread的接口？\n
 *  3、是不是约束不让申请线程和notify资源了？如果需要，初始化的时候给足
 */
// extern HcclResult HcclGetThread(HcclComm comm, CommEngine engine, uint32_t reqThreadNum,
//     uint32_t reqNotifyNumPerThread, ThreadHandle *thread, uint32_t *threadNum, uint32_t *notifyNumPerThread);
// \endcond



// \cond
/**
 * @brief 基于已有流Stream申请指定notifyNum的通信线程资源
 * @param[in] comm 通信域句柄
 * @param[in] engine 通信引擎类型
 * @param[in] stream stream句柄
 * @param[in] notifyNumPerThread 通知数量
 * @param[out] thread 返回的线程句柄
 * @return HcclResult 执行结果状态码
 */
// extern HcclResult HcclThreadAcquireWithStream(HcclComm comm, CommEngine engine,
//     aclrtStream stream, uint32_t notifyNumPerThread, ThreadHandle *thread);
// \endcond

/**
 * @brief 基于通信域释放Notify
 * 
 * @param hcclComm 
 * @param commEngine 
 * @param notifyType 
 * @param notifyHandleList
 * @return HcclResult 
 * @warning  需要考虑是否带tag? 2、需要确认安全校验等方案 3、CommEngine commEngine,NotifyTypeT notifyType是否要加？
 */
extern HcclResult HcclFreeNotify(HcclComm comm, NotifyHandle *notifyHandleList, uint32_t notifyNum);
/** @} */  // 通信引擎资源管理

/**
 * @defgroup 通信通道管理
 * @{
 */
//  * @param[in] opTag 算子标签（建议包含算子名和标识，最大字符长度为COMM_TAG_LEN_MAX）
/**
 * @brief 基于算子tag创建通信通道
 * @param[in] comm 通信域句柄
 * @param[in] channelTag 通信通道标签（最大字符长度为COMM_TAG_LEN_MAX）
 * @param[in] engine 通信引擎类型
 * @param[in] channelDescList 通道描述列表
 * @param[in] listNum 列表数量
 * @param[in] memHandleList 内存句柄列表
 * @param[in] memHandleListNum 内存句柄列表数量
 * @param[out] channelList 创建的通道句柄列表
 * @return HcclResult 执行结果状态码
 * @note 非阻塞接口\n
 * 1.描述需建链的信息（如协议、远端EID等），支持批量完成与多个远端的建链\n
 * 2.CreateChannel时将交换内存信息（包含：已绑定到通信域的内存、已注册到算子TAG上的内存）\n
 * 3.注册后，通信域内以remoteRank+opName+customTag作为key存储该channel；如opName和customTag为空，则通信域内已remoteRank为key存储\n
 * 4.资源描述相同时，key相同情况下已有资源，则复用该资源返回，不重新创建；如需重复创建资源，可使用不同的tag\n
 * 5.注册后，通信域内以remoteRank+opName+customTag作为key存储该channel；如opName和customTag为空，则通信域内已remoteRank为key存储\n
 * 6.资源描述相同时，key相同情况下已有资源，则复用该资源返回，不重新创建（ps：host展开场景下 ，jetty不能复用）
 * @warning  note中的内容需要审核；  2.控制面是否可以都暂时不提供批量的接口，需要批量接口单独增加，或者提供通用的批量接口？需要表明不会随路交换内存！2025年8月22日4、是不是默认所有的批量channel都注册一样的内存？
 */
extern HcclResult HcclChannelCreate(HcclComm comm, const char *channelTag,
    CommEngine engine, const ChannelDesc *channelDescList, uint32_t listNum, const void **memHandleList,
    uint32_t memHandleListNum, ChannelHandle *channelList);

/**
 * @brief 获取channel中全部的交换获得的远端内存信息
 * 
 * @param comm
 * @param channel 
 * @param remoteMem 
 * @param memTag 
 * @param memNum 
 * @return HcclResult 
 * @warning  1、补充参数介绍 2、这个基于Channel的接口暂时不对外提供！！！
 */
extern HcclResult HcclChannelGetRemoteMem(HcclComm comm, ChannelHandle channel, HcclMem **remoteMem,
    char **memTag, uint32_t *memNum);

/**
 * @brief 销毁通信通道
 * @param[in] comm 通信域句柄
 * @param[in] channelList 通道句柄数组
 * @param[in] listNum 列表数量
 * @return HcclResult 执行结果状态码
 */
extern HcclResult HcclChannelDestroy(HcclComm comm, const ChannelHandle *channelList, uint32_t listNum);

/** @} */  // 通信通道管理

/** @} */  // 集合通信算子控制面编程

/** @} */  // 集合通信

/**
 * @defgroup Client-Server通信
 * @{
 */

/**
 * @defgroup CS通信域管理
 * @{
 */
/**
 * @name Server侧
 * @{
 */

//  待确认是否一定需要
typedef struct {
} ServerConfig;

// \cond
/**
 * @brief 注册内存
 * 
 * @param hcommCSHandle 
 * @param memTag 
 * @param mem 
 * @param regAttr 
 * @param memHandle 
 * @return HcclResult 
 * @warning  集合通信的内存注册不用加regAttr了
 */
// extern HcclResult HixlCSRegMem(const void *hcommCSHandle, const char *memTag, const HcclMem *mem,
//     HcclRegMemAttr regAttr, void **memHandle);
// \endcond


// \cond
/**
 * @brief 
 * 
 * @param commClientHandle 
 * @param dstEndPoint 
 * @param port 
 * @return HcclResult 
 */
extern HcclResult HixlClientConnectToServer(void *commClientHandle, EndPoint *dstEndPoint, uint32_t port);
// \endcond

/** @} */  // Server侧

/**
 * @name Client侧
 * @{
 */
 
typedef struct {
    EndPoint srcEndPoint;
    EndPoint dstEndPoint;
    CommProtocol protocol;
} CSChannelDesc;
/**
 * @brief 创建Client
 * 
 * @param ctlEndPoint 
 * @param[in] port 端口号，不指定传入0
 * @param dstEndPoint 
 * @param dstPort 
 * @param clientHandle 
 * @return HcclResult 
 */
// extern HcclResult HixlCSClientCreate(const EndPoint *ctlEndPoint, uint32_t port,
//     EndPoint *dstCtlEndPoint, uint32_t dstPort, void **clientHandle);
// const EndPoint *ctlEndPoint, uint32_t port,
extern HcclResult HixlCSClientCreate(char *serverIp, uint32_t serverPort, const EndPoint *srcEndPoint,
    const EndPoint *dstEndPoint, void **clientHandle);

/**
 * @brief Client连接到Server
 * 
 * @return HcclResult 
 */
// const CSChannelDesc *channeDesc
 
extern HcclResult HixlCSClientConnect(void *clientHandle);

/**
 * @brief 查询CS连接状态（主要为Client）
 * 
 * @param hcommCSHandle 
 * @param status 
 * @return HcclResult 
 */
extern HcclResult HixlCSClientGetStatus(void *clientHandle, int32_t *status);

/**
 * @brief 
 * 
 * @param clientHandle 
 * @param remoteMemList 
 * @param memTagList 
 * @param listNum 
 * @param timeout 
 * @return HcclResult 
 * @warning  改成非阻塞接口？
 */
extern HcclResult HixlCSClientGetRemoteMem(void *clientHandle, HcclMem **remoteMemList,
    char **memTagList, uint32_t *listNum, uint32_t timeout);

/**
 * @brief 注册内存
 * 
 * @param serverHandle
 * @param memTag 
 * @param mem 
 * @param memHandle 
 * @return HcclResult 
 * @warning  1、可以优化成批量接口 2、HcclMem建议修改为其他的类型
 */
extern HcclResult HixlCSClientRegMem(const void *clientHandle, const char *memTag, const HcclMem *mem,
    void **memHandle);

/**
 * @brief 解注册内存
 * 
 * @param endPoint 
 * @param memHandle 
 * @return HcclResult 
 */
extern HcclResult HixlCSClientUnRegMem(const void *clientHandle, void *memHandle);

/**
 * @brief 
 * 
 * @param hcommCSHandle 
 * @return HcclResult 
 */
extern HcclResult HixlCSClientDestroy(void *clientHandle);

// \cond
/**
 * @brief 建链
 * 
 * @param clientHandle 
 * @param dstCtlEndPoint 
 * @param dstPort 
 * @return HcclResult 
 */
extern HcclResult HixlCSConnectToServer(void *clientHandle, EndPoint *dstCtlEndPoint, uint32_t dstPort);
// \endcond

/** @} */  // Client侧

/** @} */  // CS通信域管理

/**
 * @defgroup 单边通信算子（待最终确定）
 * @{
 */

 
/**
 * @brief 批量放
 * 
 * @param clientHandle 
 * @param remoteBufList 
 * @param localBufList 
 * @param lenList 
 * @param listnum 
 * @return HcclResult 
 */
extern HcclResult HixlCSClientBatchPut(void *clientHandle, uint32_t listnum, void **remoteBufList, const void **localBufList,
    uint64_t *lenList, void **completeHandle);

/**
 * @brief 批量获取
 * 
 * @param clientHandle 
 * @param localBufList 
 * @param remoteBufList 
 * @param lenList 
 * @param listnum 
 * @return HcclResult 
 */
extern HcclResult HixlCSClientBatchGet(void *clientHandle, uint32_t listnum, void **localBufList, const void **remoteBufList, 
    uint64_t *lenList, void **completeHandle);

/**
 * @brief 查询完成状态
 * 
 * @param completeHandle 
 * @return HcclResult 
 */
extern HcclResult HixlCSClientQueryCompleteStatus(void *clientHandle, void *completeHandle, int32_t *status);

/** @} */  // 单边通信算子（待最终确定）


// \cond
/**
 * @defgroup 单边通信算子控制面编程
 * @{
 */
/** @} */  // 单边通信算子控制面编程


/**
 * @defgroup Client-Server控制面
 * @{
 */


/**
 * @defgroup Client-Server编程接口
 * @{
 */

// \cond
/**
 * @name Client侧——Link信息查询
 * @{
 */
/**
 * @brief 获取Client侧的本地端点列表
 */
// extern HcclResult HixlCSClientGetLocalEndPoints(void *clientHandle, EndPoint **localEndPointList,
//     uint32_t *listSize);

/**
 * @brief 获取Client侧的远端端点列表
 * 
 * @param clientHandle 
 * @param remoteEndPointList 
 * @param listSize 
 * @return HcclResult 
 */
// extern HcclResult HixlCSClientGetRemoteEndPoints(void *clientHandle, EndPoint **remoteEndPointList,
//     uint32_t *listSize);

/**
 * @brief 获取Client侧的连接列表
 * 
 * @param clientHandle 
 * @param linkList 
 * @param listSize 
 * @return HcclResult 
 */
extern HcclResult HixlCSClientGetLinks(void *clientHandle, CommLink **linkList, uint32_t *listSize);
/** @} */  // Client侧——Link信息查询
// \endcond
/**
 * @name Client侧——通信通道管理
 * @{
 */
// \cond
/**
 * @brief 基于Client创建通信通道
 * 
 * @param clientHandle 
 * @param channelTag
 * @param engine
 * @param channeDescList 
 * @param listNum
 * @param channelHandleList 
 * @return HcclResult 
 * @warning  考虑要加上tag  2、要求目标EndPoint必须要在Server中 3、不需要把内存交换过来吧？
 */
// extern HcclResult HixlCSClientCreateChannel(void *clientHandle, const char *channelTag, CommEngine engine,
//     const CSChannelDesc *channeDescList, uint32_t listNum, ChannelHandle **channelHandleList);

/**
 * @brief 查询通信通道的状态
 * @param[in] comm 通信域句柄 
 * @param[in] channelList 通道句柄列表
 * @param[in] listNum 列表数量
 * @param[out] statusList 返回状态列表，0表示成功
 * @return HcclResult 执行结果状态码
 * @note 非阻塞接口
 * @warning  statusList是否改成枚举？
 */
// extern HcclResult HixlCSClientChannelGetStatus(void *clientHandle, const ChannelHandle *channelList,
//     uint32_t listNum, int32_t *statusList);

/**
 * @brief 查询通信通道的状态
 * @param[in] comm 通信域句柄 
 * @param[in] channelList 通道句柄列表
 * @param[in] listNum 列表数量
 * @param[out] statusList 返回状态列表，0表示成功
 * @return HcclResult 执行结果状态码
 * @note 非阻塞接口
 * @warning  statusList是否改成枚举？
 */
extern HcclResult HcclChannelGetStatus(HcclComm comm, const ChannelHandle *channelList, uint32_t listNum,
    int32_t *statusList);

/**
 * @brief 获取channel中全部的交换获得的远端内存信息
 * 
 * @param comm
 * @param channel 
 * @param remoteMem 
 * @param memTag 
 * @param memNum 
 * @return HcclResult 
 * @warning  1、补充参数介绍 2、这个基于Channel的接口暂时不对外提供！！！
 */
// extern HcclResult HixlCSClientChannelGetRemoteMem(void *clientHandle, ChannelHandle channel, HcclMem **remoteMem,
//     char **memTag, uint32_t *memNum);

/**
 * @brief 销毁通信通道
 * @param[in] clientHandle client句柄
 * @param[in] channelList 通道句柄数组
 * @param[in] listNum 列表数量
 * @return HcclResult 执行结果状态码
 */
// extern HcclResult HixlCSClientChannelDestroy(void *clientHandle, const ChannelHandle *channelList,
//     uint32_t listNum);
// \endcond

// \cond
/**
 * @brief 从client句柄获取channel
 * 
 * @param clientHandle 
 * @return HcclResult 
 * @warning  考虑要加上tag？
 */
// extern HcclResult HixlCSClientGetChannel(void *clientHandle, CommEngine engine,
//     ChannelHandle *channelHandle);
// \endcond
/** @} */  // Client侧——通信通道管理
// \cond
/**
 * @name Client侧——通信引擎资源管理
 * @{
 */

/**
 * @brief 获取通信线程资源
 * 
 * @param[in] clientHandle Client句柄
 * @param[in] engine 通信引擎类型
 * @param[in] threadNum 线程数量
 * @param[in] notifyNumPerThread 每线程的通知数量
 * @param[out] thread 返回的线程句柄
 * @return HcclResult 执行结果状态码
 * @warning  thread能否处理成通信域内的threadIdx？ 这样该接口改为获取thread数量。2、Notify是否需要？
 */
// extern HcclResult HixlCSClientAllocThreadRes(void *clientHandle, CommEngine engine, uint32_t threadNum,
//     uint32_t notifyNumPerThread, ThreadHandle *thread);

/** @} */  // Client侧——通信引擎资源管理
// \endcond

/** @} */  // Client侧编程接口
/** @} */  // Client-Server编程接口


// \endcond

/** @} */


/**
 * @defgroup 通信数据面
 * @{
 */

/**
 * @defgroup 通信初始化配置
 * @{
 */

/**
 * @brief Aicore通信初始化
 * @param[in] addr Aicore通信缓存地址
 * @param[in] len 缓存地址长度
 * @param[in] eventId 事件标识
 * @return 无
 * @note 建议在HcommLocalCopyNbi等接口调用前调用,在设置的缓存空间不够时，可再次调用该接口调整缓存大小。
 * 当前只支持AIV，暂不支持AIC，若支持，AIC只支持RoCE和URMA。
 * 910A3上每个AIV最大8个eventId，通信缓存大小192KB。使用参考：
 * @code {.c}
 * uint32_t len = 32 * 1024;
 * __ubuf__ uint8_t *addr = (__ubuf__ uint8_t *)((191 - 32) * 1024);
 * TEventID eventId = 7;
 * HcommInit(addr, len, evtid);
 * HcommLocalCopyNbi(dst, src, len);
 * @endcode
 */
__aicore__ inline void HcommInit(__ubuf__ uint8_t *addr, uint32_t len, TEventID eventId);

/** @} */  // 通信初始化配置

/** @} */  // 本地拷贝和规约

/**
 * @defgroup 本地线程间同步通知
 * @{
 */

/** @} */  // 本地线程间同步通知

/**
 * @defgroup 算子间同步和值通知
 * @{
 * @note 应用于一个通信引擎算子与另一个通信引擎算子或引擎算子外的同步通知
 */

/**
 * @brief 算子间写值
 * 
 * @param thread 
 * @param valuePtr 
 * @param value 
 * @return HcclResult 
 */
extern HcclResult HcommInterOpValueWriteOnThread(ThreadHandle thread, uint32_t *valuePtr, uint32_t value);

/**
 * @brief 算子间等值
 * 
 * @param thread 
 * @param valuePtr 
 * @param expectValue 
 * @return HcclResult 
 */
extern HcclResult HcommInterOpValueWaitOnThread(ThreadHandle thread, uint32_t *valuePtr, uint32_t expectValue);


// \cond
/**
 * @name 本地通知——掩码方式（AIV）
 * @{
 */

/**
 * @brief 本地记录mask
 * 
 */
// __aicore__ inline void HcommLocalNotifyRecordMask(NotifyHandle notifyHandle, uint32_t mask);

/**
 * @brief 本地等待mask
 * 
 */
// __aicore__ inline void HcommLocalNotifyWaitMask(NotifyHandle notifyHandle, uint32_t mask, uint32_t timeout);
/** @} */  // 本地通知——掩码方式（AIV）

/**
 * @name 本地通知——计数方式（AIV）
 * @{
 */
/**
 * @brief 本地加法计数通知
 * 
 * @param[in] thread 线程句柄
 * @param[in] notifyType 通知类别
 * @param[in] notifyHandle 通知标识
 * @return HcclResult 执行结果状态码
 * @warning  怎么区分基于内存的、rtNotify、rtEvent的？需要分别对应新的接口？
 * 或者这个notifyId改为signalId，signalId增加标识区分类别。
 */
// __aicore__ inline void HcommLocalNotifyAddCount(NotifyHandle notifyHandle, uint32_t increment);

/**
 * @brief 本地等待通知数值
 * @return HcclResult 执行结果状态码
 */
// __aicore__ inline void HcommLocalNotifyWaitCount(NotifyHandle notifyHandle, uint32_t expectedValue, uint32_t timeout);
/** @} */  // 本地通知——计数方式（AIV）
// \endcond
/** @} */  // 算子间同步和值通知

/**
 * @defgroup 线程内存屏障
 * @{
 * @note 表示在该内存屏障操作之前的和之后的任务操作保序
 * @warning  确认下是否要调整含义
 */

/**
 * @brief 本地同步操作（thread上阻塞完成）
 * @param[in] thread 线程句柄
 * @return HcclResult 执行结果状态码
 * @note 确保该thread上此前的所有任务都已经执行完成。在AIV、Host 网卡等场景常用
 * @warning  当前主要支持AIV，其他是否支持？
 */
extern HcclResult HcommFenceOnThread(ThreadHandle thread);


/**
 * @brief 本地内存屏障
 * @return 无
 * @note 确保该thread上此前的所有任务都已经执行完成。在AIV、Host 网卡等场景常用
 */
__aicore__ inline void HcommFence();
/** @} */  // 线程内存屏障

/**
 * @defgroup 通信通道上内存读写和规约
 * @{
 */


/**
 * @brief 单边写操作
 * @param[in] thread 线程句柄
 * @param[in] channel 通道句柄
 * @param[out] dst 目标内存地址
 * @param[in] src 源内存地址
 * @param[in] len 数据长度（字节）
 * @return HcclResult 执行结果状态码
 * @warning  因为有commChannelFence带了channel，所有跨卡通信的接口是否都统一加channel？
 */
extern HcclResult HcommWriteNbiOnThread(
    ThreadHandle thread, ChannelHandle channel, void *dst, const void *src, uint64_t len);

/**
 * @brief 单边写操作
 * @param[in] thread 线程句柄
 * @param[in] channel 通道句柄
 * @param[out] dst 目标内存地址
 * @param[in] src 源内存地址
 * @param[in] len 数据长度（字节）
 * @return int32_t 执行结果状态码
 * @warning  因为有commChannelFence带了channel，所有跨卡通信的接口是否都统一加channel？
 */
extern int32_t HcommWriteOnThread(
    ThreadHandle thread, ChannelHandle channel, void *dst, const void *src, uint64_t len);

/**
 * @brief 单边写操作
 * @param[in] channel 通道句柄
 * @param[out] dst 目标内存地址
 * @param[in] src 源内存地址
 * @param[in] len 数据长度（字节）
 * @return 无
 */
__aicore__ inline void HcommWriteNbi(ChannelHandle channel, __gm__ void *dst, __gm__ void *src, uint64_t len);

/**
 * @brief 归约写操作
 * @param[in] thread 线程句柄
 * @param[in] channel 通道句柄
 * @param[out] dst 目标内存地址
 * @param[in] src 源内存地址
 * @param[in] count 元素个数
 * @param[in] dataType 数据类型
 * @param[in] reduceOp 归约操作类型
 * @return HcclResult 执行结果状态码
 */
extern HcclResult HcommWriteReduceNbiOnThread(ThreadHandle thread, ChannelHandle channel, void *dst, const void *src,
    uint64_t count, HcclDataType dataType, HcclReduceOp reduceOp);
    
/**
 * @brief 归约写操作
 * @param[in] thread 线程句柄
 * @param[in] channel 通道句柄
 * @param[out] dst 目标内存地址
 * @param[in] src 源内存地址
 * @param[in] count 元素个数
 * @param[in] dataType 数据类型
 * @param[in] reduceOp 归约操作类型
 * @return int32_t 执行结果状态码
 */
extern int32_t HcommWriteReduceOnThread(ThreadHandle thread, ChannelHandle channel, void *dst, const void *src,
    uint64_t count, HcommDataType dataType, HcommReduceOp reduceOp);

/**
 * @brief 归约写操作
 * @param[in] channel 通道句柄
 * @param[out] dst 目标内存地址
 * @param[in] src 源内存地址
 * @param[in] count 元素个数
 * @param[in] dataType 数据类型
 * @param[in] reduceOp 归约操作类型
 * @return 无
 */
__aicore__ inline void HcommWriteReduceNbi(ChannelHandle channel, __gm__ void *dst, __gm__ void *src,
    uint64_t count, HcclDataType dataType, HcclReduceOp reduceOp);

/**
 * @brief 单边读操作
 * @param[in] thread 线程句柄
 * @param[in] channel 通道句柄
 * @param[out] dst 目标内存地址
 * @param[in] src 源内存地址
 * @param[in] len 数据长度（字节）
 * @return HcclResult 执行结果状态码
 */
extern HcclResult HcommReadNbiOnThread(
    ThreadHandle thread, ChannelHandle channel, void *dst, const void *src, uint64_t len);


/**
 * @brief 单边读操作
 * @param[in] thread 线程句柄
 * @param[in] channel 通道句柄
 * @param[out] dst 目标内存地址
 * @param[in] src 源内存地址
 * @param[in] len 数据长度（字节）
 * @return int32_t 执行结果状态码
 */
extern int32_t HcommReadOnThread(
    ThreadHandle thread, ChannelHandle channel, void *dst, const void *src, uint64_t len);

/**
 * @brief 单边读操作
 * @param[in] channel 通道句柄
 * @param[out] dst 目标内存地址
 * @param[in] src 源内存地址
 * @param[in] len 数据长度（字节）
 * @return 无
 */
__aicore__ inline void HcommReadNbi(ChannelHandle channel, __gm__ void *dst, __gm__ void *src, uint64_t len);

/**
 * @brief 归约读操作
 * @param[in] thread 线程句柄
 * @param[in] channel 通道句柄
 * @param[out] dst 目标内存地址
 * @param[in] src 源内存地址
 * @param[in] count 元素个数
 * @param[in] dataType 数据类型
 * @param[in] reduceOp 归约操作类型
 * @return HcclResult 执行结果状态码
 */
extern HcclResult HcommReadReduceNbiOnThread(ThreadHandle thread, ChannelHandle channel, void *dst, const void *src,
    uint64_t count, HcclDataType dataType, HcclReduceOp reduceOp);

/**
 * @brief 归约读操作
 * @param[in] thread 线程句柄
 * @param[in] channel 通道句柄
 * @param[out] dst 目标内存地址
 * @param[in] src 源内存地址
 * @param[in] count 元素个数
 * @param[in] dataType 数据类型
 * @param[in] reduceOp 归约操作类型
 * @return int32_t 执行结果状态码
 */
extern int32_t HcommReadReduceOnThread(ThreadHandle thread, ChannelHandle channel, void *dst, const void *src, uint64_t count,
    HcommDataType dataType, HcommReduceOp reduceOp);

/**
 * @brief 归约读操作
 * @param[in] channel 通道句柄
 * @param[out] dst 目标内存地址
 * @param[in] src 源内存地址
 * @param[in] count 元素个数
 * @param[in] dataType 数据类型
 * @param[in] reduceOp 归约操作类型
 * @return 无
 */
__aicore__ inline void HcommReadReduceNbi(ChannelHandle channel, __gm__ void *dst, __gm__ void *src, uint64_t count,
    HcclDataType dataType, HcclReduceOp reduceOp);

/** @} */  // 通信通道上内存读写和规约

/**
 * @defgroup 通信通道上同步通知
 * @{
 */

/**
 * @brief 通信通道间记录通知
 * @param[in] thread 线程句柄
 * @param[in] channel 通道句柄
 * @param[in] remoteNotifyIdx 远端通知索引
 * @return HcclResult 执行结果状态码
 */
extern HcclResult HcommNotifyRecordOnThread(ThreadHandle thread, ChannelHandle channel, uint32_t remoteNotifyIdx);

/**
 * @brief 通信通道间记录通知+1
 * @param[in] channel 通道句柄
 * @param[in] remoteNotifyIdx 远端通知索引
 * @return 无
 */
__aicore__ inline void HcommNotifyRecord(ChannelHandle channel, uint32_t remoteNotifyIdx);


/**
 * @brief 通信通道间等待通知
 * @param[in] thread 线程句柄
 * @param[in] channel 通道句柄
 * @param[in] localNotifyIdx 本地通知索引
 * @param[in] timeout 超时时间(毫秒)
 * @return HcclResult 执行结果状态码
 */
extern HcclResult HcommNotifyWaitOnThread(ThreadHandle thread, ChannelHandle channel, uint32_t localNotifyIdx,
    uint32_t timeout);

/**
 * @brief 通信通道间等待通知-1
 * @param[in] channel 通道句柄
 * @param[in] localNotifyIdx 本地通知索引
 * @return 无
 */
__aicore__ inline void HcommNotifyWait(ChannelHandle channel, uint32_t localNotifyIdx);

// \cond

/**
 * @name 通道通知——计数方式（AIV）
 * @{
 */

/**
 * @brief 通信通道间加法计数通知
 * @return HcclResult 执行结果状态码
 */
// __aicore__ inline void HcommChannelNotifyAddCount(ChannelHandle channel, uint32_t remoteNotifyIdx, uint32_t increment);

/**
 * @brief 通信通道间等待通知数值
 * @return HcclResult 执行结果状态码
 */
// __aicore__ inline void HcommNotifyWaitCount(ChannelHandle channel, uint32_t localNotifyIdx,
//     uint32_t expectedValue, uint32_t timeout);

/** @} */  // 通道通知——计数方式（AIV）
// \endcond

/** @} */  // 通信通道上同步通知

/**
 * @defgroup 通信通道上带通知的内存写和规约
 * @{
 */

/**
 * @brief 带通知的单边写操作
 * @param[in] thread 线程句柄
 * @param[in] channel 通道句柄
 * @param[out] dst 目标内存地址
 * @param[in] src 源内存地址
 * @param[in] len 数据长度（字节）
 * @param[in] notifyIdx 远端通知索引
 * @return HcclResult 执行结果状态码
 * @note 当前在A5上主要支持
 */
extern HcclResult HcommWriteWithNotifyNbiOnThread(ThreadHandle thread, ChannelHandle channel, void *dst, const void *src,
    uint64_t len, uint32_t remoteNotifyIdx);


/**
 * @brief 带通知的单边写操作
 * @param[in] thread 线程句柄
 * @param[in] channel 通道句柄
 * @param[out] dst 目标内存地址
 * @param[in] src 源内存地址
 * @param[in] len 数据长度（字节）
 * @param[in] notifyIdx 远端通知索引
 * @return int32_t 执行结果状态码
 * @note 当前在A5上主要支持
 */
extern int32_t HcommWriteWithNotifyOnThread(ThreadHandle thread, ChannelHandle channel, void *dst, const void *src,
    uint64_t len, uint32_t remoteNotifyIdx);

/**
 * @brief 带通知的单边写操作
 * @param[in] channel 通道句柄
 * @param[out] dst 目标内存地址
 * @param[in] src 源内存地址
 * @param[in] len 数据长度（字节）
 * @param[in] remoteNotifyIdx 远端通知索引
 * @return 无
 */
__aicore__ inline void HcommWriteWithNotifyNbi(ChannelHandle channel, __gm__ void *dst, __gm__ void *src,
    uint64_t len, uint32_t remoteNotifyIdx);

/**
 * @brief 带通知的归约写操作
 * @param[in] thread 线程句柄
 * @param[in] channel 通道句柄
 * @param[out] dst 目标内存地址
 * @param[in] src 源内存地址
 * @param[in] count 元素个数
 * @param[in] dataType 数据类型
 * @param[in] reduceOp 归约操作类型
 * @param[in] remoteNotifyIdx 远端通知索引
 * @return HcclResult 执行结果状态码
 * @note 当前在A5上主要支持
 */
extern HcclResult HcommWriteReduceWithNotifyNbiOnThread(ThreadHandle thread, ChannelHandle channel, void *dst, const void *src,
    uint64_t count, HcclDataType dataType, HcclReduceOp reduceOp, uint32_t remoteNotifyIdx);

/**
 * @brief 带通知的归约写操作
 * @param[in] thread 线程句柄
 * @param[in] channel 通道句柄
 * @param[out] dst 目标内存地址
 * @param[in] src 源内存地址
 * @param[in] count 元素个数
 * @param[in] dataType 数据类型
 * @param[in] reduceOp 归约操作类型
 * @param[in] remoteNotifyIdx 远端通知索引
 * @return HcclResult 执行结果状态码
 * @note 当前在A5上主要支持
 */
extern HcclResult HcommWriteReduceWithNotifyOnThread(ThreadHandle thread, ChannelHandle channel, void *dst, const void *src,
    uint64_t count, HcclDataType dataType, HcclReduceOp reduceOp, uint32_t remoteNotifyIdx);

/**
 * @brief 带通知的归约写操作
 * @param[in] channel 通道句柄
 * @param[out] dst 目标内存地址
 * @param[in] src 源内存地址
 * @param[in] count 元素个数
 * @param[in] dataType 数据类型
 * @param[in] reduceOp 归约操作类型
 * @param[in] remoteNotifyIdx 远端通知索引
 * @return 无
 */
__aicore__ inline void HcommWriteReduceWithNotifyNbi(ChannelHandle channel, __gm__ void *dst, __gm__ void *src,
    uint64_t count, HcclDataType dataType, HcclReduceOp reduceOp, uint32_t remoteNotifyIdx);
/** @} */  // 通信通道上带通知的内存写和规约

/**
 * @defgroup 通信通道上内存屏障
 * @{
 * @warning  是阻塞的保序操作，协议的fence，待确定
 */

/**
 * @brief 通信通道级内存屏障操作
 * @param[in] thread 线程句柄
 * @param[in] channel 通道句柄
 * @return HcclResult 执行结果状态码
 * @note 确保该通道上此前的所有任务都已经执行完成
 * @warning  1）其他channel相关的接口，是否都要加上channel？\n
 *          2）channel加了fence，local数据接口是否要由对应的CommLocalFence？——不用，因为当前是阻塞完成的？\n 
 *          3) 参数是否含有channel，有分歧。倾向于有
 */
extern HcclResult HcommChannelFenceOnThread(ThreadHandle thread, ChannelHandle channel);

/** @} */  // 通信通道上内存屏障


/**
 * @defgroup 批量下发设置接口
 * @{
 */


/** @} */  // 批量下发设置接口

/** @} */  // 通信数据面

/**
 * @defgroup 通信控制面
 * @{
 */

/* 网络设备句柄 */
typedef void *EndPointHandle;

typedef struct {
    uint32_t sdid;
    int32_t pid;
} HcommMemGrantInfo;

/**
 * @struct HcommBuf
 * @brief 内存缓冲区描述结构体
 * @var addr   - 虚拟地址指针
 * @var len    - 内存长度（单位字节）
 */
typedef struct {
    void *addr;
    uint64_t len;
} HcommBuf;


/* Socket通信句柄（不透明指针） */
typedef void *HcommSocket;

const uint32_t HCCL_SOCK_CONN_TAG_MAX_SIZE = 192; ///< 握手标识最大长度（含终止符）

/**
 * @name EndPoint管理
 * @{
 */

HcommEndPointGetNum(deviceId, uint32_t *listNum)
HcommEndPointGetEndPoint(int32_t deviceId, EndPoint *endPointList, uint32_t listNum, uint32_t *reallistNum);

/**
 * @brief 通过设备ID获取EndPoint新
 */
//  * @param[in] deviceId 设备物理ID
//  * @param[out] addr 返回的地址信息数组
//  * @param[out] addrNum 返回的地址数量
//  * @return 执行状态码 HcclResult
extern HcclResult HcommEndPointGet(int32_t deviceId, EndPoint **endPointList, uint32_t *listNum);

/**
 * @brief 打开网络端口EndPoint
 * @param[in] endPoint EndPoint初始化配置信息
 * @param[out] endPointHandle 返回的EndPoint句柄
 * @return 执行状态码 HcclResult
 * @note 支持重复打开相同EndPoint
 */
extern HcclResult HcommEndPointCreate(const EndPoint *endPoint, EndPointHandle *endPointHandle);

/**
 * @brief 关闭网络端口EndPoint
 * @param[in] endPointHandle EndPoint句柄
 * @return 执行状态码 HcclResult
 */
extern HcclResult HcommEndPointDestroy(EndPointHandle endPointHandle);
/** @} */  // EndPoint管理


/**
 * @name 内存注册与导入管理
 * @{
 */

/**
 * @brief 注册内存到EndPoint
 */
extern HcclResult HcommMemReg(EndPointHandle endPointHandle, HcclMem mem, void **memHandle);

/**
 * @brief 从EndPoint解内存注册
 */
extern HcclResult HcommMemUnReg(EndPointHandle endPointHandle, void *memHandle);

/**
 * @brief 导出指定内存描述，用于交换
 */
extern HcclResult HcommMemExport(EndPointHandle endPointHandle, const void *memHandle, void **memDesc,
    uint32_t *memDescLen);

/**
 * @brief 基于内存描述，导入获得内存
 * @warning  1、需要确认所有接口是否一定要加上endPointHandle？2、所有接口参数细节带确认 3、看看内存tag是否需要
 */
extern HcclResult HcommMemImport(EndPointHandle endPointHandle, const void *memDesc, uint32_t descLen,
    HcommBuf *outBuf);

/**
 * @brief 关闭内存
 */
extern HcclResult HcommMemClose(EndPointHandle endPointHandle, const HcommBuf *buf);

/**
 * @brief 授权本机内存给指定远端进程
 * @param[in] localBuf 本地缓冲区描述符
 * @param[in] remoteGrantInfo 远端授权目标信息
 * @return 执行状态码 HcclResult
 */
extern HcclResult HcommMemGrant(HcommBuf *localBuf, const HcommMemGrantInfo *remoteGrantInfo);

/**
 * @brief 内存重映射接口
 * @param[in] netDev    目标网络设备
 * @param[in] memArray  内存段数组指针
 * @param[in] arraySize 内存段数组长度
 * @return 执行状态码 HcclResult
 * @attention 需确保内存段已经在目标网络设备注册
 */
extern HcclResult HcommMemRemap(const EndPointHandle endPointHandle, const HcclMem *memArray, uint64_t arraySize);
/** @} */  // 内存注册与导入管理

/**
 * @name 通信通道管理
 * @{
 */


/**
 * @brief 通道描述参数
 * @warning  创建channel的参数需要分析； HccsAttr的定义需要分析（HCCS & UB MEM），或者改名？
 * 可能还要增加CntNotify，其他协议对应的Attr？
 */
typedef struct {
    EndPoint remoteEndPoint; ///< 远端端侧描述
    uint32_t notifyNum;  ///< channel上使用的通知消息数量
    union {
        HccsAttr hccsAttr;
        RoCEAttr roceAttr;
        UbAttr ubAttr;
    };
} HcommChannelDesc;

/**
 * @brief 创建通信通道
 * @warning  提供批量接口，通信引擎？
 */
extern HcclResult HcommChannelCreate(EndPointHandle *endPointHandle, CommEngine engine, HcommChannelDesc *channelDescList,
    uint32_t listNum, const void **memHandleList, uint32_t memHandleListNum, ChannelHandle *channelList);

/**
 * @brief 获取通道通知数量
 * @param[in] channel 通道句柄
 * @param[out] notifyNum 通知槽数量
 * @return HcclResult 执行结果状态码
 * @note 当前约束channel两端的notify资源数量是对等的
 */
extern HcclResult HChannelGetRemoteMem(ChannelHandle channel, uint32_t *notifyNum);

/**
 * @brief 销毁通信通道
 * @param[in] channelList 通道句柄数组
 * @param[in] listNum 列表数量
 * @return HcclResult 执行结果状态码
 */
extern HcclResult HcommChannelDestroy(const ChannelHandle *channelList, uint32_t listNum);

// \cond
/**
 * @brief 获取指定channel的Hccl通信缓存（待确认。）
 * @param[in] channel 通信通道句柄
 * @param[out] buffer Hccl缓存信息
 * @return HcclResult 执行结果状态码
 * @note 获取远端CCL buffer
 * @warning  Channel不能GetHcclBuffer了怎么办？
 */
extern HcclResult HcommChannelGetHcclBuffer(ChannelHandle channel, CommBuffer *buffer);
// \endcond
/**
 * @brief 获取channel中全部的交换获得的远端内存信息
 * @param channel 
 * @param remoteMem 
 * @param memTag 
 * @param memNum 
 * @return HcclResult 
 * @warning  1、补充参数介绍 2、这个基于Channel的接口暂时不对外提供！！！ 3、不提供memTag吧？
 */
extern HcclResult HcommChannelGetRemoteMem(ChannelHandle channel, HcclMem **remoteMem, uint32_t *memNum);

/** @} */  // 引擎资源管理
/**
 * @name 设备socket通信（暂不开放）
 * @{
 */

/**
 * @brief 创建Socket通信实例
 * @param[in] nicDeployment 网卡部署位置（参考HcclNetDevDeployment枚举）
 * @param[in] devicePhyId 物理设备ID
 * @param[in] domain 协议域（如AF_INET/AF_INET6）
 * @param[in] addr 绑定的本地地址（支持IPv4/IPv6）
 * @param[in] addrlen 地址结构体长度
 * @param[out] socket 输出的socket句柄
 * @return 执行状态码 HcclResult
 */
extern HcclResult HcommSocketCreate(HcclNetDevDeployment nicDeployment, int32_t devicePhyId, int domain,
    const struct sockaddr *addr, socklen_t addrlen, HcommSocket *socket);

/**
 * @brief 关闭Socket句柄并释放资源
 * @param[in] socket 要关闭的socket句柄
 * @return 执行状态码 HcclResult
 */
extern HcclResult HcommSocketClose(HcommSocket socket);

/**
 * @brief 设置监听模式（服务端用）
 * @param[in] socket 已创建的socket句柄
 * @param[in] backlog 最大挂起连接数（参考系统SOMAXCONN）
 * @return 执行状态码 HcclResult
 */
extern HcclResult HcommSocketListen(HcommSocket socket, int32_t backlog);

/**
 * @brief 接受客户端连接（非阻塞操作）
 * @param[in] serverSocket 处于监听状态的服务器socket句柄
 * @param[in] handShakeTag 握手标识
 * @param[in] tagLen 标识长度（必须<=HCCL_SOCK_CONN_TAG_MAX_SIZE）
 * @param[out] socket 输出的新连接句柄
 * @return 执行状态码 HcclResult
 */
extern HcclResult HcommSocketAccept(void *serverSocket, char *handShakeTag, uint32_t tagLen, HcommSocket *socket);

/**
 * @brief 客户端发起连接请求（非阻塞操作）
 * @param[in] socket 已初始化的socket句柄
 * @param[in] addr 目标服务器地址
 * @param[in] addrlen 地址结构体长度
 * @param[in] handShakeTag 握手标识
 * @param[in] tagLen 标识长度（必须<=HCCL_SOCK_CONN_TAG_MAX_SIZE）
 * @return 执行状态码 HcclResult
 */
extern HcclResult HcommSocketConnect(
    HcommSocket socket, const struct sockaddr *addr, socklen_t addrlen, char *handShakeTag, uint32_t tagLen);

/**
 * @brief 获取Socket连接状态
 * @param[in] socket 目标socket句柄
 * @param[out] status 状态码输出（0表示正常）
 * @return 执行状态码 HcclResult
 */
extern HcclResult HcommSocketGetStatus(HcommSocket socket, int32_t *status);

/**
 * @brief 发送数据（非阻塞）
 * @param[in] socket 已连接的socket句柄
 * @param[in] data 待发送数据缓冲区
 * @param[in] len 待发送数据长度（字节）
 * @param[out] sendLen 实际发送数据长度（可能部分发送）
 * @return 执行状态码 HcclResult
 */
extern HcclResult HcommSocketISend(HcommSocket socket, void *data, uint64_t len, uint64_t *sendLen);

/**
 * @brief 接收数据（非阻塞）
 * @param[in] socket 已连接的socket句柄
 * @param[out] recvBuf 接收数据缓冲区
 * @param[in] len 缓冲区最大容量
 * @param[out] recvLen 实际接收数据长度
 * @return 执行状态码 HcclResult
 */
extern HcclResult HcommSocketIRecv(HcommSocket socket, void *recvBuf, uint64_t len, uint64_t *recvLen);
/** @} */  // 设备socket通信（暂不开放）


/** @} */  // 通信控制面

/** @} */  // Client-Server通信



/** @} */  // 对用户开放API

/**
 * @defgroup 对组件开放接口
 * @{
 */

 /**
 * @defgroup 通信引擎上下文管理接口
 * @{
 * @note 算子编程可选接口
 */

// \cond
/**
 * @brief 获取或生成一个通信域内指定算子标签的唯一标识
 * @param[in] comm 通信域句柄
 * @param[in] opName 算子名称
 * @param[in] opNameSize 算子名称长度
 * @param[in] customTag 自定义标签
 * @param[in] tagSize 标签长度
 * @param[out] opTagUId 算子标签唯一标识
 * @return HcclResult 执行结果状态码
 * @warning  考虑删除uniqueId的接口
 */
// extern HcclResult HcommGetOpTagUniqueId(HcclComm comm, const char *opName, uint32_t opNameSize, const char *customTag,
    // uint32_t tagSize, uint64_t *opTagUId);

// \cond

/**
 * @brief 通信引擎上下文
 */
// typedef struct {
//     void *ctx;        ///< 引擎上下文
//     uint32_t ctxType; ///< thread数量
//     uint32_t ctxSize; ///< 上下文大小（单位字节）
// } CommEngineCtx;
// \endcond

//  * @param[in] opTag 算子标签（建议包含算子名和标识，最大字符长度为COMM_TAG_LEN_MAX）
/**
 * @brief 创建算子通信引擎上下文
 * @param[in] comm 通信域句柄
 * @param[in] engineTag 引擎标签（最大字符长度为COMM_TAG_LEN_MAX）
 * @param[in] engine 通信引擎类型
 * @param[inout] engineCtx 通信引擎上下文\n
 *                         -size: 申请的ctx内存大小；\n
 *                         -addr: 返回的ctx内存地址；\n
 *                         -type: 返回的ctx内存类型，分host和device。
 * @return HcclResult 执行结果状态码
 * @note 1、由使用者决定ctx的大小，并排布ctx里面的内容\n
 *       2、通信库提供ctx地址空间申请接口，并返回该地址空间的类型{host/device}，不同类型决定地址空间的访问方式\n
 *       3、通信库基于通信域+opTag为key存储ctx地址
 * @warning  1、是否要交换EngineCtx和Ctreate？ 另外，函数名是否要加Engine？其他接口也一样。\n
 *               2、是否考虑将HcommCreateCtx和HcommGetCtx合并成为：\n
 *                 HcommEmplaceCtx(HcclComm comm, const char *opTag, CommEngine engine, HcclMem *engineCtx, bool *found)\n
 *                 这样一是可以减少相似接口，二是在频繁创建ctx场景减少哈希表查询次数，提高少许性能\n
 *               3、opTag是否可变成uint64_t idx，方便内部用线性表替代哈希表提高索引性能，\n
 *                 如： HcommGetOpTagIdx(HcclComm comm, const char *opTag, uint64_t *opTagIdx)
 */
extern HcclResult HcommCreateEngineCtx(HcclComm comm, const char *engineTag, CommEngine engine, HcclMem *engineCtx);

/**
 * @brief 获取算子通信引擎上下文
 * @param[in] comm 通信域句柄
 * @param[in] engineTag 引擎标签（最大字符长度为COMM_TAG_LEN_MAX）
 * @param[in] engine 通信引擎类型
 * @param[out] engineCtx 通信引擎上下文\n
 *                       -size: ctx内存大小；\n
 *                       -addr: ctx内存地址；\n
 *                       -type: ctx内存类型，分host和device。
 * @return HcclResult 执行结果状态码
 * @note 使用者可先查询ctx是否已存在，再决定是否重新申请ctx地址
 * @warning 可以考虑将两个Ctx接口一起优化下
 */
extern HcclResult HcommGetEngineCtx(HcclComm comm, const char *engineTag, CommEngine engine, HcclMem *engineCtx);
// \endcond
/**
 * @brief 获取通信引擎上下文，如果不存在就新创建
 * @param[in] comm 通信域句柄
 * @param[in] engineTag 引擎标签（最大字符长度为COMM_TAG_LEN_MAX）
 * @param[in] engine 通信引擎类型
 * @param[out] engineCtx 通信引擎上下文\n
 *                      -size: ctx内存大小，出入参；\n
 *                      -addr: ctx内存地址；\n
 *                      -type: ctx内存类型，分host和device。
 * @param[out] exist 是否存在
 * @return HcclResult 执行结果状态码
 * @warning 优化HcclMem的方式
 */
extern HcclResult HcommEngineCtxAcquire(HcclComm comm, const char *engineTag, CommEngine engine, HcclMem *engineCtx,
    bool *exist);

/**
 * @brief 销毁通信引擎上下文
 * @param[in] comm 通信域句柄
 * @param[in] engineCtx 通信引擎上下文\n
 *                      -size: ctx内存大小；\n
 *                      -addr: ctx内存地址；\n
 *                      -type: ctx内存类型，分host和device。
 * @return HcclResult 执行结果状态码
 */
extern HcclResult HcommEngineCtxDestroy(HcclComm comm, const HcclMem *engineCtx);

// \cond
/**
 * @brief 创建命名的内存（取代ctx的申请释放接口）
 * 
 * @param[in] comm 通信域句柄
 * @param[in] memTag 内存标识
 * @param[in] memSize 内存大小
 * @param[in] memLocation 内存位置
 * @param[out] mem 内存句柄 
 * @return HcclResult 执行结果状态码
 */
// HcclResult HcommCreateNamedMem(HcclComm comm, const char *memTag, uint32_t memSize,
//     int32_t memLocation, void **mem);

/**
 * @brief 释放命名的内存（取代ctx的申请释放接口）
 * 
 * @param[in] comm 通信域句柄
 * @param[in] memTag 内存标识
 * @param[in] mem 内存句柄
 * @return HcclResult 执行结果状态码
 */
HcclResult HcommFreeNamedMem(HcclComm comm, const char *memTag, const void *mem);
// \endcond
/** @} */  // 通信引擎上下文管理接口
 /** @} */  // 对组件开放接口

#ifdef __cplusplus
}
#endif  // __cplusplus

#endif