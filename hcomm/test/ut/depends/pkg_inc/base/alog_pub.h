/**
 * @alog_pub.h
 *
 * Copyright (c) Huawei Technologies Co., Ltd. 2024. All rights reserved.
 *
 * This program is distributed in the hope that it will be useful,
 * but WITHOUT ANY WARRANTY; without even the implied warranty of
 * MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.
 */

#ifndef ALOG_PUB_H_
#define ALOG_PUB_H_

#include <stdint.h>
#include "log_types.h"

#ifdef __cplusplus
extern "C" {
#endif // __cplusplus

/**
 * @ingroup     : alog
 * @brief       : check module debug log level enable or not
 * @param [in]  : moduleId   module id enum, eg: SLOG
 * @param [in]  : level      debug log level, eg: DLOG_ERROR/DLOG_WARN/DLOG_INFO/DLOG_DEBUG
 * @return      : 1: enable, 0: disable
 */
LOG_FUNC_VISIBILITY int32_t AlogCheckDebugLevel(uint32_t moduleId, int32_t level) __attribute((weak));

/**
 * @ingroup     : alog
 * @brief       : record log
 * @param [in]  : moduleId   module id, eg: SLOG
 * @param [in]  : logType    log type, eg: DLOG_TYPE_DEBUG/DLOG_TYPE_RUN
 * @param [in]  : level      log level, eg: DLOG_ERROR/DLOG_WARN/DLOG_INFO/DLOG_DEBUG
 * @return:     : 0: success, other: failed
 */
LOG_FUNC_VISIBILITY int32_t AlogRecord(uint32_t moduleId, uint32_t logType, int32_t level, const char *fmt, ...)
    __attribute((weak)) __attribute__((format(printf, 4, 5)));

#ifdef __cplusplus
}
#endif // __cplusplus
#endif // ALOG_PUB_H_