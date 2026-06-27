/**
 * Copyright (c) 2025 Huawei Technologies Co., Ltd.
 * This program is free software, you can redistribute it and/or modify it under the terms and conditions of
 * CANN Open Software License Agreement Version 2.0 (the "License").
 * Please refer to the License for details. You may not use this file except in compliance with the License.
 * THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
 * INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
 * See LICENSE in the root of the software repository for the full text of the License.
 */

#include <stdlib.h>
#include <errno.h>
#include "securec.h"
#include "ra_hdc_tlv.h"
#include "ra_rs_err.h"
#include "rs_tlv.h"
#include "ra_adp.h"
#include "ra_adp_tlv.h"

struct RsTlvOps {
    int (*tlvInit)(unsigned int phyId, unsigned int *bufferSize);
    int (*tlvDeinit)(unsigned int phyId);
    int (*tlvRequest)(struct TlvRequestMsgHead *head, char *data);
};

struct RsTlvOps gRaRsTlvOps = {
    .tlvInit = RsTlvInit,
    .tlvDeinit = RsTlvDeinit,
    .tlvRequest = RsTlvRequest,
};

int RaRsTlvInit(char *inBuf, char *outBuf, int *outLen, int *opResult, int rcvBufLen)
{
    union OpTlvInitData *dataOut = (union OpTlvInitData *)(outBuf + sizeof(struct MsgHead));
    union OpTlvInitData *dataIn = (union OpTlvInitData *)(inBuf + sizeof(struct MsgHead));

    HCCP_CHECK_PARAM_LEN_RET_HOST(sizeof(union OpTlvInitData), sizeof(struct MsgHead), rcvBufLen, opResult);

    *opResult = gRaRsTlvOps.tlvInit(dataIn->txData.phyId, &dataOut->rxData.bufferSize);
    CHK_PRT_RETURN(*opResult == -ENOTSUPP, hccp_warn("tlv_init unsuccessful ret[%d]", *opResult), 0);
    if (*opResult != 0) {
        hccp_err("tlv_init failed ret[%d]", *opResult);
    }

    return 0;
}

int RaRsTlvDeinit(char *inBuf, char *outBuf, int *outLen, int *opResult, int rcvBufLen)
{
    union OpTlvDeinitData *dataIn = (union OpTlvDeinitData *)(inBuf + sizeof(struct MsgHead));

    HCCP_CHECK_PARAM_LEN_RET_HOST(sizeof(union OpTlvDeinitData), sizeof(struct MsgHead), rcvBufLen, opResult);

    *opResult = gRaRsTlvOps.tlvDeinit(dataIn->txData.phyId);
    if (*opResult != 0) {
        hccp_err("tlv_deinit failed ret[%d]", *opResult);
    }

    return 0;
}

int RaRsTlvRequest(char *inBuf, char *outBuf, int *outLen, int *opResult, int rcvBufLen)
{
    union OpTlvRequestData *dataIn = (union OpTlvRequestData *)(inBuf + sizeof(struct MsgHead));

    HCCP_CHECK_PARAM_LEN_RET_HOST(sizeof(union OpTlvRequestData), sizeof(struct MsgHead), rcvBufLen, opResult);

    *opResult = gRaRsTlvOps.tlvRequest(&dataIn->txData.head, dataIn->txData.data);
    if (*opResult != 0) {
        hccp_err("tlv_request failed ret[%d]", *opResult);
    }

    return 0;
}
