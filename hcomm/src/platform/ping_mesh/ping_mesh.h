/**
 * Copyright (c) 2025 Huawei Technologies Co., Ltd.
 * This program is free software, you can redistribute it and/or modify it under the terms and conditions of
 * CANN Open Software License Agreement Version 2.0 (the "License").
 * Please refer to the License for details. You may not use this file except in compliance with the License.
 * THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
 * INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
 * See LICENSE in the root of the software repository for the full text of the License.
 */
 
#ifndef PING_MESH_PUB_H
#define PING_MESH_PUB_H
 
#include <map>
#include <thread>
#include <atomic>
#include "hccl_ip_address.h"
#include "hccl_socket.h"
#include "hdc_pub.h"
#include "network/hccp_common.h"
#include "network/hccp_ping.h"
#include "hccn_rping.h"
 
namespace hccl
{
constexpr u32 ONE_MILLISEC = 1000;
constexpr u32 RPING_INTERFACE_OPCODE= 71;
constexpr u32 RPING_INTERFACE_VERSION = 1;
constexpr u32 RPING_PAYLOAD_LEN_MAX = 1500;
constexpr u64 TSD_EXT_PARA_NUM = 2;
constexpr u32 RPING_SERVICE_LEVEL_DEFAULT = 4;
constexpr u32 RPING_TRAFFIC_CLASS_DEFAULT = 132;

// HCCN接口需要的结构体
struct RpingInput {
    HcclIpAddress sip;
    HcclIpAddress dip;
    int srcPort;   // UDP源端口号，用户配置，参与hash选路
    int reserved;  // 保留字段，用于对齐，暂不使用
    int sl;        // 指定队列
    int tc;        // 主要是修改DSCP
    int port;      // 监听端口
    u32 len;
    char payload[RPING_PAYLOAD_LEN_MAX];
};
 
struct RpingOutput {
    u32 txPkt;     // rping发包总数
    u32 rxPkt;     // rping收包总数
    u32 minRTT;
    u32 maxRTT;
    u32 avgRTT;
    u32 state;
    u32 reserved[2];
};

// 需要重填的payload头只有前136字节，后面是固定的
struct RpingPayloadHead {
    char srcIp[64];
    char dstIp[64];
    u32 payloadLen;
    u32 resvd[3];
    u64 timestamp[8];
    u32 rpingBatchId;
    u8 reserved[44];
};

union RpingIpHead {
    struct {
        u32	versionTclassFlow; // 4bit version, 8bit tclass, 20bit flow label
        u16	payLen;            // ub报文的payload长度
        u8	nextHdr;           // 下一个头部的类型
        u8	hopLimit;          // 最大跳数
        u8 	srcIp[16];         // sip的gid，128bit
        u8 	dstIp[16];         // dip的gid，128bit
    } ipv6;
    
    struct {
        u8  rsvd[20];           // 前20字节为空
        u32 verIhlTosTlen;      // 4bit version, 4bit IHL, 8bit type of service, 16bit total length
        u32 IdFlagsFragOffset;  // 16bit identification, 3bit flags, 13bit fragment offset
        u8  tol;                // time to live
        u8  protocol;           // 协议类型
        u16 headChecksum;
        u32 srcIp;
        u32 dstIp;
    } ipv4;
};
 
enum class RpingState {
    UNINIT,
    INITED,
    READY,
    RUN,
    STOP,
    RESERVED
};
 
enum class RpingLinkState {
    CONNECTED,
    CONNECTING,
    DISCONNECTED,
    TIMEOUT,
    ERROR
};

enum WhiteListStatus {
    WHITE_LIST_CLOSE = 0,
    WHITE_LIST_OPEN = 1
};

class PingMesh {
private:
    PingInitInfo initInfo_ {};                   // 初始化信息
    void *pingHandle_ = nullptr;                   // 记录hccp侧的pingmesh句柄
    std::shared_ptr<HcclSocket> socket_ = nullptr; // 记录server端的socket信息，用于建立rdma链路
    HcclIpAddress *ipAddr_ = nullptr;              // 记录device的ip信息
    u8 *payload_ = nullptr;                        // client侧记录的payload信息
    RpingState rpingState_ = RpingState::UNINIT;   // 记录client状态
    int rpingTargetNum_ = 0;                       // 记录client目标数量
    std::map<std::string, std::shared_ptr<HcclSocket>> socketMaps_;  // 记录client端的socket信息
    std::map<std::string, PingQpInfo> rdmaInfoMaps_;    // 记录target的rdma信息
    std::unique_ptr<std::thread> connThread_;      // server端等待socket建链的背景线程
    HcclNetDevCtx netCtx_ = nullptr;               // 记录网络上下文信息
    std::shared_ptr<HDCommunicate> hdcD2H_ = nullptr; // 从device侧获取数据的接口
    s32 deviceLogicId_ = 0;
    u32 devicePhyId_ = 0;
    bool isDeinited_ = false;
    bool isSocketClosed_ = false;
    std::atomic<bool> connThreadStop_{false};      // 侦听的子线程的结束条件
    bool isUsePayload_ = false;
    std::map<std::string, u32> payloadLenMap_;     // 记录自定义payload的长度
 
    HcclResult RpingSendInitInfo(u32 deviceId, u32 port, HcclIpAddress ipAddr, PingInitInfo initInfo,
        std::shared_ptr<HcclSocket> socket);
    HcclResult RpingRecvTargetInfo(void *clientNetCtx, u32 port, HcclIpAddress ipAddr, PingInitInfo &recvInfo, u32 timeout);
    HcclResult StartSocketThread(u32 deviceId, HcclIpAddress ipAddr, u32 port);
    HcclResult HccnCloseSubProc(u32 deviceId);
    HcclResult HccnRaInit(u32 deviceId);
public:
    PingMesh();
    ~PingMesh();
    HcclResult HccnRpingInit(u32 deviceId, u32 mode, HcclIpAddress ipAddr, u32 port, u32 nodeNum, u32 bufferSize,
                             u32 sl = RPING_SERVICE_LEVEL_DEFAULT, u32 tc = RPING_TRAFFIC_CLASS_DEFAULT);
    HcclResult HccnRpingDeinit(u32 deviceId);
    HcclResult HccnRpingAddTarget(u32 deviceId, u32 targetNum, RpingInput *input, HccnRpingAddTargetConfig *config);
    HcclResult HccnRpingRemoveTarget(u32 deviceId, u32 targetNum, RpingInput *input);
    HcclResult HccnRpingGetTarget(u32 deviceId, u32 targetNum, RpingInput *input, int *targetStat);
    HcclResult HccnRpingBatchPingStart(u32 deviceId, u32 pktNum, u32 interval, u32 timeout);
    HcclResult HccnRpingBatchPingStop(u32 deviceId);
    HcclResult HccnRpingGetResult(u32 deviceId, u32 targetNum, RpingInput *input, RpingOutput *output);
    HcclResult HccnRpingRefillPayloadHead(u8 *originalHead, u32 payloadNum);
    HcclResult HccnRpingGetPayload(u32 deviceId, void **payload, u32 *payloadLen);

    inline s32 GetDeviceLogicId() {
        return deviceLogicId_;
    }
};
 
}
#endif