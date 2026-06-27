/*
 * Copyright (c) Huawei Technologies Co., Ltd. 2025-2025. All rights reserved.
 * Description: rts_ffts.h
 * Create: 2025-03-21
 */

#ifndef CCE_RUNTIME_RTS_FFTS_H
#define CCE_RUNTIME_RTS_FFTS_H

#include <stdlib.h>

#include "base.h"

#if defined(__cplusplus)
extern "C" {
#endif
/**
 * @brief get kernel inter core sync address.
 *
 * @param addr inter core sync address.
 * @param len buffer len
 * @return RT_ERROR_NONE for ok
 * @return RT_ERROR_INVALID_VALUE for error input
 */
RTS_API rtError_t rtsGetInterCoreSyncAddr(uint64_t *addr, uint32_t *len);

#if defined(__cplusplus)
}
#endif

#endif  // CCE_RUNTIME_RTS_FFTS_H