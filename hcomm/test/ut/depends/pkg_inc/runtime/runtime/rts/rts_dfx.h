/*
 * Copyright (c) Huawei Technologies Co., Ltd. 2025-2025. All rights reserved.
 * Description: rts_dfx.h
 * Create: 2025-07-31
 */

#ifndef CCE_RUNTIME_RTS_DFX_H
#define CCE_RUNTIME_RTS_DFX_H

#include <stdlib.h>

#include "base.h"

#if defined(__cplusplus)
extern "C" {
#endif

/**
 * @ingroup rts_profiling
 * @brief Support users customized profiling breakpoint at specified network locations.
 * @param [in] userdata the user data.
 * @param [in] length the data length.
 * @param [in] stream the stream.
 * @return RT_ERROR_NONE for ok.
 * @return other for error.
 */
RTS_API rtError_t rtsProfTrace(void *userdata,  int32_t length , rtStream_t stream);

#if defined(__cplusplus)
}
#endif

#endif  // CCE_RUNTIME_RTS_DFX_H