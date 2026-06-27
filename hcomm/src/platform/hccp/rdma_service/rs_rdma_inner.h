/**
 * Copyright (c) 2025 Huawei Technologies Co., Ltd.
 * This program is free software, you can redistribute it and/or modify it under the terms and conditions of
 * CANN Open Software License Agreement Version 2.0 (the "License").
 * Please refer to the License for details. You may not use this file except in compliance with the License.
 * THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
 * INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
 * See LICENSE in the root of the software repository for the full text of the License.
 */

#ifndef RS_RDMA_INNER_H
#define RS_RDMA_INNER_H

#define RS_WC_NUM 16384
#define RS_QP_ATTR_MIN_RNR_TIMER 12
#define RS_QP_ATTR_TIMEOUT 16
#define RS_QP_ATTR_RETRY_CNT 7
#define RS_QP_ATTR_RNR_RETRY 7
#define RS_QP_ATTR_MAX_SEND_SGE 8
#define RS_QP_ATTR_GID_LEN 16
#define RS_MAX_RD_ATOMIC_NUM 128
#define RS_QP_TX_DEPTH_PEER_ONLINE 4096 // host RDMA adapt
#define RS_MAX_RD_ATOMIC_NUM_PEER_ONLINE 16 // host RDMA adapt
#define RS_BUF_SIZE 2048

enum RsCmdOpcode {
    RS_CMD_QP_INFO = 0x12345678,
    RS_CMD_MR_INFO = 0x12345687,
    RS_CMD_LEN_INFO = 0x12345867,
};

struct RsMrInfo {
    uint32_t cmd;    /* MUST be the first element */

    uint32_t rkey;
    uint64_t addr;
    uint64_t len;
};
#endif // RS_RDMA_INNER_H
