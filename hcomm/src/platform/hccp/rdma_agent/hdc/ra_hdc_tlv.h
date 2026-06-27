/**
 * Copyright (c) 2025 Huawei Technologies Co., Ltd.
 * This program is free software, you can redistribute it and/or modify it under the terms and conditions of
 * CANN Open Software License Agreement Version 2.0 (the "License").
 * Please refer to the License for details. You may not use this file except in compliance with the License.
 * THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
 * INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
 * See LICENSE in the root of the software repository for the full text of the License.
 */

#ifndef RA_HDC_TLV_H
#define RA_HDC_TLV_H

#include "ra_tlv.h"
#include "ra_rs_comm.h"
#include "ra_hdc.h"

union OpTlvInitData {
    struct {
        unsigned int phyId;
        uint32_t reserved[RA_RSVD_NUM_61];
    } txData;

    struct {
        unsigned int bufferSize;
        uint32_t reserved[RA_RSVD_NUM_63];
    } rxData;
};

union OpTlvDeinitData {
    struct {
        unsigned int phyId;
        uint32_t reserved[RA_RSVD_NUM_61];
    } txData;

    struct {
        uint32_t reserved[RA_RSVD_NUM_64];
    } rxData;
};

union OpTlvRequestData {
    struct {
        struct TlvRequestMsgHead head;
        char data[MAX_TLV_MSG_DATA_LEN];
    } txData;

    struct {
        unsigned int recvBytes;
        char recvData[MAX_TLV_MSG_DATA_LEN];
    } rxData;
};

int RaHdcTlvInit(struct RaTlvHandle *tlvHandle);
int RaHdcTlvDeinit(struct RaTlvHandle *tlvHandle);
int RaHdcTlvRequest(struct RaTlvHandle *tlvHandle, unsigned int moduleType,
    struct TlvMsg *sendMsg, struct TlvMsg *recvMsg);
#endif // RA_HDC_TLV_H
