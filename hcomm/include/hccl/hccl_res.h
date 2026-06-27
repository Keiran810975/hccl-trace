/**
 * Copyright (c) 2025 Huawei Technologies Co., Ltd.
 * This program is free software, you can redistribute it and/or modify it under the terms and conditions of
 * CANN Open Software License Agreement Version 2.0 (the "License").
 * Please refer to the License for details. You may not use this file except in compliance with the License.
 * THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
 * INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
 * See LICENSE in the root of the software repository for the full text of the License.
 */

#ifndef HCCL_RES_H
#define HCCL_RES_H

#include <stdint.h>
#include <arpa/inet.h>
#include "securec.h"
#include "acl/acl_rt.h"

#ifdef __cplusplus
extern "C" {
#endif  // __cplusplus

/**
 * @brief 通信域句柄类型（不透明结构）
 */
typedef void *HcclComm;

#ifndef CHANNEL_HANDLE_DEFINED
#define CHANNEL_HANDLE_DEFINED
/**
 * @brief 通道句柄类型
 */
typedef uint64_t ChannelHandle;
#endif

#ifndef THREAD_HANDLE_DEFINED
#define THREAD_HANDLE_DEFINED
/**
 * @brief 线程句柄类型
 */
typedef uint64_t ThreadHandle;
#endif

/**
 * @brief 通信引擎类型枚举
 */
typedef enum {
    COMM_ENGINE_RESERVED = -1,    ///< 保留的通信引擎
    COMM_ENGINE_CPU = 0,          ///< HOST CPU引擎
    COMM_ENGINE_CPU_TS = 1,       ///< HOST CPU TS引擎
    COMM_ENGINE_AICPU = 2,        ///< AICPU引擎
    COMM_ENGINE_AICPU_TS = 3,     ///< AICPU TS引擎
    COMM_ENGINE_AIV = 4,          ///< AIV引擎
    COMM_ENGINE_CCU = 5,          ///< CCU引擎
} CommEngine;

/// HCCL资源标识最大长度（字节）
const uint32_t HCCL_RES_TAG_MAX_LEN = 255;

/**
 * @brief 兼容Abi字段结构体
 */
typedef struct {
    uint32_t version;
    uint32_t magicWord;
    uint32_t size;
    uint32_t reserved;
} CommAbiHeader;

/**
 * @brief 通信协议类型枚举
 */
typedef enum {
    COMM_PROTOCOL_RESERVED = -1,  ///< 保留协议类型
    COMM_PROTOCOL_HCCS = 0,       ///< HCCS协议
    COMM_PROTOCOL_ROCE = 1,       ///< RDMA over Converged Ethernet
    COMM_PROTOCOL_PCIE = 2,       ///< PCIE协议
    COMM_PROTOCOL_SIO = 3,        ///< SIO协议
} CommProtocol;

/**
 * @brief 通信设备地址类别
 */
typedef enum {
    COMM_ADDR_TYPE_RESERVED = -1, ///< 保留地址类型
    COMM_ADDR_TYPE_IP_V4 = 0,     ///< IPv4地址类型
    COMM_ADDR_TYPE_IP_V6 = 1,     ///< IPv6地址类型
    COMM_ADDR_TYPE_ID = 2,         ///< ID地址类型
} CommAddrType;

/**
 * @brief 通信设备地址描述结构体
 * @note 支持CommAddrType的扩展，地址最大长度36字节
 */
typedef struct {
    CommAddrType type;         ///< 通信地址类别
    union {
        uint8_t raws[36];      ///< 通用数据
        struct in_addr addr;   ///< IPv4地址结构
        struct in6_addr addr6; ///< IPv6地址结构
        uint32_t id;           ///< 标识
    };
} CommAddr;

/**
 * @brief 通信设备Endpoint位置类型枚举
 */
typedef enum {
    ENDPOINT_LOC_TYPE_RESERVED = -1, ///< 保留的Endpoint位置
    ENDPOINT_LOC_TYPE_DEVICE = 0,    ///< Endpoint在Device上
    ENDPOINT_LOC_TYPE_HOST = 1,      ///< Endpoint在Host上
} EndpointLocType;

/**
 * @brief Endpoint位置类型结构体
 * @note 支持EndpointLocType的扩展，最大60字节内容
 */
typedef struct {
    EndpointLocType locType;        ///< Endpoint的位置类别
    union {
        uint8_t raws[60];           ///< 通用数据
        struct {
            uint32_t devPhyId;      ///< 设备物理Id
            uint32_t superDevId;    ///< 超节点deviceId
            uint32_t serverIdx;     ///< Server的索引
            uint32_t superPodIdx;   ///< 超节点位置索引
        } device;                   ///< 当locType为DEVICE时使用
        struct {
            uint32_t id;            ///< 普通Id，当locType为HOST等时可能使用
        } host;
    };
} EndpointLoc;

typedef struct {
    CommProtocol protocol;  ///< 通信协议
    CommAddr commAddr;      ///< 通信地址
    EndpointLoc loc;        ///< Endpoint的位置信息
    union {
        uint8_t raws[52];   ///< 通用数据
    };
} EndpointDesc;

inline HcclResult EndpointDescInit(EndpointDesc *endpoint, uint32_t num)
{
    for (uint32_t idx = 0; idx < num; idx++) {
        if (endpoint != nullptr) {
            // 用0xFF填充整个结构体
            (void)memset_s(endpoint, sizeof(EndpointDesc), 0xFF, sizeof(EndpointDesc));
            
            // 显式设置关键字段为无效值
            endpoint->protocol = COMM_PROTOCOL_RESERVED;
            endpoint->commAddr.type = COMM_ADDR_TYPE_RESERVED;
            endpoint->loc.locType = ENDPOINT_LOC_TYPE_RESERVED;
            endpoint++;  // 移动到下一个描述符
        } else {
            return HCCL_E_PTR;
        }
    }
    return HCCL_SUCCESS;
}

const uint32_t HCCL_CHANNEL_MAGIC_WORD = 0x0f0f0f0f;
const uint32_t HCCL_CHANNEL_VERSION = 1;    // HcclChannelDesc更新时，HCCL_CHANNEL_VERSION + 1

/**
 * @brief 通道描述参数
 * @note 1、结构体需要将union内的raws完成初始化，union内及内部的结构体可以在末尾扩展新内容，但是总内存不能超过128字节。
 * union内扩展可以不需自增版本号，但是要增加双向兼容处理逻辑。
 * 2、结构体末尾允许扩展内容，但是每次扩展需要自增版本号，添加新增字段的初始化，且增加双向兼容处理逻辑。
 */
typedef struct {
    CommAbiHeader header;
    uint32_t remoteRank;    ///< 远端rankId
    CommProtocol channelProtocol; ///< 通信协议
    EndpointDesc localEndpoint; ///< 本地网络设备端侧描述
    EndpointDesc remoteEndpoint; ///< 远端网络设备端侧描述
    uint32_t notifyNum;  ///< channel上使用的通知消息数量
    void *memHandles; ///< 注册到通信域的待交换内存句柄
    uint32_t memHandleNum; ///< 注册到通信域的待交换内存句柄数量
    union {
        uint8_t raws[128]; ///< 通用缓存
        struct {
            uint32_t queueNum;        ///< QP数量
            uint32_t retryCnt;        ///< 最大重传次数
            uint32_t retryInterval;   ///< 重传间隔(ms)（对应协议计算公式）
            uint8_t tc;               ///< 流量类别(QoS)
            uint8_t sl;               ///< 服务等级(QoS)
        } roceAttr;
    };
} HcclChannelDesc;

#ifndef LIKELY
#define LIKELY(x) (__builtin_expect(!!(x), 1))
#define UNLIKELY(x) (__builtin_expect(!!(x), 0))
#endif

/**
 * @brief 初始化HcclChannelDesc结构体
 *
 * @param[inout] channelDesc 返回的通道描述参数
 * @param[in] descNum 描述数量
 * @return HcclResult 执行结果状态码
 */
inline HcclResult HcclChannelDescInit(HcclChannelDesc *channelDesc, uint32_t descNum)
{
    for (uint32_t idx = 0; idx < descNum; idx++) {
        if (channelDesc != nullptr) {
            // 先用0xFF填充整个结构体
            (void)memset_s(channelDesc, sizeof(HcclChannelDesc), 0xFF, sizeof(HcclChannelDesc));
            
            // 初始化ABI头信息
            channelDesc->header.version     = HCCL_CHANNEL_VERSION;
            channelDesc->header.magicWord   = HCCL_CHANNEL_MAGIC_WORD;
            channelDesc->header.size        = sizeof(HcclChannelDesc);
            channelDesc->header.reserved    = 0;

            // 初始化关键字段
            channelDesc->remoteRank = ~0U;  // 保持原始无效值标记
            channelDesc->channelProtocol = COMM_PROTOCOL_RESERVED;
            channelDesc->notifyNum  = 0;
            channelDesc->memHandles = nullptr;
            channelDesc->memHandleNum = 0;

            // 显式设置EndpointDesc相关字段为无效值
            if (UNLIKELY(EndpointDescInit(&channelDesc->localEndpoint, 1) != HCCL_SUCCESS) ||
                UNLIKELY(EndpointDescInit(&channelDesc->remoteEndpoint, 1) != HCCL_SUCCESS)) {
                return HCCL_E_INTERNAL;
            }
            channelDesc++;  // 移动到下一个描述符
        } else {
            return HCCL_E_PTR;
        }
    }
    return HCCL_SUCCESS;
}

/**
 * @name 通信内存获取
 * @{
 */
/**
 * @brief 获取通信域中的Hccl缓存(HCCL Buffer)
 * @param[in] comm 通信域句柄
 * @param[out] buffer Hccl缓存地址
 * @param[out] size Hccl缓存大小
 * @return HcclResult 执行结果状态码
 * @warning 重要约束：返回的buffer内存由库内管理，调用者严禁释放
 */
extern HcclResult HcclGetHcclBuffer(HcclComm comm, void **buffer, uint64_t *size);

/**
 * @defgroup 通信引擎资源管理
 * @{
 */

/**
 * @brief 获取通信线程资源
 *
 * @param[in] comm 通信域句柄
 * @param[in] engine 通信引擎类型
 * @param[in] threadNum 线程数量
 * @param[in] notifyNumPerThread 每线程的通知数量
 * @param[out] threads 返回的线程句柄
 * @return HcclResult 执行结果状态码
 */
extern HcclResult HcclThreadAcquire(HcclComm comm, CommEngine engine, uint32_t threadNum,
    uint32_t notifyNumPerThread, ThreadHandle *threads);

/**
 * @brief 基于已有rts stream获取指定notifyNum的通信线程资源
 * @param[in] comm 通信域句柄
 * @param[in] engine 通信引擎类型
 * @param[in] stream stream句柄
 * @param[in] notifyNum 通知数量
 * @param[out] thread 返回的线程句柄
 * @note 当前适用于CPU_TS场景
 * @return HcclResult 执行结果状态码
 */
extern HcclResult HcclThreadAcquireWithStream(HcclComm comm, CommEngine engine, aclrtStream stream,
    uint32_t notifyNum, ThreadHandle *thread);

/** @} */  // 通信引擎资源管理

/**
 * @defgroup 通信通道管理接口
 * @{
 */
/**
 * @brief 基于通信域和给定信息创建通信通道
 * @param[in] comm 通信域句柄
 * @param[in] engine 通信引擎类型
 * @param[in] channelDescs 通道描述列表
 * @param[in] channelNum channel数量
 * @param[out] channels 创建的通道句柄列表
 * @return HcclResult 执行结果状态码
 * @warning 重要约束：channelDescs必须使用HcclChannelDescInit进行初始化
 */
extern HcclResult HcclChannelAcquire(HcclComm comm, CommEngine engine, const HcclChannelDesc *channelDescs,
    uint32_t channelNum, ChannelHandle *channels);

/**
 * @brief 获取指定channel的Hccl通信缓存
 * @param[in] comm 通信域句柄
 * @param[in] channel 通信通道句柄
 * @param[out] buffer Hccl缓存地址
 * @param[out] size Hccl缓存大小
 * @return HcclResult 执行结果状态码
 */
extern HcclResult HcclChannelGetHcclBuffer(HcclComm comm, ChannelHandle channel, void **buffer, uint64_t *size);

 /**
 * @defgroup 通信引擎上下文管理接口（编程控制面可选接口）
 * @{
 */

/**
 * @brief 创建算子通信引擎上下文
 * @param[in] comm 通信域句柄
 * @param[in] ctxTag 引擎标签（最大字符长度为HCCL_RES_TAG_MAX_LEN）
 * @param[in] engine 通信引擎类型
 * @param[in] size ctx内存大小
 * @param[out] ctx 通信引擎上下文
 * @return HcclResult 执行结果状态码
 */
extern HcclResult HcclEngineCtxCreate(HcclComm comm, const char *ctxTag, CommEngine engine, uint64_t size, void **ctx);

/**
 * @brief 获取算子通信引擎上下文
 * @param[in] comm 通信域句柄
 * @param[in] ctxTag 引擎标签（最大字符长度为HCCL_RES_TAG_MAX_LEN）
 * @param[in] engine 通信引擎类型
 * @param[out] ctx 通信引擎上下文
 * @param[out] size ctx内存大小
 * @return HcclResult 执行结果状态码
 * @note 使用者可先查询ctx是否已存在，再决定是否重新申请ctx地址
 */
extern HcclResult HcclEngineCtxGet(HcclComm comm, const char *ctxTag, CommEngine engine, void **ctx, uint64_t *size);

/**
 * @brief 拷贝算子通信引擎上下文
 * @param[in] comm 通信域句柄
 * @param[in] engine 通信引擎类型
 * @param[in] ctxTag 引擎标签（最大字符长度为HCCL_RES_TAG_MAX_LEN）
 * @param[in] srcCtx 拷贝的源引擎
 * @param[in] size 拷贝的ctx内存大小
 * @param[in] dstCtxOffset 拷贝的ctx地址偏移
 * @return HcclResult 执行结果状态码
 * @note 1、目标ctx通过ctxTag获取
 */
extern HcclResult HcclEngineCtxCopy(HcclComm comm, CommEngine engine, const char *ctxTag, const void *srcCtx,
    uint64_t size, uint64_t dstCtxOffset);

#ifdef __cplusplus
}
#endif  // __cplusplus
#endif