/*
 * Copyright (c) Huawei Technologies Co., Ltd. 2020-2021. All rights reserved.
 * Description: stream.h
 * Create: 2020-01-01
 */

#ifndef CCE_RUNTIME_RT_EXTERNAL_STREAM_H
#define CCE_RUNTIME_RT_EXTERNAL_STREAM_H

#include <stdlib.h>

#include "rt_external_base.h"

#if defined(__cplusplus)
extern "C" {
#endif

/**
 * @ingroup dvrt_stream
 * @brief create stream instance
 * @param [in] stm   stream hadle
 * @param [out] sqId   stream op sqId
 * @return RT_ERROR_NONE for ok
 * @return RT_ERROR_INVALID_VALUE for error input
 */
RTS_API rtError_t rtStreamGetSqid(const rtStream_t stm, uint32_t *sqId);

/**
 * @ingroup dvrt_stream
 * @brief get stream cq info
 * @param [in] stm   stream hadle
 * @param [out] sqId   stream op cqId
 * @param [out] cqId   stream op logic cqId
 * @return RT_ERROR_NONE for ok
 * @return RT_ERROR_INVALID_VALUE for error input
 */
RTS_API rtError_t rtStreamGetCqid(const rtStream_t stm, uint32_t *cqId, uint32_t *logicCqId);

/*
 * @ingroup dvrt_stream
 * @brief enable debug for dump overflow exception with stream
 * @param [in] addr: ddr address of kernel exception dumpped
 * @param [in] stm: stream handle
 * @param [in] flag: debug flag
 * @return RT_ERROR_NONE for ok
 * @return RT_ERROR_INVALID_VALUE for error input
 */
RTS_API rtError_t rtDebugRegisterForStream(rtStream_t stm, uint32_t flag, const void *addr,
                                           uint32_t *streamId, uint32_t *taskId);

#if defined(__cplusplus)
}
#endif

#endif  // CCE_RUNTIME_RT_EXTERNAL_STREAM_H

